# Ron Clanker's FPL Management System
## An Autonomous Multi-Agent Fantasy Premier League Manager

---

## 🎯 System Overview

This project implements a fully autonomous Fantasy Premier League management system using multi-agent architecture. The system makes ALL team decisions independently, with no human input on selections. The human developer's role is to enhance data inputs and improve the system architecture.

**Primary Objective**: Maximize FPL points through intelligent, autonomous decision-making.

**Public Persona**: Ron Clanker - a no-nonsense 1970s/80s football manager who communicates team selections with old-school football wisdom and tactical nous.

---

## 🚨 CURRENT SEASON STATUS (2025/26)

**Date**: Saturday, October 4th 2025
**Current Gameweek**: 7 (in progress)
**Ron's Entry Point**: Gameweek 8 (FRESH START - NEW TEAM)

Ron is entering FPL as a **brand new team starting at GW8** with a blank slate and £100m budget. This is the DREAM scenario - fresh start with 6 gameweeks of real performance data to analyze before first selection. See `SEASON_SITUATION.md` for full details.

**MASSIVE Advantages**:
- ✅ **Fresh £100m budget** - build optimal team from scratch
- ✅ **6 GWs of REAL data** - identify PROVEN Defensive Contribution performers
- ✅ **All chips available** - perfect flexibility
- ✅ **International break** - extended preparation time
- ✅ **Market inefficiency** - DC players still undervalued despite proven results
- ✅ **31 gameweeks** to compete (GW8-38)

**Immediate Priority**: Analyze GW1-7 data to identify consistent DC performers, build optimal GW8 squad around proven 2pt earners.

---

## 📋 Gameweek Workflow - Ron's Requirements

### Every Gameweek Ron Must Deliver:

1. **Team Selection** (15 players within budget)
2. **Captain & Vice-Captain** chosen
3. **Formation** decided (starting XI + bench order)
4. **Team Announcement** in Ron's voice explaining:
   - Why each key player was selected
   - The tactical approach for the gameweek
   - Captain reasoning
   - Any transfers made and why
   - His overall strategy

**Example Format**:
```
GAMEWEEK 8 - RON'S TEAM SELECTION

Right lads, here's how we're lining up for Gameweek 8...

BETWEEN THE STICKS: Raya
Solid keeper. Arsenal's defense has been rock solid. Four clean sheets
in seven games. That's £5.6m well spent.

THE BACK LINE: Gabriel (C), Senesi, Timber
This is where we're different from everyone else. Gabriel's not just
defending - he's averaging 11 tackles and clearances per game. That's
2 guaranteed points from Defensive Contribution nearly every week, PLUS
the clean sheet potential. Same with Timber - 10.5 defensive actions
per game. The market's still pricing them on goals and assists. We're
smarter than that.

MIDFIELD ENGINE ROOM: Caicedo, Rice, Semenyo, Kudus, Gravenberch
Caicedo and Rice - proper midfielders. 12+ defensive actions most weeks.
Another 4 points from DC every gameweek the so-called experts miss.
Semenyo for the goals, Kudus for creativity. Balanced.

UP FRONT: Watkins, Haaland
Haaland gets the armband.

THE GAFFER'S LOGIC:
Five players earning Defensive Contribution points week in, week out.
That's 10 guaranteed points before we've even counted goals and assists.
Foundation first, fancy stuff second.

- Ron
```

This format should be generated for EVERY gameweek decision.

---

## 🏗️ Architecture Philosophy

### Multi-Agent Hierarchical System

The system follows a **hierarchical orchestrator-worker pattern** where specialized agents handle specific domains, coordinated by a central manager (Ron Clanker).

