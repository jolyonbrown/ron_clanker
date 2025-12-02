#!/usr/bin/env python3
"""Post GW13 announcement to Slack via webhook"""

import sys
import os
import requests
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / '.env')
except ImportError:
    pass

# Read announcement
announcement_path = project_root / 'data' / 'ron_gw13_announcement.txt'
announcement = announcement_path.read_text()

# Get webhook URL
webhook_url = os.getenv('SLACK_WEBHOOK_URL') or os.getenv('WEBHOOK_URL')

if not webhook_url:
    print("⚠️  No webhook URL configured (set SLACK_WEBHOOK_URL or WEBHOOK_URL)")
    sys.exit(1)

# Slack format (simple text payload)
payload = {
    "text": f"*Ron Clanker - GW13 Team Selection*\n\n{announcement}"
}

try:
    response = requests.post(webhook_url, json=payload, timeout=10)

    if response.status_code == 200:
        print("✓ Announcement posted to Slack")
    else:
        print(f"⚠️  Failed to post: HTTP {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

except Exception as e:
    print(f"⚠️  Error posting to Slack: {e}")
    sys.exit(1)
