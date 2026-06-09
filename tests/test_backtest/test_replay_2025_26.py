"""
Keystone validation: replay Ron's actual 2025-26 season and reproduce
the official FPL scores from raw per-player data.

season_team_history stores POST-autosub picks (the FPL API rearranges
positions once a GW finishes), so the lock-time replay reconstructs the
deadline selection by inverting the recorded automatic_subs, then
requires the engine to re-derive FPL's substitutions, armband and score
for all 31 gameweeks — including 3 vice-captain promotions, 9 autosubs,
3 DGWs and all 8 chips.

Runs against the live database plus the season archive; skipped when
either is unavailable (e.g. CI without data).
"""

from pathlib import Path

import pytest

from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.replay import replay_season
from backtest.scoring import BENCH_BOOST

ARCHIVE_GLOB = 'data/archives/2025-26_*/fpl_api_snapshots/ron_picks_by_gw.json'
_repo = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.skipif(
    not DEFAULT_DB.exists() or not list(_repo.glob(ARCHIVE_GLOB)),
    reason='requires live ron_clanker.db and the 2025-26 season archive',
)


@pytest.fixture(scope='module')
def replays():
    with HistoricalDataProvider() as provider:
        return replay_season(provider, mode='lock_time')


def test_replays_full_season(replays):
    assert len(replays) == 31  # Ron entered at GW8
    assert [r.gameweek for r in replays] == list(range(8, 39))


def test_official_points_reproduced_every_gameweek(replays):
    mismatches = [
        (r.gameweek, r.computed.gross_points, r.official_points)
        for r in replays
        if not r.points_match
    ]
    assert mismatches == []


def test_bench_points_reproduced_every_gameweek(replays):
    mismatches = [
        (r.gameweek, r.computed.bench_points, r.official_bench_points)
        for r in replays
        if not r.bench_match
    ]
    assert mismatches == []


def test_effective_captain_matches_official_armband(replays):
    """Covers the 3 vice-captain promotions (GW11, 28, 33)."""
    mismatches = [r.gameweek for r in replays if not r.captain_match]
    assert mismatches == []


def test_autosubs_match_fpl_exactly_outside_bench_boost(replays):
    mismatches = [
        (r.gameweek, r.computed.autosubs, r.official_autosubs)
        for r in replays
        if r.active_chip != BENCH_BOOST and not r.autosubs_match
    ]
    assert mismatches == []


def test_bench_boost_quirk_no_scoring_autosubs(replays):
    """FPL records positional autosubs under Bench Boost, but they have no
    scoring effect (all 15 score). The engine must derive none — and the
    points must still match, proving the recorded sub was cosmetic."""
    for r in replays:
        if r.active_chip == BENCH_BOOST:
            assert r.computed.autosubs == []
            assert r.points_match


def test_hard_paths_were_exercised(replays):
    """Guard against this suite passing vacuously on future data."""
    assert sum(len(r.computed.autosubs) for r in replays) >= 5
    chips = {r.active_chip for r in replays if r.active_chip}
    assert {'wildcard', 'freehit', 'bboost', '3xc'} <= chips
    assert any(r.transfer_cost > 0 for r in replays)
