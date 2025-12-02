# Weekly Gameweek Checklist

## Post-Gameweek Review (Run after gameweek completes)

### 1. Collect Final Gameweek Results
```bash
venv/bin/python scripts/collect_fpl_data.py
```
**Purpose**: Update database with final player points, bonus points, gameweek finished status

**Timing**: Wait until all games complete + bonus points confirmed (usually Monday evening/Tuesday morning)

---

### 2. Track Ron's Performance
```bash
venv/bin/python scripts/track_ron_team.py
```
**What it does**:
- Fetches Ron's actual FPL team for the gameweek
- Calculates total points (including bench, autosubs, captain)
- Compares predictions vs actual performance
- Stores results in `ron_tracking` table
- Identifies biggest prediction errors

**Output**:
- Gameweek summary stored in database
- Report saved to `data/ron_tracking/gw{N}_report.txt`

---

### 3. Generate Ron's Post-Match Review
```bash
venv/bin/python scripts/review_gameweek.py --gw N
```
**What it does**:
- Analyzes gameweek performance
- Identifies what worked / what didn't
- Generates Ron's commentary in his persona
- Updates learning metrics

**Expected output**: Ron's gruff post-match analysis:
```
GAMEWEEK 11 REVIEW

73 points. Job done.

WHAT WORKED:
- Captain Haaland: 13 points. Told you he'd feast on Bournemouth.
- Gabriel: 8 points (CS + 2 DC). Foundation first, fancy stuff second.

WHAT DIDN'T:
- Son blanked. Spurs at home to Villa, should've scored.
- Bench left 12 points unused. Formation call was wrong.

LESSONS:
- DC strategy paying off: 5 defenders/mids averaging 2pts from tackles
- Need better bench management - can't leave points on table

League rank: 45,231 (+5,432 from last week)

Next up: GW12. Fixtures turn against us. Time to plan.

- RC
```

---

### 4. Review Prediction Accuracy
```bash
sqlite3 data/ron_clanker.db "
SELECT
    p.web_name,
    pp.predicted_points as predicted,
    p.event_points as actual,
    (p.event_points - pp.predicted_points) as error,
    CASE
        WHEN ABS(p.event_points - pp.predicted_points) > 5 THEN '🚨'
        ELSE '✓'
    END as flag
FROM player_predictions pp
JOIN players p ON pp.player_id = p.id
WHERE pp.gameweek = N
    AND p.id IN (SELECT player_id FROM draft_team WHERE for_gameweek = N)
ORDER BY ABS(p.event_points - pp.predicted_points) DESC
LIMIT 15;
"
```
**Purpose**: Identify which predictions were way off - helps improve model

---

### 5. Update Learning Metrics
```bash
venv/bin/python scripts/update_learning_metrics.py --gw N
```
**What it tracks**:
- Overall prediction RMSE
- Captain pick success rate
- Transfer decision quality
- Chip usage effectiveness

**Stored in**: `learning_metrics` table for long-term trend analysis

---

## Pre-Deadline Workflow (Run 24-48 hours before deadline)

### 1. Collect Fresh FPL Data
```bash
venv/bin/python scripts/collect_fpl_data.py
```
**Purpose**: Updates player prices, ownership, fixtures, gameweek deadlines, chance_of_playing_this_round

**Critical**: Must run this FIRST - all predictions depend on current data

**Data Quality Check** (NEW - CRITICAL):
After collecting data, verify team strength data was fetched:
```bash
sqlite3 data/ron_clanker.db "
SELECT name, strength_attack_home, strength_defence_home
FROM teams
WHERE id = 13
LIMIT 1;
"
```
Should show Man City with strength values (e.g., 1210, 1230). If NULL, data collection script is broken.

---

### 2. Process News Intelligence

#### Option A: Simplified Press Conferences (RECOMMENDED for Pi)
```bash
venv/bin/python scripts/process_press_conferences.py \
  data/news_input/premier_league_press_conferences_gwN.txt N
```
**Memory**: ~1-2MB
**Time**: ~15 seconds
**Format**: Structured team-by-team injury/availability lists

