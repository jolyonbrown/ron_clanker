#!/usr/bin/env python3
"""
Database Maintenance

Optimizes database, cleans up old data, and runs VACUUM.
Runs daily to keep database performant.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.db_maintenance')


def main():
    """Run database maintenance tasks."""

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("DATABASE MAINTENANCE")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    db = Database()

    # Check database size before
    print("\n" + "-" * 80)
    print("DATABASE SIZE")
    print("-" * 80)

    db_path = project_root / "data" / "fpl_data.db"
    if db_path.exists():
        size_before = db_path.stat().st_size / (1024 ** 2)
        print(f"Size before: {size_before:.2f} MB")
    else:
        print("⚠️  Database file not found at expected location")
        size_before = 0

    # Clean up old intelligence cache (older than 30 days)
    print("\n" + "-" * 80)
    print("CLEANING OLD INTELLIGENCE")
    print("-" * 80)

    try:
        deleted = db.execute_update("""
            DELETE FROM intelligence_cache
            WHERE timestamp < datetime('now', '-30 days')
        """)

        if deleted > 0:
            print(f"✓ Deleted {deleted} old intelligence items")
        else:
            print("✓ No old intelligence to clean")

    except Exception as e:
        logger.warning(f"DBMaintenance: Could not clean intelligence: {e}")
        print(f"⚠️  Intelligence cleanup skipped: {e}")

    # Clean up expired YouTube transcripts
    print("\n" + "-" * 80)
    print("CLEANING EXPIRED TRANSCRIPTS")
    print("-" * 80)

    try:
        deleted = db.execute_update("""
            DELETE FROM youtube_transcripts
            WHERE expires_at < CURRENT_TIMESTAMP
        """)

        if deleted > 0:
            print(f"✓ Deleted {deleted} expired transcripts")
        else:
            print("✓ No expired transcripts")

    except Exception as e:
        logger.warning(f"DBMaintenance: Could not clean transcripts: {e}")
        print(f"⚠️  Transcript cleanup skipped: {e}")

    # Analyze tables (update statistics for query optimizer)
    print("\n" + "-" * 80)
    print("ANALYZING TABLES")
    print("-" * 80)

    try:
        db.execute_update("ANALYZE")
        print("✓ Table statistics updated")

    except Exception as e:
        logger.warning(f"DBMaintenance: Could not analyze tables: {e}")
        print(f"⚠️  Analyze skipped: {e}")

    # Vacuum database (reclaim space, defragment)
    print("\n" + "-" * 80)
    print("VACUUMING DATABASE")
    print("-" * 80)

    try:
        # Note: VACUUM can't run in a transaction
        db.execute_update("VACUUM")
        print("✓ Database vacuumed")

    except Exception as e:
        logger.warning(f"DBMaintenance: Could not vacuum: {e}")
        print(f"⚠️  Vacuum skipped: {e}")

    # Check database size after
    if db_path.exists():
        size_after = db_path.stat().st_size / (1024 ** 2)
        print(f"Size after: {size_after:.2f} MB")

        if size_before > 0:
            saved = size_before - size_after
            if saved > 0:
                print(f"Space saved: {saved:.2f} MB")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("DATABASE MAINTENANCE COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f} seconds")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nMaintenance cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"DBMaintenance: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
