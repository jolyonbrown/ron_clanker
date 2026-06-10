"""
Captain suitability scoring — shared by the live manager and the
backtest harness (ron_clanker-wxlx captain-model wrap).

Extracted from RonManager._calculate_captain_score so the same code
that picks Ron's real armband can be replayed and A/B-tested against
recorded seasons. Combines signals beyond raw xP:

    1. Position multiplier — 2025/26 DC rules make DEF near-parity
       with MID/FWD; GKs almost never carry the armband.
    2. Ceiling/variance bonus — captains need upside, not just a
       high mean; recent hauls and high variance earn a bonus.
    3. Fixture difficulty and home advantage.
    4. Availability (chance_of_playing).
    5. Minutes reliability — rotation risks are poor captains.

All history reads filter `gameweek < ?` so the score is walk-forward
safe in replays (the minutes-reliability query previously had no
filter — harmless live where the DB only holds the past, but lookahead
in a backtest; fixed during extraction).
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger('ron_clanker.captain_scoring')

POSITION_MULTIPLIER = {
    1: 0.25,   # GK - almost never captain
    2: 0.95,   # DEF - DC rules make them consistent haulers
    3: 1.00,   # MID - standard captain picks
    4: 1.05,   # FWD - slight edge for goal focus, but not dominant
}

FIXTURE_MULTIPLIER = {
    1: 1.15,   # Very easy
    2: 1.10,   # Easy
    3: 1.00,   # Medium
    4: 0.95,   # Hard
    5: 0.90,   # Very hard
}


def calculate_captain_score(player: Dict, gameweek: Optional[int],
                            db) -> float:
    """Captain suitability score for one player (higher = better).

    `player` needs xP, element_type, and player_id/id; team_id enables
    the fixture signals. `db` is the project Database wrapper (live DB
    or a backtest era DB with player_gameweek_history + fixtures).
    """
    base_xp = player.get('xP', 0)
    if base_xp <= 0:
        return 0.0

    score = base_xp * POSITION_MULTIPLIER.get(
        player.get('element_type', 3), 1.0
    )

    player_id = player.get('player_id') or player.get('id')

    # --- Ceiling/variance bonus from recent history ---
    if player_id and db:
        try:
            history = db.execute_query("""
                SELECT total_points, minutes
                FROM player_gameweek_history
                WHERE player_id = ? AND gameweek < ?
                ORDER BY gameweek DESC
                LIMIT 6
            """, (player_id, gameweek or 99))

            if history and len(history) >= 3:
                points = [h['total_points'] for h in history
                          if h['minutes'] and h['minutes'] > 0]
                if points:
                    import numpy as np
                    std_pts = np.std(points) if len(points) > 1 else 0
                    max_pts = max(points)

                    # Upper confidence bound: reward boom potential
                    ceiling_bonus = 0.3 * std_pts
                    if max_pts >= 12:
                        ceiling_bonus += 1.5
                    elif max_pts >= 8:
                        ceiling_bonus += 0.75
                    elif max_pts >= 6:
                        ceiling_bonus += 0.25
                    score += ceiling_bonus
        except Exception as e:
            logger.debug(f"captain scoring: history lookup failed: {e}")

    # --- Fixture difficulty and home advantage ---
    if player_id and gameweek and db:
        try:
            team_id = player.get('team_id') or player.get('team')
            if team_id:
                fixture = db.execute_query("""
                    SELECT team_h, team_a, team_h_difficulty, team_a_difficulty
                    FROM fixtures
                    WHERE event = ? AND (team_h = ? OR team_a = ?)
                    LIMIT 1
                """, (gameweek, team_id, team_id))

                if fixture:
                    fix = fixture[0]
                    is_home = fix['team_h'] == team_id
                    fdr = (fix['team_h_difficulty'] if is_home
                           else fix['team_a_difficulty'])
                    score *= FIXTURE_MULTIPLIER.get(fdr, 1.0)
                    if is_home:
                        score *= 1.05
        except Exception as e:
            logger.debug(f"captain scoring: fixture lookup failed: {e}")

    # --- Availability adjustment ---
    chance = player.get('chance_of_playing_next_round')
    if chance is not None and chance < 75:
        score *= (chance / 100)

    # --- Minutes reliability penalty ---
    # gameweek < ? keeps this walk-forward (was unfiltered pre-extraction)
    if player_id and db:
        try:
            recent_mins = db.execute_query("""
                SELECT minutes FROM player_gameweek_history
                WHERE player_id = ? AND gameweek < ?
                ORDER BY gameweek DESC LIMIT 3
            """, (player_id, gameweek or 99))
            if recent_mins and len(recent_mins) >= 2:
                avg_mins = sum(r['minutes'] or 0 for r in recent_mins) / len(recent_mins)
                if avg_mins < 45:
                    score *= 0.3
                elif avg_mins < 70:
                    score *= 0.7
        except Exception:
            pass

    return score


def select_captain_and_vice(starting_xi, gameweek, db):
    """Score an XI and return (captain_id, vice_id) — the live manager's
    primary armband logic, harness-replayable."""
    scored = sorted(
        ((p, calculate_captain_score(p, gameweek, db)) for p in starting_xi),
        key=lambda t: -t[1],
    )
    cap = scored[0][0] if scored else None
    vice = scored[1][0] if len(scored) >= 2 else None

    def pid(p):
        return (p.get('player_id') or p.get('id')) if p else None
    return pid(cap), pid(vice)
