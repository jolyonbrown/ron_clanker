#!/usr/bin/env python3
"""
Decision Synthesis Engine - The Brain

Integrates all intelligence sources and ML predictions to generate
unified, context-aware recommendations for team decisions.

This is the critical integration layer that connects:
- ML predictions (expected points)
- League intelligence (competitive position, rivals)
- Global rankings (elite template)
- Fixture analysis (difficulty swings, DGW/BGW)
- Chip strategy (optimal timing)
- Price predictions (transfer urgency)

Output: Structured recommendations for Manager Agent
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from data.database import Database
from utils.gameweek import get_current_gameweek
from intelligence.league_intel import LeagueIntelligenceService
from intelligence.chip_strategy import ChipStrategyAnalyzer
from intelligence.fixture_optimizer import FixtureOptimizer
from ml.prediction.model import PlayerPerformancePredictor
from ml.prediction.features import FeatureEngineer
from models.price_change import PriceChangePredictor

logger = logging.getLogger('ron_clanker.synthesis')


class DecisionSynthesisEngine:
    """
    The brain that connects all intelligence to decisions.

    Pre-deadline workflow:
    1. Run ML predictions → player_predictions table
    2. Gather all intelligence (league, global, fixtures, chips)
    3. Synthesize context-aware recommendations
    4. Output structured recommendations for Manager Agent
    """

    def __init__(self, database: Database = None, config: Dict = None):
        """
        Initialize Decision Synthesis Engine.

        Args:
            database: Database connection
            config: Configuration dict with team_id, league_id, etc.
        """
        self.db = database or Database()
        self.config = config or self._load_config()

        # Intelligence services
        self.league_intel = LeagueIntelligenceService(self.db)
        self.chip_analyzer = ChipStrategyAnalyzer(self.db, self.league_intel)
        self.fixture_optimizer = FixtureOptimizer(self.db)

        # ML systems
        self.feature_engineer = FeatureEngineer(self.db)
        self.performance_predictor = PlayerPerformancePredictor(
            model_dir=Path('models/prediction')
        )
        self.price_predictor = PriceChangePredictor()

        # State
        self.current_gw = None
        self.ml_predictions = {}
        self.intelligence_cache = {}

        logger.info("DecisionSynthesisEngine: Initialized")

    def _load_config(self) -> Dict:
        """Load configuration from file."""
        import json
        config_file = Path('config/ron_config.json')

        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)

        logger.warning("DecisionSynthesis: No config file found")
        return {}

    def run_ml_predictions(self, gameweek: int) -> Dict[int, float]:
        """
        Run ML predictions for all players for target gameweek.

        Args:
            gameweek: Target gameweek

        Returns:
            Dict mapping player_id -> expected_points
        """
        logger.info(f"DecisionSynthesis: Running ML predictions for GW{gameweek}")

        # Load trained models
        try:
            self.performance_predictor.load_models(version='latest')
        except Exception as e:
            logger.warning(f"DecisionSynthesis: Could not load models: {e}")
            logger.warning("DecisionSynthesis: Will use fallback predictions")
            return self._fallback_predictions(gameweek)

        # Get all players
        players = self.db.execute_query("""
            SELECT id, web_name, element_type, team_id, now_cost
            FROM players
            WHERE status != 'u'
            ORDER BY id
        """)

        if not players:
            logger.error("DecisionSynthesis: No players found")
            return {}

        predictions = {}

        for player in players:
            try:
                # Engineer features for this player
                features = self.feature_engineer.engineer_features(
                    player_id=player['id'],
                    gameweek=gameweek
                )

                if features:
                    # Get ML prediction
                    xp = self.performance_predictor.predict(features)
                    predictions[player['id']] = float(xp)
                else:
                    # Fallback to simple form-based prediction
                    predictions[player['id']] = self._simple_prediction(player['id'])

            except Exception as e:
                logger.warning(f"DecisionSynthesis: Prediction failed for {player['web_name']}: {e}")
                predictions[player['id']] = 2.0  # Safe fallback

        logger.info(f"DecisionSynthesis: Generated {len(predictions)} predictions")

        # Store to database
        self._store_predictions(predictions, gameweek)

        return predictions

    def _fallback_predictions(self, gameweek: int) -> Dict[int, float]:
        """
        Fallback predictions using simple form + fixture difficulty.
        Used when ML models aren't available.
        """
        logger.info("DecisionSynthesis: Using fallback predictions")

        players = self.db.execute_query("""
            SELECT p.id, p.element_type, p.form,
                   p.points_per_game, p.ict_index
            FROM players p
            WHERE p.status != 'u'
        """)

        predictions = {}
        for player in players:
            # Simple heuristic: form * 1.5 + points_per_game * 0.5
            form = float(player.get('form', 0) or 0)
            ppg = float(player.get('points_per_game', 0) or 0)

            xp = (form * 1.5 + ppg * 0.5) / 2.0
            predictions[player['id']] = max(0.0, xp)

        return predictions

    def _simple_prediction(self, player_id: int) -> float:
        """Simple form-based prediction for a single player."""
        player = self.db.execute_query("""
            SELECT form, points_per_game FROM players WHERE id = ?
        """, (player_id,))

        if player:
            form = float(player[0].get('form', 0) or 0)
            ppg = float(player[0].get('points_per_game', 0) or 0)
            return (form * 1.5 + ppg * 0.5) / 2.0

        return 2.0

    def _store_predictions(self, predictions: Dict[int, float], gameweek: int):
        """Store ML predictions to database."""
        for player_id, xp in predictions.items():
            try:
                self.db.execute_update("""
                    INSERT OR REPLACE INTO player_predictions
                    (player_id, gameweek, predicted_points, prediction_date, model_version)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'synthesis_v1')
                """, (player_id, gameweek, xp))
            except Exception as e:
                logger.warning(f"DecisionSynthesis: Failed to store prediction for {player_id}: {e}")

        logger.info(f"DecisionSynthesis: Stored {len(predictions)} predictions to database")

    def gather_intelligence(self, gameweek: int) -> Dict:
        """
        Gather all intelligence from various services.

        Returns:
            Dict with all intelligence data
        """
        logger.info(f"DecisionSynthesis: Gathering intelligence for GW{gameweek}")

        intelligence = {
            'gameweek': gameweek,
            'timestamp': datetime.now().isoformat(),
            'league': None,
            'global_template': None,
            'fixtures': None,
            'chips': None
        }

        # League intelligence
        if self.config.get('league_id') and self.config.get('team_id'):
            try:
                intelligence['league'] = self._gather_league_intel(gameweek)
            except Exception as e:
                logger.warning(f"DecisionSynthesis: League intel failed: {e}")

        # Global template (from database if available)
        try:
            intelligence['global_template'] = self._gather_global_template(gameweek)
        except Exception as e:
            logger.warning(f"DecisionSynthesis: Global template failed: {e}")

        # Fixture analysis
        try:
            intelligence['fixtures'] = self._gather_fixture_intel(gameweek)
        except Exception as e:
            logger.warning(f"DecisionSynthesis: Fixture intel failed: {e}")

        # Chip strategy
        if self.config.get('team_id') and self.config.get('league_id'):
            try:
                intelligence['chips'] = self._gather_chip_intel(gameweek)
            except Exception as e:
                logger.warning(f"DecisionSynthesis: Chip intel failed: {e}")

        self.intelligence_cache = intelligence
        logger.info("DecisionSynthesis: Intelligence gathering complete")

        return intelligence

    def _gather_league_intel(self, gameweek: int) -> Dict:
        """Gather league competitive intelligence."""
        league_id = self.config['league_id']
        team_id = self.config['team_id']

        # Get standings
        standings = self.league_intel.db.execute_query("""
            SELECT entry_id, rank, total_points, event_points
            FROM league_standings_history
            WHERE league_id = ? AND gameweek = ?
            ORDER BY rank
        """, (league_id, gameweek))

        if not standings:
            return None

        # Find Ron's position
        ron_standing = next((s for s in standings if s['entry_id'] == team_id), None)
        leader = standings[0]

        if ron_standing:
            gap = ron_standing['total_points'] - leader['total_points']
            position = "leading" if gap >= 0 else "chasing"

            return {
                'rank': ron_standing['rank'],
                'total_points': ron_standing['total_points'],
                'gap_to_leader': gap,
                'position': position,
                'league_size': len(standings)
            }

        # Ron not in standings yet (new team)
        return {
            'rank': None,
            'total_points': 0,
            'gap_to_leader': -leader['total_points'],
            'position': 'chasing',
            'league_size': len(standings)
        }

    def _gather_global_template(self, gameweek: int) -> Dict:
        """
        Gather global elite template info.
        This would ideally come from recent track_global_rankings run.
        For now, we'll use a simplified version.
        """
        # Check if we have recent global rankings data
        # (In production, this would query a global_rankings table)

        # For now, return placeholder that indicates we should cover high ownership
        return {
            'template_threshold': 70.0,  # Consider 70%+ owned as "template"
            'differential_threshold': 30.0,  # <30% owned = differential
            'note': 'Use player ownership % from players table'
        }

    def _gather_fixture_intel(self, gameweek: int) -> Dict:
        """Gather fixture difficulty and swing analysis."""
        # Get next 6 gameweeks of fixtures
        fixture_report = self.fixture_optimizer.analyze_fixture_difficulty_range(
            start_gw=gameweek,
            num_gameweeks=6
        )

        return {
            'next_6_gws': fixture_report,
            'focus_gw': gameweek
        }

    def _gather_chip_intel(self, gameweek: int) -> Dict:
        """Gather chip timing recommendations."""
        team_id = self.config['team_id']
        league_id = self.config['league_id']

        # Get chip recommendations
        recommendations = self.chip_analyzer.recommend_chip_timing(
            ron_entry_id=team_id,
            league_id=league_id,
            current_gw=gameweek,
            horizon=6
        )

        return recommendations

    def synthesize_recommendations(self, gameweek: int) -> Dict:
        """
        Main synthesis method: combines ML + intelligence → recommendations.

        Args:
            gameweek: Target gameweek

        Returns:
            Dict with comprehensive recommendations
        """
        logger.info(f"DecisionSynthesis: Synthesizing recommendations for GW{gameweek}")

        self.current_gw = gameweek

        # Step 1: Run ML predictions
        self.ml_predictions = self.run_ml_predictions(gameweek)

        # Step 2: Gather intelligence
        intelligence = self.gather_intelligence(gameweek)

        # Step 3: Generate recommendations
        recommendations = {
            'gameweek': gameweek,
            'generated_at': datetime.now().isoformat(),
            'strategy': self._determine_strategy(intelligence),
            'top_players': self._rank_players_by_value(gameweek, intelligence),
            'captain_recommendation': self._recommend_captain(gameweek, intelligence),
            'chip_recommendation': intelligence.get('chips', {}),
            'transfer_targets': self._identify_transfer_targets(gameweek, intelligence),
            'risks_to_cover': self._identify_template_risks(gameweek, intelligence)
        }

        logger.info("DecisionSynthesis: Recommendations complete")

        return recommendations

    def _determine_strategy(self, intelligence: Dict) -> Dict:
        """Determine overall strategy based on competitive position."""
        league = intelligence.get('league')

        if not league:
            return {
                'risk_level': 'MODERATE',
                'approach': 'balanced',
                'reasoning': 'No league data - play balanced strategy'
            }

        gap = league.get('gap_to_leader', 0)
        position = league.get('position', 'chasing')

        if position == 'leading':
            return {
                'risk_level': 'LOW',
                'approach': 'defensive',
                'reasoning': f"Leading by {abs(gap)}pts - cover template, avoid risks"
            }

        elif abs(gap) > 200:
            return {
                'risk_level': 'BOLD',
                'approach': 'aggressive_differentials',
                'reasoning': f"Chasing {abs(gap)}pts - need differentials with high upside"
            }

        elif abs(gap) > 50:
            return {
                'risk_level': 'MODERATE-HIGH',
                'approach': 'balanced_differentials',
                'reasoning': f"Chasing {abs(gap)}pts - mix template + differentials"
            }

        else:
            return {
                'risk_level': 'MODERATE',
                'approach': 'balanced',
                'reasoning': f"Close race ({abs(gap)}pts) - balanced approach"
            }

    def _rank_players_by_value(self, gameweek: int, intelligence: Dict, top_n: int = 50) -> List[Dict]:
        """
        Rank all players by value considering ML + context.

        Value = ML expected points + fixture bonus + ownership context
        """
        players = self.db.execute_query("""
            SELECT id, web_name, element_type, team_id, now_cost,
                   selected_by_percent, form
            FROM players
            WHERE status != 'u'
        """)

        ranked = []

        for player in players:
            player_id = player['id']

            # ML prediction
            xp = self.ml_predictions.get(player_id, 2.0)

            # Price (for value calculation)
            price = player['now_cost'] / 10.0

            # Ownership
            ownership = float(player.get('selected_by_percent', 0) or 0)

            # Value score = xP / price (points per million)
            value_score = xp / price if price > 0 else 0

            # Ownership context
            is_template = ownership > 70.0
            is_differential = ownership < 30.0

            ranked.append({
                'player_id': player_id,
                'name': player['web_name'],
                'position': player['element_type'],
                'price': price,
                'xp': round(xp, 2),
                'ownership': ownership,
                'value_score': round(value_score, 3),
                'is_template': is_template,
                'is_differential': is_differential
            })

        # Sort by value score
        ranked.sort(key=lambda x: x['value_score'], reverse=True)

        return ranked[:top_n]

    def _recommend_captain(self, gameweek: int, intelligence: Dict) -> Dict:
        """Recommend captain based on ML + ownership + strategy."""
        strategy = self._determine_strategy(intelligence)

        # Get top predicted players
        top_players = sorted(
            [
                {'id': pid, 'xp': xp}
                for pid, xp in self.ml_predictions.items()
            ],
            key=lambda x: x['xp'],
            reverse=True
        )[:10]

        # Get player details
        recommendations = []
        for p in top_players:
            player = self.db.execute_query("""
                SELECT web_name, selected_by_percent, now_cost
                FROM players WHERE id = ?
            """, (p['id'],))

            if player:
                ownership = float(player[0].get('selected_by_percent', 0) or 0)
                recommendations.append({
                    'player_id': p['id'],
                    'name': player[0]['web_name'],
                    'xp': round(p['xp'], 2),
                    'ownership': ownership,
                    'safety': 'safe' if ownership > 50 else 'differential'
                })

        # Choose based on strategy
        if strategy['risk_level'] in ['LOW', 'MODERATE']:
            # Pick safe captain (high ownership)
            safe_picks = [r for r in recommendations if r['ownership'] > 50]
            primary = safe_picks[0] if safe_picks else recommendations[0]
            differential = [r for r in recommendations if r['ownership'] < 30]

            return {
                'primary': primary,
                'differential_option': differential[0] if differential else None,
                'recommendation': 'primary',
                'reasoning': f"{strategy['risk_level']} strategy - play it safe"
            }

        else:  # BOLD, MODERATE-HIGH
            # Consider differential
            differential = [r for r in recommendations if r['ownership'] < 30]
            safe = [r for r in recommendations if r['ownership'] > 50]

            return {
                'primary': safe[0] if safe else recommendations[0],
                'differential_option': differential[0] if differential else None,
                'recommendation': 'differential' if differential and strategy['risk_level'] == 'BOLD' else 'primary',
                'reasoning': f"{strategy['risk_level']} strategy - {'consider differential' if differential else 'no good differential available'}"
            }

    def _identify_transfer_targets(self, gameweek: int, intelligence: Dict) -> Dict:
        """Identify good transfer targets based on fixtures + ML."""
        # This is a simplified version - full implementation would analyze
        # fixture swings, price changes, form trends, etc.

        return {
            'targets_in': [],  # Would be populated with analysis
            'targets_out': [],
            'note': 'Full transfer analysis requires current team context'
        }

    def _identify_template_risks(self, gameweek: int, intelligence: Dict) -> List[Dict]:
        """Identify high-ownership players we might not have (template gaps)."""
        # Check for high ownership players
        template_players = self.db.execute_query("""
            SELECT id, web_name, selected_by_percent, now_cost
            FROM players
            WHERE CAST(selected_by_percent AS FLOAT) > 70.0
            AND status != 'u'
            ORDER BY CAST(selected_by_percent AS FLOAT) DESC
            LIMIT 10
        """)

        risks = []
        for p in template_players or []:
            xp = self.ml_predictions.get(p['id'], 0)
            risks.append({
                'player_id': p['id'],
                'name': p['web_name'],
                'ownership': float(p['selected_by_percent']),
                'xp': round(xp, 2),
                'price': p['now_cost'] / 10.0,
                'risk_level': 'HIGH' if xp > 6.0 else 'MODERATE'
            })

        return risks
