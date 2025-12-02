#!/usr/bin/env python3
"""
News Intelligence Processor

Uses Claude Haiku to intelligently process news/opinion from multiple sources:
- PremierLeague.com news
- YouTube FPL creator shorts
- RSS feeds
- Expert articles

Instead of dumb keyword matching, Claude extracts:
- Player availability/injury status
- Form insights
- Rotation risks
- Expert recommendations (captain picks, transfers)
- Sentiment (positive/negative for each player)

This provides "football common sense" to complement ML predictions.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import anthropic
import json

logger = logging.getLogger(__name__)


class NewsIntelligenceProcessor:
    """
    Process news and expert opinion using Claude Haiku.

    Converts unstructured text into structured player insights.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize news processor.

        Args:
            api_key: Anthropic API key (or reads from ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')

        if not self.api_key:
            logger.warning("No Anthropic API key configured. News processing disabled.")
            self.enabled = False
            self.client = None
        else:
            self.enabled = True
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info("News Intelligence Processor ENABLED (Claude Haiku 4.5)")

    def process_news_article(
        self,
        title: str,
        content: str,
        source: str,
        url: str = None
    ) -> Dict[str, Any]:
        """
        Process a news article to extract player intelligence.

        Args:
            title: Article title
            content: Article body text
            source: Source name (e.g., "PremierLeague.com", "BBC Sport")
            url: Optional source URL

        Returns:
            Dict with extracted intelligence:
            {
                'players': [
                    {
                        'name': 'Erling Haaland',
                        'status': 'AVAILABLE',  # AVAILABLE, DOUBT, INJURED, SUSPENDED
                        'confidence': 0.9,
                        'details': 'Manager confirmed he will start',
                        'sentiment': 'POSITIVE'  # POSITIVE, NEUTRAL, NEGATIVE
                    },
                    ...
                ],
                'general_insights': ['City expected to rotate heavily', ...],
                'source': source,
                'processed_at': timestamp
            }
        """
        if not self.enabled:
            logger.error("News processing disabled - no API key")
            return {'players': [], 'general_insights': []}

        # If content is too large, chunk it and process in parts
        MAX_CONTENT_SIZE = 15000  # chars - conservative limit to avoid token issues
        if len(content) > MAX_CONTENT_SIZE:
            logger.info(f"Content too large ({len(content)} chars), chunking into parts")
            return self._process_large_content(title, content, source, url)

        # Build prompt for Claude
        prompt = f"""You are analyzing FPL news to extract actionable player intelligence.

NEWS ARTICLE:
Title: {title}
Source: {source}
Content:
{content}

TASK:
Extract FPL-relevant intelligence from this article. For each player mentioned, determine:

1. Player Name (use full name if possible, e.g., "Erling Haaland" not just "Haaland")
2. Status: AVAILABLE (fit and likely to play), DOUBT (injury doubt/rotation risk), INJURED (confirmed out), SUSPENDED, or NEUTRAL (just mentioned, no status update)
3. Confidence: 0.0-1.0 (how certain is this information?)
   - 1.0 = Manager confirmed in press conference
   - 0.8 = Reliable journalist report
   - 0.6 = Speculation from expert
   - 0.4 = Rumor
4. Details: Brief summary of the intelligence (one sentence)
5. Sentiment: POSITIVE (good for FPL), NEUTRAL, or NEGATIVE (bad for FPL)

Also extract any general insights about teams, tactics, or fixtures.

RESPOND IN JSON FORMAT:
{{
  "players": [
    {{
      "name": "Player Full Name",
      "status": "AVAILABLE|DOUBT|INJURED|SUSPENDED|NEUTRAL",
      "confidence": 0.0-1.0,
      "details": "One sentence summary",
      "sentiment": "POSITIVE|NEUTRAL|NEGATIVE"
    }}
  ],
  "general_insights": [
    "Team X expected to rotate heavily for this fixture",
    "Easy fixture for Team Y attackers"
  ]
}}

Only include players with meaningful FPL intelligence. Ignore passing mentions.
If no relevant intelligence, return empty arrays."""

        try:
            # Use Claude Haiku 4.5 (fast & cheap)
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4096,  # Increased to handle large press conference files
                temperature=0.3,  # Lower temp for factual extraction
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse JSON response
            response_text = message.content[0].text.strip()

            # Extract JSON from response (may be wrapped in markdown)
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            intelligence = json.loads(response_text)

            # Add metadata
            intelligence['source'] = source
            intelligence['source_url'] = url
            intelligence['processed_at'] = datetime.now().isoformat()
            intelligence['article_title'] = title

            logger.info(f"Extracted intelligence on {len(intelligence.get('players', []))} players from {source}")
            return intelligence

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude response: {e}")
            logger.error(f"Response text: {response_text[:500]}")

            # Try to salvage partial JSON by finding last complete object
            try:
                # Find last complete player object
                last_complete = response_text.rfind('}')
                if last_complete > 0:
                    # Try to close the JSON properly
                    truncated = response_text[:last_complete+1]
                    # Add closing brackets if needed
                    if truncated.count('{') > truncated.count('}'):
                        truncated += '}'
                    if truncated.count('[') > truncated.count(']'):
                        truncated += ']'
                    if not truncated.endswith('}'):
                        truncated += '}'

                    intelligence = json.loads(truncated)
                    intelligence['source'] = source
                    intelligence['source_url'] = url
                    intelligence['processed_at'] = datetime.now().isoformat()
                    intelligence['article_title'] = title
                    logger.warning("Recovered partial intelligence from truncated response")
                    return intelligence
            except:
                pass

            return {'players': [], 'general_insights': [], 'source': source}

        except Exception as e:
            logger.error(f"Failed to process news article: {e}")
            return {'players': [], 'general_insights': [], 'source': source}

    def _process_large_content(
        self,
        title: str,
        content: str,
        source: str,
        url: str = None,
        batch_size: int = 20
    ) -> Dict[str, Any]:
        """
        Process large content by chunking it into smaller pieces.

        For paragraph-based content (big five format), batches into groups of paragraphs.
        For other content, splits by character count to keep related info together.

        Args:
            batch_size: Number of paragraphs per batch (for big five format)
        """
        # Check if this looks like "big five" paragraph format
        # (multiple short paragraphs, 100-120 total)
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

        if len(paragraphs) > 50 and len(paragraphs) < 200:
            # Looks like "big five" format - batch by paragraphs
            logger.info(f"Detected big five format: {len(paragraphs)} paragraphs, batching {batch_size} at a time")
            chunks = []

            for i in range(0, len(paragraphs), batch_size):
                batch = paragraphs[i:i + batch_size]
                chunks.append('\n\n'.join(batch))

            logger.info(f"Split into {len(chunks)} batches of ~{batch_size} paragraphs")
        else:
            # Regular chunking by character count
            chunks = []
            current_chunk = ""

            for line in content.split('\n'):
                current_chunk += line + '\n'
                # Start new chunk when we hit 10000 chars
                if len(current_chunk) > 10000:
                    chunks.append(current_chunk)
                    current_chunk = ""

            if current_chunk:
                chunks.append(current_chunk)

            logger.info(f"Split content into {len(chunks)} chunks by character count")

        # Process each chunk
        all_players = []
        all_insights = []

        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Processing chunk {i}/{len(chunks)}")
            result = self.process_news_article(
                title=f"{title} (Part {i})",
                content=chunk,
                source=source,
                url=url
            )
            all_players.extend(result.get('players', []))
            all_insights.extend(result.get('general_insights', []))

        # Return combined results in standard format
        return {
            'players': all_players,
            'general_insights': all_insights,
            'source': source,
            'source_url': url,
            'processed_at': datetime.now().isoformat(),
            'article_title': title
        }

    def process_simple_press_conferences(
        self,
        content: str,
        gameweek: int,
        source: str = "Press Conferences"
    ) -> Dict[str, Any]:
        """
        Process simplified press conference format.

        Format example:
        Arsenal
        OUT
        Player Name - injury type
        ...
        DOUBT
        Player Name - status details
        ...

        This is a lightweight, pre-structured format that's easy to parse
        and doesn't require heavy LLM processing.

        Args:
            content: The pre-formatted press conference text
            gameweek: Current gameweek number
            source: Source identifier

        Returns:
            Dict with extracted intelligence (same format as process_news_article)
        """
        if not self.enabled:
            logger.error("News processing disabled - no API key")
            return {'players': [], 'general_insights': []}

        prompt = f"""You are analyzing STRUCTURED press conference injury/availability data for FPL Gameweek {gameweek}.

The data is ALREADY pre-processed and formatted by team with clear status sections (OUT, DOUBT, IN).

DATA:
{content}

TASK:
Convert this structured data into FPL intelligence. For each player:

1. Player Name (full name)
2. Status:
   - OUT/INJURED entries → INJURED
   - DOUBT entries → DOUBT
   - IN entries → AVAILABLE
   - SUSPENDED entries → SUSPENDED
3. Confidence: 0.9 (this is official press conference data)
4. Details: Combine the injury type/status info (one sentence)
5. Sentiment:
   - INJURED/OUT → NEGATIVE
   - DOUBT → NEGATIVE (risky for FPL)
   - IN/returning → POSITIVE

RESPOND IN JSON FORMAT:
{{
  "players": [
    {{
      "name": "Player Full Name",
      "status": "INJURED|DOUBT|AVAILABLE|SUSPENDED",
      "confidence": 0.9,
      "details": "Brief status summary",
      "sentiment": "POSITIVE|NEGATIVE"
    }}
  ],
  "general_insights": [
    "Any team-wide rotation or tactical insights"
  ]
}}

This is high-quality official data. Extract ALL players mentioned."""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4096,  # Large enough for all press conference players
                temperature=0.2,  # Very low temp for factual extraction
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse JSON response
            response_text = message.content[0].text.strip()

            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            intelligence = json.loads(response_text)

            # Add metadata
            intelligence['source'] = source
            intelligence['source_url'] = None
            intelligence['processed_at'] = datetime.now().isoformat()
            intelligence['article_title'] = f'GW{gameweek} Press Conference Summary'

            logger.info(f"Extracted intelligence on {len(intelligence.get('players', []))} players from press conferences")
            return intelligence

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error (likely truncation): {e}")

            # Try to salvage partial response
            try:
                # Find the last complete player object
                last_complete_brace = response_text.rfind('}')

                if last_complete_brace > 0:
                    # Truncate to last complete object
                    truncated = response_text[:last_complete_brace+1]

                    # Ensure proper closing of arrays/objects
                    open_braces = truncated.count('{')
                    close_braces = truncated.count('}')
                    open_brackets = truncated.count('[')
                    close_brackets = truncated.count(']')

                    # Close any unclosed structures
                    if open_brackets > close_brackets:
                        truncated += ']'
                    if open_braces > close_braces:
                        truncated += '}'

                    # Try parsing the recovered JSON
                    intelligence = json.loads(truncated)
                    intelligence['source'] = source
                    intelligence['source_url'] = None
                    intelligence['processed_at'] = datetime.now().isoformat()
                    intelligence['article_title'] = f'GW{gameweek} Press Conference Summary (Partial)'

                    logger.warning(f"Recovered {len(intelligence.get('players', []))} players from truncated response")
                    return intelligence
            except Exception as recovery_error:
                logger.error(f"Could not recover partial data: {recovery_error}")

            return {'players': [], 'general_insights': [], 'source': source}

        except Exception as e:
            logger.error(f"Failed to process press conferences: {e}")
            return {'players': [], 'general_insights': [], 'source': source}

    def process_youtube_transcript(
        self,
        video_title: str,
        transcript: str,
        creator: str,
        video_url: str = None
    ) -> Dict[str, Any]:
        """
        Process YouTube video transcript to extract FPL recommendations.

        Handles full transcripts by batching into chunks if needed.

        Args:
            video_title: Video title
            transcript: Full transcript text
            creator: Creator name (e.g., "FPL Harry")
            video_url: Optional YouTube URL

        Returns:
            Dict with extracted intelligence (same format as process_news_article)
        """
        if not self.enabled:
            logger.error("News processing disabled - no API key")
            return {'players': [], 'recommendations': {}}

        # Determine if we need to batch (>10k chars)
        if len(transcript) > 10000:
            logger.info(f"Large transcript ({len(transcript)} chars) - processing in batches")
            return self._process_youtube_transcript_batched(
                video_title, transcript, creator, video_url
            )

        # Small transcript - process in one go
        prompt = f"""You are analyzing an FPL YouTube video to extract expert recommendations and player intelligence.

VIDEO:
Title: {video_title}
Creator: {creator}
Transcript:
{transcript}

TASK:
Extract FPL-relevant intelligence from this transcript. Focus on:

1. Player mentions with status updates (injuries, rotation, form)
2. Captain recommendations
3. Transfer recommendations (who to bring in/out)
4. Team/formation advice

For each player mentioned, provide:
- Player Name
- Status: AVAILABLE, DOUBT, INJURED, SUSPENDED, or NEUTRAL
- Confidence: 0.0-1.0 (expert opinions are typically 0.6-0.7)
- Details: What the creator said
- Sentiment: POSITIVE (recommends), NEUTRAL, NEGATIVE (avoid)

RESPOND IN JSON FORMAT:
{{
  "players": [
    {{
      "name": "Player Full Name",
      "status": "AVAILABLE|DOUBT|INJURED|SUSPENDED|NEUTRAL",
      "confidence": 0.6,
      "details": "Creator's take on this player",
      "sentiment": "POSITIVE|NEUTRAL|NEGATIVE"
    }}
  ],
  "recommendations": {{
    "captain_picks": ["Player 1", "Player 2"],
    "transfers_in": ["Player A", "Player B"],
    "transfers_out": ["Player X", "Player Y"]
  }},
  "general_insights": [
    "Key tactical or fixture insights from the video"
  ]
}}

Only include actionable intelligence. If nothing relevant, return empty arrays."""

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1000,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse JSON response
            response_text = message.content[0].text.strip()

            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            intelligence = json.loads(response_text)

            # Add metadata
            intelligence['source'] = f'YouTube: {creator}'
            intelligence['source_url'] = video_url
            intelligence['processed_at'] = datetime.now().isoformat()
            intelligence['video_title'] = video_title

            logger.info(f"Extracted intelligence from {creator} video")
            return intelligence

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude response: {e}")
            return {'players': [], 'recommendations': {}, 'source': f'YouTube: {creator}'}

        except Exception as e:
            logger.error(f"Failed to process YouTube transcript: {e}")
            return {'players': [], 'recommendations': {}, 'source': f'YouTube: {creator}'}

    def _process_youtube_transcript_batched(
        self,
        video_title: str,
        transcript: str,
        creator: str,
        video_url: str = None
    ) -> Dict[str, Any]:
        """
        Process large YouTube transcript in batches (similar to news article batching).

        Splits transcript into ~8000 char chunks, processes each, then aggregates.
        """
        BATCH_SIZE = 8000  # ~2000 tokens, safe for Haiku with output buffer

        # Split into words for cleaner breaks
        words = transcript.split()
        batches = []
        current_batch = []
        current_length = 0

        for word in words:
            word_len = len(word) + 1  # +1 for space
            if current_length + word_len > BATCH_SIZE and current_batch:
                batches.append(' '.join(current_batch))
                current_batch = [word]
                current_length = word_len
            else:
                current_batch.append(word)
                current_length += word_len

        if current_batch:
            batches.append(' '.join(current_batch))

        logger.info(f"Processing {len(batches)} batches for video: {video_title}")

        # Process each batch
        all_players = []
        all_captain_picks = []
        all_transfers_in = []
        all_transfers_out = []
        all_insights = []

        for i, batch_text in enumerate(batches, 1):
            logger.info(f"Processing batch {i}/{len(batches)} ({len(batch_text)} chars)")

            prompt = f"""You are analyzing part {i} of {len(batches)} from an FPL YouTube video.

VIDEO: {video_title}
CREATOR: {creator}
TRANSCRIPT SECTION {i}/{len(batches)}:
{batch_text}

Extract FPL intelligence from this section:
- Player mentions (injuries, rotation, form, availability)
- Captain recommendations
- Transfer suggestions (in/out)
- Tactical insights

RESPOND IN JSON:
{{
  "players": [
    {{
      "name": "Full Player Name",
      "status": "AVAILABLE|DOUBT|INJURED|SUSPENDED|NEUTRAL",
      "confidence": 0.7,
      "details": "What the creator said",
      "sentiment": "POSITIVE|NEUTRAL|NEGATIVE"
    }}
  ],
  "recommendations": {{
    "captain_picks": ["Player 1"],
    "transfers_in": ["Player A"],
    "transfers_out": ["Player X"]
  }},
  "general_insights": ["Key insights"]
}}

Only include actionable intelligence."""

            try:
                message = self.client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=1500,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}]
                )

                response_text = message.content[0].text.strip()

                # Extract JSON
                if '```json' in response_text:
                    json_start = response_text.find('```json') + 7
                    json_end = response_text.find('```', json_start)
                    response_text = response_text[json_start:json_end].strip()
                elif '```' in response_text:
                    json_start = response_text.find('```') + 3
                    json_end = response_text.find('```', json_start)
                    response_text = response_text[json_start:json_end].strip()

                batch_intel = json.loads(response_text)

                # Aggregate results
                all_players.extend(batch_intel.get('players', []))
                recs = batch_intel.get('recommendations', {})
                all_captain_picks.extend(recs.get('captain_picks', []))
                all_transfers_in.extend(recs.get('transfers_in', []))
                all_transfers_out.extend(recs.get('transfers_out', []))
                all_insights.extend(batch_intel.get('general_insights', []))

            except Exception as e:
                logger.error(f"Failed to process batch {i}: {e}")
                continue

        # Deduplicate players (same player might be mentioned in multiple batches)
        unique_players = {}
        for player in all_players:
            name = player['name']
            if name not in unique_players:
                unique_players[name] = player
            else:
                # Keep the entry with higher confidence
                if player['confidence'] > unique_players[name]['confidence']:
                    unique_players[name] = player

        # Combine results
        intelligence = {
            'players': list(unique_players.values()),
            'recommendations': {
                'captain_picks': list(set(all_captain_picks)),
                'transfers_in': list(set(all_transfers_in)),
                'transfers_out': list(set(all_transfers_out))
            },
            'general_insights': all_insights,
            'source': f'YouTube: {creator}',
            'source_url': video_url,
            'processed_at': datetime.now().isoformat(),
            'video_title': video_title
        }

        logger.info(f"Batched processing complete: {len(intelligence['players'])} unique players")
        return intelligence

    def aggregate_intelligence(
        self,
        intelligence_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Aggregate multiple intelligence sources for each player.

        Combines news from different sources to build consensus view.

        Args:
            intelligence_items: List of intelligence dicts from process_news_article/process_youtube_transcript

        Returns:
            Dict mapping player names to aggregated intelligence:
            {
                'Erling Haaland': {
                    'status': 'AVAILABLE',
                    'confidence': 0.85,  # Average of sources
                    'sentiment': 'POSITIVE',
                    'sources': ['PremierLeague.com', 'FPL Harry'],
                    'details': ['Manager confirmed start', 'Harry recommends captain']
                }
            }
        """
        aggregated = {}

        for item in intelligence_items:
            for player_intel in item.get('players', []):
                name = player_intel['name']

                if name not in aggregated:
                    aggregated[name] = {
                        'status': player_intel['status'],
                        'confidence': player_intel['confidence'],
                        'sentiment': player_intel['sentiment'],
                        'sources': [item['source']],
                        'details': [player_intel['details']]
                    }
                else:
                    # Combine intelligence from multiple sources
                    existing = aggregated[name]

                    # Add source
                    existing['sources'].append(item['source'])
                    existing['details'].append(player_intel['details'])

                    # Update confidence (average)
                    existing['confidence'] = (
                        existing['confidence'] + player_intel['confidence']
                    ) / 2

                    # Status priority: INJURED > DOUBT > SUSPENDED > AVAILABLE > NEUTRAL
                    status_priority = {
                        'INJURED': 4,
                        'DOUBT': 3,
                        'SUSPENDED': 2,
                        'AVAILABLE': 1,
                        'NEUTRAL': 0
                    }

                    if status_priority.get(player_intel['status'], 0) > status_priority.get(existing['status'], 0):
                        existing['status'] = player_intel['status']

                    # Sentiment: if any NEGATIVE, mark as NEGATIVE
                    if player_intel['sentiment'] == 'NEGATIVE':
                        existing['sentiment'] = 'NEGATIVE'
                    elif player_intel['sentiment'] == 'POSITIVE' and existing['sentiment'] != 'NEGATIVE':
                        existing['sentiment'] = 'POSITIVE'

        logger.info(f"Aggregated intelligence on {len(aggregated)} players from {len(intelligence_items)} sources")
        return aggregated
