#!/usr/bin/env python3
"""
Monitor Price Changes

Tracks player price changes and updates predictions.
Runs hourly to catch price rises/falls early.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.price_monitor')


def main():
    """Monitor price changes."""

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("PRICE CHANGE MONITORING")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"PriceMonitor: Starting price monitoring at {start_time}")

    db = Database()

    # Get current prices from latest bootstrap data
    print("\n" + "-" * 80)
    print("CHECKING FOR PRICE CHANGES")
    print("-" * 80)

    try:
        # Get all players from database
        players_data = db.execute_query("""
            SELECT id, web_name, now_cost FROM players
            ORDER BY id
        """)

        if not players_data:
            print("❌ No players data available")
            print("Run: venv/bin/python scripts/collect_fpl_data.py")
            return 1

        print(f"Checking {len(players_data)} players...")

        # Track changes
        price_rises = []
        price_falls = []

        # TODO: This needs to fetch from FPL API and compare to database
        # For now, just check price_changes table for recent changes
        recent_changes = db.execute_query("""
            SELECT player_id, old_price, new_price, detected_at
            FROM price_changes
            WHERE DATE(detected_at) = DATE('now')
            ORDER BY detected_at DESC
        """)

        if recent_changes:
            for change in recent_changes:
                player = db.execute_query("""
                    SELECT web_name FROM players WHERE id = ?
                """, (change['player_id'],))

                if player:
                    change_amount = change['new_price'] - change['old_price']
                    change_data = {
                        'id': change['player_id'],
                        'name': player[0]['web_name'],
                        'old': change['old_price'] / 10,
                        'new': change['new_price'] / 10,
                        'change': change_amount / 10
                    }

                    if change_amount > 0:
                        price_rises.append(change_data)
                    else:
                        price_falls.append(change_data)

        # Report changes
        if price_rises:
            logger.info(f"PriceMonitor: Detected {len(price_rises)} price rises")
            print(f"\n📈 PRICE RISES ({len(price_rises)}):")
            for p in price_rises[:10]:  # Show first 10
                print(f"  {p['name']}: £{p['old']:.1f}m → £{p['new']:.1f}m (+£{p['change']:.1f}m)")
                logger.info(f"PriceMonitor: RISE - {p['name']} ({p['id']}) +£{p['change']:.1f}m")

        if price_falls:
            logger.info(f"PriceMonitor: Detected {len(price_falls)} price falls")
            print(f"\n📉 PRICE FALLS ({len(price_falls)}):")
            for p in price_falls[:10]:  # Show first 10
                print(f"  {p['name']}: £{p['old']:.1f}m → £{p['new']:.1f}m ({p['change']:.1f}m)")
                logger.info(f"PriceMonitor: FALL - {p['name']} ({p['id']}) {p['change']:.1f}m")

        if not price_rises and not price_falls:
            logger.info("PriceMonitor: No price changes detected")
            print("\n✓ No price changes detected")

        # Update database with new prices
        if price_rises or price_falls:
            print("\n" + "-" * 80)
            print("UPDATING DATABASE")
            print("-" * 80)

            updated = 0
            for player_data in players:
                try:
                    db.execute_update("""
                        UPDATE players
                        SET now_cost = ?, cost_change_event = ?
                        WHERE id = ?
                    """, (
                        player_data['now_cost'],
                        player_data.get('cost_change_event', 0),
                        player_data['id']
                    ))
                    updated += 1
                except Exception as e:
                    logger.warning(f"PriceMonitor: Could not update player {player_data['id']}: {e}")

            print(f"✓ Updated {updated} player records")

        # Log changes to price_changes table (if it exists)
        if price_rises or price_falls:
            try:
                for p in price_rises + price_falls:
                    db.execute_update("""
                        INSERT INTO price_changes
                        (player_id, old_price, new_price, change_amount, detected_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (p['id'], int(p['old'] * 10), int(p['new'] * 10), int(p['change'] * 10)))

            except Exception as e:
                # Table might not exist - that's OK
                logger.debug(f"PriceMonitor: Could not log to price_changes table: {e}")

    except Exception as e:
        logger.error(f"PriceMonitor: Error checking prices: {e}", exc_info=True)
        print(f"❌ Error: {e}")
        return 1

    duration = (datetime.now() - start_time).total_seconds()

    total_changes = len(price_rises) + len(price_falls)
    logger.info(f"PriceMonitor: Complete - Duration: {duration:.1f}s, Changes detected: {total_changes} (Rises: {len(price_rises)}, Falls: {len(price_falls)})")

    print("\n" + "=" * 80)
    print("PRICE MONITORING COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f} seconds")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nPrice monitoring cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PriceMonitor: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
