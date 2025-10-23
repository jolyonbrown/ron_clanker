# Manager Comparison: manager.py vs manager_agent_v2.py

## Overview

**Goal**: Consolidate to single event-driven manager architecture (ron_clanker-81)

**Current State**:
- `manager.py`: 1047 lines, synchronous, USED IN PRODUCTION
- `manager_agent_v2.py`: 583 lines, event-driven, INCOMPLETE

---

## Feature Comparison

### ✅ Features in BOTH

| Feature | manager.py | manager_agent_v2.py | Notes |
|---------|-----------|---------------------|-------|
| Squad building | `_build_optimal_squad()` | `_build_squad_from_rankings()` | Both work |
| Position assignment | `_assign_positions()` | `_assign_squad_positions()` | Both use formation optimizer |
| Captain selection | `_assign_captain()` | `_select_captain()` | Both work |
| Team announcement | Part of `select_initial_team()` | `_generate_team_announcement()` | v2 is better structured |

### ❌ Features ONLY in manager.py (need to port)

| Feature | Method | Lines | Priority | Complexity |
|---------|--------|-------|----------|------------|
| **Transfer optimization** | `_decide_transfers_optimized()` | 516-577 | P0 | HIGH |
| **ML transfer decisions** | `_decide_transfers_ml()` | 578-701 | P0 | HIGH |
| **ML captain selection** | `_assign_captain_ml()` | 702-771 | P0 | MEDIUM |
| **Starting XI optimizer** | `_optimize_starting_xi()` | 772-878 | P1 | MEDIUM |
| **Chip usage (ML)** | `_decide_chip_usage_ml()` | 880-903 | P0 | MEDIUM |
| **Weekly decision orchestration** | `make_weekly_decision()` | 372-514 | P0 | HIGH |
| **Gameweek review** | `review_gameweek()` | 1017-1047 | P2 | LOW |
| **Basic transfer logic** | `_decide_transfers()` | 913-944 | P1 | LOW |
| **Basic chip usage** | `_decide_chip_usage()` | 973-985 | P1 | LOW |

### ✅ Features ONLY in manager_agent_v2.py (v2 advantages)

| Feature | Method | Notes |
|---------|--------|-------|
| Event subscription | `setup_subscriptions()` | Listens to VALUE_RANKINGS_COMPLETED |
| Event handling | `handle_event()` | React to events asynchronously |
| Event publishing | Inherited from `BaseAgent` | Publishes TEAM_SELECTED |
| Better separation | Smaller, focused methods | Easier to understand |

---

## Dependencies Analysis

### manager.py imports:

```python
from rules.rules_engine import RulesEngine
from agents.data_collector import DataCollector
from agents.player_valuation import PlayerValuationAgent
from agents.synthesis.engine import DecisionSynthesisEngine  # ← ML CORE
from agents.transfer_optimizer import TransferOptimizer      # ← TRANSFERS
from intelligence.chip_strategy import ChipStrategyAnalyzer  # ← CHIPS
from ron_clanker.persona import RonClanker
from data.database import Database
from utils.gameweek import get_current_gameweek
```

**Critical dependencies**:
- `DecisionSynthesisEngine`: ML predictions, recommendations
- `TransferOptimizer`: Multi-GW transfer planning
- `ChipStrategyAnalyzer`: Chip vs transfer comparison

### manager_agent_v2.py imports:

```python
from agents.base_agent import BaseAgent
from agents.player_valuation import PlayerValuationAgent
from rules.rules_engine import RulesEngine
from ron_clanker.persona import RonClanker
from data.database import Database
from infrastructure.events import Event, EventType, EventPriority
```

**Missing**:
- ❌ `DecisionSynthesisEngine`
- ❌ `TransferOptimizer`
- ❌ `ChipStrategyAnalyzer`

---

## Method-by-Method Porting Plan

### Priority 0: Core Decision Making

#### 1. **Weekly Decision Orchestration**
- **Source**: `manager.py::make_weekly_decision()` (lines 372-514)
- **Target**: New method in `manager_agent_v2.py`
- **Complexity**: HIGH - orchestrates everything
- **Strategy**: Convert to event-driven pattern
  - Listen for `GAMEWEEK_PLANNING` event
  - Gather data from cached events (fixtures, value rankings)
  - Call ML synthesis
  - Make transfers
  - Select chips
  - Publish `TEAM_SELECTED` event

#### 2. **ML Transfer Decisions**
- **Source**: `manager.py::_decide_transfers_ml()` (lines 578-701)
- **Target**: Port to `manager_agent_v2.py::_decide_transfers()`
- **Complexity**: HIGH - uses DecisionSynthesisEngine, TransferOptimizer
- **Dependencies**:
  - Add `self.synthesis_engine` to v2
  - Add `self.transfer_optimizer` to v2
  - Add `self.chip_strategy` to v2

#### 3. **ML Captain Selection**
- **Source**: `manager.py::_assign_captain_ml()` (lines 702-771)
- **Target**: Replace `manager_agent_v2.py::_select_captain()`
- **Complexity**: MEDIUM - uses ML predictions
- **Dependencies**: `self.synthesis_engine`

