"""
Captain Optimization Model

A specialized model for captain selection that goes beyond just highest xP.

Key features:
- Considers ceiling potential (variance in scoring)
- Accounts for ownership for differential advantage
- Binary classification: captain vs non-captain
- Uses historical captain performance data

Usage:
    from ml.captain_optimizer import CaptainOptimizer

    optimizer = CaptainOptimizer()

    # Train on historical captain picks
    optimizer.train()

    # Get captain recommendation for a squad
    recommendation = optimizer.recommend_captain(
        player_ids=[123, 456, 789],
        gameweek=15
    )
    # Returns: {'captain_id': 123, 'vice_captain_id': 456, 'confidence': 0.85}

    # Get captain scores for all players
    scores = optimizer.score_captain_candidates(player_ids, gameweek)
    # Returns: {123: 0.92, 456: 0.78, 789: 0.65}
"""

import sqlite3
import logging
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime
import joblib

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score

logger = logging.getLogger('ron_clanker.captain')


class CaptainOptimizer:
    """
    Optimizes captain selection using ML classification.

    Unlike xP prediction which estimates average points, this model
    identifies players with high "captain ceiling" - the combination
    of high expected points AND high variance (boom potential).
    """

    MODEL_VERSION = "1.0"

    # Captain classification thresholds
    CAPTAIN_PERCENTILE = 90  # Top 10% of scores are "good captain picks"

    def __init__(
        self,
        db_path: str = 'data/ron_clanker.db',
        model_dir: str = 'models/captain'
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
        gameweek: int,
        conn: sqlite3.Connection = None
    ) -> Optional[np.ndarray]:
        """
        Extract captain-relevant features for a player.

        Features:
        1. Expected points (base prediction)
        2. Form variance (ceiling potential)
        3. Ownership (differential value)
        4. Home/Away
        5. Fixture difficulty (from Elo if available)
        6. Recent captain performance (historical)
        7. Position (attackers generally better captains)
        8. Minutes reliability
        9. Ceiling metric (max points in last 5)
        10. Goals per 90 (explosive potential)
        """
        close_conn = False
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            close_conn = True

        cursor = conn.cursor()

        try:
            # Get player data
            cursor.execute("""
                SELECT
                    p.id, p.element_type, p.team_id, p.now_cost,
                    p.selected_by_percent, p.form, p.points_per_game,
                    p.total_points, p.minutes, p.goals_scored, p.assists
                FROM players p
                WHERE p.id = ?
            """, (player_id,))

            player = cursor.fetchone()
            if not player:
                return None

            # Get recent gameweek history for variance calculation
            cursor.execute("""
                SELECT total_points, minutes
                FROM player_gameweek_history
                WHERE player_id = ?
                ORDER BY gameweek DESC
                LIMIT 5
            """, (player_id,))

            history = cursor.fetchall()

            # Get fixture info
            cursor.execute("""
                SELECT
                    f.team_h, f.team_a, f.team_h_difficulty, f.team_a_difficulty
                FROM fixtures f
                WHERE f.event = ?
                AND (f.team_h = ? OR f.team_a = ?)
            """, (gameweek, player['team_id'], player['team_id']))

            fixture = cursor.fetchone()

            # Build features
            features = []

            # 1. Base form metrics
            form = float(player['form'] or 0)
            ppg = float(player['points_per_game'] or 0)
            features.append(form)
            features.append(ppg)

            # 2. Form variance (ceiling potential)
            if history:
                points_history = [h['total_points'] for h in history]
                form_variance = np.std(points_history) if len(points_history) > 1 else 0
                form_max = max(points_history)
                form_mean = np.mean(points_history)
            else:
                form_variance = 0
                form_max = 0
                form_mean = 0

            features.append(form_variance)
            features.append(form_max)

            # 3. Ownership (lower = more differential)
            ownership = float(player['selected_by_percent'] or 0)
            features.append(ownership)
            # Differential bonus (inverse of ownership)
            features.append(100.0 - ownership)

            # 4. Home/Away and fixture difficulty
            if fixture:
                is_home = fixture['team_h'] == player['team_id']
                fdr = fixture['team_h_difficulty'] if not is_home else fixture['team_a_difficulty']
            else:
                is_home = True  # Default
                fdr = 3  # Default medium difficulty

            features.append(1.0 if is_home else 0.0)
            features.append(float(fdr))

            # 5. Position encoding (attackers score higher)
            position = player['element_type']
            # Forward=4 gets highest weight, GK=1 lowest
            position_weight = position / 4.0
            features.append(position_weight)

            # 6. Minutes reliability
            total_minutes = player['minutes'] or 0
            games_played = len([h for h in history if h['minutes'] > 0]) if history else 0
            minutes_per_game = total_minutes / max(1, games_played * 90)
            features.append(min(1.0, minutes_per_game))

            # 7. Goal threat (goals per 90)
            goals = player['goals_scored'] or 0
            minutes = player['minutes'] or 1
            goals_per_90 = (goals * 90) / max(1, minutes)
            features.append(goals_per_90)

            # 8. Price tier (premium players often captain picks)
            price_tier = (player['now_cost'] or 50) / 150.0  # Normalize to 0-1
            features.append(price_tier)

            # 9. Ceiling metric: max - mean (upside potential)
            ceiling_metric = form_max - form_mean
            features.append(ceiling_metric)

            # 10. Assists per 90
            assists = player['assists'] or 0
            assists_per_90 = (assists * 90) / max(1, minutes)
            features.append(assists_per_90)

            self.feature_names = [
                'form', 'ppg', 'form_variance', 'form_max', 'ownership',
                'differential_bonus', 'is_home', 'fdr', 'position_weight',
                'minutes_reliability', 'goals_per_90', 'price_tier',
                'ceiling_metric', 'assists_per_90'
            ]

            return np.array(features).reshape(1, -1)

        finally:
            if close_conn:
                conn.close()

    def prepare_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare training data from historical gameweek results.

        Labels: 1 if player was in top 10% of scorers that GW, 0 otherwise.
        This creates a binary classification for "good captain pick".
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        X_list = []
        y_list = []

        try:
            # Get gameweeks with data
            cursor.execute("""
                SELECT DISTINCT gameweek
                FROM player_gameweek_history
                WHERE total_points IS NOT NULL
                ORDER BY gameweek
            """)
            gameweeks = [r['gameweek'] for r in cursor.fetchall()]

            logger.info(f"Processing {len(gameweeks)} gameweeks for captain training")

            for gw in gameweeks:
                # Get all player scores for this GW
                cursor.execute("""
                    SELECT player_id, total_points
                    FROM player_gameweek_history
                    WHERE gameweek = ? AND minutes > 0
                    ORDER BY total_points DESC
                """, (gw,))

                gw_results = cursor.fetchall()
                if len(gw_results) < 10:
                    continue

                # Determine threshold for "good captain" (top 10%)
                all_points = [r['total_points'] for r in gw_results]
                captain_threshold = np.percentile(all_points, self.CAPTAIN_PERCENTILE)

                # Extract features for each player
                for result in gw_results:
                    features = self.extract_features(result['player_id'], gw, conn)
                    if features is not None:
                        X_list.append(features.flatten())
                        # Label: 1 if good captain pick, 0 otherwise
                        label = 1 if result['total_points'] >= captain_threshold else 0
                        y_list.append(label)

            X = np.array(X_list)
            y = np.array(y_list)

            logger.info(f"Training data: {X.shape[0]} samples, {sum(y)} positive examples")

            return X, y

        finally:
            conn.close()

    def train(self, test_size: float = 0.2) -> Dict[str, float]:
        """
        Train the captain optimizer model.

        Uses a ranking approach - trains regression to predict points,
        then scores captain picks based on predicted ceiling potential.

        Returns:
            Dictionary of evaluation metrics
        """
        logger.info("Preparing training data...")
        X, y_class = self.prepare_training_data()

        if len(X) == 0:
            raise ValueError("No training data available")

        # Get actual points for regression target
        y_points = self._get_points_for_training()

        if y_points is None or len(y_points) != len(X):
            # Fall back to using class labels with a lower threshold
            logger.info("Using classification approach with lower threshold")
            return self._train_classifier(X, y_class, test_size)

        # Train regression model for points prediction
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_points, test_size=test_size, random_state=42
        )

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Use GradientBoostingRegressor for points prediction
        from sklearn.ensemble import GradientBoostingRegressor
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42
        )
        self.model.fit(X_train_scaled, y_train)
        self.model_type = 'regressor'

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        # Also check ranking quality (does top prediction match actual top?)
        captain_accuracy = self._evaluate_captain_ranking(X_test_scaled, y_test)

        self.is_trained = True

        metrics = {
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'captain_accuracy': captain_accuracy,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }

        logger.info(f"Captain model trained: RMSE={rmse:.3f}, MAE={mae:.3f}, R2={r2:.3f}")
        logger.info(f"Captain ranking accuracy: {captain_accuracy:.3f}")

        return metrics

    def _train_classifier(self, X, y, test_size: float) -> Dict[str, float]:
        """Fallback to classifier approach with lower threshold."""
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        self.model.fit(X_train_scaled, y_train)
        self.model_type = 'classifier'

        # Use lower threshold for predictions
        y_prob = self.model.predict_proba(X_test_scaled)[:, 1]
        threshold = 0.1
        y_pred = (y_prob >= threshold).astype(int)

        precision = precision_score(y_test, y_pred)
        recall = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)

        self.is_trained = True

        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'threshold_used': threshold,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }

    def _get_points_for_training(self) -> Optional[np.ndarray]:
        """Get actual points corresponding to training features."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        points_list = []

        try:
            cursor.execute("""
                SELECT DISTINCT gameweek
                FROM player_gameweek_history
                WHERE total_points IS NOT NULL
                ORDER BY gameweek
            """)
            gameweeks = [r['gameweek'] for r in cursor.fetchall()]

            for gw in gameweeks:
                cursor.execute("""
                    SELECT player_id, total_points
                    FROM player_gameweek_history
                    WHERE gameweek = ? AND minutes > 0
                    ORDER BY player_id
                """, (gw,))

                for result in cursor.fetchall():
                    points_list.append(result['total_points'])

            return np.array(points_list) if points_list else None

        finally:
            conn.close()

    def _evaluate_captain_ranking(self, X_test: np.ndarray, y_test: np.ndarray) -> float:
        """Evaluate how often our top pick matches actual top scorer."""
        # Group test samples into hypothetical gameweeks (10 players each)
        n_samples = len(X_test)
        n_groups = n_samples // 10

        correct = 0
        total = 0

        for i in range(n_groups):
            start = i * 10
            end = start + 10

            group_X = X_test[start:end]
            group_y = y_test[start:end]

            # Our prediction
            pred_scores = self.model.predict(group_X)
            our_pick = np.argmax(pred_scores)

            # Actual best
            actual_best = np.argmax(group_y)

            if our_pick == actual_best:
                correct += 1
            total += 1

        return correct / total if total > 0 else 0

    def score_captain_candidates(
        self,
        player_ids: List[int],
        gameweek: int
    ) -> Dict[int, float]:
        """
        Score players as captain candidates.

        Args:
            player_ids: List of player IDs to evaluate
            gameweek: Target gameweek

        Returns:
            Dict mapping player_id to captain score (normalized 0-1)
        """
        if not self.is_trained:
            raise ValueError("Model not trained yet")

        scores = {}
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            raw_scores = []
            for player_id in player_ids:
                features = self.extract_features(player_id, gameweek, conn)
                if features is not None:
                    features_scaled = self.scaler.transform(features)

                    if getattr(self, 'model_type', 'classifier') == 'regressor':
                        # Regression model: predict points
                        score = self.model.predict(features_scaled)[0]
                    else:
                        # Classification model: probability
                        score = self.model.predict_proba(features_scaled)[0, 1]

                    scores[player_id] = float(score)
                    raw_scores.append(float(score))
                else:
                    scores[player_id] = 0.0

            # Normalize scores to 0-1 range for consistency
            if raw_scores and getattr(self, 'model_type', 'classifier') == 'regressor':
                min_score = min(raw_scores)
                max_score = max(raw_scores)
                score_range = max_score - min_score if max_score > min_score else 1

                for player_id in scores:
                    if scores[player_id] > 0:
                        scores[player_id] = (scores[player_id] - min_score) / score_range

            return scores

        finally:
            conn.close()

    def recommend_captain(
        self,
        player_ids: List[int],
        gameweek: int,
        ownership_penalty: float = 0.0
    ) -> Dict:
        """
        Recommend captain and vice captain.

        Args:
            player_ids: Squad player IDs
            gameweek: Target gameweek
            ownership_penalty: Optional penalty for highly owned players (0-1)
                              0 = no penalty, 1 = full differential weighting

        Returns:
            Dict with captain_id, vice_captain_id, confidence, and full scores
        """
        scores = self.score_captain_candidates(player_ids, gameweek)

        # Optionally apply ownership penalty
        if ownership_penalty > 0:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            for pid in scores:
                cursor.execute(
                    "SELECT selected_by_percent FROM players WHERE id = ?",
                    (pid,)
                )
                row = cursor.fetchone()
                if row:
                    ownership = row[0] or 0
                    # Reduce score for highly owned players
                    penalty = (ownership / 100) * ownership_penalty
                    scores[pid] = scores[pid] * (1 - penalty)
            conn.close()

        # Sort by score
        sorted_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if len(sorted_players) < 2:
            return {'captain_id': None, 'vice_captain_id': None, 'confidence': 0}

        captain_id, captain_score = sorted_players[0]
        vice_id, vice_score = sorted_players[1]

        return {
            'captain_id': captain_id,
            'vice_captain_id': vice_id,
            'confidence': captain_score,
            'margin': captain_score - vice_score,
            'all_scores': scores
        }

    def save(self, filepath: str = None):
        """Save model to disk."""
        if filepath is None:
            filepath = self.model_dir / f'captain_optimizer_{self.MODEL_VERSION}.pkl'

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'model_version': self.MODEL_VERSION,
            'model_type': getattr(self, 'model_type', 'classifier'),
            'is_trained': self.is_trained
        }

        joblib.dump(model_data, filepath)
        logger.info(f"Captain model saved to {filepath}")

    def load(self, filepath: str = None):
        """Load model from disk."""
        if filepath is None:
            filepath = self.model_dir / f'captain_optimizer_{self.MODEL_VERSION}.pkl'

        if not Path(filepath).exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")

        model_data = joblib.load(filepath)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.feature_names = model_data.get('feature_names', [])
        self.model_type = model_data.get('model_type', 'classifier')
        self.is_trained = model_data['is_trained']

        logger.info(f"Captain model loaded from {filepath}")

    def get_feature_importance(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Get feature importance from the model."""
        if not self.is_trained or not self.feature_names:
            return []

        importances = self.model.feature_importances_
        indices = np.argsort(importances)[::-1][:top_n]

        return [(self.feature_names[i], importances[i]) for i in indices]


def get_captain_optimizer(db_path: str = 'data/ron_clanker.db') -> CaptainOptimizer:
    """Factory function to get a CaptainOptimizer instance."""
    return CaptainOptimizer(db_path)
