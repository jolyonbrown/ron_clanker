"""
LiveOptimizerStrategy — the live decision pipeline wrapped as a backtest
Strategy, so optimizer code changes can be A/B tested against a recorded
season before they ever pick a real team.

What runs for real (the code under test):
    - services/squad_optimizer.py MILP squad build (initial squad via the
      wildcard path: multi-GW horizon, time decay, blank-GW filter)
    - agents/transfer_optimizer.py weekly transfer decisions (position
      scans, replacement search, roll-vs-make thresholds, multi-transfer
      greedy)
    - services/squad_optimizer.py optimize_starting_xi MILP for lineups

What is shimmed, and why:
    - The live services read the players table for prices and injury
      status. Those are END-OF-SEASON values — lookahead. EraDatabase is
      a scratch copy of the schema whose players rows are re-priced from
      the walk-forward price map before every decision; status flags are
      neutralised ('a' for priceable players, 'u' for unpriceable ones).
    - TransferOptimizer._get_multi_gw_predictions normally re-runs the
      ML synthesis engine (current models = lookahead, ~9 min/GW). The
      subclass reads the stored player_predictions instead — the same
      numbers the live system had before each deadline.
    - identify_unavailable_players returns [] : there is no historical
      injury-status record, and the stored predictions already encode
      what was known about availability at the time.

Known fidelity gaps (accepted, documented):
    - Horizon predictions (gw+1..gw+3) are the FINAL pre-GW stored
      values — slightly fresher than the live system would have had at
      gw. Mild optimism in multi-GW planning.
    - Captain is the top stored xP in the XI, not the live
      ceiling-bonus captain model (whose pickle is post-season anyway).
    - Chips are not wrapped yet; this strategy plays chipless.
    - Ownership-based risk adjustment is inert (MODERATE default).

Illegal recommendations from the live code (club rule, budget) are
VETOED so the season can finish, but counted and logged loudly — a veto
is a live-code defect surfaced by the backtest, not noise.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set

from agents.transfer_optimizer import TransferOptimizer
from data.database import Database
from services.squad_optimizer import SquadOptimizer

from backtest.data import HistoricalDataProvider
from backtest.scoring import Pick
from backtest.state import OwnedPlayer, sell_price
from backtest.strategy import AsOfView, GWDecision, InitialSquad, Strategy

logger = logging.getLogger('ron_clanker.backtest.live_strategy')

ERA_DB_PATH = Path(__file__).resolve().parent.parent / 'data' / '.backtest_era.db'


class EraDatabase:
    """A scratch database the live services can query, re-priced per GW.

    Copies teams/fixtures/players from the source DB once, then refresh()
    overwrites players.now_cost from the walk-forward price map and
    neutralises status fields before each decision.
    """

    def __init__(self, source_db_path: Path, era_path: Path = ERA_DB_PATH):
        self.path = Path(era_path)
        if self.path.exists():
            self.path.unlink()
        self.db = Database(str(self.path))   # creates empty schema
        self._copy_tables(source_db_path, ('teams', 'players', 'fixtures'))

    def _copy_tables(self, source: Path, tables) -> None:
        src = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
        dst = sqlite3.connect(self.path)
        try:
            for table in tables:
                src_cols = [r[1] for r in src.execute(f'PRAGMA table_info({table})')]
                dst_cols = {r[1] for r in dst.execute(f'PRAGMA table_info({table})')}
                cols = [c for c in src_cols if c in dst_cols]
                rows = src.execute(
                    f'SELECT {", ".join(cols)} FROM {table}'
                ).fetchall()
                dst.executemany(
                    f'INSERT OR REPLACE INTO {table} ({", ".join(cols)}) '
                    f'VALUES ({", ".join("?" * len(cols))})',
                    rows,
                )
            dst.commit()
        finally:
            src.close()
            dst.close()

    def refresh(self, prices: Dict[int, int]) -> None:
        """Re-price every player for the current decision gameweek."""
        con = sqlite3.connect(self.path)
        try:
            con.execute(
                "UPDATE players SET status = 'a', "
                "chance_of_playing_next_round = NULL"
            )
            con.executemany(
                "UPDATE players SET now_cost = ? WHERE id = ?",
                [(price, pid) for pid, price in prices.items()],
            )
            # No era price -> can't be bought at a fair price -> exclude.
            placeholders = ','.join('?' * len(prices))
            con.execute(
                f"UPDATE players SET status = 'u' "
                f"WHERE id NOT IN ({placeholders})",
                list(prices),
            )
            con.commit()
        finally:
            con.close()

    def cleanup(self) -> None:
        if self.path.exists():
            self.path.unlink()


class _BacktestTransferOptimizer(TransferOptimizer):
    """The real TransferOptimizer with its two era-unsafe seams replaced."""

    def __init__(self, database: Database, predictions_lookup):
        super().__init__(database, chip_strategy=None)
        self.verbose = False
        self._predictions_lookup = predictions_lookup   # fn(gw) -> {pid: xp}

    def _get_multi_gw_predictions(self, start_gw: int, horizon: int):
        multi: Dict[int, Dict[int, float]] = {}
        for gw in range(start_gw, start_gw + horizon):
            for pid, xp in self._predictions_lookup(gw).items():
                multi.setdefault(pid, {})[gw] = xp
        return multi

    def identify_unavailable_players(self, current_team: List[Dict]) -> List[Dict]:
        # No historical status record; stored predictions encode what was
        # known about availability at each deadline.
        return []


class LiveOptimizerStrategy(Strategy):
    name = 'live-optimizer'

    def __init__(self, provider: HistoricalDataProvider, horizon: int = 4):
        self._provider = provider
        self._horizon = horizon
        self._era = EraDatabase(provider.db_path)
        self._squad_opt = SquadOptimizer(self._era.db)
        self._transfer_opt = _BacktestTransferOptimizer(
            self._era.db, provider.predictions
        )
        self._etypes = provider.player_element_types()
        self._teams = provider.player_team_ids()
        self._names = provider.player_names()
        self.vetoed: List[str] = []   # live-code defects surfaced in replay

    def close(self) -> None:
        self._era.cleanup()

    # ------------------------------------------------------------------

    def _multi_gw_predictions(self, gameweek: int) -> Dict[int, Dict[int, float]]:
        multi: Dict[int, Dict[int, float]] = {}
        for gw in range(gameweek, gameweek + self._horizon):
            for pid, xp in self._provider.predictions(gw).items():
                multi.setdefault(pid, {})[gw] = xp
        return multi

    def initial_squad(self, gameweek: int, view: AsOfView) -> InitialSquad:
        self._era.refresh(view.prices())
        squad = self._squad_opt.optimize_wildcard(
            gameweek=gameweek,
            current_squad=[],          # fresh entry: no selling value
            bank=100.0,                # £100m budget
            multi_gw_predictions=self._multi_gw_predictions(gameweek),
            horizon=self._horizon,
            verbose=False,
        )
        purchases = {p['id']: p['now_cost'] for p in squad.players}
        picks = self._build_picks(set(purchases), gameweek, view)
        return InitialSquad(purchases=purchases, picks=picks)

    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        prices = view.prices()
        self._era.refresh(prices)

        squad: Dict[int, OwnedPlayer] = dict(state_info['squad'])
        current_team = []
        for pid, owned in squad.items():
            price = prices.get(pid, owned.purchase_price)
            current_team.append({
                'player_id': pid,
                'id': pid,
                'web_name': self._names.get(pid, str(pid)),
                'element_type': self._etypes[pid],
                'now_cost': price,
                'selling_price': sell_price(owned.purchase_price, price),
            })

        result = self._transfer_opt.optimize_transfers(
            current_team=current_team,
            ml_predictions={},
            current_gw=gameweek,
            free_transfers=state_info['available_ft'],
            bank=state_info['bank'] / 10.0,
            horizon=self._horizon,
        )

        transfers = self._vet_transfers(
            gameweek, result['recommended_transfers'], squad,
            state_info['bank'], prices,
        )

        squad_ids = set(squad)
        for t in transfers:
            squad_ids.discard(t.out_id)
            squad_ids.add(t.in_id)

        picks = self._build_picks(squad_ids, gameweek, view)
        return GWDecision(transfers=transfers, chip=None, picks=picks)

    # ------------------------------------------------------------------

    def _vet_transfers(self, gameweek, options, squad, bank, prices):
        """Mirror the simulator's rules over the live recommendations.
        Anything vetoed here is a defect in the live optimizer — counted
        and logged, never silently fixed."""
        from backtest.state import MAX_PER_CLUB, Transfer

        club_counts: Dict[Optional[int], int] = {}
        for pid in squad:
            club = self._teams.get(pid)
            club_counts[club] = club_counts.get(club, 0) + 1

        accepted: List[Transfer] = []
        owned = dict(squad)
        for opt in options:
            out_id, in_id = opt.player_out_id, opt.player_in_id
            veto = None
            if out_id not in owned:
                veto = f'sells {out_id} not in squad'
            elif in_id in owned:
                veto = f'buys {in_id} already in squad'
            else:
                pay = prices.get(in_id)
                receive = sell_price(
                    owned[out_id].purchase_price,
                    prices.get(out_id, owned[out_id].purchase_price),
                )
                in_club = self._teams.get(in_id)
                out_club = self._teams.get(out_id)
                new_count = club_counts.get(in_club, 0) + 1 \
                    - (1 if in_club == out_club else 0)
                if pay is None:
                    veto = f'no price for incoming {in_id}'
                elif bank + receive - pay < 0:
                    veto = (f'budget: bank {bank} + sell {receive} '
                            f'< buy {pay}')
                elif new_count > MAX_PER_CLUB:
                    veto = f'club rule: {new_count} from club {in_club}'

            if veto:
                msg = (f"GW{gameweek}: VETOED live recommendation "
                       f"{self._names.get(out_id, out_id)} -> "
                       f"{self._names.get(in_id, in_id)} ({veto})")
                logger.error(msg)
                self.vetoed.append(msg)
                continue

            bank += receive - pay
            del owned[out_id]
            owned[in_id] = OwnedPlayer(player_id=in_id, purchase_price=pay)
            club_counts[out_club] = club_counts.get(out_club, 1) - 1
            club_counts[in_club] = club_counts.get(in_club, 0) + 1
            accepted.append(Transfer(out_id=out_id, in_id=in_id))
        return accepted

    # ------------------------------------------------------------------

    def _build_picks(self, squad_ids: Set[int], gameweek: int,
                     view: AsOfView) -> List[Pick]:
        preds = self._provider.predictions(gameweek)
        prices = view.prices()
        players = [
            {
                'id': pid,
                'player_id': pid,
                'web_name': self._names.get(pid, str(pid)),
                'element_type': self._etypes[pid],
                'now_cost': prices.get(pid, 0),
                'xP': preds.get(pid, 0.0),
            }
            for pid in squad_ids
        ]
        starting, bench = self._squad_opt.optimize_starting_xi(players)
        ranked = sorted(starting, key=lambda p: -p.get('xP', 0.0))
        captain, vice = ranked[0]['id'], ranked[1]['id']
        return [
            Pick(
                player_id=p['id'],
                position=p['position'],
                element_type=p['element_type'],
                is_captain=(p['id'] == captain),
                is_vice_captain=(p['id'] == vice),
            )
            for p in starting + bench
        ]
