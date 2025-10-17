#!/usr/bin/env python3
"""
View Cached YouTube Transcripts

Tool for the team to analyze cached transcripts and extracted intelligence.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database


def main():
    """View cached transcripts and intelligence."""

    db = Database()

    print("\n" + "=" * 80)
    print("CACHED YOUTUBE TRANSCRIPTS")
    print("=" * 80)

    # Get cache statistics
    stats = db.execute_query("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as valid,
            SUM(CASE WHEN intelligence_extracted = 1 THEN 1 ELSE 0 END) as processed,
            SUM(word_count) as total_words
        FROM youtube_transcripts
    """)

    if stats:
        s = stats[0]
        print(f"\nCache Statistics:")
        print(f"  Total transcripts: {s['total'] or 0}")
        print(f"  Valid (not expired): {s['valid'] or 0}")
        print(f"  Processed: {s['processed'] or 0}")
        print(f"  Total words cached: {s['total_words'] or 0:,}")

    # List cached transcripts
    print("\n" + "-" * 80)
    print("CACHED TRANSCRIPTS")
    print("-" * 80)

    transcripts = db.execute_query("""
        SELECT
            video_id,
            word_count,
            fetched_at,
            expires_at,
            intelligence_extracted,
            CASE
                WHEN expires_at > CURRENT_TIMESTAMP THEN 'Valid'
                ELSE 'Expired'
            END as status
        FROM youtube_transcripts
        ORDER BY fetched_at DESC
        LIMIT 20
    """)

    if transcripts:
        for t in transcripts:
            status = "✓" if t['status'] == 'Valid' else "✗"
            processed = "✓" if t['intelligence_extracted'] else "○"
            print(f"\n{status} {t['video_id']}")
            print(f"   Words: {t['word_count']:,}")
            print(f"   Fetched: {t['fetched_at']}")
            print(f"   Expires: {t['expires_at']}")
            print(f"   Processed: {processed}")
    else:
        print("\nNo cached transcripts yet.")
        print("Run: venv/bin/python scripts/test_youtube_transcripts.py")

    # Show intelligence extracted
    print("\n" + "-" * 80)
    print("EXTRACTED INTELLIGENCE")
    print("-" * 80)

    intelligence = db.execute_query("""
        SELECT
            yi.player_name,
            yi.intelligence_type,
            yi.details,
            yi.confidence,
            yi.extracted_at,
            yi.video_id,
            p.web_name as matched_player
        FROM youtube_intelligence yi
        LEFT JOIN players p ON yi.player_id = p.id
        ORDER BY yi.extracted_at DESC
        LIMIT 20
    """)

    if intelligence:
        print(f"\nFound {len(intelligence)} intelligence items:\n")

        for i, item in enumerate(intelligence, 1):
            match_status = "✓" if item['matched_player'] else "?"
            print(f"{i}. [{item['intelligence_type']}] {item['player_name']} {match_status}")
            print(f"   Details: {item['details'][:80]}...")
            print(f"   Confidence: {item['confidence']:.0%}")
            print(f"   Video: {item['video_id']}")
            print(f"   Extracted: {item['extracted_at']}")
            if item['matched_player']:
                print(f"   Matched to: {item['matched_player']}")
            print()
    else:
        print("\nNo intelligence extracted yet.")

    # Option to view full transcript
    print("\n" + "=" * 80)
    print("VIEW FULL TRANSCRIPT")
    print("=" * 80)

    video_id = input("\nEnter video ID to view full transcript (or press ENTER to skip): ").strip()

    if video_id:
        transcript = db.execute_query("""
            SELECT transcript_text, word_count
            FROM youtube_transcripts
            WHERE video_id = ?
        """, (video_id,))

        if transcript:
            text = transcript[0]['transcript_text']
            words = transcript[0]['word_count']

            print(f"\n{'=' * 80}")
            print(f"TRANSCRIPT: {video_id}")
            print(f"Words: {words:,}")
            print(f"{'=' * 80}\n")
            print(text)
            print(f"\n{'=' * 80}")
        else:
            print(f"\n❌ No cached transcript found for {video_id}")

    # Export option
    print("\n" + "=" * 80)
    print("EXPORT OPTIONS")
    print("=" * 80)
    print("""
To export all transcripts:
  venv/bin/python -c "
  from data.database import Database
  db = Database()
  transcripts = db.execute_query('SELECT * FROM youtube_transcripts')
  import json
  with open('transcripts_export.json', 'w') as f:
      json.dump(transcripts, f, indent=2)
  print(f'Exported {len(transcripts)} transcripts')
  "

To export intelligence:
  venv/bin/python -c "
  from data.database import Database
  db = Database()
  intel = db.execute_query('SELECT * FROM youtube_intelligence')
  import json
  with open('intelligence_export.json', 'w') as f:
      json.dump(intel, f, indent=2)
  print(f'Exported {len(intel)} intelligence items')
  "
    """)

    print("=" * 80)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
