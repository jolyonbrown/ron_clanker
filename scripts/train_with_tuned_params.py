#!/usr/bin/env python3
"""
Train Models with Tuned Hyperparameters

Uses the hyperparameters found by Optuna tuning to train the final models.

Usage:
    python train_with_tuned_params.py
    python train_with_tuned_params.py --params config/tuned_hyperparameters.json
"""

import sys
import argparse
import logging
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import numpy as np

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('train_tuned')


def load_training_data(db_path: str) -> Dict[int, tuple]:
    """Load training data from historical tables."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            h.season_id, h.player_code, h.gameweek,
            hp.element_type as position,
            h.total_points, h.minutes, h.goals_scored, h.assists,
            h.clean_sheets, h.bonus, h.bps,
            h.influence, h.creativity, h.threat, h.ict_index,
            h.was_home, h.value, h.selected
        FROM historical_gameweek_data h
        JOIN historical_players hp ON h.season_id = hp.season_id AND h.player_code = hp.player_code
        WHERE h.minutes > 0
        ORDER BY h.season_id, h.player_code, h.gameweek
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # Group by player
    player_history = {}
    for row in rows:
        key = (row['season_id'], row['player_code'])
        if key not in player_history:
            player_history[key] = []
        player_history[key].append(dict(row))

    # Build feature matrices
    data = {1: ([], []), 2: ([], []), 3: ([], []), 4: ([], [])}
    feature_names = None

    for history in player_history.values():
        if len(history) < 3:
            continue

        position = history[0]['position']

        for i in range(3, len(history)):
            current = history[i]
            recent = history[max(0, i-5):i]

            features = [
                np.mean([g['total_points'] for g in recent]),
                np.mean([g['minutes'] for g in recent]),
                np.mean([g['goals_scored'] for g in recent]),
                np.mean([g['assists'] for g in recent]),
                np.mean([g['bonus'] for g in recent]),
                np.mean([g['bps'] for g in recent]),
                np.mean([g['clean_sheets'] for g in recent]),
                np.mean([g['influence'] or 0 for g in recent]),
                np.mean([g['creativity'] or 0 for g in recent]),
                np.mean([g['threat'] or 0 for g in recent]),
                np.mean([g['ict_index'] or 0 for g in recent]),
                1 if current['was_home'] else 0,
                (current['value'] or 50) / 10.0,
                len(recent),
            ]

            if feature_names is None:
                feature_names = [
                    'form_avg_points', 'form_avg_minutes', 'form_avg_goals',
                    'form_avg_assists', 'form_avg_bonus', 'form_avg_bps',
                    'form_avg_clean_sheets', 'form_avg_influence', 'form_avg_creativity',
                    'form_avg_threat', 'form_avg_ict_index', 'is_home', 'price', 'form_games'
                ]

            data[position][0].append(features)
            data[position][1].append(current['total_points'])

    result = {}
    for pos in [1, 2, 3, 4]:
        if data[pos][0]:
            result[pos] = (np.array(data[pos][0]), np.array(data[pos][1]))

    return result, feature_names


def train_with_params(X: np.ndarray, y: np.ndarray, params: Dict) -> tuple:
    """Train ensemble with specified hyperparameters."""
    # Train/val split for meta-learner
    split = int(len(X) * 0.85)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    base_models = []

    # Random Forest
    rf = RandomForestRegressor(
        **params['rf_params'],
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train, y_train)
    base_models.append(('RandomForest', rf))

    # Gradient Boosting
    gb = GradientBoostingRegressor(
        **params['gb_params'],
        random_state=42
    )
    gb.fit(X_train, y_train)
    base_models.append(('GradientBoosting', gb))

    # XGBoost
    if XGBOOST_AVAILABLE:
        xgb_model = xgb.XGBRegressor(
            **params['xgb_params'],
            random_state=42,
            verbosity=0,
            n_jobs=-1
        )
        xgb_model.fit(X_train, y_train)
        base_models.append(('XGBoost', xgb_model))

    # Meta-learner
    meta_X_val = np.column_stack([m.predict(X_val) for _, m in base_models])
    meta = Ridge(alpha=params['meta_alpha'])
    meta.fit(meta_X_val, y_val)

    ensemble = {
        'base_models': base_models,
        'meta_model': meta
    }

    return ensemble


def evaluate_ensemble(ensemble: Dict, X: np.ndarray, y: np.ndarray, n_splits: int = 5) -> Dict:
    """Evaluate ensemble with TimeSeriesSplit CV."""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    rmse_scores = []
    mae_scores = []

    for train_idx, test_idx in tscv.split(X):
        X_test = X[test_idx]
        y_test = y[test_idx]

        # Get predictions
        base_preds = [m.predict(X_test) for _, m in ensemble['base_models']]
        meta_X = np.column_stack(base_preds)
        y_pred = ensemble['meta_model'].predict(meta_X)

        rmse_scores.append(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae_scores.append(mean_absolute_error(y_test, y_pred))

    return {
        'mean_rmse': np.mean(rmse_scores),
        'std_rmse': np.std(rmse_scores),
        'mean_mae': np.mean(mae_scores),
        'std_mae': np.std(mae_scores),
    }


def main():
    parser = argparse.ArgumentParser(description='Train with tuned hyperparameters')
    parser.add_argument('--params', default='config/tuned_hyperparameters.json',
                        help='Path to tuned parameters JSON')
    parser.add_argument('--db', default='data/ron_clanker.db',
                        help='Database path')
    parser.add_argument('--output-version', default=None,
                        help='Model version tag')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("TRAINING WITH TUNED HYPERPARAMETERS")
    print("=" * 70)

    # Load tuned parameters
    with open(args.params, 'r') as f:
        all_params = json.load(f)

    print(f"Loaded parameters from: {args.params}")

    start_time = datetime.now()

    # Load data
    logger.info("Loading training data...")
    data, feature_names = load_training_data(args.db)

    total_samples = sum(len(X) for X, y in data.values())
    print(f"Total samples: {total_samples:,}")

    # Train each position
    models = {}
    metrics = {}
    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

    for pos in [1, 2, 3, 4]:
        if pos not in data:
            continue

        pos_key = str(pos)
        if pos_key not in all_params:
            logger.warning(f"No tuned params for position {pos}, skipping")
            continue

        X, y = data[pos]
        params = all_params[pos_key]

        logger.info(f"Training {position_names[pos]} ({len(X)} samples)...")

        ensemble = train_with_params(X, y, params)
        eval_metrics = evaluate_ensemble(ensemble, X, y)

        models[pos] = ensemble
        metrics[pos] = {
            'samples': len(X),
            **eval_metrics,
            'params': params
        }

        print(f"  {position_names[pos]}: RMSE={eval_metrics['mean_rmse']:.4f} (+/- {eval_metrics['std_rmse']:.4f})")

    # Save models
    model_dir = Path('models/prediction')
    model_dir.mkdir(parents=True, exist_ok=True)

    version = args.output_version or f"tuned_{datetime.now().strftime('%Y%m%d')}"

    for pos, ensemble in models.items():
        path = model_dir / f'ensemble_{pos}_{version}.pkl'
        joblib.dump(ensemble, path)
        logger.info(f"Saved {path}")

    # Save feature columns
    if feature_names:
        feature_path = model_dir / f'feature_columns_{version}.pkl'
        joblib.dump(feature_names, feature_path)

    # Save metrics
    metrics_path = model_dir / f'metrics_{version}.json'
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2, default=str)

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"Duration: {duration:.1f}s")
    print(f"Models saved with version: {version}")
    print(f"Metrics saved to: {metrics_path}")


if __name__ == '__main__':
    main()
