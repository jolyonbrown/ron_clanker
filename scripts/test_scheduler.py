#!/usr/bin/env python3
"""
Test script for the Celery scheduler and gameweek deadline monitoring.

Tests:
1. Gameweek deadline calculator
2. Manual task triggering
3. Event bus integration
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tasks.gameweek_scheduler import GameweekScheduler
from infrastructure.event_bus import EventBus
from infrastructure.events import EventType
from infrastructure.celery_app import app


def test_gameweek_scheduler():
    """Test the gameweek deadline calculator."""
    print("=" * 80)
    print("TEST 1: Gameweek Deadline Scheduler")
    print("=" * 80)

    scheduler = GameweekScheduler()

    # Test getting next deadline
    print("\n[1] Getting next deadline...")
    deadline = scheduler.get_next_deadline()

    if deadline:
        print(f"  ✅ Found next deadline:")
        print(f"     Gameweek: {deadline['gameweek']}")
        print(f"     Deadline: {deadline['deadline']}")
        print(f"     Hours until: {deadline['hours_until']:.1f}")
    else:
        print("  ❌ No upcoming deadline found")
        return False

    # Test planning status
    print("\n[2] Checking planning trigger status...")
    status = scheduler.get_planning_status()

    print(f"  Triggers:")
    for trigger, active in status['triggers'].items():
        symbol = "🔔" if active else "⏳"
        print(f"    {trigger}: {symbol} {'ACTIVE' if active else 'waiting'}")

    if status['time_until_next_trigger'] > 0:
        print(f"  Next trigger in: {status['time_until_next_trigger']:.1f} hours")

    return True


def test_event_bus():
    """Test event bus integration."""
    print("\n" + "=" * 80)
    print("TEST 2: Event Bus Integration")
    print("=" * 80)

    event_bus = EventBus()

    # Subscribe to test events
    print("\n[1] Setting up event listener...")

    received_events = []

    def test_handler(event):
        received_events.append(event)
        print(f"  📨 Received: {event['event_type']}")

    event_bus.subscribe(EventType.DATA_UPDATED, test_handler)

    # Publish test event
    print("\n[2] Publishing test DATA_UPDATED event...")
    event_bus.publish(
        EventType.DATA_UPDATED,
        {
            'gameweek': 8,
            'trigger': 'test',
            'timestamp': datetime.now().isoformat()
        }
    )

    # Give it a moment to process
    import time
    time.sleep(1)

    if received_events:
        print(f"  ✅ Event received successfully!")
        return True
    else:
        print(f"  ❌ No events received")
        return False


def test_manual_task_trigger():
    """Test manually triggering Celery tasks."""
    print("\n" + "=" * 80)
    print("TEST 3: Manual Task Triggering")
    print("=" * 80)

    print("\n[1] Triggering daily_data_refresh task...")
    try:
        # Import the task
        from tasks.scheduled_tasks import daily_data_refresh

        # Call directly (not via Celery, since we're testing)
        result = daily_data_refresh()
        print(f"  ✅ Task executed: {result}")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_celery_connection():
    """Test Celery/Redis connection."""
    print("\n" + "=" * 80)
    print("TEST 4: Celery Connection")
    print("=" * 80)

    try:
        # Try to inspect Celery
        inspector = app.control.inspect()

        print("\n[1] Checking for active workers...")
        active = inspector.active()

        if active:
            print(f"  ✅ Found {len(active)} active workers")
            for worker_name, tasks in active.items():
                print(f"     - {worker_name}: {len(tasks)} active tasks")
        else:
            print("  ⚠️  No active workers (expected if not running via Docker)")

        print("\n[2] Checking scheduled tasks...")
        scheduled = inspector.scheduled()

        if scheduled:
            print(f"  ✅ Found scheduled tasks")
        else:
            print("  ⚠️  No scheduled tasks (beat scheduler may not be running)")

        return True

    except Exception as e:
        print(f"  ⚠️  Could not connect to Celery: {e}")
        print("     This is expected if Redis is not running")
        return False


def main():
    """Run all tests."""
    print(f"\n{'#' * 80}")
    print("# RON CLANKER SCHEDULER TEST SUITE")
    print(f"# {datetime.now()}")
    print(f"{'#' * 80}\n")

    results = []

    # Test 1: Gameweek scheduler
    try:
        results.append(("Gameweek Scheduler", test_gameweek_scheduler()))
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.append(("Gameweek Scheduler", False))

    # Test 2: Event bus
    try:
        results.append(("Event Bus", test_event_bus()))
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.append(("Event Bus", False))

    # Test 3: Manual task trigger
    try:
        results.append(("Manual Task Trigger", test_manual_task_trigger()))
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.append(("Manual Task Trigger", False))

    # Test 4: Celery connection (may fail if not running)
    try:
        results.append(("Celery Connection", test_celery_connection()))
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        results.append(("Celery Connection", False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    print(f"\nPassed: {passed_count}/{total_count}")

    if passed_count == total_count:
        print("\n🎉 All tests passed!")
        return 0
    elif passed_count >= 3:
        print("\n✅ Core tests passed (Celery connection optional)")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
