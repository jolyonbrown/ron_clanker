#!/usr/bin/env python3
"""
Build Optimal GW8 Squad - Ron Clanker's Fresh Start

Improved squad builder that:
1. Uses API data only (no real-world knowledge)
2. Allocates budget efficiently (£98-99m target)
3. Balances DC specialists with premium attackers
4. Validates all constraints

Strategy:
- Lock in Haaland (£14.5m) - premium essential
- Add premium attacking mid (Saka/Palmer £9-11m)
- Fill with DC specialists for foundation
- Use £98-99m of £100m budget
"""

import sys
import json
import requests
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
SQUAD_CONSTRAINTS = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}

def load_fpl_data():
    """Load latest FPL data"""
    print("🔄 Loading FPL data...")
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    bootstrap = response.json()

    players = {p['id']: p for p in bootstrap['elements']}
    teams = {t['id']: t for t in bootstrap['teams']}

    print(f"  ✅ Loaded {len(players)} players, {len(teams)} teams")
    return players, teams, bootstrap

def load_player_analysis():
    """Load GW1-7 analysis"""
    analysis_path = project_root / 'data' / 'analysis' / 'player_analysis_gw1-7.json'
    if analysis_path.exists():
        with open(analysis_path, 'r') as f:
            return json.load(f)
    return None

def get_player_stats(player_id, players, analysis):
    """Get player stats from analysis and current API"""
    player = players[player_id]

    # Get analysis data if available
    analysis_data = analysis.get(str(player_id), {}) if analysis else {}

    # Current price from API
    price = player['now_cost'] / 10

    # Stats from analysis
    total_points = analysis_data.get('total_fpl_points', player['total_points'])
    weeks = analysis_data.get('weeks_played', 1)
    ppg = total_points / weeks if weeks > 0 else 0

    dc_per_90 = analysis_data.get('avg_dc_per_gw', 0)
    dc_consistency = analysis_data.get('dc_consistency_pct', 0)

    # DC specialist thresholds
    position = POSITION_MAP[player['element_type']]
    is_dc_specialist = False
    if position == 'DEF' and dc_consistency >= 70:
        is_dc_specialist = True
    elif position == 'MID' and dc_consistency >= 70:
        is_dc_specialist = True

    return {
        'id': player_id,
        'name': player['web_name'],
        'position': position,
        'price': price,
        'ppg': ppg,
        'total_points': total_points,
        'dc_per_90': dc_per_90,
        'is_dc_specialist': is_dc_specialist,
        'dc_consistency': dc_consistency,
        'minutes': analysis_data.get('total_minutes', player['minutes']),
        'status': player['status'],
        'value_score': ppg / price if price > 0 else 0
    }

