# Multi-Gameweek Strategic Planning

Ron Clanker's strategic planning system for thinking 4-6 gameweeks ahead.

## Overview

The Multi-GW Planning system helps Ron make strategic decisions by analyzing:
- **Fixture runs**: Which teams have good/bad upcoming schedules
- **Transfer sequences**: Plan multi-week transfer strategies
- **Chip timing**: When to use Wildcard, Bench Boost, Triple Captain, Free Hit
- **Budget management**: Track team value growth and price change opportunities

## Quick Usage

### Quick Summary (Daily)
```bash
python scripts/plan_multi_gameweeks.py --gw 8 --quick
```

**Output:**
- Key message for the day
- Best fixtures next 3 GWs
- Transfer action recommendation
- Urgent chip deadlines
- Price fall alerts

**Example:**
```
RON'S QUICK SUMMARY - GW8

Key Message: Bank transfer for 2 FT next week
Best Fixtures (next 3 GWs): Leeds, Wolves, Arsenal
Transfer Action: Bank Transfer
```

### Full Strategic Plan
```bash
python scripts/plan_multi_gameweeks.py --gw 8 --horizon 6 --save
```

**Output includes:**
1. **Key Recommendations** - Top 5 priority actions
2. **Fixture Analysis** - Best runs, fixture swings (improving/worsening)
3. **Transfer Strategy** - Who to move out, when to take hits
4. **Chip Strategy** - Optimal timing for each chip
5. **Budget & Team Value** - Price targets, value growth projection

### Save Reports
```bash
python scripts/plan_multi_gameweeks.py --gw 8 --horizon 6 --save
```

Saves to `reports/strategic_plans/`:
- Text report: `strategic_plan_gw8_YYYYMMDD_HHMMSS.txt`
- JSON data: `strategic_plan_gw8_YYYYMMDD_HHMMSS.json`

## System Components

### 1. Fixture Analyzer (`planning/fixture_analyzer.py`)

**Purpose**: Analyze upcoming fixture difficulty 3-6 weeks ahead

**Key Features:**
- `find_best_fixture_runs()` - Teams with easiest upcoming schedules
- `identify_fixture_swings()` - Teams whose difficulty changes significantly
- `get_player_fixture_rating()` - Position-aware fixture difficulty

**Example Insight:**
```
Fixture Swings - Improving:
  • Wolves: 4.0 → 2.3 (bring in around GW9)
  • Leeds: 3.7 → 2.0 (bring in around GW10)
```

### 2. Transfer Sequencer (`planning/transfer_sequencer.py`)

**Purpose**: Plan multi-transfer strategies over several gameweeks

**Key Features:**
- `plan_transfer_sequence()` - Optimize transfer timing over 4-6 GWs
- `evaluate_hit_decision()` - Calculate if -4 hit is worth it
- `identify_transfer_priorities()` - Flag injured/underperforming players
- `recommend_transfer_strategy()` - Overall transfer action

**Decision Logic:**
- Only take -4 hit if expected gain > 4 points over next 3 GWs
- Bank transfers when no urgent needs (build to 2 FT)
- Consider wildcard if 3+ urgent transfers needed

### 3. Chip Optimizer (`planning/chip_optimizer.py`)

**Purpose**: Identify optimal timing for FPL chips

**2025/26 Rules:**
- TWO of each chip (first/second half)
- Must use first half chips by GW19 deadline
- Second half chips available GW20-38

**Chip Strategies:**

**Wildcard:**
- First half: GW3-5 (early template break) or GW10-15 (mid-season pivot)
- Second half: Before DGWs or final run-in (GW32-34)

**Bench Boost:**
- Wait for Double Gameweeks (DGW)
- Best when all 15 players playing twice

**Triple Captain:**
- DGWs on premium players (Haaland/Salah)
- Or best single fixture for premium

**Free Hit:**
- Blank Gameweeks (BGW) when many teams don't play
- Strategic one-week punt

### 4. Budget Tracker (`planning/budget_tracker.py`)

**Purpose**: Monitor team value and price change opportunities

**Key Features:**
- `get_current_budget_status()` - Team value, selling value, profit
- `identify_price_rise_targets()` - Players likely to rise soon
- `identify_price_fall_risks()` - Owned players about to fall
- `calculate_value_growth_opportunity()` - Projected value growth

