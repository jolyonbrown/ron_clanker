"""
Keystone 2: run Ron's recorded 2025-26 season through the FULL simulator
(state machine + scoring engine) and reproduce the official record.

This goes beyond the scoring replay (test_replay_2025_26.py): here the
squad evolves from recorded transfers rather than being read per-GW, the
bank evolves from transaction prices, free transfers accrue/freeze under
the chip rules, and Free Hit gameweeks revert. Per gameweek we require:

    - gross points == official event_points
    - hit cost == official event_transfers_cost (incl. the GW36 -28)
    - bank == official bank (exact, all 31 GWs)
    - squad value within 0.2m of official (fixture-time vs deadline-time
      price snapshots differ slightly; 'value' = market value + bank)

Skipped when the live DB or season archive is unavailable.
"""

from pathlib import Path

import pytest

from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.simulate import RonReplayStrategy, simulate_season

ARCHIVE_GLOB = 'data/archives/2025-26_*/fpl_api_snapshots/ron_transfers.json'
_repo = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists() or not list(_repo.glob(ARCHIVE_GLOB)),
    reason='requires live ron_clanker.db and the 2025-26 season archive',
)


@pytest.fixture(scope='module')
def sim():
    with HistoricalDataProvider() as provider:
        result = simulate_season(RonReplayStrategy(provider), provider,
                                 start_gw=8, end_gw=38)
        entries = {gw: provider.entry(gw) for gw in provider.gameweeks()}
    return result, entries


def test_simulates_full_season(sim):
    result, _ = sim
    assert [g.gameweek for g in result.gameweeks] == list(range(8, 39))


def test_points_reproduced(sim):
    result, entries = sim
    bad = [(g.gameweek, g.score.gross_points, entries[g.gameweek].event_points)
           for g in result.gameweeks
           if g.score.gross_points != entries[g.gameweek].event_points]
    assert bad == []


def test_hit_costs_reproduced(sim):
    """Validates the whole FT machine: accrual, banking, AFCON top-up,
    and the WC/FH freeze rule. The GW36 -28 only reconciles if chip GWs
    don't accrue the +1."""
    result, entries = sim
    bad = [(g.gameweek, g.hit_cost, entries[g.gameweek].event_transfers_cost)
           for g in result.gameweeks
           if g.hit_cost != entries[g.gameweek].event_transfers_cost]
    assert bad == []
    by_gw = {g.gameweek: g for g in result.gameweeks}
    assert by_gw[36].hit_cost == 28


def test_bank_reproduced_exactly(sim):
    """Bank evolves purely from recorded transaction prices; Free Hit
    gameweeks must show the persistent (reverted) bank."""
    result, entries = sim
    bad = [(g.gameweek, g.bank, entries[g.gameweek].bank)
           for g in result.gameweeks
           if g.bank != entries[g.gameweek].bank]
    assert bad == []


def test_squad_value_tracks_official(sim):
    result, entries = sim
    diffs = [abs(g.squad_value - entries[g.gameweek].value)
             for g in result.gameweeks]
    assert max(diffs) <= 2  # tenths; price snapshot timing noise


def test_total_season_points(sim):
    result, _ = sim
    assert result.total_net_points == 1704
    assert result.total_hits == 28
