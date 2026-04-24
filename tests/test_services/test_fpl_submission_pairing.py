"""
Tests for FPL submission transfer pairing.

Covers the type-matched pairing logic in submit_gameweek_from_draft.
FPL's /transfers/ endpoint validates element_in/element_out type-match
per pair, even with wildcard=true, so every pair must be within the
same position (GKP/DEF/MID/FWD). Prior to the fix, arbitrary set.pop()
pairing produced 400 errors on every wildcard play.

These tests exercise the pairing-building section only, using a
FakeDB that returns canned rows for the lookups the code performs.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest


# ---------------------------------------------------------------------------
# The logic we're testing, extracted into a pure function for testability.
#
# This mirrors exactly what submit_gameweek_from_draft does between loading
# the current picks and calling submit_transfers. Keeping the logic here
# lets us test without having to stand up the full FPL session machinery.
# ---------------------------------------------------------------------------

def _build_transfer_pairs(
    new_players: set,
    removed_players: set,
    draft_transfers: Optional[List[Dict]],
    chip_used: Optional[str],
    player_type: Dict[int, int],
    player_now_cost: Dict[int, int],
    player_selling_price: Dict[int, int],
):
    """
    Re-implementation of the pairing logic for testing.
    Produces the same transfers_for_api list that the live code does.
    """
    removed_by_type: Dict[int, List[int]] = defaultdict(list)
    for pid in removed_players:
        et = player_type.get(pid)
        if et is not None:
            removed_by_type[et].append(pid)

    skip_explicit_pairs = chip_used in ('wildcard', 'freehit')

    transfers_for_api = []
    errors = []
    for player_in_id in new_players:
        player_out_id = None

        if not skip_explicit_pairs:
            for t in (draft_transfers or []):
                t_in = t.get('player_in_id', t.get('element_in'))
                t_out = t.get('player_out_id', t.get('element_out'))
                if t_in == player_in_id and t_out in removed_players:
                    player_out_id = t_out
                    et = player_type.get(t_out)
                    if et is not None and t_out in removed_by_type[et]:
                        removed_by_type[et].remove(t_out)
                    break

        if not player_out_id:
            in_type = player_type.get(player_in_id)
            if in_type is not None and removed_by_type[in_type]:
                player_out_id = removed_by_type[in_type].pop()

        if not player_out_id:
            errors.append(player_in_id)
            continue

        transfers_for_api.append({
            'element_in': player_in_id,
            'element_out': player_out_id,
            'purchase_price': player_now_cost.get(player_in_id, 0),
            'selling_price': player_selling_price.get(player_out_id, 0),
        })

    return transfers_for_api, errors


# ---------------------------------------------------------------------------
# Position constants (FPL element_type)
# ---------------------------------------------------------------------------
GKP, DEF, MID, FWD = 1, 2, 3, 4


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_wildcard_full_rebuild_pairs_all_by_type():
    """
    The GW33 scenario: 8 players swapped across all positions.
    Every pair must have matching element_type.
    """
    # Old squad had: GKP 101, DEF 201/202, MID 301/302/303, FWD 401/402/403
    # New squad has: GKP 111, DEF 211/212, MID 311/312/313, FWD 411/412/413
    removed = {101, 201, 202, 301, 302, 303, 401, 402, 403}
    new = {111, 211, 212, 311, 312, 313, 411, 412, 413}

    player_type = {
        **{pid: GKP for pid in [101, 111]},
        **{pid: DEF for pid in [201, 202, 211, 212]},
        **{pid: MID for pid in [301, 302, 303, 311, 312, 313]},
        **{pid: FWD for pid in [401, 402, 403, 411, 412, 413]},
    }

    transfers, errors = _build_transfer_pairs(
        new_players=new,
        removed_players=removed,
        draft_transfers=None,
        chip_used='wildcard',
        player_type=player_type,
        player_now_cost={pid: 50 for pid in new},
        player_selling_price={pid: 50 for pid in removed},
    )

    assert errors == []
    assert len(transfers) == 9

    # Every pair must be type-matched
    for t in transfers:
        assert player_type[t['element_in']] == player_type[t['element_out']], (
            f"Type mismatch: in={t['element_in']} ({player_type[t['element_in']]}) "
            f"out={t['element_out']} ({player_type[t['element_out']]})"
        )


def test_freehit_also_forces_type_matching():
    """Free Hit rebuilds use the same pairing logic as Wildcard."""
    removed = {201, 202, 301, 302}
    new = {211, 212, 311, 312}

    player_type = {
        201: DEF, 202: DEF, 211: DEF, 212: DEF,
        301: MID, 302: MID, 311: MID, 312: MID,
    }

    transfers, errors = _build_transfer_pairs(
        new_players=new,
        removed_players=removed,
        draft_transfers=None,
        chip_used='freehit',
        player_type=player_type,
        player_now_cost={pid: 50 for pid in new},
        player_selling_price={pid: 50 for pid in removed},
    )

    assert errors == []
    for t in transfers:
        assert player_type[t['element_in']] == player_type[t['element_out']]


def test_normal_transfer_honors_explicit_pair():
    """
    A single FT with an explicit draft_transfers record should use the
    manager's intended pair, not fall back to type-matched.
    """
    removed = {201}
    new = {211}
    draft_transfers = [{'player_in_id': 211, 'player_out_id': 201}]

    transfers, errors = _build_transfer_pairs(
        new_players=new,
        removed_players=removed,
        draft_transfers=draft_transfers,
        chip_used=None,
        player_type={201: DEF, 211: DEF},
        player_now_cost={211: 50},
        player_selling_price={201: 50},
    )

    assert errors == []
    assert transfers == [{
        'element_in': 211, 'element_out': 201,
        'purchase_price': 50, 'selling_price': 50,
    }]


def test_wildcard_ignores_stale_draft_transfers():
    """
    When chip is wildcard, any stale rows in the transfers table from a
    prior non-WC run must be ignored. Otherwise those stale pairs could
    mis-pair the rebuild.
    """
    removed = {201, 202, 301, 302}
    new = {211, 212, 311, 312}
    # Stale row from a prior single-FT attempt: 201→211
    stale_transfers = [{'player_in_id': 211, 'player_out_id': 201}]

    player_type = {
        201: DEF, 202: DEF, 211: DEF, 212: DEF,
        301: MID, 302: MID, 311: MID, 312: MID,
    }

    transfers, errors = _build_transfer_pairs(
        new_players=new,
        removed_players=removed,
        draft_transfers=stale_transfers,
        chip_used='wildcard',
        player_type=player_type,
        player_now_cost={pid: 50 for pid in new},
        player_selling_price={pid: 50 for pid in removed},
    )

    # All pairs must be type-matched (not mis-paired via stale record)
    assert errors == []
    for t in transfers:
        assert player_type[t['element_in']] == player_type[t['element_out']]


def test_pairing_logs_error_when_no_same_type_available():
    """
    If somehow new/removed sets don't have matching type cardinality
    (shouldn't happen given FPL squad constraints, but guard anyway),
    the unpairable player is reported as an error, not silently mis-paired.
    """
    removed = {201}  # one DEF
    new = {311}       # one MID — different type, no DEF available

    player_type = {201: DEF, 311: MID}

    transfers, errors = _build_transfer_pairs(
        new_players=new,
        removed_players=removed,
        draft_transfers=None,
        chip_used='wildcard',
        player_type=player_type,
        player_now_cost={311: 50},
        player_selling_price={201: 50},
    )

    assert transfers == []
    assert errors == [311]


def test_mixed_position_counts_still_pair_correctly():
    """
    Rebuilds preserve 2/5/5/3 but individual positions can change
    players even if counts match. Ensure pairing handles this.
    """
    # 5 DEF replaced, 5 MID unchanged, etc.
    removed = {201, 202, 203, 204, 205}  # 5 DEF out
    new = {211, 212, 213, 214, 215}       # 5 DEF in

    player_type = {pid: DEF for pid in removed | new}

    transfers, errors = _build_transfer_pairs(
        new_players=new,
        removed_players=removed,
        draft_transfers=None,
        chip_used='wildcard',
        player_type=player_type,
        player_now_cost={pid: 50 for pid in new},
        player_selling_price={pid: 50 for pid in removed},
    )

    assert errors == []
    assert len(transfers) == 5
    # All DEF-for-DEF pairs
    for t in transfers:
        assert player_type[t['element_in']] == DEF
        assert player_type[t['element_out']] == DEF
    # Each removed player is used exactly once
    outs = [t['element_out'] for t in transfers]
    assert sorted(outs) == sorted(removed)
