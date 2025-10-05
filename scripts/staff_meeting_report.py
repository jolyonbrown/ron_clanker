#!/usr/bin/env python3
"""
Generate Ron's Weekly Staff Meeting Report

Combines all analysis into a comprehensive staff meeting format.
Each specialist presents their findings, Ron makes decisions.

Usage:
    python scripts/staff_meeting_report.py --gw 8
    python scripts/staff_meeting_report.py --gw 8 --save
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import json
from datetime import datetime


def load_gw_analysis(gameweek: int) -> dict:
    """Load gameweek analysis results."""
    analysis_file = f"data/gw_results/gw{gameweek}_analysis.json"

    if not os.path.exists(analysis_file):
        print(f"❌ Analysis not found. Run: python scripts/analyze_gw_results.py --gw {gameweek} --save-report")
        sys.exit(1)

    with open(analysis_file) as f:
        return json.load(f)


def generate_meeting_report(analysis: dict, gameweek: int) -> str:
    """Generate formatted staff meeting report."""

    gw = gameweek
    next_gw = gw + 1

    report = f"""
{'=' * 90}
STAFF MEETING - GAMEWEEK {gw} REVIEW
Two Points FC - Tactical Debrief
{'=' * 90}

📅 Date: {datetime.now().strftime('%A, %B %d, %Y')}
⏰ Time: Monday Morning, Post-GW{gw}
📍 Location: The Gaffer's Office

ATTENDEES:
- Ron Clanker (Manager)
- Dr. Eleanor Wright (Learning & Performance)
- Margaret Stephenson (Head of Analysis)
- Derek Thompson (Defensive Coach)
- Sophia Martinez (Attacking Coach)
- Priya Chakraborty (Fixture Analyst)
- James O'Brien (Strategy & Value)
- Terence Williams (Chip Specialist)

{'=' * 90}

RON: "Right, let's get started. Ellie, what's the damage?"

{'=' * 90}
1. ELLIE'S PERFORMANCE REVIEW
{'=' * 90}

**Final Score: {analysis['final_score']} points**

Predicted Range: 65-75 points (baseline)
Actual: {analysis['final_score']} points
Variance: {analysis['final_score'] - 70:+.0f} pts from midpoint

vs Average: {analysis['comparison']['average_score']} pts ({analysis['vs_average']:+.0f})
vs Highest: {analysis['comparison']['highest_score']} pts

**Result: {'✅ BEAT AVERAGE' if analysis['beat_average'] else '❌ BELOW AVERAGE'}**

KEY LEARNINGS:
"""

    for learning in analysis['learnings']:
        report += f"  • {learning}\n"

    report += f"""
ELLIE: "{analysis['staff_comments']['ellie']}"

{'=' * 90}

RON: "Maggie, the numbers."

{'=' * 90}
2. MAGGIE'S DATA UPDATE
{'=' * 90}

POINTS BREAKDOWN:
  • Starting XI: {analysis['points_breakdown']['starting_xi']} pts
  • Captain Contribution: {analysis['points_breakdown']['captain']} pts
  • Bench: {analysis['points_breakdown']['bench']} pts
  • DC Points: {analysis['points_breakdown']['dc_points']} pts
  • Bonus Points: {analysis['points_breakdown']['bonus']} pts

DC ANALYSIS:
  • Players Earning DC: {analysis['dc_analysis']['dc_earners']}/15
  • Total DC Points: {analysis['dc_analysis']['total_dc_points']}
  • DC % of Total: {analysis['dc_analysis']['dc_contribution_pct']:.1f}%

MAGGIE: "{analysis['staff_comments']['maggie']}"

RON: "So the DC strategy..."

MAGGIE: "{'Working as designed.' if analysis['dc_analysis']['dc_earners'] >= 8 else 'Below expectations. Need to investigate individual performances.'}"

{'=' * 90}

RON: "Digger, defensive work."

{'=' * 90}
3. DIGGER'S DEFENSIVE ANALYSIS
{'=' * 90}

DC EARNERS THIS WEEK:
"""

    dc_players = analysis['dc_analysis']['dc_player_names']
    for i, player in enumerate(dc_players, 1):
        report += f"  {i}. {player}\n"

    if not dc_players:
        report += "  ⚠️  No players earned DC points\n"

    report += f"""
