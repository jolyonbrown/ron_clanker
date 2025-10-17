#!/usr/bin/env python3
"""
Quick test of Ron's team selection (no interactive prompts).
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
from agents.manager_agent_v2 import RonManager
from agents.data_collector import DataCollector
from infrastructure.event_bus import get_event_bus
from infrastructure.events import Event, EventType


async def test_ron_selection():
    """Test Ron's autonomous team selection."""
    print("=" * 80)
    print("TESTING RON'S AUTONOMOUS TEAM SELECTION")
    print("=" * 80)

    event_bus = get_event_bus()
    agents = []
    team_selected = False
    final_team = None

    async def handle_team_selection(event: Event):
        """Handler for TEAM_SELECTED event."""
        nonlocal team_selected, final_team
        team_selected = True
        final_team = event.payload
        print("\n✅ TEAM_SELECTED event received!")

    try:
        print("\n[1/5] Starting agents...")
        await event_bus.connect()
        await event_bus.subscribe(EventType.TEAM_SELECTED, handle_team_selection)
        await event_bus.start_listening()

        # Start all agents
        digger = DCAnalyst()
        priya = FixtureAnalyst()
        sophia = XGAnalyst()
        jimmy = ValueAnalyst()
        ron = RonManager()

        agents = [digger, priya, sophia, jimmy, ron]

        for agent in agents:
            await agent.start()
            print(f"  ✅ {agent.agent_name} started")
            await asyncio.sleep(0.2)

        print("\n[2/5] Collecting FPL data...")
        data_collector = DataCollector()
        data = await data_collector.update_all_data()
        current_gw = data['current_gameweek']['id']
        await data_collector.close()
        print(f"  ✅ GW{current_gw} data loaded")

        print("\n[3/5] Triggering analysis pipeline...")
        data_event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'data_type': 'all',
                'gameweek': current_gw,
                'players_count': len(data['players'])
            },
            source='test'
        )
        await event_bus.publish(data_event)
        await asyncio.sleep(3)  # Wait for analyses

        print("\n[4/5] Requesting team selection...")
        selection_request = Event(
            event_type=EventType.TEAM_SELECTION_REQUESTED,
            payload={'gameweek': current_gw},
            source='test'
        )
        await event_bus.publish(selection_request)

        # Wait for Ron's decision
        print("  Waiting for Ron's decision...")
        max_wait = 30
        waited = 0

        while not team_selected and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

        if not team_selected:
            print("\n❌ FAILED: Ron didn't select team in time")
            return False

        print("\n[5/5] Validating selection...")
        print(f"  Squad size: {len(final_team['squad'])} players")
        print(f"  Total cost: £{final_team['total_cost']:.1f}m")

        # Get full squad details
        squad_data = ron.get_current_team()

        if squad_data and len(squad_data) == 15:
            print("\n✅ SUCCESS: Ron selected a valid team!")

            # Show starting XI
            starting = [p for p in squad_data if p.get('position', 16) <= 11]
            print(f"\nStarting XI ({len(starting)} players):")
            for p in sorted(starting, key=lambda x: x['position']):
                captain = "(C)" if p.get('is_captain') else ""
                vice = "(VC)" if p.get('is_vice_captain') else ""
                print(f"  {p['position']:2}. {p['web_name']:<20} £{p['now_cost']/10:.1f}m {captain}{vice}")

            return True
        else:
            print(f"\n❌ FAILED: Invalid squad (got {len(squad_data) if squad_data else 0}/15 players)")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print("\n[Cleanup]")
        for agent in agents:
            await agent.stop()
        await event_bus.disconnect()
        print("✅ Done")


if __name__ == "__main__":
    success = asyncio.run(test_ron_selection())
    sys.exit(0 if success else 1)
