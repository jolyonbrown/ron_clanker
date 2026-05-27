# data/archives — where season snapshots live

This directory is **gitignored** (see `.gitignore`). Season archives are
30-100 MB and don't belong in git; they live here on the local box and
should be rsync'd off-box for real safety.

Each archive is a self-contained subdirectory named
`<season>_<YYYYMMDD_HHMMSS>/`. Contents are documented in the per-archive
`README.md` (e.g. `data/archives/2025-26_20260526_084029/README.md`).

Standard layout for every archive:

```
<season>_<timestamp>/
├── README.md                  # what's in this archive, schema notes, caveats, loading examples
├── manifest.json              # provenance: git commit, SHA-256, per-table row counts
├── ron_clanker_<season>.db    # SQLite snapshot (online backup API → safe even mid-write)
├── csv/*.csv.gz               # every table as gzipped CSV (portable, schema-free)
├── fpl_api_snapshots/         # raw FPL API JSON the DB doesn't capture
│   ├── manifest.json
│   ├── bootstrap_static.json
│   ├── dream_teams_all_gws.json
│   ├── event_<final_gw>_live.json
│   ├── ron_summary.json
│   ├── ron_history.json
│   ├── ron_transfers.json
│   ├── ron_picks_by_gw.json   # source of truth for what Ron fielded each GW
│   ├── ron_cup.json
│   └── fixtures_all.json
└── models_at_season_end/      # frozen models/ at archive time (for reproducibility)
```

## Creating a new archive

```bash
python scripts/archive_season.py --season YYYY-YY
```

That creates the SQLite snapshot, CSV exports, and the top-level
`manifest.json`. You then need to manually capture the FPL API JSON
(`fpl_api_snapshots/`), frozen models (`models_at_season_end/`), and
write a README — none of which `archive_season.py` does today. The
2025-26 README is a good template.

## Loading an archive

```python
import pandas as pd, sqlite3
ARCH = 'data/archives/2025-26_20260526_084029'

# Option A — pure pandas, no SQLite
sth = pd.read_csv(f'{ARCH}/csv/season_team_history.csv.gz')

# Option B — SQL via the snapshot DB (open read-only to be safe)
con = sqlite3.connect(f'file:{ARCH}/ron_clanker_2025-26.db?mode=ro', uri=True)
df = pd.read_sql('SELECT * FROM season_team_history', con)
```

See the per-archive README for column dictionaries and known caveats.

## Existing archives

| Season | Path | Notes |
|---|---|---|
| 2025-26 | `2025-26_20260526_084029/` | Ron's first full season (entered GW8). Final 1,704 pts, rank ~9.07M. Used all 8 chips. |

Older small archive from `2025-26_20260521_144729/` was a mid-season test
and can be deleted.
