"""
Ron Clanker Services Layer

This module provides clean, well-documented interfaces to core system
capabilities. Designed to be consumed by any agent architecture.

Services:
    - MLPredictionService: Player performance and price predictions
    - (Future) FixtureService: Fixture analysis and difficulty ratings
    - (Future) IntelligenceService: News and team intelligence

Design Philosophy:
    These services abstract away implementation details (database schemas,
    model architectures, feature engineering) and provide simple interfaces.

    Any agent that needs predictions can simply:
        from services import MLPredictionService
        service = MLPredictionService()
        predictions = service.predict_player_points(player_ids, gameweek)

    The service handles:
    - Model loading and versioning
    - Feature engineering
    - Fallback strategies when models unavailable
    - Performance tracking
"""

from .ml_prediction_service import MLPredictionService

__all__ = ['MLPredictionService']
