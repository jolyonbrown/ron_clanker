#!/usr/bin/env python3
"""
Review GW10 Team Decision

Presents Ron's full GW10 decision for user review before posting to Slack.
"""

import asyncio
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.manager_agent_v2 import RonManager
from data.database import Database
import json

async def main():
    db = Database()
    ron = RonManager(database=db)

    print("\n" + "="*80)
    print("GENERATING RON'S GW10 TEAM DECISION")
    print("="*80)
    print("\nThis will take ~15-20 minutes to:")
    print("  1. Generate ML predictions for GW10-13")
    print("  2. Evaluate transfer options")
    print("  3. Optimize formation and captain")
    print("  4. Generate announcement via Claude API")
    print("\nPlease wait...")
    print()

    # Generate the decision
    result = await ron.make_weekly_decision(10)

    # Present for review
    print("\n" + "="*80)
    print("RON'S GW10 DECISION - READY FOR REVIEW")
    print("="*80)

    # Starting XI
    print("\n📋 STARTING XI (4-3-3):")
    starting = [p for p in result['team'] if p['position'] <= 11]
    starting.sort(key=lambda x: x['position'])

    for player in starting:
        pos_type = ['', 'GK', 'DEF', 'MID', 'FWD'][player['element_type']]
        captain = " (C)" if player.get('is_captain') else " (VC)" if player.get('is_vice_captain') else ""
        xp = player.get('xP', 0)
        print(f"  {player['position']:2d}. {player['web_name']:20s} {pos_type:3s} {xp:5.2f}xP{captain}")

    # Bench
    print("\n🪑 BENCH:")
    bench = [p for p in result['team'] if p['position'] > 11]
    bench.sort(key=lambda x: x['position'])

    for player in bench:
        pos_type = ['', 'GK', 'DEF', 'MID', 'FWD'][player['element_type']]
        xp = player.get('xP', 0)
        print(f"  {player['position']:2d}. {player['web_name']:20s} {pos_type:3s} {xp:5.2f}xP")

    # Captain
    captain = next((p for p in result['team'] if p.get('is_captain')), None)
    vice = next((p for p in result['team'] if p.get('is_vice_captain')), None)

    print(f"\n⚽ CAPTAIN: {captain['web_name']} ({captain.get('xP', 0):.2f}xP)")
    print(f"👤 VICE: {vice['web_name']} ({vice.get('xP', 0):.2f}xP)")

    # Transfers
    transfers = result.get('transfers', [])
    if transfers:
        print(f"\n🔄 TRANSFERS ({len(transfers)}):")
        for t in transfers:
            print(f"  OUT: {t['player_out']['web_name']:20s} → IN: {t['player_in']['web_name']:20s}")
            print(f"       {t.get('reasoning', 'No reason provided')}")
    else:
        print("\n🔄 TRANSFERS: None")

    # Chip
    chip = result.get('chip_used')
    print(f"\n💎 CHIP USED: {chip if chip else 'None'}")

    # Announcement
    print("\n" + "="*80)
    print("RON'S ANNOUNCEMENT (for Slack)")
    print("="*80)
    print()
    print(result['announcement'])
    print()
    print("="*80)

    # Expected points
    total_xp = sum(p.get('xP', 0) for p in result['team'] if p['position'] <= 11)
    print(f"\n📊 TOTAL EXPECTED POINTS: {total_xp:.2f}")

    # Save for manual posting
    review_data = {
        'gameweek': 10,
        'formation': result.get('formation', '4-3-3'),
        'captain': captain['web_name'] if captain else 'Unknown',
        'vice': vice['web_name'] if vice else 'Unknown',
        'transfers': len(transfers),
        'chip_used': chip,
        'total_xp': round(total_xp, 2),
        'announcement': result['announcement']
    }

    with open('data/ron_gw10_review.json', 'w') as f:
        json.dump(review_data, f, indent=2)

    print("\n✅ Decision saved to: data/ron_gw10_review.json")
    print("\nTo post to Slack, run:")
    print("  venv/bin/python scripts/post_to_slack.py data/ron_gw10_review.json")
    print()
    print("="*80)

if __name__ == '__main__':
    asyncio.run(main())
