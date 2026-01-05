#!/usr/bin/env python3
"""
Train Neural Network Models (MLP + LSTM) with GPU Acceleration

Uses PyTorch with CUDA for fast training on historical data.
Creates models that integrate with the existing stacking ensemble.

Usage:
    python train_neural_models.py                    # Train all models
    python train_neural_models.py --mlp-only         # MLP only (faster)
    python train_neural_models.py --epochs 200       # More training
    python train_neural_models.py --check-gpu        # Just check GPU status
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

from ml.prediction.neural_models import (
    PositionNeuralEnsemble,
    check_gpu,
    DEVICE
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('train_neural')


# Features to include in form sequences for LSTM
SEQUENCE_FEATURES = [
    'total_points', 'minutes', 'goals_scored', 'assists',
    'clean_sheets', 'bonus', 'bps', 'influence', 'creativity', 'threat'
]


def load_training_data(
    db_path: str,
    seasons: List[str] = None,
    sequence_length: int = 5
) -> Tuple[Dict, Dict, Dict, Dict]:
    """
    Load historical data formatted for neural network training.

    Returns:
        features_by_position: Dict[position -> np.ndarray of features]
        sequences_by_position: Dict[position -> np.ndarray of form sequences]
        targets_by_position: Dict[position -> np.ndarray of points]
        feature_names: List of feature column names
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

    query = f"""
        SELECT
            h.season_id,
            h.player_code,
            h.gameweek,
            hp.element_type as position,
            hp.web_name,
            h.total_points,
            h.minutes,
            h.goals_scored,
            h.assists,
            h.clean_sheets,
            h.goals_conceded,
            h.bonus,
            h.bps,
            h.saves,
            h.influence,
            h.creativity,
            h.threat,
            h.ict_index,
            h.expected_goals,
            h.expected_assists,
            h.was_home,
            h.value,
            h.selected
        FROM historical_gameweek_data h
        JOIN historical_players hp ON h.season_id = hp.season_id AND h.player_code = hp.player_code
        WHERE h.minutes > 0
        {season_filter}
        ORDER BY h.season_id, h.player_code, h.gameweek
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logger.info(f"Loaded {len(rows)} historical gameweek records")

    # Group by player
    player_history = {}
    for row in rows:
        key = (row['season_id'], row['player_code'])
        if key not in player_history:
            player_history[key] = []
        player_history[key].append(dict(row))

    # Process into features, sequences, and targets
    features_by_position = {1: [], 2: [], 3: [], 4: []}
    sequences_by_position = {1: [], 2: [], 3: [], 4: []}
    targets_by_position = {1: [], 2: [], 3: [], 4: []}

    for (season_id, player_code), history in player_history.items():
        if len(history) < sequence_length + 1:
            continue

        position = history[0]['position']

        # For each gameweek where we have enough history
        for i in range(sequence_length, len(history)):
            current = history[i]
            recent = history[i-sequence_length:i]

            # Build aggregate features (for MLP)
            features = build_aggregate_features(history[:i], recent, current)
            features_by_position[position].append(features)

            # Build sequence features (for LSTM)
            sequence = build_sequence_features(recent)
            sequences_by_position[position].append(sequence)

            # Target
            targets_by_position[position].append(current['total_points'])

    # Convert to numpy arrays
    feature_names = list(features_by_position[1][0].keys()) if features_by_position[1] else []

    for pos in [1, 2, 3, 4]:
        if features_by_position[pos]:
            features_by_position[pos] = np.array([
                [f[k] for k in feature_names] for f in features_by_position[pos]
            ])
            sequences_by_position[pos] = np.array(sequences_by_position[pos])
            targets_by_position[pos] = np.array(targets_by_position[pos])
            logger.info(
                f"Position {pos}: {len(targets_by_position[pos])} samples, "
                f"{features_by_position[pos].shape[1]} features, "
                f"sequences {sequences_by_position[pos].shape}"
            )
        else:
            features_by_position[pos] = np.array([])
            sequences_by_position[pos] = np.array([])
            targets_by_position[pos] = np.array([])

    return features_by_position, sequences_by_position, targets_by_position, feature_names


def build_aggregate_features(all_history: List[Dict], recent: List[Dict], current: Dict) -> Dict:
    """
    Build aggregate features from player history for MLP.

    IMPORTANT: Feature names and order MUST match FeatureEngineer.engineer_features()
    to ensure neural models can be used in the prediction pipeline.
    See ml/prediction/features.py for the authoritative feature list.
    """

    # Safe mean function
    def safe_mean(values, default=0.0):
        values = [v for v in values if v is not None]
        return np.mean(values) if values else default

    # Calculate form trend
    form_trend = compute_trend([g['total_points'] for g in recent])

    features = {
        # Player attributes (matches FeatureEngineer)
        # Note: 'player_id' and 'position' excluded - not used in model input
        'price': (current['value'] or 50) / 10.0,
        'ownership': (current['selected'] or 0) / 100000.0,

        # FPL calculated stats - use recent form as proxy for historical data
        'fpl_form': safe_mean([g['total_points'] for g in recent[-3:]]),  # Last 3 games
        'fpl_points_per_game': safe_mean([g['total_points'] for g in all_history]),

        # Current ICT metrics - use most recent game's ICT
        'current_influence': float(recent[-1]['influence'] or 0) if recent else 0.0,
        'current_creativity': float(recent[-1]['creativity'] or 0) if recent else 0.0,
        'current_threat': float(recent[-1]['threat'] or 0) if recent else 0.0,
        'current_ict_index': float(recent[-1]['ict_index'] or 0) if recent else 0.0,

        # Recent form (last 5 games) - matches FeatureEngineer exactly
        'form_avg_points': safe_mean([g['total_points'] for g in recent]),
        'form_avg_minutes': safe_mean([g['minutes'] for g in recent]),
        'form_avg_goals': safe_mean([g['goals_scored'] for g in recent]),
        'form_avg_assists': safe_mean([g['assists'] for g in recent]),
        'form_avg_bonus': safe_mean([g['bonus'] for g in recent]),
        'form_avg_bps': safe_mean([g['bps'] for g in recent]),
        'form_avg_clean_sheets': safe_mean([g['clean_sheets'] for g in recent]),
        'form_avg_saves': safe_mean([g.get('saves', 0) for g in recent]),  # Added to match
        'form_avg_influence': safe_mean([g['influence'] for g in recent]),
        'form_avg_creativity': safe_mean([g['creativity'] for g in recent]),
        'form_avg_threat': safe_mean([g['threat'] for g in recent]),
        'form_avg_ict_index': safe_mean([g['ict_index'] for g in recent]),
        'form_trend': form_trend,
        'form_games_played': len(recent),  # Added to match

        # xG features - matches FeatureEngineer
        'avg_xg': safe_mean([float(g.get('expected_goals', 0) or 0) for g in recent]),
        'avg_xa': safe_mean([float(g.get('expected_assists', 0) or 0) for g in recent]),
        'avg_xgi': safe_mean([float(g.get('expected_goal_involvements', 0) or 0) for g in recent]),
        'xg_overperformance': (
            safe_mean([g['goals_scored'] for g in recent]) -
            safe_mean([float(g.get('expected_goals', 0) or 0) for g in recent])
        ),
        'xa_overperformance': (
            safe_mean([g['assists'] for g in recent]) -
            safe_mean([float(g.get('expected_assists', 0) or 0) for g in recent])
        ),

        # Season stats - matches FeatureEngineer
        'season_games': len(all_history),
        'season_ppg': safe_mean([g['total_points'] for g in all_history]),
        'season_mpg': safe_mean([g['minutes'] for g in all_history]),
        'season_gpg': safe_mean([g['goals_scored'] for g in all_history]),
        'season_apg': safe_mean([g['assists'] for g in all_history]),
        'season_cs_pg': safe_mean([g['clean_sheets'] for g in all_history]),

        # Fixture features - historical data doesn't have opponent info, use defaults
        'fixture_difficulty': 3,  # Medium difficulty default
        'is_home': 1.0 if current['was_home'] else 0.0,
        'opponent_strength': 1.0,  # Normalized default
        'opponent_defensive_strength': 1.0,
        'opponent_attacking_strength': 1.0,

        # Defensive Contribution (DC) features - matches FeatureEngineer
        'avg_tackles': safe_mean([g.get('tackles', 0) or 0 for g in recent]),
        'avg_cbi': safe_mean([
            (g.get('clearances', 0) or 0) +
            (g.get('blocks', 0) or 0) +
            (g.get('interceptions', 0) or 0)
            for g in recent
        ]),
        'avg_recoveries': safe_mean([g.get('recoveries', 0) or 0 for g in recent]),
        'dc_score': (
            safe_mean([g.get('tackles', 0) or 0 for g in recent]) +
            safe_mean([
                (g.get('clearances', 0) or 0) +
                (g.get('blocks', 0) or 0) +
                (g.get('interceptions', 0) or 0)
                for g in recent
            ])
        ),

        # Derived features - matches FeatureEngineer
        'minutes_reliability': min(1.0, safe_mean([g['minutes'] for g in recent]) / 90.0),
        'attacking_threat': (
            safe_mean([g['goals_scored'] for g in recent]) * 4 +
            safe_mean([g['assists'] for g in recent]) * 3
        ),
        'defensive_reliability': safe_mean([g['clean_sheets'] for g in recent]),
        'dc_potential': (
            safe_mean([g.get('tackles', 0) or 0 for g in recent]) +
            safe_mean([
                (g.get('clearances', 0) or 0) +
                (g.get('blocks', 0) or 0) +
                (g.get('interceptions', 0) or 0)
                for g in recent
            ]) +
            safe_mean([g.get('recoveries', 0) or 0 for g in recent])
        ),
    }

    return features


def build_sequence_features(recent: List[Dict]) -> np.ndarray:
    """Build sequence array from recent games for LSTM."""
    sequence = []

    for game in recent:
        game_features = [
            game['total_points'] / 20.0,  # Normalize points
            game['minutes'] / 90.0,  # Normalize minutes
            game['goals_scored'],
            game['assists'],
            game['clean_sheets'],
            game['bonus'] / 3.0,  # Max bonus is 3
            game['bps'] / 50.0,  # Normalize BPS
            (game['influence'] or 0) / 100.0,
            (game['creativity'] or 0) / 100.0,
            (game['threat'] or 0) / 100.0,
        ]
        sequence.append(game_features)

    return np.array(sequence)


def compute_trend(values: List[float]) -> float:
    """Compute linear regression slope for trend detection."""
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values))
    try:
        coeffs = np.polyfit(x, values, 1)
        return float(coeffs[0])
    except Exception:
        return 0.0


def main():
    parser = argparse.ArgumentParser(description='Train neural network models with GPU')
    parser.add_argument('--seasons', nargs='+', default=['2022-23', '2023-24', '2024-25'],
                        help='Seasons to use for training')
    parser.add_argument('--db', default='data/ron_clanker.db', help='Database path')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs')
    parser.add_argument('--batch-size', type=int, default=256, help='Batch size')
    parser.add_argument('--sequence-length', type=int, default=5, help='Form sequence length')
    parser.add_argument('--mlp-only', action='store_true', help='Train MLP only (skip LSTM)')
    parser.add_argument('--check-gpu', action='store_true', help='Just check GPU and exit')
    parser.add_argument('--output-version', default=None, help='Model version tag')

    args = parser.parse_args()

    # GPU check mode
    if args.check_gpu:
        check_gpu()
        return

    print("\n" + "=" * 70)
    print("NEURAL NETWORK MODEL TRAINING")
    print("=" * 70)
    check_gpu()
    print(f"\nSeasons: {', '.join(args.seasons)}")
    print(f"Epochs: {args.epochs}")
    print(f"Batch Size: {args.batch_size}")
    print(f"Sequence Length: {args.sequence_length}")
    print(f"LSTM: {'Disabled' if args.mlp_only else 'Enabled'}")
    print("=" * 70)

    start_time = datetime.now()

    # Load data
    logger.info("Loading training data...")
    features, sequences, targets, feature_names = load_training_data(
        args.db,
        args.seasons,
        args.sequence_length
    )

    total_samples = sum(len(t) for t in targets.values() if len(t) > 0)
    print(f"\nTotal training samples: {total_samples:,}")

    # Initialize ensemble
    ensemble = PositionNeuralEnsemble(
        model_dir=Path('models/neural'),
        use_lstm=not args.mlp_only
    )

    # Train each position
    all_metrics = {}
    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

    for position in [1, 2, 3, 4]:
        if len(targets[position]) == 0:
            logger.warning(f"No data for position {position}, skipping")
            continue

        print(f"\n{'='*60}")
        print(f"TRAINING {position_names[position].upper()}")
        print(f"{'='*60}")
        print(f"Samples: {len(targets[position]):,}")

        metrics = ensemble.train_position(
            position=position,
            X=features[position],
            y=targets[position],
            sequences=sequences[position] if not args.mlp_only else None,
            epochs=args.epochs,
            batch_size=args.batch_size
        )

        all_metrics[position] = metrics

        # Print results
        if 'mlp' in metrics:
            print(f"\nMLP Results:")
            print(f"  Val RMSE: {metrics['mlp']['final_val_rmse']:.4f}")
            print(f"  Val MAE: {metrics['mlp']['final_val_mae']:.4f}")
            print(f"  Epochs: {metrics['mlp']['epochs_trained']}")

        if 'lstm' in metrics:
            print(f"\nLSTM Results:")
            print(f"  Val RMSE: {metrics['lstm']['final_val_rmse']:.4f}")
            print(f"  Val MAE: {metrics['lstm']['final_val_mae']:.4f}")
            print(f"  Epochs: {metrics['lstm']['epochs_trained']}")

    # Save models
    version = args.output_version or f"gpu_{datetime.now().strftime('%Y%m%d_%H%M')}"
    ensemble.save_all(version)

    # Summary
    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)

    for pos, metrics in all_metrics.items():
        print(f"\n{position_names[pos]}:")
        if 'mlp' in metrics:
            print(f"  MLP RMSE: {metrics['mlp']['final_val_rmse']:.4f}")
        if 'lstm' in metrics:
            print(f"  LSTM RMSE: {metrics['lstm']['final_val_rmse']:.4f}")

    print(f"\nTotal Duration: {duration:.1f}s ({duration/60:.1f} min)")
    print(f"Models saved with version: {version}")
    print(f"Device used: {DEVICE}")

    # Save metrics
    metrics_file = Path('models/neural') / f'metrics_{version}.json'
    with open(metrics_file, 'w') as f:
        # Convert numpy types for JSON
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.float64, np.float32)):
                return float(obj)
            return obj

        json.dump(all_metrics, f, indent=2, default=convert)
    print(f"Metrics saved to: {metrics_file}")


if __name__ == '__main__':
    main()
