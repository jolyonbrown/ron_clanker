#!/usr/bin/env python3
"""
Gameweek Utilities

Single source of truth for current gameweek tracking.
All scripts should use these functions instead of making assumptions.
"""

import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger('ron_clanker.gameweek_utils')


def get_current_gameweek(db) -> Optional[int]:
    """
    Get the current gameweek ID from database.

    The database is synced from FPL API via scripts/sync_gameweek_status.py.
    This should be run regularly (hourly) to keep GW status accurate.

    Returns:
        int: Current gameweek ID (e.g., 8)
        None: If no current gameweek found (shouldn't happen in season)

    Example:
        from data.database import Database
        from utils.gameweek import get_current_gameweek

        db = Database()
        current_gw = get_current_gameweek(db)
        print(f"Current GW: {current_gw}")
    """
    try:
        result = db.execute_query("""
            SELECT id FROM gameweeks
            WHERE is_current = 1
            LIMIT 1
        """)

        if result and len(result) > 0:
            gw_id = result[0]['id']
            logger.debug(f"GameweekUtils: Current GW is {gw_id}")
            return gw_id
        else:
            logger.warning("GameweekUtils: No current gameweek found in database!")
            logger.warning("GameweekUtils: Run scripts/sync_gameweek_status.py to sync from FPL API")
            return None

    except Exception as e:
        logger.error(f"GameweekUtils: Error fetching current gameweek: {e}")
        return None


def get_next_gameweek(db) -> Optional[int]:
    """
    Get the next gameweek ID from database.

    Returns:
        int: Next gameweek ID
        None: If no next gameweek found
    """
    try:
        result = db.execute_query("""
            SELECT id FROM gameweeks
            WHERE is_next = 1
            LIMIT 1
        """)

        if result and len(result) > 0:
            return result[0]['id']
        else:
            logger.warning("GameweekUtils: No next gameweek found")
            return None

    except Exception as e:
        logger.error(f"GameweekUtils: Error fetching next gameweek: {e}")
        return None


def get_gameweek_info(db, gameweek_id: int) -> Optional[Dict]:
    """
    Get detailed info about a specific gameweek.

    Args:
        gameweek_id: The gameweek ID

    Returns:
        Dict with keys: id, name, deadline_time, finished, is_current, is_next
        None if gameweek not found
    """
    try:
        result = db.execute_query("""
            SELECT id, name, deadline_time, finished, is_current, is_next
            FROM gameweeks
            WHERE id = ?
        """, (gameweek_id,))

        if result and len(result) > 0:
            return result[0]
        else:
            logger.warning(f"GameweekUtils: Gameweek {gameweek_id} not found")
            return None

    except Exception as e:
        logger.error(f"GameweekUtils: Error fetching gameweek {gameweek_id}: {e}")
        return None


def is_gameweek_finished(db, gameweek_id: int) -> bool:
    """
    Check if a gameweek is finished.

    Args:
        gameweek_id: The gameweek ID

    Returns:
        bool: True if finished, False otherwise
    """
    info = get_gameweek_info(db, gameweek_id)
    if info:
        return bool(info['finished'])
    return False


def is_gameweek_live(db, gameweek_id: int) -> bool:
    """
    Check if a gameweek is currently live.

    Args:
        gameweek_id: The gameweek ID

    Returns:
        bool: True if live (current but not finished), False otherwise
    """
    info = get_gameweek_info(db, gameweek_id)
    if info:
        return bool(info['is_current']) and not bool(info['finished'])
    return False


def get_gameweeks_range(db, start_gw: int, end_gw: int) -> list:
    """
    Get info for a range of gameweeks.

    Args:
        start_gw: Starting gameweek ID (inclusive)
        end_gw: Ending gameweek ID (inclusive)

    Returns:
        List of gameweek dicts
    """
    try:
        result = db.execute_query("""
            SELECT id, name, deadline_time, finished, is_current, is_next
            FROM gameweeks
            WHERE id >= ? AND id <= ?
            ORDER BY id
        """, (start_gw, end_gw))

        return result or []

    except Exception as e:
        logger.error(f"GameweekUtils: Error fetching gameweeks {start_gw}-{end_gw}: {e}")
        return []


def get_upcoming_gameweeks(db, count: int = 5) -> list:
    """
    Get the next N upcoming gameweeks (including current if not finished).

    Args:
        count: Number of gameweeks to return

    Returns:
        List of gameweek dicts
    """
    current_gw = get_current_gameweek(db)
    if not current_gw:
        return []

    try:
        result = db.execute_query("""
            SELECT id, name, deadline_time, finished, is_current, is_next
            FROM gameweeks
            WHERE id >= ?
            ORDER BY id
            LIMIT ?
        """, (current_gw, count))

        return result or []

    except Exception as e:
        logger.error(f"GameweekUtils: Error fetching upcoming gameweeks: {e}")
        return []


def get_gameweek_deadline(db, gameweek_id: int) -> Optional[str]:
    """
    Get the deadline time for a gameweek.

    Args:
        gameweek_id: The gameweek ID

    Returns:
        str: Deadline time in ISO format (e.g., "2025-10-18T10:00:00Z")
        None: If gameweek not found
    """
    info = get_gameweek_info(db, gameweek_id)
    if info:
        return info['deadline_time']
    return None


# Convenience functions for common patterns

def get_current_or_next_gameweek(db) -> Optional[int]:
    """
    Get current gameweek if live, otherwise next gameweek.
    Useful for planning/preview scripts.

    Returns:
        int: Gameweek ID to plan for
        None: If can't determine
    """
    current = get_current_gameweek(db)
    if current:
        # Check if current GW is finished
        if is_gameweek_finished(db, current):
            # Current is finished, return next
            return get_next_gameweek(db)
        else:
            # Current is still live
            return current

    # No current GW, try next
    return get_next_gameweek(db)


def get_latest_finished_gameweek(db) -> Optional[int]:
    """
    Get the most recent finished gameweek.
    Useful for post-gameweek analysis.

    Returns:
        int: Latest finished gameweek ID
        None: If no finished gameweeks (start of season)
    """
    try:
        result = db.execute_query("""
            SELECT id FROM gameweeks
            WHERE finished = 1
            ORDER BY id DESC
            LIMIT 1
        """)

        if result and len(result) > 0:
            return result[0]['id']
        return None

    except Exception as e:
        logger.error(f"GameweekUtils: Error fetching latest finished GW: {e}")
        return None
