"""
Minutes Prediction Model

Predicts expected playing minutes for players in upcoming gameweeks.
Essential for optimizing bench order and understanding auto-sub value.

Key factors:
- Recent minutes history (rolling average)
- Minutes consistency (variance)
- Injury/doubt status
- Manager rotation patterns
- Position (GKs rarely rotated, FWDs more often)
- Fixture congestion
"""

import sqlite3
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict
import joblib

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

logger = logging.getLogger('ron_clanker.minutes')


class MinutesPredictor:
    """
    Predicts expected minutes for players in upcoming gameweeks.

    Uses historical minutes data with features:
    - Rolling minutes average (last 3, 5, 10 games)
    - Minutes consistency (std dev)
    - Recent trend (improving/declining)
    - Injury status
    - Position
    - Team context (fixture congestion)
    """

    MODEL_VERSION = "1.0"

    def __init__(
        self,
        db_path: str = 'data/ron_clanker.db',
        model_dir: str = 'models/minutes'
    ):
        self.db_path = db_path
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def extract_features(
        self,
        player_id: int,
        target_gameweek: int,
        conn: sqlite3.Connection = None
    ) -> Optional[np.ndarray]:
        """
        Extract minutes-relevant features for a player.

        Features:
        1. Rolling minutes avg (3 games)
        2. Rolling minutes avg (5 games)
        3. Rolling minutes avg (10 games)
        4. Minutes std (5 games) - consistency
        5. Minutes trend (recent 3 vs prev 3)
        6. Max minutes in last 5 games
        7. Games with 0 minutes (last 5)
        8. Games with 60+ minutes (last 5)
        9. Chance of playing (FPL)
        10. Position (1-4)
        11. Team strength (affects rotation likelihood)
        12. Is home next game
        13. Fixture difficulty
        14. Days since last game (if available)
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            close_conn = True

        cursor = conn.cursor()

        try:
            # Get player info
            cursor.execute("""
                SELECT
                    p.id, p.element_type, p.team_id,
                    p.chance_of_playing_next_round, p.status
                FROM players p
                WHERE p.id = ?
            """, (player_id,))

            player = cursor.fetchone()
            if not player:
                return None

            # Get minutes history (before target gameweek)
            cursor.execute("""
                SELECT minutes, gameweek
                FROM player_gameweek_history
                WHERE player_id = ? AND gameweek < ?
                ORDER BY gameweek DESC
                LIMIT 10
            """, (player_id, target_gameweek))

            history = cursor.fetchall()

            if len(history) < 3:
                return None  # Need at least 3 games of history

            minutes_list = [h['minutes'] for h in history]

            features = []

            # 1-3. Rolling averages
            avg_3 = np.mean(minutes_list[:3]) if len(minutes_list) >= 3 else np.mean(minutes_list)
            avg_5 = np.mean(minutes_list[:5]) if len(minutes_list) >= 5 else np.mean(minutes_list)
            avg_10 = np.mean(minutes_list[:10]) if len(minutes_list) >= 10 else np.mean(minutes_list)
            features.extend([avg_3 / 90, avg_5 / 90, avg_10 / 90])  # Normalize to 0-1

            # 4. Consistency (lower std = more consistent starter)
            std_5 = np.std(minutes_list[:5]) if len(minutes_list) >= 5 else np.std(minutes_list)
            features.append(std_5 / 45)  # Normalize (45 = half game variance)

            # 5. Trend (positive = improving, negative = declining)
            if len(minutes_list) >= 6:
                recent_3 = np.mean(minutes_list[:3])
                prev_3 = np.mean(minutes_list[3:6])
                trend = (recent_3 - prev_3) / 90  # Normalize
            else:
                trend = 0
            features.append(trend)

            # 6. Max minutes (ceiling)
            max_mins = max(minutes_list[:5]) if len(minutes_list) >= 5 else max(minutes_list)
            features.append(max_mins / 90)

            # 7. Games with 0 minutes (benched/injured count)
            zero_count = sum(1 for m in minutes_list[:5] if m == 0)
            features.append(zero_count / 5)

            # 8. Games with 60+ minutes (regular starter indicator)
            full_count = sum(1 for m in minutes_list[:5] if m >= 60)
            features.append(full_count / 5)

            # 9. Chance of playing (FPL API)
            chance = player['chance_of_playing_next_round']
            if chance is None:
                chance = 100  # Assume available if no news
            features.append(chance / 100)

            # 10. Position (GKs=1 most stable, FWDs=4 most rotated)
            position = player['element_type']
            features.append(position / 4)

            # 11. Get team strength (stronger teams rotate more in cups)
            cursor.execute("""
                SELECT strength FROM teams WHERE id = ?
            """, (player['team_id'],))
            team = cursor.fetchone()
            team_strength = (team['strength'] / 5) if team else 0.5
            features.append(team_strength)

            # 12-13. Next fixture info
            cursor.execute("""
                SELECT team_h, team_a, team_h_difficulty, team_a_difficulty
                FROM fixtures
                WHERE event = ? AND (team_h = ? OR team_a = ?)
            """, (target_gameweek, player['team_id'], player['team_id']))

            fixture = cursor.fetchone()
            if fixture:
                is_home = fixture['team_h'] == player['team_id']
                fdr = fixture['team_a_difficulty'] if is_home else fixture['team_h_difficulty']
            else:
                is_home = True
                fdr = 3
            features.append(1.0 if is_home else 0.0)
            features.append(fdr / 5)

            # 14. Approximate days rest (from previous GW, default to 7)
            days_rest = 7 / 7  # Normalized, could be improved with actual date tracking
            features.append(days_rest)

            self.feature_names = [
                'avg_mins_3', 'avg_mins_5', 'avg_mins_10',
                'mins_std_5', 'mins_trend', 'max_mins_5',
                'zero_mins_count', 'full_game_count',
                'chance_of_playing', 'position',
                'team_strength', 'is_home', 'fdr', 'days_rest'
            ]

            return np.array(features).reshape(1, -1)

        finally:
            if close_conn:
                conn.close()

    def prepare_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare training data from historical gameweek data.

        For each player-gameweek, extract features from BEFORE that gameweek
        and use actual minutes from that gameweek as the target.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        X_list = []
        y_list = []

        try:
            # Get gameweeks with sufficient history (start from GW4)
            cursor.execute("""
                SELECT DISTINCT gameweek
                FROM player_gameweek_history
                WHERE gameweek >= 4
                ORDER BY gameweek
            """)
            gameweeks = [r['gameweek'] for r in cursor.fetchall()]

            logger.info(f"Processing {len(gameweeks)} gameweeks for minutes training")

            for gw in gameweeks:
                # Get all players who played that GW
                cursor.execute("""
                    SELECT player_id, minutes
                    FROM player_gameweek_history
                    WHERE gameweek = ?
                """, (gw,))

                gw_data = cursor.fetchall()

                for record in gw_data:
                    features = self.extract_features(record['player_id'], gw, conn)
                    if features is not None:
                        X_list.append(features.flatten())
                        # Target: normalized minutes (0-1)
                        y_list.append(min(record['minutes'] / 90, 1.0))

            X = np.array(X_list)
            y = np.array(y_list)

            logger.info(f"Training data: {X.shape[0]} samples")

            return X, y

        finally:
            conn.close()

    def train(self, test_size: float = 0.2) -> Dict[str, float]:
        """
        Train the minutes prediction model.

        Returns:
            Dictionary of evaluation metrics
        """
        logger.info("Preparing training data for MinutesPredictor...")
        X, y = self.prepare_training_data()

        if len(X) == 0:
            raise ValueError("No training data available")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42
        )
        self.model.fit(X_train_scaled, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)

        # Convert back to minutes for interpretable metrics
        y_test_mins = y_test * 90
        y_pred_mins = y_pred * 90

        rmse = np.sqrt(mean_squared_error(y_test_mins, y_pred_mins))
        mae = mean_absolute_error(y_test_mins, y_pred_mins)
        r2 = r2_score(y_test, y_pred)

        self.is_trained = True

        metrics = {
            'rmse_minutes': rmse,
            'mae_minutes': mae,
            'r2': r2,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }

        logger.info(f"Minutes model trained: RMSE={rmse:.1f}min, MAE={mae:.1f}min, R2={r2:.3f}")

        return metrics

    def predict_minutes(
        self,
        player_id: int,
        gameweek: int
    ) -> Dict[str, float]:
        """
        Predict expected minutes for a player in a gameweek.

        Returns:
            Dict with 'expected_minutes', 'confidence', 'start_probability'
        """
        if not self.is_trained:
            raise ValueError("Model not trained yet")

        features = self.extract_features(player_id, gameweek)
        if features is None:
            # Return default for new/unknown players
            return {
                'expected_minutes': 45.0,
                'confidence': 0.3,
                'start_probability': 0.5
            }

        features_scaled = self.scaler.transform(features)
        pred_normalized = self.model.predict(features_scaled)[0]

        # Convert to minutes
        expected_mins = pred_normalized * 90

        # Estimate start probability (>= 60 mins)
        start_prob = min(1.0, pred_normalized / 0.67)  # 60/90 = 0.67

        # Confidence based on feature quality
        confidence = min(1.0, features[0][7] + 0.3)  # full_game_count + base

        return {
            'expected_minutes': max(0, min(90, expected_mins)),
            'confidence': confidence,
            'start_probability': start_prob
        }

    def predict_batch(
        self,
        player_ids: List[int],
        gameweek: int
    ) -> Dict[int, Dict[str, float]]:
        """
        Predict minutes for multiple players.
        """
        results = {}
        for pid in player_ids:
            results[pid] = self.predict_minutes(pid, gameweek)
        return results

    def save(self, filepath: str = None):
        """Save model to disk."""
        if filepath is None:
            filepath = self.model_dir / f'minutes_predictor_{self.MODEL_VERSION}.pkl'

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'model_version': self.MODEL_VERSION,
            'is_trained': self.is_trained
        }

        joblib.dump(model_data, filepath)
        logger.info(f"Minutes model saved to {filepath}")

    def load(self, filepath: str = None):
        """Load model from disk."""
        if filepath is None:
            filepath = self.model_dir / f'minutes_predictor_{self.MODEL_VERSION}.pkl'

        if not Path(filepath).exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")

        model_data = joblib.load(filepath)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.feature_names = model_data.get('feature_names', [])
        self.is_trained = model_data['is_trained']

        logger.info(f"Minutes model loaded from {filepath}")

    def get_feature_importance(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Get feature importance from the model."""
        if not self.is_trained or not self.feature_names:
            return []

        importances = self.model.feature_importances_
        indices = np.argsort(importances)[::-1][:top_n]

        return [(self.feature_names[i], importances[i]) for i in indices]


def get_minutes_predictor(db_path: str = 'data/ron_clanker.db') -> MinutesPredictor:
    """Factory function to get a MinutesPredictor instance."""
    return MinutesPredictor(db_path)
