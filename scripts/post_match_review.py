#!/usr/bin/env python3
"""
Post-Match Review - Ron's Analysis After the Gameweek

Generates Ron's candid post-gameweek commentary after a few beers and a cigar.
Analyzes Premier League results, mini-league standings, and Ron's team performance.

Usage:
    python scripts/post_match_review.py --gw 7
    python scripts/post_match_review.py --gw 7 --post-telegram
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime
from typing import Dict, List, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ron_clanker.persona import RonClanker
from intelligence.league_intel import LeagueIntelligenceService
from utils.gameweek import get_current_gameweek
from utils.config import load_config, get_telegram_token, get_telegram_chat_id
from telegram_bot.notifications import send_post_match_review
import requests
import os


def get_ron_performance(db: Database, gameweek: int, team_id: int) -> Dict[str, Any]:
    """Get Ron's points and rank for the gameweek."""

    # Get Ron's gameweek points
    team_picks = db.execute_query("""
        SELECT p.web_name, p.element_type, rt.position, rt.is_captain, rt.is_vice_captain,
               pgh.total_points, pgh.minutes
        FROM rival_team_picks rt
        JOIN players p ON rt.player_id = p.id
        LEFT JOIN player_gameweek_history pgh ON p.id = pgh.player_id AND pgh.gameweek = ?
        WHERE rt.entry_id = ? AND rt.gameweek = ?
    """, (gameweek, team_id, gameweek))

    if not team_picks:
        return None

    # Calculate total points (starters only, captain doubled)
    total_points = 0
    for pick in team_picks:
        if pick['position'] <= 11:  # Starting XI
            pts = pick.get('total_points', 0) or 0
            if pick['is_captain']:
                total_points += pts * 2
            else:
                total_points += pts

    # Get overall rank from FPL API (if available)
    try:
        response = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_id}/", timeout=10)
        if response.status_code == 200:
            data = response.json()
            overall_rank = data.get('summary_overall_rank', 0)
        else:
            overall_rank = 0
    except:
        overall_rank = 0

    # Get average score
    avg_query = db.execute_query("""
        SELECT AVG(total_points) as avg_score
        FROM rival_teams
        WHERE gameweek = ?
    """, (gameweek,))

    average_score = int(avg_query[0]['avg_score']) if avg_query and avg_query[0]['avg_score'] else 50

    return {
        'points': total_points,
        'rank': overall_rank,
        'average': average_score,
        'team_picks': team_picks
    }


def analyze_team_performance(team_picks: List[Dict], gameweek: int) -> Dict[str, Any]:
    """Analyze Ron's team performance - heroes, villains, differentials."""

    heroes = []
    villains = []
    captain = None
    differentials = []

    for pick in team_picks:
        if pick['position'] > 11:  # Bench
            continue

        pts = pick.get('total_points', 0) or 0
        minutes = pick.get('minutes', 0) or 0

        # Captain
        if pick['is_captain']:
            captain = {
                'name': pick['web_name'],
                'points': pts
            }

        # Heroes (8+ points)
        if pts >= 8:
            reason = "Delivered" if pts >= 10 else "Solid shift"
            heroes.append({
                'name': pick['web_name'],
                'points': pts,
                'reason': reason
            })

        # Villains (played but 2 or fewer points)
        elif minutes > 0 and pts <= 2:
            if minutes < 60:
                reason = "Subbed off early, useless"
            else:
                reason = "Full 90, did nothing"
            villains.append({
                'name': pick['web_name'],
                'points': pts,
                'reason': reason
            })

        # TODO: Check ownership for differentials (needs FPL API)
        # For now, just flag low-owned players who did well

    # Sort heroes by points
    heroes.sort(key=lambda x: x['points'], reverse=True)
    villains.sort(key=lambda x: x['points'])

    return {
        'captain': captain or {'name': 'Unknown', 'points': 0},
        'heroes': heroes,
        'villains': villains,
        'differentials': differentials
    }


def get_league_analysis(db: Database, league_service: LeagueIntelligenceService,
                       gameweek: int, league_id: int, team_id: int) -> Dict[str, Any]:
    """Get mini-league standings and drama."""

    # Get league standings
    standings = db.execute_query("""
        SELECT entry_id, entry_name, player_name, rank, total_points
        FROM rival_teams
        WHERE league_id = ? AND gameweek = ?
        ORDER BY rank
    """, (league_id, gameweek))

    if not standings:
        return {
            'name': 'Unknown League',
            'ron_rank': 0,
            'total_managers': 0,
            'leader': {},
            'gap_to_leader': 0,
            'big_movers': []
        }

    # Find Ron's position
    ron_standing = next((s for s in standings if s['entry_id'] == team_id), None)
    ron_rank = ron_standing['rank'] if ron_standing else len(standings)
    ron_points = ron_standing['total_points'] if ron_standing else 0

    leader = standings[0]
    gap = leader['total_points'] - ron_points

    # Get league name
    league_info = db.execute_query("SELECT name FROM leagues WHERE id = ?", (league_id,))
    league_name = league_info[0]['name'] if league_info else f"League {league_id}"

    # Calculate big movers (compare to previous GW)
    big_movers = []
    if gameweek > 1:
        prev_standings = db.execute_query("""
            SELECT entry_id, rank
            FROM rival_teams
            WHERE league_id = ? AND gameweek = ?
        """, (league_id, gameweek - 1))

        prev_ranks = {s['entry_id']: s['rank'] for s in prev_standings}

        for current in standings:
            entry_id = current['entry_id']
            if entry_id in prev_ranks:
                change = prev_ranks[entry_id] - current['rank']  # Positive = moved up
                if abs(change) >= 2:  # Moved 2+ places
                    big_movers.append({
                        'name': current['entry_name'],
                        'change': change,
                        'points': current['total_points']
                    })

        big_movers.sort(key=lambda x: abs(x['change']), reverse=True)

    return {
        'name': league_name,
        'ron_rank': ron_rank,
        'total_managers': len(standings),
        'leader': {
            'name': leader['entry_name'],
            'points': leader['total_points']
        },
        'gap_to_leader': gap,
        'big_movers': big_movers
    }


