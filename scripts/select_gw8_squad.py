#!/usr/bin/env python3
"""
Ron Clanker's GW8 Squad Selection

Builds Ron's optimal 15-player squad for Gameweek 8 using:
- DC performance analysis from GW1-7
- Fixture difficulty for GW8
- Budget optimization (£100m)
- Ron's tactical philosophy

Generates Ron's team announcement in his voice.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import requests
from typing import Dict, List, Tuple
from datetime import datetime


# FPL API constants
FPL_BASE_URL = "https://fantasy.premierleague.com/api"
BUDGET = 1000  # £100.0m in FPL units (0.1m)
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def load_dc_analysis() -> Dict:
    """Load comprehensive performance analysis from previous step."""
    # Try new comprehensive analysis first
    analysis_file = "data/analysis/recommendations_gw1-7.json"

    if not os.path.exists(analysis_file):
        # Fall back to old DC-only analysis
        analysis_file = "data/analysis/gw8_dc_recommendations.json"

    if not os.path.exists(analysis_file):
        print(f"❌ Analysis file not found: {analysis_file}")
        print("Run 'python scripts/analyze_player_performance.py --start-gw 1 --end-gw 7' first!")
        sys.exit(1)

    with open(analysis_file, 'r') as f:
        return json.load(f)


def fetch_bootstrap_data() -> Dict:
    """Fetch main FPL data."""
    print("Fetching latest FPL data...")
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def fetch_fixtures() -> List[Dict]:
    """Fetch upcoming fixtures."""
    print("Fetching fixture data...")
    response = requests.get(f"{FPL_BASE_URL}/fixtures/")
    response.raise_for_status()
    return response.json()


def get_gw8_fixtures(fixtures: List[Dict]) -> List[Dict]:
    """Filter fixtures for GW8."""
    return [f for f in fixtures if f['event'] == 8]


def calculate_fixture_difficulty(team_id: int, gw8_fixtures: List[Dict], teams: List[Dict]) -> Dict:
    """
    Calculate fixture difficulty for a team in GW8.

    Returns:
        Dict with opponent, home/away, difficulty
    """
    # Find team's fixture
    fixture = next(
        (f for f in gw8_fixtures if f['team_h'] == team_id or f['team_a'] == team_id),
        None
    )

    if not fixture:
        return {'opponent': 'Unknown', 'is_home': None, 'difficulty': 3}

    is_home = fixture['team_h'] == team_id
    opponent_id = fixture['team_a'] if is_home else fixture['team_h']
    difficulty = fixture['team_h_difficulty'] if is_home else fixture['team_a_difficulty']

    opponent = next((t for t in teams if t['id'] == opponent_id), {})

    return {
        'opponent': opponent.get('short_name', 'Unknown'),
        'is_home': is_home,
        'difficulty': difficulty
    }


def build_player_pool(bootstrap: Dict, dc_recommendations: Dict, gw8_fixtures: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Build position-specific player pools for selection.

    Returns:
        Dict with keys: 'gkp', 'def', 'mid', 'fwd'
    """
    teams = bootstrap['teams']
    all_players = {p['id']: p for p in bootstrap['elements']}

    # Create lookup for DC recommendations (handle both old and new format)
    # New format has top_midfielders_dc, old format has top_midfielders
    mid_key = 'top_midfielders_dc' if 'top_midfielders_dc' in dc_recommendations else 'top_midfielders'

    dc_defender_ids = {p['id'] for p in dc_recommendations.get('top_defenders', [])}
    dc_mid_ids = {p['id'] for p in dc_recommendations.get(mid_key, [])}
    elite_dc_ids = {p['id'] for p in dc_recommendations.get('elite_dc_performers', [])}

    pool = {'gkp': [], 'def': [], 'mid': [], 'fwd': []}

    for player in bootstrap['elements']:
        # Skip unavailable players
        if player['chance_of_playing_next_round'] is not None and player['chance_of_playing_next_round'] < 75:
            continue

        player_id = player['id']
        position = POSITION_MAP[player['element_type']]

        # Get fixture info
        fixture = calculate_fixture_difficulty(player['team'], gw8_fixtures, teams)

        # Enhanced player data
        enhanced = {
            **player,
            'price': player['now_cost'] / 10.0,
            'fixture_gw8': fixture,
            'is_dc_specialist': player_id in dc_defender_ids or player_id in dc_mid_ids,
            'is_elite_dc': player_id in elite_dc_ids,
            'form_num': float(player['form']) if player['form'] else 0.0,
            'points_per_million': player['total_points'] / (player['now_cost'] / 10.0)
        }

        if position == 'GKP':
            pool['gkp'].append(enhanced)
        elif position == 'DEF':
            pool['def'].append(enhanced)
        elif position == 'MID':
            pool['mid'].append(enhanced)
        elif position == 'FWD':
            pool['fwd'].append(enhanced)

    # Sort each pool by relevance
    pool['gkp'].sort(key=lambda p: (p['total_points'], -p['now_cost']), reverse=True)
    pool['def'].sort(key=lambda p: (p['is_elite_dc'], p['is_dc_specialist'], p['total_points']), reverse=True)
    pool['mid'].sort(key=lambda p: (p['is_elite_dc'], p['total_points']), reverse=True)
    pool['fwd'].sort(key=lambda p: (p['total_points'], -p['now_cost']), reverse=True)

    return pool


