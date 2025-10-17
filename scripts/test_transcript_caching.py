#!/usr/bin/env python3
"""
Test YouTube Transcript Caching

Verifies that caching works correctly with cache hits/misses.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.youtube_monitor import YouTubeMonitor
from data.database import Database


async def test_caching():
    """Test transcript caching functionality."""

    print("\n" + "=" * 80)
    print("YOUTUBE TRANSCRIPT CACHING TEST")
    print("=" * 80)

    db = Database()
    monitor = YouTubeMonitor(database=db)

    print("\nThis test demonstrates:")
    print("  1. First fetch: Downloads transcript, caches for 7 days")
    print("  2. Second fetch: Uses cache (instant)")
    print("  3. Intelligence extraction and storage")

    print("\n" + "-" * 80)
    print("STEP 1: Check initial cache state")
    print("-" * 80)

    count = db.execute_query("SELECT COUNT(*) as count FROM youtube_transcripts")[0]['count']
    print(f"Cached transcripts: {count}")

    print("\n" + "-" * 80)
    print("STEP 2: Test with a video URL")
    print("-" * 80)

    print("\nEnter an FPL YouTube video URL to test caching:")
    print("(or press ENTER to use a demo explanation)")

    video_url = input("\nYouTube URL: ").strip()

    if not video_url:
        print("\n📚 Demo Explanation:")
        print("""
When you provide a URL, the system will:

1. FIRST FETCH (Cache Miss):
   ├─> Extract video ID from URL
   ├─> Check database cache → NOT FOUND
   ├─> Fetch transcript from YouTube (~5-10 seconds)
   ├─> Store in database with 7-day TTL
   ├─> Extract intelligence (player injuries, etc.)
   ├─> Store intelligence in database
   └─> Return intelligence

2. SECOND FETCH (Cache Hit):
   ├─> Extract video ID from URL
   ├─> Check database cache → FOUND ✓
   ├─> Return cached transcript (< 1 second)
   ├─> Check if intelligence already extracted
   └─> Skip if already processed

3. Team Analysis:
   ├─> Transcripts stored as plaintext in database
   ├─> View with: venv/bin/python scripts/view_transcripts.py
   ├─> Export with SQL queries
   └─> Intelligence linked to FPL player IDs
        """)
        return

    print(f"\n→ Testing with: {video_url}")

    # First fetch
    print("\n" + "-" * 80)
    print("FIRST FETCH (should download and cache)")
    print("-" * 80)

    start = datetime.now()
    intel1 = await monitor.check_video_urls([video_url])
    duration1 = (datetime.now() - start).total_seconds()

    print(f"\n✓ Completed in {duration1:.2f} seconds")
    print(f"  Intelligence items found: {len(intel1)}")

    if intel1:
        print("\n  Sample intelligence:")
        for item in intel1[:3]:
            print(f"    • [{item['type']}] {item['player_name']}")

    # Check cache
    video_id = monitor._extract_video_id(video_url)
    cached = db.execute_query("""
        SELECT word_count, expires_at, intelligence_extracted
        FROM youtube_transcripts
        WHERE video_id = ?
    """, (video_id,))

    if cached:
        c = cached[0]
        print(f"\n  ✓ Cached transcript:")
        print(f"    Words: {c['word_count']:,}")
        print(f"    Expires: {c['expires_at']}")
        print(f"    Intelligence extracted: {'Yes' if c['intelligence_extracted'] else 'No'}")

    # Second fetch
    print("\n" + "-" * 80)
    print("SECOND FETCH (should use cache)")
    print("-" * 80)

    start = datetime.now()
    intel2 = await monitor.check_video_urls([video_url])
    duration2 = (datetime.now() - start).total_seconds()

    print(f"\n✓ Completed in {duration2:.2f} seconds")
    print(f"  Intelligence items found: {len(intel2)}")

    # Compare
    print("\n" + "-" * 80)
    print("COMPARISON")
    print("-" * 80)

    print(f"\nFirst fetch:  {duration1:.2f}s (download + cache)")
    print(f"Second fetch: {duration2:.2f}s (cache hit)")

    if duration2 < duration1 * 0.3:  # Should be much faster
        print(f"\n✓ CACHING WORKS! {duration2/duration1*100:.0f}% of original time")
    else:
        print(f"\n⚠️  Cache may not be working correctly")

    # Show database state
    print("\n" + "-" * 80)
    print("DATABASE STATE")
    print("-" * 80)

    total_transcripts = db.execute_query("SELECT COUNT(*) as c FROM youtube_transcripts")[0]['c']
    total_intelligence = db.execute_query("SELECT COUNT(*) as c FROM youtube_intelligence")[0]['c']

    print(f"\nCached transcripts: {total_transcripts}")
    print(f"Extracted intelligence: {total_intelligence}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

    print("""
To view cached transcripts:
  venv/bin/python scripts/view_transcripts.py

To cleanup expired cache:
  venv/bin/python scripts/cleanup_expired_transcripts.py

To check cache stats:
  venv/bin/python -c "
  from data.database import Database
  db = Database()
  stats = db.execute_query('SELECT COUNT(*) as count, SUM(word_count) as words FROM youtube_transcripts')
  print(f'Cached: {stats[0][\"count\"]} transcripts, {stats[0][\"words\"]:,} words')
  "
    """)


if __name__ == '__main__':
    try:
        asyncio.run(test_caching())
    except KeyboardInterrupt:
        print("\n\nTest cancelled.")
        sys.exit(0)
