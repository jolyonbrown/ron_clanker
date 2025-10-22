"""
Telegram Notifications Module

Simple interface for sending notifications without running the full bot.
Used by scripts to send one-off notifications.
"""

import logging
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger('ron_clanker.telegram_notifications')


def send_notification(
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: Optional[str] = 'Markdown'
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
    }

    if parse_mode:
        payload['parse_mode'] = parse_mode

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


def send_scout_report(
    bot_token: str,
    chat_id: str,
    intel_count: int,
    breakdown: Dict[str, int],
    top_items: List[Dict[str, Any]] = None
) -> bool:
    """
    Send daily scout intelligence report.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        intel_count: Total number of intelligence items gathered
        breakdown: Dictionary of intelligence types and counts
        top_items: Optional list of top intelligence items

    Returns:
        Success status
    """
    # Don't use markdown formatting to avoid parsing errors - use plain text
    message = f"🔍 DAILY SCOUT REPORT\n\n"
    message += f"Intelligence gathered: {intel_count} items\n\n"

    if breakdown:
        message += "Breakdown:\n"
        for intel_type, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            message += f"  • {intel_type}: {count}\n"

    if top_items:
        message += "\nKey findings:\n"
        for item in top_items[:3]:
            player = item.get('player_name', 'Unknown')
            intel_type = item.get('type', 'info')
            message += f"  • [{intel_type}] {player}\n"

    message += f"\nReport generated at {datetime.now().strftime('%H:%M')}"

    # Use parse_mode=None to avoid markdown parsing issues
    return send_notification(bot_token, chat_id, message, parse_mode=None)


def send_league_intelligence(
    bot_token: str,
    chat_id: str,
    gameweek: int,
    league_name: str,
    ron_rank: int,
    total_managers: int,
    key_insights: List[str] = None
) -> bool:
    """
    Send league intelligence summary.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        gameweek: Current gameweek
        league_name: Name of the league
        ron_rank: Ron's current rank
        total_managers: Total managers in league
        key_insights: List of key insights/observations

    Returns:
        Success status
    """
    message = f"🏆 *LEAGUE INTELLIGENCE - GW{gameweek}*\n\n"
    message += f"*{league_name}*\n"
    message += f"Ron's Position: *{ron_rank}/{total_managers}*\n"

    if key_insights:
        message += "\n*Key Intel:*\n"
        for insight in key_insights[:5]:
            message += f"  • {insight}\n"

    message += f"\n_Full report saved to reports/league_intelligence/_"

    return send_notification(bot_token, chat_id, message)


def send_price_predictions(
    bot_token: str,
    chat_id: str,
    rises: List[Dict[str, Any]],
    falls: List[Dict[str, Any]],
    prediction_date: str = None
) -> bool:
    """
    Send price change predictions.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        rises: List of predicted price rises
        falls: List of predicted price falls
        prediction_date: Date of predictions (default: tomorrow)

    Returns:
        Success status
    """
    if not rises and not falls:
        return True

    pred_date = prediction_date or "tomorrow"
    message = f"🔮 *PRICE PREDICTIONS - {pred_date}*\n\n"

    if rises:
        message += f"📈 *LIKELY RISES ({len(rises)}):*\n"
        for player in rises[:5]:  # Top 5
            name = player.get('player_name', player.get('name', 'Unknown'))
            confidence = player.get('confidence', 0)
            price = player.get('price', 0)
            message += f"  • {name} (£{price}m) - {confidence:.0%}\n"
        if len(rises) > 5:
            message += f"  _...and {len(rises) - 5} more_\n"
        message += "\n"

    if falls:
        message += f"📉 *LIKELY FALLS ({len(falls)}):*\n"
        for player in falls[:5]:  # Top 5
            name = player.get('player_name', player.get('name', 'Unknown'))
            confidence = player.get('confidence', 0)
            price = player.get('price', 0)
            message += f"  • {name} (£{price}m) - {confidence:.0%}\n"
        if len(falls) > 5:
            message += f"  _...and {len(falls) - 5} more_\n"

    return send_notification(bot_token, chat_id, message)


def send_deadline_selection(
    bot_token: str,
    chat_id: str,
    gameweek: int,
    captain: str,
    vice_captain: str,
    transfers_made: int = 0,
    chip_used: str = None
) -> bool:
    """
    Send pre-deadline team selection notification.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        gameweek: Gameweek number
        captain: Captain name
        vice_captain: Vice-captain name
        transfers_made: Number of transfers made
        chip_used: Chip used (if any)

    Returns:
        Success status
    """
    message = f"⚽ *PRE-DEADLINE SELECTION - GW{gameweek}*\n\n"
    message += f"*Captain:* {captain} (C)\n"
    message += f"*Vice-Captain:* {vice_captain} (V)\n"

    if transfers_made > 0:
        message += f"\n*Transfers:* {transfers_made} made\n"
    else:
        message += "\n_No transfers made_\n"

    if chip_used:
        message += f"\n💎 *CHIP ACTIVE:* {chip_used.upper()}\n"

    message += f"\n_Team locked and ready for GW{gameweek}_"

    return send_notification(bot_token, chat_id, message)


def send_cron_success(
    bot_token: str,
    chat_id: str,
    job_name: str,
    details: str = None
) -> bool:
    """
    Send cron job success notification.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        job_name: Name of the cron job
        details: Optional details about the job execution

    Returns:
        Success status
    """
    message = f"✅ *{job_name.upper()} - COMPLETE*\n\n"

    if details:
        message += f"{details}\n\n"

    message += f"_Completed at {datetime.now().strftime('%H:%M:%S')}_"

    return send_notification(bot_token, chat_id, message)


def send_cron_failure(
    bot_token: str,
    chat_id: str,
    job_name: str,
    error: str
) -> bool:
    """
    Send cron job failure notification.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        job_name: Name of the cron job
        error: Error message

    Returns:
        Success status
    """
    message = f"❌ *{job_name.upper()} - FAILED*\n\n"
    message += f"*Error:*\n```\n{error[:500]}\n```\n\n"
    message += f"_Check logs for details_"

    return send_notification(bot_token, chat_id, message)
