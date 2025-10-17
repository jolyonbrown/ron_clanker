# Ron Clanker - Next Tasks

## Current Status (October 17, 2025)

**Phase 1 (Foundation)**: ✅ COMPLETE
**Phase 2 (Intelligence)**: ✅ COMPLETE
**Phase 3 (Prediction)**: ⚠️ STARTED (needs ML models)
**Phase 4 (Advanced Strategy)**: ⚠️ STARTED (needs multi-week planning)
**Phase 5 (Mastery)**: ❌ NOT STARTED

**All beads issues**: ✅ CLOSED (32/32)

---

## Today's Session (October 17th) - COMPLETED

✅ Fixed gameweek selection bug (demo_ron_autonomous.py)
✅ Added official Premier League injuries page to Scout
✅ Implemented YouTube transcript caching (fully autonomous)
✅ Created transcript analysis tools for team
✅ Configured 3 FPL YouTube channels
✅ Documentation updates (logging, gameweek logic, YouTube monitoring)

---

## IMMEDIATE PRIORITIES (Next 1-2 Sessions)

### 1. ✅ **Scheduled Automated Operation** 🔄
**Priority: HIGH** → **STATUS: COMPLETE**
**Why**: System is autonomous but needs to run automatically

Completed Tasks:
- [x] Set up daily cron job for Scout intelligence gathering
- [x] Set up daily price change monitoring
- [x] Set up pre-deadline team selection automation
- [x] Configure notification system (Discord/Slack webhook for decisions)
- [x] Create health monitoring and database maintenance
- [x] Write comprehensive automation documentation

**Deliverable**: ✅ System runs autonomously without human intervention

Scripts created:
- `scripts/daily_scout.py` - Daily intelligence gathering
- `scripts/collect_fpl_data.py` - Daily FPL data sync
- `scripts/pre_deadline_selection.py` - Team selection automation
- `scripts/monitor_prices.py` - Hourly price monitoring
- `scripts/health_check.py` - System health verification
- `scripts/setup_cron.py` - Interactive cron installer
- `scripts/setup_notifications.py` - Notification configurator

See: `docs/AUTOMATED_OPERATION.md` for full guide

---