```
┌─────────────────────────────────────────────┐
│         RON CLANKER (Manager Agent)         │
│         - Final decision authority          │
│         - Orchestrates all agents           │
│         - Communicates selections           │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────┐         ┌─────────┐
│ STRATEGY│         │  DATA   │
│ LAYER   │◄────────┤ LAYER   │
└────┬────┘         └────┬────┘
     │                   │
     │              ┌────┴─────────────┐
     │              ▼                  ▼
     │         ┌─────────┐      ┌──────────┐
     │         │  Rules  │      │   MCP    │
     │         │ Engine  │      │  Client  │
     │         └─────────┘      └──────────┘
     │
     └─► Analysis Agents:
         • Player Valuation
         • Fixture Analysis
         • Price Prediction
         • Defensive Contribution
         • Transfer Optimization
         • Chip Strategy
```

### Core Principles

1. **Autonomy**: System makes all decisions without human intervention
2. **Specialization**: Each agent masters a specific domain
3. **Event-Driven**: Agents react to gameweek deadlines, price changes, injuries
4. **Learning**: System improves from historical data and outcomes
5. **Transparency**: All decisions are logged and explainable

---

## 🤖 Agent Specifications

### 1. Manager Agent (Ron Clanker)

**Role**: Central orchestrator and final decision maker

**Responsibilities**:
- Coordinate all specialist agents
- Make final team selection decisions
- Resolve conflicts between agent recommendations
- Communicate decisions in Ron Clanker's persona
- Maintain team state and history

**Decision Framework**:
```python
class RonClanker:
    def make_decision(self, agent_recommendations):
        """
        Weighs recommendations from specialist agents
        Applies tactical philosophy
        Makes final autonomous decision
        """
        # Aggregate specialist inputs
        # Apply manager's strategy bias
        # Execute decision
        # Log reasoning
        return final_decision
```

**Communication Style**: 
- "Right lads, here's the team for Saturday..."
- Old-school tactical terminology
- No-nonsense explanations
- References to "the gaffer's philosophy"

### 2. Rules Engine Agent

**Role**: Understands and enforces FPL rules

**Responsibilities**:
- Parse and internalize rule documents
- Validate all team selections against rules
- Track chip availability and usage
- Enforce budget constraints
- Calculate point predictions based on scoring rules

**Key Features**:
- Rule document parser for 2025/26 rules
- NEW: Defensive Contribution point calculator
- NEW: Revised assist rule implementation
- Budget tracking with 50% sell-on fee logic
- Formation validator
- Transfer limit enforcer

**Implementation**:
```python
class RulesEngine:
    def __init__(self, rules_documents):
        self.rules = self.parse_rules(rules_documents)
        self.scoring_system = self.extract_scoring()
        self.chip_rules = self.extract_chip_rules()
    
    def validate_team(self, team):
        """Ensures team meets all FPL rules"""
        pass
    
    def calculate_expected_points(self, player, gameweek):
        """Applies scoring rules to predict points"""
        pass
    
    def can_use_chip(self, chip_type, gameweek):
        """Validates chip timing rules"""
        pass
```

### 3. Data Collection Agent

**Role**: Gather all required data via MCP server

**Responsibilities**:
- Connect to fantasy-pl-mcp server
- Fetch player stats, prices, ownership
- Retrieve fixture schedules
- Monitor injury news
- Track price changes
- Collect historical performance data

**Data Sources**:
- FPL API (via MCP)
- Historical database
- Price change monitoring
- Fixture difficulty ratings

### 4. Player Valuation Agent

**Role**: Assess player value and expected points

**Responsibilities**:
- Calculate expected points per gameweek
- Identify undervalued players
- **NEW**: Prioritize defensive contribution earners
- Weight recent form vs. fixtures
- Consider price changes in value calculation

**Key Innovation - Defensive Contribution Focus**:
```python
class DefensiveContributionAnalyzer:
    """
    Exploits new 2025/26 rules that reward defensive work
    Most managers will miss this opportunity
    """
    def identify_dc_specialists(self, players):
        """
        Find defenders averaging 10+ CBI+Tackles
        Find midfielders averaging 12+ CBI+Tackles+Recoveries
        """
        # High-floor, consistent points
        # Lower ownership = differential
        # Better priced = budget flexibility
        return undervalued_defensive_players
```

### 5. Fixture Analysis Agent

**Role**: Evaluate upcoming fixture difficulty

