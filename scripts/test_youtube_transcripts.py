#!/usr/bin/env python3
"""
Test YouTube Transcript Extraction

Demonstrates the YouTube monitor fetching and parsing transcripts
from real FPL YouTube videos to extract injury/team news.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.youtube_monitor import YouTubeMonitor


async def test_transcript_extraction():
    """Test extracting transcripts from FPL YouTube videos."""

    print("\n" + "=" * 80)
    print("YOUTUBE TRANSCRIPT EXTRACTION TEST")
    print("=" * 80)

    print("\nThe YouTube monitor can:")
    print("  • Extract transcripts from any YouTube video (if available)")
    print("  • Search for injury/team news mentions")
    print("  • Extract player names and context")
    print("  • No API key required!")

    print("\n" + "-" * 80)
    print("NOTE: We need actual video URLs to test this feature")
    print("-" * 80)

    monitor = YouTubeMonitor()

    # Example: Test with a specific FPL video
    # You would add real FPL video URLs here
    test_videos = [
        # Example format (not a real video):
        # 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    ]

    print("\nTo test YouTube transcript extraction, you can:")
    print("\n1. Add video URLs to the test_videos list in this script")
    print("2. Or test interactively:")

    print("\n" + "=" * 80)
    print("INTERACTIVE TEST")
    print("=" * 80)

    print("\nEnter a YouTube video URL to extract transcript")
    print("(or press ENTER to skip)")
    print("\nRecommended: FPL Harry, Let's Talk FPL, FPL Focal videos")
    print("Example: https://www.youtube.com/watch?v=VIDEO_ID")

    user_input = input("\nYouTube URL: ").strip()

    if user_input:
        print(f"\n→ Testing with: {user_input}")
        print("→ Fetching transcript...")

        try:
            # Extract video ID
            video_id = monitor._extract_video_id(user_input)
            if not video_id:
                print("❌ Could not extract video ID from URL")
                return

            print(f"✓ Video ID: {video_id}")

            # Fetch transcript
            print("→ Downloading transcript...")
            transcript = await monitor._fetch_transcript(video_id)

            if not transcript:
                print("❌ No transcript available for this video")
                print("   (Video may not have captions/subtitles enabled)")
                return

            print(f"✓ Transcript fetched: {len(transcript)} characters")

            # Show sample
            print("\n" + "-" * 80)
            print("TRANSCRIPT SAMPLE (first 500 characters):")
            print("-" * 80)
            print(transcript[:500])
            if len(transcript) > 500:
                print(f"... ({len(transcript) - 500} more characters)")

            # Extract intelligence
            print("\n" + "-" * 80)
            print("EXTRACTING INTELLIGENCE...")
            print("-" * 80)

            mentions = monitor._extract_intelligence(transcript, "")

            if mentions:
                print(f"✓ Found {len(mentions)} intelligence mentions:\n")

                for i, mention in enumerate(mentions, 1):
                    print(f"{i}. [{mention['type']}] {mention['player_name']}")
                    print(f"   Context: {mention['details'][:100]}...")
                    print()

            else:
                print("No injury/team news mentions detected in transcript")
                print("(Video may not contain FPL-relevant injury information)")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

    else:
        print("\nNo URL provided. Skipping interactive test.")

    print("\n" + "=" * 80)
    print("HOW TO USE IN PRODUCTION")
    print("=" * 80)

    print("""
The Scout can monitor YouTube videos in two ways:

1. MANUAL (Press Conference Days):
   - When injury news breaks, manually add video URLs
   - Scout checks specific videos for injury mentions
   - Example: FPL Harry's "GW8 Injury News" video

2. AUTOMATED (Future):
   - Monitor FPL channel RSS feeds for new videos
   - Automatically check videos with injury-related titles
   - Extract and classify intelligence

Current approach: Manual video URLs (more practical for Phase 2)

To monitor a video, call:
  scout.check_youtube(['https://www.youtube.com/watch?v=VIDEO_ID'])

Or add to MONITORED_VIDEOS in youtube_monitor.py
    """)

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    print("\nYouTube Transcript Extraction Demo")
    print("Note: You'll need a real YouTube video URL to see transcripts\n")

    try:
        asyncio.run(test_transcript_extraction())
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(0)
