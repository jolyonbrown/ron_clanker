# Ron Clanker Scripts Guide

## Analysis Scripts

### 1. `analyze_player_performance.py` - Comprehensive Generic Analysis ⭐ RECOMMENDED

**Purpose**: Generic, reusable player analysis using ALL available FPL stats

**Stats Analyzed**:
- ✅ Defensive Contribution (DC) - tackles, CBI, recoveries
- ✅ Expected Goals (xG) and Expected Assists (xA)
- ✅ Expected Goals Conceded (xGC) - for defenders/keepers
- ✅ ICT Index (Influence, Creativity, Threat)
- ✅ Bonus Points System (BPS)
- ✅ Form and consistency metrics
- ✅ Value metrics (points per £m, xGI per £m)
- ✅ Ownership and transfer trends

**Usage**:
```bash
# Analyze current season data (auto-detects current GW)
python scripts/analyze_player_performance.py

# Analyze specific gameweek range
python scripts/analyze_player_performance.py --start-gw 1 --end-gw 10

# Test with sample (100 players)
python scripts/analyze_player_performance.py --start-gw 1 --end-gw 7 --sample 100

# Custom output directory
python scripts/analyze_player_performance.py --output data/analysis/october

# Set minimum games for rankings
python scripts/analyze_player_performance.py --min-games 5
```

**Output Files** (in `--output` dir, default `data/analysis/`):
- `player_analysis_gw{X}-{Y}.json` - Full detailed stats for all players
- `rankings_gw{X}-{Y}.json` - All ranking lists
- `recommendations_gw{X}-{Y}.json` - Curated picks for squad selection

**Rankings Generated**:
- Defenders by DC consistency
- Defenders by clean sheet potential (xGC + CS%)
- Defenders by value
- Midfielders by xGI (expected goal involvement)
- Midfielders by DC consistency
- Forwards by xG
- Goalkeepers by saves and clean sheets
- Elite DC performers (80%+ consistency)
- Best value overall
- Most consistent scorers
- Elite finishers (xG overperformance)
- Differential picks (<10% ownership)

**Use This For**:
- Regular season analysis (any gameweek)
- Identifying transfer targets
- Comparing players across multiple metrics
- Finding differentials and value picks

---

### 2. `analyze_dc_performers.py` - DC-Focused Analysis (Legacy)

**Purpose**: Original script focused specifically on Defensive Contribution

**Stats Analyzed**:
- ✅ DC consistency
- ✅ DC points per £m
- ✅ Average tackles, CBI, recoveries

**Usage**:
```bash
# Full analysis
python scripts/analyze_dc_performers.py

# Sample mode (100 players for testing)
python scripts/analyze_dc_performers.py --sample
```

**Output Files**:
- `data/analysis/dc_analysis_gw1-7.json`
- `data/analysis/dc_rankings_gw1-7.json`
- `data/analysis/gw8_dc_recommendations.json`

**Use This For**:
- Quick DC-only analysis
- Validating the comprehensive script's DC calculations
- Legacy compatibility with GW8 initial selection

**Note**: This is the original script built yesterday. The comprehensive script above is more powerful and should be used going forward.

---

## Squad Selection Scripts

### 3. `select_gw8_squad.py` - GW8 Initial Team Selection

**Purpose**: Select Ron's initial 15-player squad for Gameweek 8 (fresh £100m start)

**Features**:
- Uses DC analysis recommendations
- Fetches GW8 fixtures
- Optimizes £100m budget
- Applies Ron's tactical philosophy (DC-focused)
- Generates team announcement in Ron's voice

**Usage**:
```bash
# Requires DC analysis to be run first
python scripts/analyze_dc_performers.py
python scripts/select_gw8_squad.py
```

**Output Files**:
- `data/squads/gw8_squad.json` - Squad details
- `data/squads/gw8_team_announcement.txt` - Ron's announcement

**Use This For**:
- Initial GW8 team selection (2025/26 season)
- Seeing Ron's tactical philosophy in action

**Note**: This is season-specific. For future seasons starting at GW1, we'll create a similar `select_initial_squad.py`.

---

## Recommended Workflow

### For Initial Team Selection (GW8 2025/26):

