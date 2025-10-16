#!/usr/bin/env python3
"""
Quick test script to verify Data Collector (Maggie) can fetch FPL data.
"""

import asyncio
import sys
from agents.data_collector import DataCollector


async def test_data_collector():
    """Test basic data fetching."""
    print("🔍 Testing Data Collector (Maggie)...")
    print("=" * 60)

    # Initialize without Redis for simple test
    collector = DataCollector()

    try:
        # Fetch bootstrap data
        print("\n1. Fetching bootstrap data (players, teams, gameweeks)...")
        data = await collector.update_all_data()

        if not data:
            print("❌ Failed to fetch data")
            return False

        # Display summary
        print(f"✅ Successfully fetched FPL data:")
        print(f"   • Players: {len(data['players'])}")
        print(f"   • Teams: {len(data['teams'])}")
        print(f"   • Fixtures: {len(data['fixtures'])}")

        current_gw = data.get('current_gameweek')
        if current_gw:
            print(f"   • Current Gameweek: {current_gw['id']} ({current_gw['name']})")
            print(f"   • Deadline: {current_gw.get('deadline_time', 'N/A')}")

        # Test player filtering
        print("\n2. Testing player filtering...")
        players = data['players']

        defenders = collector.filter_players_by_position(players, 2)
        midfielders = collector.filter_players_by_position(players, 3)

        print(f"   • Defenders: {len(defenders)}")
        print(f"   • Midfielders: {len(midfielders)}")

        # Test value calculation
        print("\n3. Finding best value defenders...")
        best_value_defs = collector.get_best_value_players(players, position=2, top_n=5)

        for i, player in enumerate(best_value_defs, 1):
            name = player['web_name']
            cost = player['now_cost'] / 10
            points = player['total_points']
            value = player['value']
            print(f"   {i}. {name} - £{cost}m, {points} pts, {value:.2f} pts/£m")

        print("\n" + "=" * 60)
        print("✅ All tests passed! Maggie is working correctly.")
        return True

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await collector.close()


if __name__ == "__main__":
    success = asyncio.run(test_data_collector())
    sys.exit(0 if success else 1)
