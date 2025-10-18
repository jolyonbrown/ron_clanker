# Telegram Bot Setup Guide

Complete guide to setting up Ron Clanker's Telegram bot for automated notifications and commands.

---

## Quick Start

### 1. Create Telegram Bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot`
3. Follow prompts:
   - **Bot name**: Ron Clanker (or whatever you want)
   - **Username**: Must end in `bot`, e.g., `ron_clanker_fpl_bot`
4. **Copy the bot token** - you'll need this!

Example token: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Get Your Chat ID

1. **Start a chat** with your new bot (search for the username you created)
2. Send any message to the bot
3. Message **@userinfobot** on Telegram
4. It will reply with your **Chat ID** (a number like `12345678`)

### 3. Configure Ron Clanker

Add to `.env` file (create from `.env.example` if it doesn't exist):

```bash
# Copy template
cp .env.example .env

# Edit .env and add your credentials
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
```

**IMPORTANT**: The `.env` file contains sensitive credentials and should NEVER be committed to git. It's already in `.gitignore`.

### 4. Install Dependencies

```bash
pip install python-telegram-bot
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

### 5. Test It

```bash
# Test notifications
python scripts/test_telegram_notifications.py --test all

# If tests pass, start the bot
python scripts/run_telegram_bot.py
```

Then send `/start` to your bot on Telegram!

---

## Features

### Automated Notifications

Ron will automatically send you updates when:

- **🏴󠁧󠁢󠁥󠁮󠁧󠁿 Team Announcements** - Before each gameweek deadline
- **🔄 Transfers** - When Ron makes a transfer
- **💎 Chip Usage** - When a chip is activated
- **🍺 Post-Match Reviews** - After each gameweek (Ron's honest thoughts!)
- **💰 Price Changes** - Important price movements
- **🏥 Injury News** - Updates on your players

### Interactive Commands

- `/start` - Welcome message and command list
- `/help` - Show available commands
- `/status` - Current team overview
- `/team` - Full squad with formation
- `/league` - Mini-league standings
- `/chips` - Available chips status
- `/predictions` - Next gameweek ML predictions

---

## Usage

### Running the Bot

**Polling Mode** (simple, works anywhere):
```bash
python scripts/run_telegram_bot.py
```

**Webhook Mode** (for production servers):
```bash
python scripts/run_telegram_bot.py --mode webhook --webhook-url https://your-domain.com
```

### Sending Notifications from Scripts

You can send notifications from any Python script:

```python
from telegram_bot.notifications import send_notification

send_notification(
    bot_token="YOUR_TOKEN",
    chat_id="YOUR_CHAT_ID",
    message="🤖 Test message from Ron!"
)
```

Or use the convenience functions:

```python
from telegram_bot.notifications import (
    send_team_announcement,
    send_transfer_alert,
    send_post_match_review
)

# Team announcement
send_team_announcement(bot_token, chat_id, gameweek=8, announcement=ron_text)

# Transfer alert
send_transfer_alert(
    bot_token, chat_id,
    gameweek=8,
    player_out="Mbeumo",
    player_in="Palmer",
    reasoning="Better fixtures ahead",
    is_hit=False
)

# Post-match review
send_post_match_review(bot_token, chat_id, gameweek=8, review=ron_review)
```

### Integration with Existing Scripts

Add Telegram notifications to any script:

```python
import json
from pathlib import Path
from telegram_bot.notifications import send_notification

# Load config
with open('config/ron_config.json') as f:
    config = json.load(f)

# Send notification
if config.get('telegram_bot_token'):
    send_notification(
        bot_token=config['telegram_bot_token'],
        chat_id=config['telegram_chat_id'],
        message="✅ Script completed!"
    )
```

---

## Automation Examples

### Post-Gameweek Review

After GW8 finishes:

```bash
# 1. Generate Ron's review via Claude
python scripts/generate_post_match_prompt.py --gw 8 --save

# 2. Copy prompt to Claude, get Ron's analysis

# 3. Send to Telegram
python -c "
from telegram_bot.notifications import send_post_match_review
import json

with open('config/ron_config.json') as f:
    config = json.load(f)

review_text = '''[Paste Ron's analysis here]'''

send_post_match_review(
    config['telegram_bot_token'],
    config['telegram_chat_id'],
    gameweek=8,
    review=review_text
)
"
```

### Cron Job for Daily Updates

Add to crontab:

```bash
# Daily price changes at 2:30 AM (after FPL price changes)
30 2 * * * cd /home/jolyon/ron_clanker && venv/bin/python scripts/notify_price_changes.py

# Post-gameweek review on Sundays at 11 PM
0 23 * * 0 cd /home/jolyon/ron_clanker && venv/bin/python scripts/notify_post_match_review.py
```

---

## Troubleshooting

### Bot Token Invalid

```
❌ Error: Unauthorized
```

**Solution**: Check your bot token is correct in `config/ron_config.json`. Get a new one from @BotFather if needed.

### Message Not Received

```
✅ Message sent successfully
(but you don't see it in Telegram)
```

**Solution**:
1. Make sure you've started a chat with your bot first
2. Check the chat ID is correct
3. Verify the bot isn't blocked

### Import Error

```
❌ ModuleNotFoundError: No module named 'telegram'
```

**Solution**:
```bash
pip install python-telegram-bot
```

### Webhook Issues

```
❌ Webhook failed to set
```

**Solution**:
- Make sure your server is publicly accessible
- Use HTTPS (required for webhooks)
- Check firewall allows traffic on webhook port

---

## Advanced Configuration

### Group Chat Support

To send notifications to a group:

1. Add your bot to a Telegram group
2. Get the group chat ID:
   - Forward a message from the group to @userinfobot
   - Or use the bot's `getUpdates` API endpoint
3. Group chat IDs are negative numbers (e.g., `-123456789`)
4. Update `telegram_chat_id` in config

### Multiple Notification Channels

Send to different chats for different notifications:

```python
# config/ron_config.json
{
  "telegram_bot_token": "...",
  "telegram_chat_id": "12345678",           # Personal chat
  "telegram_group_chat_id": "-987654321",   # League chat
  "telegram_admin_chat_id": "11111111"      # Admin alerts
}
```

### Custom Notification Formatting

Telegram supports **Markdown** and **HTML** formatting:

**Markdown**:
```
*bold text*
_italic text_
[link](http://example.com)
`code`
```

**HTML**:
```html
<b>bold</b>
<i>italic</i>
<a href="http://example.com">link</a>
<code>code</code>
```

---

## Security Notes

1. **Keep your bot token secret!** Don't commit it to git.
2. Use environment variables or secure config files
3. If token is compromised, revoke it via @BotFather and create a new one
4. Don't share your chat ID publicly

---

## Example: Complete Workflow

```bash
# 1. Setup (one time)
python scripts/test_telegram_notifications.py --test all

# 2. Start bot for commands
python scripts/run_telegram_bot.py &

# 3. Use commands on Telegram
/status  # See current team
/league  # Check mini-league standings

# 4. Automated notifications (run by cron or manually)
python scripts/notify_price_changes.py
python scripts/notify_team_announcement.py --gw 9

# 5. Post-gameweek (after GW finishes)
python scripts/generate_post_match_prompt.py --gw 8
# Copy to Claude, get Ron's analysis, then:
python scripts/send_post_match_review.py --gw 8 --review-file review.txt
```

---

## FAQ

**Q: Can I use this with WhatsApp instead?**
A: Not with this bot, but you could build a similar one using Twilio API.

**Q: How much does it cost?**
A: Telegram bots are **completely free**!

**Q: Can multiple people use the same bot?**
A: Yes! Add their chat IDs to a list and send to all of them.

**Q: What's the rate limit?**
A: Telegram allows 30 messages/second. More than enough for Ron!

**Q: Can I customize Ron's messages?**
A: Absolutely! Edit the templates in `telegram_bot/notifications.py`

---

## Next Steps

1. ✅ Set up bot and test notifications
2. 🔄 Integrate with existing scripts (team announcements, price changes)
3. 🤖 Set up automated cron jobs
4. 🍺 Wait for GW8 to finish and test post-match review!

---

*"Right, lad. You've got the bot running. Now you'll know exactly what I'm thinking, when I'm thinking it. No excuses."*

*- Ron Clanker*
