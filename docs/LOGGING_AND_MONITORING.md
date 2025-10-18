# Ron Clanker - Logging & Monitoring Guide

## Overview

This guide explains where Ron Clanker's logs appear, how to capture them, and how to run end-to-end system tests with full visibility.

## Where Logs Appear

### 1. Console Output (stdout/stderr)

All agents log to console by default using Python's `logging` module:

```python
# From agents/manager.py:18
logger = logging.getLogger(__name__)
logger.info("Ron Clanker initialized. Ready to manage.")
```

**Log format** (configured in scripts):
```
2025-10-17 19:03:42,484 - agents.scout - INFO - Scout (Intelligence Agent) initialized
│                       │              │       │
│                       │              │       └─ Message
│                       │              └─ Log level
│                       └─ Logger name (module)
└─ Timestamp
```

### 2. Log Files

Logs can be captured to files in the `logs/` directory:

**Configuration** (from config/settings.py:25):
```python
LOG_FILE = os.getenv('LOG_FILE', str(BASE_DIR / 'logs' / 'ron_clanker.log'))
```

**Current log files**:
```bash
$ ls -lh logs/
full_system_test_20251017_190339.log  # Full system test output (7.3K)
```

### 3. Event Bus (Redis)

Agent-to-agent communication happens via Redis pub/sub:
- Not traditional logs
- Events like `INJURY_INTELLIGENCE`, `TRANSFER_RECOMMENDED`
- Visible in agent logs when published/received

**Check Redis status**:
```bash
$ docker compose ps
NAME        STATUS
ron_redis   Up 2 hours (healthy)
```

## Running End-to-End Tests

### Full System Test

Tests all components: Scout, Hugo, Event Bus, Intelligence Gathering

```bash
# Run with console output
venv/bin/python scripts/test_full_system.py

# Run with log file capture
./scripts/run_with_logging.sh scripts/test_full_system.py

# Or manually:
venv/bin/python scripts/test_full_system.py > logs/system_test.log 2>&1
```

**What it tests**:
1. ✅ Scout agent initialization (1651 players loaded)
2. ✅ RSS feed monitoring (BBC Sport, Sky Sports, The Athletic)
3. ✅ Intelligence classification (confidence scoring, severity)
4. ✅ Hugo's injury response system
5. ✅ Event bus connectivity (Redis)
6. ✅ Docker infrastructure status

**Sample output**:
```
================================================================================
🔍 SCOUT INTELLIGENCE GATHERING TEST
================================================================================

1. Loading player cache for fuzzy name matching...
   ✓ Loaded 1651 player names

2. Testing RSS feed monitoring (BBC Sport, Sky Sports)...
   ✓ Found 1 intelligence items from RSS feeds

   Recent intelligence from RSS:
   - [INJURY] Man Utd: I can't bank on three years at Man Utd - Amorim...

5. Testing IntelligenceClassifier...
   ✓ Classifier operational
   • Test: 'Cole Palmer confirmed out for six weeks'
     - Player matched: cole palmer (ID: 235)
     - Confidence: 100%
     - Severity: HIGH
     - Actionable: ✅ YES
```

### Daily Monitoring

Monitors FPL data, prices, injuries, squad impact:

```bash
venv/bin/python scripts/daily_monitor.py
```

**What it monitors**:
- Latest FPL data sync
- Price changes (rises/falls)
- Injury/availability updates
- Squad player impact alerts

### Autonomous Team Selection Demo

Full autonomous decision-making with Ron:

```bash
venv/bin/python scripts/demo_ron_autonomous.py
```

**What it does**:
1. Starts specialist analysts (Digger, Priya, Sophia, Jimmy)
2. Each agent analyzes their domain (DC, fixtures, xG, value)
3. Publishes analysis events via event bus
4. Ron (Manager Agent) synthesizes recommendations
5. Makes final autonomous team selection
6. Announces decisions in Ron's voice

## Step-by-Step System Flow

### Complete Agent Interaction (from actual test run)

```
[00:00] Scout Initialization
2025-10-17 19:03:41,338 - agents.base_agent - INFO - scout initialized
2025-10-17 19:03:42,483 - intelligence.website_monitor - INFO - WebsiteMonitor initialized
2025-10-17 19:03:42,484 - intelligence.rss_monitor - INFO - RSSMonitor initialized
2025-10-17 19:03:42,484 - intelligence.youtube_monitor - INFO - YouTubeMonitor initialized

[00:01] Player Cache Loading
2025-10-17 19:03:42,506 - agents.scout - INFO - Scout: Loaded 743 players into cache and classifier

[00:02] RSS Feed Monitoring
2025-10-17 19:03:42,508 - intelligence.rss_monitor - INFO - RSSMonitor: Checking bbc_sport_football...
2025-10-17 19:03:43,075 - intelligence.rss_monitor - INFO - RSSMonitor: Found 1 items from bbc_sport_football
2025-10-17 19:03:43,076 - intelligence.rss_monitor - INFO - RSSMonitor: Checking sky_sports_football...
2025-10-17 19:03:43,284 - intelligence.rss_monitor - INFO - RSSMonitor: Found 0 items from sky_sports_football

[00:03] Hugo (Transfer Strategy) Initialization
2025-10-17 19:03:43,510 - agents.base_agent - INFO - hugo initialized
2025-10-17 19:03:43,511 - agents.transfer_strategy - INFO - Hugo (Transfer Strategist) initialized

[Result] System Operational
✅ All agents initialized
✅ Intelligence gathering working
✅ Event bus connected (Redis healthy)
✅ Ready for autonomous decision-making
```

