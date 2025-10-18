#!/usr/bin/env python3
"""
Player Performance Prediction Models

Position-specific models to predict expected points for next gameweek.
Uses ensemble methods (Random Forest, Gradient Boosting) with engineered features.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib

logger = logging.getLogger('ron_clanker.ml.prediction')


class PlayerPerformancePredictor:
    """
    Predicts player expected points using position-specific ML models.

    Separate models for each position:
    - Goalkeepers (position=1)
    - Defenders (position=2)
    - Midfielders (position=3)
    - Forwards (position=4)
    """

    def __init__(self, model_dir: Path = None):
        """
        Initialize predictor.

        Args:
            model_dir: Directory to save/load trained models
        """
        self.model_dir = model_dir or Path('models/prediction')
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # Position-specific models
        self.models = {
            1: None,  # GK
            2: None,  # DEF
            3: None,  # MID
            4: None   # FWD
        }

        # Feature columns (will be set during training)
        self.feature_columns = None

        logger.info("PlayerPerformancePredictor: Initialized")

    def prepare_training_data(self, features_list: List[Dict], targets: List[float]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert feature dicts to numpy arrays for sklearn.

        Args:
            features_list: List of feature dicts from FeatureEngineer
            targets: List of actual points scored (ground truth)

        Returns:
            (X, y) tuple of numpy arrays
        """
        if not features_list:
            raise ValueError("No features provided for training")

        # Get feature columns from first sample (excluding player_id which we don't use for training)
        if self.feature_columns is None:
            self.feature_columns = [
                k for k in features_list[0].keys()
                if k not in ['player_id']
            ]

        # Convert to numpy
        X = np.array([[f[col] for col in self.feature_columns] for f in features_list])
        y = np.array(targets)

        logger.info(f"Prepared training data: {X.shape[0]} samples, {X.shape[1]} features")
        return X, y

    def train_position_model(self, position: int, X: np.ndarray, y: np.ndarray) -> Dict:
        """
        Train a model for a specific position.

        Uses Gradient Boosting Regressor with cross-validation.

        Returns:
            Dict with training metrics
        """
        logger.info(f"Training model for position {position} with {len(X)} samples")

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Train Gradient Boosting model
        model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            verbose=0
        )

        model.fit(X_train, y_train)

        # Evaluate
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)

        metrics = {
            'position': position,
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'train_rmse': np.sqrt(mean_squared_error(y_train, y_pred_train)),
            'test_rmse': np.sqrt(mean_squared_error(y_test, y_pred_test)),
            'train_mae': mean_absolute_error(y_train, y_pred_train),
            'test_mae': mean_absolute_error(y_test, y_pred_test),
            'train_r2': r2_score(y_train, y_pred_train),
            'test_r2': r2_score(y_test, y_pred_test)
        }

        # Cross-validation score
        cv_scores = cross_val_score(
            model, X_train, y_train, cv=5,
            scoring='neg_mean_squared_error'
        )
        metrics['cv_rmse'] = np.sqrt(-cv_scores.mean())

        self.models[position] = model

        logger.info(
            f"Position {position} model trained - "
            f"Test RMSE: {metrics['test_rmse']:.2f}, "
            f"Test MAE: {metrics['test_mae']:.2f}, "
            f"Test R²: {metrics['test_r2']:.3f}"
        )

        return metrics

    def train_all_models(self, features_by_position: Dict[int, List[Dict]],
                         targets_by_position: Dict[int, List[float]]) -> Dict:
        """
        Train models for all positions.

        Args:
            features_by_position: Dict mapping position -> list of feature dicts
            targets_by_position: Dict mapping position -> list of actual points

        Returns:
            Dict with all training metrics
        """
        all_metrics = {}

        position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

        for position in [1, 2, 3, 4]:
            if position not in features_by_position or not features_by_position[position]:
                logger.warning(f"No training data for position {position}")
                continue

            logger.info(f"Training {position_names[position]} model...")

            features = features_by_position[position]
            targets = targets_by_position[position]

            X, y = self.prepare_training_data(features, targets)
            metrics = self.train_position_model(position, X, y)

            all_metrics[position] = metrics

        logger.info(f"All models trained: {len(all_metrics)} positions")
        return all_metrics

    def predict(self, features: Dict) -> float:
        """
        Predict expected points for a single player.

        Args:
            features: Feature dict from FeatureEngineer

        Returns:
            Predicted points for next gameweek
        """
        position = features['position']

        if self.models[position] is None:
            logger.warning(f"No model trained for position {position}, returning 0")
            return 0.0

        # Convert features to numpy array
        X = np.array([[features[col] for col in self.feature_columns]])

        prediction = self.models[position].predict(X)[0]

        # Ensure non-negative prediction
        return max(0.0, prediction)

    def predict_batch(self, features_list: List[Dict]) -> List[float]:
        """
        Predict expected points for multiple players.

        Args:
            features_list: List of feature dicts

        Returns:
            List of predicted points
        """
        predictions = []

        for features in features_list:
            pred = self.predict(features)
            predictions.append(pred)

        return predictions

    def save_models(self, version: str = 'latest'):
        """
        Save trained models to disk.

        Args:
            version: Version identifier for the models
        """
        for position, model in self.models.items():
            if model is not None:
                model_path = self.model_dir / f'position_{position}_{version}.pkl'
                joblib.dump(model, model_path)
                logger.info(f"Saved position {position} model to {model_path}")

        # Save feature columns
        if self.feature_columns:
            feature_path = self.model_dir / f'feature_columns_{version}.pkl'
            joblib.dump(self.feature_columns, feature_path)
            logger.info(f"Saved feature columns to {feature_path}")

    def load_models(self, version: str = 'latest'):
        """
        Load trained models from disk.

        Args:
            version: Version identifier for the models
        """
        # Load feature columns first
        feature_path = self.model_dir / f'feature_columns_{version}.pkl'
        if feature_path.exists():
            self.feature_columns = joblib.load(feature_path)
            logger.info(f"Loaded feature columns from {feature_path}")
        else:
            logger.warning(f"Feature columns file not found: {feature_path}")

        # Load models
        loaded_count = 0
        for position in [1, 2, 3, 4]:
            model_path = self.model_dir / f'position_{position}_{version}.pkl'
            if model_path.exists():
                self.models[position] = joblib.load(model_path)
                loaded_count += 1
                logger.info(f"Loaded position {position} model from {model_path}")
            else:
                logger.warning(f"Model file not found for position {position}: {model_path}")

        logger.info(f"Loaded {loaded_count} position models")

    def get_feature_importance(self, position: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """
        Get feature importance for a position's model.

        Args:
            position: Position (1-4)
            top_n: Number of top features to return

        Returns:
            List of (feature_name, importance) tuples
        """
        if self.models[position] is None:
            logger.warning(f"No model for position {position}")
            return []

        model = self.models[position]
        importances = model.feature_importances_

        # Create (feature, importance) pairs
        feature_importance = list(zip(self.feature_columns, importances))

        # Sort by importance
        feature_importance.sort(key=lambda x: x[1], reverse=True)

        return feature_importance[:top_n]
