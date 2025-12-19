"""
Chip Availability Service

Fetches chip definitions and usage from FPL API.
Provides generic chip availability tracking that adapts to any season's rules.

The API provides:
- bootstrap-static/chips: All chip definitions with validity windows (start_event, stop_event)
- entry/{team_id}/history/chips: Chips already used by the team

Usage:
    from services.chip_availability import ChipAvailabilityService

    service = ChipAvailabilityService()
    available = service.get_available_chips(team_id=12222054, current_gw=16)

    for chip in available:
        print(f"{chip['name']}: available GW{chip['start_event']}-{chip['stop_event']}")
        if chip['expires_soon']:
            print(f"  WARNING: Expires in {chip['gws_until_expiry']} gameweeks!")
"""

import logging
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

FPL_BASE_URL = "https://fantasy.premierleague.com/api"


@dataclass
class ChipDefinition:
    """A chip as defined by the FPL API."""
    id: int
    name: str  # 'wildcard', 'freehit', 'bboost', '3xc'
    number: int  # Which instance (1 or 2 for double-chip seasons)
    start_event: int  # First GW it can be used
    stop_event: int  # Last GW it can be used
    chip_type: str  # 'transfer' or 'team'

    @property
    def display_name(self) -> str:
        """Human-readable chip name."""
        names = {
            'wildcard': 'Wildcard',
            'freehit': 'Free Hit',
            'bboost': 'Bench Boost',
            '3xc': 'Triple Captain'
        }
        base_name = names.get(self.name, self.name)
        return f"{base_name} #{self.number}" if self.number > 1 else base_name


@dataclass
class ChipStatus:
    """Status of a specific chip for a team."""
    definition: ChipDefinition
    used: bool
    used_in_gw: Optional[int]
    used_at: Optional[str]
    available_now: bool
    gws_until_expiry: int
    expires_soon: bool  # Within 3 GWs

    def to_dict(self) -> Dict:
        return {
            'chip_id': self.definition.id,
            'name': self.definition.name,
            'display_name': self.definition.display_name,
            'number': self.definition.number,
            'chip_type': self.definition.chip_type,
            'start_event': self.definition.start_event,
            'stop_event': self.definition.stop_event,
            'used': self.used,
            'used_in_gw': self.used_in_gw,
            'used_at': self.used_at,
            'available_now': self.available_now,
            'gws_until_expiry': self.gws_until_expiry,
            'expires_soon': self.expires_soon,
        }


