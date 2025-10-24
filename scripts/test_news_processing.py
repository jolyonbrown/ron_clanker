#!/usr/bin/env python3
"""
Test News Intelligence Processing

Tests the Claude-based news processor with sample articles.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor


# Sample FPL-related news for testing
SAMPLE_ARTICLES = [
    {
        'title': 'Haaland and Palmer lead FPL picks for Gameweek 9',
        'content': '''
        Erling Haaland continues his remarkable form and is the standout captain choice
        for Gameweek 9. The Manchester City striker has scored in his last three games
        and faces Aston Villa at home. With 6 goals in his last 4 matches, Haaland
        is a must-have for any serious FPL manager.

        Cole Palmer is another excellent option. Chelsea's midfielder has been
        exceptional, contributing goals and assists regularly. Chelsea face Sunderland
        at home, which should be a favorable fixture.

        Mohamed Salah is a slight doubt for Liverpool's match against Arsenal after
        picking up a knock in training. Manager Arne Slot said he's "75-80% likely"
        to feature, but there's definitely some rotation risk.

        Budget option Joao Pedro of Chelsea is in great form with 3 goals in his last
        2 games. At £7.5m, he represents excellent value for money.

        Defensive picks: Gabriel of Arsenal continues to be a solid choice, averaging
        11 defensive actions per game plus clean sheet potential. Same with William
        Saliba who has been rock solid.
        ''',
        'source': 'Test Article 1'
    },
    {
        'title': 'Gameweek 9 Injury Update',
        'content': '''
        Injury news ahead of the Gameweek 9 deadline:

        Manchester United's Bruno Fernandes is suspended after picking up his 5th
        yellow card. He will miss the next match.

        Alexander Isak is confirmed OUT for Newcastle with a hamstring injury.
        He's expected to miss 2-3 weeks.

        Kevin De Bruyne returned to training and is expected to start for Man City.
        This is positive news for City's attack.

        Bukayo Saka trained fully and is expected to start for Arsenal despite
        injury concerns earlier in the week.
        ''',
        'source': 'Test Article 2'
    }
]


def main():
    """Test news processing."""
    print("\n" + "=" * 80)
    print("TESTING NEWS INTELLIGENCE PROCESSOR")
    print("=" * 80)
    print()

    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        print("   Set ANTHROPIC_API_KEY environment variable")
        return 1

    all_intelligence = []

    # Process each test article
    for article in SAMPLE_ARTICLES:
        print(f"📰 Processing: {article['title']}")
        print(f"   Source: {article['source']}")

        intelligence = processor.process_news_article(
            title=article['title'],
            content=article['content'],
            source=article['source']
        )

        if intelligence['players']:
            all_intelligence.append(intelligence)
            print(f"   ✓ Extracted intel on {len(intelligence['players'])} players:")

            for player in intelligence['players']:
                print(f"      - {player['name']}: {player['status']} ({player['sentiment']}, conf: {player['confidence']:.0%})")
                print(f"        \"{player['details']}\"")

        if intelligence.get('general_insights'):
            print(f"   ✓ General insights:")
            for insight in intelligence['general_insights']:
                print(f"      - {insight}")

        print()

    # Aggregate intelligence
    print("=" * 80)
    print("AGGREGATED INTELLIGENCE")
    print("=" * 80)
    print()

    aggregated = processor.aggregate_intelligence(all_intelligence)

    print(f"📊 Intelligence on {len(aggregated)} players:\n")

    # Display by category
    injured = {k: v for k, v in aggregated.items() if v['status'] == 'INJURED'}
    suspended = {k: v for k, v in aggregated.items() if v['status'] == 'SUSPENDED'}
    doubts = {k: v for k, v in aggregated.items() if v['status'] == 'DOUBT'}
    positives = {k: v for k, v in aggregated.items() if v['sentiment'] == 'POSITIVE'}

    if injured:
        print("🚑 INJURED:")
        for player, intel in injured.items():
            print(f"   {player}: {intel['details'][0]} (confidence: {intel['confidence']:.0%})")

    if suspended:
        print("\n🟥 SUSPENDED:")
        for player, intel in suspended.items():
            print(f"   {player}: {intel['details'][0]} (confidence: {intel['confidence']:.0%})")

    if doubts:
        print("\n⚠️  DOUBTS:")
        for player, intel in doubts.items():
            print(f"   {player}: {intel['details'][0]} (confidence: {intel['confidence']:.0%})")

    if positives:
        print("\n✅ POSITIVE MENTIONS:")
        for player, intel in positives.items():
            print(f"   {player}: {', '.join(intel['details'])}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
