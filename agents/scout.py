"""
Scout Agent - "The Scout"

Monitors external sources for intelligence: injury news, team news, rotation
risks, press conferences, etc.

The Scout's Responsibilities:
- Monitor websites (Premier Injuries, BBC Sport, etc.)
- Monitor YouTube transcripts (FPL content creators)
- Monitor email newsletters (LazyFPL, etc.)
- Classify intelligence (confirmed, rumored, speculation)
- Assign confidence scores (0-1)
- Match player names to FPL IDs
- Publish intelligence events for other agents

This gives Ron early competitive advantage on injuries, rotation, and team news.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import re

from agents.base_agent import BaseAgent
from data.database import Database
from agents.data_collector import DataCollector
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


@dataclass
class IntelligenceItem:
    """A piece of intelligence gathered from external sources."""
    type: str  # "INJURY", "ROTATION", "SUSPENSION", "LINEUP_LEAK", "PRESS_CONFERENCE"
    player_id: Optional[int]  # FPL player ID (None if not matched yet)
    player_name: str
    details: str  # The intelligence text
    confidence: float  # 0-1 score
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    source: str  # Where this came from
    timestamp: datetime
    actionable: bool  # Should we act on this?
    raw_data: Optional[Dict] = None  # Original scraped data


class ScoutAgent(BaseAgent):
    """
    The Scout - Intelligence Gathering Agent

    Monitors external sources for team news, injuries, rotation risks.

    Sources (Phase 2):
    - RSS feeds: BBC Sport, Sky Sports (fastest, most reliable)
    - YouTube transcripts: FPL content creators (FPL Harry, etc.)
    - Website scraping: Premier Injuries, BBC Sport (backup)

    Future:
    - Email parsing: LazyFPL newsletters
    - Twitter alternatives: Nitter RSS, manual webhooks

    Intelligence Pipeline:
    1. Monitor sources (scheduled every 30 mins)
    2. Extract raw intelligence
    3. Classify and score confidence
    4. Match players to FPL IDs
    5. Publish high-confidence intelligence events
    6. Track source reliability over time (like Ellie)

    Subscribes to:
    - PRICE_CHECK: Trigger during daily monitoring
    - GAMEWEEK_PLANNING: Check for late team news

    Publishes:
    - INJURY_INTELLIGENCE: Player injury detected
    - ROTATION_RISK: Rotation warning
    - SUSPENSION_INTELLIGENCE: Suspension detected
    - LINEUP_LEAK: Early team news
    - PRESS_CONFERENCE_UPDATE: Manager quotes
    """

    def __init__(
        self,
        database: Database = None,
        data_collector: DataCollector = None
    ):
        """
        Initialize The Scout.

        Args:
            database: Optional database instance
            data_collector: Optional data collector for player matching
        """
        super().__init__(agent_name="scout")
        self.db = database or Database()
        self.data_collector = data_collector or DataCollector()

        # Components
        from intelligence.website_monitor import WebsiteMonitor
        from intelligence.rss_monitor import RSSMonitor
        from intelligence.youtube_monitor import YouTubeMonitor
        from intelligence.intelligence_classifier import IntelligenceClassifier

        self.website_monitor = WebsiteMonitor()
        self.rss_monitor = RSSMonitor()
        self.youtube_monitor = YouTubeMonitor()
        self.classifier = IntelligenceClassifier()  # Will be loaded with players on start

        # Player name cache for fuzzy matching
        self._player_cache: Dict[str, int] = {}

        logger.info("Scout (Intelligence Agent) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        await self.subscribe_to(EventType.PRICE_CHECK)  # Daily monitoring trigger
        await self.subscribe_to(EventType.GAMEWEEK_PLANNING)  # Check for late news

        logger.info("Scout: Subscribed to PRICE_CHECK and GAMEWEEK_PLANNING")

    async def handle_event(self, event: Event) -> None:
        """
        Handle incoming events.

        Args:
            event: The event to process
        """
        try:
            if event.event_type == EventType.PRICE_CHECK:
                # Daily monitoring trigger
                await self._run_daily_monitoring()

            elif event.event_type == EventType.GAMEWEEK_PLANNING:
                # Check for late breaking news before deadline
                trigger_point = event.payload.get('trigger_point')

                if trigger_point == '6h':
                    # 6 hours before deadline - check for last-minute news
                    logger.info("Scout: Checking for late breaking team news (6h before deadline)")
                    await self._check_urgent_intelligence()

        except Exception as e:
            logger.error(f"Scout: Error handling event {event.event_type}: {e}")

    async def gather_intelligence(self) -> List[Dict[str, Any]]:
        """
        Gather intelligence from all sources and return as list of dicts.

        This is the public method used by scripts for daily intelligence gathering.

        Returns:
            List of intelligence items as dictionaries
        """
        logger.info("Scout: Gathering intelligence from all sources")

        try:
            # Check RSS feeds (fastest and most reliable)
            rss_intel = await self.rss_monitor.check_all(max_age_hours=24)
            logger.info(f"Scout: Found {len(rss_intel)} items from RSS feeds")

            # Check website sources (with polite delays)
            async with self.website_monitor as monitor:
                website_intel = await monitor.check_all()
            logger.info(f"Scout: Found {len(website_intel)} items from websites")

            # Check YouTube videos (if any configured)
            youtube_intel = await self.youtube_monitor.check_all(max_age_hours=24)
            logger.info(f"Scout: Found {len(youtube_intel)} items from YouTube")

            # Combine all raw intelligence
            raw_intelligence = rss_intel + website_intel + youtube_intel

            # Convert raw intelligence to IntelligenceItems using classifier
            all_intelligence: List[Dict[str, Any]] = []

            for raw in raw_intelligence:
                # Classify intelligence (confidence, severity, player matching)
                classified = self.classifier.classify(
                    raw,
                    base_confidence=raw.get('base_reliability', 0.8)
                )

                # Build intelligence dict
                intel_dict = {
                    'type': raw['type'],
                    'player_id': classified.player_id,
                    'player_name': classified.matched_name or raw['player_name'],
                    'details': raw['details'],
                    'confidence': classified.confidence,
                    'severity': classified.severity,
                    'source': raw['source'],
                    'timestamp': raw['timestamp'],
                    'actionable': classified.actionable,
                }
                all_intelligence.append(intel_dict)

            logger.info(f"Scout: Processed {len(all_intelligence)} total intelligence items")
            return all_intelligence

        except Exception as e:
            logger.error(f"Scout: Error gathering intelligence: {e}")
            return []

    async def _run_daily_monitoring(self) -> None:
        """
        Run daily intelligence monitoring.

        This is triggered by PRICE_CHECK events (03:00 AM daily).
        Monitors all sources and publishes intelligence events.
        """
        logger.info("Scout: Running daily intelligence monitoring")

        try:
            # Gather intelligence
            all_intelligence_dicts = await self.gather_intelligence()

            # Publish events for actionable intelligence
            for intel_dict in all_intelligence_dicts:
                if intel_dict['actionable'] and intel_dict['confidence'] > 0.7:
                    # Convert dict back to IntelligenceItem for event publishing
                    intel = IntelligenceItem(
                        type=intel_dict['type'],
                        player_id=intel_dict['player_id'],
                        player_name=intel_dict['player_name'],
                        details=intel_dict['details'],
                        confidence=intel_dict['confidence'],
                        severity=intel_dict['severity'],
                        source=intel_dict['source'],
                        timestamp=intel_dict['timestamp'],
                        actionable=intel_dict['actionable'],
                    )
                    await self._publish_intelligence(intel)

            logger.info(f"Scout: Processed {len(all_intelligence_dicts)} intelligence items")

        except Exception as e:
            logger.error(f"Scout: Error in daily monitoring: {e}")

    async def _check_urgent_intelligence(self) -> None:
        """
        Check for urgent last-minute intelligence.

        Called 6h before deadline - check for late breaking news.
        """
        logger.info("Scout: Checking for urgent intelligence")

        # Run same monitoring but with urgency flag
        await self._run_daily_monitoring()

    async def _publish_intelligence(self, intel: IntelligenceItem) -> None:
        """
        Publish intelligence event.

        Args:
            intel: The intelligence item to publish
        """
        # Determine event type
        event_type_map = {
            'INJURY': EventType.INJURY_INTELLIGENCE,
            'ROTATION': EventType.ROTATION_RISK,
            'SUSPENSION': EventType.SUSPENSION_INTELLIGENCE,
            'LINEUP_LEAK': EventType.LINEUP_LEAK,
            'PRESS_CONFERENCE': EventType.PRESS_CONFERENCE_UPDATE,
        }

        event_type = event_type_map.get(intel.type, EventType.INTELLIGENCE_DETECTED)

        # Determine priority based on severity
        priority_map = {
            'CRITICAL': EventPriority.CRITICAL,
            'HIGH': EventPriority.HIGH,
            'MEDIUM': EventPriority.NORMAL,
            'LOW': EventPriority.LOW,
        }
        priority = priority_map.get(intel.severity, EventPriority.NORMAL)

        # Build payload
        payload = {
            'type': intel.type,
            'player_id': intel.player_id,
            'player_name': intel.player_name,
            'details': intel.details,
            'confidence': intel.confidence,
            'severity': intel.severity,
            'source': intel.source,
            'actionable': intel.actionable,
            'timestamp': intel.timestamp.isoformat()
        }

        # Publish event
        await self.publish_event(
            event_type,
            payload=payload,
            priority=priority
        )

        logger.info(
            f"Scout: Published {intel.type} intelligence - "
            f"{intel.player_name} ({intel.confidence:.0%} confidence) "
            f"from {intel.source}"
        )

        # Log to database for reliability tracking
        await self._log_intelligence(intel)

    async def _log_intelligence(self, intel: IntelligenceItem) -> None:
        """
        Log intelligence to database for tracking.

        This allows us to track which sources are accurate over time.
        Similar to how Ellie tracks agent performance.

        Args:
            intel: The intelligence item to log
        """
        try:
            # TODO: Create intelligence_log table in database
            # For now, just log to decisions table
            self.db.execute_update(
                """
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    None,  # May not have gameweek yet
                    'intelligence_detected',
                    f"Player: {intel.player_name}, Type: {intel.type}",
                    f"Source: {intel.source}, Confidence: {intel.confidence:.0%}, Details: {intel.details}",
                    'scout'
                )
            )
        except Exception as e:
            logger.error(f"Scout: Error logging intelligence: {e}")

    def _match_player_name(self, name: str) -> Optional[int]:
        """
        Match a player name to FPL player ID.

        Uses fuzzy matching to handle variations:
        - "Haaland" -> "Erling Haaland"
        - "Gabriel" -> "Gabriel dos Santos Magalhães"
        - "Salah" -> "Mohamed Salah"

        Args:
            name: Player name from intelligence source

        Returns:
            FPL player ID or None if no match
        """
        # Check cache first
        if name in self._player_cache:
            return self._player_cache[name]

        # TODO (ron_clanker-28): Implement fuzzy player name matching
        # For now, return None
        return None

    async def load_player_cache(self) -> None:
        """
        Load player names from database for fuzzy matching.

        Should be called on startup.
        """
        try:
            players = self.db.execute_query(
                "SELECT id, web_name, first_name, second_name FROM players"
            )

            for player in players:
                # Add all name variations to cache
                self._player_cache[player['web_name'].lower()] = player['id']

                full_name = f"{player['first_name']} {player['second_name']}".lower()
                self._player_cache[full_name] = player['id']

                # Just surname
                self._player_cache[player['second_name'].lower()] = player['id']

            # Update classifier with player cache
            from intelligence.intelligence_classifier import IntelligenceClassifier
            self.classifier = IntelligenceClassifier(self._player_cache)

            logger.info(f"Scout: Loaded {len(players)} players into cache and classifier")

        except Exception as e:
            logger.error(f"Scout: Error loading player cache: {e}")


def get_scout() -> ScoutAgent:
    """Get singleton Scout agent instance."""
    return ScoutAgent()
