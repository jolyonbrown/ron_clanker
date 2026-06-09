"""
Smoke test: the greedy model-following baseline completes a full
simulated season under strict rule enforcement.

The simulator validates everything as it goes (squad shape, club rule,
budget, FT accounting, lineup == squad), so simply finishing 31
gameweeks without an exception is most of the assertion.
"""

from pathlib import Path

import pytest

from backtest.baselines import GreedyModelStrategy
from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.simulate import simulate_season

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists(),
    reason='requires live ron_clanker.db',
)


@pytest.fixture(scope='module')
def greedy_result():
    with HistoricalDataProvider() as provider:
        return simulate_season(GreedyModelStrategy(), provider,
                               start_gw=8, end_gw=38)


def test_completes_all_gameweeks(greedy_result):
    assert [g.gameweek for g in greedy_result.gameweeks] == list(range(8, 39))


def test_never_takes_hits_by_construction(greedy_result):
    assert greedy_result.total_hits == 0
    assert all(g.n_transfers <= 1 for g in greedy_result.gameweeks)


def test_scores_plausibly(greedy_result):
    # A degenerate strategy (illegal lineups would raise; fielding
    # blanking players or junk would crater the score) lands far below
    # this. 31 GWs at even 30 pts/GW is 930.
    assert greedy_result.total_net_points > 930


def test_bank_never_negative(greedy_result):
    assert all(g.bank >= 0 for g in greedy_result.gameweeks)
