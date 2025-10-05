#!/usr/bin/env python3
"""
Fixture Monitor - Track DGWs, BGWs, and Postponements

Monitors the fixture list for changes that affect chip strategy:
- Double Gameweeks (DGWs) - Teams playing twice
- Blank Gameweeks (BGWs) - Teams not playing
- Postponements and rescheduling
- Fixture difficulty changes

Saves fixture snapshots weekly to detect deltas.

Usage:
    python scripts/monitor_fixtures.py
    python scripts/monitor_fixtures.py --check-changes
    python scripts/monitor_fixtures.py --show-upcoming 6
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from datetime import datetime
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FPL_BASE_URL = "https://fantasy.premierleague.com/api"


def fetch_fixtures():
    """Fetch all fixtures from FPL API"""
    response = requests.get(f"{FPL_BASE_URL}/fixtures/")
    response.raise_for_status()
    return response.json()


def fetch_bootstrap():
    """Fetch bootstrap data for teams and gameweeks"""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def save_fixture_snapshot(fixtures, bootstrap):
    """Save current fixture state for delta detection"""
    output_dir = project_root / 'data' / 'fixtures'
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    current_gw = next((e['id'] for e in bootstrap['events'] if e['is_current']), 1)

    snapshot = {
        'timestamp': timestamp,
        'current_gameweek': current_gw,
        'fixtures': fixtures,
        'teams': bootstrap['teams'],
        'events': bootstrap['events']
    }

    output_file = output_dir / f'fixtures_snapshot_{timestamp}.json'
    with open(output_file, 'w') as f:
        json.dump(snapshot, f, indent=2)

    # Also save as 'latest' for easy comparison
    latest_file = output_dir / 'fixtures_latest.json'
    with open(latest_file, 'w') as f:
        json.dump(snapshot, f, indent=2)

    print(f"💾 Fixture snapshot saved: {output_file}")
    return output_file


def load_previous_snapshot():
    """Load the most recent previous snapshot"""
    fixtures_dir = project_root / 'data' / 'fixtures'
    if not fixtures_dir.exists():
        return None

    latest_file = fixtures_dir / 'fixtures_latest.json'
    if not latest_file.exists():
        return None

    with open(latest_file, 'r') as f:
        return json.load(f)


def detect_fixture_changes(current_fixtures, previous_snapshot):
    """Detect changes in fixtures since last snapshot"""
    if not previous_snapshot:
        return {
            'new_fixtures': [],
            'postponed': [],
            'rescheduled': [],
            'dgw_changes': [],
            'bgw_changes': []
        }

    previous_fixtures = {f['id']: f for f in previous_snapshot['fixtures']}
    current_fixtures_dict = {f['id']: f for f in current_fixtures}

    changes = {
        'new_fixtures': [],
        'postponed': [],
        'rescheduled': [],
        'dgw_changes': [],
        'bgw_changes': []
    }

    # Check for new fixtures
    for fixture_id, fixture in current_fixtures_dict.items():
        if fixture_id not in previous_fixtures:
            changes['new_fixtures'].append(fixture)

    # Check for postponements/rescheduling
    for fixture_id, old_fixture in previous_fixtures.items():
        current = current_fixtures_dict.get(fixture_id)

        if not current:
            continue

        # Check if gameweek changed (rescheduled)
        if old_fixture['event'] != current['event']:
            changes['rescheduled'].append({
                'fixture': current,
                'old_gw': old_fixture['event'],
                'new_gw': current['event']
            })

        # Check if postponed (event set to None)
        if old_fixture['event'] is not None and current['event'] is None:
            changes['postponed'].append({
                'fixture': current,
                'original_gw': old_fixture['event']
            })

    return changes


def analyze_dgws_and_bgws(fixtures, bootstrap, upcoming_gws=10):
    """Analyze upcoming gameweeks for DGWs and BGWs"""
    teams = {t['id']: t for t in bootstrap['teams']}
    current_gw = next((e['id'] for e in bootstrap['events'] if e['is_current']), 1)

    # Count fixtures per team per gameweek
    fixtures_per_team_gw = defaultdict(lambda: defaultdict(int))

    for fixture in fixtures:
        if fixture['event'] is None:
            continue

        gw = fixture['event']
        if gw < current_gw or gw > current_gw + upcoming_gws:
            continue

        home_team = fixture['team_h']
        away_team = fixture['team_a']

        fixtures_per_team_gw[gw][home_team] += 1
        fixtures_per_team_gw[gw][away_team] += 1

    # Identify DGWs and BGWs
    dgws = defaultdict(list)  # GW -> [teams with 2+ fixtures]
    bgws = defaultdict(list)  # GW -> [teams with 0 fixtures]

    for gw in range(current_gw, current_gw + upcoming_gws + 1):
        for team_id, team in teams.items():
            fixture_count = fixtures_per_team_gw[gw].get(team_id, 0)

            if fixture_count >= 2:
                dgws[gw].append({
                    'team': team['short_name'],
                    'team_id': team_id,
                    'fixtures': fixture_count
                })
            elif fixture_count == 0:
                bgws[gw].append({
                    'team': team['short_name'],
                    'team_id': team_id
                })

    return dgws, bgws


def display_fixture_report(fixtures, bootstrap, show_upcoming=6):
    """Display comprehensive fixture report"""
    teams = {t['id']: t for t in bootstrap['teams']}
    current_gw = next((e['id'] for e in bootstrap['events'] if e['is_current']), 1)

    print("\n" + "=" * 100)
    print("FIXTURE MONITORING REPORT")
    print("=" * 100)
    print(f"Date: {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print(f"Current Gameweek: {current_gw}")
    print(f"Total Fixtures: {len(fixtures)}")
    print("=" * 100)

    # Analyze DGWs/BGWs
    dgws, bgws = analyze_dgws_and_bgws(fixtures, bootstrap, show_upcoming)

    # Report DGWs
    print("\n" + "=" * 100)
    print("🎯 DOUBLE GAMEWEEKS (DGWs) - CHIP OPPORTUNITIES")
    print("=" * 100)

    dgw_found = False
    for gw in sorted(dgws.keys()):
        if dgws[gw]:
            dgw_found = True
            print(f"\n📅 GAMEWEEK {gw} - {len(dgws[gw])} teams with DGW:")
            for team_info in dgws[gw]:
                print(f"   🔥 {team_info['team']} - {team_info['fixtures']} fixtures")

    if not dgw_found:
        print(f"\n✅ No DGWs detected in next {show_upcoming} gameweeks")
        print("   (DGWs typically occur after cup rounds or postponements)")

    # Report BGWs
    print("\n" + "=" * 100)
    print("⚠️  BLANK GAMEWEEKS (BGWs) - PLAN AHEAD")
    print("=" * 100)

    bgw_found = False
    for gw in sorted(bgws.keys()):
        if bgws[gw]:
            bgw_found = True
            print(f"\n📅 GAMEWEEK {gw} - {len(bgws[gw])} teams with BGW:")
            for team_info in bgws[gw]:
                print(f"   ❌ {team_info['team']} - NO FIXTURE")

    if not bgw_found:
        print(f"\n✅ No BGWs detected in next {show_upcoming} gameweeks")

    # Postponed fixtures (no gameweek assigned)
    postponed = [f for f in fixtures if f['event'] is None]
    if postponed:
        print("\n" + "=" * 100)
        print("⏸️  POSTPONED FIXTURES (To Be Rescheduled)")
        print("=" * 100)
        for fix in postponed[:10]:  # Show first 10
            home = teams[fix['team_h']]['short_name']
            away = teams[fix['team_a']]['short_name']
            print(f"   {home} vs {away} - TBD")

    # Upcoming key fixtures
    print("\n" + "=" * 100)
    print(f"📅 NEXT {show_upcoming} GAMEWEEKS OVERVIEW")
    print("=" * 100)

    for gw in range(current_gw, min(current_gw + show_upcoming, 39)):
        gw_fixtures = [f for f in fixtures if f['event'] == gw]
        dgw_count = len(dgws.get(gw, []))
        bgw_count = len(bgws.get(gw, []))

        status = ""
        if dgw_count > 0:
            status = f"🎯 DGW ({dgw_count} teams)"
        elif bgw_count > 0:
            status = f"⚠️  BGW ({bgw_count} teams)"

        print(f"   GW{gw:2d}: {len(gw_fixtures):2d} fixtures {status}")


def display_changes_report(changes, teams):
    """Display fixture changes detected"""
    print("\n" + "=" * 100)
    print("🔔 FIXTURE CHANGES DETECTED")
    print("=" * 100)

    total_changes = (
        len(changes['new_fixtures']) +
        len(changes['postponed']) +
        len(changes['rescheduled'])
    )

    if total_changes == 0:
        print("\n✅ No fixture changes since last check")
        return

    print(f"\n⚠️  {total_changes} changes detected!")

    # New fixtures
    if changes['new_fixtures']:
        print(f"\n📅 NEW FIXTURES ADDED: {len(changes['new_fixtures'])}")
        for fix in changes['new_fixtures'][:10]:
            home = teams[fix['team_h']]['short_name']
            away = teams[fix['team_a']]['short_name']
            gw = fix['event'] if fix['event'] else 'TBD'
            print(f"   GW{gw}: {home} vs {away}")

    # Postponed
    if changes['postponed']:
        print(f"\n⏸️  POSTPONED: {len(changes['postponed'])}")
        for item in changes['postponed']:
            fix = item['fixture']
            home = teams[fix['team_h']]['short_name']
            away = teams[fix['team_a']]['short_name']
            print(f"   {home} vs {away} (was GW{item['original_gw']})")

    # Rescheduled
    if changes['rescheduled']:
        print(f"\n🔄 RESCHEDULED: {len(changes['rescheduled'])}")
        for item in changes['rescheduled']:
            fix = item['fixture']
            home = teams[fix['team_h']]['short_name']
            away = teams[fix['team_a']]['short_name']
            print(f"   {home} vs {away}: GW{item['old_gw']} → GW{item['new_gw']}")


def generate_chip_recommendations(dgws, bgws, current_gw):
    """Generate chip strategy recommendations based on fixtures"""
    print("\n" + "=" * 100)
    print("💡 TERRY'S CHIP STRATEGY RECOMMENDATIONS")
    print("=" * 100)

    recommendations = []

    # Check for DGWs in next 6 weeks
    near_dgws = {gw: teams for gw, teams in dgws.items() if current_gw <= gw <= current_gw + 6}

    if near_dgws:
        print("\n🎯 UPCOMING DGW OPPORTUNITIES:")
        for gw, teams in sorted(near_dgws.items()):
            print(f"\nGW{gw}: {len(teams)} teams with DGW")
            print("   💡 Consider:")
            print("      - Wildcard before GW to load up on DGW players")
            print("      - Bench Boost during GW (if bench has DGW players)")
            print("      - Triple Captain on best DGW option (premium with good fixtures)")
    else:
        print("\n✅ No DGWs in next 6 weeks")
        print("   - Hold chips for now")
        print("   - Continue normal transfer strategy")

    # Check for BGWs
    near_bgws = {gw: teams for gw, teams in bgws.items() if current_gw <= gw <= current_gw + 6}

    if near_bgws:
        print("\n⚠️  UPCOMING BGW WARNINGS:")
        for gw, teams in sorted(near_bgws.items()):
            if len(teams) >= 4:  # Significant BGW
                print(f"\nGW{gw}: {len(teams)} teams with NO fixture")
                print("   💡 Consider:")
                print("      - Free Hit to field full team")
                print("      - Or ensure enough non-blank players in squad")


def main():
    parser = argparse.ArgumentParser(description="Monitor fixtures for DGWs, BGWs, and changes")
    parser.add_argument('--check-changes', action='store_true',
                       help='Compare to previous snapshot and show changes')
    parser.add_argument('--show-upcoming', type=int, default=6,
                       help='Number of upcoming gameweeks to analyze (default: 6)')
    parser.add_argument('--save', action='store_true',
                       help='Save current fixture snapshot')

    args = parser.parse_args()

    try:
        print("📥 Fetching fixture data...")
        fixtures = fetch_fixtures()
        bootstrap = fetch_bootstrap()

        teams = {t['id']: t for t in bootstrap['teams']}
        current_gw = next((e['id'] for e in bootstrap['events'] if e['is_current']), 1)

        # Display main report
        display_fixture_report(fixtures, bootstrap, args.show_upcoming)

        # Check for changes if requested
        if args.check_changes:
            previous = load_previous_snapshot()
            if previous:
                changes = detect_fixture_changes(fixtures, previous)
                display_changes_report(changes, teams)
            else:
                print("\n⚠️  No previous snapshot found - this is the first check")

        # Generate chip recommendations
        dgws, bgws = analyze_dgws_and_bgws(fixtures, bootstrap, args.show_upcoming)
        generate_chip_recommendations(dgws, bgws, current_gw)

        # Always save snapshot for future comparisons (or if explicitly requested)
        if args.save or args.check_changes:
            save_fixture_snapshot(fixtures, bootstrap)

        print("\n" + "=" * 100)
        print("✅ FIXTURE MONITORING COMPLETE")
        print("=" * 100)
        print("\n💡 TIP: Run weekly with --check-changes to detect DGW/BGW announcements")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
