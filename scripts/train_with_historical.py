#!/usr/bin/env python3
"""
Train ML Models with Historical Data

Uses TimeSeriesSplit cross-validation on multi-season historical data
for more robust model evaluation.

Usage:
    python train_with_historical.py                    # Train on all historical data
    python train_with_historical.py --seasons 2023-24 2024-25
    python train_with_historical.py --cv-folds 5      # Specify CV folds
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

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.prediction.model import PlayerPerformancePredictor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('train_historical')


def load_historical_data(db_path: str, seasons: List[str] = None) -> Tuple[Dict, Dict, Dict]:
    """
    Load historical gameweek data for ML training.

    Returns:
        features_by_position: Dict[position -> List[feature_dicts]]
        targets_by_position: Dict[position -> List[total_points]]
        gameweeks_by_position: Dict[position -> List[gameweek_numbers]]
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build season filter
    if seasons:
        season_filter = f"AND h.season_id IN ({','.join(['?']*len(seasons))})"
        params = seasons
    else:
        season_filter = ""
        params = []

    # Query historical data with player info
    query = f"""
        SELECT
            h.season_id,
            h.player_code,
            h.gameweek,
            hp.element_type as position,
            hp.web_name,
            -- Target
            h.total_points,
            -- Features: Recent form (we'll compute rolling averages)
            h.minutes,
            h.goals_scored,
            h.assists,
            h.clean_sheets,
            h.bonus,
            h.bps,
            h.influence,
            h.creativity,
            h.threat,
            h.ict_index,
            h.expected_goals,
            h.expected_assists,
            -- Context
            h.was_home,
            h.value,
            h.selected
        FROM historical_gameweek_data h
        JOIN historical_players hp ON h.season_id = hp.season_id AND h.player_code = hp.player_code
        WHERE h.minutes > 0  -- Only include games where player played
        {season_filter}
        ORDER BY h.season_id, h.player_code, h.gameweek
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logger.info(f"Loaded {len(rows)} historical gameweek records")

    # Group by player and compute features
    features_by_position = {1: [], 2: [], 3: [], 4: []}
    targets_by_position = {1: [], 2: [], 3: [], 4: []}
    gameweeks_by_position = {1: [], 2: [], 3: [], 4: []}

    # Group rows by player
    player_history = {}
    for row in rows:
        key = (row['season_id'], row['player_code'])
        if key not in player_history:
            player_history[key] = []
        player_history[key].append(dict(row))

    # Process each player's history
    for (season_id, player_code), history in player_history.items():
        if len(history) < 3:  # Need at least 3 games to compute meaningful features
            continue

        position = history[0]['position']

        # For each gameweek (starting from 4th), create features from previous games
        for i in range(3, len(history)):
            current = history[i]
            recent = history[max(0, i-5):i]  # Last 5 games

            # Compute rolling averages
            features = {
                'player_code': player_code,
                'position': position,
                # Recent form (last 5 games)
                'form_avg_points': np.mean([g['total_points'] for g in recent]),
                'form_avg_minutes': np.mean([g['minutes'] for g in recent]),
                'form_avg_goals': np.mean([g['goals_scored'] for g in recent]),
                'form_avg_assists': np.mean([g['assists'] for g in recent]),
                'form_avg_bonus': np.mean([g['bonus'] for g in recent]),
                'form_avg_bps': np.mean([g['bps'] for g in recent]),
                'form_avg_clean_sheets': np.mean([g['clean_sheets'] for g in recent]),
                'form_avg_influence': np.mean([g['influence'] or 0 for g in recent]),
                'form_avg_creativity': np.mean([g['creativity'] or 0 for g in recent]),
                'form_avg_threat': np.mean([g['threat'] or 0 for g in recent]),
                'form_avg_ict_index': np.mean([g['ict_index'] or 0 for g in recent]),
                # Form trend
                'form_trend': compute_trend([g['total_points'] for g in recent]),
                'form_games_played': len(recent),
                # Season stats (cumulative up to this point)
                'season_ppg': np.mean([g['total_points'] for g in history[:i]]),
                'season_mpg': np.mean([g['minutes'] for g in history[:i]]),
                'season_gpg': np.mean([g['goals_scored'] for g in history[:i]]),
                'season_apg': np.mean([g['assists'] for g in history[:i]]),
                'season_cs_pg': np.mean([g['clean_sheets'] for g in history[:i]]),
                'season_games': i,
                # Current game context
                'is_home': 1 if current['was_home'] else 0,
                'price': (current['value'] or 50) / 10.0,
                'ownership': (current['selected'] or 0) / 100000.0,  # Normalize
                # ICT current (use recent average as proxy)
                'current_influence': np.mean([g['influence'] or 0 for g in recent]),
                'current_creativity': np.mean([g['creativity'] or 0 for g in recent]),
                'current_threat': np.mean([g['threat'] or 0 for g in recent]),
                'current_ict_index': np.mean([g['ict_index'] or 0 for g in recent]),
                # FPL-like metrics
                'fpl_form': np.mean([g['total_points'] for g in recent[-3:]]) if len(recent) >= 3 else 0,
                'fpl_points_per_game': np.mean([g['total_points'] for g in history[:i]]),
                # Derived
                'minutes_reliability': min(1.0, np.mean([g['minutes'] for g in recent]) / 90.0),
                'attacking_threat': np.mean([g['goals_scored'] for g in recent]) * 4 + np.mean([g['assists'] for g in recent]) * 3,
                'defensive_reliability': np.mean([g['clean_sheets'] for g in recent]),
                # Placeholder for fixture difficulty (would need fixture data)
                'fixture_difficulty': 3,
                'opponent_strength': 1.0,
                'opponent_defensive_strength': 1.0,
                'opponent_attacking_strength': 1.0,
            }

            # Use a composite gameweek number for temporal ordering
            # Season 2022-23 GW1 = 1, Season 2023-24 GW1 = 39, etc.
            season_offset = {'2022-23': 0, '2023-24': 38, '2024-25': 76}.get(season_id, 0)
            composite_gw = season_offset + current['gameweek']

            features_by_position[position].append(features)
            targets_by_position[position].append(current['total_points'])
            gameweeks_by_position[position].append(composite_gw)

    # Log statistics
    for pos in [1, 2, 3, 4]:
        logger.info(f"Position {pos}: {len(features_by_position[pos])} training samples")

    return features_by_position, targets_by_position, gameweeks_by_position


def compute_trend(values: List[float]) -> float:
    """Compute linear regression slope for trend detection."""
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values))
    coeffs = np.polyfit(x, values, 1)
    return float(coeffs[0])


def main():
    parser = argparse.ArgumentParser(description='Train ML models with historical data')
    parser.add_argument('--seasons', nargs='+', default=['2022-23', '2023-24', '2024-25'],
                        help='Seasons to use for training')
    parser.add_argument('--cv-folds', type=int, default=5,
                        help='Number of cross-validation folds')
    parser.add_argument('--db', default='data/ron_clanker.db',
                        help='Database path')
    parser.add_argument('--output-version', default=None,
                        help='Model version tag (default: auto-generated)')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("TRAINING ML MODELS WITH HISTORICAL DATA")
    print("=" * 70)
    print(f"Seasons: {', '.join(args.seasons)}")
    print(f"CV Folds: {args.cv_folds}")
    print("=" * 70)

    start_time = datetime.now()

    # Load historical data
    logger.info("Loading historical data...")
    features, targets, gameweeks = load_historical_data(args.db, args.seasons)

    total_samples = sum(len(f) for f in features.values())
    print(f"\nTotal training samples: {total_samples:,}")

    # Initialize predictor
    predictor = PlayerPerformancePredictor(model_dir=Path('models/prediction'))

    # Train with TimeSeriesSplit CV
    logger.info("Training models with TimeSeriesSplit cross-validation...")
    metrics = predictor.train_all_models_cv(
        features_by_position=features,
        targets_by_position=targets,
        gameweeks_by_position=gameweeks,
        n_splits=args.cv_folds
    )

    # Save models
    version = args.output_version or f"historical_{datetime.now().strftime('%Y%m%d')}"
    predictor.save_models(version=version)

    # Print results
    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)

    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

    for pos, m in metrics.items():
        cv = m['cv_results']
        print(f"\n{position_names[pos]}:")
        print(f"  Samples: {m['total_samples']:,}")
        print(f"  CV RMSE: {cv['mean_rmse']:.3f} (+/- {cv['std_rmse']:.3f})")
        print(f"  CV MAE:  {cv['mean_mae']:.3f} (+/- {cv['std_mae']:.3f})")
        print(f"  CV R2:   {cv['mean_r2']:.3f} (+/- {cv['std_r2']:.3f})")
        print(f"  Meta weights: {m['meta_weights']}")

    print(f"\nDuration: {duration:.1f}s")
    print(f"Models saved with version: {version}")

    # Save metrics to JSON
    metrics_file = Path('models/prediction') / f'metrics_{version}.json'
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"Metrics saved to: {metrics_file}")


if __name__ == '__main__':
    main()
