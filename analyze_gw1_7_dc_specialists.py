#!/usr/bin/env python3
"""
Analyze GW1-7 Performance Data to Identify Defensive Contribution Specialists

This script exploits Ron's fresh GW8 entry by analyzing 6 gameweeks of REAL data
to identify players consistently earning Defensive Contribution (DC) points.

2025/26 DC Rules:
- Defenders: 1 pt for every 5 combined blocks + interceptions + tackles (CBI+T)
- Midfielders: 1 pt for every 6 combined CBI + tackles + recoveries (CBI+T+R)

This is the market inefficiency Ron can exploit!
"""

import asyncio
import json
from typing import Dict, List, Any
from collections import defaultdict
from agents.data_collector import DataCollector


async def analyze_dc_specialists():
    """Analyze GW1-7 data to find consistent DC earners."""
    print("=" * 80)
    print("RON CLANKER'S GW1-7 DEFENSIVE CONTRIBUTION ANALYSIS")
    print("Analyzing 6 gameweeks of REAL data to identify DC specialists...")
    print("=" * 80)

    collector = DataCollector()

    try:
        # Fetch all data
        print("\n📊 Fetching FPL data...")
        data = await collector.update_all_data()

        players = data['players']
        current_gw = data['current_gameweek']['id']

        print(f"✅ Data loaded: {len(players)} players, Current GW: {current_gw}")
        print(f"   Analyzing GW1-{current_gw} performance...\n")

        # We need detailed player data to get gameweek-by-gameweek stats
        # The FPL API doesn't provide CBI/Tackles in bootstrap, so we'll use
        # a proxy: players with high BPS (Bonus Point System) relative to goals/assists
        # typically have strong defensive stats

        print("=" * 80)
        print("PHASE 1: IDENTIFYING DEFENDERS WITH HIGH DEFENSIVE FLOORS")
        print("=" * 80)

        defenders = collector.filter_players_by_position(players, 2)
        available_defenders = collector.filter_available_players(defenders)

        # Sort by total points (proxy for consistency until we get detailed stats)
        defenders_by_points = sorted(
            available_defenders,
            key=lambda x: x.get('total_points', 0),
            reverse=True
        )

        print(f"\nTop 20 Defenders by Total Points (GW1-{current_gw}):\n")
        print(f"{'Rank':<5} {'Name':<20} {'Team':<15} {'Price':<8} {'Pts':<5} {'Mins':<6} {'CS':<4} {'BPS':<5}")
        print("-" * 80)

        defender_candidates = []
        for i, player in enumerate(defenders_by_points[:20], 1):
            name = player['web_name']
            team = data['teams'][player['team'] - 1]['short_name']
            price = f"£{player['now_cost'] / 10:.1f}m"
            points = player['total_points']
            minutes = player['minutes']
            clean_sheets = player['clean_sheets']
            bps = player['bps']

            # Calculate points per 90 minutes
            if minutes > 0:
                pts_per_90 = (points / minutes) * 90
            else:
                pts_per_90 = 0

            print(f"{i:<5} {name:<20} {team:<15} {price:<8} {points:<5} {minutes:<6} {clean_sheets:<4} {bps:<5}")

            # High-floor defenders: significant minutes, decent points
            if minutes >= 450 and points >= 30:  # 5+ full games, 30+ points
                defender_candidates.append({
                    'name': name,
                    'id': player['id'],
                    'team': team,
                    'price': player['now_cost'] / 10,
                    'points': points,
                    'minutes': minutes,
                    'clean_sheets': clean_sheets,
                    'bps': bps,
                    'pts_per_90': pts_per_90
                })

        print("\n" + "=" * 80)
        print("PHASE 2: IDENTIFYING MIDFIELDERS WITH HIGH DEFENSIVE WORK RATE")
        print("=" * 80)

        midfielders = collector.filter_players_by_position(players, 3)
        available_midfielders = collector.filter_available_players(midfielders)

        # For midfielders, we want those with HIGH BPS relative to their goals/assists
        # This indicates defensive work
        midfield_candidates = []

        for player in available_midfielders:
            goals = player.get('goals_scored', 0)
            assists = player.get('assists', 0)
            bps = player.get('bps', 0)
            minutes = player.get('minutes', 0)
            points = player.get('total_points', 0)

            if minutes < 450:  # Need meaningful sample
                continue

            # Calculate BPS not from goals/assists (proxy for defensive work)
            # Rough estimate: goal = ~30 BPS, assist = ~20 BPS
            attacking_bps = (goals * 30) + (assists * 20)
            defensive_bps = max(0, bps - attacking_bps)

            if defensive_bps > 50:  # Significant defensive contribution
                midfield_candidates.append({
                    'name': player['web_name'],
                    'id': player['id'],
                    'team': data['teams'][player['team'] - 1]['short_name'],
                    'price': player['now_cost'] / 10,
                    'points': points,
                    'minutes': minutes,
                    'goals': goals,
                    'assists': assists,
                    'bps': bps,
                    'defensive_bps': defensive_bps,
                    'pts_per_90': (points / minutes) * 90 if minutes > 0 else 0
                })

        # Sort by defensive BPS
        midfield_candidates.sort(key=lambda x: x['defensive_bps'], reverse=True)

        print(f"\nTop 15 Midfielders by Defensive BPS (proxy for DC work):\n")
        print(f"{'Rank':<5} {'Name':<20} {'Team':<12} {'Price':<8} {'Pts':<5} {'G':<3} {'A':<3} {'dBPS':<6}")
        print("-" * 80)

        for i, player in enumerate(midfield_candidates[:15], 1):
            print(
                f"{i:<5} {player['name']:<20} {player['team']:<12} "
                f"£{player['price']:<7.1f} {player['points']:<5} "
                f"{player['goals']:<3} {player['assists']:<3} {player['defensive_bps']:<6.0f}"
            )

        print("\n" + "=" * 80)
        print("PHASE 3: RON'S RECOMMENDATIONS - DC SPECIALISTS FOR GW8")
        print("=" * 80)

        print("\n🎯 HIGH-PRIORITY DEFENSIVE CONTRIBUTORS:\n")

        print("DEFENDERS (Target: 3-5 in starting XI):")
        print("-" * 80)
        for i, player in enumerate(defender_candidates[:10], 1):
            value = player['points'] / player['price'] if player['price'] > 0 else 0
            print(
                f"  {i}. {player['name']:<18} ({player['team']:<10}) "
                f"£{player['price']:.1f}m - {player['points']} pts "
                f"({player['clean_sheets']} CS, {value:.1f} pts/£m)"
            )

        print("\nMIDFIELDERS (Target: 2-3 defensive-minded in squad):")
        print("-" * 80)
        for i, player in enumerate(midfield_candidates[:8], 1):
            value = player['points'] / player['price'] if player['price'] > 0 else 0
            print(
                f"  {i}. {player['name']:<18} ({player['team']:<10}) "
                f"£{player['price']:.1f}m - {player['points']} pts "
                f"({value:.1f} pts/£m, dBPS: {player['defensive_bps']:.0f})"
            )

        print("\n" + "=" * 80)
        print("RON'S STRATEGIC INSIGHT:")
        print("=" * 80)
        print("""
The market is still pricing these players on last season's goals and assists.
But with the new DC rules, players with high defensive actions have a FLOOR of
2 points per game BEFORE clean sheets, goals, or assists.

This is where we gain an edge. While everyone chases last week's hat-trick hero,
we're building a team with consistent 2-point earners who can spike to 6-10 points.

Foundation first. Fancy stuff second.

- Ron
        """)

        # Save analysis results
        analysis = {
            'analyzed_gameweeks': f"GW1-{current_gw}",
            'analysis_date': str(data['updated_at']),
            'defender_candidates': defender_candidates[:15],
            'midfielder_candidates': midfield_candidates[:10],
        }

        with open('data/gw1_7_dc_analysis.json', 'w') as f:
            json.dump(analysis, f, indent=2, default=str)

        print("\n✅ Analysis saved to: data/gw1_7_dc_analysis.json")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(analyze_dc_specialists())
