"""
Player Valuation Agent

Assesses player value and calculates expected points.
KEY FOCUS: Exploits 2025/26 Defensive Contribution rules for competitive edge.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
from rules.scoring import PointsCalculator

logger = logging.getLogger(__name__)


class PlayerValuationAgent:
    """
    Specialist agent for player valuation and point prediction.

    Phase 1 Strategy: Simple but effective
    - Form-based predictions
    - Fixture difficulty weighting
    - NEW: Defensive Contribution identification (our edge!)
    - Value per million calculations
    """

    def __init__(self):
        self.calculator = PointsCalculator()

    # ========================================================================
    # CORE VALUATION METHODS
    # ========================================================================

    def calculate_expected_points(
        self,
        player: Dict[str, Any],
        fixture_difficulty: int = 3,
        num_gameweeks: int = 1
    ) -> float:
        """
        Calculate expected points for upcoming gameweek(s).

        Uses:
        - Recent form (points per game)
        - Fixture difficulty adjustment
        - Minutes probability
        - Defensive contribution likelihood

        Args:
            player: Player data dict
            fixture_difficulty: 1-5 (1=easiest)
            num_gameweeks: Number of gameweeks to project

        Returns:
            Expected points for the period
        """
        # Get base expected points from form
        ppg = float(player.get('points_per_game', 0) or 0)
        form = float(player.get('form', 0) or 0)

        # Weight recent form more heavily
        base_expectation = (ppg * 0.4) + (form * 0.6)

        # Adjust for fixture difficulty
        difficulty_multiplier = {
            1: 1.25,  # Very easy
            2: 1.1,   # Easy
            3: 1.0,   # Average
            4: 0.9,   # Hard
            5: 0.75   # Very hard
        }.get(fixture_difficulty, 1.0)

        # Adjust for minutes probability
        minutes = player.get('minutes', 0)
        total_games = player.get('appearances', 1) or 1
        minutes_per_game = minutes / max(total_games, 1)

        if minutes_per_game < 30:
            minutes_probability = 0.3
        elif minutes_per_game < 60:
            minutes_probability = 0.7
        elif minutes_per_game < 80:
            minutes_probability = 0.9
        else:
            minutes_probability = 1.0

        # Calculate expected points
        expected = (
            base_expectation *
            difficulty_multiplier *
            minutes_probability *
            num_gameweeks
        )

        return round(expected, 2)

    def calculate_value_score(self, player: Dict[str, Any]) -> float:
        """
        Calculate overall value score (points per million).

        Higher is better.
        """
        cost = player.get('now_cost', 1) / 10  # Convert to £m
        total_points = player.get('total_points', 0)

        if cost == 0:
            return 0

        value = total_points / cost
        return round(value, 2)

    def assess_defensive_contribution_potential(
        self,
        player: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        NEW 2025/26: Identify players likely to earn defensive contribution points.

        This is our competitive edge! Most managers will overlook these players.

        Returns:
            Dict with DC assessment and recommendations
        """
        position = player.get('element_type')
        player_name = player.get('web_name', 'Unknown')

        # Only DEF and MID can earn DC points
        if position not in [2, 3]:
            return {
                'eligible': False,
                'likelihood': 0,
                'expected_dc_points_per_game': 0,
                'reasoning': 'Not a defender or midfielder'
            }

        # For Phase 1, use proxy metrics since we don't have detailed tackle/interception data yet
        # We'll use BPS and ICT index as proxies for defensive work
        bps = player.get('bps', 0)
        total_points = player.get('total_points', 0)
        games = player.get('appearances', 1) or 1

        # Heuristic: Defenders with high BPS relative to points likely doing defensive work
        # Midfielders with defensive roles similar
        points_per_game = total_points / games
        bps_per_game = bps / games

        if position == 2:  # Defender
            # High BPS defenders likely getting tackles/interceptions
            if bps_per_game >= 25:
                likelihood = 0.8
                expected_dc = 1.6  # 80% chance * 2 points
                reasoning = f"High BPS/game ({bps_per_game:.1f}) suggests strong defensive work"
            elif bps_per_game >= 20:
                likelihood = 0.6
                expected_dc = 1.2
                reasoning = f"Good BPS/game ({bps_per_game:.1f}) suggests decent defensive work"
            else:
                likelihood = 0.3
                expected_dc = 0.6
                reasoning = f"Lower BPS/game ({bps_per_game:.1f}) suggests inconsistent DC"

        else:  # Midfielder (position == 3)
            # Defensive midfielders - need to identify these
            # Heuristic: Low attacking returns but high BPS = defensive mid
            attacking_returns_per_game = (
                player.get('goals_scored', 0) + player.get('assists', 0)
            ) / games

            if attacking_returns_per_game < 0.2 and bps_per_game >= 20:
                # Likely defensive midfielder
                likelihood = 0.7
                expected_dc = 1.4
                reasoning = f"Low attacking returns ({attacking_returns_per_game:.2f}/game) but high BPS suggests defensive mid"
            elif attacking_returns_per_game < 0.3 and bps_per_game >= 15:
                likelihood = 0.5
                expected_dc = 1.0
                reasoning = "Moderate defensive contribution likely"
            else:
                likelihood = 0.2
                expected_dc = 0.4
                reasoning = "Primarily attacking midfielder, occasional DC"

        return {
            'eligible': True,
            'likelihood': likelihood,
            'expected_dc_points_per_game': round(expected_dc, 2),
            'reasoning': reasoning,
            'competitive_edge': likelihood >= 0.6  # Flag high-potential DC players
        }

    # ========================================================================
    # PLAYER RANKING & RECOMMENDATIONS
    # ========================================================================

    def rank_players_by_value(
        self,
        players: List[Dict[str, Any]],
        position: Optional[int] = None,
        max_price: Optional[int] = None,
        include_dc_boost: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Rank players by overall value considering multiple factors.

        Args:
            players: List of player dicts
            position: Optional position filter (1=GK, 2=DEF, 3=MID, 4=FWD)
            max_price: Optional max price filter
            include_dc_boost: Whether to boost DEF/MID with DC potential

        Returns:
            Sorted list of players with value scores
        """
        ranked = []

        for player in players:
            # Apply filters
            if position and player.get('element_type') != position:
                continue
            if max_price and player.get('now_cost', 9999) > max_price:
                continue

            # Skip unavailable players
            if player.get('status') != 'a':
                continue
            if player.get('chance_of_playing_next_round', 100) < 75:
                continue

            # Calculate base value
            value_score = self.calculate_value_score(player)

            # NEW: Add DC potential boost
            dc_boost = 0
            if include_dc_boost and player.get('element_type') in [2, 3]:
                dc_assessment = self.assess_defensive_contribution_potential(player)
                if dc_assessment['competitive_edge']:
                    # Boost value for high DC potential players
                    dc_boost = dc_assessment['expected_dc_points_per_game'] * 0.5

            total_value = value_score + dc_boost

            ranked.append({
                **player,
                'value_score': value_score,
                'dc_boost': dc_boost,
                'total_value_score': round(total_value, 2)
            })

        # Sort by total value score
        ranked.sort(key=lambda x: x['total_value_score'], reverse=True)

        return ranked

    def find_bargain_players(
        self,
        players: List[Dict[str, Any]],
        position: Optional[int] = None,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Identify undervalued players with high expected returns.

        Perfect for building budget-friendly squad.

        Returns:
            Top N bargain players
        """
        # Focus on players under 7.0m
        bargain_candidates = [
            p for p in players
            if p.get('now_cost', 999) <= 70 and  # Under 7.0m
            p.get('minutes', 0) > 270  # At least 3 full games
        ]

        ranked = self.rank_players_by_value(bargain_candidates, position)

        return ranked[:top_n]

    def find_premium_players(
        self,
        players: List[Dict[str, Any]],
        position: Optional[int] = None,
        min_price: int = 90,  # 9.0m+
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Identify best premium players worth the investment.

        Returns:
            Top N premium players
        """
        premium_candidates = [
            p for p in players
            if p.get('now_cost', 0) >= min_price
        ]

        ranked = self.rank_players_by_value(premium_candidates, position)

        return ranked[:top_n]

    # ========================================================================
    # TEAM VALUATION
    # ========================================================================

    def evaluate_team(
        self,
        team: List[Dict[str, Any]],
        upcoming_fixtures: Dict[int, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Evaluate overall team strength and expected points.

        Args:
            team: List of 15 players
            upcoming_fixtures: Dict mapping player_id to fixture list

        Returns:
            Team evaluation with strengths, weaknesses, and expected points
        """
        total_expected = 0
        position_breakdown = {1: [], 2: [], 3: [], 4: []}

        for player in team:
            player_id = player['id']
            position = player['element_type']

            # Get average fixture difficulty for this player
            fixtures = upcoming_fixtures.get(player_id, [])
            if fixtures:
                avg_difficulty = sum(f.get('difficulty', 3) for f in fixtures[:3]) / min(len(fixtures), 3)
            else:
                avg_difficulty = 3

            expected_points = self.calculate_expected_points(player, int(avg_difficulty))

            position_breakdown[position].append({
                'player': player.get('web_name'),
                'expected_points': expected_points
            })

            # Only count starting XI
            if player.get('position', 16) <= 11:
                # Apply captain multiplier
                if player.get('is_captain'):
                    expected_points *= 2
                total_expected += expected_points

        return {
            'total_expected_points': round(total_expected, 2),
            'position_breakdown': position_breakdown,
            'team_value': sum(p.get('now_cost', 0) for p in team) / 10,
            'evaluation_timestamp': 'now'
        }

    def identify_transfer_targets(
        self,
        current_team: List[Dict[str, Any]],
        all_players: List[Dict[str, Any]],
        position: Optional[int] = None,
        max_price: Optional[int] = None
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
        """
        Identify potential transfer targets to upgrade team.

        Returns:
            List of (player_out, player_in, expected_gain) tuples
        """
        opportunities = []

        # Get players not in current team
        team_ids = {p['id'] for p in current_team}
        available_players = [p for p in all_players if p['id'] not in team_ids]

        # Rank available players
        ranked_available = self.rank_players_by_value(
            available_players,
            position=position,
            max_price=max_price
        )

        # For each current team player, find better alternatives
        for current_player in current_team:
            current_pos = current_player['element_type']
            current_value = current_player.get('total_value_score', 0)

            # Find players in same position with better value
            better_players = [
                p for p in ranked_available
                if p['element_type'] == current_pos and
                p.get('total_value_score', 0) > current_value * 1.1  # At least 10% better
            ]

            for better_player in better_players[:3]:  # Top 3 alternatives
                expected_gain = self.calculate_expected_points(better_player, 3) - \
                               self.calculate_expected_points(current_player, 3)

                if expected_gain > 0.5:  # Meaningful improvement
                    opportunities.append((
                        current_player,
                        better_player,
                        round(expected_gain, 2)
                    ))

        # Sort by expected gain
        opportunities.sort(key=lambda x: x[2], reverse=True)

        return opportunities[:10]  # Top 10 transfer opportunities
