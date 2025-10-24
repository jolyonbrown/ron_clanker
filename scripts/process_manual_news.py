#!/usr/bin/env python3
"""
Process Manual News Input

Quick script to process news text you paste/provide.
Stores intelligence in database for immediate use in team selection.

Usage:
    python scripts/process_manual_news.py "Your news text here..."

Or provide a file:
    python scripts/process_manual_news.py --file news.txt
"""

import sys
from pathlib import Path
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor
from data.database import Database


def main():
    parser = argparse.ArgumentParser(description='Process manual news input')
    parser.add_argument('text', nargs='?', help='News text to process')
    parser.add_argument('--file', '-f', help='Read news from file')
    parser.add_argument('--title', '-t', default='Manual News Input', help='Title for the news')
    parser.add_argument('--source', '-s', default='Manual Input', help='Source name')

    args = parser.parse_args()

    # Get text from file or argument
    if args.file:
        with open(args.file, 'r') as f:
            text = f.read()
        print(f"📄 Reading from file: {args.file}\n")
    elif args.text:
        text = args.text
    else:
        print("📝 Paste your news text (end with Ctrl+D on Unix or Ctrl+Z on Windows):")
        text = sys.stdin.read()

    if not text.strip():
        print("❌ No text provided")
        return 1

    print("=" * 80)
    print("PROCESSING MANUAL NEWS INPUT")
    print("=" * 80)
    print()

    # Initialize
    db = Database()
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        return 1

    # Process
    print(f"🤖 Processing with Claude Haiku...")
    print(f"   Text length: {len(text)} characters")
    print()

    intelligence = processor.process_news_article(
        title=args.title,
        content=text,
        source=args.source
    )

    # Display results
    print("=" * 80)
    print("EXTRACTED INTELLIGENCE")
    print("=" * 80)
    print()

    if intelligence['players']:
        print(f"📊 Found intelligence on {len(intelligence['players'])} players:\n")

        for player in intelligence['players']:
            print(f"   {player['name']}")
            print(f"      Status: {player['status']}, Sentiment: {player['sentiment']}")
            print(f"      Confidence: {player['confidence']:.0%}")
            print(f"      Details: {player['details']}")
            print()

        # Store in database
        print("💾 Storing in database...")
        for player in intelligence['players']:
            db.execute_update("""
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (9, 'news_intelligence', ?, ?, 'news_processor', CURRENT_TIMESTAMP)
            """, (
                f"Player: {player['name']}, Status: {player['status']}, Sentiment: {player['sentiment']}",
                f"Confidence: {int(player['confidence']*100)}%, Sources: {args.source}, Details: {player['details']}"
            ))

        print(f"✓ Stored intelligence on {len(intelligence['players'])} players")
        print()

    else:
        print("⚠️  No player-specific intelligence found")
        print()

    if intelligence.get('general_insights'):
        print("💡 GENERAL INSIGHTS:")
        for insight in intelligence['general_insights']:
            print(f"   • {insight}")
        print()

    print("=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print()
    print("This intelligence is now stored and will be used in team selection.")
    print("Run your team selection script to see the adjusted predictions.")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