**FPL Selling Rules:**
- Selling value = purchase price + (profit / 2) rounded down
- Example: Bought at 10.0m, now 10.4m → Sell for 10.2m

### 5. Multi-GW Planner (`planning/multi_gw_planner.py`)

**Purpose**: Main orchestrator combining all planning modules

**Main Method:**
```python
plan = planner.generate_strategic_plan(current_gw=8, planning_horizon=6)
```

**Returns:**
- `fixtures`: Best runs, swings, teams to target/avoid
- `transfers`: Strategy, priorities, targets in/out
- `chips`: Available chips, recommendations, optimal timing
- `budget`: Current status, price targets, value growth
- `recommendations`: Top 5 prioritized actions

## Integration with Ron's Workflow

### Pre-Deadline (6 hours before)
1. Run full strategic plan: `--gw X --horizon 6`
2. Review key recommendations
3. Check transfer strategy (use FTs or take hit?)
4. Verify chip timing (use this week or save?)
5. Make final decisions

### Daily (Morning)
1. Run quick summary: `--gw X --quick`
2. Check for price fall alerts
3. Note upcoming fixture swings
4. Monitor chip urgency

### Weekly (Monday after GW)
1. Review how plan performed
2. Adjust future strategy based on results
3. Update longer-term targets

## Example: Full Strategic Plan Output

```
================================================================================
RON CLANKER'S STRATEGIC PLAN: GW8-13
================================================================================

KEY RECOMMENDATIONS
--------------------------------------------------------------------------------

1. [HIGH] Make 1 transfer(s)
   1 high-priority transfers available, use FTs
   Target: GW8

2. [MEDIUM] Plan Triple Captain
   GW10 DGW - triple captain on premium (Haaland/Salah) in DGW
   Optimal: GW10

3. [MEDIUM] Target players from: Leeds, Wolves, Arsenal
   These teams have best upcoming fixtures
   Period: GW8-13

FIXTURE ANALYSIS
--------------------------------------------------------------------------------

Teams with Best Fixtures:
  1. Leeds: Avg difficulty 2.2 (target)
  2. Wolves: Avg difficulty 2.3 (target)
  3. Arsenal: Avg difficulty 2.5 (target)

Fixture Swings - Improving:
  • Wolves: 4.0 → 2.3 (bring in around GW9)

TRANSFER STRATEGY
--------------------------------------------------------------------------------

1 high-priority transfers available, use FTs

Transfer Priorities:
  • Saliba (Priority 2: Poor form (1.8))

CHIP STRATEGY
--------------------------------------------------------------------------------

Available Chips: wildcard, bench_boost, triple_captain, free_hit
Priority Chip: triple_captain

Recommendations:

  🟡 Triple Captain
    GW10 DGW - triple captain on premium (Haaland/Salah) in DGW
    Optimal: GW10

BUDGET & TEAM VALUE
--------------------------------------------------------------------------------

Current Team Value: £99.9m
Total Budget: £99.7m
Profit: £0.4m

Projected Growth (GW8-13):
  Current: £99.9m
  Projected: £100.3m
  Expected gain: £0.4m

================================================================================
```

## Tips for Using Multi-GW Planning

1. **Think Ahead**: Don't just react to last gameweek - plan 4-6 weeks out

2. **Fixture Swings**: Time transfers for when fixtures turn (e.g., bring in Wolves before GW9)

3. **Bank vs Use FTs**: Only use transfers if urgent. Otherwise bank for 2 FT next week.

4. **Hit Threshold**: Only take -4 if expected gain > 4 points over next 3 GWs

5. **Chip Patience**: Wait for optimal windows (DGWs, BGWs) rather than using early

6. **Budget Growth**: Target 0.5-1.0m value growth per 10 gameweeks through price timing

## Future Enhancements

- [ ] Integration with ML predictions for transfer targets
- [ ] Template analysis (when to follow/fade the crowd)
- [ ] Differential identification (low ownership, high upside)
- [ ] Risk-adjusted strategies based on league position
- [ ] Historical performance tracking (what worked/didn't)

---

*"Plan your work, work your plan. That's how championships are won."* - Ron Clanker