def select_squad(pool: Dict[str, List[Dict]], budget: int = BUDGET) -> Dict:
    """
    Select Ron's optimal 15-player squad.

    Strategy:
    1. Lock in premium forwards (Haaland)
    2. Build DC-focused defense (3-4 elite DC defenders)
    3. Add DC midfielders (2-3 players)
    4. Fill with attacking threats
    5. Budget bench players

    Returns:
        Dict with squad, formation, captain, spend
    """

    squad = {
        'gkp': [],
        'def': [],
        'mid': [],
        'fwd': []
    }

    remaining_budget = budget
    team_counts = {}  # Track players per team (max 3 allowed)
    MAX_PER_TEAM = 3

    def add_player(position: str, player: Dict) -> bool:
        """
        Helper to add player and track budget + team constraints.

        Returns:
            True if player added, False if would violate constraints
        """
        nonlocal remaining_budget

        # Check team constraint (max 3 per team)
        team_id = player['team']
        current_count = team_counts.get(team_id, 0)
        if current_count >= MAX_PER_TEAM:
            return False

        # Add player
        squad[position].append(player)
        remaining_budget -= player['now_cost']
        team_counts[team_id] = current_count + 1
        return True

    def can_afford_and_team_ok(player: Dict) -> bool:
        """Check if player is affordable and doesn't violate team limit."""
        team_id = player['team']
        return (player['now_cost'] <= remaining_budget and
                team_counts.get(team_id, 0) < MAX_PER_TEAM)

    # Step 1: Goalkeepers (2) - one premium, one budget
    # Premium keeper (£5.0-5.5m)
    premium_gkp = next((p for p in pool['gkp'] if 50 <= p['now_cost'] <= 55 and can_afford_and_team_ok(p)), pool['gkp'][0])
    add_player('gkp', premium_gkp)

    # Budget keeper (£4.0-4.5m) - different team
    budget_gkp = next((p for p in pool['gkp'] if 40 <= p['now_cost'] <= 45 and can_afford_and_team_ok(p)), pool['gkp'][-1])
    add_player('gkp', budget_gkp)

    # Step 2: Premium Forwards (Haaland + one more)
    # Haaland (likely most expensive)
    haaland = next((p for p in pool['fwd'] if 'Haaland' in p['web_name'] and can_afford_and_team_ok(p)), pool['fwd'][0])
    add_player('fwd', haaland)

    # Second premium forward - different team
    second_fwd = next((p for p in pool['fwd'] if p['id'] != haaland['id'] and p['now_cost'] >= 70 and can_afford_and_team_ok(p)), pool['fwd'][1])
    add_player('fwd', second_fwd)

    # Budget enabler forward - different team
    budget_fwd = next((p for p in pool['fwd'] if p['now_cost'] <= 55 and p['id'] not in [f['id'] for f in squad['fwd']] and can_afford_and_team_ok(p)), pool['fwd'][-1])
    add_player('fwd', budget_fwd)

    # Step 3: Defenders (5) - prioritize DC specialists
    # Target: 3-4 elite DC defenders
    dc_defenders = [p for p in pool['def'] if (p['is_dc_specialist'] or p['is_elite_dc']) and can_afford_and_team_ok(p)]

    # Take top DC defenders that fit budget and team constraints
    for defender in dc_defenders[:5]:
        if len(squad['def']) < 5 and defender['now_cost'] <= remaining_budget - 500:  # Keep buffer
            if add_player('def', defender):
                pass  # Successfully added
            # If failed due to team limit, try next

    # Fill remaining defender slots with value picks
    while len(squad['def']) < 5:
        next_def = next(
            (p for p in pool['def']
             if p['id'] not in [d['id'] for d in squad['def']]
             and p['now_cost'] <= 55
             and can_afford_and_team_ok(p)),
            None
        )
        if next_def:
            add_player('def', next_def)
        else:
            # Relax price constraint if needed
            next_def = next(
                (p for p in pool['def']
                 if p['id'] not in [d['id'] for d in squad['def']]
                 and can_afford_and_team_ok(p)),
                pool['def'][0]
            )
            add_player('def', next_def)

    # Step 4: Midfielders (5) - mix of DC specialists and attackers
    # Target: 2 DC midfielders + 3 attacking threats

    # DC midfielders
    dc_mids = [p for p in pool['mid'] if (p['is_dc_specialist'] or p['is_elite_dc']) and can_afford_and_team_ok(p)]
    for midfielder in dc_mids[:2]:
        if len(squad['mid']) < 5:
            add_player('mid', midfielder)

    # Premium attacking midfielders (Salah, Saka, Palmer, Son)
    premium_mids = [
        p for p in pool['mid']
        if p['now_cost'] >= 80
        and p['id'] not in [m['id'] for m in squad['mid']]
        and can_afford_and_team_ok(p)
    ]

    # Add 2-3 premium attackers
    for mid in premium_mids[:3]:
        if len(squad['mid']) < 5 and mid['now_cost'] <= remaining_budget - 200:
            add_player('mid', mid)

    # Fill remaining with value picks
    while len(squad['mid']) < 5:
        next_mid = next(
            (p for p in pool['mid']
             if p['id'] not in [m['id'] for m in squad['mid']]
             and p['now_cost'] <= remaining_budget - 100
             and can_afford_and_team_ok(p)),
            None
        )
        if next_mid:
            add_player('mid', next_mid)
        else:
            # Relax budget constraint if needed
            next_mid = next(
                (p for p in pool['mid']
                 if p['id'] not in [m['id'] for m in squad['mid']]
                 and can_afford_and_team_ok(p)),
                pool['mid'][0]
            )
            add_player('mid', next_mid)

    # Calculate totals
    total_cost = sum(
        p['now_cost'] for position in squad.values() for p in position
    )

    # Validate team distribution (max 3 per team)
    all_players = [p for position in squad.values() for p in position]
    final_team_counts = {}
    for player in all_players:
        team_id = player['team']
        final_team_counts[team_id] = final_team_counts.get(team_id, 0) + 1

    # Check for violations
    violations = {team_id: count for team_id, count in final_team_counts.items() if count > MAX_PER_TEAM}
    if violations:
        print(f"⚠️  WARNING: Team limit violations detected: {violations}")

    return {
        'squad': squad,
        'total_cost': total_cost,
        'budget_remaining': budget - total_cost,
        'formation': '3-5-2',  # Ron's preferred
        'team_distribution': final_team_counts
    }


