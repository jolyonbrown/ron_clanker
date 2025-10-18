#!/usr/bin/env python3
"""
Test Decision Synthesis Engine

Verifies that the synthesis engine can:
1. Run ML predictions
2. Gather intelligence
3. Generate recommendations

Usage:
    python scripts/test_synthesis_engine.py
    python scripts/test_synthesis_engine.py --gw 9
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.gameweek import get_current_gameweek

# Import synthesis engine directly to avoid circular imports
import importlib.util
spec = importlib.util.spec_from_file_location(
    "synthesis_engine",
    project_root / "agents/synthesis/engine.py"
)
synthesis_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(synthesis_module)
DecisionSynthesisEngine = synthesis_module.DecisionSynthesisEngine


def main():
    parser = argparse.ArgumentParser(description='Test Decision Synthesis Engine')
    parser.add_argument('--gw', type=int, help='Gameweek to analyze (default: current)')
    args = parser.parse_args()

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("DECISION SYNTHESIS ENGINE TEST")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize
    db = Database()
    gameweek = args.gw or get_current_gameweek(db)

    if not gameweek:
        print("❌ Could not determine gameweek")
        return 1

    print(f"Target Gameweek: {gameweek}")
    print("=" * 80)

    # Initialize synthesis engine
    print("\n📦 Initializing Decision Synthesis Engine...")
    engine = DecisionSynthesisEngine(database=db)

    print(f"   Config: team_id={engine.config.get('team_id')}, league_id={engine.config.get('league_id')}")

    # Test 1: Run ML Predictions
    print("\n" + "-" * 80)
    print("TEST 1: ML PREDICTIONS")
    print("-" * 80)

    try:
        predictions = engine.run_ml_predictions(gameweek)
        print(f"✅ Generated {len(predictions)} predictions")

        # Show top 10
        top_pred = sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:10]
        print("\nTop 10 predicted players:")
        for player_id, xp in top_pred:
            player = db.execute_query("SELECT web_name, element_type FROM players WHERE id = ?", (player_id,))
            if player:
                pos = ['', 'GKP', 'DEF', 'MID', 'FWD'][player[0]['element_type']]
                print(f"  {player[0]['web_name']:20s} ({pos}): {xp:.2f} xP")

    except Exception as e:
        print(f"❌ ML Predictions failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Gather Intelligence
    print("\n" + "-" * 80)
    print("TEST 2: INTELLIGENCE GATHERING")
    print("-" * 80)

    try:
        intelligence = engine.gather_intelligence(gameweek)

        print(f"✅ Intelligence gathered")
        print(f"\nLeague Intel: {'✅' if intelligence.get('league') else '❌'}")
        if intelligence.get('league'):
            league = intelligence['league']
            print(f"   Rank: {league.get('rank', 'N/A')}")
            print(f"   Gap to leader: {league.get('gap_to_leader', 0):+d} pts")
            print(f"   Position: {league.get('position', 'unknown')}")

        print(f"\nGlobal Template: {'✅' if intelligence.get('global_template') else '❌'}")
        print(f"Fixtures: {'✅' if intelligence.get('fixtures') else '❌'}")
        print(f"Chips: {'✅' if intelligence.get('chips') else '❌'}")

    except Exception as e:
        print(f"❌ Intelligence gathering failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Synthesize Recommendations
    print("\n" + "-" * 80)
    print("TEST 3: SYNTHESIS - GENERATE RECOMMENDATIONS")
    print("-" * 80)

    try:
        recommendations = engine.synthesize_recommendations(gameweek)

        print(f"✅ Recommendations generated")

        # Strategy
        strategy = recommendations.get('strategy', {})
        print(f"\n📊 STRATEGY:")
        print(f"   Risk Level: {strategy.get('risk_level', 'UNKNOWN')}")
        print(f"   Approach: {strategy.get('approach', 'unknown')}")
        print(f"   Reasoning: {strategy.get('reasoning', 'N/A')}")

        # Top players
        top_players = recommendations.get('top_players', [])[:10]
        print(f"\n⭐ TOP 10 VALUE PLAYERS:")
        print(f"{'Player':20s} {'Pos':5s} {'Price':8s} {'xP':6s} {'Value':8s} {'Own%':7s} {'Type':12s}")
        print("-" * 80)

        for p in top_players:
            pos = ['', 'GKP', 'DEF', 'MID', 'FWD'][p['position']]
            player_type = 'TEMPLATE' if p['is_template'] else ('DIFF' if p['is_differential'] else 'NORMAL')

            print(f"{p['name']:20s} {pos:5s} £{p['price']:5.1f}m  {p['xp']:5.2f}  "
                  f"{p['value_score']:7.3f}  {p['ownership']:6.1f}%  {player_type:12s}")

        # Captain
        captain = recommendations.get('captain_recommendation', {})
        print(f"\n👑 CAPTAIN RECOMMENDATION:")
        primary = captain.get('primary', {})
        if primary:
            print(f"   Primary: {primary.get('name', 'N/A')} ({primary.get('xp', 0):.2f} xP, {primary.get('ownership', 0):.1f}% owned)")

        differential = captain.get('differential_option')
        if differential:
            print(f"   Differential: {differential.get('name', 'N/A')} ({differential.get('xp', 0):.2f} xP, {differential.get('ownership', 0):.1f}% owned)")

        print(f"   Recommendation: {captain.get('recommendation', 'N/A')}")
        print(f"   Reasoning: {captain.get('reasoning', 'N/A')}")

        # Template risks
        risks = recommendations.get('risks_to_cover', [])
        if risks:
            print(f"\n⚠️  TEMPLATE RISKS TO CONSIDER:")
            for risk in risks[:5]:
                print(f"   {risk['name']:20s}: {risk['ownership']:.1f}% owned, {risk['xp']:.2f} xP ({risk['risk_level']} risk)")

        # Save to file
        output_dir = project_root / 'reports' / 'synthesis'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f'synthesis_gw{gameweek}_{start_time.strftime("%Y%m%d_%H%M%S")}.json'

        with open(output_file, 'w') as f:
            json.dump(recommendations, f, indent=2, default=str)

        print(f"\n💾 Full recommendations saved to: {output_file}")

    except Exception as e:
        print(f"❌ Synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("✅ SYNTHESIS ENGINE TEST COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Gameweek: {gameweek}")
    print(f"Predictions: {len(predictions)}")
    print(f"Recommendations: Generated")

    return 0


if __name__ == '__main__':
    sys.exit(main())
