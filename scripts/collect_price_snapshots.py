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

# A change is only a NIGHTLY price move if the snapshots are close
# together. Larger gaps (collection outage, season boundary) would
# record months of price drift as one night and poison training labels.
MAX_DETECTION_GAP_DAYS = 3

# A real night changes a handful of prices. If a large share of players
# "changed" at once, the player IDs have been renumbered underneath us
# (new season's bootstrap went live before season_rollover.py ran) and
# the diffs compare DIFFERENT HUMANS sharing an id. Refuse to record.
MAX_CHANGED_SHARE = 0.30


def detect_price_changes(db, backfill: bool = False) -> int:
    """Derive price_changes rows from day-over-day snapshot prices.

    monitor_prices.py was meant to write price_changes but its detection
    was never implemented (the trainer waited on an empty table all
    season). Snapshots already carry now_cost per day, so changes are
    consecutive-snapshot diffs. Idempotent: at most one change row per
    (player, date).

    backfill=True processes every consecutive snapshot-date pair;
    otherwise only the latest pair (the nightly path).
    """
    dates = [r['snapshot_date'] for r in db.execute_query(
        "SELECT DISTINCT snapshot_date FROM player_transfer_snapshots "
        "ORDER BY snapshot_date")]
    if len(dates) < 2:
        return 0
    pairs = list(zip(dates, dates[1:])) if backfill else [(dates[-2], dates[-1])]

    inserted = 0
    for prev_d, cur_d in pairs:
        gap = (date.fromisoformat(str(cur_d)[:10])
               - date.fromisoformat(str(prev_d)[:10])).days
        if gap > MAX_DETECTION_GAP_DAYS:
            logger.info(
                "PriceChanges: skipping %s -> %s (gap %dd > %dd, not a "
                "nightly move)", prev_d, cur_d, gap, MAX_DETECTION_GAP_DAYS)
            continue
        rows = db.execute_query("""
            SELECT cur.player_id,
                   prev.now_cost AS old_price,
                   cur.now_cost AS new_price,
                   cur.gameweek
            FROM player_transfer_snapshots cur
            JOIN player_transfer_snapshots prev
              ON prev.player_id = cur.player_id
             AND prev.snapshot_date = ?
            WHERE cur.snapshot_date = ?
              AND cur.now_cost != prev.now_cost
        """, (prev_d, cur_d))
        compared = db.execute_query("""
            SELECT COUNT(*) AS n
            FROM player_transfer_snapshots cur
            JOIN player_transfer_snapshots prev
              ON prev.player_id = cur.player_id
             AND prev.snapshot_date = ?
            WHERE cur.snapshot_date = ?
        """, (prev_d, cur_d))[0]['n']
        if compared and len(rows) / compared > MAX_CHANGED_SHARE:
            logger.error(
                "PriceChanges: %d/%d players 'changed' %s -> %s — this is "
                "an ID renumbering (new season bootstrap?), not price moves."
                " Run scripts/season_rollover.py. Skipping detection.",
                len(rows), compared, prev_d, cur_d)
            continue
        detected_at = f'{str(cur_d)[:10]} 02:30:00'
        for r in rows:
            db.execute_update("""
                INSERT INTO price_changes
                    (player_id, old_price, new_price, change_amount,
                     detected_at, gameweek)
                SELECT ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM price_changes
                    WHERE player_id = ? AND DATE(detected_at) = ?
                )
            """, (r['player_id'], r['old_price'], r['new_price'],
                  r['new_price'] - r['old_price'], detected_at,
                  r['gameweek'], r['player_id'], str(cur_d)[:10]))
            inserted += 1
    return inserted


def verify_price_predictions(db) -> int:
    """Fill price_predictions outcomes (actual_change, prediction_correct)
    once the night they predicted has been observed.

    A prediction made at 23:00 for date d is settled by the ~02:00 change
    on d, which the nightly snapshot+detection run records on d's run.
    Only dates detection actually covered are verified: d must be a
    snapshot date whose previous snapshot is within the gap guard —
    otherwise (outage, season boundary) the prediction stays NULL rather
    than being scored against missing data."""
    dates = [str(r['snapshot_date'])[:10] for r in db.execute_query(
        "SELECT DISTINCT snapshot_date FROM player_transfer_snapshots "
        "ORDER BY snapshot_date")]
    verifiable = set()
    for prev_d, cur_d in zip(dates, dates[1:]):
        gap = (date.fromisoformat(cur_d) - date.fromisoformat(prev_d)).days
        if gap <= MAX_DETECTION_GAP_DAYS:
            verifiable.add(cur_d)
    if not verifiable:
        return 0

    pending = db.execute_query(
        "SELECT id, player_id, prediction_for_date, predicted_change "
        "FROM price_predictions WHERE actual_change IS NULL")
    verified = 0
    for p in pending:
        d = str(p['prediction_for_date'])[:10]
        if d not in verifiable:
            continue
        change = db.execute_query(
            "SELECT change_amount FROM price_changes "
            "WHERE player_id = ? AND DATE(detected_at) = ?",
            (p['player_id'], d))
        actual = 0
        if change:
            actual = 1 if change[0]['change_amount'] > 0 else -1
        db.execute_update(
            "UPDATE price_predictions "
            "SET actual_change = ?, prediction_correct = ? WHERE id = ?",
            (actual, 1 if actual == p['predicted_change'] else 0, p['id']))
        verified += 1
    return verified


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

        # Derive nightly price changes from the latest snapshot pair
        changes = detect_price_changes(db)
        print(f"💱 Price changes detected since previous snapshot: {changes}")

        # Settle last night's predictions against what actually happened
        verified = verify_price_predictions(db)
        print(f"🎯 Price predictions verified: {verified}")

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
    if '--backfill-changes' in sys.argv:
        # One-off: derive price_changes from ALL existing snapshot history
        n = detect_price_changes(Database(), backfill=True)
        print(f"Backfilled {n} price changes from snapshot history")
        sys.exit(0)
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
