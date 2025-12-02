#!/usr/bin/env python3
"""Post GW13 announcement to Telegram"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from telegram_bot.notifications import send_team_announcement

announcement = open('data/ron_gw13_announcement.txt').read()

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

if not bot_token or not chat_id:
    print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
    sys.exit(1)

result = send_team_announcement(bot_token, chat_id, 13, announcement)

if result:
    print("✓ Announcement posted to Telegram")
else:
    print("❌ Failed to post to Telegram")
