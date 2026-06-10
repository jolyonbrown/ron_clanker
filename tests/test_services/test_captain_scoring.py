"""Shared captain scoring (ml/captain_scoring.py) — the live armband
logic, extracted so the backtest can replay it."""

import pytest

from ml.captain_scoring import (
    calculate_captain_score,
    select_captain_and_vice,
)


class FakeDB:
    """history: {player_id: [(gw, points, minutes), ...]};
    fixtures: list of dicts for the fixture query."""

    def __init__(self, history=None, fixtures=None):
        self.history = history or {}
        self.fixtures = fixtures or []

    def execute_query(self, query, params=()):
        if 'total_points' in query:
            pid, before_gw = params
            rows = [
                {'total_points': pts, 'minutes': mins}
                for gw, pts, mins in sorted(self.history.get(pid, []),
                                            reverse=True)
                if gw < before_gw
            ]
            return rows[:6]
        if 'minutes FROM player_gameweek_history' in query:
            pid, before_gw = params
            rows = [
                {'minutes': mins}
                for gw, pts, mins in sorted(self.history.get(pid, []),
                                            reverse=True)
                if gw < before_gw
            ]
            return rows[:3]
        if 'FROM fixtures' in query:
            return self.fixtures
        raise AssertionError(f'unexpected query: {query}')


def player(pid=1, xp=6.0, et=3, team=10):
    return {'player_id': pid, 'element_type': et, 'xP': xp, 'team_id': team}


class TestScore:
    def test_zero_xp_scores_zero(self):
        assert calculate_captain_score(player(xp=0), 20, FakeDB()) == 0.0

    def test_position_ordering_at_equal_xp(self):
        db = FakeDB()
        scores = {
            et: calculate_captain_score(player(et=et), 20, db)
            for et in (1, 2, 3, 4)
        }
        assert scores[4] > scores[3] > scores[2] > scores[1]
        assert scores[1] == pytest.approx(6.0 * 0.25)

    def test_ceiling_bonus_rewards_recent_hauler(self):
        steady = FakeDB({1: [(g, 5, 90) for g in range(14, 20)]})
        hauler = FakeDB({1: [(14, 2, 90), (15, 15, 90), (16, 3, 90),
                             (17, 12, 90), (18, 2, 90), (19, 6, 90)]})
        s_steady = calculate_captain_score(player(), 20, steady)
        s_hauler = calculate_captain_score(player(), 20, hauler)
        assert s_hauler > s_steady

    def test_minutes_penalty_crushes_rotation_risk(self):
        nailed = FakeDB({1: [(g, 4, 90) for g in range(17, 20)]})
        benched = FakeDB({1: [(g, 4, 20) for g in range(17, 20)]})
        s_nailed = calculate_captain_score(player(), 20, nailed)
        s_benched = calculate_captain_score(player(), 20, benched)
        assert s_benched < s_nailed * 0.5

    def test_walk_forward_ignores_future_history(self):
        """A monster haul AFTER the decision GW must not affect the score."""
        past_only = FakeDB({1: [(g, 4, 90) for g in range(15, 20)]})
        with_future = FakeDB({1: [(g, 4, 90) for g in range(15, 20)]
                              + [(25, 20, 90)]})
        a = calculate_captain_score(player(), 20, past_only)
        b = calculate_captain_score(player(), 20, with_future)
        assert a == pytest.approx(b)

    def test_easy_home_fixture_beats_hard_away(self):
        easy_home = FakeDB(fixtures=[{'team_h': 10, 'team_a': 11,
                                      'team_h_difficulty': 2,
                                      'team_a_difficulty': 4}])
        hard_away = FakeDB(fixtures=[{'team_h': 11, 'team_a': 10,
                                      'team_h_difficulty': 2,
                                      'team_a_difficulty': 5}])
        assert calculate_captain_score(player(), 20, easy_home) > \
            calculate_captain_score(player(), 20, hard_away)

    def test_availability_doubt_reduces_score(self):
        p = player()
        doubtful = dict(p, chance_of_playing_next_round=50)
        db = FakeDB()
        assert calculate_captain_score(doubtful, 20, db) == pytest.approx(
            calculate_captain_score(p, 20, db) * 0.5
        )


class TestSelect:
    def test_returns_top_two_by_score(self):
        xi = [player(pid=1, xp=4.0, et=3),
              player(pid=2, xp=8.0, et=3),
              player(pid=3, xp=6.0, et=3)]
        cap, vice = select_captain_and_vice(xi, 20, FakeDB())
        assert (cap, vice) == (2, 3)

    def test_handles_short_xi(self):
        cap, vice = select_captain_and_vice([player(pid=7)], 20, FakeDB())
        assert cap == 7 and vice is None
