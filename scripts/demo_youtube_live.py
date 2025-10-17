#!/usr/bin/env python3
"""
Live YouTube Transcript Demo

Demonstrates fetching a real transcript from an FPL YouTube video.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.youtube_monitor import YouTubeMonitor


async def demo():
    """Demo fetching a real FPL video transcript."""

    print("\n" + "=" * 80)
    print("LIVE YOUTUBE TRANSCRIPT DEMO")
    print("=" * 80)

    monitor = YouTubeMonitor()

    # Example FPL video (you can replace with any FPL video)
    # Using a popular FPL channel as example
    print("\nTo demonstrate, we need an FPL YouTube video URL.")
    print("\nRecommended channels:")
    print("  • FPL Harry (@FPLHarry)")
    print("  • Let's Talk FPL (@LetsTalkFPL)")
    print("  • FPL Focal (@FPLFocal)")

    print("\nExample URLs you could try:")
    print("  • Any 'Injury News' video")
    print("  • Gameweek preview videos")
    print("  • Press conference reaction videos")

    print("\n" + "-" * 80)
    video_url = input("Enter YouTube video URL (or press ENTER to skip): ").strip()

    if not video_url:
        print("\nNo URL provided. Demo explanation:")
        print("\nWhen you provide an FPL video URL, the system will:")
        print("  1. Extract the video ID")
        print("  2. Fetch the transcript (if available)")
        print("  3. Search for injury-related keywords")
        print("  4. Extract player names and context")
        print("  5. Classify the intelligence type")
        print("\nExample output:")
        print("  [INJURY] Cole Palmer")
        print("    Context: 'Cole Palmer is out for six weeks with a knee injury...'")
        print("\nThe transcript is NOT stored - it's fetched fresh each time.")
        return

    print(f"\n→ Processing: {video_url}")

    try:
        # Check the video
        intelligence = await monitor.check_video_urls([video_url])

        if intelligence:
            print(f"\n✓ Found {len(intelligence)} intelligence items:\n")
            print("=" * 80)

            for i, item in enumerate(intelligence, 1):
                print(f"\n{i}. [{item['type']}] {item['player_name']}")
                print(f"   Details: {item['details']}")
                print(f"   Reliability: {item['base_reliability']:.0%}")

            print("\n" + "=" * 80)
        else:
            print("\nNo injury/team news detected in this video.")
            print("Either:")
            print("  • Video has no transcript available")
            print("  • Transcript doesn't contain injury keywords")
            print("  • No player names detected in injury context")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nCommon issues:")
        print("  • Video has no captions/subtitles")
        print("  • Video ID couldn't be extracted from URL")
        print("  • Network/API error")

    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(demo())
