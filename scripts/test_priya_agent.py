#!/usr/bin/env python3
"""
Test script for Priya (Fixture Analyst) agent.
"""

import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.fixture_analyst import FixtureAnalyst
from agents.data_collector import DataCollector
from infrastructure.event_bus import get_event_bus
from infrastructure.events import Event, EventType


async def test_priya_agent():
    """Test Priya agent with event bus."""
    print("=" * 80)
    print("PRIYA AGENT INTEGRATION TEST")
    print("=" * 80)

    event_bus = get_event_bus()
    priya = None
    analysis_received = False
    analysis_result = None

    async def handle_fixture_analysis(event: Event):
        """Handler for FIXTURE_ANALYSIS_COMPLETED events."""
        nonlocal analysis_received, analysis_result
        print("\n✅ FIXTURE_ANALYSIS_COMPLETED event received!")
        analysis_received = True
        analysis_result = event.payload

    try:
        print("\n[1/4] Connecting to event bus...")
        await event_bus.connect()
        print("✅ Connected")

        print("\n[2/4] Starting Priya agent...")
        await event_bus.subscribe(EventType.FIXTURE_ANALYSIS_COMPLETED, handle_fixture_analysis)
        await event_bus.start_listening()

        priya = FixtureAnalyst()
        await priya.start()
        print("✅ Priya started")

        await asyncio.sleep(1)

        print("\n[3/4] Publishing DATA_UPDATED event...")
        data_collector = DataCollector()
        data = await data_collector.update_all_data()
        await data_collector.close()

        data_event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'data_type': 'all',
                'gameweek': data['current_gameweek']['id']
            },
            source='test_script'
        )
        await event_bus.publish(data_event)
        print("✅ Event published")

        print("\n[4/4] Waiting for analysis...")
        max_wait = 30
        waited = 0

        while not analysis_received and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

        if not analysis_received:
            print("\n❌ TIMEOUT")
            return False

        # Display results
        print("\n" + "=" * 80)
        print("FIXTURE ANALYSIS RESULTS")
        print("=" * 80)

        if analysis_result:
            print(f"\nGW{analysis_result['start_gameweek']}-{analysis_result['end_gameweek']} Analysis")

            # Top 5 easiest fixtures
            print("\n✅ TOP 5 TEAMS - EASIEST FIXTURES:")
            print("-" * 80)
            for i, team in enumerate(analysis_result['teams_with_easy_fixtures'][:5], 1):
                print(f"{i}. {team['team_short_name']:<15} Avg: {team['avg_difficulty']:.2f}")

            # Top 5 hardest fixtures
            print("\n🔴 TOP 5 TEAMS - HARDEST FIXTURES:")
            print("-" * 80)
            hardest = sorted(
                analysis_result['team_analysis'],
                key=lambda x: x['avg_difficulty'],
                reverse=True
            )[:5]
            for i, team in enumerate(hardest, 1):
                print(f"{i}. {team['team_short_name']:<15} Avg: {team['avg_difficulty']:.2f}")

            # Fixture swings
            if analysis_result['fixture_swings']:
                print("\n📊 TOP 3 FIXTURE SWINGS:")
                print("-" * 80)
                for swing in analysis_result['fixture_swings'][:3]:
                    print(f"{swing['team_name']}: {swing['swing_type']}")
                    print(f"   {swing['first_half_difficulty']:.2f} → {swing['second_half_difficulty']:.2f}")

        print("\n✅ TEST PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if priya:
            await priya.stop()
        await event_bus.disconnect()


if __name__ == "__main__":
    success = asyncio.run(test_priya_agent())
    sys.exit(0 if success else 1)
