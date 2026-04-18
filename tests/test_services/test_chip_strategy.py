"""
Tests for the horizon-based chip strategy.

Covers:
- Bench Boost EV = sum of bench xP (not sum of all 15 or all players)
- Triple Captain searches all 15 squad members for best target
- Triple Captain returns captain_override when best != pre-chosen captain
- Deadline pressure forces a chip when chips_available >= gws_remaining
- Hold logic: play now only when EV(now) ≥ threshold × max EV(future)
- Bench detection uses squad slot (pos > 11) not multiplier
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from services.chip_availability import ChipDefinition, ChipStatus
from services.chip_strategy import (
    BB_AUTOSUB_HAIRCUT,
    BENCH_BOOST,
    FREE_HIT,
    TRIPLE_CAPTAIN,
    WILDCARD,
    ChipDecision,
    ChipStrategyService,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeDB:
    """Minimal stand-in for data.database.Database that returns canned rows."""

    def __init__(
        self,
        predictions: Dict[int, Dict[int, float]],  # {gw: {player_id: xp}}
        player_meta: Optional[Dict[int, Dict]] = None,
    ):
        self.predictions = predictions
        self.player_meta = player_meta or {}

    def execute_query(self, query: str, params=()):
        q = query.lower()
        if 'from player_predictions' in q:
            if 'between ? and ?' in q:
                start_gw, end_gw = params
                out = []
                for gw in range(start_gw, end_gw + 1):
                    for pid, xp in self.predictions.get(gw, {}).items():
                        out.append({
                            'player_id': pid, 'gameweek': gw,
                            'predicted_points': xp,
                        })
                return out
            # Single-gameweek query
            if ' in (' in q:
                gw, *ids = params
                preds = self.predictions.get(gw, {})
                return [
                    {'player_id': pid, 'predicted_points': preds.get(pid, 0.0)}
                    for pid in ids if pid in preds
                ]
            gw = params[0]
            return [
                {'player_id': pid, 'predicted_points': xp}
                for pid, xp in self.predictions.get(gw, {}).items()
            ]
        if 'from players where id in' in q:
            return [
                {'id': pid, **meta}
                for pid, meta in self.player_meta.items()
                if pid in params
            ]
        return []


class FakeAvailability:
    """Return a fixed set of ChipStatus objects ignoring team_id/GW."""

    def __init__(self, chips: List[ChipStatus]):
        self._chips = chips

    def get_available_chips(self, team_id, current_gw):
        return list(self._chips)


def _make_chip(name: str, start: int = 20, stop: int = 38, number: int = 2,
               used: bool = False, expires_soon: bool = False,
               gws_until_expiry: int = 99) -> ChipStatus:
    chip_type = 'transfer' if name in {'wildcard', 'freehit'} else 'team'
    return ChipStatus(
        definition=ChipDefinition(
            id=hash(name) & 0xffff,
            name=name,
            number=number,
            start_event=start,
            stop_event=stop,
            chip_type=chip_type,
        ),
        used=used,
        used_in_gw=None,
        used_at=None,
        available_now=not used,
        gws_until_expiry=gws_until_expiry,
        expires_soon=expires_soon,
    )


def _make_squad() -> List[Dict]:
    """
    Reference 15-player squad. Slots 1-11 are the XI, 12-15 are bench.
    element_type follows FPL: 1 GKP, 2 DEF, 3 MID, 4 FWD.
    """
    return [
        # Starting XI: 1 GKP, 4 DEF, 4 MID, 2 FWD
        {'id': 101, 'position': 1, 'element_type': 1, 'multiplier': 1, 'is_captain': False, 'team_id': 1},
        {'id': 201, 'position': 2, 'element_type': 2, 'multiplier': 1, 'is_captain': False, 'team_id': 2},
        {'id': 202, 'position': 3, 'element_type': 2, 'multiplier': 1, 'is_captain': False, 'team_id': 3},
        {'id': 203, 'position': 4, 'element_type': 2, 'multiplier': 1, 'is_captain': False, 'team_id': 4},
        {'id': 204, 'position': 5, 'element_type': 2, 'multiplier': 1, 'is_captain': False, 'team_id': 5},
        {'id': 301, 'position': 6, 'element_type': 3, 'multiplier': 1, 'is_captain': False, 'team_id': 6},
        {'id': 302, 'position': 7, 'element_type': 3, 'multiplier': 1, 'is_captain': False, 'team_id': 7},
        {'id': 303, 'position': 8, 'element_type': 3, 'multiplier': 1, 'is_captain': False, 'team_id': 8},
        {'id': 304, 'position': 9, 'element_type': 3, 'multiplier': 1, 'is_captain': False, 'team_id': 9},
        {'id': 401, 'position': 10, 'element_type': 4, 'multiplier': 2, 'is_captain': True,  'team_id': 10},
        {'id': 402, 'position': 11, 'element_type': 4, 'multiplier': 1, 'is_captain': False, 'team_id': 11},
        # Bench (slots 12-15). Multiplier is 1 in draft_team even for bench.
        {'id': 102, 'position': 12, 'element_type': 1, 'multiplier': 1, 'is_captain': False, 'team_id': 12},
        {'id': 205, 'position': 13, 'element_type': 2, 'multiplier': 1, 'is_captain': False, 'team_id': 13},
        {'id': 305, 'position': 14, 'element_type': 3, 'multiplier': 1, 'is_captain': False, 'team_id': 14},
        {'id': 403, 'position': 15, 'element_type': 4, 'multiplier': 1, 'is_captain': False, 'team_id': 15},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bench_detection_uses_squad_slot_not_multiplier():
    """All draft_team rows have multiplier=1 except the captain; bench must
    still be detected via slot 12-15."""
    svc = ChipStrategyService(database=None)
    enriched = svc._enrich_squad(_make_squad())
    bench_ids = [p['id'] for p in enriched if p['is_bench']]
    assert bench_ids == [102, 205, 305, 403]


def test_bench_boost_ev_sums_only_bench():
    """BB EV should equal sum of bench xP × autosub haircut."""
    predictions = {
        33: {
            # Starters - high xP
            101: 5.0, 201: 6.0, 202: 6.0, 203: 6.0, 204: 6.0,
            301: 7.0, 302: 7.0, 303: 7.0, 304: 7.0,
            401: 9.0, 402: 8.0,
            # Bench - modest xP
            102: 3.0, 205: 4.0, 305: 2.0, 403: 5.0,
        }
    }
    svc = ChipStrategyService(
        database=FakeDB(predictions),
        availability_service=FakeAvailability([_make_chip(BENCH_BOOST)]),
    )
    plans = svc.plan_all_chips(
        team_id=1, current_gw=33, squad=_make_squad(), free_transfers=1,
    )
    bb = plans[BENCH_BOOST]
    # Only GWs within the chip window that have predictions count; but our
    # chip window is 33-38 and we only fed GW33, so other GWs have 0.
    expected = (3.0 + 4.0 + 2.0 + 5.0) * BB_AUTOSUB_HAIRCUT
    assert bb.ev_by_gw[33] == pytest.approx(expected, abs=0.01)


def test_triple_captain_searches_all_15_not_just_pre_chosen_captain():
    """TC EV should find the highest-xP squad member, not just p[is_captain]."""
    squad = _make_squad()
    predictions = {
        33: {
            101: 2.0, 201: 2.0, 202: 2.0, 203: 2.0, 204: 2.0,
            301: 2.0, 302: 2.0, 303: 2.0, 304: 2.0,
            401: 5.0,   # pre-chosen captain
            402: 2.0,
            102: 1.0, 205: 1.0, 305: 1.0,
            403: 12.0,  # bench player with ridiculous xP — TC target!
        }
    }
    svc = ChipStrategyService(
        database=FakeDB(predictions),
        availability_service=FakeAvailability([_make_chip(TRIPLE_CAPTAIN)]),
    )
    plans = svc.plan_all_chips(
        team_id=1, current_gw=33, squad=squad, free_transfers=1,
    )
    tc = plans[TRIPLE_CAPTAIN]
    # Best target should be player 403 (12.0 xP), not the pre-chosen captain
    assert tc.ev_by_gw[33] == pytest.approx(12.0, abs=0.01)
    target = tc.captain_target_by_gw[33]
    assert target[0] == 403


def test_triple_captain_decision_carries_captain_override():
    """When TC fires and best target != current captain, decision must carry
    captain_override so the manager can swap the armband."""
    squad = _make_squad()
    # Haaland-shaped: big xP now, smaller later. Expires soon so we force play.
    preds = {
        33: {
            401: 6.0,   # pre-chosen captain
            304: 15.0,  # actually the best TC target
            **{pid: 2.0 for pid in [101, 201, 202, 203, 204, 301, 302, 303, 402, 102, 205, 305, 403]},
        },
    }
    # Expire at GW33 → force use
    chip = _make_chip(TRIPLE_CAPTAIN, start=33, stop=33,
                      expires_soon=True, gws_until_expiry=0)
    svc = ChipStrategyService(
        database=FakeDB(preds),
        availability_service=FakeAvailability([chip]),
    )
    decision = svc.get_recommended_chip(
        team_id=1, gameweek=33, squad=squad, free_transfers=1,
    )
    assert decision is not None
    assert decision.chip_name == TRIPLE_CAPTAIN
    assert decision.use_chip
    assert decision.captain_override == 304


def test_deadline_pressure_forces_bb_when_only_one_gw_remains():
    """When chips_available >= gws_remaining, must play the chip even without
    a high-EV target. Verifies BB is eligible for force-play (was not before)."""
    squad = _make_squad()
    # Tiny bench xP but one GW left, chip available → must play
    preds = {33: {pid: 1.0 for pid in [101, 201, 202, 203, 204, 301, 302, 303, 304, 401, 402, 102, 205, 305, 403]}}
    chip = _make_chip(BENCH_BOOST, start=33, stop=33,
                      expires_soon=True, gws_until_expiry=0)
    svc = ChipStrategyService(
        database=FakeDB(preds),
        availability_service=FakeAvailability([chip]),
    )
    decision = svc.get_recommended_chip(
        team_id=1, gameweek=33, squad=squad, free_transfers=1,
    )
    assert decision is not None
    assert decision.chip_name == BENCH_BOOST
    assert decision.use_chip
    assert decision.urgency == 'HIGH'
    assert 'FORCED' in decision.reason


def test_hold_when_future_gw_clearly_better():
    """When a future GW has much higher EV, don't play now."""
    squad = _make_squad()
    # Bench xP low now, very high in GW34
    preds = {
        33: {pid: 1.0 for pid in [101, 201, 202, 203, 204, 301, 302, 303, 304, 401, 402, 102, 205, 305, 403]},
        34: {
            **{pid: 1.0 for pid in [101, 201, 202, 203, 204, 301, 302, 303, 304, 401, 402]},
            102: 10.0, 205: 10.0, 305: 10.0, 403: 10.0,
        },
    }
    chip = _make_chip(BENCH_BOOST, start=33, stop=38)
    svc = ChipStrategyService(
        database=FakeDB(preds),
        availability_service=FakeAvailability([chip]),
    )
    decision = svc.get_recommended_chip(
        team_id=1, gameweek=33, squad=squad, free_transfers=1,
    )
    # GW34 EV (40 × 0.8 = 32) is far higher than GW33 (4 × 0.8 = 3.2),
    # so we should NOT play now.
    assert decision is None


