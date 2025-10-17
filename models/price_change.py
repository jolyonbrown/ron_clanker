"""
Price Change Prediction Model

Predicts player price rises/falls 6-12 hours ahead using lightweight ML.
Optimized for Raspberry Pi 3 (low memory, CPU-only).

Model Strategy:
- Logistic Regression (primary) - fast, low memory
- Gradient Boosting (optional) - better accuracy if RAM permits
- Feature set: ~10-15 features max
- Binary classification: rise vs no-rise (simplest)
- Or 3-class: rise, hold, fall

Performance Targets:
- Accuracy: 70%+ on test set
- Inference: <100ms per player
- Memory: <50MB for model
- Training: <5 minutes on full dataset
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path
import pickle
import logging

# Scikit-learn imports (lightweight, RPi3-friendly)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score

logger = logging.getLogger('ron_clanker.price_predictor')


class PriceChangePredictor:
    """
    Lightweight price change prediction model optimized for RPi3.

    Uses logistic regression by default for speed and low memory usage.
    Can optionally use gradient boosting if more accuracy is needed.
    """

    MODEL_VERSION = "1.0_logistic_rpi3"

    # Feature engineering constants
    NET_TRANSFER_THRESHOLD = 50000  # Transfers needed for high confidence
    SELECTED_BY_THRESHOLD = 5.0  # % ownership threshold
    FORM_WINDOW = 5  # Last 5 gameweeks

    def __init__(self, model_type: str = "logistic"):
        """
        Initialize predictor.

        Args:
            model_type: "logistic" (default, fastest) or "gbm" (slower, better accuracy)
        """
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.is_trained = False

        # Model selection
        if model_type == "logistic":
            # Fast, low memory, good for RPi3
            self.model = LogisticRegression(
                max_iter=500,
                random_state=42,
                class_weight='balanced',  # Handle imbalanced data
                n_jobs=1  # Single core (RPi3 has 4 cores but leave headroom)
            )
        elif model_type == "gbm":
            # Better accuracy but slower
            from sklearn.ensemble import GradientBoostingClassifier
            self.model = GradientBoostingClassifier(
                n_estimators=50,  # Keep low for RPi3
                max_depth=3,
                learning_rate=0.1,
                random_state=42
            )
        else:
            raise ValueError(f"Unknown model_type: {model_type}")

    def extract_features(self, player_data: Dict) -> np.ndarray:
        """
        Extract features from player data for prediction.

        Features (10-15 total, optimized for RPi3 memory):
        1. Net transfers (normalized)
        2. Net transfer rate (recent change)
        3. Selected by percentage
        4. Form (last 5 GWs)
        5. Points per game
        6. Price (normalized)
        7. Cost change this season
        8. Position (one-hot: GK, DEF, MID, FWD)
        9. Price change history (how many times changed)
        10. Transfer momentum (acceleration)

        Args:
            player_data: Dictionary with player stats

        Returns:
            Feature vector as numpy array
        """
        features = []

        # Transfer metrics
        net_transfers = player_data.get('net_transfers', 0)
        transfers_in = player_data.get('transfers_in', 0)
        transfers_out = player_data.get('transfers_out', 0)

        # Normalize net transfers (key feature)
        features.append(net_transfers / 100000.0)  # Scale to reasonable range

        # Transfer rate (how fast is it changing?)
        transfers_in_event = player_data.get('transfers_in_event', 0)
        transfers_out_event = player_data.get('transfers_out_event', 0)
        net_transfer_rate = (transfers_in_event - transfers_out_event) / 10000.0
        features.append(net_transfer_rate)

        # Ownership
        selected_by = player_data.get('selected_by_percent', 0.0)
        features.append(selected_by / 10.0)  # Normalize

        # Performance metrics
        form = float(player_data.get('form', 0.0))
        features.append(form)

        points_per_game = float(player_data.get('points_per_game', 0.0))
        features.append(points_per_game)

        # Price metrics
        now_cost = player_data.get('now_cost', 40) / 10.0  # Convert to £m
        features.append(now_cost)

        cost_change_event = player_data.get('cost_change_event', 0) / 10.0
        features.append(cost_change_event)

        cost_change_start = player_data.get('cost_change_start', 0) / 10.0
        features.append(cost_change_start)

        # Position (one-hot encoding)
        position = player_data.get('element_type', 3)  # 1=GK, 2=DEF, 3=MID, 4=FWD
        for pos in [1, 2, 3, 4]:
            features.append(1.0 if position == pos else 0.0)

        # Total features: 12 (8 continuous + 4 one-hot position)
        return np.array(features).reshape(1, -1)

    def prepare_training_data(
        self,
        snapshots: List[Dict],
        price_changes: List[Dict]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare training data from historical snapshots and price changes.

        Memory-efficient for RPi3: processes data in batches if needed.

        Args:
            snapshots: List of player transfer snapshots
            price_changes: List of historical price changes

        Returns:
            X (features), y (labels)
        """
        X_list = []
        y_list = []

        # Create lookup of price changes by player and date
        price_change_map = {}
        for change in price_changes:
            key = (change['player_id'], change['detected_at'][:10])  # Date only
            change_direction = 1 if change['change_amount'] > 0 else -1 if change['change_amount'] < 0 else 0
            price_change_map[key] = change_direction

        logger.info(f"Processing {len(snapshots)} snapshots for training")

        # Process each snapshot
        for snapshot in snapshots:
            player_id = snapshot['player_id']
            snapshot_date = snapshot['snapshot_date']

            # Look ahead 1 day to see if price changed
            next_day = (pd.to_datetime(snapshot_date) + timedelta(days=1)).strftime('%Y-%m-%d')

            # Check if price changed in next 24h
            changed = False
            change_direction = 0

            for days_ahead in range(1, 3):  # Check next 1-2 days
                check_date = (pd.to_datetime(snapshot_date) + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
                if (player_id, check_date) in price_change_map:
                    change_direction = price_change_map[(player_id, check_date)]
                    changed = True
                    break

            # Extract features
            features = self.extract_features(snapshot)

            # Label: 0=no change, 1=rise, 2=fall
            if change_direction > 0:
                label = 1  # Rise
            elif change_direction < 0:
                label = 2  # Fall
            else:
                label = 0  # No change

            X_list.append(features.flatten())
            y_list.append(label)

        X = np.array(X_list)
        y = np.array(y_list)

        logger.info(f"Training data shape: X={X.shape}, y={y.shape}")
        logger.info(f"Label distribution: {np.bincount(y)}")

        return X, y

    def train(
        self,
        snapshots: List[Dict],
        price_changes: List[Dict],
        test_size: float = 0.2
    ) -> Dict[str, float]:
        """
        Train the model on historical data.

        Optimized for RPi3: uses efficient numpy operations.

        Args:
            snapshots: Historical player snapshots
            price_changes: Historical price changes
            test_size: Fraction of data for testing

        Returns:
            Dictionary of performance metrics
        """
        logger.info(f"Training {self.model_type} model on {len(snapshots)} snapshots")

        # Prepare data
        X, y = self.prepare_training_data(snapshots, price_changes)

        if len(X) == 0:
            raise ValueError("No training data available")

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        logger.info(f"Train size: {len(X_train)}, Test size: {len(X_test)}")

        # Scale features (important for logistic regression)
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train model
        logger.info("Training model...")
        start_time = datetime.now()

        self.model.fit(X_train_scaled, y_train)

        train_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Training completed in {train_duration:.2f} seconds")

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)

        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average='weighted')

        logger.info(f"Accuracy: {accuracy:.3f}")
        logger.info(f"F1 Score: {f1:.3f}")

        # Detailed report
        report = classification_report(
            y_test, y_pred,
            target_names=['No Change', 'Rise', 'Fall'],
            output_dict=True
        )

        self.is_trained = True

        return {
            'accuracy': accuracy,
            'f1_score': f1,
            'precision_rise': report['Rise']['precision'],
            'recall_rise': report['Rise']['recall'],
            'precision_fall': report['Fall']['precision'],
            'recall_fall': report['Fall']['recall'],
            'train_duration': train_duration,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }

    def predict(self, player_data: Dict) -> Tuple[int, float]:
        """
        Predict price change for a single player.

        Fast inference for RPi3 (<100ms per prediction).

        Args:
            player_data: Player stats dictionary

        Returns:
            (predicted_change, confidence)
            predicted_change: -1 (fall), 0 (no change), 1 (rise)
            confidence: 0.0 to 1.0
        """
        if not self.is_trained:
            raise ValueError("Model not trained yet")

        # Extract features
        features = self.extract_features(player_data)

        # Scale
        features_scaled = self.scaler.transform(features)

        # Predict
        prediction = self.model.predict(features_scaled)[0]
        probabilities = self.model.predict_proba(features_scaled)[0]

        # Convert to -1, 0, 1 format
        if prediction == 1:  # Rise
            change = 1
        elif prediction == 2:  # Fall
            change = -1
        else:  # No change
            change = 0

        # Confidence is the probability of the predicted class
        confidence = probabilities[prediction]

        return change, confidence

    def save(self, filepath: str):
        """Save model to disk."""
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'model_version': self.MODEL_VERSION,
            'is_trained': self.is_trained
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"Model saved to {filepath}")

    @classmethod
    def load(cls, filepath: str) -> 'PriceChangePredictor':
        """Load model from disk."""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        predictor = cls(model_type=model_data['model_type'])
        predictor.model = model_data['model']
        predictor.scaler = model_data['scaler']
        predictor.is_trained = model_data['is_trained']

        logger.info(f"Model loaded from {filepath}")

        return predictor
