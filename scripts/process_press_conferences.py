#!/usr/bin/env python3
"""
Process Press Conference Summary Files

Handles the simplified press conference format (team-by-team injury/availability).
Much more efficient than full article processing.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor
from data.database import Database


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/process_press_conferences.py <press_conf_file.txt> <gameweek>")
        print("Example: python scripts/process_press_conferences.py data/news_input/premier_league_press_conferences_gw10.txt 10")
        return 1

    press_conf_path = Path(sys.argv[1])
    gameweek = int(sys.argv[2])

    if not press_conf_path.exists():
        print(f"❌ File not found: {press_conf_path}")
        return 1

    print("\n" + "=" * 80)
    print("PRESS CONFERENCE PROCESSING")
    print("=" * 80)
    print()
    print(f"📋 File: {press_conf_path.name}")
    print(f"⚽ Gameweek: {gameweek}")
    print()

    # Read content
    print("📝 Reading press conference data...")
    try:
        with open(press_conf_path, 'r') as f:
            content = f.read()

        print(f"✓ Content length: {len(content)} characters")
        print(f"✓ Lines: {len(content.splitlines())}")
        print()

        # Show preview
        print("CONTENT PREVIEW (first 500 chars):")
        print("-" * 80)
        print(content[:500])
        print("-" * 80)
        print()

    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return 1

    # Process with Claude
    db = Database()
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        return 1

    print("🤖 Processing with Claude Haiku (simplified format)...")
    print()

    intelligence = processor.process_simple_press_conferences(
        content=content,
        gameweek=gameweek,
        source="Press Conferences"
    )

    # Display results
    print("=" * 80)
    print("EXTRACTED INTELLIGENCE")
    print("=" * 80)
    print()

    if intelligence['players']:
        print(f"📊 Found intelligence on {len(intelligence['players'])} players:\n")

        # Group by status
        injured = [p for p in intelligence['players'] if p['status'] == 'INJURED']
        doubts = [p for p in intelligence['players'] if p['status'] == 'DOUBT']
        suspended = [p for p in intelligence['players'] if p['status'] == 'SUSPENDED']
        available = [p for p in intelligence['players'] if p['status'] == 'AVAILABLE']

        if injured:
            print(f"🚑 INJURED ({len(injured)}):")
            for p in injured:
                print(f"   {p['name']}")
                print(f"      {p['details']}")
            print()

        if suspended:
            print(f"🟥 SUSPENDED ({len(suspended)}):")
            for p in suspended:
                print(f"   {p['name']}")
                print(f"      {p['details']}")
            print()

        if doubts:
            print(f"⚠️  DOUBTS ({len(doubts)}):")
            for p in doubts:
                print(f"   {p['name']}")
                print(f"      {p['details']}")
            print()

        if available:
            print(f"✅ RETURNING/AVAILABLE ({len(available)}):")
            for p in available[:15]:  # Limit to first 15
                print(f"   {p['name']}: {p['details'][:80]}...")
            if len(available) > 15:
                print(f"   ... and {len(available) - 15} more")
            print()

    else:
        print("⚠️  No player-specific intelligence extracted")
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
                    ) VALUES (?, 'news_intelligence', ?, ?, 'press_conf_processor', CURRENT_TIMESTAMP)
                """, (
                    gameweek,
                    f"Player: {player['name']}, Status: {player['status']}, Sentiment: {player['sentiment']}",
                    f"Confidence: {int(player['confidence']*100)}%, Source: Press Conferences, Details: {player['details']}"
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
