#!/usr/bin/env python3
"""
Gather News Intelligence for GW Decision Making

Pulls news from multiple sources, processes with Claude Haiku,
and stores actionable intelligence in database.

Sources:
- PremierLeague.com news
- YouTube FPL creator shorts
- RSS feeds (already integrated)

This gives Ron "football common sense" to complement ML predictions.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor
from intelligence.premierleague_scraper import fetch_premierleague_news
from intelligence.youtube_monitor import YouTubeMonitor
from data.database import Database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# FPL YouTube creator shorts to monitor (updated frequently)
FPL_YOUTUBE_CHANNELS = {
    'FPL Harry': {
        'recent_videos': [
            # Add recent video URLs here manually or from database
            # Example: 'https://www.youtube.com/watch?v=VIDEO_ID'
        ]
    },
    'Let\'s Talk FPL': {
        'recent_videos': []
    }
}


async def main():
    """Main news gathering workflow."""
    print("\n" + "=" * 80)
    print("NEWS INTELLIGENCE GATHERING")
    print("=" * 80)
    print()

    db = Database()
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        print("   Set ANTHROPIC_API_KEY environment variable")
        return 1

    all_intelligence = []

    # ========================================================================
    # 1. Fetch PremierLeague.com News
    # ========================================================================
    print("📰 Fetching PremierLeague.com news...")
    try:
        pl_articles = await fetch_premierleague_news(max_age_hours=24, max_articles=10)
        print(f"   Found {len(pl_articles)} articles")

        for article in pl_articles:
            if article['content']:
                print(f"   Processing: {article['title']}")

                intelligence = processor.process_news_article(
                    title=article['title'],
                    content=article['content'],
                    source='PremierLeague.com',
                    url=article['url']
                )

                if intelligence['players']:
                    all_intelligence.append(intelligence)
                    print(f"      ✓ Extracted intel on {len(intelligence['players'])} players")

    except Exception as e:
        logger.error(f"Error fetching PremierLeague.com news: {e}")
        print(f"   ⚠️  Error: {e}")

    # ========================================================================
    # 2. Fetch YouTube FPL Creator Videos
    # ========================================================================
    print("\n🎥 Fetching YouTube FPL creator content...")
    try:
        youtube_monitor = YouTubeMonitor(database=db)

        # Get recent videos from database (if configured)
        videos = db.execute_query("""
            SELECT yv.video_id, yv.title, yc.channel_name,
                   'https://www.youtube.com/watch?v=' || yv.video_id as url
            FROM youtube_videos yv
            JOIN youtube_channels yc ON yv.channel_id = yc.channel_id
            WHERE yv.published_at > datetime('now', '-24 hours')
            ORDER BY yv.published_at DESC
            LIMIT 10
        """)

        if videos:
            print(f"   Found {len(videos)} recent videos in database")

            for video in videos:
                # Get transcript from database
                transcript_rows = db.execute_query("""
                    SELECT text FROM youtube_transcripts
                    WHERE video_id = ?
                    ORDER BY start_time
                """, (video['video_id'],))

                if transcript_rows:
                    transcript = ' '.join([row['text'] for row in transcript_rows])
                    print(f"   Processing: {video['title']}")

                    intelligence = processor.process_youtube_transcript(
                        video_title=video['title'],
                        transcript=transcript,
                        creator=video['channel_name'],
                        video_url=video['url']
                    )

                    if intelligence['players']:
                        all_intelligence.append(intelligence)
                        print(f"      ✓ Extracted intel on {len(intelligence['players'])} players")
                    if intelligence.get('recommendations', {}).get('captain_picks'):
                        print(f"      ✓ Captain picks: {', '.join(intelligence['recommendations']['captain_picks'])}")

        else:
            print("   ℹ️  No recent videos in database")
            print("   Run scripts/test_youtube_transcripts.py to fetch videos")

    except Exception as e:
        logger.error(f"Error processing YouTube videos: {e}")
        print(f"   ⚠️  Error: {e}")

    # ========================================================================
    # 3. Aggregate Intelligence
    # ========================================================================
    print("\n" + "=" * 80)
    print("INTELLIGENCE AGGREGATION")
    print("=" * 80)
    print()

    if not all_intelligence:
        print("❌ No intelligence extracted from sources")
        print("   This could mean:")
        print("   1. No recent news articles found")
        print("   2. Articles didn't mention FPL-relevant players")
        print("   3. API processing failed")
        return 1

    aggregated = processor.aggregate_intelligence(all_intelligence)

    print(f"📊 Aggregated intelligence on {len(aggregated)} players:\n")

    # Display by category
    injured = {k: v for k, v in aggregated.items() if v['status'] == 'INJURED'}
    doubts = {k: v for k, v in aggregated.items() if v['status'] == 'DOUBT'}
    positives = {k: v for k, v in aggregated.items() if v['sentiment'] == 'POSITIVE'}

    if injured:
        print("🚑 INJURED:")
        for player, intel in injured.items():
            print(f"   {player}: {intel['details'][0]} (confidence: {intel['confidence']:.0%})")

    if doubts:
        print("\n⚠️  DOUBTS:")
        for player, intel in doubts.items():
            print(f"   {player}: {intel['details'][0]} (confidence: {intel['confidence']:.0%})")

    if positives:
        print("\n✅ POSITIVE MENTIONS:")
        for player, intel in list(positives.items())[:10]:  # Top 10
            print(f"   {player}: {intel['details'][0]}")

    # ========================================================================
    # 4. Store in Database
    # ========================================================================
    print("\n" + "=" * 80)
    print("STORING INTELLIGENCE")
    print("=" * 80)

    # Store aggregated intelligence for use in team selection
    for player_name, intel in aggregated.items():
        try:
            # Try to match player name to player_id (fuzzy matching)
            player_rows = db.execute_query("""
                SELECT id FROM players
                WHERE LOWER(web_name) LIKE LOWER(?)
                   OR LOWER(second_name) LIKE LOWER(?)
                LIMIT 1
            """, (f"%{player_name}%", f"%{player_name}%"))

            player_id = player_rows[0]['id'] if player_rows else None

            # Store in decisions table as intelligence
            db.execute_update("""
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                None,  # No specific gameweek yet
                'news_intelligence',
                f"Player: {player_name}, Status: {intel['status']}, Sentiment: {intel['sentiment']}",
                f"Confidence: {intel['confidence']:.0%}, Sources: {', '.join(intel['sources'])}, Details: {'; '.join(intel['details'])}",
                'news_processor'
            ))

        except Exception as e:
            logger.error(f"Error storing intelligence for {player_name}: {e}")

    print(f"✓ Stored intelligence on {len(aggregated)} players")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Sources processed: {len(all_intelligence)}")
    print(f"Players with intelligence: {len(aggregated)}")
    print(f"Injured players: {len(injured)}")
    print(f"Doubt players: {len(doubts)}")
    print(f"Positive mentions: {len(positives)}")
    print()

    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
