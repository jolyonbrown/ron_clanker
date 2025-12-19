"""
Free Transfer Tracker Service

Fetches and calculates available free transfers from FPL API.
Uses the entry history endpoint to track transfer usage per gameweek.
Supports special events (e.g., AFCON) via config/special_events.yaml.

Usage:
    from services.free_transfer_tracker import FreeTransferTracker

    tracker = FreeTransferTracker()
    result = tracker.get_available_free_transfers(team_id=12222054)
    print(f"Free transfers: {result['free_transfers']}")
"""

import logging
import requests
from pathlib import Path
from typing import Dict, Optional, List

import yaml

logger = logging.getLogger(__name__)

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
MAX_BANKED_TRANSFERS = 5
CONFIG_DIR = Path(__file__).parent.parent / "config"


class FreeTransferTracker:
    """
    Calculates available free transfers from FPL API history data.

    FPL Rules:
    - 1 free transfer per gameweek (accumulates after each deadline)
    - Max 5 banked free transfers (1 new + 4 max extra)
    - Wildcard/Free Hit doesn't consume normal FTs
    - Special events (e.g., AFCON) may grant additional FTs via config
    """

    def __init__(self):
        self._cache = {}
        self._special_events = self._load_special_events()

    def _load_special_events(self) -> Dict:
        """Load special events config (FT top-ups, etc.)."""
        config_path = CONFIG_DIR / "special_events.yaml"
        if not config_path.exists():
            logger.debug("No special_events.yaml found")
            return {}
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load special_events.yaml: {e}")
            return {}

    def get_ft_topup_for_gw(self, target_gw: int) -> Optional[Dict]:
        """
        Check if a special FT top-up applies to this gameweek.

        Returns the top-up config if applicable, None otherwise.
        """
        topups = self._special_events.get('ft_topups', [])
        for topup in topups:
            effective_from = topup.get('effective_from_gw')
            if effective_from and target_gw >= effective_from:
                return topup
        return None

    def get_available_free_transfers(
        self,
        team_id: int,
        target_gw: Optional[int] = None,
        override_ft: Optional[int] = None
    ) -> Dict:
        """
        Fetch and calculate available free transfers for the target gameweek.

        Args:
            team_id: FPL team ID
            target_gw: Target gameweek (default: next gameweek)
            override_ft: Manual override for special events (e.g., AFCON 5 FTs)

        Returns:
            {
                'free_transfers': int,      # Available FTs for this GW
                'bank': float,              # Money in bank (£m)
                'team_value': float,        # Total team value (£m)
                'banked_before': int,       # FTs banked going into this GW
                'last_gw_transfers': int,   # Transfers used last GW
                'calculation': str,         # Human-readable explanation
                'is_override': bool,        # Whether override was applied
            }
        """
        try:
            # Get current/next gameweek if not specified
            if target_gw is None:
                target_gw = self._get_next_gameweek()

            # Fetch team history
            history = self._fetch_team_history(team_id)
            entry = self._fetch_team_entry(team_id)

            # Calculate FTs from history
            ft_data = self._calculate_free_transfers(history, target_gw)

            # Get bank and value from entry
            bank = entry.get('last_deadline_bank', 0) / 10.0
            team_value = entry.get('last_deadline_value', 1000) / 10.0

            # Apply override if provided
            if override_ft is not None:
                actual_ft = override_ft
                is_override = True
                calculation = f"Override: {override_ft} FTs (calculated was {ft_data['free_transfers']})"
            else:
                actual_ft = ft_data['free_transfers']
                is_override = False
                calculation = ft_data['calculation']

            result = {
                'free_transfers': actual_ft,
                'bank': bank,
                'team_value': team_value,
                'banked_before': ft_data['banked_before'],
                'last_gw_transfers': ft_data['last_gw_transfers'],
                'calculation': calculation,
                'is_override': is_override,
                'target_gw': target_gw,
            }

            logger.info(
                f"FreeTransferTracker: GW{target_gw} - {actual_ft} FTs available "
                f"(bank: £{bank}m) - {calculation}"
            )

            return result

        except Exception as e:
            logger.error(f"FreeTransferTracker: Error fetching FT data: {e}")
            # Return safe default
            return {
                'free_transfers': 1,
                'bank': 0.0,
                'team_value': 100.0,
                'banked_before': 0,
                'last_gw_transfers': 0,
                'calculation': f"Error: {e}, defaulting to 1 FT",
                'is_override': False,
                'target_gw': target_gw,
            }

    def _fetch_team_entry(self, team_id: int) -> Dict:
        """Fetch team entry data."""
        response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/")
        response.raise_for_status()
        return response.json()

    def _fetch_team_history(self, team_id: int) -> Dict:
        """Fetch team season history."""
        response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/history/")
        response.raise_for_status()
        return response.json()

    def _get_next_gameweek(self) -> int:
        """Get the next gameweek number from bootstrap data."""
        response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
        response.raise_for_status()
        data = response.json()

        for gw in data['events']:
            if gw['is_next']:
                return gw['id']

        # Fallback: find first unfinished
        for gw in data['events']:
            if not gw['finished']:
                return gw['id']

        return 38  # Season end fallback

    def _calculate_free_transfers(
        self,
        history: Dict,
        target_gw: int
    ) -> Dict:
        """
        Calculate free transfers available for target gameweek.

        Logic:
        - Start with 0 banked FTs at beginning of season
        - Each GW: available = min(5, banked + 1)
        - After GW: banked = max(0, available - transfers_used)
        - Apply special event top-ups (e.g., AFCON) when applicable
        - Repeat until target GW
        """
        current_history = history.get('current', [])

        if not current_history:
            # New team, no history yet
            return {
                'free_transfers': 1,
                'banked_before': 0,
                'last_gw_transfers': 0,
                'calculation': "New team - 1 FT available",
                'special_event': None,
            }

        # Track banked FTs through the season
        banked = 0
        last_transfers = 0
        applied_topup = None

        # Build set of GWs where top-ups apply
        topups = self._special_events.get('ft_topups', [])
        topup_triggers = {t['trigger_after_gw']: t for t in topups if 'trigger_after_gw' in t}

        for gw_data in current_history:
            gw_num = gw_data['event']
            transfers_used = gw_data['event_transfers']

            # Calculate what was available at start of this GW
            available = min(MAX_BANKED_TRANSFERS, banked + 1)

            # Calculate what's banked after this GW
            if transfers_used <= available:
                banked = available - transfers_used
            else:
                banked = 0

            # Apply top-up if this GW triggers one
            if gw_num in topup_triggers:
                topup = topup_triggers[gw_num]
                topup_to = topup.get('topup_to', MAX_BANKED_TRANSFERS)
                if banked < topup_to:
                    banked = topup_to - 1  # -1 because we add 1 for next GW
                    applied_topup = topup

            last_transfers = transfers_used

            # Stop if we've processed up to the GW before target
            if gw_num >= target_gw - 1:
                break

        # Check if top-up applies for target GW (if we haven't processed trigger GW yet)
        if target_gw - 1 in topup_triggers and (not current_history or current_history[-1]['event'] < target_gw - 1):
            topup = topup_triggers[target_gw - 1]
            topup_to = topup.get('topup_to', MAX_BANKED_TRANSFERS)
            banked = topup_to - 1
            applied_topup = topup

        # Calculate FTs available for target GW
        free_transfers = min(MAX_BANKED_TRANSFERS, banked + 1)

        last_gw = current_history[-1]['event'] if current_history else 0

        if applied_topup:
            calculation = (
                f"GW{last_gw}: {applied_topup['name']} top-up to {applied_topup['topup_to']} FTs → "
                f"GW{target_gw}: {free_transfers} FTs"
            )
        else:
            calculation = (
                f"GW{last_gw}: used {last_transfers}, banked {banked} → "
                f"GW{target_gw}: min(5, {banked}+1) = {free_transfers} FTs"
            )

        return {
            'free_transfers': free_transfers,
            'banked_before': banked,
            'last_gw_transfers': last_transfers,
            'calculation': calculation,
            'special_event': applied_topup['name'] if applied_topup else None,
        }

    def get_transfer_history(self, team_id: int) -> List[Dict]:
        """
        Get detailed transfer history for a team.

        Returns list of transfers with player details.
        """
        response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/transfers/")
        response.raise_for_status()
        return response.json()


# Convenience function for quick access
def get_free_transfers(team_id: int, override_ft: Optional[int] = None) -> int:
    """
    Quick helper to get just the free transfer count.

    Args:
        team_id: FPL team ID
        override_ft: Manual override for special events

    Returns:
        Number of free transfers available
    """
    tracker = FreeTransferTracker()
    result = tracker.get_available_free_transfers(team_id, override_ft=override_ft)
    return result['free_transfers']


if __name__ == "__main__":
    # Test the tracker
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
    from utils.config import load_config

    config = load_config()
    team_id = config.get('team_id')

    if team_id:
        print(f"\n=== Free Transfer Tracker Test (Team {team_id}) ===\n")

        tracker = FreeTransferTracker()
        result = tracker.get_available_free_transfers(team_id)

        for key, val in result.items():
            print(f"{key}: {val}")

        print(f"\n✓ {result['free_transfers']} free transfers available for GW{result['target_gw']}")
    else:
        print("No team_id configured")
