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
      gw. Mild optimism in multi-GW planning. The chip planner sees the
      same freshness across its whole window.
    - Captain is the top stored xP in the XI, not the live
      ceiling-bonus captain model (whose pickle is post-season anyway).
    - Ownership-based risk adjustment is inert (MODERATE default).

Two strategies are exported: LiveOptimizerStrategy plays chipless;
LiveOptimizerWithChipsStrategy adds the real ChipStrategyService
(services/chip_strategy.py) deciding chip timing each gameweek. Both
bugs the chip replay surfaced on first run — optimize_free_hit assuming
a fresh £100m budget, and TransferOptimizer ignoring the max-3-per-club
rule — are fixed in the live code (2026-06-10).

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
from services.chip_availability import ChipAvailabilityService, ChipDefinition
from services.chip_strategy import (
    BENCH_BOOST,
    FREE_HIT,
    TRIPLE_CAPTAIN,
    WILDCARD,
    ChipStrategyService,
)
from services.squad_optimizer import SquadOptimizer

from backtest.data import HistoricalDataProvider
from backtest.scoring import Pick
from backtest.state import OwnedPlayer, Transfer, sell_price
from backtest.strategy import AsOfView, GWDecision, InitialSquad, Strategy

logger = logging.getLogger('ron_clanker.backtest.live_strategy')

ERA_DB_PATH = Path(__file__).resolve().parent.parent / 'data' / '.backtest_era.db'


