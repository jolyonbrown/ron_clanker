# Gameweek Tracking System

## Overview

Ron Clanker's **single source of truth** for current gameweek tracking. All scripts use this system to avoid confusion about which gameweek is active.

## The Problem This Solves

Before this system:
- ❌ Scripts made assumptions about current GW
- ❌ Database could be out of sync with FPL API
- ❌ Different scripts had different ideas of "current gameweek"
- ❌ Confusion between GW7/GW8 when GW8 started

After this system:
- ✅ Single source of truth (database synced from FPL API)
- ✅ All scripts use `get_current_gameweek()` utility
- ✅ Hourly sync keeps status accurate
- ✅ Clear distinction between current/next/finished gameweeks

## Architecture

```
┌─────────────────────┐
│   FPL API           │  (Source of truth)
│   /bootstrap-static │
└──────────┬──────────┘
           │
           │ Hourly sync (cron)
           ▼
┌─────────────────────┐
│  Database           │
│  gameweeks table    │  (Local cache)
│  - is_current       │
│  - is_next          │
│  - finished         │
└──────────┬──────────┘
           │
           │ get_current_gameweek()
           ▼
┌─────────────────────┐
│  All Scripts        │  (Consumers)
│  - collect_data.py  │
│  - daily_scout.py   │
│  - track_league.py  │
│  - etc.             │
└─────────────────────┘
```

## Components

### 1. Sync Script (`scripts/sync_gameweek_status.py`)

Fetches gameweek status from FPL API and updates database.

**Run manually:**
```bash
python scripts/sync_gameweek_status.py
python scripts/sync_gameweek_status.py --verbose
```

**Automated:** Runs every hour via cron (see `config/crontab.example`)

**What it does:**
- Fetches all 38 gameweeks from FPL API
- Updates `is_current`, `is_next`, `finished` flags in database
- Verifies sync was successful
- Logs discrepancies

### 2. Utility Functions (`utils/gameweek.py`)

Provides easy access to gameweek information.

**Core functions:**

```python
from data.database import Database
from utils.gameweek import get_current_gameweek, get_next_gameweek

db = Database()

# Get current gameweek (e.g., 8)
current_gw = get_current_gameweek(db)

# Get next gameweek (e.g., 9)
next_gw = get_next_gameweek(db)

# Get detailed info
info = get_gameweek_info(db, 8)
# Returns: {'id': 8, 'name': 'Gameweek 8', 'deadline_time': '2025-10-18T10:00:00Z',
#           'finished': False, 'is_current': True, 'is_next': False}

# Check status
is_live = is_gameweek_live(db, 8)        # True if current and not finished
is_done = is_gameweek_finished(db, 7)    # True if finished

# Get ranges
upcoming = get_upcoming_gameweeks(db, count=5)  # Next 5 GWs
latest_finished = get_latest_finished_gameweek(db)  # Most recent finished GW
```

**Advanced functions:**

```python
# Get current if live, otherwise next (useful for planning)
plan_for = get_current_or_next_gameweek(db)

# Get deadline time
deadline = get_gameweek_deadline(db, 8)  # "2025-10-18T10:00:00Z"

# Get multiple gameweeks
gws = get_gameweeks_range(db, start_gw=8, end_gw=12)
```

### 3. Database Schema

```sql
CREATE TABLE gameweeks (
    id INTEGER PRIMARY KEY,                -- 1-38
    name TEXT,                             -- "Gameweek 8"
    deadline_time TIMESTAMP,               -- "2025-10-18T10:00:00Z"
    finished BOOLEAN,                      -- 1 if GW complete
    is_current BOOLEAN,                    -- 1 if GW is live now
    is_next BOOLEAN,                       -- 1 if GW is next up
    -- ... other fields
);
```

**Constraints:**
- Only ONE gameweek should have `is_current = 1`
- Only ONE gameweek should have `is_next = 1`
- If current GW is finished, it's about to transition to next

## Usage Examples

### Example 1: Data Collection Script

**Before (bad):**
```python
# Hardcoded or guessed gameweek
current_gw = 8  # ❌ Wrong when season progresses
```

**After (good):**
```python
from data.database import Database
from utils.gameweek import get_current_gameweek

db = Database()
current_gw = get_current_gameweek(db)  # ✅ Always correct

if current_gw:
    print(f"Collecting data for GW{current_gw}")
else:
    print("Error: Could not determine current gameweek")
    print("Run: python scripts/sync_gameweek_status.py")
```

### Example 2: Pre-Deadline Planning

```python
from utils.gameweek import get_current_or_next_gameweek, get_gameweek_deadline

db = Database()

# Which GW should we plan for?
target_gw = get_current_or_next_gameweek(db)

# When's the deadline?
deadline = get_gameweek_deadline(db, target_gw)

print(f"Planning for GW{target_gw}")
print(f"Deadline: {deadline}")
```

### Example 3: Post-Gameweek Analysis

```python
from utils.gameweek import get_latest_finished_gameweek

db = Database()

# Which GW just finished?
last_gw = get_latest_finished_gameweek(db)

if last_gw:
    print(f"Analyzing results from GW{last_gw}")
    # Fetch player performances, update predictions, etc.
```

### Example 4: Multi-Gameweek Planning