#### Option B: Email Newsletters
```bash
venv/bin/python scripts/process_email_newsletter.py \
  data/news_input/GWN_newsletter.eml
```
**Memory**: ~1-2MB (after cleanup)
**Time**: ~20 seconds
**Note**: Automatically removes HTML, headers, images

#### Option C: Long-Form Articles ("Big Five" format)
Uses `NewsIntelligenceProcessor.process_news_article()` with automatic batching
**Memory**: ~2-3MB (batched in groups of 20 paragraphs)
**Time**: ~60-90 seconds for 120 paragraphs

**Output**: All news stored in `decisions` table as `news_intelligence` entries

---

### 3. Generate ML Predictions (Optional - done automatically by manager)
```bash
venv/bin/python scripts/predict_gameweek.py --gw N --save
```
**Purpose**: Pre-generate predictions to save time during team selection
**Time**: ~3 minutes for all 700+ players
**Note**: Manager agent will run this anyway if not pre-generated

---

### 4. Run Team Selection (THE MAIN EVENT)
```bash
venv/bin/python scripts/pre_deadline_selection.py
```

**What it does**:
1. Loads Ron's current team from `draft_team` table (GW N-1)
2. Generates ML predictions for GW N, N+1, N+2, N+3 (for transfer planning)
3. Adjusts predictions based on news intelligence (injuries, doubts)
4. Uses `TransferOptimizer` to evaluate transfer options
5. Decides: transfers to make, captain/vice, chip usage
6. **Generates announcement via Claude API** (Ron's persona)
7. Stores decision in database

**Time**: 15-20 minutes (includes ML predictions for 4 gameweeks)
**Memory**: ~200-300MB peak

**Output**:
- Team stored in `draft_team` table for gameweek N
- Transfers logged in `transfers` table
- Decisions logged in `decisions` table
- Announcement text returned

---

### 5. Review Selection
```bash
# View Ron's announcement
venv/bin/python scripts/show_latest_team.py

# Or check database directly
sqlite3 data/ron_clanker.db "
SELECT * FROM draft_team
WHERE for_gameweek = N
ORDER BY position;
"
```

---

## What Went Wrong This Week (GW10) - Lessons Learned

### 🚨 NEW: GW10 DATA QUALITY DISASTER

**CRITICAL ISSUE**: ML predictions completely broken despite database fixes
- Haaland (Man City home vs Bournemouth): 4.62 xP ❌ (should be ~8-10)
- João Pedro (Chelsea away at Spurs): 8.94 xP ❌ (too high)
- Gabriel (Arsenal home vs Bournemouth): 4.51 xP, BENCHED ❌
- Cullen (Burnley AWAY at Arsenal): 4.96 xP, STARTED ❌

**ROOT CAUSE**: Historical training data likely corrupted or model needs complete retrain

**BEADS ISSUE**: ron_clanker-104 (P0)

**LESSONS**:
1. **ALWAYS validate data quality after collection** - don't trust that scripts work
2. **Add sanity checks to predictions** - flag obviously wrong predictions (Haaland < 5 xP at home)
3. **Consider wiping historical data** - start fresh from GW10 onwards with clean data
4. **Test predictions on known-good fixtures** - e.g., premium striker at home to weak team

---

## What Went Wrong Earlier (Lessons Learned)

### ❌ MISTAKE 1: Created GW-specific scripts
**What I did**: Created `select_gw10_team.py` with hardcoded logic
**Why wrong**: Scripts should be REUSABLE across all gameweeks
**Correct approach**: Use `pre_deadline_selection.py` which works for ANY gameweek

### ❌ MISTAKE 2: Generated static announcement text
**What I did**: Wrote hardcoded announcement in `ron_gw10_announcement.txt`
**Why wrong**: Ron's announcements MUST be generated dynamically via Claude API using his persona
**Correct approach**: `RonManager.make_weekly_decision()` calls Claude API to generate personalized announcement

### ❌ MISTAKE 3: Ignored existing team / picked fresh squad
**What I did**: Selected completely new 15 players ignoring Ron's GW9 team
**Why wrong**: FPL rules - Ron has existing team, can only make transfers or use chips
**Correct approach**: Start from `draft_team` table for previous gameweek, make transfers from there

### ❌ MISTAKE 4: Took shortcuts to avoid "slow" manager
**What I did**: Tried to bypass full manager process because it takes 15+ minutes
**Why wrong**: The time is NECESSARY for proper ML predictions + transfer optimization
**Correct approach**: Let it run - 15-20 minutes is acceptable for weekly decision-making

---

## Critical Files & Their Roles

### Scripts (Reusable)
- `scripts/collect_fpl_data.py` - Fetch latest FPL data
- `scripts/process_press_conferences.py` - Process structured news
- `scripts/process_email_newsletter.py` - Process email newsletters
- `scripts/predict_gameweek.py` - Pre-generate ML predictions
- `scripts/pre_deadline_selection.py` - **MAIN SCRIPT** for team selection

### Core Agents
- `agents/manager_agent_v2.py` - RonManager (orchestrator)
- `agents/transfer_optimizer.py` - Transfer planning
- `agents/synthesis/engine.py` - ML prediction synthesis
- `intelligence/news_processor.py` - News intelligence extraction

### Data Flow
1. FPL API → `players` table, `gameweeks` table
2. News sources → `decisions` table (type: `news_intelligence`)
3. ML models → `player_predictions` table
4. Manager decision → `draft_team` table, `transfers` table, `decisions` table

---

## Memory Optimization (Raspberry Pi)

### Why News Processing Was Crashing
**Problem**: Processing 120-paragraph "big five" articles in one API call = 36K tokens = 8GB+ RAM
**Solution**: Batched processing in groups of 20 paragraphs = 6 API calls of 6K tokens each = ~2MB RAM

### Implementation
`intelligence/news_processor.py`:
- Detects "big five" format (50-200 paragraphs)
- Automatically batches into groups of 20
- Processes each batch separately
- Combines results

**Result**: All news formats now stay under 4GB target ✅

---

## Database Schema Quick Reference

### draft_team (Ron's current squad)
```sql
SELECT
    p.web_name,
    p.element_type,
    dt.position,
    dt.is_captain,
    dt.is_vice_captain
FROM draft_team dt
JOIN players p ON dt.player_id = p.id
WHERE dt.for_gameweek = N;
```

### News Intelligence
```sql
SELECT
    decision_data,
    reasoning,
    created_at
FROM decisions
WHERE decision_type = 'news_intelligence'
AND gameweek = N
ORDER BY created_at DESC;
```

### Predictions
```sql
SELECT
    p.web_name,
    pp.predicted_points,
    p.now_cost / 10.0 as price
FROM player_predictions pp
JOIN players p ON pp.player_id = p.id
WHERE pp.gameweek = N
ORDER BY pp.predicted_points DESC
LIMIT 50;
```

---

## Timing Expectations

| Task | Time | Memory |
|------|------|--------|
| Collect FPL data | 30s | 50MB |
| Process press conferences | 15s | 2MB |
| Process email newsletter | 20s | 2MB |
| Process big five article | 90s | 3MB |
| Generate ML predictions (all players) | 3min | 150MB |
| **Full team selection** | **15-20min** | **250MB** |

**Total weekly workflow**: ~25 minutes from start to finish

---

## Next Week's Gameweek (GW11) - Streamlined Process

```bash
# 1. Collect data (run 24-48h before deadline)
venv/bin/python scripts/collect_fpl_data.py

# 1a. VALIDATE data quality (NEW - CRITICAL)
sqlite3 data/ron_clanker.db "
SELECT name, strength_attack_home, strength_defence_home
FROM teams WHERE id = 13 LIMIT 1;
"
# Should show values like: Man City|1210|1230
# If NULL, data collection is broken - FIX BEFORE PROCEEDING

# 2. Process news (as it becomes available)
venv/bin/python scripts/process_press_conferences.py \
  data/news_input/premier_league_press_conferences_gw11.txt 11

venv/bin/python scripts/process_email_newsletter.py \
  data/news_input/GW11_newsletter.eml

# 3. Make team selection (run 6h before deadline)
venv/bin/python scripts/pre_deadline_selection.py

# 4. Review & submit to FPL website
# - Check announcement makes sense
# - Verify captain/vice-captain are reasonable
# - Submit team manually (no API submission yet)

# 5. Post announcement to Slack
# (Automated in pre_deadline_selection.py)
```

**Expected duration**: ~25 minutes total
**Manual steps**: Data validation, team submission to FPL website

---

## Troubleshooting

### "EventBus object has no attribute 'start'"
**Fix**: The event bus uses `connect()` not `start()` - but for simple runs, you don't need the event bus at all

### "No such table: draft_team"
**Fix**: Run database migrations or ensure database schema is up to date

### Manager taking forever / hanging
**Check**: It's generating predictions for 4 gameweeks - should complete in 15-20min
**Monitor**: Check `/tmp/ron_gw10_output.txt` for progress logs

### Pi out of memory
**Fix**: Use simplified press conference format instead of big five articles
**Check**: `process_press_conferences.py` uses only ~2MB RAM

---

## Files Created This Week (To Delete)

❌ `scripts/select_gw10_team.py` - GW-specific, not reusable
❌ `data/ron_gw10_announcement.txt` - Static text, should be dynamic
❌ `data/ron_gw10_team.json` - Output from wrong approach

✅ KEEP:
- `scripts/process_press_conferences.py` - Reusable for all GWs
- `scripts/test_news_memory.py` - Useful for testing
- `NEWS_PROCESSING_USAGE.md` - Documentation

---

## Automation (Future)

### Cron Job for Weekly Execution
```cron
# Run 6 hours before typical Saturday 13:30 deadline
30 7 * * 6 cd /home/jolyon/ron_clanker && venv/bin/python scripts/pre_deadline_selection.py >> logs/cron_deadline.log 2>&1
```

### Prerequisites
1. News files must be manually placed in `data/news_input/` before cron runs
2. FPL data collection should run first (separate cron job or manual)
3. Telegram notification should be configured for announcement delivery

---

---

## GW11 Critical Learnings - Data Processing Fixes

### 🚨 CRITICAL: YouTube Transcript Processing Was Broken

**Problem**: `intelligence/news_processor.py` was only processing first 3000 characters of YouTube transcripts (11% of content!)

**Impact**:
- Video 1 (28K chars): Found 5 players → Should have found 18 players
- Video 2 (26K chars): Found 8 players → Should have found 26 players

**Fix**: Added `_process_youtube_transcript_batched()` method in `news_processor.py`:
```python
def _process_youtube_transcript_batched(self, video_title: str, transcript: str, creator: str, video_url: str = None):
    BATCH_SIZE = 8000  # ~2000 tokens, safe for Haiku
    # Split into words for cleaner breaks
    words = transcript.split()
    batches = []
    current_batch = []
    current_length = 0

    for word in words:
        word_len = len(word) + 1
        if current_length + word_len > BATCH_SIZE and current_batch:
            batches.append(' '.join(current_batch))
            current_batch = [word]
            current_length = word_len
        else:
            current_batch.append(word)
            current_length += word_len

    if current_batch:
        batches.append(' '.join(current_batch))
```

**Modified**: `process_youtube_transcript()` to detect large transcripts and route to batched processing:
```python
if len(transcript) > 10000:
    logger.info(f"Large transcript ({len(transcript)} chars) - processing in batches")
    return self._process_youtube_transcript_batched(video_title, transcript, creator, video_url)
```

**Validation**: Always check transcript length and verify full processing:
```bash
# Check how many chars were processed
grep "Large transcript" logs/intelligence.log
```

---

### 🚨 CRITICAL: Newsletter Processing Was Truncating Content

**Problem**: `scripts/process_email_newsletter.py` was limiting content to 8000 characters

**Impact**: GW11 newsletter was 17,998 characters - only processing first 44%!

**Fix**: Removed truncation limit, let automatic batching handle it:
```python
# OLD CODE (WRONG):
# if len(text_content) > 8000:
#     text_content = text_content[:8000]

# NEW CODE (CORRECT):
intelligence = processor.process_news_article(
    title=subject,
    content=text_content,  # Full content - batching handled automatically
    source=f'Email: {eml_path.name}',
    url=None
)
```

**Result**: Extracted intelligence on 45 players from full 17,998 character newsletter

---

### ✅ Memory Management Success

**Challenge**: Previous GW11 attempt hung with load values >20, likely memory exhaustion

**Solution**: Full ML-based selection completed successfully with controlled memory:
- Duration: 20.4 minutes (1225 seconds)
- Peak memory: ~187MB
- No system hang or crash

**Key**: The batching improvements in news processing kept memory usage reasonable throughout

---

### 🔧 EventBus Fix (Already Documented)

**Issue**: `'EventBus' object has no attribute 'start'`

**Fix**: EventBus uses `connect()` not `start()` - but for simple runs, we don't need EventBus at all:
```python
# OLD (WRONG):
# event_bus = get_event_bus()
# await event_bus.start()

# NEW (CORRECT):
# Note: EventBus uses connect() not start() - but for simple runs, we don't need it
# event_bus = get_event_bus()
# await event_bus.connect()
```

**Already documented** in troubleshooting section above ✅

---

### ⚠️ Free Transfer Count Validation

**Issue**: Initial scripts showed Ron had 1 FT, then 2 FT - actual was 3 FT

**Fix**: Always verify transfer count from database before selection:
```bash
sqlite3 data/ron_clanker.db "
SELECT
    for_gameweek,
    free_transfers_available,
    transfers_made
FROM team_state
ORDER BY for_gameweek DESC
LIMIT 1;
"
```

**Lesson**: Don't assume - validate before every selection

---

### 🎯 Gabriel Benching Mistake (Form vs Fixtures)

**Critical Error**: Gabriel (11.0 form, 55 pts in last 5 GWs) was benched in favor of lower-performing players

**Why it happened**: ML model over-weighted fixtures, under-weighted recent form

**Fix**: ML system corrected in final run - Gabriel now starting

**Validation Check**: After team selection, always review starting XI against top form players:
```bash
sqlite3 data/ron_clanker.db "
SELECT
    p.web_name,
    p.form,
    p.element_type,
    dt.position,
    CASE WHEN dt.position <= 11 THEN 'Starting' ELSE 'Bench' END as status
FROM draft_team dt
JOIN players p ON dt.player_id = p.id
WHERE dt.for_gameweek = N
    AND CAST(p.form AS FLOAT) > 8.0
ORDER BY CAST(p.form AS FLOAT) DESC;
"
```

**Sanity check**: Players with form >8.0 should almost always start (unless injured/suspended)

---

### 📢 Announcement Generation - Personality Matters

**Issue**: Initial announcements were too concise, lacking Ron's character

**Fix**: Pass detailed reasoning context to `generate_team_announcement()`:
```python
announcement = ron.generate_team_announcement(
    gameweek=11,
    squad=squad,
    transfers=[],
    chip_used=None,
    free_transfers=3,
    bank=4.2,
    reasoning={
        'approach': '400 points off the pace - using international break to regroup',
        'key_differentials': ['Guéhi captain (Palace defense strong, differential)',
                              'Gabriel NOW STARTING - was benching 11.0 form like an idiot',
                              '3 FTs saved for break']
    }
)
```

**Result**: Authentic Ron voice with self-deprecation and tactical reasoning

**Confirmed**: Uses Claude Haiku 4.5 (verified in `ron_clanker/llm_banter.py:382`)

---

### 📝 Position Validation

**Issue**: João Pedro was initially listed as midfielder instead of forward in announcement

**Fix**: Cross-reference `element_type` from database when generating announcements:
- element_type 1 = GK
- element_type 2 = DEF
- element_type 3 = MID
- element_type 4 = FWD

**Validation**: Always verify announcement matches database `element_type`

---

### 🎯 Transfer Analysis - Context is Key

**Discovery**: ML system recommended Haaland → Woltemade (+19.1pts over 4 GWs)

**Ron's Decision**: No transfers, bank 3 FTs for international break

**Why**: 400 points off pace, needs bigger restructure not piecemeal changes

**Lesson**: Transfer optimizer provides recommendations, but manager considers broader context (league position, upcoming blank/double GWs, chip strategy)

---

### 🔄 Next Gameweek Improvements Needed

**Immediate (International Break)**:
1. Move Ron to larger system with more memory + GPU
2. Complete ML model retrain with clean data
3. Fix prediction issues (ron_clanker-105)
4. Consider fresh historical data from GW1 onwards

**Process Improvements**:
1. Add automated form vs bench sanity checks
2. Add transcript/newsletter length validation
3. Add position validation in announcement generation
4. Document expected memory/duration for each step

**Strategic**:
- Ron is 400 points off the pace - need aggressive differential strategy
- International break = perfect time for major overhaul
- All chips still available - need optimal timing plan

---

---

## GW13 Critical Learnings - ML Model & Database Sync Issues

### 🚨 CRITICAL: ML Model Predicting Nonsensical Values

**Problem**: ML predictions completely broken despite data collection working correctly
- Haaland (14 goals, home vs Leeds who conceded 22): Predicted 2.8 points ❌
- Model recommended transferring OUT Haaland for Woltemade
- Data was correct (Haaland stats: 1034 minutes, 14 goals, 104 total points)

**Impact**: Automated system would have made catastrophic transfer decision

**Root Cause**: ML model itself is broken, not data collection
- `data/database.py` `upsert_player()` was only updating 12 fields (missing goals, minutes, etc.) - FIXED
- Even with corrected data, predictions didn't regenerate properly
- Possible cached predictions or corrupted training data

**Manual Override Decision**: Ron manually overrode system:
- STARTED Haaland instead of benching him
- Applied TRIPLE CAPTAIN chip on Haaland vs Leeds (home)
- Team set manually before deadline

**BEADS ISSUE**: ron_clanker-109 (P0) - Investigate why predictions didn't update after data fix

---

### 🚨 CRITICAL: `current_team` Table Out of Sync

**Problem**: `current_team` table didn't reflect actual FPL team
- GW12 manual transfers (Burn/Gabriel → Virgil/Chalobah) made on FPL website
- Database still showed Burn/Gabriel in `current_team`
- `pre_deadline_selection.py` used wrong baseline team

**Impact**: First selection attempt showed impossible team (players not owned)

**Fix Applied**: Created `scripts/sync_current_team_gw12.py` to manually sync from FPL API data
- Ran `track_ron_team.py` to fetch actual team
- Manually updated `current_team` table with correct 15 players

**BEADS ISSUE**: ron_clanker-108 (P1) - Auto-sync current_team before each GW selection

**Prevention**: Always sync team before selection:
```bash
# STEP 1a: Sync current team from FPL API (CRITICAL - NEW STEP)
venv/bin/python scripts/track_ron_team.py

# Verify team is correct
sqlite3 data/ron_clanker.db "
SELECT p.web_name, ct.position
FROM current_team ct
JOIN players p ON ct.player_id = p.id
ORDER BY ct.position;
"
```

---

### 🚨 CRITICAL: `upsert_player()` Missing Critical Fields

**Problem**: `data/database.py` `upsert_player()` function only updating 12 fields
- Missing: minutes, goals_scored, assists, clean_sheets, goals_conceded, etc.
- Players like Haaland showed 0 goals, 0 minutes in database
- ML predictions based on incomplete/wrong data

**Fix Applied**: Updated `upsert_player()` to include all 35 player fields:
```python
def upsert_player(self, player_data: Dict[str, Any]) -> int:
    query = """
        INSERT INTO players (
            id, code, first_name, second_name, web_name, team_id,
            element_type, now_cost, selected_by_percent, form,
            points_per_game, total_points, minutes, goals_scored, assists,
            clean_sheets, goals_conceded, own_goals, penalties_saved,
            penalties_missed, yellow_cards, red_cards, saves, bonus, bps,
            status, news, chance_of_playing_next_round,
            influence, creativity, threat, ict_index,
            tackles, interceptions, clearances_blocks_interceptions, recoveries,
            updated_at
        ) VALUES (?, ?, ...)
        ON CONFLICT(id) DO UPDATE SET
            [all fields updated]
    """
```

**Verification**: After data collection, check key players have correct stats:
```bash
sqlite3 data/ron_clanker.db "
SELECT web_name, minutes, goals_scored, total_points
FROM players
WHERE web_name = 'Haaland';
"
# Should show: Haaland|1034|14|104 (or current values)
```

---

### ✅ Slack Notification Success (After Confusion)

**Problem**: Multiple failed attempts to post announcement
- Tried `post_to_slack()` - doesn't exist
- Tried `NotificationManager` - wrong class name
- Tried `NotificationService` with Discord embeds - wrong format (HTTP 400)
- Found Telegram scripts - user said "we don't use telegram"

**Solution**: Found `utils/notifications.py` with `NotificationService` class
- `.env` uses `SLACK_WEBHOOK_URL` not `WEBHOOK_URL`
- Slack uses simple JSON: `{"text": "..."}`
- Discord uses embeds format (different)

**Working Script**: `scripts/post_gw13_slack.py`
```python
from dotenv import load_dotenv
webhook_url = os.getenv('SLACK_WEBHOOK_URL')
payload = {"text": f"*Ron Clanker - GW13 Team Selection*\n\n{announcement}"}
response = requests.post(webhook_url, json=payload)
```

**Result**: Successfully posted to Slack ✅

---

### 📋 GW13 Updated Workflow (What Actually Ran)

```bash
# 1. Collect fresh FPL data
venv/bin/python scripts/collect_fpl_data.py

# 1a. SYNC CURRENT TEAM (CRITICAL NEW STEP)
venv/bin/python scripts/track_ron_team.py

# Verify current team is correct
sqlite3 data/ron_clanker.db "
SELECT p.web_name FROM current_team ct
JOIN players p ON ct.player_id = p.id
ORDER BY ct.position;
"

# 1b. Verify data quality (especially after upsert_player fix)
sqlite3 data/ron_clanker.db "
SELECT web_name, minutes, goals_scored, total_points
FROM players
WHERE web_name IN ('Haaland', 'Salah', 'Saka')
LIMIT 5;
"

# 2. Run team selection (EXPECTED TO FAIL if ML model still broken)
venv/bin/python scripts/pre_deadline_selection.py --gameweek 13

# 3. CRITICAL: Validate predictions manually if system recommends weird transfers
# If predictions look wrong (e.g., Haaland <5 xP at home):
#   - Check specific fixtures
#   - Apply manual override
#   - Create announcement manually

# 4. Manual override (GW13 only - due to broken ML)
# Created scripts/announce_gw13_manual.py with Ron's manual decision
# Saved announcement to data/ron_gw13_announcement.txt

# 5. Post announcement to Slack
venv/bin/python scripts/post_gw13_slack.py
```

**GW13 Final Decision**:
- NO TRANSFERS (banking FT)
- TRIPLE CAPTAIN on Haaland (home vs Leeds)
- Formation: 4-4-2
- Captain: Haaland (TC), Vice: Guéhi
- Manual override due to broken ML predictions

---

### 🔧 Files Created/Modified for GW13

**New Scripts**:
- `scripts/sync_current_team_gw12.py` - Manual team sync (one-time fix)
- `scripts/announce_gw13_manual.py` - Manual announcement generation
- `scripts/post_gw13_slack.py` - Slack posting with correct format

**Modified Files**:
- `data/database.py` - Fixed `upsert_player()` to include all 35 fields ✅

**Data Files**:
- `data/ron_gw13_announcement.txt` - Manual announcement
- `data/ron_gw13_team.json` - (if created)

---

### ⚠️ URGENT TODO Before GW14

1. **Fix ML Model** (ron_clanker-109 - P0):
   - Investigate why predictions didn't regenerate after data fix
   - Consider full model retrain with clean data
   - Add sanity checks: flag predictions <5 xP for premium players at home

2. **Auto-sync Current Team** (ron_clanker-108 - P1):
   - Add `track_ron_team.py` to pre-selection workflow
   - Sync `current_team` table before every selection
   - Validate 15 players match FPL website

3. **Add Prediction Validation**:
   - Add sanity checks to flag obviously wrong predictions
   - Alert if Haaland/Salah predicted <5 xP at home vs weak opponent
   - Manual review required if predictions flagged

4. **Test Full Workflow**:
   - Run complete workflow with fixed `upsert_player()`
   - Verify predictions regenerate correctly
   - Test on GW14 preparation

---

**Last Updated**: 2025-11-29 (Post-GW13 selection - MANUAL OVERRIDE)
**Next Review**: Before GW14 deadline (MUST fix ML model first)
**Status**: Critical ML model issues - system not fully autonomous ⚠️

**GW13 Team**: No transfers, TC Haaland (C), Guéhi (VC), 4-4-2 formation
**Critical Issues**: ML predictions broken, manual override required, auto-sync needed
