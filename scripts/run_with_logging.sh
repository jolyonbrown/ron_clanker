#!/bin/bash
# Run any Python script with comprehensive logging
#
# Usage: ./scripts/run_with_logging.sh scripts/test_full_system.py
#
# Logs will be saved to logs/ directory with timestamp

SCRIPT=$1
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SCRIPT_NAME=$(basename "$SCRIPT" .py)
LOGFILE="logs/${SCRIPT_NAME}_${TIMESTAMP}.log"

if [ -z "$SCRIPT" ]; then
    echo "Usage: $0 <python_script>"
    echo "Example: $0 scripts/test_full_system.py"
    exit 1
fi

echo "Running: $SCRIPT"
echo "Logging to: $LOGFILE"
echo ""

# Run script with both console output and file logging
venv/bin/python "$SCRIPT" 2>&1 | tee "$LOGFILE"

echo ""
echo "Log saved to: $LOGFILE"
echo "Size: $(du -h "$LOGFILE" | cut -f1)"
