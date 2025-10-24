#!/usr/bin/env python3
"""
Test Real GW9 News from PremierLeague.com

Fetches actual GW9 matchweek blog and processes with Claude.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.premierleague_scraper import PremierLeagueNewsScraper
from intelligence.news_processor import NewsIntelligenceProcessor


async def main():
    """Fetch and process real GW9 news."""
    print("\n" + "=" * 80)
    print("REAL GW9 NEWS INTELLIGENCE TEST")
    print("=" * 80)
    print()

    # Initialize
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        print("   Set ANTHROPIC_API_KEY environment variable")
        return 1

    # Fetch GW9 blog
    print("📰 Fetching GW9 matchweek blog from PremierLeague.com...")
    print("   URL: https://premierleague.com/en/matchweek/2025_9/blog")
    print()

    async with PremierLeagueNewsScraper() as scraper:
        blog = await scraper.fetch_gameweek_blog(gameweek=9, year=2025)

        if not blog or not blog.get('content'):
            print("❌ Failed to fetch blog content")
            print("   This could mean:")
            print("   1. URL format is incorrect")
            print("   2. Page structure has changed")
            print("   3. Network/timeout issue")
            return 1

        print(f"✓ Fetched blog: {blog['title']}")
        print(f"✓ Content length: {len(blog['content'])} characters")
        print()

        # Show first 500 chars as preview
        print("CONTENT PREVIEW (first 500 chars):")
        print("-" * 80)
        print(blog['content'][:500])
        print("-" * 80)
        print()

        # Process with Claude
        print("🤖 Processing with Claude Haiku...")
        print()

        intelligence = processor.process_news_article(
            title=blog['title'],
            content=blog['content'],
            source=blog['source'],
            url=blog['url']
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
            available = [p for p in intelligence['players'] if p['status'] == 'AVAILABLE' and p['sentiment'] == 'POSITIVE']

            if injured:
                print("🚑 INJURED:")
                for p in injured:
                    print(f"   {p['name']}: {p['details']}")
                    print(f"      Confidence: {p['confidence']:.0%}, Sentiment: {p['sentiment']}")
                print()

            if suspended:
                print("🟥 SUSPENDED:")
                for p in suspended:
                    print(f"   {p['name']}: {p['details']}")
                    print(f"      Confidence: {p['confidence']:.0%}")
                print()

            if doubts:
                print("⚠️  DOUBTS:")
                for p in doubts:
                    print(f"   {p['name']}: {p['details']}")
                    print(f"      Confidence: {p['confidence']:.0%}, Sentiment: {p['sentiment']}")
                print()

            if available:
                print("✅ POSITIVE MENTIONS:")
                for p in available[:10]:  # Top 10
                    print(f"   {p['name']}: {p['details']}")
                print()

        else:
            print("⚠️  No player-specific intelligence extracted")
            print()

        if intelligence.get('general_insights'):
            print("💡 GENERAL INSIGHTS:")
            for insight in intelligence['general_insights']:
                print(f"   • {insight}")
            print()

        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Source: {blog['source']}")
        print(f"URL: {blog['url']}")
        print(f"Players with intelligence: {len(intelligence['players'])}")
        print(f"General insights: {len(intelligence.get('general_insights', []))}")
        print()

        return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
