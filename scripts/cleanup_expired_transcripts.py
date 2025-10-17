#!/usr/bin/env python3
"""
Cleanup Expired Transcripts

Removes expired transcripts from cache (7-day TTL).
Should be run daily via cron.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database


def cleanup():
    """Remove expired transcripts from cache."""

    db = Database()

    print("\n" + "=" * 80)
    print("YOUTUBE TRANSCRIPT CACHE CLEANUP")
    print("=" * 80)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check what will be deleted
    expired = db.execute_query("""
        SELECT COUNT(*) as count, SUM(word_count) as words
        FROM youtube_transcripts
        WHERE expires_at < CURRENT_TIMESTAMP
    """)

    if expired and expired[0]['count'] > 0:
        print(f"\nFound {expired[0]['count']} expired transcripts")
        print(f"Total words to clean: {expired[0]['words']:,}")

        # Delete expired transcripts
        deleted = db.execute_update("""
            DELETE FROM youtube_transcripts
            WHERE expires_at < CURRENT_TIMESTAMP
        """)

        print(f"✓ Deleted {deleted} expired transcripts")

        # Also cleanup orphaned intelligence (optional)
        orphaned = db.execute_update("""
            DELETE FROM youtube_intelligence
            WHERE video_id NOT IN (SELECT video_id FROM youtube_transcripts)
        """)

        if orphaned > 0:
            print(f"✓ Cleaned up {orphaned} orphaned intelligence items")

    else:
        print("\n✓ No expired transcripts to clean")

    # Show remaining cache
    remaining = db.execute_query("""
        SELECT
            COUNT(*) as count,
            SUM(word_count) as words,
            MIN(expires_at) as oldest_expiry
        FROM youtube_transcripts
        WHERE expires_at > CURRENT_TIMESTAMP
    """)

    if remaining:
        r = remaining[0]
        print(f"\nRemaining in cache:")
        print(f"  Valid transcripts: {r['count']}")
        print(f"  Total words: {r['words']:,}" if r['words'] else "  Total words: 0")
        print(f"  Oldest expires: {r['oldest_expiry']}")

    print("\n" + "=" * 80)
    print("CLEANUP COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    cleanup()
