#!/usr/bin/env python3
"""
Show Latest Team Selection

Displays Ron's most recent team announcement.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database


def main():
    """Display latest team selection."""

    db = Database()

    print("\n" + "=" * 80)
    print("RON CLANKER'S LATEST TEAM SELECTION")
    print("=" * 80)

    # Get latest team selection
    selection = db.execute_query("""
        SELECT
            gameweek,
            announcement_text,
            created_at,
            formation
        FROM team_selections
        ORDER BY created_at DESC
        LIMIT 1
    """)

    if not selection:
        print("\nNo team selections found in database.")
        print("Run: venv/bin/python scripts/demo_ron_autonomous.py")
        return 1

    sel = selection[0]

    print(f"\nGameweek: {sel['gameweek']}")
    print(f"Selected: {sel['created_at']}")
    if sel['formation']:
        print(f"Formation: {sel['formation']}")

    print("\n" + "-" * 80)
    print(sel['announcement_text'])
    print("-" * 80)

    # Get squad details
    squad = db.execute_query("""
        SELECT
            p.web_name,
            p.team_name,
            p.position,
            ss.is_starting,
            ss.is_captain,
            ss.is_vice_captain,
            ss.bench_order
        FROM squad_selections ss
        JOIN players p ON ss.player_id = p.id
        WHERE ss.gameweek = ?
        ORDER BY
            ss.is_starting DESC,
            CASE p.position
                WHEN 'GKP' THEN 1
                WHEN 'DEF' THEN 2
                WHEN 'MID' THEN 3
                WHEN 'FWD' THEN 4
            END,
            ss.bench_order
    """, (sel['gameweek'],))

    if squad:
        print("\nFULL SQUAD:\n")

        print("STARTING XI:")
        for player in squad:
            if player['is_starting']:
                markers = []
                if player['is_captain']:
                    markers.append("(C)")
                if player['is_vice_captain']:
                    markers.append("(VC)")

                marker_str = " ".join(markers)
                print(f"  ⭐ {player['web_name']} - {player['team_name']} [{player['position']}] {marker_str}")

        print("\nBENCH:")
        for player in squad:
            if not player['is_starting']:
                print(f"  {player['bench_order']}. {player['web_name']} - {player['team_name']} [{player['position']}]")

    print("\n" + "=" * 80)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)
