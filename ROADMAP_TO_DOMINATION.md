# Ron Clanker's Roadmap to FPL Domination
## Two Points FC - Season 2025/26

**Current Status**: GW8 squad selected, ready to go
**Team Name**: Two Points FC ✅
**Entry Point**: Gameweek 8 (Fresh £100m start)

---

## ✅ PHASE 1: FOUNDATION (COMPLETE)

### What We've Built:
- ✅ Rules Engine (validates teams, enforces FPL rules)
- ✅ Data Collection via MCP (743 players, live API access)
- ✅ Comprehensive Analysis System (xG, xA, xGC, DC, ICT, form, value)
- ✅ Player Valuation (identifies DC specialists, value picks, differentials)
- ✅ Manager Agent Framework (Ron + 7 specialist backroom staff)
- ✅ GW8 Squad Selected (£88.6m, 10 DC specialists, Haaland captain)
- ✅ Database schema (SQLite, ready for season data)
- ✅ Testing suite (17 tests passing)

### What We Know Works:
- DC strategy identification (317 elite performers found)
- Budget optimization (£11.4m flexibility maintained)
- Team constraints (3-per-team rule enforced)
- Comprehensive player rankings (multiple criteria)

---

## 🎯 PHASE 2: GAMEWEEK EXECUTION (NEXT UP)

### Immediate Priorities (This Week):

#### 1. **Finalize GW8 Team Registration**
*Owner Action Required*
- Register "Two Points FC" on FPL website
- Input the 15-player squad
- Set captain (Haaland) and vice (Gabriel)
- Confirm starting XI (3-5-2 formation)
- ⏰ **Deadline**: GW8 deadline (check FPL for exact time)

#### 2. **Build Gameweek Tracking System**
*Scripts to create:*
- `scripts/track_gameweek_live.py` - Monitor live scores during GW
- `scripts/analyze_gw_results.py` - Post-GW performance analysis
- `scripts/compare_predictions.py` - Predicted vs actual points

**What it does:**
- Track live scores as GW8 unfolds
- Calculate actual points earned
- Compare to pre-GW expectations (Ron predicted 65-75 baseline)
- Identify what worked / what didn't
- Feed learnings to Ellie (Learning Agent)

#### 3. **Post-GW8 Review Process**
*After GW8 completes:*
- Run analysis on actual results
- Compare Ron's team vs template average
- Identify price risers/fallers
- Calculate overall rank projection
- Generate Ron's post-match commentary

**Staff Meeting Format:**
```
MONDAY POST-GW8:
1. Ellie: Results vs predictions review
2. Maggie: Latest data (price changes, injuries, form)
3. Digger: DC performance analysis
4. Sophia: Attacking returns review
5. Priya: Next 4 GW fixture outlook
6. Jimmy: Transfer opportunities identified
7. Terry: Chip strategy check
8. Ron: Decisions for GW9
```

---

## 🔄 PHASE 3: TRANSFER STRATEGY (GW9-12)

### Goals:
- Develop weekly transfer decision framework
- Implement price change prediction
- Build multi-week transfer planning
- Optimize free transfer vs hits calculations

### Scripts to Build:

#### 1. **`scripts/analyze_transfer_targets.py`**
- Identify players to bring in based on:
  - Upcoming fixtures (next 3-6 GW)
  - Form trends (recent GW performance)
  - Price predictions (about to rise)
  - DC consistency
  - Value (points per £m)

#### 2. **`scripts/plan_transfers.py`**
- Input: Current squad, available budget, fixture outlook
- Output: Recommended transfers with EV calculations
- Consider: Free transfers available, hit penalty (-4pts)
- Plan: 1-3 gameweeks ahead for fixture swings

#### 3. **`scripts/monitor_price_changes.py`**
- Track net transfers (in - out) for all players
- Predict price rises/falls 6-12 hours ahead
- Alert for: Squad players about to drop, targets about to rise
- Execute: Pre-emptive transfers to maximize team value

### Transfer Principles (Jimmy's Guidelines):
- ✅ Only take -4 hit if expected gain > 6 points over next 3 GW
- ✅ Plan around fixture swings (buy before good run starts)
- ✅ Build team value through early price rise captures
- ✅ Bank transfers when no clear moves (max 5 banked)
- ✅ **NEW**: Specify exact fixtures when analyzing targets

**Fixture Clarity Update:**
- Every transfer analysis MUST show: `Player X vs [Opponent] (H/A) in GW Y`
- Example: "Semenyo vs CRY (H) in GW8, vs ARS (A) in GW9, vs WHU (H) in GW10"

---

## 🎪 PHASE 4: CHIP MASTERY (GW8-19)

