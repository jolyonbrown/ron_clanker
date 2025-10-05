# Tracking Ron Clanker's FPL Team

## Overview

Once Ron's team is registered on the FPL website, we can track all performance data via the FPL API using `track_ron_team.py`.

---

## Setup

### 1. Register Ron's Team
- Go to https://fantasy.premierleague.com
- Create/join with Ron's team
- Note the team ID from the URL: `fantasy.premierleague.com/entry/{TEAM_ID}/event/X`

### 2. Configure Team ID

**Option A: Update config file (recommended)**
```bash
# Edit config/ron_config.json
{
  "team_id": 123456,  # Ron's actual team ID
  "team_name": "Two Points FC",
  "manager_name": "Ron Clanker",
  "season": "2025/26",
  "entry_gameweek": 8
}
```

**Option B: Use command line flag**
```bash
python scripts/track_ron_team.py --team-id 123456
```

---

## Usage

### Basic Tracking
```bash
# Track current gameweek (uses config team ID)
python scripts/track_ron_team.py

# Track specific team ID
python scripts/track_ron_team.py --team-id 123456

# Track specific gameweek
python scripts/track_ron_team.py --gameweek 8
```

### Detailed Analysis
```bash
# Verbose mode - shows player-by-player performance
python scripts/track_ron_team.py --verbose

# Save tracking data to file
python scripts/track_ron_team.py --save

# Combine options
python scripts/track_ron_team.py --team-id 123456 --gameweek 8 --verbose --save
```

---

## Output

### Team Overview
- Team name, manager details
- Overall points & rank
- Latest gameweek points & rank
- Team value & bank
- Chips used

### Gameweek History
- Last 10 gameweeks (or all if fewer)
- Points, rank progression
- Transfers made
- Points left on bench

### Squad Details
- 15 players with names, teams, prices
- Captain (C) and Vice-Captain (VC) marked
- Starting XI vs Bench
- Formation visible from positions

### Detailed Performance (--verbose)
- Player-by-player breakdown:
  - Minutes played
  - Points earned (including captain multiplier)
  - Goals, assists
  - Defensive Contribution points
  - Bonus points

### Transfer History
- All transfers made this season
- Player in/out with teams
- Gameweek when transfer made

---

## Data Available from FPL API

### ✅ What We Can Track

**Team Level:**
- Overall rank & points
- Gameweek rank & points
- Team value progression
- Bank balance
- Transfer history (all transfers)
- Chips used (which chip, which GW)

**Squad Level:**
- 15 players (by name, team, position, price)
- Captain & vice-captain
- Starting XI vs bench
- Formation
- Automatic substitutions

**Player Level (per gameweek):**
- Minutes played
- Points scored
- Goals, assists
- Defensive Contribution
- Bonus points
- Clean sheets
- All detailed stats (xG, xA, ICT, etc.)

### ❌ What's NOT Available
- Live in-game updates (only post-match)
- Predicted points (we calculate these separately)
- Private league rankings (unless league ID known)
- Draft team decisions (this is a standard team)

---

## Typical Workflow

### During Gameweek (Saturday/Sunday)
```bash
# Quick check on current performance
python scripts/track_ron_team.py

# Watch live (manual refresh)
watch -n 300 python scripts/track_ron_team.py
```

### Post-Gameweek (Monday)
```bash
# Full analysis with player details
python scripts/track_ron_team.py --verbose --save

# Compare to our predictions
python scripts/analyze_gw_results.py --gw 8

# Staff meeting report
python scripts/staff_meeting_report.py --gw 8
```

### Mid-Week Planning
```bash
# Check current squad status
python scripts/track_ron_team.py

# Check player availability
python scripts/check_squad_availability.py --squad gw8

# Plan transfers
python scripts/analyze_transfer_targets.py --gw 9
```

---

## Integration with Other Scripts

### GW Results Analysis
`analyze_gw_results.py` can fetch actual team data automatically:
```bash
# Will use Ron's team ID from config
python scripts/analyze_gw_results.py --gw 8
```

### Live Tracking
`track_gameweek_live.py` for real-time monitoring:
```bash
# Watch Ron's team live during gameweek
python scripts/track_gameweek_live.py --gw 8 --watch
```

### Staff Meeting Report
`staff_meeting_report.py` incorporates actual data:
```bash
# Generate Monday morning staff meeting with real results
python scripts/staff_meeting_report.py --gw 8
```

---

## Saved Data

When using `--save` flag, tracking data is saved to:
```
data/ron_tracking/ron_team_gw{X}_{timestamp}.json
```

Contains full API responses:
- Entry data (team overview)
- History data (all gameweeks)
- Picks data (squad for this GW)
- Transfers data (all transfers)

Useful for:
- Historical analysis
- Debugging
- Building training datasets for ML models
- Season review

---

## Examples

### Example 1: Check Ron's GW8 Performance
```bash
python scripts/track_ron_team.py --gameweek 8 --verbose
```

Output shows:
- Ron scored 73 points in GW8
- Haaland (C) delivered 24 points
- DC specialists: Gabriel (6), Caicedo (7), Garner (5)
- Overall rank: 2,156,789
- No chips used

### Example 2: Save Full Season Data
```bash
# Loop through all gameweeks
for gw in {8..38}; do
  python scripts/track_ron_team.py --gameweek $gw --save
done
```

Creates 31 JSON files with complete season history.

### Example 3: Compare to Template
```bash
# Get Ron's data
python scripts/track_ron_team.py --gameweek 8 --save

# Compare to average (from FPL API)
python scripts/compare_to_average.py --gw 8
```

Shows:
- Ron: 73 points, Rank 2.1M
- Average: 58 points
- Beat average by: +15 points (+26%)
- DC strategy premium: +12 points from DC alone

---

## Troubleshooting

### "No team ID available"
- Ron's team not yet registered
- Update `config/ron_config.json` with team_id
- Or use `--team-id` flag

### "Team ID not found"
- Check team ID is correct
- Verify team exists on FPL website
- API may be temporarily down

### "No picks data available for GW X"
- Gameweek hasn't started yet
- Gameweek deadline not passed
- Team wasn't registered for that GW

### Rate limiting
- FPL API has rate limits
- Add delays between requests if fetching bulk data
- Use saved data when possible

---

## Next Steps

Once Ron's team is registered (post-GW8 deadline), we can:

1. **Automate Tracking**: Set up cron job for daily updates
2. **Build Dashboards**: Visualize performance trends
3. **ML Training**: Use actual data to train prediction models
4. **Comparison Analysis**: Ron vs template, Ron vs rivals
5. **Season Review**: End-of-season comprehensive analysis

---

**Status**: Ready to use once Ron's team is registered
**Team ID**: TBD (update config/ron_config.json)
**Entry Gameweek**: GW8
**Season**: 2025/26
