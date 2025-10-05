# Ron Clanker's Gameweek Workflow
## The Weekly Cycle - Two Points FC

---

## 📅 WEEKLY SCHEDULE

### **MONDAY - Post-Gameweek Review**

#### 1. Analyze Results
```bash
# Run comprehensive analysis
python scripts/analyze_gw_results.py --gw 8 --save-report
```

**Output:**
- Final score breakdown
- DC strategy effectiveness
- Captain performance analysis
- vs Average comparison
- Key learnings identified

#### 2. Staff Meeting
```bash
# Generate staff meeting report
python scripts/staff_meeting_report.py --gw 8 --save
```

**Attendees:**
- Ron (decisions)
- Ellie (performance review)
- Maggie (data update)
- Digger (defensive analysis)
- Sophia (attacking analysis)
- Priya (fixture outlook)
- Jimmy (value analysis)
- Terry (chip strategy)

**Outcome:** Action items for next GW identified

---

### **TUESDAY - Transfer Planning**

#### 3. Fixture Analysis (Next 3-6 GWs)
```bash
# Analyze upcoming fixtures (TO BE BUILT)
python scripts/analyze_fixtures.py --start-gw 9 --end-gw 14
```

**Focus:**
- Identify fixture swings
- Rate difficulty for each team
- Highlight double/blank gameweeks
- Plan 3-4 GW transfer strategy

#### 4. Identify Transfer Targets
```bash
# Find best transfer options (TO BE BUILT)
python scripts/analyze_transfer_targets.py --gw 9
```

**Criteria:**
- Upcoming fixtures (next 3-6 GW)
- Form trends (last 3 GW)
- DC consistency
- Price predictions (about to rise)
- Value (points per £m)

---

### **WEDNESDAY - Price Monitoring**

#### 5. Track Price Changes
```bash
# Monitor predicted price changes (TO BE BUILT)
python scripts/monitor_price_changes.py
```

**Actions:**
- Check squad players (prevent drops)
- Track targets (buy before rise)
- Build team value strategy
- Alert on critical changes

---

### **THURSDAY/FRIDAY - Team News & Decisions**

#### 6. Monitor Team News
- Check press conferences
- Injury updates
- Rotation risks
- Lineup predictions

#### 7. Finalize Transfers
```bash
# Execute planned transfers
python scripts/execute_transfers.py --gw 9 --transfer-out PLAYER_ID --transfer-in PLAYER_ID
```

**Process:**
1. Confirm team news
2. Execute transfers (before deadline)
3. Update squad file
4. Save transfer reasoning

---

### **SATURDAY (GW DEADLINE) - Final Setup**

#### 8. Set Captain & Formation
```bash
# Select optimal captain (TO BE BUILT)
python scripts/select_captain.py --gw 9
```

**Factors:**
- Fixture difficulty
- Form (last 3 GW)
- xG/xA trends
- Ownership (differential vs safe)

#### 9. Confirm Starting XI
- Review bench order
- Check auto-sub strategy
- Verify formation (3-5-2)
- Lock in team

---

### **SATURDAY/SUNDAY - Live Tracking**

#### 10. Monitor Live Scores
```bash
# Watch mode (auto-refresh every 60s)
python scripts/track_gameweek_live.py --gw 9 --watch --refresh 60

# Or single check
python scripts/track_gameweek_live.py --gw 9
```

**View:**
- Live points as they happen
- Player performance breakdown
- Running total
- Captain contribution
- Fixture status

#### 11. Save Snapshots (Optional)
```bash
# Save snapshot at key moments
python scripts/track_gameweek_live.py --gw 9 --save
```

---

## 🎯 QUICK REFERENCE COMMANDS

### Pre-Gameweek Setup
```bash
# 1. Review last GW
python scripts/analyze_gw_results.py --gw 8 --save-report

# 2. Staff meeting
python scripts/staff_meeting_report.py --gw 8 --save

# 3. Plan transfers (when ready)
python scripts/analyze_transfer_targets.py --gw 9

# 4. Set captain (when ready)
python scripts/select_captain.py --gw 9
```

### During Gameweek
```bash
# Live tracking
python scripts/track_gameweek_live.py --gw 9 --watch
```

### Post-Gameweek
```bash
# Full analysis
python scripts/analyze_gw_results.py --gw 9 --save-report

# Staff meeting
python scripts/staff_meeting_report.py --gw 9 --save
```

---

## 📊 OUTPUT FILES STRUCTURE

```
data/
├── squads/
│   ├── gw8_squad.json                    # Squad selection
│   └── gw8_team_announcement.txt         # Ron's announcement
│
├── gw_results/
│   └── gw8_analysis.json                 # Post-GW analysis
│
├── staff_meetings/
│   └── gw8_meeting.txt                   # Staff meeting report
│
├── transfers/
│   └── gw9_transfer_plan.json            # Transfer strategy
│
└── live_tracking/
    └── gw8_snapshot_TIMESTAMP.json       # Live snapshots
```

---