```bash
# Step 1: Run comprehensive analysis on GW1-7 data
python scripts/analyze_player_performance.py --start-gw 1 --end-gw 7

# Step 2: Select GW8 squad using analysis
python scripts/select_gw8_squad.py

# Step 3: Review Ron's team announcement
cat data/squads/gw8_team_announcement.txt
```

### For Weekly Analysis (ongoing):

```bash
# Analyze recent gameweeks to identify form players
python scripts/analyze_player_performance.py --start-gw 5 --end-gw 12

# Look at differential picks
grep -A 20 "DIFFERENTIAL PICKS" <output>

# Check value rankings for budget players
grep -A 20 "BEST VALUE" <output>
```

### For Transfer Planning:

```bash
# Analyze last 5 gameweeks for current form
python scripts/analyze_player_performance.py --start-gw 8 --end-gw 12 --min-games 3

# Compare to season-long data
python scripts/analyze_player_performance.py --start-gw 1 --end-gw 12

# Review xG/xA trends to find players due returns
# Check xg_overperformance (negative = unlucky, could regress positively)
```

---

## Future Scripts (To Be Built)

### Phase 2+:
- `select_transfers.py` - Weekly transfer optimization
- `optimize_captain.py` - Captain selection using fixtures + form
- `plan_chip_strategy.py` - Wildcard/BB/TC/FH timing
- `simulate_gameweek.py` - Monte Carlo simulation of GW outcomes
- `compare_squads.py` - Compare Ron's team vs template/rivals

---

## Data Files Structure

```
data/
├── analysis/
│   ├── player_analysis_gw1-7.json       # Full comprehensive data
│   ├── rankings_gw1-7.json              # All rankings
│   ├── recommendations_gw1-7.json       # Curated picks for selection
│   ├── dc_analysis_gw1-7.json          # Legacy DC-only data
│   └── dc_rankings_gw1-7.json          # Legacy DC rankings
│
└── squads/
    ├── gw8_squad.json                   # GW8 team selection
    └── gw8_team_announcement.txt        # Ron's announcement
```

---

## Key Metrics Explained

### Defensive Contribution (DC)
- **2 points** awarded if player hits threshold:
  - Defenders: 10+ tackles + CBI
  - Midfielders: 12+ tackles + CBI + recoveries
- **dc_consistency_pct**: % of games played where DC earned
- **Elite threshold**: 80%+ consistency

### Expected Stats (xG, xA, xGC)
- **xG**: Quality of shooting chances (higher = better)
- **xA**: Quality of passing chances created
- **xGI**: xG + xA (total goal involvement)
- **xGC**: Expected goals conceded (lower = better defense)

### Overperformance Metrics
- **xg_overperformance**: Actual goals - xG
  - Positive = elite finisher (Haaland, Salah)
  - Negative = unlucky (could regress positively)
- **xgc_overperformance**: xGC - actual goals conceded
  - Positive = defense/keeper performing well

### Value Metrics
- **points_per_million**: Total FPL points / price
- **xgi_per_million**: Expected goal involvement / price
- Higher = better value

### Form & Consistency
- **avg_points_per_gw**: Average points per game played
- **points_variance**: Lower = more consistent
- **return_pct**: % of games with goal or assist

---

## Tips for Using Analysis Data

1. **Combine Multiple Metrics**: Don't rely on one stat alone
   - DC consistency + xGI = elite midfielder
   - xGC + clean sheet % = reliable defender
   - xG + xG overperformance = proven finisher

2. **Consider Sample Size**:
   - Minimum 3 games for meaningful stats
   - 5+ games for reliable trends
   - Season-long (10+ games) for true quality

3. **Balance Present and Future**:
   - Recent form (last 3-5 GW) = current hot streak
   - Season-long = underlying quality
   - Fixture run = future potential

4. **Value Sweet Spots**:
   - Budget defenders (£4.5-5.5m) with high DC%
   - Mid-priced mids (£5.5-7.0m) with high xGI
   - Premium forwards (£10m+) with elite xG

5. **Differential Strategy**:
   - <10% ownership
   - Points per £m > 4.0
   - Upcoming good fixtures
   - Recent xG/xA suggests returns coming

---

**Last Updated**: Oct 5, 2025
**Season**: 2025/26
**Status**: Phase 1 Complete, Enhanced Analytics Added