def select_captain(squad: Dict) -> Tuple[Dict, Dict]:
    """
    Select captain and vice-captain.

    Priority:
    1. Haaland (if in squad)
    2. Salah (if in squad)
    3. Highest-owned premium midfielder
    4. Top forward
    """
    all_players = [p for position in squad['squad'].values() for p in position]

    # Try Haaland first
    captain = next((p for p in all_players if 'Haaland' in p['web_name']), None)

    if not captain:
        # Try Salah
        captain = next((p for p in all_players if 'Salah' in p['web_name']), None)

    if not captain:
        # Highest points overall
        captain = max(all_players, key=lambda p: p['total_points'])

    # Vice-captain: second-highest points, different position
    vice_candidates = [p for p in all_players if p['id'] != captain['id']]
    vice = max(vice_candidates, key=lambda p: p['total_points'])

    return captain, vice


def format_team_announcement(squad_data: Dict, captain: Dict, vice: Dict, dc_recommendations: Dict) -> str:
    """
    Generate Ron's team announcement in his voice.
    """
    squad = squad_data['squad']
    total_cost = squad_data['total_cost'] / 10.0
    budget_remaining = squad_data['budget_remaining'] / 10.0

    # Count DC specialists in squad
    all_players = [p for position in squad.values() for p in position]
    dc_count = sum(1 for p in all_players if p['is_dc_specialist'] or p['is_elite_dc'])

    announcement = f"""
{'=' * 80}
RON CLANKER'S GAMEWEEK 8 SQUAD ANNOUNCEMENT
{'=' * 80}

Right lads, here's how we're setting up for Gameweek 8.

Fresh start. Clean slate. £100m to build something proper.

I've spent the last week analyzing the data - all seven gameweeks worth.
And I'll tell you what I've found: while everyone else is chasing last
week's goals, there's points being left on the table every single week
from defensive work. Those new rules about tackles and clearances? That's
our edge.

{'=' * 80}
THE SQUAD
{'=' * 80}

BETWEEN THE STICKS:
"""

    # Goalkeepers
    for i, gkp in enumerate(squad['gkp'], 1):
        fixture = gkp['fixture_gw8']
        home_away = "at home" if fixture['is_home'] else "away"
        announcement += f"\n  {i}. {gkp['web_name']} (£{gkp['price']:.1f}m) - {fixture['opponent']} ({home_away})"
        if i == 1:
            announcement += f"\n     {gkp['total_points']} points so far. Solid."

    # Defenders
    announcement += "\n\nTHE BACK LINE:\n"
    for i, defender in enumerate(squad['def'], 1):
        fixture = defender['fixture_gw8']
        home_away = "H" if fixture['is_home'] else "A"
        dc_marker = "⭐" if defender['is_elite_dc'] else "✓" if defender['is_dc_specialist'] else ""

        announcement += f"\n  {i}. {defender['web_name']} (£{defender['price']:.1f}m) - {fixture['opponent']} ({home_away}) {dc_marker}"

        if defender['is_dc_specialist'] or defender['is_elite_dc']:
            announcement += f"\n     DC specialist. {defender['total_points']} points. {defender['tackles']} tackles, {defender['clearances_blocks_interceptions']} clearances."

    # Midfielders
    announcement += "\n\nMIDFIELD ENGINE ROOM:\n"
    for i, mid in enumerate(squad['mid'], 1):
        fixture = mid['fixture_gw8']
        home_away = "H" if fixture['is_home'] else "A"
        dc_marker = "⭐" if mid['is_elite_dc'] else "✓" if mid['is_dc_specialist'] else ""

        announcement += f"\n  {i}. {mid['web_name']} (£{mid['price']:.1f}m) - {fixture['opponent']} ({home_away}) {dc_marker}"

        if mid['is_dc_specialist'] or mid['is_elite_dc']:
            announcement += f"\n     {mid['total_points']} pts. Defensive work: {mid.get('tackles', 0)} tackles, {mid.get('clearances_blocks_interceptions', 0)} CBI, {mid.get('recoveries', 0)} recoveries."
        elif mid['total_points'] > 30:
            announcement += f"\n     {mid['total_points']} points. Attacking threat."

    # Forwards
    announcement += "\n\nUP FRONT:\n"
    for i, fwd in enumerate(squad['fwd'], 1):
        fixture = fwd['fixture_gw8']
        home_away = "H" if fixture['is_home'] else "A"

        announcement += f"\n  {i}. {fwd['web_name']} (£{fwd['price']:.1f}m) - {fixture['opponent']} ({home_away})"

        if fwd['id'] == captain['id']:
            announcement += " (C)"
        elif fwd['id'] == vice['id']:
            announcement += " (VC)"

        if fwd['total_points'] > 40:
            announcement += f"\n     {fwd['total_points']} points, {fwd['goals_scored']} goals. Main man."

    # The Gaffer's Logic
    announcement += f"""

{'=' * 80}
THE GAFFER'S LOGIC
{'=' * 80}

This team is built on a simple principle: foundation first, fancy stuff second.

**{dc_count} DEFENSIVE CONTRIBUTION SPECIALISTS** in the squad. That's players who
are earning 2 points from tackles and clearances nearly every week. The market
hasn't caught on yet - they're still pricing them on goals and assists.

Do the math: {dc_count} players x 2 DC points = {dc_count * 2} points per gameweek BEFORE we've
even counted goals, assists, or clean sheets. That's our floor. Our baseline.

Meanwhile, we've got {captain['web_name']} leading the line. {captain['total_points']} points
in 7 games. He gets the armband for Gameweek 8.

CAPTAIN: {captain['web_name']} (C)
VICE-CAPTAIN: {vice['web_name']} (VC)

Reasoning: {captain['web_name']}'s fixture looks favorable. If he can't score this
week, we've got bigger problems.

FORMATION: 3-5-2
- Three at the back, all earning defensive contribution points
- Five in midfield - mix of workers and creators
- Two up top for the goals

BUDGET: £{total_cost:.1f}m spent, £{budget_remaining:.1f}m remaining
CHIPS AVAILABLE: All chips available (2 Wildcards, 2 Bench Boosts, 2 Free Hits, 2 Triple Captains)
CHIP USAGE THIS WEEK: None - saving for when we need it

{'=' * 80}
THE STRATEGY
{'=' * 80}

While everyone else is template-chasing and reacting to last week's hauls,
we're building something sustainable. High floor from defensive work,
high ceiling from premium attackers.

Six gameweeks of data don't lie. The players in this squad have PROVEN
they can deliver. Now it's time to see if the strategy holds up.

Fortune favours the brave, but championships are won with discipline.

Let's get to work.

- Ron

{'=' * 80}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Squad value: £{total_cost:.1f}m
DC specialists: {dc_count}/15 players
{'=' * 80}
"""

    return announcement


