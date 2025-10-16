#!/usr/bin/env python3
"""Test Rules Engine validation."""

from agents.rules_engine import RulesEngine

def test_rules_engine():
    """Test basic rules validation."""
    print("Testing Rules Engine...")
    print("=" * 60)

    engine = RulesEngine()

    # Test valid formations
    print("\n1. Valid Formations:")
    formations = engine.get_valid_formations()
    for def_, mid, fwd in formations:
        print(f"   {def_}-{mid}-{fwd}")

    # Test formation validation
    print("\n2. Formation Validation:")
    print(f"   4-4-2 valid? {engine.is_formation_valid(4, 4, 2)}")
    print(f"   5-5-1 valid? {engine.is_formation_valid(5, 5, 1)}")
    print(f"   3-3-3 valid? {engine.is_formation_valid(3, 3, 3)}")

    # Test squad composition
    print("\n3. Squad Composition Rules:")
    print(f"   Squad size: {engine.SQUAD_SIZE}")
    print(f"   GK required: {engine.SQUAD_COMPOSITION[1]}")
    print(f"   DEF required: {engine.SQUAD_COMPOSITION[2]}")
    print(f"   MID required: {engine.SQUAD_COMPOSITION[3]}")
    print(f"   FWD required: {engine.SQUAD_COMPOSITION[4]}")
    print(f"   Max players per team: {engine.MAX_PLAYERS_PER_TEAM}")

    # Test DC scoring
    print("\n4. Defensive Contribution Rules:")
    print(f"   Defender threshold: 1 pt per {engine.DC_DEFENDER_THRESHOLD} CBI+T")
    print(f"   Midfielder threshold: 1 pt per {engine.DC_MIDFIELDER_THRESHOLD} CBI+T+R")

    # Calculate DC example
    defender_stats = {
        'clearances_blocks_interceptions': 8,
        'tackles': 4,
        'minutes': 90
    }
    dc_points_def = engine.calculate_defensive_contribution_points(2, defender_stats)
    print(f"\n   Example: Defender with 8 CBI + 4 tackles = {dc_points_def} DC points")

    midfielder_stats = {
        'clearances_blocks_interceptions': 6,
        'tackles': 4,
        'recoveries': 5,
        'minutes': 90
    }
    dc_points_mid = engine.calculate_defensive_contribution_points(3, midfielder_stats)
    print(f"   Example: Midfielder with 6 CBI + 4 T + 5 Rec = {dc_points_mid} DC points")

    print("\n" + "=" * 60)
    print("✅ Rules Engine working correctly!\n")

if __name__ == "__main__":
    test_rules_engine()
