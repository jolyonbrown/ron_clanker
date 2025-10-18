#!/usr/bin/env python3
"""
Test Telegram Notifications

Tests sending notifications to Telegram without running the full bot.

Usage:
    python scripts/test_telegram_notifications.py --test all
    python scripts/test_telegram_notifications.py --test announcement
    python scripts/test_telegram_notifications.py --test transfer
    python scripts/test_telegram_notifications.py --test review
"""

import sys
from pathlib import Path
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from telegram_bot.notifications import (
    send_notification,
    send_team_announcement,
    send_transfer_alert,
    send_post_match_review
)
from utils.config import get_telegram_token, get_telegram_chat_id


def test_basic_notification(bot_token: str, chat_id: str):
    """Test basic notification."""
    print("\n📱 Testing basic notification...")

    message = (
        "🤖 *Test Notification*\n\n"
        "If you can see this, Ron's Telegram notifications are working!\n\n"
        "_This is a test from the notification system._"
    )

    success = send_notification(bot_token, chat_id, message)

    if success:
        print("   ✅ Basic notification sent!")
    else:
        print("   ❌ Failed to send basic notification")

    return success


def test_team_announcement(bot_token: str, chat_id: str):
    """Test team announcement."""
    print("\n📱 Testing team announcement...")

    announcement = """Right, lads. Gameweek 8. Here's how we're lining up:

BETWEEN THE STICKS: Raya
Solid keeper. Arsenal defense has been rock solid.

THE BACK LINE: Gabriel (C), Timber, Saliba
This is where we're different. Gabriel's averaging 11 tackles and
clearances per game. That's 2 guaranteed points from Defensive
Contribution nearly every week. The market's still pricing them
on goals and assists. We're smarter than that.

MIDFIELD ENGINE ROOM: Caicedo, Rice, Saka, Palmer, Son
Caicedo and Rice - proper midfielders. 12+ defensive actions most
weeks. Another 4 points from DC every gameweek.

UP FRONT: Haaland, Watkins
Haaland gets the armband.

THE GAFFER'S LOGIC:
Five players earning Defensive Contribution points week in, week out.
That's 10 guaranteed points before we've even counted goals and assists.
Foundation first, fancy stuff second.

- Ron"""

    success = send_team_announcement(bot_token, chat_id, 8, announcement)

    if success:
        print("   ✅ Team announcement sent!")
    else:
        print("   ❌ Failed to send team announcement")

    return success


def test_transfer_alert(bot_token: str, chat_id: str):
    """Test transfer notification."""
    print("\n📱 Testing transfer alert...")

    success = send_transfer_alert(
        bot_token=bot_token,
        chat_id=chat_id,
        gameweek=8,
        player_out="Mbeumo",
        player_in="Palmer",
        reasoning="Palmer's fixtures are turning green. Mbeumo's blanked three weeks running. The numbers say move now before the price rise.",
        is_hit=False
    )

    if success:
        print("   ✅ Transfer alert sent!")
    else:
        print("   ❌ Failed to send transfer alert")

    return success


def test_post_match_review(bot_token: str, chat_id: str):
    """Test post-match review."""
    print("\n📱 Testing post-match review...")

    review = """======================================================================
RON'S POST-MATCH THOUGHTS - GAMEWEEK 8
======================================================================
*Lights cigar, pours a pint, settles into the chair*

Right. 67 bloody points. THAT'S how you do it! 12 above average.
The plan worked, lads. Absolutely worked.

======================================================================
THE PREMIER LEAGUE
======================================================================
• City 5-0 Bournemouth - Haaland hat-trick. Expected.
• Arsenal 0-0 Everton - Absolute snooze fest.

======================================================================
MINI-LEAGUE SITUATION
======================================================================
League: The Gaffer's League
Position: 4 of 14

Two places up from last week. 15 points behind Jenkins at the top.
Right in the mix. This is ours for the taking.

======================================================================
MY LOT - THE BRUTALLY HONEST ASSESSMENT
======================================================================
✓ Captain Haaland: 15 points
  That's what I'm talking about. Captain choice was spot on.

HEROES:
  • Haaland: 15 points - Hat-trick, that's why he's the captain
  • Gabriel: 9 points - Clean sheet + defensive contribution, exactly the plan

VILLAINS:
  • Mbeumo: 2 points - Full 90, did nothing. Out next week.

======================================================================
Overall Rank: 247,892
Top 250k. That's the standard.

======================================================================
THE VERDICT
======================================================================
Good weekend. The data worked, the picks delivered, job done.
This is what happens when you trust the fundamentals.

*Takes satisfied puff of cigar*

Right. That's enough analysis for one night.
Next gameweek is what matters now.

- Ron Clanker
*Saturday night, 05 October 2025, 22:30*"""

    success = send_post_match_review(bot_token, chat_id, 8, review)

    if success:
        print("   ✅ Post-match review sent!")
    else:
        print("   ❌ Failed to send post-match review")

    return success


def main():
    parser = argparse.ArgumentParser(description='Test Telegram notifications')
    parser.add_argument('--test', choices=['all', 'basic', 'announcement', 'transfer', 'review'],
                       default='all', help='Which test to run')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("TELEGRAM NOTIFICATION TESTS")
    print("=" * 70)

    # Load config from .env
    bot_token = get_telegram_token()
    chat_id = get_telegram_chat_id()

    if not bot_token or not chat_id:
        print("\n❌ Telegram not configured!")
        print("\nAdd to .env file:")
        print("  TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN")
        print("  TELEGRAM_CHAT_ID=YOUR_CHAT_ID")
        print("\nSetup instructions:")
        print("1. Message @BotFather on Telegram, send /newbot")
        print("2. Follow prompts to create your bot")
        print("3. Copy the bot token to .env")
        print("4. Start a chat with your bot")
        print("5. Message @userinfobot to get your chat ID")
        print("6. Add chat ID to .env")
        print("\nSee docs/TELEGRAM_BOT_SETUP.md for detailed instructions")
        return 1

    print(f"Bot Token: {bot_token[:20]}...")
    print(f"Chat ID: {chat_id}")
    print("=" * 70)

    # Run tests
    results = {}

    if args.test in ['all', 'basic']:
        results['basic'] = test_basic_notification(bot_token, chat_id)

    if args.test in ['all', 'announcement']:
        results['announcement'] = test_team_announcement(bot_token, chat_id)

    if args.test in ['all', 'transfer']:
        results['transfer'] = test_transfer_alert(bot_token, chat_id)

    if args.test in ['all', 'review']:
        results['review'] = test_post_match_review(bot_token, chat_id)

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:20s}: {status}")

    if all(results.values()):
        print("\n🎉 All tests passed! Telegram notifications working!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
