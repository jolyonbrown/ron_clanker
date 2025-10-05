# Pre-Deadline Optimizer
## Ron's Weekly Decision Engine

The pre-deadline optimizer is Ron's core weekly decision tool, used 24-48 hours before each gameweek deadline to make final squad decisions.

---

## Overview

**Purpose**: Re-analyze all data with latest information and provide optimized recommendations for:
- Squad selection (fresh start) or squad validation (standard mode)
- Transfer decisions (GW9+)
- Captain & vice-captain selection
- Formation & bench order

**Reusable**: Same script works for every gameweek throughout the season.

---

## Two Modes

### 1. Fresh Start Mode (GW8 Only)

For Ron's entry gameweek with full £100m budget.

```bash
python scripts/pre_deadline_optimizer.py --gw 8 --fresh-start
```

**What it does:**
- ✅ Analyzes all 743 players with latest data
- ✅ Selects best 15 within £100m budget
- ✅ Prioritizes DC specialists (70%+ consistency)
- ✅ Includes premium attackers (Haaland, etc.)
- ✅ Validates against 3-per-team rule
- ✅ Optimizes value (points per £m)
- ✅ Selects captain & vice-captain
- ✅ Sets formation (3-5-2 default)
- ✅ Orders bench for auto-subs

### 2. Standard Mode (GW9-38)

For weekly optimization with transfers.

```bash
python scripts/pre_deadline_optimizer.py --gw 9
```

**What it does:**
- ✅ Loads current squad from latest squad file
- ✅ Checks all players for injuries/suspensions
- ✅ Analyzes transfer opportunities
- ✅ Calculates expected value of transfers
- ✅ Recommends hits (-4pts) if worth it
- ✅ Plans multi-week transfers
- ✅ Optimizes captain selection
- ✅ Adjusts formation if needed

---

## Usage

### Basic Commands

```bash
# GW8 - Fresh start
python scripts/pre_deadline_optimizer.py --gw 8 --fresh-start

# GW9+ - Standard weekly optimization
python scripts/pre_deadline_optimizer.py --gw 9

# Save recommendations to file
python scripts/pre_deadline_optimizer.py --gw 8 --fresh-start --save

# Verbose output
python scripts/pre_deadline_optimizer.py --gw 9 --verbose
```

### Advanced Options

```bash
# Override free transfers (if you know you have 2)
python scripts/pre_deadline_optimizer.py --gw 10 --free-transfers 2

# Override budget (in millions)
python scripts/pre_deadline_optimizer.py --gw 9 --budget 2.5

# Combine options
python scripts/pre_deadline_optimizer.py --gw 12 --free-transfers 2 --budget 3.0 --save
```

---

## Output

### 1. Availability Check
Shows any squad players with injury/suspension flags:
```
================================================================================
AVAILABILITY CHECK
================================================================================

Checking 15 players...
⚠️  CONCERN: Gabriel (ARS) - 75% chance of playing
✅ All other players available
```

### 2. Squad Selection (Fresh Start)
Best 15 players selected:
```
================================================================================
FRESH START OPTIMIZATION - GW8
================================================================================

Selected 13 DC specialists - foundation secured
Total cost: £89.4m
Remaining: £10.6m

STARTING XI (3-5-2):
  GKP: Dúbravka (BUR) £4.0m
  DEF: Guéhi, Alderete, Mukiele
  MID: Semenyo, Anthony, Caicedo, Sarr, Gravenberch
  FWD: Haaland (C), Thiago
```

### 3. Transfer Recommendations (Standard Mode)
*Phase 3 feature - coming soon*
```
TRANSFER RECOMMENDATIONS:
  OUT: Player X (poor fixtures, form drop)
  IN:  Player Y (fixture swing, rising)
  Expected gain: +6 pts over 3 GWs
  Hit cost: -4 pts
  Net gain: +2 pts
  Recommendation: MAKE TRANSFER
```