## 🔄 THE WEEKLY CYCLE (Summary)

### Day 1 (Monday): **REVIEW**
- ✅ Analyze GW results
- ✅ Staff meeting
- ✅ Identify learnings

### Day 2 (Tuesday): **PLAN**
- 📊 Fixture analysis
- 🎯 Transfer targets identified
- 📈 Price change monitoring begins

### Day 3-4 (Wed-Thu): **PREPARE**
- 👁️ Team news monitoring
- 💰 Price change alerts
- 🤔 Transfer decisions made

### Day 5-6 (Fri-Sat): **EXECUTE**
- ✍️ Make transfers
- 👑 Set captain
- ✅ Confirm lineup

### Day 7 (Sat-Sun): **TRACK**
- 🔴 Live monitoring
- 📊 Points accumulation
- 🎉 Results capture

### Repeat → **IMPROVE**

---

## 🎯 RON'S DECISION CHECKLIS

T

Before every gameweek deadline:

### Transfers
- [ ] Analyzed next 3-6 GW fixtures
- [ ] Identified transfer targets
- [ ] Checked price predictions
- [ ] Confirmed team news (injuries, rotation)
- [ ] Calculated EV of transfers vs hits
- [ ] Executed transfers (if needed)
- [ ] Updated squad file

### Captain
- [ ] Reviewed fixture difficulty
- [ ] Checked recent form (last 3 GW)
- [ ] Analyzed xG/xA trends
- [ ] Considered ownership (safe vs differential)
- [ ] Made captain selection
- [ ] Set vice-captain (fallback)

### Team Setup
- [ ] Confirmed starting XI (3-5-2 formation)
- [ ] Set bench order (auto-sub strategy)
- [ ] Verified all 15 players selected
- [ ] Checked for DGW/BGW impacts
- [ ] Saved squad to file

### Chips (if using)
- [ ] Confirmed chip timing is optimal
- [ ] Maximized chip value (DGW, fixtures, etc.)
- [ ] Documented chip usage reasoning
- [ ] Updated chip status in tracking

---

## 💡 PRO TIPS

### 1. **Early Transfers**
- Make transfers Tuesday/Wednesday if possible
- Get ahead of price rises
- Avoid deadline panic
- Unless waiting on team news!

### 2. **Captain Selection**
- Don't overthink - data + gut
- Haaland/Salah usually optimal
- Consider differentials when chasing rank
- Safe picks when protecting rank

### 3. **Price Changes**
- Monitor Tuesday-Thursday (high activity)
- Sell before price drops
- Buy before price rises
- Build £3-5m team value over season

### 4. **Fixture Swings**
- Plan 3-4 weeks ahead
- Use free transfers strategically
- Avoid last-minute scrambles
- Fixture planning > reactive transfers

### 5. **Live Tracking**
- Check at half-time, full-time
- Don't stress during games
- Use snapshots for records
- Review patterns post-GW

---

## 🚨 EMERGENCY PROTOCOLS

### Player Injured/Suspended Last Minute
1. Check auto-sub order (will bench player come on?)
2. If needed: emergency transfer with -4 hit
3. Calculate: Expected pts from new player vs -4 penalty
4. Only if gain > 4 points over next 2-3 GW

### Price Drop Alert (Squad Player)
1. Assess: Is player still optimal for fixtures?
2. If keeping: Accept price drop (it's just 0.1m)
3. If transferring: Move before drop (tonight!)
4. Don't panic sell for 0.1m alone

### Chip Opportunity (DGW/BGW Announced)
1. Priya: Analyze fixture impact
2. Terry: Recommend chip usage
3. Jimmy: Calculate optimal timing
4. Ron: Make final decision
5. Execute: Update plans immediately

---

## 📈 SUCCESS METRICS TO TRACK

### Weekly
- ✅ Points scored vs average
- ✅ Captain success rate
- ✅ DC points earned (target: 20+ per GW)
- ✅ Transfers: hits taken vs value gained

### Monthly
- ✅ Overall rank trend
- ✅ Team value growth
- ✅ Chip usage effectiveness
- ✅ Template beat rate

### Season
- ✅ Final rank (target: Top 100k)
- ✅ Total points
- ✅ DC strategy validation
- ✅ Lessons learned for next season

---

## 🎬 NEXT STEPS

### For GW8 (Ron's Debut):
1. ✅ Squad registered (owner action)
2. 🔴 Saturday: Live tracking begins
3. 📊 Monday: First staff meeting
4. 🎯 Tuesday: Plan GW9 transfers

### To Build (Priority Order):
1. **Transfer analysis system** (GW9 prep)
2. **Fixture analyzer** (3-6 GW outlook)
3. **Price change predictor** (team value growth)
4. **Captain optimizer** (data-driven selection)

---

**Last Updated**: October 5, 2025
**Current GW**: 8 (debut week)
**Next Milestone**: Post-GW8 staff meeting

*"Week in, week out. Consistent process. Marginal gains. That's how we climb."*
- Ron Clanker
