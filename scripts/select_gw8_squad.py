#!/usr/bin/env python3
"""
GW8 Squad Selection - Ron Clanker's First Team

Runs the full autonomous analysis pipeline and generates Ron's
official GW8 team announcement.
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

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


async def select_gw8_squad():
    """Generate Ron's GW8 squad selection and announcement."""

    print("=" * 80)
    print("RON CLANKER - GAMEWEEK 8 SQUAD SELECTION")
    print("=" * 80)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nRunning full autonomous analysis pipeline...\n")

    event_bus = get_event_bus()
    agents = []
    team_selected = False
    final_team = None

    async def handle_team_selection(event: Event):
        """Capture team selection."""
        nonlocal team_selected, final_team
        team_selected = True
        final_team = event.payload

    try:
        # Start system
        print("[1/6] Starting event bus and agents...")
        await event_bus.connect()
        await event_bus.subscribe(EventType.TEAM_SELECTED, handle_team_selection)
        await event_bus.start_listening()

        # Initialize all agents
        digger = DCAnalyst()
        priya = FixtureAnalyst()
        sophia = XGAnalyst()
        jimmy = ValueAnalyst()
        ron = RonManager()

        agents = [digger, priya, sophia, jimmy, ron]

        for agent in agents:
            await agent.start()
            await asyncio.sleep(0.2)

        print("  ✅ All agents online\n")

        # Collect latest data
        print("[2/6] Fetching latest FPL data...")
        data_collector = DataCollector()
        data = await data_collector.update_all_data()
        current_gw = data['current_gameweek']['id']
        await data_collector.close()

        # Ron enters at GW8 - select team for NEXT gameweek using current data
        target_gw = 8
        print(f"  ✅ Current GW: {current_gw}")
        print(f"  ✅ Using GW1-{current_gw} data to select team FOR GW{target_gw}\n")

        # Trigger analysis pipeline
        print("[3/6] Running specialist analyses...")
        print("  → Digger analyzing DC performance...")
        print("  → Priya analyzing fixtures...")
        print("  → Sophia analyzing xG data...")
        print("  → Jimmy combining into value rankings...")

        data_event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'data_type': 'all',
                'gameweek': target_gw,
                'players_count': len(data['players'])
            },
            source='gw8_selection'
        )
        await event_bus.publish(data_event)
        await asyncio.sleep(3)

        print("  ✅ Analyses complete\n")

        # Request team selection
        print(f"[4/6] Ron making final team selection for GW{target_gw}...")
        selection_request = Event(
            event_type=EventType.TEAM_SELECTION_REQUESTED,
            payload={'gameweek': target_gw},
            source='gw8_selection'
        )
        await event_bus.publish(selection_request)

        # Wait for decision
        max_wait = 30
        waited = 0
        while not team_selected and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

        if not team_selected:
            print("  ❌ Team selection timed out\n")
            return False

        print("  ✅ Team selected\n")

        # Get full squad details
        print("[5/6] Generating team announcement...")
        squad = ron.get_current_team()
        announcement = final_team['announcement']

        # Display to console
        print("\n" + "=" * 80)
        print(announcement)
        print("=" * 80)

        # Save to file
        print("\n[6/6] Saving announcement...")
        output_dir = project_root / "data" / "squads"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"gw{target_gw}_team_announcement.txt"

        with open(output_file, 'w') as f:
            f.write(announcement)
            f.write(f"\n\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Using GW1-{current_gw} data for GW{target_gw} selection\n")
            f.write(f"System: Ron Clanker Autonomous FPL Manager v0.1\n")

        print(f"  ✅ Saved to {output_file}\n")

        # Summary stats
        print("=" * 80)
        print("SELECTION SUMMARY")
        print("=" * 80)
        print(f"\nTarget Gameweek: {target_gw}")
        print(f"Based on: GW1-{current_gw} data")
        print(f"Squad size: {len(squad)} players")
        print(f"Total cost: £{final_team['total_cost']:.1f}m / £100.0m")
        print(f"Budget remaining: £{100.0 - final_team['total_cost']:.1f}m")

        # Position breakdown
        by_pos = {}
        for p in squad:
            pos = ['GKP', 'DEF', 'MID', 'FWD'][p['element_type'] - 1]
            by_pos[pos] = by_pos.get(pos, [])
            by_pos[pos].append(p)

        print(f"\nSquad composition:")
        for pos in ['GKP', 'DEF', 'MID', 'FWD']:
            count = len(by_pos.get(pos, []))
            total_cost = sum(p['now_cost'] for p in by_pos.get(pos, []))
            print(f"  {pos}: {count} players, £{total_cost/10:.1f}m")

        # Captain
        captain = next((p for p in squad if p.get('is_captain')), None)
        vice = next((p for p in squad if p.get('is_vice_captain')), None)
        if captain:
            print(f"\nCaptain: {captain['web_name']} (£{captain['now_cost']/10:.1f}m)")
        if vice:
            print(f"Vice-captain: {vice['web_name']} (£{vice['now_cost']/10:.1f}m)")

        print("\n" + "=" * 80)
        print(f"✅ GW{target_gw} SQUAD SELECTION COMPLETE")
        print("=" * 80)
        print(f"\nAnnouncement saved to: {output_file}")
        print(f"\nRon Clanker is ready for Gameweek {target_gw}. COYG! 🚀\n")

        return True

    except Exception as e:
        print(f"\n❌ Error during selection: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print("\n[Cleanup] Stopping agents...")
        for agent in agents:
            await agent.stop()
        await event_bus.disconnect()


if __name__ == "__main__":
    success = asyncio.run(select_gw8_squad())
    sys.exit(0 if success else 1)