**Responsibilities**:
- Rate opponent strength
- Identify fixture swings (3-6 gameweeks ahead)
- Flag double gameweeks
- Warn about blank gameweeks
- Consider home/away splits

**Forward Planning**:
```python
def analyze_fixture_run(team, gameweeks=6):
    """
    Look ahead 6 gameweeks for planning
    Weight near fixtures more heavily
    Identify optimal transfer timing
    """
    weighted_difficulty = sum(
        fixture.difficulty * (0.85 ** i) 
        for i, fixture in enumerate(next_fixtures)
    )
    return fixture_rating
```

### 6. Price Change Prediction Agent

**Role**: Predict and exploit price movements

**Responsibilities**:
- Monitor net transfer data
- Predict rises/falls 6-12 hours ahead
- Recommend timing for transfers
- Maximize team value over season

**Strategy**:
- Get ahead of price rises (buy before 0.1m increase)
- Avoid price falls (sell before 0.1m decrease)
- Build 5-10M budget advantage over season

### 7. Transfer Strategy Agent

**Role**: Plan optimal transfer sequence

**Responsibilities**:
- Decide when to use free transfers
- Calculate EV of taking points hits
- Plan multi-week transfer strategies
- **NEW**: Exploit AFCON 5 free transfer window
- Coordinate with fixture swings

**Transfer Philosophy**:
```python
def should_take_hit(transfer_benefit, hit_cost=4):
    """
    Only take -4 hit if expected gain > 4 points
    Consider fixture run, not just one gameweek
    Factor in price change gains
    """
    if expected_gain_over_3_gws > hit_cost:
        return True
    return False
```

### 8. Chip Strategy Agent

**Role**: Optimize chip timing

**Responsibilities**:
- Identify optimal Wildcard timing
- Plan Bench Boost for strong bench gameweeks
- Select Triple Captain for highest ceiling
- Use Free Hit for blank/double gameweeks

**NEW 2025/26 Rules**:
- TWO of each chip (first/second half of season)
- Must use before GW19 deadline / after GW20
- Cannot carry over to second half

---

## 🔄 System Workflow

### Daily Operations

```
03:00 AM - POST-PRICE CHANGE
├─► Data Collection Agent: Fetch updated prices, ownership
├─► Price Prediction Agent: Verify predictions, update model
└─► Store daily snapshot in database

06:00 AM - MORNING ANALYSIS
├─► Player Valuation Agent: Recalculate all player values
├─► Fixture Analysis Agent: Update difficulty ratings
└─► Generate daily opportunity report

12:00 PM - MIDDAY CHECK
├─► Injury/News Agent: Scan for team news
└─► Update affected player values

18:00 PM - EVENING ANALYSIS (Post-gameweek)
├─► All Analysis Agents: Process gameweek results
├─► Learning System: Update predictions based on actual outcomes
└─► Identify trending players for price monitoring

23:00 PM - PRE-PRICE CHANGE
├─► Price Prediction Agent: Final predictions for tonight
├─► Alert Manager Agent of likely changes
└─► Prepare pre-emptive transfer recommendations
```

### Gameweek Workflow

```
GW Deadline - 48 Hours
├─► Manager Agent initiates planning
├─► Strategy Agent: Review transfer strategy
├─► Fixture Analysis Agent: Analyze next 3 GWs
└─► Generate preliminary recommendations

GW Deadline - 24 Hours
├─► All Analysis Agents: Final data collection
├─► Player Valuation Agent: Lock in expected points
├─► Transfer Strategy Agent: Finalize transfer plan
├─► Chip Strategy Agent: Recommend chip usage
└─► Manager Agent: Review all inputs

GW Deadline - 6 Hours
├─► Rules Engine: Validate all proposals
├─► Manager Agent: Make final decisions
├─► Execute transfers
├─► Set captain/vice-captain
├─► Arrange substitution priority
└─► Ron Clanker: Announce team selection

GW Deadline - 1 Hour
├─► Final validation check
├─► Lock in team
└─► Log all decisions with reasoning

GW Complete
├─► Collect actual points scored
├─► Compare predictions vs reality
├─► Update ML models
├─► Identify what worked / what didn't
└─► Feed learning back to all agents
```

