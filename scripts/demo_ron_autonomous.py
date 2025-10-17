#!/usr/bin/env python3
"""
Ron Clanker - Fully Autonomous Team Selection Demo

Demonstrates the complete autonomous FPL management system:

1. Specialist agents analyze data (Digger, Priya, Sophia)
2. Jimmy combines analyses into value rankings
3. Ron makes final team selection decision
4. Full team announcement in Ron's voice

No human input required. Ron's in charge.
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


def print_header(title):
    """Print a nice header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


async def demo_autonomous_selection():
    """Demonstrate fully autonomous team selection."""

    print_header("🤖 RON CLANKER - FULLY AUTONOMOUS TEAM SELECTION")

    print("\nThis is it. The full system working autonomously.")
    print("Watch Ron analyze FPL data through his specialist agents,")
    print("synthesize their recommendations, and select his team.")
    print("\nNo human input. Ron makes the call.\n")

    input("Press ENTER to watch Ron work...")

    event_bus = get_event_bus()
    agents = []
    team_selected = False
    final_team = None

    async def handle_team_selection(event: Event):
        """Handler for TEAM_SELECTED event."""
        nonlocal team_selected, final_team
        team_selected = True
        final_team = event.payload
        print("\n🎯 TEAM_SELECTED event received!")

    try:
        print("\n[Phase 1] Starting the specialists...")
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
            print(f"  ✅ {agent.agent_name} ready")
            await asyncio.sleep(0.3)

        print("\n[Phase 2] Collecting latest FPL data...")
        data_collector = DataCollector()
        data = await data_collector.update_all_data()
        current_gw = data['current_gameweek']['id']
        await data_collector.close()

        # Ron selects for NEXT gameweek (target)
        target_gw = current_gw + 1

        print(f"  ✅ Data loaded: {len(data['players'])} players, GW{current_gw}")
        print(f"  ✅ Target: Selecting FOR GW{target_gw} using GW1-{current_gw} data")

        print("\n[Phase 3] Triggering analysis pipeline...")
        print("  Ron: 'Right lads, get me the analysis. I need to pick the team.'\n")

        # Trigger the pipeline
        data_event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'data_type': 'all',
                'gameweek': target_gw,
                'players_count': len(data['players'])
            },
            source='demo'
        )
        await event_bus.publish(data_event)

        # Wait for analyses to complete
        print("  Digger analyzing DC performance...")
        await asyncio.sleep(1)
        print("  Priya analyzing fixtures...")
        await asyncio.sleep(0.5)
        print("  Sophia analyzing xG data...")
        await asyncio.sleep(0.5)
        print("  Jimmy combining everything...")
        await asyncio.sleep(1)

        print("\n[Phase 4] Ron making the final call...")
        print("  Ron: 'Right, I've got Jimmy's rankings. Time to pick the squad.'\n")

        # Trigger Ron's team selection
        selection_request = Event(
            event_type=EventType.TEAM_SELECTION_REQUESTED,
            payload={'gameweek': target_gw},
            source='demo'
        )
        await event_bus.publish(selection_request)

        # Wait for Ron's decision
        max_wait = 30
        waited = 0

        while not team_selected and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

        if not team_selected:
            print("\n❌ Ron didn't make a decision in time")
            return False

        print_header("RON'S AUTONOMOUS TEAM SELECTION")

        # Display the announcement
        print(final_team['announcement'])

        print("\n" + "=" * 80)
        print("SQUAD DETAILS")
        print("=" * 80)

        # Show the squad
        squad_data = ron.get_current_team()

        if squad_data:
            # Group by position
            by_pos = {}
            for player in squad_data:
                pos = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]
                if pos not in by_pos:
                    by_pos[pos] = []
                by_pos[pos].append(player)

            for pos in ['GKP', 'DEF', 'MID', 'FWD']:
                if pos in by_pos:
                    print(f"\n{pos}:")
                    for player in by_pos[pos]:
                        starter = "⭐" if player.get('position', 16) <= 11 else "  "
                        captain = "(C)" if player.get('is_captain') else ""
                        vice = "(VC)" if player.get('is_vice_captain') else ""
                        value = player.get('value_score', 0)

                        print(
                            f"  {starter} {player['web_name']:<20} £{player['now_cost']/10:.1f}m  "
                            f"Value: {value:.1f} {captain}{vice}"
                        )

        print(f"\n{'─' * 80}")
        print(f"Total cost: £{final_team['total_cost']:.1f}m / £100.0m")
        print(f"Squad value score: {sum(p.get('value_score', 0) for p in squad_data) / len(squad_data):.1f} avg")

        print_header("DEMO COMPLETE")

        print("\n✅ Autonomous team selection successful!")
        print("\n🎯 What just happened:")
        print("  1. Digger identified DC specialists")
        print("  2. Priya analyzed upcoming fixtures")
        print("  3. Sophia identified xG threats")
        print("  4. Jimmy combined all analyses into value rankings")
        print("  5. Ron made the final team selection decision")
        print("  6. Squad validated against FPL rules")
        print("  7. Team announcement generated in Ron's voice")

        print("\n💡 Key insights:")
        print("  • Zero human input required")
        print("  • Event-driven coordination across 5 agents")
        print("  • Multi-dimensional analysis (DC + fixtures + xG)")
        print("  • Ron's tactical philosophy applied")
        print("  • Valid FPL squad, within budget, ready to submit")

        print("\n🚀 Next steps:")
        print("  • Automate with Celery Beat (daily/weekly triggers)")
        print("  • Add learning agent to track decisions vs outcomes")
        print("  • Implement transfer logic for ongoing management")
        print("  • Connect to FPL API for actual submissions")

        print("\n" + "=" * 80)

        return True

    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print("\n[Cleanup]")
        for agent in agents:
            await agent.stop()
        await event_bus.disconnect()
        print("✅ All agents stopped")


if __name__ == "__main__":
    success = asyncio.run(demo_autonomous_selection())
    sys.exit(0 if success else 1)