### 4. Captain Selection
Data-driven captain choice:
```
🔴 CAPTAIN: Haaland (MCI)
   Form: 10.3 PPG
   Fixture: vs EVE (H)
   Ownership: 78%

🟡 VICE-CAPTAIN: Semenyo (BOU)
   Form: 9.4 PPG
   Fixture: vs CRY (H)
   Differential: 12% owned
```

### 5. Ron's Commentary
The Gaffer's verdict:
```
Right, GW8. Fresh start. Here's the plan:

Selected 13 DC specialists - that's our foundation.
Total squad cost: £89.4m
Budget remaining: £10.6m

Formation: 3-5-2

Captain: Haaland - best form in the squad.

Strategy: Let everyone else chase goals. We're banking DC points
every week. Steady. Reliable. That's how you win marathons.
```

---

## Data Sources

### Loaded Automatically:
1. **FPL API bootstrap-static** - Latest player data, prices, status
2. **Pre-computed analysis** - `data/analysis/player_analysis_gw*.json`
3. **Current squad** - `data/squads/gw*_squad.json` (standard mode)
4. **Team API data** - If team_id configured (future)

### Uses When Available:
- Player injury/availability status
- Latest price changes
- Form updates
- xG, xA, DC statistics
- Fixture difficulty

---

## Weekly Workflow

### Tuesday (4 days to deadline)
```bash
# Initial analysis
python scripts/pre_deadline_optimizer.py --gw 9 --save

# Review recommendations
# Identify potential transfers
# Start monitoring price changes
```

### Thursday (2 days to deadline)
```bash
# Refresh with latest data
python scripts/pre_deadline_optimizer.py --gw 9 --save

# Check if recommendations changed
# Monitor injury news
```

### Friday (1 day to deadline)
```bash
# Final check after team news
python scripts/pre_deadline_optimizer.py --gw 9 --save

# Make decision on transfers
# Prepare to execute Saturday AM
```

### Saturday Morning (Deadline day)
```bash
# Last-minute validation
python scripts/pre_deadline_optimizer.py --gw 9

# Execute transfers on FPL website
# Set captain & formation
# Lock in team before deadline
```

---

## Integration with Other Scripts

### Feeds From:
- `analyze_player_performance.py` - Player analysis data
- `check_squad_availability.py` - Injury status
- `track_ron_team.py` - Current squad state (GW9+)

### Feeds Into:
- Squad files saved for tracking
- Transfer decisions logged
- Captain choices recorded
- Formation history

### Will Integrate (Phase 3):
- `analyze_transfer_targets.py` - Transfer recommendations
- `select_captain.py` - Advanced captain optimization
- `monitor_price_changes.py` - Timing transfer execution
- `analyze_fixtures.py` - Multi-week planning

---

## Saved Output

When using `--save` flag, creates:
```
data/pre_deadline_reports/gw{X}_recommendations_{timestamp}.json
```

Contains:
```json
{
  "gameweek": 8,
  "timestamp": "2025-10-05T20:49:28",
  "mode": "fresh_start",
  "availability_issues": [...],
  "squad_selection": {
    "squad": {...},
    "total_cost": 89.4,
    "remaining_budget": 10.6,
    "dc_count": 13
  },
  "captain": {...},
  "formation": {...}
}
```

---

## Algorithm Details

### Fresh Start Squad Selection

**Strategy**:
1. Select 2 cheapest GKPs (maximize budget for outfield)
2. Select 3-4 top DC defenders (70%+ consistency)
3. Fill remaining DEF slots with value picks
4. Select 3-4 top DC midfielders
5. Add premium/attacking mids for ceiling
6. Select 1 premium forward (Haaland preferred)
7. Fill remaining FWD with budget options

**Constraints**:
- Total cost ≤ £100m
- Exactly 2 GKP, 5 DEF, 5 MID, 3 FWD
- Max 3 players per team
- All players status = 'a' (available)

