#!/usr/bin/env python3
"""
Debug script to trace enrichment logic
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from agents.synthesis.engine import DecisionSynthesisEngine

db = Database()

print("=" * 80)
print("CURRENT TEAM FROM DATABASE")
print("=" * 80)

current_team = db.get_actual_current_team()

for i, player in enumerate(current_team[:5], 1):
    print(f"\nPlayer {i}:")
    print(f"  player_id (from ct): {player.get('player_id')}")
    print(f"  id (from ct row): {player.get('id')}")
    print(f"  web_name: {player.get('web_name')}")
    print(f"  element_type: {player.get('element_type')}")

print("\n" + "=" * 80)
print("ML PREDICTIONS")
print("=" * 80)

engine = DecisionSynthesisEngine(database=db)
recs = engine.synthesize_recommendations(9)

print(f"\nTotal predictions: {len(recs['top_players'])}")
print("\nFirst 5 predictions:")

for i, pred in enumerate(recs['top_players'][:5], 1):
    print(f"\n{i}. {pred['name']}")
    print(f"   player_id: {pred['player_id']}")
    print(f"   xp: {pred.get('xp', 0):.2f}")
    print(f"   value_score: {pred.get('value_score', 0):.4f}")

# Now check specific players from current_team
print("\n" + "=" * 80)
print("ENRICHMENT TEST - MATCH CHECK")
print("=" * 80)

# Create predictions lookup
predictions_lookup = {}
for player_pred in recs.get('top_players', []):
    predictions_lookup[player_pred['player_id']] = {
        'xP': player_pred.get('xp', 0),
        'value_score': player_pred.get('value_score', 0),
        'name': player_pred['name']
    }

print(f"\nPredictions lookup has {len(predictions_lookup)} entries")

# Try to match first 3 players
for i, player in enumerate(current_team[:3], 1):
    fpl_player_id = player.get('player_id')
    print(f"\n{i}. {player.get('web_name')} (player_id={fpl_player_id})")

    pred = predictions_lookup.get(fpl_player_id)
    if pred:
        print(f"   ✅ MATCH FOUND:")
        print(f"      Prediction for: {pred['name']}")
        print(f"      xP: {pred['xP']:.2f}")
        print(f"      value_score: {pred['value_score']:.4f}")
    else:
        print(f"   ❌ NO MATCH - player_id {fpl_player_id} not in predictions")

        # Check if it's there under id instead
        row_id = player.get('id')
        pred_by_row = predictions_lookup.get(row_id)
        if pred_by_row:
            print(f"   ⚠️  FOUND UNDER row id={row_id}: {pred_by_row['name']}")
