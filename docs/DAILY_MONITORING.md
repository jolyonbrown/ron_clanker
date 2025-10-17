# Daily Monitoring System

Ron Clanker's automated daily monitoring for price changes, injuries, and squad alerts.

## What It Does

The daily monitoring script (`scripts/daily_monitor.py`) runs every day at 3:00 AM (after FPL price changes) and:

1. **Syncs Latest FPL Data**
   - Player prices, stats, ownership
   - Injury news and availability
   - Fixture updates

2. **Detects Price Changes**
   - Tracks all price rises/falls
   - Logs changes to database
   - Alerts if squad players affected

3. **Monitors Injury News**
   - Detects new injury reports
   - Tracks availability status
   - Notes chance of playing percentages

4. **Squad Impact Analysis**
   - Checks if changes affect current squad
   - Calculates squad value changes
   - Generates alerts for affected players

5. **Daily Report**
   - Saves detailed report to `data/daily_reports/`
   - Includes price changes, injuries, squad impact
   - Logs all alerts for review

## Setup

### Automatic (Cron Job)

Run the setup script:

```bash
./scripts/setup_cron.sh
```

This installs a cron job to run at 3:00 AM daily.

### Manual Run

Test the script anytime:

```bash
venv/bin/python scripts/daily_monitor.py
```

## Output

### Console Output

```
================================================================================
RON CLANKER - DAILY MONITORING
Run time: 2025-10-17 03:00:00
================================================================================

📡 Fetching latest FPL data...
Current Gameweek: 7 (Gameweek 7)
Deadline: 2025-10-03T17:30:00Z

💰 Checking for price changes...
Found 12 price changes:
  📈 Haaland              £14.5m → £14.6m
  📉 Palmer               £10.3m → £10.2m

🏥 Checking injury/availability updates...
Found 3 status updates:
  ⚠️  Saka                 Status: d - Knock, 50% chance

👥 Checking impact on current squad...
  ⚠️  2 squad players affected:
  • Saka: Injury/News: Knock, 50% chance (50% likely to play)

💾 Updating database...
  ✅ Database updated

================================================================================
DAILY SUMMARY
================================================================================
Price Changes: 12
Injury Updates: 3
Squad Alerts: 1

🚨 ALERTS:
  SQUAD ALERT: Saka - Injury/News: Knock, 50% chance (50% likely to play)

📄 Report saved: data/daily_reports/report_20251017.txt

✅ Daily monitoring complete!
```

### Daily Reports

Detailed reports saved to `data/daily_reports/report_YYYYMMDD.txt`:

```
================================================================================
RON CLANKER - DAILY REPORT
2025-10-17 03:00:15
================================================================================

PRICE CHANGES (12):
--------------------------------------------------------------------------------
↑ Haaland             £14.5m → £14.6m (45.2% owned)
↓ Palmer              £10.3m → £10.2m (23.1% owned)
...

INJURY/NEWS UPDATES (3):
--------------------------------------------------------------------------------
Saka                 [d] Knock, 50% chance of playing
...

SQUAD IMPACT:
--------------------------------------------------------------------------------
⚠️  Saka: Injury/News: Knock, 50% chance (50% likely to play)

Total squad value change: £0.1m

ALERTS:
--------------------------------------------------------------------------------
SQUAD ALERT: Saka - Injury/News: Knock, 50% chance (50% likely to play)
```

## Database Tables Used

- `price_changes` - Historical price change log
- `players` - Updated with latest prices/news
- `my_team` - Current squad for impact analysis

## Viewing Logs

```bash
# Live monitoring
tail -f logs/daily_monitor.log

# View today's report
cat data/daily_reports/report_$(date +%Y%m%d).txt

# Check cron job status
crontab -l
```

## Alerts

The system generates alerts for:

- **Price Changes**: Squad player price rises/falls
- **Injuries**: Squad player injury news
- **Availability**: Chance of playing drops below 75%
- **Suspensions**: Red/yellow card accumulation

Alerts are:
- Printed to console
- Saved in daily reports
- Logged to database (future: email/SMS)

## Integration

The daily monitor integrates with:
- **Data Collector (Maggie)**: Fetches latest FPL data
- **Database**: Stores changes and generates alerts
- **Squad Management**: Checks impact on current team

## Next Steps

Future enhancements:
- Email/SMS alerts for critical changes
- Slack/Discord notifications
- Pre-deadline optimization trigger
- Price prediction based on trends
