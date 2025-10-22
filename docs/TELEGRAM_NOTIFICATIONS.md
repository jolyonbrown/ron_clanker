# Telegram Notifications for Cron Jobs

Ron Clanker's automated cron jobs can send notifications to Telegram to keep you informed of important events.

## 📱 What Gets Notified

### Automated Notifications

The following cron jobs send Telegram notifications when they complete:

1. **Daily Scout Report** (03:00 daily)
   - Intelligence items gathered
   - Breakdown by type
   - Top findings

2. **League Intelligence** (07:00 daily)
   - Current league position
   - Key insights about rivals
   - Links to full report

3. **Price Predictions** (01:30 daily)
   - Predicted price rises (top 5)
   - Predicted price falls (top 5)
   - Confidence levels

4. **Post-Match Review** (Monday mornings)
   - Ron's analysis of the gameweek
   - Team performance
   - League standings

### Error Notifications

If any cron job fails, you'll receive an error notification with:
- Job name
- Error message
- Reminder to check logs

## 🔧 Configuration

### 1. Enable/Disable Notifications

Telegram notifications are **enabled by default**. To disable them, set:

```bash
# In .env file
TELEGRAM_NOTIFICATIONS_ENABLED=false
```

Or as an environment variable:

```bash
export TELEGRAM_NOTIFICATIONS_ENABLED=false
```

### 2. Required Telegram Settings

Make sure these are set in your `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

See `docs/TELEGRAM_BOT_SETUP.md` for instructions on getting these values.

## 📋 Notification Examples

### Scout Report
```
🔍 DAILY SCOUT REPORT

Intelligence gathered: 47 items

Breakdown:
  • injury_news: 12
  • press_conference: 8
  • youtube_analysis: 15
  • team_news: 12

Key findings:
  • [injury_news] Salah
  • [press_conference] Haaland
  • [youtube_analysis] Palmer

Report generated at 03:02
```

### Price Predictions
```
🔮 PRICE PREDICTIONS - tomorrow

📈 LIKELY RISES (8):
  • Haaland (£15.2m) - 87%
  • Palmer (£10.8m) - 82%
  • Saka (£10.1m) - 76%
  • Gordon (£7.4m) - 71%
  • Watkins (£9.0m) - 68%
  ...and 3 more

📉 LIKELY FALLS (5):
  • Rashford (£8.7m) - 79%
  • Jesus (£8.9m) - 73%
  ...and 3 more
```

### League Intelligence
```
🏆 LEAGUE INTELLIGENCE - GW8

The Gaffer's League
Ron's Position: 3/12

Key Intel:
  • 2 rivals used wildcard this week
  • Ron has differential captain (Caicedo)
  • 4 rivals missing Palmer

Full report saved to reports/league_intelligence/
```

## 🎯 Testing Notifications

Test the notification system:

```bash
# Test basic notification
venv/bin/python scripts/test_telegram_notifications.py

# Run a script manually to see notifications
venv/bin/python scripts/daily_scout.py
venv/bin/python scripts/predict_price_changes.py
```

## 🔇 Quiet Mode

If you want logs but no notifications, disable them:

```bash
export TELEGRAM_NOTIFICATIONS_ENABLED=false
venv/bin/python scripts/daily_scout.py
```

The script will run normally but skip sending Telegram messages.

## 📊 Notification Frequency

| Job | Frequency | Time (BST) | Notification Type |
|-----|-----------|------------|-------------------|
| Scout | Daily | 03:00 | Summary |
| League Intel | Daily | 07:00 | Summary |
| Price Predictions | Daily | 01:30 | Detailed |
| Post-Match Review | Monday | 08:00+ | Full review |
| Errors | As needed | Any | Alert |

## 🐛 Troubleshooting

### Notifications Not Sending

1. Check environment variables are set:
   ```bash
   venv/bin/python utils/config.py
   ```

2. Check Telegram bot is active:
   ```bash
   venv/bin/python scripts/test_telegram_notifications.py
   ```

3. Check cron logs:
   ```bash
   tail -f logs/cron_scout.log
   ```

### Too Many Notifications

Disable notifications for specific jobs by editing the script and commenting out the notification section, or disable globally:

```bash
export TELEGRAM_NOTIFICATIONS_ENABLED=false
```

## 💡 Tips

- **Don't spam**: Notifications are designed to be concise and actionable
- **Check logs**: Detailed information is always in log files
- **Customize**: Edit notification functions in `telegram_bot/notifications.py` to adjust format
- **Mute if needed**: You can mute the Telegram chat and check notifications at your convenience

## 🔗 Related Documentation

- [Telegram Bot Setup](TELEGRAM_BOT_SETUP.md) - Initial bot configuration
- [Security Audit](SECURITY_AUDIT_REPORT.md) - Security considerations
- [Crontab Configuration](../config/crontab) - Automated job schedule
