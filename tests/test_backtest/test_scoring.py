"""Unit tests for the backtest scoring engine (synthetic squads)."""

import pytest

from backtest.scoring import (
    BENCH_BOOST,
    TRIPLE_CAPTAIN,
    GK, DEF, MID, FWD,
    Pick,
    PlayerGW,
    score_gameweek,
)


def make_squad(captain_id=8, vice_id=9):
    """A standard 15: GK, 4 DEF, 4 MID, 2 FWD starting; GK, DEF, MID, FWD bench.

    player_id == position for readability (1-15).
    """
    types = {
        1: GK, 2: DEF, 3: DEF, 4: DEF, 5: DEF,
        6: MID, 7: MID, 8: MID, 9: MID, 10: FWD, 11: FWD,
        12: GK, 13: DEF, 14: MID, 15: FWD,
    }
    return [
        Pick(
            player_id=pos,
            position=pos,
            element_type=types[pos],
            is_captain=(pos == captain_id),
            is_vice_captain=(pos == vice_id),
        )
        for pos in range(1, 16)
    ]


def all_played(points_by_id):
    """Stats where every listed player played 90 and scored given points."""
    return {pid: PlayerGW(points=pts, minutes=90) for pid, pts in points_by_id.items()}


def flat_stats(points=2, minutes=90, ids=range(1, 16)):
    return {pid: PlayerGW(points=points, minutes=minutes) for pid in ids}


class TestBasicScoring:
    def test_everyone_plays_captain_doubles(self):
        stats = flat_stats(points=2)
        score = score_gameweek(make_squad(), stats)
        # 11 starters x 2pts + captain doubled once more = 24
        assert score.gross_points == 24
        assert score.effective_captain == 8
        assert score.bench_points == 8
        assert score.autosubs == []

    def test_triple_captain(self):
        stats = flat_stats(points=2)
        score = score_gameweek(make_squad(), stats, chip=TRIPLE_CAPTAIN)
        assert score.gross_points == 26  # 22 + 2 extra captain doublings

    def test_bench_boost_counts_all_15_no_autosubs(self):
        stats = dict(flat_stats(points=2))
        stats[5] = PlayerGW(points=0, minutes=0)  # a starter blanks
        score = score_gameweek(make_squad(), stats, chip=BENCH_BOOST)
        # 14 players x 2 + captain extra 2; blanked starter stays (no subs on BB)
        assert score.gross_points == 30
        assert score.autosubs == []
        assert score.bench_points == 0

    def test_transfer_cost_deducted_from_net_only(self):
        stats = flat_stats(points=2)
        score = score_gameweek(make_squad(), stats, transfer_cost=8)
        assert score.gross_points == 24
        assert score.net_points == 16

    def test_unknown_players_score_zero(self):
        # Stats dict missing most players entirely (blank GW behaviour)
        stats = all_played({8: 10})
        score = score_gameweek(make_squad(), stats)
        assert score.gross_points == 20  # captain only, doubled


class TestCaptaincy:
    def test_vice_inherits_when_captain_blank(self):
        stats = dict(flat_stats(points=2))
        stats[8] = PlayerGW(points=0, minutes=0)  # captain no-show
        score = score_gameweek(make_squad(), stats)
        assert score.effective_captain == 9
        # Captain subbed out for first eligible bench outfielder (13, DEF ok)
        assert (8, 13) in score.autosubs
        # 11 effective starters x 2 + vice doubled = 24
        assert score.gross_points == 24

    def test_no_armband_when_captain_and_vice_blank(self):
        stats = dict(flat_stats(points=2))
        stats[8] = PlayerGW(points=0, minutes=0)
        stats[9] = PlayerGW(points=0, minutes=0)
        score = score_gameweek(make_squad(), stats)
        assert score.effective_captain is None
        # 9 surviving starters + 2 subs (13, 14) all at x1
        assert score.gross_points == 22

    def test_captain_multiplier_recorded(self):
        stats = flat_stats(points=2)
        score = score_gameweek(make_squad(), stats)
        assert score.multipliers[8] == 2
        assert score.multipliers[1] == 1
        assert score.multipliers[12] == 0


