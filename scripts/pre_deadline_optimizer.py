#!/usr/bin/env python3
"""
Pre-Deadline Optimizer - Ron Clanker's Weekly Decision Engine

Runs 24-48 hours before each gameweek deadline to:
1. Refresh all analysis with latest data
2. Validate current squad (or select fresh for GW8)
3. Recommend transfers (GW9+)
4. Optimize captain selection
5. Set formation and bench order

Reusable every gameweek throughout the season.

Usage:
    # GW8 - Fresh start (select best 15 from £100m)
    python scripts/pre_deadline_optimizer.py --gw 8 --fresh-start

    # GW9+ - Standard mode (transfers from current squad)
    python scripts/pre_deadline_optimizer.py --gw 9

    # Override current squad state
    python scripts/pre_deadline_optimizer.py --gw 10 --free-transfers 2 --budget 1.5

    # Save recommendations
    python scripts/pre_deadline_optimizer.py --gw 8 --fresh-start --save
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
FORMATION_CONSTRAINTS = {
    "GKP": (1, 1),  # Exactly 1 GKP in starting XI
    "DEF": (3, 5),  # 3-5 defenders
    "MID": (2, 5),  # 2-5 midfielders
    "FWD": (1, 3),  # 1-3 forwards
}
SQUAD_CONSTRAINTS = {
    "GKP": 2,  # Total in squad of 15
    "DEF": 5,
    "MID": 5,
    "FWD": 3,
}


class PreDeadlineOptimizer:
    """Ron's weekly decision engine"""

    def __init__(self, gameweek: int, fresh_start: bool = False):
        self.gameweek = gameweek
        self.fresh_start = fresh_start
        self.bootstrap = None
        self.players = {}
        self.teams = {}
        self.current_squad = None
        self.budget = 100.0 if fresh_start else None
        self.free_transfers = 0 if fresh_start else 1

    def load_data(self):
        """Load all required data"""
        print(f"\n🔄 Loading latest FPL data for GW{self.gameweek}...")

        # Get bootstrap data
        print("  - Fetching bootstrap-static...")
        response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
        response.raise_for_status()
        self.bootstrap = response.json()

        # Build lookups
        self.players = {p['id']: p for p in self.bootstrap['elements']}
        self.teams = {t['id']: t for t in self.bootstrap['teams']}

        print(f"  - Loaded {len(self.players)} players, {len(self.teams)} teams")

        # Load current squad if not fresh start
        if not self.fresh_start:
            self._load_current_squad()

        # Load player analysis if available
        self._load_player_analysis()

    def _load_current_squad(self):
        """Load current squad from latest squad file or team API"""
        # Try to load from most recent squad file
        squad_dir = project_root / 'data' / 'squads'
        squad_files = sorted(squad_dir.glob('gw*_squad.json'), reverse=True)

        if squad_files:
            latest_squad = squad_files[0]
            print(f"  - Loading current squad from {latest_squad.name}")
            with open(latest_squad, 'r') as f:
                squad_data = json.load(f)
                self.current_squad = squad_data

                # Get budget info if available
                if 'budget' in squad_data:
                    self.budget = squad_data['budget'].get('remaining', 0)

        # TODO: In future, fetch from team API if team_id configured
        # config = self._load_config()
        # if config.get('team_id'):
        #     team_data = fetch_team_entry(config['team_id'])
        #     self.budget = team_data['last_deadline_bank'] / 10

    def _load_player_analysis(self):
        """Load pre-computed player analysis if available"""
        analysis_dir = project_root / 'data' / 'analysis'

        # Look for analysis covering gameweeks up to this one
        analysis_files = sorted(analysis_dir.glob('player_analysis_*.json'), reverse=True)

        if analysis_files:
            latest = analysis_files[0]
            print(f"  - Loading player analysis from {latest.name}")
            with open(latest, 'r') as f:
                self.player_analysis = json.load(f)
        else:
            print(f"  - No pre-computed analysis found, will analyze fresh")
            self.player_analysis = None

    def run_availability_check(self):
        """Check squad for injuries, suspensions, unavailability"""
        print("\n" + "=" * 80)
        print("AVAILABILITY CHECK")
        print("=" * 80)

        if self.fresh_start:
            print("\n✅ Fresh start mode - will select from all available players")
            return []

        if not self.current_squad:
            print("\n⚠️  No current squad loaded")
            return []

        issues = []

        # Flatten current squad
        all_players = []
        squad = self.current_squad.get('squad', {})
        for position_group in ['goalkeepers', 'defenders', 'midfielders', 'forwards']:
            if position_group in squad:
                all_players.extend(squad[position_group])

        print(f"\nChecking {len(all_players)} players...")

        for squad_player in all_players:
            player = self.players.get(squad_player['id'])
            if not player:
                continue

            status = player['status']
            news = player.get('news', '')
            chance_this = player.get('chance_of_playing_this_round')
            chance_next = player.get('chance_of_playing_next_round')

            is_flagged = (
                status != 'a' or
                news != '' or
                chance_this is not None
            )

            if is_flagged:
                team_name = self.teams[player['team']]['short_name']
                issues.append({
                    'player': player['web_name'],
                    'team': team_name,
                    'status': status,
                    'news': news,
                    'chance': chance_this
                })

                severity = {
                    'i': '🚑 INJURED',
                    's': '🟥 SUSPENDED',
                    'u': '❌ UNAVAILABLE',
                    'd': '⚠️  DOUBTFUL',
                    'a': '⚠️  CONCERN'
                }.get(status, '❓')

                print(f"{severity}: {player['web_name']} ({team_name}) - {news}")

        if not issues:
            print("✅ All squad players available - no flags")
        else:
            print(f"\n⚠️  {len(issues)} player(s) flagged for attention")

        return issues

    def analyze_fresh_start(self):
        """GW8 mode - select best 15 from scratch"""
        print("\n" + "=" * 80)
        print(f"FRESH START OPTIMIZATION - GW{self.gameweek}")
        print("=" * 80)
        print(f"Budget: £{self.budget}m")
        print(f"Constraint: 15 players (2 GKP, 5 DEF, 5 MID, 3 FWD)")
        print(f"Strategy: DC specialists + premium attackers")

        # Use existing player analysis if available
        if self.player_analysis:
            print("\n✅ Using pre-computed player analysis")
            # Convert dict-keyed analysis to list
            players_analyzed = self._convert_analysis_format(self.player_analysis)
        else:
            print("\n⏳ Running fresh player analysis...")
            # Use bootstrap data with basic scoring
            players_analyzed = self._quick_analyze_players()

        # Select best squad within budget and constraints
        print("\n🔍 Selecting optimal 15-player squad...")
        selected_squad = self._select_optimal_squad(players_analyzed)

        return selected_squad

    def analyze_standard_mode(self):
        """GW9+ mode - optimize from current squad with transfers"""
        print("\n" + "=" * 80)
        print(f"STANDARD MODE OPTIMIZATION - GW{self.gameweek}")
        print("=" * 80)
        print(f"Free Transfers: {self.free_transfers}")
        print(f"Budget: £{self.budget}m")

        if not self.current_squad:
            print("\n❌ No current squad available")
            print("Tip: Use --fresh-start for GW8 or ensure squad file exists")
            return None

        print("\n📊 Current Squad Status:")
        self._display_current_squad_summary()

        # Analyze if transfers needed
        print("\n🔍 Analyzing transfer opportunities...")
        transfer_recommendations = self._analyze_transfers()

        return transfer_recommendations

    def _convert_analysis_format(self, analysis_dict):
        """Convert pre-computed analysis from dict to list format"""
        players_list = []

        for player_id_str, data in analysis_dict.items():
            player_id = int(player_id_str)
            player = self.players.get(player_id)

            if not player:
                continue

            # Skip unavailable players
            if player['status'] != 'a':
                continue

            team = self.teams.get(data['team'], {})
            team_name = team.get('short_name', 'UNK')

            # Get current price from bootstrap (analysis may have old price)
            price = player['now_cost'] / 10

            # Calculate value metrics
            total_points = data.get('total_fpl_points', data.get('total_points', 0))
            weeks = data.get('weeks_played', 1)
            points_per_game = total_points / weeks if weeks > 0 else 0

            dc_consistency = data.get('dc_consistency_pct', 0)
            is_dc_specialist = dc_consistency >= 70  # 70%+ DC weeks

            players_list.append({
                'id': player_id,
                'name': data['name'],
                'team': team_name,
                'position': data['position'],
                'price': price,
                'form': points_per_game,  # Use PPG as form proxy
                'points_per_game': points_per_game,
                'dc_per_90': data.get('avg_dc_per_gw', 0),
                'is_dc_specialist': is_dc_specialist,
                'total_points': total_points,
                'minutes': data.get('total_minutes', 0),
                'value_score': points_per_game / price if price > 0 else 0,
                'dc_consistency_pct': dc_consistency
            })

        return players_list

    def _quick_analyze_players(self):
        """Quick player analysis using bootstrap data"""
        analyzed = []

        for player in self.bootstrap['elements']:
            # Skip if unavailable
            if player['status'] != 'a':
                continue

            # Skip if not playing
            if player['minutes'] == 0:
                continue

            # Calculate value metrics
            form = float(player['form']) if player['form'] else 0
            points_per_game = float(player['points_per_game']) if player['points_per_game'] else 0
            price = player['now_cost'] / 10

            # DC analysis
            dc = player.get('defensive_contribution', 0)
            dc_per_90 = float(player.get('defensive_contribution_per_90', 0))

            # Position thresholds
            position = POSITION_MAP[player['element_type']]
            is_dc_specialist = False

            if position == 'DEF' and dc_per_90 >= 10:
                is_dc_specialist = True
            elif position == 'MID' and dc_per_90 >= 12:
                is_dc_specialist = True

            analyzed.append({
                'id': player['id'],
                'name': player['web_name'],
                'team': self.teams[player['team']]['short_name'],
                'position': position,
                'price': price,
                'form': form,
                'points_per_game': points_per_game,
                'dc_per_90': dc_per_90,
                'is_dc_specialist': is_dc_specialist,
                'total_points': player['total_points'],
                'minutes': player['minutes'],
                'value_score': points_per_game / price if price > 0 else 0
            })

        return analyzed

    def _select_optimal_squad(self, players_analyzed):
        """Select best 15 players within budget and constraints"""

        # Separate by position
        by_position = defaultdict(list)
        for p in players_analyzed:
            by_position[p['position']].append(p)

        # Sort each position by value score
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x['value_score'], reverse=True)

        # Greedy selection with DC priority
        selected = {
            'GKP': [],
            'DEF': [],
            'MID': [],
            'FWD': []
        }

        total_cost = 0
        budget = self.budget

        # Strategy: Fill DC specialists first, then premiums

        # 1. Select 2 cheapest GKPs
        for gkp in sorted(by_position['GKP'], key=lambda x: x['price'])[:2]:
            selected['GKP'].append(gkp)
            total_cost += gkp['price']

        # 2. Select top DC defenders (aim for 3-4)
        dc_defs = [p for p in by_position['DEF'] if p['is_dc_specialist']]
        for def_player in dc_defs[:4]:
            if total_cost + def_player['price'] <= budget:
                selected['DEF'].append(def_player)
                total_cost += def_player['price']

        # 3. Fill remaining DEF slots with value picks
        while len(selected['DEF']) < SQUAD_CONSTRAINTS['DEF']:
            for def_player in by_position['DEF']:
                if def_player not in selected['DEF']:
                    if total_cost + def_player['price'] <= budget:
                        selected['DEF'].append(def_player)
                        total_cost += def_player['price']
                        break

        # 4. Select top DC midfielders (aim for 3-4)
        dc_mids = [p for p in by_position['MID'] if p['is_dc_specialist']]
        for mid_player in dc_mids[:4]:
            if total_cost + mid_player['price'] <= budget:
                selected['MID'].append(mid_player)
                total_cost += mid_player['price']

        # 5. Fill remaining MID with attacking/premium options
        while len(selected['MID']) < SQUAD_CONSTRAINTS['MID']:
            for mid_player in by_position['MID']:
                if mid_player not in selected['MID']:
                    if total_cost + mid_player['price'] <= budget:
                        selected['MID'].append(mid_player)
                        total_cost += mid_player['price']
                        break

        # 6. Select forwards (premium + budget)
        # Try to get one premium (Haaland if possible)
        premium_fwds = [p for p in by_position['FWD'] if p['price'] >= 11.0]
        if premium_fwds and total_cost + premium_fwds[0]['price'] <= budget:
            selected['FWD'].append(premium_fwds[0])
            total_cost += premium_fwds[0]['price']

        # Fill remaining FWD slots
        while len(selected['FWD']) < SQUAD_CONSTRAINTS['FWD']:
            for fwd_player in by_position['FWD']:
                if fwd_player not in selected['FWD']:
                    if total_cost + fwd_player['price'] <= budget:
                        selected['FWD'].append(fwd_player)
                        total_cost += fwd_player['price']
                        break

        return {
            'squad': selected,
            'total_cost': total_cost,
            'remaining_budget': budget - total_cost,
            'dc_count': sum(1 for pos in selected.values() for p in pos if p.get('is_dc_specialist'))
        }

    def _display_current_squad_summary(self):
        """Display summary of current squad"""
        if not self.current_squad:
            return

        squad = self.current_squad.get('squad', {})

        for pos_group, pos_label in [
            ('goalkeepers', 'GKP'),
            ('defenders', 'DEF'),
            ('midfielders', 'MID'),
            ('forwards', 'FWD')
        ]:
            if pos_group in squad and squad[pos_group]:
                print(f"\n{pos_label}:")
                for p in squad[pos_group]:
                    player = self.players.get(p['id'])
                    if player:
                        status = '✅' if player['status'] == 'a' else '⚠️'
                        print(f"  {status} {player['web_name']:20s} £{p['price']:.1f}m")

    def _analyze_transfers(self):
        """Analyze if transfers should be made"""
        # TODO: Implement transfer analysis
        # For now, return placeholder
        return {
            'recommended_transfers': [],
            'expected_gain': 0,
            'take_hit': False,
            'reasoning': 'Transfer analysis not yet implemented - coming in Phase 3'
        }

    def select_captain(self, squad):
        """Select captain and vice-captain"""
        print("\n" + "=" * 80)
        print("CAPTAIN SELECTION")
        print("=" * 80)

        # Get all outfield players (starting XI candidates)
        all_players = []
        if isinstance(squad, dict) and 'squad' in squad:
            # Fresh start format
            for pos in ['DEF', 'MID', 'FWD']:
                all_players.extend(squad['squad'].get(pos, []))
        else:
            # Current squad format
            return self._select_captain_from_current()

        # Sort by expected points (use form as proxy for now)
        candidates = sorted(all_players, key=lambda x: x.get('form', 0), reverse=True)

        if candidates:
            captain = candidates[0]
            vice = candidates[1] if len(candidates) > 1 else candidates[0]

            print(f"\n🔴 CAPTAIN: {captain['name']} ({captain['team']})")
            print(f"   Form: {captain.get('form', 0)}, PPG: {captain.get('points_per_game', 0)}")
            print(f"\n🟡 VICE-CAPTAIN: {vice['name']} ({vice['team']})")
            print(f"   Form: {vice.get('form', 0)}, PPG: {vice.get('points_per_game', 0)}")

            return {'captain': captain, 'vice_captain': vice}

        return None

    def _select_captain_from_current(self):
        """Select captain from current squad"""
        # Placeholder
        return {
            'captain': None,
            'vice_captain': None,
            'reasoning': 'Captain selection from current squad - TBD'
        }

    def optimize_formation(self, squad):
        """Select best starting XI and bench order"""
        print("\n" + "=" * 80)
        print("FORMATION & BENCH OPTIMIZATION")
        print("=" * 80)

        # For fresh start, use a balanced 3-5-2 or 3-4-3
        if isinstance(squad, dict) and 'squad' in squad:
            selected = squad['squad']

            # Pick starting XI
            starting = {
                'GKP': [selected['GKP'][0]],  # Best GKP
                'DEF': selected['DEF'][:3],    # Top 3 DEF
                'MID': selected['MID'][:5],    # Top 5 MID
                'FWD': selected['FWD'][:2]     # Top 2 FWD
            }

            bench = {
                'GKP': selected['GKP'][1:],
                'DEF': selected['DEF'][3:],
                'MID': selected['MID'][5:],
                'FWD': selected['FWD'][2:]
            }

            print("\n📋 STARTING XI (3-5-2):")
            for pos in ['GKP', 'DEF', 'MID', 'FWD']:
                for p in starting[pos]:
                    print(f"  {pos}: {p['name']:20s} ({p['team']}) £{p['price']:.1f}m")

            print("\n🪑 BENCH (in autosub order):")
            bench_order = []
            for pos in ['GKP', 'DEF', 'MID', 'FWD']:
                for p in bench[pos]:
                    bench_order.append(p)
                    print(f"  {len(bench_order)}. {p['name']:20s} ({p['team']}) £{p['price']:.1f}m")

            return {
                'starting_xi': starting,
                'bench': bench_order,
                'formation': '3-5-2'
            }

        return None

    def generate_report(self, availability_issues, squad_selection, captain_choice, formation):
        """Generate Ron's final recommendations"""
        print("\n" + "=" * 80)
        print(f"RON'S RECOMMENDATIONS - GW{self.gameweek}")
        print("=" * 80)

        report = {
            'gameweek': self.gameweek,
            'timestamp': datetime.now().isoformat(),
            'mode': 'fresh_start' if self.fresh_start else 'standard',
            'availability_issues': availability_issues,
            'squad_selection': squad_selection,
            'captain': captain_choice,
            'formation': formation,
        }

        # Ron's commentary
        print("\n" + "=" * 80)
        print("THE GAFFER'S VERDICT")
        print("=" * 80)

        if self.fresh_start:
            dc_count = squad_selection.get('dc_count', 0)
            total_cost = squad_selection.get('total_cost', 0)
            remaining = squad_selection.get('remaining_budget', 0)

            print(f"\nRight, GW{self.gameweek}. Fresh start. Here's the plan:\n")
            print(f"Selected {dc_count} DC specialists - that's our foundation.")
            print(f"Total squad cost: £{total_cost:.1f}m")
            print(f"Budget remaining: £{remaining:.1f}m")
            print(f"\nFormation: {formation.get('formation', 'TBD')}")

            if captain_choice:
                cap = captain_choice.get('captain', {})
                print(f"\nCaptain: {cap.get('name', 'TBD')} - best form in the squad.")

            print(f"\nStrategy: Let everyone else chase goals. We're banking DC points")
            print(f"every week. Steady. Reliable. That's how you win marathons.")

        else:
            print(f"\nGW{self.gameweek} analysis complete.\n")
            print("Squad looks solid. Monitor team news closer to deadline.")
            print("\nTransfer recommendations will be available in Phase 3.")

        print("\n" + "=" * 80)

        return report