class EraDatabase:
    """A scratch database the live services can query, re-priced per GW.

    Copies teams/fixtures/players from the source DB once, then refresh()
    overwrites players.now_cost from the walk-forward price map and
    neutralises status fields before each decision.
    """

    @staticmethod
    def _connect(path) -> sqlite3.Connection:
        # Scratch data, rewritten every gameweek — trade durability for
        # speed (per-GW shrinkage rewrites 18k prediction rows).
        con = sqlite3.connect(path)
        con.execute("PRAGMA synchronous = OFF")
        con.execute("PRAGMA journal_mode = MEMORY")
        return con

    def __init__(self, source_db_path: Path, era_path: Path = ERA_DB_PATH):
        self.path = Path(era_path)
        if self.path.exists():
            self.path.unlink()
        self.db = Database(str(self.path))   # creates empty schema
        # player_predictions is the walk-forward-safe store the live chip
        # strategy queries directly; copying it lets those query paths run
        # unmodified.
        self._copy_tables(
            source_db_path,
            ('teams', 'players', 'fixtures', 'player_predictions'),
        )
        self._normalize_dgw_predictions()
        # Keep the (normalized) raw values so calibration can be
        # re-applied per decision gameweek without compounding.
        con = self._connect(self.path)
        try:
            con.execute("ALTER TABLE player_predictions ADD COLUMN raw_xp REAL")
            con.execute("UPDATE player_predictions SET raw_xp = predicted_points")
            con.commit()
        finally:
            con.close()

    def _normalize_dgw_predictions(self) -> None:
        """Restore the GW-total contract (commit 06551f0) on the copied
        predictions: the whole 2025-26 store predates the fix and holds
        per-fixture values, which makes double gameweeks look WORSE than
        normal ones. Multiplying by the team's fixture count gives the
        numbers next season's pipeline stores natively (doubles ×2,
        blanks ×0)."""
        con = self._connect(self.path)
        try:
            con.execute("""
                UPDATE player_predictions SET predicted_points =
                    predicted_points * (
                        SELECT COUNT(*) FROM fixtures f
                        JOIN players p ON p.id = player_predictions.player_id
                        WHERE f.event = player_predictions.gameweek
                          AND (f.team_h = p.team_id OR f.team_a = p.team_id)
                    )
            """)
            con.commit()
        finally:
            con.close()

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
        con = self._connect(self.path)
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

    def apply_shrinkage(self, params: Optional[Dict[int, tuple]]) -> None:
        """Rewrite predicted_points = max(0, a + b*raw) per position with
        the given walk-forward calibration params, or restore raw values
        when params is None (insufficient history)."""
        con = self._connect(self.path)
        try:
            if params is None:
                con.execute(
                    "UPDATE player_predictions SET predicted_points = raw_xp"
                )
            else:
                for et, (a, b) in params.items():
                    con.execute(
                        "UPDATE player_predictions "
                        "SET predicted_points = MAX(0, ? + ? * raw_xp) "
                        "WHERE player_id IN "
                        "  (SELECT id FROM players WHERE element_type = ?)",
                        (a, b, et),
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

    def __init__(self, provider: HistoricalDataProvider, horizon: int = 4,
                 shrink_predictions: bool = False):
        self._provider = provider
        self._horizon = horizon
        self._era = EraDatabase(provider.db_path)
        self._squad_opt = SquadOptimizer(self._era.db)
        self._transfer_opt = _BacktestTransferOptimizer(
            self._era.db, self._predictions_for
        )
        self._etypes = provider.player_element_types()
        self._teams = provider.player_team_ids()
        self._names = provider.player_names()
        self.vetoed: List[str] = []   # live-code defects surfaced in replay
        # Winner's-curse correction: walk-forward per-position calibration
        # applied to every prediction the decision code consumes.
        # Measured trade-off (2025-26): shrinking EVERYTHING costs ~31 pts
        # because the transfer optimizer's thresholds are tuned to raw
        # scale, while shrinking chip EV only keeps the transfer engine
        # intact and makes chip timing robust.
        self._shrinker = None        # applied at every seam
        self._era_shrinker = None    # applied to the era DB only (chip EV)
        if shrink_predictions:
            from backtest.calibration import PredictionShrinker
            self._shrinker = PredictionShrinker(provider)
            self.name = f'{self.name}+shrink'
        self._decision_gw: int = 0

    def close(self) -> None:
        self._era.cleanup()

    # ------------------------------------------------------------------

    def _predictions_for(self, target_gw: int) -> Dict[int, float]:
        """Predictions for a target GW, calibrated with parameters known
        at the DECISION gameweek (never the target — that would leak
        actuals that don't exist yet at the deadline)."""
        preds = self._provider.predictions(target_gw)
        if self._shrinker:
            preds = self._shrinker.shrink(preds, as_of_gw=self._decision_gw)
        return preds

    def _refresh_era(self, gameweek: int, view: AsOfView) -> None:
        self._decision_gw = gameweek
        self._era.refresh(view.prices())
        shrinker = self._era_shrinker or self._shrinker
        if shrinker:
            self._era.apply_shrinkage(shrinker.params_as_of(gameweek))

    def _multi_gw_predictions(self, gameweek: int) -> Dict[int, Dict[int, float]]:
        multi: Dict[int, Dict[int, float]] = {}
        for gw in range(gameweek, gameweek + self._horizon):
            for pid, xp in self._predictions_for(gw).items():
                multi.setdefault(pid, {})[gw] = xp
        return multi

    def initial_squad(self, gameweek: int, view: AsOfView) -> InitialSquad:
        self._refresh_era(gameweek, view)
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

    def _current_team_dicts(self, squad: Dict[int, OwnedPlayer],
                            prices: Dict[int, int]) -> List[Dict]:
        team = []
        for pid, owned in squad.items():
            price = prices.get(pid, owned.purchase_price)
            team.append({
                'player_id': pid,
                'id': pid,
                'web_name': self._names.get(pid, str(pid)),
                'element_type': self._etypes[pid],
                'now_cost': price,
                'selling_price': sell_price(owned.purchase_price, price),
            })
        return team

    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        prices = view.prices()
        self._refresh_era(gameweek, view)

        squad: Dict[int, OwnedPlayer] = dict(state_info['squad'])
        current_team = self._current_team_dicts(squad, prices)

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
        from backtest.state import MAX_PER_CLUB

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
                     view: AsOfView,
                     captain_override: Optional[int] = None) -> List[Pick]:
        preds = self._predictions_for(gameweek)
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
        starter_ids = {p['id'] for p in starting}
        if captain_override is not None and captain_override in starter_ids:
            if captain_override != captain:
                captain, vice = captain_override, ranked[0]['id']
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