**Optimization Metric**:
- Value score = Points per game / Price
- DC specialists prioritized (guaranteed floor)
- Balance between floor (DC) and ceiling (premiums)

### Transfer Analysis (GW9+)

*Coming in Phase 3*

**Will consider**:
- Expected points next 3-6 GWs
- Fixture difficulty
- Price changes (maximize team value)
- Form trends
- Ownership (template vs differential)

**Decision criteria**:
- Only take -4 hit if expected gain > 6 pts over 3 GWs
- Plan transfers around fixture swings
- Bank transfers when no clear moves (max 5)

---

## Current Limitations

### What Works Now:
✅ Fresh start squad selection
✅ Availability checking
✅ Basic captain selection (by form)
✅ Formation optimization
✅ Ron's commentary

### Phase 3 Additions:
⏳ Transfer recommendations
⏳ Advanced captain selection (fixtures, xG, ownership)
⏳ Multi-week transfer planning
⏳ Hit calculation (expected value)
⏳ Fixture-based formation changes
⏳ Chip strategy integration

---

## Examples

### Example 1: GW8 Fresh Start
```bash
$ python scripts/pre_deadline_optimizer.py --gw 8 --fresh-start --save

Output:
- 15-player squad selected (13 DC specialists)
- £89.4m spent, £10.6m remaining
- Haaland captain, Semenyo vice
- 3-5-2 formation
- Saved to gw8_recommendations_*.json
```

### Example 2: GW9 Weekly Check
```bash
$ python scripts/pre_deadline_optimizer.py --gw 9

Output:
- Current squad loaded (15 players)
- 2 availability concerns flagged (Gabriel 75%, Haaland minor)
- Transfer analysis: No clear moves this week
- Captain: Haaland (best fixture)
- Recommendation: Hold transfers, monitor team news
```

### Example 3: GW12 with 2 Free Transfers
```bash
$ python scripts/pre_deadline_optimizer.py --gw 12 --free-transfers 2 --save

Output:
- 2 FT available (confirmed)
- Identified fixture swing for 2 players
- Recommended transfers:
  OUT: Player A (bad fixtures GW12-15)
  OUT: Player B (injury concern)
  IN: Player C (fixture swing)
  IN: Player D (form + fixtures)
- Expected gain: +8 pts over 4 GWs
- Execute both transfers
```

---

## Tips

### Best Practices:
1. **Run Early**: Tuesday/Wednesday to spot trends
2. **Run Often**: Daily as deadline approaches
3. **Save Output**: Track how recommendations evolve
4. **Check Diffs**: Compare Tuesday vs Friday recommendations
5. **Validate Manually**: Ron's gut + data = best decisions

### Common Issues:
- **"No squad file found"**: Normal for GW8, use --fresh-start
- **"Budget: None"**: Squad file missing budget info, use --budget flag
- **Different squad vs manual selection**: Algorithm is aggressive on DC, may differ from gut feel

### When to Override Algorithm:
- Team news breaks late (player suddenly ruled out)
- Gut feeling on differential captain
- Price changes force different picks
- Fixture postponement announced

---

## Future Enhancements

**Phase 3 (Transfer Strategy)**:
- Full transfer recommendation engine
- Multi-week planning
- Price change integration
- Hit calculation logic

**Phase 4 (Chip Strategy)**:
- Wildcard timing recommendations
- Bench Boost optimal GWs
- Triple Captain best fixtures
- Free Hit blank/DGW planning

**Phase 5 (ML Integration)**:
- ML-based xPts predictions
- Captain selection neural network
- Transfer EV calculation
- Formation optimization model

---

**Status**: Phase 2 Complete
**Next**: Phase 3 Transfer Strategy
**Ready for**: GW8 fresh start & GW9+ weekly use

---

*"Trust the process. Trust the data. But never forget - football's played by humans, not spreadsheets. The optimizer gives you the facts. Your gut makes the call."* - Ron Clanker
