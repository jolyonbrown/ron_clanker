#!/usr/bin/env python3
"""
Test the decision logger by publishing sample events.

Run this in one terminal, and decision_logger.py in another to see it work.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.event_bus import EventBus
from infrastructure.events import Event, EventType, EventPriority


async def publish_test_events():
    """Publish a series of test events to demonstrate the logger."""

    event_bus = EventBus()
    await event_bus.connect()

    print("Publishing test events...")
    print("(Watch the decision_logger output)")
    print("")

    # 1. Data refresh
    print("1. Publishing DATA_UPDATED event...")
    await event_bus.publish(Event(
        event_type=EventType.DATA_UPDATED,
        payload={
            'gameweek': 8,
            'timestamp': datetime.now().isoformat(),
            'trigger': 'test'
        },
        source='test'
    ))
    await asyncio.sleep(1)

    # 2. Gameweek planning trigger
    print("2. Publishing GAMEWEEK_PLANNING event...")
    await event_bus.publish(Event(
        event_type=EventType.GAMEWEEK_PLANNING,
        payload={
            'gameweek': 8,
            'trigger_point': '24h',
            'hours_until': 23.5,
            'timestamp': datetime.now().isoformat()
        },
        source='test',
        priority=EventPriority.HIGH
    ))
    await asyncio.sleep(1)

    # 3. DC Analysis
    print("3. Publishing DC_ANALYSIS_COMPLETED event...")
    await event_bus.publish(Event(
        event_type=EventType.DC_ANALYSIS_COMPLETED,
        payload={
            'gameweek': 8,
            'top_dc_players': [
                {'name': 'Gabriel', 'dc_points': 14},
                {'name': 'Caicedo', 'dc_points': 13},
                {'name': 'Senesi', 'dc_points': 12}
            ],
            'timestamp': datetime.now().isoformat()
        },
        source='digger'
    ))
    await asyncio.sleep(1)

    # 4. Value rankings
    print("4. Publishing VALUE_RANKINGS_COMPLETED event...")
    await event_bus.publish(Event(
        event_type=EventType.VALUE_RANKINGS_COMPLETED,
        payload={
            'gameweek': 8,
            'top_value_picks': [
                {'name': 'Semenyo', 'position': 'MID', 'value_score': 49.8, 'price': 79},
                {'name': 'Haaland', 'position': 'FWD', 'value_score': 45.2, 'price': 145},
                {'name': 'Senesi', 'position': 'DEF', 'value_score': 44.9, 'price': 50},
                {'name': 'Caicedo', 'position': 'MID', 'value_score': 43.0, 'price': 58},
                {'name': 'Gabriel', 'position': 'DEF', 'value_score': 42.2, 'price': 63}
            ],
            'timestamp': datetime.now().isoformat()
        },
        source='jimmy'
    ))
    await asyncio.sleep(1)

    # 5. Team selection - THE BIG ONE
    print("5. Publishing TEAM_SELECTED event...")
    await event_bus.publish(Event(
        event_type=EventType.TEAM_SELECTED,
        payload={
            'gameweek': 8,
            'total_cost': 963,
            'squad': [
                {'name': 'Roefs', 'position_id': 1, 'price': 46, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Senesi', 'position_id': 2, 'price': 50, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Gabriel', 'position_id': 2, 'price': 63, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Guéhi', 'position_id': 2, 'price': 49, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Semenyo', 'position_id': 3, 'price': 79, 'is_captain': True, 'is_vice_captain': False},
                {'name': 'Caicedo', 'position_id': 3, 'price': 58, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Sarr', 'position_id': 3, 'price': 65, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Cullen', 'position_id': 3, 'price': 50, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Ndiaye', 'position_id': 3, 'price': 65, 'is_captain': False, 'is_vice_captain': False},
                {'name': 'Haaland', 'position_id': 4, 'price': 145, 'is_captain': False, 'is_vice_captain': True},
                {'name': 'Thiago', 'position_id': 4, 'price': 61, 'is_captain': False, 'is_vice_captain': False},
            ],
            'captain': {'name': 'Semenyo'},
            'vice_captain': {'name': 'Haaland'},
            'reasoning': "Building a foundation with DC specialists. Gabriel and Caicedo earn 2pts/week from defensive work before we even count clean sheets. That's the edge.",
            'timestamp': datetime.now().isoformat()
        },
        source='ron',
        priority=EventPriority.HIGH
    ))
    await asyncio.sleep(2)

    # 6. Price change
    print("6. Publishing PRICE_CHANGE_DETECTED event...")
    await event_bus.publish(Event(
        event_type=EventType.PRICE_CHANGE_DETECTED,
        payload={
            'player_name': 'Haaland',
            'old_price': 145,
            'new_price': 146,
            'change_type': 'rise',
            'timestamp': datetime.now().isoformat()
        },
        source='price_monitor'
    ))
    await asyncio.sleep(1)

    print("\n✅ All test events published!")
    print("Check the decision logger output to see them logged.\n")

    await event_bus.disconnect()


async def main():
    try:
        await publish_test_events()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
