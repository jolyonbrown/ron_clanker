#!/usr/bin/env python3
"""
Hyperparameter Tuning with Optuna

Uses Optuna to find optimal hyperparameters for the ensemble models.
Evaluates using TimeSeriesSplit cross-validation for robust results.

Usage:
    python tune_hyperparameters.py                     # Tune all positions
    python tune_hyperparameters.py --position 4        # Tune forwards only
    python tune_hyperparameters.py --n-trials 50       # More trials (better results)
    python tune_hyperparameters.py --quick             # Quick test (10 trials)
"""

import sys
import argparse
import logging
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import numpy as np

import optuna
from optuna.samplers import TPESampler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Suppress Optuna's verbose logging
optuna.logging.set_verbosity(optuna.logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('hyperparameter_tuning')


def load_training_data(db_path: str, seasons: List[str] = None) -> Dict[int, Tuple[np.ndarray, np.ndarray]]:
    """Load and prepare training data by position."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if seasons:
        season_filter = f"AND h.season_id IN ({','.join(['?']*len(seasons))})"
        params = seasons
    else:
        season_filter = ""
        params = []

    query = f"""
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
        {season_filter}
        ORDER BY h.season_id, h.player_code, h.gameweek
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    # Group by player
    player_history = {}
    for row in rows:
        key = (row['season_id'], row['player_code'])
        if key not in player_history:
            player_history[key] = []
        player_history[key].append(dict(row))

    # Build feature matrices by position
    data_by_position = {1: ([], []), 2: ([], []), 3: ([], []), 4: ([], [])}

    for (season_id, player_code), history in player_history.items():
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

            data_by_position[position][0].append(features)
            data_by_position[position][1].append(current['total_points'])

    # Convert to numpy arrays
    result = {}
    for pos in [1, 2, 3, 4]:
        if data_by_position[pos][0]:
            result[pos] = (
                np.array(data_by_position[pos][0]),
                np.array(data_by_position[pos][1])
            )

    return result


def create_objective(X: np.ndarray, y: np.ndarray, n_splits: int = 5):
    """Create Optuna objective function for a given dataset."""

    def objective(trial: optuna.Trial) -> float:
        # Hyperparameters to tune
        rf_params = {
            'n_estimators': trial.suggest_int('rf_n_estimators', 30, 150),
            'max_depth': trial.suggest_int('rf_max_depth', 4, 12),
            'min_samples_split': trial.suggest_int('rf_min_samples_split', 5, 20),
            'min_samples_leaf': trial.suggest_int('rf_min_samples_leaf', 2, 10),
        }

        gb_params = {
            'n_estimators': trial.suggest_int('gb_n_estimators', 30, 150),
            'learning_rate': trial.suggest_float('gb_learning_rate', 0.01, 0.3, log=True),
            'max_depth': trial.suggest_int('gb_max_depth', 2, 8),
            'min_samples_split': trial.suggest_int('gb_min_samples_split', 5, 20),
            'min_samples_leaf': trial.suggest_int('gb_min_samples_leaf', 2, 10),
        }

        xgb_params = {
            'n_estimators': trial.suggest_int('xgb_n_estimators', 30, 150),
            'learning_rate': trial.suggest_float('xgb_learning_rate', 0.01, 0.3, log=True),
            'max_depth': trial.suggest_int('xgb_max_depth', 2, 8),
            'min_child_weight': trial.suggest_int('xgb_min_child_weight', 1, 10),
            'subsample': trial.suggest_float('xgb_subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('xgb_colsample_bytree', 0.6, 1.0),
        }

        meta_alpha = trial.suggest_float('meta_alpha', 0.01, 10.0, log=True)

        # TimeSeriesSplit CV
        tscv = TimeSeriesSplit(n_splits=n_splits)
        cv_scores = []

        for train_idx, test_idx in tscv.split(X):
            X_train_fold, X_test_fold = X[train_idx], X[test_idx]
            y_train_fold, y_test_fold = y[train_idx], y[test_idx]

            # Split train for meta-learner
            split = int(len(X_train_fold) * 0.8)
            X_train, X_val = X_train_fold[:split], X_train_fold[split:]
            y_train, y_val = y_train_fold[:split], y_train_fold[split:]

            if len(X_val) < 5:
                continue

            # Train base models
            base_preds_val = []
            base_preds_test = []

            rf = RandomForestRegressor(**rf_params, random_state=42, n_jobs=-1)
            rf.fit(X_train, y_train)
            base_preds_val.append(rf.predict(X_val))
            base_preds_test.append(rf.predict(X_test_fold))

            gb = GradientBoostingRegressor(**gb_params, random_state=42)
            gb.fit(X_train, y_train)
            base_preds_val.append(gb.predict(X_val))
            base_preds_test.append(gb.predict(X_test_fold))

            if XGBOOST_AVAILABLE:
                xgb_model = xgb.XGBRegressor(**xgb_params, random_state=42, verbosity=0, n_jobs=-1)
                xgb_model.fit(X_train, y_train)
                base_preds_val.append(xgb_model.predict(X_val))
                base_preds_test.append(xgb_model.predict(X_test_fold))

            # Meta-learner
            meta_X_val = np.column_stack(base_preds_val)
            meta_X_test = np.column_stack(base_preds_test)

            meta = Ridge(alpha=meta_alpha)
            meta.fit(meta_X_val, y_val)

            y_pred = meta.predict(meta_X_test)
            rmse = np.sqrt(mean_squared_error(y_test_fold, y_pred))
            cv_scores.append(rmse)

        return np.mean(cv_scores) if cv_scores else float('inf')

    return objective


def tune_position(position: int, X: np.ndarray, y: np.ndarray,
                  n_trials: int = 50, n_splits: int = 5) -> Dict:
    """Tune hyperparameters for a single position."""
    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

    logger.info(f"Tuning {position_names[position]} ({len(X)} samples, {n_trials} trials)...")

    study = optuna.create_study(
        direction='minimize',
        sampler=TPESampler(seed=42)
    )

    objective = create_objective(X, y, n_splits)

    study.optimize(
        objective,
        n_trials=n_trials,
        show_progress_bar=True,
        n_jobs=1  # Sequential to avoid memory issues
    )

    best_params = study.best_params
    best_value = study.best_value

    # Organize params by model
    result = {
        'position': position,
        'position_name': position_names[position],
        'n_samples': len(X),
        'n_trials': n_trials,
        'best_cv_rmse': float(best_value),
        'rf_params': {
            'n_estimators': best_params['rf_n_estimators'],
            'max_depth': best_params['rf_max_depth'],
            'min_samples_split': best_params['rf_min_samples_split'],
            'min_samples_leaf': best_params['rf_min_samples_leaf'],
        },
        'gb_params': {
            'n_estimators': best_params['gb_n_estimators'],
            'learning_rate': best_params['gb_learning_rate'],
            'max_depth': best_params['gb_max_depth'],
            'min_samples_split': best_params['gb_min_samples_split'],
            'min_samples_leaf': best_params['gb_min_samples_leaf'],
        },
        'xgb_params': {
            'n_estimators': best_params['xgb_n_estimators'],
            'learning_rate': best_params['xgb_learning_rate'],
            'max_depth': best_params['xgb_max_depth'],
            'min_child_weight': best_params['xgb_min_child_weight'],
            'subsample': best_params['xgb_subsample'],
            'colsample_bytree': best_params['xgb_colsample_bytree'],
        },
        'meta_alpha': best_params['meta_alpha'],
    }

    logger.info(f"  Best CV RMSE: {best_value:.4f}")

    return result


def main():
    parser = argparse.ArgumentParser(description='Tune hyperparameters with Optuna')
    parser.add_argument('--position', type=int, choices=[1, 2, 3, 4],
                        help='Tune specific position only')
    parser.add_argument('--n-trials', type=int, default=30,
                        help='Number of Optuna trials per position (default: 30)')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 10 trials per position')
    parser.add_argument('--thorough', action='store_true',
                        help='Thorough mode: 100 trials per position')
    parser.add_argument('--cv-folds', type=int, default=3,
                        help='Number of CV folds (default: 3)')
    parser.add_argument('--db', default='data/ron_clanker.db',
                        help='Database path')
    parser.add_argument('--output', default='config/tuned_hyperparameters.json',
                        help='Output file for tuned parameters')

    args = parser.parse_args()

    if args.quick:
        n_trials = 10
    elif args.thorough:
        n_trials = 100
    else:
        n_trials = args.n_trials

    print("\n" + "=" * 70)
    print("HYPERPARAMETER TUNING WITH OPTUNA")
    print("=" * 70)
    print(f"Trials per position: {n_trials}")
    print(f"CV folds: {args.cv_folds}")
    print("=" * 70)

    start_time = datetime.now()

    # Load data
    logger.info("Loading training data...")
    data = load_training_data(args.db, ['2022-23', '2023-24', '2024-25'])

    total_samples = sum(len(X) for X, y in data.values())
    print(f"Total samples: {total_samples:,}")

    # Tune each position
    results = {}
    positions = [args.position] if args.position else [1, 2, 3, 4]

    for pos in positions:
        if pos not in data:
            logger.warning(f"No data for position {pos}")
            continue

        X, y = data[pos]
        result = tune_position(pos, X, y, n_trials, args.cv_folds)
        results[pos] = result

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    duration = (datetime.now() - start_time).total_seconds()

    # Print summary
    print("\n" + "=" * 70)
    print("TUNING COMPLETE")
    print("=" * 70)

    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

    for pos, r in results.items():
        print(f"\n{position_names[pos]}:")
        print(f"  Best CV RMSE: {r['best_cv_rmse']:.4f}")
        print(f"  RF: n_est={r['rf_params']['n_estimators']}, depth={r['rf_params']['max_depth']}")
        print(f"  GB: n_est={r['gb_params']['n_estimators']}, lr={r['gb_params']['learning_rate']:.3f}, depth={r['gb_params']['max_depth']}")
        print(f"  XGB: n_est={r['xgb_params']['n_estimators']}, lr={r['xgb_params']['learning_rate']:.3f}, depth={r['xgb_params']['max_depth']}")
        print(f"  Meta alpha: {r['meta_alpha']:.4f}")

    print(f"\nDuration: {duration:.1f}s")
    print(f"Parameters saved to: {args.output}")
    print("\nTo use these parameters, run:")
    print(f"  python scripts/train_with_tuned_params.py")


if __name__ == '__main__':
    main()
