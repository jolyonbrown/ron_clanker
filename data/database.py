"""
Database interface for Ron Clanker's FPL system.

Provides connection management and core data access patterns.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import json
from datetime import datetime


class Database:
    """Main database interface."""

    def __init__(self, db_path: str = "data/ron_clanker.db"):
        self.db_path = db_path
        self._ensure_database_exists()

    def _ensure_database_exists(self):
        """Create database and tables if they don't exist."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        if not db_file.exists():
            self.initialize_schema()

    def initialize_schema(self):
        """Initialize database schema from SQL file."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected rows."""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute query with multiple parameter sets."""
        with self.get_connection() as conn:
            cursor = conn.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount

    # ========================================================================
    # PLAYER DATA
    # ========================================================================

    def upsert_player(self, player_data: Dict[str, Any]) -> int:
        """Insert or update player data."""
        query = """
            INSERT INTO players (
                id, code, first_name, second_name, web_name, team_id,
                element_type, now_cost, selected_by_percent, form,
                points_per_game, total_points, status, news,
                chance_of_playing_next_round,
                influence, creativity, threat, ict_index,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                now_cost = excluded.now_cost,
                selected_by_percent = excluded.selected_by_percent,
                form = excluded.form,
                points_per_game = excluded.points_per_game,
                total_points = excluded.total_points,
                status = excluded.status,
                news = excluded.news,
                chance_of_playing_next_round = excluded.chance_of_playing_next_round,
                influence = excluded.influence,
                creativity = excluded.creativity,
                threat = excluded.threat,
                ict_index = excluded.ict_index,
                updated_at = CURRENT_TIMESTAMP
        """
        params = (
            player_data['id'], player_data.get('code'),
            player_data.get('first_name'), player_data.get('second_name'),
            player_data.get('web_name'), player_data.get('team'),
            player_data.get('element_type'), player_data.get('now_cost'),
            player_data.get('selected_by_percent'), player_data.get('form'),
            player_data.get('points_per_game'), player_data.get('total_points'),
            player_data.get('status'), player_data.get('news'),
            player_data.get('chance_of_playing_next_round'),
            player_data.get('influence'), player_data.get('creativity'),
            player_data.get('threat'), player_data.get('ict_index')
        )
        return self.execute_update(query, params)

    def get_all_players(self, element_type: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all players, optionally filtered by position."""
        query = "SELECT * FROM players"
        params = ()

        if element_type:
            query += " WHERE element_type = ?"
            params = (element_type,)

        query += " ORDER BY total_points DESC"
        return self.execute_query(query, params)

    def get_player(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific player by ID."""
        results = self.execute_query(
            "SELECT * FROM players WHERE id = ?",
            (player_id,)
        )
        return results[0] if results else None

    # ========================================================================
    # TEAM DATA (FPL Teams - Arsenal, Liverpool, etc.)
    # ========================================================================

    def upsert_team(self, team_data: Dict[str, Any]) -> int:
        """Insert or update team data."""
        query = """
            INSERT INTO teams (
                id, code, name, short_name, strength,
                strength_overall_home, strength_overall_away,
                strength_attack_home, strength_attack_away,
                strength_defence_home, strength_defence_away,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                short_name = excluded.short_name,
                strength = excluded.strength,
                strength_overall_home = excluded.strength_overall_home,
                strength_overall_away = excluded.strength_overall_away,
                strength_attack_home = excluded.strength_attack_home,
                strength_attack_away = excluded.strength_attack_away,
                strength_defence_home = excluded.strength_defence_home,
                strength_defence_away = excluded.strength_defence_away,
                updated_at = CURRENT_TIMESTAMP
        """
        params = (
            team_data['id'], team_data.get('code'),
            team_data.get('name'), team_data.get('short_name'),
            team_data.get('strength'),
            team_data.get('strength_overall_home'), team_data.get('strength_overall_away'),
            team_data.get('strength_attack_home'), team_data.get('strength_attack_away'),
            team_data.get('strength_defence_home'), team_data.get('strength_defence_away')
        )
        return self.execute_update(query, params)

    def get_team(self, team_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific team by ID."""
        results = self.execute_query(
            "SELECT * FROM teams WHERE id = ?",
            (team_id,)
        )
        return results[0] if results else None

    def get_all_teams(self) -> List[Dict[str, Any]]:
        """Get all teams."""
        return self.execute_query("SELECT * FROM teams ORDER BY name")

    # ========================================================================
    # TEAM STATE (Ron's FPL Team)
    # ========================================================================

    def get_current_team(self, gameweek: int) -> List[Dict[str, Any]]:
        """Get the current team for a gameweek."""
        query = """
            SELECT mt.*, p.web_name, p.element_type, p.team_id, p.now_cost
            FROM my_team mt
            JOIN players p ON mt.player_id = p.id
            WHERE mt.gameweek = ?
            ORDER BY mt.position
        """
        return self.execute_query(query, (gameweek,))

    def set_team(self, gameweek: int, team_data: List[Dict[str, Any]]):
        """Set the team for a gameweek."""
        # Clear existing team
        self.execute_update("DELETE FROM my_team WHERE gameweek = ?", (gameweek,))

        # Insert new team
        query = """
            INSERT INTO my_team
            (player_id, gameweek, position, purchase_price, selling_price,
             is_captain, is_vice_captain, multiplier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params_list = [
            (
                player.get('player_id', player.get('id')), gameweek, player['position'],
                player['purchase_price'], player['selling_price'],
                player.get('is_captain', False), player.get('is_vice_captain', False),
                player.get('multiplier', 1)
            )
            for player in team_data
        ]
        return self.execute_many(query, params_list)

    # ========================================================================
    # CURRENT/DRAFT TEAM (New Architecture)
    # ========================================================================

    def get_actual_current_team(self) -> List[Dict[str, Any]]:
        """
        Get Ron's actual current team (source of truth).

        Returns the 15 players in current_team table with full player details.
        """
        query = """
            SELECT
                ct.id,
                ct.player_id,
                ct.position,
                ct.purchase_price,
                ct.selling_price,
                ct.is_captain,
                ct.is_vice_captain,
                ct.multiplier,
                p.web_name,
                p.element_type,
                p.team_id,
                p.now_cost,
                p.form,
                p.points_per_game,
                p.status
            FROM current_team ct
            JOIN players p ON ct.player_id = p.id
            ORDER BY ct.position
        """
        return self.execute_query(query)

    def set_actual_current_team(self, team_data: List[Dict[str, Any]]) -> int:
        """
        Set Ron's actual current team (replaces entire team).

        This should only be called when confirming a team selection.
        """
        # Clear existing
        self.execute_update("DELETE FROM current_team")

        # Insert new team
        query = """
            INSERT INTO current_team
            (player_id, position, purchase_price, selling_price,
             is_captain, is_vice_captain, multiplier)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params_list = [
            (
                player.get('player_id', player.get('id')),
                player['position'],
                player['purchase_price'],
                player['selling_price'],
                player.get('is_captain', False),
                player.get('is_vice_captain', False),
                player.get('multiplier', 1)
            )
            for player in team_data
        ]
        return self.execute_many(query, params_list)

    def get_draft_team(self, gameweek: int) -> List[Dict[str, Any]]:
        """
        Get draft team for a specific gameweek.

        Returns empty list if no draft exists for that gameweek.
        """
        query = """
            SELECT
                dt.id,
                dt.player_id,
                dt.position,
                dt.purchase_price,
                dt.selling_price,
                dt.is_captain,
                dt.is_vice_captain,
                dt.multiplier,
                dt.for_gameweek,
                p.web_name,
                p.element_type,
                p.team_id,
                p.now_cost,
                p.form,
                p.points_per_game,
                p.status
            FROM draft_team dt
            JOIN players p ON dt.player_id = p.id
            WHERE dt.for_gameweek = ?
            ORDER BY dt.position
        """
        return self.execute_query(query, (gameweek,))

    def create_draft_from_current(self, gameweek: int) -> int:
        """
        Create a draft team for gameweek by copying current team.

        Clears any existing draft for this gameweek first.
        """
        # Clear existing draft for this gameweek
        self.execute_update("DELETE FROM draft_team WHERE for_gameweek = ?", (gameweek,))

        # Copy current_team to draft_team
        query = """
            INSERT INTO draft_team
            (player_id, position, purchase_price, selling_price,
             is_captain, is_vice_captain, multiplier, for_gameweek)
            SELECT
                player_id, position, purchase_price, selling_price,
                is_captain, is_vice_captain, multiplier, ?
            FROM current_team
        """
        return self.execute_update(query, (gameweek,))

    def set_draft_team(self, gameweek: int, team_data: List[Dict[str, Any]]) -> int:
        """
        Set the draft team for a gameweek (replaces existing draft).
        """
        # Clear existing draft
        self.execute_update("DELETE FROM draft_team WHERE for_gameweek = ?", (gameweek,))

        # Insert new draft
        query = """
            INSERT INTO draft_team
            (player_id, position, purchase_price, selling_price,
             is_captain, is_vice_captain, multiplier, for_gameweek)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params_list = [
            (
                player.get('player_id', player.get('id')),
                player['position'],
                player['purchase_price'],
                player['selling_price'],
                player.get('is_captain', False),
                player.get('is_vice_captain', False),
                player.get('multiplier', 1),
                gameweek
            )
            for player in team_data
        ]
        return self.execute_many(query, params_list)

    def confirm_draft_to_current(self, gameweek: int) -> int:
        """
        Confirm draft team as the new current team.

        Copies draft_team to current_team and archives old current_team to my_team history.
        """
        # First, archive current team to my_team history
        # (We'll do this when implementing full workflow)

        # Clear current_team
        self.execute_update("DELETE FROM current_team")

        # Copy draft to current
        query = """
            INSERT INTO current_team
            (player_id, position, purchase_price, selling_price,
             is_captain, is_vice_captain, multiplier)
            SELECT
                player_id, position, purchase_price, selling_price,
                is_captain, is_vice_captain, multiplier
            FROM draft_team
            WHERE for_gameweek = ?
        """
        return self.execute_update(query, (gameweek,))

    def get_draft_transfers(self, gameweek: int) -> List[Dict[str, Any]]:
        """Get proposed transfers for a gameweek draft."""
        query = """
            SELECT
                dt.id,
                dt.for_gameweek,
                dt.player_out_id,
                dt.player_in_id,
                dt.transfer_cost,
                dt.is_free_transfer,
                dt.reasoning,
                dt.expected_gain,
                p_out.web_name as player_out_name,
                p_in.web_name as player_in_name
            FROM draft_transfers dt
            JOIN players p_out ON dt.player_out_id = p_out.id
            JOIN players p_in ON dt.player_in_id = p_in.id
            WHERE dt.for_gameweek = ?
            ORDER BY dt.created_at
        """
        return self.execute_query(query, (gameweek,))

    def add_draft_transfer(
        self,
        gameweek: int,
        player_out_id: int,
        player_in_id: int,
        transfer_cost: int = 0,
        is_free_transfer: bool = True,
        reasoning: str = "",
        expected_gain: Optional[float] = None
    ) -> int:
        """Add a proposed transfer to the draft."""
        query = """
            INSERT INTO draft_transfers
            (for_gameweek, player_out_id, player_in_id, transfer_cost,
             is_free_transfer, reasoning, expected_gain)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        return self.execute_update(
            query,
            (gameweek, player_out_id, player_in_id, transfer_cost,
             is_free_transfer, reasoning, expected_gain)
        )

    def clear_draft_transfers(self, gameweek: int) -> int:
        """Clear all draft transfers for a gameweek."""
        return self.execute_update(
            "DELETE FROM draft_transfers WHERE for_gameweek = ?",
            (gameweek,)
        )

    # ========================================================================
    # DECISIONS & LEARNING
    # ========================================================================

    def log_decision(
        self,
        gameweek: int,
        decision_type: str,
        decision_data: Dict[str, Any],
        reasoning: str,
        expected_value: Optional[float] = None,
        agent_source: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> int:
        """Log a decision for learning purposes."""
        query = """
            INSERT INTO decisions
            (gameweek, decision_type, decision_data, reasoning,
             expected_value, agent_source, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            gameweek, decision_type, json.dumps(decision_data), reasoning,
            expected_value, agent_source, confidence
        )
        return self.execute_update(query, params)

    def log_transfer(
        self,
        gameweek: int,
        player_out_id: int,
        player_in_id: int,
        transfer_cost: int = 0,
        is_free_transfer: bool = True,
        reasoning: str = "",
        expected_gain: Optional[float] = None
    ) -> int:
        """Log a transfer."""
        query = """
            INSERT INTO transfers
            (gameweek, player_out_id, player_in_id, transfer_cost,
             is_free_transfer, reasoning, expected_gain)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            gameweek, player_out_id, player_in_id, transfer_cost,
            is_free_transfer, reasoning, expected_gain
        )
        return self.execute_update(query, params)

    def save_player_prediction(
        self,
        player_id: int,
        gameweek: int,
        predicted_points: float,
        predicted_minutes: Optional[int] = None,
        confidence: Optional[float] = None,
        model_version: Optional[str] = None
    ) -> int:
        """Save a player point prediction."""
        query = """
            INSERT INTO player_predictions
            (player_id, gameweek, predicted_points, predicted_minutes,
             prediction_confidence, model_version)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, gameweek) DO UPDATE SET
                predicted_points = excluded.predicted_points,
                predicted_minutes = excluded.predicted_minutes,
                prediction_confidence = excluded.prediction_confidence,
                model_version = excluded.model_version
        """
        params = (
            player_id, gameweek, predicted_points, predicted_minutes,
            confidence, model_version
        )
        return self.execute_update(query, params)

    def get_prediction_accuracy(self, gameweek: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get prediction accuracy statistics."""
        query = """
            SELECT
                COUNT(*) as total_predictions,
                AVG(ABS(prediction_error)) as mean_absolute_error,
                AVG(prediction_error * prediction_error) as mean_squared_error
            FROM player_predictions
            WHERE actual_points IS NOT NULL
        """
        params = ()

        if gameweek:
            query += " AND gameweek = ?"
            params = (gameweek,)

        return self.execute_query(query, params)

    # ========================================================================
    # FIXTURES & GAMEWEEKS
    # ========================================================================

    def upsert_fixture(self, fixture_data: Dict[str, Any]) -> int:
        """Insert or update fixture data."""
        query = """
            INSERT INTO fixtures
            (id, code, event, team_h, team_a, team_h_difficulty, team_a_difficulty,
             kickoff_time, started, finished)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                started = excluded.started,
                finished = excluded.finished,
                team_h_score = excluded.team_h_score,
                team_a_score = excluded.team_a_score
        """
        params = (
            fixture_data['id'], fixture_data.get('code'), fixture_data.get('event'),
            fixture_data.get('team_h'), fixture_data.get('team_a'),
            fixture_data.get('team_h_difficulty'), fixture_data.get('team_a_difficulty'),
            fixture_data.get('kickoff_time'), fixture_data.get('started', False),
            fixture_data.get('finished', False)
        )
        return self.execute_update(query, params)

    def upsert_gameweek(self, gameweek_data: Dict[str, Any]) -> int:
        """Insert or update gameweek data."""
        query = """
            INSERT INTO gameweeks (
                id, name, deadline_time, finished, is_current, is_next,
                chip_plays, most_selected, most_transferred_in,
                most_captained, most_vice_captained
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                deadline_time = excluded.deadline_time,
                finished = excluded.finished,
                is_current = excluded.is_current,
                is_next = excluded.is_next,
                chip_plays = excluded.chip_plays,
                most_selected = excluded.most_selected,
                most_transferred_in = excluded.most_transferred_in,
                most_captained = excluded.most_captained,
                most_vice_captained = excluded.most_vice_captained
        """
        # Convert chip_plays list to JSON string if present
        chip_plays = gameweek_data.get('chip_plays')
        if isinstance(chip_plays, list):
            chip_plays = json.dumps(chip_plays)

        params = (
            gameweek_data['id'],
            gameweek_data.get('name'),
            gameweek_data.get('deadline_time'),
            gameweek_data.get('finished', False),
            gameweek_data.get('is_current', False),
            gameweek_data.get('is_next', False),
            chip_plays,
            gameweek_data.get('most_selected'),
            gameweek_data.get('most_transferred_in'),
            gameweek_data.get('most_captained'),
            gameweek_data.get('most_vice_captained')
        )
        return self.execute_update(query, params)

    def get_upcoming_fixtures(self, team_id: int, num_gameweeks: int = 6) -> List[Dict[str, Any]]:
        """Get upcoming fixtures for a team."""
        query = """
            SELECT f.*,
                   t_opp.name as opponent_name,
                   t_opp.short_name as opponent_short_name,
                   CASE
                       WHEN f.team_h = ? THEN f.team_a_difficulty
                       ELSE f.team_h_difficulty
                   END as difficulty,
                   CASE
                       WHEN f.team_h = ? THEN 'H'
                       ELSE 'A'
                   END as venue
            FROM fixtures f
            LEFT JOIN teams t_opp ON
                (f.team_h = ? AND f.team_a = t_opp.id) OR
                (f.team_a = ? AND f.team_h = t_opp.id)
            WHERE (f.team_h = ? OR f.team_a = ?)
            AND f.finished = FALSE
            ORDER BY f.event ASC
            LIMIT ?
        """
        params = (team_id, team_id, team_id, team_id, team_id, team_id, num_gameweeks)
        return self.execute_query(query, params)

    def get_current_gameweek(self) -> Optional[Dict[str, Any]]:
        """Get the current gameweek."""
        results = self.execute_query(
            "SELECT * FROM gameweeks WHERE is_current = TRUE LIMIT 1"
        )
        return results[0] if results else None
