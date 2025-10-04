"""
FPL 2025/26 Scoring Rules

Implements the official FPL scoring system including the new
Defensive Contribution rules.
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ScoringRules:
    """FPL 2025/26 scoring rules by position."""

    # Minutes played
    MINUTES_0_59 = 0
    MINUTES_60_PLUS = 2
    MINUTES_1_59_GK_DEF = 1  # GK/DEF get 1 point for any minutes up to 60

    # Goals scored
    GOAL_GK = 10
    GOAL_DEF = 6
    GOAL_MID = 5
    GOAL_FWD = 4

    # Assists
    ASSIST = 3

    # Clean sheets (60+ minutes)
    CLEAN_SHEET_GK_DEF = 4
    CLEAN_SHEET_MID = 1
    CLEAN_SHEET_FWD = 0

    # Goals conceded (per 2 goals, GK/DEF only)
    GOALS_CONCEDED_PENALTY = -1

    # Penalties
    PENALTY_SAVED = 5
    PENALTY_MISSED = -2

    # Cards
    YELLOW_CARD = -1
    RED_CARD = -3

    # Saves (GK only, per 3 saves)
    SAVES_BONUS = 1

    # Own goals
    OWN_GOAL = -2

    # Bonus points (BPS system)
    # Awarded to top 3 players in each match

    # NEW 2025/26: DEFENSIVE CONTRIBUTION
    # Defenders: 10+ combined Tackles + Interceptions + Clearances/Blocks
    DEF_CONTRIBUTION_THRESHOLD = 10
    DEF_CONTRIBUTION_POINTS = 2

    # Midfielders: 12+ combined Tackles + Interceptions + Clearances/Blocks + Recoveries
    MID_CONTRIBUTION_THRESHOLD = 12
    MID_CONTRIBUTION_POINTS = 2


class PointsCalculator:
    """Calculate FPL points based on player stats."""

    def __init__(self):
        self.rules = ScoringRules()

    def calculate_points(
        self,
        stats: Dict[str, Any],
        position: int  # 1=GK, 2=DEF, 3=MID, 4=FWD
    ) -> Dict[str, int]:
        """
        Calculate total points for a player's performance.

        Returns breakdown of points by category.
        """
        points = {
            'minutes': 0,
            'goals': 0,
            'assists': 0,
            'clean_sheets': 0,
            'goals_conceded': 0,
            'saves': 0,
            'penalties_saved': 0,
            'penalties_missed': 0,
            'yellow_cards': 0,
            'red_cards': 0,
            'own_goals': 0,
            'bonus': 0,
            'defensive_contribution': 0,  # NEW
            'total': 0
        }

        minutes = stats.get('minutes', 0)

        # Minutes points
        if position in [1, 2]:  # GK or DEF
            if minutes > 0 and minutes < 60:
                points['minutes'] = self.rules.MINUTES_1_59_GK_DEF
            elif minutes >= 60:
                points['minutes'] = self.rules.MINUTES_60_PLUS
        else:  # MID or FWD
            if minutes >= 60:
                points['minutes'] = self.rules.MINUTES_60_PLUS

        # Goals
        goals = stats.get('goals_scored', 0)
        if position == 1:
            points['goals'] = goals * self.rules.GOAL_GK
        elif position == 2:
            points['goals'] = goals * self.rules.GOAL_DEF
        elif position == 3:
            points['goals'] = goals * self.rules.GOAL_MID
        else:
            points['goals'] = goals * self.rules.GOAL_FWD

        # Assists
        points['assists'] = stats.get('assists', 0) * self.rules.ASSIST

        # Clean sheets (60+ minutes only)
        if minutes >= 60 and stats.get('clean_sheets', 0) > 0:
            if position in [1, 2]:
                points['clean_sheets'] = self.rules.CLEAN_SHEET_GK_DEF
            elif position == 3:
                points['clean_sheets'] = self.rules.CLEAN_SHEET_MID

        # Goals conceded (GK/DEF only, -1 per 2 goals)
        if position in [1, 2]:
            goals_conceded = stats.get('goals_conceded', 0)
            points['goals_conceded'] = (goals_conceded // 2) * self.rules.GOALS_CONCEDED_PENALTY

        # Saves (GK only, +1 per 3 saves)
        if position == 1:
            saves = stats.get('saves', 0)
            points['saves'] = (saves // 3) * self.rules.SAVES_BONUS

        # Penalties
        points['penalties_saved'] = stats.get('penalties_saved', 0) * self.rules.PENALTY_SAVED
        points['penalties_missed'] = stats.get('penalties_missed', 0) * self.rules.PENALTY_MISSED

        # Cards
        points['yellow_cards'] = stats.get('yellow_cards', 0) * self.rules.YELLOW_CARD
        points['red_cards'] = stats.get('red_cards', 0) * self.rules.RED_CARD

        # Own goals
        points['own_goals'] = stats.get('own_goals', 0) * self.rules.OWN_GOAL

        # Bonus
        points['bonus'] = stats.get('bonus', 0)

        # NEW 2025/26: Defensive Contribution
        if position == 2:  # Defenders
            tackles = stats.get('tackles', 0)
            interceptions = stats.get('interceptions', 0)
            cbi = stats.get('clearances_blocks_interceptions', 0)
            total_defensive = tackles + interceptions + cbi

            if total_defensive >= self.rules.DEF_CONTRIBUTION_THRESHOLD:
                points['defensive_contribution'] = self.rules.DEF_CONTRIBUTION_POINTS

        elif position == 3:  # Midfielders
            tackles = stats.get('tackles', 0)
            interceptions = stats.get('interceptions', 0)
            cbi = stats.get('clearances_blocks_interceptions', 0)
            recoveries = stats.get('recoveries', 0)
            total_defensive = tackles + interceptions + cbi + recoveries

            if total_defensive >= self.rules.MID_CONTRIBUTION_THRESHOLD:
                points['defensive_contribution'] = self.rules.MID_CONTRIBUTION_POINTS

        # Calculate total
        points['total'] = sum(points.values())

        return points

    def calculate_expected_points(
        self,
        player_stats: Dict[str, Any],
        position: int,
        fixture_difficulty: int = 3,
        minutes_probability: float = 1.0
    ) -> float:
        """
        Calculate expected points for a player in upcoming fixture.

        Uses historical averages weighted by fixture difficulty.
        """
        # Get per-90 stats
        total_minutes = player_stats.get('minutes', 1)
        if total_minutes == 0:
            return 0.0

        # Calculate per-90 rates
        per_90 = {}
        for stat in ['goals_scored', 'assists', 'clean_sheets', 'tackles',
                     'interceptions', 'clearances_blocks_interceptions', 'recoveries']:
            total_stat = player_stats.get(stat, 0)
            per_90[stat] = (total_stat / total_minutes) * 90

        # Adjust for fixture difficulty (1=easiest, 5=hardest)
        difficulty_multiplier = {
            1: 1.3,
            2: 1.15,
            3: 1.0,
            4: 0.85,
            5: 0.7
        }.get(fixture_difficulty, 1.0)

        # Expected stats for this match
        expected_stats = {
            'minutes': 90 * minutes_probability,
            'goals_scored': per_90['goals_scored'] * difficulty_multiplier,
            'assists': per_90['assists'] * difficulty_multiplier,
            'clean_sheets': per_90['clean_sheets'] * difficulty_multiplier,
            'tackles': per_90['tackles'],
            'interceptions': per_90['interceptions'],
            'clearances_blocks_interceptions': per_90['clearances_blocks_interceptions'],
            'recoveries': per_90['recoveries'],
            'bonus': player_stats.get('bonus', 0) / max(player_stats.get('appearances', 1), 1)
        }

        # For defensive contribution, use probability-based calculation
        if position == 2:
            # Probability defender hits 10+ defensive actions
            avg_defensive = (expected_stats['tackles'] +
                           expected_stats['interceptions'] +
                           expected_stats['clearances_blocks_interceptions'])
            # Simplified: if average is above threshold, high probability
            if avg_defensive >= self.rules.DEF_CONTRIBUTION_THRESHOLD:
                expected_stats['defensive_contribution'] = 2 * 0.8  # 80% chance
            else:
                expected_stats['defensive_contribution'] = 2 * 0.3  # 30% chance

        elif position == 3:
            avg_defensive = (expected_stats['tackles'] +
                           expected_stats['interceptions'] +
                           expected_stats['clearances_blocks_interceptions'] +
                           expected_stats['recoveries'])
            if avg_defensive >= self.rules.MID_CONTRIBUTION_THRESHOLD:
                expected_stats['defensive_contribution'] = 2 * 0.7
            else:
                expected_stats['defensive_contribution'] = 2 * 0.2

        # Calculate points (treating fractional stats as probabilities)
        points_breakdown = self.calculate_points(expected_stats, position)

        # Weighted by minutes probability
        return points_breakdown['total'] * minutes_probability


def validate_team_formation(team: list) -> tuple[bool, str]:
    """
    Validate that a team meets FPL formation requirements.

    Returns: (is_valid, error_message)
    """
    if len(team) != 15:
        return False, f"Team must have exactly 15 players, has {len(team)}"

    # Count by position
    position_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    starting_positions = {1: 0, 2: 0, 3: 0, 4: 0}

    for player in team:
        pos = player.get('element_type')
        position_counts[pos] = position_counts.get(pos, 0) + 1

        if player.get('position', 16) <= 11:  # Starting XI
            starting_positions[pos] = starting_positions.get(pos, 0) + 1

    # Squad requirements
    if position_counts[1] != 2:
        return False, "Must have exactly 2 goalkeepers"
    if position_counts[2] < 3 or position_counts[2] > 5:
        return False, "Must have 3-5 defenders"
    if position_counts[3] < 2 or position_counts[3] > 5:
        return False, "Must have 2-5 midfielders"
    if position_counts[4] < 1 or position_counts[4] > 3:
        return False, "Must have 1-3 forwards"

    # Starting XI requirements
    if starting_positions[1] != 1:
        return False, "Must have exactly 1 goalkeeper in starting XI"
    if starting_positions[2] < 3:
        return False, "Must have at least 3 defenders in starting XI"
    if starting_positions[4] < 1:
        return False, "Must have at least 1 forward in starting XI"
    if sum(starting_positions.values()) != 11:
        return False, "Starting XI must have exactly 11 players"

    return True, "Valid formation"
