#!/usr/bin/env python3
"""
Season Archiver

Takes a safe, self-contained snapshot of the full season dataset so it can be
preserved before summer training/schema changes churn the live database.

Produces, under an archive directory:
  - ron_clanker_<season>.db   A consistent SQLite copy (via the backup API,
                              so it is safe to run while the DB is in use / WAL).
  - csv/<table>.csv.gz        Every table exported to gzipped CSV (portable,
                              tool-agnostic, survives schema changes).
  - manifest.json             Season label, timestamp, git commit, file sizes,
                              SHA-256 of the .db copy, and per-table row counts.

The CSV exports make the archive useful even if you never open the .db again
(e.g. loading straight into pandas for model training).

Usage:
    python scripts/archive_season.py                      # auto-detect season
    python scripts/archive_season.py --season 2025-26
    python scripts/archive_season.py --output-dir /mnt/backup/fpl
    python scripts/archive_season.py --no-csv             # .db snapshot only
    python scripts/archive_season.py --db data/ron_clanker.db
"""

import argparse
import csv
import gzip
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def infer_season_label(today: datetime) -> str:
    """Derive an FPL season label like '2025-26' from the current date.

    FPL seasons run roughly August -> May. Treat July as the rollover point.
    """
    if today.month >= 7:
        start = today.year
    else:
        start = today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def git_commit() -> str:
    """Best-effort current git commit hash for provenance."""
    try:
        out = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=str(project_root), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else 'unknown'
    except Exception:
        return 'unknown'


def list_tables(conn: sqlite3.Connection) -> list:
    """Return user table names (excludes sqlite internal tables)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def snapshot_db(source_db: Path, dest_db: Path) -> None:
    """Make a consistent copy of the SQLite DB using the online backup API.

    Safe even if the source is being written to and is in WAL mode.
    """
    src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True, timeout=60)
    try:
        dst = sqlite3.connect(str(dest_db))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def export_tables_to_csv(db_path: Path, csv_dir: Path) -> dict:
    """Export every table to a gzipped CSV. Returns {table: row_count}."""
    csv_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    try:
        for table in list_tables(conn):
            cursor = conn.execute(f'SELECT * FROM "{table}"')
            columns = [d[0] for d in cursor.description]
            out_path = csv_dir / f"{table}.csv.gz"
            n = 0
            with gzip.open(out_path, 'wt', newline='', encoding='utf-8') as fh:
                writer = csv.writer(fh)
                writer.writerow(columns)
                for row in cursor:
                    writer.writerow(row)
                    n += 1
            counts[table] = n
    finally:
        conn.close()
    return counts


def table_row_counts(db_path: Path) -> dict:
    """Row counts per table (used when CSV export is skipped)."""
    counts = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    try:
        for table in list_tables(conn):
            counts[table] = conn.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
    finally:
        conn.close()
    return counts


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def archive_season(source_db: Path, output_root: Path, season: str,
                   export_csv: bool = True) -> Path:
    if not source_db.exists():
        raise FileNotFoundError(f"Source database not found: {source_db}")

    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%d_%H%M%S')
    archive_dir = output_root / f"{season}_{stamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest_db = archive_dir / f"ron_clanker_{season}.db"
    print(f"Snapshotting {source_db} -> {dest_db} ...")
    snapshot_db(source_db, dest_db)

    if export_csv:
        print("Exporting tables to gzipped CSV ...")
        counts = export_tables_to_csv(dest_db, archive_dir / 'csv')
    else:
        counts = table_row_counts(dest_db)

    manifest = {
        'season': season,
        'created_at': now.isoformat(),
        'source_db': str(source_db.resolve()),
        'archived_db': dest_db.name,
        'archived_db_bytes': dest_db.stat().st_size,
        'archived_db_sha256': sha256_of(dest_db),
        'git_commit': git_commit(),
        'csv_exported': export_csv,
        'table_row_counts': counts,
        'total_rows': sum(counts.values()),
    }
    manifest_path = archive_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print("\n" + "=" * 72)
    print(f"Season archive complete: {archive_dir}")
    print("=" * 72)
    print(f"  DB snapshot : {dest_db.name} "
          f"({manifest['archived_db_bytes'] / 1e6:.1f} MB)")
    print(f"  SHA-256     : {manifest['archived_db_sha256']}")
    print(f"  Tables      : {len(counts)}  |  Total rows: {manifest['total_rows']:,}")
    print(f"  CSV export  : {'yes (csv/*.csv.gz)' if export_csv else 'skipped'}")
    print(f"  Manifest    : {manifest_path}")
    print("\nThis archive lives on the same machine. For real safety, copy it")
    print("off-box, e.g.:")
    print(f"  rsync -av '{archive_dir}/' <remote-or-cloud-destination>/")
    return archive_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive the full season dataset.")
    parser.add_argument('--db', default=str(project_root / 'data' / 'ron_clanker.db'),
                        help='Source SQLite database (default: data/ron_clanker.db)')
    parser.add_argument('--output-dir', default=str(project_root / 'data' / 'archives'),
                        help='Where to write the archive (default: data/archives)')
    parser.add_argument('--season', default=None,
                        help='Season label, e.g. 2025-26 (default: inferred from date)')
    parser.add_argument('--no-csv', action='store_true',
                        help='Skip CSV export (snapshot the .db only)')
    args = parser.parse_args()

    season = args.season or infer_season_label(datetime.now(timezone.utc))

    try:
        archive_season(
            source_db=Path(args.db),
            output_root=Path(args.output_dir),
            season=season,
            export_csv=not args.no_csv,
        )
    except Exception as e:
        print(f"\n❌ Archive failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
