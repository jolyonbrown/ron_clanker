#!/bin/bash
#
# Ron Clanker Database Backup Script
#
# Backs up SQLite database to multiple locations with timestamps.
# Run daily via cron: 0 2 * * * /home/jolyon/ron_clanker/scripts/backup_database.sh
#

set -e

# Configuration
PROJECT_DIR="/home/jolyon/ron_clanker"
DB_FILE="$PROJECT_DIR/data/ron_clanker.db"
BACKUP_DIR="$PROJECT_DIR/data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="ron_clanker_${TIMESTAMP}.db"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    echo "❌ Database not found: $DB_FILE"
    exit 1
fi

echo "🔄 Starting backup..."
echo "Source: $DB_FILE"
echo "Target: $BACKUP_DIR/$BACKUP_NAME"

# Create backup with SQLite's .backup command (safe for in-use databases)
sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/$BACKUP_NAME'"

if [ $? -eq 0 ]; then
    # Get backup size
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_NAME" | cut -f1)

    echo "✅ Backup created successfully!"
    echo "   Size: $BACKUP_SIZE"
    echo "   Location: $BACKUP_DIR/$BACKUP_NAME"

    # Create latest symlink
    ln -sf "$BACKUP_NAME" "$BACKUP_DIR/latest.db"

    # Keep only last 30 backups (about 1 month)
    cd "$BACKUP_DIR"
    ls -t ron_clanker_*.db | tail -n +31 | xargs -r rm

    REMAINING=$(ls -1 ron_clanker_*.db | wc -l)
    echo "   Retained: $REMAINING backups"

    # Also backup to git-tracked location for version control
    cp "$BACKUP_DIR/$BACKUP_NAME" "$PROJECT_DIR/data/ron_clanker_latest_backup.db"
    echo "   Git backup: data/ron_clanker_latest_backup.db (for version control)"

else
    echo "❌ Backup failed!"
    exit 1
fi

# Summary
echo ""
echo "📊 Database Status:"
sqlite3 "$DB_FILE" << 'SQL'
.mode column
SELECT 'Players' as table_name, COUNT(*) as count FROM players
UNION ALL
SELECT 'Decisions', COUNT(*) FROM decisions
UNION ALL
SELECT 'Gameweeks', COUNT(*) FROM gameweeks
UNION ALL
SELECT 'Transfers', COUNT(*) FROM transfers;
SQL

echo ""
echo "✅ Backup complete!"
