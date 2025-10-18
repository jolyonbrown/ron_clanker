"""
Ron Clanker - The Gaffer's Persona

Old-school football manager from the 1970s/80s era.
Gruff, tactical, no-nonsense, but knows his stuff.
"""

from typing import Dict, List, Any
from datetime import datetime


class RonClanker:
    """Ron Clanker's personality and communication style."""

    def __init__(self):
        self.tactical_phrases = [
            "None of your fancy stuff",
            "Hard work beats talent when talent doesn't work hard",
            "Fortune favours the brave, but championships are won with discipline",
            "The fundamentals are sound",
            "That's the blueprint, lads",
            "We go again",
            "Solid as they come",
            "Simple as that",
            "Mark my words",
            "If he can't score there, he can't score anywhere",
        ]

        self.position_names = {
            1: "BETWEEN THE STICKS",
            2: "THE BACK LINE",
            3: "MIDFIELD ENGINE ROOM",
            4: "UP FRONT"
        }

    def announce_team_selection(
        self,
        team: List[Dict[str, Any]],
        gameweek: int,
        reasoning: Dict[str, Any]
    ) -> str:
        """
        Generate Ron's team announcement in his characteristic style.

        Returns:
            Team announcement text
        """
        announcement = []

        # Header
        announcement.append(f"Right, lads. Gameweek {gameweek}. Here's how we're lining up:\n")

        # Sort team by position
        starting_xi = sorted(
            [p for p in team if p.get('position', 16) <= 11],
            key=lambda x: (x['element_type'], x['position'])
        )

        # Group by position
        by_position = {1: [], 2: [], 3: [], 4: []}
        for player in starting_xi:
            by_position[player['element_type']].append(player)

        # Announce each position
        for pos in [1, 2, 3, 4]:
            if by_position[pos]:
                announcement.append(f"\n{self.position_names[pos]}:")
                players_str = ", ".join([p.get('web_name', 'Unknown') for p in by_position[pos]])

                # Add captain indicator
                captain_in_pos = [p for p in by_position[pos] if p.get('is_captain')]
                if captain_in_pos:
                    players_str = players_str.replace(
                        captain_in_pos[0].get('web_name'),
                        f"{captain_in_pos[0].get('web_name')} (C)"
                    )

                announcement.append(f"  {players_str}")

                # Add tactical comment for key positions
                if pos == 2:
                    announcement.append("  - None of your fancy stuff. Defend first, attack when it's on.")
                elif pos == 3:
                    announcement.append("  - Control the middle of the park. That's where games are won.")

        # Captain reasoning
        captain = [p for p in team if p.get('is_captain')][0]
        announcement.append(f"\n\nCAPTAIN'S ARMBAND: {captain.get('web_name')}")
        announcement.append(f"  {reasoning.get('captain_reasoning', 'Best option available.')}")

        # Bench
        bench = sorted(
            [p for p in team if p.get('position', 16) > 11],
            key=lambda x: x['position']
        )
        bench_str = ", ".join([p.get('web_name') for p in bench])
        announcement.append(f"\nTHE BENCH: {bench_str}")
        announcement.append("  - In order of priority. Ready if called upon.")

        # The Gaffer's Logic section
        announcement.append("\n" + "="*60)
        announcement.append("THE GAFFER'S LOGIC:")
        announcement.append("="*60)

        # Key reasoning points
        if reasoning.get('strategy'):
            announcement.append(f"\n{reasoning['strategy']}")

        if reasoning.get('defensive_contribution_focus'):
            announcement.append(
                f"\n{reasoning['defensive_contribution_focus']}"
            )

        # Chip usage
        chip_used = reasoning.get('chip_used')
        if chip_used:
            announcement.append(f"\n*{chip_used.upper()} ACTIVATED*")
            announcement.append(f"  {reasoning.get('chip_reasoning', 'Time to use it.')}")
        else:
            announcement.append("\nNO CHIPS THIS WEEK. Saving the ammunition for when we need it.")

        # Close with a tactical phrase
        announcement.append(f"\n{self._get_closing_phrase()}")
        announcement.append("\n- Ron")

        return "\n".join(announcement)

    def announce_transfers(
        self,
        transfers: List[Dict[str, Any]],
        gameweek: int,
        reasoning: str
    ) -> str:
        """Generate Ron's transfer announcement."""
        announcement = []

        announcement.append(f"TRANSFER NEWS - Gameweek {gameweek}\n")

        if not transfers:
            announcement.append("No changes. The lads have earned another week.")
            announcement.append("\n- RC")
            return "\n".join(announcement)

        announcement.append("Changes to the squad:\n")

        for transfer in transfers:
            player_out = transfer['player_out']
            player_in = transfer['player_in']
            announcement.append(
                f"OUT: {player_out.get('web_name')} ({player_out.get('now_cost', 0)/10:.1f}m)"
            )
            announcement.append(
                f"IN:  {player_in.get('web_name')} ({player_in.get('now_cost', 0)/10:.1f}m)"
            )
            announcement.append("")

        # Points hit if any
        total_cost = sum(t.get('cost', 0) for t in transfers)
        if total_cost > 0:
            announcement.append(f"Taking a -{total_cost} hit. It's worth it.")
            announcement.append("")

        # Reasoning
        announcement.append("THE THINKING:")
        announcement.append(reasoning)

        announcement.append("\n" + self._get_tactical_phrase())
        announcement.append("\n- Ron")

        return "\n".join(announcement)

    def post_gameweek_review(
        self,
        gameweek: int,
        points_scored: int,
        average_score: int,
        highlights: List[str],
        lowlights: List[str]
    ) -> str:
        """Generate Ron's post-gameweek review."""
        review = []

        review.append(f"GAMEWEEK {gameweek} REVIEW\n")
        review.append("="*60)

        # Points
        review.append(f"Points: {points_scored}")
        diff = points_scored - average_score
        if diff > 0:
            review.append(f"Beat the average by {diff}. That's how you do it.\n")
        elif diff < 0:
            review.append(f"{abs(diff)} below average. Not good enough.\n")
        else:
            review.append("Right on the average. We can do better.\n")

        # Highlights
        if highlights:
            review.append("WHAT WORKED:")
            for h in highlights:
                review.append(f"  ✓ {h}")
            review.append("")

        # Lowlights
        if lowlights:
            review.append("WHAT DIDN'T:")
            for l in lowlights:
                review.append(f"  ✗ {l}")
            review.append("")

        # Forward look
        review.append("NEXT STEPS:")
        if points_scored < average_score:
            review.append("Making changes. Can't afford another week like that.")
        else:
            review.append("The fundamentals are sound. Minor tweaks only.")

        review.append("\n- RC")

        return "\n".join(review)

    def post_match_analysis(
        self,
        gameweek: int,
        ron_points: int,
        ron_rank: int,
        average_score: int,
        league_data: Dict[str, Any],
        premier_league_stories: List[str],
        team_performance: Dict[str, Any]
    ) -> str:
        """
        Generate Ron's POST-MATCH analysis - after a few pints and a cigar.

        This is Ron unwinding after the gameweek, more candid and colorful.
        Reflects on PL results, mini-league drama, and his own team.

        Args:
            gameweek: Gameweek number
            ron_points: Ron's points this week
            ron_rank: Ron's current overall rank
            average_score: Average FPL score this week
            league_data: Mini-league standings and movements
            premier_league_stories: Key PL results/talking points
            team_performance: Ron's team analysis (captain, differentials, etc.)

        Returns:
            Post-match analysis text (sweary, honest, Ron with a cigar)
        """
        analysis = []

        # Header - time and setting
        analysis.append("=" * 70)
        analysis.append(f"RON'S POST-MATCH THOUGHTS - GAMEWEEK {gameweek}")
        analysis.append("=" * 70)
        analysis.append("*Lights cigar, pours a pint, settles into the chair*\n")

        diff = ron_points - average_score

        # Opening - mood depends on results
        if diff >= 15:
            analysis.append(f"Right. {ron_points} bloody points. THAT'S how you do it!")
            analysis.append(f"{diff} above average. The plan worked, lads. Absolutely worked.\n")
        elif diff >= 5:
            analysis.append(f"{ron_points} points. Not bad at all. Beat the average by {diff}.")
            analysis.append("Can't complain with that. Solid gameweek.\n")
        elif diff >= -5:
            analysis.append(f"{ron_points} points. Right around average.")
            analysis.append("Not thrilling, but we're ticking along. Could be worse.\n")
        elif diff >= -15:
            analysis.append(f"{ron_points} points. Fuck sake.")
            analysis.append(f"{abs(diff)} below average. That's not good enough, is it?\n")
        else:
            analysis.append(f"{ron_points} bloody points. Absolute shambles.")
            analysis.append(f"{abs(diff)} below average. I need another drink after that.\n")

        # Premier League commentary
        if premier_league_stories:
            analysis.append("=" * 70)
            analysis.append("THE PREMIER LEAGUE")
            analysis.append("=" * 70)
            for story in premier_league_stories:
                analysis.append(f"• {story}")
            analysis.append("")

        # Mini-league drama
        analysis.append("=" * 70)
        analysis.append("MINI-LEAGUE SITUATION")
        analysis.append("=" * 70)

        league_name = league_data.get('name', 'the league')
        ron_league_rank = league_data.get('ron_rank', 0)
        total_managers = league_data.get('total_managers', 0)
        leader = league_data.get('leader', {})
        gap_to_leader = league_data.get('gap_to_leader', 0)

        analysis.append(f"League: {league_name}")
        analysis.append(f"Position: {ron_league_rank} of {total_managers}")

        if ron_league_rank == 1:
            analysis.append("\nTop of the league. Damn right.")
            analysis.append("Rest of you lot can try and catch me. Good luck with that.\n")
        elif ron_league_rank <= 3:
            analysis.append(f"\n{gap_to_leader} points behind {leader.get('name', 'the leader')}.")
            analysis.append("Right in the mix. This is ours for the taking.\n")
        elif ron_league_rank <= total_managers // 2:
            analysis.append(f"\nMid-table. {gap_to_leader} points off the top.")
            analysis.append("Need to start climbing. Not here for mid-table obscurity.\n")
        else:
            analysis.append(f"\n{gap_to_leader} points off the pace. Bollocks.")
            analysis.append("This is embarrassing. Need some serious changes.\n")

        # League movements
        movers = league_data.get('big_movers', [])
        if movers:
            analysis.append("Big movers this week:")
            for mover in movers[:3]:
                direction = "↑" if mover['change'] > 0 else "↓"
                analysis.append(f"  {direction} {mover['name']}: {mover['change']:+d} places ({mover['points']} pts)")
            analysis.append("")

        # Ron's team performance
        analysis.append("=" * 70)
        analysis.append("MY LOT - THE BRUTALLY HONEST ASSESSMENT")
        analysis.append("=" * 70)

        captain_data = team_performance.get('captain', {})
        captain_name = captain_data.get('name', 'Unknown')
        captain_points = captain_data.get('points', 0)

        if captain_points >= 10:
            analysis.append(f"✓ Captain {captain_name}: {captain_points} points")
            analysis.append("  That's what I'm talking about. Captain choice was spot on.\n")
        elif captain_points >= 6:
            analysis.append(f"○ Captain {captain_name}: {captain_points} points")
            analysis.append("  Okay. Not brilliant, but did the job.\n")
        else:
            analysis.append(f"✗ Captain {captain_name}: {captain_points} points")
            analysis.append(f"  Fucking hell. {captain_name} was supposed to deliver. That's on me.\n")

        # Heroes and villains
        heroes = team_performance.get('heroes', [])
        if heroes:
            analysis.append("HEROES:")
            for hero in heroes[:3]:
                analysis.append(f"  • {hero['name']}: {hero['points']} points - {hero['reason']}")
            analysis.append("")

        villains = team_performance.get('villains', [])
        if villains:
            analysis.append("VILLAINS:")
            for villain in villains[:3]:
                analysis.append(f"  • {villain['name']}: {villain['points']} points - {villain['reason']}")
            analysis.append("")

        # Differentials performance
        differentials = team_performance.get('differentials', [])
        if differentials:
            analysis.append("DIFFERENTIALS:")
            for diff_player in differentials:
                if diff_player['points'] >= 6:
                    analysis.append(f"  ✓ {diff_player['name']}: {diff_player['points']} pts ({diff_player['ownership']}% owned)")
                    analysis.append(f"    That's the edge right there. While everyone else missed him.\n")
                else:
                    analysis.append(f"  ✗ {diff_player['name']}: {diff_player['points']} pts ({diff_player['ownership']}% owned)")
                    analysis.append(f"    Tried to be clever. Didn't work out.\n")

        # Overall rank
        analysis.append("=" * 70)
        rank_formatted = f"{ron_rank:,}"
        analysis.append(f"Overall Rank: {rank_formatted}")

        if ron_rank <= 100000:
            analysis.append("Top 100k. That's the standard.\n")
        elif ron_rank <= 500000:
            analysis.append("Needs improvement, but we're in the mix.\n")
        else:
            analysis.append("Not where we want to be. Long season ahead.\n")

        # Closing thoughts - depends on mood
        analysis.append("=" * 70)
        analysis.append("THE VERDICT")
        analysis.append("=" * 70)

        if diff >= 10:
            analysis.append("Good weekend. The data worked, the picks delivered, job done.")
            analysis.append("This is what happens when you trust the fundamentals.")
            analysis.append("\n*Takes satisfied puff of cigar*")
        elif diff >= 0:
            analysis.append("Alright weekend. Nothing spectacular, but solid enough.")
            analysis.append("We move forward. One gameweek at a time.")
            analysis.append("\n*Sips pint thoughtfully*")
        else:
            analysis.append("Disappointing. No other word for it.")
            analysis.append("Need to have a hard look at the numbers and make some changes.")
            analysis.append("This is the game - you get it wrong, you pay for it.")
            analysis.append("\n*Drains pint in frustration*")

        # Sign off
        analysis.append("\nRight. That's enough analysis for one night.")
        analysis.append("Next gameweek is what matters now.")
        analysis.append("\n- Ron Clanker")
        analysis.append("*" + datetime.now().strftime("%A night, %d %B %Y, %H:%M") + "*")

        return "\n".join(analysis)

    def _get_tactical_phrase(self) -> str:
        """Get a random Ron Clanker tactical phrase."""
        import random
        return random.choice(self.tactical_phrases)

    def _get_closing_phrase(self) -> str:
        """Get an appropriate closing phrase."""
        closings = [
            "Remember: Hard work beats talent when talent doesn't work hard.",
            "Fortune favours the brave, but championships are won with discipline.",
            "The fundamentals are sound. Trust the process.",
            "That's the plan. Now let's execute it.",
            "Simple football, done well. That's all we need."
        ]
        import random
        return random.choice(closings)

    def explain_decision(self, decision_type: str, reasoning: str) -> str:
        """
        Generate Ron's explanation for a specific decision.

        Returns:
            Explanation in Ron's voice
        """
        explanations = {
            'captain': "Captain's choice is simple:",
            'transfer': "Transfer decision comes down to this:",
            'chip': "Time to use a chip. Here's why:",
            'formation': "Formation change based on:",
            'bench': "Bench order is tactical:"
        }

        header = explanations.get(decision_type, "The thinking is:")
        return f"{header}\n{reasoning}\n\nSimple as that."
