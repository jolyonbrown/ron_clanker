#!/usr/bin/env python3
"""
ML Prediction Service
=====================

A clean, well-documented interface for all ML prediction capabilities.
Designed to be consumed by any agent architecture - current or future.

USAGE FOR FUTURE AGENTS
-----------------------

Basic usage:
    from services import MLPredictionService

    # Initialize once (loads models, connects to database)
    service = MLPredictionService()

    # Get predictions for specific players
    predictions = service.predict_player_points(
        player_ids=[123, 456, 789],
        gameweek=15
    )
    # Returns: {123: 6.5, 456: 4.2, 789: 8.1}

    # Get predictions for ALL players
    all_predictions = service.predict_all_players(gameweek=15)

    # Get price change predictions
    price_predictions = service.predict_price_changes(player_ids=[123, 456])
    # Returns: {123: ('rise', 0.85), 456: ('hold', 0.92)}

    # Check model health
    info = service.get_model_info()
    # Returns: {'version': 'gw13_full', 'positions': [1,2,3,4], ...}


WHAT THIS SERVICE PROVIDES
--------------------------

1. PLAYER PERFORMANCE PREDICTIONS (expected points)
   - Uses trained stacked ensemble models (RF + GB + XGB + Ridge meta-learner)
   - Position-specific models (GK, DEF, MID, FWD)
   - Automatic feature engineering from historical data
   - News/injury adjustments applied automatically
   - Graceful fallback to form-based predictions if models unavailable

2. PRICE CHANGE PREDICTIONS
   - Predicts rise/fall/hold with confidence scores
   - Based on net transfers and ownership trends

3. MODEL MANAGEMENT
   - Automatic version detection
   - Model registry with metadata
   - Performance tracking

4. ROBUSTNESS
   - Never throws exceptions to callers (returns safe defaults)
   - Logs all issues for debugging
   - Handles missing data gracefully


ARCHITECTURE NOTES FOR DEVELOPERS
---------------------------------

The service wraps:
    - ml/prediction/model.py (PlayerPerformancePredictor)
    - ml/prediction/features.py (FeatureEngineer)
    - ml/prediction/news_adjustment.py (NewsAwarePredictionAdjuster)
    - models/price_change.py (PriceChangePredictor)

Data flows:
    1. Feature Engineering: Reads player_gameweek_history, players, fixtures
    2. Model Inference: Uses saved .pkl files from models/prediction/
    3. Adjustments: Applies news intelligence from scout_events table
    4. Output: Returns simple Dict[player_id -> expected_points]

To retrain models:
    python scripts/train_prediction_models.py --train-end <gameweek>

Model storage:
    models/prediction/ensemble_{position}_{version}.pkl
    models/prediction/feature_columns_{version}.pkl


EXTENDING THIS SERVICE
----------------------

To add a new prediction capability:
    1. Add method to this class with clear docstring
    2. Handle exceptions internally, return safe defaults
    3. Log all operations for debugging
    4. Update get_model_info() to include new capability

To integrate with new agent:
    1. Import MLPredictionService
    2. Call methods as needed
    3. Handle returned Dict/Tuple appropriately
    4. Check get_model_info() if you need to verify model availability
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger('ron_clanker.services.ml')


class MLPredictionService:
    """
    Unified ML prediction service for FPL player performance and price changes.

    Thread-safe, stateless (after initialization), designed for any consumer.

    Attributes:
        models_loaded: Whether prediction models are available
        model_version: Current model version string
        available_positions: List of positions with trained models [1,2,3,4]
    """

    def __init__(self, database=None, model_dir: Path = None, auto_load: bool = True):
        """
        Initialize the ML Prediction Service.

        Args:
            database: Database connection. If None, creates new connection.
            model_dir: Directory containing trained models. Default: models/prediction/
            auto_load: Whether to load models immediately. Set False for testing.

        Example:
            # Standard usage
            service = MLPredictionService()

            # Custom database connection
            from data.database import Database
            db = Database(db_path='custom.db')
            service = MLPredictionService(database=db)

            # Delayed model loading
            service = MLPredictionService(auto_load=False)
            service.load_models()  # Load manually when ready
        """
        # Import dependencies here to avoid circular imports
        from data.database import Database
        from ml.prediction.model import PlayerPerformancePredictor
        from ml.prediction.features import FeatureEngineer

        self._db = database or Database()
        self._model_dir = model_dir or Path('models/prediction')

        # Initialize predictors
        self._performance_predictor = PlayerPerformancePredictor(model_dir=self._model_dir)
        self._feature_engineer = FeatureEngineer(self._db)
        self._news_adjuster = None  # Lazy load
        self._price_predictor = None  # Lazy load
        self._learning_adjustments = None  # Lazy load

        # State tracking
        self.models_loaded = False
        self.model_version = None
        self.available_positions = []
        self.apply_learning_adjustments = True  # Enable feedback-based corrections

        if auto_load:
            self.load_models()

        logger.info(f"MLPredictionService initialized (models_loaded={self.models_loaded})")

    def load_models(self, version: str = None, use_registry: bool = True) -> bool:
        """
        Load trained prediction models.

        Args:
            version: Specific version to load (e.g., 'gw13_full').
                     If None, auto-detects latest trained model.
            use_registry: If True, consult model registry for active models.
                          Default True.

        Returns:
            True if models loaded successfully, False otherwise.

        Example:
            service.load_models()  # Load latest from registry
            service.load_models('gw10_ict')  # Load specific version
            service.load_models(use_registry=False)  # Skip registry, use symlinks
        """
        try:
            # Try loading from registry first
            if use_registry and version is None:
                loaded_version = self._load_from_registry()
                if loaded_version:
                    self.model_version = loaded_version
                    self.available_positions = [
                        pos for pos, model in self._performance_predictor.models.items()
                        if model is not None
                    ]
                    self.models_loaded = len(self.available_positions) > 0
                    logger.info(f"Models loaded from registry: version={self.model_version}")
                    return self.models_loaded

            # Fall back to direct loading
            self._performance_predictor.load_models(version=version)
            self.model_version = version or self._performance_predictor.get_latest_model_version()
            self.available_positions = [
                pos for pos, model in self._performance_predictor.models.items()
                if model is not None
            ]
            self.models_loaded = len(self.available_positions) > 0
            logger.info(f"Models loaded: version={self.model_version}, positions={self.available_positions}")
            return self.models_loaded
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            self.models_loaded = False
            return False

    def _load_from_registry(self) -> Optional[str]:
        """Load active models from registry. Returns version string or None."""
        try:
            from ml.model_registry import ModelRegistry
            import joblib

            registry = ModelRegistry()
            loaded_any = False
            version = None

            for pos in [1, 2, 3, 4]:
                active = registry.get_active_model('ensemble', 'xp_prediction', pos)
                if active and Path(active['file_path']).exists():
                    model = joblib.load(active['file_path'])
                    self._performance_predictor.models[pos] = model
                    loaded_any = True
                    version = active['version']  # Use last loaded version

                    # Load feature columns if available
                    if active.get('feature_columns_path') and Path(active['feature_columns_path']).exists():
                        self._performance_predictor.feature_columns = joblib.load(active['feature_columns_path'])

            return version if loaded_any else None

        except Exception as e:
            logger.debug(f"Registry loading failed, falling back: {e}")
            return None

    def predict_player_points(
        self,
        player_ids: List[int],
        gameweek: int,
        apply_news_adjustments: bool = True
    ) -> Dict[int, float]:
        """
        Predict expected points for specified players.

        This is the primary prediction method. Returns expected points (xP)
        for each player for the target gameweek.

        Args:
            player_ids: List of FPL player IDs to predict
            gameweek: Target gameweek number
            apply_news_adjustments: Whether to apply injury/news adjustments.
                                    Default True. Set False for raw model output.

        Returns:
            Dict mapping player_id -> expected_points (float).
            Missing players return 0.0 in the dict.

        Example:
            predictions = service.predict_player_points([123, 456], gameweek=15)
            print(f"Player 123 xP: {predictions[123]:.2f}")

        Notes:
            - Returns 0.0 for unavailable players (injured status='u')
            - Falls back to form-based prediction if ML model unavailable
            - News adjustments reduce xP for injured/doubtful players
        """
        predictions = {}

        for player_id in player_ids:
            try:
                xp = self._predict_single_player(player_id, gameweek)
                predictions[player_id] = xp
            except Exception as e:
                logger.warning(f"Prediction failed for player {player_id}: {e}")
                predictions[player_id] = 0.0

        # Apply news adjustments if requested
        if apply_news_adjustments and predictions:
            predictions = self._apply_news_adjustments(predictions, gameweek)

        return predictions

    def predict_all_players(
        self,
        gameweek: int,
        apply_news_adjustments: bool = True,
        exclude_unavailable: bool = True
    ) -> Dict[int, float]:
        """
        Predict expected points for ALL players in the database.

        Args:
            gameweek: Target gameweek number
            apply_news_adjustments: Whether to apply injury/news adjustments
            exclude_unavailable: If True, skips players with status='u'

        Returns:
            Dict mapping player_id -> expected_points for all players

        Example:
            all_predictions = service.predict_all_players(gameweek=15)
            top_players = sorted(all_predictions.items(), key=lambda x: x[1], reverse=True)[:10]

        Notes:
            - This can take 10-30 seconds for ~700 players
            - Consider caching results for the same gameweek
        """
        # Get all player IDs
        status_filter = "AND status != 'u'" if exclude_unavailable else ""
        players = self._db.execute_query(f"""
            SELECT id FROM players
            WHERE 1=1 {status_filter}
            ORDER BY id
        """)

        if not players:
            logger.warning("No players found in database")
            return {}

        player_ids = [p['id'] for p in players]
        return self.predict_player_points(player_ids, gameweek, apply_news_adjustments)

    def predict_price_changes(
        self,
        player_ids: List[int] = None
    ) -> Dict[int, Tuple[str, float]]:
        """
        Predict price changes for specified players.

        Args:
            player_ids: List of player IDs. If None, predicts for all players.

        Returns:
            Dict mapping player_id -> (prediction, confidence)
            prediction is one of: 'rise', 'fall', 'hold'
            confidence is a float between 0.0 and 1.0

        Example:
            price_preds = service.predict_price_changes([123, 456])
            for pid, (pred, conf) in price_preds.items():
                print(f"Player {pid}: {pred} ({conf:.0%} confidence)")
        """
        # Lazy load price predictor
        if self._price_predictor is None:
            try:
                from models.price_change import PriceChangePredictor
                self._price_predictor = PriceChangePredictor()
                self._price_predictor.load_model()
            except Exception as e:
                logger.error(f"Failed to load price predictor: {e}")
                return {}

        # Get player IDs if not specified
        if player_ids is None:
            players = self._db.execute_query("SELECT id FROM players WHERE status != 'u'")
            player_ids = [p['id'] for p in players] if players else []

        predictions = {}
        change_map = {-1: 'fall', 0: 'hold', 1: 'rise'}

        for player_id in player_ids:
            try:
                player_data = self._get_player_for_price_prediction(player_id)
                if player_data:
                    change, confidence = self._price_predictor.predict(player_data)
                    predictions[player_id] = (change_map.get(change, 'hold'), confidence)
                else:
                    predictions[player_id] = ('hold', 0.5)
            except Exception as e:
                logger.warning(f"Price prediction failed for {player_id}: {e}")
                predictions[player_id] = ('hold', 0.5)

        return predictions

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about loaded models and service status.

        Returns:
            Dict with:
                - models_loaded: bool
                - model_version: str or None
                - available_positions: List[int]
                - feature_columns: List[str] if available
                - model_dir: str
                - price_predictor_available: bool
                - registry_info: Dict with active model info from registry

        Example:
            info = service.get_model_info()
            if not info['models_loaded']:
                print("Warning: Using fallback predictions")
        """
        # Get registry info if available
        registry_info = {}
        try:
            from ml.model_registry import ModelRegistry
            registry = ModelRegistry()
            for pos in [1, 2, 3, 4]:
                active = registry.get_active_model('ensemble', 'xp_prediction', pos)
                if active:
                    registry_info[pos] = {
                        'id': active['id'],
                        'version': active['version'],
                        'training_samples': active.get('training_samples'),
                        'metrics': active.get('metrics', {})
                    }
        except Exception as e:
            logger.debug(f"Registry info not available: {e}")

        return {
            'models_loaded': self.models_loaded,
            'model_version': self.model_version,
            'available_positions': self.available_positions,
            'feature_columns': self._performance_predictor.feature_columns or [],
            'model_dir': str(self._model_dir),
            'price_predictor_available': self._price_predictor is not None,
            'position_names': {
                1: 'Goalkeeper',
                2: 'Defender',
                3: 'Midfielder',
                4: 'Forward'
            },
            'registry_info': registry_info
        }

    def get_feature_importance(self, position: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """
        Get feature importance for a position's model.

        Useful for understanding what drives predictions.

        Args:
            position: 1=GK, 2=DEF, 3=MID, 4=FWD
            top_n: Number of top features to return

        Returns:
            List of (feature_name, importance_score) tuples, sorted by importance.

        Example:
            importance = service.get_feature_importance(position=4, top_n=5)
            for feature, score in importance:
                print(f"{feature}: {score:.3f}")
        """
        if not self.models_loaded:
            return []
        return self._performance_predictor.get_feature_importance(position, top_n)

    def get_prediction_with_breakdown(
        self,
        player_id: int,
        gameweek: int
    ) -> Dict[str, Any]:
        """
        Get detailed prediction breakdown for a single player.

        Useful for debugging and understanding predictions.

        Args:
            player_id: FPL player ID
            gameweek: Target gameweek

        Returns:
            Dict with:
                - player_id: int
                - player_name: str
                - position: int
                - raw_prediction: float (before news adjustment)
                - adjusted_prediction: float (after news adjustment)
                - features: Dict of engineered features
                - base_model_predictions: Dict (if available)
                - news_adjustments: Dict (if applicable)

        Example:
            breakdown = service.get_prediction_with_breakdown(123, 15)
            print(f"Raw: {breakdown['raw_prediction']:.2f}")
            print(f"Adjusted: {breakdown['adjusted_prediction']:.2f}")
        """
        result = {
            'player_id': player_id,
            'player_name': None,
            'position': None,
            'raw_prediction': 0.0,
            'adjusted_prediction': 0.0,
            'features': {},
            'base_model_predictions': {},
            'news_adjustments': {}
        }

        try:
            # Get player info
            player = self._db.execute_query(
                "SELECT web_name, element_type FROM players WHERE id = ?",
                (player_id,)
            )
            if player:
                result['player_name'] = player[0]['web_name']
                result['position'] = player[0]['element_type']

            # Get features
            features = self._feature_engineer.engineer_features(player_id, gameweek)
            if features:
                result['features'] = features

                # Get raw prediction
                if self.models_loaded:
                    raw_xp = self._performance_predictor.predict(features)
                    result['raw_prediction'] = float(raw_xp)
                else:
                    result['raw_prediction'] = self._fallback_prediction(player_id)

            # Get adjusted prediction
            adjusted = self._apply_news_adjustments({player_id: result['raw_prediction']}, gameweek)
            result['adjusted_prediction'] = adjusted.get(player_id, result['raw_prediction'])

            # Calculate adjustment
            if result['raw_prediction'] > 0:
                adjustment_factor = result['adjusted_prediction'] / result['raw_prediction']
                result['news_adjustments'] = {
                    'adjustment_factor': adjustment_factor,
                    'points_changed': result['adjusted_prediction'] - result['raw_prediction']
                }

        except Exception as e:
            logger.error(f"Breakdown failed for player {player_id}: {e}")

        return result

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _predict_single_player(self, player_id: int, gameweek: int) -> float:
        """Generate prediction for a single player."""
        # Get player features
        features = self._feature_engineer.engineer_features(player_id, gameweek)

        if not features:
            logger.debug(f"No features for player {player_id}, using fallback")
            raw_prediction = self._fallback_prediction(player_id)
        elif self.models_loaded:
            # Use ML model
            raw_prediction = float(max(0.0, self._performance_predictor.predict(features)))
        else:
            # Fallback to form-based prediction
            raw_prediction = self._fallback_prediction(player_id)

        # Apply learning adjustments (bias corrections from previous gameweeks)
        adjusted_prediction = self._apply_learning_adjustments_to_prediction(player_id, raw_prediction)

        return adjusted_prediction

    def _fallback_prediction(self, player_id: int) -> float:
        """
        Simple form-based prediction when ML models unavailable.

        Uses: (form * 1.5 + points_per_game * 0.5) / 2.0
        """
        player = self._db.execute_query("""
            SELECT form, points_per_game
            FROM players
            WHERE id = ?
        """, (player_id,))

        if not player:
            return 2.0  # Safe default

        p = player[0]
        form = float(p['form'] or 0)
        ppg = float(p['points_per_game'] or 0)

        return (form * 1.5 + ppg * 0.5) / 2.0

    def _apply_news_adjustments(
        self,
        predictions: Dict[int, float],
        gameweek: int
    ) -> Dict[int, float]:
        """Apply news/injury adjustments to predictions."""
        # Lazy load news adjuster
        if self._news_adjuster is None:
            try:
                from ml.prediction.news_adjustment import NewsAwarePredictionAdjuster
                self._news_adjuster = NewsAwarePredictionAdjuster(self._db)
            except Exception as e:
                logger.warning(f"News adjuster not available: {e}")
                return predictions

        try:
            return self._news_adjuster.adjust_predictions(predictions, gameweek)
        except Exception as e:
            logger.warning(f"News adjustment failed: {e}")
            return predictions

    def _load_learning_adjustments(self) -> Dict:
        """Load active learning adjustments from PerformanceTracker."""
        if self._learning_adjustments is not None:
            return self._learning_adjustments

        try:
            from learning.performance_tracker import PerformanceTracker
            tracker = PerformanceTracker(self._db)
            self._learning_adjustments = tracker.get_active_adjustments()
            if self._learning_adjustments.get('position_corrections'):
                logger.info(f"Loaded learning adjustments: {len(self._learning_adjustments['position_corrections'])} position corrections")
            return self._learning_adjustments
        except Exception as e:
            logger.debug(f"No learning adjustments available: {e}")
            self._learning_adjustments = {'position_corrections': {}, 'price_bracket_corrections': {}}
            return self._learning_adjustments

    def _apply_learning_adjustments_to_prediction(
        self,
        player_id: int,
        raw_prediction: float
    ) -> float:
        """
        Apply learned bias corrections to a single prediction.

        Corrections are based on:
        - Position-specific biases (DEF, MID, FWD, GK)
        - Price bracket biases (Premium, Mid-price, Budget)
        """
        if not self.apply_learning_adjustments:
            return raw_prediction

        adjustments = self._load_learning_adjustments()

        if not adjustments.get('position_corrections') and not adjustments.get('price_bracket_corrections'):
            return raw_prediction

        # Get player info for corrections
        player = self._db.execute_query(
            "SELECT element_type, now_cost FROM players WHERE id = ?",
            (player_id,)
        )

        if not player:
            return raw_prediction

        position = player[0]['element_type']
        price = player[0]['now_cost']

        adjustment = 0.0

        # Apply position correction
        pos_names = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        pos_name = pos_names.get(position)
        if pos_name and pos_name in adjustments.get('position_corrections', {}):
            adjustment += adjustments['position_corrections'][pos_name]

        # Apply price bracket correction
        if price >= 100:
            bracket = 'premium'
        elif price >= 60:
            bracket = 'mid_price'
        else:
            bracket = 'budget'

        if bracket in adjustments.get('price_bracket_corrections', {}):
            adjustment += adjustments['price_bracket_corrections'][bracket]

        # Apply adjustment (don't go below 0)
        adjusted = max(0.0, raw_prediction + adjustment)

        if adjustment != 0:
            logger.debug(f"Player {player_id}: {raw_prediction:.2f} -> {adjusted:.2f} (learning adjustment: {adjustment:+.2f})")

        return adjusted

    def _get_player_for_price_prediction(self, player_id: int) -> Optional[Dict]:
        """Get player data formatted for price prediction."""
        player = self._db.execute_query("""
            SELECT
                id, element_type, now_cost, selected_by_percent,
                form, points_per_game, transfers_in_event, transfers_out_event,
                cost_change_event, cost_change_start
            FROM players
            WHERE id = ?
        """, (player_id,))

        if not player:
            return None

        p = player[0]
        return {
            'element_type': p['element_type'],
            'now_cost': p['now_cost'],
            'selected_by_percent': float(p['selected_by_percent'] or 0),
            'form': float(p['form'] or 0),
            'points_per_game': float(p['points_per_game'] or 0),
            'transfers_in_event': p['transfers_in_event'] or 0,
            'transfers_out_event': p['transfers_out_event'] or 0,
            'cost_change_event': p['cost_change_event'] or 0,
            'cost_change_start': p['cost_change_start'] or 0
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_ml_service() -> MLPredictionService:
    """
    Factory function to get a configured MLPredictionService instance.

    Returns:
        Initialized MLPredictionService with models loaded.

    Example:
        from services.ml_prediction_service import get_ml_service
        service = get_ml_service()
        predictions = service.predict_all_players(15)
    """
    return MLPredictionService()


def quick_predict(player_ids: List[int], gameweek: int) -> Dict[int, float]:
    """
    Quick one-liner for predictions.

    Args:
        player_ids: List of player IDs
        gameweek: Target gameweek

    Returns:
        Dict of player_id -> expected_points

    Example:
        from services.ml_prediction_service import quick_predict
        xp = quick_predict([123, 456], 15)
    """
    service = MLPredictionService()
    return service.predict_player_points(player_ids, gameweek)
