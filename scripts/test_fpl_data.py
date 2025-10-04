#!/usr/bin/env python3
"""
Test FPL data access and explore what's available.

This script tests direct access to the FPL API to understand:
1. What data is available
2. Whether defensive stats (tackles, interceptions, etc.) are accessible
3. Current gameweek and player data structure
"""

import requests
import json
from pprint import pprint

FPL_API_BASE = "https://fantasy.premierleague.com/api"

def fetch_bootstrap_data():
    """Fetch the main bootstrap-static data."""
    print("=" * 60)
    print("FETCHING BOOTSTRAP DATA")
    print("=" * 60)

    url = f"{FPL_API_BASE}/bootstrap-static/"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"ERROR: Status code {response.status_code}")
        return None

    data = response.json()

    print(f"\n✅ Successfully fetched bootstrap data")
    print(f"   Players: {len(data['elements'])}")
    print(f"   Teams: {len(data['teams'])}")
    print(f"   Gameweeks: {len(data['events'])}")

    return data


def analyze_current_gameweek(data):
    """Find and display current gameweek info."""
    print("\n" + "=" * 60)
    print("CURRENT GAMEWEEK INFO")
    print("=" * 60)

    current_gw = None
    for gw in data['events']:
        if gw['is_current']:
            current_gw = gw
            break

    if current_gw:
        print(f"\nCurrent Gameweek: {current_gw['id']}")
        print(f"Name: {current_gw['name']}")
        print(f"Deadline: {current_gw['deadline_time']}")
        print(f"Finished: {current_gw['finished']}")
    else:
        print("\nNo current gameweek found (season may not have started)")

    return current_gw


def explore_player_structure(data):
    """Explore what data is available for players."""
    print("\n" + "=" * 60)
    print("PLAYER DATA STRUCTURE")
    print("=" * 60)

    # Get first player as example
    example_player = data['elements'][0]

    print(f"\nExample player: {example_player['web_name']}")
    print(f"Position: {example_player['element_type']} (1=GK, 2=DEF, 3=MID, 4=FWD)")
    print(f"Team: {example_player['team']}")
    print(f"Price: £{example_player['now_cost']/10}m")
    print(f"Total Points: {example_player['total_points']}")
    print(f"\nAvailable fields:")

    # Print all available fields
    for key in sorted(example_player.keys()):
        value = example_player[key]
        if isinstance(value, (int, float, str, bool)) and value != "":
            print(f"  {key}: {value}")

    return example_player


def check_defensive_stats(data):
    """Check if defensive contribution stats are available."""
    print("\n" + "=" * 60)
    print("CHECKING FOR DEFENSIVE STATS")
    print("=" * 60)

    example_player = data['elements'][0]

    # Look for defensive stat fields
    defensive_fields = [
        'tackles', 'interceptions', 'clearances', 'blocked_shots',
        'clearances_blocks_interceptions', 'recoveries'
    ]

    found_fields = []
    for field in defensive_fields:
        if field in example_player:
            found_fields.append(field)
            print(f"  ✅ {field}: {example_player[field]}")
        else:
            print(f"  ❌ {field}: NOT FOUND")

    if not found_fields:
        print("\n⚠️  WARNING: No defensive stats found in bootstrap data")
        print("   These may be available in detailed player data...")

    return found_fields


def fetch_player_detail(player_id):
    """Fetch detailed data for a specific player."""
    print("\n" + "=" * 60)
    print(f"FETCHING DETAILED DATA FOR PLAYER {player_id}")
    print("=" * 60)

    url = f"{FPL_API_BASE}/element-summary/{player_id}/"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"ERROR: Status code {response.status_code}")
        return None

    data = response.json()

    print(f"\n✅ Successfully fetched player detail")
    print(f"   History entries: {len(data.get('history', []))}")
    print(f"   Fixture history: {len(data.get('history_past', []))}")

    # Check first history entry for defensive stats
    if data.get('history'):
        print("\n   First gameweek stats:")
        first_gw = data['history'][0]
        for key in sorted(first_gw.keys()):
            print(f"     {key}: {first_gw[key]}")

    return data


def find_top_dc_candidates(data):
    """Find players likely earning defensive contribution points."""
    print("\n" + "=" * 60)
    print("TOP DC CANDIDATES (Based on Available Data)")
    print("=" * 60)

    # Filter to defenders and midfielders
    defenders = [p for p in data['elements'] if p['element_type'] == 2]
    midfielders = [p for p in data['elements'] if p['element_type'] == 3]

    # Sort by total points (proxy for now)
    defenders.sort(key=lambda x: x['total_points'], reverse=True)
    midfielders.sort(key=lambda x: x['total_points'], reverse=True)

    print("\nTop 10 Defenders (by total points):")
    for i, player in enumerate(defenders[:10], 1):
        print(f"  {i}. {player['web_name']:20} | £{player['now_cost']/10:3.1f}m | {player['total_points']:3} pts | Form: {player['form']}")

    print("\nTop 10 Midfielders (by total points):")
    for i, player in enumerate(midfielders[:10], 1):
        print(f"  {i}. {player['web_name']:20} | £{player['now_cost']/10:3.1f}m | {player['total_points']:3} pts | Form: {player['form']}")


def main():
    """Main test function."""
    print("\n🎯 RON CLANKER - FPL DATA TEST")
    print("Testing FPL API access and available data\n")

    # 1. Fetch main data
    data = fetch_bootstrap_data()
    if not data:
        print("\n❌ Failed to fetch data. Exiting.")
        return

    # 2. Check current gameweek
    current_gw = analyze_current_gameweek(data)

    # 3. Explore player data structure
    example_player = explore_player_structure(data)

    # 4. Check for defensive stats
    defensive_fields = check_defensive_stats(data)

    # 5. Fetch detailed player data to see if defensive stats are there
    if data['elements']:
        # Get first defender
        first_defender = next(p for p in data['elements'] if p['element_type'] == 2)
        player_detail = fetch_player_detail(first_defender['id'])

    # 6. Find top candidates
    find_top_dc_candidates(data)

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\n✅ FPL API is accessible")
    print(f"✅ Found {len(data['elements'])} players")

    if defensive_fields:
        print(f"✅ Defensive stats available: {', '.join(defensive_fields)}")
    else:
        print("⚠️  Need to check detailed player endpoints for defensive stats")

    print("\nNext steps:")
    print("1. Verify defensive stats are available in player history")
    print("2. Build analysis script to calculate DC consistency")
    print("3. Select GW8 squad based on proven DC performers")


if __name__ == "__main__":
    main()
