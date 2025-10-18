#!/usr/bin/env python3
"""
Collect Post-Gameweek Data for Ron's Analysis

Gathers all data after a gameweek finishes:
- Ron's performance (points, rank, captain)
- Mini-league standings and drama
- Premier League results and stories
- Team analysis (heroes, villains, differentials)

Outputs clean JSON for Claude to generate Ron's post-match analysis.

Usage:
    python scripts/collect_gameweek_data.py --gw 8
    python scripts/collect_gameweek_data.py --gw 8 --save-json
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.gameweek import get_current_gameweek
from utils.config import load_config


class GameweekDataCollector:
    """Collects all post-gameweek data for analysis."""

    def __init__(self, db: Database, config: Dict[str, Any]):
        self.db = db
        self.config = config
        self.team_id = config.get('team_id')
        self.league_id = config.get('league_id')

    def collect_all(self, gameweek: int) -> Dict[str, Any]:
        """Collect all post-gameweek data."""

        data = {
            'gameweek': gameweek,
            'collected_at': datetime.now().isoformat(),
            'ron_performance': self.get_ron_performance(gameweek),
            'team_analysis': None,  # Set after we have team_picks
            'mini_league': self.get_mini_league_data(gameweek),
            'premier_league': self.get_premier_league_stories(gameweek),
            'context': self.get_context_data(gameweek)
        }

        # Team analysis depends on having team picks
        if data['ron_performance'] and data['ron_performance'].get('team_picks'):
            data['team_analysis'] = self.analyze_team_performance(
                data['ron_performance']['team_picks']
            )

        return data

    def get_ron_performance(self, gameweek: int) -> Optional[Dict[str, Any]]:
        """Get Ron's points, rank, and overall performance."""

        # Get Ron's team picks with actual points
        team_picks = self.db.execute_query("""
            SELECT
                p.id,
                p.web_name,
                p.element_type,
                p.selected_by_percent,
                rt.position,
                rt.is_captain,
                rt.is_vice_captain,
                pgh.total_points,
                pgh.minutes,
                pgh.goals_scored,
                pgh.assists,
                pgh.clean_sheets,
                pgh.goals_conceded,
                pgh.saves,
                pgh.bonus
            FROM rival_team_picks rt
            JOIN players p ON rt.player_id = p.id
            LEFT JOIN player_gameweek_history pgh ON p.id = pgh.player_id AND pgh.gameweek = ?
            WHERE rt.entry_id = ? AND rt.gameweek = ?
            ORDER BY rt.position
        """, (gameweek, self.team_id, gameweek))

        if not team_picks:
            return None

        # Calculate total points (starting XI only, captain doubled)
        total_points = 0
        captain_points = 0
        bench_points = 0

        for pick in team_picks:
            pts = pick.get('total_points') or 0

            if pick['position'] <= 11:  # Starting XI
                if pick['is_captain']:
                    total_points += pts * 2
                    captain_points = pts
                else:
                    total_points += pts
            else:  # Bench
                bench_points += pts

        # Get overall rank from FPL API
        overall_rank = self._get_overall_rank(self.team_id)

        # Get average score this gameweek
        average_score = self._get_average_score(gameweek)

        # Get previous gameweek rank for comparison
        prev_rank = self._get_overall_rank(self.team_id, gameweek - 1) if gameweek > 1 else overall_rank

        return {
            'points': total_points,
            'average_score': average_score,
            'points_vs_average': total_points - average_score,
            'overall_rank': overall_rank,
            'prev_rank': prev_rank,
            'rank_change': prev_rank - overall_rank if prev_rank and overall_rank else 0,
            'captain_points': captain_points,
            'bench_points': bench_points,
            'team_picks': team_picks
        }

    def analyze_team_performance(self, team_picks: List[Dict]) -> Dict[str, Any]:
        """Analyze Ron's team - heroes, villains, differentials."""

        heroes = []
        villains = []
        captain_data = None
        differentials = []

        for pick in team_picks:
            if pick['position'] > 11:  # Skip bench for heroes/villains
                continue

            pts = pick.get('total_points') or 0
            minutes = pick.get('minutes') or 0
            ownership = float(pick.get('selected_by_percent') or 0)

            # Captain analysis
            if pick['is_captain']:
                captain_data = {
                    'name': pick['web_name'],
                    'points': pts,
                    'ownership': ownership,
                    'verdict': 'success' if pts >= 6 else 'failure'
                }

            # Heroes (8+ points)
            if pts >= 8:
                reason = self._get_hero_reason(pick)
                heroes.append({
                    'name': pick['web_name'],
                    'points': pts,
                    'reason': reason,
                    'ownership': ownership
                })

            # Villains (played but poor return)
            elif minutes > 0 and pts <= 2:
                reason = self._get_villain_reason(pick)
                villains.append({
                    'name': pick['web_name'],
                    'points': pts,
                    'minutes': minutes,
                    'reason': reason
                })

            # Differentials (low owned players who started)
            if ownership < 10.0 and pts > 0:
                differentials.append({
                    'name': pick['web_name'],
                    'points': pts,
                    'ownership': ownership,
                    'verdict': 'hit' if pts >= 6 else 'miss'
                })

        # Sort by points
        heroes.sort(key=lambda x: x['points'], reverse=True)
        villains.sort(key=lambda x: x['points'])

        return {
            'captain': captain_data,
            'heroes': heroes,
            'villains': villains,
            'differentials': differentials
        }

    def get_mini_league_data(self, gameweek: int) -> Dict[str, Any]:
        """Get mini-league standings, movements, and drama."""

        # Get current standings
        standings = self.db.execute_query("""
            SELECT
                entry_id,
                entry_name,
                player_name,
                rank,
                total_points,
                gameweek_points
            FROM rival_teams
            WHERE league_id = ? AND gameweek = ?
            ORDER BY rank
        """, (self.league_id, gameweek))

        if not standings:
            return None

        # Find Ron
        ron_standing = next((s for s in standings if s['entry_id'] == self.team_id), None)

        if not ron_standing:
            return None

        # Get league info
        league_info = self.db.execute_query(
            "SELECT name FROM leagues WHERE id = ?",
            (self.league_id,)
        )
        league_name = league_info[0]['name'] if league_info else f"League {self.league_id}"

        # Calculate movements if we have previous data
        big_movers = self._get_big_movers(gameweek, standings)

        leader = standings[0]
        gap_to_leader = leader['total_points'] - ron_standing['total_points']

        return {
            'name': league_name,
            'ron_position': ron_standing['rank'],
            'total_managers': len(standings),
            'ron_points': ron_standing['total_points'],
            'ron_gw_points': ron_standing['gameweek_points'],
            'leader': {
                'name': leader['entry_name'],
                'manager': leader['player_name'],
                'points': leader['total_points']
            },
            'gap_to_leader': gap_to_leader,
            'big_movers': big_movers,
            'position_description': self._get_position_description(
                ron_standing['rank'],
                len(standings)
            )
        }

    def get_premier_league_stories(self, gameweek: int) -> List[Dict[str, Any]]:
        """Get interesting Premier League storylines."""

        fixtures = self.db.execute_query("""
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
            ORDER BY (f.team_h_score + f.team_a_score) DESC
        """, (gameweek,))

        stories = []

        for fix in fixtures:
            home = fix['home_team']
            away = fix['away_team']
            h_score = fix['team_h_score']
            a_score = fix['team_a_score']

            # Categorize the result
            story_type, comment = self._categorize_fixture(home, away, h_score, a_score)

            if story_type:
                stories.append({
                    'home': home,
                    'away': away,
                    'score': f"{h_score}-{a_score}",
                    'type': story_type,
                    'comment': comment
                })

        return stories[:5]  # Top 5 most interesting

    def get_context_data(self, gameweek: int) -> Dict[str, Any]:
        """Get contextual data for analysis."""

        return {
            'gameweek': gameweek,
            'gameweeks_remaining': 38 - gameweek,
            'season': '2025/26',
            'ron_team_name': 'Clanker\'s Cloggers'
        }

    # Helper methods

    def _get_overall_rank(self, team_id: int, gameweek: Optional[int] = None) -> Optional[int]:
        """Get overall rank from FPL API."""
        try:
            if gameweek:
                url = f"https://fantasy.premierleague.com/api/entry/{team_id}/history/"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    gw_data = next((gw for gw in data.get('current', []) if gw['event'] == gameweek), None)
                    return gw_data.get('overall_rank') if gw_data else None
            else:
                url = f"https://fantasy.premierleague.com/api/entry/{team_id}/"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return data.get('summary_overall_rank')
        except:
            pass
        return None

    def _get_average_score(self, gameweek: int) -> int:
        """Get average score for the gameweek."""
        try:
            url = "https://fantasy.premierleague.com/api/event-status/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('average_score', 50)
        except:
            pass
        return 50

    def _get_hero_reason(self, pick: Dict) -> str:
        """Generate reason why player was a hero."""
        goals = pick.get('goals_scored', 0) or 0
        assists = pick.get('assists', 0) or 0
        cs = pick.get('clean_sheets', 0) or 0
        bonus = pick.get('bonus', 0) or 0

        if goals >= 2:
            return f"Brace ({goals} goals)"
        elif goals == 1 and assists >= 1:
            return "Goal + assist"
        elif assists >= 2:
            return f"{assists} assists"
        elif cs and bonus >= 2:
            return f"Clean sheet + {bonus} bonus"
        else:
            return "Delivered"

    def _get_villain_reason(self, pick: Dict) -> str:
        """Generate reason why player was a villain."""
        minutes = pick.get('minutes', 0) or 0
        goals_conceded = pick.get('goals_conceded', 0) or 0

        if minutes < 60:
            return "Subbed off early, useless"
        elif goals_conceded >= 3:
            return f"Conceded {goals_conceded}, disaster"
        else:
            return "Full 90, did nothing"

    def _get_big_movers(self, gameweek: int, current_standings: List[Dict]) -> List[Dict]:
        """Find big movers in the league."""
        if gameweek <= 1:
            return []

        # Get previous gameweek standings
        prev_standings = self.db.execute_query("""
            SELECT entry_id, rank
            FROM rival_teams
            WHERE league_id = ? AND gameweek = ?
        """, (self.league_id, gameweek - 1))

        prev_ranks = {s['entry_id']: s['rank'] for s in prev_standings}

        big_movers = []
        for current in current_standings:
            entry_id = current['entry_id']
            if entry_id in prev_ranks:
                change = prev_ranks[entry_id] - current['rank']  # Positive = moved up
                if abs(change) >= 2:
                    big_movers.append({
                        'name': current['entry_name'],
                        'change': change,
                        'new_rank': current['rank'],
                        'points': current['total_points']
                    })

        big_movers.sort(key=lambda x: abs(x['change']), reverse=True)
        return big_movers[:5]

    def _get_position_description(self, rank: int, total: int) -> str:
        """Get description of league position."""
        if rank == 1:
            return "Top of the league"
        elif rank <= 3:
            return "Challenging for top spot"
        elif rank <= total // 2:
            return "Mid-table"
        else:
            return "Lower half"

    def _categorize_fixture(self, home: str, away: str, h_score: int, a_score: int) -> tuple:
        """Categorize fixture and generate comment."""
        total = h_score + a_score

        # High scoring
        if total >= 6:
            return ('thriller', f"Goal fest - defenders punished")

        # Hammering
        if h_score >= 4 or a_score >= 4:
            winner = home if h_score > a_score else away
            return ('hammering', f"{winner} absolutely dominant")

        # High draw
        if h_score == a_score and h_score >= 2:
            return ('high_draw', "End-to-end stuff, entertaining")

        # Boring draw
        if h_score == 0 and a_score == 0:
            return ('bore_draw', "Absolute snooze fest")

        # Upset (away team wins by 2+)
        if a_score - h_score >= 2:
            return ('upset', f"{away} shocked them")

        return (None, None)