class _SimChipAvailability(ChipAvailabilityService):
    """ChipAvailabilityService with its two FPL-API seams replaced.

    Definitions come from the season archive's bootstrap snapshot (the
    real 2025/26 windows); used chips come from the simulator's entry
    state, set before each decision. The window/instance-matching logic
    in get_available_chips runs unmodified.
    """

    def __init__(self, definitions: List[Dict]):
        super().__init__()
        self._defs = [ChipDefinition(**d) for d in definitions]
        self.used: List[Dict] = []   # [{'name': chip, 'event': gw}]

    def get_chip_definitions(self, force_refresh: bool = False):
        return self._defs

    def _fetch_used_chips(self, team_id: int) -> List[Dict]:
        return list(self.used)


class LiveOptimizerWithChipsStrategy(LiveOptimizerStrategy):
    """Layer-3 strategy plus the live ChipStrategyService deciding chips.

    The real horizon-based chip engine (services/chip_strategy.py) runs
    each gameweek: per-chip EV curves over the remaining window, hold-vs-
    play thresholds, forced-chip handling. Wildcard/Free Hit squads are
    rebuilt with the real MILP optimizer.

    Chip transfers are batch-vetted (total affordability) rather than
    per-transfer — batches may dip negative transiently, like Ron's real
    GW19 wildcard did. A failed batch vetoes the WHOLE chip and falls
    back to the chipless decision: that veto is a live-code defect (e.g.
    optimize_free_hit assumes a fresh £100m, but FPL's Free Hit budget
    is selling value + bank).
    """

    name = 'live-optimizer+chips'

    def __init__(self, provider: HistoricalDataProvider, horizon: int = 4,
                 shrink_predictions: bool = True,
                 shrink_chip_ev: bool = False):
        """Full prediction shrinkage is the DEFAULT for the chip-aware
        strategy: it was the only configuration in the 2025-26 A/B that
        was both strong and robust — 1739 points regardless of the
        wc_organic_gain knob (raw peaked at 1770 but collapsed to 1618
        one knob-notch away; chip-EV-only and EV+rebuild hybrids scored
        1624-1720 and stayed knob-sensitive). shrink_chip_ev=True with
        shrink_predictions=False gives the hybrid (era DB + WC/FH
        rebuild inputs calibrated, weekly transfers raw) for A/B use."""
        super().__init__(provider, horizon=horizon,
                         shrink_predictions=shrink_predictions)
        if shrink_chip_ev and not shrink_predictions:
            from backtest.calibration import PredictionShrinker
            self._era_shrinker = PredictionShrinker(provider)
            self.name = f'{self.name}+chipcal'
        definitions = provider.chip_definitions()
        if not definitions:
            raise RuntimeError(
                "LiveOptimizerWithChipsStrategy needs chip definitions "
                "from the season archive bootstrap — none found"
            )
        self._avail = _SimChipAvailability(definitions)
        self._chip_service = ChipStrategyService(
            database=self._era.db,
            squad_optimizer=self._squad_opt,
            availability_service=self._avail,
        )
        self.chip_log: List = []   # (gw, {chip: {use, ev_now, best_alt...}})

    # ------------------------------------------------------------------
    # Chip EXECUTION predictions: WC/FH rebuilds are 15 simultaneous
    # argmax bets — calibrated inputs build measurably better squads,
    # while the weekly transfer engine stays on the raw scale.

    def _chip_execution_predictions(self, target_gw: int) -> Dict[int, float]:
        preds = self._provider.predictions(target_gw)
        shrinker = self._era_shrinker or self._shrinker
        if shrinker:
            preds = shrinker.shrink(preds, as_of_gw=self._decision_gw)
        return preds

    def _chip_multi_gw_predictions(self, gameweek: int) -> Dict[int, Dict[int, float]]:
        multi: Dict[int, Dict[int, float]] = {}
        for gw in range(gameweek, gameweek + self._horizon):
            for pid, xp in self._chip_execution_predictions(gw).items():
                multi.setdefault(pid, {})[gw] = xp
        return multi

    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        prices = view.prices()
        self._refresh_era(gameweek, view)
        squad: Dict[int, OwnedPlayer] = dict(state_info['squad'])

        # The chip planner needs positions (bench detection drives BB EV),
        # so give it the would-be lineup of the current squad.
        pre_picks = self._build_picks(set(squad), gameweek, view)
        positions = {p.player_id: p.position for p in pre_picks}
        team_dicts = self._current_team_dicts(squad, prices)
        for d in team_dicts:
            d['position'] = positions.get(d['id'], 0)

        self._avail.used = [
            {'name': chip, 'event': gw} for gw, chip in state_info['chips_used']
        ]
        all_decisions = self._chip_service.get_chip_decision(
            team_id=0,
            gameweek=gameweek,
            squad=team_dicts,
            transfers_needed=0,
            free_transfers=state_info['available_ft'],
            bank=state_info['bank'] / 10.0,
        )
        self.chip_log.append((gameweek, {
            name: {
                'use': d.use_chip,
                'ev_now': d.expected_value,
                'best_alt_gw': d.best_alternative_gw,
                'best_alt_ev': d.best_alternative_ev,
                'reason': d.reason,
            }
            for name, d in all_decisions.items()
        }))
        playable = [d for d in all_decisions.values() if d.use_chip]
        urgency_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'NONE': 0}
        playable.sort(
            key=lambda d: (urgency_rank.get(d.urgency, 0), d.expected_value),
            reverse=True,
        )
        decision = playable[0] if playable else None
        chip = decision.chip_name if decision else None

        if chip == WILDCARD:
            rebuilt = self._squad_opt.optimize_wildcard(
                gameweek=gameweek,
                current_squad=team_dicts,
                bank=state_info['bank'] / 10.0,
                multi_gw_predictions=self._chip_multi_gw_predictions(gameweek),
                horizon=self._horizon,
                verbose=False,
            )
            chip_decision = self._squad_swap_decision(
                gameweek, squad, {p['id'] for p in rebuilt.players},
                chip, state_info['bank'], prices, view,
            )
            if chip_decision is not None:
                return chip_decision
            chip = None   # batch vetoed — fall through chipless

        elif chip == FREE_HIT:
            selling_value = sum(d['selling_price'] for d in team_dicts)
            fh = self._squad_opt.optimize_free_hit(
                gameweek=gameweek,
                predictions=self._chip_execution_predictions(gameweek),
                verbose=False,
                budget=selling_value + state_info['bank'],
            )
            chip_decision = self._squad_swap_decision(
                gameweek, squad, {p['id'] for p in fh.players},
                chip, state_info['bank'], prices, view,
            )
            if chip_decision is not None:
                return chip_decision
            chip = None

        # No chip, or a team chip (BB/TC): normal weekly transfer logic.
        base = super().decide(gameweek, state_info, view)
        if chip == BENCH_BOOST:
            base.chip = chip
        elif chip == TRIPLE_CAPTAIN:
            base.chip = chip
            if decision.captain_override is not None:
                squad_ids = set(squad)
                for t in base.transfers:
                    squad_ids.discard(t.out_id)
                    squad_ids.add(t.in_id)
                base.picks = self._build_picks(
                    squad_ids, gameweek, view,
                    captain_override=decision.captain_override,
                )
        return base

    def _squad_swap_decision(
        self, gameweek: int, squad: Dict[int, OwnedPlayer],
        new_ids: Set[int], chip: str, bank: int,
        prices: Dict[int, int], view: AsOfView,
    ) -> Optional[GWDecision]:
        """Turn a WC/FH rebuild into transfers, batch-vetting affordability.
        Returns None if the batch is unaffordable (live-code defect; the
        chip is vetoed and the caller falls back to a chipless decision)."""
        outs = sorted(set(squad) - new_ids)
        ins = sorted(new_ids - set(squad))
        received = sum(
            sell_price(squad[pid].purchase_price,
                       prices.get(pid, squad[pid].purchase_price))
            for pid in outs
        )
        paid = sum(prices.get(pid, 0) for pid in ins)
        missing = [pid for pid in ins if pid not in prices]
        if missing or bank + received - paid < 0:
            why = (f'no price for {missing}' if missing else
                   f'batch unaffordable: bank {bank} + sell {received} '
                   f'< buy {paid}')
            msg = (f"GW{gameweek}: VETOED {chip} rebuild "
                   f"({len(outs)} out / {len(ins)} in): {why}")
            logger.error(msg)
            self.vetoed.append(msg)
            return None

        transfers = [
            Transfer(out_id=o, in_id=i) for o, i in zip(outs, ins)
        ]
        picks = self._build_picks(new_ids, gameweek, view)
        return GWDecision(transfers=transfers, chip=chip, picks=picks)
