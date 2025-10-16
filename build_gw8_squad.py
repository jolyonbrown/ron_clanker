#!/usr/bin/env python3
"""
Build Ron Clanker's GW8 Squad

Fresh £100m budget. 6 gameweeks of data analyzed. Time to build a winner.

Strategy:
1. Load DC analysis from GW1-7
2. Select 3-5 high-value DC defenders
3. Select 2-3 defensive midfielders for DC points
4. Add premium attacking assets (Haaland, Salah, etc.)
5. Fill remaining positions with value picks
6. Validate with Rules Engine
7. Output 15-player squad + formation
"""

import asyncio
import json
from typing import List, Dict, Any
from agents.data_collector import DataCollector
from agents.rules_engine import RulesEngine


async def build_gw8_squad():
    """Build Ron's optimal GW8 squad."""
    print("=" * 80)
    print("RON CLANKER - GW8 SQUAD BUILDER")
    print("Building the foundation. Fresh start. £100m to spend.")
    print("=" * 80)

    collector = DataCollector()
    rules = RulesEngine()

    try:
        # Load analysis data
        print("\n📊 Loading GW1-7 DC analysis...")
        with open('data/gw1_7_dc_analysis.json', 'r') as f:
            analysis = json.load(f)

        print(f"✅ Analysis loaded from {analysis['analyzed_gameweeks']}")

        # Fetch current player data
        print("\n📡 Fetching latest FPL data...")
        data = await collector.update_all_data()
        all_players = data['players']
        teams_data = data['teams']

        # Create player lookup
        player_lookup = {p['id']: p for p in all_players}

        print(f"✅ {len(all_players)} players loaded\n")

        # Build squad systematically
        squad = []
        budget_used = 0
        budget_total = 1000  # £100.0m

        print("=" * 80)
        print("SQUAD CONSTRUCTION - RON'S WAY")
        print("=" * 80)

        # ====================================================================
        # GOALKEEPERS - 2 required
        # ====================================================================
        print("\n🧤 GOALKEEPERS (selecting 2)...")
        print("-" * 80)

        gks = [p for p in all_players if p['element_type'] == 1 and p['status'] == 'a']
        gks_sorted = sorted(gks, key=lambda x: x['total_points'], reverse=True)

        # Pick one premium, one budget
        gk1 = next(p for p in gks_sorted if 50 <= p['now_cost'] <= 60)  # £5.0-6.0m
        gk2 = next(p for p in gks_sorted if 40 <= p['now_cost'] <= 48 and p['id'] != gk1['id'])  # Budget

        for gk in [gk1, gk2]:
            squad.append(gk)
            budget_used += gk['now_cost']
            team_name = teams_data[gk['team'] - 1]['short_name']
            print(f"  ✓ {gk['web_name']:<15} ({team_name:<4}) £{gk['now_cost']/10:.1f}m - {gk['total_points']} pts")

        # ====================================================================
        # DEFENDERS - 5 required (3-4 starters with high DC potential)
        # ====================================================================
        print("\n🛡️  DEFENDERS (selecting 5 - DC SPECIALISTS)...")
        print("-" * 80)

        # Use top DC defenders from analysis
        target_defenders = [
            ('J.Timber', 'ARS'),
            ('Gabriel', 'ARS'),
            ('Senesi', 'BOU'),
            ('Guéhi', 'CRY'),
            ('Burn', 'NEW'),
        ]

        defenders_added = 0
        for name, team_short in target_defenders:
            if defenders_added >= 5:
                break

            # Find player
            defender = next(
                (p for p in all_players
                 if p['web_name'] == name and
                 teams_data[p['team'] - 1]['short_name'] == team_short and
                 p['status'] == 'a'),
                None
            )

            if defender:
                # Check team limit (max 3 from same team)
                team_count = sum(1 for p in squad if p['team'] == defender['team'])
                if team_count >= 3:
                    print(f"  ⚠️  {name} skipped (3 {team_short} players already)")
                    continue

                squad.append(defender)
                budget_used += defender['now_cost']
                defenders_added += 1
                team_name = teams_data[defender['team'] - 1]['short_name']
                print(f"  ✓ {defender['web_name']:<15} ({team_name:<4}) £{defender['now_cost']/10:.1f}m - {defender['total_points']} pts")

        # ====================================================================
        # MIDFIELDERS - 5 required (mix of DC specialists and attackers)
        # ====================================================================
        print("\n⚡ MIDFIELDERS (selecting 5)...")
        print("-" * 80)

        # RON'S STRATEGY: No premium mids - spread budget across DC specialists
        # Haaland + balanced squad with DC focus
        midfielders_added = 0

        mids = [p for p in all_players if p['element_type'] == 3 and p['status'] == 'a']
        mids_by_points = sorted(mids, key=lambda x: x['total_points'], reverse=True)

        # Get one good attacking mid (£7-9m range)
        mid_tier_mids = [
            p for p in mids_by_points
            if 70 <= p['now_cost'] <= 90 and p['total_points'] >= 20
        ]

        if mid_tier_mids:
            mid = mid_tier_mids[0]
            team_count = sum(1 for p in squad if p['team'] == mid['team'])
            if team_count < 3:
                squad.append(mid)
                budget_used += mid['now_cost']
                midfielders_added += 1
                team_name = teams_data[mid['team'] - 1]['short_name']
                print(f"  ✓ {mid['web_name']:<15} ({team_name:<4}) £{mid['now_cost']/10:.1f}m - {mid['total_points']} pts")

        # Add DC defensive midfielders
        dc_mid_targets = ['Caicedo', 'Rice', 'Gravenberch']

        for target_name in dc_mid_targets:
            if midfielders_added >= 5:
                break

            mid = next(
                (p for p in mids if target_name in p['web_name'] and p['status'] == 'a'),
                None
            )

            if mid and mid['now_cost'] <= (budget_total - budget_used):
                team_count = sum(1 for p in squad if p['team'] == mid['team'])
                if team_count >= 3:
                    continue

                squad.append(mid)
                budget_used += mid['now_cost']
                midfielders_added += 1
                team_name = teams_data[mid['team'] - 1]['short_name']
                print(f"  ✓ {mid['web_name']:<15} ({team_name:<4}) £{mid['now_cost']/10:.1f}m - {mid['total_points']} pts [DC]")

        # Fill remaining spots with budget options
        while midfielders_added < 5:
            budget_mids = [
                p for p in mids
                if p['now_cost'] <= 55 and
                p['total_points'] >= 15 and
                p['id'] not in [s['id'] for s in squad]
            ]

            if not budget_mids:
                break

            budget_mids_sorted = sorted(budget_mids, key=lambda x: x['total_points'] / (x['now_cost']/10), reverse=True)
            mid = budget_mids_sorted[0]

            team_count = sum(1 for p in squad if p['team'] == mid['team'])
            if team_count >= 3:
                budget_mids_sorted = budget_mids_sorted[1:]
                if not budget_mids_sorted:
                    break
                mid = budget_mids_sorted[0]

            squad.append(mid)
            budget_used += mid['now_cost']
            midfielders_added += 1
            team_name = teams_data[mid['team'] - 1]['short_name']
            print(f"  ✓ {mid['web_name']:<15} ({team_name:<4}) £{mid['now_cost']/10:.1f}m - {mid['total_points']} pts [Budget]")

        # ====================================================================
        # FORWARDS - 3 required
        # ====================================================================
        print("\n⚽ FORWARDS (selecting 3)...")
        print("-" * 80)

        fwds = [p for p in all_players if p['element_type'] == 4 and p['status'] == 'a']
        fwds_by_points = sorted(fwds, key=lambda x: x['total_points'], reverse=True)

        # Haaland is non-negotiable
        haaland = next((p for p in fwds_by_points if 'Haaland' in p['web_name']), None)
        if haaland and haaland['now_cost'] <= (budget_total - budget_used):
            squad.append(haaland)
            budget_used += haaland['now_cost']
            team_name = teams_data[haaland['team'] - 1]['short_name']
            print(f"  ✓ {haaland['web_name']:<15} ({team_name:<4}) £{haaland['now_cost']/10:.1f}m - {haaland['total_points']} pts [C]")

        # Add one more decent forward
        fwd_targets = ['Watkins', 'Isak', 'Jackson', 'Solanke', 'Wood']

        forwards_added = 1  # Already have Haaland
        for target_name in fwd_targets:
            if forwards_added >= 2:
                break

            fwd = next(
                (p for p in fwds_by_points if target_name in p['web_name'] and p['id'] != haaland['id']),
                None
            )

            if fwd and fwd['now_cost'] <= (budget_total - budget_used):
                team_count = sum(1 for p in squad if p['team'] == fwd['team'])
                if team_count >= 3:
                    continue

                squad.append(fwd)
                budget_used += fwd['now_cost']
                forwards_added += 1
                team_name = teams_data[fwd['team'] - 1]['short_name']
                print(f"  ✓ {fwd['web_name']:<15} ({team_name:<4}) £{fwd['now_cost']/10:.1f}m - {fwd['total_points']} pts")

        # Need more forwards - be more flexible with budget
        while forwards_added < 3:
            remaining_budget = budget_total - budget_used
            available_fwds = [
                p for p in fwds
                if p['now_cost'] <= remaining_budget and
                p['id'] not in [s['id'] for s in squad] and
                p['total_points'] >= 3
            ]

            if not available_fwds:
                # Emergency: grab cheapest available
                available_fwds = [
                    p for p in fwds
                    if p['now_cost'] <= remaining_budget and
                    p['id'] not in [s['id'] for s in squad]
                ]

            if not available_fwds:
                print(f"  ⚠️  WARNING: Cannot find {3 - forwards_added} more forward(s) within budget!")
                break

            # Sort by value
            available_fwds_sorted = sorted(
                available_fwds,
                key=lambda x: x['total_points'] / (x['now_cost']/10),
                reverse=True
            )

            fwd = available_fwds_sorted[0]

            # Check team limit
            team_count = sum(1 for p in squad if p['team'] == fwd['team'])
            if team_count >= 3:
                # Try next option
                available_fwds_sorted = [f for f in available_fwds_sorted if f['team'] != fwd['team']]
                if not available_fwds_sorted:
                    print(f"  ⚠️  WARNING: Cannot find forward within team limits!")
                    break
                fwd = available_fwds_sorted[0]

            squad.append(fwd)
            budget_used += fwd['now_cost']
            forwards_added += 1
            team_name = teams_data[fwd['team'] - 1]['short_name']
            tag = "[Bench]" if forwards_added == 3 else ""
            print(f"  ✓ {fwd['web_name']:<15} ({team_name:<4}) £{fwd['now_cost']/10:.1f}m - {fwd['total_points']} pts {tag}")

        # ====================================================================
        # VALIDATION
        # ====================================================================
        print("\n" + "=" * 80)
        print("VALIDATION")
        print("=" * 80)

        is_valid, errors = rules.validate_squad(squad, budget_total)

        print(f"\nSquad Size: {len(squad)}/15")
        print(f"Budget Used: £{budget_used/10:.1f}m / £{budget_total/10:.1f}m")
        print(f"Budget Remaining: £{(budget_total - budget_used)/10:.1f}m")

        if is_valid:
            print("\n✅ SQUAD IS VALID!")
        else:
            print("\n❌ SQUAD HAS ERRORS:")
            for error in errors:
                print(f"  - {error.message}")

        # ====================================================================
        # FINAL SQUAD OUTPUT
        # ====================================================================
        print("\n" + "=" * 80)
        print("RON'S GW8 SQUAD - FINAL SELECTION")
        print("=" * 80)

        position_names = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
        for pos_code in [1, 2, 3, 4]:
            position_players = [p for p in squad if p['element_type'] == pos_code]
            print(f"\n{position_names[pos_code]}:")
            for p in position_players:
                team_name = teams_data[p['team'] - 1]['short_name']
                print(f"  {p['web_name']:<15} ({team_name:<4}) £{p['now_cost']/10:.1f}m")

        # Save squad
        squad_data = {
            'gameweek': 8,
            'squad': [
                {
                    'id': p['id'],
                    'name': p['web_name'],
                    'team': teams_data[p['team'] - 1]['short_name'],
                    'position': p['element_type'],
                    'price': p['now_cost'] / 10,
                    'total_points_so_far': p['total_points']
                }
                for p in squad
            ],
            'total_cost': budget_used / 10,
            'budget_remaining': (budget_total - budget_used) / 10,
            'formation': '4-4-2',  # Default, can be adjusted
            'captain': 'Haaland',
            'vice_captain': 'Salah'
        }

        with open('data/gw8_squad.json', 'w') as f:
            json.dump(squad_data, f, indent=2)

        print(f"\n✅ Squad saved to: data/gw8_squad.json")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error building squad: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(build_gw8_squad())
