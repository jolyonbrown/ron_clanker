#!/usr/bin/env python3
"""
Apply Price Tracking Migration

Creates tables for price change prediction system.
Optimized for Raspberry Pi 3.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database


def main():
    """Apply price tracking migration."""

    print("\n" + "=" * 80)
    print("PRICE TRACKING MIGRATION")
    print("=" * 80)

    db = Database()

    migration_file = project_root / "data" / "migrations" / "003_add_price_tracking.sql"

    if not migration_file.exists():
        print(f"\n❌ Migration file not found: {migration_file}")
        return 1

    print(f"\nApplying migration: {migration_file.name}")

    try:
        # Read migration SQL
        with open(migration_file, 'r') as f:
            sql = f.read()

        print(f"Executing migration SQL...")

        # Use executescript for multi-statement execution
        with db.get_connection() as conn:
            conn.executescript(sql)
            conn.commit()

        print("✓ Migration applied successfully")

        # Verify tables created
        print("\n" + "-" * 80)
        print("VERIFYING TABLES")
        print("-" * 80)

        tables_to_check = [
            'price_changes',
            'player_transfer_snapshots',
            'price_predictions',
            'price_model_performance'
        ]

        for table in tables_to_check:
            result = db.execute_query(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if result:
                print(f"✓ {table}")
            else:
                print(f"✗ {table} NOT FOUND")

        print("\n" + "=" * 80)
        print("MIGRATION COMPLETE")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nMigration cancelled.")
        sys.exit(1)
