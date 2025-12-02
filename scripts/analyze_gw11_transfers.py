#!/usr/bin/env python3
"""
Analyze GW11 Transfer Options with 3 Free Transfers

Based on intelligence gathered, recommend optimal transfers.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

def main():
    db = Database()

    print("\n" + "=" * 80)
    print("GW11 TRANSFER ANALYSIS - 3 FREE TRANSFERS AVAILABLE")
    print("=" * 80)
    print()

    # Current team
    team = db.execute_query("""
        SELECT
            dt.position,
            p.web_name,
            p.element_type,
            p.form,
            p.now_cost/10.0 as price,
            t.short_name as team,
            dt.is_captain,
            dt.is_vice_captain
        FROM draft_team dt
        JOIN players p ON dt.player_id = p.id
        JOIN teams t ON p.team_id = t.id
        WHERE dt.for_gameweek = 10
        ORDER BY dt.position
    """)

    print("CURRENT TEAM (GW10):")
    print()
    for p in team[:11]:
        marker = " (C)" if p['is_captain'] else " (VC)" if p['is_vice_captain'] else ""
        form_str = str(p['form']) if p['form'] else 'N/A'
        print(f"  {p['position']:2d}. {p['web_name']:20s} - Form: {form_str:>4s} | £{p['price']:.1f}m{marker}")

    print("\nBENCH:")
    for p in team[11:]:
        form_str = str(p['form']) if p['form'] else 'N/A'
        print(f"  {p['position']:2d}. {p['web_name']:20s} - Form: {form_str:>4s} | £{p['price']:.1f}m")

    print()
    print("=" * 80)
    print("INTELLIGENCE-BASED TRANSFER RECOMMENDATIONS")
    print("=" * 80)
    print()

    # Key findings from intelligence
    print("🔍 KEY FINDINGS FROM INTELLIGENCE:")
    print()
    print("1. GABRIEL (BENCHED) - 11.0 form, 55 pts in last 5 GWs")
    print("   • MORE than Haaland's 52 points!")
    print("   • Arsenal defense is 'historically elite'")
    print("   • 3 assists, 1 goal recently")
    print("   • Best xGC in league")
    print("   ➡️  SHOULD BE STARTING")
    print()

    print("2. NDIAYE (STARTING) - 5.0 form")
    print("   • 'Lack of shots, poor fixtures'")
    print("   • Needs selling before AFCON")
    print("   • Injury doubt (but not serious)")
    print("   ➡️  CONSIDER TRANSFER OUT")
    print()

    print("3. SARR (BENCHED) - 2.3 form")
    print("   • Hamstring tightness ⚠️")
    print("   • Despite this, Palace have top xG (19.0)")
    print("   ➡️  INJURY CONCERN")
    print()

    print("4. JOÃO PEDRO (STARTING) - 4.3 form")
    print("   • Chelsea have excellent fixtures ahead")
    print("   ➡️  COULD IMPROVE")
    print()

    print("5. BURN (STARTING) - 1.7 form")
    print("   • Lowest form in starting XI")
    print("   • Newsletter: scored header vs Brentford")
    print("   ➡️  LOW FORM BUT ATTACKING THREAT")
    print()

    print()
    print("=" * 80)
    print("RECOMMENDED TRANSFER STRATEGY")
    print("=" * 80)
    print()

    print("OPTION 1: DEFENSIVE RESHUFFLE (USE 1-2 TRANSFERS)")
    print()
    print("  Transfer 1: MOVE GABRIEL TO STARTING XI")
    print("    • OUT: Burn (1.7 form, £5.2m)")
    print("    • Action: Just swap positions - Gabriel starts, Burn benched")
    print("    • Rationale: Gabriel is in incredible form, wasting 11.0 form on bench")
    print()
    print("  Transfer 2: UPGRADE BENCH COVER")
    print("    • OUT: Sarr (hamstring doubt, 2.3 form)")
    print("    • IN: Better Palace mid or other £6.6m option")
    print("    • Rationale: Injury risk, low form")
    print()

    print()
    print("OPTION 2: MIDFIELD REFRESH (USE 2-3 TRANSFERS)")
    print()
    print("  Transfer 1: FIX GABRIEL ISSUE")
    print("    • Swap Burn ↔ Gabriel positions (Gabriel starts)")
    print()
    print("  Transfer 2: UPGRADE NDIAYE")
    print("    • OUT: Ndiaye (£6.5m, poor fixtures, AFCON risk)")
    print("    • IN: Better £6-7m midfielder")
    print("    • Budget check: £4.2m in bank + £6.5m = £10.7m available")
    print()
    print("  Transfer 3: OPTIONAL - FIX SARR ISSUE")
    print("    • OUT: Sarr (injury doubt)")
    print("    • IN: Bench fodder or better Palace option")
    print()

    print()
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print()
    print("USE 1 TRANSFER MINIMUM:")
    print("  • Swap Gabriel into starting XI (move Burn to bench)")
    print("  • This is FREE (just positional change)")
    print("  • Gabriel's form (11.0) vs Burn's (1.7) makes this essential")
    print()
    print("CONSIDER 2ND TRANSFER:")
    print("  • OUT: Ndiaye (poor fixtures, AFCON risk)")
    print("  • With £10.7m available, could upgrade significantly")
    print()
    print("HOLD 3RD TRANSFER:")
    print("  • Save for GW12 flexibility")
    print("  • International break = 2 weeks to assess")
    print()

    # Check budget
    team_value = sum(p['price'] for p in team)
    bank = 100.0 - team_value

    print(f"BUDGET STATUS:")
    print(f"  Team Value: £{team_value:.1f}m")
    print(f"  In Bank: £{bank:.1f}m")
    print()

    return 0

if __name__ == '__main__':
    sys.exit(main())
