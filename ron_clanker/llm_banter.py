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


    def generate_team_announcement(
        self,
        gameweek: int,
        squad: List[Dict[str, Any]],
        transfers: List[Dict[str, Any]],
        chip_used: str = None,
        free_transfers: int = 1,
        bank: float = 0.0,
        reasoning: Dict[str, Any] = None
    ) -> str:
        """
        Generate Ron's pre-deadline team announcement.

        Args:
            gameweek: GW number
            squad: Full 15-player squad with positions, captain, etc.
            transfers: List of {player_out, player_in, reasoning} dicts
            chip_used: Name of chip used (or None)
            free_transfers: Number of free transfers available
            bank: Money in the bank
            reasoning: Optional dict with strategy notes

        Returns:
            Natural, authentic Ron team announcement
        """

        if not self.enabled:
            logger.error("Cannot generate announcement - API key not configured")
            return self._fallback_announcement(gameweek, squad, transfers)

        # Organize squad by position
        by_position = {'GKP': [], 'DEF': [], 'MID': [], 'FWD': []}
        starting_xi = []
        bench = []

        for player in squad:
            pos_name = ['', 'GKP', 'DEF', 'MID', 'FWD'][player.get('element_type', player.get('position_type', 1))]
            by_position[pos_name].append(player)

            if player.get('position', 16) <= 11:
                starting_xi.append(player)
            else:
                bench.append(player)

        # Find captain
        captain = next((p for p in squad if p.get('is_captain')), starting_xi[0] if starting_xi else squad[0])
        vice = next((p for p in squad if p.get('is_vice_captain')), None)

        # Format squad details BY POSITION to prevent LLM confusion
        # Group starting XI by position type
        starting_by_pos = {'GKP': [], 'DEF': [], 'MID': [], 'FWD': []}
        for player in starting_xi:
            pos_name = ['', 'GKP', 'DEF', 'MID', 'FWD'][player.get('element_type', 1)]
            suffix = " (C)" if player.get('is_captain') else " (VC)" if player.get('is_vice_captain') else ""
            starting_by_pos[pos_name].append(f"{player['web_name']}{suffix}")

        # Build starting text with explicit position groups
        starting_lines = []
        if starting_by_pos['GKP']:
            starting_lines.append(f"GK: {', '.join(starting_by_pos['GKP'])}")
        if starting_by_pos['DEF']:
            starting_lines.append(f"DEF: {', '.join(starting_by_pos['DEF'])}")
        if starting_by_pos['MID']:
            starting_lines.append(f"MID: {', '.join(starting_by_pos['MID'])}")
        if starting_by_pos['FWD']:
            starting_lines.append(f"FWD: {', '.join(starting_by_pos['FWD'])}")
        starting_text = "\n".join(starting_lines)

        # Format bench with positions to avoid confusion
        bench_sorted = sorted(bench, key=lambda x: x.get('position', 99))
        bench_items = []
        for p in bench_sorted:
            pos_name = ['', 'GK', 'DEF', 'MID', 'FWD'][p.get('element_type', 1)]
            bench_items.append(f"{p['web_name']} ({pos_name})")
        bench_text = ", ".join(bench_items)

        # Format transfers
        transfers_text = ""
        if transfers:
            transfers_text = "TRANSFERS:\n"
            for t in transfers:
                out_name = t['player_out']['web_name']
                in_name = t['player_in']['web_name']
                reason = t.get('reasoning', 'Squad refresh')
                transfers_text += f"OUT: {out_name} → IN: {in_name}\nReason: {reason}\n\n"
        else:
            transfers_text = "NO TRANSFERS - sticking with the squad"

        # Strategy context
        strategy_text = ""
        if reasoning:
            if reasoning.get('approach'):
                strategy_text += f"Approach: {reasoning['approach']}\n"
            if reasoning.get('key_differentials'):
                strategy_text += f"Key differentials: {', '.join(reasoning['key_differentials'])}\n"

        prompt = f"""You are Ron Clanker, a gruff 1970s/80s football manager who now runs an autonomous FPL team using AI and data science. You're announcing your team selection for Gameweek {gameweek}.

CHARACTER TRAITS:
- Old school tactical brain with modern data science tools
- References "the data", "the models", "the algorithms", "expected points"
- Proud of clever picks and differentials
- Honest about taking calculated risks
- Explains decisions with logic and numbers
- Uses football manager language ("between the sticks", "engine room", "up front")
- Not overly formal - direct and authentic
- May swear occasionally if emphasizing a point

GAMEWEEK {gameweek} SELECTION:

STARTING XI ({len(starting_xi)} players):
{starting_text}

BENCH ({len(bench)} players):
{bench_text}

{transfers_text}

CAPTAIN: {captain['web_name']}
VICE-CAPTAIN: {vice['web_name'] if vice else 'TBD'}

CHIP USED: {chip_used or 'None'}
FREE TRANSFERS: {free_transfers}
IN THE BANK: £{bank:.1f}m

{strategy_text}

TASK:
Write Ron's CONCISE team announcement for Gameweek {gameweek}. Ron's in a hurry - pub's calling.

FORMAT:
Example format (NOT a template - write naturally):

GAMEWEEK X - RON'S PICKS

Right. Here's the team.

GK: [name]
DEF: [names]
MID: [names]
FWD: [names]

[Formation]. [If transfers: OUT/IN with 1 sentence why. If no transfers: say so]

[Captain] gets the armband. [1 sentence why with ONE data point].
[Vice] vice. [Brief reason].

[If chip used: which and why. Otherwise: "No chips."]

- Ron

RULES:
- CRITICAL: Use the EXACT positions given above (GK/DEF/MID/FWD). Do NOT move players between positions based on your knowledge - FPL positions may differ from real-life positions.
- MAX 500 characters total (not words - characters!)
- Just the facts: team, captain reasoning (1 sentence), transfers (if any)
- ONE data point max (e.g., "8.9 xP", "City home", "easy fixture")
- Drop: lengthy explanations, tactical essays, multiple justifications
- Ron's got a pint waiting - BE BRIEF

TONE:
- Punchy and direct
- Gets to the point
- Still Ron's voice but economical with words
- Like texting the lads while walking to the pub

Do NOT:
- Write essays or long paragraphs
- Explain every decision
- Use emojis
- Move players to different positions than shown above (e.g., if a player is listed as DEF, keep them as DEF)
- Be overly detailed

Keep it SHORT."""

        try:
            # Use Claude Haiku 4.5
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=600,
                temperature=0.9,  # Creative but focused
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            announcement = message.content[0].text.strip()
            logger.info(f"Generated {len(announcement)} character team announcement for GW{gameweek}")
            return announcement

        except Exception as e:
            logger.error(f"Failed to generate LLM announcement: {e}")
            return self._fallback_announcement(gameweek, squad, transfers)

    def _fallback_announcement(self, gameweek: int, squad: List[Dict], transfers: List[Dict]) -> str:
        """Fallback announcement if API fails."""
        captain = next((p for p in squad if p.get('is_captain')), squad[0])

        announcement = f"""GAMEWEEK {gameweek} - RON'S TEAM SELECTION

Right lads, here's how we're lining up for Gameweek {gameweek}.

Captain: {captain['web_name']}
"""

        if transfers:
            announcement += f"\nTransfers made: {len(transfers)}\n"
            for t in transfers:
                announcement += f"OUT: {t['player_out']['web_name']} → IN: {t['player_in']['web_name']}\n"

        announcement += "\nThe fundamentals are sound. We go again.\n\n- Ron"

        return announcement


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


def generate_team_announcement(
    gameweek: int,
    squad: List[Dict[str, Any]],
    transfers: List[Dict[str, Any]],
    chip_used: str = None,
    free_transfers: int = 1,
    bank: float = 0.0,
    reasoning: Dict[str, Any] = None
) -> str:
    """
    Convenience function to generate Ron's team announcement.

    Returns:
        Natural team announcement from Ron
    """
    generator = RonBanterGenerator()
    return generator.generate_team_announcement(
        gameweek=gameweek,
        squad=squad,
        transfers=transfers,
        chip_used=chip_used,
        free_transfers=free_transfers,
        bank=bank,
        reasoning=reasoning
    )
