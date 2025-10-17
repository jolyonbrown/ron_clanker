#!/usr/bin/env python3
"""
Ron Clanker FPL System - Live Demo

Showcases the event-driven multi-agent analysis system:
- Digger: DC analysis
- Priya: Fixture analysis
- Sophia: xG analysis
- Jimmy: Combined value rankings

Watch the agents work together autonomously!
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
from agents.data_collector import DataCollector
from infrastructure.event_bus import get_event_bus
from infrastructure.events import Event, EventType


def print_header(title):
    """Print a nice header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_section(title):
    """Print a section header."""
    print(f"\n{'─' * 80}")
    print(f"  {title}")
    print(f"{'─' * 80}")


async def demo_system():
    """Full system demonstration."""

    print_header("🤖 RON CLANKER'S FPL MULTI-AGENT SYSTEM - LIVE DEMO")

    print("\nThis demo showcases the autonomous, event-driven analysis pipeline.")
    print("Watch as specialist agents coordinate via Redis pub/sub to analyze")
    print("FPL data and produce comprehensive player value rankings.\n")

    input("Press ENTER to start the demo...")

    event_bus = get_event_bus()
    agents = {}
    results = {
        'dc': None,
        'fixture': None,
        'xg': None,
        'value': None
    }

    # Event handlers to capture results
    async def handle_dc(e):
        results['dc'] = e.payload
        print("    ✅ Digger completed DC analysis")

    async def handle_fixture(e):
        results['fixture'] = e.payload
        print("    ✅ Priya completed fixture analysis")

    async def handle_xg(e):
        results['xg'] = e.payload
        print("    ✅ Sophia completed xG analysis")

    async def handle_value(e):
        results['value'] = e.payload
        print("    ✅ Jimmy completed value rankings")

    try:
        # Setup
        print_section("PHASE 1: System Initialization")

        print("\n[1] Connecting to Redis event bus...")
        await event_bus.connect()
        print("    ✅ Connected to Redis")

        print("\n[2] Subscribing to analysis events...")
        await event_bus.subscribe(EventType.DC_ANALYSIS_COMPLETED, handle_dc)
        await event_bus.subscribe(EventType.FIXTURE_ANALYSIS_COMPLETED, handle_fixture)
        await event_bus.subscribe(EventType.XG_ANALYSIS_COMPLETED, handle_xg)
        await event_bus.subscribe(EventType.VALUE_RANKINGS_COMPLETED, handle_value)
        await event_bus.start_listening()
        print("    ✅ Event listeners active")

        print("\n[3] Starting specialist agents...")

        agents['digger'] = DCAnalyst()
        await agents['digger'].start()
        print("    ✅ Digger (DC Analyst) ready")
        await asyncio.sleep(0.5)

        agents['priya'] = FixtureAnalyst()
        await agents['priya'].start()
        print("    ✅ Priya (Fixture Analyst) ready")
        await asyncio.sleep(0.5)

        agents['sophia'] = XGAnalyst()
        await agents['sophia'].start()
        print("    ✅ Sophia (xG Analyst) ready")
        await asyncio.sleep(0.5)

        agents['jimmy'] = ValueAnalyst()
        await agents['jimmy'].start()
        print("    ✅ Jimmy (Value Analyst) ready")

        await asyncio.sleep(1)

        # Trigger analysis
        print_section("PHASE 2: Data Collection & Analysis Pipeline")

        print("\n[4] Fetching latest FPL data...")
        data_collector = DataCollector()
        data = await data_collector.update_all_data()
        current_gw = data['current_gameweek']['id']
        await data_collector.close()

        print(f"    ✅ Data loaded: {len(data['players'])} players, GW{current_gw}")

        print(f"\n[5] Publishing DATA_UPDATED event...")
        print("    → Event will trigger all specialist agents simultaneously")

        data_event = Event(
            event_type=EventType.DATA_UPDATED,
            payload={
                'data_type': 'all',
                'gameweek': current_gw,
                'players_count': len(data['players'])
            },
            source='demo'
        )
        await event_bus.publish(data_event)
        print("    ✅ Event published to Redis")

        print(f"\n[6] Agents processing (autonomous coordination via events)...")

        # Wait for all analyses
        max_wait = 45
        waited = 0

        while waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

            # Check if all complete
            if all(results.values()):
                break

        if not all(results.values()):
            print("\n⚠️  Not all analyses completed in time")
            print(f"    DC: {'✅' if results['dc'] else '❌'}")
            print(f"    Fixture: {'✅' if results['fixture'] else '❌'}")
            print(f"    xG: {'✅' if results['xg'] else '❌'}")
            print(f"    Value: {'✅' if results['value'] else '❌'}")
            return

        print(f"\n    ✅ All analyses complete in {waited} seconds!")

        # Display results
        print_section("PHASE 3: Analysis Results")

        # Digger results
        print("\n🛡️  DIGGER (DC ANALYST) - Top DC Specialists")
        print("\nDefensive Contribution = consistent 2pt floor every gameweek")
        dc_data = results['dc']
        print(f"Analyzed {dc_data['players_analyzed']} players\n")

        print("Top 5 Defenders:")
        for i, p in enumerate(dc_data['defender_recommendations'][:5], 1):
            print(f"  {i}. {p['name']:<20} £{p['price']:.1f}m  DC: {p['dc_consistency']:.1f}%  Value: {p['dc_value']:.2f}")

        print("\nTop 5 Midfielders:")
        for i, p in enumerate(dc_data['midfielder_recommendations'][:5], 1):
            print(f"  {i}. {p['name']:<20} £{p['price']:.1f}m  DC: {p['dc_consistency']:.1f}%  Value: {p['dc_value']:.2f}")

        # Priya results
        print("\n\n📅 PRIYA (FIXTURE ANALYST) - Next 6 Gameweeks")
        fixture_data = results['fixture']
        print(f"Looking ahead: GW{fixture_data['start_gameweek']}-{fixture_data['end_gameweek']}\n")

        print("Teams with EASIEST fixtures:")
        for i, t in enumerate(fixture_data['teams_with_easy_fixtures'][:5], 1):
            print(f"  {i}. {t['team_short_name']:<15} Avg difficulty: {t['avg_difficulty']:.2f}")

        if fixture_data['fixture_swings']:
            print("\nBiggest fixture swings:")
            for swing in fixture_data['fixture_swings'][:3]:
                arrow = "📈" if swing['swing_type'] == 'improving' else "📉"
                print(f"  {arrow} {swing['team_name']}: {swing['first_half_difficulty']:.1f} → {swing['second_half_difficulty']:.1f} ({swing['swing_type']})")

        # Sophia results
        print("\n\n⚽ SOPHIA (xG ANALYST) - Attacking Threat")
        xg_data = results['xg']
        print(f"Analyzed {xg_data['players_analyzed']} attacking players\n")

        print("Highest xG threat (xGI per 90):")
        for i, p in enumerate(xg_data['high_xgi_players'][:5], 1):
            print(f"  {i}. {p['name']:<20} {p['position']:<5} xGI/90: {p['xgi_per_90']:.2f}  (£{p['price']:.1f}m)")

        print("\nUnderperformers (due to score):")
        for i, p in enumerate(xg_data['underperformers'][:5], 1):
            print(f"  {i}. {p['name']:<20} {p['goals']}G vs {p['xg']:.1f}xG  (deficit: {abs(p['xg_diff']):.1f})")

        # Jimmy results - THE BIG ONE
        print("\n\n💎 JIMMY (VALUE ANALYST) - Combined Rankings")
        value_data = results['value']
        print(f"Combined all analyses for {value_data['total_players_ranked']} players")
        print("\nScoring: 35% pts/£m + 25% DC + 20% fixtures + 20% xG\n")

        print("=" * 80)
        print("TOP 15 OVERALL VALUE PICKS (ACCORDING TO RON'S SYSTEM)")
        print("=" * 80)
        print(f"\n{'#':<3} {'Player':<20} {'Pos':<5} {'Price':<8} {'Value':<8} {'Points':<8} {'Key Insight'}")
        print("-" * 80)

        for i, p in enumerate(value_data['top_overall'][:15], 1):
            # Determine key insight
            insight = ""
            if p.get('dc_consistency', 0) > 50:
                insight = "High DC"
            elif p.get('xgi_per_90', 0) > 0.5:
                insight = "xG threat"
            elif p.get('avg_fixture_difficulty', 5) < 2.5:
                insight = "Easy fixtures"
            else:
                insight = f"{p['points_per_million']:.1f} pts/£m"

            print(
                f"{i:<3} {p['name']:<20} {p['position']:<5} "
                f"£{p['price']:<7.1f} {p['value_score']:<8.1f} "
                f"{p['total_points']:<8} {insight}"
            )

        print("\n" + "-" * 80)
        print("BEST VALUE BY POSITION")
        print("-" * 80)

        for pos_key, pos_name in [('gkp', 'GKP'), ('def', 'DEF'), ('mid', 'MID'), ('fwd', 'FWD')]:
            best = value_data.get(f'best_value_{pos_key}', [])
            if best:
                print(f"\n{pos_name}:")
                for i, p in enumerate(best[:3], 1):
                    print(
                        f"  {i}. {p['name']:<20} £{p['price']:.1f}m  "
                        f"Value: {p['value_score']:.1f}  "
                        f"({p['total_points']} pts = {p['points_per_million']:.1f} pts/£m)"
                    )

        # Show value score breakdown
        top_pick = value_data['top_overall'][0]
        print("\n" + "=" * 80)
        print(f"VALUE SCORE BREAKDOWN: {top_pick['name']} (Top Overall Pick)")
        print("=" * 80)
        print(f"\n  Base Points (35%):    {top_pick['base_score']:.1f}  [{top_pick['total_points']} pts at £{top_pick['price']:.1f}m]")
        print(f"  DC Potential (25%):   {top_pick['dc_score']:.1f}  [Consistency: {top_pick.get('dc_consistency', 0):.0f}%]")
        print(f"  Fixture Quality (20%): {top_pick['fixture_score']:.1f}  [Avg difficulty: {top_pick.get('avg_fixture_difficulty', 'N/A')}]")
        print(f"  xG Threat (20%):      {top_pick['xg_score']:.1f}  [xGI/90: {top_pick.get('xgi_per_90', 0):.2f}]")
        print(f"  {'─' * 78}")
        print(f"  TOTAL VALUE SCORE:    {top_pick['value_score']:.1f}")

        # Final summary
        print_section("DEMO COMPLETE")

        print("\n✅ Successfully demonstrated:")
        print("  • Event-driven architecture with Redis pub/sub")
        print("  • Autonomous agent coordination")
        print("  • Multi-dimensional player analysis")
        print("  • Comprehensive value rankings")

        print("\n🎯 What Ron has now:")
        print("  • Digger identifies DC specialists (defensive floor)")
        print("  • Priya analyzes fixtures 6 weeks ahead (timing)")
        print("  • Sophia identifies xG threats (attacking ceiling)")
        print("  • Jimmy combines everything (holistic value)")

        print("\n📈 Next steps:")
        print("  • Ron (Manager Agent) will use Jimmy's rankings for team selection")
        print("  • Event-driven automation with Celery Beat")
        print("  • Learning agent to track decisions vs outcomes")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[Cleanup] Stopping agents...")
        for agent in agents.values():
            await agent.stop()
        await event_bus.disconnect()
        print("✅ All agents stopped\n")


if __name__ == "__main__":
    asyncio.run(demo_system())
