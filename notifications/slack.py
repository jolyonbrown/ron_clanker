#!/usr/bin/env python3
"""
Slack Webhook Notifications

Sends Ron's team announcements and gameweek reviews to Slack channels.
"""

import logging
import requests
from typing import Dict, Any, Optional
import os

logger = logging.getLogger('ron_clanker.slack')


class SlackNotifier:
    """
    Sends notifications to Slack via webhook.

    Supports:
    - Pre-deadline team announcements
    - Post-gameweek reviews with banter
    - Transfer announcements
    """

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL (or reads from SLACK_WEBHOOK_URL env var)
        """
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')

        if not self.webhook_url:
            logger.warning("No Slack webhook URL configured. Notifications disabled.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Slack notifications ENABLED")

    def send_message(self, text: str, blocks: Optional[list] = None) -> bool:
        """
        Send a message to Slack.

        Args:
            text: Plain text message (fallback)
            blocks: Slack Block Kit blocks for rich formatting

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Slack disabled, skipping notification")
            return False

        payload = {
            'text': text
        }

        if blocks:
            payload['blocks'] = blocks

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.error(f"Slack notification failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    def send_team_announcement(self, announcement_text: str, gameweek: int) -> bool:
        """
        Send Ron's pre-deadline team announcement.

        Args:
            announcement_text: Ron's team announcement (from persona.py)
            gameweek: Current gameweek

        Returns:
            True if sent successfully
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🏴󠁧󠁢󠁥󠁮󠁧󠁿 RON'S TEAM - GAMEWEEK {gameweek}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{announcement_text}```"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Ron Clanker - Autonomous FPL Manager_"
                    }
                ]
            }
        ]

        return self.send_message(
            text=f"RON'S TEAM - GW{gameweek}\n\n{announcement_text}",
            blocks=blocks
        )

    def send_gameweek_review(
        self,
        review_text: str,
        gameweek: int,
        ron_points: int,
        average_points: int,
        league_position: Optional[int] = None
    ) -> bool:
        """
        Send Ron's post-gameweek review with banter.

        Args:
            review_text: Ron's post-match analysis (from persona.py)
            gameweek: Gameweek number
            ron_points: Ron's points this GW
            average_points: Average points this GW
            league_position: Ron's position in mini-league (optional)

        Returns:
            True if sent successfully
        """

        # Emoji based on performance
        diff = ron_points - average_points
        if diff >= 15:
            emoji = "🔥"
            mood = "SUPERB"
        elif diff >= 5:
            emoji = "✅"
            mood = "SOLID"
        elif diff >= -5:
            emoji = "😐"
            mood = "MEH"
        elif diff >= -15:
            emoji = "😬"
            mood = "POOR"
        else:
            emoji = "💩"
            mood = "SHAMBLES"

        header_text = f"{emoji} RON'S GW{gameweek} REVIEW - {mood}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": header_text,
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Ron's Points:*\n{ron_points}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Average:*\n{average_points}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Difference:*\n{diff:+d}"
                    }
                ]
            }
        ]

        if league_position:
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*League Position:*\n{league_position}"
                    }
                ]
            })

        blocks.append({
            "type": "divider"
        })

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{review_text}```"
            }
        })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_Ron Clanker - Still undefeated at trash talk_"
                }
            ]
        })

        return self.send_message(
            text=f"RON'S GW{gameweek} REVIEW\n\n{review_text}",
            blocks=blocks
        )

    def send_transfer_announcement(
        self,
        transfer_text: str,
        gameweek: int,
        num_transfers: int,
        points_hit: int = 0
    ) -> bool:
        """
        Send Ron's transfer announcement.

        Args:
            transfer_text: Transfer announcement from persona.py
            gameweek: Gameweek number
            num_transfers: Number of transfers made
            points_hit: Points deducted for transfers (0 if free)

        Returns:
            True if sent successfully
        """
        if num_transfers == 0:
            emoji = "🔒"
            header = f"NO CHANGES - GW{gameweek}"
        elif points_hit > 0:
            emoji = "💸"
            header = f"TRANSFERS (-{points_hit}) - GW{gameweek}"
        else:
            emoji = "🔄"
            header = f"TRANSFERS - GW{gameweek}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} RON'S {header}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{transfer_text}```"
                }
            }
        ]

        return self.send_message(
            text=f"RON'S TRANSFERS - GW{gameweek}\n\n{transfer_text}",
            blocks=blocks
        )


def send_team_announcement_to_slack(announcement: str, gameweek: int) -> bool:
    """
    Convenience function to send team announcement.

    Args:
        announcement: Team announcement text
        gameweek: Gameweek number

    Returns:
        True if sent successfully
    """
    notifier = SlackNotifier()
    return notifier.send_team_announcement(announcement, gameweek)


def send_gameweek_review_to_slack(
    review: str,
    gameweek: int,
    ron_points: int,
    average_points: int,
    league_position: Optional[int] = None
) -> bool:
    """
    Convenience function to send gameweek review.

    Args:
        review: Review text
        gameweek: Gameweek number
        ron_points: Ron's points
        average_points: Average points
        league_position: League position (optional)

    Returns:
        True if sent successfully
    """
    notifier = SlackNotifier()
    return notifier.send_gameweek_review(
        review,
        gameweek,
        ron_points,
        average_points,
        league_position
    )
