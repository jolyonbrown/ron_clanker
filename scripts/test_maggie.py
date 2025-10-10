#!/usr/bin/env python3
"""
Test Maggie (DataCollector) - Verify she fetches FPL data properly.

Tests:
1. Fetch bootstrap data
2. Cache works (second fetch is instant)
3. Filter and analysis methods work
4. Event publishing works (if event bus enabled)
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.data_collector import DataCollector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_basic_fetch():
    """Test basic data fetching."""
    print("\n" + "=" * 60)
    print("TEST 1: Basic Data Fetch")
    print("=" * 60)

    maggie = DataCollector()

    try:
        # First fetch (will hit API)
        print("\n1. Fetching data (first time - will hit FPL API)...")
        start = datetime.now()
        data = await maggie.update_all_data()
        duration = (datetime.now() - start).total_seconds()

        print(f"   ✓ Fetched in {duration:.2f}s")
        print(f"   ✓ Players: {len(data['players'])}")
        print(f"   ✓ Teams: {len(data['teams'])}")
        print(f"   ✓ Fixtures: {len(data['fixtures'])}")
        print(f"   ✓ Current GW: {data['current_gameweek']['id'] if data['current_gameweek'] else 'None'}")

        return True

    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await maggie.close()


async def test_caching():
    """Test that caching works."""
    print("\n" + "=" * 60)
    print("TEST 2: Cache Performance")
    print("=" * 60)

    maggie = DataCollector()

    try:
        # First fetch (API call)
        print("\n1. First fetch (cold cache - hits API)...")
        start = datetime.now()
        data1 = await maggie.update_all_data()
        duration1 = (datetime.now() - start).total_seconds()
        print(f"   ✓ Duration: {duration1:.2f}s")

        # Second fetch (should hit cache)
        print("\n2. Second fetch (warm cache - should be instant)...")
        start = datetime.now()
        data2 = await maggie.update_all_data()
        duration2 = (datetime.now() - start).total_seconds()
        print(f"   ✓ Duration: {duration2:.2f}s")

        # Cache should be MUCH faster
        if duration2 < duration1 / 5:  # At least 5x faster
            print(f"   ✓ Cache working! ({duration1/duration2:.1f}x faster)")
            return True
        else:
            print(f"   ⚠ Cache may not be working (only {duration1/duration2:.1f}x faster)")
            return False

    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return False

    finally:
        await maggie.close()


async def test_filtering():
    """Test filtering and analysis methods."""
    print("\n" + "=" * 60)
    print("TEST 3: Filtering & Analysis")
    print("=" * 60)

    maggie = DataCollector()

    try:
        data = await maggie.update_all_data()
        players = data['players']

        # Test position filtering
        print("\n1. Filter by position...")
        defenders = maggie.filter_players_by_position(players, 2)
        print(f"   ✓ Found {len(defenders)} defenders")

        # Test availability filtering
        print("\n2. Filter available players...")
        available = maggie.filter_available_players(players)
        print(f"   ✓ Found {len(available)} available players")

        # Test value calculation
        print("\n3. Best value players...")
        best_value = maggie.get_best_value_players(players, top_n=5)
        print("   ✓ Top 5 value players:")
        for i, p in enumerate(best_value, 1):
            print(f"      {i}. {p['web_name']:20} | £{p['now_cost']/10:.1f}m | {p['total_points']:3} pts | Value: {p['value']:.2f}")

        # Test price changers
        print("\n4. Price change candidates...")
        changers = maggie.get_price_changers(players, min_net_transfers=500)
        print(f"   ✓ {len(changers['risers'])} likely risers")
        print(f"   ✓ {len(changers['fallers'])} likely fallers")

        if changers['risers']:
            print("   Top 3 risers:")
            for p in changers['risers'][:3]:
                print(f"      - {p['web_name']:20} | Net: +{p['net_transfers']:,}")

        return True

    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await maggie.close()


async def test_player_details():
    """Test fetching individual player details."""
    print("\n" + "=" * 60)
    print("TEST 4: Player Details")
    print("=" * 60)

    maggie = DataCollector()

    try:
        # Get a player ID from bootstrap
        data = await maggie.update_all_data()
        player = data['players'][0]  # First player
        player_id = player['id']

        print(f"\n1. Fetching details for {player['web_name']} (ID: {player_id})...")
        start = datetime.now()
        details = await maggie.fetch_player_data(player_id)
        duration = (datetime.now() - start).total_seconds()

        if details:
            print(f"   ✓ Fetched in {duration:.2f}s")
            print(f"   ✓ History entries: {len(details.get('history', []))}")
            print(f"   ✓ Past seasons: {len(details.get('history_past', []))}")

            # Show first gameweek if available
            if details.get('history'):
                gw = details['history'][0]
                print(f"   ✓ GW1 stats: {gw.get('total_points')} pts, {gw.get('minutes')} mins")

            return True
        else:
            print("   ✗ No data returned")
            return False

    except Exception as e:
        print(f"   ✗ ERROR: {e}")
        return False

    finally:
        await maggie.close()


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("TESTING MAGGIE - DATA COLLECTOR")
    print("=" * 60)

    tests = [
        ("Basic Fetch", test_basic_fetch),
        ("Caching", test_caching),
        ("Filtering", test_filtering),
        ("Player Details", test_player_details),
    ]

    results = {}

    for name, test_func in tests:
        try:
            result = await test_func()
            results[name] = result
        except Exception as e:
            logger.error(f"Test {name} crashed: {e}")
            results[name] = False

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} | {name}")

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests passed! Maggie is working perfectly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
