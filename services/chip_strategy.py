"""
Chip Strategy Service

Horizon-based chip decision engine. For each available chip, computes
expected value (EV) in every remaining gameweek of the chip's window,
then decides whether to play the chip THIS gameweek or hold for a
higher-EV future opportunity.

Key behaviours vs the previous point-in-time heuristic version:
- Reads `player_predictions` for real per-player per-GW xP instead of
  hardcoded magic numbers.
- Evaluates every candidate GW in each chip's remaining window, not
  just the current one.
- Bench Boost EV is the sum of bench xP for the target GW (no more
  "GW 32-34? fire it" shortcut).
- Triple Captain searches all 15 squad players for the best TC target
  and can return a `captain_override` when the best target is not the
  pre-chosen captain.
- Free Hit EV is `optimal_XI(gw) - current_XI(gw)` using the existing
  SquadOptimizer; fires on DGW-unready squads, not only on BGWs.
- Wildcard EV is a 4-GW horizon uplift over the current squad;
  fires proactively in front of fixture swings.
- Deadline pressure forces BB/TC/FH/WC — previously only WC/FH.

Public API is backwards-compatible with the old module:
    service = ChipStrategyService(database)
    decisions = service.get_chip_decision(team_id, gameweek, squad, ...)
    best = service.get_recommended_chip(team_id, gameweek, squad, ...)

New method for annual/seasonal visibility:
    plans = service.plan_all_chips(team_id, current_gw, squad, free_transfers, bank)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.chip_availability import ChipAvailabilityService, ChipStatus

logger = logging.getLogger(__name__)

# Chip names (FPL API values)
WILDCARD = 'wildcard'
FREE_HIT = 'freehit'
BENCH_BOOST = 'bboost'
TRIPLE_CAPTAIN = '3xc'

TRANSFER_CHIPS = {WILDCARD, FREE_HIT}
TEAM_CHIPS = {BENCH_BOOST, TRIPLE_CAPTAIN}

# Element-type ids used by FPL
POS_GKP, POS_DEF, POS_MID, POS_FWD = 1, 2, 3, 4

# Formation constraints for starting XI
FORMATION_MIN = {POS_GKP: 1, POS_DEF: 3, POS_MID: 2, POS_FWD: 1}
FORMATION_MAX = {POS_GKP: 1, POS_DEF: 5, POS_MID: 5, POS_FWD: 3}

# How many GWs ahead to evaluate for each chip type
FH_HORIZON_GWS = 6    # look at next 6 GWs for FH opportunities
WC_HORIZON_GWS = 4    # WC evaluates 4-GW uplift starting from each candidate GW
WC_LOOKAHEAD_GWS = 6  # and considers starting WC in next 6 GWs

# Bench Boost xP haircut for autosub realism (without BB, some bench xP
# already lands via autosubs when XI players don't play).
BB_AUTOSUB_HAIRCUT = 0.8


@dataclass
class ChipDecision:
    """Result of a single chip's evaluation for THIS gameweek."""
    use_chip: bool
    chip_name: Optional[str]
    chip_display_name: Optional[str]
    reason: str
    urgency: str  # 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
    replaces_transfers: bool
    expected_value: float
    # Forward-looking extensions
    best_alternative_gw: Optional[int] = None
    best_alternative_ev: Optional[float] = None
    # Triple Captain can ask the manager to swap the captain
    captain_override: Optional[int] = None
    captain_override_name: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'use_chip': self.use_chip,
            'chip_name': self.chip_name,
            'chip_display_name': self.chip_display_name,
            'reason': self.reason,
            'urgency': self.urgency,
            'replaces_transfers': self.replaces_transfers,
            'expected_value': self.expected_value,
            'best_alternative_gw': self.best_alternative_gw,
            'best_alternative_ev': self.best_alternative_ev,
            'captain_override': self.captain_override,
            'captain_override_name': self.captain_override_name,
        }


