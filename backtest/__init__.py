"""
Backtesting framework for strategy validation (ron_clanker-obi).

Replays historical seasons with walk-forward discipline: at each gameweek,
strategies may only see data available before that gameweek's deadline,
then are scored against what actually happened.

Modules:
    scoring  - pure FPL gameweek scoring engine (autosubs, captain/vice,
               chips, hits). No database access.
    data     - HistoricalDataProvider over a season database (live DB or
               an archive snapshot from data/archives/).
    replay   - replay a recorded season through the scoring engine and
               compare against the official FPL scores. This is the
               framework's own validation: if we can't reproduce Ron's
               actual 2025-26 scores, nothing downstream can be trusted.
    metrics  - prediction quality metrics (MAE, RMSE, Spearman, top-K,
               captain regret) computed walk-forward per gameweek.

Entry point: scripts/run_backtest.py
"""

from backtest.scoring import Pick, PlayerGW, GWScore, score_gameweek
from backtest.data import HistoricalDataProvider

__all__ = [
    'Pick',
    'PlayerGW',
    'GWScore',
    'score_gameweek',
    'HistoricalDataProvider',
]