def save_squad(squad_data: Dict, captain: Dict, vice: Dict, announcement: str):
    """Save squad selection to files."""
    output_dir = "data/squads"
    os.makedirs(output_dir, exist_ok=True

)

    # Save squad data
    squad_file = os.path.join(output_dir, "gw8_squad.json")
    squad_output = {
        'gameweek': 8,
        'generated': datetime.now().isoformat(),
        'squad': {
            'goalkeepers': [{'id': p['id'], 'name': p['web_name'], 'price': p['price']} for p in squad_data['squad']['gkp']],
            'defenders': [{'id': p['id'], 'name': p['web_name'], 'price': p['price'], 'is_dc_specialist': p['is_dc_specialist']} for p in squad_data['squad']['def']],
            'midfielders': [{'id': p['id'], 'name': p['web_name'], 'price': p['price'], 'is_dc_specialist': p['is_dc_specialist']} for p in squad_data['squad']['mid']],
            'forwards': [{'id': p['id'], 'name': p['web_name'], 'price': p['price']} for p in squad_data['squad']['fwd']],
        },
        'captain': {'id': captain['id'], 'name': captain['web_name']},
        'vice_captain': {'id': vice['id'], 'name': vice['web_name']},
        'formation': squad_data['formation'],
        'total_cost': squad_data['total_cost'] / 10.0,
        'budget_remaining': squad_data['budget_remaining'] / 10.0
    }

    with open(squad_file, 'w') as f:
        json.dump(squad_output, f, indent=2)
    print(f"✅ Squad saved: {squad_file}")

    # Save announcement
    announcement_file = os.path.join(output_dir, "gw8_team_announcement.txt")
    with open(announcement_file, 'w') as f:
        f.write(announcement)
    print(f"✅ Team announcement saved: {announcement_file}")


