"""
Tests for DecisionSynthesisEngine memoization.

Covers:
- Second call with same gameweek returns cached dict without re-running.
- Different gameweek triggers a fresh synthesis.
- invalidate_cache() forces a recompute.
- Fresh rows in player_predictions skip the ML inference loop.
- Stale rows (older than TTL) trigger a re-run.
- Missing rows trigger a re-run.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from agents.synthesis.engine import DecisionSynthesisEngine


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeDB:
    """Minimal stand-in returning canned rows for freshness-check queries."""

    def __init__(self, predictions=None, newest=None):
        # predictions: dict of {player_id: xp} for the target GW
        # newest: datetime of most recent created_at; None = no rows
        self.predictions = predictions or {}
        self.newest = newest

    def execute_query(self, query, params=()):
        q = query.lower()
        if 'count(*)' in q and 'max(created_at)' in q:
            if self.newest is None:
                return [{'row_count': 0, 'newest': None}]
            return [{
                'row_count': len(self.predictions),
                'newest': self.newest.isoformat(sep=' '),
            }]
        if 'select player_id, predicted_points' in q:
            return [
                {'player_id': pid, 'predicted_points': xp}
                for pid, xp in self.predictions.items()
            ]
        return []


def _make_engine(db: FakeDB) -> DecisionSynthesisEngine:
    """Build an engine bypassing heavy initialisation."""
    eng = DecisionSynthesisEngine.__new__(DecisionSynthesisEngine)
    eng.db = db
    eng.config = {}
    eng.current_gw = None
    eng.ml_predictions = {}
    eng.intelligence_cache = {}
    eng._cached_recs_gw = None
    eng._cached_recs = None
    eng._predictions_cache_ttl_hours = 24
    return eng


# ---------------------------------------------------------------------------
# In-process memoization on synthesize_recommendations
# ---------------------------------------------------------------------------

def test_second_call_returns_cached_without_rerun():
    db = FakeDB()
    eng = _make_engine(db)
    eng._cached_recs_gw = 33
    eng._cached_recs = {'gameweek': 33, 'strategy': 'sentinel'}

    # No patch: if it tried to run the real path it would crash on missing
    # intelligence services. The cache short-circuit must return first.
    result = eng.synthesize_recommendations(33)
    assert result == {'gameweek': 33, 'strategy': 'sentinel'}


def test_different_gameweek_bypasses_cache():
    db = FakeDB()
    eng = _make_engine(db)
    eng._cached_recs_gw = 33
    eng._cached_recs = {'gameweek': 33}

    # Different GW should not return cached dict. Patch the heavy path so
    # the test doesn't actually run synthesis — we only need to prove the
    # cache was bypassed.
    with patch.object(
        DecisionSynthesisEngine, 'run_ml_predictions', return_value={1: 5.0}
    ), patch.object(
        DecisionSynthesisEngine, 'gather_intelligence', return_value={}
    ), patch.object(
        DecisionSynthesisEngine, '_determine_strategy', return_value={}
    ), patch.object(
        DecisionSynthesisEngine, '_rank_players_by_value', return_value=[]
    ), patch.object(
        DecisionSynthesisEngine, '_recommend_captain', return_value={}
    ), patch.object(
        DecisionSynthesisEngine, '_identify_transfer_targets', return_value=[]
    ), patch.object(
        DecisionSynthesisEngine, '_identify_template_risks', return_value=[]
    ):
        result = eng.synthesize_recommendations(34)

    assert result['gameweek'] == 34
    assert eng._cached_recs_gw == 34  # cache updated to new GW


def test_invalidate_cache_forces_recompute():
    db = FakeDB()
    eng = _make_engine(db)
    eng._cached_recs_gw = 33
    eng._cached_recs = {'gameweek': 33, 'tag': 'stale'}

    eng.invalidate_cache()
    assert eng._cached_recs_gw is None
    assert eng._cached_recs is None


# ---------------------------------------------------------------------------
# Cross-process freshness via player_predictions
# ---------------------------------------------------------------------------

def test_fresh_db_rows_short_circuit_ml_inference():
    predictions = {101: 5.0, 102: 3.5, 103: 7.2}
    db = FakeDB(predictions=predictions, newest=datetime.now() - timedelta(hours=2))
    eng = _make_engine(db)

    # If run_ml_predictions called the heavy path, it would try to load
    # models and iterate players — we don't mock those because the
    # freshness check MUST short-circuit before any of that runs.
    result = eng.run_ml_predictions(33)
    assert result == {101: 5.0, 102: 3.5, 103: 7.2}


def test_stale_db_rows_force_rerun():
    predictions = {101: 5.0}
    # TTL default is 24h — 48h old is definitely stale
    db = FakeDB(predictions=predictions, newest=datetime.now() - timedelta(hours=48))
    eng = _make_engine(db)

    cached = eng._load_cached_predictions(33)
    assert cached is None


def test_missing_db_rows_force_rerun():
    db = FakeDB(predictions={}, newest=None)
    eng = _make_engine(db)

    cached = eng._load_cached_predictions(33)
    assert cached is None


def test_unparseable_timestamp_forces_rerun():
    predictions = {101: 5.0}
    db = FakeDB(predictions=predictions, newest="not-a-date")
    eng = _make_engine(db)
    # Override the attribute that FakeDB uses to format; keep raw string
    db.newest = "not-a-date"

    # Patch the isoformat call chain - we want the fallback branch tested.
    class CrankyDB(FakeDB):
        def execute_query(self, query, params=()):
            q = query.lower()
            if 'count(*)' in q:
                return [{'row_count': 1, 'newest': 'garbage-string'}]
            return []

    eng2 = _make_engine(CrankyDB())
    cached = eng2._load_cached_predictions(33)
    assert cached is None


# ---------------------------------------------------------------------------
# End-to-end: full synthesize_recommendations flow uses cache chain
# ---------------------------------------------------------------------------

def test_dgw_multiplier_doubles_dgw_players():
    """
    _apply_dgw_multiplier should double the xP of players whose teams
    have two fixtures, leave SGW players alone, and zero blanking
    players. This is the fix for GW36 2026-05-09 where TC went to
    Fernandes (1 fix, 6.58 per-fixture) over Haaland (2 fix, 6.03
    per-fixture but ~12 GW-total).
    """
    class DGWFakeDB(FakeDB):
        def execute_query(self, query, params=()):
            q = query.lower()
            if 'team_h' in q and 'union all' in q:
                # Two fixtures for team_id=1 (DGW), one for team_id=2 (SGW),
                # zero for team_id=3 (blank)
                return [
                    {'team_id': 1}, {'team_id': 1},  # DGW
                    {'team_id': 2},                  # SGW
                ]
            if 'select id, team_id from players' in q:
                return [
                    {'id': 100, 'team_id': 1},  # DGW player
                    {'id': 200, 'team_id': 2},  # SGW player
                    {'id': 300, 'team_id': 3},  # blank player
                ]
            return super().execute_query(query, params)

    db = DGWFakeDB(predictions={})
    eng = _make_engine(db)
    raw = {100: 6.0, 200: 5.0, 300: 4.0}

    adjusted = eng._apply_dgw_multiplier(raw, gameweek=36)

    assert adjusted[100] == 12.0  # DGW: 6.0 × 2
    assert adjusted[200] == 5.0   # SGW: unchanged
    assert adjusted[300] == 0.0   # Blank: zeroed
    # input dict shouldn't be mutated
    assert raw[100] == 6.0


def test_dgw_multiplier_handles_unknown_team():
    """If a player's team_id can't be resolved, leave xP alone."""
    class StrangeFakeDB(FakeDB):
        def execute_query(self, query, params=()):
            q = query.lower()
            if 'team_h' in q and 'union all' in q:
                return [{'team_id': 1}, {'team_id': 1}]
            if 'select id, team_id from players' in q:
                return []  # No team mapping returned
            return super().execute_query(query, params)

    db = StrangeFakeDB(predictions={})
    eng = _make_engine(db)
    raw = {100: 6.0}

    adjusted = eng._apply_dgw_multiplier(raw, gameweek=36)

    assert adjusted[100] == 6.0  # untouched fallback


def test_dgw_multiplier_empty_predictions_returns_empty():
    db = FakeDB(predictions={})
    eng = _make_engine(db)
    assert eng._apply_dgw_multiplier({}, gameweek=36) == {}


def test_full_flow_uses_db_cache_and_memoizes():
    predictions = {101: 5.0, 102: 3.5}
    db = FakeDB(predictions=predictions, newest=datetime.now() - timedelta(hours=1))
    eng = _make_engine(db)

    with patch.object(
        DecisionSynthesisEngine, 'gather_intelligence', return_value={}
    ) as gather, patch.object(
        DecisionSynthesisEngine, '_determine_strategy', return_value={}
    ), patch.object(
        DecisionSynthesisEngine, '_rank_players_by_value', return_value=[]
    ), patch.object(
        DecisionSynthesisEngine, '_recommend_captain', return_value={}
    ), patch.object(
        DecisionSynthesisEngine, '_identify_transfer_targets', return_value=[]
    ), patch.object(
        DecisionSynthesisEngine, '_identify_template_risks', return_value=[]
    ):
        first = eng.synthesize_recommendations(33)
        second = eng.synthesize_recommendations(33)

    # First call hit gather_intelligence; second should have been cached
    # by the in-process memo and not touched gather_intelligence again.
    assert gather.call_count == 1
    assert first is second  # same object - true cache, not recomputed
