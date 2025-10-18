#!/usr/bin/env python3
"""
Track Global Rankings (Top 100 / Top 1000)

Scrapes and analyzes the top-performing FPL teams to identify:
- Template picks (most owned players by elite managers)
- Emerging differentials (underpriced gems)
- Chip timing patterns (when do elite managers use chips)
- Captain choices (who elite managers trust)
- Team structure (budget allocation, formation preferences)

This intelligence helps Ron learn from the best while maintaining
his defensive contribution strategy.

Usage:
    python scripts/track_global_rankings.py --top 100
    python scripts/track_global_rankings.py --top 1000
    python scripts/track_global_rankings.py --top 100 --detailed
    python scripts/track_global_rankings.py --gw 8
"""

import sys
from pathlib import Path
import argparse
import requests
import logging
from datetime import datetime
from collections import Counter
from typing import List, Dict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.gameweek import get_current_gameweek

logger = logging.getLogger('ron_clanker.global_rankings')

FPL_API = "https://fantasy.premierleague.com/api"
OVERALL_LEAGUE_ID = 314  # FPL Overall league


def fetch_league_page(league_id: int, page: int) -> Dict:
    """Fetch a page from the league standings."""
    try:
        url = f"{FPL_API}/leagues-classic/{league_id}/standings/?page_standings={page}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        logger.debug(f"GlobalRankings: Fetched page {page} ({len(data['standings']['results'])} entries)")

        return data

    except requests.RequestException as e:
        logger.error(f"GlobalRankings: Failed to fetch page {page}: {e}")
        raise


