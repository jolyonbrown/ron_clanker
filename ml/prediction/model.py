#!/usr/bin/env python3
"""
Player Performance Prediction Models

Position-specific models to predict expected points for next gameweek.
Uses STACKED ENSEMBLE: RandomForest + GradientBoosting + XGBoost + Meta-learner
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("XGBoost not available, falling back to RF+GB ensemble")

logger = logging.getLogger('ron_clanker.ml.prediction')


class PlayerPerformancePredictor:
    """
    Predicts player expected points using STACKED ENSEMBLE models.

    Architecture:
    - Base models: RandomForest, GradientBoosting, XGBoost (3 diverse learners)
    - Meta-model: Ridge regression (learns optimal weights)
    - Position-specific: Separate ensembles for GK, DEF, MID, FWD

    Benefits of stacking:
    - 5-10% accuracy improvement over single models
    - More robust to overfitting
    - Captures different aspects of player performance
    """

    def __init__(self, model_dir: Path = None):
        """
        Initialize stacked ensemble predictor.

        Args:
            model_dir: Directory to save/load trained models
        """
        self.model_dir = model_dir or Path('models/prediction')
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # Position-specific STACKED ensembles
        # Each position has: {'base_models': [RF, GB, XGB], 'meta_model': Ridge}
        self.models = {
            1: None,  # GK ensemble
            2: None,  # DEF ensemble
            3: None,  # MID ensemble
            4: None   # FWD ensemble
        }

        # Feature columns (will be set during training)
        self.feature_columns = None

        logger.info(f"PlayerPerformancePredictor: Initialized with stacking ensemble (XGBoost: {XGBOOST_AVAILABLE})")

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
        Train a STACKED ENSEMBLE for a specific position.

        Process:
        1. Split data: 60% train, 20% validation, 20% test
        2. Train base models (RF, GB, XGB) on train set
        3. Generate predictions on validation set (for meta-learner)
        4. Train meta-learner on validation predictions
        5. Evaluate final ensemble on test set

        Returns:
            Dict with training metrics
        """
        logger.info(f"Training stacked ensemble for position {position} with {len(X)} samples")

        # Three-way split: train (60%), validation (20%), test (20%)
        X_temp, X_test, y_temp, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp, test_size=0.25, random_state=42  # 0.25 of 80% = 20% total
        )

        logger.info(f"Split - Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

        # ============================================
        # STEP 1: Train base models
        # ============================================
        base_models = []

        # Model 1: Random Forest (RPi-optimized: fewer trees, shallower)
        logger.info("Training Random Forest...")
        rf = RandomForestRegressor(
            n_estimators=50,  # Reduced from 100 for speed
            max_depth=8,       # Reduced from 10
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        rf.fit(X_train, y_train)
        base_models.append(('RandomForest', rf))

        # Model 2: Gradient Boosting (RPi-optimized: fewer trees)
        logger.info("Training Gradient Boosting...")
        gb = GradientBoostingRegressor(
            n_estimators=50,  # Reduced from 100 for speed
            learning_rate=0.1,
            max_depth=4,       # Reduced from 5
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42
        )
        gb.fit(X_train, y_train)
        base_models.append(('GradientBoosting', gb))

        # Model 3: XGBoost (if available, RPi-optimized)
        if XGBOOST_AVAILABLE:
            logger.info("Training XGBoost...")
            xgb_model = xgb.XGBRegressor(
                n_estimators=50,   # Reduced from 100 for speed
                learning_rate=0.1,
                max_depth=4,        # Reduced from 5
                min_child_weight=5,
                random_state=42,
                verbosity=0,
                n_jobs=2            # Limit parallelism on RPi
            )
            xgb_model.fit(X_train, y_train)
            base_models.append(('XGBoost', xgb_model))

        # ============================================
        # STEP 2: Generate meta-features from validation set
        # ============================================
        meta_features_val = []
        for name, model in base_models:
            preds = model.predict(X_val)
            meta_features_val.append(preds)

        # Stack predictions horizontally: each column is one base model's predictions
        meta_X_val = np.column_stack(meta_features_val)

        # ============================================
        # STEP 3: Train meta-learner
        # ============================================
        logger.info("Training meta-learner (Ridge regression)...")
        meta_model = Ridge(alpha=1.0)
        meta_model.fit(meta_X_val, y_val)

        # ============================================
        # STEP 4: Evaluate on test set
        # ============================================
        # Generate meta-features for test set
        meta_features_test = []
        for name, model in base_models:
            preds = model.predict(X_test)
            meta_features_test.append(preds)
        meta_X_test = np.column_stack(meta_features_test)

        # Final stacked prediction
        y_pred_test = meta_model.predict(meta_X_test)

        # Also get base model predictions for comparison
        individual_test_preds = {}
        for name, model in base_models:
            preds = model.predict(X_test)
            rmse = np.sqrt(mean_squared_error(y_test, preds))
            individual_test_preds[name] = {
                'rmse': rmse,
                'mae': mean_absolute_error(y_test, preds),
                'r2': r2_score(y_test, preds)
            }

        # ============================================
        # STEP 5: Package ensemble and compute metrics
        # ============================================
        ensemble = {
            'base_models': base_models,
            'meta_model': meta_model
        }
        self.models[position] = ensemble

        metrics = {
            'position': position,
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test),
            'ensemble': {
                'test_rmse': np.sqrt(mean_squared_error(y_test, y_pred_test)),
                'test_mae': mean_absolute_error(y_test, y_pred_test),
                'test_r2': r2_score(y_test, y_pred_test)
            },
            'base_models': individual_test_preds,
            'meta_weights': dict(zip([name for name, _ in base_models], meta_model.coef_))
        }

        logger.info(
            f"Position {position} stacked ensemble trained:\n"
            f"  Final Test RMSE: {metrics['ensemble']['test_rmse']:.2f}\n"
            f"  Final Test MAE: {metrics['ensemble']['test_mae']:.2f}\n"
            f"  Final Test R²: {metrics['ensemble']['test_r2']:.3f}\n"
            f"  Meta-learner weights: {metrics['meta_weights']}"
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
        Predict expected points for a single player using stacked ensemble.

        Args:
            features: Feature dict from FeatureEngineer

        Returns:
            Predicted points for next gameweek
        """
        position = features['position']

        ensemble = self.models[position]
        if ensemble is None:
            logger.warning(f"No ensemble trained for position {position}, returning 0")
            return 0.0

        # Convert features to numpy array
        X = np.array([[features[col] for col in self.feature_columns]])

        # Get predictions from all base models
        base_predictions = []
        for name, model in ensemble['base_models']:
            pred = model.predict(X)[0]
            base_predictions.append(pred)

        # Stack predictions and use meta-learner
        meta_features = np.array([base_predictions])
        prediction = ensemble['meta_model'].predict(meta_features)[0]

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
        Save trained stacked ensemble models to disk.

        Args:
            version: Version identifier for the models
        """
        for position, ensemble in self.models.items():
            if ensemble is not None:
                # Save the entire ensemble (base_models + meta_model)
                ensemble_path = self.model_dir / f'ensemble_{position}_{version}.pkl'
                joblib.dump(ensemble, ensemble_path)
                logger.info(f"Saved position {position} stacked ensemble to {ensemble_path}")

        # Save feature columns
        if self.feature_columns:
            feature_path = self.model_dir / f'feature_columns_{version}.pkl'
            joblib.dump(self.feature_columns, feature_path)
            logger.info(f"Saved feature columns to {feature_path}")

    def get_latest_model_version(self) -> str:
        """
        Auto-detect the most recently trained model version.

        Returns:
            Model version string (e.g., 'gw9_ict') or 'latest' if none found
        """
        import glob
        import os

        # Find all model files and get their modification times
        model_files = glob.glob(str(self.model_dir / 'ensemble_1_*.pkl'))

        if not model_files:
            logger.warning("No model files found, defaulting to 'latest'")
            return 'latest'

        # Get the most recently modified model file
        latest_file = max(model_files, key=os.path.getmtime)

        # Extract version from filename: ensemble_1_VERSION.pkl -> VERSION
        version = Path(latest_file).stem.replace('ensemble_1_', '')

        logger.info(f"Auto-detected latest model version: {version}")
        return version

    def load_models(self, version: str = None):
        """
        Load trained stacked ensemble models from disk.

        Args:
            version: Version identifier for the models. If None, auto-detects latest trained model.
        """
        # Auto-detect latest version if not specified
        if version is None:
            version = self.get_latest_model_version()
            logger.info(f"Using auto-detected model version: {version}")
        # Load feature columns first
        feature_path = self.model_dir / f'feature_columns_{version}.pkl'
        if feature_path.exists():
            self.feature_columns = joblib.load(feature_path)
            logger.info(f"Loaded feature columns from {feature_path}")
        else:
            logger.warning(f"Feature columns file not found: {feature_path}")

        # Load stacked ensembles
        loaded_count = 0
        for position in [1, 2, 3, 4]:
            ensemble_path = self.model_dir / f'ensemble_{position}_{version}.pkl'

            # Try new ensemble format first
            if ensemble_path.exists():
                self.models[position] = joblib.load(ensemble_path)
                loaded_count += 1
                logger.info(f"Loaded position {position} stacked ensemble from {ensemble_path}")
            else:
                # Fallback: try old single-model format for backward compatibility
                old_path = self.model_dir / f'position_{position}_{version}.pkl'
                if old_path.exists():
                    old_model = joblib.load(old_path)
                    # Wrap single model in ensemble structure
                    self.models[position] = {
                        'base_models': [('LegacyModel', old_model)],
                        'meta_model': Ridge(alpha=0.0)  # Identity meta-model
                    }
                    # Fit meta-model to pass through single prediction
                    self.models[position]['meta_model'].coef_ = np.array([1.0])
                    self.models[position]['meta_model'].intercept_ = 0.0
                    loaded_count += 1
                    logger.info(f"Loaded legacy position {position} model (converted to ensemble)")
                else:
                    logger.warning(f"Ensemble file not found for position {position}: {ensemble_path}")

        logger.info(f"Loaded {loaded_count} position ensembles")

    def get_feature_importance(self, position: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """
        Get aggregated feature importance for a position's stacked ensemble.

        Averages feature importance across all tree-based base models (RF, GB, XGB),
        weighted by meta-learner coefficients.

        Args:
            position: Position (1-4)
            top_n: Number of top features to return

        Returns:
            List of (feature_name, importance) tuples
        """
        ensemble = self.models[position]
        if ensemble is None:
            logger.warning(f"No ensemble for position {position}")
            return []

        # Aggregate importance from tree-based models
        aggregated_importance = np.zeros(len(self.feature_columns))
        total_weight = 0.0

        for i, (name, model) in enumerate(ensemble['base_models']):
            # Only tree-based models have feature_importances_
            if hasattr(model, 'feature_importances_'):
                # Weight by meta-learner coefficient
                meta_weight = ensemble['meta_model'].coef_[i]
                aggregated_importance += model.feature_importances_ * abs(meta_weight)
                total_weight += abs(meta_weight)

        # Normalize
        if total_weight > 0:
            aggregated_importance /= total_weight

        # Create (feature, importance) pairs
        feature_importance = list(zip(self.feature_columns, aggregated_importance))

        # Sort by importance
        feature_importance.sort(key=lambda x: x[1], reverse=True)

        return feature_importance[:top_n]