DIGGER: "{analysis['staff_comments']['digger']}"

RON: "That's {'proper' if analysis['dc_analysis']['dc_earners'] >= 8 else 'not good enough'}."

{'=' * 90}

RON: "Sophia, attacking returns."

{'=' * 90}
4. SOPHIA'S ATTACKING ANALYSIS
{'=' * 90}

TOP PERFORMERS:
"""

    top_scorers = sorted(analysis['player_details'], key=lambda p: p['points_earned'], reverse=True)[:5]
    for i, player in enumerate(top_scorers, 1):
        b = player['breakdown']
        details = []
        if b['goals_scored'] > 0:
            details.append(f"{b['goals_scored']}G")
        if b['assists'] > 0:
            details.append(f"{b['assists']}A")
        if b['clean_sheets'] > 0:
            details.append("CS")
        if b['defensive_contribution'] > 0:
            details.append(f"DC({b['defensive_contribution']})")

        cap = "(C)" if player['is_captain'] else ""
        details_str = ", ".join(details) if details else "-"
        report += f"  {i}. {player['name']} {cap} - {player['points_earned']} pts ({details_str})\n"

    total_goals = sum(p['breakdown']['goals_scored'] for p in analysis['player_details'])
    total_assists = sum(p['breakdown']['assists'] for p in analysis['player_details'])

    report += f"""
TEAM TOTALS:
  • Goals: {total_goals}
  • Assists: {total_assists}
  • Goal Involvements: {total_goals + total_assists}

SOPHIA: "{analysis['staff_comments']['sophia']}"

{'=' * 90}

RON: "Captain choice - was it right?"

{'=' * 90}
5. CAPTAIN ANALYSIS
{'=' * 90}