@dataclass
class ChipPlan:
    """Forward-looking plan for a single chip across its remaining window."""
    chip_name: str
    chip_display_name: str
    best_gw: Optional[int]
    best_gw_ev: float
    ev_by_gw: Dict[int, float] = field(default_factory=dict)
    captain_target_by_gw: Dict[int, Tuple[int, str]] = field(default_factory=dict)
    expires_at_gw: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            'chip_name': self.chip_name,
            'chip_display_name': self.chip_display_name,
            'best_gw': self.best_gw,
            'best_gw_ev': self.best_gw_ev,
            'ev_by_gw': self.ev_by_gw,
            'captain_target_by_gw': {
                gw: {'player_id': pid, 'name': name}
                for gw, (pid, name) in self.captain_target_by_gw.items()
            },
            'expires_at_gw': self.expires_at_gw,
            'notes': self.notes,
        }


class ChipStrategyService:
    """
    Horizon-based chip decision engine.

    For each call to `get_chip_decision` or `get_recommended_chip`, the
    service builds a per-chip EV curve across the chip's remaining
    window, then decides whether the current GW is the right moment
    to fire — or if holding for a better future GW is preferable.
    """

    def __init__(self, database=None, squad_optimizer=None, availability_service=None):
        self.db = database
        self.availability = availability_service or ChipAvailabilityService()
        self._optimizer = squad_optimizer  # lazily constructed if None

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def get_chip_decision(
        self,
        team_id: int,
        gameweek: int,
        squad: List[Dict[str, Any]],
        transfers_needed: int = 0,
        free_transfers: int = 1,
        captain_xp: float = 0.0,  # kept for backwards compat; unused
        bench_xp: float = 0.0,    # kept for backwards compat; unused
        bank: float = 0.0,
    ) -> Dict[str, ChipDecision]:
        """
        Evaluate every available chip for THIS gameweek.

        Returns a dict mapping chip_name -> ChipDecision. Each decision
        carries `use_chip`, EV, and (if applicable) the best alternative
        future GW so you can see what you're holding out for.
        """
        del captain_xp, bench_xp  # back-compat only, no longer used

        plans = self.plan_all_chips(
            team_id=team_id,
            current_gw=gameweek,
            squad=squad,
            free_transfers=free_transfers,
            bank=bank,
            transfers_needed=transfers_needed,
        )

        chip_statuses = {
            c.definition.name: c
            for c in self.availability.get_available_chips(team_id, gameweek)
        }

        decisions: Dict[str, ChipDecision] = {}
        for chip_name, plan in plans.items():
            status = chip_statuses.get(chip_name)
            if status is None:
                continue
            decisions[chip_name] = self._decide_from_plan(
                chip_name=chip_name,
                status=status,
                plan=plan,
                current_gw=gameweek,
                chips_available=len([c for c in chip_statuses.values() if c.available_now]),
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
        bank: float = 0.0,
    ) -> Optional[ChipDecision]:
        """Return the single best chip to play THIS GW, or None to hold."""
        decisions = self.get_chip_decision(
            team_id=team_id,
            gameweek=gameweek,
            squad=squad,
            transfers_needed=transfers_needed,
            free_transfers=free_transfers,
            captain_xp=captain_xp,
            bench_xp=bench_xp,
            bank=bank,
        )

        playable = [d for d in decisions.values() if d.use_chip]
        if not playable:
            return None

        urgency_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'NONE': 0}
        playable.sort(
            key=lambda d: (urgency_rank.get(d.urgency, 0), d.expected_value),
            reverse=True,
        )
        return playable[0]

    def plan_all_chips(
        self,
        team_id: int,
        current_gw: int,
        squad: List[Dict[str, Any]],
        free_transfers: int = 1,
        bank: float = 0.0,
        transfers_needed: int = 0,
    ) -> Dict[str, ChipPlan]:
        """
        Build a forward-looking plan for every available chip.

        For each chip, evaluates EV in every remaining GW of its window
        (bounded by the chip's `stop_event`) and identifies the best-EV GW.
        Used by `chip_plan_report.py` and internally by `get_chip_decision`.
        """
        statuses = self.availability.get_available_chips(team_id, current_gw)
        squad_meta = self._enrich_squad(squad)

        plans: Dict[str, ChipPlan] = {}
        for status in statuses:
            if not status.available_now:
                continue
            name = status.definition.name
            window = self._remaining_window(status, current_gw)
            if not window:
                continue

            try:
                if name == WILDCARD:
                    plans[name] = self._plan_wildcard(
                        status, current_gw, window, squad_meta, bank, transfers_needed,
                    )
                elif name == FREE_HIT:
                    plans[name] = self._plan_free_hit(
                        status, current_gw, window, squad_meta,
                    )
                elif name == BENCH_BOOST:
                    plans[name] = self._plan_bench_boost(
                        status, current_gw, window, squad_meta,
                    )
                elif name == TRIPLE_CAPTAIN:
                    plans[name] = self._plan_triple_captain(
                        status, current_gw, window, squad_meta,
                    )
            except Exception as exc:  # pragma: no cover - log & skip
                logger.warning("ChipStrategy: plan for %s failed: %s", name, exc)

        return plans

    # ------------------------------------------------------------------
    # PLAN BUILDERS (one per chip)
    # ------------------------------------------------------------------

    def _plan_bench_boost(
        self,
        status: ChipStatus,
        current_gw: int,
        window: List[int],
        squad: List[Dict[str, Any]],
    ) -> ChipPlan:
        """BB EV = sum of bench xP for that GW (haircut for autosubs)."""
        bench_ids = [p['id'] for p in squad if p.get('is_bench')]
        # Evaluate each GW in the window
        ev_by_gw: Dict[int, float] = {}
        for gw in window:
            preds = self._predictions_for_gw(gw, bench_ids)
            ev = sum(preds.values()) * BB_AUTOSUB_HAIRCUT
            ev_by_gw[gw] = round(ev, 2)

        best_gw, best_ev = self._argmax(ev_by_gw)
        return ChipPlan(
            chip_name=BENCH_BOOST,
            chip_display_name=status.definition.display_name,
            best_gw=best_gw,
            best_gw_ev=best_ev,
            ev_by_gw=ev_by_gw,
            expires_at_gw=status.definition.stop_event,
            notes=f"Best bench total across remaining window (current bench: {len(bench_ids)}/4)",
        )

    def _plan_triple_captain(
        self,
        status: ChipStatus,
        current_gw: int,
        window: List[int],
        squad: List[Dict[str, Any]],
    ) -> ChipPlan:
        """
        TC EV = max xP over any squad player for that GW.

        Extra value over a normal captain pick ≈ max_xP (3× vs 2×).
        If best TC target differs from pre-chosen captain, records that
        as captain_override.
        """
        squad_ids = [p['id'] for p in squad]
        id_to_name = {p['id']: p.get('web_name', str(p['id'])) for p in squad}

        ev_by_gw: Dict[int, float] = {}
        target_by_gw: Dict[int, Tuple[int, str]] = {}
        for gw in window:
            preds = self._predictions_for_gw(gw, squad_ids)
            if not preds:
                ev_by_gw[gw] = 0.0
                continue
            best_pid = max(preds, key=preds.get)
            ev = preds[best_pid]
            ev_by_gw[gw] = round(ev, 2)
            target_by_gw[gw] = (best_pid, id_to_name.get(best_pid, str(best_pid)))

        best_gw, best_ev = self._argmax(ev_by_gw)
        return ChipPlan(
            chip_name=TRIPLE_CAPTAIN,
            chip_display_name=status.definition.display_name,
            best_gw=best_gw,
            best_gw_ev=best_ev,
            ev_by_gw=ev_by_gw,
            captain_target_by_gw=target_by_gw,
            expires_at_gw=status.definition.stop_event,
            notes="TC search considers all 15 squad players, not just pre-chosen captain",
        )

    def _plan_free_hit(
        self,
        status: ChipStatus,
        current_gw: int,
        window: List[int],
        squad: List[Dict[str, Any]],
    ) -> ChipPlan:
        """
        FH EV = xP(optimal_FH_squad_XI, gw) - xP(current_XI, gw).

        Uses SquadOptimizer.optimize_free_hit for the hypothetical squad.
        Evaluated for at most FH_HORIZON_GWS ahead to cap optimizer cost.
        """
        # Cap horizon; user's WC/BB/TC planning typically drives FH timing
        eval_window = window[:FH_HORIZON_GWS]

        ev_by_gw: Dict[int, float] = {}
        for gw in eval_window:
            preds_all = self._predictions_for_gw(gw, None)  # all players
            if not preds_all:
                ev_by_gw[gw] = 0.0
                continue

            # Current squad xP for this GW (best XI)
            current_xi_xp = self._best_xi_xp(squad, preds_all)

            # Optimal FH squad xP for this GW (its own best XI)
            try:
                fh_squad = self._get_optimizer().optimize_free_hit(
                    gameweek=gw, predictions=preds_all, verbose=False,
                )
                fh_xi_xp = self._best_xi_xp_from_players(
                    fh_squad.players, preds_all,
                )
            except Exception as exc:
                logger.warning("ChipStrategy: FH optimize failed for GW%s: %s", gw, exc)
                fh_xi_xp = current_xi_xp  # treat as no gain

            ev = max(0.0, fh_xi_xp - current_xi_xp)
            ev_by_gw[gw] = round(ev, 2)

        best_gw, best_ev = self._argmax(ev_by_gw)
        return ChipPlan(
            chip_name=FREE_HIT,
            chip_display_name=status.definition.display_name,
            best_gw=best_gw,
            best_gw_ev=best_ev,
            ev_by_gw=ev_by_gw,
            expires_at_gw=status.definition.stop_event,
            notes="FH EV = optimal 100m XI vs current XI for the gameweek",
        )

    def _plan_wildcard(
        self,
        status: ChipStatus,
        current_gw: int,
        window: List[int],
        squad: List[Dict[str, Any]],
        bank: float,
        transfers_needed: int,
    ) -> ChipPlan:
        """
        WC EV for starting GW = 4-GW xP uplift of optimal rebuild vs current squad.

        For each candidate starting GW in the next WC_LOOKAHEAD_GWS GWs,
        run `optimize_wildcard` and compute the XI-xP sum across the
        WC_HORIZON_GWS GWs starting there, minus the same for the current
        squad (held static — pessimistic but consistent baseline).
        """
        eval_window = window[:WC_LOOKAHEAD_GWS]

        # Build horizon predictions once, indexed by player+gw
        horizon_end = min(
            max(eval_window) + WC_HORIZON_GWS - 1 if eval_window else current_gw,
            status.definition.stop_event,
        )
        multi_gw_preds = self._multi_gw_predictions(current_gw, horizon_end)

        ev_by_gw: Dict[int, float] = {}
        for start_gw in eval_window:
            horizon_gws = [
                g for g in range(start_gw, start_gw + WC_HORIZON_GWS)
                if g <= status.definition.stop_event
            ]
            if not horizon_gws:
                continue

            # Baseline: current squad static over horizon
            baseline = 0.0
            for gw in horizon_gws:
                preds_gw = {
                    pid: multi_gw_preds.get(pid, {}).get(gw, 0.0)
                    for pid in (p['id'] for p in squad)
                }
                baseline += self._best_xi_xp(squad, preds_gw)

            # Optimal WC squad
            try:
                wc_squad = self._get_optimizer().optimize_wildcard(
                    gameweek=start_gw,
                    current_squad=squad,
                    bank=bank,
                    multi_gw_predictions=multi_gw_preds,
                    horizon=len(horizon_gws),
                    verbose=False,
                )
                rebuild = 0.0
                for gw in horizon_gws:
                    preds_gw = {
                        pid: multi_gw_preds.get(pid, {}).get(gw, 0.0)
                        for pid in (p['id'] for p in wc_squad.players)
                    }
                    rebuild += self._best_xi_xp_from_players(wc_squad.players, preds_gw)
            except Exception as exc:
                logger.warning("ChipStrategy: WC optimize failed for GW%s: %s", start_gw, exc)
                rebuild = baseline  # treat as no gain

            # Subtract an expected gain from "no WC" transfers over horizon
            # (roughly free_transfers * 2pts/transfer * horizon/N_to_use)
            no_wc_transfer_gain = transfers_needed * 2.0
            ev = max(0.0, rebuild - baseline - no_wc_transfer_gain)
            ev_by_gw[start_gw] = round(ev, 2)

        best_gw, best_ev = self._argmax(ev_by_gw)
        return ChipPlan(
            chip_name=WILDCARD,
            chip_display_name=status.definition.display_name,
            best_gw=best_gw,
            best_gw_ev=best_ev,
            ev_by_gw=ev_by_gw,
            expires_at_gw=status.definition.stop_event,
            notes=f"WC EV = xP uplift over {WC_HORIZON_GWS} GWs minus FT-based baseline gain",
        )

    # ------------------------------------------------------------------
    # DECISION LOGIC
    # ------------------------------------------------------------------

    def _decide_from_plan(
        self,
        chip_name: str,
        status: ChipStatus,
        plan: ChipPlan,
        current_gw: int,
        chips_available: int,
    ) -> ChipDecision:
        """Decide whether plan.best_gw == current_gw → play now, or hold."""
        ev_now = plan.ev_by_gw.get(current_gw, 0.0)
        best_future_ev = max(
            (ev for gw, ev in plan.ev_by_gw.items() if gw > current_gw),
            default=0.0,
        )
        best_future_gw = None
        for gw, ev in plan.ev_by_gw.items():
            if gw > current_gw and ev == best_future_ev and best_future_ev > 0:
                best_future_gw = gw
                break

        gws_remaining = status.definition.stop_event - current_gw + 1
        forced = chips_available >= gws_remaining and gws_remaining > 0

        # Deadline-pressure ratio: as GWs run out, the premium we demand
        # for waiting shrinks.
        urgency_ratio = chips_available / max(gws_remaining, 1)
        keep_threshold = max(0.7, 1.0 - 0.3 * urgency_ratio)

        play_now = False
        reason_bits: List[str] = []

        if forced:
            play_now = ev_now > 0
            reason_bits.append(
                f"FORCED: {chips_available} chips, only {gws_remaining} GWs left"
            )
        elif ev_now <= 0:
            play_now = False
            reason_bits.append("No positive EV this GW")
        elif ev_now >= best_future_ev * keep_threshold:
            play_now = True
            reason_bits.append(
                f"EV {ev_now:.1f} ≥ {keep_threshold:.0%} of best future "
                f"(GW{best_future_gw}: {best_future_ev:.1f})"
                if best_future_gw else f"EV {ev_now:.1f}, no better future GW"
            )
        else:
            play_now = False
            reason_bits.append(
                f"Hold: EV {ev_now:.1f} now vs {best_future_ev:.1f} at GW{best_future_gw}"
            )

        urgency = self._urgency_label(status, play_now, forced)

        # TC: propose captain_override for current GW (if playing)
        captain_override = None
        captain_override_name = None
        if chip_name == TRIPLE_CAPTAIN and play_now:
            target = plan.captain_target_by_gw.get(current_gw)
            if target:
                captain_override, captain_override_name = target

        display_name = status.definition.display_name
        reason = f"{display_name}: " + "; ".join(reason_bits)
        if chip_name == TRIPLE_CAPTAIN and captain_override_name:
            reason += f" (target: {captain_override_name})"

        return ChipDecision(
            use_chip=play_now,
            chip_name=chip_name,
            chip_display_name=display_name,
            reason=reason,
            urgency=urgency,
            replaces_transfers=chip_name in TRANSFER_CHIPS,
            expected_value=ev_now,
            best_alternative_gw=best_future_gw,
            best_alternative_ev=best_future_ev if best_future_ev > 0 else None,
            captain_override=captain_override,
            captain_override_name=captain_override_name,
        )

    @staticmethod
    def _urgency_label(status: ChipStatus, play_now: bool, forced: bool) -> str:
        if forced:
            return 'HIGH'
        if play_now:
            return 'HIGH' if status.expires_soon else 'MEDIUM'
        return 'LOW' if status.expires_soon else 'NONE'

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _remaining_window(self, status: ChipStatus, current_gw: int) -> List[int]:
        start = max(current_gw, status.definition.start_event)
        stop = status.definition.stop_event
        return list(range(start, stop + 1))

    def _enrich_squad(self, squad: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalise a squad dict list to have `id`, `web_name`, `element_type`,
        `team_id`, `is_captain`, `is_bench`, `now_cost`, `selling_price`.

        The `squad` argument comes from the manager's `make_weekly_decision`;
        shapes vary slightly between callers so we look up missing fields.
        """
        if not squad:
            return []

        ids = [p.get('id') or p.get('player_id') for p in squad if p.get('id') or p.get('player_id')]
        player_rows: Dict[int, Dict[str, Any]] = {}
        if self.db and ids:
            placeholders = ','.join('?' * len(ids))
            try:
                rows = self.db.execute_query(
                    f"SELECT id, web_name, element_type, team_id, now_cost "
                    f"FROM players WHERE id IN ({placeholders})",
                    tuple(ids),
                )
                player_rows = {r['id']: dict(r) for r in rows}
            except Exception as exc:
                logger.warning("ChipStrategy: enrich squad lookup failed: %s", exc)

        enriched: List[Dict[str, Any]] = []
        for p in squad:
            pid = p.get('id') or p.get('player_id')
            if pid is None:
                continue
            base = dict(player_rows.get(pid, {}))
            base.update({k: v for k, v in p.items() if v is not None})
            base['id'] = pid
            # Bench detection: squad slot (1-15) is the reliable signal in
            # draft_team; multiplier is 1 for both starters and bench in
            # some flows (only captain differs with mult=2).
            pos = base.get('position') or base.get('position_in_squad') or 0
            mult = base.get('multiplier')
            if pos:
                is_bench = pos > 11
            elif mult is not None:
                is_bench = mult == 0
            else:
                is_bench = False
            base['is_bench'] = is_bench
            enriched.append(base)
        return enriched

    def _predictions_for_gw(
        self, gameweek: int, player_ids: Optional[List[int]]
    ) -> Dict[int, float]:
        """Load predicted_points for the given gameweek. None = all players."""
        if not self.db:
            return {}
        try:
            if player_ids:
                placeholders = ','.join('?' * len(player_ids))
                rows = self.db.execute_query(
                    f"SELECT player_id, predicted_points "
                    f"FROM player_predictions "
                    f"WHERE gameweek = ? AND player_id IN ({placeholders})",
                    tuple([gameweek] + list(player_ids)),
                )
            else:
                rows = self.db.execute_query(
                    "SELECT player_id, predicted_points FROM player_predictions "
                    "WHERE gameweek = ?",
                    (gameweek,),
                )
            return {r['player_id']: float(r['predicted_points'] or 0.0) for r in rows}
        except Exception as exc:
            logger.warning("ChipStrategy: predictions load failed for GW%s: %s", gameweek, exc)
            return {}

    def _multi_gw_predictions(
        self, start_gw: int, end_gw: int
    ) -> Dict[int, Dict[int, float]]:
        """Load predictions for GWs [start_gw, end_gw] keyed by player then GW."""
        if not self.db:
            return {}
        try:
            rows = self.db.execute_query(
                "SELECT player_id, gameweek, predicted_points FROM player_predictions "
                "WHERE gameweek BETWEEN ? AND ?",
                (start_gw, end_gw),
            )
        except Exception as exc:
            logger.warning(
                "ChipStrategy: multi-GW predictions load failed %s-%s: %s",
                start_gw, end_gw, exc,
            )
            return {}
        result: Dict[int, Dict[int, float]] = {}
        for r in rows:
            result.setdefault(r['player_id'], {})[r['gameweek']] = float(
                r['predicted_points'] or 0.0
            )
        return result

    def _best_xi_xp(
        self,
        squad: List[Dict[str, Any]],
        predictions: Dict[int, float],
    ) -> float:
        """Compute xP of the best starting XI from a 15-player squad."""
        return self._best_xi_xp_from_players(squad, predictions)

    def _best_xi_xp_from_players(
        self,
        players: List[Dict[str, Any]],
        predictions: Dict[int, float],
    ) -> float:
        """
        Greedy best-XI under standard formation constraints.

        Fills the mandatory minimums (1 GKP, 3 DEF, 2 MID, 1 FWD) with
        highest-xP players per position, then fills the remaining 4
        slots with highest-xP players subject to per-position maxes.
        """
        if not players:
            return 0.0
        # Group by position
        by_pos: Dict[int, List[Tuple[float, int]]] = {1: [], 2: [], 3: [], 4: []}
        for p in players:
            pid = p.get('id')
            pos = p.get('element_type')
            if pid is None or pos not in by_pos:
                continue
            by_pos[pos].append((predictions.get(pid, 0.0), pid))
        for pos in by_pos:
            by_pos[pos].sort(reverse=True)

        chosen_xp = 0.0
        remaining = {pos: list(by_pos[pos]) for pos in by_pos}
        chosen_count = {pos: 0 for pos in by_pos}

        # Fill mandatory minimums
        for pos, minimum in FORMATION_MIN.items():
            for _ in range(minimum):
                if remaining[pos]:
                    xp, _pid = remaining[pos].pop(0)
                    chosen_xp += xp
                    chosen_count[pos] += 1

        # Fill remaining slots (11 - 7 = 4) with highest-xP under maxes
        slots_left = 11 - sum(chosen_count.values())
        pool: List[Tuple[float, int, int]] = []  # (xp, pos, pid)
        for pos, items in remaining.items():
            for xp, pid in items:
                if chosen_count[pos] < FORMATION_MAX[pos]:
                    pool.append((xp, pos, pid))
        pool.sort(reverse=True)
        for xp, pos, _pid in pool:
            if slots_left == 0:
                break
            if chosen_count[pos] >= FORMATION_MAX[pos]:
                continue
            chosen_xp += xp
            chosen_count[pos] += 1
            slots_left -= 1

        return chosen_xp

    @staticmethod
    def _argmax(ev_by_gw: Dict[int, float]) -> Tuple[Optional[int], float]:
        if not ev_by_gw:
            return None, 0.0
        best_gw = max(ev_by_gw, key=ev_by_gw.get)
        return best_gw, ev_by_gw[best_gw]

    def _get_optimizer(self):
        if self._optimizer is None:
            from services.squad_optimizer import SquadOptimizer
            self._optimizer = SquadOptimizer(self.db)
        return self._optimizer


# ------------------------------------------------------------------
# CLI smoke test
# ------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from data.database import Database
    from utils.config import load_config

    config = load_config()
    team_id = config.get('team_id')
    if not team_id:
        print("No team_id configured")
        sys.exit(1)

    db = Database()
    svc = ChipStrategyService(database=db)

    current_gw = int(sys.argv[1]) if len(sys.argv) > 1 else 33

    squad_rows = db.execute_query(
        "SELECT d.player_id as id, d.position, d.multiplier, d.is_captain, "
        "p.web_name, p.element_type, p.team_id, p.now_cost, d.selling_price "
        "FROM draft_team d JOIN players p ON p.id = d.player_id "
        "WHERE d.for_gameweek = ? ORDER BY d.position",
        (current_gw,),
    )
    squad = [dict(r) for r in squad_rows]

    print(f"\n=== Chip plan for GW{current_gw} ===\n")
    plans = svc.plan_all_chips(
        team_id=team_id, current_gw=current_gw, squad=squad, free_transfers=1,
    )
    for name, plan in plans.items():
        print(f"[{plan.chip_display_name}] best GW{plan.best_gw} EV={plan.best_gw_ev:.1f}")
        for gw in sorted(plan.ev_by_gw):
            marker = " <-- best" if gw == plan.best_gw else ""
            target = plan.captain_target_by_gw.get(gw)
            target_s = f"  (target: {target[1]})" if target else ""
            print(f"    GW{gw}: {plan.ev_by_gw[gw]:.1f}{target_s}{marker}")
        print()

    print(f"=== Decision for GW{current_gw} ===")
    best = svc.get_recommended_chip(
        team_id=team_id, gameweek=current_gw, squad=squad, free_transfers=1,
    )
    if best:
        print(f"USE {best.chip_display_name} — {best.reason}")
        if best.captain_override_name:
            print(f"  Captain override: {best.captain_override_name}")
    else:
        print("No chip recommended this GW")
