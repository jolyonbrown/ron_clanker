#!/usr/bin/env python3
"""
Season rollover — reset the live database for a new FPL season.

WHY THIS EXISTS (ron_clanker-0l1x): when the new season's game opens
(~July), FPL renumbers every element ID — player id 233 becomes a
different human, team ids reshuffle with promotion. The live DB is
keyed by the OLD ids everywhere (predictions, gameweek history, price
snapshots, squads), so every history-keyed walk-forward feature —
calibration pairs, play probability, captain ceiling — would silently
join the wrong players. The only stable cross-season keys are
players.code and teams.code.

What it does, in order:

  1. SAFETY: verifies a season archive exists (data/archives/<season>_*)
     and takes a fresh pre-rollover DB backup.
  2. MIGRATE: copies player_gameweek_history into
     historical_gameweek_data keyed by player_code (opponent club code
     and home/away derived via fixtures + teams.code), and registers
     the season in `seasons` — so the closing season joins the
     multi-season training set and the backtest HistoricalSeasonProvider.
  3. WIPE: deletes every current-season, id-keyed table (list below).
  4. VACUUM.

Defaults to --dry-run. Run for real with:
    venv/bin/python scripts/season_rollover.py --closing-season 2025-26 --execute

Run BEFORE the new season's bootstrap goes live if possible. The price
snapshot detector also has a mass-change guard as a second line of
defence, but a clean wipe is the real protection.

After rollover, once the new game is live:
    venv/bin/python scripts/collect_fpl_data.py   # fresh bootstrap
(timers keep running; they are harmless against an empty season)
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

# Current-season, id-keyed (or stale-by-construction) tables. Wiped.
WIPE_TABLES = [
    # bootstrap mirrors — ids renumber
    'players', 'teams', 'fixtures', 'gameweeks',
    # per-GW data keyed by old player ids (pgh AFTER migration)
    'player_gameweek_history', 'player_predictions',
    # price pipeline (snapshot ids renumber; model + its lineage survive)
    'player_transfer_snapshots', 'price_changes', 'price_predictions',
    # squad state
    'current_team', 'draft_team', 'draft_transfers', 'my_team',
    'transfers', 'team_value',
    # decision/learning logs for the closed season (archived)
    'decisions', 'learning_metrics',
    # league + rivals (league re-forms; picks reference old ids)
    'league_rivals', 'league_standings_history', 'rival_chip_usage',
    'rival_team_picks', 'rival_transfers',
    # Elo is team-id keyed; ids reshuffle with promotion — re-learns
    'elo_ratings', 'elo_match_results',
    # empty-by-audit tables, wiped for completeness
    'chips_used', 'agent_performance', 'model_predictions',
    'model_performance', 'learned_thresholds', 'player_code_mapping',
]

# Cross-season tables that must SURVIVE: historical_gameweek_data,
# historical_players, historical_teams, seasons, season_team_history,
# model_registry, price_model_performance.


def verify_archive(season: str) -> Path:
    archives = project_root / 'data' / 'archives'
    candidates = sorted(archives.glob(f'{season}_*/manifest.json'))
    if not candidates:
        sys.exit(
            f"ABORT: no archive found for {season} under data/archives/.\n"
            f"Run: venv/bin/python scripts/archive_season.py --season {season}"
        )
    return candidates[-1].parent


def backup_live_db(db_path: Path) -> Path:
    backups = project_root / 'data' / 'backups'
    backups.mkdir(exist_ok=True)
    dest = backups / f'pre_rollover_{datetime.now():%Y%m%d_%H%M%S}.db'
    shutil.copy2(db_path, dest)
    return dest


def migrate_history(db, season: str) -> int:
    """Copy the closing season's per-GW data into the cross-season table,
    keyed by player_code. Idempotent: replaces any existing rows for the
    season."""
    db.execute_update(
        "DELETE FROM historical_gameweek_data WHERE season_id = ?", (season,))
    db.execute_update("""
        INSERT INTO historical_gameweek_data (
            season_id, player_code, gameweek, minutes, goals_scored,
            assists, clean_sheets, goals_conceded, own_goals,
            penalties_saved, penalties_missed, yellow_cards, red_cards,
            saves, bonus, bps, influence, creativity, threat, ict_index,
            expected_goals, expected_assists, expected_goal_involvements,
            expected_goals_conceded, total_points, opponent_team_code,
            was_home, fixture_difficulty, value, selected, transfers_in,
            transfers_out, fixture_id, kickoff_time
        )
        SELECT
            ?, p.code, h.gameweek, h.minutes, h.goals_scored,
            h.assists, h.clean_sheets, h.goals_conceded, h.own_goals,
            h.penalties_saved, h.penalties_missed, h.yellow_cards,
            h.red_cards, h.saves, h.bonus, h.bps, h.influence,
            h.creativity, h.threat, h.ict_index,
            h.expected_goals, h.expected_assists,
            h.expected_goal_involvements, h.expected_goals_conceded,
            h.total_points,
            CASE WHEN f.team_h = p.team_id THEN ta.code ELSE th.code END,
            CASE WHEN f.team_h = p.team_id THEN 1 ELSE 0 END,
            CASE WHEN f.team_h = p.team_id
                 THEN f.team_h_difficulty ELSE f.team_a_difficulty END,
            h.value, h.selected, h.transfers_in, h.transfers_out,
            h.fixture_id, f.kickoff_time
        FROM player_gameweek_history h
        JOIN players p ON p.id = h.player_id
        LEFT JOIN fixtures f ON f.id = h.fixture_id
        LEFT JOIN teams th ON th.id = f.team_h
        LEFT JOIN teams ta ON ta.id = f.team_a
    """, (season,))
    rows = db.execute_query(
        "SELECT COUNT(*) AS n FROM historical_gameweek_data "
        "WHERE season_id = ?", (season,))
    n = rows[0]['n']

    # Register the season (idempotent)
    db.execute_update("""
        INSERT OR REPLACE INTO seasons
            (id, name, start_year, end_year, total_gameweeks, is_current,
             data_source, import_completed_at)
        VALUES (?, ?, ?, ?, 38, 0, 'ron_clanker_live', CURRENT_TIMESTAMP)
    """, (season, season.replace('-', '/20'),
          int(season[:4]), int(season[:4]) + 1))
    return n


def wipe_current_season(db) -> dict:
    counts = {}
    for table in WIPE_TABLES:
        try:
            rows = db.execute_query(f"SELECT COUNT(*) AS n FROM {table}")
            counts[table] = rows[0]['n']
            db.execute_update(f"DELETE FROM {table}")
        except Exception as e:
            counts[table] = f'ERROR: {e}'
    return counts


def main():
    ap = argparse.ArgumentParser(description='Season rollover (destructive!)')
    ap.add_argument('--closing-season', required=True,
                    help='Season being closed, e.g. 2025-26')
    ap.add_argument('--execute', action='store_true',
                    help='Actually do it (default is dry-run)')
    ap.add_argument('--db', default='data/ron_clanker.db')
    args = ap.parse_args()

    print('=' * 68)
    print(f'SEASON ROLLOVER — closing {args.closing_season}'
          + ('' if args.execute else '   [DRY RUN]'))
    print('=' * 68)

    archive = verify_archive(args.closing_season)
    print(f'✓ archive found: {archive}')

    db = Database(args.db)
    if not args.execute:
        pgh = db.execute_query(
            "SELECT COUNT(*) AS n FROM player_gameweek_history")[0]['n']
        print(f'would migrate {pgh} player_gameweek_history rows into '
              f'historical_gameweek_data as season {args.closing_season}')
        print(f'would wipe {len(WIPE_TABLES)} tables:')
        for t in WIPE_TABLES:
            try:
                n = db.execute_query(f"SELECT COUNT(*) AS n FROM {t}")[0]['n']
            except Exception:
                n = '?'
            print(f'   {t:35s} {n}')
        print('\nRe-run with --execute to perform the rollover.')
        return

    backup = backup_live_db(Path(args.db))
    print(f'✓ pre-rollover backup: {backup}')

    migrated = migrate_history(db, args.closing_season)
    print(f'✓ migrated {migrated} rows into historical_gameweek_data '
          f'({args.closing_season})')

    counts = wipe_current_season(db)
    for t, n in counts.items():
        print(f'   wiped {t:35s} {n}')

    with db.get_connection() as con:
        con.execute('VACUUM')
    print('✓ VACUUM complete')
    print('\nNext steps once the new season bootstrap is live:')
    print('  venv/bin/python scripts/collect_fpl_data.py')


if __name__ == '__main__':
    main()
