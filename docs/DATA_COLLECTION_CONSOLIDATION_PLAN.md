# Data Collection Consolidation Plan
## Issue: ron_clanker-77

**Date**: 2025-10-22
**Branch**: feature/consolidate-data-collection
**Status**: Planning

---

## Problem Statement

Multiple overlapping data collection scripts with bugs and data quality issues are preventing Ron from making accurate decisions and generating correct post-gameweek analysis.

### Symptoms
- Ron's Slack reviews have wrong player points (Haaland 0pts vs actual 26pts)
- Duplicate player records in database
- ML predictions fail due to missing historical data
- Unclear which script to run after each gameweek
- Manual intervention required for post-GW data collection

---

## Current State Analysis

### Database
- **Active DB**: `data/ron_clanker.db` (1.7MB)
- **Empty DB**: `data/fpl.db` (0 bytes) - ❌ unused, should be removed

### Tables (Confirmed in DB)
✅ `gameweeks` - 38 rows, tracks current/finished status
✅ `player_gameweek_history` - **CRITICAL for ML predictions**
✅ `league_standings_history` - Mini-league history
✅ `rival_team_picks` - Rivals' team selections
✅ `league_rivals` - Rival metadata
✅ `players` - 591 FPL players
✅ `teams` - 20 PL teams
✅ `fixtures` - Match schedule

❌ `rival_teams` - Does NOT exist (collect_gameweek_data.py expects it)
❌ `leagues` - Does NOT exist (collect_gameweek_data.py expects it)

### Existing Scripts

#### 1. `scripts/collect_fpl_data.py` ✅ **WORKS**
**Purpose**: Daily FPL API baseline sync
**Cron**: 02:30 daily
**Tables Updated**:
- `players` (591 players with current stats)
- `teams` (20 teams with strength ratings)
- `gameweeks` (38 GWs with finished/current status)

**What it DOESN'T do**:
- ❌ Player gameweek history (ML needs this!)
- ❌ Rival team picks
- ❌ League standings
- ❌ Fixture results

**Verdict**: Good for baseline data, but not sufficient for post-GW analysis

---

