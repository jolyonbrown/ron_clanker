"""
Ron Clanker Telegram Bot

Main bot class with command handlers and notification methods.
"""

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from telegram import Update, ParseMode
    from telegram.ext import Updater, CommandHandler, CallbackContext
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not installed. Install with: pip install python-telegram-bot")

logger = logging.getLogger('ron_clanker.telegram_bot')


class RonClankerBot:
    """
    Ron Clanker's Telegram Bot

    Provides automated notifications and interactive commands.
    """

    def __init__(self, token: str, chat_id: str, database=None, config: Dict = None):
        """
        Initialize the bot.

        Args:
            token: Telegram bot token (from @BotFather)
            chat_id: Default chat ID to send notifications to
            database: Database instance
            config: Configuration dict
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot not installed. Install with: pip install python-telegram-bot")

        self.token = token
        self.chat_id = chat_id
        self.db = database
        self.config = config or {}

        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher

        # Register command handlers
        self._register_commands()

        logger.info("Ron Clanker Telegram Bot initialized")

    def _register_commands(self):
        """Register all command handlers."""
        handlers = [
            CommandHandler('start', self.cmd_start),
            CommandHandler('help', self.cmd_help),
            CommandHandler('status', self.cmd_status),
            CommandHandler('team', self.cmd_team),
            CommandHandler('league', self.cmd_league),
            CommandHandler('chips', self.cmd_chips),
            CommandHandler('predictions', self.cmd_predictions),
        ]

        for handler in handlers:
            self.dispatcher.add_handler(handler)

        logger.info(f"Registered {len(handlers)} command handlers")

    # =================================================================
    # NOTIFICATION METHODS
    # =================================================================

    def send_message(self, text: str, chat_id: Optional[str] = None, parse_mode: str = 'Markdown') -> bool:
        """
        Send a message to Telegram.

        Args:
            text: Message text
            chat_id: Chat ID (uses default if not provided)
            parse_mode: Parse mode (Markdown or HTML)

        Returns:
            Success status
        """
        target_chat = chat_id or self.chat_id

        try:
            self.updater.bot.send_message(
                chat_id=target_chat,
                text=text,
                parse_mode=parse_mode
            )
            logger.info(f"Message sent to {target_chat}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def notify_team_announcement(self, gameweek: int, announcement: str) -> bool:
        """
        Send team announcement notification.

        Args:
            gameweek: Gameweek number
            announcement: Ron's team announcement text

        Returns:
            Success status
        """
        message = f"🏴󠁧󠁢󠁥󠁮󠁧󠁿 *TEAM ANNOUNCEMENT - GAMEWEEK {gameweek}*\n\n"
        message += f"```\n{announcement}\n```"

        return self.send_message(message)

    def notify_transfer(self, gameweek: int, player_out: str, player_in: str,
                       reasoning: str, is_hit: bool = False) -> bool:
        """
        Send transfer notification.

        Args:
            gameweek: Gameweek number
            player_out: Player being transferred out
            player_in: Player being transferred in
            reasoning: Transfer reasoning
            is_hit: Whether it's a points hit

        Returns:
            Success status
        """
        hit_emoji = "⚠️" if is_hit else "✅"
        hit_text = " (-4 HIT)" if is_hit else ""

        message = f"{hit_emoji} *TRANSFER - GW{gameweek}*{hit_text}\n\n"
        message += f"OUT: ❌ {player_out}\n"
        message += f"IN: ✅ {player_in}\n\n"
        message += f"*Ron says:*\n_{reasoning}_"

        return self.send_message(message)

    def notify_post_match_review(self, gameweek: int, review_text: str) -> bool:
        """
        Send post-gameweek review.

        Args:
            gameweek: Gameweek number
            review_text: Ron's post-match analysis

        Returns:
            Success status
        """
        message = f"🍺 *RON'S POST-MATCH THOUGHTS - GW{gameweek}*\n\n"
        message += f"```\n{review_text}\n```"

        return self.send_message(message)

    def notify_price_change(self, changes: List[Dict[str, Any]]) -> bool:
        """
        Send price change alert.

        Args:
            changes: List of price changes

        Returns:
            Success status
        """
        if not changes:
            return True

        message = "💰 *PRICE CHANGES*\n\n"

        rises = [c for c in changes if c.get('change', 0) > 0]
        falls = [c for c in changes if c.get('change', 0) < 0]

        if rises:
            message += "📈 *RISES:*\n"
            for change in rises:
                message += f"  • {change['name']}: £{change['old_price']}m → £{change['new_price']}m\n"
            message += "\n"

        if falls:
            message += "📉 *FALLS:*\n"
            for change in falls:
                message += f"  • {change['name']}: £{change['old_price']}m → £{change['new_price']}m\n"

        return self.send_message(message)

    def notify_injury_news(self, news: List[Dict[str, Any]]) -> bool:
        """
        Send injury news alert.

        Args:
            news: List of injury news items

        Returns:
            Success status
        """
        if not news:
            return True

        message = "🏥 *INJURY NEWS*\n\n"

        for item in news:
            status_emoji = "❌" if item.get('status') == 'out' else "⚠️"
            message += f"{status_emoji} *{item['name']}*: {item['news']}\n"

        return self.send_message(message)

    def notify_chip_used(self, gameweek: int, chip: str, reasoning: str) -> bool:
        """
        Send chip usage notification.

        Args:
            gameweek: Gameweek number
            chip: Chip name
            reasoning: Why the chip was used

        Returns:
            Success status
        """
        chip_emoji = {
            'wildcard': '🃏',
            'freehit': '🎯',
            'bencboost': '💪',
            'triplecap': '👑'
        }.get(chip.lower(), '💎')

        message = f"{chip_emoji} *CHIP ACTIVATED - GW{gameweek}*\n\n"
        message += f"*{chip.upper()}*\n\n"
        message += f"*Ron's thinking:*\n_{reasoning}_"

        return self.send_message(message)

    # =================================================================
    # COMMAND HANDLERS
    # =================================================================

    def cmd_start(self, update: 'Update', context: 'CallbackContext'):
        """Handle /start command."""
        message = (
            "⚽ *Ron Clanker's FPL Bot*\n\n"
            "Right, lad. I'm Ron Clanker. This is my FPL bot.\n\n"
            "*Commands:*\n"
            "/status - Current team overview\n"
            "/team - Full squad with formation\n"
            "/league - Mini-league standings\n"
            "/chips - Available chips\n"
            "/predictions - Next gameweek predictions\n"
            "/help - Show this message\n\n"
            "You'll get automatic updates when I make decisions. "
            "No nonsense, just the facts."
        )
        update.message.reply_text(message, parse_mode='Markdown')

    def cmd_help(self, update: 'Update', context: 'CallbackContext'):
        """Handle /help command."""
        self.cmd_start(update, context)

    def cmd_status(self, update: 'Update', context: 'CallbackContext'):
        """Handle /status command - current team overview."""
        if not self.db:
            update.message.reply_text("Database not available")
            return

        try:
            from utils.gameweek import get_current_gameweek

            current_gw = get_current_gameweek(self.db)
            team_id = self.config.get('team_id')

            # Get current team
            team = self.db.execute_query("""
                SELECT p.web_name, p.element_type, rt.is_captain, rt.position
                FROM rival_team_picks rt
                JOIN players p ON rt.player_id = p.id
                WHERE rt.entry_id = ? AND rt.gameweek = ?
                ORDER BY rt.position
            """, (team_id, current_gw))

            if not team:
                update.message.reply_text(f"No team data for GW{current_gw}")
                return

            starting = [p for p in team if p['position'] <= 11]
            captain = next((p for p in starting if p['is_captain']), None)

            message = f"📊 *CURRENT STATUS - GW{current_gw}*\n\n"
            message += f"*Captain:* {captain['web_name'] if captain else 'Unknown'}\n"
            message += f"*Squad:* {len(team)} players\n"
            message += f"*Formation:* {len([p for p in starting if p['element_type']==2])}-"
            message += f"{len([p for p in starting if p['element_type']==3])}-"
            message += f"{len([p for p in starting if p['element_type']==4])}\n\n"
            message += "Use /team for full squad details"

            update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Status command error: {e}")
            update.message.reply_text(f"Error getting status: {e}")

    def cmd_team(self, update: 'Update', context: 'CallbackContext'):
        """Handle /team command - full squad."""
        if not self.db:
            update.message.reply_text("Database not available")
            return

        try:
            from utils.gameweek import get_current_gameweek

            current_gw = get_current_gameweek(self.db)
            team_id = self.config.get('team_id')

            team = self.db.execute_query("""
                SELECT p.web_name, p.element_type, rt.is_captain, rt.position
                FROM rival_team_picks rt
                JOIN players p ON rt.player_id = p.id
                WHERE rt.entry_id = ? AND rt.gameweek = ?
                ORDER BY rt.position
            """, (team_id, current_gw))

            if not team:
                update.message.reply_text(f"No team data for GW{current_gw}")
                return

            message = f"⚽ *THE SQUAD - GW{current_gw}*\n\n"

            # Group by position
            by_pos = {1: [], 2: [], 3: [], 4: []}
            for p in team:
                if p['position'] <= 11:  # Starting XI
                    by_pos[p['element_type']].append(p)

            pos_names = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

            for pos in [1, 2, 3, 4]:
                if by_pos[pos]:
                    message += f"*{pos_names[pos]}:*\n"
                    for p in by_pos[pos]:
                        cap = " (C)" if p['is_captain'] else ""
                        message += f"  • {p['web_name']}{cap}\n"
                    message += "\n"

            # Bench
            bench = [p for p in team if p['position'] > 11]
            if bench:
                message += "*BENCH:*\n"
                for p in bench:
                    message += f"  {p['position']-11}. {p['web_name']}\n"

            update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Team command error: {e}")
            update.message.reply_text(f"Error getting team: {e}")

    def cmd_league(self, update: 'Update', context: 'CallbackContext'):
        """Handle /league command - mini-league standings."""
        if not self.db:
            update.message.reply_text("Database not available")
            return

        try:
            from utils.gameweek import get_current_gameweek

            current_gw = get_current_gameweek(self.db)
            league_id = self.config.get('league_id')
            team_id = self.config.get('team_id')

            standings = self.db.execute_query("""
                SELECT entry_name, player_name, rank, total_points, entry_id
                FROM rival_teams
                WHERE league_id = ? AND gameweek = ?
                ORDER BY rank
                LIMIT 10
            """, (league_id, current_gw))

            if not standings:
                update.message.reply_text("No league data available")
                return

            league_info = self.db.execute_query("SELECT name FROM leagues WHERE id = ?", (league_id,))
            league_name = league_info[0]['name'] if league_info else f"League {league_id}"

            message = f"🏆 *{league_name.upper()}* - GW{current_gw}\n\n"

            for s in standings:
                marker = "👉" if s['entry_id'] == team_id else "  "
                message += f"{marker} {s['rank']}. {s['entry_name']}: {s['total_points']} pts\n"

            update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"League command error: {e}")
            update.message.reply_text(f"Error getting league: {e}")

    def cmd_chips(self, update: 'Update', context: 'CallbackContext'):
        """Handle /chips command - available chips."""
        message = (
            "💎 *AVAILABLE CHIPS*\n\n"
            "First Half (GW1-19):\n"
            "  • Wildcard 1\n"
            "  • Free Hit 1\n"
            "  • Bench Boost 1\n"
            "  • Triple Captain 1\n\n"
            "Second Half (GW20-38):\n"
            "  • Wildcard 2\n"
            "  • Free Hit 2\n"
            "  • Bench Boost 2\n"
            "  • Triple Captain 2\n\n"
            "_Note: Chips must be used in their designated half or lost._"
        )
        update.message.reply_text(message, parse_mode='Markdown')

    def cmd_predictions(self, update: 'Update', context: 'CallbackContext'):
        """Handle /predictions command - next GW predictions."""
        update.message.reply_text(
            "🔮 *PREDICTIONS*\n\n"
            "ML predictions coming soon!\n"
            "Check back after models are trained."
        )

    # =================================================================
    # BOT CONTROL
    # =================================================================

    def start_polling(self):
        """Start the bot in polling mode."""
        logger.info("Starting Telegram bot (polling mode)...")
        self.updater.start_polling()
        logger.info("Bot is running. Press Ctrl+C to stop.")

    def start_webhook(self, webhook_url: str, port: int = 8443):
        """Start the bot in webhook mode."""
        logger.info(f"Starting Telegram bot (webhook mode): {webhook_url}")
        self.updater.start_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=self.token,
            webhook_url=f"{webhook_url}/{self.token}"
        )
        logger.info("Bot is running via webhook")

    def stop(self):
        """Stop the bot."""
        logger.info("Stopping Telegram bot...")
        self.updater.stop()
        logger.info("Bot stopped")

    def idle(self):
        """Keep the bot running until interrupted."""
        self.updater.idle()