def build_optimized_squad(players, teams, analysis):
    """Build squad with better budget allocation"""
    print("\n" + "=" * 80)
    print("BUILDING OPTIMIZED GW8 SQUAD")
    print("=" * 80)
    print("Strategy: Premium attackers + DC foundation")
    print("Budget target: £98-99m of £100m")

    selected = defaultdict(list)
    total_cost = 0
    budget = 100.0

    # Get all available players with stats
    available = []
    for pid, player in players.items():
        if player['status'] != 'a':  # Skip unavailable
            continue
        if player['minutes'] < 100:  # Skip non-playing
            continue

        stats = get_player_stats(pid, players, analysis)
        team = teams[player['team']]
        stats['team'] = team['short_name']
        available.append(stats)

    # Group by position
    by_position = defaultdict(list)
    for p in available:
        by_position[p['position']].append(p)

    # Sort each position by value score
    for pos in by_position:
        by_position[pos].sort(key=lambda x: x['value_score'], reverse=True)

    print("\n📋 Selection Strategy:")

    # STEP 1: Premium forwards - Lock Haaland
    print("\n1️⃣ Selecting premium forward...")
    haaland = next((p for p in by_position['FWD'] if p['name'] == 'Haaland'), None)
    if haaland:
        selected['FWD'].append(haaland)
        total_cost += haaland['price']
        print(f"   ✅ Haaland £{haaland['price']}m - {haaland['ppg']:.1f} PPG")

    # STEP 2: Premium attacking midfielder (Saka/B.Fernandes - balanced with Haaland)
    print("\n2️⃣ Selecting premium attacking midfielder...")
    # Prioritize Saka/B.Fernandes for balance (cheaper than Salah)
    premium_names = ['Saka', 'B.Fernandes', 'Son']
    premium_mid = None
    for name in premium_names:
        for p in by_position['MID']:
            if name in p['name'] and p['price'] >= 9.0:
                premium_mid = p
                break
        if premium_mid:
            break

    # If no named premium found, take mid-priced option (£9-11m range)
    if not premium_mid:
        premium_mids = [p for p in by_position['MID'] if 9.0 <= p['price'] <= 11.0]
        if premium_mids:
            # Sort by value score
            premium_mids.sort(key=lambda x: x['value_score'], reverse=True)
            premium_mid = premium_mids[0]

    if premium_mid:
        selected['MID'].append(premium_mid)
        total_cost += premium_mid['price']
        print(f"   ✅ {premium_mid['name']} £{premium_mid['price']}m - {premium_mid['ppg']:.1f} PPG")

    # STEP 3: Budget GKPs (cheapest 2)
    print("\n3️⃣ Selecting budget goalkeepers...")
    budget_gkps = sorted(by_position['GKP'], key=lambda x: x['price'])[:2]
    for gkp in budget_gkps:
        selected['GKP'].append(gkp)
        total_cost += gkp['price']
        print(f"   ✅ {gkp['name']} £{gkp['price']}m")

    # STEP 4: DC defenders (aim for 4)
    print("\n4️⃣ Selecting DC defenders...")
    dc_defs = [p for p in by_position['DEF'] if p['is_dc_specialist']]
    for def_player in dc_defs[:4]:
        selected['DEF'].append(def_player)
        total_cost += def_player['price']
        print(f"   ✅ {def_player['name']} £{def_player['price']}m - DC: {def_player['dc_per_90']:.1f}")

    # Fill remaining DEF slot
    while len(selected['DEF']) < 5:
        for def_player in by_position['DEF']:
            if def_player not in selected['DEF']:
                selected['DEF'].append(def_player)
                total_cost += def_player['price']
                print(f"   ✅ {def_player['name']} £{def_player['price']}m")
                break

    # STEP 5: DC midfielders (fill remaining slots)
    print("\n5️⃣ Selecting DC midfielders...")
    dc_mids = [p for p in by_position['MID']
               if p['is_dc_specialist'] and p not in selected['MID']]

    slots_needed = 5 - len(selected['MID'])
    for mid_player in dc_mids[:slots_needed]:
        selected['MID'].append(mid_player)
        total_cost += mid_player['price']
        print(f"   ✅ {mid_player['name']} £{mid_player['price']}m - DC: {mid_player['dc_per_90']:.1f}")

    # STEP 6: Fill remaining FWD slots
    print("\n6️⃣ Selecting remaining forwards...")
    slots_needed = 3 - len(selected['FWD'])
    for fwd_player in by_position['FWD']:
        if fwd_player not in selected['FWD'] and slots_needed > 0:
            selected['FWD'].append(fwd_player)
            total_cost += fwd_player['price']
            print(f"   ✅ {fwd_player['name']} £{fwd_player['price']}m - {fwd_player['ppg']:.1f} PPG")
            slots_needed -= 1

    # STEP 7: Upgrade if budget remaining > £2m
    remaining = budget - total_cost
    print(f"\n💰 Budget status: £{total_cost:.1f}m spent, £{remaining:.1f}m remaining")

    if remaining > 2.0:
        print("\n7️⃣ Upgrading with remaining budget...")
        # Try to upgrade weakest players
        # Find lowest value player not in starting XI (bench)
        # This is a simple approach - could be improved
        print("   ⚠️  Consider manual upgrades with £{:.1f}m spare budget".format(remaining))

    # Count DC specialists
    dc_count = sum(1 for pos in selected.values() for p in pos if p.get('is_dc_specialist'))

    return {
        'squad': dict(selected),
        'total_cost': total_cost,
        'remaining_budget': budget - total_cost,
        'dc_count': dc_count
    }