def main():
    parser = argparse.ArgumentParser(description='Collect post-gameweek data')
    parser.add_argument('--gw', '--gameweek', type=int, dest='gameweek',
                       help='Gameweek to collect (default: most recent finished)')
    parser.add_argument('--save-json', action='store_true',
                       help='Save data to JSON file')
    parser.add_argument('--output-dir', type=str, default='reports/gameweek_data',
                       help='Output directory for JSON files')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("POST-GAMEWEEK DATA COLLECTOR")
    print("=" * 70)

    # Initialize
    db = Database()

    # Load config (from .env and ron_config.json)
    config = load_config()

    collector = GameweekDataCollector(db, config)

    # Determine gameweek
    if args.gameweek:
        gameweek = args.gameweek
    else:
        current_gw = get_current_gameweek(db)
        gameweek = current_gw - 1 if current_gw and current_gw > 1 else 1

    print(f"Collecting data for Gameweek {gameweek}...")
    print("=" * 70)

    # Collect all data
    data = collector.collect_all(gameweek)

    # Display summary
    if data['ron_performance']:
        perf = data['ron_performance']
        print(f"\n✅ RON'S PERFORMANCE:")
        print(f"   Points: {perf['points']} (avg: {perf['average_score']})")
        print(f"   vs Average: {perf['points_vs_average']:+d}")
        print(f"   Rank: {perf['overall_rank']:,}" if perf['overall_rank'] else "   Rank: Unknown")
        print(f"   Captain: {perf['captain_points']} points")

    if data['mini_league']:
        league = data['mini_league']
        print(f"\n✅ MINI-LEAGUE:")
        print(f"   {league['name']}")
        print(f"   Position: {league['ron_position']} of {league['total_managers']}")
        print(f"   Gap to leader: {league['gap_to_leader']:+d} points")

    if data['premier_league']:
        print(f"\n✅ PREMIER LEAGUE:")
        print(f"   {len(data['premier_league'])} interesting results")

    # Save to JSON
    if args.save_json:
        output_dir = project_root / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f'gw{gameweek}_data_{timestamp}.json'

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        print(f"\n💾 Saved to: {output_file}")

    # Pretty print for review
    print("\n" + "=" * 70)
    print("COMPLETE DATA (JSON):")
    print("=" * 70)
    print(json.dumps(data, indent=2, default=str))

    return 0


if __name__ == '__main__':
    sys.exit(main())
