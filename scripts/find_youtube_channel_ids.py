#!/usr/bin/env python3
"""
Find YouTube Channel IDs for FPL Content Creators

YouTube channel IDs are needed for RSS feed monitoring.
This script helps find them from channel URLs/handles.
"""

import sys
import re


def extract_channel_id_from_url(url):
    """
    Extract channel ID from various YouTube URL formats.

    Formats:
    - youtube.com/channel/CHANNEL_ID
    - youtube.com/@Handle
    - youtube.com/c/CustomName
    """
    # Direct channel ID URL
    match = re.search(r'youtube\.com/channel/([A-Za-z0-9_-]+)', url)
    if match:
        return match.group(1)

    # Handle format
    match = re.search(r'youtube\.com/@([A-Za-z0-9_-]+)', url)
    if match:
        return f"@{match.group(1)}"

    return None


def main():
    """Find channel IDs for FPL creators."""

    print("\n" + "=" * 80)
    print("FIND YOUTUBE CHANNEL IDs FOR FPL CREATORS")
    print("=" * 80)

    print("\nKnown FPL YouTube Channels:")
    print("-" * 80)

    channels = {
        "FPL Harry": {
            "handle": "@FPLHarry",
            "url": "https://www.youtube.com/@FPLHarry",
            "channel_id": "UC1w8Y3hV9VgvlMOjGUpFbag",  # Need to verify
            "notes": "Very popular, excellent injury updates, lots of Shorts"
        },
        "Let's Talk FPL": {
            "handle": "@LetsTalkFPL",
            "url": "https://www.youtube.com/@LetsTalkFPL",
            "channel_id": "UC6D0LPUJ6FP5HUdHROjRLFA",  # Need to verify
            "notes": "Daily videos, team reveals, press conference reactions"
        },
        "FPL Focal": {
            "handle": "@FPLFocal",
            "url": "https://www.youtube.com/@FPLFocal",
            "channel_id": "UC-K6XFYJlIYCVQ4kV36VIdw",  # Need to verify
            "notes": "Gameweek previews, differentials"
        },
        "FPL Mate": {
            "handle": "@FPLMate",
            "url": "https://www.youtube.com/@FPLMate",
            "channel_id": "UCYzIyq9tFLmgBhPHSbVTnLw",  # Need to verify
            "notes": "Statistical analysis, player picks"
        },
        "Andy LTFPL": {
            "handle": "@AndyLTFPL",
            "url": "https://www.youtube.com/@AndyLTFPL",
            "channel_id": "UCqGpT8eTZAYNHxo-sQ3PH3w",  # Need to verify
            "notes": "Budget picks, differentials"
        }
    }

    for name, info in channels.items():
        print(f"\n{name}")
        print(f"  Handle: {info['handle']}")
        print(f"  URL: {info['url']}")
        print(f"  Channel ID: {info['channel_id']}")
        print(f"  Notes: {info['notes']}")

    print("\n" + "=" * 80)
    print("HOW TO VERIFY CHANNEL IDs")
    print("=" * 80)

    print("""
Method 1: RSS Feed Test
  Try: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
  If it loads, the ID is correct!

Method 2: View Page Source
  1. Go to channel page (e.g., youtube.com/@FPLHarry)
  2. View page source (Ctrl+U)
  3. Search for "channelId"
  4. Look for: "channelId":"UCxxxxxxxxxxxxxxxxxx"

Method 3: YouTube Data API (requires API key)
  - Can query by handle/username to get channel ID
  - More reliable but requires setup

For Ron Clanker, we'll use the channel IDs above and verify via RSS.
If RSS feed works, the channel ID is correct!
    """)

    print("=" * 80)
    print("SQL TO ADD CHANNELS")
    print("=" * 80)

    print("\n-- Run this SQL to add FPL channels to database:\n")

    for name, info in channels.items():
        print(f"""INSERT OR REPLACE INTO youtube_channels (channel_id, channel_name, channel_handle, reliability, enabled)
VALUES ('{info['channel_id']}', '{name}', '{info['handle']}', 0.85, 1);""")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
