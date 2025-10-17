"""
Scheduled Celery tasks for autonomous FPL management.

These tasks are triggered by Celery Beat according to the schedule
defined in infrastructure/celery_app.py. They publish events to the
event bus, which specialist agents listen to and react to.

Ron Clanker operates autonomously through these scheduled triggers.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.celery_app import app
from infrastructure.event_bus import EventBus
from infrastructure.events import Event, EventType, EventPriority
from tasks.gameweek_scheduler import GameweekScheduler
from agents.data_collector import DataCollector
import asyncio


def publish_event_sync(event: Event):
    """
    Helper to publish events synchronously from Celery tasks.

    Args:
        event: Event to publish
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        event_bus = EventBus()
        loop.run_until_complete(event_bus.connect())
        loop.run_until_complete(event_bus.publish(event))
        loop.run_until_complete(event_bus.disconnect())
    finally:
        loop.close()


@app.task(name='tasks.scheduled_tasks.daily_data_refresh')
def daily_data_refresh():
    """
    Daily data refresh at 6:00 AM.

    Fetches latest FPL data and publishes DATA_UPDATED event.
    All analyst agents subscribe to this and update their analyses.
    """
    print(f"[{datetime.now()}] Running daily data refresh")

    try:
        # Initialize components
        data_collector = DataCollector()
        event_bus = EventBus()

        # Fetch latest data using async
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bootstrap = loop.run_until_complete(data_collector.fetch_bootstrap_data())
            current_gw = data_collector.get_current_gameweek(bootstrap)
            gameweek = current_gw['id'] if current_gw else None
        finally:
            loop.run_until_complete(data_collector.close())
            loop.close()

        print(f"  Current gameweek: {gameweek}")
        print(f"  Total players: {len(bootstrap.get('elements', []))}")

        # Publish DATA_UPDATED event
        # All specialist agents listen to this
        event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'gameweek': gameweek,
                'timestamp': datetime.now().isoformat(),
                'trigger': 'scheduled_daily_refresh'
            },
            source='scheduler'
        )

        publish_event_sync(event)
        print(f"  ✅ Published DATA_UPDATED event (GW{gameweek})")
        return {'status': 'success', 'gameweek': gameweek}

    except Exception as e:
        print(f"  ❌ Error in daily_data_refresh: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='tasks.scheduled_tasks.check_gameweek_deadlines')
def check_gameweek_deadlines():
    """
    Check for upcoming gameweek deadlines every 6 hours.

    Triggers planning events at:
    - 48 hours before deadline (early planning)
    - 24 hours before deadline (final planning)
    - 6 hours before deadline (last-minute checks)
    """
    print(f"[{datetime.now()}] Checking gameweek deadlines")

    try:
        scheduler = GameweekScheduler()
        event_bus = EventBus()

        status = scheduler.get_planning_status()

        if not status['next_deadline']:
            print("  No upcoming gameweek deadline found")
            return {'status': 'no_deadline'}

        deadline = status['next_deadline']
        triggers = status['triggers']

        print(f"  GW{deadline['gameweek']} deadline: {deadline['deadline']}")
        print(f"  Hours until: {deadline['hours_until']:.1f}")

        # Check each trigger point
        triggered = []

        if triggers['48h']:
            print("  🔔 48-hour trigger activated!")
            event_bus.publish(
                EventType.GAMEWEEK_PLANNING,
                {
                    'gameweek': deadline['gameweek'],
                    'trigger_point': '48h',
                    'deadline': deadline['deadline_str'],
                    'hours_until': deadline['hours_until'],
                    'timestamp': datetime.now().isoformat()
                }
            )
            triggered.append('48h')

        if triggers['24h']:
            print("  🔔 24-hour trigger activated!")
            event_bus.publish(
                EventType.GAMEWEEK_PLANNING,
                {
                    'gameweek': deadline['gameweek'],
                    'trigger_point': '24h',
                    'deadline': deadline['deadline_str'],
                    'hours_until': deadline['hours_until'],
                    'timestamp': datetime.now().isoformat()
                }
            )
            triggered.append('24h')

        if triggers['6h']:
            print("  🔔 6-hour trigger activated!")
            event_bus.publish(
                EventType.GAMEWEEK_PLANNING,
                {
                    'gameweek': deadline['gameweek'],
                    'trigger_point': '6h',
                    'deadline': deadline['deadline_str'],
                    'hours_until': deadline['hours_until'],
                    'timestamp': datetime.now().isoformat()
                }
            )
            triggered.append('6h')

        if triggered:
            print(f"  ✅ Triggered: {', '.join(triggered)}")
            return {
                'status': 'triggered',
                'gameweek': deadline['gameweek'],
                'triggers': triggered
            }
        else:
            print(f"  ⏳ No triggers yet. Next trigger in {status['time_until_next_trigger']:.1f}h")
            return {
                'status': 'waiting',
                'gameweek': deadline['gameweek'],
                'hours_until_next': status['time_until_next_trigger']
            }

    except Exception as e:
        print(f"  ❌ Error in check_gameweek_deadlines: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='tasks.scheduled_tasks.pre_price_change_analysis')
def pre_price_change_analysis():
    """
    Pre-price change analysis at 2:00 AM.

    Runs before FPL price changes (which happen at ~2:30 AM).
    Analyzes net transfer trends to predict likely price changes.
    """
    print(f"[{datetime.now()}] Running pre-price change analysis")

    try:
        event_bus = EventBus()
        data_collector = DataCollector()

        # Get current gameweek
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bootstrap = loop.run_until_complete(data_collector.fetch_bootstrap_data())
            current_gw = data_collector.get_current_gameweek(bootstrap)
            gameweek = current_gw['id'] if current_gw else None
        finally:
            loop.run_until_complete(data_collector.close())
            loop.close()

        # TODO: Implement price change prediction logic
        # For now, just publish event for future agent to handle

        event_bus.publish(
            EventType.PRICE_CHECK,
            {
                'gameweek': gameweek,
                'check_type': 'pre_change',
                'timestamp': datetime.now().isoformat()
            }
        )

        print(f"  ✅ Published PRICE_CHECK event (pre-change)")
        return {'status': 'success', 'type': 'pre_change'}

    except Exception as e:
        print(f"  ❌ Error in pre_price_change_analysis: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='tasks.scheduled_tasks.post_price_change_analysis')
def post_price_change_analysis():
    """
    Post-price change analysis at 3:00 AM.

    Runs after FPL price changes complete.
    Analyzes actual price changes and updates team value.
    """
    print(f"[{datetime.now()}] Running post-price change analysis")

    try:
        event_bus = EventBus()
        data_collector = DataCollector()

        # Fetch updated data after price changes
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bootstrap = loop.run_until_complete(data_collector.fetch_bootstrap_data(force_refresh=True))
            current_gw = data_collector.get_current_gameweek(bootstrap)
            gameweek = current_gw['id'] if current_gw else None
        finally:
            loop.run_until_complete(data_collector.close())
            loop.close()

        # Publish DATA_UPDATED event with price change flag
        event_bus.publish(
            EventType.DATA_UPDATED,
            {
                'gameweek': gameweek,
                'trigger': 'post_price_change',
                'timestamp': datetime.now().isoformat()
            }
        )

        event_bus.publish(
            EventType.PRICE_CHECK,
            {
                'gameweek': gameweek,
                'check_type': 'post_change',
                'timestamp': datetime.now().isoformat()
            }
        )

        print(f"  ✅ Published DATA_UPDATED and PRICE_CHECK events (post-change)")
        return {'status': 'success', 'type': 'post_change'}

    except Exception as e:
        print(f"  ❌ Error in post_price_change_analysis: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='tasks.scheduled_tasks.post_gameweek_review')
def post_gameweek_review():
    """
    Post-gameweek review on Mondays at 10:00 AM.

    Analyzes completed gameweek results:
    - Compare predictions vs actual points
    - Review captain choice effectiveness
    - Identify what worked / what didn't
    - Feed learning back to agents
    """
    print(f"[{datetime.now()}] Running post-gameweek review")

    try:
        event_bus = EventBus()
        data_collector = DataCollector()

        # Get just-completed gameweek
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            bootstrap = loop.run_until_complete(data_collector.fetch_bootstrap_data())
            current_gw_data = data_collector.get_current_gameweek(bootstrap)
            current_gw = current_gw_data['id'] if current_gw_data else None
        finally:
            loop.run_until_complete(data_collector.close())
            loop.close()

        # Assuming review happens after GW completes
        completed_gw = current_gw - 1 if current_gw and current_gw > 1 else current_gw

        print(f"  Reviewing GW{completed_gw} results")

        # TODO: Implement detailed review logic
        # For now, publish event for learning agent to handle

        event_bus.publish(
            EventType.GAMEWEEK_COMPLETE,
            {
                'gameweek': completed_gw,
                'timestamp': datetime.now().isoformat(),
                'trigger': 'scheduled_weekly_review'
            }
        )

        print(f"  ✅ Published GAMEWEEK_COMPLETE event (GW{completed_gw})")
        return {'status': 'success', 'gameweek': completed_gw}

    except Exception as e:
        print(f"  ❌ Error in post_gameweek_review: {e}")
        return {'status': 'error', 'message': str(e)}


# Manual trigger tasks (can be called directly for testing)

@app.task(name='tasks.scheduled_tasks.trigger_team_selection')
def trigger_team_selection(gameweek=None):
    """
    Manually trigger team selection for a specific gameweek.

    Useful for testing or emergency team changes.
    """
    print(f"[{datetime.now()}] Manually triggering team selection")

    try:
        event_bus = EventBus()
        data_collector = DataCollector()

        if gameweek is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                bootstrap = loop.run_until_complete(data_collector.fetch_bootstrap_data())
                current_gw = data_collector.get_current_gameweek(bootstrap)
                gameweek = current_gw['id'] if current_gw else None
            finally:
                loop.run_until_complete(data_collector.close())
                loop.close()

        # First ensure we have latest data
        event_bus.publish(
            EventType.DATA_UPDATED,
            {
                'gameweek': gameweek,
                'trigger': 'manual_selection',
                'timestamp': datetime.now().isoformat()
            }
        )

        # Then trigger planning
        event_bus.publish(
            EventType.GAMEWEEK_PLANNING,
            {
                'gameweek': gameweek,
                'trigger_point': 'manual',
                'timestamp': datetime.now().isoformat()
            }
        )

        print(f"  ✅ Triggered team selection for GW{gameweek}")
        return {'status': 'success', 'gameweek': gameweek}

    except Exception as e:
        print(f"  ❌ Error in trigger_team_selection: {e}")
        return {'status': 'error', 'message': str(e)}