def test_play_now_when_current_gw_is_the_best():
    """When current GW is the peak EV, fire the chip."""
    squad = _make_squad()
    preds = {
        33: {
            **{pid: 1.0 for pid in [101, 201, 202, 203, 204, 301, 302, 303, 304, 401, 402]},
            102: 10.0, 205: 10.0, 305: 10.0, 403: 10.0,  # huge bench now
        },
        34: {pid: 1.0 for pid in [101, 201, 202, 203, 204, 301, 302, 303, 304, 401, 402, 102, 205, 305, 403]},
    }
    chip = _make_chip(BENCH_BOOST, start=33, stop=38)
    svc = ChipStrategyService(
        database=FakeDB(preds),
        availability_service=FakeAvailability([chip]),
    )
    decision = svc.get_recommended_chip(
        team_id=1, gameweek=33, squad=squad, free_transfers=1,
    )
    assert decision is not None
    assert decision.chip_name == BENCH_BOOST
    assert decision.use_chip


def test_chip_plan_to_dict_roundtrip():
    """ChipPlan.to_dict should serialize without exceptions."""
    preds = {33: {401: 5.0, 102: 3.0}}
    svc = ChipStrategyService(
        database=FakeDB(preds),
        availability_service=FakeAvailability([_make_chip(BENCH_BOOST)]),
    )
    plans = svc.plan_all_chips(
        team_id=1, current_gw=33, squad=_make_squad(), free_transfers=1,
    )
    for p in plans.values():
        d = p.to_dict()
        assert 'chip_name' in d
        assert 'ev_by_gw' in d
        assert 'best_gw' in d


