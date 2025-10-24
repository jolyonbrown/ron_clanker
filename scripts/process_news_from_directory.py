#!/usr/bin/env python3
"""
Process News from Directory

Reads all .txt files from a directory and processes them with Claude.
Stores intelligence in database for immediate use in team selection.

Usage:
    python scripts/process_news_from_directory.py [directory_path]

Default directory: data/news_input/

Just drop .txt files with press conference quotes, injury news, etc.
into the directory and run this script.
"""

import sys
from pathlib import Path
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor
from data.database import Database


def main():
    parser = argparse.ArgumentParser(description='Process news from directory')
    parser.add_argument('directory', nargs='?', default='data/news_input',
                       help='Directory containing .txt news files (default: data/news_input)')

    args = parser.parse_args()

    news_dir = Path(args.directory)

    if not news_dir.exists():
        print(f"📁 Creating directory: {news_dir}")
        news_dir.mkdir(parents=True, exist_ok=True)
        print()
        print(f"✓ Directory created!")
        print(f"  Drop .txt files with news into: {news_dir.absolute()}")
        print(f"  Then run this script again.")
        print()
        return 0

    # Find all .txt files
    txt_files = list(news_dir.glob('*.txt'))

    if not txt_files:
        print(f"📁 Looking in: {news_dir.absolute()}")
        print()
        print("❌ No .txt files found in directory")
        print()
        print("Instructions:")
        print(f"  1. Create .txt files in: {news_dir.absolute()}")
        print("  2. Paste press conference quotes, injury news, etc.")
        print("  3. Run this script again")
        print()
        return 1

    print("\n" + "=" * 80)
    print("PROCESSING NEWS FROM DIRECTORY")
    print("=" * 80)
    print()
    print(f"📁 Directory: {news_dir.absolute()}")
    print(f"📄 Found {len(txt_files)} .txt files")
    print()

    # Initialize
    db = Database()
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        print("   Set ANTHROPIC_API_KEY environment variable")
        return 1

    all_intelligence = []

    # Process each file
    for txt_file in txt_files:
        print("-" * 80)
        print(f"📰 Processing: {txt_file.name}")
        print()

        # Read file
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            print("   ⚠️  File is empty, skipping")
            print()
            continue

        print(f"   Text length: {len(content)} characters")

        # Process with Claude
        intelligence = processor.process_news_article(
            title=txt_file.stem.replace('_', ' ').title(),
            content=content,
            source=f'Manual Input: {txt_file.name}'
        )

        if intelligence['players']:
            all_intelligence.append(intelligence)
            print(f"   ✓ Extracted intel on {len(intelligence['players'])} players:")

            for player in intelligence['players']:
                status_emoji = {
                    'INJURED': '🚑',
                    'DOUBT': '⚠️ ',
                    'SUSPENDED': '🟥',
                    'AVAILABLE': '✅',
                    'NEUTRAL': '⚪'
                }.get(player['status'], '❓')

                sentiment_emoji = {
                    'POSITIVE': '👍',
                    'NEGATIVE': '👎',
                    'NEUTRAL': '➖'
                }.get(player['sentiment'], '❓')

                print(f"      {status_emoji} {player['name']}: {player['status']} {sentiment_emoji} ({player['confidence']:.0%})")
                print(f"         \"{player['details']}\"")
            print()
        else:
            print("   ⚠️  No player intelligence extracted")
            print()

        if intelligence.get('general_insights'):
            print(f"   💡 {len(intelligence['general_insights'])} general insights extracted")
            print()

    # Aggregate and store
    print("=" * 80)
    print("AGGREGATING INTELLIGENCE")
    print("=" * 80)
    print()

    if not all_intelligence:
        print("❌ No intelligence extracted from any files")
        return 1

    aggregated = processor.aggregate_intelligence(all_intelligence)

    print(f"📊 Total players with intelligence: {len(aggregated)}")
    print()

    # Display summary
    injured = {k: v for k, v in aggregated.items() if v['status'] == 'INJURED'}
    doubts = {k: v for k, v in aggregated.items() if v['status'] == 'DOUBT'}
    suspended = {k: v for k, v in aggregated.items() if v['status'] == 'SUSPENDED'}
    positive = {k: v for k, v in aggregated.items() if v['sentiment'] == 'POSITIVE'}

    if injured:
        print("🚑 INJURED:")
        for player, intel in injured.items():
            print(f"   {player} (conf: {intel['confidence']:.0%})")
        print()

    if suspended:
        print("🟥 SUSPENDED:")
        for player, intel in suspended.items():
            print(f"   {player} (conf: {intel['confidence']:.0%})")
        print()

    if doubts:
        print("⚠️  DOUBTS:")
        for player, intel in doubts.items():
            print(f"   {player} (conf: {intel['confidence']:.0%})")
        print()

    if positive:
        print("✅ POSITIVE MENTIONS:")
        for player, intel in list(positive.items())[:10]:
            print(f"   {player}")
        print()

    # Store in database
    print("-" * 80)
    print("💾 STORING IN DATABASE")
    print()

    stored_count = 0
    for player_name, intel in aggregated.items():
        try:
            db.execute_update("""
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (9, 'news_intelligence', ?, ?, 'news_processor', CURRENT_TIMESTAMP)
            """, (
                f"Player: {player_name}, Status: {intel['status']}, Sentiment: {intel['sentiment']}",
                f"Confidence: {int(intel['confidence']*100)}%, Sources: {', '.join(intel['sources'])}, Details: {'; '.join(intel['details'])}"
            ))
            stored_count += 1
        except Exception as e:
            print(f"   ⚠️  Error storing {player_name}: {e}")

    print(f"✓ Stored intelligence on {stored_count} players")
    print()

    # Summary
    print("=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print()
    print(f"✓ Processed {len(txt_files)} files")
    print(f"✓ Extracted intelligence on {len(aggregated)} players")
    print(f"✓ Stored in database for GW9 team selection")
    print()
    print("Next steps:")
    print("  - Intelligence is now in database")
    print("  - Run your team selection script to see adjusted predictions")
    print("  - Premium player floor will prevent Haaland-benching disasters")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
