"""
Rules Engine Agent - The Rulebook

Understands and enforces all FPL rules for team selection and validation.
Phase 1: Core validation for GW8 squad building.

2025/26 FPL Rules Summary:
- Squad: 15 players (2 GK, 5 DEF, 5 MID, 3 FWD)
- Budget: £100m for new team
- Max 3 players from same team
- Starting XI: Must field 11 players in valid formation
- Formations: Must have 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Represents a rule validation error."""
    rule: str
    message: str
    severity: str = "error"  # error, warning


class RulesEngine:
    """
    FPL Rules Engine

    Validates team selections against official FPL rules.
    """

    # Squad composition rules
    SQUAD_SIZE = 15
    SQUAD_COMPOSITION = {
        1: 2,  # Goalkeepers
        2: 5,  # Defenders
        3: 5,  # Midfielders
        4: 3,  # Forwards
    }

    # Budget rules
    NEW_TEAM_BUDGET = 1000  # £100.0m (stored as 100.0 * 10)

    # Team rules
    MAX_PLAYERS_PER_TEAM = 3

    # Formation rules
    STARTING_XI_SIZE = 11
    VALID_FORMATIONS = {
        # (DEF, MID, FWD) - GK is always 1
        (3, 4, 3), (3, 5, 2), (3, 2, 5),
        (4, 3, 3), (4, 4, 2), (4, 5, 1), (4, 2, 4),
        (5, 3, 2), (5, 4, 1), (5, 2, 3),
    }

    # Defensive Contribution scoring (2025/26 new rules)
    DC_DEFENDER_THRESHOLD = 5  # 1 pt per 5 CBI+T
    DC_MIDFIELDER_THRESHOLD = 6  # 1 pt per 6 CBI+T+R

    # Base points system
    POINTS_PLAYING_0_60 = 1
    POINTS_PLAYING_60_PLUS = 2
    POINTS_GOAL_GK_DEF = 6
    POINTS_GOAL_MID = 5
    POINTS_GOAL_FWD = 4
    POINTS_ASSIST = 3
    POINTS_CLEAN_SHEET_GK_DEF = 4
    POINTS_CLEAN_SHEET_MID = 1
    POINTS_GOAL_CONCEDED = -1  # Per 2 goals (GK/DEF only)
    POINTS_PENALTY_SAVE = 5
    POINTS_PENALTY_MISS = -2
    POINTS_YELLOW_CARD = -1
    POINTS_RED_CARD = -3
    POINTS_OWN_GOAL = -2
    POINTS_SAVES = 1  # Per 3 saves (GK only)

    def __init__(self):
        """Initialize Rules Engine."""
        pass

    # ========================================================================
    # SQUAD VALIDATION
    # ========================================================================

    def validate_squad(
        self,
        players: List[Dict[str, Any]],
        budget: int = NEW_TEAM_BUDGET
    ) -> Tuple[bool, List[ValidationError]]:
        """
        Validate a complete squad of 15 players.

        Args:
            players: List of player dicts (must include: id, element_type, team, now_cost)
            budget: Available budget in tenths (1000 = £100.0m)

        Returns:
            (is_valid, list of errors)
        """
        errors = []

        # Check squad size
        if len(players) != self.SQUAD_SIZE:
            errors.append(ValidationError(
                rule="squad_size",
                message=f"Squad must have exactly {self.SQUAD_SIZE} players (has {len(players)})"
            ))

        # Check position composition
        position_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for player in players:
            pos = player.get('element_type')
            if pos in position_counts:
                position_counts[pos] += 1

        for position, required in self.SQUAD_COMPOSITION.items():
            actual = position_counts.get(position, 0)
            if actual != required:
                pos_name = self._position_name(position)
                errors.append(ValidationError(
                    rule="position_composition",
                    message=f"Must have {required} {pos_name} (has {actual})"
                ))

        # Check budget
        total_cost = sum(p.get('now_cost', 0) for p in players)
        if total_cost > budget:
            errors.append(ValidationError(
                rule="budget",
                message=f"Squad cost £{total_cost/10:.1f}m exceeds budget £{budget/10:.1f}m"
            ))

        # Check max players per team
        team_counts = {}
        for player in players:
            team = player.get('team')
            team_counts[team] = team_counts.get(team, 0) + 1

        for team, count in team_counts.items():
            if count > self.MAX_PLAYERS_PER_TEAM:
                errors.append(ValidationError(
                    rule="team_limit",
                    message=f"Max {self.MAX_PLAYERS_PER_TEAM} players from team {team} (has {count})"
                ))

        # Check for duplicate players
        player_ids = [p.get('id') for p in players]
        if len(player_ids) != len(set(player_ids)):
            errors.append(ValidationError(
                rule="duplicates",
                message="Squad contains duplicate players"
            ))

        return (len(errors) == 0, errors)

    def validate_starting_xi(
        self,
        players: List[Dict[str, Any]],
        formation: Tuple[int, int, int] = None
    ) -> Tuple[bool, List[ValidationError]]:
        """
        Validate a starting XI selection.

        Args:
            players: List of 11 player dicts
            formation: Optional (DEF, MID, FWD) tuple to validate

        Returns:
            (is_valid, list of errors)
        """
        errors = []

        # Check starting XI size
        if len(players) != self.STARTING_XI_SIZE:
            errors.append(ValidationError(
                rule="starting_xi_size",
                message=f"Starting XI must have exactly {self.STARTING_XI_SIZE} players (has {len(players)})"
            ))
            return (False, errors)

        # Count positions
        position_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for player in players:
            pos = player.get('element_type')
            if pos in position_counts:
                position_counts[pos] += 1

        # Must have exactly 1 GK
        if position_counts[1] != 1:
            errors.append(ValidationError(
                rule="formation_gk",
                message=f"Starting XI must have exactly 1 GK (has {position_counts[1]})"
            ))

        # Check formation validity
        formation_actual = (position_counts[2], position_counts[3], position_counts[4])

        if formation_actual not in self.VALID_FORMATIONS:
            errors.append(ValidationError(
                rule="formation_invalid",
                message=f"Formation {formation_actual[0]}-{formation_actual[1]}-{formation_actual[2]} is not valid"
            ))

        # If specific formation requested, validate it matches
        if formation and formation != formation_actual:
            errors.append(ValidationError(
                rule="formation_mismatch",
                message=f"Requested formation {formation} doesn't match actual {formation_actual}"
            ))

        return (len(errors) == 0, errors)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _position_name(self, position: int) -> str:
        """Convert position code to name."""
        names = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
        return names.get(position, f"Position {position}")

    def calculate_squad_cost(self, players: List[Dict[str, Any]]) -> float:
        """Calculate total squad cost in £m."""
        total = sum(p.get('now_cost', 0) for p in players)
        return total / 10

    def get_budget_remaining(
        self,
        players: List[Dict[str, Any]],
        budget: int = NEW_TEAM_BUDGET
    ) -> float:
        """Get remaining budget in £m."""
        total_cost = sum(p.get('now_cost', 0) for p in players)
        return (budget - total_cost) / 10

    def is_formation_valid(self, defenders: int, midfielders: int, forwards: int) -> bool:
        """Check if a formation is valid."""
        return (defenders, midfielders, forwards) in self.VALID_FORMATIONS

    def get_valid_formations(self) -> List[Tuple[int, int, int]]:
        """Return all valid formations."""
        return sorted(list(self.VALID_FORMATIONS))

    # ========================================================================
    # POINTS CALCULATION (2025/26 Rules)
    # ========================================================================

    def calculate_base_points(
        self,
        player: Dict[str, Any],
        gameweek_stats: Dict[str, Any]
    ) -> int:
        """
        Calculate points for a player based on gameweek performance.

        Args:
            player: Player dict with element_type
            gameweek_stats: Dict with performance stats (goals, assists, minutes, etc.)

        Returns:
            Total points earned
        """
        points = 0
        position = player.get('element_type')

        # Appearance points
        minutes = gameweek_stats.get('minutes', 0)
        if minutes > 0:
            if minutes >= 60:
                points += self.POINTS_PLAYING_60_PLUS
            else:
                points += self.POINTS_PLAYING_0_60

        # Goals
        goals = gameweek_stats.get('goals_scored', 0)
        if goals > 0:
            if position in [1, 2]:  # GK or DEF
                points += goals * self.POINTS_GOAL_GK_DEF
            elif position == 3:  # MID
                points += goals * self.POINTS_GOAL_MID
            elif position == 4:  # FWD
                points += goals * self.POINTS_GOAL_FWD

        # Assists
        assists = gameweek_stats.get('assists', 0)
        points += assists * self.POINTS_ASSIST

        # Clean sheets
        clean_sheets = gameweek_stats.get('clean_sheets', 0)
        if clean_sheets > 0:
            if position in [1, 2]:  # GK or DEF
                points += clean_sheets * self.POINTS_CLEAN_SHEET_GK_DEF
            elif position == 3:  # MID
                points += clean_sheets * self.POINTS_CLEAN_SHEET_MID

        # Goals conceded (GK and DEF only, -1 per 2 conceded)
        if position in [1, 2]:
            goals_conceded = gameweek_stats.get('goals_conceded', 0)
            points += (goals_conceded // 2) * self.POINTS_GOAL_CONCEDED

        # Saves (GK only, 1 pt per 3 saves)
        if position == 1:
            saves = gameweek_stats.get('saves', 0)
            points += (saves // 3) * self.POINTS_SAVES

        # Penalty saves
        penalty_saves = gameweek_stats.get('penalties_saved', 0)
        points += penalty_saves * self.POINTS_PENALTY_SAVE

        # Penalty misses
        penalty_misses = gameweek_stats.get('penalties_missed', 0)
        points += penalty_misses * self.POINTS_PENALTY_MISS

        # Cards
        yellow_cards = gameweek_stats.get('yellow_cards', 0)
        points += yellow_cards * self.POINTS_YELLOW_CARD

        red_cards = gameweek_stats.get('red_cards', 0)
        points += red_cards * self.POINTS_RED_CARD

        # Own goals
        own_goals = gameweek_stats.get('own_goals', 0)
        points += own_goals * self.POINTS_OWN_GOAL

        # Defensive Contribution (NEW 2025/26)
        dc_points = self.calculate_defensive_contribution_points(position, gameweek_stats)
        points += dc_points

        return points

    def calculate_defensive_contribution_points(
        self,
        position: int,
        stats: Dict[str, Any]
    ) -> int:
        """
        Calculate Defensive Contribution points (NEW 2025/26 rules).

        Defenders: 1 pt per 5 combined blocks + interceptions + tackles
        Midfielders: 1 pt per 6 combined blocks + interceptions + tackles + recoveries

        Args:
            position: Player position (1=GK, 2=DEF, 3=MID, 4=FWD)
            stats: Dict with defensive stats

        Returns:
            DC points earned
        """
        if position == 2:  # Defender
            cbi_tackles = (
                stats.get('clearances_blocks_interceptions', 0) +
                stats.get('tackles', 0)
            )
            return cbi_tackles // self.DC_DEFENDER_THRESHOLD

        elif position == 3:  # Midfielder
            cbi_tackles_recoveries = (
                stats.get('clearances_blocks_interceptions', 0) +
                stats.get('tackles', 0) +
                stats.get('recoveries', 0)
            )
            return cbi_tackles_recoveries // self.DC_MIDFIELDER_THRESHOLD

        return 0  # GK and FWD don't get DC points

    # ========================================================================
    # TRANSFER RULES
    # ========================================================================

    def validate_transfer(
        self,
        player_out: Dict[str, Any],
        player_in: Dict[str, Any],
        current_squad: List[Dict[str, Any]],
        budget_available: float
    ) -> Tuple[bool, List[ValidationError]]:
        """
        Validate a proposed transfer.

        Args:
            player_out: Player being transferred out
            player_in: Player being transferred in
            current_squad: Current 15-player squad
            budget_available: Available budget for transfer (£m)

        Returns:
            (is_valid, list of errors)
        """
        errors = []

        # Check player_out is in squad
        if player_out['id'] not in [p['id'] for p in current_squad]:
            errors.append(ValidationError(
                rule="transfer_out_not_in_squad",
                message=f"Player {player_out.get('web_name')} is not in current squad"
            ))

        # Check player_in not already in squad
        if player_in['id'] in [p['id'] for p in current_squad]:
            errors.append(ValidationError(
                rule="transfer_in_already_in_squad",
                message=f"Player {player_in.get('web_name')} is already in squad"
            ))

        # Check positions match
        if player_out.get('element_type') != player_in.get('element_type'):
            errors.append(ValidationError(
                rule="transfer_position_mismatch",
                message=f"Must replace {self._position_name(player_out['element_type'])} with {self._position_name(player_in['element_type'])}"
            ))

        # Check budget
        cost_in = player_in.get('now_cost', 0) / 10
        if cost_in > budget_available:
            errors.append(ValidationError(
                rule="transfer_budget_exceeded",
                message=f"Transfer cost £{cost_in}m exceeds available budget £{budget_available}m"
            ))

        # Check max players from same team after transfer
        new_squad = [p for p in current_squad if p['id'] != player_out['id']]
        new_squad.append(player_in)

        team_counts = {}
        for player in new_squad:
            team = player.get('team')
            team_counts[team] = team_counts.get(team, 0) + 1

        for team, count in team_counts.items():
            if count > self.MAX_PLAYERS_PER_TEAM:
                errors.append(ValidationError(
                    rule="team_limit",
                    message=f"Transfer would exceed max {self.MAX_PLAYERS_PER_TEAM} players from team {team}"
                ))

        return (len(errors) == 0, errors)
