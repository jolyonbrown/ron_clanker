"""
Strategy interface for counterfactual season simulation.

A Strategy is the decision-maker being evaluated: given only what was
knowable before a gameweek's deadline, it picks transfers, a chip, and
a lineup. The simulator owns the rules (budget, FTs, hits, scoring) so
strategies stay pure decision logic.

Walk-forward discipline is enforced structurally: strategies receive an
AsOfView, which exposes pre-deadline data only (stored predictions,
history strictly before the GW, prices, the fixture schedule) and has
no access to actuals.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backtest.data import HistoricalDataProvider
from backtest.scoring import Pick
from backtest.state import Transfer


class AsOfView:
    """Pre-deadline data for one gameweek. No actuals, no future."""

    def __init__(self, provider: HistoricalDataProvider, gameweek: int,
                 prices: Dict[int, int]):
        self._provider = provider
        self.gameweek = gameweek
        self._prices = prices

    def predictions(self) -> Dict[int, float]:
        """The model's stored pre-deadline xP for this gameweek."""
        return self._provider.predictions(self.gameweek)

    def history(self) -> Dict[int, Dict]:
        """Per-player aggregates strictly before this gameweek."""
        return self._provider.history_before(self.gameweek)

    def prices(self) -> Dict[int, int]:
        """Latest known market prices (tenths), carried forward."""
        return self._prices

    def fixture_counts(self) -> Dict[int, int]:
        """team_id -> fixtures this GW (0 = blank, 2 = DGW)."""
        return self._provider.fixture_counts(self.gameweek)

    def element_types(self) -> Dict[int, int]:
        return self._provider.player_element_types()

    def team_ids(self) -> Dict[int, int]:
        return self._provider.player_team_ids()

    def names(self) -> Dict[int, str]:
        return self._provider.player_names()


@dataclass
class GWDecision:
    """One gameweek's decisions. picks must cover exactly the post-transfer
    squad (15 players, positions 1-15, one captain, one vice)."""
    transfers: List[Transfer] = field(default_factory=list)
    chip: Optional[str] = None
    picks: List[Pick] = field(default_factory=list)


@dataclass
class InitialSquad:
    """Entry-point decision: the squad bought with the starting budget."""
    purchases: Dict[int, int]            # player_id -> price paid (tenths)
    picks: List[Pick] = field(default_factory=list)
    bank_override: Optional[int] = None  # replays trust the recorded bank


class Strategy(ABC):
    """Decision-maker evaluated by the simulator."""

    name: str = 'strategy'

    # Replay strategies set this False: recorded squads were legal at the
    # time, but end-of-season club assignments can make them look like
    # max-3-per-club violations after mid-season moves.
    check_clubs: bool = True

    @abstractmethod
    def initial_squad(self, gameweek: int, view: AsOfView) -> InitialSquad:
        """Build the entry squad at the start gameweek."""

    @abstractmethod
    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        """Decide one gameweek. state_info carries the simulator-owned
        facts a manager would know: squad (with purchase prices), bank,
        available FTs, chips still available."""
