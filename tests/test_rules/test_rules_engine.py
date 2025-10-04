"""
Tests for Rules Engine.
"""

import pytest
from rules.rules_engine import RulesEngine


class TestRulesEngine:
    """Test FPL rules enforcement."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RulesEngine()

    def test_validate_budget_constraint(self):
        """Test team must be within budget."""
        # Team costing 101.0m (over budget) - properly formatted starting XI
        expensive_team = [
            {'id': 1, 'element_type': 1, 'now_cost': 50, 'team_id': 1, 'position': 1, 'is_captain': False, 'is_vice_captain': False},  # GK starting
            {'id': 2, 'element_type': 1, 'now_cost': 40, 'team_id': 2, 'position': 12, 'is_captain': False, 'is_vice_captain': False},  # GK bench
            {'id': 3, 'element_type': 2, 'now_cost': 80, 'team_id': 3, 'position': 2, 'is_captain': False, 'is_vice_captain': False},  # DEF
            {'id': 4, 'element_type': 2, 'now_cost': 70, 'team_id': 4, 'position': 3, 'is_captain': False, 'is_vice_captain': False},
            {'id': 5, 'element_type': 2, 'now_cost': 60, 'team_id': 5, 'position': 4, 'is_captain': False, 'is_vice_captain': False},
            {'id': 6, 'element_type': 2, 'now_cost': 50, 'team_id': 6, 'position': 13, 'is_captain': False, 'is_vice_captain': False},
            {'id': 7, 'element_type': 2, 'now_cost': 40, 'team_id': 7, 'position': 14, 'is_captain': False, 'is_vice_captain': False},
            {'id': 8, 'element_type': 3, 'now_cost': 120, 'team_id': 8, 'position': 5, 'is_captain': True, 'is_vice_captain': False},  # MID
            {'id': 9, 'element_type': 3, 'now_cost': 100, 'team_id': 9, 'position': 6, 'is_captain': False, 'is_vice_captain': True},
            {'id': 10, 'element_type': 3, 'now_cost': 80, 'team_id': 10, 'position': 7, 'is_captain': False, 'is_vice_captain': False},
            {'id': 11, 'element_type': 3, 'now_cost': 60, 'team_id': 1, 'position': 8, 'is_captain': False, 'is_vice_captain': False},
            {'id': 12, 'element_type': 3, 'now_cost': 40, 'team_id': 2, 'position': 15, 'is_captain': False, 'is_vice_captain': False},
            {'id': 13, 'element_type': 4, 'now_cost': 110, 'team_id': 3, 'position': 9, 'is_captain': False, 'is_vice_captain': False},  # FWD
            {'id': 14, 'element_type': 4, 'now_cost': 90, 'team_id': 4, 'position': 10, 'is_captain': False, 'is_vice_captain': False},
            {'id': 15, 'element_type': 4, 'now_cost': 70, 'team_id': 5, 'position': 11, 'is_captain': False, 'is_vice_captain': False},
        ]

        is_valid, msg = self.engine.validate_team(expensive_team)
        assert not is_valid
        assert "exceeds budget" in msg

    def test_validate_max_three_per_team(self):
        """Test cannot have more than 3 players from same team."""
        # 4 players from team 1 (too many)
        same_team = [
            {'id': 1, 'element_type': 1, 'now_cost': 50, 'team_id': 1, 'position': 1, 'is_captain': True, 'is_vice_captain': False},
            {'id': 2, 'element_type': 1, 'now_cost': 50, 'team_id': 2, 'position': 12, 'is_captain': False, 'is_vice_captain': True},
            {'id': 3, 'element_type': 2, 'now_cost': 50, 'team_id': 1, 'position': 2, 'is_captain': False, 'is_vice_captain': False},
            {'id': 4, 'element_type': 2, 'now_cost': 50, 'team_id': 1, 'position': 3, 'is_captain': False, 'is_vice_captain': False},
            {'id': 5, 'element_type': 2, 'now_cost': 50, 'team_id': 1, 'position': 4, 'is_captain': False, 'is_vice_captain': False},  # 4th from team 1
            {'id': 6, 'element_type': 2, 'now_cost': 50, 'team_id': 3, 'position': 13, 'is_captain': False, 'is_vice_captain': False},
            {'id': 7, 'element_type': 2, 'now_cost': 50, 'team_id': 4, 'position': 14, 'is_captain': False, 'is_vice_captain': False},
            {'id': 8, 'element_type': 3, 'now_cost': 50, 'team_id': 5, 'position': 5, 'is_captain': False, 'is_vice_captain': False},
            {'id': 9, 'element_type': 3, 'now_cost': 50, 'team_id': 6, 'position': 6, 'is_captain': False, 'is_vice_captain': False},
            {'id': 10, 'element_type': 3, 'now_cost': 50, 'team_id': 7, 'position': 7, 'is_captain': False, 'is_vice_captain': False},
            {'id': 11, 'element_type': 3, 'now_cost': 50, 'team_id': 8, 'position': 8, 'is_captain': False, 'is_vice_captain': False},
            {'id': 12, 'element_type': 3, 'now_cost': 50, 'team_id': 9, 'position': 15, 'is_captain': False, 'is_vice_captain': False},
            {'id': 13, 'element_type': 4, 'now_cost': 50, 'team_id': 10, 'position': 9, 'is_captain': False, 'is_vice_captain': False},
            {'id': 14, 'element_type': 4, 'now_cost': 50, 'team_id': 2, 'position': 10, 'is_captain': False, 'is_vice_captain': False},
            {'id': 15, 'element_type': 4, 'now_cost': 50, 'team_id': 3, 'position': 11, 'is_captain': False, 'is_vice_captain': False},
        ]

        is_valid, msg = self.engine.validate_team(same_team)
        assert not is_valid
        assert "more than 3 players from same team" in msg

    def test_validate_captain_required(self):
        """Test team must have exactly 1 captain."""
        team = [
            {'id': 1, 'element_type': 1, 'now_cost': 50, 'team_id': 1, 'position': 1, 'is_captain': False, 'is_vice_captain': False},
            {'id': 2, 'element_type': 1, 'now_cost': 50, 'team_id': 2, 'position': 12, 'is_captain': False, 'is_vice_captain': False},
            {'id': 3, 'element_type': 2, 'now_cost': 50, 'team_id': 3, 'position': 2, 'is_captain': False, 'is_vice_captain': False},
            {'id': 4, 'element_type': 2, 'now_cost': 50, 'team_id': 4, 'position': 3, 'is_captain': False, 'is_vice_captain': False},
            {'id': 5, 'element_type': 2, 'now_cost': 50, 'team_id': 5, 'position': 4, 'is_captain': False, 'is_vice_captain': False},
            {'id': 6, 'element_type': 2, 'now_cost': 50, 'team_id': 6, 'position': 13, 'is_captain': False, 'is_vice_captain': False},
            {'id': 7, 'element_type': 2, 'now_cost': 50, 'team_id': 7, 'position': 14, 'is_captain': False, 'is_vice_captain': False},
            {'id': 8, 'element_type': 3, 'now_cost': 50, 'team_id': 8, 'position': 5, 'is_captain': False, 'is_vice_captain': False},
            {'id': 9, 'element_type': 3, 'now_cost': 50, 'team_id': 9, 'position': 6, 'is_captain': False, 'is_vice_captain': False},
            {'id': 10, 'element_type': 3, 'now_cost': 50, 'team_id': 10, 'position': 7, 'is_captain': False, 'is_vice_captain': False},
            {'id': 11, 'element_type': 3, 'now_cost': 50, 'team_id': 1, 'position': 8, 'is_captain': False, 'is_vice_captain': False},
            {'id': 12, 'element_type': 3, 'now_cost': 50, 'team_id': 2, 'position': 15, 'is_captain': False, 'is_vice_captain': False},
            {'id': 13, 'element_type': 4, 'now_cost': 50, 'team_id': 3, 'position': 9, 'is_captain': False, 'is_vice_captain': False},
            {'id': 14, 'element_type': 4, 'now_cost': 50, 'team_id': 4, 'position': 10, 'is_captain': False, 'is_vice_captain': False},
            {'id': 15, 'element_type': 4, 'now_cost': 50, 'team_id': 5, 'position': 11, 'is_captain': False, 'is_vice_captain': False},
        ]

        # No captain
        is_valid, msg = self.engine.validate_team(team)
        assert not is_valid
        assert "captain" in msg.lower()

    def test_calculate_transfer_cost(self):
        """Test transfer cost calculation."""
        # 1 transfer with 1 FT = free
        cost = self.engine.calculate_transfer_cost(1, 1)
        assert cost == 0

        # 2 transfers with 1 FT = -4
        cost = self.engine.calculate_transfer_cost(2, 1)
        assert cost == 4

        # 3 transfers with 2 FT = -4
        cost = self.engine.calculate_transfer_cost(3, 2)
        assert cost == 4

        # Wildcard active = free
        cost = self.engine.calculate_transfer_cost(10, 0, is_wildcard=True)
        assert cost == 0

    def test_can_use_chip_first_half(self):
        """Test chip usage in first half of season."""
        chips_used = []

        # Can use wildcard in GW1
        can_use, msg = self.engine.can_use_chip('wildcard', 1, chips_used)
        assert can_use

        # Cannot use if already used in first half
        chips_used.append({
            'chip_name': 'wildcard',
            'chip_half': 1,
            'gameweek': 5
        })

        can_use, msg = self.engine.can_use_chip('wildcard', 10, chips_used)
        assert not can_use
        assert "already used" in msg

    def test_can_use_chip_second_half(self):
        """Test chip usage in second half of season."""
        # Used wildcard in first half
        chips_used = [{
            'chip_name': 'wildcard',
            'chip_half': 1,
            'gameweek': 5
        }]

        # Can use wildcard again in second half (GW20+)
        can_use, msg = self.engine.can_use_chip('wildcard', 25, chips_used)
        assert can_use

    def test_calculate_selling_price(self):
        """Test selling price with 50% profit rule."""
        # No profit - sell at current price
        selling = self.engine.calculate_selling_price(
            purchase_price=60,
            current_price=60
        )
        assert selling == 60

        # Price dropped - sell at current (lower) price
        selling = self.engine.calculate_selling_price(
            purchase_price=60,
            current_price=55
        )
        assert selling == 55

        # Price rose 0.2m - get 0.1m profit (50%)
        selling = self.engine.calculate_selling_price(
            purchase_price=60,
            current_price=62
        )
        assert selling == 61  # 60 + (2 // 2)

        # Price rose 0.3m - get 0.1m profit (rounded down)
        selling = self.engine.calculate_selling_price(
            purchase_price=60,
            current_price=63
        )
        assert selling == 61  # 60 + (3 // 2)

    def _create_valid_base_team(self):
        """Create a valid base team for testing."""
        team = [
            {'id': i, 'element_type': pos, 'now_cost': 50, 'team_id': i % 10, 'position': i+1}
            for i, pos in enumerate([1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4])
        ]
        return team
