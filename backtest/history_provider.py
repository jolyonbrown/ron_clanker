"""
HistoricalSeasonProvider — replay past seasons (2022-23 .. 2024-25)
from historical_gameweek_data (vaastav import, per-fixture rows).

Multi-season replay exists to fight single-season overfitting: every
decision-layer change this summer was validated on 2025-26 alone, and
several showed knife-edge sensitivity. A strategy that wins on four
seasons is a far safer bet than one tuned to win on one.

The historical table lacks two things the simulator needs, both
recovered here:

  POSITIONS  historical_gameweek_data has no element_type. Players
             still in the 2025-26 players table are joined by code
             (45-66% of players); the rest are INFERRED from scoring
             arithmetic — goals are worth 6/6/5/4 by position, clean
             sheets 4/4/1/0, keepers bank save points — by scoring
             each played fixture under all four position formulas and
             keeping the best fit. Inference accuracy is validated
             against the joined players in tests.

  TEAMS      derived from fixture structure: for each fixture, the
             home side's club code is the away players' opponent code
             (verified unambiguous across all three seasons).

Predictions are a model-free walk-forward baseline: recency-decayed
points-per-played-gameweek x the team's fixture count (doubles count
double, blanks zero) — deliberately simple, so what's being compared
across seasons is the DECISION machinery, not a model.

Chips are NOT modelled for past seasons (chip rules differed —
two-of-each is new in 2025-26) and FT top-ups don't apply: replay
chipless strategies only (GreedyModelStrategy is rules-compatible).
"""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backtest.data import DEFAULT_DB
from backtest.scoring import PlayerGW

logger = logging.getLogger('ron_clanker.backtest.history_provider')

# Classic scoring (pre-2025-26 — no defensive contribution points)
GOAL_PTS = {1: 6, 2: 6, 3: 5, 4: 4}
CS_PTS = {1: 4, 2: 4, 3: 1, 4: 0}

PRED_WINDOW = 5
PRED_DECAY = 0.7


