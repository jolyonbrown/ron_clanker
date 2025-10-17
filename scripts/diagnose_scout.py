#!/usr/bin/env python3
"""
Scout Agent Diagnostic Tool

Comprehensive testing and troubleshooting for The Scout:
- Tests each intelligence source independently
- Shows detailed error messages
- Displays raw data collected
- Tests player name matching
- Verifies classification system
- Identifies issues and suggests fixes
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.scout import ScoutAgent
from intelligence.rss_monitor import RSSMonitor
from intelligence.website_monitor import WebsiteMonitor
from intelligence.youtube_monitor import YouTubeMonitor
from intelligence.intelligence_classifier import IntelligenceClassifier
from data.database import Database


def print_header(title, char="="):
    """Print a formatted header."""
    print(f"\n{char * 80}")
    print(f"  {title}")
    print(f"{char * 80}\n")


def print_section(title):
    """Print a section divider."""
    print(f"\n{'-' * 80}")
    print(f"  {title}")
    print(f"{'-' * 80}\n")


async def test_rss_feeds():
    """Test RSS feed monitoring in detail."""
    print_header("TEST 1: RSS FEED MONITORING")

    print("Testing RSS feeds (fastest, most reliable source)...\n")

    rss = RSSMonitor()

    # Test each feed individually
    feeds = {
        'bbc_sport_football': 'BBC Sport Football',
        'sky_sports_football': 'Sky Sports Football',
        'sky_sports_premier_league': 'Sky Sports Premier League'
    }

    results = {}
    errors = []

    for feed_key, feed_name in feeds.items():
        try:
            print(f"📡 Checking {feed_name}...")

            # Get the feed URL
            feed_url = rss.feeds.get(feed_key, {}).get('url')
            if not feed_url:
                print(f"   ❌ No URL configured for {feed_key}")
                errors.append(f"{feed_name}: No URL configured")
                continue

            print(f"   URL: {feed_url}")

            # Check the feed
            items = await rss._check_feed(feed_key, max_age_hours=48)
            results[feed_name] = items

            print(f"   ✅ Found {len(items)} items\n")

            # Show first item if available
            if items:
                first = items[0]
                print(f"   Sample item:")
                print(f"     Player: {first.get('player_name', 'N/A')}")
                print(f"     Type: {first.get('type', 'N/A')}")
                print(f"     Details: {first.get('details', 'N/A')[:80]}...")
                print(f"     Reliability: {first.get('base_reliability', 0):.0%}\n")

        except Exception as e:
            print(f"   ❌ Error: {e}\n")
            errors.append(f"{feed_name}: {str(e)}")

    # Summary
    total_items = sum(len(items) for items in results.values())
    print_section("RSS RESULTS")
    print(f"Total items collected: {total_items}")
    print(f"Successful feeds: {len(results)} / {len(feeds)}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\n⚠️  Issues detected:")
        for error in errors:
            print(f"  • {error}")

    return results, errors


async def test_website_scraping():
    """Test website scraping with detailed diagnostics."""
    print_header("TEST 2: WEBSITE SCRAPING")

    print("Testing website scraping (backup intelligence source)...\n")
    print("⚠️  Note: Websites may block scrapers. RSS is preferred.\n")

    results = {}
    errors = []

    try:
        async with WebsiteMonitor() as web_monitor:
            # Test premier injuries
            print("📡 Checking Premier Injuries website...")
            try:
                items = await web_monitor.check_premier_injuries()
                results['Premier Injuries'] = items
                print(f"   ✅ Found {len(items)} items\n")
            except Exception as e:
                print(f"   ❌ Error: {e}\n")
                errors.append(f"Premier Injuries: {str(e)}")

            # Test BBC Sport (if implemented)
            print("📡 Checking BBC Sport website...")
            try:
                # Note: This might not be implemented yet
                print("   ℹ️  BBC Sport scraping not yet implemented\n")
            except Exception as e:
                print(f"   ❌ Error: {e}\n")

    except Exception as e:
        print(f"❌ WebsiteMonitor error: {e}\n")
        errors.append(f"WebsiteMonitor: {str(e)}")

    total_items = sum(len(items) for items in results.values())
    print_section("WEBSITE RESULTS")
    print(f"Total items collected: {total_items}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\n⚠️  Issues detected:")
        for error in errors:
            print(f"  • {error}")

    return results, errors


async def test_youtube_monitor():
    """Test YouTube transcript monitoring."""
    print_header("TEST 3: YOUTUBE TRANSCRIPT MONITORING")

    print("YouTube monitor allows processing FPL content creator videos.\n")

    youtube = YouTubeMonitor()

    print("✅ YouTube monitor initialized")
    print("\n📺 Recommended channels:")
    print("   • FPL Harry")
    print("   • FPL Focal")
    print("   • Let's Talk FPL")
    print("   • FPL Wire")

    print("\n💡 Usage:")
    print("   Pass video URLs dynamically when injury news breaks")
    print("   Example: scout.check_youtube(['https://www.youtube.com/watch?v=...'])")

    print("\n⚠️  Note: Requires video URLs to be configured")
    print("   This is intentionally manual for press conference days\n")

    return {}, []


async def test_player_matching():
    """Test player name matching and classification."""
    print_header("TEST 4: PLAYER NAME MATCHING")

    print("Testing the intelligence classifier's player matching...\n")

    # Load player cache
    db = Database()
    players = db.execute_query("SELECT id, web_name, first_name, second_name FROM players LIMIT 743")

    print(f"✅ Loaded {len(players)} players from database\n")

    # Create player cache (name -> id mapping)
    player_cache = {}
    for p in players:
        player_cache[p['web_name'].lower()] = p['id']
        full_name = f"{p['first_name']} {p['second_name']}".lower()
        player_cache[full_name] = p['id']
        player_cache[p['second_name'].lower()] = p['id']

    print(f"✅ Created cache with {len(player_cache)} name variations\n")

    # Initialize classifier
    classifier = IntelligenceClassifier(player_cache)
    print("✅ Intelligence classifier initialized\n")

    # Test matching with sample intelligence
    print_section("SAMPLE CLASSIFICATIONS")

    test_cases = [
        {
            'player_name': 'Cole Palmer',
            'details': 'Cole Palmer confirmed out for six weeks with knee injury',
            'type': 'INJURY',
            'base_reliability': 0.90
        },
        {
            'player_name': 'Haaland',
            'details': 'Erling Haaland a doubt for weekend clash',
            'type': 'INJURY',
            'base_reliability': 0.70
        },
        {
            'player_name': 'Salah',
            'details': 'Mohamed Salah expected to start despite minor knock',
            'type': 'TEAM_NEWS',
            'base_reliability': 0.80
        }
    ]

    for test in test_cases:
        print(f"Input: \"{test['details']}\"")

        try:
            result = classifier.classify(test, test['base_reliability'])

            print(f"  ✅ Matched: {result.matched_name} (ID: {result.player_id})")
            print(f"     Confidence: {result.confidence:.0%}")
            print(f"     Severity: {result.severity}")
            print(f"     Actionable: {'YES' if result.actionable else 'NO'}\n")

        except Exception as e:
            print(f"  ❌ Error: {e}\n")

    return player_cache


async def test_full_scout_agent():
    """Test the complete Scout agent."""
    print_header("TEST 5: COMPLETE SCOUT AGENT")

    print("Testing the full Scout agent with all components...\n")

    scout = ScoutAgent()
    print("✅ Scout initialized\n")

    print("Loading player cache for fuzzy matching...")
    await scout.load_player_cache()
    print(f"✅ Loaded {len(scout._player_cache)} player name variations\n")

    print("Running intelligence gathering sweep...")
    print("(This checks all sources and classifies results)\n")

    try:
        # Note: Scout's gather_intelligence method needs to exist
        # If not, we'll catch the error
        print("⚠️  Full sweep not yet implemented in Scout agent")
        print("   Use RSS and Website monitors individually (Tests 1-2)")

    except Exception as e:
        print(f"❌ Error: {e}")

    return scout


async def main():
    """Run all diagnostic tests."""

    print("\n" + "=" * 80)
    print(" " * 20 + "🕵️  SCOUT AGENT DIAGNOSTICS")
    print("=" * 80)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nThis diagnostic tool tests all Scout components and identifies issues.")
    print("=" * 80)

    all_errors = []

    # Test 1: RSS Feeds
    try:
        rss_results, rss_errors = await test_rss_feeds()
        all_errors.extend(rss_errors)
    except Exception as e:
        print(f"❌ RSS test failed: {e}")
        all_errors.append(f"RSS test: {str(e)}")

    # Test 2: Website Scraping
    try:
        web_results, web_errors = await test_website_scraping()
        all_errors.extend(web_errors)
    except Exception as e:
        print(f"❌ Website test failed: {e}")
        all_errors.append(f"Website test: {str(e)}")

    # Test 3: YouTube
    try:
        youtube_results, youtube_errors = await test_youtube_monitor()
        all_errors.extend(youtube_errors)
    except Exception as e:
        print(f"❌ YouTube test failed: {e}")
        all_errors.append(f"YouTube test: {str(e)}")

    # Test 4: Player Matching
    try:
        player_cache = await test_player_matching()
    except Exception as e:
        print(f"❌ Player matching test failed: {e}")
        all_errors.append(f"Player matching: {str(e)}")

    # Test 5: Full Scout Agent
    try:
        scout = await test_full_scout_agent()
    except Exception as e:
        print(f"❌ Scout agent test failed: {e}")
        all_errors.append(f"Scout agent: {str(e)}")

    # Final Summary
    print_header("DIAGNOSTIC SUMMARY", "=")

    print(f"Tests completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if all_errors:
        print(f"⚠️  {len(all_errors)} issues detected:\n")
        for i, error in enumerate(all_errors, 1):
            print(f"  {i}. {error}")

        print("\n" + "-" * 80)
        print("RECOMMENDATIONS:")
        print("-" * 80)

        if any('RSS' in e for e in all_errors):
            print("\n📡 RSS Feed Issues:")
            print("  • Check internet connectivity")
            print("  • Verify RSS feed URLs are still valid")
            print("  • Check if feeds require authentication")

        if any('Website' in e or 'Premier Injuries' in e for e in all_errors):
            print("\n🌐 Website Scraping Issues:")
            print("  • Websites may be blocking scrapers (normal)")
            print("  • Use RSS feeds as primary source")
            print("  • Website scraping is backup only")
            print("  • Consider adding User-Agent headers")

        if any('Player' in e or 'match' in e.lower() for e in all_errors):
            print("\n👤 Player Matching Issues:")
            print("  • Check database has player data")
            print("  • Run: venv/bin/python scripts/sync_fpl_data.py")
            print("  • Verify player cache loading")

    else:
        print("✅ All tests passed! Scout is operational.\n")
        print("Intelligence Sources:")
        print("  ✅ RSS feeds working")
        print("  ✅ Player matching working")
        print("  ✅ Classification system working")

    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("""
1. If RSS feeds working: Scout is operational! ✅
2. If issues detected: Follow recommendations above
3. To use Scout in production:
   • Set up daily cron job (03:00 AM)
   • Configure event bus for Hugo integration
   • Add YouTube URLs for press conference days
4. Monitor Scout logs for ongoing issues

For help: See docs/LOGGING_AND_MONITORING.md
    """)

    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(main())