## Monitoring Logs in Real-Time

### Watch logs as they happen

```bash
# Run test in background, tail the log
venv/bin/python scripts/test_full_system.py > logs/test.log 2>&1 &
tail -f logs/test.log
```

### Filter logs by level

```bash
# Show only errors
venv/bin/python scripts/test_full_system.py 2>&1 | grep ERROR

# Show only agent activity
venv/bin/python scripts/test_full_system.py 2>&1 | grep "agents\."
```

### Configure log level

Set via environment variable:

```bash
# More verbose (DEBUG level)
LOG_LEVEL=DEBUG venv/bin/python scripts/test_full_system.py

# Less verbose (WARNING level)
LOG_LEVEL=WARNING venv/bin/python scripts/daily_monitor.py
```

## Key Log Locations by Agent

| Agent | Logger Name | Key Log Messages |
|-------|------------|-----------------|
| Scout | `agents.scout` | Player cache loaded, Intelligence found, RSS checks |
| Hugo | `agents.transfer_strategy` | Transfer recommendations, Squad impact |
| Ron (Manager) | `agents.manager_agent_v2` | Team selections, Final decisions |
| Data Collector (Maggie) | `agents.data_collector` | FPL API fetches, Cache hits/misses |
| DC Analyst (Digger) | `agents.dc_analyst` | DC performers identified, Analysis complete |
| Fixture Analyst (Priya) | `agents.fixture_analyst` | Fixture difficulty, Swings detected |
| xG Analyst (Sophia) | `agents.xg_analyst` | xG analysis, Overperformers found |
| Value Analyst (Jimmy) | `agents.value_analyst` | Value rankings, Transfer targets |

## Event Bus Monitoring

### Check Redis events

```bash
# Monitor all events in real-time
redis-cli -p 6379 MONITOR

# Subscribe to specific event channel
redis-cli -p 6379 SUBSCRIBE "fpl_event:INJURY_INTELLIGENCE"
```

### Event Types Published

From `infrastructure/events.py`:

| Event Type | Published By | Consumed By | Payload |
|-----------|-------------|------------|---------|
| `INJURY_INTELLIGENCE` | Scout | Hugo | Player ID, Severity, Confidence |
| `ROTATION_RISK` | Scout | Hugo | Player ID, Risk level |
| `TRANSFER_RECOMMENDED` | Hugo | Ron | Player out/in, Expected gain |
| `TEAM_SELECTED` | Ron | All | Final team, Reasoning |
| `DATA_REFRESHED` | Maggie | All | Bootstrap data |

## Troubleshooting

### No logs appearing

**Check logging configuration**:
```python
# In your script
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Logs directory empty

Logs only saved when explicitly redirected:
```bash
# This saves logs
venv/bin/python script.py > logs/output.log 2>&1

# This does not
venv/bin/python script.py
```

### Redis not connected

```bash
# Check Docker status
docker compose ps

# Start if not running
docker compose up -d redis

# Check Redis logs
docker compose logs redis
```

### Agent not logging

Check logger is created:
```python
import logging
logger = logging.getLogger(__name__)  # Must be after imports
```

## Production Logging Setup

For automated/scheduled runs (Phase 3), set up proper logging:

### 1. Configure logging in settings.py

```python
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/ron_clanker.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'standard',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}
```

### 2. Cron job with logging

```bash
# crontab -e
0 3 * * * cd /home/jolyon/ron_clanker && ./scripts/run_with_logging.sh scripts/daily_monitor.py
```

### 3. Log rotation

```bash
# /etc/logrotate.d/ron_clanker
/home/jolyon/ron_clanker/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 jolyon jolyon
}
```

## Summary

**Logs currently appear in**:
1. ✅ Console (all scripts)
2. ✅ `logs/` directory when redirected
3. ✅ Redis event bus (agent communication)

**Best way to see full system working**:
```bash
./scripts/run_with_logging.sh scripts/test_full_system.py
```

**Check specific logs**:
```bash
# Full system test
cat logs/full_system_test_*.log

# Grep for specific agent
grep "agents.scout" logs/*.log

# Show only warnings/errors
grep -E "WARNING|ERROR" logs/*.log
```

**Live monitoring**:
```bash
# Terminal 1: Run system
venv/bin/python scripts/demo_ron_autonomous.py > logs/live.log 2>&1

# Terminal 2: Watch logs
tail -f logs/live.log | grep --line-buffered "agents\."
```

---

*Ron Clanker logging: Every decision tracked, every move logged. That's how you improve.*
