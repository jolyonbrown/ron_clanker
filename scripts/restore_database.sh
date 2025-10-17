#!/bin/bash
#
# Ron Clanker Database Restore Script
#
# Restores database from backup with safety checks.
#

set -e

PROJECT_DIR="/home/jolyon/ron_clanker"
DB_FILE="$PROJECT_DIR/data/ron_clanker.db"
BACKUP_DIR="$PROJECT_DIR/data/backups"

# Check if backup file specified
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/ron_clanker_*.db 2>/dev/null || echo "  No backups found"
    echo ""
    echo "Quick restore from latest:"
    echo "  $0 latest"
    exit 1
fi

# Handle 'latest' shortcut
if [ "$1" = "latest" ]; then
    BACKUP_FILE="$BACKUP_DIR/latest.db"
else
    BACKUP_FILE="$1"
fi

# Check backup exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup not found: $BACKUP_FILE"
    exit 1
fi

echo "⚠️  WARNING: This will replace the current database!"
echo "Current database: $DB_FILE"
echo "Restore from: $BACKUP_FILE"
echo ""

# Safety check - create pre-restore backup
SAFETY_BACKUP="$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).db"
if [ -f "$DB_FILE" ]; then
    echo "📦 Creating safety backup: $SAFETY_BACKUP"
    cp "$DB_FILE" "$SAFETY_BACKUP"
fi

read -p "Continue with restore? (yes/no): " -r
if [ "$REPLY" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo "🔄 Restoring database..."

# Restore
cp "$BACKUP_FILE" "$DB_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Database restored successfully!"
    echo ""
    echo "📊 Restored Database Status:"
    sqlite3 "$DB_FILE" << 'SQL'
.mode column
SELECT 'Players' as table_name, COUNT(*) as count FROM players
UNION ALL
SELECT 'Decisions', COUNT(*) FROM decisions
UNION ALL
SELECT 'Gameweeks', COUNT(*) FROM gameweeks;
SQL
else
    echo "❌ Restore failed!"
    if [ -f "$SAFETY_BACKUP" ]; then
        echo "Restoring from safety backup..."
        cp "$SAFETY_BACKUP" "$DB_FILE"
    fi
    exit 1
fi
