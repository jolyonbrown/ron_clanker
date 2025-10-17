#!/usr/bin/env python3
"""
Ron Clanker Database Backup Script

Backs up SQLite database to multiple locations with timestamps.
Run daily via cron: 0 2 * * * /home/jolyon/ron_clanker/venv/bin/python /home/jolyon/ron_clanker/scripts/backup_database.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import shutil
import sqlite3

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import Database

# Configuration
PROJECT_DIR = Path("/home/jolyon/ron_clanker")
DB_FILE = PROJECT_DIR / "data" / "ron_clanker.db"
BACKUP_DIR = PROJECT_DIR / "data" / "backups"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_NAME = f"ron_clanker_{TIMESTAMP}.db"

def main():
    # Create backup directory
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Check if database exists
    if not DB_FILE.exists():
        print(f"❌ Database not found: {DB_FILE}")
        sys.exit(1)

    print("🔄 Starting backup...")
    print(f"Source: {DB_FILE}")
    print(f"Target: {BACKUP_DIR / BACKUP_NAME}")

    try:
        # Use SQLite backup API (safe for in-use databases)
        source_conn = sqlite3.connect(str(DB_FILE))
        backup_conn = sqlite3.connect(str(BACKUP_DIR / BACKUP_NAME))

        with backup_conn:
            source_conn.backup(backup_conn)

        source_conn.close()
        backup_conn.close()

        # Get backup size
        backup_size = (BACKUP_DIR / BACKUP_NAME).stat().st_size
        backup_size_mb = backup_size / (1024 * 1024)

        print(f"✅ Backup created successfully!")
        print(f"   Size: {backup_size_mb:.2f} MB")
        print(f"   Location: {BACKUP_DIR / BACKUP_NAME}")

        # Create latest symlink
        latest_link = BACKUP_DIR / "latest.db"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(BACKUP_NAME)

        # Keep only last 30 backups (about 1 month)
        backups = sorted(BACKUP_DIR.glob("ron_clanker_*.db"), reverse=True)
        for old_backup in backups[30:]:
            old_backup.unlink()
            print(f"   Removed old backup: {old_backup.name}")

        remaining = len(list(BACKUP_DIR.glob("ron_clanker_*.db")))
        print(f"   Retained: {remaining} backups")

        # Also backup to git-tracked location for version control
        git_backup = PROJECT_DIR / "data" / "ron_clanker_latest_backup.db"
        shutil.copy2(BACKUP_DIR / BACKUP_NAME, git_backup)
        print(f"   Git backup: data/ron_clanker_latest_backup.db (for version control)")

    except Exception as e:
        print(f"❌ Backup failed: {e}")
        sys.exit(1)

    # Summary
    print("\n📊 Database Status:")
    db = Database(str(DB_FILE))

    players = db.execute_query("SELECT COUNT(*) as count FROM players")[0]['count']
    decisions = db.execute_query("SELECT COUNT(*) as count FROM decisions")[0]['count']
    gameweeks = db.execute_query("SELECT COUNT(*) as count FROM gameweeks")[0]['count']

    try:
        transfers = db.execute_query("SELECT COUNT(*) as count FROM transfers")[0]['count']
    except:
        transfers = 0

    print(f"   Players: {players}")
    print(f"   Decisions: {decisions}")
    print(f"   Gameweeks: {gameweeks}")
    print(f"   Transfers: {transfers}")

    print("\n✅ Backup complete!")

if __name__ == '__main__':
    main()
