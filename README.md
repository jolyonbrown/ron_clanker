# Ron Clanker's FPL Management System

The AI FPL manager. Sunbed not included.

![Image of Ron Clanker,wearing 70s style football managers clothing, sheepskin jacket and smoking a cigar. On the sidelines of the pitch showing no emotion](https://github.com/jolyonbrown/ron_clanker/blob/main/ron_clanker/RON_CLANKER.png?raw=true)

## Overview

Ron Clanker is a fully autonomous Fantasy Premier League management system built on event-driven multi-agent architecture. The system makes ALL team decisions independently, exploiting the new 2025/26 Defensive Contribution rules for competitive advantage.

**Current Status**: Phase 3 - ML Predictions & News Intelligence ✅
**Live Status**: GW9 team submitted (Oct 26, 2025)
**Deployment**: Raspberry Pi 3B (production mode)
**Database**: SQLite + Redis event bus
**Performance**: 64.6 expected points (GW9)

## Completed Features

### Phase 1: Foundation ✅
- ✅ SQLite database with complete schema
- ✅ FPL Rules Engine (2025/26 DC rules, assists, bonus points)
- ✅ Data collection from FPL API
- ✅ Basic player valuation and DC analysis
- ✅ Automated backup system
- ✅ Docker infrastructure (Redis event bus)

### Phase 2: Intelligence & Events ✅
- ✅ **Scout Agent**: Multi-source intelligence gathering
  - RSS feeds (Sky Sports, BBC Sport, The Athletic)
  - Website monitoring (premierinjuries.com)
  - YouTube analysis (FPL Harry, Let's Talk FPL)
- ✅ **Hugo (Transfer Strategy Agent)**: Event-driven transfer planning
- ✅ **Event Bus Architecture**: Redis pub/sub for agent coordination
- ✅ **Specialist Analysts**:
  - Priya (Player Valuation): DC specialist identification
  - Sanjay (Fixture Analysis): Difficulty ratings, fixture swings
  - DC Analyst: Defensive contribution deep-dive
  - xG Analyst: Expected goals analysis
- ✅ **GW8 Squad Selection**: First autonomous team pick (£99.0m, validated)
- ✅ **Ron's Voice**: Team announcements in classic manager style

### Phase 3: ML Predictions & News Intelligence ✅
- ✅ **ML Prediction System**: PyTorch models for player performance
  - 591 players predicted across 4 gameweeks
  - Feature engineering: form, fixtures, DC metrics, xG, opponent strength
  - Multi-gameweek transfer optimization (GW9-12 lookahead)
- ✅ **News Intelligence System**: Claude API-powered news processing
  - Press conference analysis (60 players tracked for GW9)
  - Email newsletter parsing (FPL content extraction)
  - YouTube video intelligence gathering
  - Injury/doubt/availability tracking with confidence scores
  - News-adjusted predictions (100 players adjusted for GW9)
- ✅ **Premier League Scraper**: Official PL website monitoring
- ✅ **Transfer Optimizer**: Multi-gameweek expected value analysis
- ✅ **GW9 Team Submitted**: Live FPL entry (64.6 xP, 4-defender DC strategy)
- ✅ **Slack Integration**: Automated team announcements in Ron's voice

## Quick Start

### 1. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Redis (event bus)

```bash
docker compose up -d redis
```

### 4. Set up database and sync FPL data

```bash
# Initialize database schema
venv/bin/python scripts/setup_database.py

# Sync latest FPL data (743 players, 38 gameweeks)
venv/bin/python scripts/sync_fpl_data.py
```

### 5. Test the system

```bash
# Run full system test (Scout, Hugo, event bus)
venv/bin/python scripts/test_full_system.py

# Or run individual agents
venv/bin/python -m agents.scout
venv/bin/python scripts/select_gw8_squad.py
```

### 6. Daily backup (optional, recommended)

```bash
# Manual backup
venv/bin/python scripts/backup_database.py

# Or set up automated daily backups via cron (see DEPLOYMENT.md)
```

## Project Structure

```
ron_clanker/
├── agents/                    # Specialist agents (event-driven)
│   ├── base_agent.py          # Base agent class with event bus
│   ├── scout.py               # Scout - intelligence gathering
│   ├── transfer_strategy.py   # Hugo - transfer planning
│   ├── dc_analyst.py          # DC specialist analyst
│   ├── fixture_analyst.py     # Sanjay - fixture analysis
│   ├── value_analyst.py       # Priya - player valuation
│   ├── xg_analyst.py          # xG analyst
│   └── manager_agent_v2.py    # Ron Clanker - decision maker
├── intelligence/              # Multi-source intelligence
│   ├── rss_monitor.py         # RSS feed monitoring
│   ├── website_monitor.py     # Website scraping
│   ├── youtube_monitor.py     # YouTube analysis
│   ├── news_processor.py      # Claude API news intelligence
│   └── premierleague_scraper.py # Official PL website scraping
├── rules/                     # FPL rules engine
│   ├── scoring.py             # Points calculation (DC, assists, bonus)
│   └── rules_engine.py        # Validation engine
├── infrastructure/            # Event-driven infrastructure
│   ├── events.py              # Event definitions
│   └── event_bus.py           # Redis pub/sub
├── ml/                        # Machine learning models
│   ├── prediction/
│   │   ├── model.py           # PyTorch prediction model
│   │   ├── features.py        # Feature engineering
│   │   └── news_adjustment.py # News intelligence integration
│   └── training/              # Model training scripts
├── data/                      # Database & storage
│   ├── database.py            # SQLite interface
│   ├── schema.sql             # Database schema
│   ├── ron_clanker.db         # Live database (~300KB)
│   ├── news_input/            # Press conferences, newsletters
│   └── backups/               # Automated backups (30-day retention)
├── scripts/                   # Operational scripts
│   ├── sync_fpl_data.py       # Sync from FPL API
│   ├── show_gw9_selection.py  # GW9 team selection
│   ├── process_news_from_directory.py # Batch news processing
│   ├── process_manual_news.py # Manual news input
│   ├── train_models_quick.py  # ML model training
│   ├── backup_database.py     # Backup automation
│   └── test_full_system.py    # System integration test
├── docker-compose.yml         # Redis infrastructure
├── CLAUDE.md                  # Full system specification
├── ARCHITECTURE.md            # Database strategy
└── DEPLOYMENT.md              # Deployment guide (RPi, containers)
```

## Key Competitive Advantage

**2025/26 Defensive Contribution Rules**: Ron Clanker specifically targets defenders averaging 10+ tackles/interceptions/clearances and midfielders averaging 12+ defensive actions. This NEW scoring category is overlooked by most managers but provides 2 guaranteed points per game - a massive edge.

## Autonomous Decision Making

Ron Clanker makes all decisions independently:
- ✅ **Team Selection**: 15 players, £100m budget, FPL rules validated
- ✅ **Formation**: Starting XI + bench order (4-3-3, 3-5-2, 4-4-2, etc.)
- ✅ **Captain Choice**: ML-predicted expected points + fixture analysis
- ✅ **Transfer Strategy**: Multi-gameweek optimizer (4-week lookahead)
- ✅ **Intelligence Gathering**: Press conferences, newsletters, YouTube
- ✅ **DC Exploitation**: Targets high-floor defenders and midfielders
- ✅ **News Intelligence**: Claude API processes 60+ players per gameweek
- ✅ **ML Predictions**: PyTorch models predict 591 players across 4 GWs
- ⏳ **Chip Timing**: Planned for Phase 4
- ⏳ **Price Prediction**: Net transfer tracking planned for Phase 4

## Development

### Running tests

```bash
# All tests
pytest

# With coverage
pytest --cov=agents --cov=rules --cov=data

# Specific test file
pytest tests/test_rules/test_scoring.py
```

### Code quality

```bash
# Format code
black .

# Lint
flake8 .

# Type checking
mypy agents rules
```

## Next Steps (Phase 4)

- [ ] **Chip Strategy Agent**: Optimal timing for Wildcard, Bench Boost, Triple Captain
- [ ] **Price Predictor**: Net transfer tracking, predict rises/falls 6-12 hours ahead
- [ ] **Advanced xG Analysis**: Shot quality, overperformance detection
- [ ] **Ownership Tracking**: Template analysis, differential identification
- [ ] **Pre-Deadline Automation**: Autonomous squad submission 1 hour before GW
- [ ] **Performance Learning**: Compare predictions vs actuals, improve models
- [ ] **Model Retraining**: Weekly model updates based on actual results
- [ ] **Ensemble Models**: Combine multiple prediction approaches

See CLAUDE.md for full roadmap and architecture.

## Deployment

**Current Setup**: Raspberry Pi 3B (development mode)

**Architecture**:
- **Infrastructure**: Redis container (event bus + cache)
- **Database**: SQLite file-based (300KB, persistent)
- **Agents**: Python scripts (not containerized for Phase 1-2)
- **Memory Usage**: ~300MB (excellent for RPi)
- **System Load**: < 2.0 (very comfortable)

**Why Python Scripts Instead of Containers?**
The original plan was to containerize all agents, but building multiple Docker images simultaneously caused the RPi to lock up (load > 20). For Phase 1-2 development, running agents as Python scripts provides:
- Fast iteration (no rebuild required)
- Low resource usage (768MB RAM saved)
- Easy debugging
- Full event-driven architecture still works (Redis handles pub/sub)

See DEPLOYMENT.md for full deployment strategy, backup procedures, and migration path to containerized production deployment in Phase 3.

## Ron's Philosophy

> "Hard work beats talent when talent doesn't work hard. While everyone else chases last week's goals, we're building a team that grinds out points week after week."
>
> *- Ron Clanker*

## License

MIT License - See LICENSE file

---

**Ron Clanker is ready to manage. Let's show these young guns how it's done.**
