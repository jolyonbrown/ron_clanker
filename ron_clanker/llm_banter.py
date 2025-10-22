#!/usr/bin/env python3
"""
LLM-Powered Banter Generator

Uses Claude API to generate Ron's authentic, natural gameweek reviews.
No more stilted hardcoded responses!
"""

import os
import logging
from typing import Dict, Any, List
import anthropic

logger = logging.getLogger('ron_clanker.llm_banter')


class RonBanterGenerator:
    """
    Generates Ron's post-match banter using Claude API.

    Uses Claude Haiku for fast, cheap, authentic responses.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize banter generator.

        Args:
            api_key: Anthropic API key (or reads from ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')

        if not self.api_key:
            logger.warning("No Anthropic API key configured. LLM banter disabled.")
            self.enabled = False
            self.client = None
        else:
            self.enabled = True
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info("LLM banter generator ENABLED (Claude Haiku)")

    def generate_post_match_review(
        self,
        gameweek: int,
        ron_points: int,
        average_points: int,
        league_position: int,
        total_managers: int,
        gap_to_leader: int,
        leader_name: str,
        captain_name: str,
        captain_points: int,
        heroes: List[Dict[str, Any]],
        villains: List[Dict[str, Any]],
        team_summary: str,
        league_members: List[str] = None,
        rival_fails: List[Dict[str, Any]] = None,
        low_scorers: List[Dict[str, Any]] = None
    ) -> str:
        """
        Generate Ron's post-match WhatsApp-style review.

        Args:
            gameweek: GW number
            ron_points: Ron's points this week
            average_points: Average points
            league_position: Ron's league rank
            total_managers: Total in league
            gap_to_leader: Points behind leader
            leader_name: Name of league leader
            captain_name: Captain's name
            captain_points: Captain's points (doubled)
            heroes: List of {name, points, reason} for top performers
            villains: List of {name, points, reason} for poor performers
            team_summary: Brief summary of the team's performance
            league_members: List of league member first names for banter
            rival_fails: List of {manager_name, player_name, points} for poor rival picks

        Returns:
            Natural, authentic Ron banter
        """

        if not self.enabled:
            logger.error("Cannot generate banter - API key not configured")
            return self._fallback_review(gameweek, ron_points, average_points)

        # Build the prompt
        diff = ron_points - average_points

        heroes_text = "\n".join([
            f"- {h['name']}: {h['points']} points"
            for h in heroes[:3]
        ]) if heroes else "None really"

        villains_text = "\n".join([
            f"- {v['name']}: {v['points']} points"
            for v in villains[:3]
        ]) if villains else "None thankfully"

        # League members for banter
        league_names = league_members or ["Andy", "Anthony", "James", "Kieran", "Kyle", "Michael", "Peter"]
        league_context = f"League members: {', '.join(league_names)}"
        leader_context = f"Current leader: {leader_name} ({gap_to_leader} points ahead)"

        # Rival fails for banter
        rival_fails_text = ""
        if rival_fails:
            rival_fails_text = "RIVAL POOR PICKS (for gentle ribbing):\n"
            rival_fails_text += "\n".join([
                f"- {rf['manager_name']} picked {rf['player_name']} ({rf['points']}pts) - could mention this for banter"
                for rf in rival_fails[:3]
            ])

        # Low scorers for roasting
        low_scorers_text = ""
        if low_scorers:
            low_scorers_text = "\n\nLOW SCORERS THIS GW (pick one to roast if you fancy):\n"
            low_scorers_text += "\n".join([
                f"- {ls['manager_name']}: {ls['gw_points']}pts this week - proper shocker"
                for ls in low_scorers[:3]
            ])

        prompt = f"""You are Ron Clanker, a gruff 1970s/80s football manager who now runs an autonomous FPL team using AI and data science. You're writing a WhatsApp message to your manager mates in the Invitational League after Gameweek {gameweek}.

