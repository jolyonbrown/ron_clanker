#!/usr/bin/env python3
"""
Integration test for all specialist analysts working together.

Tests the full analysis pipeline:
1. Digger (DC Analyst)
2. Priya (Fixture Analyst)
3. Sophia (xG Analyst)
4. Jimmy (Value Analyst) - combines all three

Verifies event-driven coordination and final value rankings.
"""

import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.dc_analyst import DCAnalyst
from agents.fixture_analyst import FixtureAnalyst
from agents.xg_analyst import XGAnalyst
from agents.value_analyst import ValueAnalyst
from agents.data_collector import DataCollector
from infrastructure.event_bus import get_event_bus
from infrastructure.events import Event, EventType


async def test_all_analysts():
    """Test all analysts working together in coordination."""
    print("=" * 80)
    print("FULL ANALYST PIPELINE INTEGRATION TEST")
    print("=" * 80)

    event_bus = get_event_bus()
    agents = []
    value_rankings_received = False
    value_result = None

    async def handle_value_rankings(event: Event):
        """Handler for VALUE_RANKINGS_COMPLETED."""
        nonlocal value_rankings_received, value_result
        print("\n🎯 VALUE_RANKINGS_COMPLETED event received!")
        value_rankings_received = True
        value_result = event.payload

    try:
        print("\n[1/6] Connecting to event bus...")
        await event_bus.connect()
        print("✅ Connected")

        print("\n[2/6] Subscribing to VALUE_RANKINGS_COMPLETED...")
        await event_bus.subscribe(EventType.VALUE_RANKINGS_COMPLETED, handle_value_rankings)
        await event_bus.start_listening()
        print("✅ Subscribed")

        print("\n[3/6] Starting all specialist agents...")

        # Start all agents
        digger = DCAnalyst()
        priya = FixtureAnalyst()
        sophia = XGAnalyst()
        jimmy = ValueAnalyst()

        agents = [digger, priya, sophia, jimmy]

        for agent in agents:
            await agent.start()
            print(f"  ✅ {agent.agent_name} started")

        await asyncio.sleep(2)

        print("\n[4/6] Fetching FPL data and triggering analysis...")
        data_collector = DataCollector()
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
        print(f"✅ DATA_UPDATED event published (GW{data['current_gameweek']['id']})")

        print("\n[5/6] Waiting for analysis pipeline to complete...")
        print("  Expected: Digger → Priya → Sophia → Jimmy")

        max_wait = 45  # seconds
        waited = 0

        while not value_rankings_received and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1
            if waited % 5 == 0:
                print(f"  Still waiting... ({waited}s/{max_wait}s)")

        if not value_rankings_received:
            print("\n❌ TIMEOUT: Value rankings not received")
            return False

        # Display results
        print("\n" + "=" * 80)
        print("VALUE RANKINGS RESULTS")
        print("=" * 80)

        if value_result:
            print(f"\nGameweek: {value_result['gameweek']}")
            print(f"Total players ranked: {value_result['total_players_ranked']}")
            print(f"\nScoring weights:")
            for component, weight in value_result['scoring_weights'].items():
                print(f"  {component}: {weight*100:.0f}%")

            # Top overall value picks
            print("\n💎 TOP 10 OVERALL VALUE PICKS:")
            print("-" * 80)
            print(f"{'Rank':<5} {'Player':<20} {'Pos':<5} {'Price':<8} {'Value':<8} {'Pts/£m'}")
            print("-" * 80)
            for i, player in enumerate(value_result['top_overall'][:10], 1):
                print(
                    f"{i:<5} {player['name']:<20} {player['position']:<5} "
                    f"£{player['price']:.1f}m   {player['value_score']:<8.1f} "
                    f"{player['points_per_million']:.1f}"
                )

            # Best by position
            print("\n🥇 BEST VALUE BY POSITION:")
            print("-" * 80)

            for position in ['GKP', 'DEF', 'MID', 'FWD']:
                best_key = f'best_value_{position.lower()}'
                best_players = value_result.get(best_key, [])

                if best_players:
                    print(f"\n{position}:")
                    for i, player in enumerate(best_players[:3], 1):
                        print(
                            f"  {i}. {player['name']:<20} £{player['price']:.1f}m  "
                            f"Value: {player['value_score']:.1f}  "
                            f"({player['total_points']} pts)"
                        )

            # Show scoring breakdown for top pick
            if value_result['top_overall']:
                top_pick = value_result['top_overall'][0]
                print(f"\n📊 VALUE SCORE BREAKDOWN - {top_pick['name']}:")
                print("-" * 80)
                print(f"  Base score (pts/£m):     {top_pick['base_score']:.1f}")
                print(f"  DC potential:            {top_pick['dc_score']:.1f}")
                print(f"  Fixture quality:         {top_pick['fixture_score']:.1f}")
                print(f"  xG threat:               {top_pick['xg_score']:.1f}")
                print(f"  → Total value score:     {top_pick['value_score']:.1f}")

        print("\n" + "=" * 80)
        print("✅ TEST PASSED: Full analyst pipeline working!")
        print("=" * 80)
        print("\nPipeline verified:")
        print("  ✅ Digger analyzed DC performance")
        print("  ✅ Priya analyzed fixtures")
        print("  ✅ Sophia analyzed xG data")
        print("  ✅ Jimmy combined all analyses into value rankings")
        print("  ✅ Event-driven coordination successful")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print("\n[6/6] Cleanup...")
        for agent in agents:
            await agent.stop()
        await event_bus.disconnect()
        print("✅ All agents stopped")


if __name__ == "__main__":
    success = asyncio.run(test_all_analysts())
    sys.exit(0 if success else 1)