#### 2. `scripts/collect_gameweek_data.py` ❌ **BROKEN**
**Purpose**: Post-gameweek analysis data collection
**Status**: Never successfully runs
**Problems**:
- Queries `rival_teams` table (doesn't exist, should be `league_rivals`?)
- Queries `leagues` table (doesn't exist)
- Good architecture, wrong table names

**Intended Tables**:
- ✅ `rival_team_picks` (exists)
- ✅ `players` (exists)
- ✅ `player_gameweek_history` (exists)
- ❌ `rival_teams` (missing - logic needs league_rivals + league_standings_history)
- ❌ `leagues` (missing - need to add or work around)

**Verdict**: Fixable with schema alignment

---

#### 3. `scripts/backfill_gameweek_history.py` ⚠️ **MANUAL ONLY**
**Purpose**: Backfill player_gameweek_history from FPL API
**Usage**: Manual runs for historical data
**SQL**: `INSERT OR REPLACE INTO player_gameweek_history`

**What it does well**:
- Fetches player history from FPL API (`/api/element-summary/{player_id}/`)
- Handles all stat fields correctly
- Uses INSERT OR REPLACE (good for deduplication)

**What it doesn't do**:
- Not automated (manual script)
- Doesn't run after each gameweek
- Requires iterating all 591 players (slow)

**Verdict**: Good logic to borrow for consolidated script

---

#### 4. `scripts/track_mini_league.py` ⚠️ **UNCLEAR USAGE**
**Purpose**: Track league standings and rival picks
**Tables Updated**:
- `league_standings_history`
- `rival_team_picks`

**Status**: Exists but unclear if/when it runs
**Verdict**: Logic should be absorbed into consolidated collector

---

### Critical Dependencies

#### ML Prediction System
**Files**: `ml/prediction/features.py`, `agents/synthesis/engine.py`
**Depends On**: `player_gameweek_history` table

**Why Critical**:
```python
# Feature engineer queries this for form calculation
history = db.execute_query("""
    SELECT gameweek, total_points, minutes, goals_scored, assists,
           bonus, bps, clean_sheets, saves
    FROM player_gameweek_history
    WHERE player_id = ? AND gameweek < ?
    ORDER BY gameweek DESC LIMIT ?
""", (player_id, gameweek, window))
```

**If table is empty/wrong**:
- ML predictions fall back to defaults (avg_points: 0.0)
- Transfer optimizer can't identify good targets
- Captain selection is inaccurate
- Ron makes bad decisions!

---

#### Post-Match Analysis (Banter)
**Files**: `scripts/post_match_review.py`, `scripts/send_gw_review.py`
**Depends On**:
- `player_gameweek_history` (Ron's players' actual points)
- `rival_team_picks` (what rivals picked)
- `league_standings_history` (league positions)

**Current Bug**: Wrong points shown because player_gameweek_history has stale/missing data

---

#### Auto Model Retraining
**Files**: `scripts/auto_retrain_models.py`, `scripts/train_models_quick.py`
**Depends On**: `player_gameweek_history` (training data)

**If data is missing**: Models trained on incomplete data, predictions degrade

---

## The Root Problem

**There is NO automated post-gameweek data collection pipeline!**

```
┌─────────────────────────────────────────────────────────┐
│  CURRENT STATE (BROKEN)                                 │
├─────────────────────────────────────────────────────────┤
│  02:30  collect_fpl_data.py (players, teams, gameweeks) │
│  ???    WHO COLLECTS PLAYER GW HISTORY???              │
│  ???    WHO COLLECTS RIVAL PICKS???                    │
│  ???    WHO COLLECTS LEAGUE STANDINGS???               │
│         ↓ (missing data)                                │
│  03:00  daily_scout.py (needs fresh data)               │
│  06:00  ML predictions (needs player_gameweek_history)  │
│  Mon    post_match_review.py (shows WRONG data!)        │
└─────────────────────────────────────────────────────────┘
```

---

## Solution: Consolidated Post-Gameweek Collector

### Design Principles

1. **Single Authoritative Script**: One script to rule them all
2. **Run Automatically**: Triggered by cron after GW finishes
3. **Idempotent**: Safe to run multiple times (INSERT OR REPLACE)
4. **Fast**: Complete in <2 minutes to avoid timeout
5. **Validated**: Check data quality, log warnings
6. **Comprehensive**: Collect ALL required data in one pass

---

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  NEW CONSOLIDATED PIPELINE                                   │
├──────────────────────────────────────────────────────────────┤
│  02:30  collect_fpl_data.py                                  │
│         └─► players, teams, gameweeks (baseline)             │
│                                                              │
│  02:35  collect_post_gameweek_data.py ⭐ NEW                │
│         ├─► Check if current GW is finished                 │
│         ├─► Player gameweek history (591 players)           │
│         │   └─► FPL API: /api/element-summary/{id}/         │
│         │   └─► player_gameweek_history table               │
│         ├─► League standings                                │
│         │   └─► FPL API: /api/leagues-classic/{id}/         │
│         │   └─► league_standings_history table              │
│         ├─► Rival team picks                                │
│         │   └─► FPL API: /api/entry/{id}/event/{gw}/picks/  │
│         │   └─► rival_team_picks table                      │
│         └─► Validate: Check for duplicates, missing data    │
│                                                              │
│  03:00  daily_scout.py (has fresh data!)                    │
│  06:00  ML predictions (has player_gameweek_history!)       │
│  Mon    post_match_review.py (shows CORRECT data!)          │
└──────────────────────────────────────────────────────────────┘
```

---

### New Script: `collect_post_gameweek_data.py`

#### Responsibilities

1. **Check GW Status**
   ```python
   gw = db.execute_query("SELECT * FROM gameweeks WHERE is_current = 1")
   if not gw[0]['finished']:
       print("GW not finished yet, skipping collection")
       return 0
   ```

2. **Collect Player Gameweek History** (INCREMENTAL APPROACH ⚡)

   **Smart Strategy**: The FPL API returns FULL season history for each player, but we already have most of it!

   **Incremental Logic**:
   ```python
   # Check what we already have
   max_gw_in_db = db.execute_query("""
       SELECT MAX(gameweek) FROM player_gameweek_history
   """)[0]['MAX(gameweek)'] or 0

   current_finished_gw = db.execute_query("""
       SELECT id FROM gameweeks
       WHERE is_current = 1 AND finished = 1
   """)[0]['id']

   if current_finished_gw <= max_gw_in_db:
       print("Already have latest GW data, skipping")
       return

   # Only fetch players who actually played in the NEW gameweek
   players_who_played = db.execute_query("""
       SELECT id FROM players
       WHERE minutes > 0  -- Updated by collect_fpl_data.py
   """)

   # Fetch ONLY those ~200-300 players (not all 591!)
   for player in players_who_played:
       data = fetch_player_history(player['id'])
       # API returns full history, but INSERT OR REPLACE only updates new rows
       # Old GW data already in DB won't change
       store_history(data['history'])  # Idempotent!
   ```

   **Why This is Better**:
   - ✅ Only fetches ~200-300 players instead of 591 (3x faster!)
   - ✅ Idempotent - safe to re-run, won't duplicate
   - ✅ Can skip entirely if we already have the current GW
   - ✅ First run (GW8): fetches all 591 players
   - ✅ Subsequent runs: only players who played that week

   **Optimization Notes**:
   - Use `INSERT OR REPLACE` (already in backfill script)
   - Add 0.1s delay between requests to avoid rate limits
   - Log progress every 50 players
   - Total time: ~30-40 seconds instead of 2 minutes!

3. **Collect League Standings**
   - GET `/api/leagues-classic/{league_id}/standings/?page_standings=1`
   - Extract all managers' ranks, points, GW points
   - INSERT OR REPLACE into `league_standings_history`
   - Track: entry_id, gameweek, rank, total_points, gameweek_points

4. **Collect Rival Team Picks**
   - For each rival: GET `/api/entry/{entry_id}/event/{gw}/picks/`
   - Extract picks (15 players), captain, vice, bench order
   - INSERT OR REPLACE into `rival_team_picks`
   - Track: entry_id, gameweek, player_id, position, is_captain, is_vice

5. **Validate Data Quality**
   - Check for duplicates (should be 0 with UNIQUE constraints)
   - Check completeness (591 players * current_gw rows expected)
   - Log warnings if data seems wrong
   - Report stats (players collected, rivals tracked, etc.)

#### Table Schema Fixes Needed

**Add `leagues` table**:
```sql
CREATE TABLE IF NOT EXISTS leagues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created TIMESTAMP,
    admin_entry INTEGER,
    scoring TEXT,
    size INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Or work around**: Store league name in config, don't need full table for now

**Fix `collect_gameweek_data.py` queries**:
- Change `rival_teams` to use `league_rivals` + `league_standings_history` JOIN
- Remove `leagues` table dependency or add minimal league tracking

---

### Cron Schedule

```cron
# Data collection pipeline (runs EVERY day)
30 2 * * * cd /home/jolyon/ron_clanker && venv/bin/python scripts/collect_fpl_data.py >> logs/cron_data.log 2>&1

# Post-GW collection (checks if GW finished, exits if not)
35 2 * * * cd /home/jolyon/ron_clanker && venv/bin/python scripts/collect_post_gameweek_data.py >> logs/cron_postgw.log 2>&1

# Intelligence (needs post-GW data)
0 3 * * * cd /home/jolyon/ron_clanker && venv/bin/python scripts/daily_scout.py >> logs/cron_scout.log 2>&1
```

**Key insight**: Run post-GW collector EVERY day, but it exits early if GW isn't finished. This way we don't need complex cron timing logic.

---

## Implementation Plan

### Phase 1: Create Consolidated Collector ⭐
1. Create `scripts/collect_post_gameweek_data.py`
2. Implement GW finished check
3. Implement player gameweek history collection
   - Borrow logic from `backfill_gameweek_history.py`
   - Add optimization: only fetch players who played
   - Add progress logging
4. Implement league standings collection
   - Use FPL API league endpoint
   - Handle pagination if league > 50 managers
5. Implement rival team picks collection
   - Iterate league_rivals table
   - Fetch each rival's picks for current GW
6. Add validation and quality checks
7. Add comprehensive logging

### Phase 2: Schema Fixes
1. Add `leagues` table (optional, can defer)
2. Verify all UNIQUE constraints exist
3. Add indexes if missing:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_history_player_gameweek
   ON player_gameweek_history(player_id, gameweek);
   ```

### Phase 3: Fix Existing Scripts
1. Fix `collect_gameweek_data.py` table references
   - Replace `rival_teams` with proper JOINs
   - Remove or add `leagues` table dependency
2. Mark `backfill_gameweek_history.py` as historical-only
3. Deprecate `track_mini_league.py` (absorbed into consolidated collector)

### Phase 4: Integration
1. Add to cron schedule (02:35 daily)
2. Test with real GW8 data (currently finished)
3. Verify ML predictions use fresh data
4. Verify post-match review shows correct points
5. Monitor logs for 1 full gameweek cycle

### Phase 5: Cleanup
1. Delete `data/fpl.db` (empty, unused)
2. Update documentation
3. Archive old scripts to `scripts/deprecated/`
4. Update `CLAUDE.md` with new data flow

---

## Testing Strategy

### Test with GW8 Data (Already Finished)
```bash
# 1. Clear existing GW8 player history (to test fresh collection)
sqlite3 data/ron_clanker.db "DELETE FROM player_gameweek_history WHERE gameweek = 8"

# 2. Run new collector
python scripts/collect_post_gameweek_data.py

# 3. Verify data
sqlite3 data/ron_clanker.db "SELECT COUNT(*) FROM player_gameweek_history WHERE gameweek = 8"
# Expected: ~200-300 (players who actually played)

# 4. Check Ron's team points
python scripts/post_match_review.py --gw 8

# 5. Verify ML can use data
python scripts/test_manager_ml_integration.py
```

### Validation Queries
```sql
-- Check for duplicates (should be 0)
SELECT player_id, gameweek, COUNT(*) as cnt
FROM player_gameweek_history
WHERE gameweek = 8
GROUP BY player_id, gameweek
HAVING cnt > 1;

-- Check data completeness
SELECT COUNT(DISTINCT player_id) as players_collected
FROM player_gameweek_history
WHERE gameweek = 8;

-- Verify Ron's team has data
SELECT p.web_name, pgh.total_points, pgh.minutes
FROM rival_team_picks rtp
JOIN players p ON rtp.player_id = p.id
LEFT JOIN player_gameweek_history pgh
  ON p.id = pgh.player_id AND pgh.gameweek = 8
WHERE rtp.entry_id = 12222054 AND rtp.gameweek = 8
ORDER BY rtp.position;
```

---

## Success Criteria

✅ Post-GW data collected automatically after each gameweek
✅ `player_gameweek_history` populated with actual points for all players
✅ ML predictions have fresh data (no more avg_points: 0.0 fallbacks)
✅ Post-match reviews show CORRECT player points
✅ No manual intervention required
✅ Script completes in < 2 minutes
✅ No duplicate records
✅ Comprehensive logging for debugging
✅ Runs idempotently (safe to re-run)

---

## Risks & Mitigation

### Risk 1: FPL API Rate Limiting
**Impact**: 591 player requests might trigger rate limit
**Mitigation**:
- Add 0.1s delay between requests
- Only fetch players who played (reduces to ~200-300)
- Implement retry logic with exponential backoff

### Risk 2: API Response Changes
**Impact**: FPL might change API structure
**Mitigation**:
- Validate response structure before parsing
- Log raw responses on errors
- Graceful degradation (skip player if parse fails)

### Risk 3: Incomplete Data
**Impact**: Some players might not have history yet
**Mitigation**:
- Handle missing data gracefully (NULL fields)
- Log warnings but don't fail
- Validation step reports gaps

### Risk 4: Timing Issues
**Impact**: Run before bonus points awarded
**Mitigation**:
- Check GW `finished` flag (set after bonus awarded)
- Cron at 02:35 (well after midnight bonus deadline)
- Can re-run safely if needed

---

## Future Enhancements

1. ~~**Incremental Updates**: Only fetch last GW, not full history~~ ✅ **IMPLEMENTED IN PLAN**
2. **Parallel Requests**: Use `asyncio` to fetch players concurrently (could reduce 30s to 5s!)
3. **Smarter Incremental**: Check fixtures endpoint instead of per-player requests
   ```python
   # FPL API has a live gameweek endpoint that shows ALL player stats!
   # GET /api/event/{gw}/live/
   # Returns: All players' points for that specific GW in one request
   # Could replace 591 requests with just 1! But need to test API structure.
   ```
4. **Data Quality Metrics**: Track collection success rate over time
5. **Alert System**: Notify if collection fails or data looks wrong

---

## References

- FPL API Docs: https://github.com/vaastav/Fantasy-Premier-League
- Issue: ron_clanker-77
- Related Scripts: `collect_fpl_data.py`, `backfill_gameweek_history.py`
- Database Schema: `data/schema.sql`

---

**Status**: Ready to implement
**Next Step**: Create `collect_post_gameweek_data.py`
