#!/usr/bin/env python3
"""
Analyze Ron's GW8 lineup with formation constraints.
Shows what ML would recommend respecting FPL rules.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ml.prediction.features import FeatureEngineer
from ml.prediction.model import PlayerPerformancePredictor

def main():
    db = Database()
    fe = FeatureEngineer(db)
    predictor = PlayerPerformancePredictor(model_dir=project_root / 'models' / 'prediction')
    predictor.load_models(version='gw8_v1')

    # Get Ron's team with predictions
    team = db.execute_query('''
        SELECT p.id, p.web_name, p.element_type, mt.position, mt.is_captain
        FROM my_team mt
        JOIN players p ON mt.player_id = p.id
        WHERE mt.gameweek = 8
    ''')

    # Add xPts predictions
    players_with_xpts = []
    for p in team:
        features = fe.engineer_features(p['id'], 8)
        if features:
            xpts = predictor.predict(features)
            players_with_xpts.append({
                'name': p['web_name'],
                'position': p['element_type'],
                'current_pos': p['position'],
                'is_captain': p['is_captain'],
                'xpts': xpts
            })

    # Separate by position
    gk = [p for p in players_with_xpts if p['position'] == 1]
    defs = [p for p in players_with_xpts if p['position'] == 2]
    mids = [p for p in players_with_xpts if p['position'] == 3]
    fwds = [p for p in players_with_xpts if p['position'] == 4]

    # Sort each position by xPts
    gk.sort(key=lambda x: x['xpts'], reverse=True)
    defs.sort(key=lambda x: x['xpts'], reverse=True)
    mids.sort(key=lambda x: x['xpts'], reverse=True)
    fwds.sort(key=lambda x: x['xpts'], reverse=True)

    print('=' * 80)
    print('FORMATION OPTIMIZATION - RESPECTING FPL RULES')
    print('=' * 80)

    # Valid formations: (GK, DEF, MID, FWD)
    formations = [
        (1, 3, 4, 3), (1, 3, 5, 2), (1, 4, 3, 3),
        (1, 4, 4, 2), (1, 4, 5, 1), (1, 5, 3, 2),
        (1, 5, 4, 1)
    ]

    # Evaluate each formation
    best_formation = None
    best_total = 0

    for form in formations:
        gk_count, def_count, mid_count, fwd_count = form

        # Select best players for this formation
        selected_gk = gk[:gk_count]
        selected_def = defs[:def_count]
        selected_mid = mids[:mid_count]
        selected_fwd = fwds[:fwd_count]

        # Calculate total xPts
        total_xpts = sum(p['xpts'] for p in selected_gk + selected_def + selected_mid + selected_fwd)

        if total_xpts > best_total:
            best_total = total_xpts
            best_formation = {
                'formation': f'{def_count}-{mid_count}-{fwd_count}',
                'gk': selected_gk,
                'def': selected_def,
                'mid': selected_mid,
                'fwd': selected_fwd,
                'total': total_xpts
            }

    # Show current formation
    print('\n📊 CURRENT LINEUP:')
    current_starters = [p for p in players_with_xpts if p['current_pos'] <= 11]
    current_gk = [p for p in current_starters if p['position'] == 1]
    current_def = [p for p in current_starters if p['position'] == 2]
    current_mid = [p for p in current_starters if p['position'] == 3]
    current_fwd = [p for p in current_starters if p['position'] == 4]

    current_formation = f'{len(current_def)}-{len(current_mid)}-{len(current_fwd)}'
    current_total = sum(p['xpts'] for p in current_starters)

    print(f'\n  Formation: {current_formation}')
    print(f'  GK:  {current_gk[0]["name"]} ({current_gk[0]["xpts"]:.2f})')
    print(f'  DEF:', ', '.join([f'{p["name"]} ({p["xpts"]:.2f})' for p in current_def]))
    print(f'  MID:', ', '.join([f'{p["name"]} ({p["xpts"]:.2f})' for p in current_mid]))
    print(f'  FWD:', ', '.join([f'{p["name"]} ({p["xpts"]:.2f})' for p in current_fwd]))
    print(f'\n  Total xPts: {current_total:.2f}')

    # Show ML optimal formation
    print('\n✅ ML OPTIMAL LINEUP:')
    print(f'\n  Formation: {best_formation["formation"]}')
    print(f'  GK:  {best_formation["gk"][0]["name"]} ({best_formation["gk"][0]["xpts"]:.2f})')
    print(f'  DEF:', ', '.join([f'{p["name"]} ({p["xpts"]:.2f})' for p in best_formation["def"]]))
    print(f'  MID:', ', '.join([f'{p["name"]} ({p["xpts"]:.2f})' for p in best_formation["mid"]]))
    print(f'  FWD:', ', '.join([f'{p["name"]} ({p["xpts"]:.2f})' for p in best_formation["fwd"]]))
    print(f'\n  Total xPts: {best_formation["total"]:.2f}')

    improvement = best_formation['total'] - current_total
    print(f'\n📈 Formation improvement: +{improvement:.2f} pts')

    # Captain recommendation
    all_selected = best_formation['gk'] + best_formation['def'] + best_formation['mid'] + best_formation['fwd']
    all_selected.sort(key=lambda x: x['xpts'], reverse=True)
    best_captain = all_selected[0]

    current_captain = [p for p in players_with_xpts if p['is_captain']][0]

    print(f'\n🎯 CAPTAIN:')
    print(f'  Current: {current_captain["name"]} ({current_captain["xpts"]:.2f} xPts)')
    print(f'  ML Recommended: {best_captain["name"]} ({best_captain["xpts"]:.2f} xPts)')
    cap_gain = best_captain['xpts'] - current_captain['xpts']
    print(f'  Captaincy gain: +{cap_gain:.2f} pts')

    print(f'\n💡 TOTAL POTENTIAL IMPROVEMENT: +{improvement + cap_gain:.2f} pts')
    print()


if __name__ == '__main__':
    main()