def get_premier_league_stories(db: Database, gameweek: int) -> List[str]:
    """Get interesting Premier League storylines from the gameweek."""

    # Get fixtures with results
    fixtures = db.execute_query("""
        SELECT
            home_team.name as home_team,
            away_team.name as away_team,
            f.team_h_score,
            f.team_a_score,
            f.finished
        FROM fixtures f
        JOIN teams home_team ON f.team_h = home_team.id
        JOIN teams away_team ON f.team_a = away_team.id
        WHERE f.event = ? AND f.finished = 1
    """, (gameweek,))

    stories = []

    for fix in fixtures:
        home = fix['home_team']
        away = fix['away_team']
        h_score = fix['team_h_score']
        a_score = fix['team_a_score']

        # Highlight interesting results
        if h_score + a_score >= 5:  # High scoring
            stories.append(f"{home} {h_score}-{a_score} {away} - Goals galore. Defenders punished.")
        elif h_score >= 4 or a_score >= 4:  # Hammering
            winner = home if h_score > a_score else away
            stories.append(f"{home} {h_score}-{a_score} {away} - {winner} absolutely dominant.")
        elif h_score == a_score and h_score >= 2:  # High draw
            stories.append(f"{home} {h_score}-{a_score} {away} - End-to-end stuff. Entertaining.")
        elif h_score == 0 and a_score == 0:  # Boring draw
            stories.append(f"{home} 0-0 {away} - Snooze fest. Waste of 90 minutes.")

    # Limit to top 3-4 stories
    return stories[:4]




def main():
    parser = argparse.ArgumentParser(description='Generate Ron\'s post-match analysis')
    parser.add_argument('--gw', '--gameweek', type=int, dest='gameweek',
                       help='Gameweek to review (default: most recent finished)')
    parser.add_argument('--post-telegram', action='store_true',
                       help='Post to Telegram')
    parser.add_argument('--save-file', action='store_true', default=True,
                       help='Save to file (default: True)')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("RON'S POST-MATCH REVIEW GENERATOR")
    print("=" * 70)

    # Initialize
    db = Database()
    ron = RonClanker()
    league_service = LeagueIntelligenceService(db)

    # Load config (from .env and ron_config.json)
    config = load_config()

    team_id = config.get('team_id')
    league_id = config.get('league_id')

    # Determine gameweek
    if args.gameweek:
        gameweek = args.gameweek
    else:
        # Get most recent finished gameweek
        current_gw = get_current_gameweek(db)
        gameweek = current_gw - 1 if current_gw else 1

    print(f"Gameweek: {gameweek}")
    print(f"Team ID: {team_id}")
    print(f"League ID: {league_id}")
    print("=" * 70)

    # Gather data
    print("\n📊 Collecting data...")

    # 1. Ron's performance
    print("  • Ron's performance...")
    ron_perf = get_ron_performance(db, gameweek, team_id)

    if not ron_perf:
        print(f"❌ No data found for GW{gameweek}")
        return 1

    print(f"    ✓ {ron_perf['points']} points")

    # 2. Team analysis
    print("  • Analyzing team...")
    team_analysis = analyze_team_performance(ron_perf['team_picks'], gameweek)
    print(f"    ✓ Captain: {team_analysis['captain']['name']} ({team_analysis['captain']['points']} pts)")

    # 3. League standings
    print("  • Mini-league standings...")
    league_data = get_league_analysis(db, league_service, gameweek, league_id, team_id)
    print(f"    ✓ Position: {league_data['ron_rank']} of {league_data['total_managers']}")

    # 4. Premier League stories
    print("  • Premier League results...")
    pl_stories = get_premier_league_stories(db, gameweek)
    print(f"    ✓ {len(pl_stories)} interesting results")

    # Generate Ron's analysis
    print("\n🍺 Generating Ron's post-match analysis...")

    analysis = ron.post_match_analysis(
        gameweek=gameweek,
        ron_points=ron_perf['points'],
        ron_rank=ron_perf['rank'],
        average_score=ron_perf['average'],
        league_data=league_data,
        premier_league_stories=pl_stories,
        team_performance=team_analysis
    )

    # Display
    print("\n" + "=" * 70)
    print(analysis)
    print("=" * 70)

    # Save to file
    if args.save_file:
        output_dir = project_root / 'reports' / 'post_match'
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f'gw{gameweek}_post_match_{timestamp}.txt'

        with open(output_file, 'w') as f:
            f.write(analysis)

        print(f"\n💾 Saved to: {output_file}")

    # Post to Telegram
    if args.post_telegram or os.getenv('TELEGRAM_NOTIFICATIONS_ENABLED', 'true').lower() == 'true':
        bot_token = get_telegram_token()
        chat_id = get_telegram_chat_id()

        if bot_token and chat_id:
            print("\n📱 Posting to Telegram...")
            success = send_post_match_review(bot_token, chat_id, gameweek, analysis)

            if success:
                print("   ✅ Posted successfully!")
            else:
                print("   ❌ Failed to post")
        else:
            print("\n⚠️  Telegram not configured (add bot_token and chat_id to .env)")

    print("\n✅ Post-match review complete!")

    return 0


if __name__ == '__main__':
    sys.exit(main())
