"""
Historical data access for backtesting.

HistoricalDataProvider wraps a season database — either the live
data/ron_clanker.db or an archive snapshot from data/archives/ — and
serves the views the backtest needs. All connections are read-only.

Walk-forward discipline: anything a *strategy* consumes must come from
before the decision gameweek. The provider keeps the line explicit:

    actuals(gw), entry(gw), picks(gw)   -> outcome data, used only to
                                           SCORE gameweek gw after the fact
    predictions(gw)                     -> what the model said BEFORE gw
                                           (stored in-season, so already
                                           lookahead-free)
    history_before(gw)                  -> per-player aggregates strictly
                                           before gw, safe for features

Benchmarks (average manager score per GW) come from a bootstrap_static
JSON snapshot, since the live gameweeks table doesn't store them. The
provider finds one automatically in data/archives/ if not given a path.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from backtest.scoring import Pick, PlayerGW

logger = logging.getLogger('ron_clanker.backtest.data')

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'ron_clanker.db'


@dataclass(frozen=True)
class EntryGW:
    """Ron's recorded entry-level state for one gameweek (from the FPL API)."""
    gameweek: int
    event_points: int            # official GW score (gross, before hits)
    event_transfers: int
    event_transfers_cost: int    # positive points spent on hits
    bank: int                    # tenths of £m
    value: int                   # tenths of £m
    points_on_bench: int
    overall_rank: Optional[int]
    active_chip: Optional[str]


