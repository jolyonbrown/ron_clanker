"""
YouTube Transcript Monitor for Intelligence Gathering

Monitors FPL YouTube channels for injury/team news by:
1. Checking YouTube RSS feeds for new videos
2. Extracting transcripts using youtube-transcript-api
3. Parsing transcripts for injury mentions

YouTube RSS feeds are free, no auth required!
RSS URL format: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID

Used by Scout agent to gather early intelligence from FPL content creators.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re
import aiohttp
import feedparser
from youtube_transcript_api import YouTubeTranscriptApi
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class YouTubeMonitor:
    """
    Monitor FPL YouTube channels for injury and team news.

    Uses YouTube RSS feeds (no auth!) + youtube-transcript-api for transcripts.
    """

    # Trusted FPL YouTube channels
    # NOTE: Channel IDs for RSS feeds are difficult to maintain.
    # Instead, configure specific video URLs to monitor in database.
    # This is a more practical approach for Phase 2.
    #
    # Recommended FPL YouTube channels to monitor:
    # - FPL Harry (@FPLHarry) - highly recommended
    #   * YouTube Shorts are particularly valuable (quick injury news snippets)
    #   * Example: GW8 selection short mentioning Enzo doubt at Chelsea
    # - FPL Focal (@FPLFocal)
    # - Let's Talk FPL (@LetsTalkFPL)
    # - FPL Mate (@FPLMate)
    # - Andy LTFPL (@AndyLTFPL)
    #
    # YouTube Shorts Strategy:
    # - Shorts often contain condensed injury/team news
    # - Shorter transcripts = faster processing
    # - Content creators post quick updates as Shorts
    # - Same API works for both regular videos and Shorts
    #
    # To add channels: need channel ID (not handle) for RSS feed:
    # Format: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
    CHANNELS = {
        # Disabled until correct channel IDs are verified
        # 'fpl_harry': {
        #     'handle': '@FPLHarry',
        #     'channel_id': 'UCXXXXXXXXXXXXXXXX',  # Need to find from channel page
        #     'reliability': 0.85,
        #     'enabled': False
        # },
    }

    # Alternative: Monitor specific video URLs (configurable)
    # This can be populated from database or config file
    MONITORED_VIDEOS = [
        # Example: 'https://www.youtube.com/watch?v=VIDEO_ID'
        # Can be updated via database configuration
    ]

    # Keywords indicating injury/team news in video titles
    VIDEO_KEYWORDS = [
        'injury', 'injured', 'news', 'press conference', 'team news',
        'update', 'suspended', 'doubt', 'fitness', 'ruled out',
        'returns', 'back', 'unavailable', 'miss', 'out for'
    ]

    # Keywords in transcripts
    TRANSCRIPT_KEYWORDS = [
        'injury', 'injured', 'out for', 'sidelined', 'ruled out',
        'doubtful', 'fitness', 'concern', 'suspended', 'ban',
        'rotation', 'rested', 'press conference', 'manager said',
        'returns', 'comeback', 'unavailable', 'miss', 'weeks',
        'knee', 'hamstring', 'ankle', 'muscle', 'strain'
    ]

    def __init__(self, database=None):
        """Initialize YouTube monitor."""
        self._last_check: Dict[str, datetime] = {}

        # Database for caching transcripts
        if database:
            self.db = database
        else:
            from data.database import Database
            self.db = Database()

        logger.info("YouTubeMonitor initialized")

    async def check_all(self, max_age_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Check all configured YouTube channels for new videos.

        Args:
            max_age_hours: Only check videos from last N hours

        Returns:
            List of raw intelligence items from YouTube transcripts
        """
        intelligence = []

        # Check configured channels (via RSS feeds)
        for channel_name, config in self.CHANNELS.items():
            if not config.get('enabled'):
                continue

            try:
                logger.info(f"YouTubeMonitor: Checking {channel_name}...")

                # Check channel RSS feed for new videos
                channel_intel = await self._check_channel(
                    config['channel_id'],
                    config['reliability'],
                    channel_name,
                    max_age_hours
                )

                intelligence.extend(channel_intel)
                logger.info(f"YouTubeMonitor: Found {len(channel_intel)} items from {channel_name}")

            except Exception as e:
                logger.error(f"YouTubeMonitor: Error checking {channel_name}: {e}")

        # Check specific monitored video URLs
        for video_url in self.MONITORED_VIDEOS:
            try:
                logger.info(f"YouTubeMonitor: Checking video {video_url}...")

                video_intel = await self._check_video_url(video_url, 0.85)
                intelligence.extend(video_intel)

            except Exception as e:
                logger.error(f"YouTubeMonitor: Error checking video {video_url}: {e}")

        return intelligence

    async def check_video_urls(self, video_urls: List[str], reliability: float = 0.85) -> List[Dict[str, Any]]:
        """
        Check specific YouTube video URLs for intelligence.

        This is a more practical approach than channel monitoring.

        Args:
            video_urls: List of YouTube video URLs to check
            reliability: Reliability score for these videos

        Returns:
            List of intelligence items
        """
        intelligence = []

        for video_url in video_urls:
            try:
                video_intel = await self._check_video_url(video_url, reliability)
                intelligence.extend(video_intel)
            except Exception as e:
                logger.error(f"YouTubeMonitor: Error checking video {video_url}: {e}")

        return intelligence

    async def _check_video_url(
        self,
        video_url: str,
        reliability: float = 0.85
    ) -> List[Dict[str, Any]]:
        """
        Check a specific YouTube video URL for intelligence.

        Args:
            video_url: YouTube video URL
            reliability: Source reliability score

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            # Extract video ID
            video_id = self._extract_video_id(video_url)
            if not video_id:
                logger.warning(f"YouTubeMonitor: Could not extract video ID from {video_url}")
                return []

            # Fetch transcript (uses cache automatically)
            transcript_text = await self._fetch_transcript(video_id)
            if not transcript_text:
                logger.debug(f"YouTubeMonitor: No transcript for {video_id}")
                return []

            # Extract intelligence from transcript
            mentions = self._extract_intelligence(transcript_text, "")

            # Store intelligence in database for team analysis
            for mention in mentions:
                # Try to match player ID
                player_id = None
                try:
                    player_match = self.db.execute_query("""
                        SELECT id FROM players
                        WHERE LOWER(web_name) = LOWER(?)
                           OR LOWER(first_name || ' ' || second_name) = LOWER(?)
                        LIMIT 1
                    """, (mention['player_name'], mention['player_name']))

                    if player_match:
                        player_id = player_match[0]['id']
                except:
                    pass

                # Store in database
                self.db.execute_update("""
                    INSERT INTO youtube_intelligence
                    (video_id, player_id, player_name, intelligence_type, details, context, confidence, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (video_id, player_id, mention['player_name'], mention['type'],
                      mention['details'], mention['details'], reliability))

                # Build intelligence item for return
                intelligence.append({
                    'type': mention['type'],
                    'player_name': mention['player_name'],
                    'details': mention['details'],
                    'video_url': video_url,
                    'video_id': video_id,
                    'source': 'YouTube',
                    'base_reliability': reliability,
                    'timestamp': datetime.now()
                })

            # Mark transcript as processed
            if intelligence:
                self.db.execute_update("""
                    UPDATE youtube_transcripts
                    SET intelligence_extracted = 1
                    WHERE video_id = ?
                """, (video_id,))

        except Exception as e:
            logger.error(f"YouTubeMonitor: Error checking video URL {video_url}: {e}")

        return intelligence

    async def _check_channel(
        self,
        channel_id: str,
        reliability: float,
        channel_name: str,
        max_age_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Check a YouTube channel's RSS feed for new videos with injury news.

        Args:
            channel_id: YouTube channel ID
            reliability: Source reliability score (0-1)
            channel_name: Name of channel
            max_age_hours: Only check videos from last N hours

        Returns:
            List of intelligence items
        """
        intelligence = []

        try:
            # YouTube RSS feed URL
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

            # Fetch RSS feed
            async with aiohttp.ClientSession() as session:
                async with session.get(rss_url, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"YouTubeMonitor: HTTP {response.status} for {channel_name}")
                        return []

                    feed_content = await response.text()

            # Parse RSS feed
            feed = feedparser.parse(feed_content)

            # Process recent videos
            for entry in feed.entries[:10]:  # Check 10 most recent
                try:
                    title = entry.get('title', '')
                    published = entry.get('published')
                    video_url = entry.get('link', '')

                    # Extract video ID from URL
                    video_id = self._extract_video_id(video_url)
                    if not video_id:
                        continue

                    # Check if video title suggests injury/team news
                    title_lower = title.lower()
                    if not any(keyword in title_lower for keyword in self.VIDEO_KEYWORDS):
                        # Skip videos that don't seem relevant
                        continue

                    # Check video age
                    if published:
                        try:
                            pub_date = date_parser.parse(published)
                            age_hours = (datetime.now(pub_date.tzinfo) - pub_date).total_seconds() / 3600

                            if age_hours > max_age_hours:
                                continue
                        except:
                            pass  # If can't parse date, check it anyway

                    # Fetch transcript
                    transcript_text = await self._fetch_transcript(video_id)
                    if not transcript_text:
                        logger.debug(f"YouTubeMonitor: No transcript for {video_id}")
                        continue

                    # Search transcript for injury mentions
                    mentions = self._extract_intelligence(transcript_text, title)

                    # Build intelligence items
                    for mention in mentions:
                        intelligence.append({
                            'type': mention['type'],
                            'player_name': mention['player_name'],
                            'details': mention['details'],
                            'video_title': title,
                            'video_url': video_url,
                            'video_id': video_id,
                            'published': published,
                            'source': f"YouTube: {channel_name}",
                            'base_reliability': reliability,
                            'timestamp': datetime.now()
                        })

                except Exception as e:
                    logger.debug(f"YouTubeMonitor: Error processing video: {e}")
                    continue

        except Exception as e:
            logger.error(f"YouTubeMonitor: Error fetching channel {channel_name}: {e}")

        return intelligence

    def _extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract YouTube video ID from URL.

        Args:
            url: YouTube video URL

        Returns:
            Video ID or None
        """
        # Match patterns like:
        # https://www.youtube.com/watch?v=VIDEO_ID
        # https://youtu.be/VIDEO_ID

        patterns = [
            r'v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    async def _fetch_transcript(self, video_id: str) -> Optional[str]:
        """
        Fetch transcript for a YouTube video with caching.

        Checks cache first (7-day TTL), fetches if needed.

        Args:
            video_id: YouTube video ID

        Returns:
            Transcript text or None if unavailable
        """
        try:
            # Check cache first
            cached = self.db.execute_query("""
                SELECT transcript_text, expires_at
                FROM youtube_transcripts
                WHERE video_id = ? AND expires_at > CURRENT_TIMESTAMP
            """, (video_id,))

            if cached:
                logger.debug(f"YouTubeMonitor: Using cached transcript for {video_id}")
                return cached[0]['transcript_text']

            # Cache miss - fetch from YouTube
            logger.debug(f"YouTubeMonitor: Fetching transcript for {video_id} (cache miss)")
            transcript = YouTubeTranscriptApi.get_transcript(video_id)

            # Combine all text segments
            text = ' '.join([entry['text'] for entry in transcript])

            # Cache transcript with 7-day TTL
            word_count = len(text.split())
            self.db.execute_update("""
                INSERT OR REPLACE INTO youtube_transcripts
                (video_id, transcript_text, word_count, fetched_at, expires_at, intelligence_extracted)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, datetime('now', '+7 days'), 0)
            """, (video_id, text, word_count))

            logger.info(f"YouTubeMonitor: Cached transcript for {video_id} ({word_count} words)")

            return text

        except Exception as e:
            logger.debug(f"YouTubeMonitor: Could not fetch transcript for {video_id}: {e}")
            return None

    def _extract_intelligence(self, transcript: str, video_title: str) -> List[Dict[str, Any]]:
        """
        Extract intelligence from transcript text.

        Args:
            transcript: Full transcript text
            video_title: Video title for context

        Returns:
            List of intelligence mentions
        """
        intelligence = []

        # Convert to lowercase for searching
        text_lower = transcript.lower()

        # Find sentences with injury keywords
        # Split into sentences (rough approximation)
        sentences = re.split(r'[.!?]+', transcript)

        for sentence in sentences:
            sentence_lower = sentence.lower()

            # Check if sentence contains injury keywords
            if not any(keyword in sentence_lower for keyword in self.TRANSCRIPT_KEYWORDS):
                continue

            # Extract player names from sentence
            player_names = self._extract_player_names_from_text(sentence)

            if not player_names:
                continue

            # Classify intelligence type
            intel_type = self._classify_transcript_type(sentence_lower)

            # Build intelligence items
            for player_name in player_names:
                intelligence.append({
                    'type': intel_type,
                    'player_name': player_name,
                    'details': sentence.strip()
                })

        return intelligence

    def _extract_player_names_from_text(self, text: str) -> List[str]:
        """
        Extract player names from text using pattern matching.

        Args:
            text: Text to extract from

        Returns:
            List of potential player names
        """
        # Pattern: Capitalized names (first and last)
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
        matches = re.findall(pattern, text)

        # Filter out common false positives
        exclude = [
            'Premier League', 'Fantasy Premier', 'Fantasy Football',
            'Manchester United', 'Manchester City', 'Liverpool FC',
            'The Guardian', 'Sky Sports', 'BBC Sport',
            'Let Talk', 'Press Conference', 'Team News',
        ]

        names = []
        for name in matches:
            if name in exclude:
                continue
            if len(name.split()) < 2:
                continue
            names.append(name)

        # Deduplicate
        return list(dict.fromkeys(names))

    def _classify_transcript_type(self, text: str) -> str:
        """
        Classify intelligence type from transcript text.

        Args:
            text: Transcript text (lowercase)

        Returns:
            Intelligence type
        """
        if any(word in text for word in ['suspended', 'banned', 'red card']):
            return 'SUSPENSION'
        elif any(word in text for word in ['rotation', 'rested', 'rotated', 'bench']):
            return 'ROTATION'
        elif any(word in text for word in ['press conference', 'manager said', 'boss said']):
            return 'PRESS_CONFERENCE'
        elif any(word in text for word in ['returns', 'comeback', 'back in', 'fit again']):
            return 'INJURY'  # Recovery news
        else:
            return 'INJURY'


async def test_youtube_monitor():
    """Test the YouTube monitor."""
    print("Testing YouTubeMonitor...\n")
    print("=" * 80)
    print("\nYouTube Intelligence Monitor - Transcript Extraction")
    print("\nApproach:")
    print("  - Monitor specific FPL video URLs (configurable)")
    print("  - Extract transcripts using youtube-transcript-api")
    print("  - Parse for injury/team news mentions")
    print("  - No API key required!")
    print("\n" + "=" * 80)

    monitor = YouTubeMonitor()

    # Test with example video URLs (these would be configured in database)
    # For testing, we can add specific URLs to MONITORED_VIDEOS
    print("\nNote: To test with real videos, add URLs to MONITORED_VIDEOS list")
    print("Example: monitor.MONITORED_VIDEOS.append('https://www.youtube.com/watch?v=VIDEO_ID')")

    # Check all configured sources
    intelligence = await monitor.check_all(max_age_hours=72)

    if intelligence:
        print(f"\nFound {len(intelligence)} intelligence items from YouTube:\n")
        print("=" * 80)

        for item in intelligence[:20]:  # Show first 20
            print(f"\n[{item['type']}] {item['player_name']}")
            print(f"  Source: {item['source']} ({item['base_reliability']:.0%} reliable)")
            if item.get('video_title'):
                print(f"  Video: {item['video_title']}")
            print(f"  Details: {item['details'][:100]}...")
            if item.get('video_url'):
                print(f"  URL: {item['video_url']}")
            print("-" * 80)

        print(f"\nTotal: {len(intelligence)} intelligence items from YouTube")
    else:
        print("\n✓ YouTube monitor initialized successfully")
        print("✓ Transcript extraction capability ready")
        print("\nTo use:")
        print("  1. Add video URLs to monitor.MONITORED_VIDEOS")
        print("  2. Or call monitor.check_video_urls([list_of_urls])")
        print("  3. Or configure URLs in database for automatic monitoring")
        print("\nIntegration with Scout: Videos can be flagged for monitoring when")
        print("referenced in other intelligence sources (RSS, websites, etc.)")

    print("\n" + "=" * 80)
    print("✅ YouTubeMonitor test complete!")
    print("=" * 80)


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_youtube_monitor())
