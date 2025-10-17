#!/usr/bin/env python3
"""
Migrate YouTube Caching Tables

Adds tables for caching YouTube transcripts and intelligence.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database


def migrate():
    """Run YouTube caching migration."""

    db = Database()

    print("Creating YouTube caching tables...")

    # Table 1: YouTube channels
    db.execute_update("""
        CREATE TABLE IF NOT EXISTS youtube_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE NOT NULL,
            channel_name TEXT NOT NULL,
            channel_handle TEXT,
            reliability REAL DEFAULT 0.85,
            enabled BOOLEAN DEFAULT 1,
            last_checked TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ youtube_channels")

    # Table 2: YouTube videos
    db.execute_update("""
        CREATE TABLE IF NOT EXISTS youtube_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            channel_id TEXT NOT NULL,
            title TEXT NOT NULL,
            published_at TIMESTAMP,
            duration INTEGER,
            has_transcript BOOLEAN DEFAULT 0,
            is_relevant BOOLEAN DEFAULT 0,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ youtube_videos")

    # Table 3: Cached transcripts
    db.execute_update("""
        CREATE TABLE IF NOT EXISTS youtube_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            transcript_text TEXT NOT NULL,
            word_count INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            intelligence_extracted BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ youtube_transcripts")

    # Table 4: Intelligence from transcripts
    db.execute_update("""
        CREATE TABLE IF NOT EXISTS youtube_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            player_id INTEGER,
            player_name TEXT NOT NULL,
            intelligence_type TEXT NOT NULL,
            details TEXT NOT NULL,
            context TEXT,
            confidence REAL DEFAULT 0.85,
            severity TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ youtube_intelligence")

    # Indexes
    print("\nCreating indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_youtube_videos_channel ON youtube_videos(channel_id)",
        "CREATE INDEX IF NOT EXISTS idx_youtube_videos_published ON youtube_videos(published_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_youtube_videos_relevant ON youtube_videos(is_relevant)",
        "CREATE INDEX IF NOT EXISTS idx_youtube_transcripts_video ON youtube_transcripts(video_id)",
        "CREATE INDEX IF NOT EXISTS idx_youtube_transcripts_expires ON youtube_transcripts(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_youtube_intelligence_video ON youtube_intelligence(video_id)",
        "CREATE INDEX IF NOT EXISTS idx_youtube_intelligence_player ON youtube_intelligence(player_id)",
    ]

    for idx_sql in indexes:
        try:
            db.execute_update(idx_sql)
        except Exception as e:
            if 'already exists' not in str(e).lower():
                print(f"Warning: {e}")

    print("✓ Indexes created")

    # Verify
    print("\nVerifying tables...")
    tables = db.execute_query("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name LIKE '%youtube%'
        ORDER BY name
    """)

    for table in tables:
        print(f"  ✓ {table['name']}")

    print(f"\nMigration complete! Created {len(tables)} tables.")
    return True


if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
