#!/usr/bin/env python3
"""
Fixture Analysis for Multi-Gameweek Planning

Analyzes upcoming fixtures 3-6 gameweeks ahead to identify:
- Teams with favorable fixture runs
- Players to target for upcoming good fixtures
- Teams to avoid due to difficult runs
- Optimal transfer timing based on fixture swings
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('ron_clanker.planning')


class FixtureAnalyzer:
    """
    Analyzes fixture difficulty over multiple gameweeks.

    Helps Ron plan ahead by identifying:
    - Fixture swings (when difficulty changes significantly)
    - Best time to bring in/out players based on fixtures
    - Teams with sustained good/bad runs
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("FixtureAnalyzer: Initialized")

    def get_fixture_difficulty_ratings(self) -> Dict[int, Dict]:
        """
        Get current FPL difficulty ratings for all teams.

        Returns:
            Dict mapping team_id to difficulty stats:
                - home_difficulty: Average difficulty at home
                - away_difficulty: Average difficulty away
                - overall_strength: Combined measure
        """
        # FPL provides difficulty ratings 1-5 (1=easiest, 5=hardest)
        # We'll use team strength as a proxy based on historical performance

        teams = self.db.execute_query("""
            SELECT
                id,
                name,
                strength_overall_home,
                strength_overall_away,
                strength_attack_home,
                strength_attack_away,
                strength_defence_home,
                strength_defence_away
            FROM teams
            ORDER BY id
        """)

        ratings = {}
        for team in teams:
            ratings[team['id']] = {
                'name': team['name'],
                'strength_home': team['strength_overall_home'],
                'strength_away': team['strength_overall_away'],
                'attack_home': team['strength_attack_home'],
                'attack_away': team['strength_attack_away'],
                'defence_home': team['strength_defence_home'],
                'defence_away': team['strength_defence_away']
            }

        return ratings

    def analyze_upcoming_fixtures(self, team_id: int, start_gw: int,
                                  num_gameweeks: int = 6) -> Dict:
        """
        Analyze upcoming fixtures for a team.

        Args:
            team_id: Team to analyze
            start_gw: Starting gameweek
            num_gameweeks: How many gameweeks to look ahead (default 6)

        Returns:
            Dict with:
                - fixtures: List of upcoming fixtures with difficulty
                - average_difficulty: Mean difficulty over period
                - difficulty_trend: 'improving', 'worsening', or 'stable'
                - recommendation: 'target', 'hold', or 'avoid'
        """
        logger.debug(f"Analyzing fixtures for team {team_id}, GW{start_gw}-{start_gw+num_gameweeks-1}")

        # Get upcoming fixtures
        fixtures = self.db.execute_query("""
            SELECT
                event as gameweek,
                team_h,
                team_a,
                team_h_difficulty,
                team_a_difficulty
            FROM fixtures
            WHERE (team_h = ? OR team_a = ?)
            AND event >= ?
            AND event < ?
            ORDER BY event
        """, (team_id, team_id, start_gw, start_gw + num_gameweeks))

        if not fixtures:
            return {'error': f'No fixtures found for team {team_id}'}

        # Calculate difficulty for each fixture from team's perspective
        fixture_details = []
        difficulties = []

        team_strengths = self.get_fixture_difficulty_ratings()

        for fixture in fixtures:
            is_home = fixture['team_h'] == team_id

            if is_home:
                opponent_id = fixture['team_a']
                difficulty = fixture['team_h_difficulty']
                venue = 'H'
                # Difficulty based on opponent's away strength
                opponent_strength = team_strengths.get(opponent_id, {}).get('strength_away', 3)
            else:
                opponent_id = fixture['team_h']
                difficulty = fixture['team_a_difficulty']
                venue = 'A'
                # Difficulty based on opponent's home strength
                opponent_strength = team_strengths.get(opponent_id, {}).get('strength_home', 3)

            opponent_name = team_strengths.get(opponent_id, {}).get('name', f'Team {opponent_id}')

            # Convert opponent strength to difficulty (1-5 scale)
            # Higher opponent strength = higher difficulty
            calculated_difficulty = min(5, max(1, round(opponent_strength / 250)))

            fixture_details.append({
                'gameweek': fixture['gameweek'],
                'opponent': opponent_name,
                'opponent_id': opponent_id,
                'venue': venue,
                'difficulty': difficulty or calculated_difficulty,
                'opponent_strength': opponent_strength
            })

            difficulties.append(difficulty or calculated_difficulty)

        # Calculate average difficulty
        avg_difficulty = sum(difficulties) / len(difficulties) if difficulties else 3.0

        # Determine trend (compare first half vs second half)
        mid_point = len(difficulties) // 2
        if mid_point > 0:
            first_half_avg = sum(difficulties[:mid_point]) / mid_point
            second_half_avg = sum(difficulties[mid_point:]) / (len(difficulties) - mid_point)

            if second_half_avg < first_half_avg - 0.5:
                trend = 'improving'
            elif second_half_avg > first_half_avg + 0.5:
                trend = 'worsening'
            else:
                trend = 'stable'
        else:
            trend = 'stable'

        # Generate recommendation
        if avg_difficulty <= 2.5:
            recommendation = 'target'  # Good fixtures, bring players in
        elif avg_difficulty >= 3.5:
            recommendation = 'avoid'   # Bad fixtures, move players out
        else:
            recommendation = 'hold'    # Neutral fixtures

        return {
            'team_id': team_id,
            'team_name': team_strengths.get(team_id, {}).get('name', f'Team {team_id}'),
            'fixtures': fixture_details,
            'average_difficulty': avg_difficulty,
            'difficulty_trend': trend,
            'recommendation': recommendation,
            'analysis_period': f'GW{start_gw}-{start_gw+num_gameweeks-1}'
        }

    def identify_fixture_swings(self, start_gw: int, num_gameweeks: int = 6) -> List[Dict]:
        """
        Identify teams with significant fixture swings.

        A fixture swing is when difficulty changes significantly over the period,
        indicating optimal transfer timing.

        Args:
            start_gw: Starting gameweek
            num_gameweeks: Analysis window

        Returns:
            List of teams with fixture swings, sorted by opportunity
        """
        logger.info(f"Identifying fixture swings for GW{start_gw}-{start_gw+num_gameweeks-1}")

        # Get all teams
        teams = self.db.execute_query("SELECT id, name FROM teams ORDER BY id")

        swings = []

        for team in teams:
            analysis = self.analyze_upcoming_fixtures(team['id'], start_gw, num_gameweeks)

            if 'error' in analysis:
                continue

            # Look for significant swings
            fixtures = analysis['fixtures']

            if len(fixtures) < 4:
                continue

            # Compare first 3 GWs vs last 3 GWs
            first_three = [f['difficulty'] for f in fixtures[:3]]
            last_three = [f['difficulty'] for f in fixtures[-3:]]

            first_avg = sum(first_three) / len(first_three)
            last_avg = sum(last_three) / len(last_three)

            swing_magnitude = last_avg - first_avg

            # Significant swing if change > 1.0 on difficulty scale
            if abs(swing_magnitude) >= 1.0:
                swing_type = 'favorable' if swing_magnitude < 0 else 'unfavorable'

                swings.append({
                    'team_id': team['id'],
                    'team_name': team['name'],
                    'swing_type': swing_type,
                    'swing_magnitude': swing_magnitude,
                    'early_difficulty': first_avg,
                    'late_difficulty': last_avg,
                    'recommendation': 'bring_in' if swing_type == 'favorable' else 'move_out',
                    'optimal_gw': start_gw + 2 if swing_type == 'favorable' else start_gw,
                    'fixtures': analysis['fixtures']
                })

        # Sort by swing magnitude (most significant first)
        swings.sort(key=lambda x: abs(x['swing_magnitude']), reverse=True)

        logger.info(f"Found {len(swings)} significant fixture swings")

        return swings

    def find_best_fixture_runs(self, start_gw: int, num_gameweeks: int = 6,
                               top_n: int = 10) -> List[Dict]:
        """
        Find teams with the best upcoming fixture runs.

        Args:
            start_gw: Starting gameweek
            num_gameweeks: Analysis window
            top_n: Return top N teams

        Returns:
            List of teams with best fixtures, sorted by difficulty
        """
        logger.info(f"Finding best fixture runs for GW{start_gw}-{start_gw+num_gameweeks-1}")

        teams = self.db.execute_query("SELECT id, name FROM teams ORDER BY id")

        fixture_runs = []

        for team in teams:
            analysis = self.analyze_upcoming_fixtures(team['id'], start_gw, num_gameweeks)

            if 'error' not in analysis:
                fixture_runs.append({
                    'team_id': team['id'],
                    'team_name': analysis['team_name'],
                    'average_difficulty': analysis['average_difficulty'],
                    'trend': analysis['difficulty_trend'],
                    'fixtures': analysis['fixtures'],
                    'recommendation': analysis['recommendation']
                })

        # Sort by average difficulty (easiest first)
        fixture_runs.sort(key=lambda x: x['average_difficulty'])

        return fixture_runs[:top_n]

    def get_player_fixture_rating(self, player_id: int, start_gw: int,
                                  num_gameweeks: int = 4) -> Dict:
        """
        Get fixture rating for a specific player over next N gameweeks.

        Useful for transfer decisions and captain picks.

        Args:
            player_id: Player to analyze
            start_gw: Starting gameweek
            num_gameweeks: How many gameweeks ahead

        Returns:
            Dict with fixture analysis for this player
        """
        # Get player's team
        player = self.db.execute_query("""
            SELECT id, web_name, element_type, team_id
            FROM players
            WHERE id = ?
        """, (player_id,))

        if not player:
            return {'error': f'Player {player_id} not found'}

        player = player[0]

        # Get team fixture analysis
        team_analysis = self.analyze_upcoming_fixtures(
            player['team_id'],
            start_gw,
            num_gameweeks
        )

        if 'error' in team_analysis:
            return team_analysis

        # Position-specific weighting
        # Attackers care more about opponent's defensive strength
        # Defenders care more about opponent's attacking strength
        position = player['element_type']  # 1=GK, 2=DEF, 3=MID, 4=FWD

        fixture_ratings = []
        team_strengths = self.get_fixture_difficulty_ratings()

        for fixture in team_analysis['fixtures']:
            opponent_id = fixture['opponent_id']
            opponent = team_strengths.get(opponent_id, {})

            # Weight by position
            if position in [1, 2]:  # GK/DEF - care about clean sheets
                # Easier if opponent has weak attack
                if fixture['venue'] == 'H':
                    strength = opponent.get('attack_away', 500)
                else:
                    strength = opponent.get('attack_home', 500)
                rating = max(1, min(5, round(strength / 250)))
            else:  # MID/FWD - care about scoring
                # Easier if opponent has weak defence
                if fixture['venue'] == 'H':
                    strength = opponent.get('defence_away', 500)
                else:
                    strength = opponent.get('defence_home', 500)
                rating = max(1, min(5, 6 - round(strength / 250)))

            fixture_ratings.append({
                'gameweek': fixture['gameweek'],
                'opponent': fixture['opponent'],
                'venue': fixture['venue'],
                'rating': rating,
                'difficulty': fixture['difficulty']
            })

        avg_rating = sum(f['rating'] for f in fixture_ratings) / len(fixture_ratings)

        return {
            'player_id': player_id,
            'player_name': player['web_name'],
            'position': position,
            'team_id': player['team_id'],
            'fixtures': fixture_ratings,
            'average_rating': avg_rating,
            'recommendation': 'favorable' if avg_rating <= 2.5 else ('neutral' if avg_rating <= 3.5 else 'difficult')
        }
