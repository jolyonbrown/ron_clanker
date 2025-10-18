# Gameweek Selection Logic - Ron Clanker

## How Ron Selects Teams

### Key Principle

**Ron ALWAYS selects his team for the NEXT (upcoming) gameweek, using data from ALL COMPLETED gameweeks up to and including the current one.**

## Current State (October 17th, 2025)

- **Current Gameweek**: 7 (Finished on Oct 3rd)
- **Target Gameweek**: 8 (Ron's first entry - upcoming)
- **Data Used**: GW1-7 INCLUSIVE (all completed gameweeks)
- **Purpose**: Predict player performance FOR GW8

## Terminology

### "Current Gameweek" vs "Target Gameweek"

| Term | Meaning | Current Value | Where It Appears |
|------|---------|---------------|------------------|
| **Current GW** | Latest completed/in-progress gameweek | 7 | Console logs, data fetching |
| **Target GW** | Gameweek Ron is selecting FOR | 8 | Team announcements, selections |

### Important Distinction

```
Current GW:  The gameweek that just finished or is in progress
Target GW:   The gameweek Ron is picking his team FOR (always current + 1)
```

## Announcement Format

### Header (ALWAYS uses Target GW)

```
GAMEWEEK 8 - RON'S TEAM SELECTION

Right lads, here's how we're lining up for Gameweek 8...
```

### Footer (Shows data range + target)

```
Generated: 2025-10-17 13:07:23
Using GW1-7 data for GW8 selection
System: Ron Clanker Autonomous FPL Manager v0.1
```

## Code Implementation

### In `scripts/select_gw8_squad.py`

```python
# Line 73: Get current gameweek from FPL API
current_gw = data['current_gameweek']['id']  # Returns 7

# Line 77: Set target (Ron's entry point)
target_gw = 8  # Explicitly set - Ron enters at GW8

# Line 79: Console message
print(f"✅ Using GW1-{current_gw} data to select team FOR GW{target_gw}")
# Output: "Using GW1-7 data to select team FOR GW8"
```

### In `agents/manager_agent_v2.py`

```python
# Line 509-511: Announcement generation
announcement = f"""GAMEWEEK {gameweek} - RON'S TEAM SELECTION

Right lads, here's how we're lining up for Gameweek {gameweek}...
"""
# When called with gameweek=8, outputs "GAMEWEEK 8"
```

## Data Analysis Flow

```
1. Fetch FPL API data
   └─> Get current_gw = 7 (latest completed gameweek)

2. Determine target
   └─> target_gw = 8 (Ron's first entry point)

3. Analyze player performance
   └─> Use GW1-7 data (all completed games)
   └─> Calculate: points, form, DC, xG, fixtures

4. Generate predictions
   └─> Predict performance FOR GW8
   └─> Rank players by value for GW8

5. Select team
   └─> Build optimal squad FOR GW8
   └─> Within £100m budget

6. Announce
   └─> "GAMEWEEK 8 - RON'S TEAM SELECTION"
   └─> "Using GW1-7 data for GW8 selection"
```

## Verification Script

Run this to confirm the logic:

```bash
venv/bin/python scripts/verify_gw_logic.py
```

**Expected output**:
```
CURRENT GAMEWEEK: 7 (Finished)
TARGET GAMEWEEK: 8 (Ron is picking his team for THIS gameweek)
DATA ANALYSIS PERIOD: GW1-7 INCLUSIVE
✅ LOGIC VERIFIED: Ron is selecting FOR GW8 using GW1-7 data
```

## Why This Matters

### Correct Understanding:

✅ **Current GW = 7**: This is the latest gameweek that has data
✅ **Target GW = 8**: This is the gameweek Ron is selecting FOR
✅ **Data Range = GW1-7**: All completed gameweeks used for analysis
✅ **Announcement = "GAMEWEEK 8"**: Team selection for upcoming gameweek

### Common Confusion:

❌ Seeing "Current GW: 7" in logs and thinking Ron is selecting for GW7
❌ Confusing "current" with "target"
❌ Thinking Ron should select for GW7 instead of GW8

### The Reality:

- **GW7 has already finished** (October 3rd deadline passed)
- **GW8 is upcoming** (Ron's first entry point)
- **You cannot pick a team for a finished gameweek**
- **Ron uses GW1-7 results to predict GW8 performance**

## Example Timeline

```
GW1-6:  Completed (Sep 14 - Sep 30)
  └─> Data available for analysis

GW7:    Finished (Oct 3rd deadline)
  └─> Latest results available
  └─> This is "current_gw" in the code

[October 17th - TODAY]
  └─> Ron analyzes GW1-7 data
  └─> Predicts GW8 performance
  └─> Selects team FOR GW8

GW8:    Upcoming (Ron's first gameweek)
  └─> Deadline: TBD
  └─> This is "target_gw" in the code
  └─> Team announcement says "GAMEWEEK 8"
```

## Console Output Clarification

### What You See in Console:

```bash
[2/6] Fetching latest FPL data...
  ✅ Current GW: 7
  ✅ Using GW1-7 data to select team FOR GW8
```

**Explanation**:
- "Current GW: 7" = Latest gameweek with data (just finished)
- "FOR GW8" = Ron is selecting his team for GW8 (next/upcoming)

### Team Announcement Always Says:

```
GAMEWEEK 8 - RON'S TEAM SELECTION

Right lads, here's how we're lining up for Gameweek 8...
```

**No confusion here** - announcement always uses TARGET gameweek (8), not CURRENT gameweek (7).

## Files to Check

Verify the announcements yourself:

```bash
# Main announcement (should say GAMEWEEK 8)
cat data/squads/gw8_team_announcement.txt | head -5

# Should output:
# GAMEWEEK 8 - RON'S TEAM SELECTION
#
# Right lads, here's how we're lining up for Gameweek 8...
```

## Summary

| Question | Answer |
|----------|--------|
| What gameweek is current? | GW7 (finished) |
| What gameweek is Ron selecting for? | GW8 (next/upcoming) |
| What data is used? | GW1-7 INCLUSIVE |
| What does announcement say? | "GAMEWEEK 8 - RON'S TEAM SELECTION" |
| Is the logic correct? | ✅ YES - verified |

## Still Seeing "GAMEWEEK 7"?

If you're seeing "GAMEWEEK 7" anywhere, check:

1. **Are you looking at console logs?**
   - Console mentions "Current GW: 7" (this is correct - just info)
   - But announcement still says "GAMEWEEK 8"

2. **Are you looking at an old file?**
   - Check file timestamps
   - Re-run selection to generate fresh announcement

3. **Are you looking at a different script's output?**
   - Only `select_gw8_squad.py` generates official announcement
   - Other scripts might mention GW7 when fetching data

4. **Verify yourself:**
   ```bash
   venv/bin/python scripts/verify_gw_logic.py
   cat data/squads/gw8_team_announcement.txt | head -3
   ```

---

**Last Updated**: October 17th, 2025
**Status**: ✅ All verification checks passed
**Confirmed**: Ron is selecting FOR GW8 using GW1-7 data
