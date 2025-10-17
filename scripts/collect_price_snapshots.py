#!/usr/bin/env python3
"""
Collect Daily Price Snapshots

Captures daily snapshots of player transfer data for price prediction training.
Should run daily at 23:00 (before 02:00 price changes).

Optimized for Raspberry Pi 3 - efficient, low memory.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.data_collector import DataCollector
from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.price_snapshots')


async def collect_snapshots():
    """Collect today's player snapshots."""

    start_time = datetime.now()
    today = date.today()

    print("\n" + "=" * 80)
    print("DAILY PRICE SNAPSHOT COLLECTION")
    print("=" * 80)
    print(f"Date: {today}")
    print(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    db = Database()
    collector = DataCollector()

    try:
        # Get latest FPL data
        print("\n📡 Fetching latest FPL data...")
        fpl_data = await collector.update_all_data()

        if not fpl_data:
            print("❌ Failed to fetch FPL data")
            return 1

        players = fpl_data.get('players', [])
        print(f"✓ Retrieved {len(players)} players")

        # Get current gameweek
        current_gw = None
        for event in fpl_data.get('events', []):
            if event.get('is_current'):
                current_gw = event['id']
                break

        print(f"Current Gameweek: {current_gw}")

        # Check if snapshots already exist for today (batch check)
        existing_players = set()
        existing_check = db.execute_query("""
            SELECT player_id FROM player_transfer_snapshots
            WHERE snapshot_date = ?
        """, (today,))

        for row in existing_check:
            existing_players.add(row['player_id'])

        # Store snapshots (batch insert for efficiency)
        print(f"\n💾 Storing snapshots (batched for RPi3 efficiency)...")

        snapshots_to_insert = []
        skipped_count = len(existing_players)

        for i, player in enumerate(players):
            if (i + 1) % 100 == 0:
                print(f"  Processing {i + 1}/{len(players)}...")

            if player['id'] in existing_players:
                continue

            # Prepare snapshot data
            snapshots_to_insert.append((
                player['id'], today,
                player.get('transfers_in', 0),
                player.get('transfers_out', 0),
                player.get('transfers_in', 0) - player.get('transfers_out', 0),
                player.get('transfers_in_event', 0),
                player.get('transfers_out_event', 0),
                float(player.get('selected_by_percent', 0.0)),
                float(player.get('form', 0.0)),
                float(player.get('points_per_game', 0.0)),
                player.get('total_points', 0),
                player.get('now_cost', 0),
                player.get('cost_change_event', 0),
                player.get('cost_change_start', 0),
                current_gw
            ))

        # Batch insert all snapshots at once (much faster than individual inserts)
        if snapshots_to_insert:
            try:
                db.execute_many("""
                    INSERT INTO player_transfer_snapshots (
                        player_id, snapshot_date,
                        transfers_in, transfers_out, net_transfers,
                        transfers_in_event, transfers_out_event,
                        selected_by_percent,
                        form, points_per_game, total_points,
                        now_cost, cost_change_event, cost_change_start,
                        gameweek
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, snapshots_to_insert)

                snapshot_count = len(snapshots_to_insert)
                print(f"✓ Stored {snapshot_count} new snapshots")
            except Exception as e:
                logger.error(f"Error storing snapshots: {e}")
                snapshot_count = 0
        else:
            snapshot_count = 0
            print("✓ No new snapshots to store")

        if skipped_count > 0:
            print(f"⚠️  Skipped {skipped_count} existing snapshots")

        # Show top movers (high net transfers)
        print("\n" + "-" * 80)
        print("TOP TRANSFER TARGETS (Today)")
        print("-" * 80)

        top_in = db.execute_query("""
            SELECT
                pts.player_id,
                p.web_name,
                t.name as team_name,
                pts.net_transfers,
                pts.now_cost / 10.0 as price,
                pts.selected_by_percent
            FROM player_transfer_snapshots pts
            JOIN players p ON pts.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            WHERE pts.snapshot_date = ?
            ORDER BY pts.net_transfers DESC
            LIMIT 10
        """, (today,))

        if top_in:
            print("\n📈 Most Transferred IN:")
            for i, player in enumerate(top_in, 1):
                print(f"  {i}. {player['web_name']} ({player['team_name']}) - "
                      f"{player['net_transfers']:,} net | £{player['price']:.1f}m | "
                      f"{player['selected_by_percent']:.1f}% owned")

        # Bottom movers
        top_out = db.execute_query("""
            SELECT
                pts.player_id,
                p.web_name,
                t.name as team_name,
                pts.net_transfers,
                pts.now_cost / 10.0 as price,
                pts.selected_by_percent
            FROM player_transfer_snapshots pts
            JOIN players p ON pts.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            WHERE pts.snapshot_date = ?
            ORDER BY pts.net_transfers ASC
            LIMIT 10
        """, (today,))

        if top_out:
            print("\n📉 Most Transferred OUT:")
            for i, player in enumerate(top_out, 1):
                print(f"  {i}. {player['web_name']} ({player['team_name']}) - "
                      f"{player['net_transfers']:,} net | £{player['price']:.1f}m | "
                      f"{player['selected_by_percent']:.1f}% owned")

        # Stats
        print("\n" + "-" * 80)
        print("DATABASE STATISTICS")
        print("-" * 80)

        snapshot_stats = db.execute_query("""
            SELECT
                COUNT(DISTINCT snapshot_date) as days,
                COUNT(*) as total_snapshots,
                MIN(snapshot_date) as first_date,
                MAX(snapshot_date) as last_date
            FROM player_transfer_snapshots
        """)

        if snapshot_stats:
            stats = snapshot_stats[0]
            print(f"\nTotal snapshots: {stats['total_snapshots']:,}")
            print(f"Days collected: {stats['days']}")
            print(f"Date range: {stats['first_date']} to {stats['last_date']}")

            # Estimate if we have enough data to train
            if stats['days'] >= 7:
                print(f"\n✓ Enough data to train model ({stats['days']} days)")
            else:
                print(f"\n⚠️  Need more data - collect for {7 - stats['days']} more days")

        duration = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 80)
        print("SNAPSHOT COLLECTION COMPLETE")
        print("=" * 80)
        print(f"Duration: {duration:.1f} seconds")
        print(f"Status: SUCCESS")

        return 0

    except Exception as e:
        logger.error(f"Snapshot collection error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1

    finally:
        await collector.close()


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(collect_snapshots())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nSnapshot collection cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
