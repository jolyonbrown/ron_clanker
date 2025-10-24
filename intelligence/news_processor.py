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
                max_tokens=2000,  # Increased for longer responses
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

    def process_youtube_transcript(
        self,
        video_title: str,
        transcript: str,
        creator: str,
        video_url: str = None
    ) -> Dict[str, Any]:
        """
        Process YouTube video transcript to extract FPL recommendations.

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

        prompt = f"""You are analyzing an FPL YouTube video to extract expert recommendations and player intelligence.

VIDEO:
Title: {video_title}
Creator: {creator}
Transcript:
{transcript[:3000]}  # Limit to first 3000 chars for shorts

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