### 2. **Price Change Prediction** 📈
**Priority: HIGH** (promoted from #3)
**Why**: Currently monitors but doesn't predict - can improve transfer decisions

Tasks:
- [ ] Implement price predictor model (models/price_change.py is empty)
- [ ] Collect historical price change data
- [ ] Track net transfers as predictor feature
- [ ] Build simple ML model (logistic regression → gradient boosting)
- [ ] Test prediction accuracy (target: 70%+ accuracy)
- [ ] Integrate with Hugo for pre-emptive transfers

**Deliverable**: Predict price rises/falls 6-12 hours ahead

---

### 3. **Player Performance Prediction** 🎲
**Priority: HIGH** (promoted from #4)
**Why**: Currently uses form, but ML would be better for expected points

Tasks:
- [ ] Implement xG-based prediction model
- [ ] Historical data collection (GW1-7 for training)
- [ ] Feature engineering (form, fixtures, DC, xG, opponent strength)
- [ ] Train model for each position (GK, DEF, MID, FWD)
- [ ] Compare predicted vs actual points
- [ ] Integrate with value analyst rankings

**Deliverable**: More accurate expected points predictions

---

### 4. **Multi-Gameweek Planning** 📅
**Priority: MEDIUM** (promoted from #5)
**Why**: Currently reactive, needs to plan ahead

Tasks:
- [ ] Fixture difficulty prediction (3-6 gameweeks ahead)
- [ ] Transfer planning sequence (e.g., "GW10: out Palmer, in Saka, GW11: out Haaland, in Kane")
- [ ] Chip timing optimization (when to use Wildcard, Bench Boost, etc.)
- [ ] Template deviation analysis (when to follow/fade popular picks)
- [ ] Budget planning (build team value over season)

**Deliverable**: Ron plans 4-6 gameweeks ahead

---

### 6. **Learning and Improvement System** 📊
**Priority: MEDIUM**
**Why**: System should improve from mistakes

Tasks:
- [ ] Track all decisions made (transfers, captain, chips)
- [ ] Compare predicted vs actual outcomes
- [ ] Identify systematic biases (e.g., "always underestimate defenders")
- [ ] Agent performance tracking (which analysts are most accurate?)
- [ ] Adjust weights based on historical accuracy
- [ ] Weekly review reports

**Deliverable**: System learns from experience and improves

---

### 7. **Monitoring Dashboard** 📱
**Priority: LOW**
**Why**: Nice to have for tracking Ron's decisions

Tasks:
- [ ] Simple web dashboard (Flask/FastAPI)
- [ ] Show current team selection
- [ ] Show recent decisions and reasoning
- [ ] Show cached YouTube transcripts
- [ ] Show intelligence gathered today
- [ ] Show agent performance metrics
- [ ] Historical points tracking

**Deliverable**: Web UI to monitor Ron's decisions

---

### 8. **FPL API Team Submission** 🎯
**Priority: MEDIUM** (moved from #2 - requires manual team registration first)
**Why**: Currently makes decisions but doesn't submit them to FPL

**BLOCKED**: Need to manually register Ron's FPL team first before implementing API submission

Tasks:
- [ ] Manual team registration (user to complete)
- [ ] Research FPL API authentication (session cookies, login)
- [ ] Implement team submission endpoint integration
- [ ] Add transfer execution (buy/sell players)
- [ ] Add captain selection submission
- [ ] Add chip activation submission
- [ ] Add safety checks (confirm before submission)
- [ ] Add dry-run mode for testing

**Note**: FPL API is unofficial, may need reverse engineering from browser network traffic

**Deliverable**: Ron can actually manage a live FPL team

---

### 9. **Chip Strategy Optimization** 🃏
**Priority: MEDIUM**
**Why**: Chips worth 20-30 points if used correctly

Tasks:
- [ ] Wildcard timing (identify when team needs major overhaul)
- [ ] Bench Boost timing (identify gameweeks with strong bench)
- [ ] Triple Captain timing (identify high ceiling games)
- [ ] Free Hit timing (blank/double gameweeks)
- [ ] AFCON strategy (5 free transfers exploit)

**Deliverable**: Optimal chip usage timing

---

## LONG TERM (Future Sessions)

### 10. **Advanced ML Models** 🤖
**Priority: LOW**
**Why**: Phase 3-5 from CLAUDE.md

Tasks:
- [ ] Ensemble models (combine multiple prediction methods)
- [ ] Reinforcement learning for long-term planning
- [ ] Neural network for complex patterns
- [ ] Transfer learning from previous seasons
- [ ] Meta-learning (learn how to learn)

**Deliverable**: State-of-the-art FPL AI

---

### 11. **Risk Management** 🎰
**Priority: LOW**
**Why**: Strategy should depend on current rank

Tasks:
- [ ] Identify rank-based strategy (aggressive if behind, conservative if ahead)
- [ ] Calculate risk/reward of differentials
- [ ] Ownership-adjusted decisions (fade template when ahead)
- [ ] Variance management (high variance picks when chasing)

**Deliverable**: Adaptive strategy based on rank

---

### 12. **Integration Improvements** 🔧
**Priority: LOW**
**Why**: Quality of life improvements

Tasks:
- [ ] Better error handling and recovery
- [ ] Logging improvements (structured logging)
- [ ] Better testing coverage
- [ ] Docker deployment optimization
- [ ] Database backups automation (✅ partially complete)
- [ ] Monitoring and alerting (✅ health checks complete)

**Deliverable**: More robust, production-ready system

---

## COMPLETED WORK (Reference)

### Phase 1 (Foundation) - ✅ COMPLETE
- [x] Project structure and MCP integration
- [x] Rules Engine (parse rules, validate teams)
- [x] Data Collection Agent (Maggie)
- [x] Simple Player Valuation
- [x] Basic Manager Agent (Ron)
- [x] SQLite database

### Phase 2 (Intelligence) - ✅ COMPLETE
- [x] Fixture Analysis Agent (Priya)
- [x] Defensive Contribution Analyzer (Digger)
- [x] xG Analysis Agent (Sophia)
- [x] Value Analyst (Jimmy)
- [x] Transfer Strategy Agent (Hugo)
- [x] Scout Intelligence Gathering
- [x] Captain Selection Logic
- [x] Event bus coordination
- [x] YouTube transcript monitoring (NEW)
- [x] Official PL injuries page (NEW)
- [x] RSS feed monitoring
- [x] Intelligence classification

---

## Recommendation for Next Session

**Task #1: ✅ COMPLETE - Scheduled Automation**
→ System now runs autonomously! See `docs/AUTOMATED_OPERATION.md`

**If you want to improve transfer decisions:**
→ **Task #2: Price Change Prediction** (predict rises/falls 6-12h ahead)

**If you want better expected points:**
→ **Task #3: Player Performance Prediction** (xG-based ML models)

**If you want strategic planning:**
→ **Task #4: Multi-Gameweek Planning** (think ahead 4-6 weeks)

**If you want Ron to submit teams automatically:**
→ **Task #8: FPL API Submission** (BLOCKED: manual team registration needed first)

---

## Quick Wins (Can do in 30-60 mins)

1. ✅ **Setup daily cron job** - COMPLETE (scripts/setup_cron.py)
2. ✅ **Add Discord webhook** - COMPLETE (scripts/setup_notifications.py)
3. ✅ **Database backup script** - COMPLETE (scripts/backup_database.py)
4. ✅ **Health monitoring** - COMPLETE (scripts/health_check.py)
5. **Add tests** - Ensure system doesn't break (still TODO)
6. **Register Ron's FPL team** - Manual setup needed for API submission

---

**Last Updated**: October 17, 2025 (Post-Automation)
**Status**: Automation complete, ML models next
**Next Priority**: Price change prediction OR player performance prediction
