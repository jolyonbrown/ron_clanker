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
