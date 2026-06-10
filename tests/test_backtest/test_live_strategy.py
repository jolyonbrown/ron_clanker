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

    def test_chips_played_legally(self, chips_run):
        """At most one of each chip per half. NOT necessarily all 8: the
        WC organic-gain discount deliberately lets a wildcard expire when
        the rebuild uplift is within prediction noise — on 2025-26 data,
        skipping the first-half WC beat playing it by ~58 points."""
        result, _ = chips_run
        chips = [(g.gameweek, g.chip) for g in result.gameweeks if g.chip]
        assert len(chips) >= 6
        for half, lo, hi in ((1, 8, 19), (2, 20, 38)):
            half_chips = [c for gw, c in chips if lo <= gw <= hi]
            assert len(half_chips) == len(set(half_chips)), \
                f'half {half} repeats a chip: {half_chips}'

    def test_second_half_team_chips_find_the_dgws(self, chips_run):
        """2025-26 had DGWs at GW26/33/36. With DGW-normalized
        predictions the engine must land at least one big team chip
        (BB/TC) on a double gameweek — the pre-tuning engine burned both
        on ordinary single GWs (GW24/31)."""
        result, _ = chips_run
        h2_team_chips = {g.gameweek for g in result.gameweeks
                         if g.chip in ('bboost', '3xc') and g.gameweek >= 20}
        assert h2_team_chips & {26, 33, 36}, \
            f'no second-half BB/TC on a DGW: {sorted(h2_team_chips)}'

    def test_points_regression_floor(self, chips_run):
        # Baseline 1676 with DGW-normalized predictions and tuned chip
        # knobs (was 1660 pre-normalization). Chips must beat the
        # chipless floor; a drop below 1640 means a chip-timing or
        # optimizer regression — investigate before weakening.
        result, _ = chips_run
        assert result.total_net_points >= 1640

    def test_no_hits(self, chips_run):
        result, _ = chips_run
        assert result.total_hits == 0
