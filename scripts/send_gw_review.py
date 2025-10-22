#!/usr/bin/env python3
"""
Send Gameweek Review to Slack

Generates Ron's post-match analysis and sends it to Slack.

Usage:
    python scripts/send_gw_review.py [gameweek]
    python scripts/send_gw_review.py 8
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config
from ron_clanker.llm_banter import generate_ron_review
from notifications.slack import SlackNotifier


def get_gw_average(db: Database, gameweek: int) -> int:
    """Get the FPL average for a gameweek."""
    # For GW8 2025/26, average was around 53 points
    # In general, FPL average ranges from 45-55
    # Could fetch this from FPL API bootstrap-static endpoint if needed
    return 53


def get_ron_gw_data(db: Database, team_id: int, gameweek: int) -> dict:
    """Get Ron's gameweek performance data."""

    # Get Ron's points and league standing for this GW
    standing = db.execute_query("""
        SELECT
            rank as league_rank,
            total_points as league_total_points,
            event_points as gw_points
        FROM league_standings_history
        WHERE entry_id = ? AND gameweek = ?
    """, (team_id, gameweek))

    if not standing:
        print(f"No standing data found for GW{gameweek}")
        return None

    ron_data = standing[0]

    # Get Ron's team for this GW
    team = db.execute_query("""
        SELECT
            mt.player_id,
            mt.position,
            mt.is_captain,
            p.web_name,
            p.element_type,
            MAX(pgh.total_points) as gw_points  -- Use MAX to handle duplicate records
        FROM my_team mt
        JOIN players p ON mt.player_id = p.id
        LEFT JOIN player_gameweek_history pgh ON (
            mt.player_id = pgh.player_id AND pgh.gameweek = ?
        )
        WHERE mt.gameweek = ?
        GROUP BY mt.player_id, mt.position, mt.is_captain, p.web_name, p.element_type
        ORDER BY mt.position
    """, (gameweek, gameweek))

    # Get league info
    league_info = db.execute_query("""
        SELECT DISTINCT league_id
        FROM league_standings_history
        WHERE entry_id = ? AND gameweek = ?
    """, (team_id, gameweek))

    league_id = league_info[0]['league_id'] if league_info else None

    # Get total managers in league
    total_managers = db.execute_query("""
        SELECT COUNT(DISTINCT entry_id) as total
        FROM league_standings_history
        WHERE league_id = ? AND gameweek = ?
    """, (league_id, gameweek))

    # Get league leader
    leader = db.execute_query("""
        SELECT
            lr.player_name,
            lsh.total_points,
            lsh.rank
        FROM league_standings_history lsh
        JOIN league_rivals lr ON lsh.entry_id = lr.entry_id
        WHERE lsh.league_id = ? AND lsh.gameweek = ? AND lsh.rank = 1
    """, (league_id, gameweek))

    return {
        'ron_points': ron_data['gw_points'],
        'ron_league_rank': ron_data['league_rank'],
        'ron_overall_rank': 1_000_000,  # Placeholder - could fetch from FPL API if needed
        'ron_total_points': ron_data['league_total_points'],
        'team': team,
        'league_id': league_id,
        'total_managers': total_managers[0]['total'] if total_managers else 0,
        'leader': leader[0] if leader else None
    }


