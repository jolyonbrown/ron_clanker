#!/usr/bin/env python3
"""
Quick exploration of FPL player status fields
"""

import json
import requests

FPL_BASE_URL = "https://fantasy.premierleague.com/api"

def get_bootstrap_data():
    """Fetch bootstrap-static data from FPL API"""
    print("Fetching FPL data...")
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()

def main():
    data = get_bootstrap_data()

    print("=" * 80)
    print("FPL PLAYER STATUS FIELDS EXPLORATION")
    print("=" * 80)

    # Get one player to see all fields
    if 'elements' in data and len(data['elements']) > 0:
        player = data['elements'][0]

        print("\n📋 ALL PLAYER FIELDS:")
        print("-" * 80)
        for key in sorted(player.keys()):
            print(f"  {key:30s} = {player[key]}")

    print("\n" + "=" * 80)
    print("AVAILABILITY/STATUS RELATED FIELDS")
    print("=" * 80)

    # Look for status-related fields
    status_fields = [
        'status', 'chance_of_playing_next_round', 'chance_of_playing_this_round',
        'news', 'news_added', 'in_dreamteam', 'dreamteam_count',
        'unavailable', 'available'
    ]

    print("\nSearching for flagged/unavailable players...")
    flagged_players = []

    for player in data['elements'][:100]:  # Check first 100
        status_info = {
            'name': player['web_name'],
            'team': player['team'],
            'status': player.get('status'),
            'news': player.get('news', ''),
            'chance_this_round': player.get('chance_of_playing_this_round'),
            'chance_next_round': player.get('chance_of_playing_next_round'),
        }

        # Flag if any status indicator
        if (status_info['status'] != 'a' or
            status_info['news'] or
            status_info['chance_this_round'] is not None):
            flagged_players.append(status_info)

    if flagged_players:
        print(f"\n🚨 Found {len(flagged_players)} players with status indicators:\n")
        for p in flagged_players[:10]:  # Show first 10
            print(f"  {p['name']:20s}")
            print(f"    Status: {p['status']}")
            print(f"    News: {p['news']}")
            print(f"    Chance this round: {p['chance_this_round']}")
            print(f"    Chance next round: {p['chance_next_round']}")
            print()
    else:
        print("\n✅ No flagged players found in first 100")

    print("\n" + "=" * 80)
    print("STATUS CODE LEGEND (if we find examples)")
    print("=" * 80)
    print("  a = available")
    print("  d = doubtful")
    print("  i = injured")
    print("  s = suspended")
    print("  u = unavailable")
    print("  n = not in squad")

if __name__ == '__main__':
    main()
