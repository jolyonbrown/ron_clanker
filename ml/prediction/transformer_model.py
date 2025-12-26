#!/usr/bin/env python3
"""
Transformer Model for FPL Prediction

Uses self-attention to model player form sequences and learn player embeddings.

Architecture:
- Player embedding: player_code → 32-dim learned vector
- Feature projection: GW stats → hidden_dim
- Positional encoding: sequence position awareness
- Transformer encoder: self-attention over form sequence
- Output head: predicted xP for next gameweek

Weekly Cadence Integration:
1. POST-GW: Add new data to training set
2. WEEKLY: Fine-tune on latest data (or full retrain monthly)
3. PRE-DEADLINE: Generate predictions for all players
"""

import logging
import math
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from sklearn.preprocessing import StandardScaler
import joblib

logger = logging.getLogger('ron_clanker.ml.transformer')

# Check GPU availability
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
logger.info(f"Transformer model using device: {DEVICE}")


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for sequence position awareness."""

    def __init__(self, d_model: int, max_len: int = 50, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        # Create positional encoding matrix
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))

        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # Shape: (1, max_len, d_model)

        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Tensor of shape (batch, seq_len, d_model)
        Returns:
            Tensor with positional encoding added
        """
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class FPLTransformer(nn.Module):
    """
    Transformer model for FPL point prediction with learned player embeddings.

    Input: Sequence of last N gameweeks for a player
    Output: Predicted points for next gameweek
    Bonus: Learned 32-dim player embeddings
    """

    def __init__(
        self,
        num_players: int = 1000,
        embedding_dim: int = 32,
        num_features: int = 20,
        hidden_dim: int = 64,
        num_heads: int = 4,
        num_layers: int = 2,
        dropout: float = 0.1,
        max_seq_len: int = 10
    ):
        """
        Args:
            num_players: Max number of unique players (for embedding table)
            embedding_dim: Dimension of player embeddings
            num_features: Number of input features per gameweek
            hidden_dim: Transformer hidden dimension
            num_heads: Number of attention heads
            num_layers: Number of transformer encoder layers
            dropout: Dropout rate
            max_seq_len: Maximum sequence length (gameweeks of history)
        """
        super().__init__()

        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim

        # Player embedding layer - learns latent player representations
        self.player_embedding = nn.Embedding(num_players, embedding_dim)

        # Project GW features to hidden dimension
        self.feature_projection = nn.Linear(num_features, hidden_dim - embedding_dim)

        # Positional encoding
        self.pos_encoder = PositionalEncoding(hidden_dim, max_seq_len, dropout)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            activation='gelu',
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Output head
        self.output_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)
        )

        self._init_weights()

    def _init_weights(self):
        """Initialize weights using Xavier/Kaiming initialization."""
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

        # Initialize embeddings from normal distribution
        nn.init.normal_(self.player_embedding.weight, mean=0, std=0.1)

    def forward(
        self,
        player_ids: torch.Tensor,
        features: torch.Tensor,
        mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Forward pass.

        Args:
            player_ids: Player IDs, shape (batch,)
            features: GW features, shape (batch, seq_len, num_features)
            mask: Optional attention mask for padding

        Returns:
            Predicted points, shape (batch,)
        """
        batch_size, seq_len, _ = features.shape

        # Get player embeddings and expand to sequence length
        player_emb = self.player_embedding(player_ids)  # (batch, embedding_dim)
        player_emb = player_emb.unsqueeze(1).expand(-1, seq_len, -1)  # (batch, seq_len, embedding_dim)

        # Project features
        feat_proj = self.feature_projection(features)  # (batch, seq_len, hidden_dim - embedding_dim)

        # Concatenate player embedding with projected features
        x = torch.cat([player_emb, feat_proj], dim=-1)  # (batch, seq_len, hidden_dim)

        # Add positional encoding
        x = self.pos_encoder(x)

        # Transformer encoder
        x = self.transformer_encoder(x, src_key_padding_mask=mask)

        # Use last sequence position for prediction (or could use mean pooling)
        x = x[:, -1, :]  # (batch, hidden_dim)

        # Output prediction
        output = self.output_head(x).squeeze(-1)  # (batch,)

        return output

    def get_player_embeddings(self) -> np.ndarray:
        """Extract learned player embeddings as numpy array."""
        return self.player_embedding.weight.detach().cpu().numpy()


class FPLSequenceDataset(Dataset):
    """Dataset for player gameweek sequences."""

    def __init__(
        self,
        sequences: List[Dict],
        player_id_map: Dict[int, int],
        seq_len: int = 6
    ):
        """
        Args:
            sequences: List of dicts with 'player_code', 'features', 'target'
            player_id_map: Map from player_code to embedding index
            seq_len: Fixed sequence length (pad/truncate to this)
        """
        self.sequences = sequences
        self.player_id_map = player_id_map
        self.seq_len = seq_len

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        seq = self.sequences[idx]

        player_id = self.player_id_map.get(seq['player_code'], 0)
        features = np.array(seq['features'], dtype=np.float32)
        target = float(seq['target'])

        # Pad or truncate to fixed length
        if len(features) < self.seq_len:
            padding = np.zeros((self.seq_len - len(features), features.shape[1]), dtype=np.float32)
            features = np.vstack([padding, features])
            mask = np.array([True] * (self.seq_len - len(seq['features'])) + [False] * len(seq['features']))
        else:
            features = features[-self.seq_len:]
            mask = np.array([False] * self.seq_len)

        return {
            'player_id': torch.tensor(player_id, dtype=torch.long),
            'features': torch.tensor(features, dtype=torch.float32),
            'mask': torch.tensor(mask, dtype=torch.bool),
            'target': torch.tensor(target, dtype=torch.float32)
        }


class TransformerPredictor:
    """
    High-level interface for training and prediction with the FPL Transformer.

    Handles:
    - Data loading from database
    - Training loop with validation
    - Model saving/loading
    - Prediction generation
    """

    FEATURE_COLS = [
        'minutes', 'goals_scored', 'assists', 'clean_sheets',
        'goals_conceded', 'saves', 'bonus', 'bps',
        'influence', 'creativity', 'threat', 'ict_index',
        'expected_goals', 'expected_assists',
        'expected_goal_involvements', 'expected_goals_conceded',
        'yellow_cards', 'red_cards', 'own_goals', 'penalties_missed'
    ]

    def __init__(self, model_dir: str = 'models/transformer'):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.model: Optional[FPLTransformer] = None
        self.scaler: Optional[StandardScaler] = None
        self.player_id_map: Dict[int, int] = {}
        self.seq_len = 6

    def build_sequences_from_db(self, database) -> List[Dict]:
        """
        Build training sequences from historical_gameweek_data.

        Each sequence: last N gameweeks → predict next GW points
        """
        logger.info("Building sequences from historical data...")

        # Fetch all historical data ordered by player and gameweek
        rows = database.execute_query("""
            SELECT player_code, season_id, gameweek, total_points,
                   minutes, goals_scored, assists, clean_sheets,
                   goals_conceded, saves, bonus, bps,
                   influence, creativity, threat, ict_index,
                   expected_goals, expected_assists,
                   expected_goal_involvements, expected_goals_conceded,
                   yellow_cards, red_cards, own_goals, penalties_missed
            FROM historical_gameweek_data
            ORDER BY player_code, season_id, gameweek
        """)

        if not rows:
            logger.warning("No historical data found!")
            return []

        # Group by player
        from collections import defaultdict
        player_data = defaultdict(list)
        for row in rows:
            player_data[row['player_code']].append(row)

        # Build player ID map
        unique_players = sorted(player_data.keys())
        self.player_id_map = {code: idx for idx, code in enumerate(unique_players)}

        # Create sequences
        sequences = []
        for player_code, gws in player_data.items():
            if len(gws) < self.seq_len + 1:
                continue  # Need enough history

            for i in range(self.seq_len, len(gws)):
                # Features from previous N gameweeks
                feature_gws = gws[i - self.seq_len:i]
                features = []
                for gw in feature_gws:
                    gw_features = [
                        gw.get('minutes', 0) or 0,
                        gw.get('goals_scored', 0) or 0,
                        gw.get('assists', 0) or 0,
                        gw.get('clean_sheets', 0) or 0,
                        gw.get('goals_conceded', 0) or 0,
                        gw.get('saves', 0) or 0,
                        gw.get('bonus', 0) or 0,
                        gw.get('bps', 0) or 0,
                        gw.get('influence', 0) or 0,
                        gw.get('creativity', 0) or 0,
                        gw.get('threat', 0) or 0,
                        gw.get('ict_index', 0) or 0,
                        gw.get('expected_goals', 0) or 0,
                        gw.get('expected_assists', 0) or 0,
                        gw.get('expected_goal_involvements', 0) or 0,
                        gw.get('expected_goals_conceded', 0) or 0,
                        gw.get('yellow_cards', 0) or 0,
                        gw.get('red_cards', 0) or 0,
                        gw.get('own_goals', 0) or 0,
                        gw.get('penalties_missed', 0) or 0,
                    ]
                    features.append(gw_features)

                # Target: points in next gameweek
                target = gws[i].get('total_points', 0) or 0

                sequences.append({
                    'player_code': player_code,
                    'features': features,
                    'target': target
                })

        logger.info(f"Built {len(sequences)} sequences from {len(player_data)} players")
        return sequences

    def train(
        self,
        database,
        epochs: int = 50,
        batch_size: int = 64,
        learning_rate: float = 1e-3,
        val_split: float = 0.1
    ):
        """
        Train the transformer model on historical data.

        Args:
            database: Database connection
            epochs: Number of training epochs
            batch_size: Batch size
            learning_rate: Learning rate
            val_split: Validation split ratio
        """
        # Build sequences
        sequences = self.build_sequences_from_db(database)
        if not sequences:
            raise ValueError("No training sequences available!")

        # Fit scaler on all features
        all_features = []
        for seq in sequences:
            all_features.extend(seq['features'])
        all_features = np.array(all_features)

        self.scaler = StandardScaler()
        self.scaler.fit(all_features)

        # Scale features in sequences
        for seq in sequences:
            seq['features'] = self.scaler.transform(seq['features']).tolist()

        # Split train/val
        np.random.shuffle(sequences)
        val_size = int(len(sequences) * val_split)
        train_seqs = sequences[val_size:]
        val_seqs = sequences[:val_size]

        logger.info(f"Training on {len(train_seqs)} sequences, validating on {len(val_seqs)}")

        # Create datasets
        train_dataset = FPLSequenceDataset(train_seqs, self.player_id_map, self.seq_len)
        val_dataset = FPLSequenceDataset(val_seqs, self.player_id_map, self.seq_len)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        # Initialize model
        num_players = len(self.player_id_map)
        num_features = len(self.FEATURE_COLS)

        self.model = FPLTransformer(
            num_players=num_players + 1,  # +1 for unknown players
            embedding_dim=32,
            num_features=num_features,
            hidden_dim=64,
            num_heads=4,
            num_layers=2,
            dropout=0.1,
            max_seq_len=self.seq_len
        ).to(DEVICE)

        optimizer = optim.AdamW(self.model.parameters(), lr=learning_rate, weight_decay=0.01)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        criterion = nn.MSELoss()

        best_val_loss = float('inf')

        for epoch in range(epochs):
            # Training
            self.model.train()
            train_loss = 0.0
            for batch in train_loader:
                player_ids = batch['player_id'].to(DEVICE)
                features = batch['features'].to(DEVICE)
                mask = batch['mask'].to(DEVICE)
                targets = batch['target'].to(DEVICE)

                optimizer.zero_grad()
                outputs = self.model(player_ids, features, mask)
                loss = criterion(outputs, targets)
                loss.backward()

                # Gradient clipping
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation
            self.model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for batch in val_loader:
                    player_ids = batch['player_id'].to(DEVICE)
                    features = batch['features'].to(DEVICE)
                    mask = batch['mask'].to(DEVICE)
                    targets = batch['target'].to(DEVICE)

                    outputs = self.model(player_ids, features, mask)
                    loss = criterion(outputs, targets)
                    val_loss += loss.item()

            val_loss /= len(val_loader)
            scheduler.step()

            if (epoch + 1) % 10 == 0 or epoch == 0:
                logger.info(f"Epoch {epoch+1}/{epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                self.save()

        logger.info(f"Training complete. Best validation loss: {best_val_loss:.4f}")

    def predict(self, player_code: int, recent_gws: List[Dict]) -> float:
        """
        Predict points for a player given recent gameweek data.

        Args:
            player_code: Player's code
            recent_gws: List of recent gameweek dicts with stats

        Returns:
            Predicted points
        """
        if self.model is None:
            raise ValueError("Model not loaded!")

        self.model.eval()

        # Extract features
        features = []
        for gw in recent_gws[-self.seq_len:]:
            gw_features = [
                gw.get('minutes', 0) or 0,
                gw.get('goals_scored', 0) or 0,
                gw.get('assists', 0) or 0,
                gw.get('clean_sheets', 0) or 0,
                gw.get('goals_conceded', 0) or 0,
                gw.get('saves', 0) or 0,
                gw.get('bonus', 0) or 0,
                gw.get('bps', 0) or 0,
                gw.get('influence', 0) or 0,
                gw.get('creativity', 0) or 0,
                gw.get('threat', 0) or 0,
                gw.get('ict_index', 0) or 0,
                gw.get('expected_goals', 0) or 0,
                gw.get('expected_assists', 0) or 0,
                gw.get('expected_goal_involvements', 0) or 0,
                gw.get('expected_goals_conceded', 0) or 0,
                gw.get('yellow_cards', 0) or 0,
                gw.get('red_cards', 0) or 0,
                gw.get('own_goals', 0) or 0,
                gw.get('penalties_missed', 0) or 0,
            ]
            features.append(gw_features)

        # Scale and pad
        features = np.array(features, dtype=np.float32)
        if self.scaler:
            features = self.scaler.transform(features)

        # Pad if needed
        if len(features) < self.seq_len:
            padding = np.zeros((self.seq_len - len(features), features.shape[1]), dtype=np.float32)
            features = np.vstack([padding, features])

        # Get player ID
        player_id = self.player_id_map.get(player_code, 0)

        # Predict
        with torch.no_grad():
            player_id_tensor = torch.tensor([player_id], dtype=torch.long).to(DEVICE)
            features_tensor = torch.tensor(features, dtype=torch.float32).unsqueeze(0).to(DEVICE)

            prediction = self.model(player_id_tensor, features_tensor)
            return prediction.item()

    def predict_all_available(
        self,
        database,
        gameweek: int = 17,
        available_statuses: List[str] = None
    ) -> List[Dict]:
        """
        Predict points for all available players.

        Filters out injured, suspended, and unavailable players before prediction.

        Args:
            database: Database connection
            gameweek: Current gameweek (for form data)
            available_statuses: List of status codes to include.
                               Default: ['a'] (available only)
                               Use ['a', 'd'] to include doubtful players

        Returns:
            List of dicts with player info and predictions, sorted by xP descending
        """
        if self.model is None:
            raise ValueError("Model not loaded!")

        # Default to only fully available players
        if available_statuses is None:
            available_statuses = ['a']

        # Build status filter
        status_placeholders = ','.join('?' * len(available_statuses))

        # Get available players with their info
        players = database.execute_query(f"""
            SELECT p.id, p.code, p.web_name, p.now_cost, p.element_type,
                   p.status, p.chance_of_playing_next_round,
                   t.short_name as team, t.id as team_id
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE p.status IN ({status_placeholders})
            AND p.now_cost > 0
        """, tuple(available_statuses))

        if not players:
            logger.warning("No available players found!")
            return []

        logger.info(f"Predicting for {len(players)} available players (status in {available_statuses})")

        # Get form sequences and predict
        predictions = []
        for p in players:
            # Get recent form data
            form_data = database.execute_query("""
                SELECT minutes, total_points, goals_scored, assists,
                       clean_sheets, goals_conceded, bonus, bps,
                       influence, creativity, threat, ict_index,
                       saves, penalties_saved, yellow_cards, red_cards
                FROM player_gameweek_history
                WHERE player_id = ? AND gameweek <= ?
                ORDER BY gameweek DESC
                LIMIT ?
            """, (p['id'], gameweek, self.seq_len))

            if len(form_data) < 3:  # Need minimum form data
                continue

            # Convert to sequence format (oldest first)
            form_seq = []
            for row in reversed(form_data):
                form_seq.append({
                    'minutes': row['minutes'] or 0,
                    'goals_scored': row['goals_scored'] or 0,
                    'assists': row['assists'] or 0,
                    'clean_sheets': row['clean_sheets'] or 0,
                    'goals_conceded': row['goals_conceded'] or 0,
                    'saves': row['saves'] or 0,
                    'bonus': row['bonus'] or 0,
                    'bps': row['bps'] or 0,
                    'influence': float(row['influence'] or 0),
                    'creativity': float(row['creativity'] or 0),
                    'threat': float(row['threat'] or 0),
                    'ict_index': float(row['ict_index'] or 0),
                    'expected_goals': 0,  # Not in player_gameweek_history
                    'expected_assists': 0,
                    'expected_goal_involvements': 0,
                    'expected_goals_conceded': 0,
                    'yellow_cards': row['yellow_cards'] or 0,
                    'red_cards': row['red_cards'] or 0,
                    'own_goals': 0,
                    'penalties_missed': 0,
                })

            try:
                xp = self.predict(p['code'], form_seq)
                predictions.append({
                    'id': p['id'],
                    'code': p['code'],
                    'name': p['web_name'],
                    'team': p['team'],
                    'team_id': p['team_id'],
                    'pos': p['element_type'],  # 1=GK, 2=DEF, 3=MID, 4=FWD
                    'price': p['now_cost'] / 10,
                    'status': p['status'],
                    'chance_of_playing': p['chance_of_playing_next_round'],
                    'xp': xp
                })
            except Exception as e:
                logger.debug(f"Prediction failed for {p['web_name']}: {e}")
                continue

        # Sort by xP descending
        predictions.sort(key=lambda x: x['xp'], reverse=True)

        logger.info(f"Generated predictions for {len(predictions)} players")
        return predictions

    def save(self):
        """Save model, scaler, and player ID map."""
        if self.model is None:
            return

        torch.save(self.model.state_dict(), self.model_dir / 'transformer_model.pt')
        joblib.dump(self.scaler, self.model_dir / 'scaler.pkl')
        joblib.dump(self.player_id_map, self.model_dir / 'player_id_map.pkl')
        joblib.dump({'seq_len': self.seq_len}, self.model_dir / 'config.pkl')
        logger.info(f"Model saved to {self.model_dir}")

    def load(self):
        """Load model, scaler, and player ID map."""
        model_path = self.model_dir / 'transformer_model.pt'
        scaler_path = self.model_dir / 'scaler.pkl'
        player_map_path = self.model_dir / 'player_id_map.pkl'
        config_path = self.model_dir / 'config.pkl'

        if not all(p.exists() for p in [model_path, scaler_path, player_map_path]):
            raise FileNotFoundError(f"Model files not found in {self.model_dir}")

        self.scaler = joblib.load(scaler_path)
        self.player_id_map = joblib.load(player_map_path)

        # Load config (seq_len)
        if config_path.exists():
            config = joblib.load(config_path)
            self.seq_len = config.get('seq_len', 6)
        else:
            self.seq_len = 6  # Default

        num_players = len(self.player_id_map)
        self.model = FPLTransformer(
            num_players=num_players + 1,
            embedding_dim=32,
            num_features=len(self.FEATURE_COLS),
            hidden_dim=64,
            num_heads=4,
            num_layers=2,
            max_seq_len=self.seq_len
        ).to(DEVICE)

        self.model.load_state_dict(torch.load(model_path, map_location=DEVICE))
        self.model.eval()
        logger.info(f"Model loaded from {self.model_dir}")


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from data.database import Database

    print(f"Using device: {DEVICE}")
    print(f"CUDA available: {torch.cuda.is_available()}")

    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    db = Database('./data/ron_clanker.db')

    predictor = TransformerPredictor()

    print("\nTraining transformer model...")
    predictor.train(db, epochs=30, batch_size=128)

    print("\nModel trained and saved!")
    print(f"Player embeddings shape: {predictor.model.get_player_embeddings().shape}")
