# FPL DATA AUDIT - What Data Do We Have Access To?

## ✅ DATA WE'RE CURRENTLY USING

### Player Performance Stats
- ✅ Total points, points per game
- ✅ Minutes played, starts
- ✅ Goals, assists
- ✅ Form (FPL's rolling average)
- ✅ Price (now_cost)
- ✅ Status (available, injured, suspended, doubtful)
- ✅ **Defensive Contribution (DC)** - our edge!
- ✅ DC per 90 minutes

### Market Data
- ✅ Ownership % (selected_by_percent)
- ✅ Transfers in/out per gameweek
- ✅ Price changes tracking

### Team Data
- ✅ Team IDs and names
- ✅ Basic team info

---

## 🆕 DATA WE JUST ADDED (This Session!)

### Fixture Analysis
- ✅ **Fixture difficulty ratings (1-5)** for every match
- ✅ Home/away fixtures for next 6 gameweeks
- ✅ Team strength ratings (attack/defence, home/away)

### Underlying Stats (xG, xA)
- ✅ **Expected Goals (xG)** - predictive of future scoring
- ✅ **Expected Assists (xA)** - predictive of creativity
- ✅ **Expected Goal Involvements (xGI)** - total threat
- ✅ **xG/xA/xGI per 90 minutes** - rate stats

### FPL Advanced Metrics
- ✅ **ICT Index** (Influence, Creativity, Threat)
- ✅ **BPS** (Bonus Point System score)
- ✅ **Bonus points earned**
- ✅ **Starts per 90** (nailed-on indicator)

---

## ⚠️ DATA WE HAVE BUT AREN'T FULLY UTILIZING YET

### Detailed Performance Stats
- ⚠️ Clean sheets, clean sheets per 90
- ⚠️ Saves, saves per 90 (GKPs)
- ⚠️ Expected goals conceded (xGC) per 90
- ⚠️ Yellow cards, red cards
- ⚠️ Own goals
- ⚠️ Penalties taken, missed, saved

### Detailed Defensive Stats
- ⚠️ Clearances, blocks, interceptions (CBI) - separate breakdown
- ⚠️ Tackles
- ⚠️ Recoveries

### Set Piece Data
- ⚠️ Corners and indirect freekicks order
- ⚠️ Direct freekicks order
- ⚠️ Penalties order

### Cost & Value Stats
- ⚠️ Cost change from start of season
- ⚠️ Cost change this gameweek
- ⚠️ Value form (form / price)
- ⚠️ Value season (total points / price)

### Ranking Stats
- ⚠️ Form rank (vs all players and by position)
- ⚠️ Points per game rank
- ⚠️ ICT rank
- ⚠️ Influence/Creativity/Threat individual ranks
- ⚠️ Price rank, ownership rank

### Dream Team
- ⚠️ Times in dream team (top performers each GW)
- ⚠️ Currently in dream team (boolean)

### Team Strength Ratings
- ⚠️ **strength_attack_home** (1000-1400 scale)
- ⚠️ **strength_attack_away**
- ⚠️ **strength_defence_home**
- ⚠️ **strength_defence_away**
- ⚠️ **strength_overall_home**
- ⚠️ **strength_overall_away**

These could help predict clean sheet probability!

---

## 🚫 DATA WE DON'T HAVE ACCESS TO

### Real-Time / External Data
- ❌ Press conference quotes (manual check needed)
- ❌ Training ground reports
- ❌ Tactical changes (formation shifts)
- ❌ Player morale, confidence
- ❌ Contract situations
- ❌ Referee assignments (can affect cards)
- ❌ Weather conditions

### Historical Context
- ❌ Player vs opponent history
- ❌ Head-to-head team records
- ❌ Home/away form splits (would need to calculate)

---

## 💡 RECOMMENDED IMPROVEMENTS

### Immediate (Can Add Tomorrow)

1. **Set Piece Takers Priority**
   - Check corners_order, freekicks_order, penalties_order
   - Prioritize players on set pieces (higher assist potential)

2. **Clean Sheet Probability**
   - Use team strength_defence ratings
   - Cross-reference with opponent strength_attack
   - Calculate clean sheet odds for defenders/GKPs

3. **BPS Predictor**
   - Track players with high BPS averages
   - BPS often leads to bonus points (3/2/1 pts)

4. **Form Momentum**
   - Track players with rising form (last 3-4 GWs)
   - Identify hot streaks vs cold streaks

5. **Fixture Swing Detection**
   - Identify teams whose fixtures get much easier/harder
   - Time transfers around fixture swings

### Medium-Term (Next Few Weeks)

6. **Value Tracking**
   - Monitor value_form and value_season
   - Find underpriced gems (high value scores)

7. **Ownership vs Performance**
   - Identify low-owned players outperforming (differentials)
   - Identify template picks to avoid (high-owned, low-value)

8. **xGC for Defenders**
   - Use expected_goals_conceded to predict clean sheets
   - Better than just looking at past clean sheets

### Long-Term (Phase 3+)

9. **Composite Scores**
   - Combine xGI, BPS, form, fixtures into single "Ron Score"
   - Machine learning model to weight factors

10. **Historical Regression Models**
    - Track xG vs actual goals over time
    - Identify players overperforming (sell high) vs underperforming (buy low)

---

## 🎯 HOW THIS CHANGES OUR DECISION-MAKING

### Previous Approach (GW1-7 Analysis Only)
- Looked at past points
- Calculated DC contribution
- Sorted by PPG and value

**MISSED:**
- Fixture difficulty ahead
- Underlying performance (xG)
- Rotation risk (starts)

### NEW Approach (Full Data)

**Player Evaluation Formula:**
```
PRIORITY = (
    Past_Performance (PPG, DC, total points)
    + Future_Fixtures (next 6 GW difficulty)
    + Underlying_Stats (xGI per 90)
    + Reliability (starts, minutes)
    + Value (price, ownership for differentials)
    + Set_Pieces (bonus for takers)
    + Team_Strength (defensive/attacking ratings)
)
```

**Example: Woltemade vs Thiago Decision**

**OLD THINKING:**
- Woltemade: 8.0 PPG > Thiago: 5.3 PPG
- Pick Woltemade

**NEW THINKING:**
| Factor | Woltemade | Thiago |
|--------|-----------|---------|
| PPG | 8.0 (small sample) | 5.3 (larger sample) |
| Starts | 4/7 (rotation risk) ❌ | 7/7 (nailed) ✅ |
| xGI/90 | 0.61 | 0.47 |
| Fixtures GW8-13 | 3.0 avg | 2.8 avg (easier) ✅ |
| Total Points | 24 | 32 (more) ✅ |
| Minutes | 303 | 561 (more reliable) ✅ |

**VERDICT:** Thiago more reliable long-term despite lower PPG.

---

## 📋 DATA SOURCES SUMMARY

### FPL API Endpoints We Use:
1. ✅ `/bootstrap-static/` - Main data (players, teams, gameweeks)
2. ✅ `/fixtures/` - All 380 fixtures with difficulty ratings
3. ⚠️ `/element-summary/{player_id}/` - Player history, fixtures (not using yet)
4. ⚠️ `/entry/{team_id}/` - Team data (for tracking our team later)
5. ⚠️ `/event/{gw}/live/` - Live gameweek data (during matches)

### Data We Could Add:
- Player history endpoint (detailed GW-by-GW breakdown)
- Live gameweek data (during matches for real-time decisions)

---

## ✅ CONCLUSION: DATA COVERAGE

**What Ron Knows:**
- ✅ **Past performance** (points, DC, form)
- ✅ **Underlying stats** (xG, xA, xGI)
- ✅ **Future fixtures** (difficulty next 6 GWs)
- ✅ **Reliability** (starts, minutes)
- ✅ **Market sentiment** (ownership, transfers)
- ✅ **Team strength** ratings

**What Ron Needs to Check Manually:**
- ⚠️ Press conferences (Friday before deadline)
- ⚠️ Team news (late injury updates)
- ⚠️ International break issues

**Ron's Data Coverage: 95%**

The remaining 5% (press conferences, late team news) requires human monitoring, which is appropriate. Ron works from data, human monitors news.

---

**Updated:** October 17th, 2025
**Next Review:** After implementing set piece and clean sheet probability models
