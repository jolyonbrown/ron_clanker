"""Tests for FreeTransferTracker special events handling."""

import pytest
from unittest.mock import patch, MagicMock

from services.free_transfer_tracker import FreeTransferTracker


class TestSpecialEventsFTTopup:
    """Test FT top-up logic for special events like AFCON."""

    @pytest.fixture
    def mock_special_events(self):
        """AFCON-style FT top-up config."""
        return {
            'season': '2025/26',
            'ft_topups': [
                {
                    'name': 'AFCON 2025/26',
                    'trigger_after_gw': 15,
                    'effective_from_gw': 16,
                    'topup_to': 5,
                    'carry_over': True,
                }
            ]
        }

    @pytest.fixture
    def tracker_with_afcon(self, mock_special_events):
        """Tracker with AFCON config loaded."""
        with patch.object(FreeTransferTracker, '_load_special_events', return_value=mock_special_events):
            return FreeTransferTracker()

    @pytest.fixture
    def tracker_no_events(self):
        """Tracker with no special events."""
        with patch.object(FreeTransferTracker, '_load_special_events', return_value={}):
            return FreeTransferTracker()

    def test_get_ft_topup_before_trigger(self, tracker_with_afcon):
        """Before trigger GW, no top-up applies."""
        assert tracker_with_afcon.get_ft_topup_for_gw(15) is None

    def test_get_ft_topup_at_effective_gw(self, tracker_with_afcon):
        """At effective GW, top-up applies."""
        topup = tracker_with_afcon.get_ft_topup_for_gw(16)
        assert topup is not None
        assert topup['name'] == 'AFCON 2025/26'
        assert topup['topup_to'] == 5

    def test_get_ft_topup_after_effective_gw(self, tracker_with_afcon):
        """After effective GW, top-up still applies (carry over)."""
        topup = tracker_with_afcon.get_ft_topup_for_gw(20)
        assert topup is not None

    def test_calculate_ft_with_topup(self, tracker_with_afcon):
        """FT calculation applies top-up after trigger GW."""
        # History: manager used 1 FT each week through GW15
        history = {
            'current': [
                {'event': i, 'event_transfers': 1}
                for i in range(1, 16)
            ]
        }

        result = tracker_with_afcon._calculate_free_transfers(history, target_gw=16)

        # Should have 5 FTs due to AFCON top-up
        assert result['free_transfers'] == 5
        assert result['special_event'] == 'AFCON 2025/26'
        assert 'top-up' in result['calculation']

    def test_calculate_ft_without_special_events(self, tracker_no_events):
        """Normal FT calculation without special events."""
        history = {
            'current': [
                {'event': i, 'event_transfers': 1}
                for i in range(1, 16)
            ]
        }

        result = tracker_no_events._calculate_free_transfers(history, target_gw=16)

        # Normal calculation: used 1 each week (all available), so 0 banked, +1 = 1 FT
        assert result['free_transfers'] == 1
        assert result['special_event'] is None

    def test_topup_doesnt_reduce_existing_fts(self, tracker_with_afcon):
        """Top-up should not reduce FTs if manager already has more."""
        # Manager banked heavily - already has 5 FTs
        history = {
            'current': [
                {'event': i, 'event_transfers': 0}
                for i in range(1, 16)
            ]
        }

        result = tracker_with_afcon._calculate_free_transfers(history, target_gw=16)

        # Should still have 5 (max), not reduced
        assert result['free_transfers'] == 5

    def test_new_team_no_history(self, tracker_with_afcon):
        """New team with no history gets 1 FT."""
        history = {'current': []}

        result = tracker_with_afcon._calculate_free_transfers(history, target_gw=16)

        assert result['free_transfers'] == 1
        assert result['special_event'] is None


class TestRulesEngineSpecialEvents:
    """Test RulesEngine special events integration."""

    def test_rules_engine_loads_special_events(self):
        """RulesEngine loads special events from config."""
        from rules.rules_engine import RulesEngine

        engine = RulesEngine()
        # Should have special_events attribute
        assert hasattr(engine, 'special_events')

    def test_get_ft_topups(self):
        """RulesEngine exposes FT top-ups."""
        from rules.rules_engine import RulesEngine

        engine = RulesEngine()
        topups = engine.get_ft_topups()

        # Should be a list (may be empty if no config)
        assert isinstance(topups, list)

    def test_get_ft_topup_for_gw(self):
        """RulesEngine can check top-up for specific GW."""
        from rules.rules_engine import RulesEngine

        engine = RulesEngine()
        # GW16 should have AFCON top-up (if config exists)
        topup = engine.get_ft_topup_for_gw(16)

        # Either None or valid top-up dict
        if topup:
            assert 'name' in topup
            assert 'topup_to' in topup
