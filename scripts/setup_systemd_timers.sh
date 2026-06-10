#!/bin/bash
# Install Ron Clanker systemd user timers
#
# Usage: bash scripts/setup_systemd_timers.sh
#
# This installs user-level systemd timers (no root needed).
# Timers persist across reboots and handle missed runs.

set -e

PROJECT_DIR="/home/jolyon/ron_clanker"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
CONFIG_DIR="$PROJECT_DIR/config/systemd"

echo "============================================"
echo "RON CLANKER - SYSTEMD TIMER INSTALLATION"
echo "============================================"
echo

# Ensure logs directory exists
mkdir -p "$PROJECT_DIR/logs"

# Ensure systemd user dir exists
mkdir -p "$SYSTEMD_USER_DIR"

# Copy service and timer files
echo "Installing service and timer files..."
for file in "$CONFIG_DIR"/*.service "$CONFIG_DIR"/*.timer; do
    if [ -f "$file" ]; then
        cp "$file" "$SYSTEMD_USER_DIR/"
        echo "  Installed: $(basename "$file")"
    fi
done

# Reload systemd user daemon
echo
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

# Enable and start all timers
echo
echo "Enabling timers..."

TIMERS=(
    "ron-deadline-check"
    "ron-data-collection"
    "ron-post-gameweek"
    "ron-daily-scout"
    "ron-db-maintenance"
    "ron-price-snapshot"
    "ron-price-predict"
    "ron-price-train"
)

for timer in "${TIMERS[@]}"; do
    systemctl --user enable "${timer}.timer" 2>/dev/null
    systemctl --user start "${timer}.timer" 2>/dev/null
    echo "  Enabled: ${timer}.timer"
done

# Ron-in-Slack daemon (long-running service, not a timer). Exits
# cleanly if SLACK_BOT_TOKEN/SLACK_APP_TOKEN are unset — safe to enable
# before the Slack app is created.
systemctl --user enable ron-slack-bot.service 2>/dev/null
systemctl --user restart ron-slack-bot.service 2>/dev/null
echo "  Enabled: ron-slack-bot.service"
echo

# Enable lingering so timers run even when not logged in
echo
echo "Enabling lingering (timers run when logged out)..."
loginctl enable-linger "$(whoami)" 2>/dev/null || echo "  Note: loginctl enable-linger may need sudo"

# Show status
echo
echo "============================================"
echo "INSTALLED TIMERS"
echo "============================================"
systemctl --user list-timers --all | grep ron-

echo
echo "============================================"
echo "QUICK REFERENCE"
echo "============================================"
echo "  Check status:  systemctl --user list-timers | grep ron"
echo "  Run manually:  systemctl --user start ron-deadline-check.service"
echo "  View logs:     journalctl --user -u ron-deadline-check -f"
echo "  Disable:       systemctl --user disable ron-deadline-check.timer"
echo "  Uninstall:     bash scripts/uninstall_systemd_timers.sh"
echo
echo "Ron Clanker is now autonomous."
