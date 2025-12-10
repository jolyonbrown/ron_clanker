#!/usr/bin/env python3
"""
Neural Network Models for FPL Prediction

GPU-accelerated models using PyTorch:
1. MLP - Multi-layer perceptron for non-linear feature interactions
2. FormLSTM - LSTM for player form sequences (captures momentum, patterns)

These models integrate with the existing stacking ensemble.
"""

import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
import joblib

logger = logging.getLogger('ron_clanker.ml.neural')

# Check GPU availability
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
logger.info(f"Neural models using device: {DEVICE}")


class FPLPredictorMLP(nn.Module):
    """
    Multi-layer Perceptron for FPL point prediction.

    Captures non-linear interactions between features that tree-based
    models might miss. Architecture: Input -> 64 -> 32 -> 16 -> 1

    Benefits over tree models:
    - Captures smooth non-linear relationships
    - Better extrapolation for extreme values
    - Can learn complex feature interactions
    """

    def __init__(self, input_dim: int, hidden_dims: List[int] = None, dropout: float = 0.2):
        """
        Args:
            input_dim: Number of input features
            hidden_dims: List of hidden layer sizes (default: [64, 32, 16])
            dropout: Dropout rate for regularization
        """
        super().__init__()

        if hidden_dims is None:
            hidden_dims = [64, 32, 16]

        layers = []
        prev_dim = input_dim

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout)
            ])
            prev_dim = hidden_dim

        # Output layer (single value for regression)
        layers.append(nn.Linear(prev_dim, 1))

        self.network = nn.Sequential(*layers)

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x).squeeze(-1)


