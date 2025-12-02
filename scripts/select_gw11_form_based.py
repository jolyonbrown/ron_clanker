#!/usr/bin/env python3
"""
GW11 Form-Based Team Selection (Emergency Fallback)

Uses simple, proven metrics instead of broken ML predictions:
- Recent form (last 5 games performance)
- Team strength for fixtures
- Defensive contribution potential
- Points per game

This is a TEMPORARY solution for GW11 while ML model is fixed.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from typing import Dict, List, Tuple

GW11 = 11
FREE_TRANSFERS = 3  # Ron rolled transfers - has 3 available!

def get_current_team(db: Database, gameweek: int = 10) -> List[Dict]:
    """Get Ron's current team from previous gameweek."""
    query = """
    SELECT
        dt.player_id,
        dt.position,
        dt.purchase_price,
        dt.selling_price,
        dt.is_captain,
        dt.is_vice_captain,
        p.web_name,
        p.element_type,
        p.now_cost,
        p.team_id,
        p.form
    FROM draft_team dt
    JOIN players p ON dt.player_id = p.id
    WHERE dt.for_gameweek = ?
    ORDER BY dt.position
    """
    return db.execute_query(query, (gameweek,))


def get_gw11_fixtures(db: Database) -> Dict[int, Dict]:
    """Get GW11 fixtures for each team."""
    query = """
    SELECT
        team_h as team_id,
        team_a as opponent_id,
        1 as is_home,
        t.name as team_name,
        t.strength_attack_home as team_attack,
        t.strength_defence_home as team_defence,
        opp.strength_defence_home as opp_defence,
        opp.strength_attack_home as opp_attack
    FROM fixtures f
    JOIN teams t ON f.team_h = t.id
    JOIN teams opp ON f.team_a = opp.id
    WHERE f.event = ?

    UNION ALL

    SELECT
        team_a as team_id,
        team_h as opponent_id,
        0 as is_home,
        t.name as team_name,
        t.strength_attack_away as team_attack,
        t.strength_defence_away as team_defence,
        opp.strength_defence_away as opp_defence,
        opp.strength_attack_away as opp_attack
    FROM fixtures f
    JOIN teams t ON f.team_a = t.id
    JOIN teams opp ON f.team_h = opp.id
    WHERE f.event = ?
    """

    results = db.execute_query(query, (GW11, GW11))
    fixtures = {}
    for row in results:
        fixtures[row['team_id']] = row
    return fixtures


def calculate_form_score(player: Dict, fixture: Dict) -> float:
    """
    Calculate expected points based on form and fixture.

    Simple formula:
    - Base: form * 1.0 (recent performance)
    - Fixture adjustment: +/- 20% based on opponent strength
    - Home bonus: +0.5 if at home
    """
    form = float(player.get('form', 0) or 0)

    if not fixture:
        return form

    # Fixture difficulty (lower opponent strength = easier)
    if player['element_type'] in [3, 4]:  # Attackers
        difficulty = fixture['opp_defence'] / 1200.0  # Normalize around 1.0
    else:  # Defenders/GK
        difficulty = fixture['opp_attack'] / 1200.0

    fixture_modifier = 1.2 - (difficulty - 1.0)  # Easier fixture = higher modifier

    score = form * fixture_modifier

    # Home bonus
    if fixture['is_home']:
        score += 0.5

    return score


