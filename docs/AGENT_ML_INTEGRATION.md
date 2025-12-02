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

## Future Improvements

These are planned but not yet implemented (see beads issues):

- [ ] LSTM for form sequences (ron_clanker-b1w)
- [ ] Player embeddings (ron_clanker-mxz)
- [ ] Better cross-validation (ron_clanker-92q)
- [ ] Hyperparameter tuning (ron_clanker-ix0)
- [ ] Historical data backfill (ron_clanker-naw)

When these are implemented, the service interface will remain the same -
predictions will just be more accurate.

## Contact / Issues

For issues with the ML service, check:
1. Model files exist in `models/prediction/`
2. Database has recent player data
3. Logs in `logs/ron_clanker.ml.log`

Create beads issues for bugs or enhancements:
```bash
bd create "ML Service: <description>" -t bug
```
