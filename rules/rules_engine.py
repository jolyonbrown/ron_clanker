"""
FPL Rules Engine

Validates team selections, transfers, and chip usage against official FPL rules.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from .scoring import PointsCalculator, validate_team_formation


@dataclass
class TeamConstraints:
    """FPL team building constraints."""
    TOTAL_PLAYERS = 15
    STARTING_PLAYERS = 11
    BENCH_PLAYERS = 4

    MAX_PLAYERS_PER_TEAM = 3
    INITIAL_BUDGET = 1000  # £100.0m in FPL units (multiply by 10)

    MIN_GOALKEEPERS = 2
    MAX_GOALKEEPERS = 2
    MIN_DEFENDERS = 3
    MAX_DEFENDERS = 5
    MIN_MIDFIELDERS = 2
    MAX_MIDFIELDERS = 5
    MIN_FORWARDS = 1
    MAX_FORWARDS = 3

    # Starting XI minimums
    MIN_STARTING_DEFENDERS = 3
    MIN_STARTING_FORWARDS = 1


@dataclass
class TransferRules:
    """FPL transfer and chip rules."""
    FREE_TRANSFERS_PER_WEEK = 1
    MAX_BANKED_TRANSFERS = 5
    POINTS_HIT_PER_TRANSFER = 4

    # Chip rules (2025/26 - TWO of each chip)
    CHIPS = ['wildcard', 'bench_boost', 'triple_captain', 'free_hit']
    CHIPS_PER_HALF = {
        'wildcard': 1,
        'bench_boost': 1,
        'triple_captain': 1,
        'free_hit': 1
    }

    # First half chips must be used before GW19 deadline
    FIRST_HALF_DEADLINE_GW = 19
    # Second half chips available from GW20
    SECOND_HALF_START_GW = 20

    # Special events
    AFCON_FREE_TRANSFERS_GW = None  # TBD when AFCON occurs
    AFCON_FREE_TRANSFERS = 5


class RulesEngine:
    """
    Validates all FPL operations against official rules.

    The Rules Engine is the source of truth for what is and isn't allowed.
    """

    def __init__(self):
        self.constraints = TeamConstraints()
        self.transfer_rules = TransferRules()
        self.calculator = PointsCalculator()

    # ========================================================================
    # TEAM VALIDATION
    # ========================================================================

    def validate_team(self, team: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Validate a complete 15-player squad.

        Checks:
        - Correct number of players
        - Valid formation
        - Budget constraint
        - Max 3 players per team
        - Starting XI is valid
        """
        # Basic count check
        if len(team) != self.constraints.TOTAL_PLAYERS:
            return False, f"Must have exactly {self.constraints.TOTAL_PLAYERS} players"

        # Formation validation
        is_valid, msg = validate_team_formation(team)
        if not is_valid:
            return False, msg

        # Budget check
        total_cost = sum(p.get('now_cost', 0) for p in team)
        if total_cost > self.constraints.INITIAL_BUDGET:
            return False, f"Team cost {total_cost/10:.1f}m exceeds budget {self.constraints.INITIAL_BUDGET/10:.1f}m"

        # Max 3 players per team check
        team_counts = {}
        for player in team:
            team_id = player.get('team_id')
            team_counts[team_id] = team_counts.get(team_id, 0) + 1
            if team_counts[team_id] > self.constraints.MAX_PLAYERS_PER_TEAM:
                return False, f"Cannot have more than {self.constraints.MAX_PLAYERS_PER_TEAM} players from same team"

        # Captain validation
        captains = [p for p in team if p.get('is_captain')]
        vice_captains = [p for p in team if p.get('is_vice_captain')]

        if len(captains) != 1:
            return False, "Must have exactly 1 captain"
        if len(vice_captains) != 1:
            return False, "Must have exactly 1 vice-captain"

        # Captain must be in starting XI
        captain = captains[0]
        if captain.get('position', 16) > 11:
            return False, "Captain must be in starting XI"

        return True, "Team is valid"

    def validate_starting_xi(self, team: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Validate that the starting XI meets formation requirements."""
        starting = [p for p in team if p.get('position', 16) <= 11]

        if len(starting) != self.constraints.STARTING_PLAYERS:
            return False, f"Starting XI must have exactly {self.constraints.STARTING_PLAYERS} players"

        # Count by position
        position_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for player in starting:
            pos = player.get('element_type')
            position_counts[pos] = position_counts.get(pos, 0) + 1

        # Validate
        if position_counts[1] != 1:
            return False, "Must start exactly 1 goalkeeper"
        if position_counts[2] < self.constraints.MIN_STARTING_DEFENDERS:
            return False, f"Must start at least {self.constraints.MIN_STARTING_DEFENDERS} defenders"
        if position_counts[4] < self.constraints.MIN_STARTING_FORWARDS:
            return False, f"Must start at least {self.constraints.MIN_STARTING_FORWARDS} forward"

        return True, "Starting XI is valid"

    # ========================================================================
    # TRANSFER VALIDATION
    # ========================================================================

    def validate_transfer(
        self,
        current_team: List[Dict[str, Any]],
        player_out_id: int,
        player_in: Dict[str, Any],
        available_budget: int
    ) -> Tuple[bool, str]:
        """
        Validate a single transfer.

        Checks:
        - Player out is in current team
        - Player in is not already in team
        - Transfer maintains valid team constraints
        - Budget is sufficient
        """
        # Check player_out exists in team
        player_out = None
        for p in current_team:
            if p['id'] == player_out_id:
                player_out = p
                break

        if not player_out:
            return False, f"Player {player_out_id} is not in current team"

        # Check player_in not already in team
        for p in current_team:
            if p['id'] == player_in['id']:
                return False, f"Player {player_in['web_name']} is already in team"

        # Calculate new budget
        selling_price = player_out.get('selling_price', player_out.get('now_cost'))
        buying_price = player_in['now_cost']
        cost = buying_price - selling_price

        if cost > available_budget:
            return False, f"Insufficient budget. Need {cost/10:.1f}m, have {available_budget/10:.1f}m"

        # Check if transfer maintains position constraints
        if player_out['element_type'] != player_in['element_type']:
            # Different positions - validate new squad composition
            new_team = [p for p in current_team if p['id'] != player_out_id]
            new_team.append(player_in)
            is_valid, msg = self.validate_team(new_team)
            if not is_valid:
                return False, f"Transfer would violate team constraints: {msg}"

        # Check max 3 players per team
        player_in_team_id = player_in['team_id']
        same_team_count = sum(
            1 for p in current_team
            if p['team_id'] == player_in_team_id and p['id'] != player_out_id
        )
        if same_team_count >= self.constraints.MAX_PLAYERS_PER_TEAM:
            return False, f"Already have {self.constraints.MAX_PLAYERS_PER_TEAM} players from this team"

        return True, "Transfer is valid"

    def calculate_transfer_cost(
        self,
        num_transfers: int,
        free_transfers_available: int,
        is_wildcard: bool = False,
        is_free_hit: bool = False
    ) -> int:
        """Calculate points cost for transfers."""
        if is_wildcard or is_free_hit:
            return 0

        if num_transfers <= free_transfers_available:
            return 0

        extra_transfers = num_transfers - free_transfers_available
        return extra_transfers * self.transfer_rules.POINTS_HIT_PER_TRANSFER

    # ========================================================================
    # CHIP VALIDATION
    # ========================================================================

    def can_use_chip(
        self,
        chip_name: str,
        gameweek: int,
        chips_used: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """
        Validate if a chip can be used in this gameweek.

        2025/26 Rules:
        - TWO of each chip (one per half)
        - First half: GW1-19 (must use before GW19 deadline)
        - Second half: GW20-38
        """
        if chip_name not in self.transfer_rules.CHIPS:
            return False, f"Invalid chip: {chip_name}"

        # Determine which half we're in
        if gameweek <= self.transfer_rules.FIRST_HALF_DEADLINE_GW:
            chip_half = 1
        else:
            chip_half = 2

        # Check if this chip has been used in this half
        used_in_half = [
            c for c in chips_used
            if c['chip_name'] == chip_name and c['chip_half'] == chip_half
        ]

        if used_in_half:
            return False, f"{chip_name} already used in {'first' if chip_half == 1 else 'second'} half"

        # Wildcard/Free Hit specific rules
        if chip_name in ['wildcard', 'free_hit']:
            # Can't use if already used this half
            if used_in_half:
                return False, f"{chip_name} already used in {'first' if chip_half == 1 else 'second'} half"

        return True, f"{chip_name} can be used in GW{gameweek}"

    def validate_bench_boost(self, team: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Validate Bench Boost usage."""
        bench = [p for p in team if p.get('position', 0) > 11]

        if len(bench) != self.constraints.BENCH_PLAYERS:
            return False, f"Bench must have exactly {self.constraints.BENCH_PLAYERS} players"

        # All bench players should have reasonable chance of playing
        uncertain_players = [
            p for p in bench
            if p.get('chance_of_playing_next_round', 100) < 75
        ]

        if uncertain_players:
            return True, f"Warning: {len(uncertain_players)} bench players have <75% chance of playing"

        return True, "Bench Boost ready"

    def validate_triple_captain(self, captain_player: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate Triple Captain usage."""
        if captain_player.get('chance_of_playing_next_round', 100) < 100:
            return True, f"Warning: Captain has {captain_player.get('chance_of_playing_next_round')}% chance of playing"

        return True, "Triple Captain ready"

    # ========================================================================
    # PRICE CHANGE CALCULATIONS
    # ========================================================================

    def calculate_selling_price(self, purchase_price: int, current_price: int) -> int:
        """
        Calculate selling price with 50% sell-on fee.

        FPL Rule: You only get 50% of any price rises.
        """
        if current_price <= purchase_price:
            return current_price

        price_rise = current_price - purchase_price
        profit = price_rise // 2  # 50% of profit (rounded down)

        return purchase_price + profit

    # ========================================================================
    # POINTS CALCULATION
    # ========================================================================

    def calculate_gameweek_points(
        self,
        team: List[Dict[str, Any]],
        player_gameweek_stats: Dict[int, Dict[str, Any]]
    ) -> int:
        """
        Calculate total gameweek points including captain and bench.

        Returns total points for the gameweek.
        """
        total_points = 0

        # Process starting XI
        for player in team:
            if player.get('position', 16) > 11:
                continue  # Skip bench

            player_id = player['id']
            stats = player_gameweek_stats.get(player_id, {})

            points_breakdown = self.calculator.calculate_points(
                stats,
                player['element_type']
            )

            player_points = points_breakdown['total']

            # Apply captain multiplier
            if player.get('is_captain'):
                multiplier = player.get('multiplier', 2)  # 2x or 3x (Triple Captain)
                player_points *= multiplier

            total_points += player_points

        return total_points

    def get_automatic_subs(
        self,
        team: List[Dict[str, Any]],
        player_gameweek_stats: Dict[int, Dict[str, Any]]
    ) -> List[Tuple[int, int]]:
        """
        Calculate automatic substitutions.

        Returns list of (bench_player_id, starting_player_id) swaps.
        """
        # Get players who didn't play
        starting = sorted(
            [p for p in team if p.get('position', 16) <= 11],
            key=lambda x: x['position']
        )
        bench = sorted(
            [p for p in team if p.get('position', 16) > 11],
            key=lambda x: x['position']
        )

        non_players = [
            p for p in starting
            if player_gameweek_stats.get(p['id'], {}).get('minutes', 0) == 0
        ]

        if not non_players:
            return []

        # Auto-sub logic (simplified - actual FPL rules are complex)
        # Priority: First sub, then second, then third
        subs_made = []

        for bench_player in bench:
            if not non_players:
                break

            bench_stats = player_gameweek_stats.get(bench_player['id'], {})
            if bench_stats.get('minutes', 0) == 0:
                continue  # Bench player didn't play either

            # Find valid player to replace (same position or flexible)
            for non_player in non_players[:]:
                # Simplified: same position swap
                if bench_player['element_type'] == non_player['element_type']:
                    subs_made.append((bench_player['id'], non_player['id']))
                    non_players.remove(non_player)
                    break

        return subs_made
