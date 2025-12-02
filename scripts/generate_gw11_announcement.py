#!/usr/bin/env python3
"""
Generate Ron's GW11 Team Announcement

Uses Claude API to generate announcement in Ron's persona.
"""

import sys
from pathlib import Path
from anthropic import Anthropic

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

def generate_announcement():
    """Generate Ron's GW11 announcement."""

    db = Database()

    # Get team
    team_query = """
    SELECT
        p.web_name,
        p.element_type,
        dt.position,
        dt.is_captain,
        dt.is_vice_captain,
        p.form,
        p.now_cost/10.0 as price,
        t.name as team,
        t.short_name
    FROM draft_team dt
    JOIN players p ON dt.player_id = p.id
    JOIN teams t ON p.team_id = t.id
    WHERE dt.for_gameweek = 11
    ORDER BY dt.position
    """
    team = db.execute_query(team_query)

    # Get fixtures for starting XI
    fixtures_query = """
    SELECT
        p.web_name,
        p.team_id,
        CASE
            WHEN f.team_h = p.team_id THEN opp.short_name || ' (H)'
            ELSE opp.short_name || ' (A)'
        END as opponent
    FROM draft_team dt
    JOIN players p ON dt.player_id = p.id
    LEFT JOIN fixtures f ON f.event = 11 AND (f.team_h = p.team_id OR f.team_a = p.team_id)
    LEFT JOIN teams opp ON (f.team_h = opp.id AND f.team_a = p.team_id) OR (f.team_a = opp.id AND f.team_h = p.team_id)
    WHERE dt.for_gameweek = 11 AND dt.position <= 11
    """
    fixtures = {row['web_name']: row['opponent'] for row in db.execute_query(fixtures_query)}

    # Format team data for Claude
    starting_xi = []
    bench = []

    for player in team:
        pos_type = ['GK', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]
        fixture = fixtures.get(player['web_name'], 'N/A')

        player_info = {
            'name': player['web_name'],
            'position': pos_type,
            'team': player['short_name'],
            'form': player['form'],
            'price': player['price'],
            'fixture': fixture,
            'is_captain': player['is_captain'],
            'is_vice': player['is_vice_captain']
        }

        if player['position'] <= 11:
            starting_xi.append(player_info)
        else:
            bench.append(player_info)

    # Create prompt for Claude
    prompt = f"""You are Ron Clanker, a gruff old-school football manager from the 1970s/80s who now runs a Fantasy Premier League team autonomously.

Generate Ron's team announcement for Gameweek 11.

CONTEXT:
- This is GW11 selection
- NO transfers made this week (rolled the transfer to save for next week)
- Formation: 4-3-3
- Captain: Haaland (Man City vs Liverpool)
- Vice: Guéhi

STARTING XI:
{chr(10).join(f"- {p['name']} ({p['position']}, {p['team']}) vs {p['fixture']} - Form: {p['form']}" for p in starting_xi)}

BENCH:
{chr(10).join(f"- {p['name']} ({p['position']}, {p['team']})" for p in bench)}

KEY FIXTURES:
- Man City vs Liverpool (Haaland's big test)
- Chelsea vs Wolves (João Pedro)
- Crystal Palace vs Brighton (Guéhi, Richards)
- Bournemouth at Villa (Semenyo, Senesi)

INSTRUCTIONS:
Write Ron's announcement in his classic style:
1. Brief introduction to the gameweek
2. Formation explanation (4-3-3)
3. Why no transfer this week (no good options, saving flexibility)
4. Captain choice reasoning (Haaland vs Liverpool)
5. Key talking points about the team
6. Sign off as "- Ron"

Keep it concise (200-300 words), authentic to his persona - no-nonsense, tactical, slightly gruff.
DO NOT use emojis.
"""

    # Call Claude API
    client = Anthropic()

    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    announcement = response.content[0].text

    # Save announcement
    output_file = project_root / "data" / "ron_gw11_announcement.txt"
    output_file.write_text(announcement)

    print(announcement)
    print(f"\n\n✅ Announcement saved to: {output_file}")

    # Also save to database
    import json
    db.execute_update("""
        INSERT INTO decisions
        (gameweek, decision_type, decision_data, reasoning)
        VALUES (?, ?, ?, ?)
    """, (
        11,
        'team_announcement',
        json.dumps({'announcement': announcement}),
        'GW11 form-based selection announcement'
    ))

    return announcement


if __name__ == "__main__":
    generate_announcement()