```python
from utils.gameweek import get_current_gameweek, get_upcoming_gameweeks

db = Database()
current = get_current_gameweek(db)

# Look ahead 6 gameweeks for fixture planning
upcoming = get_upcoming_gameweeks(db, count=6)

print(f"Fixture planning from GW{current}:")
for gw in upcoming:
    status = "LIVE" if gw['is_current'] else "UPCOMING"
    print(f"  GW{gw['id']}: {gw['deadline_time']} ({status})")
```

## Troubleshooting

### Database out of sync

**Symptoms:**
- Scripts report wrong gameweek
- `get_current_gameweek()` returns unexpected value

**Solution:**
```bash
python scripts/sync_gameweek_status.py --verbose
```

This will:
1. Fetch current status from FPL API
2. Update database
3. Show before/after comparison

### No current gameweek found

**Symptoms:**
- `get_current_gameweek()` returns `None`
- Scripts can't determine which GW is active

**Causes:**
- Database never synced
- Season not started
- API error

**Solution:**
```bash
# Sync from API
python scripts/sync_gameweek_status.py

# Check result
python -c "from data.database import Database; from utils.gameweek import get_current_gameweek; print(f'Current GW: {get_current_gameweek(Database())}')"
```

### Cron job not running

**Check if installed:**
```bash
crontab -l | grep sync_gameweek_status
```

**Should see:**
```
0 * * * * cd /home/jolyon/ron_clanker && venv/bin/python scripts/sync_gameweek_status.py >> logs/cron_gameweek.log 2>&1
```

**Check logs:**
```bash
tail -f logs/cron_gameweek.log
```

## Migration Guide

### Updating Existing Scripts

**Pattern 1: Scripts with hardcoded GW**

```python
# OLD
current_gw = 8  # ❌

# NEW
from utils.gameweek import get_current_gameweek
current_gw = get_current_gameweek(db)  # ✅
```

**Pattern 2: Scripts fetching from API every time**

```python
# OLD - fetches from API every time (slow, wasteful)
response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
data = response.json()
current_gw = next(e['id'] for e in data['events'] if e['is_current'])  # ❌

# NEW - uses cached database (fast, efficient)
from utils.gameweek import get_current_gameweek
current_gw = get_current_gameweek(db)  # ✅
```

**Pattern 3: Scripts with database queries**

```python
# OLD - direct query (not reusable, error-prone)
result = db.execute_query("SELECT id FROM gameweeks WHERE is_current = 1 LIMIT 1")
current_gw = result[0]['id'] if result else None  # ❌

# NEW - use utility (clean, tested, consistent)
from utils.gameweek import get_current_gameweek
current_gw = get_current_gameweek(db)  # ✅
```

## Best Practices

1. **Always import from utils.gameweek:**
   ```python
   from utils.gameweek import get_current_gameweek
   ```

2. **Never hardcode gameweek numbers:**
   ```python
   # ❌ Don't do this
   if gameweek == 8:
       ...

   # ✅ Do this instead
   current = get_current_gameweek(db)
   if gameweek == current:
       ...
   ```

3. **Handle None gracefully:**
   ```python
   current_gw = get_current_gameweek(db)
   if current_gw is None:
       logger.error("Could not determine current gameweek")
       return
   ```

4. **Run sync before major operations:**
   ```python
   # In critical scripts, ensure fresh data
   os.system("python scripts/sync_gameweek_status.py")
   current_gw = get_current_gameweek(db)
   ```

5. **Use appropriate function for context:**
   - Analysis of past data: `get_latest_finished_gameweek()`
   - Planning future: `get_current_or_next_gameweek()`
   - Live operations: `get_current_gameweek()` + `is_gameweek_live()`

## Testing

```bash
# Test sync
python scripts/sync_gameweek_status.py --verbose

# Test utilities
python -c "
from data.database import Database
from utils.gameweek import *

db = Database()
print(f'Current: {get_current_gameweek(db)}')
print(f'Next: {get_next_gameweek(db)}')
print(f'Latest finished: {get_latest_finished_gameweek(db)}')
print(f'GW8 live? {is_gameweek_live(db, 8)}')
print(f'GW7 finished? {is_gameweek_finished(db, 7)}')
"

# Test cron job (run manually)
cd /home/jolyon/ron_clanker && venv/bin/python scripts/sync_gameweek_status.py
```

## Maintenance

### Regular Tasks

1. **Monitor sync job:**
   ```bash
   tail -f logs/cron_gameweek.log
   ```

2. **Verify accuracy weekly:**
   ```bash
   python scripts/sync_gameweek_status.py --verbose
   ```

3. **Check for drift:**
   ```python
   # Compare DB to API manually
   python -c "
   import requests
   from data.database import Database
   from utils.gameweek import get_current_gameweek

   # From API
   r = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/')
   api_gw = next(e['id'] for e in r.json()['events'] if e['is_current'])

   # From DB
   db_gw = get_current_gameweek(Database())

   print(f'API: GW{api_gw}')
   print(f'DB:  GW{db_gw}')
   print('✅ Match' if api_gw == db_gw else '❌ MISMATCH')
   "
   ```

## Summary

- **Problem:** Scripts confused about current gameweek
- **Solution:** Single source of truth (database synced from FPL API)
- **How:** Hourly cron job + utility functions
- **Result:** All scripts always know the correct current gameweek

**Key files:**
- `scripts/sync_gameweek_status.py` - Syncs from API
- `utils/gameweek.py` - Provides access functions
- `config/crontab.example` - Hourly automation

**Key function:**
```python
from utils.gameweek import get_current_gameweek
current_gw = get_current_gameweek(db)
```

This is now Ron's reliable gameweek tracking system! 🎯
