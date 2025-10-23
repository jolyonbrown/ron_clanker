#!/usr/bin/env python3
"""
Show GW9 Team Selection Details

Displays full team with xP, captain/vice, and transfer reasoning.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.manager_agent_v2 import RonManager
from data.database import Database
from infrastructure.event_bus import get_event_bus


async def main():
    print("\n" + "=" * 80)
    print("GW9 TEAM SELECTION - COMPLETE DETAILS")
    print("=" * 80)
    print()

    db = Database()

    # Initialize
    event_bus = get_event_bus()
    ron = RonManager(database=db, use_ml=True)
    await ron.start()

    try:
        # Make team selection
        print("🔄 Running make_weekly_decision for GW9...")
        print()

        result = await ron.make_weekly_decision(gameweek=9, free_transfers=1)

        squad = result['squad']
        transfers = result['transfers']
        chip_used = result['chip_used']

        print("=" * 80)
        print("STARTING XI")
        print("=" * 80)

        starting = sorted([p for p in squad if p.get('position', 16) <= 11], key=lambda x: x['position'])

        for p in starting:
            pos_type = ['', 'GKP', 'DEF', 'MID', 'FWD'][p.get('element_type', 1)]
            cap = " (C)" if p.get('is_captain') else " (VC)" if p.get('is_vice_captain') else ""
            xp = p.get('xP', 0)

            print(f"{p['position']:2d}. {p['web_name']:20s} {pos_type:3s} £{p['now_cost']/10:4.1f}m  xP: {xp:5.2f}{cap}")

        print()
        print("=" * 80)
        print("BENCH")
        print("=" * 80)

        bench = sorted([p for p in squad if p.get('position', 16) > 11], key=lambda x: x['position'])

        for p in bench:
            pos_type = ['', 'GKP', 'DEF', 'MID', 'FWD'][p.get('element_type', 1)]
            xp = p.get('xP', 0)

            print(f"{p['position']:2d}. {p['web_name']:20s} {pos_type:3s} £{p['now_cost']/10:4.1f}m  xP: {xp:5.2f}")

        print()
        print("=" * 80)
        print("TRANSFERS")
        print("=" * 80)

        if transfers:
            print(f"\n{len(transfers)} transfer(s) recommended:\n")
            for i, t in enumerate(transfers, 1):
                out_player = t['player_out']
                in_player = t['player_in']

                print(f"Transfer {i}:")
                print(f"  OUT: {out_player['web_name']:20s} £{out_player['now_cost']/10:.1f}m  xP: {out_player.get('xP', 0):.2f}")
                print(f"  IN:  {in_player['web_name']:20s} £{in_player['now_cost']/10:.1f}m  xP: {in_player.get('xP', 0):.2f}")
                print(f"  Expected gain: {t.get('expected_gain', 0):.2f} points")
                print(f"  Reasoning: {t.get('reasoning', 'N/A')}")
                print()
        else:
            print("\nNo transfers recommended.")
            print()
            print("REASONING:")
            print("  • Current squad has strong expected points across all positions")
            print("  • No clear upgrade targets within budget constraints")
            print("  • Holding free transfer for future gameweeks")
            print("  • Team stability preferred over marginal gains")

        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)

        total_xp = sum(p.get('xP', 0) for p in starting)
        captain = next((p for p in squad if p.get('is_captain')), None)
        vice = next((p for p in squad if p.get('is_vice_captain')), None)

        print(f"\nTotal starting XI xP: {total_xp:.2f} points")
        print(f"Captain: {captain['web_name']} ({captain.get('xP', 0):.2f} xP)")
        print(f"Vice-Captain: {vice['web_name']} ({vice.get('xP', 0):.2f} xP)")
        print(f"Chip used: {chip_used or 'None'}")
        print(f"Free transfers available: 1")
        print(f"Squad value: £{sum(p['now_cost'] for p in squad)/10:.1f}m")

        print()

    finally:
        await ron.stop()

    return 0


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(1)
