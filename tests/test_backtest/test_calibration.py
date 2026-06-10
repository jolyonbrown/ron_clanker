"""Walk-forward prediction calibration (winner's-curse shrinkage)."""

import pytest

from backtest.calibration import PredictionShrinker
from backtest.data import DEFAULT_DB, HistoricalDataProvider

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists(),
    reason='requires live ron_clanker.db',
)


@pytest.fixture(scope='module')
def shrinker():
    with HistoricalDataProvider() as provider:
        s = PredictionShrinker(provider)
        # touch a few param sets while the provider is open
        s.params_as_of(8)
        s.params_as_of(12)
        s.params_as_of(25)
        return s


def test_identity_until_enough_history(shrinker):
    # Predictions start GW8; fewer than 3 completed GWs -> identity
    assert shrinker.params_as_of(8) is None
    preds = {1: 5.0, 2: 0.0}
    assert shrinker.shrink(preds, as_of_gw=8) == preds


def test_fits_compress_after_history(shrinker):
    params = shrinker.params_as_of(25)
    assert params is not None
    assert set(params) == {1, 2, 3, 4}
    for et, (a, b) in params.items():
        # Measured season-wide slopes are 0.73-0.85; walk-forward fits
        # should land in a sane compressing band, never inflate wildly.
        assert 0.4 < b < 1.1, f'position {et} slope {b}'


def test_shrink_monotone_within_position(shrinker):
    with HistoricalDataProvider() as p:
        etypes = p.player_element_types()
    mids = [pid for pid, et in etypes.items() if et == 3][:3]
    preds = {mids[0]: 2.0, mids[1]: 5.0, mids[2]: 9.0}
    out = shrinker.shrink(preds, as_of_gw=25)
    assert out[mids[0]] <= out[mids[1]] <= out[mids[2]]
    assert all(v >= 0 for v in out.values())


def test_high_predictions_shrink_proportionally_more(shrinker):
    with HistoricalDataProvider() as p:
        etypes = p.player_element_types()
    fwd = next(pid for pid, et in etypes.items() if et == 4)
    out = shrinker.shrink({fwd: 8.0}, as_of_gw=25)
    # A top-of-ranking 8.0 must come down (measured realization ~0.7)
    assert out[fwd] < 8.0


def test_no_lookahead_in_params(shrinker):
    """Params as of GW12 may only use GW8-11 pairs — they must differ
    from the full-season fit (GW25) unless the season were stationary
    to numerical precision, which it isn't."""
    early = shrinker.params_as_of(12)
    late = shrinker.params_as_of(25)
    assert early is not None and late is not None
    assert early != late
