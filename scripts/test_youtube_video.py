#!/usr/bin/env python3
"""
Test YouTube Video Transcript Processing

Fetches transcript from a single YouTube video and processes with Claude.
"""

import sys
from pathlib import Path
import re

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from youtube_transcript_api import YouTubeTranscriptApi
from intelligence.news_processor import NewsIntelligenceProcessor
from data.database import Database


def extract_video_id(url):
    """Extract video ID from YouTube URL."""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_youtube_video.py <youtube_url>")
        print("Example: python scripts/test_youtube_video.py https://youtu.be/EJTSdAChwWg")
        return 1

    url = sys.argv[1]

    print("\n" + "=" * 80)
    print("YOUTUBE VIDEO TRANSCRIPT PROCESSING")
    print("=" * 80)
    print()

    # Extract video ID
    video_id = extract_video_id(url)
    if not video_id:
        print(f"❌ Could not extract video ID from: {url}")
        return 1

    print(f"📹 Video ID: {video_id}")
    print(f"🔗 URL: https://www.youtube.com/watch?v={video_id}")
    print()

    # Fetch transcript
    print("📝 Fetching transcript...")
    try:
        api = YouTubeTranscriptApi()
        fetched_transcript = api.fetch(video_id)

        # Combine transcript segments
        full_transcript = ' '.join([snippet.text for snippet in fetched_transcript])

        print(f"✓ Transcript fetched: {len(full_transcript)} characters")
        print()

        # Show preview
        print("TRANSCRIPT PREVIEW (first 500 chars):")
        print("-" * 80)
        print(full_transcript[:500])
        print("-" * 80)
        print()

    except Exception as e:
        print(f"❌ Error fetching transcript: {e}")
        print()
        print("This could mean:")
        print("  - Video doesn't have captions/transcript")
        print("  - Video ID is incorrect")
        print("  - Transcript is disabled")
        return 1

    # Process with Claude
    db = Database()
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        return 1

    print("🤖 Processing with Claude Haiku...")
    print()

    intelligence = processor.process_youtube_transcript(
        video_title=f"YouTube Video {video_id}",
        transcript=full_transcript,
        creator="FPL Creator",
        video_url=url
    )

    # Display results
    print("=" * 80)
    print("EXTRACTED INTELLIGENCE")
    print("=" * 80)
    print()

    if intelligence['players']:
        print(f"📊 Found intelligence on {len(intelligence['players'])} players:\n")

        for player in intelligence['players']:
            status_emoji = {
                'INJURED': '🚑',
                'DOUBT': '⚠️',
                'SUSPENDED': '🟥',
                'AVAILABLE': '✅',
                'NEUTRAL': '⚪'
            }.get(player['status'], '❓')

            sentiment_emoji = {
                'POSITIVE': '👍',
                'NEGATIVE': '👎',
                'NEUTRAL': '➖'
            }.get(player['sentiment'], '❓')

            print(f"{status_emoji} {player['name']}: {player['status']} {sentiment_emoji}")
            print(f"   Confidence: {player['confidence']:.0%}")
            print(f"   Details: {player['details']}")
            print()

    else:
        print("⚠️  No player-specific intelligence extracted")
        print()

    if intelligence.get('recommendations'):
        recs = intelligence['recommendations']

        if recs.get('captain_picks'):
            print("🎯 CAPTAIN RECOMMENDATIONS:")
            for cap in recs['captain_picks']:
                print(f"   • {cap}")
            print()

        if recs.get('transfers_in'):
            print("➡️  TRANSFER IN SUGGESTIONS:")
            for player in recs['transfers_in']:
                print(f"   • {player}")
            print()

        if recs.get('transfers_out'):
            print("⬅️  TRANSFER OUT SUGGESTIONS:")
            for player in recs['transfers_out']:
                print(f"   • {player}")
            print()

    if intelligence.get('general_insights'):
        print("💡 GENERAL INSIGHTS:")
        for insight in intelligence['general_insights']:
            print(f"   • {insight}")
        print()

    # Store in database
    print("-" * 80)
    print("💾 STORING IN DATABASE")
    print()

    stored_count = 0
    if intelligence['players']:
        for player in intelligence['players']:
            try:
                db.execute_update("""
                    INSERT INTO decisions (
                        gameweek, decision_type, decision_data, reasoning,
                        agent_source, created_at
                    ) VALUES (11, 'news_intelligence', ?, ?, 'youtube_processor', CURRENT_TIMESTAMP)
                """, (
                    f"Player: {player['name']}, Status: {player['status']}, Sentiment: {player['sentiment']}",
                    f"Confidence: {int(player['confidence']*100)}%, Sources: YouTube, Details: {player['details']}"
                ))
                stored_count += 1
            except Exception as e:
                print(f"   ⚠️  Error storing {player['name']}: {e}")

        print(f"✓ Stored intelligence on {stored_count} players")
    else:
        print("   No player intelligence to store")

    print()
    print("=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