---

## 🎓 Learning & Improvement System

### Data Collection for Learning

**What to Track**:
1. Every decision made (transfers, captain, chip usage)
2. Reasoning behind each decision
3. Expected points vs actual points
4. Price predictions vs actual changes
5. Which agent recommendations were followed

**Database Schema**:
```sql
decisions (
    gameweek INT,
    decision_type TEXT, -- transfer, captain, chip, etc.
    reasoning TEXT,
    expected_value FLOAT,
    actual_value FLOAT,
    agent_source TEXT
)

player_predictions (
    player_id INT,
    gameweek INT,
    predicted_points FLOAT,
    actual_points INT,
    prediction_error FLOAT
)

learning_metrics (
    metric_name TEXT,
    gameweek INT,
    value FLOAT,
    trend TEXT
)
```

### Improvement Loop

```python
class LearningSystem:
    """
    Analyzes decisions and outcomes
    Improves agent models over time
    """
    def weekly_review(self, gameweek):
        # What did we predict correctly?
        # What did we miss?
        # Which agents performed well?
        # Update model weights
        # Adjust decision thresholds
        pass
    
    def season_analysis(self):
        # Overall performance review
        # Identify systematic biases
        # Retrain ML models
        # Update agent strategies
        pass
```

---

## 🚀 Implementation Phases

### Phase 1: Foundation (Weeks 1-2)

**Goal**: Basic autonomous system that can pick and manage a team

**Components**:
1. ✅ Project structure and MCP integration
2. ✅ Rules Engine (parse rules, validate teams)
3. ✅ Data Collection Agent (MCP client)
4. ✅ Simple Player Valuation (form + fixtures)
5. ✅ Basic Manager Agent (makes valid decisions)
6. ✅ SQLite database for state management

**Deliverable**: System can autonomously select a valid team and make basic transfers

### Phase 2: Intelligence (Weeks 3-4)

**Goal**: Add smart decision-making

**Components**:
1. ✅ Fixture Analysis Agent (difficulty ratings, fixture swings)
2. ✅ Defensive Contribution Analyzer (exploit new rules!)
3. ✅ Transfer Strategy Agent (when to take hits)
4. ✅ Captain Selection Logic
5. ✅ Price monitoring (basic)

**Deliverable**: System makes strategically sound decisions considering multiple factors

### Phase 3: Prediction (Weeks 5-8)

**Goal**: Add ML-based prediction capabilities

**Components**:
1. ✅ Collect sufficient historical data
2. ✅ Price Change Predictor (ML model)
3. ✅ Player Performance Predictor (expected points)
4. ✅ Fixture Difficulty ML model
5. ✅ Learning system (compare predictions vs outcomes)

**Deliverable**: System predicts future performance with measurable accuracy

### Phase 4: Advanced Strategy (Weeks 9-12)

**Goal**: Sophisticated multi-gameweek planning

**Components**:
1. ✅ Chip Strategy Agent (optimal timing)
2. ✅ Multi-transfer planning (3-4 GW ahead)
3. ✅ AFCON strategy (exploit 5 free transfers)
4. ✅ Template analysis (when to follow/fade)
5. ✅ Differential identification

**Deliverable**: System plans 4-6 gameweeks ahead and optimizes chip usage

### Phase 5: Mastery (Weeks 13+)

**Goal**: Compete with top FPL managers

**Components**:
1. ✅ Ensemble prediction models
2. ✅ Advanced RL for long-term planning
3. ✅ Risk management (rank-based strategy)
4. ✅ Meta-gaming (consider template, ownership)
5. ✅ Continuous learning and adaptation

**Deliverable**: System consistently finishes in top 10% of FPL managers

---

## 💻 Technical Stack

### Core Technologies

**Backend**:
- Python 3.11+
- FastAPI (async API framework)
- SQLite/PostgreSQL (data storage)
- Celery (scheduled tasks)
- Redis (task queue, caching)

