"""
Website Monitor for Intelligence Gathering

Scrapes trusted websites for injury and team news:
- Premier Injuries (premierinjuries.com)
- BBC Sport
- Official Premier League

Used by Scout agent to gather early intelligence on injuries, rotation, team news.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


class WebsiteMonitor:
    """
    Monitor websites for injury and team news.

    Scrapes structured data from trusted sources and returns
    raw intelligence for classification.
    """

    # Source configurations
    SOURCES = {
        'premier_injuries': {
            'url': 'https://www.premierinjuries.com/injury-table.php',
            'reliability': 0.95,  # Very accurate
            'parser': 'parse_premier_injuries',
            'enabled': True
        },
        'bbc_sport_football': {
            'url': 'https://www.bbc.com/sport/football',
            'reliability': 0.90,
            'parser': 'parse_bbc_sport',
            'enabled': True
        },
    }

    def __init__(self):
        """Initialize website monitor."""
        self.session: Optional[aiohttp.ClientSession] = None

        # More realistic browser headers to avoid bot detection
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        logger.info("WebsiteMonitor initialized")

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def check_all(self) -> List[Dict[str, Any]]:
        """
        Check all configured website sources.

        Returns:
            List of raw intelligence items
        """
        intelligence = []

        for source_name, config in self.SOURCES.items():
            if not config.get('enabled'):
                continue

            try:
                logger.info(f"WebsiteMonitor: Checking {source_name}...")

                # Fetch page
                html = await self._fetch(config['url'])

                if not html:
                    logger.warning(f"WebsiteMonitor: No data from {source_name}")
                    continue

                # Parse with appropriate parser
                parser_method = getattr(self, config['parser'])
                source_intel = parser_method(html)

                # Enrich with metadata
                for item in source_intel:
                    item['source'] = source_name
                    item['base_reliability'] = config['reliability']
                    item['scraped_at'] = datetime.now()

                intelligence.extend(source_intel)
                logger.info(f"WebsiteMonitor: Found {len(source_intel)} items from {source_name}")

                # Polite delay between requests
                import asyncio
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"WebsiteMonitor: Error checking {source_name}: {e}")

        return intelligence

    async def _fetch(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        Fetch HTML from URL.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            HTML string or None if error
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(headers=self.headers)

            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"WebsiteMonitor: HTTP {response.status} for {url}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"WebsiteMonitor: Network error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"WebsiteMonitor: Error fetching {url}: {e}")
            return None

    def parse_premier_injuries(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse premierinjuries.com injury table.

        This site has a structured table with:
        - Player name
        - Club
        - Injury type
        - Return date
        - Status (out/doubtful)

        Args:
            html: HTML content

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Find injury table
            # Note: Actual selectors need to be inspected from the live site
            # This is a template that will need adjustment

            injury_rows = soup.find_all('tr', class_=re.compile('injury|player'))

            for row in injury_rows[:50]:  # Limit to 50 to avoid noise
                try:
                    # Extract data from row
                    # This needs to be adjusted based on actual site structure
                    cells = row.find_all('td')

                    if len(cells) < 4:
                        continue

                    player_name = cells[0].get_text(strip=True)
                    club = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    injury_type = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    return_date = cells[3].get_text(strip=True) if len(cells) > 3 else ''

                    if not player_name:
                        continue

                    # Build intelligence item
                    intelligence.append({
                        'type': 'INJURY',
                        'player_name': player_name,
                        'details': f"{injury_type} - expected back {return_date}".strip(),
                        'club': club,
                        'return_date': return_date,
                        'raw_text': row.get_text(strip=True),
                        'timestamp': datetime.now()
                    })

                except Exception as e:
                    logger.debug(f"WebsiteMonitor: Error parsing row: {e}")
                    continue

        except Exception as e:
            logger.error(f"WebsiteMonitor: Error parsing Premier Injuries: {e}")

        return intelligence

    def parse_bbc_sport(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse BBC Sport football page for injury/team news.

        Looks for:
        - Injury news headlines
        - Team news articles
        - Press conference summaries

        Args:
            html: HTML content

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Find news articles/headlines
            # BBC uses various structures, need to be flexible

            headlines = soup.find_all(['h2', 'h3', 'h4'], class_=re.compile('headline|title'))

            # Also check article summaries
            articles = soup.find_all('article')

            injury_keywords = [
                'injury', 'injured', 'out for', 'sidelined', 'ruled out',
                'doubtful', 'fitness', 'concern', 'suspended', 'ban',
                'rotation', 'rested', 'team news', 'press conference'
            ]

            # Check headlines
            for headline in headlines[:30]:  # Limit to recent news
                text = headline.get_text(strip=True)
                text_lower = text.lower()

                # Check if relevant
                if not any(keyword in text_lower for keyword in injury_keywords):
                    continue

                # Try to extract player name (heuristic)
                # Look for capitalized words (likely player names)
                words = text.split()
                potential_names = []
                for i, word in enumerate(words):
                    if word[0].isupper() and word not in ['The', 'A', 'An', 'In', 'On', 'For']:
                        if i + 1 < len(words) and words[i+1][0].isupper():
                            potential_names.append(f"{word} {words[i+1]}")

                for name in potential_names:
                    intelligence.append({
                        'type': self._classify_type(text_lower),
                        'player_name': name,
                        'details': text,
                        'raw_text': text,
                        'timestamp': datetime.now()
                    })

            # Check article content for more details
            for article in articles[:20]:
                text = article.get_text(strip=True)
                text_lower = text.lower()

                if not any(keyword in text_lower for keyword in injury_keywords):
                    continue

                # Extract structured info with regex
                # Pattern: "Player Name is injured/out"
                patterns = [
                    r'([A-Z][a-z]+ [A-Z][a-z]+) (?:is|has been) (?:injured|out for|sidelined|ruled out)',
                    r'([A-Z][a-z]+ [A-Z][a-z]+) (?:doubtful|fitness concern)',
                    r'([A-Z][a-z]+ [A-Z][a-z]+) (?:suspended|banned)',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, text)
                    for player_name in matches:
                        # Get surrounding context (50 chars either side)
                        match_pos = text.find(player_name)
                        context_start = max(0, match_pos - 50)
                        context_end = min(len(text), match_pos + len(player_name) + 100)
                        context = text[context_start:context_end]

                        intelligence.append({
                            'type': self._classify_type(context.lower()),
                            'player_name': player_name,
                            'details': context.strip(),
                            'raw_text': context,
                            'timestamp': datetime.now()
                        })

        except Exception as e:
            logger.error(f"WebsiteMonitor: Error parsing BBC Sport: {e}")

        return intelligence

    def _classify_type(self, text: str) -> str:
        """
        Classify intelligence type from text.

        Args:
            text: Text to classify

        Returns:
            Intelligence type (INJURY, SUSPENSION, ROTATION, PRESS_CONFERENCE)
        """
        text_lower = text.lower()

        if any(word in text_lower for word in ['suspended', 'banned', 'red card']):
            return 'SUSPENSION'
        elif any(word in text_lower for word in ['rotation', 'rested', 'rotated']):
            return 'ROTATION'
        elif any(word in text_lower for word in ['press conference', 'manager said', 'boss said']):
            return 'PRESS_CONFERENCE'
        else:
            return 'INJURY'


async def test_monitor():
    """Test the website monitor."""
    print("Testing WebsiteMonitor...\n")

    async with WebsiteMonitor() as monitor:
        intelligence = await monitor.check_all()

        print(f"Found {len(intelligence)} intelligence items:\n")

        for item in intelligence[:10]:  # Show first 10
            print(f"[{item['type']}] {item['player_name']}")
            print(f"  Source: {item['source']} ({item['base_reliability']:.0%} reliable)")
            print(f"  Details: {item['details'][:100]}...")
            print()


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_monitor())
