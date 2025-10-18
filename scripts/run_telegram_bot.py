#!/usr/bin/env python3
"""
Run Telegram Bot

Starts Ron Clanker's Telegram bot in polling or webhook mode.

Usage:
    python scripts/run_telegram_bot.py
    python scripts/run_telegram_bot.py --mode webhook --webhook-url https://your-domain.com
"""

import sys
from pathlib import Path
import argparse
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from telegram_bot.bot import RonClankerBot
from data.database import Database
from utils.config import load_config, get_telegram_token, get_telegram_chat_id

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Run Ron Clanker Telegram Bot')
    parser.add_argument('--mode', choices=['polling', 'webhook'], default='polling',
                       help='Bot mode (default: polling)')
    parser.add_argument('--webhook-url', type=str,
                       help='Webhook URL (required for webhook mode)')
    parser.add_argument('--port', type=int, default=8443,
                       help='Webhook port (default: 8443)')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("RON CLANKER TELEGRAM BOT")
    print("=" * 70)

    # Load config from .env
    config = load_config()
    bot_token = get_telegram_token()
    chat_id = get_telegram_chat_id()

    if not bot_token or not chat_id:
        print("\n❌ Telegram not configured!")
        print("\nAdd to .env file:")
        print("  TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN")
        print("  TELEGRAM_CHAT_ID=YOUR_CHAT_ID")
        print("\nSetup instructions:")
        print("  1. Message @BotFather on Telegram, send /newbot")
        print("  2. Copy the bot token to .env")
        print("  3. Start a chat with your bot")
        print("  4. Message @userinfobot to get your chat ID")
        print("  5. Add chat ID to .env")
        print("\nSee docs/TELEGRAM_BOT_SETUP.md for detailed instructions")
        return 1

    print(f"Bot Token: {bot_token[:20]}...")
    print(f"Chat ID: {chat_id}")
    print(f"Mode: {args.mode}")
    print("=" * 70)

    # Initialize database
    db = Database()

    # Create bot
    try:
        bot = RonClankerBot(
            token=bot_token,
            chat_id=chat_id,
            database=db,
            config=config
        )
    except Exception as e:
        print(f"\n❌ Failed to create bot: {e}")
        print("\nMake sure python-telegram-bot is installed:")
        print("  pip install python-telegram-bot")
        return 1

    # Start bot
    print("\n🤖 Starting bot...")

    try:
        if args.mode == 'webhook':
            if not args.webhook_url:
                print("❌ Webhook URL required for webhook mode")
                return 1

            bot.start_webhook(args.webhook_url, args.port)
        else:
            bot.start_polling()

        print("\n✅ Bot is running!")
        print("   Send /start to your bot on Telegram to test it\n")
        print("Press Ctrl+C to stop...\n")

        # Keep running
        bot.idle()

    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping bot...")
        bot.stop()
        print("✅ Bot stopped")

    except Exception as e:
        print(f"\n❌ Bot error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