**ML/AI**:
- PyTorch (neural networks)
- scikit-learn (classical ML)
- pandas/numpy (data processing)
- Ray (distributed computing for RL)

**Data & Integration**:
- fantasy-pl-mcp (FPL data via MCP)
- Beautiful Soup (web scraping supplements)
- requests (API calls)

### Project Structure

```
fpl-optimization-system/
├── agents/
│   ├── __init__.py
│   ├── manager.py              # Ron Clanker
│   ├── rules_engine.py         # Rule interpreter
│   ├── data_collector.py       # MCP client
│   ├── player_valuation.py     # Player assessment
│   ├── fixture_analysis.py     # Fixture difficulty
│   ├── price_predictor.py      # Price changes
│   ├── transfer_strategy.py    # Transfer planning
│   └── chip_strategy.py        # Chip timing
│
├── models/
│   ├── player_performance.py   # Points prediction
│   ├── price_change.py         # Price prediction
│   └── ensemble.py             # Combined models
│
├── data/
│   ├── database.py             # DB interface
│   ├── schema.sql              # DB schema
│   └── migrations/
│
├── rules/
│   ├── fpl_rules_2025.pdf      # Official rules
│   ├── parser.py               # Extract rules
│   └── scoring.py              # Points calculator
│
├── ron_clanker/
│   ├── persona.py              # Ron's personality
│   ├── communication.py        # Team announcements
│   └── tactical_philosophy.py  # Decision style
│
├── ml/
│   ├── training/               # Model training
│   ├── inference/              # Predictions
│   └── evaluation/             # Performance metrics
│
├── tasks/
│   ├── daily_jobs.py           # Scheduled tasks
│   └── gameweek_pipeline.py    # GW workflow
│
├── config/
│   ├── settings.py             # Configuration
│   └── mcp_config.json         # MCP setup
│
├── tests/
│   ├── test_agents/
│   ├── test_rules/
│   └── test_models/
│
├── notebooks/
│   └── exploration.ipynb       # Data analysis
│
├── scripts/
│   ├── setup_database.py
│   ├── backfill_data.py
│   └── train_models.py
│
├── requirements.txt
├── docker-compose.yml
├── README.md
└── CLAUDE.md                   # This file
```

---

## 🎭 Ron Clanker's Persona

### Character Background

Ron Clanker is a gruff, experienced football manager from the old school. He managed lower-league clubs in the 1970s and 80s, known for tactical discipline and getting the best out of limited resources. He's adapted to the modern game but maintains his traditional values.

### Communication Style

**Team Announcements**:
```
"Right, lads. Saturday's the day. Here's how we're lining up:

BETWEEN THE STICKS: Pickford. Solid as they come.

THE BACK FOUR: Robertson, Gabriel, Saliba, Trippier
- None of your fancy stuff. Defend first, attack when it's on.

MIDFIELD ENGINE ROOM: Rice, Saka, Palmer, Son
- Rice is key. He'll win the ball, simple as that. New rules reward 
  graft, and this lad's got it in spades. Mark my words.

UP FRONT: Haaland (C), Watkins
- Haaland's the main man. If he doesn't score, we're in trouble.

THE GAFFER'S LOGIC:
We're prioritizing the middle of the park this week. These new 
defensive contribution points? That's money in the bank, that is. 
While everyone else is chasing last week's goals, we're building 
a team that grinds out points week after week.

Rice averages 11 tackles and interceptions per match. That's 2 
points guaranteed before he's even thought about going forward.

Substitutes in order: Fabianski, Burn, Gordon, Mbeumo

Captain's got the armband because he's got City at home to 
Bournemouth. If he can't score there, he can't score anywhere.

NO CHIPS THIS WEEK. Saving the ammunition for when we need it.

Remember: Fortune favours the brave, but championships are won 
with discipline.

- Ron
```

**After a Good Gameweek**:
```
"73 points. Not bad for a day's work. The defensive contribution 
strategy is paying dividends. While the fancy dans were chasing 
premium forwards, we've been building a foundation.

Told you Rice would deliver. 2 points for defensive work, then 
goes and gets an assist. That's 9 points from a midfielder most 
people overlook. 

This is the blueprint, lads."
```

