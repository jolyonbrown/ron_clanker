#!/usr/bin/env python3
"""
Initialize the Ron Clanker database.

Run this script to create the database and tables.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import Database
from config.settings import DATABASE_PATH
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Initialize database."""
    logger.info("Initializing Ron Clanker database...")
    logger.info(f"Database location: {DATABASE_PATH}")

    db = Database(DATABASE_PATH)

    logger.info("Database initialized successfully!")
    logger.info(f"Schema created at {DATABASE_PATH}")

    # Test connection
    try:
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Created {len(tables)} tables: {', '.join(tables)}")
    except Exception as e:
        logger.error(f"Error testing database: {e}")
        return 1

    logger.info("Ron Clanker is ready to manage!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