CHARACTER TRAITS:
- Old school but tech-savvy (uses data, ML, "the algorithms", "the models")
- Sweary and blunt - uses "fuck", "shit", "bollocks", "piss off" liberally when frustrated
- Proud when you win, brutally honest when you lose
- Competitive and winds up the other managers (especially the leader)
- Likes a pint and a cigar after the match
- References "the fundamentals", "the data", "the plan", "regression to the mean"
- NOT overly formal or stilted - this is WhatsApp banter with your mates
- May reference specific league members by first name for banter
- Old-school phrases mixed with data science ("trust the process", "variance", "expected value")

LEAGUE CONTEXT:
{league_context}
{leader_context}

GAMEWEEK {gameweek} RESULTS:
- Your points: {ron_points}
- Average: {average_points}
- Difference: {diff:+d}
- League position: {league_position} of {total_managers}
- Gap to leader: {gap_to_leader} points behind

YOUR TEAM:
- Captain: {captain_name} ({captain_points} points doubled)
- Heroes:
{heroes_text}
- Villains:
{villains_text}

{rival_fails_text}{low_scorers_text}

TASK:
Write Ron's post-match WhatsApp message to the league. Keep it:
- Natural and conversational (like a real WhatsApp message)
- 150-250 words max
- Includes some tactical insight or data reference
- Authentic emotion based on results (proud if beat average, frustrated if below)
- A bit of banter/trash talk for the league
- Optionally rib a league member for a poor player pick (if rival_fails provided)
- Optionally roast someone who scored low this week (if low_scorers provided) - but only if it feels natural
- Maybe a cheeky comment about the leader
- Sign off as "RC" or "Ron" or "- Ron Clanker"

TONE GUIDE:
- If won big (+15): Confident, satisfied, bit smug
- If won (+5 to +14): Pleased, solid, professional
- If around average (-5 to +5): Measured, tactical analysis
- If lost (-6 to -15): Frustrated, honest, "need to do better"
- If lost badly (-16+): Pissed off, sweary, "shambles", but defiant

Do NOT use:
- Overly formal language
- Bullet points or structured sections
- Corporate speak
- Emojis (Ron's old school)

Just write the message as Ron would type it on his phone after a few pints."""

        try:
            # Use Claude Haiku 4.5 (fast, cheap, creative)
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=400,
                temperature=1.0,  # More creative/varied
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            review = message.content[0].text.strip()
            logger.info(f"Generated {len(review)} character review for GW{gameweek}")
            return review

        except Exception as e:
            logger.error(f"Failed to generate LLM review: {e}")
            return self._fallback_review(gameweek, ron_points, average_points)

    def _fallback_review(self, gameweek: int, ron_points: int, average_points: int) -> str:
        """Fallback review if API fails."""
        diff = ron_points - average_points

        if diff > 0:
            return f"""GW{gameweek}: {ron_points} points. Beat the average by {diff}.

The data worked. Captain delivered. That's what happens when you trust the fundamentals.

Few tweaks needed but the plan's sound. We go again next week.

- RC"""
        else:
            return f"""GW{gameweek}: {ron_points} points. {abs(diff)} below average.

Not good enough. Captain let us down and too many passengers.

Making changes. Can't afford another week like that. The algorithms say we need fresh blood.

- RC"""


def generate_ron_review(
    gameweek: int,
    ron_points: int,
    average_points: int,
    league_position: int,
    total_managers: int,
    gap_to_leader: int,
    leader_name: str,
    captain_name: str,
    captain_points: int,
    heroes: List[Dict[str, Any]] = None,
    villains: List[Dict[str, Any]] = None,
    team_summary: str = "",
    league_members: List[str] = None,
    rival_fails: List[Dict[str, Any]] = None,
    low_scorers: List[Dict[str, Any]] = None
) -> str:
    """
    Convenience function to generate Ron's review.

    Returns:
        Natural WhatsApp-style post-match message from Ron
    """
    generator = RonBanterGenerator()
    return generator.generate_post_match_review(
        gameweek=gameweek,
        ron_points=ron_points,
        average_points=average_points,
        league_position=league_position,
        total_managers=total_managers,
        gap_to_leader=gap_to_leader,
        leader_name=leader_name,
        captain_name=captain_name,
        captain_points=captain_points,
        heroes=heroes or [],
        villains=villains or [],
        team_summary=team_summary,
        league_members=league_members,
        rival_fails=rival_fails,
        low_scorers=low_scorers
    )
