"""
Telegram Notifications Module

Simple interface for sending notifications without running the full bot.
Used by scripts to send one-off notifications.
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger('ron_clanker.telegram_notifications')


def send_notification(
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = 'Markdown'
) -> bool:
    """
    Send a notification to Telegram (simple, stateless).

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        message: Message text
        parse_mode: Parse mode (Markdown or HTML)

    Returns:
        Success status
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': parse_mode
    }

    try:
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info(f"Notification sent to {chat_id}")
            return True
        else:
            logger.error(f"Failed to send notification: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Exception sending notification: {e}")
        return False


def send_team_announcement(bot_token: str, chat_id: str, gameweek: int, announcement: str) -> bool:
    """Send team announcement notification."""
    message = f"🏴󠁧󠁢󠁥󠁮󠁧󠁿 *TEAM ANNOUNCEMENT - GAMEWEEK {gameweek}*\n\n"
    message += f"```\n{announcement}\n```"
    return send_notification(bot_token, chat_id, message)


def send_post_match_review(bot_token: str, chat_id: str, gameweek: int, review: str) -> bool:
    """Send post-match review notification."""
    message = f"🍺 *RON'S POST-MATCH THOUGHTS - GW{gameweek}*\n\n"
    message += f"```\n{review}\n```"
    return send_notification(bot_token, chat_id, message)


def send_transfer_alert(
    bot_token: str,
    chat_id: str,
    gameweek: int,
    player_out: str,
    player_in: str,
    reasoning: str,
    is_hit: bool = False
) -> bool:
    """Send transfer notification."""
    hit_emoji = "⚠️" if is_hit else "✅"
    hit_text = " (-4 HIT)" if is_hit else ""

    message = f"{hit_emoji} *TRANSFER - GW{gameweek}*{hit_text}\n\n"
    message += f"OUT: ❌ {player_out}\n"
    message += f"IN: ✅ {player_in}\n\n"
    message += f"*Ron says:*\n_{reasoning}_"

    return send_notification(bot_token, chat_id, message)


def send_price_changes(bot_token: str, chat_id: str, rises: list, falls: list) -> bool:
    """Send price change alert."""
    if not rises and not falls:
        return True

    message = "💰 *PRICE CHANGES*\n\n"

    if rises:
        message += "📈 *RISES:*\n"
        for player in rises:
            message += f"  • {player['name']}: £{player['old_price']}m → £{player['new_price']}m\n"
        message += "\n"

    if falls:
        message += "📉 *FALLS:*\n"
        for player in falls:
            message += f"  • {player['name']}: £{player['old_price']}m → £{player['new_price']}m\n"

    return send_notification(bot_token, chat_id, message)