def main():
    """Main squad selection pipeline."""
    print("\n⚽ RON CLANKER'S SQUAD SELECTOR - GAMEWEEK 8\n")

    # Load DC analysis
    dc_recommendations = load_dc_analysis()
    print(f"✅ Loaded DC analysis: {len(dc_recommendations['elite_dc_performers'])} elite performers identified\n")

    # Fetch latest FPL data
    bootstrap = fetch_bootstrap_data()
    fixtures = fetch_fixtures()
    gw8_fixtures = get_gw8_fixtures(fixtures)

    print(f"✅ {len(gw8_fixtures)} fixtures in Gameweek 8\n")

    # Build player pool
    print("Building player pool...")
    pool = build_player_pool(bootstrap, dc_recommendations, gw8_fixtures)
    print(f"  GKP: {len(pool['gkp'])} available")
    print(f"  DEF: {len(pool['def'])} available")
    print(f"  MID: {len(pool['mid'])} available")
    print(f"  FWD: {len(pool['fwd'])} available\n")

    # Select squad
    print("Selecting Ron's optimal squad...")
    squad_data = select_squad(pool)
    print(f"✅ Squad selected: £{squad_data['total_cost']/10.0:.1f}m spent\n")

    # Select captain
    captain, vice = select_captain(squad_data)
    print(f"✅ Captain: {captain['web_name']}")
    print(f"✅ Vice-Captain: {vice['web_name']}\n")

    # Generate announcement
    print("Generating Ron's team announcement...\n")
    announcement = format_team_announcement(squad_data, captain, vice, dc_recommendations)

    # Print to console
    print(announcement)

    # Save to files
    save_squad(squad_data, captain, vice, announcement)

    print("\n✅ Squad selection complete!")
    print("\nRon's ready for Gameweek 8. Let's show them how it's done.\n")


if __name__ == "__main__":
    main()
