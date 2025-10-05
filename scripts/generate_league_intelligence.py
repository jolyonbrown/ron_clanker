#!/usr/bin/env python3
"""
Weekly League Intelligence Report

Generates Ron's Monday morning intelligence brief on the mini-league.
Combines data from all staff members for competitive decision-making.

Usage:
    python scripts/generate_league_intelligence.py --league 160968
    python scripts/generate_league_intelligence.py --league 160968 --save
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from datetime import datetime
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def load_config():
    """Load Ron's config"""
    config_file = project_root / 'config' / 'ron_config.json'
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {}


def fetch_all_data(league_id):
    """Fetch all required data"""
    print("📥 Gathering intelligence...")

    # Bootstrap data
    bootstrap = requests.get(f"{FPL_BASE_URL}/bootstrap-static/").json()

    # League data
    league = requests.get(
        f"{FPL_BASE_URL}/leagues-classic/{league_id}/standings/"
    ).json()

    return bootstrap, league


def generate_intelligence_report(league_id, bootstrap, league_data, ron_team_id=None):
    """Generate comprehensive intelligence report"""

    current_gw = next(e['id'] for e in bootstrap['events'] if e['is_current'])
    gws_remaining = 38 - current_gw + 1
    standings = league_data['standings']['results']
    league_info = league_data['league']

    report_lines = []

    # Header
    report_lines.append("=" * 100)
    report_lines.append("WEEKLY LEAGUE INTELLIGENCE BRIEF")
    report_lines.append("=" * 100)
    report_lines.append(f"League: {league_info['name']}")
    report_lines.append(f"Date: {datetime.now().strftime('%A, %d %B %Y')}")
    report_lines.append(f"Current Gameweek: {current_gw}")
    report_lines.append(f"Gameweeks Remaining: {gws_remaining}")
    report_lines.append("=" * 100)

    # MAGGIE - League Table Analysis
    report_lines.append("\n" + "=" * 100)
    report_lines.append("📊 MAGGIE'S LEAGUE TABLE ANALYSIS")
    report_lines.append("=" * 100)

    leader = standings[0]
    report_lines.append(f"\n🏆 LEADER: {leader['player_name']} ({leader['entry_name']})")
    report_lines.append(f"   Total: {leader['total']} pts | Last GW: {leader['event_total']} pts")

    report_lines.append(f"\n📈 TOP 5:")
    for team in standings[:5]:
        gap = team['total'] - leader['total']
        gap_str = f"{gap:+d}" if gap != 0 else "LEADER"
        report_lines.append(f"   {team['rank']}. {team['player_name']:25s} {team['total']:4d} pts ({gap_str:>7s})")

    if ron_team_id:
        ron_team = next((t for t in standings if t['entry'] == ron_team_id), None)
        if ron_team:
            report_lines.append(f"\n🤖 RON'S POSITION: {ron_team['rank']}/{len(standings)}")
            report_lines.append(f"   Total: {ron_team['total']} pts")
            report_lines.append(f"   Gap to leader: {ron_team['total'] - leader['total']:+d} pts")

    avg_total = sum(t['total'] for t in standings) / len(standings)
    avg_gw = sum(t['event_total'] for t in standings) / len(standings)
    report_lines.append(f"\n📊 LEAGUE AVERAGES:")
    report_lines.append(f"   Total: {avg_total:.1f} pts")
    report_lines.append(f"   Last GW: {avg_gw:.1f} pts")

    # TERRY - Chip Intelligence
    report_lines.append("\n" + "=" * 100)
    report_lines.append("🎴 TERRY'S CHIP INTELLIGENCE")
    report_lines.append("=" * 100)

    chip_usage = defaultdict(list)
    chips_remaining = {}

    for team in standings:
        try:
            history = requests.get(f"{FPL_BASE_URL}/entry/{team['entry']}/history/").json()
            chips = history.get('chips', [])

            for chip in chips:
                chip_usage[chip['name']].append({
                    'manager': team['player_name'],
                    'gameweek': chip['event'],
                    'rank': team['rank']
                })

            # Calculate remaining chips
            used_chips = {c['name'] for c in chips}
            remaining = 8 - len(chips)  # Simplified - assumes 8 total
            chips_remaining[team['player_name']] = {
                'remaining': remaining,
                'used': list(used_chips)
            }
        except:
            pass

    report_lines.append("\n🎯 CHIPS USED SO FAR:")
    for chip_name in ['wildcard', 'bboost', 'freehit', '3xc']:
        if chip_name in chip_usage:
            users = chip_usage[chip_name]
            report_lines.append(f"\n{chip_name.upper()}: {len(users)} teams")
            for u in sorted(users, key=lambda x: x['rank'])[:5]:
                report_lines.append(f"   - {u['manager']} (Rank {u['rank']}) - GW{u['gameweek']}")

    report_lines.append("\n📋 TOP 5 CHIPS REMAINING:")
    top_5_chips = [(name, data) for name, data in chips_remaining.items()]
    top_5_chips.sort(key=lambda x: standings.index(
        next(t for t in standings if t['player_name'] == x[0])
    ))
    for name, data in top_5_chips[:5]:
        team_rank = next(t['rank'] for t in standings if t['player_name'] == name)
        report_lines.append(f"   Rank {team_rank}: {name} - {data['remaining']}/8 chips left")

    # ELLIE - Catch-Up Scenarios
    report_lines.append("\n" + "=" * 100)
    report_lines.append("🎯 ELLIE'S CATCH-UP ANALYSIS")
    report_lines.append("=" * 100)

    if ron_team_id:
        ron_team = next((t for t in standings if t['entry'] == ron_team_id), None)
        if ron_team:
            gap = leader['total'] - ron_team['total']
            pts_per_gw_needed = gap / gws_remaining if gws_remaining > 0 else 0

            report_lines.append(f"\n📊 CURRENT SITUATION:")
            report_lines.append(f"   Ron's points: {ron_team['total']}")
            report_lines.append(f"   Leader's points: {leader['total']}")
            report_lines.append(f"   Gap: {gap} pts")
            report_lines.append(f"   GWs remaining: {gws_remaining}")
            report_lines.append(f"   Points/GW advantage needed: +{pts_per_gw_needed:.1f}")

            report_lines.append(f"\n🎲 SCENARIOS:")
            gws_played = current_gw
            leader_avg = leader['total'] / gws_played
            ron_avg = ron_team['total'] / gws_played if gws_played > 0 else 0

            for ron_future_avg in [60, 65, 70, 75, 80]:
                ron_final = ron_team['total'] + (ron_future_avg * gws_remaining)
                leader_final = leader['total'] + (leader_avg * gws_remaining)
                margin = ron_final - leader_final

                outcome = "🏆 WINS" if margin > 0 else "📉 LOSES"
                report_lines.append(f"   Ron @ {ron_future_avg} pts/GW: {ron_final:.0f} vs {leader_final:.0f} = {outcome}")
    else:
        # Ron entering fresh
        report_lines.append(f"\n📊 RON ENTERING AT GW{current_gw + 1}:")
        report_lines.append(f"   Leader: {leader['total']} pts")
        report_lines.append(f"   GWs remaining for Ron: {gws_remaining}")

        leader_avg = leader['total'] / current_gw
        report_lines.append(f"\n🎲 SCENARIOS:")
        for ron_avg in [60, 65, 70, 75, 80]:
            ron_final = ron_avg * gws_remaining
            leader_final = leader['total'] + (leader_avg * gws_remaining)
            margin = ron_final - leader_final

            outcome = "🏆 WINS" if margin > 0 else "📉 LOSES"
            report_lines.append(f"   Ron @ {ron_avg} pts/GW: {ron_final:.0f} vs {leader_final:.0f} = {outcome}")

    # RON'S VERDICT
    report_lines.append("\n" + "=" * 100)
    report_lines.append("💬 THE GAFFER'S VERDICT")
    report_lines.append("=" * 100)

    if ron_team_id:
        ron_team = next((t for t in standings if t['entry'] == ron_team_id), None)
        if ron_team:
            if ron_team['rank'] == 1:
                report_lines.append("\nTop of the league. That's where we belong.")
                report_lines.append("But it's a marathon, not a sprint. Stay focused.")
            elif ron_team['rank'] <= 3:
                report_lines.append(f"\nRank {ron_team['rank']}. In touching distance of the top.")
                report_lines.append("Keep grinding. The DC strategy will deliver over time.")
            else:
                gap = leader['total'] - ron_team['total']
                report_lines.append(f"\nRank {ron_team['rank']}. {gap} points behind.")
                report_lines.append("Long way to go, but that's fine. We play the long game.")

            # Chip strategy
            if chips_remaining.get(ron_team['player_name'], {}).get('remaining', 0) > 6:
                report_lines.append("\nGood news: We've got all our chips. Use them wisely.")
        else:
            report_lines.append("\nNot in the league yet - that's the plan.")
    else:
        report_lines.append("\nEntering fresh. Clean slate. £100m to work with.")
        report_lines.append("Everyone else has played 7 gameweeks. We've got 31 to catch them.")
        report_lines.append(f"Leader's on {leader['total']} points. That's {leader['total']/current_gw:.1f} per week.")
        report_lines.append("We beat that average, we win. Simple maths.")

    report_lines.append("\n" + "=" * 100)

    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly league intelligence report")
    parser.add_argument('--league', type=int, required=True,
                       help='Mini-league ID')
    parser.add_argument('--save', action='store_true',
                       help='Save report to file')

    args = parser.parse_args()

    try:
        # Load data
        config = load_config()
        ron_team_id = config.get('team_id')

        bootstrap, league_data = fetch_all_data(args.league)

        # Generate report
        report = generate_intelligence_report(args.league, bootstrap, league_data, ron_team_id)

        # Display
        print(report)

        # Save if requested
        if args.save:
            output_dir = project_root / 'data' / 'league_intelligence'
            output_dir.mkdir(parents=True, exist_ok=True)

            current_gw = next(e['id'] for e in bootstrap['events'] if e['is_current'])
            timestamp = datetime.now().strftime('%Y%m%d')
            output_file = output_dir / f'league_{args.league}_gw{current_gw}_{timestamp}.txt'

            with open(output_file, 'w') as f:
                f.write(report)

            print(f"\n💾 Intelligence report saved to: {output_file}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
