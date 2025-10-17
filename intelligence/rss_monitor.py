"""
RSS Feed Monitor for Intelligence Gathering

Monitors RSS feeds from football news sources for injury/team news.

RSS feeds are the IDEAL source:
- Designed for programmatic access
- No bot detection
- Fast and reliable
- Real-time updates

Used by Scout agent to gather early intelligence.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime
import feedparser
import aiohttp
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class RSSMonitor:
    """
    Monitor RSS feeds for injury and team news.

    RSS feeds are designed for automated consumption - no scraping issues!
    """

    # RSS feed configurations
    FEEDS = {
        'bbc_sport_football': {
            'url': 'http://feeds.bbci.co.uk/sport/football/rss.xml',
            'reliability': 0.95,  # Very reliable
            'enabled': True
        },
        'sky_sports_football': {
            'url': 'https://www.skysports.com/rss/12040',
            'reliability': 0.90,
            'enabled': True
        },
        'premier_league_official': {
            'url': 'https://www.premierleague.com/news?pageSize=20&type=all',  # May have RSS
            'reliability': 1.0,  # Official source
            'enabled': False  # Need to verify RSS availability
        },
        'sky_sports_premier_league': {
            'url': 'https://www.skysports.com/rss/0,20514,11661,00.xml',
            'reliability': 0.90,
            'enabled': True
        },
    }

    def __init__(self):
        """Initialize RSS monitor."""
        self._last_check: Dict[str, datetime] = {}
        logger.info("RSSMonitor initialized")

    async def check_all(self, max_age_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Check all configured RSS feeds.

        Args:
            max_age_hours: Only return items from last N hours

        Returns:
            List of raw intelligence items from RSS feeds
        """
        intelligence = []

        for feed_name, config in self.FEEDS.items():
            if not config.get('enabled'):
                continue

            try:
                logger.info(f"RSSMonitor: Checking {feed_name}...")

                # Fetch feed
                feed_intel = await self._fetch_feed(
                    config['url'],
                    config['reliability'],
                    feed_name,
                    max_age_hours
                )

                intelligence.extend(feed_intel)
                logger.info(f"RSSMonitor: Found {len(feed_intel)} items from {feed_name}")

            except Exception as e:
                logger.error(f"RSSMonitor: Error checking {feed_name}: {e}")

        return intelligence

    async def _fetch_feed(
        self,
        url: str,
        reliability: float,
        source_name: str,
        max_age_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Fetch and parse RSS feed.

        Args:
            url: Feed URL
            reliability: Source reliability score (0-1)
            source_name: Name of source
            max_age_hours: Only return items from last N hours

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            # Fetch feed asynchronously
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"RSSMonitor: HTTP {response.status} for {url}")
                        return []

                    feed_content = await response.text()

            # Parse RSS feed
            feed = feedparser.parse(feed_content)

            # Keywords that indicate injury/team news
            injury_keywords = [
                'injury', 'injured', 'out for', 'sidelined', 'ruled out',
                'doubtful', 'fitness', 'concern', 'suspended', 'ban',
                'rotation', 'rested', 'team news', 'press conference',
                'returns', 'comeback', 'recovery', 'unavailable', 'miss',
                'knee', 'hamstring', 'ankle', 'muscle', 'strain'
            ]

            # Process feed entries
            for entry in feed.entries[:50]:  # Limit to 50 most recent
                try:
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')
                    content = f"{title} {summary}".lower()

                    # Check if relevant
                    if not any(keyword in content for keyword in injury_keywords):
                        continue

                    # Check age
                    published = entry.get('published', entry.get('updated'))
                    if published:
                        try:
                            pub_date = date_parser.parse(published)
                            age_hours = (datetime.now(pub_date.tzinfo) - pub_date).total_seconds() / 3600

                            if age_hours > max_age_hours:
                                continue
                        except:
                            pass  # If can't parse date, include it anyway

                    # Extract player names (heuristic)
                    player_names = self._extract_player_names(title)

                    # Build intelligence item for each player mentioned
                    for player_name in player_names:
                        intel_type = self._classify_type(content)

                        intelligence.append({
                            'type': intel_type,
                            'player_name': player_name,
                            'details': title,
                            'summary': summary,
                            'link': entry.get('link', ''),
                            'published': published,
                            'source': source_name,
                            'base_reliability': reliability,
                            'timestamp': datetime.now()
                        })

                except Exception as e:
                    logger.debug(f"RSSMonitor: Error parsing entry: {e}")
                    continue

        except Exception as e:
            logger.error(f"RSSMonitor: Error fetching feed {url}: {e}")

        return intelligence

    def _extract_player_names(self, text: str) -> List[str]:
        """
        Extract player names from text.

        Heuristic: Look for capitalized names (2 words).

        Args:
            text: Text to extract from

        Returns:
            List of potential player names
        """
        import re

        # Pattern: Two capitalized words (likely a name)
        # E.g., "Cole Palmer", "Erling Haaland"
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
        matches = re.findall(pattern, text)

        # Filter out common false positives
        exclude_exact = [
            'Premier League', 'Fantasy Premier', 'Fantasy Football',
            'Manchester United', 'Manchester City', 'Liverpool FC',
            'Chelsea FC', 'Arsenal FC', 'Tottenham Hotspur',
            'The Guardian', 'Sky Sports', 'BBC Sport',
            'Press Conference', 'Team News', 'Injury Update',
            'Aston Villa', 'West Ham', 'Newcastle United',
            'Nottingham Forest', 'Brighton Hove', 'Leicester City',
            'Crystal Palace', 'Wolverhampton Wanderers',
            'Europa League', 'Champions League', 'Carabao Cup',
            'Injured Palmer',  # False match - strip "Injured" prefix
            'Maccabi Tel Aviv'
        ]

        # Strip common prefixes that aren't part of name
        prefix_words = ['Injured', 'Suspended', 'Benched']

        names = []
        for name in matches:
            if name in exclude_exact:
                continue

            # Strip prefix words
            for prefix in prefix_words:
                if name.startswith(f"{prefix} "):
                    name = name[len(prefix)+1:]
                    break

            # Must be at least 2 words
            if len(name.split()) < 2:
                continue

            # Not all caps (likely not a player name)
            if name.isupper():
                continue

            names.append(name)

        # Deduplicate
        return list(dict.fromkeys(names))

    def _classify_type(self, text: str) -> str:
        """
        Classify intelligence type from text.

        Args:
            text: Text to classify

        Returns:
            Intelligence type
        """
        text_lower = text.lower()

        if any(word in text_lower for word in ['suspended', 'banned', 'red card', 'yellow card']):
            return 'SUSPENSION'
        elif any(word in text_lower for word in ['rotation', 'rested', 'rotated', 'bench']):
            return 'ROTATION'
        elif any(word in text_lower for word in ['press conference', 'manager said', 'boss said', 'quotes']):
            return 'PRESS_CONFERENCE'
        elif any(word in text_lower for word in ['returns', 'comeback', 'back in', 'fit again', 'available']):
            return 'INJURY'  # Recovery news
        else:
            return 'INJURY'


async def test_rss_monitor():
    """Test the RSS monitor."""
    print("Testing RSSMonitor...\n")
    print("Checking RSS feeds for injury/team news in last 72 hours...\n")

    monitor = RSSMonitor()
    intelligence = await monitor.check_all(max_age_hours=72)

    print(f"Found {len(intelligence)} intelligence items:\n")
    print("=" * 80)

    for item in intelligence[:20]:  # Show first 20
        print(f"\n[{item['type']}] {item['player_name']}")
        print(f"  Source: {item['source']} ({item['base_reliability']:.0%} reliable)")
        print(f"  Details: {item['details']}")
        if item.get('link'):
            print(f"  Link: {item['link']}")
        print("-" * 80)

    print(f"\nTotal: {len(intelligence)} intelligence items from RSS feeds")


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_rss_monitor())