**After a Bad Gameweek**:
```
"48 points. Not good enough.

Captain blanked. That's on me. Should've seen City would struggle 
against that low block.

Making two changes for next week:
OUT: [Player who disappointed]
IN: [Replacement with better fixtures]

The fundamentals are sound. Fixtures turn in our favour next week. 
We go again.

- RC"
```

### Tactical Philosophy

1. **Defense First**: Prioritize players with high floors (defensive contribution)
2. **Value for Money**: Exploit undervalued players
3. **Plan Ahead**: Look 3-6 gameweeks forward
4. **Discipline**: Stick to the plan, avoid knee-jerk reactions
5. **Calculated Risks**: Take hits only when math supports it

---

## 📊 Success Metrics

### Performance Targets

**Short-term (First Season)**:
- Top 50% overall rank
- Positive points vs average each week
- 70%+ captain pick success rate
- 75%+ price prediction accuracy

**Medium-term (Season 2-3)**:
- Top 25% overall rank
- Consistently beat template teams
- 80%+ captain pick success rate
- Measurable learning improvements

**Long-term (Season 4+)**:
- Top 10% overall rank
- Compete with serious FPL players
- 85%+ captain pick success rate
- Demonstrate emergent strategies

### Learning Metrics

Track improvement over time:
- Prediction accuracy (expected vs actual points)
- Decision quality (compare to optimal hindsight)
- Agent performance (which agents contribute most)
- System evolution (how strategies adapt)

---

## 🔧 Development Guidelines

### For Claude Code Sessions

When developing this system:

1. **Start Simple**: Get basic autonomy working first
2. **Validate Everything**: Rules engine must be bulletproof
3. **Log Everything**: Every decision needs reasoning recorded
4. **Test Incrementally**: Verify each agent works independently
5. **Think Forward**: Design for future ML integration
6. **Embrace Failure**: System will make mistakes; learning is key

### Key Development Principles

**Autonomy Over Perfection**: 
- A working autonomous system that makes 60th percentile decisions is better than perfect code that requires human input

**Measurability**:
- Every agent output should be quantifiable
- Track prediction accuracy obsessively
- Build feedback loops into everything

**Modularity**:
- Agents should be plug-and-play
- Easy to upgrade individual agents
- Clear interfaces between components

**Transparency**:
- Log all reasoning
- Make decisions explainable
- Ron Clanker should be able to articulate "why"

---

## 🎯 Next Steps

### Immediate Actions

1. **Set up MCP server**: Get fantasy-pl-mcp running
2. **Create project structure**: Initialize repo with folder layout
3. **Build Rules Engine**: Parse official FPL rules
4. **Implement Data Collector**: Connect to MCP, fetch data
5. **Design database schema**: Plan data storage
6. **Build Manager Agent shell**: Create Ron Clanker framework

### First Milestone: Basic Autonomy

The system should be able to:
- Read the rules documents
- Fetch current FPL data
- Select a valid team (15 players, under budget)
- Pick a starting 11 with captain
- Make 1 transfer per gameweek
- Provide reasoning for decisions in Ron's voice

This is the foundation. Everything else builds on this.

---

## 📚 Resources & References

### FPL Rules & Data
- Official Rules: `/rules/fpl_rules_2025.pdf`
- FPL API: `https://fantasy.premierleague.com/api/`
- MCP Server: `https://github.com/rishijatia/fantasy-pl-mcp`

### Multi-Agent Systems Research
- Hierarchical orchestration patterns
- Event-driven multi-agent coordination
- Agent specialization and communication
- Autonomous decision-making frameworks

### Machine Learning for Games
- Deep reinforcement learning for game agents
- Multi-agent reinforcement learning (MARL)
- Ensemble prediction models
- Transfer learning and continuous improvement

---

## 🤝 Human-System Interaction

### What Humans Do

- **Enhance Data Inputs**: Add new data sources
- **Improve Agent Logic**: Refine decision algorithms  
- **Train Models**: Help with ML model development
- **Monitor Performance**: Track metrics and identify issues
- **Expand Capabilities**: Add new agents or features