def main():
    parser = argparse.ArgumentParser(
        description="Ron Clanker's Pre-Deadline Optimizer - Weekly Decision Engine"
    )
    parser.add_argument('--gw', '--gameweek', type=int, required=True,
                       dest='gameweek', help='Gameweek to optimize for')
    parser.add_argument('--fresh-start', action='store_true',
                       help='Fresh start mode (GW8 - select best 15 from scratch)')
    parser.add_argument('--free-transfers', type=int,
                       help='Override free transfers available (default: 1, or 0 for fresh start)')
    parser.add_argument('--budget', type=float,
                       help='Override budget in millions (default: 100.0 for fresh start)')
    parser.add_argument('--save', action='store_true',
                       help='Save recommendations to file')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed analysis')

    args = parser.parse_args()

    print("=" * 80)
    print("RON CLANKER'S PRE-DEADLINE OPTIMIZER")
    print("=" * 80)
    print(f"Gameweek: {args.gameweek}")
    print(f"Mode: {'Fresh Start (GW8)' if args.fresh_start else 'Standard (Transfers)'}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    try:
        # Initialize optimizer
        optimizer = PreDeadlineOptimizer(args.gameweek, args.fresh_start)

        # Override settings if provided
        if args.free_transfers is not None:
            optimizer.free_transfers = args.free_transfers
        if args.budget is not None:
            optimizer.budget = args.budget

        # Load data
        optimizer.load_data()

        # Check availability
        availability_issues = optimizer.run_availability_check()

        # Run optimization
        if args.fresh_start:
            squad_selection = optimizer.analyze_fresh_start()
        else:
            squad_selection = optimizer.analyze_standard_mode()

        # Captain selection
        captain_choice = optimizer.select_captain(squad_selection)

        # Formation optimization
        formation = optimizer.optimize_formation(squad_selection)

        # Generate final report
        report = optimizer.generate_report(
            availability_issues,
            squad_selection,
            captain_choice,
            formation
        )

        # Save if requested
        if args.save:
            output_dir = project_root / 'data' / 'pre_deadline_reports'
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'gw{args.gameweek}_recommendations_{timestamp}.json'

            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)

            print(f"\n💾 Recommendations saved to: {output_file}")

        print("\n" + "=" * 80)
        print("✅ OPTIMIZATION COMPLETE")
        print("=" * 80)
        print("\nNext steps:")
        if args.fresh_start:
            print("1. Review squad selection")
            print("2. Check player news closer to deadline")
            print("3. Input team on FPL website")
            print("4. Set captain & formation")
        else:
            print("1. Review transfer recommendations")
            print("2. Monitor price changes")
            print("3. Check team news Friday")
            print("4. Make final decision Saturday AM")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
