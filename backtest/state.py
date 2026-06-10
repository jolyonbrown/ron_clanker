"""
FPL entry state machine: squad ownership, budget, free transfers, chips.

Tracks everything that persists between gameweeks for a simulated entry
and applies the FPL transfer economics:

    - Money is integer tenths of £m throughout (10 = £1.0m).
    - Selling price: purchase price + half the profit, rounded down to
      the nearest 0.1m (i.e. integer floor division in tenths). A player
      whose price fell sells at the current price.
    - Free transfers: 1 accrues per gameweek, bank up to 5. Transfers
      beyond the available FTs cost 4 points each.
    - Wildcard / Free Hit gameweeks FREEZE the FT count: banked FTs are
      kept (2025/26 carry-through rule) but the +1 does NOT accrue.
      Derived from and validated against Ron's actual 2025-26 history —
      the GW36 -28 hit (9 transfers, 2 FTs) only reconciles this way.
    - Special-event top-ups (AFCON December 2025: everyone topped up to
      5 FTs at GW16) are passed in as config, mirroring
      config/special_events.yaml.
    - Chips: two of each per season; the first set expires after GW19,
      the second is available from GW20 (2025/26 rules).

Free Hit reversion is handled by snapshot()/restore() — the simulator
snapshots before applying FH transfers and restores after scoring.
"""

import logging
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Set, Tuple

from backtest.scoring import FREE_HIT, WILDCARD

logger = logging.getLogger('ron_clanker.backtest.state')

MAX_BANKED_FT = 5
HIT_COST = 4
SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}   # element_type -> required count
MAX_PER_CLUB = 3
STARTING_BUDGET = 1000                    # tenths


def sell_price(purchase: int, current: int) -> int:
    """FPL selling price in tenths: half the profit, rounded down."""
    if current <= purchase:
        return current
    return purchase + (current - purchase) // 2


@dataclass(frozen=True)
class OwnedPlayer:
    player_id: int
    purchase_price: int   # tenths


@dataclass(frozen=True)
class Transfer:
    """One transfer. Explicit prices (when replaying recorded history)
    override the price map, because real transactions happen at whatever
    the price was at click time, not at the deadline."""
    out_id: int
    in_id: int
    out_price: Optional[int] = None   # money received (sell price), tenths
    in_price: Optional[int] = None    # money paid, tenths


class IllegalSquadError(ValueError):
    pass


class IllegalTransferError(ValueError):
    pass


def validate_squad(
    player_ids: Set[int],
    element_types: Dict[int, int],
    team_ids: Dict[int, int],
    check_clubs: bool = True,
) -> None:
    """Raise IllegalSquadError unless the 15 satisfy FPL squad rules.

    check_clubs=False skips the max-3-per-club rule: replays of recorded
    seasons were legal at the time, but club assignments in the players
    table are end-of-season state and mid-season moves can make an old
    squad look illegal.
    """
    if len(player_ids) != 15:
        raise IllegalSquadError(f"Squad must have 15 players, got {len(player_ids)}")
    counts: Dict[int, int] = {}
    clubs: Dict[int, int] = {}
    for pid in player_ids:
        et = element_types.get(pid)
        if et is None:
            raise IllegalSquadError(f"Unknown element type for player {pid}")
        counts[et] = counts.get(et, 0) + 1
        club = team_ids.get(pid)
        clubs[club] = clubs.get(club, 0) + 1
    if counts != SQUAD_SHAPE:
        raise IllegalSquadError(f"Squad shape {counts} != required {SQUAD_SHAPE}")
    if check_clubs:
        over = {c: n for c, n in clubs.items() if n > MAX_PER_CLUB}
        if over:
            raise IllegalSquadError(
                f"More than {MAX_PER_CLUB} players from club(s) {over}"
            )