### First Half Chips (Must use before GW19):
- 🃏 Wildcard 1
- 🎯 Triple Captain 1
- 📊 Bench Boost 1
- 🆓 Free Hit 1

### Chip Strategy Scripts:

#### 1. **`scripts/identify_wildcard_timing.py`**
**Triggers for Wildcard:**
- 5+ players need replacing (team broken)
- Major fixture swing coming (build for 6-8 GW run)
- Template pivot opportunity (differential squad rebuild)
- Injury crisis

**Optimal Windows:**
- GW8-10: Early template break (if needed)
- GW12-15: Fixture swing period
- GW17-19: Pre-AFCON preparation (if 5 free transfers apply)

#### 2. **`scripts/plan_triple_captain.py`**
**Criteria:**
- Haaland/Salah double gameweek (if occurs)
- Single GW with perfect fixture + form + ownership
- Maximum captaincy differential opportunity
- Calculate: Expected points, ceiling, variance

#### 3. **`scripts/optimize_bench_boost.py`**
**Ideal Scenario:**
- All 4 bench players have strong fixtures
- Double gameweek for bench coverage
- High expected returns from bench 15

#### 4. **`scripts/plan_free_hit.py`**
**Use Cases:**
- Blank gameweek (most teams don't play)
- Double gameweek (load up on DGW players)
- Emergency fixture pile-up exploit

### Terry's Chip Timeline (Projected):
- **GW12-14**: Wildcard 1 (fixture swing window)
- **GW15-17**: Bench Boost (if strong bench fixtures align)
- **GW18**: Triple Captain (pre-AFCON, on in-form premium)
- **GW19**: Free Hit (if needed for AFCON blank)

---

## 📊 PHASE 5: INTELLIGENCE & LEARNING (GW8-38)

### Machine Learning Integration:

#### 1. **Player Performance Prediction**
`ml/models/player_xpts_predictor.py`
- Train on GW1-7 data → predict GW8+ points
- Features: xG, xA, xGC, DC%, form, fixtures, minutes
- Update weekly with actual results
- Compare: ML predictions vs Ron's gut vs actual

#### 2. **Price Change Prediction Model**
`ml/models/price_change_predictor.py`
- Track: Net transfers, ownership %, TSB (top 10k)
- Predict: Tonight's risers/fallers (6-12hrs ahead)
- Accuracy target: 80%+ within 24 hours
- Alert system for squad protection

#### 3. **Fixture Difficulty ML Model**
`ml/models/fixture_difficulty.py`
- Beyond FPL's ratings - actual xG/xGC analysis
- Team form + opponent weakness = true difficulty
- Home/away splits
- Predict: Expected points by fixture

#### 4. **Captain Selection Optimizer**
`ml/models/captain_optimizer.py`
- Input: All players, fixtures, form, ownership
- Output: Top 5 captain picks with EV
- Consider: Safe vs differential, ceiling vs floor
- Track: Ron's picks vs optimal (learning loop)

### Ellie's Learning Framework:
```python
class LearningSystem:
    def weekly_review(self, gameweek):
        """
        Compare predictions vs actual:
        - Which players outperformed expectations?
        - Which DC specialists failed to deliver?
        - Did we captain correctly?
        - Transfer decisions - right or wrong?

        Update models based on new data
        """

    def identify_biases(self):
        """
        Are we:
        - Overvaluing DC at expense of attacking returns?
        - Underestimating template players?
        - Missing form trends?
        - Getting fixtures wrong?
        """

    def strategy_adaptation(self):
        """
        Should we:
        - Increase attacking players?
        - Add more premiums?
        - Pivot to template?
        - Stay the course?
        """
```

---

## 🎯 PHASE 6: COMPETITIVE EDGE (GW12+)

### Advanced Features:

#### 1. **Template Analysis**
`scripts/analyze_template.py`
- Track top 10k effective ownership
- Identify template core (Salah, Haaland, Palmer, etc.)
- Calculate: Our differential %
- Decide: When to follow, when to fade

#### 2. **Rank Projections**
`scripts/project_rank.py`
- Current rank + points pace = projected finish
- Simulate: Rest of season scenarios
- Identify: Required point gains for target rank
- Strategy: Safe vs aggressive based on rank

#### 3. **Mini-League Tracker**
`scripts/track_rivals.py`
- Monitor specific rivals (if in mini-leagues)
- Compare: Our team vs theirs
- Identify: Differentials that matter
- Strategy: Chase or protect lead

#### 4. **Chip Combination Strategies**
- Wildcard → Bench Boost combo (GW12-13)
- Free Hit → Triple Captain (DGW if occurs)
- Optimal chip sequencing for rank climb

---

## 🏆 PHASE 7: SECOND HALF DOMINANCE (GW20-38)

### New Chips Available (GW20+):
- 🃏 Wildcard 2
- 🎯 Triple Captain 2
- 📊 Bench Boost 2
- 🆓 Free Hit 2

### Strategy Adjustments:

#### 1. **Double Gameweek Planning**
- Identify DGWs (usually GW24-26, GW32-34)
- Wildcard before DGW → load up
- Bench Boost during DGW → maximize
- Triple Captain on best DGW player

#### 2. **Blank Gameweek Navigation**
- Free Hit for blank GWs
- Maintain non-blank players in regular squad
- Don't waste transfers chasing blanks

#### 3. **Final Sprint (GW32-38)**
- Fixture analysis critical
- Form > fixtures in run-in
- Bold differentials if chasing rank
- Safe template if protecting rank

---

## 🔧 IMMEDIATE NEXT STEPS (This Week)

### Day 1 (Today): ✅ COMPLETE
- [x] Analysis complete (GW1-7, all 743 players)
- [x] Squad selected (GW8)
- [x] Team name chosen (Two Points FC)
- [x] Documentation complete

### Day 2 (Tomorrow): 🎯 ACTION REQUIRED
1. **Register Team** (Owner)
   - Input squad on FPL website
   - Set captain/vice
   - Confirm formation

2. **Build GW Tracking** (Development)
   - Live score monitor
   - Points calculator
   - Results analyzer

### Day 3-5 (Pre-GW8):
1. **Monitor for Changes**
   - Price changes affecting squad
   - Injury news
   - Team news (pressers)

2. **Prepare Post-GW Analysis**
   - Review framework ready
   - Comparison metrics defined
   - Ron's commentary template

### Day 6 (GW8 Deadline Day):
- Final checks (injuries, lineup confirmations)
- Last-minute captain switch if needed
- Lock in team
- Ron's final pre-match thoughts

### Day 7+ (GW8 In Progress):
- Live tracking
- Monitor results
- Capture all data for review

### Day 8 (Monday Post-GW8):
- **STAFF MEETING**
- Full results analysis
- GW9 planning begins
- Transfer targets identified

---

## 📈 SUCCESS METRICS

### Short-Term (GW8-15):
- ✅ Avg 60+ points per GW (DC foundation working)
- ✅ Beat template average 6/8 weeks
- ✅ Positive team value growth (£1-2m)
- ✅ Top 50% overall rank

### Mid-Term (GW16-28):
- ✅ Avg 65+ points per GW
- ✅ Top 25% overall rank
- ✅ Chip usage optimized (all first-half chips used well)
- ✅ £3-5m team value gain

### Long-Term (GW29-38):
- ✅ Top 100k overall rank
- ✅ Avg 70+ points per GW in run-in
- ✅ Prove DC strategy viability
- ✅ Finish season with pride

### Stretch Goals:
- 🌟 Top 50k overall rank
- 🌟 Beat template average 25+ weeks
- 🌟 Successful chip sequencing (all 8 chips well-used)
- 🌟 "I told you so" rights for Ron

---

## 🎬 NEXT SESSION AGENDA

### Priorities:
1. ✅ Register team (owner action)
2. 🔨 Build GW tracking scripts
3. 📊 Set up post-GW review workflow
4. 🎯 Prepare GW9 transfer analysis framework
5. 🤖 Design ML model pipeline (begin Phase 5)

### Questions to Answer:
- How do we track live GW scores efficiently?
- What's our transfer decision algorithm?
- When do we start building ML models?
- How do we present Ron's weekly commentary?
- Should we build a dashboard for visualization?

---

## 💬 Ron's Final Word

*"Right, I've seen the roadmap. Lot of fancy stuff there - machine learning, algorithms, predictive models. Maggie and the team are excited.*

*But here's what matters: We've got a squad. We've got a strategy. We've got 31 gameweeks to prove it works.*

*The template will beat us some weeks. That's fine. We're not chasing weekly rank - we're building something sustainable.*

*Every week, we bank our DC points. Every week, we make smart decisions. Every week, we get a little bit better.*

*Small gains compound. By Christmas, we'll be climbing. By March, we'll be competing. By May, we'll have proved that proper football - hard work, tactical discipline, foundation before flair - still wins.*

*Let's get to work.*

*Two Points FC. Up the table we go."*

---

**Last Updated**: October 5, 2025
**Current Phase**: 2 (Gameweek Execution)
**Next Milestone**: GW8 Results & Review
**Season Goal**: Top 100k, Prove the DC Strategy
