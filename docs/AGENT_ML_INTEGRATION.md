# ML Integration Guide for Future Agents

This document explains how to integrate ML predictions into any agent architecture.
The current Ron Clanker implementation is being replaced with individual autonomous
agents, but they all need access to the same ML capabilities.

## Quick Start

```python
from services import MLPredictionService

# Initialize (does model loading automatically)
ml_service = MLPredictionService()

# Get predictions for specific players
predictions = ml_service.predict_player_points(
    player_ids=[123, 456, 789],
    gameweek=15
)
# Result: {123: 6.5, 456: 4.2, 789: 8.1}

# Get predictions for ALL players
all_predictions = ml_service.predict_all_players(gameweek=15)
```

## Service Interface

### MLPredictionService

The main service class. Initialize once per agent, reuse for all predictions.

#### Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `predict_player_points(player_ids, gameweek)` | Predict xP for specific players | `Dict[int, float]` |
| `predict_all_players(gameweek)` | Predict xP for all players | `Dict[int, float]` |
| `predict_price_changes(player_ids)` | Predict price rises/falls | `Dict[int, Tuple[str, float]]` |
| `get_model_info()` | Get model status/version | `Dict[str, Any]` |
| `get_feature_importance(position, top_n)` | Explain predictions | `List[Tuple[str, float]]` |
| `get_prediction_with_breakdown(player_id, gameweek)` | Detailed single prediction | `Dict[str, Any]` |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `models_loaded` | `bool` | Whether ML models are available |
| `model_version` | `str` | Current model version (e.g., 'gw13_full') |
| `available_positions` | `List[int]` | Positions with trained models [1,2,3,4] |

## Example Agent Implementation

Here's how a hypothetical "Captain Selection Agent" might use the service:

```python
from services import MLPredictionService
from data.database import Database

class CaptainSelectionAgent:
    """Agent that selects optimal captain using ML predictions."""

    def __init__(self):
        self.ml = MLPredictionService()
        self.db = Database()

    def select_captain(self, current_team: List[int], gameweek: int) -> int:
        """Select optimal captain from current team."""

        # Get predictions for all team members
        predictions = self.ml.predict_player_points(current_team, gameweek)

        # Sort by predicted points
        sorted_players = sorted(
            predictions.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Captain is highest predicted scorer
        captain_id = sorted_players[0][0]

        # Get breakdown for logging/explanation
        breakdown = self.ml.get_prediction_with_breakdown(captain_id, gameweek)
        print(f"Captain: {breakdown['player_name']} (xP: {breakdown['adjusted_prediction']:.2f})")

        return captain_id
```

## What the Service Handles

1. **Model Loading**: Automatically finds and loads latest trained models
2. **Feature Engineering**: Extracts 30+ features from historical data
3. **Position-Specific Models**: Uses appropriate model for GK/DEF/MID/FWD
4. **News Adjustments**: Reduces predictions for injured/doubtful players
5. **Fallbacks**: Returns form-based predictions if models unavailable
6. **Error Handling**: Never throws to caller, logs issues and returns safe defaults

## What Your Agent Must Handle

1. **Gameweek Context**: You must know which gameweek to predict for
2. **Player IDs**: You need valid FPL player IDs from the database
3. **Decision Logic**: The service gives you predictions, you make the decision
4. **Caching**: Consider caching predictions if calling multiple times per GW

## Database Requirements

