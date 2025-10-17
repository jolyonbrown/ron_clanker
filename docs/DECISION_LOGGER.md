# Decision Logger - Real-time Visibility

The decision logger subscribes to Ron's event bus and displays all important decisions in real-time.

## What It Logs

**📊 Data Events:**
- Data refreshes (daily at 6AM)
- Price changes

**🎯 Planning Events:**
- Gameweek planning triggers (48h/24h/6h before deadline)

**🤖 Agent Analysis:**
- Digger (DC Analyst) - Top defensive contributors
- Priya (Fixture Analyst) - Fixture difficulty
- Sophia (xG Analyst) - Expected goals analysis
- Jimmy (Value Analyst) - Top 5 value picks

**🏆 Big Decisions:**
- Team selections (full squad with reasoning)
- Transfers (in/out with reasoning)
- Captain choices
- Chip usage

**🏁 Reviews:**
- Gameweek completion and post-match analysis

## Running the Logger

### Option 1: Docker (Recommended)

The logger runs automatically as part of the Docker stack:

```bash
docker compose up -d decision_logger
```

View the logs in real-time:

```bash
docker compose logs -f decision_logger
```

### Option 2: Standalone (tmux/screen)

Run in a dedicated terminal session:

```bash
# Start a tmux session
tmux new -s ron_logger

# Inside tmux, run the logger
cd /home/jolyon/ron_clanker
source venv/bin/activate
python scripts/decision_logger.py

# Detach from tmux: Ctrl+B, then D
# Reattach later: tmux attach -t ron_logger
```

### Option 3: Background Process

```bash
cd /home/jolyon/ron_clanker
source venv/bin/activate
nohup python scripts/decision_logger.py > logs/logger_console.log 2>&1 &
```

Stop it with:
```bash
pkill -f decision_logger.py
```

## Log Files

Logs are written to:
```
logs/decisions_YYYYMMDD.log
```

A new log file is created each day. This includes ALL logged events with timestamps.

## Output Format

### Team Selection Example:
```
🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆
[13:45:23] RON'S TEAM SELECTION - GAMEWEEK 8
🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆

Total Cost: £96.3m

GKP:
  • Roefs £4.6m

DEF:
  • Senesi £5.0m
  • Gabriel £6.3m
  • Guéhi £4.9m

MID:
  • Semenyo £7.9m (C)
  • Caicedo £5.8m
  • Sarr £6.5m
  • Cullen £5.0m
  • Ndiaye £6.5m

FWD:
  • Haaland £14.5m (VC)
  • Thiago £6.1m

Captain: Semenyo
Vice-Captain: Haaland

Ron's Reasoning:
Building a foundation with DC specialists. Gabriel and Caicedo earn
2pts/week from defensive work before we even count clean sheets.
That's the edge.

🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆
```

### Analysis Completion Example:
```
[06:00:15] 📊 DATA REFRESH - GW8 (scheduled_daily_refresh)
[06:00:32] 🛡️  DIGGER: DC Analysis Complete (GW8)
  Top DC picks:
    1. Gabriel (14 DC pts)
    2. Caicedo (13 DC pts)
    3. Senesi (12 DC pts)
[06:00:45] 💎 JIMMY: Value Rankings Complete (GW8)
  Top 5 value picks:
    1. Semenyo (MID) £7.9m - Value: 49.8
    2. Haaland (FWD) £14.5m - Value: 45.2
    3. Senesi (DEF) £5.0m - Value: 44.9
    4. Caicedo (MID) £5.8m - Value: 43.0
    5. Gabriel (DEF) £6.3m - Value: 42.2
```

## Testing

Test the logger with sample events:

```bash
# Terminal 1: Start the logger
python scripts/decision_logger.py

# Terminal 2: Publish test events
python scripts/test_decision_logger.py
```

You should see the test events appear in the logger output.

## Integration with System

The decision logger automatically receives events from:
- Celery Beat scheduler (daily tasks)
- Specialist agents (Digger, Priya, Sophia, Jimmy)
- Ron (Manager Agent)
- Manual triggers

No configuration needed - just run it and it will listen to everything.

## Troubleshooting

**"Error connecting to Redis"**
- Make sure Redis is running: `docker compose up -d redis`
- Or start the full stack: `docker compose up -d`

**"No events appearing"**
- Check that agents are running and publishing events
- Verify Redis is accessible
- Check that the event bus is using the correct Redis URL

**"Permission denied on logs/"**
```bash
mkdir -p logs
chmod 755 logs
```
