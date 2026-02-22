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
        reasoning: Dict[str, Any] = None,
        fixtures: Dict[int, Dict[str, Any]] = None,
        league_position: int = None,
        league_total: int = None,
        overall_rank: int = None,
        total_points: int = None
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
            fixtures: Dict mapping team_id to fixture info:
                      {team_id: {'opponent': 'ARS', 'home': True, 'fdr': 3}}

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
        # Group starting XI by position type, including fixture info
        starting_by_pos = {'GKP': [], 'DEF': [], 'MID': [], 'FWD': []}
        for player in starting_xi:
            pos_name = ['', 'GKP', 'DEF', 'MID', 'FWD'][player.get('element_type', 1)]
            suffix = " (C)" if player.get('is_captain') else " (VC)" if player.get('is_vice_captain') else ""

            # Add fixture info if available
            fixture_str = ""
            if fixtures:
                team_id = player.get('team_id') or player.get('team')
                if team_id and team_id in fixtures:
                    fix = fixtures[team_id]
                    h_a = "(H)" if fix.get('home') else "(A)"
                    fixture_str = f" vs {fix['opponent']} {h_a}"

            starting_by_pos[pos_name].append(f"{player['web_name']}{suffix}{fixture_str}")

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

        # Build league context
        league_context = ""
        if league_position and league_total:
            league_context = f"LEAGUE POSITION: {league_position} of {league_total}\n"
        if overall_rank:
            league_context += f"OVERALL RANK: {overall_rank:,}\n"
        if total_points:
            league_context += f"TOTAL POINTS: {total_points}\n"

        prompt = f"""You are Ron Clanker, a gruff 1970s/80s football manager who now runs an autonomous FPL team using AI and data science. You're announcing your team selection for Gameweek {gameweek} to the league WhatsApp group.

CHARACTER - Ron Clanker:
- Managed lower-league clubs in the 70s and 80s. Hard as nails. Knows the game inside out.
- Now uses "the algorithms", "the models", "the data" - but always filtered through proper football knowledge
- Blunt, sweary when the mood takes him, and proud of his unconventional picks
- Uses old-school football language: "between the sticks", "the back line", "engine room", "up front", "the gaffer's logic"
- Genuinely believes in Defensive Contribution as the market inefficiency of the season
- Talks about players like he's watched them train all week
- Mixes data science with gut feeling: "the models say 8.9 xP but I've seen that look in his eye"
- Has genuine tactical opinions - WHY this formation, WHY these players over alternatives
- Competitive, confident, occasionally self-deprecating when he's had a bad week

{league_context}

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
Write Ron's team announcement for Gameweek {gameweek}. This goes to the league group chat.

Ron should walk through the team position by position, giving his reasoning for key picks. He should explain the tactical approach, why the captain got the armband, and what he expects from the gameweek. If transfers were made, explain the logic properly.

STRUCTURE (use as a guide, not a rigid template):

GAMEWEEK {gameweek} - RON'S TEAM SELECTION

[Opening line - Ron's mood, the situation, what's at stake]

BETWEEN THE STICKS: [Keeper with 1-2 sentences on why]

THE BACK LINE: [Defenders with reasoning - mention DC stats, clean sheet potential, fixtures]

MIDFIELD ENGINE ROOM: [Midfielders with reasoning - form, fixtures, DC potential, differentials]

UP FRONT: [Forwards with reasoning]

[If transfers made: explain the logic - who's out, who's in, and WHY with conviction]

THE GAFFER'S LOGIC:
[2-3 sentences on the overall tactical approach this week. What's the strategy? Where are the points coming from? What edge does Ron have over the template managers?]

[Captain reasoning - proper explanation with data]
[Bench order logic if noteworthy]
[Chip status and bank balance]

- Ron

CRITICAL ACCURACY RULES:
- ONLY use facts provided in the data above. Do NOT invent statistics, league positions, points gaps, clean sheet records, xP numbers, or any other data.
- Each player's TEAM and FIXTURE is shown next to their name above (e.g. "Wilson vs SOU (A)" means Wilson plays AWAY to Southampton). Use ONLY these fixtures. Do NOT guess or change them.
- The bank balance is stated above as "IN THE BANK". Use that exact figure.
- If league position is provided above, use it. If not, do NOT mention league position or points gaps.
- Do NOT fabricate percentages, clean sheet probabilities, or xP figures. Ron can reference "the data" or "the models" vaguely without inventing specific numbers.
- If you don't know a fact, Ron can be vague ("the data backs it", "form's there") rather than making something up.

OTHER RULES:
- CRITICAL: Use the EXACT positions given above (GK/DEF/MID/FWD). Do NOT move players between positions.
- Aim for 200-400 words. Not a tweet, not an essay.
- Every key decision should have a WHY
- Mix Ron's old-school wisdom with data-driven insight

TONE:
- Confident and authoritative - this is THE GAFFER speaking
- Colourful language and football metaphors
- Genuine tactical insight, not just listing players
- Passion for his picks, especially the clever ones others might miss
- A touch of swagger

Do NOT:
- Use emojis
- Move players to different positions than shown above
- Invent ANY statistics or facts not provided in the data above
- Be generic - every line should feel like Ron specifically chose those words
- Use corporate/formal language - Ron's a football man, not a CEO"""

        try:
            # Use Claude Haiku 4.5
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1200,
                temperature=1.0,  # Creative and varied
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
    reasoning: Dict[str, Any] = None,
    fixtures: Dict[int, Dict[str, Any]] = None,
    league_position: int = None,
    league_total: int = None,
    overall_rank: int = None,
    total_points: int = None
) -> str:
    """
    Convenience function to generate Ron's team announcement.

    Args:
        fixtures: Dict mapping team_id to fixture info:
                  {team_id: {'opponent': 'ARS', 'home': True, 'fdr': 3}}
        league_position: Ron's position in mini-league
        league_total: Total managers in mini-league
        overall_rank: Overall FPL rank
        total_points: Total FPL points this season

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
        reasoning=reasoning,
        fixtures=fixtures,
        league_position=league_position,
        league_total=league_total,
        overall_rank=overall_rank,
        total_points=total_points
    )
