#!/usr/bin/env python3
"""
Multi-Gameweek Strategic Planning

Generate Ron's strategic plan for the next 4-6 gameweeks.

Usage:
    python scripts/plan_multi_gameweeks.py --gw 8 --horizon 6
    python scripts/plan_multi_gameweeks.py --gw 8 --quick  # Quick summary
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from planning.multi_gw_planner import MultiGWPlanner


def format_plan_report(plan: dict) -> str:
    """
    Format strategic plan into readable report.

    Args:
        plan: Strategic plan dict from MultiGWPlanner

    Returns:
        Formatted string report
    """
    lines = []

    lines.append("=" * 80)
    lines.append(f"RON CLANKER'S STRATEGIC PLAN: {plan['planning_period']}")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.fromisoformat(plan['generated_at']).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # KEY RECOMMENDATIONS
    lines.append("-" * 80)
    lines.append("KEY RECOMMENDATIONS")
    lines.append("-" * 80)

    for i, rec in enumerate(plan['recommendations'][:5], 1):
        priority_label = {1: 'URGENT', 2: 'HIGH', 3: 'MEDIUM'}.get(rec['priority'], 'LOW')
        lines.append(f"\n{i}. [{priority_label}] {rec['action']}")
        lines.append(f"   {rec['reasoning']}")
        if 'gameweek' in rec:
            lines.append(f"   Target: GW{rec['gameweek']}")
        elif 'gameweek_range' in rec:
            lines.append(f"   Period: {rec['gameweek_range']}")

    # FIXTURE ANALYSIS
    lines.append("\n" + "-" * 80)
    lines.append("FIXTURE ANALYSIS")
    lines.append("-" * 80)

    fixtures = plan['fixtures']

    lines.append("\nTeams with Best Fixtures:")
    for i, team in enumerate(fixtures['best_fixture_runs'][:5], 1):
        lines.append(
            f"  {i}. {team['team_name']}: "
            f"Avg difficulty {team['average_difficulty']:.2f} "
            f"({team['recommendation']})"
        )

    if fixtures['favorable_swings']:
        lines.append("\nFixture Swings - Improving:")
        for swing in fixtures['favorable_swings'][:3]:
            lines.append(
                f"  • {swing['team_name']}: "
                f"{swing['early_difficulty']:.1f} → {swing['late_difficulty']:.1f} "
                f"(bring in around GW{swing['optimal_gw']})"
            )

    if fixtures['unfavorable_swings']:
        lines.append("\nFixture Swings - Worsening:")
        for swing in fixtures['unfavorable_swings'][:3]:
            lines.append(
                f"  • {swing['team_name']}: "
                f"{swing['early_difficulty']:.1f} → {swing['late_difficulty']:.1f} "
                f"(move out soon)"
            )

    # TRANSFER STRATEGY
    lines.append("\n" + "-" * 80)
    lines.append("TRANSFER STRATEGY")
    lines.append("-" * 80)

    transfer_summary = plan['transfers']['summary']
    lines.append(f"\n{transfer_summary}")

    if plan['transfers']['priorities']:
        lines.append("\nTransfer Priorities:")
        for priority in plan['transfers']['priorities'][:5]:
            reasons = ', '.join(priority['reasons'])
            lines.append(
                f"  • {priority['player_name']} "
                f"(Priority {priority['priority_level']}: {reasons})"
            )

    # CHIP STRATEGY
    lines.append("\n" + "-" * 80)
    lines.append("CHIP STRATEGY")
    lines.append("-" * 80)

    chips = plan['chips']
    lines.append(f"\nAvailable Chips: {', '.join(chips['available_chips']) if chips['available_chips'] else 'None'}")

    if chips['priority_chip']:
        lines.append(f"Priority Chip: {chips['priority_chip'].replace('_', ' ').title()}")

    if chips['recommendations']:
        lines.append("\nRecommendations:")
        for chip_rec in chips['recommendations']:
            urgency_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(chip_rec['urgency'], '')
            lines.append(f"\n  {urgency_emoji} {chip_rec['chip'].replace('_', ' ').title()}")
            lines.append(f"    {chip_rec['reasoning']}")
            if chip_rec.get('optimal_gw'):
                lines.append(f"    Optimal: GW{chip_rec['optimal_gw']}")

    # BUDGET & TEAM VALUE
    lines.append("\n" + "-" * 80)
    lines.append("BUDGET & TEAM VALUE")
    lines.append("-" * 80)

    budget = plan['budget']
    current = budget['current_status']

    lines.append(f"\nCurrent Team Value: £{current['team_value']/10:.1f}m")
    lines.append(f"Total Budget: £{current['total_budget']/10:.1f}m")
    lines.append(f"Profit: £{current['profit']/10:.1f}m")

    growth = budget['value_growth']
    lines.append(f"\nProjected Growth ({growth['period']}):")
    lines.append(f"  Current: £{growth['current_value']/10:.1f}m")
    lines.append(f"  Projected: £{growth['projected_value']/10:.1f}m")
    lines.append(f"  Expected gain: £{growth['expected_growth']/10:.1f}m")

    price_targets = budget['price_targets']
    if price_targets['rise_soon'] > 0:
        lines.append(f"\nPrice Targets:")
        lines.append(f"  {price_targets['rise_soon']} player(s) likely to rise soon")
        if price_targets['top_targets']:
            lines.append("  Top 3:")
            for target in price_targets['top_targets']:
                lines.append(f"    • {target['name']}: £{target['current_price']/10:.1f}m → £{target['expected_price']/10:.1f}m")

    if price_targets['fall_risks'] > 0:
        lines.append(f"\n⚠️  {price_targets['fall_risks']} owned player(s) at risk of falling")

    lines.append("\n" + "=" * 80)
    lines.append("END OF STRATEGIC PLAN")
    lines.append("=" * 80)

    return '\n'.join(lines)


def format_quick_summary(summary: dict) -> str:
    """
    Format quick summary into readable report.

    Args:
        summary: Quick summary dict from MultiGWPlanner

    Returns:
        Formatted string
    """
    lines = []

    lines.append("=" * 80)
    lines.append(f"RON'S QUICK SUMMARY - GW{summary['gameweek']}")
    lines.append("=" * 80)

    lines.append(f"\nKey Message: {summary['key_message']}")

    lines.append(f"\nBest Fixtures (next 3 GWs): {', '.join(summary['best_fixtures_next_3_gw'])}")

    lines.append(f"\nTransfer Action: {summary['transfer_action'].replace('_', ' ').title()}")

    if summary['urgent_chips']:
        lines.append(f"\n⚠️  Urgent Chips: {', '.join(summary['urgent_chips'])}")

    if summary['price_fall_alerts'] > 0:
        lines.append(f"\n⚠️  Price Fall Alerts: {summary['price_fall_alerts']} player(s)")

    lines.append("\n" + "=" * 80)

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Multi-Gameweek Strategic Planning')
    parser.add_argument('--gw', type=int, required=True, help='Current gameweek')
    parser.add_argument('--horizon', type=int, default=6, help='Planning horizon in gameweeks (default: 6)')
    parser.add_argument('--quick', action='store_true', help='Quick summary only')
    parser.add_argument('--save', action='store_true', help='Save plan to file')

    args = parser.parse_args()

    start_time = datetime.now()

    print("\n" + "=" * 80)
    if args.quick:
        print(f"QUICK STRATEGIC SUMMARY - GW{args.gw}")
    else:
        print(f"MULTI-GAMEWEEK STRATEGIC PLANNING - GW{args.gw}")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    # Initialize
    db = Database()
    planner = MultiGWPlanner(db)

    if args.quick:
        # Quick summary
        print("Generating quick summary...")
        summary = planner.get_quick_summary(args.gw)

        report = format_quick_summary(summary)
        print("\n" + report)

    else:
        # Full strategic plan
        print(f"Generating strategic plan for GW{args.gw}-{args.gw+args.horizon-1}...")
        print(f"Planning horizon: {args.horizon} gameweeks")
        print("")

        plan = planner.generate_strategic_plan(args.gw, args.horizon)

        report = format_plan_report(plan)
        print("\n" + report)

        # Save to file if requested
        if args.save:
            output_dir = project_root / 'reports' / 'strategic_plans'
            output_dir.mkdir(parents=True, exist_ok=True)

            # Save formatted report
            report_file = output_dir / f'strategic_plan_gw{args.gw}_{start_time.strftime("%Y%m%d_%H%M%S")}.txt'
            with open(report_file, 'w') as f:
                f.write(report)

            # Save JSON data
            json_file = output_dir / f'strategic_plan_gw{args.gw}_{start_time.strftime("%Y%m%d_%H%M%S")}.json'
            with open(json_file, 'w') as f:
                json.dump(plan, f, indent=2)

            print(f"\n📄 Report saved to: {report_file}")
            print(f"📄 JSON saved to: {json_file}")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("PLANNING COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print("")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nPlanning cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
