# Session Notes - Ron Clanker Development

## Session: 2025-10-16 (Phase 1 Complete + Daily Monitoring)

### Summary
Completed Phase 1 foundation (9/9 issues), built daily monitoring system, discovered critical data integrity lesson with Isak transfer. System ready for GW8 entry.

---

## Key Accomplishments

### 1. Introduced Beads Issue Tracker
- Installed beads plugin for issue tracking
- Created 9 Phase 1 issues with dependency graphs
- ALL FUTURE PLANNING MUST USE BEADS (not markdown files)
- Commands: `bd create`, `bd ready`, `bd close`, `bd dep add`
- Issues stored in `.beads/issues.jsonl` (git committed)

### 2. Phase 1 Foundation - ALL COMPLETE (9/9 ✅)
- **Docker Infrastructure**: Redis + Postgres for event-driven architecture
- **Data Collection Agent (Maggie)**: Live FPL API integration, caching works
- **Rules Engine**: Team validation, DC scoring (defenders: 1pt/5 actions, mids: 1pt/6)
- **Player Valuation Agent**: DC specialist identification, value ranking
- **Manager Agent (Ron Clanker)**: Team selection, transfer logic, captain assignment
- **Database**: SQLite schema + 743 players, 20 teams, 380 fixtures synced
- **GW1-7 Analysis**: Identified DC specialists (Senesi £5.0m 9.2pts/£m, Guéhi £4.9m 9.4pts/£m)
- **GW8 Squad Built**: Valid 15 players, £99m/£100m (pending refinement before deadline)

### 3. Daily Monitoring System
- **Script**: `scripts/daily_monitor.py` detects price changes, injuries, squad impact
- **Cron Setup**: `scripts/setup_cron.sh` for 3 AM automation
- **Reports**: Saved to `data/daily_reports/report_YYYYMMDD.txt`
- **Documentation**: `DAILY_MONITORING.md` (user docs are OK, planning must be beads)

---

## Critical Learning - THE ISAK INCIDENT

**What Happened:**
I wrote GW8 announcement calling Isak "Newcastle's main goal threat" but user spotted error - Isak actually plays for Liverpool now (mid-season transfer). API data was CORRECT showing team_id=12 (Liverpool), I was working from outdated football knowledge.

**The Problem:**
- Isak at Liverpool: Only 8 points in 7 games at £10.6m = TERRIBLE value (0.75 pts/£m)
- Our squad included him based on flawed logic
- I mixed real-world knowledge with 2025/26 game data

**THE RULE GOING FORWARD:**
```
RON MUST ONLY WORK FROM API DATA
NO REAL-WORLD FOOTBALL KNOWLEDGE
IF API SAYS ISAK IS AT LIVERPOOL WITH 8 POINTS, THAT'S THE TRUTH
```

This is why pre-deadline optimizer (ron_clanker-11) is critical - need to rebuild squad from FRESH API data only.

---

## Current State

### Beads Status
```
Total Issues:  12
Closed:        9  (Phase 1)
Open:          3  (GW8 prep)
Ready:         2  (ron_clanker-10, ron_clanker-11)
Blocked:       1  (ron_clanker-12 waits on 11)
```

### Ready to Work (Tomorrow)
1. **ron_clanker-11** (P0): Build pre-deadline squad optimizer
   - Fetch latest API data (injuries, prices, news)
   - Rebuild optimal squad from scratch
   - FIX ISAK PROBLEM (replace with Watkins £8.7m/20pts or similar)
   - Validate all players available
   - Run 48hrs before GW8 deadline

2. **ron_clanker-10** (P1): Set up cron job
   - Run `./scripts/setup_cron.sh`
   - Verify daily monitoring runs at 3 AM
   - Check logs in `logs/daily_monitor.log`

### Blocked
- **ron_clanker-12**: Final GW8 squad selection + Ron's announcement
  - Depends on optimizer finishing
  - Will run 24-48hrs before deadline
  - Generates `data/squads/gw8_team_announcement.txt`