class FormLSTM(nn.Module):
    """
    LSTM for modeling player form sequences.

    Input: Sequence of recent gameweek stats (last 5-10 games)
    Output: Predicted points for next gameweek

    Use cases:
    - Detects form momentum (rising/falling trends)
    - Learns bounce-back patterns after injury
    - Captures rhythm patterns (good/bad runs)
    """

    def __init__(
        self,
        sequence_features: int,
        hidden_size: int = 32,
        num_layers: int = 2,
        dropout: float = 0.2,
        bidirectional: bool = True
    ):
        """
        Args:
            sequence_features: Number of features per gameweek in sequence
            hidden_size: LSTM hidden state size
            num_layers: Number of LSTM layers
            dropout: Dropout rate
            bidirectional: Whether to use bidirectional LSTM
        """
        super().__init__()

        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.bidirectional = bidirectional
        self.num_directions = 2 if bidirectional else 1

        self.lstm = nn.LSTM(
            input_size=sequence_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=bidirectional
        )

        # Final hidden state to prediction
        self.embedding_dim = hidden_size * self.num_directions

        # Two-layer head for regression
        self.fc1 = nn.Linear(self.embedding_dim, 32)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(32, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch_size, seq_length, sequence_features)

        Returns:
            Predicted points: (batch_size,)
        """
        # LSTM output
        lstm_out, (h_n, c_n) = self.lstm(x)

        # Use final hidden state from all layers/directions
        # h_n shape: (num_layers * num_directions, batch, hidden_size)
        if self.bidirectional:
            # Concatenate forward and backward final hidden states
            final_hidden = torch.cat([h_n[-2], h_n[-1]], dim=1)
        else:
            final_hidden = h_n[-1]

        # Regression head
        x = self.fc1(final_hidden)
        x = self.relu(x)
        x = self.dropout(x)
        prediction = self.fc2(x).squeeze(-1)

        return prediction


class NeuralPredictor:
    """
    Wrapper for training and inference with neural models.

    Handles:
    - GPU/CPU device management
    - Feature scaling
    - Training with early stopping
    - Batch prediction
    - Model persistence
    """

    def __init__(
        self,
        input_dim: int,
        model_type: str = 'mlp',
        model_dir: Path = None,
        sequence_length: int = 5,
        sequence_features: int = 10
    ):
        """
        Args:
            input_dim: Number of input features (for MLP)
            model_type: 'mlp' or 'lstm'
            model_dir: Directory for saving models
            sequence_length: Number of gameweeks in sequence (for LSTM)
            sequence_features: Features per gameweek (for LSTM)
        """
        self.model_type = model_type
        self.model_dir = model_dir or Path('models/neural')
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.device = DEVICE

        # Feature scaler
        self.scaler = StandardScaler()

        # Create model
        if model_type == 'mlp':
            self.model = FPLPredictorMLP(input_dim).to(self.device)
        elif model_type == 'lstm':
            self.sequence_length = sequence_length
            self.sequence_features = sequence_features
            self.model = FormLSTM(sequence_features).to(self.device)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        logger.info(f"Created {model_type.upper()} model on {self.device}")

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 100,
        batch_size: int = 256,
        learning_rate: float = 0.001,
        patience: int = 10,
        validation_split: float = 0.2
    ) -> Dict:
        """
        Train the neural model with early stopping.

        Args:
            X: Feature matrix (n_samples, n_features) or sequences
            y: Target values
            epochs: Maximum training epochs
            batch_size: Training batch size
            learning_rate: Initial learning rate
            patience: Early stopping patience
            validation_split: Fraction for validation

        Returns:
            Training metrics dict
        """
        # Fit scaler and transform
        if self.model_type == 'mlp':
            X_scaled = self.scaler.fit_transform(X)
        else:
            # For LSTM, scale each feature across all sequences
            original_shape = X.shape
            X_flat = X.reshape(-1, X.shape[-1])
            X_scaled_flat = self.scaler.fit_transform(X_flat)
            X_scaled = X_scaled_flat.reshape(original_shape)

        # Split train/val
        n_val = int(len(X) * validation_split)
        X_train, X_val = X_scaled[:-n_val], X_scaled[-n_val:]
        y_train, y_val = y[:-n_val], y[-n_val:]

        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train).to(self.device)
        y_train_t = torch.FloatTensor(y_train).to(self.device)
        X_val_t = torch.FloatTensor(X_val).to(self.device)
        y_val_t = torch.FloatTensor(y_val).to(self.device)

        # DataLoader
        train_dataset = TensorDataset(X_train_t, y_train_t)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        # Loss and optimizer
        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5
        )

        # Training loop with early stopping
        best_val_loss = float('inf')
        patience_counter = 0
        best_state = None
        train_losses = []
        val_losses = []

        for epoch in range(epochs):
            # Training
            self.model.train()
            epoch_loss = 0.0

            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()
                predictions = self.model(X_batch)
                loss = criterion(predictions, y_batch)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item() * len(X_batch)

            train_loss = epoch_loss / len(X_train)
            train_losses.append(train_loss)

            # Validation
            self.model.eval()
            with torch.no_grad():
                val_predictions = self.model(X_val_t)
                val_loss = criterion(val_predictions, y_val_t).item()
            val_losses.append(val_loss)

            # Learning rate scheduling
            scheduler.step(val_loss)

            # Early stopping check
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = self.model.state_dict().copy()
            else:
                patience_counter += 1

            if (epoch + 1) % 10 == 0:
                logger.info(
                    f"Epoch {epoch+1}/{epochs} - "
                    f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}"
                )

            if patience_counter >= patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

        # Restore best model
        if best_state is not None:
            self.model.load_state_dict(best_state)

        # Final metrics
        self.model.eval()
        with torch.no_grad():
            final_val_pred = self.model(X_val_t).cpu().numpy()

        rmse = np.sqrt(np.mean((final_val_pred - y_val) ** 2))
        mae = np.mean(np.abs(final_val_pred - y_val))

        metrics = {
            'final_val_rmse': float(rmse),
            'final_val_mae': float(mae),
            'best_val_loss': float(best_val_loss),
            'epochs_trained': len(train_losses),
            'train_losses': train_losses,
            'val_losses': val_losses
        }

        logger.info(f"Training complete - Val RMSE: {rmse:.4f}, Val MAE: {mae:.4f}")

        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions.

        Args:
            X: Feature matrix or sequences

        Returns:
            Predicted points
        """
        self.model.eval()

        # Scale features
        if self.model_type == 'mlp':
            X_scaled = self.scaler.transform(X)
        else:
            original_shape = X.shape
            X_flat = X.reshape(-1, X.shape[-1])
            X_scaled_flat = self.scaler.transform(X_flat)
            X_scaled = X_scaled_flat.reshape(original_shape)

        X_t = torch.FloatTensor(X_scaled).to(self.device)

        with torch.no_grad():
            predictions = self.model(X_t).cpu().numpy()

        # Ensure non-negative predictions
        return np.maximum(0, predictions)

    def save(self, version: str = 'latest'):
        """Save model, scaler, and config."""
        model_path = self.model_dir / f'{self.model_type}_{version}.pt'
        scaler_path = self.model_dir / f'{self.model_type}_scaler_{version}.pkl'

        # Save model config for rebuilding architecture
        config = {
            'model_state_dict': self.model.state_dict(),
            'model_type': self.model_type,
            'device': str(self.device)
        }

        if self.model_type == 'mlp':
            # Get input dimension from first layer
            config['input_dim'] = self.model.network[0].in_features
        elif self.model_type == 'lstm':
            config['sequence_features'] = self.model.lstm.input_size
            config['hidden_size'] = self.model.hidden_size
            config['num_layers'] = self.model.num_layers
            config['bidirectional'] = self.model.bidirectional

        torch.save(config, model_path)

        joblib.dump(self.scaler, scaler_path)

        logger.info(f"Saved {self.model_type} model to {model_path}")

    def load(self, version: str = 'latest'):
        """Load model and scaler."""
        model_path = self.model_dir / f'{self.model_type}_{version}.pt'
        scaler_path = self.model_dir / f'{self.model_type}_scaler_{version}.pkl'

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)

        # Rebuild model with correct architecture from saved config
        if self.model_type == 'mlp' and 'input_dim' in checkpoint:
            input_dim = checkpoint['input_dim']
            self.model = FPLPredictorMLP(input_dim).to(self.device)
        elif self.model_type == 'lstm' and 'sequence_features' in checkpoint:
            self.model = FormLSTM(
                sequence_features=checkpoint['sequence_features'],
                hidden_size=checkpoint.get('hidden_size', 32),
                num_layers=checkpoint.get('num_layers', 2),
                bidirectional=checkpoint.get('bidirectional', True)
            ).to(self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])

        if scaler_path.exists():
            self.scaler = joblib.load(scaler_path)

        self.model.eval()
        logger.info(f"Loaded {self.model_type} model from {model_path}")


