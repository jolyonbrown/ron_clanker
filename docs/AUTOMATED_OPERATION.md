# Ron Clanker - Automated Operation Guide

Complete guide for setting up Ron Clanker to run fully autonomously.

---

## Overview

Ron Clanker is designed to operate autonomously without human intervention. This guide shows how to set up scheduled tasks, notifications, and monitoring so the system runs 24/7.

**Once configured, Ron will:**
- ✅ Gather intelligence daily from all sources
- ✅ Monitor player prices hourly
- ✅ Select teams before each gameweek deadline
- ✅ Send notifications about decisions
- ✅ Maintain and optimize the database
- ✅ Monitor system health

---

## Quick Start

### 1. Setup Automated Tasks

```bash
# Run the cron setup script
venv/bin/python scripts/setup_cron.py

# Follow the interactive prompts to install cron jobs
```

### 2. Setup Notifications (Optional)

```bash
# Configure Discord/Slack notifications
venv/bin/python scripts/setup_notifications.py

# Follow prompts to add your webhook URL
```

### 3. Verify Setup

```bash
# Test the health check
venv/bin/python scripts/health_check.py

# Test data collection
venv/bin/python scripts/collect_fpl_data.py

# Test Scout
venv/bin/python scripts/daily_scout.py
```

Done! Ron is now autonomous.

---

## Scheduled Tasks

### Daily Schedule

| Time  | Task                      | Description                           |
|-------|---------------------------|---------------------------------------|
| 02:30 | Data Collection           | Fetch latest FPL data                 |
| 03:00 | Scout Intelligence        | Gather news, injuries, YouTube        |
| 04:00 | Transcript Cleanup        | Remove expired YouTube cache          |
| 05:00 | Database Maintenance      | Optimize database, clean old data     |
| Hourly| Price Monitoring          | Track price changes                   |
| 6h    | Health Check              | Verify system is operational          |

### Gameweek Schedule

| Time          | Task                   | Description                        |
|---------------|------------------------|------------------------------------|
| Fri 12:30     | Pre-deadline Selection | Select team (Friday evening GWs)   |
| Sat 05:00     | Pre-deadline Selection | Select team (Saturday morning GWs) |
| Mon 08:00     | Weekly Review          | Analyze gameweek results           |

### Weekly Schedule

| Day    | Time  | Task              | Description                   |
|--------|-------|-------------------|-------------------------------|
| Sunday | 03:00 | Database Backup   | Create backup of all data     |
| Sunday | 04:00 | Log Rotation      | Archive old logs              |

---

## Cron Jobs

### Installation

The cron jobs are defined in `config/crontab.example` and can be installed using:

```bash
# Interactive setup
venv/bin/python scripts/setup_cron.py

# Or manually
cp config/crontab.example config/crontab
# Edit PROJECT_PATH in config/crontab
crontab config/crontab
```

### Verification

```bash
# View installed cron jobs
crontab -l

# Check if Ron's jobs are listed
crontab -l | grep ron_clanker
```

### Logs

All cron jobs output to `logs/cron_*.log`:

```bash
# View Scout logs
tail -f logs/cron_scout.log

# View deadline selection logs
tail -f logs/cron_deadline.log

# View price monitoring logs
tail -f logs/cron_prices.log

# View all cron logs
tail -f logs/cron_*.log
```

---

## Notifications

### Setup

Ron can send notifications to Discord or Slack when:
- Team is selected for a gameweek
- Significant price changes occur
- System health issues are detected
- Alerts or errors occur

**Setup notifications:**

```bash
venv/bin/python scripts/setup_notifications.py
```

### Discord Setup

1. Open Discord server settings
2. Select "Integrations" → "Webhooks"
3. Click "New Webhook"
4. Name it "Ron Clanker"
5. Copy the webhook URL
6. Run setup script and paste URL

### Slack Setup

1. Go to https://api.slack.com/apps
2. Create new app → "Incoming Webhooks"
3. Activate incoming webhooks
4. Add new webhook to workspace
5. Copy webhook URL
6. Run setup script and paste URL

### Manual Configuration

If you prefer not to use the setup script:

```bash
# Set environment variable
export WEBHOOK_URL="https://discord.com/api/webhooks/..."

# Or add to .env file
echo 'WEBHOOK_URL=https://discord.com/api/webhooks/...' >> .env

# Or add to shell profile
echo 'export WEBHOOK_URL="..."' >> ~/.bashrc
```

### Test Notifications

```python
# Test in Python
from utils.notifications import NotificationService

ns = NotificationService()
ns.send_alert("Test", "Ron Clanker is operational", "info")
```

---

## Monitoring

### Health Checks

The system runs health checks every 6 hours to verify:
- Database connectivity
- FPL data freshness
- Intelligence gathering
- Disk space
- Log file sizes

**Manual health check:**

```bash
venv/bin/python scripts/health_check.py
```

**Expected output:**
```
✓ Database: Database OK
✓ Bootstrap Data: Bootstrap data is 0.5 hours old
✓ Intelligence Cache: 92 intelligence items in last 48h
✓ Disk Space: Disk space OK: 25.3 GB free
✓ Log Files: Logs OK: 12.4 MB total

Status: ✓ ALL SYSTEMS OPERATIONAL
```

### Database Status

```bash
# Check database size
ls -lh data/fpl_data.db

# View recent intelligence
venv/bin/python scripts/view_transcripts.py

# Check player data
sqlite3 data/fpl_data.db "SELECT COUNT(*) FROM players"
```

### Log Files

```bash
# View main log
tail -f logs/ron_clanker.log

# View agent logs
tail -f logs/scout.log
tail -f logs/maggie.log
tail -f logs/ron.log

# View all logs
tail -f logs/*.log
```