def generate_gw_review(gameweek: int) -> str:
    """Generate Ron's GW review with all the data."""

    db = Database()
    config = load_config()

    team_id = config.get('team_id')
    league_id = config.get('league_id')

    if not team_id:
        print("ERROR: FPL_TEAM_ID not set in .env file")
        return None

    # Get GW data
    gw_data = get_ron_gw_data(db, team_id, gameweek)
    if not gw_data:
        print(f"Could not get data for GW{gameweek}")
        return None

    average_score = get_gw_average(db, gameweek)

    # Extract team performance data
    captain = [p for p in gw_data['team'] if p['is_captain']][0]
    captain_points = captain['gw_points'] or 0

    # Find heroes (8+ points) and villains (2 or less points) from starting XI
    starting_xi = [p for p in gw_data['team'] if p['position'] <= 11]

    heroes = []
    villains = []

    for player in starting_xi:
        pts = player['gw_points'] or 0
        if pts >= 8 and not player['is_captain']:  # Don't double-count captain
            heroes.append({
                'name': player['web_name'],
                'points': pts,
                'reason': "Delivered"
            })
        elif pts <= 2 and not player['is_captain']:
            villains.append({
                'name': player['web_name'],
                'points': pts,
                'reason': "Disappointing"
            })

    # Sort by points
    heroes.sort(key=lambda x: x['points'], reverse=True)
    villains.sort(key=lambda x: x['points'])

    # League data
    leader_data = gw_data['leader'] or {}
    gap_to_leader = leader_data.get('total_points', 0) - gw_data['ron_total_points']
    leader_name = leader_data.get('player_name', 'Unknown')

    # Get league members for banter
    league_members_data = db.execute_query("""
        SELECT DISTINCT player_name
        FROM league_rivals
        WHERE league_id = ?
        AND player_name != 'Ron Clanker'
        ORDER BY player_name
    """, (gw_data['league_id'],))

    league_members = [m['player_name'].split()[0] for m in (league_members_data or [])]  # First names only

    # Get league GW scores to identify low scorers for banter
    league_gw_scores = db.execute_query("""
        SELECT
            lr.player_name,
            lsh.event_points as gw_points
        FROM league_standings_history lsh
        JOIN league_rivals lr ON lsh.entry_id = lr.entry_id
        WHERE lsh.league_id = ? AND lsh.gameweek = ?
        AND lr.player_name != 'Ron Clanker'
        ORDER BY lsh.event_points ASC
    """, (gw_data['league_id'], gameweek))

    # Identify low scorers (bottom 3) for potential roasting
    low_scorers = []
    if league_gw_scores:
        for scorer in league_gw_scores[:3]:  # Bottom 3
            low_scorers.append({
                'manager_name': scorer['player_name'].split()[0],  # First name only
                'gw_points': scorer['gw_points']
            })

    # TODO: Get actual rival fails from rival_team_picks + player_gameweek_history
    # For now, stub with example data
    rival_fails = [
        {'manager_name': 'Kyle', 'player_name': 'Haaland', 'points': 0},
        {'manager_name': 'Michael', 'player_name': 'Salah', 'points': 2}
    ]

    # Generate Ron's LLM-powered review
    review = generate_ron_review(
        gameweek=gameweek,
        ron_points=gw_data['ron_points'],
        average_points=average_score,
        league_position=gw_data['ron_league_rank'],
        total_managers=gw_data['total_managers'],
        gap_to_leader=gap_to_leader,
        leader_name=leader_name,
        captain_name=captain['web_name'],
        captain_points=captain_points * 2,  # Captain points are doubled
        heroes=heroes,
        villains=villains,
        team_summary=f"{len(heroes)} heroes, {len(villains)} villains",
        league_members=league_members,
        rival_fails=rival_fails,
        low_scorers=low_scorers
    )

    return review, gw_data


def send_gw_review(gameweek: int, dry_run: bool = False):
    """Generate and send GW review to Slack."""

    print(f"Generating GW{gameweek} review...")

    result = generate_gw_review(gameweek)
    if not result:
        print("Failed to generate review")
        return False

    review, gw_data = result

    print("\n" + "="*70)
    print("GENERATED REVIEW:")
    print("="*70)
    print(review)
    print("="*70)

    if dry_run:
        print("\nDRY RUN - not sending to Slack")
        return True

    # Send to Slack
    print("\nSending to Slack...")

    config = load_config()
    db = Database()
    average_score = get_gw_average(db, gameweek)

    notifier = SlackNotifier()
    success = notifier.send_gameweek_review(
        review_text=review,
        gameweek=gameweek,
        ron_points=gw_data['ron_points'],
        average_points=average_score,
        league_position=gw_data['ron_league_rank']
    )

    if success:
        print("✓ Sent to Slack successfully!")
    else:
        print("✗ Failed to send to Slack (check webhook URL in .env)")

    return success


if __name__ == "__main__":
    gameweek = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv

    send_gw_review(gameweek, dry_run=dry_run)