class ChipAvailabilityService:
    """
    Service to track chip availability from FPL API.

    Adapts to any season's chip configuration automatically.
    """

    def __init__(self):
        self._chip_definitions: Optional[List[ChipDefinition]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 3600  # 1 hour cache

    def _fetch_chip_definitions(self) -> List[ChipDefinition]:
        """Fetch chip definitions from bootstrap-static API."""
        try:
            response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
            response.raise_for_status()
            data = response.json()

            chips_data = data.get('chips', [])

            # Group chips by name and sort by start_event to derive numbering
            # (API returns number=1 for all chips, but we need to distinguish
            # first-half vs second-half chips)
            from collections import defaultdict
            chips_by_name = defaultdict(list)
            for chip in chips_data:
                chips_by_name[chip['name']].append(chip)

            definitions = []
            for name, chip_list in chips_by_name.items():
                # Sort by start_event to get proper numbering
                sorted_chips = sorted(chip_list, key=lambda c: c['start_event'])
                for i, chip in enumerate(sorted_chips, start=1):
                    definitions.append(ChipDefinition(
                        id=chip['id'],
                        name=chip['name'],
                        number=i,  # Derive from position, not API field
                        start_event=chip['start_event'],
                        stop_event=chip['stop_event'],
                        chip_type=chip.get('chip_type', 'team')
                    ))

            # Sort final list by id for consistent ordering
            definitions.sort(key=lambda d: d.id)

            logger.info(f"ChipAvailability: Loaded {len(definitions)} chip definitions from API")
            return definitions

        except Exception as e:
            logger.error(f"ChipAvailability: Error fetching chip definitions: {e}")
            return []

    def _fetch_used_chips(self, team_id: int) -> List[Dict]:
        """Fetch chips already used by a team."""
        try:
            response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/history/")
            response.raise_for_status()
            data = response.json()

            chips_used = data.get('chips', [])
            logger.info(f"ChipAvailability: Team {team_id} has used {len(chips_used)} chips")
            return chips_used

        except Exception as e:
            logger.error(f"ChipAvailability: Error fetching used chips for team {team_id}: {e}")
            return []

    def _get_current_gameweek(self) -> int:
        """Get current gameweek from API."""
        try:
            response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
            response.raise_for_status()
            data = response.json()

            for gw in data['events']:
                if gw['is_current']:
                    return gw['id']
                if gw['is_next']:
                    return gw['id']

            return 1
        except Exception:
            return 1

    def get_chip_definitions(self, force_refresh: bool = False) -> List[ChipDefinition]:
        """Get all chip definitions for the season (cached)."""
        now = datetime.now()

        if (force_refresh or
            self._chip_definitions is None or
            self._cache_timestamp is None or
            (now - self._cache_timestamp).total_seconds() > self._cache_ttl_seconds):

            self._chip_definitions = self._fetch_chip_definitions()
            self._cache_timestamp = now

        return self._chip_definitions or []

    def get_available_chips(
        self,
        team_id: int,
        current_gw: Optional[int] = None,
        expiry_warning_gws: int = 4
    ) -> List[ChipStatus]:
        """
        Get list of available chips for a team.

        Args:
            team_id: FPL team ID
            current_gw: Current gameweek (auto-detected if not provided)
            expiry_warning_gws: Number of GWs before expiry to flag as 'expires_soon'

        Returns:
            List of ChipStatus objects for all chips
        """
        if current_gw is None:
            current_gw = self._get_current_gameweek()

        definitions = self.get_chip_definitions()
        used_chips = self._fetch_used_chips(team_id)

        # Build lookup of used chips by name
        used_lookup = {}
        for used in used_chips:
            chip_name = used.get('name')
            if chip_name not in used_lookup:
                used_lookup[chip_name] = []
            used_lookup[chip_name].append(used)

        results = []

        for defn in definitions:
            # Check if this specific chip instance was used
            used_instances = used_lookup.get(defn.name, [])

            # Match by checking if the gameweek falls within this chip's window
            used_this_instance = None
            for used in used_instances:
                used_gw = used.get('event')
                if defn.start_event <= used_gw <= defn.stop_event:
                    used_this_instance = used
                    break

            # Calculate availability
            is_used = used_this_instance is not None
            in_window = defn.start_event <= current_gw <= defn.stop_event
            available_now = not is_used and in_window

            # Calculate expiry
            if current_gw <= defn.stop_event:
                gws_until_expiry = defn.stop_event - current_gw + 1
            else:
                gws_until_expiry = 0

            expires_soon = 0 < gws_until_expiry <= expiry_warning_gws and not is_used

            results.append(ChipStatus(
                definition=defn,
                used=is_used,
                used_in_gw=used_this_instance.get('event') if used_this_instance else None,
                used_at=used_this_instance.get('time') if used_this_instance else None,
                available_now=available_now,
                gws_until_expiry=gws_until_expiry,
                expires_soon=expires_soon
            ))

        return results

    def get_expiring_chips(
        self,
        team_id: int,
        current_gw: Optional[int] = None,
        within_gws: int = 4
    ) -> List[ChipStatus]:
        """
        Get chips that are expiring soon and haven't been used.

        Use this to alert Ron about chips that need to be used or lost.
        """
        all_chips = self.get_available_chips(team_id, current_gw)

        expiring = [
            chip for chip in all_chips
            if chip.available_now and 0 < chip.gws_until_expiry <= within_gws
        ]

        # Sort by urgency (fewest GWs until expiry first)
        expiring.sort(key=lambda c: c.gws_until_expiry)

        return expiring

    def get_chip_summary(
        self,
        team_id: int,
        current_gw: Optional[int] = None
    ) -> Dict:
        """
        Get a summary of chip status for display/logging.

        Returns dict with 'available', 'used', 'expiring_soon', 'expired' lists.
        """
        if current_gw is None:
            current_gw = self._get_current_gameweek()

        all_chips = self.get_available_chips(team_id, current_gw)

        summary = {
            'current_gw': current_gw,
            'total_chips': len(all_chips),
            'available': [],
            'used': [],
            'expiring_soon': [],
            'expired': [],
        }

        for chip in all_chips:
            chip_info = chip.to_dict()

            if chip.used:
                summary['used'].append(chip_info)
            elif chip.available_now:
                summary['available'].append(chip_info)
                if chip.expires_soon:
                    summary['expiring_soon'].append(chip_info)
            elif current_gw > chip.definition.stop_event:
                summary['expired'].append(chip_info)

        return summary

    def should_consider_chip(
        self,
        team_id: int,
        chip_name: str,
        current_gw: Optional[int] = None
    ) -> Dict:
        """
        Check if a specific chip type should be considered this gameweek.

        Returns recommendation with reasoning.
        """
        if current_gw is None:
            current_gw = self._get_current_gameweek()

        all_chips = self.get_available_chips(team_id, current_gw)

        # Find matching chips (there may be 2 of each type in split-season format)
        matching = [c for c in all_chips if c.definition.name == chip_name]

        if not matching:
            return {
                'should_consider': False,
                'reason': f'No {chip_name} chip defined for this season',
                'chips': []
            }

        available = [c for c in matching if c.available_now]

        if not available:
            used = [c for c in matching if c.used]
            if used:
                return {
                    'should_consider': False,
                    'reason': f'{chip_name} already used in GW{used[0].used_in_gw}',
                    'chips': [c.to_dict() for c in matching]
                }
            else:
                return {
                    'should_consider': False,
                    'reason': f'{chip_name} not available in current window',
                    'chips': [c.to_dict() for c in matching]
                }

        # Check urgency
        most_urgent = min(available, key=lambda c: c.gws_until_expiry)

        if most_urgent.expires_soon:
            return {
                'should_consider': True,
                'urgency': 'HIGH',
                'reason': f'{most_urgent.definition.display_name} expires in {most_urgent.gws_until_expiry} GWs - use or lose!',
                'chips': [c.to_dict() for c in available]
            }
        else:
            return {
                'should_consider': True,
                'urgency': 'LOW',
                'reason': f'{most_urgent.definition.display_name} available, {most_urgent.gws_until_expiry} GWs until expiry',
                'chips': [c.to_dict() for c in available]
            }


# Convenience function for quick checks
def get_available_chips(team_id: int, current_gw: Optional[int] = None) -> List[Dict]:
    """Quick helper to get available chips as dicts."""
    service = ChipAvailabilityService()
    chips = service.get_available_chips(team_id, current_gw)
    return [c.to_dict() for c in chips if c.available_now]


if __name__ == "__main__":
    # Test the service
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
    from utils.config import load_config

    config = load_config()
    team_id = config.get('team_id')

    if team_id:
        print(f"\n=== Chip Availability Test (Team {team_id}) ===\n")

        service = ChipAvailabilityService()
        summary = service.get_chip_summary(team_id)

        print(f"Current GW: {summary['current_gw']}")
        print(f"Total chips defined: {summary['total_chips']}")

        print(f"\nAvailable chips ({len(summary['available'])}):")
        for chip in summary['available']:
            expiry = f" [EXPIRES in {chip['gws_until_expiry']} GWs!]" if chip['expires_soon'] else ""
            print(f"  - {chip['display_name']}: GW{chip['start_event']}-{chip['stop_event']}{expiry}")

        print(f"\nUsed chips ({len(summary['used'])}):")
        for chip in summary['used']:
            print(f"  - {chip['display_name']}: used in GW{chip['used_in_gw']}")

        if summary['expiring_soon']:
            print(f"\n⚠️  EXPIRING SOON ({len(summary['expiring_soon'])}):")
            for chip in summary['expiring_soon']:
                print(f"  - {chip['display_name']}: {chip['gws_until_expiry']} GWs left!")
    else:
        print("No team_id configured")
