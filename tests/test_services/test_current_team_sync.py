"""
Tests for sync_current_team_from_fpl chip-aware walk-back.

The public /event/{gw}/picks/ endpoint returns the squad as it existed
at the start of that gameweek's deadline. For Free Hit gameweeks it
returns the temporary FH squad — but FPL reverts to the pre-FH squad
once the GW ends, so syncing from an FH GW's picks gives the wrong
state for the next selection.

GW36 2026-05-09 lost -28 points to this — manager planned 2 transfers
off a stale FH-squad baseline, submission found 9 differences vs FPL's
actual post-revert state.

These tests verify the walk-back logic skips Free Hit GWs and uses
the previous GW's squad (which is what FPL actually has).
"""

from unittest.mock import patch

import pytest

from scripts.track_ron_team import sync_current_team_from_fpl


def _mock_bootstrap():
    """Minimal bootstrap response with one player."""
    return {
        'elements': [
            {'id': 100, 'web_name': 'TestPlayer', 'now_cost': 50,
             'element_type': 1, 'team': 1},
        ],
        'teams': [{'id': 1, 'name': 'Test FC', 'short_name': 'TST'}],
        'events': [],
    }


def _mock_pick(element_id):
    return {
        'element': element_id, 'position': 1,
        'is_captain': False, 'is_vice_captain': False, 'multiplier': 1,
    }


@pytest.fixture
def mock_db():
    """Mock the Database class so tests don't touch the real DB."""
    with patch('data.database.Database') as mock_cls:
        instance = mock_cls.return_value
        # Track inserts so tests can verify what got synced
        instance._inserted = []

        def fake_update(query, params=()):
            if 'INSERT INTO current_team' in query:
                instance._inserted.append(params)
            return 1

        instance.execute_update.side_effect = fake_update
        yield instance


def test_no_chip_uses_current_event_picks(mock_db):
    """Normal GW (no chip) → use current_event picks directly."""
    with patch('scripts.track_ron_team.fetch_bootstrap_data', return_value=_mock_bootstrap()), \
         patch('scripts.track_ron_team.fetch_team_entry', return_value={'current_event': 36}), \
         patch('scripts.track_ron_team.build_purchase_price_map', return_value={}), \
         patch('scripts.track_ron_team.fetch_team_picks') as fetch_picks:

        gw36_picks = {'active_chip': None, 'picks': [_mock_pick(100)]}
        fetch_picks.return_value = gw36_picks

        result = sync_current_team_from_fpl(team_id=12222054)

        assert result is True
        # Only one call — no walk-back
        assert fetch_picks.call_count == 1
        assert fetch_picks.call_args[0] == (12222054, 36)


def test_freehit_walks_back_one_gw(mock_db):
    """FH in current_event → walk back to current_event - 1."""
    with patch('scripts.track_ron_team.fetch_bootstrap_data', return_value=_mock_bootstrap()), \
         patch('scripts.track_ron_team.fetch_team_entry', return_value={'current_event': 35}), \
         patch('scripts.track_ron_team.build_purchase_price_map', return_value={}), \
         patch('scripts.track_ron_team.fetch_team_picks') as fetch_picks:

        # GW35 had FH, GW34 was wildcard (permanent — no further walk-back)
        responses = {
            35: {'active_chip': 'freehit', 'picks': [_mock_pick(200)]},
            34: {'active_chip': 'wildcard', 'picks': [_mock_pick(100)]},
        }
        fetch_picks.side_effect = lambda tid, gw: responses[gw]

        result = sync_current_team_from_fpl(team_id=12222054)

        assert result is True
        # Two fetches: GW35 (saw FH), then GW34 (no walk-back from WC)
        called_gws = [c[0][1] for c in fetch_picks.call_args_list]
        assert called_gws == [35, 34]
        # The synced squad must be GW34's, not GW35's
        synced_player_id = mock_db._inserted[0][0]
        assert synced_player_id == 100  # GW34 player


def test_wildcard_does_not_walk_back(mock_db):
    """WC squad is permanent — no walk-back even though it's a transfer chip."""
    with patch('scripts.track_ron_team.fetch_bootstrap_data', return_value=_mock_bootstrap()), \
         patch('scripts.track_ron_team.fetch_team_entry', return_value={'current_event': 34}), \
         patch('scripts.track_ron_team.build_purchase_price_map', return_value={}), \
         patch('scripts.track_ron_team.fetch_team_picks') as fetch_picks:

        fetch_picks.return_value = {
            'active_chip': 'wildcard',
            'picks': [_mock_pick(100)],
        }

        result = sync_current_team_from_fpl(team_id=12222054)

        assert result is True
        assert fetch_picks.call_count == 1


def test_team_chips_do_not_walk_back(mock_db):
    """Triple Captain / Bench Boost don't change squad composition."""
    with patch('scripts.track_ron_team.fetch_bootstrap_data', return_value=_mock_bootstrap()), \
         patch('scripts.track_ron_team.fetch_team_entry', return_value={'current_event': 36}), \
         patch('scripts.track_ron_team.build_purchase_price_map', return_value={}), \
         patch('scripts.track_ron_team.fetch_team_picks') as fetch_picks:

        fetch_picks.return_value = {
            'active_chip': '3xc',
            'picks': [_mock_pick(100)],
        }

        result = sync_current_team_from_fpl(team_id=12222054)

        assert result is True
        assert fetch_picks.call_count == 1


def test_consecutive_freehits_walk_back_multiple_times(mock_db):
    """Edge case: back-to-back FHs (rare but possible if both halves used)."""
    with patch('scripts.track_ron_team.fetch_bootstrap_data', return_value=_mock_bootstrap()), \
         patch('scripts.track_ron_team.fetch_team_entry', return_value={'current_event': 19}), \
         patch('scripts.track_ron_team.build_purchase_price_map', return_value={}), \
         patch('scripts.track_ron_team.fetch_team_picks') as fetch_picks:

        # GW19 FH, GW18 also FH (would imply two FHs but illustrates loop), GW17 normal
        responses = {
            19: {'active_chip': 'freehit', 'picks': [_mock_pick(300)]},
            18: {'active_chip': 'freehit', 'picks': [_mock_pick(200)]},
            17: {'active_chip': None, 'picks': [_mock_pick(100)]},
        }
        fetch_picks.side_effect = lambda tid, gw: responses[gw]

        result = sync_current_team_from_fpl(team_id=12222054)

        assert result is True
        called_gws = [c[0][1] for c in fetch_picks.call_args_list]
        assert called_gws == [19, 18, 17]
        # Final synced squad is GW17's
        assert mock_db._inserted[0][0] == 100


def test_explicit_gameweek_argument_still_walks_back(mock_db):
    """If caller passes gameweek=N and N had FH, still walk back."""
    with patch('scripts.track_ron_team.fetch_bootstrap_data', return_value=_mock_bootstrap()), \
         patch('scripts.track_ron_team.fetch_team_entry', return_value={'current_event': 36}), \
         patch('scripts.track_ron_team.build_purchase_price_map', return_value={}), \
         patch('scripts.track_ron_team.fetch_team_picks') as fetch_picks:

        responses = {
            35: {'active_chip': 'freehit', 'picks': [_mock_pick(200)]},
            34: {'active_chip': None, 'picks': [_mock_pick(100)]},
        }
        fetch_picks.side_effect = lambda tid, gw: responses[gw]

        result = sync_current_team_from_fpl(team_id=12222054, gameweek=35)

        assert result is True
        called_gws = [c[0][1] for c in fetch_picks.call_args_list]
        assert called_gws == [35, 34]