class PositionNeuralEnsemble:
    """
    Position-specific neural models that integrate with existing ensemble.

    For each position (GK, DEF, MID, FWD):
    - MLP model trained on aggregated features
    - Optional LSTM model trained on form sequences

    The outputs can be added as additional base models to the stacking ensemble.
    """

    def __init__(self, model_dir: Path = None, use_lstm: bool = True):
        """
        Args:
            model_dir: Directory for saving models
            use_lstm: Whether to include LSTM models
        """
        self.model_dir = model_dir or Path('models/neural')
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.use_lstm = use_lstm

        # Position-specific models
        self.mlp_models: Dict[int, NeuralPredictor] = {}
        self.lstm_models: Dict[int, NeuralPredictor] = {}

        logger.info(f"PositionNeuralEnsemble initialized (LSTM: {use_lstm})")

    def train_position(
        self,
        position: int,
        X: np.ndarray,
        y: np.ndarray,
        sequences: np.ndarray = None,
        **kwargs
    ) -> Dict:
        """
        Train neural models for a specific position.

        Args:
            position: Player position (1-4)
            X: Feature matrix (n_samples, n_features)
            y: Target points
            sequences: Optional form sequences (n_samples, seq_len, seq_features)
            **kwargs: Training hyperparameters

        Returns:
            Training metrics
        """
        metrics = {'position': position}

        # Train MLP
        logger.info(f"Training MLP for position {position}...")
        mlp_predictor = NeuralPredictor(
            input_dim=X.shape[1],
            model_type='mlp',
            model_dir=self.model_dir / f'pos_{position}'
        )
        mlp_metrics = mlp_predictor.train(X, y, **kwargs)
        self.mlp_models[position] = mlp_predictor
        metrics['mlp'] = mlp_metrics

        # Train LSTM if sequences provided
        if self.use_lstm and sequences is not None:
            logger.info(f"Training LSTM for position {position}...")
            lstm_predictor = NeuralPredictor(
                input_dim=sequences.shape[2],  # sequence features
                model_type='lstm',
                model_dir=self.model_dir / f'pos_{position}',
                sequence_length=sequences.shape[1],
                sequence_features=sequences.shape[2]
            )
            lstm_metrics = lstm_predictor.train(sequences, y, **kwargs)
            self.lstm_models[position] = lstm_predictor
            metrics['lstm'] = lstm_metrics

        return metrics

    def predict(
        self,
        position: int,
        X: np.ndarray,
        sequences: np.ndarray = None
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Get predictions from neural models.

        Args:
            position: Player position
            X: Features for MLP
            sequences: Sequences for LSTM

        Returns:
            (mlp_predictions, lstm_predictions or None)
        """
        mlp_preds = None
        lstm_preds = None

        if position in self.mlp_models:
            mlp_preds = self.mlp_models[position].predict(X)

        if self.use_lstm and position in self.lstm_models and sequences is not None:
            lstm_preds = self.lstm_models[position].predict(sequences)

        return mlp_preds, lstm_preds

    def save_all(self, version: str = 'latest'):
        """Save all position models."""
        for pos in [1, 2, 3, 4]:
            if pos in self.mlp_models:
                self.mlp_models[pos].save(version)
            if pos in self.lstm_models:
                self.lstm_models[pos].save(version)

        logger.info(f"Saved all neural models with version: {version}")

    def load_all(self, version: str = 'latest'):
        """Load all position models."""
        for pos in [1, 2, 3, 4]:
            mlp_path = self.model_dir / f'pos_{pos}' / f'mlp_{version}.pt'
            if mlp_path.exists():
                # We need to know input_dim, load from config or use default
                predictor = NeuralPredictor(
                    input_dim=30,  # Will be overwritten on load
                    model_type='mlp',
                    model_dir=self.model_dir / f'pos_{pos}'
                )
                predictor.load(version)
                self.mlp_models[pos] = predictor

            if self.use_lstm:
                lstm_path = self.model_dir / f'pos_{pos}' / f'lstm_{version}.pt'
                if lstm_path.exists():
                    predictor = NeuralPredictor(
                        input_dim=10,  # sequence features
                        model_type='lstm',
                        model_dir=self.model_dir / f'pos_{pos}'
                    )
                    predictor.load(version)
                    self.lstm_models[pos] = predictor

        logger.info(f"Loaded neural models with version: {version}")


def check_gpu():
    """Check GPU availability and print info."""
    print("=" * 60)
    print("GPU STATUS CHECK")
    print("=" * 60)

    if torch.cuda.is_available():
        print(f"CUDA Available: Yes")
        print(f"GPU Device: {torch.cuda.get_device_name(0)}")
        print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        print(f"PyTorch CUDA Version: {torch.version.cuda}")
    else:
        print("CUDA Available: No (using CPU)")

    print(f"PyTorch Version: {torch.__version__}")
    print("=" * 60)


if __name__ == '__main__':
    check_gpu()