def test_best_xi_xp_respects_formation_minimums():
    """Best XI requires 1 GKP, ≥3 DEF, ≥2 MID, ≥1 FWD; can't fill 11 with
    just high-xP midfielders."""
    svc = ChipStrategyService(database=None)
    squad = _make_squad()
    # Midfielders dominate xP but formation constraints still apply
    preds = {
        101: 1.0,  # GKP (forced pick)
        201: 0.1, 202: 0.1, 203: 0.1, 204: 0.1,  # DEF (3 forced)
        301: 20.0, 302: 20.0, 303: 20.0, 304: 20.0,  # MID (all in)
        401: 0.1, 402: 0.1,  # FWD (1 forced)
        102: 0.1, 205: 0.1, 305: 0.1, 403: 0.1,
    }
    xp = svc._best_xi_xp(svc._enrich_squad(squad), preds)
    # 1 GKP (1.0) + 3 DEF (0.3) + 4 MID (80) + 1 FWD (0.1) + 2 flex slots
    # Flex slots can add 1 more DEF (0.1) and 1 more FWD (0.1) or stay at MID max
    # MID max is 5; we have 4 MID. Flex can pick 1 more MID? No, we already took all 4.
    # So flex picks 2 more from remaining DEF/FWD: 0.1 each = 0.2
    # Total: 1.0 + 0.3 + 80 + 0.1 + 0.2 = 81.6
    assert xp == pytest.approx(81.6, abs=0.5)