def fetch_top_n_teams(n: int, gameweek: int) -> List[Dict]:
    """
    Fetch top N teams from overall league.

    Args:
        n: Number of top teams to fetch (e.g., 100, 1000)
        gameweek: Current gameweek

    Returns:
        List of team dicts with entry_id, rank, total, player_name, entry_name
    """
    print(f"\n📥 Fetching top {n} teams from FPL overall league...")

    teams = []
    page = 1
    entries_per_page = 50  # FPL API returns 50 per page
    pages_needed = (n // entries_per_page) + (1 if n % entries_per_page else 0)

    while len(teams) < n:
        try:
            data = fetch_league_page(OVERALL_LEAGUE_ID, page)
            results = data['standings']['results']

            for team in results:
                if len(teams) >= n:
                    break

                teams.append({
                    'entry_id': team['entry'],
                    'rank': team['rank'],
                    'total': team['total'],
                    'event_total': team.get('event_total', 0),
                    'player_name': team['player_name'],
                    'entry_name': team['entry_name']
                })

            print(f"   Fetched page {page}/{pages_needed} - {len(teams)}/{n} teams")

            if not data['standings']['has_next'] or len(teams) >= n:
                break

            page += 1

        except Exception as e:
            logger.error(f"GlobalRankings: Error fetching page {page}: {e}")
            break

    print(f"✅ Fetched {len(teams)} teams")
    return teams[:n]


def fetch_team_picks(entry_id: int, gameweek: int) -> Dict:
    """Fetch team picks for a specific team and gameweek."""
    try:
        url = f"{FPL_API}/entry/{entry_id}/event/{gameweek}/picks/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    except requests.RequestException as e:
        logger.warning(f"GlobalRankings: Could not fetch picks for {entry_id} GW{gameweek}: {e}")
        return None


def fetch_team_history(entry_id: int) -> Dict:
    """Fetch team history including chip usage."""
    try:
        url = f"{FPL_API}/entry/{entry_id}/history/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    except requests.RequestException as e:
        logger.warning(f"GlobalRankings: Could not fetch history for {entry_id}: {e}")
        return None


def analyze_template(teams: List[Dict], gameweek: int, db: Database) -> Dict:
    """
    Analyze the template among elite teams.

    Returns:
        Dict with template analysis
    """
    print(f"\n📊 Analyzing template picks (GW{gameweek})...")

    player_ownership = Counter()
    captain_choices = Counter()
    total_teams_analyzed = 0

    for i, team in enumerate(teams, 1):
        picks_data = fetch_team_picks(team['entry_id'], gameweek)

        if picks_data and 'picks' in picks_data:
            total_teams_analyzed += 1

            for pick in picks_data['picks']:
                player_id = pick['element']
                player_ownership[player_id] += 1

                if pick['is_captain']:
                    captain_choices[player_id] += 1

        if i % 25 == 0:
            print(f"   Analyzed {i}/{len(teams)} teams...")

    # Get player names from database
    template_players = []
    for player_id, count in player_ownership.most_common(20):
        player_data = db.execute_query(
            "SELECT web_name, now_cost, element_type, selected_by_percent FROM players WHERE id = ?",
            (player_id,)
        )

        if player_data:
            p = player_data[0]
            ownership_pct = (count / total_teams_analyzed) * 100

            template_players.append({
                'player_id': player_id,
                'name': p['web_name'],
                'price': p['now_cost'] / 10.0,
                'position': ['', 'GKP', 'DEF', 'MID', 'FWD'][p['element_type']],
                'elite_ownership': ownership_pct,
                'global_ownership': float(p['selected_by_percent']),
                'count': count
            })

    # Top captains
    captain_picks = []
    for player_id, count in captain_choices.most_common(10):
        player_data = db.execute_query(
            "SELECT web_name FROM players WHERE id = ?",
            (player_id,)
        )

        if player_data:
            captain_pct = (count / total_teams_analyzed) * 100
            captain_picks.append({
                'player_id': player_id,
                'name': player_data[0]['web_name'],
                'count': count,
                'percentage': captain_pct
            })

    print(f"✅ Template analysis complete ({total_teams_analyzed} teams analyzed)")

    return {
        'template_players': template_players,
        'captain_picks': captain_picks,
        'teams_analyzed': total_teams_analyzed
    }


def analyze_chip_usage(teams: List[Dict], gameweek: int) -> Dict:
    """
    Analyze chip usage patterns among elite teams.

    Returns:
        Dict with chip usage analysis
    """
    print(f"\n📊 Analyzing chip usage patterns...")

    chips_used = Counter()
    chips_by_gw = {}
    total_analyzed = 0

    for i, team in enumerate(teams, 1):
        history = fetch_team_history(team['entry_id'])

        if history and 'chips' in history:
            total_analyzed += 1

            for chip in history['chips']:
                chip_name = chip['name']
                chip_gw = chip['event']

                chips_used[chip_name] += 1

                if chip_gw not in chips_by_gw:
                    chips_by_gw[chip_gw] = Counter()
                chips_by_gw[chip_gw][chip_name] += 1

        if i % 25 == 0:
            print(f"   Analyzed {i}/{len(teams)} teams...")

    print(f"✅ Chip analysis complete ({total_analyzed} teams analyzed)")

    return {
        'total_chips_used': dict(chips_used),
        'chips_by_gameweek': {gw: dict(chips) for gw, chips in chips_by_gw.items()},
        'teams_analyzed': total_analyzed
    }


def find_differentials(template_players: List[Dict], ron_entry_id: int, gameweek: int, db: Database) -> Dict:
    """
    Find differential opportunities vs elite template.

    Returns:
        Dict with differential analysis
    """
    print(f"\n🔍 Finding differentials vs elite template...")

    # Get Ron's picks
    ron_picks = db.execute_query("""
        SELECT player_id FROM rival_team_picks
        WHERE entry_id = ? AND gameweek = ?
    """, (ron_entry_id, gameweek))

    if not ron_picks:
        print("   ⚠️  Ron's team not found in database for this gameweek")
        return {'ron_differentials': [], 'elite_template_missing': []}

    ron_player_ids = {row['player_id'] for row in ron_picks}

    # Ron's differentials (players Ron has that elite don't)
    elite_player_ids = {p['player_id'] for p in template_players if p['elite_ownership'] > 50}

    ron_differentials = []
    for player_id in ron_player_ids:
        if player_id not in elite_player_ids:
            player_data = db.execute_query(
                "SELECT web_name, now_cost, element_type, selected_by_percent FROM players WHERE id = ?",
                (player_id,)
            )

            if player_data:
                p = player_data[0]
                ron_differentials.append({
                    'name': p['web_name'],
                    'price': p['now_cost'] / 10.0,
                    'position': ['', 'GKP', 'DEF', 'MID', 'FWD'][p['element_type']],
                    'global_ownership': float(p['selected_by_percent'])
                })

    # Elite template Ron is missing (>70% owned by elite)
    elite_template_missing = []
    for player in template_players:
        if player['elite_ownership'] > 70 and player['player_id'] not in ron_player_ids:
            elite_template_missing.append(player)

    print(f"✅ Found {len(ron_differentials)} Ron differentials, {len(elite_template_missing)} elite template gaps")

    return {
        'ron_differentials': ron_differentials,
        'elite_template_missing': elite_template_missing
    }


def display_template_report(template: Dict, chip_usage: Dict, differentials: Dict = None):
    """Display comprehensive template report."""

    print("\n" + "=" * 100)
    print("ELITE TEMPLATE ANALYSIS")
    print("=" * 100)

    # Template players
    print(f"\n📊 TEMPLATE PLAYERS (Top 20 by elite ownership):")
    print(f"{'Player':20s} {'Pos':5s} {'Price':8s} {'Elite Own':12s} {'Global Own':12s}")
    print("-" * 100)

    for p in template['template_players'][:20]:
        print(f"{p['name']:20s} {p['position']:5s} £{p['price']:5.1f}m   "
              f"{p['elite_ownership']:6.1f}%       {p['global_ownership']:6.1f}%")

    # Captain picks
    print(f"\n⭐ CAPTAIN PICKS:")
    print(f"{'Player':20s} {'Count':8s} {'Percentage':12s}")
    print("-" * 100)

    for c in template['captain_picks'][:10]:
        print(f"{c['name']:20s} {c['count']:8d} {c['percentage']:10.1f}%")

    # Chip usage
    print(f"\n💎 CHIP USAGE SUMMARY:")
    print(f"   Teams analyzed: {chip_usage['teams_analyzed']}")
    for chip, count in chip_usage['total_chips_used'].items():
        pct = (count / chip_usage['teams_analyzed']) * 100
        print(f"   {chip}: {count} ({pct:.1f}%)")

    if chip_usage['chips_by_gameweek']:
        print(f"\n💎 CHIP USAGE BY GAMEWEEK:")
        for gw in sorted(chip_usage['chips_by_gameweek'].keys()):
            chips = chip_usage['chips_by_gameweek'][gw]
            chip_str = ', '.join([f"{chip}({count})" for chip, count in chips.items()])
            print(f"   GW{gw}: {chip_str}")

    # Differentials (if Ron's data available)
    if differentials:
        print(f"\n" + "=" * 100)
        print("DIFFERENTIAL ANALYSIS")
        print("=" * 100)

        if differentials['ron_differentials']:
            print(f"\n🤖 RON'S DIFFERENTIALS ({len(differentials['ron_differentials'])} players):")
            print(f"{'Player':20s} {'Pos':5s} {'Price':8s} {'Global Own':12s}")
            print("-" * 100)

            for p in differentials['ron_differentials'][:10]:
                print(f"{p['name']:20s} {p['position']:5s} £{p['price']:5.1f}m   {p['global_ownership']:6.1f}%")

        if differentials['elite_template_missing']:
            print(f"\n👑 ELITE TEMPLATE RON IS MISSING ({len(differentials['elite_template_missing'])} players):")
            print(f"{'Player':20s} {'Pos':5s} {'Price':8s} {'Elite Own':12s}")
            print("-" * 100)

            for p in differentials['elite_template_missing']:
                print(f"{p['name']:20s} {p['position']:5s} £{p['price']:5.1f}m   {p['elite_ownership']:6.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Track global FPL rankings")
    parser.add_argument('--top', type=int, default=100,
                       help='Number of top teams to analyze (default: 100)')
    parser.add_argument('--gw', '--gameweek', type=int, dest='gameweek',
                       help='Gameweek to analyze (default: current)')
    parser.add_argument('--detailed', action='store_true',
                       help='Include detailed analysis (slower)')
    parser.add_argument('--ron-id', type=int,
                       help='Ron\'s team ID for differential analysis')

    args = parser.parse_args()

    start_time = datetime.now()

    print("=" * 100)
    print("GLOBAL RANKINGS TRACKER")
    print("=" * 100)
    print(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tracking: Top {args.top} teams")
    print("=" * 100)

    try:
        # Initialize
        db = Database()

        # Get current gameweek
        gameweek = args.gameweek or get_current_gameweek(db)
        if not gameweek:
            print("❌ Could not determine current gameweek")
            return 1

        print(f"Gameweek: {gameweek}")

        # Fetch top teams
        teams = fetch_top_n_teams(args.top, gameweek)

        if not teams:
            print("❌ Failed to fetch teams")
            return 1

        # Analyze template
        template = analyze_template(teams, gameweek, db)

        # Analyze chip usage
        chip_usage = analyze_chip_usage(teams, gameweek)

        # Differential analysis (if Ron's team ID provided)
        differentials = None
        if args.ron_id:
            differentials = find_differentials(template['template_players'], args.ron_id, gameweek, db)

        # Display report
        display_template_report(template, chip_usage, differentials)

        duration = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 100)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 100)
        print(f"Duration: {duration:.1f}s")
        print(f"Teams analyzed: {len(teams)}")
        print(f"Template players identified: {len(template['template_players'])}")

        return 0

    except Exception as e:
        logger.error(f"GlobalRankings: Fatal error: {e}", exc_info=True)
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
