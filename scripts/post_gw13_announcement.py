#!/usr/bin/env python3
"""Post GW13 announcement to Slack"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.notifications import NotificationService

announcement = open('data/ron_gw13_announcement.txt').read()

notifier = NotificationService()
result = notifier.send_team_selection(
    gameweek=13,
    announcement=announcement,
    deadline="2025-11-29 13:30 UTC"
)

if result:
    print("✓ Announcement posted to Slack/Discord")
else:
    print("⚠️  Failed to post (check WEBHOOK_URL)")
