#!/usr/bin/env python3
"""
Simple Demo - See Ron's System in Action

Shows step-by-step how agents work with clear logging.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure clear, readable logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-25s | %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


async def demo():
    """Run a simple demonstration of Ron's system."""

    print("\n" + "=" * 80)
    print("RON CLANKER - SIMPLE DEMONSTRATION")
    print("=" * 80)
    print("\nWatch the logs below to see each component initialize and work...\n")

    # Step 1: Initialize Scout
    print("\n[STEP 1] Starting Scout (Intelligence Gathering Agent)")
    print("-" * 80)

    from agents.scout import ScoutAgent
    scout = ScoutAgent()

    logger.info("Scout agent created")

    print("Loading player cache for fuzzy name matching...")
    await scout.load_player_cache()
    logger.info(f"Player cache loaded: {len(scout._player_cache)} names")

    # Step 2: Gather Intelligence
    print("\n[STEP 2] Gathering Intelligence from External Sources")
    print("-" * 80)

    from intelligence.rss_monitor import RSSMonitor
    rss = RSSMonitor()

    logger.info("Checking RSS feeds...")
    intel = await rss.check_all(max_age_hours=24)
    logger.info(f"Intelligence gathered: {len(intel)} items")

    if intel:
        print(f"\nFound {len(intel)} intelligence items:")
        for item in intel[:3]:
            print(f"  • [{item['type']}] {item['player_name']}: {item['details'][:60]}...")

    # Step 3: Initialize Hugo (Transfer Strategy)
    print("\n[STEP 3] Starting Hugo (Transfer Strategy Agent)")
    print("-" * 80)

    from agents.transfer_strategy import TransferStrategyAgent
    hugo = TransferStrategyAgent()

    logger.info("Hugo initialized and listening for intelligence events")

    # Step 4: Check Infrastructure
    print("\n[STEP 4] Checking Infrastructure Status")
    print("-" * 80)

    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        logger.info("✅ Redis event bus: Connected and healthy")
    except Exception as e:
        logger.warning(f"⚠️  Redis event bus: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print("\nAll logs above show real-time agent activity.")
    print("In production, these logs would:")
    print("  • Guide autonomous decision-making")
    print("  • Track intelligence gathering")
    print("  • Monitor injury/transfer events")
    print("  • Record Ron's decisions")
    print("\nCheck the timestamps - you can see exactly when each step happened.")
    print("\n" + "=" * 80)


if __name__ == '__main__':
    asyncio.run(demo())