The service reads from these tables (you don't need to manage these):

- `players` - Current player data (form, price, status)
- `player_gameweek_history` - Historical performance (points, minutes, goals)
- `fixtures` - Fixture difficulty data
- `scout_events` - News intelligence (for adjustments)

## Model Architecture

The prediction models use stacked ensembles:

```
Input: 30+ engineered features
    ↓
[Random Forest] → prediction_1
[Gradient Boosting] → prediction_2  → [Ridge Meta-Learner] → Final xP
[XGBoost] → prediction_3
```

Each position (GK, DEF, MID, FWD) has its own ensemble.

## Feature Categories

Features used for prediction:

1. **Recent Form (Last 5 Games)**
   - avg_points, avg_minutes, avg_goals, avg_assists
   - avg_bonus, avg_bps, avg_clean_sheets
   - form_trend (improving/declining)

2. **Season Stats**
   - points_per_game, minutes_per_game
   - goals_per_game, assists_per_game

3. **ICT Index**
   - influence, creativity, threat
   - Both season totals and recent averages

4. **Fixture Context**
   - fixture_difficulty (1-5)
   - is_home, opponent_strength
   - opponent_defensive_strength, opponent_attacking_strength

5. **Player Attributes**
   - price, ownership, position

## Retraining Models

To retrain with new gameweek data:

```bash
cd /home/jolyon/projects/ron_clanker
python scripts/train_prediction_models.py --train-end <latest_gameweek>
```

Models are saved to `models/prediction/` with version tags.

## Debugging Predictions

If predictions seem off, use `get_prediction_with_breakdown()`:

```python
breakdown = ml_service.get_prediction_with_breakdown(player_id, gameweek)

print(f"Player: {breakdown['player_name']}")
print(f"Position: {breakdown['position']}")
print(f"Raw xP: {breakdown['raw_prediction']:.2f}")
print(f"Adjusted xP: {breakdown['adjusted_prediction']:.2f}")
print(f"Key features:")
for key in ['form_avg_points', 'fixture_difficulty', 'fpl_form']:
    print(f"  {key}: {breakdown['features'].get(key)}")
```

## Price Predictions

```python
price_preds = ml_service.predict_price_changes([123, 456, 789])

for player_id, (direction, confidence) in price_preds.items():
    if direction == 'rise' and confidence > 0.7:
        print(f"Player {player_id} likely to rise (confidence: {confidence:.0%})")
```

## Checking Service Health

```python
info = ml_service.get_model_info()

if not info['models_loaded']:
    print("WARNING: ML models not loaded, using fallback predictions")
    print("Run training script to create models")
else:
    print(f"Models loaded: version {info['model_version']}")
    print(f"Positions covered: {info['available_positions']}")
```

## New ML Components (December 2025)

### Model Registry (`ml/model_registry.py`)

Version control for ML models with activation, rollback, and performance tracking.

```python
from ml.model_registry import ModelRegistry

registry = ModelRegistry()

# List active models
for model in registry.list_models(active_only=True):
    print(f"{model['model_type']} v{model['version']}: {model['metrics']}")

# Register a new model
registry.register_model(
    model_type='ensemble',
    model_name='xp_prediction',
    position=4,  # FWD
    version='v2.0',
    hyperparameters={'n_estimators': 200, 'max_depth': 10},
    metrics={'rmse': 2.15, 'mae': 1.72},
    training_samples=4200,
    trained_on_gameweeks='1-14'
)

# Activate a specific version
registry.activate_model('ensemble', 'xp_prediction', 4, 'v2.0')

# Load active model for predictions
model_data = registry.get_active_model('ensemble', 'xp_prediction', 4)
```

### Elo Rating System (`ml/elo_ratings.py`)

Dynamic team strength ratings updated after each gameweek.

```python
from ml.elo_ratings import EloRatingSystem

elo = EloRatingSystem()

# Get fixture difficulty based on Elo ratings
difficulty = elo.get_fixture_difficulty(
    team_id=13,      # Man City
    opponent_id=2,   # Aston Villa
    is_home=True
)
# Returns: 2.3 (easier fixture - City favored)

# Get attack/defence breakdown
team_elo = elo.get_team_ratings(team_id=13)
# Returns: {'overall_elo': 1615, 'attack_elo': 1680, 'defence_elo': 1550}

# Update after gameweek completes
matches_updated = elo.update_after_gameweek(gameweek=14)

# Get rankings
rankings = elo.get_rankings()
for r in rankings[:5]:
    print(f"{r['rank']}. {r['short_name']} - {r['overall_elo']:.0f}")
```

### Captain Optimizer (`ml/captain_optimizer.py`)

ML model for identifying optimal captain picks based on ceiling potential.

```python
from ml.captain_optimizer import CaptainOptimizer

optimizer = CaptainOptimizer()

# Train the model (weekly)
metrics = optimizer.train()
optimizer.save()
print(f"Training accuracy: {metrics['train_accuracy']:.1%}")

# Get captain recommendation
team_player_ids = [1, 23, 45, 67, 89, ...]  # 15 player IDs
gameweek = 15

recommendations = optimizer.get_captain_recommendation(
    candidate_player_ids=team_player_ids,
    gameweek=gameweek
)

for rec in recommendations[:3]:
    print(f"{rec['web_name']}: {rec['captain_score']:.2f} score")
    print(f"  Features: form={rec['form']:.1f}, goals_per_90={rec['goals_per_90']:.2f}")
```

### Weekly Model Update Pipeline (`scripts/update_ml_models.py`)

Run after each gameweek completes to keep models current:

```bash
# Update all models
venv/bin/python scripts/update_ml_models.py

# Just Elo ratings
venv/bin/python scripts/update_ml_models.py --elo

# Force captain model retrain
venv/bin/python scripts/update_ml_models.py --captain --force
```

## Future Improvements

Planned enhancements (see beads issues):

- [ ] LSTM for form sequences (ron_clanker-b1w)
- [ ] Player embeddings (ron_clanker-mxz)
- [x] Hyperparameter tuning with Optuna (ron_clanker-ix0) ✅
- [x] Model registry and versioning (ron_clanker-971) ✅
- [x] Elo fixture difficulty system (ron_clanker-ee1) ✅
- [x] Captain optimization model (ron_clanker-sus) ✅
- [x] LightGBM price prediction (ron_clanker-vi8) ✅

When future improvements are implemented, the service interface will remain
the same - predictions will just be more accurate.

## Contact / Issues

For issues with the ML service, check:
1. Model files exist in `models/prediction/`
2. Database has recent player data
3. Logs in `logs/ron_clanker.ml.log`

Create beads issues for bugs or enhancements:
```bash
bd create "ML Service: <description>" -t bug
```
