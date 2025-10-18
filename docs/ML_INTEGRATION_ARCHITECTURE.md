ML & INTELLIGENCE INTEGRATION AUDIT
====================================

WHAT WE HAVE BUILT (Data & Models):
===================================

1. ML MODELS ✅ (Exist but Not Used)
   • PlayerPerformancePredictor (ml/prediction/model.py)
     - Position-specific Gradient Boosting models
     - Trained models saved: position_1-4_gw8_v1.pkl
     - Feature engineering: ml/prediction/features.py
     - ❌ NO predictions in database
     - ❌ NOT used in team selection
   
   • PriceChangePredictor (models/price_change.py)
     - Logistic Regression (RPi-optimized)
     - Predicts player price rises/falls
     - ❌ NOT integrated into transfer decisions
   
   Scripts exist but not in decision pipeline:
   • scripts/predict_gameweek.py
   • scripts/train_prediction_models.py
   • scripts/predict_price_changes.py

2. INTELLIGENCE SERVICES ✅ (Generate Reports, Not Used in Decisions)
   • LeagueIntelligenceService
     - Tracks 13 rivals, chip usage, differentials
     - Generates reports daily
     - ❌ NOT consulted for team selection
   
   • ChipStrategyAnalyzer
     - Analyzes optimal chip timing
     - ❌ NOT used for chip decisions
   
   • FixtureOptimizer
     - Identifies fixture swings, DGW/BGW
     - ❌ NOT used for transfer planning
   
   • GlobalRankingsAnalyzer
     - Top 100/1000 template analysis
     - ❌ NOT used to inform picks

3. DATA COLLECTION ✅ (Working)
   • Daily FPL data (players, fixtures, gameweeks)
   • Price snapshots & changes
   • Gameweek histories
   • League data

WHAT'S MISSING (The Integration Layer):
=======================================

❌ DECISION SYNTHESIS ENGINE
   Purpose: Connect ML + Intelligence → Recommendations

   Should provide:
   ┌─────────────────────────────────────────┐
   │  UNIFIED RECOMMENDATIONS                │
   ├─────────────────────────────────────────┤
   │                                         │
   │  TRANSFERS:                             │
   │  • Player A out (-4 hit worth it?)      │
   │    Reason: Price falling, fixture swing │
   │    ML: 2.3 xP → 4.7 xP with replacement│
   │    Elite: 15% ownership → differential  │
   │                                         │
   │  CAPTAIN:                               │
   │  • Haaland (safe) vs differential      │
   │    ML: 8.5 xP                          │
   │    Elite: 96% captain him              │
   │    League: You're chasing, need risk   │
   │    → Recommend: Differential captain   │
   │                                         │
   │  CHIPS:                                 │
   │  • Triple Captain: WAIT                │
   │    Reason: No DGW, 79% elite used it   │
   │    Best timing: GW12 (DGW predicted)   │
   │                                         │
   │  STRATEGY:                              │
   │  • Risk level: BOLD                    │
   │    Reason: 406pts behind, need diff    │
   │    Cover: Haaland (100% elite own)     │
   │    Punt: 2-3 <30% ownership picks      │
   │                                         │
   └─────────────────────────────────────────┘

CURRENT FLOW (Broken):
======================

Data Collection → [Intelligence Reports] → 📁 Files
                ↓
           [ML Models] → 📁 Not Run
                ↓
                ❌ GAP
                ↓
         Manager Agent → Basic valuation only
                ↓
         Team Selection

NEEDED FLOW (Integrated):
=========================

Data Collection
    ↓
┌───────────────────────────────┐
│  1. RUN ML PREDICTIONS        │
│  • Expected points (all)      │
│  • Price changes (targets)    │
│  • Store to database          │
└──────────┬────────────────────┘
           ↓
┌───────────────────────────────┐
│  2. RUN INTELLIGENCE          │
│  • League analysis            │
│  • Global rankings            │
│  • Fixture swings             │
│  • Chip timing                │
└──────────┬────────────────────┘
           ↓
┌───────────────────────────────┐
│  3. DECISION SYNTHESIS ⭐     │ <- NEW
│                               │
│  Input: ML + Intelligence     │
│  Process:                     │
│   • Evaluate each player      │
│   • Consider context          │
│   • Score opportunities       │
│   • Assess risks              │
│  Output: Recommendations      │
└──────────┬────────────────────┘
           ↓
┌───────────────────────────────┐
│  4. RON'S DECISION            │
│  • Reviews synthesis          │
│  • Applies philosophy         │
│  • Makes final call           │
│  • Generates announcement     │
└──────────┬────────────────────┘
           ↓
    Team Selection

KEY INTEGRATION POINTS:
======================

1. Pre-Deadline Pipeline (6hrs before):
   ✅ Collect latest data
   ✅ Generate ML predictions → player_predictions table
   ✅ Run intelligence services
   ⭐ NEW: Synthesis engine combines all inputs
   ✅ Manager reviews + decides

2. Transfer Evaluation:
   Current: "Is player value good?"
   Needed: "Is player value good + ML predicts X points + 
            fits strategy + price rising + differential?"

3. Captain Selection:
   Current: "Highest expected points"
   Needed: "Highest xP + ownership context + league position +
            risk appetite + elite consensus"

4. Chip Timing:
   Current: "Manual/basic rules"
   Needed: "DGW/BGW detection + rival chip status + 
            opportunity score + competitive need"

