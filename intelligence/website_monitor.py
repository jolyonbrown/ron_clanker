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
        'premier_league_injuries': {
            'url': 'https://www.premierleague.com/en/latest-player-injuries',
            'reliability': 1.0,  # Official source - highest reliability
            'parser': 'parse_premier_league_injuries',
            'enabled': True
        },
        'premier_injuries_newsroom': {
            'url': 'https://premierinjuries.com/newsroom/epl',
            'reliability': 0.95,  # Very accurate
            'parser': 'parse_premier_injuries_newsroom',
            'enabled': False  # Currently returns 403, disabled
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

    def parse_premier_injuries_newsroom(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse premierinjuries.com newsroom page.

        The newsroom has an "EPL TEAM INJURIES" section with links to team-specific
        injury pages. We'll parse the main listings and team-specific content.

        Args:
            html: HTML content

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Look for articles/headlines about injuries
            # The newsroom typically has article cards or list items

            # Try multiple selectors for robustness
            articles = (
                soup.find_all('article') +
                soup.find_all('div', class_=re.compile('post|article|news|injury|item')) +
                soup.find_all('li', class_=re.compile('post|article|news'))
            )

            injury_keywords = [
                'injury', 'injured', 'out', 'sidelined', 'ruled out',
                'doubtful', 'fitness', 'concern', 'suspended',
                'returns', 'comeback', 'recovery'
            ]

            for article in articles[:30]:  # Limit to recent items
                try:
                    # Get headline/title
                    title_elem = (
                        article.find('h1') or
                        article.find('h2') or
                        article.find('h3') or
                        article.find('a', class_=re.compile('title|headline'))
                    )

                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    title_lower = title.lower()

                    # Check if relevant
                    if not any(keyword in title_lower for keyword in injury_keywords):
                        continue

                    # Extract player names from title
                    # Pattern: Capitalized words (likely player names)
                    words = title.split()
                    potential_names = []

                    for i, word in enumerate(words):
                        if word and word[0].isupper() and word not in ['Team', 'The', 'A', 'An', 'In', 'On', 'For', 'To']:
                            # Check if next word is also capitalized (full name)
                            if i + 1 < len(words) and words[i+1] and words[i+1][0].isupper():
                                potential_names.append(f"{word} {words[i+1]}")

                    # Get article text for more context
                    text_elem = article.find('p') or article.find('div', class_=re.compile('content|summary|excerpt'))
                    details = text_elem.get_text(strip=True) if text_elem else title

                    # Get link
                    link_elem = article.find('a')
                    link = link_elem.get('href', '') if link_elem else ''
                    if link and not link.startswith('http'):
                        link = f"https://premierinjuries.com{link}"

                    # Create intelligence item for each player
                    for player_name in potential_names:
                        # Filter out team names
                        if player_name in ['Manchester United', 'Manchester City', 'Liverpool', 'Chelsea', 'Arsenal']:
                            continue

                        intelligence.append({
                            'type': 'INJURY',
                            'player_name': player_name,
                            'details': details[:200],  # Limit details length
                            'link': link,
                            'raw_text': title,
                            'timestamp': datetime.now()
                        })

                except Exception as e:
                    logger.debug(f"WebsiteMonitor: Error parsing article: {e}")
                    continue

        except Exception as e:
            logger.error(f"WebsiteMonitor: Error parsing Premier Injuries newsroom: {e}")

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

    def parse_premier_league_injuries(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse official Premier League injuries page.

        The official PL page has structured injury data for all teams.
        This is the most reliable source as it's direct from the league.

        Args:
            html: HTML content

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Look for injury table or list items
            # The PL site typically has a structured layout
            # Try various selectors to find injury data

            # Method 1: Look for player injury cards/items
            injury_items = (
                soup.find_all('div', class_=re.compile('injury|player|item')) +
                soup.find_all('li', class_=re.compile('injury|player|item')) +
                soup.find_all('tr', class_=re.compile('injury|player'))
            )

            # Method 2: Look for tables with injury data
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        # Typical structure: Player Name | Team | Injury | Return Date
                        player_text = cells[0].get_text(strip=True)
                        injury_text = ' '.join(cell.get_text(strip=True) for cell in cells[1:])

                        # Extract player name (usually in format "First Last")
                        if player_text and not player_text.lower() in ['player', 'name']:
                            intelligence.append({
                                'type': 'INJURY',
                                'player_name': player_text,
                                'details': f"{player_text}: {injury_text}",
                                'raw_text': injury_text,
                                'timestamp': datetime.now()
                            })

            # Method 3: Parse injury cards (if page uses card layout)
            for item in injury_items:
                try:
                    # Find player name
                    name_elem = (
                        item.find('h2') or
                        item.find('h3') or
                        item.find('span', class_=re.compile('name|player')) or
                        item.find('a', class_=re.compile('name|player'))
                    )

                    if not name_elem:
                        continue

                    player_name = name_elem.get_text(strip=True)

                    # Find injury details
                    detail_elem = (
                        item.find('p') or
                        item.find('span', class_=re.compile('injury|status|detail')) or
                        item.find('div', class_=re.compile('injury|status|detail'))
                    )

                    details = detail_elem.get_text(strip=True) if detail_elem else ''

                    # Find return date if available
                    date_elem = item.find(['span', 'div'], class_=re.compile('date|return'))
                    return_date = date_elem.get_text(strip=True) if date_elem else ''

                    full_details = f"{player_name}: {details}"
                    if return_date:
                        full_details += f" (Return: {return_date})"

                    intelligence.append({
                        'type': 'INJURY',
                        'player_name': player_name,
                        'details': full_details,
                        'raw_text': details,
                        'return_date': return_date if return_date else None,
                        'timestamp': datetime.now()
                    })

                except Exception as e:
                    logger.debug(f"WebsiteMonitor: Error parsing injury item: {e}")
                    continue

            # Deduplicate by player name
            seen_players = set()
            unique_intelligence = []
            for item in intelligence:
                if item['player_name'] not in seen_players:
                    seen_players.add(item['player_name'])
                    unique_intelligence.append(item)

            logger.info(f"WebsiteMonitor: Parsed {len(unique_intelligence)} unique injuries from Premier League")

            return unique_intelligence

        except Exception as e:
            logger.error(f"WebsiteMonitor: Error parsing Premier League injuries: {e}")
            return []

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
