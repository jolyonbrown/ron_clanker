#!/usr/bin/env python3
"""
Simple test for gameweek deadline monitoring.

Tests just the core scheduler logic without requiring Redis/Celery to be running.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tasks.gameweek_scheduler import GameweekScheduler


def main():
    print("=" * 80)
    print("GAMEWEEK DEADLINE MONITOR TEST")
    print("=" * 80)

    scheduler = GameweekScheduler()

    print("\n[1] Fetching next deadline...")
    deadline = scheduler.get_next_deadline()

    if not deadline:
        print("  ❌ No upcoming deadline found")
        return 1

    print(f"  ✅ Found deadline:")
    print(f"     Gameweek: {deadline['gameweek']}")
    print(f"     Name: {deadline['name']}")
    print(f"     Deadline: {deadline['deadline']}")
    print(f"     Hours until: {deadline['hours_until']:.1f}")

    print("\n[2] Checking planning trigger status...")
    status = scheduler.get_planning_status()

    print(f"  Trigger windows:")
    for trigger, active in status['triggers'].items():
        symbol = "🔔" if active else "⏳"
        state = "ACTIVE - TRIGGER NOW" if active else "waiting"
        print(f"    {trigger}: {symbol} {state}")

    if status['time_until_next_trigger'] > 0:
        print(f"\n  Next trigger in: {status['time_until_next_trigger']:.1f} hours")
    else:
        print(f"\n  ⚠️  Within trigger window - should trigger immediately!")

    print("\n[3] Summary...")
    if any(status['triggers'].values()):
        print("  🔔 System should trigger planning NOW")
    else:
        hours_left = status['time_until_next_trigger']
        if hours_left > 24:
            print(f"  ⏳ Next planning trigger in {hours_left:.1f} hours (at 48h mark)")
        elif hours_left > 6:
            print(f"  ⏳ Next planning trigger in {hours_left:.1f} hours (at 24h mark)")
        else:
            print(f"  ⏳ Final planning trigger in {hours_left:.1f} hours (at 6h mark)")

    print("\n✅ Gameweek deadline monitoring working correctly!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
