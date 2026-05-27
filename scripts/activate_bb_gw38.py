#!/usr/bin/env python3
"""
One-off: activate Bench Boost for GW38.

The autonomous pipeline ran without FPL_TEAM_ID in env (subprocess context),
so chip_strategy returned None and we submitted with chip=None. BB is the
unused 2nd-half chip and this is the final GW — use-it-or-lose-it.

Updates the decisions table and re-submits the team with chip='bboost'.
"""
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from services.fpl_submission import FPLSubmissionClient


GAMEWEEK = 38


def update_chip_decision(db: Database) -> None:
    db.execute_update(
        """UPDATE decisions
           SET decision_data = ?, reasoning = ?
           WHERE id = ? AND gameweek = ? AND decision_type = 'chip_usage'""",
        (json.dumps({'chip': 'bboost'}),
         'FORCED: 1 chip, 1 GW left (final week of season)',
         607, GAMEWEEK),
    )
    print(f"Updated decision row to chip=bboost for GW{GAMEWEEK}")


async def main() -> int:
    db = Database()
    update_chip_decision(db)

    client = FPLSubmissionClient(dry_run=False)
    if not await asyncio.to_thread(client.login):
        print("FPL login FAILED")
        return 1
    print("Logged in to FPL")

    result = client.submit_gameweek_from_draft(GAMEWEEK)
    print(f"Result: success={result.success}, msg={result.message}")
    if not result.success:
        return 1

    verification = client.verify_submission(GAMEWEEK)
    print(f"Verification: {verification}")
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
