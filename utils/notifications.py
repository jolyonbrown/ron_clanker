"""
Notification System

Sends notifications to Discord, Slack, or other webhook services.
Used for alerts about team selections, price changes, and system status.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger('ron_clanker.notifications')


class NotificationService:
    """Service for sending webhook notifications."""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize notification service.

        Args:
            webhook_url: Discord/Slack webhook URL. If None, reads from env.
        """
        self.webhook_url = webhook_url or os.getenv('WEBHOOK_URL')
        self.enabled = bool(self.webhook_url)

        if not self.enabled:
            logger.info("Notifications disabled - no WEBHOOK_URL configured")

    def send_team_selection(self, gameweek: int, announcement: str, deadline: str) -> bool:
        """
        Send team selection notification.

        Args:
            gameweek: Gameweek number
            announcement: Ron's team announcement text
            deadline: Deadline timestamp

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        try:
            import requests

            # Format for Discord/Slack
            message = {
                "content": f"🤖 **Ron Clanker - GW{gameweek} Team Selection**",
                "embeds": [{
                    "title": f"Gameweek {gameweek} Team",
                    "description": announcement[:2000],  # Discord limit
                    "color": 3447003,  # Blue
                    "footer": {
                        "text": f"Deadline: {deadline}"
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }

            response = requests.post(
                self.webhook_url,
                json=message,
                timeout=10
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info(f"Notification sent: GW{gameweek} team selection")
                return True
            else:
                logger.warning(f"Notification failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Notification error: {e}", exc_info=True)
            return False

    def send_price_changes(self, rises: list, falls: list) -> bool:
        """
        Send price change notification.

        Args:
            rises: List of players who rose (dicts with name, old, new)
            falls: List of players who fell

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        if not rises and not falls:
            return True  # Nothing to notify

        try:
            import requests

            # Format message
            content = "📊 **Price Changes Detected**\n\n"

            if rises:
                content += f"📈 **Rises ({len(rises)}):**\n"
                for p in rises[:5]:  # Limit to 5
                    content += f"• {p['name']}: £{p['old']:.1f}m → £{p['new']:.1f}m\n"
                if len(rises) > 5:
                    content += f"_(and {len(rises) - 5} more)_\n"

            if falls:
                content += f"\n📉 **Falls ({len(falls)}):**\n"
                for p in falls[:5]:
                    content += f"• {p['name']}: £{p['old']:.1f}m → £{p['new']:.1f}m\n"
                if len(falls) > 5:
                    content += f"_(and {len(falls) - 5} more)_\n"

            message = {
                "content": content[:2000]
            }

            response = requests.post(
                self.webhook_url,
                json=message,
                timeout=10
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info(f"Notification sent: {len(rises)} rises, {len(falls)} falls")
                return True
            else:
                logger.warning(f"Notification failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Notification error: {e}", exc_info=True)
            return False

    def send_alert(self, title: str, message: str, level: str = "info") -> bool:
        """
        Send generic alert notification.

        Args:
            title: Alert title
            message: Alert message
            level: Alert level (info, warning, error)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        try:
            import requests

            # Color by level
            colors = {
                "info": 3447003,    # Blue
                "warning": 16776960, # Yellow
                "error": 15158332    # Red
            }

            # Emoji by level
            emojis = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌"
            }

            color = colors.get(level, colors["info"])
            emoji = emojis.get(level, emojis["info"])

            payload = {
                "embeds": [{
                    "title": f"{emoji} {title}",
                    "description": message[:2000],
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info(f"Alert sent: {title}")
                return True
            else:
                logger.warning(f"Alert failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Alert error: {e}", exc_info=True)
            return False

    def send_health_check(self, results: list) -> bool:
        """
        Send health check notification.

        Args:
            results: List of (check_name, passed, message) tuples

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        try:
            import requests

            passed_count = sum(1 for _, passed, _ in results if passed)
            total_count = len(results)
            all_passed = passed_count == total_count

            # Format message
            content = "🏥 **System Health Check**\n\n"

            for name, passed, message in results:
                status = "✅" if passed else "❌"
                content += f"{status} **{name}**: {message}\n"

            content += f"\n**Status**: {passed_count}/{total_count} checks passed"

            # Color based on health
            color = 2067276 if all_passed else 15158332  # Green or Red

            payload = {
                "embeds": [{
                    "title": "System Health Check",
                    "description": content[:2000],
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info("Health check notification sent")
                return True
            else:
                logger.warning(f"Health check notification failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Health check notification error: {e}", exc_info=True)
            return False
