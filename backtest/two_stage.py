"""
Two-stage prediction adjustment: xP' = P(plays) x xP  (ron_clanker-vtw).

Stored predictions behave like E[points | plays] and badly under-price
rotation/availability risk — the GW33 2025-26 double gameweek had two
players predicted ~11 who played 0 minutes. The classic fix is the
two-stage decomposition: multiply by the probability the player plays
at all.

P(plays) here is a recency-weighted play rate over the player's last
N team-fixture gameweeks, computed STRICTLY from history before the
decision gameweek (even when adjusting a future target gameweek — the
minutes between decision and target haven't happened yet).

Form chosen by walk-forward sweep on 2025-26 (vs raw MAE 1.477 /
Spearman 0.628 / 52 top-15 no-shows):

    play-rate, N=3, decay=0.6  ->  MAE 1.173, Spearman 0.702,
                                   27 no-shows

The neighbourhood (N=3-8, decay 0.6-0.8, minutes-share variant) is
flat — no knife edges. Composing a linear calibration AFTER this is
measurably destructive (the per-position intercept re-inflates exactly
the players this zeroed): if both corrections are wanted, measure the
combination through the harness first.
"""

import logging
import sqlite3
from typing import Dict, List, Tuple

from backtest.data import HistoricalDataProvider

logger = logging.getLogger('ron_clanker.backtest.two_stage')

WINDOW = 3
DECAY = 0.6
DEFAULT_PROB = 0.6   # no appearance history (new signing, youth debut)


class PlayProbability:
    """Walk-forward P(plays > 0 minutes) from recent minutes history."""

    def __init__(self, provider: HistoricalDataProvider,
                 window: int = WINDOW, decay: float = DECAY,
                 default: float = DEFAULT_PROB):
        self.window = window
        self.decay = decay
        self.default = default
        # (gw, minutes) per player, only GWs where their team had a fixture
        con = sqlite3.connect(f'file:{provider.db_path}?mode=ro', uri=True)
        try:
            self._history: Dict[int, List[Tuple[int, int]]] = {}
            for pid, gw, mins in con.execute(
                "SELECT player_id, gameweek, SUM(minutes) "
                "FROM player_gameweek_history "
                "GROUP BY player_id, gameweek ORDER BY gameweek"
            ):
                self._history.setdefault(pid, []).append((gw, mins or 0))
        finally:
            con.close()
        self._cache: Dict[Tuple[int, int], float] = {}

    def prob(self, player_id: int, as_of_gw: int) -> float:
        key = (player_id, as_of_gw)
        if key in self._cache:
            return self._cache[key]
        past = [(g, m) for g, m in self._history.get(player_id, [])
                if g < as_of_gw][-self.window:]
        if not past:
            p = self.default
        else:
            w, num, den = 1.0, 0.0, 0.0
            for g, m in reversed(past):       # most recent first
                num += w * (1.0 if m > 0 else 0.0)
                den += w
                w *= self.decay
            p = num / den
        self._cache[key] = p
        return p

    def adjust(self, predictions: Dict[int, float],
               as_of_gw: int) -> Dict[int, float]:
        """xP' = P(plays) x xP, with P(plays) as of the DECISION GW."""
        return {pid: xp * self.prob(pid, as_of_gw)
                for pid, xp in predictions.items()}

    def multipliers(self, player_ids, as_of_gw: int) -> Dict[int, float]:
        return {pid: self.prob(pid, as_of_gw) for pid in player_ids}