class TestAutosubs:
    def test_gk_only_replaced_by_bench_gk(self):
        stats = dict(flat_stats(points=2))
        stats[1] = PlayerGW(points=0, minutes=0)  # starting GK no-show
        score = score_gameweek(make_squad(), stats)
        assert (1, 12) in score.autosubs
        assert score.multipliers[12] == 1

    def test_gk_not_replaced_when_bench_gk_also_blank(self):
        stats = dict(flat_stats(points=2))
        stats[1] = PlayerGW(points=0, minutes=0)
        stats[12] = PlayerGW(points=0, minutes=0)
        score = score_gameweek(make_squad(), stats)
        assert score.autosubs == []
        assert score.gross_points == 22  # 10 starters x2 + captain extra

    def test_bench_priority_order_respected(self):
        stats = dict(flat_stats(points=2))
        stats[6] = PlayerGW(points=0, minutes=0)  # MID starter out
        score = score_gameweek(make_squad(), stats)
        # First bench outfielder (13, DEF) keeps formation valid -> used first
        assert score.autosubs == [(6, 13)]

    def test_formation_constraint_skips_invalid_sub(self):
        # XI with exactly 3 DEF: a blanked DEF can only be replaced by a DEF
        types = {
            1: GK, 2: DEF, 3: DEF, 4: DEF,
            5: MID, 6: MID, 7: MID, 8: MID, 9: MID,
            10: FWD, 11: FWD,
            12: GK, 13: MID, 14: DEF, 15: FWD,
        }
        squad = [
            Pick(player_id=pos, position=pos, element_type=types[pos],
                 is_captain=(pos == 8), is_vice_captain=(pos == 9))
            for pos in range(1, 16)
        ]
        stats = dict(flat_stats(points=2))
        stats[2] = PlayerGW(points=0, minutes=0)  # DEF out, only 3 in XI
        score = score_gameweek(squad, stats)
        # Bench order is MID(13), DEF(14), FWD(15): MID would leave 2 DEF -> skip
        assert score.autosubs == [(2, 14)]

    def test_last_forward_must_be_replaced_by_forward(self):
        # XI with exactly 1 FWD
        types = {
            1: GK, 2: DEF, 3: DEF, 4: DEF, 5: DEF,
            6: MID, 7: MID, 8: MID, 9: MID, 10: MID,
            11: FWD,
            12: GK, 13: DEF, 14: MID, 15: FWD,
        }
        squad = [
            Pick(player_id=pos, position=pos, element_type=types[pos],
                 is_captain=(pos == 8), is_vice_captain=(pos == 9))
            for pos in range(1, 16)
        ]
        stats = dict(flat_stats(points=2))
        stats[11] = PlayerGW(points=0, minutes=0)  # the only FWD blanks
        score = score_gameweek(squad, stats)
        assert score.autosubs == [(11, 15)]

    def test_multiple_autosubs(self):
        stats = dict(flat_stats(points=2))
        stats[6] = PlayerGW(points=0, minutes=0)
        stats[10] = PlayerGW(points=0, minutes=0)
        score = score_gameweek(make_squad(), stats)
        assert score.autosubs == [(6, 13), (10, 14)]
        assert score.gross_points == 24

    def test_bench_points_reflect_post_autosub_bench(self):
        stats = dict(flat_stats(points=2))
        stats[6] = PlayerGW(points=0, minutes=0)
        stats[13] = PlayerGW(points=5, minutes=90)  # sub comes on with 5
        score = score_gameweek(make_squad(), stats)
        assert (6, 13) in score.autosubs
        # Bench now: 12 (2), 14 (2), 15 (2), plus blanked starter 6 (0)
        assert score.bench_points == 6


class TestValidation:
    def test_rejects_wrong_squad_size(self):
        with pytest.raises(ValueError):
            score_gameweek(make_squad()[:14], {})