@dataclass
class EntryState:
    """Persistent state of a simulated FPL entry."""
    squad: Dict[int, OwnedPlayer] = field(default_factory=dict)
    bank: int = STARTING_BUDGET
    banked_ft: int = 0                 # FTs banked after the previous GW
    chips_used: List[Tuple[int, str]] = field(default_factory=list)  # (gw, chip)
    ft_topups: Dict[int, int] = field(default_factory=dict)  # gw -> top-up-to

    # ------------------------------------------------------------------
    # Free transfers

    def available_ft(self, gameweek: int) -> int:
        avail = min(MAX_BANKED_FT, self.banked_ft + 1)
        topup = self.ft_topups.get(gameweek)
        if topup:
            avail = max(avail, topup)
        return avail

    # ------------------------------------------------------------------
    # Chips

    def chip_available(self, chip: str, gameweek: int) -> bool:
        """Two of each chip: one playable up to GW19, one from GW20."""
        half = 1 if gameweek <= 19 else 2
        used_in_half = [
            (gw, c) for gw, c in self.chips_used
            if c == chip and (1 if gw <= 19 else 2) == half
        ]
        return not used_in_half

    # ------------------------------------------------------------------
    # Squad / budget

    def buy_initial_squad(
        self,
        purchases: Dict[int, int],   # player_id -> price paid (tenths)
        element_types: Dict[int, int],
        team_ids: Dict[int, int],
        bank_override: Optional[int] = None,
        check_clubs: bool = True,
    ) -> None:
        validate_squad(set(purchases), element_types, team_ids,
                       check_clubs=check_clubs)
        cost = sum(purchases.values())
        if bank_override is not None:
            # Replaying a recorded entry: trust the recorded bank rather
            # than deadline-time price approximations.
            self.bank = bank_override
        else:
            if cost > self.bank:
                raise IllegalSquadError(
                    f"Initial squad costs {cost}, budget is {self.bank}"
                )
            self.bank -= cost
        self.squad = {
            pid: OwnedPlayer(player_id=pid, purchase_price=price)
            for pid, price in purchases.items()
        }

    def squad_market_value(self, prices: Dict[int, int]) -> int:
        """Current market value of the squad (not selling value)."""
        return sum(
            prices.get(pid, p.purchase_price) for pid, p in self.squad.items()
        )

    def squad_selling_value(self, prices: Dict[int, int]) -> int:
        return sum(
            sell_price(p.purchase_price, prices.get(pid, p.purchase_price))
            for pid, p in self.squad.items()
        )

    # ------------------------------------------------------------------
    # Gameweek transfer application

    def apply_gameweek(
        self,
        gameweek: int,
        transfers: List[Transfer],
        chip: Optional[str],
        prices: Dict[int, int],
        element_types: Optional[Dict[int, int]] = None,
        team_ids: Optional[Dict[int, int]] = None,
        check_clubs: bool = True,
    ) -> int:
        """Apply one gameweek's transfers in order. Returns the hit cost.

        Transfers are applied sequentially so that within-window churn
        (selling a player bought earlier the same window, as happens on
        wildcards) resolves with correct prices.
        """
        if chip and not self.chip_available(chip, gameweek):
            raise IllegalTransferError(
                f"GW{gameweek}: {chip} not available (already used this half)"
            )

        for t in transfers:
            if t.out_id not in self.squad:
                raise IllegalTransferError(
                    f"GW{gameweek}: selling player {t.out_id} not in squad"
                )
            if t.in_id in self.squad:
                raise IllegalTransferError(
                    f"GW{gameweek}: buying player {t.in_id} already in squad"
                )
            owned = self.squad.pop(t.out_id)
            received = t.out_price if t.out_price is not None else sell_price(
                owned.purchase_price, prices.get(t.out_id, owned.purchase_price)
            )
            paid = t.in_price if t.in_price is not None else prices.get(t.in_id)
            if paid is None:
                raise IllegalTransferError(
                    f"GW{gameweek}: no price known for incoming player {t.in_id}"
                )
            self.bank += received - paid
            self.squad[t.in_id] = OwnedPlayer(player_id=t.in_id, purchase_price=paid)

        # FPL validates affordability on the confirmed batch, not per
        # transfer — within-window ordering can dip negative transiently
        # (e.g. Ron's GW19 wildcard).
        if self.bank < 0:
            raise IllegalTransferError(
                f"GW{gameweek}: bank negative ({self.bank}) after transfer window"
            )

        if element_types is not None and team_ids is not None and transfers:
            validate_squad(set(self.squad), element_types, team_ids,
                           check_clubs=check_clubs)

        # FT accounting and hits
        if chip in (WILDCARD, FREE_HIT):
            # Frozen: keep banked FTs, no +1 accrual, no hits.
            hit = 0
        else:
            avail = self.available_ft(gameweek)
            n = len(transfers)
            hit = max(0, n - avail) * HIT_COST
            self.banked_ft = max(0, avail - n)

        if chip:
            self.chips_used.append((gameweek, chip))
        return hit

    # ------------------------------------------------------------------
    # Free Hit snapshot/restore

    def snapshot(self) -> Dict:
        return {
            'squad': dict(self.squad),
            'bank': self.bank,
        }

    def restore(self, snap: Dict) -> None:
        self.squad = dict(snap['squad'])
        self.bank = snap['bank']
