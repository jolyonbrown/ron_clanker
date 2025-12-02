# GW10 ML Model Fix - Post-Mortem

**Date**: 2025-11-01
**Issue**: ron_clanker-103
**Severity**: P0 - Critical

## Problem Summary

The ML prediction model was producing completely inverted predictions for GW10, causing Ron to:
- Captain João Pedro (0.95 xP actual) over Haaland (7.32 xP actual)
- Consider transferring OUT Haaland for Woltemade
- Make decisions opposite to reality

## Root Cause

**Team strength data was missing from the database.**

All `strength_attack_home`, `strength_attack_away`, `strength_defence_home`, and `strength_defence_away` fields were NULL in the `teams` table.

This caused:
1. Opponent strength features to show as 0.003 instead of proper ratings (1000-1500 scale)
2. All fixtures to appear equally difficult to the ML model
3. Model to rely heavily on other features which were mis-weighted
4. Predictions to become inverted/unreliable

## Investigation Process

1. **Initial observation**: João Pedro captained over Haaland (seems wrong)
2. **Checked predictions**:
   - Haaland: 4.62 xP (Man City home vs Bournemouth) ❌
   - Woltemade: 12.88 xP (Newcastle away at West Ham) ❌
   - João Pedro: 8.94 xP (Chelsea away at Spurs) ❌

3. **Checked actual stats**:
   - Haaland: Form 7.7, PPG 9.4, 85 total points, ICT 100.3
   - Woltemade: Form 5.3, PPG 5.7, 34 total points, ICT 35.3
   - Clearly Haaland should be rated much higher

4. **Investigated features**:
   - Ran debug script to extract all features fed to model
   - Found: `opponent_strength: 0.003` for ALL players
   - This was clearly wrong

5. **Checked database**:
   ```sql
   SELECT name, strength_attack_home, strength_attack_away,
          strength_defence_home, strength_defence_away
   FROM teams WHERE name = 'Bournemouth';
   ```
   Result: All NULL

6. **Checked FPL API**:
   - API DOES provide all strength fields on 1000-1500 scale
   - Arsenal: attack_home 1340, defence_home 1260, etc.

7. **Found bug in data collection**:
   - `scripts/collect_fpl_data.py` was only fetching `strength_overall_home/away`
   - Not fetching `strength_attack_*` or `strength_defence_*` fields

## Fix Applied

### 1. Updated Data Collection Script

**File**: `scripts/collect_fpl_data.py` (lines 71-85)

```python
for team in fpl_data['teams']:
    team_data = {
        'id': team['id'],
        'code': team['code'],
        'name': team['name'],
        'short_name': team['short_name'],
        'strength': team.get('strength'),
        'strength_overall_home': team.get('strength_overall_home'),
        'strength_overall_away': team.get('strength_overall_away'),
        # NEW: Added these fields
        'strength_attack_home': team.get('strength_attack_home'),
        'strength_attack_away': team.get('strength_attack_away'),
        'strength_defence_home': team.get('strength_defence_home'),
        'strength_defence_away': team.get('strength_defence_away'),
    }
    db.upsert_team(team_data)
```

### 2. Re-collected FPL Data

Ran: `venv/bin/python scripts/collect_fpl_data.py`

Result: All team strength fields now populated correctly:
- Bournemouth: attack_home 1100, defence_home 1200
- Man City: attack_home 1210, defence_away 1380
- etc.

### 3. Regenerated Predictions

Deleted broken predictions:
```sql
DELETE FROM player_predictions WHERE gameweek IN (10, 11, 12, 13);
```

Regenerated with correct data:
```bash
venv/bin/python scripts/predict_gameweek.py --gw 10 --save
venv/bin/python scripts/predict_gameweek.py --gw 11 --save
venv/bin/python scripts/predict_gameweek.py --gw 12 --save
venv/bin/python scripts/predict_gameweek.py --gw 13 --save
```

### 4. Fixed Syntax Error

**File**: `ron_clanker/llm_banter.py` (line 348)

Had invalid f-string syntax: `{if transfers: ...}`

Changed to plain text for LLM prompt.

## Results

### Before Fix:
| Player | Prediction | Context |
|--------|-----------|---------|
| Haaland | 4.62 xP | Man City home vs Bournemouth |
| Woltemade | 12.88 xP | Newcastle away at West Ham |
| João Pedro | 8.94 xP | Chelsea away at Spurs |

### After Fix:
| Player | Prediction | Context | Change |
|--------|-----------|---------|--------|
| Haaland | **7.32 xP** | Man City home vs Bournemouth | +58% ✅ |
| Woltemade | **6.01 xP** | Newcastle away at West Ham | -53% ✅ |
| João Pedro | **0.95 xP** | Chelsea away at Spurs | -89% ✅ |

**Captain selection**: Haaland now properly rated higher than João Pedro

## Prevention

### Why This Happened

1. **No validation**: Data collection script silently skipped fields without warning
2. **No monitoring**: No alerts when critical features are NULL
3. **No sanity checks**: Model predictions not validated against basic heuristics

### Improvements Needed

1. **Add data validation**:
   ```python
   # After upserting teams
   assert all(t['strength_attack_home'] is not None for t in teams)
   ```

2. **Add prediction sanity checks**:
   ```python
   # Flag if premium players (>£12m) predicted < 5 xP at home
   if player.price > 12.0 and player.is_home and xP < 5.0:
       logger.warning(f"Suspiciously low prediction: {player.name} {xP}")
   ```

3. **Add feature monitoring**:
   ```python
   # Log feature distributions
   opponent_strengths = [f['opponent_strength'] for f in features]
   if max(opponent_strengths) < 1.0:  # Should be 1000-1500
       logger.error("Opponent strength features look wrong!")
   ```

4. **Weekly checklist**: Add "Verify team strength data populated" to gameweek workflow

## Impact

**Time to fix**: ~30 minutes
**Games affected**: None (caught before GW10 deadline)
**Data affected**: GW10-13 predictions regenerated

## Files Modified

1. `scripts/collect_fpl_data.py` - Added strength field collection
2. `ron_clanker/llm_banter.py` - Fixed f-string syntax
3. `scripts/debug_model_features.py` - Created for debugging (can keep)
4. `scripts/review_gw10_decision.py` - Created for user review workflow

## Lessons Learned

1. **Always validate critical data** - NULL fields should raise errors, not silently fail
2. **Monitor feature distributions** - Catch data quality issues before they reach the model
3. **Sanity check predictions** - Flag when they violate basic common sense
4. **Test data collection thoroughly** - Verify ALL fields are populated, not just some
5. **Have failsafe backups** - Saved Ron's GW10 team before regenerating

## Status

✅ **RESOLVED**
- All team strength data now populated correctly
- Predictions regenerated with accurate fixture difficulty
- Captain selection now sensible (Haaland > João Pedro)
- Full team selection flow running with fixed data
- User review before posting to Slack

---

**Last Updated**: 2025-11-01 10:45 UTC
**Next Review**: After GW10 completes - verify predictions were accurate