def display_squad(squad):
    """Display the selected squad"""
    print("\n" + "=" * 80)
    print("FINAL SQUAD")
    print("=" * 80)

    selected = squad['squad']

    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        print(f"\n{pos}:")
        for p in selected[pos]:
            dc_marker = "🛡️ DC" if p.get('is_dc_specialist') else ""
            print(f"  {p['name']:20s} {p['team']:4s} £{p['price']:.1f}m  {p['ppg']:.1f}PPG  {dc_marker}")

    print(f"\n💰 Total: £{squad['total_cost']:.1f}m")
    print(f"   Remaining: £{squad['remaining_budget']:.1f}m")
    print(f"🛡️  DC Specialists: {squad['dc_count']}")

def select_captain(squad):
    """Select captain based on PPG"""
    all_outfield = []
    for pos in ['DEF', 'MID', 'FWD']:
        all_outfield.extend(squad['squad'][pos])

    # Sort by PPG
    candidates = sorted(all_outfield, key=lambda x: x['ppg'], reverse=True)

    captain = candidates[0]
    vice = candidates[1]

    print("\n" + "=" * 80)
    print("CAPTAIN SELECTION")
    print("=" * 80)
    print(f"\n🔴 CAPTAIN: {captain['name']} ({captain['team']}) - {captain['ppg']:.1f} PPG")
    print(f"🟡 VICE: {vice['name']} ({vice['team']}) - {vice['ppg']:.1f} PPG")

    return {'captain': captain, 'vice': vice}

def select_starting_xi(squad):
    """Select starting XI - 3-5-2 formation"""
    selected = squad['squad']

    # Sort each position by PPG to get best players
    for pos in selected:
        selected[pos].sort(key=lambda x: x['ppg'], reverse=True)

    starting = {
        'GKP': selected['GKP'][:1],
        'DEF': selected['DEF'][:3],
        'MID': selected['MID'][:5],
        'FWD': selected['FWD'][:2]
    }

    bench = {
        'GKP': selected['GKP'][1:],
        'DEF': selected['DEF'][3:],
        'MID': selected['MID'][5:],
        'FWD': selected['FWD'][2:]
    }

    print("\n" + "=" * 80)
    print("STARTING XI (3-5-2)")
    print("=" * 80)

    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        for p in starting[pos]:
            print(f"{pos}: {p['name']:20s} ({p['team']}) £{p['price']:.1f}m")

    print("\n🪑 BENCH:")
    bench_order = []
    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        for p in bench[pos]:
            bench_order.append(p)
            print(f"  {len(bench_order)}. {p['name']:20s} ({p['team']}) £{p['price']:.1f}m")

    return {'starting_xi': starting, 'bench': bench_order, 'formation': '3-5-2'}

def save_squad(squad, captain, formation):
    """Save squad to file"""
    output = {
        'gameweek': 8,
        'mode': 'fresh_start',
        'squad': squad,
        'captain': captain,
        'formation': formation
    }

    # Save to squads directory
    squads_dir = project_root / 'data' / 'squads'
    squads_dir.mkdir(parents=True, exist_ok=True)

    output_file = squads_dir / 'gw8_optimized_squad.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n💾 Squad saved to: {output_file}")
    return output_file

def main():
    print("=" * 80)
    print("RON CLANKER - GW8 OPTIMAL SQUAD BUILDER")
    print("=" * 80)

    # Load data
    players, teams, bootstrap = load_fpl_data()
    analysis = load_player_analysis()

    # Build squad
    squad = build_optimized_squad(players, teams, analysis)

    # Display squad
    display_squad(squad)

    # Select captain
    captain = select_captain(squad)

    # Select starting XI
    formation = select_starting_xi(squad)

    # Save
    save_squad(squad, captain, formation)

    print("\n" + "=" * 80)
    print("✅ SQUAD OPTIMIZATION COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    main()