class HistoricalSeasonProvider:
    """Duck-typed stand-in for HistoricalDataProvider over one past season."""

    def __init__(self, season_id: str, db_path: Path = DEFAULT_DB):
        self.season = season_id
        self.db_path = Path(db_path)
        con = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            self._rows = [dict(r) for r in con.execute(
                "SELECT player_code, gameweek, fixture_id, was_home, minutes,"
                "       total_points, value, goals_scored, assists,"
                "       clean_sheets, goals_conceded, saves, penalties_saved,"
                "       penalties_missed, yellow_cards, red_cards, own_goals,"
                "       bonus"
                " FROM historical_gameweek_data WHERE season_id = ?"
                " ORDER BY gameweek", (season_id,)
            )]
            self._known = {
                r['code']: (r['element_type'], r['web_name'])
                for r in con.execute(
                    "SELECT code, element_type, web_name FROM players")
            }
        finally:
            con.close()

        self._teams_by_gw = self._derive_teams()
        self._etypes = self._derive_positions()
        self._by_gw: Dict[int, List[dict]] = {}
        for r in self._rows:
            self._by_gw.setdefault(r['gameweek'], []).append(r)

    # ------------------------------------------------------------------
    # Derivations

    def _derive_teams(self) -> Dict[int, Dict[int, int]]:
        """gw -> {player_code: club_code}. Home side's club code is the
        away players' opponent code (and vice versa)."""
        con = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
        try:
            sides = con.execute(
                "SELECT gameweek, fixture_id, was_home,"
                "       MIN(opponent_team_code) AS opp"
                " FROM historical_gameweek_data WHERE season_id = ?"
                " GROUP BY gameweek, fixture_id, was_home",
                (self.season,),
            ).fetchall()
        finally:
            con.close()
        # club code of a side = opponent code recorded by the OTHER side
        club_of_side: Dict[Tuple[int, int, int], int] = {}
        opp_of_side = {(gw, f, h): opp for gw, f, h, opp in sides}
        for (gw, f, h), _ in opp_of_side.items():
            other = opp_of_side.get((gw, f, 1 - h))
            if other is not None:
                club_of_side[(gw, f, h)] = other
        teams: Dict[int, Dict[int, int]] = {}
        for r in self._rows:
            club = club_of_side.get(
                (r['gameweek'], r['fixture_id'], r['was_home'])
            )
            if club is not None:
                teams.setdefault(r['gameweek'], {})[r['player_code']] = club
        return teams

    def _derive_positions(self) -> Dict[int, int]:
        """player_code -> element_type for THIS season.

        Scoring-arithmetic inference takes precedence when its evidence
        is strong: FPL reclassifies players between seasons (Bowen,
        Havertz, Cunha, Gakpo, Mbeumo...), so the 2025-26 players-table
        position can be WRONG for a past season, while the arithmetic
        (a goal worth 5 = MID that season) cannot. The join covers
        weak-evidence players; returnless unknowns default to MID."""
        etypes: Dict[int, int] = {}
        rows_by_player: Dict[int, List[dict]] = {}
        for r in self._rows:
            rows_by_player.setdefault(r['player_code'], []).append(r)

        for code, rows in rows_by_player.items():
            inferred, strong = self._infer_position(rows)
            known = self._known.get(code)
            if strong:
                etypes[code] = inferred
            elif known:
                etypes[code] = known[0]
            else:
                etypes[code] = inferred
        return etypes

    @staticmethod
    def _infer_position(rows: List[dict]) -> Tuple[int, bool]:
        """(element_type, strong_evidence) from scoring arithmetic."""
        # Keepers are unmistakable: only they record saves/penalty saves.
        if any(r['saves'] or r['penalties_saved'] for r in rows):
            return 1, True
        matches = {et: 0 for et in (2, 3, 4)}
        for r in rows:
            mins = r['minutes'] or 0
            if mins <= 0:
                continue
            base = 2 if mins >= 60 else 1
            common = (base + 3 * (r['assists'] or 0) + (r['bonus'] or 0)
                      - (r['yellow_cards'] or 0) - 3 * (r['red_cards'] or 0)
                      - 2 * (r['own_goals'] or 0)
                      - 2 * (r['penalties_missed'] or 0))
            for et in (2, 3, 4):
                pts = common + GOAL_PTS[et] * (r['goals_scored'] or 0)
                if mins >= 60 and (r['clean_sheets'] or 0):
                    pts += CS_PTS[et]
                if et == 2:
                    pts -= (r['goals_conceded'] or 0) // 2
                if pts == (r['total_points'] or 0):
                    matches[et] += 1
        ranked = sorted((2, 3, 4), key=lambda et: -matches[et])
        best, second = ranked[0], ranked[1]
        strong = (matches[best] >= 4
                  and matches[best] - matches[second] >= 3)
        if matches[best] == 0:
            return 3, False   # returnless: formulas coincide, default MID
        # Weak tie-break toward MID (most numerous position)
        if matches[best] == matches[3]:
            best = 3
        return best, strong

    # ------------------------------------------------------------------
    # Provider interface (the subset simulate_season + strategies use)

    def gameweeks(self) -> List[int]:
        return sorted(self._by_gw)

    def player_element_types(self) -> Dict[int, int]:
        return dict(self._etypes)

    def player_team_ids(self) -> Dict[int, int]:
        """Season-level club per player (last known)."""
        out: Dict[int, int] = {}
        for gw in sorted(self._teams_by_gw):
            out.update(self._teams_by_gw[gw])
        return out

    def player_names(self) -> Dict[int, str]:
        return {
            code: self._known[code][1] if code in self._known else f'#{code}'
            for code in self._etypes
        }

    def actuals(self, gameweek: int) -> Dict[int, PlayerGW]:
        agg: Dict[int, List[int]] = {}
        for r in self._by_gw.get(gameweek, []):
            cur = agg.setdefault(r['player_code'], [0, 0])
            cur[0] += r['total_points'] or 0
            cur[1] += r['minutes'] or 0
        return {pid: PlayerGW(points=p, minutes=m)
                for pid, (p, m) in agg.items()}

    def prices(self, gameweek: int) -> Dict[int, int]:
        out: Dict[int, int] = {}
        for r in self._by_gw.get(gameweek, []):
            if r['value']:
                out[r['player_code']] = max(out.get(r['player_code'], 0),
                                            r['value'])
        return out

    def price_map_through(self, gameweek: int) -> Dict[int, int]:
        out: Dict[int, int] = {}
        for gw in sorted(self._by_gw):
            if gw > gameweek:
                break
            out.update(self.prices(gw))
        return out

    def fixture_counts(self, gameweek: int) -> Dict[int, int]:
        counts: Dict[Tuple[int, int], set] = {}
        for r in self._by_gw.get(gameweek, []):
            club = self._teams_by_gw.get(gameweek, {}).get(r['player_code'])
            if club is not None:
                counts.setdefault(club, set()).add(r['fixture_id'])
        return {club: len(fids) for club, fids in counts.items()}

    def history_before(self, gameweek: int) -> Dict[int, Dict]:
        out: Dict[int, Dict] = {}
        for gw in sorted(self._by_gw):
            if gw >= gameweek:
                break
            for pid, a in self.actuals(gw).items():
                h = out.setdefault(pid, {'appearances': 0, 'points': 0,
                                         'minutes': 0})
                if a.minutes > 0:
                    h['appearances'] += 1
                h['points'] += a.points
                h['minutes'] += a.minutes
        return out

    def predictions(self, gameweek: int) -> Dict[int, float]:
        """Model-free walk-forward baseline: recency-decayed points per
        PLAYED gameweek x the team's fixture count this gameweek."""
        fc = self.fixture_counts(gameweek)
        teams = self._teams_by_gw.get(gameweek, {})
        # per-player recent played-GW points, walk-forward
        recent: Dict[int, List[int]] = {}
        for gw in sorted(self._by_gw):
            if gw >= gameweek:
                break
            for pid, a in self.actuals(gw).items():
                if a.minutes > 0:
                    recent.setdefault(pid, []).append(a.points)
        out: Dict[int, float] = {}
        for pid, pts in recent.items():
            n_fix = fc.get(teams.get(pid), 0)
            if n_fix == 0:
                out[pid] = 0.0
                continue
            w, num, den = 1.0, 0.0, 0.0
            for p in reversed(pts[-PRED_WINDOW:]):
                num += w * p
                den += w
                w *= PRED_DECAY
            # A red-card week can drag the decayed mean negative
            out[pid] = max(0.0, (num / den) * n_fix)
        return out

    # Unused-by-greedy provider surface, kept for interface parity
    def api_picks(self):
        return None

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
