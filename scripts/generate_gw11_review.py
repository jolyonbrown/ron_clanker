#!/usr/bin/env python3
"""
Generate Ron's GW11 Post-Match Review using LLM Banter
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ron_clanker.llm_banter import RonBanterGenerator

def main():
    print("=" * 80)
    print("GENERATING RON'S GW11 POST-MATCH REVIEW")
    print("=" * 80)

    banter = RonBanterGenerator()

    # GW11 Facts
    gameweek = 11
    ron_points = 57
    average_points = 38
    league_position = None  # We don't track mini-league yet
    total_managers = None
    gap_to_leader = None
    leader_name = None

    # Captain facts
    captain_name = "Guéhi"
    captain_points = 0  # Didn't play, 0 minutes

    # Heroes (top performers)
    heroes = [
        {"name": "João Pedro (VC)", "points": 14, "reason": "Got the armband when Guéhi was ruled out, 7pts doubled"},
        {"name": "Richards", "points": 8, "reason": "Auto-subbed in for injured Guéhi, full 90 minutes"},
        {"name": "Haaland", "points": 6, "reason": "Solid contribution from the premium"}
    ]

    # Villains (poor performers)
    villains = [
        {"name": "Guéhi (C)", "points": 0, "reason": "Ruled out last minute with injury - 0 minutes played, lost the captaincy multiplier"},
        {"name": "Bench players", "points": 9, "reason": "Left 9 points unused on the bench"}
    ]

    # Team summary
    team_summary = f"""57 points, +19 above average. Decent score ruined by captain disaster.

Guéhi was meant to be the differential captain - Palace's defense solid, soft fixture.
Then he gets ruled out last minute with an injury. Zero minutes. Richards auto-subbed in
with 8 points (solid), João Pedro got the armband as VC (7pts × 2 = 14pts).

Beat the average by 19 points, but it should've been much better with the right captain.

Overall rank: 11,969,488 (still way off the pace)
Started at GW8, now 4 weeks in: 231 total points
Team value: £101.3m, £5.3m in bank
Transfers: 0 (banked the FT, now have 3 for international break)
All 8 chips still available"""

    print("\nGenerating review with Claude API...")
    print()

    review = banter.generate_post_match_review(
        gameweek=gameweek,
        ron_points=ron_points,
        average_points=average_points,
        league_position=league_position,
        total_managers=total_managers,
        gap_to_leader=gap_to_leader,
        leader_name=leader_name,
        captain_name=captain_name,
        captain_points=captain_points,
        heroes=heroes,
        villains=villains,
        team_summary=team_summary
    )

    print(review)
    print()

    # Save to file
    output_file = project_root / 'data' / 'ron_gw11_review.txt'
    with open(output_file, 'w') as f:
        f.write(review)

    print("=" * 80)
    print(f"✅ Review saved to: {output_file}")
    print("=" * 80)

    return 0

if __name__ == '__main__':
    sys.exit(main())
