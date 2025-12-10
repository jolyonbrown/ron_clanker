#!/usr/bin/env python3
"""
Player Performance Prediction Models

Position-specific models to predict expected points for next gameweek.
Uses STACKED ENSEMBLE: RandomForest + GradientBoosting + XGBoost + Neural (MLP/LSTM) + Meta-learner
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split, cross_val_score, TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logging.warning("XGBoost not available, falling back to RF+GB ensemble")

# Neural network support (optional - requires PyTorch)
try:
    from .neural_models import PositionNeuralEnsemble, DEVICE
    NEURAL_AVAILABLE = True
except ImportError:
    NEURAL_AVAILABLE = False
    logging.info("Neural models not available (PyTorch not installed)")

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

    def __init__(self, model_dir: Path = None, use_neural: bool = True, neural_version: str = None):
        """
        Initialize stacked ensemble predictor.

        Args:
            model_dir: Directory to save/load trained models
            use_neural: Whether to include neural models (MLP/LSTM) in ensemble
            neural_version: Version tag for neural models (e.g., 'gpu_20251209_1741')
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

        # Neural models (optional GPU-accelerated models)
        self.use_neural = use_neural and NEURAL_AVAILABLE
        self.neural_ensemble = None
        self.neural_version = neural_version

        if self.use_neural:
            self._load_neural_models()

        logger.info(
            f"PlayerPerformancePredictor: Initialized with stacking ensemble "
            f"(XGBoost: {XGBOOST_AVAILABLE}, Neural: {self.use_neural})"
        )

    def _load_neural_models(self):
        """Load pre-trained neural models if available."""
        try:
            neural_dir = Path('models/neural')
            if not neural_dir.exists():
                logger.info("No neural models directory found, skipping neural integration")
                self.use_neural = False
                return

            self.neural_ensemble = PositionNeuralEnsemble(model_dir=neural_dir, use_lstm=True)

            # Auto-detect version if not specified
            if self.neural_version is None:
                # Find the most recent model version
                import glob
                mlp_files = glob.glob(str(neural_dir / 'pos_1' / 'mlp_*.pt'))
                if mlp_files:
                    import os
                    latest = max(mlp_files, key=os.path.getmtime)
                    self.neural_version = Path(latest).stem.replace('mlp_', '')
                    logger.info(f"Auto-detected neural model version: {self.neural_version}")
                else:
                    logger.info("No neural models found, disabling neural integration")
                    self.use_neural = False
                    return

            self.neural_ensemble.load_all(self.neural_version)
            logger.info(f"Loaded neural models (version: {self.neural_version})")

        except Exception as e:
            logger.warning(f"Failed to load neural models: {e}")
            self.use_neural = False

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

    def train_position_model_cv(
        self,
        position: int,
        X: np.ndarray,
        y: np.ndarray,
        gameweeks: np.ndarray = None,
        n_splits: int = 5
    ) -> Dict:
        """
        Train a STACKED ENSEMBLE using TimeSeriesSplit cross-validation.

        This method respects temporal ordering - never trains on future data.
        More robust than fixed splits, especially with limited data.

        Process:
        1. Use TimeSeriesSplit to create temporal folds
        2. For each fold: train base models, generate meta-features
        3. Aggregate performance across folds
        4. Train final model on all data
        5. Return cross-validated metrics

        Args:
            position: Player position (1-4)
            X: Feature matrix
            y: Target values
            gameweeks: Optional gameweek indices for proper temporal ordering
            n_splits: Number of CV folds (default 5)

        Returns:
            Dict with cross-validated training metrics
        """
        logger.info(f"Training position {position} with TimeSeriesSplit CV ({n_splits} folds)")

        # Sort by gameweek if provided (ensures temporal ordering)
        if gameweeks is not None:
            sort_idx = np.argsort(gameweeks)
            X = X[sort_idx]
            y = y[sort_idx]

        tscv = TimeSeriesSplit(n_splits=n_splits)

        # Track metrics across folds
        fold_metrics = {
            'rf_rmse': [], 'gb_rmse': [], 'xgb_rmse': [],
            'ensemble_rmse': [], 'ensemble_mae': [], 'ensemble_r2': []
        }

        # Cross-validation loop
        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train_fold, X_test_fold = X[train_idx], X[test_idx]
            y_train_fold, y_test_fold = y[train_idx], y[test_idx]

            # Further split train into train/val for meta-learner
            split_point = int(len(X_train_fold) * 0.8)
            X_train = X_train_fold[:split_point]
            y_train = y_train_fold[:split_point]
            X_val = X_train_fold[split_point:]
            y_val = y_train_fold[split_point:]

            # Train base models
            base_models = []

            rf = RandomForestRegressor(
                n_estimators=50, max_depth=8, min_samples_split=10,
                min_samples_leaf=5, random_state=42, n_jobs=-1
            )
            rf.fit(X_train, y_train)
            base_models.append(('RandomForest', rf))
            fold_metrics['rf_rmse'].append(
                np.sqrt(mean_squared_error(y_test_fold, rf.predict(X_test_fold)))
            )

            gb = GradientBoostingRegressor(
                n_estimators=50, learning_rate=0.1, max_depth=4,
                min_samples_split=10, min_samples_leaf=5, random_state=42
            )
            gb.fit(X_train, y_train)
            base_models.append(('GradientBoosting', gb))
            fold_metrics['gb_rmse'].append(
                np.sqrt(mean_squared_error(y_test_fold, gb.predict(X_test_fold)))
            )

            if XGBOOST_AVAILABLE:
                xgb_model = xgb.XGBRegressor(
                    n_estimators=50, learning_rate=0.1, max_depth=4,
                    min_child_weight=5, random_state=42, verbosity=0, n_jobs=-1
                )
                xgb_model.fit(X_train, y_train)
                base_models.append(('XGBoost', xgb_model))
                fold_metrics['xgb_rmse'].append(
                    np.sqrt(mean_squared_error(y_test_fold, xgb_model.predict(X_test_fold)))
                )

            # Generate meta-features for validation set
            meta_features_val = np.column_stack([
                model.predict(X_val) for _, model in base_models
            ])

            # Train meta-learner
            meta_model = Ridge(alpha=1.0)
            meta_model.fit(meta_features_val, y_val)

            # Evaluate ensemble on test fold
            meta_features_test = np.column_stack([
                model.predict(X_test_fold) for _, model in base_models
            ])
            y_pred = meta_model.predict(meta_features_test)

            fold_metrics['ensemble_rmse'].append(
                np.sqrt(mean_squared_error(y_test_fold, y_pred))
            )
            fold_metrics['ensemble_mae'].append(
                mean_absolute_error(y_test_fold, y_pred)
            )
            fold_metrics['ensemble_r2'].append(
                r2_score(y_test_fold, y_pred)
            )

            logger.debug(f"  Fold {fold+1}: RMSE={fold_metrics['ensemble_rmse'][-1]:.3f}")

        # Train final model on ALL data
        logger.info("Training final model on all data...")

        # Split all data for meta-learner training
        split_point = int(len(X) * 0.85)
        X_train_final = X[:split_point]
        y_train_final = y[:split_point]
        X_val_final = X[split_point:]
        y_val_final = y[split_point:]

        # Final base models
        final_base_models = []

        rf_final = RandomForestRegressor(
            n_estimators=50, max_depth=8, min_samples_split=10,
            min_samples_leaf=5, random_state=42, n_jobs=-1
        )
        rf_final.fit(X_train_final, y_train_final)
        final_base_models.append(('RandomForest', rf_final))

        gb_final = GradientBoostingRegressor(
            n_estimators=50, learning_rate=0.1, max_depth=4,
            min_samples_split=10, min_samples_leaf=5, random_state=42
        )
        gb_final.fit(X_train_final, y_train_final)
        final_base_models.append(('GradientBoosting', gb_final))

        if XGBOOST_AVAILABLE:
            xgb_final = xgb.XGBRegressor(
                n_estimators=50, learning_rate=0.1, max_depth=4,
                min_child_weight=5, random_state=42, verbosity=0, n_jobs=-1
            )
            xgb_final.fit(X_train_final, y_train_final)
            final_base_models.append(('XGBoost', xgb_final))

        # Final meta-learner
        meta_features_val_final = np.column_stack([
            model.predict(X_val_final) for _, model in final_base_models
        ])
        meta_model_final = Ridge(alpha=1.0)
        meta_model_final.fit(meta_features_val_final, y_val_final)

        # Store final ensemble
        self.models[position] = {
            'base_models': final_base_models,
            'meta_model': meta_model_final
        }

        # Aggregate CV metrics
        metrics = {
            'position': position,
            'cv_method': 'TimeSeriesSplit',
            'n_splits': n_splits,
            'total_samples': len(X),
            'cv_results': {
                'mean_rmse': float(np.mean(fold_metrics['ensemble_rmse'])),
                'std_rmse': float(np.std(fold_metrics['ensemble_rmse'])),
                'mean_mae': float(np.mean(fold_metrics['ensemble_mae'])),
                'std_mae': float(np.std(fold_metrics['ensemble_mae'])),
                'mean_r2': float(np.mean(fold_metrics['ensemble_r2'])),
                'std_r2': float(np.std(fold_metrics['ensemble_r2'])),
            },
            'base_model_cv': {
                'rf_mean_rmse': float(np.mean(fold_metrics['rf_rmse'])),
                'gb_mean_rmse': float(np.mean(fold_metrics['gb_rmse'])),
                'xgb_mean_rmse': float(np.mean(fold_metrics['xgb_rmse'])) if fold_metrics['xgb_rmse'] else None,
            },
            'meta_weights': dict(zip(
                [name for name, _ in final_base_models],
                meta_model_final.coef_.tolist()
            ))
        }

        logger.info(
            f"Position {position} CV complete:\n"
            f"  CV RMSE: {metrics['cv_results']['mean_rmse']:.3f} (+/- {metrics['cv_results']['std_rmse']:.3f})\n"
            f"  CV MAE: {metrics['cv_results']['mean_mae']:.3f} (+/- {metrics['cv_results']['std_mae']:.3f})\n"
            f"  CV R2: {metrics['cv_results']['mean_r2']:.3f} (+/- {metrics['cv_results']['std_r2']:.3f})"
        )

        return metrics

    def train_all_models_cv(
        self,
        features_by_position: Dict[int, List[Dict]],
        targets_by_position: Dict[int, List[float]],
        gameweeks_by_position: Dict[int, List[int]] = None,
        n_splits: int = 5
    ) -> Dict:
        """
        Train models for all positions using TimeSeriesSplit CV.

        Args:
            features_by_position: Dict mapping position -> list of feature dicts
            targets_by_position: Dict mapping position -> list of actual points
            gameweeks_by_position: Optional dict mapping position -> list of gameweek numbers
            n_splits: Number of CV folds

        Returns:
            Dict with all training metrics including CV results
        """
        all_metrics = {}
        position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

        for position in [1, 2, 3, 4]:
            if position not in features_by_position or not features_by_position[position]:
                logger.warning(f"No training data for position {position}")
                continue

            logger.info(f"Training {position_names[position]} with TimeSeriesSplit CV...")

            features = features_by_position[position]
            targets = targets_by_position[position]

            X, y = self.prepare_training_data(features, targets)

            # Get gameweeks if available
            gameweeks = None
            if gameweeks_by_position and position in gameweeks_by_position:
                gameweeks = np.array(gameweeks_by_position[position])

            metrics = self.train_position_model_cv(position, X, y, gameweeks, n_splits)
            all_metrics[position] = metrics

        logger.info(f"All models trained with CV: {len(all_metrics)} positions")
        return all_metrics

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

    def predict(self, features: Dict, form_sequence: np.ndarray = None) -> float:
        """
        Predict expected points for a single player using stacked ensemble.

        The prediction combines:
        1. Traditional ML models (RF, GB, XGBoost)
        2. Neural models (MLP, LSTM) if available and loaded

        Args:
            features: Feature dict from FeatureEngineer
            form_sequence: Optional form sequence for LSTM (shape: seq_len, seq_features)

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

        # Add neural model predictions if available
        if self.use_neural and self.neural_ensemble is not None:
            mlp_pred, lstm_pred = self._get_neural_predictions(position, X, form_sequence)
            if mlp_pred is not None:
                base_predictions.append(mlp_pred)
            if lstm_pred is not None:
                base_predictions.append(lstm_pred)

        # Stack predictions and use meta-learner
        # Note: If we have more predictions than the meta-learner was trained for,
        # we need to average the extra neural predictions separately
        n_base = len(ensemble['base_models'])
        if len(base_predictions) > n_base:
            # Meta-learner only knows about original base models
            # Average neural predictions with ensemble prediction
            traditional_pred = ensemble['meta_model'].predict(
                np.array([base_predictions[:n_base]])
            )[0]
            neural_preds = base_predictions[n_base:]
            neural_avg = np.mean(neural_preds)

            # Weighted combination: 70% traditional, 30% neural
            prediction = 0.7 * traditional_pred + 0.3 * neural_avg
        else:
            meta_features = np.array([base_predictions])
            prediction = ensemble['meta_model'].predict(meta_features)[0]

        # Ensure non-negative prediction
        return max(0.0, prediction)

    def _get_neural_predictions(
        self,
        position: int,
        X: np.ndarray,
        form_sequence: np.ndarray = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Get predictions from neural models.

        Args:
            position: Player position (1-4)
            X: Feature matrix for MLP (may include player_id column which we exclude)
            form_sequence: Form sequence for LSTM

        Returns:
            (mlp_prediction, lstm_prediction) - either can be None
        """
        mlp_pred = None
        lstm_pred = None

        try:
            # Neural models trained without player_id and position columns
            # Position is not needed as input since models are position-specific
            # Remove any player identifier and position columns
            X_neural = X
            if self.feature_columns:
                skip_cols = 0
                for col in self.feature_columns:
                    if col in ('player_id', 'player_code', 'position'):
                        skip_cols += 1
                    else:
                        break
                if skip_cols > 0:
                    X_neural = X[:, skip_cols:]

            if position in self.neural_ensemble.mlp_models:
                mlp_preds = self.neural_ensemble.mlp_models[position].predict(X_neural)
                mlp_pred = float(mlp_preds[0])

            if form_sequence is not None and position in self.neural_ensemble.lstm_models:
                # Add batch dimension
                seq = form_sequence.reshape(1, *form_sequence.shape)
                lstm_preds = self.neural_ensemble.lstm_models[position].predict(seq)
                lstm_pred = float(lstm_preds[0])

        except Exception as e:
            logger.warning(f"Neural prediction failed for position {position}: {e}")

        return mlp_pred, lstm_pred

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
