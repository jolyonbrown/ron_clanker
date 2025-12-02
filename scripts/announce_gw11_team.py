#!/usr/bin/env python3
"""
Generate Ron's GW11 Team Announcement

Uses llm_banter.py with Haiku to create authentic Ron announcement.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ron_clanker.llm_banter import RonBanterGenerator

def main():
    db = Database()
    ron = RonBanterGenerator()

    if not ron.enabled:
        print("❌ Anthropic API key not configured!")
        return 1

    # Get GW11 team
    team_query = """
    SELECT
        dt.player_id,
        dt.position,
        dt.is_captain,
        dt.is_vice_captain,
        p.web_name,
        p.element_type,
        p.now_cost/10.0 as price
    FROM draft_team dt
    JOIN players p ON dt.player_id = p.id
    WHERE dt.for_gameweek = 11
    ORDER BY dt.position
    """
    squad = db.execute_query(team_query)

    print("\n" + "=" * 80)
    print("GENERATING RON'S GW11 ANNOUNCEMENT")
    print("=" * 80)
    print()

    # Generate announcement
    announcement = ron.generate_team_announcement(
        gameweek=11,
        squad=squad,
        transfers=[],  # No transfers this week
        chip_used=None,
        free_transfers=2,  # Rolled transfer
        bank=4.2,
        reasoning={
            'approach': 'Rolled transfer - no good options this week, saving flexibility'
        }
    )

    print("\n" + "=" * 80)
    print("RON'S ANNOUNCEMENT")
    print("=" * 80)
    print()
    print(announcement)
    print()

    # Save to file
    output_file = project_root / "data" / "ron_gw11_announcement.txt"
    output_file.write_text(announcement)

    print(f"✅ Saved to: {output_file}")
    print()

    # Save to database
    import json
    db.execute_update("""
        INSERT INTO decisions
        (gameweek, decision_type, decision_data, reasoning)
        VALUES (?, ?, ?, ?)
    """, (
        11,
        'team_announcement',
        json.dumps({'announcement': announcement}),
        'GW11 team announcement via llm_banter'
    ))

    print("✅ Saved to database")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
