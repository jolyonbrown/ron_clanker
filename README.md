# Ron Clanker's FPL Management System

The AI FPL manager. Sunbed not included.

![Image of Ron Clanker,wearing 70s style football managers clothing, sheepskin jacket and smoking a cigar. On the sidelines of the pitch showing no emotion](/ron_clanker/blob/main/ron_clanker/RON_CLANKER.png)

## Overview

Ron Clanker is a fully autonomous Fantasy Premier League management system built on multi-agent architecture. The system makes ALL team decisions independently, exploiting the new 2025/26 Defensive Contribution rules for competitive advantage.

**Current Status**: Phase 1 - Foundation Complete ✅

## Phase 1 Features

- ✅ Database schema and management
- ✅ FPL Rules Engine (including NEW 2025/26 defensive contribution rules)
- ✅ Data Collection Agent (MCP integration ready)
- ✅ Player Valuation Agent (with DC advantage detection)
- ✅ Manager Agent (Ron Clanker) - autonomous decision-maker
- ✅ Ron Clanker's persona and communication style
- ✅ Core test suite

## Quick Start

### 1. Set up the database

```bash
python scripts/setup_database.py
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run tests

```bash
pytest
```

### 4. Docker deployment

```bash
docker compose build
docker compose up
```

## Project Structure

```
ron_clanker/
├── agents/              # Specialist agents
│   ├── manager.py       # Ron Clanker - central decision maker
│   ├── data_collector.py
│   └── player_valuation.py
├── rules/               # FPL rules engine
│   ├── scoring.py       # Points calculation (inc. DC rules)
│   └── rules_engine.py  # Team/transfer validation
├── ron_clanker/         # Ron's persona
│   └── persona.py
├── data/                # Database layer
│   ├── database.py
│   └── schema.sql
├── config/              # Configuration
│   └── settings.py
├── tests/               # Test suite
└── scripts/             # Utility scripts
```

## Key Competitive Advantage

**2025/26 Defensive Contribution Rules**: Ron Clanker specifically targets defenders averaging 10+ tackles/interceptions/clearances and midfielders averaging 12+ defensive actions. This NEW scoring category is overlooked by most managers but provides 2 guaranteed points per game - a massive edge.

## Autonomous Decision Making

Ron Clanker makes all decisions:
- ✅ Team selection (15 players within budget)
- ✅ Captain choice (expected points based)
- ✅ Weekly transfers (value-driven)
- ⏳ Chip timing (Phase 4)
- ⏳ Formation changes (Phase 2)

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

## Next Steps (Phase 2)

- [ ] Fixture Analysis Agent
- [ ] Enhanced DC detection with real tackle/interception data
- [ ] Transfer Strategy Agent
- [ ] Captain Selection improvements
- [ ] Price monitoring

## Ron's Philosophy

> "Hard work beats talent when talent doesn't work hard. While everyone else chases last week's goals, we're building a team that grinds out points week after week."
>
> *- Ron Clanker*

## License

MIT License - See LICENSE file

---

**Ron Clanker is ready to manage. Let's show these young guns how it's done.**