def evaluate_transfer_options(
    db: Database,
    current_team: List[Dict],
    fixtures: Dict[int, Dict],
    budget_available: float,
    max_transfers: int = 3
) -> List[Dict]:
    """Find potential transfer improvements across ALL available players."""

    options = []

    for player in current_team:
        position = player['element_type']
        current_price = player['now_cost'] / 10.0
        max_price = current_price + budget_available

        # Get current player's form score
        current_fixture = fixtures.get(player['team_id'])
        current_score = calculate_form_score(player, current_fixture)

        # Find better alternatives in same position - TOP 20 by form
        query = """
        SELECT
            id, web_name, element_type, now_cost, team_id,
            form, points_per_game, total_points, minutes
        FROM players
        WHERE element_type = ?
        AND now_cost <= ?
        AND id NOT IN (SELECT player_id FROM draft_team WHERE for_gameweek = 10)
        AND minutes > 200
        ORDER BY CAST(form AS REAL) DESC
        LIMIT 20
        """

        alternatives = db.execute_query(query, (position, int(max_price * 10)))

        for alt in alternatives:
            alt_fixture = fixtures.get(alt['team_id'])
            alt_score = calculate_form_score(alt, alt_fixture)

            improvement = alt_score - current_score

            # Lower threshold for suggestions since we have 3 FTs
            if improvement > 0.5:
                options.append({
                    'player_out': player,
                    'player_in': alt,
                    'improvement': improvement,
                    'current_score': current_score,
                    'new_score': alt_score,
                    'cost_change': (alt['now_cost'] / 10.0) - current_price
                })

    return sorted(options, key=lambda x: x['improvement'], reverse=True)


