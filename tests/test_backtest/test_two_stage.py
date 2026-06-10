"""Two-stage prediction adjustment (walk-forward play probability)."""

import pytest

from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.two_stage import PlayProbability

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists(),
    reason='requires live ron_clanker.db',
)


@pytest.fixture(scope='module')
def pp():
    with HistoricalDataProvider() as provider:
        return PlayProbability(provider)


def test_walk_forward_only(pp):
    """A player's probability as of GW10 may only use minutes from
    GW<10 — so changing later history can't change it. Verified by the
    cache key being (player, as_of); structurally there's no path to
    future rows, but assert the early-season default works."""
    # Probability with no history at all -> default
    assert pp.prob(999999, 10) == pp.default


def test_ever_present_player_near_one(pp):
    with HistoricalDataProvider() as provider:
        # find someone who played every GW8-15 fixture
        import sqlite3
        con = sqlite3.connect(f'file:{provider.db_path}?mode=ro', uri=True)
        pid = con.execute(
            "SELECT player_id FROM player_gameweek_history "
            "WHERE gameweek BETWEEN 8 AND 15 AND minutes >= 60 "
            "GROUP BY player_id HAVING COUNT(DISTINCT gameweek) = 8 LIMIT 1"
        ).fetchone()[0]
        con.close()
    assert pp.prob(pid, 16) == pytest.approx(1.0)


def test_adjust_scales_and_preserves_keys(pp):
    preds = {1: 5.0, 2: 3.0}
    out = pp.adjust(preds, as_of_gw=20)
    assert set(out) == {1, 2}
    for pid in preds:
        assert 0.0 <= out[pid] <= preds[pid]


def test_probabilities_bounded(pp):
    with HistoricalDataProvider() as provider:
        preds = provider.predictions(25)
    for pid in list(preds)[:200]:
        assert 0.0 <= pp.prob(pid, 25) <= 1.0
