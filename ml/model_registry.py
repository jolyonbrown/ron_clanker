"""
Model Registry

Tracks trained ML models, their metadata, and performance metrics.
Enables versioning, rollback, and performance comparison.

Usage:
    registry = ModelRegistry(db_path)

    # Register a new model
    model_id = registry.register_model(
        model_name='ensemble',
        model_type='xp_prediction',
        version='historical_20251202',
        position=3,
        file_path='models/prediction/ensemble_3_historical_20251202.pkl',
        hyperparameters={'n_estimators': 100, ...},
        metrics={'rmse': 2.80, 'mae': 1.87},
        training_samples=14192
    )

    # Activate as production model
    registry.activate_model(model_id)

    # Get active model info
    model_info = registry.get_active_model('ensemble', 'xp_prediction', position=3)

    # Load the actual model
    model = registry.load_model(model_id)
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import joblib

logger = logging.getLogger('ron_clanker.model_registry')


class ModelRegistry:
    """
    Registry for tracking ML model versions and metadata.

    Supports:
    - Model versioning with metadata
    - Activation/deactivation (rollback)
    - Performance tracking per gameweek
    - Feature column management
    """

    def __init__(self, db_path: str = 'data/ron_clanker.db', models_dir: str = 'models/prediction'):
        self.db_path = db_path
        self.models_dir = Path(models_dir)
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure registry tables exist."""
        migration_path = Path('data/migrations/005_model_registry.sql')
        if migration_path.exists():
            conn = sqlite3.connect(self.db_path)
            try:
                with open(migration_path) as f:
                    conn.executescript(f.read())
                conn.commit()
            except sqlite3.OperationalError as e:
                # Tables may already exist
                if 'already exists' not in str(e):
                    logger.warning(f"Migration warning: {e}")
            finally:
                conn.close()

    def register_model(
        self,
        model_name: str,
        model_type: str,
        version: str,
        file_path: str,
        position: Optional[int] = None,
        feature_columns_path: Optional[str] = None,
        hyperparameters: Optional[Dict] = None,
        metrics: Optional[Dict] = None,
        training_samples: Optional[int] = None,
        training_duration_seconds: Optional[float] = None,
        training_data_start: Optional[str] = None,
        training_data_end: Optional[str] = None,
        activate: bool = False
    ) -> int:
        """
        Register a new model in the registry.

        Args:
            model_name: Name of the model (e.g., 'ensemble', 'price_predictor')
            model_type: Type of prediction (e.g., 'xp_prediction', 'price_change')
            version: Version identifier (e.g., 'historical_20251202')
            file_path: Path to model file (relative to project root)
            position: Position number (1-4) for position-specific models
            feature_columns_path: Path to feature columns file
            hyperparameters: Dictionary of hyperparameters used
            metrics: Dictionary of evaluation metrics
            training_samples: Number of samples used for training
            training_duration_seconds: How long training took
            training_data_start: Earliest date in training data
            training_data_end: Latest date in training data
            activate: If True, activate this model after registration

        Returns:
            Model ID in registry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO model_registry (
                    model_name, model_type, version, position, file_path,
                    feature_columns_path, hyperparameters, metrics,
                    training_samples, training_duration_seconds,
                    training_data_start, training_data_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                model_name, model_type, version, position, file_path,
                feature_columns_path,
                json.dumps(hyperparameters) if hyperparameters else None,
                json.dumps(metrics) if metrics else None,
                training_samples, training_duration_seconds,
                training_data_start, training_data_end
            ))

            model_id = cursor.lastrowid
            conn.commit()

            logger.info(f"Registered model: {model_name}/{model_type} v{version} (id={model_id})")

            if activate:
                self.activate_model(model_id)

            return model_id

        except sqlite3.IntegrityError:
            # Model version already exists, get its ID
            cursor.execute("""
                SELECT id FROM model_registry
                WHERE model_name = ? AND model_type = ? AND version = ?
                AND (position = ? OR (position IS NULL AND ? IS NULL))
            """, (model_name, model_type, version, position, position))
            row = cursor.fetchone()
            if row:
                logger.info(f"Model already registered: {model_name}/{model_type} v{version}")
                return row[0]
            raise
        finally:
            conn.close()

    def activate_model(self, model_id: int):
        """
        Activate a model as the production version.

        Deactivates any other active models of the same type/position.

        Args:
            model_id: ID of model to activate
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get model info
            cursor.execute("""
                SELECT model_name, model_type, position FROM model_registry WHERE id = ?
            """, (model_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Model {model_id} not found")

            model_name, model_type, position = row

            # Deactivate current active model(s) of same type
            if position is not None:
                cursor.execute("""
                    UPDATE model_registry
                    SET is_active = FALSE, deactivated_at = ?
                    WHERE model_name = ? AND model_type = ? AND position = ? AND is_active = TRUE
                """, (datetime.now().isoformat(), model_name, model_type, position))
            else:
                cursor.execute("""
                    UPDATE model_registry
                    SET is_active = FALSE, deactivated_at = ?
                    WHERE model_name = ? AND model_type = ? AND position IS NULL AND is_active = TRUE
                """, (datetime.now().isoformat(), model_name, model_type))

            # Activate new model
            cursor.execute("""
                UPDATE model_registry SET is_active = TRUE WHERE id = ?
            """, (model_id,))

            conn.commit()
            logger.info(f"Activated model {model_id}: {model_name}/{model_type} position={position}")

        finally:
            conn.close()

    def deactivate_model(self, model_id: int):
        """Deactivate a model."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                UPDATE model_registry
                SET is_active = FALSE, deactivated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), model_id))
            conn.commit()
        finally:
            conn.close()

    def get_active_model(
        self,
        model_name: str,
        model_type: str,
        position: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Get info about the currently active model.

        Args:
            model_name: Model name
            model_type: Model type
            position: Position number (optional)

        Returns:
            Dictionary with model info, or None if no active model
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if position is not None:
                cursor.execute("""
                    SELECT * FROM model_registry
                    WHERE model_name = ? AND model_type = ? AND position = ? AND is_active = TRUE
                """, (model_name, model_type, position))
            else:
                cursor.execute("""
                    SELECT * FROM model_registry
                    WHERE model_name = ? AND model_type = ? AND position IS NULL AND is_active = TRUE
                """, (model_name, model_type))

            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
            return None
        finally:
            conn.close()

    def get_model_by_id(self, model_id: int) -> Optional[Dict]:
        """Get model info by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM model_registry WHERE id = ?", (model_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
            return None
        finally:
            conn.close()

    def get_model_by_version(
        self,
        model_name: str,
        model_type: str,
        version: str,
        position: Optional[int] = None
    ) -> Optional[Dict]:
        """Get model info by version."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if position is not None:
                cursor.execute("""
                    SELECT * FROM model_registry
                    WHERE model_name = ? AND model_type = ? AND version = ? AND position = ?
                """, (model_name, model_type, version, position))
            else:
                cursor.execute("""
                    SELECT * FROM model_registry
                    WHERE model_name = ? AND model_type = ? AND version = ? AND position IS NULL
                """, (model_name, model_type, version))

            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
            return None
        finally:
            conn.close()

    def list_models(
        self,
        model_name: Optional[str] = None,
        model_type: Optional[str] = None,
        active_only: bool = False
    ) -> List[Dict]:
        """List models matching criteria."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            query = "SELECT * FROM model_registry WHERE 1=1"
            params = []

            if model_name:
                query += " AND model_name = ?"
                params.append(model_name)

            if model_type:
                query += " AND model_type = ?"
                params.append(model_type)

            if active_only:
                query += " AND is_active = TRUE"

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            return [self._row_to_dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def load_model(self, model_id: int) -> Any:
        """
        Load a model from disk.

        Args:
            model_id: Model ID in registry

        Returns:
            Loaded model object
        """
        model_info = self.get_model_by_id(model_id)
        if not model_info:
            raise ValueError(f"Model {model_id} not found")

        file_path = Path(model_info['file_path'])
        if not file_path.exists():
            raise FileNotFoundError(f"Model file not found: {file_path}")

        return joblib.load(file_path)

    def load_active_model(
        self,
        model_name: str,
        model_type: str,
        position: Optional[int] = None
    ) -> Any:
        """Load the currently active model."""
        model_info = self.get_active_model(model_name, model_type, position)
        if not model_info:
            raise ValueError(f"No active model found: {model_name}/{model_type} position={position}")

        return self.load_model(model_info['id'])

    def load_feature_columns(self, model_id: int) -> Optional[List[str]]:
        """Load feature columns for a model."""
        model_info = self.get_model_by_id(model_id)
        if not model_info or not model_info.get('feature_columns_path'):
            return None

        file_path = Path(model_info['feature_columns_path'])
        if not file_path.exists():
            return None

        return joblib.load(file_path)

    def record_prediction(
        self,
        model_id: int,
        gameweek: int,
        player_id: int,
        predicted_value: float
    ):
        """Record a model prediction (actual value filled in later)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT INTO model_predictions (model_id, gameweek, player_id, predicted_value)
                VALUES (?, ?, ?, ?)
            """, (model_id, gameweek, player_id, predicted_value))
            conn.commit()
        finally:
            conn.close()

    def update_actuals(self, gameweek: int, player_actuals: Dict[int, float]):
        """
        Update predictions with actual values after gameweek completes.

        Args:
            gameweek: Gameweek number
            player_actuals: Dict mapping player_id to actual points
        """
        conn = sqlite3.connect(self.db_path)
        try:
            for player_id, actual in player_actuals.items():
                conn.execute("""
                    UPDATE model_predictions
                    SET actual_value = ?, prediction_error = ? - predicted_value
                    WHERE gameweek = ? AND player_id = ?
                """, (actual, actual, gameweek, player_id))
            conn.commit()
        finally:
            conn.close()

    def calculate_performance(self, model_id: int, gameweek: int) -> Dict[str, float]:
        """
        Calculate performance metrics for a model on a specific gameweek.

        Args:
            model_id: Model ID
            gameweek: Gameweek number

        Returns:
            Dictionary with metrics (rmse, mae, r2)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT predicted_value, actual_value
                FROM model_predictions
                WHERE model_id = ? AND gameweek = ? AND actual_value IS NOT NULL
            """, (model_id, gameweek))

            rows = cursor.fetchall()
            if not rows:
                return {}

            predictions = [r[0] for r in rows]
            actuals = [r[1] for r in rows]

            import numpy as np

            errors = np.array(actuals) - np.array(predictions)
            rmse = np.sqrt(np.mean(errors ** 2))
            mae = np.mean(np.abs(errors))

            # R2 score
            ss_res = np.sum(errors ** 2)
            ss_tot = np.sum((np.array(actuals) - np.mean(actuals)) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            metrics = {
                'rmse': float(rmse),
                'mae': float(mae),
                'r2': float(r2),
                'sample_count': len(rows)
            }

            # Store in performance table
            for metric_name, value in metrics.items():
                if metric_name != 'sample_count':
                    conn.execute("""
                        INSERT OR REPLACE INTO model_performance
                        (model_id, gameweek, metric_name, metric_value, sample_count)
                        VALUES (?, ?, ?, ?, ?)
                    """, (model_id, gameweek, metric_name, value, len(rows)))

            conn.commit()
            return metrics

        finally:
            conn.close()

    def get_performance_history(
        self,
        model_id: int,
        metric_name: str = 'rmse'
    ) -> List[Dict]:
        """Get performance history for a model."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT gameweek, metric_value, sample_count, created_at
                FROM model_performance
                WHERE model_id = ? AND metric_name = ?
                ORDER BY gameweek
            """, (model_id, metric_name))

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert database row to dictionary with parsed JSON fields."""
        d = dict(row)

        # Parse JSON fields
        if d.get('hyperparameters'):
            d['hyperparameters'] = json.loads(d['hyperparameters'])
        if d.get('metrics'):
            d['metrics'] = json.loads(d['metrics'])

        return d

    def import_existing_models(self):
        """
        Import existing model files into the registry.

        Scans the models directory and registers any untracked models.
        """
        import re

        # Pattern for ensemble models: ensemble_{position}_{version}.pkl
        ensemble_pattern = re.compile(r'ensemble_(\d)_(.+)\.pkl$')
        feature_pattern = re.compile(r'feature_columns_(.+)\.pkl$')

        # Get existing registered versions
        existing = set()
        for model in self.list_models():
            existing.add((model['model_name'], model['version'], model['position']))

        # Scan for ensemble models
        for file_path in self.models_dir.glob('ensemble_*.pkl'):
            if file_path.is_symlink():
                continue  # Skip symlinks

            match = ensemble_pattern.match(file_path.name)
            if match:
                position = int(match.group(1))
                version = match.group(2)

                if ('ensemble', version, position) in existing:
                    continue

                # Look for corresponding feature columns
                feature_path = self.models_dir / f'feature_columns_{version}.pkl'
                feature_path_str = str(feature_path) if feature_path.exists() else None

                # Look for metrics file
                metrics = None
                metrics_path = self.models_dir / f'metrics_{version}.json'
                if metrics_path.exists():
                    with open(metrics_path) as f:
                        all_metrics = json.load(f)
                        if str(position) in all_metrics:
                            metrics = all_metrics[str(position)]

                self.register_model(
                    model_name='ensemble',
                    model_type='xp_prediction',
                    version=version,
                    position=position,
                    file_path=str(file_path),
                    feature_columns_path=feature_path_str,
                    metrics=metrics.get('cv_results') if metrics else None,
                    training_samples=metrics.get('total_samples') if metrics else None
                )

        logger.info("Import complete")


def get_registry(db_path: str = 'data/ron_clanker.db') -> ModelRegistry:
    """Get a ModelRegistry instance."""
    return ModelRegistry(db_path)