def assess_captain_choice(team: List[Dict], fixtures: Dict[int, Dict]) -> Tuple[Dict, Dict]:
    """Choose captain and vice-captain based on form + fixture."""

    # Calculate score for each player
    scores = []
    for player in team:
        if player['position'] > 11:  # Skip bench
            continue

        fixture = fixtures.get(player['team_id'])
        score = calculate_form_score(player, fixture)

        # Premium forwards/mids get bonus (higher ceiling)
        price = player['now_cost'] / 10.0
        if player['element_type'] in [3, 4] and price > 10.0:
            score *= 1.15

        scores.append((player, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    captain = scores[0][0] if scores else None
    vice = scores[1][0] if len(scores) > 1 else None

    return captain, vice


def make_gw11_decision(db: Database):
    """Main decision logic for GW11."""

    print("\n" + "="*80)
    print("RON CLANKER - GW11 FORM-BASED TEAM SELECTION")
    print("="*80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nMethod: Form + Fixture Analysis (ML predictions disabled)")
    print("="*80)

    # Get current team
    current_team = get_current_team(db, gameweek=10)

    if not current_team:
        print("\n❌ ERROR: No team found for GW10")
        print("Cannot proceed without starting team.")
        return

    print(f"\n📋 Current Team ({len(current_team)} players):")
    for p in current_team[:11]:
        print(f"  {p['position']:2d}. {p['web_name']:20s} (Form: {p.get('form', 'N/A')})")

    # Get fixtures
    fixtures = get_gw11_fixtures(db)

    print(f"\n📅 GW11 Fixtures loaded: {len(fixtures)} teams")

    # Calculate budget
    team_value = sum(p['now_cost'] for p in current_team) / 10.0
    budget_available = 100.0 - team_value

    print(f"\n💰 Budget Analysis:")
    print(f"  Team Value: £{team_value:.1f}m")
    print(f"  Available: £{budget_available:.1f}m")

    # Evaluate transfer options
    print(f"\n🔄 Evaluating Transfer Options...")
    transfer_options = evaluate_transfer_options(db, current_team, fixtures, budget_available)

    if transfer_options:
        print(f"\n   Found {len(transfer_options)} potential improvements:")
        for i, opt in enumerate(transfer_options[:5], 1):
            print(f"\n   {i}. {opt['player_out']['web_name']} → {opt['player_in']['web_name']}")
            print(f"      Current: {opt['current_score']:.2f} | New: {opt['new_score']:.2f} | Gain: +{opt['improvement']:.2f}")
            print(f"      Price: £{opt['player_out']['now_cost']/10.0:.1f}m → £{opt['player_in']['now_cost']/10.0:.1f}m")
    else:
        print("   No significant improvements found.")

    # Decide on transfer
    make_transfer = False
    transfer_decision = None

    if transfer_options and transfer_options[0]['improvement'] > 2.0:
        make_transfer = True
        transfer_decision = transfer_options[0]
        print(f"\n✅ DECISION: Make 1 Free Transfer")
        print(f"   OUT: {transfer_decision['player_out']['web_name']}")
        print(f"   IN:  {transfer_decision['player_in']['web_name']}")
        print(f"   Expected Gain: +{transfer_decision['improvement']:.2f} points")
    else:
        print(f"\n✅ DECISION: Roll Transfer (save for next week)")
        print(f"   No transfer offers >2.0 point improvement")

    # Update team for GW11
    team_gw11 = current_team.copy()
    if make_transfer:
        # Remove old player, add new one
        team_gw11 = [p for p in team_gw11 if p['player_id'] != transfer_decision['player_out']['player_id']]

        new_player = transfer_decision['player_in'].copy()
        new_player['position'] = transfer_decision['player_out']['position']
        new_player['purchase_price'] = new_player['now_cost']  # Current price
        new_player['selling_price'] = new_player['now_cost']
        team_gw11.append(new_player)

    # Choose captain
    captain, vice = assess_captain_choice(team_gw11, fixtures)

    print(f"\n👑 Captain Choices:")
    print(f"   Captain: {captain['web_name'] if captain else 'N/A'}")
    print(f"   Vice:    {vice['web_name'] if vice else 'N/A'}")

    # Save to database
    print(f"\n💾 Saving GW11 Team to Database...")

    # Clear any existing GW11 draft
    db.execute_update("DELETE FROM draft_team WHERE for_gameweek = ?", (GW11,))

    # Insert GW11 team
    for player in team_gw11:
        is_captain = captain and player['player_id'] == captain['player_id']
        is_vice = vice and player['player_id'] == vice['player_id']

        # Use existing purchase/selling price, or current price for new players
        purchase_price = player.get('purchase_price', player['now_cost'])
        selling_price = player.get('selling_price', player['now_cost'])

        db.execute_update("""
            INSERT INTO draft_team
            (for_gameweek, player_id, position, purchase_price, selling_price, is_captain, is_vice_captain)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (GW11, player['player_id'], player['position'], purchase_price, selling_price, is_captain, is_vice))

    # Log transfer if made
    if make_transfer:
        db.execute_update("""
            INSERT INTO transfers
            (gameweek, player_out_id, player_in_id, transfer_cost, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (
            GW11,
            transfer_decision['player_out']['player_id'],
            transfer_decision['player_in']['player_id'],
            0,  # Free transfer
            f"Form-based: +{transfer_decision['improvement']:.2f} expected gain"
        ))

    print(f"✅ Team saved successfully")

    # Log decision
    decision_summary = {
        'method': 'form_based_fallback',
        'transfer_made': make_transfer,
        'transfer_details': transfer_decision if make_transfer else None,
        'captain': captain['web_name'] if captain else None,
        'vice_captain': vice['web_name'] if vice else None,
        'timestamp': datetime.now().isoformat()
    }

    import json
    db.execute_update("""
        INSERT INTO decisions
        (gameweek, decision_type, decision_data, reasoning)
        VALUES (?, ?, ?, ?)
    """, (
        GW11,
        'team_selection',
        json.dumps(decision_summary),
        'Emergency form-based selection due to broken ML predictions'
    ))

    print("\n" + "="*80)
    print("GW11 TEAM SELECTION COMPLETE")
    print("="*80)

    return {
        'team': team_gw11,
        'captain': captain,
        'vice': vice,
        'transfer': transfer_decision if make_transfer else None
    }


if __name__ == "__main__":
    db = Database()
    result = make_gw11_decision(db)

    print("\n🎯 Next Steps:")
    print("   1. Review team in database")
    print("   2. Generate Ron's announcement")
    print("   3. Post to Slack")
    print("\n")