CAPTAIN: {analysis['captain_analysis']['captain_name']}
  • Points Scored: {analysis['captain_analysis']['captain_points']} pts (raw: {analysis['captain_analysis']['captain_points']//2})
  • Contribution: {analysis['captain_analysis']['captain_contribution']} pts to team total

OPTIMAL CAPTAIN (Hindsight): {analysis['captain_analysis']['optimal_captain']}
  • Would have scored: {analysis['captain_analysis']['optimal_points']} pts

RESULT: {'✅ OPTIMAL CHOICE' if analysis['captain_analysis']['was_optimal'] else f"❌ SUB-OPTIMAL ({analysis['captain_analysis']['points_left_on_table']} pts lost)"}

RON: "{'Good call.' if analysis['captain_analysis']['was_optimal'] else 'Missed that one.'}"

{'=' * 90}

RON: "Priya, what's ahead?"

{'=' * 90}
6. PRIYA'S FIXTURE OUTLOOK (GW{next_gw}+)
{'=' * 90}

[FIXTURE ANALYSIS TO BE ADDED - Requires next GW fixture data]

PRIYA: "We need to fetch GW{next_gw} fixtures and analyze difficulty ratings."

RON: "Get it done. What about long-term?"

PRIYA: "Looking at GW{next_gw}-{next_gw+5}, we should identify fixture swings and plan transfers accordingly."

{'=' * 90}

RON: "Jimmy, value plays?"

{'=' * 90}
7. JIMMY'S VALUE ANALYSIS
{'=' * 90}

SQUAD VALUE:
  • Points per Player (Starting XI): {analysis['final_score']/11:.1f} pts
  • Total Squad Points: {analysis['final_score']} pts

JIMMY: "{analysis['staff_comments']['jimmy']}"

RON: "Transfer targets for next week?"

JIMMY: "Need to analyze price changes and form trends. Looking for:
  • Players about to rise (get ahead of price increase)
  • In-form DC specialists (maintain strategy)
  • Fixture swing opportunities (next 3-4 GW outlook)"

{'=' * 90}

RON: "Terry, chips?"

{'=' * 90}
8. TERRY'S CHIP STRATEGY
{'=' * 90}

CHIP STATUS:
  • Wildcard 1: Available ✓
  • Bench Boost 1: Available ✓
  • Triple Captain 1: Available ✓
  • Free Hit 1: Available ✓

ALL CHIPS INTACT - GW{gw} COMPLETE

TERRY: "Still holding. No rush. Optimal timing is everything."

RON: "When's the play?"

TERRY: "Wildcard window opening GW12-14. Bench Boost probably GW15-16 if fixtures align.
Triple Captain on Haaland when the fixture is perfect - maybe GW10-12.
Free Hit held for blank/double gameweek opportunities."

RON: "Patient. I like it."

{'=' * 90}

RON: "Right. What do we learn from GW{gw}?"

{'=' * 90}
9. CONSOLIDATED LEARNINGS
{'=' * 90}

WHAT WORKED:
"""

    # Identify what worked
    if analysis['beat_average']:
        report += f"  ✅ Beat the average by {analysis['vs_average']:.0f} points\n"
    if analysis['captain_analysis']['was_optimal']:
        report += f"  ✅ Captain choice was optimal\n"
    if analysis['dc_analysis']['dc_earners'] >= 8:
        report += f"  ✅ DC strategy delivered - {analysis['dc_analysis']['dc_earners']} earners\n"

    report += f"""
WHAT DIDN'T:
"""

    # Identify issues
    if not analysis['beat_average']:
        report += f"  ❌ Below average by {abs(analysis['vs_average']):.0f} points\n"
    if not analysis['captain_analysis']['was_optimal']:
        report += f"  ❌ Captain choice sub-optimal - {analysis['captain_analysis']['points_left_on_table']} pts lost\n"
    if analysis['dc_analysis']['dc_earners'] < 8:
        report += f"  ❌ DC underperformance - only {analysis['dc_analysis']['dc_earners']} earners\n"

    report += f"""
ACTION ITEMS FOR GW{next_gw}:
  [ ] Analyze GW{next_gw} fixtures in detail
  [ ] Identify transfer targets (form + fixtures)
  [ ] Monitor price changes (tonight's risers/fallers)
  [ ] Select optimal captain for GW{next_gw}
  [ ] Review bench order for auto-sub optimization

{'=' * 90}

RON: "Final decisions for GW{next_gw}..."

{'=' * 90}
10. RON'S DECISIONS
{'=' * 90}

TRANSFERS:
  Status: {'Free transfer available' if gw >= 8 else 'To be determined'}
  Plan: [TO BE DECIDED - Run transfer analysis]

CAPTAIN:
  Leading candidate: [TO BE DECIDED - Analyze GW{next_gw} fixtures]
  Alternatives: [Based on fixture difficulty and form]

FORMATION:
  Current: 3-5-2
  Change needed: [Evaluate based on player availability]

CHIPS:
  Usage this week: NONE - Holding all chips
  Next chip window: GW12-14 (Wildcard consideration)

RON: "We {'beat the average - keep the course' if analysis['beat_average'] else 'were below par - need improvements'}.
DC strategy is {'working' if analysis['dc_analysis']['dc_earners'] >= 8 else 'underperforming - investigate why'}.

{f"Captain choice cost us {analysis['captain_analysis']['points_left_on_table']} points - learn from it." if not analysis['captain_analysis']['was_optimal'] else 'Captain delivered as expected.'}

For GW{next_gw}, we analyze fixtures first, then make smart decisions. No knee-jerks, no panic.

Foundation first, fancy stuff second.

Meeting adjourned."

{'=' * 90}

NEXT MEETING: Monday post-GW{next_gw}
ACTION OWNER: All staff
DEADLINE: GW{next_gw} deadline

{'=' * 90}

Two Points FC - Up the table we go.

{'=' * 90}
"""

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate staff meeting report")
    parser.add_argument('--gw', type=int, required=True, help='Gameweek number')
    parser.add_argument('--save', action='store_true', help='Save report to file')

    args = parser.parse_args()

    # Load analysis
    analysis = load_gw_analysis(args.gw)

    # Generate report
    report = generate_meeting_report(analysis, args.gw)

    # Print
    print(report)

    # Save if requested
    if args.save:
        output_dir = "data/staff_meetings"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"gw{args.gw}_meeting.txt")

        with open(output_file, 'w') as f:
            f.write(report)

        print(f"\n💾 Staff meeting report saved: {output_file}")

    print(f"\n✅ Staff meeting report complete for GW{args.gw}")


if __name__ == "__main__":
    main()