class HistoricalDataProvider:
    """Read-only access to one season's recorded history."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB,
        season: str = '2025-26',
        bootstrap_path: Optional[Path] = None,
    ):
        self.db_path = Path(db_path)
        self.season = season
        self._con = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
        self._con.row_factory = sqlite3.Row
        self._bootstrap_events = self._load_bootstrap_events(bootstrap_path)

    def close(self):
        self._con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # Season structure

    def gameweeks(self) -> List[int]:
        """Gameweeks Ron actually has recorded teams for, in order."""
        rows = self._con.execute(
            "SELECT DISTINCT gameweek FROM season_team_history "
            "WHERE season = ? ORDER BY gameweek",
            (self.season,),
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Outcome data (for scoring a gameweek after the fact)

    def picks(self, gameweek: int) -> List[Pick]:
        """Ron's 15 picks for a gameweek, in POST-autosub arrangement.

        The FPL API rewrites pick positions once a GW finishes (subbed-out
        starters moved to the bench, subs promoted), and season_team_history
        stores that final state. Captain/vice flags remain lock-time. For
        the true deadline selection use
        backtest.replay.reconstruct_lock_time_picks with api_picks().
        """
        rows = self._con.execute(
            "SELECT pick_position, player_id, element_type, is_captain, "
            "is_vice_captain FROM season_team_history "
            "WHERE season = ? AND gameweek = ? ORDER BY pick_position",
            (self.season, gameweek),
        ).fetchall()
        return [
            Pick(
                player_id=r['player_id'],
                position=r['pick_position'],
                element_type=r['element_type'],
                is_captain=bool(r['is_captain']),
                is_vice_captain=bool(r['is_vice_captain']),
            )
            for r in rows
        ]

    def entry(self, gameweek: int) -> EntryGW:
        """Ron's recorded entry-level outcome for a gameweek."""
        r = self._con.execute(
            "SELECT gameweek, event_points, event_transfers, "
            "event_transfers_cost, bank, value, points_on_bench, "
            "overall_rank, active_chip FROM season_team_history "
            "WHERE season = ? AND gameweek = ? AND pick_position = 1",
            (self.season, gameweek),
        ).fetchone()
        if r is None:
            raise KeyError(f"No recorded team for {self.season} GW{gameweek}")
        return EntryGW(
            gameweek=r['gameweek'],
            event_points=r['event_points'],
            event_transfers=r['event_transfers'],
            event_transfers_cost=r['event_transfers_cost'],
            bank=r['bank'],
            value=r['value'],
            points_on_bench=r['points_on_bench'],
            overall_rank=r['overall_rank'],
            active_chip=r['active_chip'],
        )

    def actuals(self, gameweek: int) -> Dict[int, PlayerGW]:
        """Every player's actual GW return, summed across DGW fixtures."""
        rows = self._con.execute(
            "SELECT player_id, SUM(total_points) AS points, "
            "SUM(minutes) AS minutes FROM player_gameweek_history "
            "WHERE gameweek = ? GROUP BY player_id",
            (gameweek,),
        ).fetchall()
        return {
            r['player_id']: PlayerGW(points=r['points'] or 0, minutes=r['minutes'] or 0)
            for r in rows
        }

    # ------------------------------------------------------------------
    # Pre-deadline data (safe for strategies)

    def predictions(self, gameweek: int) -> Dict[int, float]:
        """The model's stored pre-deadline xP for a gameweek (GW totals,
        already summed across DGW fixtures — see commit 06551f0)."""
        rows = self._con.execute(
            "SELECT player_id, predicted_points FROM player_predictions "
            "WHERE gameweek = ?",
            (gameweek,),
        ).fetchall()
        return {r['player_id']: r['predicted_points'] for r in rows}

    def history_before(self, gameweek: int) -> Dict[int, Dict]:
        """Per-player aggregates strictly before a gameweek — the only
        actuals-derived view strategies are allowed to touch."""
        rows = self._con.execute(
            "SELECT player_id, COUNT(DISTINCT gameweek) AS appearances, "
            "SUM(total_points) AS points, SUM(minutes) AS minutes "
            "FROM player_gameweek_history WHERE gameweek < ? "
            "GROUP BY player_id",
            (gameweek,),
        ).fetchall()
        return {
            r['player_id']: {
                'appearances': r['appearances'],
                'points': r['points'] or 0,
                'minutes': r['minutes'] or 0,
            }
            for r in rows
        }

    # ------------------------------------------------------------------
    # Reference data

    def player_names(self) -> Dict[int, str]:
        rows = self._con.execute("SELECT id, web_name FROM players").fetchall()
        return {r['id']: r['web_name'] for r in rows}

    def player_element_types(self) -> Dict[int, int]:
        rows = self._con.execute("SELECT id, element_type FROM players").fetchall()
        return {r['id']: r['element_type'] for r in rows}

    def player_team_ids(self) -> Dict[int, int]:
        """Club assignment per player, from end-of-season state. Mid-season
        intra-PL moves are rare enough that this is an accepted
        approximation for the max-3-per-club rule in counterfactuals."""
        rows = self._con.execute("SELECT id, team_id FROM players").fetchall()
        return {r['id']: r['team_id'] for r in rows}

    def prices(self, gameweek: int) -> Dict[int, int]:
        """Market price (tenths) per player at the gameweek, from their
        fixture-time value. Players without a fixture that GW are absent —
        callers should carry forward (see price_map_through)."""
        rows = self._con.execute(
            "SELECT player_id, MAX(value) AS value FROM player_gameweek_history "
            "WHERE gameweek = ? AND value IS NOT NULL GROUP BY player_id",
            (gameweek,),
        ).fetchall()
        return {r['player_id']: r['value'] for r in rows}

    def price_map_through(self, gameweek: int) -> Dict[int, int]:
        """Latest known price per player up to and including a gameweek."""
        rows = self._con.execute(
            "SELECT player_id, value FROM player_gameweek_history "
            "WHERE gameweek <= ? AND value IS NOT NULL "
            "ORDER BY gameweek",
            (gameweek,),
        ).fetchall()
        prices: Dict[int, int] = {}
        for r in rows:
            prices[r['player_id']] = r['value']
        return prices

    def fixture_counts(self, gameweek: int) -> Dict[int, int]:
        """team_id -> number of fixtures in the gameweek (0 = blank, 2 = DGW).
        Schedule knowledge, safe pre-deadline."""
        rows = self._con.execute(
            "SELECT team_h, team_a FROM fixtures WHERE event = ?",
            (gameweek,),
        ).fetchall()
        counts: Dict[int, int] = {}
        for r in rows:
            counts[r['team_h']] = counts.get(r['team_h'], 0) + 1
            counts[r['team_a']] = counts.get(r['team_a'], 0) + 1
        return counts

    def transfers_by_gw(self) -> Optional[Dict[int, List[Dict]]]:
        """Ron's recorded transfers grouped by GW, chronological within
        each, from the season archive. Costs are the actual transaction
        prices (element_out_cost is the sale price received)."""
        archives = Path(__file__).resolve().parent.parent / 'data' / 'archives'
        candidates = sorted(
            archives.glob(f'{self.season}_*/fpl_api_snapshots/ron_transfers.json')
        )
        if not candidates:
            return None
        with open(candidates[-1]) as f:
            transfers = json.load(f)
        by_gw: Dict[int, List[Dict]] = {}
        for t in sorted(transfers, key=lambda t: t['time']):
            by_gw.setdefault(t['event'], []).append(t)
        return by_gw

    def api_picks(self) -> Optional[Dict[str, Dict]]:
        """Raw picks-by-GW JSON from the season archive, if present.

        Unlike season_team_history (whose positions/multipliers are
        POST-autosub, as the FPL API rearranges them once a GW finishes),
        this carries the automatic_subs array needed to reconstruct
        lock-time selections.
        """
        archives = Path(__file__).resolve().parent.parent / 'data' / 'archives'
        candidates = sorted(
            archives.glob(f'{self.season}_*/fpl_api_snapshots/ron_picks_by_gw.json')
        )
        if not candidates:
            return None
        with open(candidates[-1]) as f:
            return json.load(f)

    def average_entry_score(self, gameweek: int) -> Optional[int]:
        """Average manager score for a GW, from a bootstrap_static snapshot."""
        return self._bootstrap_events.get(gameweek)

    def chip_definitions(self) -> Optional[List[Dict]]:
        """The season's real chip windows from the archived bootstrap:
        id/name/number/start_event/stop_event/chip_type per instance."""
        archives = Path(__file__).resolve().parent.parent / 'data' / 'archives'
        candidates = sorted(
            archives.glob(f'{self.season}_*/fpl_api_snapshots/bootstrap_static.json')
        )
        if not candidates:
            return None
        with open(candidates[-1]) as f:
            chips = json.load(f).get('chips', [])
        return [
            {k: c[k] for k in
             ('id', 'name', 'number', 'start_event', 'stop_event', 'chip_type')}
            for c in chips
        ]

    # ------------------------------------------------------------------

    def _load_bootstrap_events(self, bootstrap_path: Optional[Path]) -> Dict[int, int]:
        path = bootstrap_path
        if path is None:
            archives = Path(__file__).resolve().parent.parent / 'data' / 'archives'
            candidates = sorted(
                archives.glob(f'{self.season}_*/fpl_api_snapshots/bootstrap_static.json')
            )
            if candidates:
                path = candidates[-1]
        if path is None or not Path(path).exists():
            logger.warning(
                "No bootstrap_static.json snapshot found — average-manager "
                "benchmarks unavailable"
            )
            return {}
        with open(path) as f:
            events = json.load(f).get('events', [])
        return {
            e['id']: e['average_entry_score']
            for e in events
            if e.get('average_entry_score')
        }
