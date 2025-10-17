#!/usr/bin/env python3
"""
Test script for Digger (DC Analyst) agent.

Verifies event-driven architecture:
1. Starts Redis event bus
2. Starts Digger agent
3. Publishes DATA_UPDATED event
4. Waits for DC_ANALYSIS_COMPLETED event
5. Displays results
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.dc_analyst import DCAnalyst
from agents.data_collector import DataCollector
from infrastructure.event_bus import get_event_bus
from infrastructure.events import Event, EventType, create_data_refresh_event


async def test_digger_agent():
    """Test Digger agent with event bus."""
    print("=" * 80)
    print("DIGGER AGENT INTEGRATION TEST")
    print("=" * 80)

    event_bus = get_event_bus()
    digger = None

    # Track if we received DC analysis
    analysis_received = False
    analysis_result = None

    async def handle_dc_analysis(event: Event):
        """Handler for DC_ANALYSIS_COMPLETED events."""
        nonlocal analysis_received, analysis_result
        print("\n✅ DC_ANALYSIS_COMPLETED event received!")
        analysis_received = True
        analysis_result = event.payload

    try:
        # Step 1: Connect to event bus
        print("\n[1/5] Connecting to event bus...")
        await event_bus.connect()
        print("✅ Connected to Redis")

        # Step 2: Subscribe to DC_ANALYSIS_COMPLETED
        print("\n[2/5] Subscribing to DC_ANALYSIS_COMPLETED...")
        await event_bus.subscribe(EventType.DC_ANALYSIS_COMPLETED, handle_dc_analysis)
        await event_bus.start_listening()
        print("✅ Subscribed and listening")

        # Step 3: Start Digger agent
        print("\n[3/5] Starting Digger agent...")
        digger = DCAnalyst()
        await digger.start()
        print("✅ Digger started")

        # Give it a moment to initialize
        await asyncio.sleep(1)

        # Step 4: Trigger analysis by publishing DATA_UPDATED
        print("\n[4/5] Publishing DATA_UPDATED event...")

        # First fetch data so Digger has something to analyze
        data_collector = DataCollector()
        print("   Fetching FPL data...")
        data = await data_collector.update_all_data()
        await data_collector.close()

        # Publish DATA_UPDATED event
        data_event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'data_type': 'all',
                'gameweek': data['current_gameweek']['id'],
                'players_count': len(data['players'])
            },
            source='test_script'
        )
        await event_bus.publish(data_event)
        print("✅ DATA_UPDATED event published")

        # Step 5: Wait for analysis to complete
        print("\n[5/5] Waiting for Digger to analyze data...")
        max_wait = 30  # seconds
        waited = 0

        while not analysis_received and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1
            if waited % 5 == 0:
                print(f"   Still waiting... ({waited}s/{max_wait}s)")

        if not analysis_received:
            print("\n❌ TIMEOUT: Digger did not publish analysis within 30s")
            return False

        # Display results
        print("\n" + "=" * 80)
        print("DC ANALYSIS RESULTS")
        print("=" * 80)

        if analysis_result:
            print(f"\nGameweek: {analysis_result.get('gameweek')}")
            print(f"Players analyzed: {analysis_result.get('players_analyzed')}")
            print(f"Min games required: {analysis_result.get('min_games_required')}")

            # Top defender recommendations
            print("\n🛡️  TOP 5 DEFENDER DC SPECIALISTS:")
            print("-" * 80)
            for i, player in enumerate(analysis_result.get('defender_recommendations', [])[:5], 1):
                print(
                    f"{i}. {player['name']:<20} £{player['price']:.1f}m  "
                    f"DC: {player['dc_consistency']:.1f}%  "
                    f"Value: {player['dc_value']:.2f} DC/£m"
                )

            # Top midfielder recommendations
            print("\n⚡ TOP 5 MIDFIELDER DC SPECIALISTS:")
            print("-" * 80)
            for i, player in enumerate(analysis_result.get('midfielder_recommendations', [])[:5], 1):
                print(
                    f"{i}. {player['name']:<20} £{player['price']:.1f}m  "
                    f"DC: {player['dc_consistency']:.1f}%  "
                    f"Value: {player['dc_value']:.2f} DC/£m"
                )

            # Elite performers
            elite = analysis_result.get('elite_dc_performers', [])[:5]
            if elite:
                print("\n🌟 TOP 5 ELITE DC PERFORMERS:")
                print("-" * 80)
                for i, player in enumerate(elite, 1):
                    print(
                        f"{i}. {player['name']:<20} {player['position']:<5} "
                        f"£{player['price']:.1f}m  DC: {player['dc_consistency']:.1f}%  "
                        f"Pts: {player['total_points']}"
                    )

        print("\n" + "=" * 80)
        print("✅ TEST PASSED: Digger agent working correctly!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup
        print("\n[Cleanup] Stopping agent and disconnecting...")
        if digger:
            await digger.stop()
        await event_bus.disconnect()
        print("✅ Cleanup complete")


async def main():
    """Main test runner."""
    print("\n🔬 Testing Digger (DC Analyst) Agent\n")

    success = await test_digger_agent()

    if success:
        print("\n✅ All tests passed!\n")
        sys.exit(0)
    else:
        print("\n❌ Tests failed\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