---

## Troubleshooting

### Cron Jobs Not Running

**Verify cron is installed:**
```bash
which crontab
# Should output: /usr/bin/crontab
```

**Check cron service:**
```bash
sudo systemctl status cron
# Should show: active (running)
```

**View cron logs:**
```bash
tail -f logs/cron_*.log
```

### Notifications Not Working

**Test webhook URL:**
```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

**Check environment variable:**
```bash
echo $WEBHOOK_URL
# Should output your webhook URL
```

**Verify in Python:**
```bash
venv/bin/python -c "import os; print(os.getenv('WEBHOOK_URL'))"
```

### Database Issues

**Check database integrity:**
```bash
sqlite3 data/fpl_data.db "PRAGMA integrity_check"
# Should output: ok
```

**Run maintenance:**
```bash
venv/bin/python scripts/db_maintenance.py
```

**Restore from backup:**
```bash
cp backups/fpl_data_YYYYMMDD.db data/fpl_data.db
```

### Data Collection Failing

**Test FPL API connection:**
```bash
curl -s https://fantasy.premierleague.com/api/bootstrap-static/ | head -100
```

**Run collection manually:**
```bash
venv/bin/python scripts/collect_fpl_data.py
```

**Check Maggie logs:**
```bash
tail -f logs/maggie.log
```

---

## Manual Operations

Even with automation, you may want to run tasks manually:

### Force Data Collection

```bash
venv/bin/python scripts/collect_fpl_data.py
```

### Force Scout Run

```bash
venv/bin/python scripts/daily_scout.py
```

### Force Team Selection

```bash
venv/bin/python scripts/pre_deadline_selection.py
```

### View Latest Team

```bash
venv/bin/python scripts/show_latest_team.py
```

### Check Price Changes

```bash
venv/bin/python scripts/monitor_prices.py
```

---

## System Requirements

### Disk Space

Ron Clanker requires:
- ~100 MB for application code
- ~50-200 MB for database (grows over season)
- ~50-100 MB for logs
- ~500 MB recommended free space

**Monitor disk usage:**
```bash
df -h .
du -sh data/ logs/
```

### Memory

- ~100-200 MB during normal operation
- ~300-500 MB during team selection
- 512 MB RAM recommended minimum

### CPU

- Minimal CPU usage (< 5% during tasks)
- Raspberry Pi 3B+ or better recommended

---

## Backup Strategy

### Automated Backups

Backups run weekly on Sunday at 03:00:

```bash
# View backups
ls -lh backups/

# Latest backup
ls -lht backups/ | head -1
```

### Manual Backup

```bash
venv/bin/python scripts/backup_database.py
```

### Restore from Backup

```bash
# List available backups
ls backups/

# Restore specific backup
cp backups/fpl_data_20251017.db data/fpl_data.db

# Verify integrity
sqlite3 data/fpl_data.db "PRAGMA integrity_check"
```

---

## Security Considerations

### Webhook URL Security

- Never commit webhook URLs to git
- Store in `.env` file (git-ignored)
- Rotate webhook URLs periodically
- Use separate webhooks for different environments

### Database Backups

- Backups stored in `backups/` directory
- Add to `.gitignore` if they contain sensitive data
- Consider encrypting backups if storing off-site

### Logs

- Logs may contain player names, team data
- Rotate logs weekly to limit size
- Review logs for sensitive info before sharing

---

## Performance Optimization

### Database Optimization

Database maintenance runs daily at 05:00. It:
- Removes old intelligence (30+ days)
- Removes expired transcripts
- Runs VACUUM to reclaim space
- Updates statistics for query optimizer

**Manual optimization:**
```bash
venv/bin/python scripts/db_maintenance.py
```

### Log Rotation

Logs rotate weekly on Sunday at 04:00.

**Manual rotation:**
```bash
venv/bin/python scripts/rotate_logs.py
```

### YouTube Cache Management

YouTube transcripts expire after 7 days and are cleaned daily at 04:00.

**Manual cleanup:**
```bash
venv/bin/python scripts/cleanup_expired_transcripts.py
```

---

## Advanced Configuration

### Custom Cron Schedule

Edit `config/crontab` to customize:

```bash
# Run Scout every 6 hours instead of daily
0 */6 * * * cd $PROJECT_PATH && venv/bin/python scripts/daily_scout.py

# Run price monitoring every 30 minutes
*/30 * * * * cd $PROJECT_PATH && venv/bin/python scripts/monitor_prices.py
```

Then reinstall:
```bash
crontab config/crontab
```

### Environment Variables

Create `.env` file for configuration:

```bash
# Notifications
WEBHOOK_URL=https://...
NOTIFY_PRICE_CHANGES=true

# Database
DATABASE_PATH=data/fpl_data.db

# Logging
LOG_LEVEL=INFO
```

Load in scripts:
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## Next Steps

Once automation is set up:

1. **Monitor for a week** - Check logs daily, verify tasks run
2. **Review team selections** - Let Ron make 1-2 gameweek selections
3. **Tune notifications** - Adjust thresholds to reduce noise
4. **Add price prediction** - Implement ML models for price changes
5. **Enhance intelligence** - Add more RSS feeds, YouTube channels

---

## Support

If you encounter issues:

1. **Check logs**: `tail -f logs/*.log`
2. **Run health check**: `venv/bin/python scripts/health_check.py`
3. **Test manually**: Run scripts directly to see errors
4. **Check cron logs**: `tail -f logs/cron_*.log`
5. **Review documentation**: Re-read relevant sections

---

**Last Updated**: October 17, 2025
**Version**: 1.0
**Status**: Production Ready
