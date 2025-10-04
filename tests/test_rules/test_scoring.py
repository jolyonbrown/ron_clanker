"""
Tests for FPL scoring rules.
"""

import pytest
from rules.scoring import PointsCalculator, validate_team_formation


class TestPointsCalculator:
    """Test points calculation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = PointsCalculator()

    def test_defender_goal_points(self):
        """Test defender scores correct points for goal."""
        stats = {
            'minutes': 90,
            'goals_scored': 1,
            'assists': 0,
            'clean_sheets': 0,
            'goals_conceded': 0
        }
        points = self.calculator.calculate_points(stats, position=2)  # Defender

        assert points['goals'] == 6  # DEF goal = 6 points
        assert points['minutes'] == 2
        assert points['total'] == 8

    def test_goalkeeper_goal_points(self):
        """Test goalkeeper scores correct points for goal (NEW 2025/26: 10 points)."""
        stats = {
            'minutes': 90,
            'goals_scored': 1,
            'assists': 0,
            'clean_sheets': 0,
            'goals_conceded': 0
        }
        points = self.calculator.calculate_points(stats, position=1)  # Goalkeeper

        assert points['goals'] == 10  # GK goal = 10 points (NEW rule)
        assert points['minutes'] == 2
        assert points['total'] == 12

    def test_midfielder_goal_points(self):
        """Test midfielder scores correct points for goal."""
        stats = {
            'minutes': 90,
            'goals_scored': 1,
            'assists': 0,
            'clean_sheets': 0
        }
        points = self.calculator.calculate_points(stats, position=3)  # Midfielder

        assert points['goals'] == 5  # MID goal = 5 points
        assert points['minutes'] == 2
        assert points['total'] == 7

    def test_defensive_contribution_defender(self):
        """Test NEW 2025/26 defensive contribution for defenders."""
        stats = {
            'minutes': 90,
            'tackles': 4,
            'interceptions': 3,
            'clearances_blocks_interceptions': 5,  # Total = 12, above threshold
            'goals_scored': 0,
            'assists': 0,
            'clean_sheets': 0,
            'goals_conceded': 0
        }
        points = self.calculator.calculate_points(stats, position=2)

        assert points['defensive_contribution'] == 2  # Hit 10+ threshold
        assert points['total'] == 4  # 2 for minutes + 2 for DC

    def test_defensive_contribution_midfielder(self):
        """Test NEW 2025/26 defensive contribution for midfielders."""
        stats = {
            'minutes': 90,
            'tackles': 5,
            'interceptions': 3,
            'clearances_blocks_interceptions': 3,
            'recoveries': 4,  # Total = 15, above 12 threshold
            'goals_scored': 0,
            'assists': 0,
            'clean_sheets': 0
        }
        points = self.calculator.calculate_points(stats, position=3)

        assert points['defensive_contribution'] == 2  # Hit 12+ threshold
        assert points['total'] == 4  # 2 for minutes + 2 for DC

    def test_clean_sheet_goalkeeper(self):
        """Test goalkeeper clean sheet points."""
        stats = {
            'minutes': 90,
            'clean_sheets': 1,
            'goals_conceded': 0,
            'saves': 6  # 2 save points
        }
        points = self.calculator.calculate_points(stats, position=1)  # GK

        assert points['clean_sheets'] == 4
        assert points['saves'] == 2  # 6 saves / 3 = 2 points
        assert points['total'] == 8  # 2 minutes + 4 CS + 2 saves

    def test_goals_conceded_penalty(self):
        """Test goalkeeper/defender loses points for goals conceded."""
        stats = {
            'minutes': 90,
            'goals_conceded': 3,  # -1 for every 2 = -1 point
            'clean_sheets': 0
        }
        points = self.calculator.calculate_points(stats, position=2)

        assert points['goals_conceded'] == -1
        assert points['total'] == 1  # 2 for minutes - 1 for conceding


class TestFormationValidation:
    """Test team formation validation."""

    def test_valid_343_formation(self):
        """Test valid 3-4-3 formation."""
        team = [
            # GK
            {'element_type': 1, 'position': 1},
            {'element_type': 1, 'position': 12},
            # DEF
            {'element_type': 2, 'position': 2},
            {'element_type': 2, 'position': 3},
            {'element_type': 2, 'position': 4},
            {'element_type': 2, 'position': 13},
            {'element_type': 2, 'position': 14},
            # MID
            {'element_type': 3, 'position': 5},
            {'element_type': 3, 'position': 6},
            {'element_type': 3, 'position': 7},
            {'element_type': 3, 'position': 8},
            {'element_type': 3, 'position': 15},
            # FWD
            {'element_type': 4, 'position': 9},
            {'element_type': 4, 'position': 10},
            {'element_type': 4, 'position': 11},
        ]

        is_valid, msg = validate_team_formation(team)
        assert is_valid
        assert msg == "Valid formation"

    def test_invalid_too_few_defenders(self):
        """Test invalid formation with too few defenders."""
        team = [
            {'element_type': 1, 'position': 1},
            {'element_type': 1, 'position': 12},
            # Only 2 defenders (need 3-5)
            {'element_type': 2, 'position': 2},
            {'element_type': 2, 'position': 3},
            # Too many midfielders
            {'element_type': 3, 'position': 4},
            {'element_type': 3, 'position': 5},
            {'element_type': 3, 'position': 6},
            {'element_type': 3, 'position': 7},
            {'element_type': 3, 'position': 8},
            {'element_type': 3, 'position': 13},
            {'element_type': 3, 'position': 14},
            {'element_type': 3, 'position': 15},
            # FWD
            {'element_type': 4, 'position': 9},
            {'element_type': 4, 'position': 10},
            {'element_type': 4, 'position': 11},
        ]

        is_valid, msg = validate_team_formation(team)
        assert not is_valid
        assert "3-5 defenders" in msg

    def test_invalid_wrong_team_size(self):
        """Test team with wrong number of players."""
        team = [
            {'element_type': 1, 'position': 1},
            {'element_type': 2, 'position': 2},
        ]

        is_valid, msg = validate_team_formation(team)
        assert not is_valid
        assert "exactly 15 players" in msg
