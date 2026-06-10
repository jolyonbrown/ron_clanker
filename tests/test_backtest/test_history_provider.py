"""
HistoricalSeasonProvider — past seasons reconstructed from
historical_gameweek_data (positions inferred from scoring arithmetic,
teams from fixture structure).
"""

import pytest

from backtest.data import DEFAULT_DB
from backtest.history_provider import HistoricalSeasonProvider
from backtest.state import SQUAD_SHAPE

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists(),
    reason='requires live ron_clanker.db with historical_gameweek_data',
)


@pytest.fixture(scope='module')
def provider():
    return HistoricalSeasonProvider('2023-24')


def test_full_season_coverage(provider):
    assert provider.gameweeks() == list(range(1, 39))


def test_keeper_identification_is_exact(provider):
    """Every player who recorded a save must be classed GK — the saves
    rule is the one inference signal that cannot be confounded by
    FPL's between-season position reclassifications."""
    etypes = provider.player_element_types()
    savers = {r['player_code'] for r in provider._rows if r['saves']}
    assert savers, 'sanity: season has keepers'
    assert all(etypes[pid] == 1 for pid in savers)


def test_position_pools_can_field_legal_squads(provider):
    etypes = provider.player_element_types()
    counts = {et: 0 for et in (1, 2, 3, 4)}
    for et in etypes.values():
        counts[et] += 1
    for et, need in SQUAD_SHAPE.items():
        assert counts[et] >= need * 4, f'position {et} pool too thin: {counts}'


def test_teams_partition_into_twenty_clubs(provider):
    teams = provider.player_team_ids()
    clubs = set(teams.values())
    assert len(clubs) == 20


def test_fixture_counts_sane(provider):
    for gw in (1, 19, 38):
        fc = provider.fixture_counts(gw)
        # A normal GW has 10 fixtures => 20 club-fixture slots
        assert 14 <= sum(fc.values()) <= 24
        assert all(1 <= n <= 2 for n in fc.values())


def test_prices_and_actuals_align(provider):
    prices = provider.prices(10)
    actuals = provider.actuals(10)
    assert len(prices) > 400
    assert all(35 <= v <= 160 for v in prices.values())
    assert set(actuals) <= set(provider.player_element_types())


def test_predictions_walk_forward_and_dgw_aware(provider):
    # GW1 has no history -> empty predictions (greedy falls back to ppg,
    # which is also empty -> all-zero xP, still a legal squad)
    assert provider.predictions(1) == {}
    preds = provider.predictions(20)
    assert len(preds) > 200
    assert all(v >= 0 for v in preds.values())


def test_inference_agrees_with_join_on_stable_players(provider):
    """Strong-evidence inference should agree with the 2025-26 players
    table for MOST joined players; disagreements are dominated by FPL's
    between-season reclassifications, so demand 75%+ not 100%."""
    agree = total = 0
    rows_by_player = {}
    for r in provider._rows:
        rows_by_player.setdefault(r['player_code'], []).append(r)
    for code, rows in rows_by_player.items():
        known = provider._known.get(code)
        if not known:
            continue
        inferred, strong = provider._infer_position(rows)
        if not strong:
            continue
        total += 1
        agree += inferred == known[0]
    assert total > 150
    assert agree / total > 0.75
