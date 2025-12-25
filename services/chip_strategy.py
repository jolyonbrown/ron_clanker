"""
Chip Strategy Service

Consolidated chip decision-making logic. Determines when to use chips based on:
- Chip availability (from FPL API via ChipAvailabilityService)
- Fixture data (DGWs, BGWs)
- Team state (bench strength, captain options)

Key insight: Chips fall into two categories:
1. TRANSFER chips (Wildcard, Free Hit) - Replace normal transfers
2. TEAM chips (Bench Boost, Triple Captain) - Used alongside transfers

Usage:
    from services.chip_strategy import ChipStrategyService

    service = ChipStrategyService(database)
    decision = service.get_chip_decision(
        team_id=12222054,
        gameweek=16,
        squad=current_squad,
        transfers_planned=1
    )
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from services.chip_availability import ChipAvailabilityService, ChipStatus

logger = logging.getLogger(__name__)


@dataclass
class ChipDecision:
    """Result of chip decision analysis."""
    use_chip: bool
    chip_name: Optional[str]  # 'wildcard', 'freehit', 'bboost', '3xc'
    chip_display_name: Optional[str]
    reason: str
    urgency: str  # 'HIGH', 'MEDIUM', 'LOW', 'NONE'
    replaces_transfers: bool  # True for WC/FH, False for BB/TC
    expected_value: float  # Estimated point gain from using chip

    def to_dict(self) -> Dict:
        return {
            'use_chip': self.use_chip,
            'chip_name': self.chip_name,
            'chip_display_name': self.chip_display_name,
            'reason': self.reason,
            'urgency': self.urgency,
            'replaces_transfers': self.replaces_transfers,
            'expected_value': self.expected_value,
        }


class ChipStrategyService:
    """
    Determines optimal chip usage for a gameweek.

    Categories:
    - Wildcard: Use when 4+ transfers needed or major fixture swing
    - Free Hit: Use for BGWs or one-week punts
    - Bench Boost: Use when bench is strong AND DGW
    - Triple Captain: Use on premium player in DGW or exceptional fixture
    """

    # Chip types
    WILDCARD = 'wildcard'
    FREE_HIT = 'freehit'
    BENCH_BOOST = 'bboost'
    TRIPLE_CAPTAIN = '3xc'

    # Transfer chips vs team chips
    TRANSFER_CHIPS = {WILDCARD, FREE_HIT}
    TEAM_CHIPS = {BENCH_BOOST, TRIPLE_CAPTAIN}

    def __init__(self, database=None):
        """Initialize with optional database for fixture lookups."""
        self.db = database
        self.availability = ChipAvailabilityService()

    def get_chip_decision(
        self,
        team_id: int,
        gameweek: int,
        squad: List[Dict[str, Any]],
        transfers_needed: int = 0,
        free_transfers: int = 1,
        captain_xp: float = 0.0,
        bench_xp: float = 0.0,
    ) -> Dict[str, ChipDecision]:
        """
        Get chip recommendations for this gameweek.

        Args:
            team_id: FPL team ID
            gameweek: Target gameweek
            squad: Current squad with player data
            transfers_needed: How many transfers Ron wants to make
            free_transfers: Available free transfers
            captain_xp: Expected points of planned captain
            bench_xp: Total expected points of bench players

        Returns:
            Dict mapping chip_name -> ChipDecision
        """
        # Get available chips from API
        all_chips = self.availability.get_available_chips(team_id, gameweek)
        available_chips = {c.definition.name: c for c in all_chips if c.available_now}

        # Check fixture context
        is_dgw = self._is_double_gameweek(gameweek)
        is_bgw = self._is_blank_gameweek(gameweek)
        dgw_teams = self._get_dgw_teams(gameweek) if is_dgw else []

        decisions = {}

        # Evaluate each chip type
        if self.WILDCARD in available_chips:
            decisions[self.WILDCARD] = self._evaluate_wildcard(
                chip=available_chips[self.WILDCARD],
                gameweek=gameweek,
                transfers_needed=transfers_needed,
                free_transfers=free_transfers,
            )

        if self.FREE_HIT in available_chips:
            decisions[self.FREE_HIT] = self._evaluate_free_hit(
                chip=available_chips[self.FREE_HIT],
                gameweek=gameweek,
                is_bgw=is_bgw,
                squad=squad,
            )

        if self.BENCH_BOOST in available_chips:
            decisions[self.BENCH_BOOST] = self._evaluate_bench_boost(
                chip=available_chips[self.BENCH_BOOST],
                gameweek=gameweek,
                is_dgw=is_dgw,
                bench_xp=bench_xp,
                squad=squad,
                dgw_teams=dgw_teams,
            )

        if self.TRIPLE_CAPTAIN in available_chips:
            decisions[self.TRIPLE_CAPTAIN] = self._evaluate_triple_captain(
                chip=available_chips[self.TRIPLE_CAPTAIN],
                gameweek=gameweek,
                is_dgw=is_dgw,
                captain_xp=captain_xp,
                squad=squad,
                dgw_teams=dgw_teams,
            )

        return decisions

    def get_recommended_chip(
        self,
        team_id: int,
        gameweek: int,
        squad: List[Dict[str, Any]],
        transfers_needed: int = 0,
        free_transfers: int = 1,
        captain_xp: float = 0.0,
        bench_xp: float = 0.0,
    ) -> Optional[ChipDecision]:
        """
        Get the single best chip recommendation (if any).

        Returns None if no chip should be used.
        """
        decisions = self.get_chip_decision(
            team_id=team_id,
            gameweek=gameweek,
            squad=squad,
            transfers_needed=transfers_needed,
            free_transfers=free_transfers,
            captain_xp=captain_xp,
            bench_xp=bench_xp,
        )

        # Check for "use it or lose it" pressure - multiple chips expiring soon
        expiring_chips = self._count_expiring_chips(team_id, gameweek)

        # Filter to chips worth using
        worthwhile = [d for d in decisions.values() if d.use_chip]

        # "Use it or lose it" logic: if more chips expiring than GWs remaining,
        # we MUST use one now or lose it forever
        must_use_one = (
            expiring_chips['count'] >= 1 and
            expiring_chips['gws_remaining'] <= expiring_chips['count']
        )

        if not worthwhile:
            if must_use_one:
                # Force pick the best expiring chip even if not ideally recommended
                logger.warning(
                    f"ChipStrategy: {expiring_chips['count']} chips expiring in "
                    f"{expiring_chips['gws_remaining']} GWs - MUST use one now!"
                )
                # Get all expiring chip decisions and pick the one with highest EV
                expiring_decisions = [
                    d for d in decisions.values()
                    if d.chip_name in {self.WILDCARD, self.FREE_HIT}  # Only transfer chips expire in windows
                ]
                if expiring_decisions:
                    # Pick by expected value (higher is better, even if negative)
                    expiring_decisions.sort(key=lambda d: d.expected_value, reverse=True)
                    forced = expiring_decisions[0]
                    # Override to use_chip=True with updated reason
                    return ChipDecision(
                        use_chip=True,
                        chip_name=forced.chip_name,
                        chip_display_name=forced.chip_display_name,
                        reason=f"FORCED: {expiring_chips['count']} chips expire in {expiring_chips['gws_remaining']} GWs - use or lose!",
                        urgency='HIGH',
                        replaces_transfers=forced.replaces_transfers,
                        expected_value=forced.expected_value,
                    )
            return None

        # Prioritize by urgency then expected value
        urgency_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'NONE': 0}
        worthwhile.sort(
            key=lambda d: (urgency_order.get(d.urgency, 0), d.expected_value),
            reverse=True
        )

        return worthwhile[0]

    def _count_expiring_chips(self, team_id: int, gameweek: int) -> Dict[str, int]:
        """Count how many chips are expiring and when."""
        all_chips = self.availability.get_available_chips(team_id, gameweek)
        expiring = [c for c in all_chips if c.available_now and c.expires_soon]

        if not expiring:
            return {'count': 0, 'gws_remaining': 99}

        min_expiry = min(c.gws_until_expiry for c in expiring)
        return {'count': len(expiring), 'gws_remaining': min_expiry}

    def _evaluate_wildcard(
        self,
        chip: ChipStatus,
        gameweek: int,
        transfers_needed: int,
        free_transfers: int,
    ) -> ChipDecision:
        """
        Evaluate Wildcard usage.

        Use when:
        - Need 4+ transfers (rebuilding squad)
        - Chip expiring soon AND team needs work
        """
        extra_transfers = max(0, transfers_needed - free_transfers)
        hit_cost = extra_transfers * 4

        # Strong signal: Need many transfers
        if transfers_needed >= 4:
            return ChipDecision(
                use_chip=True,
                chip_name=self.WILDCARD,
                chip_display_name=chip.definition.display_name,
                reason=f"Need {transfers_needed} transfers - Wildcard saves {hit_cost}pts in hits",
                urgency='HIGH' if chip.expires_soon else 'MEDIUM',
                replaces_transfers=True,
                expected_value=float(hit_cost + transfers_needed * 2),  # hits saved + better players
            )

        # Expiring soon - use if any benefit
        if chip.expires_soon and transfers_needed >= 2:
            return ChipDecision(
                use_chip=True,
                chip_name=self.WILDCARD,
                chip_display_name=chip.definition.display_name,
                reason=f"Wildcard expires in {chip.gws_until_expiry} GWs - use now with {transfers_needed} transfers planned",
                urgency='HIGH',
                replaces_transfers=True,
                expected_value=float(hit_cost + 4),
            )

        # Don't use
        return ChipDecision(
            use_chip=False,
            chip_name=self.WILDCARD,
            chip_display_name=chip.definition.display_name,
            reason=f"Only {transfers_needed} transfers needed - save Wildcard for bigger rebuild",
            urgency='LOW' if chip.gws_until_expiry <= 6 else 'NONE',
            replaces_transfers=True,
            expected_value=0.0,
        )

    def _evaluate_free_hit(
        self,
        chip: ChipStatus,
        gameweek: int,
        is_bgw: bool,
        squad: List[Dict[str, Any]],
    ) -> ChipDecision:
        """
        Evaluate Free Hit usage.

        Use when:
        - Blank gameweek (many teams not playing)
        - Chip expiring and no BGW coming
        """
        # Count players who might not play (team in BGW)
        non_playing = 0  # Would need fixture data to calculate properly

        if is_bgw:
            return ChipDecision(
                use_chip=True,
                chip_name=self.FREE_HIT,
                chip_display_name=chip.definition.display_name,
                reason=f"GW{gameweek} is a Blank Gameweek - Free Hit to field full XI",
                urgency='HIGH',
                replaces_transfers=True,
                expected_value=20.0,  # Rough estimate of fielding 11 vs fewer
            )

        if chip.expires_soon:
            # Free Hit squad optimizer is implemented in manager_agent_v2.py
            # Use it before it expires - builds optimal £100m squad for single GW
            return ChipDecision(
                use_chip=True,
                chip_name=self.FREE_HIT,
                chip_display_name=chip.definition.display_name,
                reason=f"Free Hit expires in {chip.gws_until_expiry} GWs - use now to build optimal squad",
                urgency='HIGH',
                replaces_transfers=True,
                expected_value=15.0,  # Estimated gain from optimal vs current squad
            )

        return ChipDecision(
            use_chip=False,
            chip_name=self.FREE_HIT,
            chip_display_name=chip.definition.display_name,
            reason="Save Free Hit for Blank Gameweek",
            urgency='NONE',
            replaces_transfers=True,
            expected_value=0.0,
        )

    def _evaluate_bench_boost(
        self,
        chip: ChipStatus,
        gameweek: int,
        is_dgw: bool,
        bench_xp: float,
        squad: List[Dict[str, Any]],
        dgw_teams: List[int],
    ) -> ChipDecision:
        """
        Evaluate Bench Boost usage.

        Use when:
        - Double Gameweek AND strong bench
        - All bench players expected to play
        """
        # Count bench players in DGW teams
        bench = [p for p in squad if p.get('position', 0) > 11]
        bench_in_dgw = sum(1 for p in bench if p.get('team') in dgw_teams) if dgw_teams else 0

        # Ideal: DGW with bench players also in DGW
        if is_dgw and bench_in_dgw >= 3:
            estimated_gain = bench_xp * 2 if bench_xp > 0 else 15.0
            return ChipDecision(
                use_chip=True,
                chip_name=self.BENCH_BOOST,
                chip_display_name=chip.definition.display_name,
                reason=f"DGW with {bench_in_dgw}/4 bench players doubling - estimated +{estimated_gain:.0f}pts",
                urgency='HIGH',
                replaces_transfers=False,
                expected_value=estimated_gain,
            )

        # DGW but bench not great
        if is_dgw:
            estimated_gain = bench_xp if bench_xp > 0 else 8.0
            return ChipDecision(
                use_chip=bench_xp >= 12,  # Only if bench is decent
                chip_name=self.BENCH_BOOST,
                chip_display_name=chip.definition.display_name,
                reason=f"DGW but only {bench_in_dgw}/4 bench in DGW teams - {bench_xp:.1f}xP bench",
                urgency='MEDIUM' if bench_xp >= 12 else 'LOW',
                replaces_transfers=False,
                expected_value=estimated_gain,
            )

        # Expiring without DGW
        if chip.expires_soon:
            return ChipDecision(
                use_chip=bench_xp >= 15,
                chip_name=self.BENCH_BOOST,
                chip_display_name=chip.definition.display_name,
                reason=f"BB expires in {chip.gws_until_expiry} GWs, no DGW - use if bench strong ({bench_xp:.1f}xP)",
                urgency='MEDIUM' if bench_xp >= 15 else 'LOW',
                replaces_transfers=False,
                expected_value=bench_xp,
            )

        return ChipDecision(
            use_chip=False,
            chip_name=self.BENCH_BOOST,
            chip_display_name=chip.definition.display_name,
            reason="Save Bench Boost for Double Gameweek with strong bench",
            urgency='NONE',
            replaces_transfers=False,
            expected_value=0.0,
        )

    def _evaluate_triple_captain(
        self,
        chip: ChipStatus,
        gameweek: int,
        is_dgw: bool,
        captain_xp: float,
        squad: List[Dict[str, Any]],
        dgw_teams: List[int],
    ) -> ChipDecision:
        """
        Evaluate Triple Captain usage.

        Use when:
        - Premium captain in DGW
        - Exceptional single-game fixture (premium vs bottom team at home)
        """
        # Find captain
        captain = next((p for p in squad if p.get('is_captain')), None)
        captain_in_dgw = captain and captain.get('team') in dgw_teams if dgw_teams else False

        # Ideal: Premium captain in DGW
        if is_dgw and captain_in_dgw:
            # TC gives extra captain_xp (normally 2x, TC gives 3x, so +1x)
            estimated_gain = captain_xp  # The extra multiplier
            return ChipDecision(
                use_chip=True,
                chip_name=self.TRIPLE_CAPTAIN,
                chip_display_name=chip.definition.display_name,
                reason=f"Captain in DGW - TC for extra {captain_xp:.1f}pts (3x instead of 2x)",
                urgency='HIGH',
                replaces_transfers=False,
                expected_value=estimated_gain,
            )

        # DGW but captain not in it
        if is_dgw:
            return ChipDecision(
                use_chip=False,
                chip_name=self.TRIPLE_CAPTAIN,
                chip_display_name=chip.definition.display_name,
                reason="DGW but captain not in doubling team - consider changing captain",
                urgency='LOW',
                replaces_transfers=False,
                expected_value=0.0,
            )

        # Expiring - use on best fixture
        if chip.expires_soon and captain_xp >= 10:
            return ChipDecision(
                use_chip=True,
                chip_name=self.TRIPLE_CAPTAIN,
                chip_display_name=chip.definition.display_name,
                reason=f"TC expires in {chip.gws_until_expiry} GWs - use on {captain_xp:.1f}xP captain",
                urgency='MEDIUM',
                replaces_transfers=False,
                expected_value=captain_xp,
            )

        return ChipDecision(
            use_chip=False,
            chip_name=self.TRIPLE_CAPTAIN,
            chip_display_name=chip.definition.display_name,
            reason="Save Triple Captain for premium player in Double Gameweek",
            urgency='NONE',
            replaces_transfers=False,
            expected_value=0.0,
        )

    def _is_double_gameweek(self, gameweek: int) -> bool:
        """Check if gameweek is a DGW (any team plays twice)."""
        if not self.db:
            return False

        try:
            result = self.db.execute_query("""
                SELECT COUNT(*) as dgw_fixtures
                FROM (
                    SELECT team_h as team_id, COUNT(*) as games
                    FROM fixtures WHERE event = ?
                    GROUP BY team_h
                    HAVING games > 1
                    UNION
                    SELECT team_a as team_id, COUNT(*) as games
                    FROM fixtures WHERE event = ?
                    GROUP BY team_a
                    HAVING games > 1
                )
            """, (gameweek, gameweek))

            return result and result[0]['dgw_fixtures'] > 0
        except Exception as e:
            logger.warning(f"ChipStrategy: Error checking DGW: {e}")
            return False

    def _is_blank_gameweek(self, gameweek: int) -> bool:
        """Check if gameweek is a BGW (fewer than 10 fixtures)."""
        if not self.db:
            return False

        try:
            result = self.db.execute_query("""
                SELECT COUNT(*) as fixture_count
                FROM fixtures WHERE event = ?
            """, (gameweek,))

            # Normal GW has 10 fixtures, BGW has fewer
            return result and result[0]['fixture_count'] < 10
        except Exception as e:
            logger.warning(f"ChipStrategy: Error checking BGW: {e}")
            return False

    def _get_dgw_teams(self, gameweek: int) -> List[int]:
        """Get list of team IDs that have double fixtures."""
        if not self.db:
            return []

        try:
            result = self.db.execute_query("""
                SELECT team_id FROM (
                    SELECT team_h as team_id FROM fixtures WHERE event = ?
                    UNION ALL
                    SELECT team_a as team_id FROM fixtures WHERE event = ?
                )
                GROUP BY team_id
                HAVING COUNT(*) > 1
            """, (gameweek, gameweek))

            return [r['team_id'] for r in result] if result else []
        except Exception as e:
            logger.warning(f"ChipStrategy: Error getting DGW teams: {e}")
            return []


if __name__ == "__main__":
    # Test the service
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
    from utils.config import load_config
    from data.database import Database

    config = load_config()
    team_id = config.get('team_id')

    if team_id:
        print(f"\n=== Chip Strategy Test (Team {team_id}) ===\n")

        db = Database()
        service = ChipStrategyService(database=db)

        # Mock squad for testing
        mock_squad = [
            {'id': 1, 'position': i, 'team': 1, 'is_captain': i == 1}
            for i in range(1, 16)
        ]

        decisions = service.get_chip_decision(
            team_id=team_id,
            gameweek=16,
            squad=mock_squad,
            transfers_needed=2,
            free_transfers=1,
            captain_xp=8.5,
            bench_xp=12.0,
        )

        for chip_name, decision in decisions.items():
            status = "USE" if decision.use_chip else "SKIP"
            print(f"{decision.chip_display_name}: {status}")
            print(f"  Reason: {decision.reason}")
            print(f"  Urgency: {decision.urgency}")
            print(f"  EV: {decision.expected_value:.1f}pts")
            print()

        best = service.get_recommended_chip(
            team_id=team_id,
            gameweek=16,
            squad=mock_squad,
            transfers_needed=2,
            free_transfers=1,
            captain_xp=8.5,
            bench_xp=12.0,
        )

        if best:
            print(f"RECOMMENDED: {best.chip_display_name}")
            print(f"  {best.reason}")
        else:
            print("RECOMMENDED: No chip this gameweek")
    else:
        print("No team_id configured")
