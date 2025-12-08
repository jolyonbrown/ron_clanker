"""
Elo Rating System for Fixture Difficulty

Replaces crude FPL API fixture difficulty ratings (1-5) with a learned
Elo-like system based on actual match results.

Features:
- Separate attacking and defensive Elo per team
- Updates after each gameweek based on actual results
- Better reflects true fixture difficulty than static FPL ratings
- Home advantage adjustment
- Recency weighting (recent form matters more)

Usage:
    from ml.elo_ratings import EloRatingSystem

    elo = EloRatingSystem(db_path='data/ron_clanker.db')

    # Update ratings after GW results
    elo.update_after_gameweek(gameweek=12)

    # Get fixture difficulty for upcoming match
    difficulty = elo.get_fixture_difficulty(
        team_id=1,  # Arsenal
        opponent_id=2,  # Aston Villa
        is_home=True,
        for_attackers=True  # vs for_defenders
    )

    # Get team strength
    strength = elo.get_team_strength(team_id=1)
    # Returns: {'attacking_elo': 1520, 'defensive_elo': 1480, 'overall': 1500}
"""

import sqlite3
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json

logger = logging.getLogger('ron_clanker.elo')

# Starting Elo for new teams (Premier League average)
BASE_ELO = 1500

# K-factor: how quickly ratings change after a match
# Higher = more reactive to recent results
K_FACTOR = 32

# Home advantage in Elo points
HOME_ADVANTAGE = 100

# Expected goals difference factor (converts goal diff to Elo change)
GOAL_DIFF_FACTOR = 50


