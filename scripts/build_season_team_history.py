#!/usr/bin/env python3
"""
Build canonical season_team_history from FPL API picks data.

What gets captured per gameweek (for Ron's entry, GW8-38 of 2025/26):
  - The 15 players Ron actually fielded
  - Their position (1-15: starting 11 + bench 12-15)
  - Captain / vice captain / multiplier (so we can resolve auto-subs later)
  - Active chip (wildcard / freehit / bboost / 3xc / None)
  - Per-GW summary stats (event_points, transfers, transfer_cost, bank, value, points_on_bench, overall_rank)

Source of truth: data/season_end_stats_2025-26/ron_picks_by_gw.json (pulled from the
official FPL entry/{id}/event/{gw}/picks/ endpoint, which is what FPL actually fielded).

This is the canonical record for backtesting:
  - draft_team is the pre-deadline *plan*, can drift from what was submitted
  - my_team was the same idea but abandoned after GW9
  - Neither captures the per-GW summary, chip used, or actual XI
"""
import json
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

PICKS_JSON = project_root / 'data' / 'season_end_stats_2025-26' / 'ron_picks_by_gw.json'

SCHEMA = """
CREATE TABLE IF NOT EXISTS season_team_history (
    season TEXT NOT NULL,
    gameweek INTEGER NOT NULL,
    pick_position INTEGER NOT NULL,  -- 1-15 (1-11 starting, 12-15 bench)
    player_id INTEGER NOT NULL,
    element_type INTEGER,            -- 1=GK 2=DEF 3=MID 4=FWD
    is_captain INTEGER NOT NULL DEFAULT 0,
    is_vice_captain INTEGER NOT NULL DEFAULT 0,
    multiplier INTEGER NOT NULL DEFAULT 1,  -- 0 if didn't play (autosubbed out), 2=cap, 3=TC
    active_chip TEXT,                -- wildcard|freehit|bboost|3xc|NULL
    event_points INTEGER,
    event_transfers INTEGER,
    event_transfers_cost INTEGER,
    bank INTEGER,                    -- in tenths of millions (FPL convention)
    value INTEGER,                   -- in tenths of millions
    points_on_bench INTEGER,
    overall_rank INTEGER,
    PRIMARY KEY (season, gameweek, pick_position)
);
CREATE INDEX IF NOT EXISTS idx_sth_player_gw ON season_team_history(player_id, gameweek);
CREATE INDEX IF NOT EXISTS idx_sth_gw ON season_team_history(gameweek);
"""

SEASON = '2025-26'


def main() -> int:
    db = Database()

    with db.get_connection() as conn:
        for stmt in SCHEMA.strip().split(';'):
            if stmt.strip():
                conn.execute(stmt)
        conn.commit()

    raw = json.loads(PICKS_JSON.read_text())
    rows_to_insert = []
    skipped = []

    for gw_str, payload in raw.items():
        if 'picks' not in payload:
            skipped.append((int(gw_str), payload.get('detail', 'no picks')))
            continue

        gw = int(gw_str)
        chip = payload.get('active_chip')
        hist = payload.get('entry_history', {}) or {}

        for pick in payload['picks']:
            rows_to_insert.append((
                SEASON,
                gw,
                pick['position'],
                pick['element'],
                pick.get('element_type'),
                int(pick.get('is_captain', False)),
                int(pick.get('is_vice_captain', False)),
                pick.get('multiplier', 1),
                chip,
                hist.get('points'),
                hist.get('event_transfers'),
                hist.get('event_transfers_cost'),
                hist.get('bank'),
                hist.get('value'),
                hist.get('points_on_bench'),
                hist.get('overall_rank'),
            ))

    # Wipe and rebuild — this is idempotent
    with db.get_connection() as conn:
        conn.execute("DELETE FROM season_team_history WHERE season = ?", (SEASON,))
        conn.executemany(
            """INSERT INTO season_team_history
               (season, gameweek, pick_position, player_id, element_type,
                is_captain, is_vice_captain, multiplier, active_chip,
                event_points, event_transfers, event_transfers_cost,
                bank, value, points_on_bench, overall_rank)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows_to_insert,
        )
        conn.commit()

    print(f"Inserted {len(rows_to_insert)} rows into season_team_history for {SEASON}")
    print(f"Skipped GWs (no picks from FPL): {[gw for gw, _ in skipped]}")

    # Sanity summary
    summary = db.execute_query(
        """SELECT gameweek, COUNT(*) AS picks,
                  SUM(CASE WHEN is_captain THEN 1 ELSE 0 END) AS captains,
                  active_chip, event_points, overall_rank
           FROM season_team_history
           WHERE season = ?
           GROUP BY gameweek
           ORDER BY gameweek""",
        (SEASON,)
    )
    print("\nPer-GW summary:")
    print(f"{'GW':>3} {'picks':>5} {'cap':>3} {'pts':>4} {'rank':>9} {'chip':>10}")
    for r in summary:
        chip = r['active_chip'] or ''
        print(f"  {r['gameweek']:>2} {r['picks']:>4} {r['captains']:>3} "
              f"{r['event_points'] or 0:>4} {r['overall_rank'] or 0:>9} {chip:>10}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