#### 4. **Chip Usage (ML)**
- **Source**: `manager.py::_decide_chip_usage_ml()` (lines 880-903)
- **Target**: New method in `manager_agent_v2.py`
- **Complexity**: MEDIUM - chip vs transfer comparison
- **Dependencies**: `self.chip_strategy`

### Priority 1: Optimization

#### 5. **Transfer Optimization (basic)**
- **Source**: `manager.py::_decide_transfers_optimized()` (lines 516-577)
- **Target**: Merge into ML transfer method
- **Complexity**: HIGH - fallback if ML fails

#### 6. **Starting XI Optimizer**
- **Source**: `manager.py::_optimize_starting_xi()` (lines 772-878)
- **Target**: Consider porting or using formation optimizer
- **Note**: Formation optimizer already handles this (ron_clanker-80)

### Priority 2: Nice to Have

#### 7. **Gameweek Review**
- **Source**: `manager.py::review_gameweek()` (lines 1017-1047)
- **Target**: New method or separate script
- **Complexity**: LOW - mostly database queries

---

## Porting Strategy

### Phase 1: Add Dependencies (FIRST)
```python
# In manager_agent_v2.py __init__()

from agents.synthesis.engine import DecisionSynthesisEngine
from agents.transfer_optimizer import TransferOptimizer
from intelligence.chip_strategy import ChipStrategyAnalyzer

self.synthesis_engine = DecisionSynthesisEngine(database=self.db)
self.transfer_optimizer = TransferOptimizer(
    database=self.db,
    chip_strategy=ChipStrategyAnalyzer(database=self.db, league_intel_service=None)
)
self.chip_strategy = self.transfer_optimizer.chip_strategy
```

### Phase 2: Port Transfer Logic
- Copy `_decide_transfers_ml()` → `manager_agent_v2.py::_decide_transfers()`
- Copy `_decide_transfers_optimized()` as fallback
- Test transfers work

### Phase 3: Port Captain Logic
- Replace `_select_captain()` with ML version from `_assign_captain_ml()`
- Test captain selection

### Phase 4: Port Chip Logic
- Add `_decide_chip_usage()` method
- Integrate with transfer decisions
- Test chip recommendations

### Phase 5: Port Weekly Decision
- Add `make_weekly_decision()` method (event-driven version)
- Listen for `GAMEWEEK_PLANNING` event
- Orchestrate: transfers → captain → chips → team announcement
- Publish `TEAM_SELECTED` event

### Phase 6: Update Scripts
- Modify `pre_deadline_selection.py` to use `RonManager` (v2)
- Test end-to-end workflow
- Run dry-run for GW9

### Phase 7: Deprecate manager.py
- Rename `manager.py` → `manager_legacy.py`
- Update all imports
- Remove from active codebase

---

## Event Flow (Target Architecture)

```
DAILY MONITORING (03:00):
  → Scout gathers intelligence
  → Scout publishes INJURY_INTELLIGENCE, ROTATION_RISK
  → Hugo caches intelligence alerts

PRE-DEADLINE (48h):
  → Celery publishes GAMEWEEK_PLANNING(trigger='48h')
  → Digger analyzes DC performers → DC_ANALYSIS_COMPLETE
  → Priya analyzes fixtures → FIXTURE_ANALYSIS_COMPLETED
  → Sophia analyzes xG → XG_ANALYSIS_COMPLETE
  → Jimmy combines all → VALUE_RANKINGS_COMPLETED

PRE-DEADLINE (24h):
  → RonManager receives VALUE_RANKINGS_COMPLETED
  → Caches rankings

PRE-DEADLINE (6h):
  → Celery publishes GAMEWEEK_PLANNING(trigger='6h')
  → RonManager.make_weekly_decision():
    - Check cached intelligence from Scout
    - Run ML predictions (DecisionSynthesisEngine)
    - Evaluate transfers (TransferOptimizer)
    - Evaluate chips (ChipStrategyAnalyzer)
    - Make final decision
    - Publish TEAM_SELECTED event
  → Ellie logs decision for learning
  → Slack/Telegram notification sent
```

---

## Testing Plan

1. **Unit Tests**: Test each ported method independently
2. **Integration Test**: Full event-driven workflow in test environment
3. **Dry Run**: Generate GW9 team using v2, compare to v1 output
4. **Production Cutover**: Switch `pre_deadline_selection.py` to v2 for GW10

---

## Success Criteria

- ✅ Single `RonManager` class (event-driven)
- ✅ All production scripts use event architecture
- ✅ No `manager.py` in active codebase
- ✅ System remains fully autonomous
- ✅ ML integration works (DecisionSynthesisEngine)
- ✅ Transfer optimization works (TransferOptimizer)
- ✅ Chip strategy works (ChipStrategyAnalyzer)
- ✅ Intelligence integration works (Scout events)
- ✅ End-to-end test passes
- ✅ Documentation updated

---

**Next Steps**: Start with Phase 1 - add dependencies to manager_agent_v2.py
