#!/usr/bin/env python3
"""
PremierLeague.com News Scraper

Scrapes latest news articles from PremierLeague.com for team news,
injuries, and tactical insights.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
import aiohttp
from bs4 import BeautifulSoup
import asyncio

logger = logging.getLogger(__name__)


class PremierLeagueNewsScraper:
    """
    Scrape news from PremierLeague.com.

    Focuses on:
    - Team news
    - Injury updates
    - Press conference reports
    """

    BASE_URL = "https://www.premierleague.com"  # Note: will auto-redirect from non-www
    NEWS_URL = f"{BASE_URL}/news"

    # Gameweek-specific blog URL format
    # Format: https://premierleague.com/en/matchweek/YYYY_GW/blog
    # Example: https://premierleague.com/en/matchweek/2025_9/blog
    MATCHWEEK_BLOG_URL = f"{BASE_URL}/en/matchweek/{{year}}_{{gw}}/blog"

    # News categories to monitor
    CATEGORIES = [
        "",  # All news
        "?tagNames=Team%20News",
        "?tagNames=Injuries"
    ]

    def __init__(self):
        """Initialize scraper."""
        self.session = None
        logger.info("PremierLeagueNewsScraper initialized")

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def fetch_gameweek_blog(
        self,
        gameweek: int,
        year: int = 2025
    ) -> Dict[str, Any]:
        """
        Fetch gameweek-specific blog content.

        Args:
            gameweek: Gameweek number (e.g., 9)
            year: Season year (default: 2025)

        Returns:
            Dict with blog content
        """
        if not self.session:
            logger.error("PremierLeagueScraper: Session not initialized. Use async with.")
            return {}

        url = self.MATCHWEEK_BLOG_URL.format(year=year, gw=gameweek)
        logger.info(f"PremierLeagueScraper: Fetching gameweek {gameweek} blog from {url}")

        try:
            async with self.session.get(url, timeout=15, allow_redirects=True) as response:
                if response.status != 200:
                    logger.error(f"PremierLeagueScraper: HTTP {response.status} from {url}")
                    return {}

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Extract main content - try multiple selectors
                blog_content = None

                # Try common content containers
                selectors = [
                    'div.article-body',
                    'div.blog-content',
                    'article',
                    'div[class*="content"]',
                    'main'
                ]

                for selector in selectors:
                    blog_content = soup.select_one(selector)
                    if blog_content:
                        logger.info(f"PremierLeagueScraper: Found content with selector: {selector}")
                        break

                if not blog_content:
                    # Fallback: get all text from body
                    logger.warning("PremierLeagueScraper: Using fallback - extracting all body text")
                    blog_content = soup.find('body')

                if blog_content:
                    # Extract all paragraphs
                    paragraphs = blog_content.find_all(['p', 'h2', 'h3', 'h4'])
                    content_text = '\n\n'.join([elem.get_text(strip=True) for elem in paragraphs if elem.get_text(strip=True)])

                    # Get title
                    title_tag = soup.find('h1') or soup.find('title')
                    title = title_tag.get_text(strip=True) if title_tag else f"Gameweek {gameweek} Blog"

                    logger.info(f"PremierLeagueScraper: Extracted {len(content_text)} characters of content")

                    return {
                        'title': title,
                        'url': url,
                        'content': content_text,
                        'gameweek': gameweek,
                        'source': 'PremierLeague.com Matchweek Blog'
                    }
                else:
                    logger.error("PremierLeagueScraper: Could not find blog content")
                    return {}

        except Exception as e:
            logger.error(f"PremierLeagueScraper: Error fetching gameweek blog: {e}")
            return {}

    async def fetch_recent_news(
        self,
        max_age_hours: int = 24,
        max_articles: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent news articles from PremierLeague.com.

        Args:
            max_age_hours: Only fetch articles from last N hours
            max_articles: Maximum number of articles to fetch

        Returns:
            List of article dicts with {title, url, summary, published_at, content}
        """
        if not self.session:
            logger.error("PremierLeagueScraper: Session not initialized. Use async with.")
            return []

        articles = []
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        try:
            # Fetch news page
            async with self.session.get(self.NEWS_URL, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"PremierLeagueScraper: HTTP {response.status} from {self.NEWS_URL}")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Find news articles (selectors may need adjustment)
                # PremierLeague.com uses dynamic loading, so we may get limited results
                article_cards = soup.find_all('article', class_='media-thumbnail', limit=max_articles)

                logger.info(f"PremierLeagueScraper: Found {len(article_cards)} article cards")

                for card in article_cards:
                    try:
                        # Extract article link
                        link_tag = card.find('a', href=True)
                        if not link_tag:
                            continue

                        url = self.BASE_URL + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']

                        # Extract title
                        title_tag = card.find('h3') or card.find('h4')
                        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

                        # Extract summary
                        summary_tag = card.find('p')
                        summary = summary_tag.get_text(strip=True) if summary_tag else ""

                        # Try to get publish date (may not be visible on listing page)
                        # We'll fetch full article if needed
                        published_at = datetime.now()  # Default to now

                        # Check if article is recent enough (we don't have exact time from listing)
                        # For now, fetch all from the listing page
                        if len(articles) >= max_articles:
                            break

                        articles.append({
                            'title': title,
                            'url': url,
                            'summary': summary,
                            'published_at': published_at,
                            'content': None,  # Will fetch if needed
                            'source': 'PremierLeague.com'
                        })

                    except Exception as e:
                        logger.warning(f"PremierLeagueScraper: Error parsing article card: {e}")
                        continue

                logger.info(f"PremierLeagueScraper: Extracted {len(articles)} articles")

        except asyncio.TimeoutError:
            logger.error("PremierLeagueScraper: Timeout fetching news page")
        except Exception as e:
            logger.error(f"PremierLeagueScraper: Error fetching news: {e}")

        return articles

    async def fetch_article_content(self, url: str) -> str:
        """
        Fetch full article content from URL.

        Args:
            url: Article URL

        Returns:
            Article body text
        """
        if not self.session:
            logger.error("PremierLeagueScraper: Session not initialized")
            return ""

        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"PremierLeagueScraper: HTTP {response.status} from {url}")
                    return ""

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Find article body (selector may need adjustment)
                article_body = soup.find('div', class_='article-body') or soup.find('article')

                if article_body:
                    # Extract text from paragraphs
                    paragraphs = article_body.find_all('p')
                    content = '\n\n'.join([p.get_text(strip=True) for p in paragraphs])
                    return content
                else:
                    logger.warning(f"PremierLeagueScraper: Could not find article body at {url}")
                    return ""

        except Exception as e:
            logger.error(f"PremierLeagueScraper: Error fetching article content from {url}: {e}")
            return ""


async def fetch_premierleague_news(max_age_hours: int = 24, max_articles: int = 10) -> List[Dict[str, Any]]:
    """
    Convenience function to fetch PremierLeague.com news.

    Args:
        max_age_hours: Only fetch articles from last N hours
        max_articles: Maximum articles to fetch

    Returns:
        List of article dicts
    """
    async with PremierLeagueNewsScraper() as scraper:
        articles = await scraper.fetch_recent_news(
            max_age_hours=max_age_hours,
            max_articles=max_articles
        )

        # Fetch full content for first few articles
        for article in articles[:5]:  # Only fetch content for top 5 to be polite
            if not article['content']:
                article['content'] = await scraper.fetch_article_content(article['url'])
                await asyncio.sleep(1)  # Polite delay

        return articles
