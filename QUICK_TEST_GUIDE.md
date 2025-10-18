# Quick Test Guide - See Ron's Logs in Action

## TL;DR - Run These Commands

```bash
# 1. Simple step-by-step demo (30 seconds)
venv/bin/python scripts/simple_demo.py

# 2. Full system test (1 minute)
venv/bin/python scripts/test_full_system.py

# 3. Save logs to file
venv/bin/python scripts/test_full_system.py > logs/my_test.log 2>&1
cat logs/my_test.log

# 4. Use the logging helper script
./scripts/run_with_logging.sh scripts/simple_demo.py
```

## Where Logs Appear

### 1. Console (Real-time)

When you run any script, you see logs like:

```
19:29:22 | agents.scout              | Scout: Loaded 743 players into cache
19:29:23 | intelligence.rss_monitor  | RSSMonitor: Found 1 items from bbc_sport_football
19:29:23 | agents.transfer_strategy  | Hugo (Transfer Strategist) initialized
```

**Format**: `TIME | COMPONENT | MESSAGE`

### 2. Log Files (Saved)

In the `logs/` directory:

```bash
$ ls -lh logs/
full_system_test_20251017_190339.log  # 7.3K - Full system test
```

### 3. Event Bus (Agent Communication)

Redis pub/sub events (not files):
- Scout → Hugo: "Player injured"
- Hugo → Ron: "Recommend transfer"
- Ron → All: "Team selected"

## What We Just Demonstrated

### Simple Demo Output:

```
[STEP 1] Starting Scout (Intelligence Gathering Agent)
19:29:22 | agents.scout | Scout (Intelligence Agent) initialized
19:29:22 | agents.scout | Scout: Loaded 743 players into cache

[STEP 2] Gathering Intelligence from External Sources
19:29:23 | intelligence.rss_monitor | RSSMonitor: Found 1 items from bbc_sport_football
Found 1 intelligence items:
  • [INJURY] Man Utd: I can't bank on three years at Man Utd - Amorim...

[STEP 3] Starting Hugo (Transfer Strategy Agent)
19:29:23 | agents.transfer_strategy | Hugo (Transfer Strategist) initialized

[STEP 4] Checking Infrastructure Status
19:29:23 | __main__ | ✅ Redis event bus: Connected and healthy
```

**Every line with `|` is a log entry showing real agent activity!**

## Key Log Sources by Component

| Component | Logger Name | What It Logs |
|-----------|------------|-------------|
| **Scout** | `agents.scout` | Intelligence gathering, RSS checks, player matching |
| **Hugo** | `agents.transfer_strategy` | Transfer recommendations, squad analysis |
| **Ron** | `agents.manager_agent_v2` | Final decisions, team selections |
| **Data Collector** | `agents.data_collector` | FPL API calls, cache hits |
| **RSS Monitor** | `intelligence.rss_monitor` | Feed checks, items found |
| **Classifier** | `intelligence.intelligence_classifier` | Player matching, severity scoring |
| **Event Bus** | `agents.base_agent` | Agent initialization, event subscriptions |

## Step-by-Step: Run & Review

### 1. Run the simple demo

```bash
venv/bin/python scripts/simple_demo.py
```

**Watch for**:
- Timestamp on each log line (shows sequence)
- Component name (shows which agent is working)
- Message (shows what's happening)

### 2. Save output to review later

```bash
venv/bin/python scripts/simple_demo.py > logs/demo.log 2>&1
cat logs/demo.log | grep "agents\."
```

This filters to show only agent activity.

### 3. Full system test (comprehensive)

```bash
venv/bin/python scripts/test_full_system.py
```

**Tests**:
- ✅ Scout initialization (1651 players)
- ✅ RSS monitoring (BBC, Sky Sports)
- ✅ Intelligence classification
- ✅ Hugo's injury response
- ✅ Event bus (Redis)
- ✅ Docker infrastructure

### 4. Run with enhanced logging helper

```bash
./scripts/run_with_logging.sh scripts/test_full_system.py
```

This automatically:
- Timestamps the log file
- Shows output in console AND saves to file
- Reports file size when done

## Common Patterns to Look For

### Agent Initialization

```
19:29:22 | agents.base_agent | scout initialized
19:29:22 | agents.scout | Scout (Intelligence Agent) initialized
```

### Intelligence Gathering

```
19:29:22 | intelligence.rss_monitor | RSSMonitor: Checking bbc_sport_football...
19:29:23 | intelligence.rss_monitor | RSSMonitor: Found 1 items from bbc_sport_football
```

### Player Matching

```
19:29:22 | agents.scout | Scout: Loaded 743 players into cache and classifier
19:29:22 | intelligence.intelligence_classifier | IntelligenceClassifier initialized with 1651 players
```

### Event Bus Activity

```
19:29:23 | agents.base_agent | hugo initialized
19:29:23 | __main__ | ✅ Redis event bus: Connected and healthy
```

## Grep Cheatsheet

```bash
# All agent logs
grep "agents\." logs/demo.log

# Only Scout activity
grep "agents.scout" logs/demo.log

# Intelligence gathering
grep "intelligence\." logs/demo.log

# Errors and warnings
grep -E "ERROR|WARNING" logs/demo.log

# Show with line numbers
grep -n "initialized" logs/demo.log

# Count occurrences
grep -c "Found" logs/demo.log
```

## Next Steps

### See Ron Make a Decision

Run the autonomous team selection demo:

```bash
venv/bin/python scripts/demo_ron_autonomous.py
```

This shows:
1. All specialist agents analyzing data
2. Publishing recommendations via event bus
3. Ron synthesizing inputs
4. Final autonomous team selection
5. Team announcement in Ron's voice

**Note**: This is interactive and waits for ENTER before proceeding.

### Monitor in Real-Time

```bash
# Terminal 1: Run system
venv/bin/python scripts/test_full_system.py > logs/live.log 2>&1 &

# Terminal 2: Watch logs
tail -f logs/live.log
```

Press Ctrl+C to stop watching.

## Troubleshooting

### "No logs appearing"

Make sure you're looking at the right stream:

```bash
# Capture both stdout AND stderr
venv/bin/python script.py 2>&1
```

### "Redis not connected"

```bash
# Check status
docker compose ps

# Start if needed
docker compose up -d redis

# Check logs
docker compose logs redis
```

### "Can't find log file"

```bash
# List all logs
ls -lht logs/

# Search for recent logs
find logs/ -name "*.log" -mtime -1
```

## Documentation

**Full details**: See `docs/LOGGING_AND_MONITORING.md` for:
- Complete logging configuration
- Production setup
- Event bus monitoring
- Log rotation
- Troubleshooting guide

## Summary

**Logs appear in**:
1. ✅ Console (always)
2. ✅ Files in `logs/` (when redirected)
3. ✅ Redis events (agent communication)

**Easiest way to see everything**:
```bash
venv/bin/python scripts/simple_demo.py
```

**Most comprehensive test**:
```bash
./scripts/run_with_logging.sh scripts/test_full_system.py
```

**Review saved logs**:
```bash
ls -lht logs/
cat logs/full_system_test_*.log
```

---

*Ron Clanker: "You can't improve what you don't measure. Check the logs, learn, adapt."*