### What Humans DON'T Do

- ❌ Pick the team
- ❌ Make transfers
- ❌ Choose captain
- ❌ Decide on chips
- ❌ Override Ron Clanker's decisions

**The system is fully autonomous. Ron's in charge.**

---

## 📝 Documentation Standards

All code should include:

1. **Agent Docstrings**: Clear explanation of agent purpose
2. **Decision Logging**: Why each decision was made
3. **Metric Tracking**: Quantitative performance measures
4. **Error Handling**: Graceful failure and recovery
5. **Testing**: Unit tests for all critical logic

---

*"The best managers adapt, but they never forget the fundamentals. Hard work beats talent when talent doesn't work hard. Now let's get out there and show these young guns how it's done."*

*- Ron Clanker*

---

**Version**: 1.0  
**Last Updated**: October 2025  
**Status**: Foundation Phase  
**Next Review**: After Phase 1 completion
- we should use the beads plugin and not markdown files for planning
- don't give estimated durations for task completions - e.g. week 1 for this, week 2 for that, 4-6 weeks for the other
- from the bd quickstart command

bd - Dependency-Aware Issue Tracker

Issues chained together like beads.

GETTING STARTED
  bd init   Initialize bd in your project
            Creates .beads/ directory with project-specific database
            Auto-detects prefix from directory name (e.g., myapp-1, myapp-2)

  bd init --prefix api   Initialize with custom prefix
            Issues will be named: api-1, api-2, ...

CREATING ISSUES
  bd create "Fix login bug"
  bd create "Add auth" -p 0 -t feature
  bd create "Write tests" -d "Unit tests for auth" --assignee alice

VIEWING ISSUES
  bd list       List all issues
  bd list --status open  List by status
  bd list --priority 0  List by priority (0-4, 0=highest)
  bd show bd-1       Show issue details

MANAGING DEPENDENCIES
  bd dep add bd-1 bd-2     Add dependency (bd-2 blocks bd-1)
  bd dep tree bd-1  Visualize dependency tree
  bd dep cycles      Detect circular dependencies

DEPENDENCY TYPES
  blocks  Task B must complete before task A
  related  Soft connection, doesn't block progress
  parent-child  Epic/subtask hierarchical relationship
  discovered-from  Auto-created when AI discovers related work

READY WORK
  bd ready       Show issues ready to work on
            Ready = status is 'open' AND no blocking dependencies
            Perfect for agents to claim next work!

UPDATING ISSUES
  bd update bd-1 --status in_progress
  bd update bd-1 --priority 0
  bd update bd-1 --assignee bob

CLOSING ISSUES
  bd close bd-1
  bd close bd-2 bd-3 --reason "Fixed in PR #42"

DATABASE LOCATION
  bd automatically discovers your database:
    1. --db /path/to/db.db flag
    2. $BEADS_DB environment variable
    3. .beads/*.db in current directory or ancestors
    4. ~/.beads/default.db as fallback

AGENT INTEGRATION
  bd is designed for AI-supervised workflows:
    • Agents create issues when discovering new work
    • bd ready shows unblocked work ready to claim
    • Use --json flags for programmatic parsing
    • Dependencies prevent agents from duplicating effort

DATABASE EXTENSION
  Applications can extend bd's SQLite database:
    • Add your own tables (e.g., myapp_executions)
    • Join with issues table for powerful queries
    • See database extension docs for integration patterns:
      https://github.com/steveyegge/beads/blob/main/EXTENDING.md

GIT WORKFLOW (AUTO-SYNC)
  bd automatically keeps git in sync:
    • ✓ Export to JSONL after CRUD operations (5s debounce)
    • ✓ Import from JSONL when newer than DB (after git pull)
    • ✓ Works seamlessly across machines and team members
    • No manual export/import needed!
  Disable with: --no-auto-flush or --no-auto-import

Ready to start!
Run bd create "My first issue" to create your first issue.
- docker-compose command has been replaced by docker compose (no hyphen)