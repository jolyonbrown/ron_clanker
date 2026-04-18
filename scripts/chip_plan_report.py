#!/usr/bin/env python3
"""
Chip Plan Report

Prints a forward-looking plan for every still-available chip: the best
gameweek to play each one, the expected-value curve across remaining
GWs in each chip's window, and any captain override Triple Captain
is eyeing.

Usage:
    venv/bin/python scripts/chip_plan_report.py            # use current GW
    venv/bin/python scripts/chip_plan_report.py --gw 33    # explicit GW
    venv/bin/python scripts/chip_plan_report.py --json     # machine-readable

Reads the live draft_team for the chosen GW, so run this after a
pre-deadline selection has been saved to see the plan Ron is sitting on.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.database import Database  # noqa: E402
from services.chip_strategy import ChipStrategyService  # noqa: E402
from utils.config import load_config  # noqa: E402


def _load_squad(db: Database, gameweek: int):
    rows = db.execute_query(
        "SELECT d.player_id as id, d.position, d.multiplier, d.is_captain, "
        "p.web_name, p.element_type, p.team_id, p.now_cost, d.selling_price "
        "FROM draft_team d JOIN players p ON p.id = d.player_id "
        "WHERE d.for_gameweek = ? ORDER BY d.position",
        (gameweek,),
    )
    return [dict(r) for r in rows]


def _current_gw(db: Database) -> int:
    row = db.execute_query(
        "SELECT id FROM gameweeks WHERE is_current = 1 LIMIT 1"
    )
    if row:
        return row[0]['id']
    # Fall back: next unfinished gameweek
    row = db.execute_query(
        "SELECT id FROM gameweeks WHERE finished = 0 ORDER BY id LIMIT 1"
    )
    return row[0]['id'] if row else 1


def _print_human(plans, decision, gameweek: int) -> None:
    print()
    print("=" * 68)
    print(f"  Chip Plan — current gameweek GW{gameweek}")
    print("=" * 68)

    if not plans:
        print("  No chips available.")
        return

    for chip_name, plan in plans.items():
        header = f"[{plan.chip_display_name}]"
        if plan.best_gw is not None:
            header += f"  best: GW{plan.best_gw} (EV {plan.best_gw_ev:.1f})"
        if plan.expires_at_gw is not None:
            header += f"  expires: GW{plan.expires_at_gw}"
        print()
        print(header)
        if plan.notes:
            print(f"  {plan.notes}")
        # EV curve
        for gw in sorted(plan.ev_by_gw):
            ev = plan.ev_by_gw[gw]
            marker = "  <-- best" if gw == plan.best_gw else ""
            target = plan.captain_target_by_gw.get(gw)
            target_s = f"  (target: {target[1]})" if target else ""
            current_s = "  [now]" if gw == gameweek else "      "
            print(f"    GW{gw}{current_s}  EV {ev:6.2f}{target_s}{marker}")

    print()
    print("-" * 68)
    if decision:
        print(f"  RECOMMENDATION: play {decision.chip_display_name}")
        print(f"    {decision.reason}")
        if decision.captain_override_name:
            print(f"    Captain override: {decision.captain_override_name}")
        if decision.best_alternative_gw:
            print(
                f"    (Alternative: hold for GW{decision.best_alternative_gw}"
                f", EV {decision.best_alternative_ev:.1f})"
            )
    else:
        print("  RECOMMENDATION: hold all chips this GW")
    print("=" * 68)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ron's chip-plan report")
    parser.add_argument("--gw", type=int, default=None,
                        help="Target gameweek (default: current GW from DB)")
    parser.add_argument("--free-transfers", type=int, default=1)
    parser.add_argument("--bank", type=float, default=0.0)
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON")
    args = parser.parse_args()

    config = load_config()
    team_id = config.get('team_id')
    if not team_id:
        print("ERROR: No team_id configured (.env)", file=sys.stderr)
        return 1

    db = Database()
    gameweek = args.gw if args.gw is not None else _current_gw(db)
    squad = _load_squad(db, gameweek)
    if not squad:
        print(f"ERROR: no draft_team saved for GW{gameweek}", file=sys.stderr)
        return 1

    svc = ChipStrategyService(database=db)
    plans = svc.plan_all_chips(
        team_id=team_id,
        current_gw=gameweek,
        squad=squad,
        free_transfers=args.free_transfers,
        bank=args.bank,
    )
    decision = svc.get_recommended_chip(
        team_id=team_id,
        gameweek=gameweek,
        squad=squad,
        free_transfers=args.free_transfers,
        bank=args.bank,
    )

    if args.json:
        out = {
            'gameweek': gameweek,
            'plans': {name: p.to_dict() for name, p in plans.items()},
            'decision': decision.to_dict() if decision else None,
        }
        print(json.dumps(out, indent=2))
    else:
        _print_human(plans, decision, gameweek)

    return 0


if __name__ == "__main__":
    sys.exit(main())
