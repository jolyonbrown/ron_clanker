#!/usr/bin/env python3
"""
Feature Engineering for Player Performance Prediction

Extracts and engineers features from historical data for ML models:
- Recent form (rolling averages)
- Fixture difficulty
- Home/away performance
- Defensive contribution potential
- Opposition strength
- Playing time trends
"""

import logging
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime

logger = logging.getLogger('ron_clanker.ml.features')


class FeatureEngineer:
    """
    Engineers features for player performance prediction.
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("FeatureEngineer: Initialized")

    def get_player_recent_form(self, player_id: int, gameweek: int, window: int = 5) -> Dict:
        """
        Calculate rolling averages for player's recent form.

        Args:
            player_id: Player ID
            gameweek: Current gameweek (predict for next GW)
            window: Number of previous gameweeks to average

        Returns:
            Dict with rolling averages:
                - avg_points: Average total points
                - avg_minutes: Average minutes played
                - avg_goals: Average goals per game
                - avg_assists: Average assists per game
                - avg_bonus: Average bonus points
                - avg_bps: Average BPS
                - avg_influence: Average ICT influence component
                - avg_creativity: Average ICT creativity component
                - avg_threat: Average ICT threat component
                - avg_ict_index: Average ICT index (sum of influence, creativity, threat)
                - form_trend: Slope of last N games (improving/declining)
        """
        history = self.db.execute_query("""
            SELECT
                gameweek, total_points, minutes, goals_scored, assists,
                bonus, bps, clean_sheets, saves,
                influence, creativity, threat, ict_index
            FROM player_gameweek_history
            WHERE player_id = ?
            AND gameweek < ?
            ORDER BY gameweek DESC
            LIMIT ?
        """, (player_id, gameweek, window))

        if not history or len(history) == 0:
            return {
                'avg_points': 0.0,
                'avg_minutes': 0.0,
                'avg_goals': 0.0,
                'avg_assists': 0.0,
                'avg_bonus': 0.0,
                'avg_bps': 0.0,
                'avg_clean_sheets': 0.0,
                'avg_saves': 0.0,
                'avg_influence': 0.0,
                'avg_creativity': 0.0,
                'avg_threat': 0.0,
                'avg_ict_index': 0.0,
                'form_trend': 0.0,
                'games_played': 0
            }

        games_played = len(history)
        total_points = [h['total_points'] for h in history]

        # Calculate trend (linear regression slope)
        if len(total_points) >= 3:
            x = np.arange(len(total_points))
            coeffs = np.polyfit(x, total_points, 1)
            form_trend = coeffs[0]  # Slope
        else:
            form_trend = 0.0

        return {
            'avg_points': np.mean([h['total_points'] for h in history]),
            'avg_minutes': np.mean([h['minutes'] for h in history]),
            'avg_goals': np.mean([h['goals_scored'] for h in history]),
            'avg_assists': np.mean([h['assists'] for h in history]),
            'avg_bonus': np.mean([h['bonus'] for h in history]),
            'avg_bps': np.mean([h['bps'] for h in history]),
            'avg_clean_sheets': np.mean([h['clean_sheets'] for h in history]),
            'avg_saves': np.mean([h['saves'] for h in history]),
            'avg_influence': np.mean([h['influence'] or 0 for h in history]),
            'avg_creativity': np.mean([h['creativity'] or 0 for h in history]),
            'avg_threat': np.mean([h['threat'] or 0 for h in history]),
            'avg_ict_index': np.mean([h['ict_index'] or 0 for h in history]),
            'form_trend': form_trend,
            'games_played': games_played,
            # xG/xA defaults (not available in current season data)
            'avg_xg': 0.0,
            'avg_xa': 0.0,
            'avg_xgi': 0.0,
            'xg_overperformance': 0.0,
            'xa_overperformance': 0.0
        }

    def get_historical_xg_features(self, player_id: int, window: int = 5) -> Dict:
        """
        Get xG/xA features from historical gameweek data.

        These features are only available in historical data (previous seasons),
        not in current season player_gameweek_history.

        Args:
            player_id: Player ID (current season)
            window: Number of recent games to average

        Returns:
            Dict with xG/xA averages
        """
        # First get the stable player code from current player ID
        player = self.db.execute_query(
            "SELECT code FROM players WHERE id = ?", (player_id,)
        )
        if not player or not player[0]['code']:
            return {
                'avg_xg': 0.0,
                'avg_xa': 0.0,
                'avg_xgi': 0.0,
                'xg_overperformance': 0.0,
                'xa_overperformance': 0.0
            }

        player_code = player[0]['code']

        # Query historical data using stable player_code
        history = self.db.execute_query("""
            SELECT
                expected_goals, expected_assists, expected_goal_involvements,
                goals_scored, assists
            FROM historical_gameweek_data
            WHERE player_code = ?
            ORDER BY season_id DESC, gameweek DESC
            LIMIT ?
        """, (player_code, window))

        if not history or len(history) == 0:
            return {
                'avg_xg': 0.0,
                'avg_xa': 0.0,
                'avg_xgi': 0.0,
                'xg_overperformance': 0.0,
                'xa_overperformance': 0.0
            }

        avg_xg = np.mean([h['expected_goals'] or 0 for h in history])
        avg_xa = np.mean([h['expected_assists'] or 0 for h in history])
        avg_xgi = np.mean([h['expected_goal_involvements'] or 0 for h in history])
        avg_goals = np.mean([h['goals_scored'] or 0 for h in history])
        avg_assists = np.mean([h['assists'] or 0 for h in history])

        return {
            'avg_xg': avg_xg,
            'avg_xa': avg_xa,
            'avg_xgi': avg_xgi,
            'xg_overperformance': avg_goals - avg_xg,  # Over/under performing xG
            'xa_overperformance': avg_assists - avg_xa
        }

    def get_fixture_difficulty(self, team_id: int, gameweek: int) -> Dict:
        """
        Get fixture difficulty for team's next match.

        Returns:
            Dict with:
                - difficulty: FPL difficulty rating (1-5)
                - is_home: Boolean
                - opponent_strength: Opposition team strength
                - opponent_defensive_strength: How good opposition is defensively
                - opponent_attacking_strength: How good opposition is going forward
        """
        fixture = self.db.execute_query("""
            SELECT
                f.id, f.team_h, f.team_a,
                f.team_h_difficulty, f.team_a_difficulty,
                t_h.strength as h_strength,
                t_a.strength as a_strength,
                t_h.strength_defence_home as h_def,
                t_a.strength_defence_away as a_def,
                t_h.strength_attack_home as h_att,
                t_a.strength_attack_away as a_att
            FROM fixtures f
            JOIN teams t_h ON f.team_h = t_h.id
            JOIN teams t_a ON f.team_a = t_a.id
            WHERE f.event = ?
            AND (f.team_h = ? OR f.team_a = ?)
            LIMIT 1
        """, (gameweek, team_id, team_id))

        if not fixture:
            return {
                'difficulty': 3,  # Default medium
                'is_home': True,
                'opponent_strength': 3,
                'opponent_defensive_strength': 3,
                'opponent_attacking_strength': 3
            }

        fix = fixture[0]
        is_home = fix['team_h'] == team_id

        if is_home:
            difficulty = fix['team_h_difficulty'] or 3
            opp_strength = fix['a_strength'] or 1000
            opp_def_strength = fix['a_def'] or 1000
            opp_att_strength = fix['a_att'] or 1000
        else:
            difficulty = fix['team_a_difficulty'] or 3
            opp_strength = fix['h_strength'] or 1000
            opp_def_strength = fix['h_def'] or 1000
            opp_att_strength = fix['h_att'] or 1000

        return {
            'difficulty': difficulty,
            'is_home': is_home,
            'opponent_strength': opp_strength / 1000.0,  # Normalize to 0-5 range
            'opponent_defensive_strength': opp_def_strength / 1000.0,
            'opponent_attacking_strength': opp_att_strength / 1000.0
        }

    def get_player_season_stats(self, player_id: int) -> Dict:
        """
        Get player's season-to-date statistics.

        Returns cumulative stats for the entire season so far.
        """
        season_stats = self.db.execute_query("""
            SELECT
                COUNT(*) as games_played,
                SUM(total_points) as total_points,
                SUM(minutes) as total_minutes,
                SUM(goals_scored) as total_goals,
                SUM(assists) as total_assists,
                SUM(clean_sheets) as total_cs,
                SUM(bonus) as total_bonus,
                AVG(bps) as avg_bps
            FROM player_gameweek_history
            WHERE player_id = ?
        """, (player_id,))

        if not season_stats or season_stats[0]['games_played'] == 0:
            return {
                'games_played': 0,
                'points_per_game': 0.0,
                'minutes_per_game': 0.0,
                'goals_per_game': 0.0,
                'assists_per_game': 0.0,
                'cs_per_game': 0.0
            }

        stats = season_stats[0]
        games = stats['games_played'] or 1

        return {
            'games_played': games,
            'points_per_game': stats['total_points'] / games if games > 0 else 0.0,
            'minutes_per_game': stats['total_minutes'] / games if games > 0 else 0.0,
            'goals_per_game': stats['total_goals'] / games if games > 0 else 0.0,
            'assists_per_game': stats['total_assists'] / games if games > 0 else 0.0,
            'cs_per_game': stats['total_cs'] / games if games > 0 else 0.0
        }

    def engineer_features(self, player_id: int, gameweek: int) -> Dict:
        """
        Engineer all features for a player for a specific gameweek prediction.

        Args:
            player_id: Player ID
            gameweek: Gameweek to predict for

        Returns:
            Dict with all engineered features ready for ML model
        """
        # Get player info
        player = self.db.execute_query("""
            SELECT
                id, code, web_name, element_type, team_id, now_cost,
                selected_by_percent, form, points_per_game,
                minutes, goals_scored, assists, clean_sheets,
                influence, creativity, threat, ict_index
            FROM players
            WHERE id = ?
        """, (player_id,))

        if not player:
            logger.warning(f"FeatureEngineer: Player {player_id} not found")
            return None

        p = player[0]

        # Get recent form
        recent_form = self.get_player_recent_form(player_id, gameweek, window=5)

        # Get xG/xA features from historical data (if available)
        xg_features = self.get_historical_xg_features(player_id, window=5)
        # Merge xG/xA into recent_form (overwrite defaults with actual data if available)
        recent_form.update(xg_features)

        # Get fixture difficulty
        fixture = self.get_fixture_difficulty(p['team_id'], gameweek)

        # Get season stats
        season = self.get_player_season_stats(player_id)

        # Combine all features
        features = {
            # Player attributes
            'player_id': player_id,
            'player_code': p['code'],  # FPL unique player code (for model compatibility)
            'position': p['element_type'],  # 1=GK, 2=DEF, 3=MID, 4=FWD
            'price': p['now_cost'] / 10.0,
            'ownership': float(p['selected_by_percent'] or 0),

            # FPL calculated stats
            'fpl_form': float(p['form'] or 0),
            'fpl_points_per_game': float(p['points_per_game'] or 0),

            # Current ICT metrics
            'current_influence': float(p['influence'] or 0),
            'current_creativity': float(p['creativity'] or 0),
            'current_threat': float(p['threat'] or 0),
            'current_ict_index': float(p['ict_index'] or 0),

            # Recent form (last 5 games)
            'form_avg_points': recent_form['avg_points'],
            'form_avg_minutes': recent_form['avg_minutes'],
            'form_avg_goals': recent_form['avg_goals'],
            'form_avg_assists': recent_form['avg_assists'],
            'form_avg_bonus': recent_form['avg_bonus'],
            'form_avg_bps': recent_form['avg_bps'],
            'form_avg_clean_sheets': recent_form['avg_clean_sheets'],
            'form_avg_saves': recent_form['avg_saves'],
            'form_avg_influence': recent_form['avg_influence'],
            'form_avg_creativity': recent_form['avg_creativity'],
            'form_avg_threat': recent_form['avg_threat'],
            'form_avg_ict_index': recent_form['avg_ict_index'],
            'form_trend': recent_form['form_trend'],
            'form_games_played': recent_form['games_played'],

            # Expected goals/assists (if available from historical data)
            'avg_xg': recent_form.get('avg_xg', 0.0),
            'avg_xa': recent_form.get('avg_xa', 0.0),
            'avg_xgi': recent_form.get('avg_xgi', 0.0),  # Expected goal involvements
            'xg_overperformance': recent_form.get('xg_overperformance', 0.0),  # goals - xG
            'xa_overperformance': recent_form.get('xa_overperformance', 0.0),  # assists - xA

            # Season stats
            'season_games': season['games_played'],
            'season_ppg': season['points_per_game'],
            'season_mpg': season['minutes_per_game'],
            'season_gpg': season['goals_per_game'],
            'season_apg': season['assists_per_game'],
            'season_cs_pg': season['cs_per_game'],

            # Fixture
            'fixture_difficulty': fixture['difficulty'],
            'is_home': 1 if fixture['is_home'] else 0,
            'opponent_strength': fixture['opponent_strength'],
            'opponent_defensive_strength': fixture['opponent_defensive_strength'],
            'opponent_attacking_strength': fixture['opponent_attacking_strength'],

            # Derived features
            'minutes_reliability': min(1.0, recent_form['avg_minutes'] / 90.0),  # 0-1 scale
            'attacking_threat': (recent_form['avg_goals'] * 4) + (recent_form['avg_assists'] * 3),
            'defensive_reliability': recent_form['avg_clean_sheets'],
        }

        return features

    def engineer_batch_features(self, player_ids: List[int], gameweek: int) -> List[Dict]:
        """
        Engineer features for multiple players at once.

        More efficient than calling engineer_features individually.
        """
        features_list = []

        for player_id in player_ids:
            features = self.engineer_features(player_id, gameweek)
            if features:
                features_list.append(features)

        logger.info(f"FeatureEngineer: Engineered features for {len(features_list)} players for GW{gameweek}")
        return features_list
