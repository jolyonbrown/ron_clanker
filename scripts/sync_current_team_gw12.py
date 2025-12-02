#!/usr/bin/env python3
"""Sync current_team with GW12 actual team from FPL"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

# GW12 actual team from track_ron_team.py output
gw12_team = [
    # Starting XI
    {"web_name": "Roefs", "position": 1, "purchase_price": 47, "selling_price": 47, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Senesi", "position": 2, "purchase_price": 50, "selling_price": 50, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Guéhi", "position": 3, "purchase_price": 51, "selling_price": 51, "is_captain": True, "is_vice_captain": False, "multiplier": 2},
    {"web_name": "Chalobah", "position": 4, "purchase_price": 51, "selling_price": 51, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Richards", "position": 5, "purchase_price": 46, "selling_price": 45, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Virgil", "position": 6, "purchase_price": 60, "selling_price": 60, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Sarr", "position": 7, "purchase_price": 67, "selling_price": 67, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Cullen", "position": 8, "purchase_price": 50, "selling_price": 50, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Ndiaye", "position": 9, "purchase_price": 66, "selling_price": 66, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "Haaland", "position": 10, "purchase_price": 149, "selling_price": 149, "is_captain": False, "is_vice_captain": False, "multiplier": 1},
    {"web_name": "João Pedro", "position": 11, "purchase_price": 75, "selling_price": 75, "is_captain": False, "is_vice_captain": True, "multiplier": 1},
    # Bench
    {"web_name": "Pope", "position": 12, "purchase_price": 52, "selling_price": 52, "is_captain": False, "is_vice_captain": False, "multiplier": 0},
    {"web_name": "Semenyo", "position": 13, "purchase_price": 79, "selling_price": 80, "is_captain": False, "is_vice_captain": False, "multiplier": 0},
    {"web_name": "Garner", "position": 14, "purchase_price": 50, "selling_price": 50, "is_captain": False, "is_vice_captain": False, "multiplier": 0},
    {"web_name": "Thiago", "position": 15, "purchase_price": 66, "selling_price": 64, "is_captain": False, "is_vice_captain": False, "multiplier": 0},
]

db = Database()

# Get player IDs
for player_data in gw12_team:
    result = db.execute_query(
        "SELECT id FROM players WHERE web_name = ?",
        (player_data["web_name"],)
    )
    if result:
        player_data["player_id"] = result[0]["id"]
    else:
        print(f"WARNING: Player {player_data['web_name']} not found in database")

# Clear and insert
db.execute_update("DELETE FROM current_team")

for player_data in gw12_team:
    if "player_id" in player_data:
        db.execute_update(
            """INSERT INTO current_team
            (player_id, position, purchase_price, selling_price, is_captain, is_vice_captain, multiplier)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                player_data["player_id"],
                player_data["position"],
                player_data["purchase_price"],
                player_data["selling_price"],
                player_data["is_captain"],
                player_data["is_vice_captain"],
                player_data["multiplier"],
            )
        )

print("✓ current_team synced with GW12 actual team")
print(f"✓ {len([p for p in gw12_team if 'player_id' in p])} players inserted")

# Verify
team = db.get_actual_current_team()
print(f"\nCurrent team ({len(team)} players):")
for p in team:
    role = "(C)" if p["is_captain"] else "(VC)" if p["is_vice_captain"] else ""
    print(f"  {p['position']:2d}. {p['web_name']:20s} {role}")
