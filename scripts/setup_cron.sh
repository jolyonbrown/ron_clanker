#!/bin/bash
# Setup cron job for Ron Clanker daily monitoring
#
# This script sets up a cron job to run daily monitoring at 3:00 AM
# (after FPL price changes happen at ~1:30 AM UK time)

PROJECT_DIR="/home/jolyon/ron_clanker"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
SCRIPT="$PROJECT_DIR/scripts/daily_monitor.py"
LOG_DIR="$PROJECT_DIR/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

# Cron job entry
CRON_JOB="0 3 * * * cd $PROJECT_DIR && $VENV_PYTHON $SCRIPT >> $LOG_DIR/daily_monitor.log 2>&1"

echo "Setting up cron job for Ron Clanker..."
echo ""
echo "Job will run: Every day at 3:00 AM"
echo "Command: $CRON_JOB"
echo ""

# Check if cron job already exists
crontab -l 2>/dev/null | grep -q "daily_monitor.py"

if [ $? -eq 0 ]; then
    echo "⚠️  Cron job already exists!"
    echo "Current crontab:"
    crontab -l | grep "daily_monitor.py"
    echo ""
    read -p "Do you want to replace it? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi

    # Remove old entry
    crontab -l | grep -v "daily_monitor.py" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✅ Cron job installed!"
echo ""
echo "To verify: crontab -l"
echo "To view logs: tail -f $LOG_DIR/daily_monitor.log"
echo "To run manually: $VENV_PYTHON $SCRIPT"
