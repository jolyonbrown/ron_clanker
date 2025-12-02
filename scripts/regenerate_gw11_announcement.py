#!/usr/bin/env python3
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ron_clanker.llm_banter import RonBanterGenerator

db = Database()
ron = RonBanterGenerator()

# Get GW11 team
team_query = """
SELECT dt.player_id, dt.position, dt.is_captain, dt.is_vice_captain,
       p.web_name, p.element_type, p.now_cost/10.0 as price
FROM draft_team dt
JOIN players p ON dt.player_id = p.id
WHERE dt.for_gameweek = 11
ORDER BY dt.position
"""
squad = db.execute_query(team_query)

# Regenerate with more personality
announcement = ron.generate_team_announcement(
    gameweek=11,
    squad=squad,
    transfers=[],
    chip_used=None,
    free_transfers=3,  # He actually has 3!
    bank=4.2,
    reasoning={
        'approach': '400 points off the pace - using international break to regroup',
        'key_differentials': ['Guéhi captain (Palace defense strong, differential)', 'Gabriel NOW STARTING - was benching 11.0 form like an idiot', '3 FTs saved for break']
    }
)

print("\n" + "="*80)
print("NEW ANNOUNCEMENT:")
print("="*80)
print(announcement)
print("="*80)

# Update database
import json
db.execute_update("""
    UPDATE decisions
    SET decision_data = ?
    WHERE gameweek = 11 AND decision_type = 'team_announcement'
    AND id = (SELECT MAX(id) FROM decisions WHERE gameweek = 11 AND decision_type = 'team_announcement')
""", (json.dumps({'announcement': announcement}),))

print("\n✅ Updated in database")