---

## Technical Context

### GW8 Entry Context
- **Current GW**: 7 (in progress)
- **Ron's Entry**: GW8 (fresh start, £100m budget)
- **Deadline**: ~2 days away (exact deadline in FPL API current_gameweek data)
- **Strategy**: Exploit DC (Defensive Contribution) rule inefficiency
  - 5 DC defenders + 3 DC midfielders = 16pt floor before goals/assists/clean sheets

### Squad Issues to Fix
- **Isak problem**: Liverpool, £10.6m, only 8 points = awful value
- **No premium mid**: Dropped Salah/Saka to fit Haaland + balanced squad
- **Need verification**: Check all players available (no injuries from internationals)

### Data Sources
- **FPL API**: `https://fantasy.premierleague.com/api/bootstrap-static/`
- **Database**: `data/ron_clanker.db` (743 players synced)
- **Daily Monitoring**: Tracks changes between syncs
- **Press conferences**: NOT automated (manual check Friday)

---

## Key Files

### Core Agents
- `agents/data_collector.py` - Maggie (FPL API client)
- `agents/rules_engine.py` - Validation, DC scoring
- `agents/player_valuation.py` - Value ranking, DC specialists
- `agents/manager.py` - Ron Clanker orchestrator

### Scripts
- `scripts/sync_fpl_data.py` - Initial DB population
- `scripts/daily_monitor.py` - Price changes, injuries, alerts
- `scripts/setup_cron.sh` - Automate daily monitoring
- `build_gw8_squad.py` - Initial squad builder (needs refinement)
- `analyze_gw1_7_dc_specialists.py` - DC analysis results

### Data
- `data/ron_clanker.db` - SQLite database
- `data/gw1_7_dc_analysis.json` - DC specialist analysis
- `data/gw8_squad.json` - Current squad (needs optimization)
- `data/daily_reports/` - Daily monitoring reports

### Documentation
- `CLAUDE.md` - Main project instructions (READ THIS FIRST)
- `SEASON_SITUATION.md` - GW8 entry context
- `DOCKER_SETUP.md` - Infrastructure setup
- `DAILY_MONITORING.md` - Daily monitoring user guide

---

## Important Decisions Made

1. **Beads for Planning**: All task tracking uses beads, no markdown TODO files
2. **Data Over Knowledge**: Ron works ONLY from API data, never real-world football knowledge
3. **Daily Monitoring**: Automated at 3 AM for price changes / injuries
4. **Press Conferences**: NOT automated (too complex), manual check if needed
5. **GW8 Timing**: Optimize 48hrs before deadline, finalize 24hrs before
6. **DC Strategy**: Foundation first - 8 players earning consistent DC points

---

## Tomorrow's Priorities

### Immediate (Before Deadline)
1. Build pre-deadline optimizer (ron_clanker-11)
2. Fix Isak issue with better value forward
3. Verify no injuries from internationals
4. Finalize squad and generate announcement

### Nice to Have
- Set up cron job for daily monitoring (ron_clanker-10)
- Test daily monitoring runs correctly

---

## Quotes to Remember

**On Data Integrity:**
> "VERY important for ron and the team to work from the data and not from knowledge and opinions you and I have"

**On Timing:**
> "Never announce early - injuries from internationals, press conferences, late team news. Ron should finalize the squad 24-48 hours before deadline, not now."

**On Planning:**
> "we should use the beads plugin and not markdown for all new work"

---

## Git Status
Branch: `feature/event-driven-architecture`
Recent commits:
- Complete Phase 1 foundation
- Database persistence + data sync
- Daily monitoring system
- Beads issues for GW8 prep

All work committed. Ready to pick up tomorrow with `bd ready`.

---

*Session ended: ~00:15 GMT, 2025-10-17*
*Next session: Pick up with ron_clanker-11 (optimizer) or ron_clanker-10 (cron)*
