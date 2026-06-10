"""
The live optimizer stack (MILP squad build + TransferOptimizer + MILP XI)
runs as a backtest Strategy over the recorded 2025-26 season.

This is the A/B harness for optimizer changes: edit the live code, re-run,
compare seasons. The assertions here are the regression guard —

    - the season completes under strict rule enforcement
    - zero vetoes: a veto means the live code recommended an ILLEGAL
      transfer (budget or club rule) that the simulator had to block.
      That is a live-code defect; fix the optimizer, don't relax this.
    - a points floor well under the current baseline (1624 at the time
      of writing) but well above naive-greedy (1469). If this trips, an
      optimizer change made Ron meaningfully worse against last season —
      investigate before weakening the bound.

Skipped without the live DB (predictions + prices needed).
"""

import logging

import pytest

from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.live_strategy import (
    LiveOptimizerStrategy,
    LiveOptimizerWithChipsStrategy,
)
from backtest.simulate import simulate_season

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists(),
    reason='requires live ron_clanker.db',
)

logging.getLogger('ron_clanker').setLevel(logging.ERROR)


@pytest.fixture(scope='module')
def live_run():
    with HistoricalDataProvider() as provider:
        strategy = LiveOptimizerStrategy(provider)
        try:
            result = simulate_season(strategy, provider, start_gw=8, end_gw=38)
        finally:
            strategy.close()
        return result, strategy


@pytest.fixture(scope='module')
def chips_run():
    with HistoricalDataProvider() as provider:
        strategy = LiveOptimizerWithChipsStrategy(provider)
        try:
            result = simulate_season(strategy, provider, start_gw=8, end_gw=38)
        finally:
            strategy.close()
        return result, strategy


def test_completes_all_gameweeks(live_run):
    result, _ = live_run
    assert [g.gameweek for g in result.gameweeks] == list(range(8, 39))


def test_no_illegal_recommendations(live_run):
    _, strategy = live_run
    assert strategy.vetoed == []


def test_points_regression_floor(live_run):
    result, _ = live_run
    assert result.total_net_points >= 1550


def test_stays_within_free_transfers(live_run):
    # The live TransferOptimizer never recommends hits; if hits appear,
    # its FT accounting (or this wrapper's) broke.
    result, _ = live_run
    assert result.total_hits == 0


def test_bank_never_negative(live_run):
    result, _ = live_run
    assert all(g.bank >= 0 for g in result.gameweeks)


class TestChipAwareStrategy:
    """The live ChipStrategyService deciding chips over a replayed season.

    First run of this harness surfaced two live-code bugs (Free Hit
    assuming a fresh £100m budget; TransferOptimizer ignoring the
    max-3-per-club rule). Both are fixed; zero vetoes is the contract.
    """

    def test_completes_all_gameweeks(self, chips_run):
        result, _ = chips_run
        assert [g.gameweek for g in result.gameweeks] == list(range(8, 39))

    def test_no_illegal_recommendations(self, chips_run):
        _, strategy = chips_run
        assert strategy.vetoed == []

    def test_all_eight_chips_played_legally(self, chips_run):
        result, _ = chips_run
        chips = [(g.gameweek, g.chip) for g in result.gameweeks if g.chip]
        assert len(chips) == 8
        for half, lo, hi in ((1, 8, 19), (2, 20, 38)):
            half_chips = [c for gw, c in chips if lo <= gw <= hi]
            assert sorted(half_chips) == ['3xc', 'bboost', 'freehit', 'wildcard'], \
                f'half {half} chips: {half_chips}'

    def test_points_regression_floor(self, chips_run):
        # Baseline 1660 at the time of writing. Chips must add value over
        # the chipless floor (1550); a drop below 1580 means a chip-timing
        # or optimizer regression — investigate before weakening.
        result, _ = chips_run
        assert result.total_net_points >= 1580

    def test_no_hits(self, chips_run):
        result, _ = chips_run
        assert result.total_hits == 0