class EloRatingSystem:
    """
    Elo-based rating system for Premier League teams.

    Tracks separate attacking and defensive Elo ratings.
    """

    def __init__(self, db_path: str = 'data/ron_clanker.db'):
        self.db_path = db_path
        self._ensure_tables()
        self._initialize_teams()

    def _ensure_tables(self):
        """Create Elo tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elo_ratings (
                team_id INTEGER NOT NULL,
                gameweek INTEGER NOT NULL,
                attacking_elo REAL NOT NULL,
                defensive_elo REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, gameweek)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elo_match_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek INTEGER NOT NULL,
                home_team_id INTEGER NOT NULL,
                away_team_id INTEGER NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                home_elo_change REAL,
                away_elo_change REAL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_elo_ratings_team_gw
            ON elo_ratings(team_id, gameweek DESC)
        """)

        conn.commit()
        conn.close()

    def _initialize_teams(self):
        """Initialize Elo ratings for any teams without ratings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get all teams
            cursor.execute("SELECT id, short_name FROM teams")
            teams = cursor.fetchall()

            for team in teams:
                # Check if team has any Elo ratings
                cursor.execute("""
                    SELECT COUNT(*) as cnt FROM elo_ratings WHERE team_id = ?
                """, (team['id'],))
                count = cursor.fetchone()['cnt']

                if count == 0:
                    # Initialize with base Elo at gameweek 0
                    cursor.execute("""
                        INSERT INTO elo_ratings (team_id, gameweek, attacking_elo, defensive_elo)
                        VALUES (?, 0, ?, ?)
                    """, (team['id'], BASE_ELO, BASE_ELO))
                    logger.info(f"Initialized Elo for {team['short_name']} (id={team['id']})")

            conn.commit()

        finally:
            conn.close()

    def get_current_ratings(self, team_id: int) -> Dict[str, float]:
        """
        Get the most recent Elo ratings for a team.

        Returns:
            Dict with 'attacking_elo', 'defensive_elo', 'overall', 'gameweek'
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT attacking_elo, defensive_elo, gameweek
                FROM elo_ratings
                WHERE team_id = ?
                ORDER BY gameweek DESC
                LIMIT 1
            """, (team_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'attacking_elo': row['attacking_elo'],
                    'defensive_elo': row['defensive_elo'],
                    'overall': (row['attacking_elo'] + row['defensive_elo']) / 2,
                    'gameweek': row['gameweek']
                }
            else:
                return {
                    'attacking_elo': BASE_ELO,
                    'defensive_elo': BASE_ELO,
                    'overall': BASE_ELO,
                    'gameweek': 0
                }
        finally:
            conn.close()

    def get_all_ratings(self, gameweek: Optional[int] = None) -> Dict[int, Dict]:
        """
        Get Elo ratings for all teams.

        Args:
            gameweek: Specific gameweek (None = most recent)

        Returns:
            Dict mapping team_id to ratings dict
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if gameweek is not None:
                cursor.execute("""
                    SELECT team_id, attacking_elo, defensive_elo
                    FROM elo_ratings
                    WHERE gameweek = ?
                """, (gameweek,))
            else:
                # Get most recent for each team
                cursor.execute("""
                    SELECT e.team_id, e.attacking_elo, e.defensive_elo, e.gameweek
                    FROM elo_ratings e
                    INNER JOIN (
                        SELECT team_id, MAX(gameweek) as max_gw
                        FROM elo_ratings
                        GROUP BY team_id
                    ) latest ON e.team_id = latest.team_id AND e.gameweek = latest.max_gw
                """)

            ratings = {}
            for row in cursor.fetchall():
                ratings[row['team_id']] = {
                    'attacking_elo': row['attacking_elo'],
                    'defensive_elo': row['defensive_elo'],
                    'overall': (row['attacking_elo'] + row['defensive_elo']) / 2
                }

            return ratings

        finally:
            conn.close()

    def calculate_expected_score(
        self,
        team_elo: float,
        opponent_elo: float,
        is_home: bool = True
    ) -> float:
        """
        Calculate expected score (0-1) based on Elo difference.

        Returns probability of team winning (with draws = 0.5)
        """
        if is_home:
            team_elo += HOME_ADVANTAGE

        expected = 1 / (1 + 10 ** ((opponent_elo - team_elo) / 400))
        return expected

    def update_ratings_from_match(
        self,
        home_team_id: int,
        away_team_id: int,
        home_goals: int,
        away_goals: int,
        gameweek: int
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Update Elo ratings based on match result.

        Uses separate updates for attacking and defensive Elo:
        - Attacking Elo: updated based on goals scored vs expected
        - Defensive Elo: updated based on goals conceded vs expected

        Returns:
            Tuple of (home_changes, away_changes) dicts with 'attacking', 'defensive' keys
        """
        # Get current ratings
        home_ratings = self.get_current_ratings(home_team_id)
        away_ratings = self.get_current_ratings(away_team_id)

        # Calculate expected goals based on attacking vs defensive Elo
        # Home expected goals = f(home_attacking vs away_defensive)
        home_attacking_strength = home_ratings['attacking_elo'] + HOME_ADVANTAGE
        away_defensive_strength = away_ratings['defensive_elo']

        # Away expected goals = f(away_attacking vs home_defensive)
        away_attacking_strength = away_ratings['attacking_elo']
        home_defensive_strength = home_ratings['defensive_elo'] + HOME_ADVANTAGE

        # Expected goals (sigmoid transformation)
        home_expected = self._elo_to_expected_goals(
            home_attacking_strength - away_defensive_strength
        )
        away_expected = self._elo_to_expected_goals(
            away_attacking_strength - home_defensive_strength
        )

        # Calculate actual performance
        home_attacking_perf = home_goals / max(home_expected, 0.5)  # Ratio of actual/expected
        away_attacking_perf = away_goals / max(away_expected, 0.5)

        home_defensive_perf = away_expected / max(away_goals, 0.5)  # Inverted - fewer goals = better
        away_defensive_perf = home_expected / max(home_goals, 0.5)

        # Convert performance ratios to Elo changes
        home_changes = {
            'attacking': self._performance_to_elo_change(home_attacking_perf),
            'defensive': self._performance_to_elo_change(home_defensive_perf)
        }
        away_changes = {
            'attacking': self._performance_to_elo_change(away_attacking_perf),
            'defensive': self._performance_to_elo_change(away_defensive_perf)
        }

        # Apply changes and store new ratings
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # New home ratings
            new_home_attacking = home_ratings['attacking_elo'] + home_changes['attacking']
            new_home_defensive = home_ratings['defensive_elo'] + home_changes['defensive']

            # New away ratings
            new_away_attacking = away_ratings['attacking_elo'] + away_changes['attacking']
            new_away_defensive = away_ratings['defensive_elo'] + away_changes['defensive']

            # Store new ratings
            cursor.execute("""
                INSERT OR REPLACE INTO elo_ratings
                (team_id, gameweek, attacking_elo, defensive_elo)
                VALUES (?, ?, ?, ?)
            """, (home_team_id, gameweek, new_home_attacking, new_home_defensive))

            cursor.execute("""
                INSERT OR REPLACE INTO elo_ratings
                (team_id, gameweek, attacking_elo, defensive_elo)
                VALUES (?, ?, ?, ?)
            """, (away_team_id, gameweek, new_away_attacking, new_away_defensive))

            # Record match result
            cursor.execute("""
                INSERT INTO elo_match_results
                (gameweek, home_team_id, away_team_id, home_goals, away_goals,
                 home_elo_change, away_elo_change)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                gameweek, home_team_id, away_team_id, home_goals, away_goals,
                home_changes['attacking'] + home_changes['defensive'],
                away_changes['attacking'] + away_changes['defensive']
            ))

            conn.commit()

        finally:
            conn.close()

        return home_changes, away_changes

    def _elo_to_expected_goals(self, elo_diff: float) -> float:
        """Convert Elo difference to expected goals."""
        # Average PL goals per team per match ≈ 1.4
        base_goals = 1.4
        # Adjust based on Elo difference (every 100 Elo ≈ 0.3 goals difference)
        adjustment = elo_diff / 300
        return max(0.5, base_goals + adjustment)

    def _performance_to_elo_change(self, performance_ratio: float) -> float:
        """Convert performance ratio to Elo change."""
        # Ratio of 1.0 = performed as expected = no change
        # Ratio > 1.0 = over-performed = Elo increase
        # Ratio < 1.0 = under-performed = Elo decrease
        # Cap the ratio to avoid extreme swings
        capped_ratio = max(0.2, min(5.0, performance_ratio))

        # Log scale to smooth extreme values
        import math
        change = K_FACTOR * math.log(capped_ratio)

        return change

    def update_after_gameweek(self, gameweek: int) -> int:
        """
        Update all Elo ratings based on gameweek results.

        Args:
            gameweek: The completed gameweek number

        Returns:
            Number of matches processed
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get completed fixtures for this gameweek
            cursor.execute("""
                SELECT
                    team_h as home_id,
                    team_a as away_id,
                    team_h_score as home_goals,
                    team_a_score as away_goals
                FROM fixtures
                WHERE event = ?
                AND finished = 1
                AND team_h_score IS NOT NULL
                AND team_a_score IS NOT NULL
            """, (gameweek,))

            matches_processed = 0
            rows = cursor.fetchall()

            for row in rows:
                home_id = row['home_id']
                away_id = row['away_id']
                home_goals = row['home_goals']
                away_goals = row['away_goals']

                # Check if already processed
                cursor.execute("""
                    SELECT id FROM elo_match_results
                    WHERE gameweek = ? AND home_team_id = ? AND away_team_id = ?
                """, (gameweek, home_id, away_id))

                if cursor.fetchone():
                    continue

                # Update ratings
                self.update_ratings_from_match(
                    home_id, away_id, home_goals, away_goals, gameweek
                )
                matches_processed += 1

            logger.info(f"Updated Elo ratings for GW{gameweek}: {matches_processed} matches")
            return matches_processed

        finally:
            conn.close()

    def get_fixture_difficulty(
        self,
        team_id: int,
        opponent_id: int,
        is_home: bool,
        for_attackers: bool = True
    ) -> float:
        """
        Get fixture difficulty rating (1-5 scale like FPL).

        Args:
            team_id: The team we're evaluating for
            opponent_id: The opponent
            is_home: Whether team_id is playing at home
            for_attackers: True for attacking difficulty (vs opponent defense)
                          False for defensive difficulty (vs opponent attack)

        Returns:
            Float between 1.0 (easiest) and 5.0 (hardest)
        """
        opponent_ratings = self.get_current_ratings(opponent_id)

        if for_attackers:
            # For attackers: opponent's defensive strength matters
            opponent_strength = opponent_ratings['defensive_elo']
        else:
            # For defenders: opponent's attacking strength matters
            opponent_strength = opponent_ratings['attacking_elo']

        # Adjust for home/away
        if is_home:
            opponent_strength -= HOME_ADVANTAGE / 2  # Playing at home helps
        else:
            opponent_strength += HOME_ADVANTAGE / 2  # Playing away hurts

        # Convert Elo to 1-5 scale
        # Base Elo (1500) = difficulty 3
        # Every 100 Elo points = 0.5 difficulty change
        difficulty = 3.0 + (opponent_strength - BASE_ELO) / 200

        # Clamp to 1-5 range
        return max(1.0, min(5.0, difficulty))

    def get_fixture_difficulties(
        self,
        team_id: int,
        opponent_ids: List[int],
        is_home: List[bool]
    ) -> List[Dict[str, float]]:
        """
        Get fixture difficulties for multiple upcoming fixtures.

        Args:
            team_id: The team we're evaluating for
            opponent_ids: List of opponent team IDs
            is_home: List of booleans (True if home fixture)

        Returns:
            List of dicts with 'attacking' and 'defensive' difficulty
        """
        difficulties = []
        for opp_id, home in zip(opponent_ids, is_home):
            difficulties.append({
                'opponent_id': opp_id,
                'is_home': home,
                'attacking_difficulty': self.get_fixture_difficulty(
                    team_id, opp_id, home, for_attackers=True
                ),
                'defensive_difficulty': self.get_fixture_difficulty(
                    team_id, opp_id, home, for_attackers=False
                )
            })
        return difficulties

    def get_rankings(self) -> List[Dict]:
        """
        Get all teams ranked by overall Elo.

        Returns:
            List of team dicts sorted by overall Elo (descending)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    t.id as team_id,
                    t.name as team_name,
                    t.short_name,
                    e.attacking_elo,
                    e.defensive_elo,
                    (e.attacking_elo + e.defensive_elo) / 2 as overall_elo,
                    e.gameweek as as_of_gw
                FROM teams t
                JOIN elo_ratings e ON t.id = e.team_id
                INNER JOIN (
                    SELECT team_id, MAX(gameweek) as max_gw
                    FROM elo_ratings
                    GROUP BY team_id
                ) latest ON e.team_id = latest.team_id AND e.gameweek = latest.max_gw
                ORDER BY overall_elo DESC
            """)

            rankings = []
            for i, row in enumerate(cursor.fetchall(), 1):
                rankings.append({
                    'rank': i,
                    'team_id': row['team_id'],
                    'team_name': row['team_name'],
                    'short_name': row['short_name'],
                    'attacking_elo': round(row['attacking_elo'], 1),
                    'defensive_elo': round(row['defensive_elo'], 1),
                    'overall_elo': round(row['overall_elo'], 1),
                    'as_of_gw': row['as_of_gw']
                })

            return rankings

        finally:
            conn.close()

    def backfill_from_historical(self, seasons: List[str] = None):
        """
        Backfill Elo ratings from historical data.

        Derives match results from player-level data by aggregating goals.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Check if historical tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='historical_gameweek_data'
            """)
            if not cursor.fetchone():
                logger.warning("Historical data not available for Elo backfill")
                return

            # Get seasons to process
            if seasons is None:
                cursor.execute("SELECT DISTINCT season_id FROM historical_gameweek_data ORDER BY season_id")
                seasons = [r['season_id'] for r in cursor.fetchall()]

            logger.info(f"Backfilling Elo from seasons: {seasons}")

            for season in seasons:
                # Derive match results from player goals
                # Group by gameweek, fixture_id, and team (home/away)
                cursor.execute("""
                    SELECT
                        h.season_id,
                        h.gameweek,
                        h.fixture_id,
                        hp.team_code,
                        h.opponent_team_code,
                        h.was_home,
                        SUM(h.goals_scored) as team_goals,
                        COUNT(DISTINCT h.player_code) as players
                    FROM historical_gameweek_data h
                    JOIN historical_players hp ON h.season_id = hp.season_id
                        AND h.player_code = hp.player_code
                    WHERE h.season_id = ?
                    AND h.fixture_id IS NOT NULL
                    AND h.minutes > 0
                    GROUP BY h.season_id, h.gameweek, h.fixture_id, hp.team_code, h.opponent_team_code, h.was_home
                    ORDER BY h.gameweek, h.fixture_id
                """, (season,))

                rows = cursor.fetchall()

                # Group into matches
                fixtures = {}
                for row in rows:
                    fid = row['fixture_id']
                    if fid not in fixtures:
                        fixtures[fid] = {'gw': row['gameweek'], 'home': None, 'away': None}

                    if row['was_home']:
                        fixtures[fid]['home'] = {
                            'team': row['team_code'],
                            'goals': row['team_goals']
                        }
                    else:
                        fixtures[fid]['away'] = {
                            'team': row['team_code'],
                            'goals': row['team_goals']
                        }

                # Process matches
                processed = 0
                for fid, fix in fixtures.items():
                    if fix['home'] and fix['away']:
                        # Map team codes to current team IDs
                        home_id = self._get_team_id_for_code(cursor, fix['home']['team'])
                        away_id = self._get_team_id_for_code(cursor, fix['away']['team'])

                        if home_id and away_id:
                            # Create pseudo-gameweek
                            year_prefix = int(season.split('-')[0])
                            pseudo_gw = year_prefix * 100 + fix['gw']

                            # Check if already processed
                            cursor.execute("""
                                SELECT id FROM elo_match_results
                                WHERE gameweek = ? AND home_team_id = ? AND away_team_id = ?
                            """, (pseudo_gw, home_id, away_id))

                            if not cursor.fetchone():
                                self.update_ratings_from_match(
                                    home_id, away_id,
                                    fix['home']['goals'], fix['away']['goals'],
                                    pseudo_gw
                                )
                                processed += 1

                logger.info(f"Processed {processed} matches from {season}")

        finally:
            conn.close()

    def _get_team_id_for_code(self, cursor, team_code: int) -> Optional[int]:
        """Get current team ID for a team code."""
        cursor.execute("SELECT id FROM teams WHERE code = ?", (team_code,))
        row = cursor.fetchone()
        return row['id'] if row else None


def get_elo_system(db_path: str = 'data/ron_clanker.db') -> EloRatingSystem:
    """Factory function to get an EloRatingSystem instance."""
    return EloRatingSystem(db_path)
