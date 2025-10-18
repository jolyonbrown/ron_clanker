#!/usr/bin/env python3
"""
Generate League Intelligence Report

Produces daily competitive analysis report for Ron:
- League standings and gaps
- Rival chip status (who has what remaining)
- Differential analysis (Ron vs rivals)
- Transfer trends in the league
- Competitive recommendations

Runs daily at 07:00 via cron (after league tracking at 06:00)
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from intelligence.league_intel import LeagueIntelligenceService
from intelligence.chip_strategy import ChipStrategyAnalyzer
from intelligence.fixture_optimizer import FixtureOptimizer

logger = logging.getLogger('ron_clanker.league_intelligence')

CONFIG_FILE = project_root / 'config' / 'ron_config.json'


def load_config():
    """Load Ron's config."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def generate_standings_report(league_service, league_id, gameweek):
    """Generate league standings section."""

    standings = league_service.db.execute_query("""
        SELECT
            lsh.entry_id,
            lr.player_name,
            lr.team_name,
            lsh.rank,
            lsh.last_rank,
            lsh.total_points,
            lsh.event_points,
            lsh.rank - COALESCE(lsh.last_rank, lsh.rank) as rank_change
        FROM league_standings_history lsh
        JOIN league_rivals lr ON lsh.entry_id = lr.entry_id AND lsh.league_id = lr.league_id
        WHERE lsh.league_id = ? AND lsh.gameweek = ?
        ORDER BY lsh.rank
    """, (league_id, gameweek))

    if not standings:
        return "No standings data available"

    leader = standings[0]

    report = []
    report.append("\n" + "=" * 80)
    report.append("LEAGUE STANDINGS")
    report.append("=" * 80)
    report.append(f"\n{'Rank':5s} {'Manager':25s} {'Points':7s} {'Gap':7s} {'Form':6s}")
    report.append("-" * 80)

    for team in standings:
        gap = team['total_points'] - leader['total_points']
        gap_str = f"{gap:+d}" if gap != 0 else "-"

        # Rank change arrow
        rc = team['rank_change']
        form = "↑" if rc < 0 else ("↓" if rc > 0 else "→")

        report.append(
            f"{team['rank']:5d} {team['player_name']:25s} "
            f"{team['total_points']:7d} {gap_str:>7s} {form:>6s}"
        )

    return "\n".join(report)


def generate_chip_status_report(league_service, ron_entry_id):
    """Generate chip usage analysis."""

    chip_status = league_service.get_rival_chip_status()

    report = []
    report.append("\n" + "=" * 80)
    report.append("CHIP ARSENAL ANALYSIS")
    report.append("=" * 80)

    # Find Ron's chips
    ron_chips = next((c for c in chip_status if c['entry_id'] == ron_entry_id), None)

    if ron_chips:
        report.append(f"\n🤖 RON'S CHIPS REMAINING:")
        report.append(f"   Wildcards: {ron_chips['wildcards_remaining']}/2")
        report.append(f"   Bench Boosts: {ron_chips['bench_boosts_remaining']}/2")
        report.append(f"   Triple Captains: {ron_chips['triple_captains_remaining']}/2")
        report.append(f"   Free Hits: {ron_chips['free_hits_remaining']}/2")

        total_remaining = (
            ron_chips['wildcards_remaining'] +
            ron_chips['bench_boosts_remaining'] +
            ron_chips['triple_captains_remaining'] +
            ron_chips['free_hits_remaining']
        )
        report.append(f"\n   TOTAL: {total_remaining}/8 chips remaining")

    # Rival chip status
    report.append(f"\n👥 RIVAL CHIP STATUS (Top 5):")
    report.append(f"\n{'Manager':25s} {'WC':4s} {'BB':4s} {'TC':4s} {'FH':4s} {'Total':6s}")
    report.append("-" * 80)

    for rival in chip_status[:5]:
        if rival['entry_id'] == ron_entry_id:
            continue

        total = (
            rival['wildcards_remaining'] +
            rival['bench_boosts_remaining'] +
            rival['triple_captains_remaining'] +
            rival['free_hits_remaining']
        )

        report.append(
            f"{rival['player_name']:25s} "
            f"{rival['wildcards_remaining']}/2  "
            f"{rival['bench_boosts_remaining']}/2  "
            f"{rival['triple_captains_remaining']}/2  "
            f"{rival['free_hits_remaining']}/2  "
            f"{total:>6d}/8"
        )

    return "\n".join(report)


def generate_differential_report(league_service, ron_entry_id, gameweek):
    """Generate differential analysis."""

    differentials = league_service.get_differentials(ron_entry_id, gameweek, rival_limit=5)

    report = []
    report.append("\n" + "=" * 80)
    report.append("DIFFERENTIAL ANALYSIS")
    report.append("=" * 80)

    # Ron's exclusives
    ron_exclusives = differentials['ron_exclusives']

    if ron_exclusives:
        report.append(f"\n🤖 RON'S DIFFERENTIALS ({len(ron_exclusives)} players):")
        report.append(f"{'Player':20s} {'Price':8s} {'Global Own':12s} {'Captain':8s}")
        report.append("-" * 80)

        for player in ron_exclusives[:10]:  # Top 10
            cap_marker = "⭐" if player['is_captain'] else ""
            report.append(
                f"{player['web_name']:20s} "
                f"£{player['price']:.1f}m    "
                f"{player['global_ownership']:>5s}%       "
                f"{cap_marker:>8s}"
            )
    else:
        report.append("\n🤖 RON'S DIFFERENTIALS: None (template team)")

    # Template gaps
    template_missing = differentials['template_missing']

    if template_missing:
        report.append(f"\n\n👥 TEMPLATE PLAYERS RON IS MISSING ({len(template_missing)} players):")
        report.append(f"{'Player':20s} {'Price':8s} {'League Own':12s}")
        report.append("-" * 80)

        for player in template_missing[:10]:  # Top 10
            report.append(
                f"{player['web_name']:20s} "
                f"£{player['price']:.1f}m    "
                f"{player['rival_count']}/5 rivals  "
                f"({player['league_ownership_pct']:.0f}%)"
            )
    else:
        report.append("\n\n👥 TEMPLATE PLAYERS RON IS MISSING: None (Ron has template)")

    return "\n".join(report)


def generate_transfer_intel_report(league_service, gameweek):
    """Generate transfer intelligence section."""

    # Get popular transfers in the league
    popular_in = league_service.db.execute_query("""
        SELECT
            rt.player_in,
            p.web_name,
            COUNT(*) as transfer_count
        FROM rival_transfers rt
        JOIN players p ON rt.player_in = p.id
        WHERE rt.gameweek = ?
        GROUP BY rt.player_in
        ORDER BY transfer_count DESC
        LIMIT 5
    """, (gameweek,))

    popular_out = league_service.db.execute_query("""
        SELECT
            rt.player_out,
            p.web_name,
            COUNT(*) as transfer_count
        FROM rival_transfers rt
        JOIN players p ON rt.player_out = p.id
        WHERE rt.gameweek = ?
        GROUP BY rt.player_out
        ORDER BY transfer_count DESC
        LIMIT 5
    """, (gameweek,))

    # Get ITB leaders (most cash available)
    itb_leaders = league_service.db.execute_query("""
        SELECT
            lsh.entry_id,
            lr.player_name,
            lsh.bank_value / 10.0 as itb,
            lsh.value / 10.0 as team_value
        FROM league_standings_history lsh
        JOIN league_rivals lr ON lsh.entry_id = lr.entry_id
        WHERE lsh.gameweek = ? AND lsh.bank_value IS NOT NULL
        ORDER BY lsh.bank_value DESC
        LIMIT 5
    """, (gameweek,))

    report = []
    report.append("\n" + "=" * 80)
    report.append("TRANSFER INTELLIGENCE")
    report.append("=" * 80)

    if popular_in:
        report.append(f"\n📈 MOST TRANSFERRED IN (GW{gameweek}):")
        for p in popular_in:
            report.append(f"   {p['web_name']}: {p['transfer_count']} rivals brought in")
    else:
        report.append(f"\n📈 No transfer data available for GW{gameweek}")

    if popular_out:
        report.append(f"\n📉 MOST TRANSFERRED OUT (GW{gameweek}):")
        for p in popular_out:
            report.append(f"   {p['web_name']}: {p['transfer_count']} rivals sold")

    if itb_leaders:
        report.append(f"\n💰 MOST CASH IN THE BANK:")
        for rival in itb_leaders:
            report.append(f"   {rival['player_name']}: £{rival['itb']:.1f}m ITB (£{rival['team_value']:.1f}m total value)")

    return "\n".join(report)


def generate_competitive_advice(league_service, ron_entry_id, league_id, gameweek):
    """Generate competitive recommendations."""

    # Get Ron's position
    standings = league_service.db.execute_query("""
        SELECT rank, total_points
        FROM league_standings_history
        WHERE league_id = ? AND gameweek = ? AND entry_id = ?
    """, (league_id, gameweek, ron_entry_id))

    # Get leader
    leader = league_service.db.execute_query("""
        SELECT total_points
        FROM league_standings_history
        WHERE league_id = ? AND gameweek = ?
        ORDER BY rank
        LIMIT 1
    """, (league_id, gameweek))

    report = []
    report.append("\n" + "=" * 80)
    report.append("COMPETITIVE STRATEGY RECOMMENDATIONS")
    report.append("=" * 80)

    if not standings:
        # Ron not in standings yet
        report.append("\n⚠️  Ron's team not yet registered in league standings")
        report.append("    Will appear after first gameweek completes")
        return "\n".join(report)

    ron_rank = standings[0]['rank']
    ron_points = standings[0]['total_points']
    leader_points = leader[0]['total_points'] if leader else ron_points
    gap = ron_points - leader_points

    gws_remaining = 38 - gameweek

    report.append(f"\n📊 CURRENT POSITION:")
    report.append(f"   Rank: {ron_rank}")
    report.append(f"   Points: {ron_points}")
    report.append(f"   Gap to leader: {gap:+d} pts")
    report.append(f"   Gameweeks remaining: {gws_remaining}")

    if gap < 0:
        # Chasing
        pts_per_gw_needed = abs(gap) / gws_remaining if gws_remaining > 0 else 0

        report.append(f"\n🎯 CHASING MODE:")
        report.append(f"   Need +{pts_per_gw_needed:.1f} pts/GW advantage to catch leader")
        report.append(f"\n   RECOMMENDED STRATEGY:")
        report.append(f"   • Seek differentials with high upside")
        report.append(f"   • Consider differential captains")
        report.append(f"   • Use chips aggressively on best opportunities")
        report.append(f"   • Monitor template gaps - consider covering high-ownership threats")

    elif gap > 0:
        # Leading
        report.append(f"\n👑 LEADING MODE:")
        report.append(f"\n   RECOMMENDED STRATEGY:")
        report.append(f"   • Maintain template coverage")
        report.append(f"   • Safe captain picks (high ownership)")
        report.append(f"   • Chip timing matched to rivals")
        report.append(f"   • Avoid unnecessary risks")

    return "\n".join(report)


def main():
    """Generate comprehensive league intelligence report."""

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("LEAGUE INTELLIGENCE REPORT")
    print("=" * 80)
    print(f"Generated: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    logger.info(f"LeagueIntelligence: Starting report generation at {start_time}")

    # Load config
    config = load_config()
    league_id = config.get('league_id')
    ron_entry_id = config.get('team_id')

    if not league_id:
        print("\n❌ ERROR: No league_id in config")
        logger.error("LeagueIntelligence: No league_id configured")
        return 1

    if not ron_entry_id:
        print("\n⚠️  WARNING: No team_id in config - reports will be limited")
        logger.warning("LeagueIntelligence: No team_id configured")

    # Initialize services
    db = Database()
    league_service = LeagueIntelligenceService(db)
    chip_analyzer = ChipStrategyAnalyzer(db, league_service)
    fixture_optimizer = FixtureOptimizer(db)

    # Get current gameweek - use latest from standings
    max_gw = db.execute_query("""
        SELECT MAX(gameweek) as gw FROM league_standings_history
    """)

    if max_gw and max_gw[0]['gw']:
        current_gw = max_gw[0]['gw']
    else:
        # Fallback to gameweeks table
        gameweek_data = db.execute_query("""
            SELECT id FROM gameweeks
            WHERE is_current = 1
            LIMIT 1
        """)
        current_gw = gameweek_data[0]['id'] if gameweek_data else 8
        logger.warning(f"LeagueIntelligence: No league standings found, using gameweek {current_gw}")

    print(f"League ID: {league_id}")
    print(f"Current Gameweek: {current_gw}")
    if ron_entry_id:
        print(f"Ron's Team ID: {ron_entry_id}")

    logger.info(f"LeagueIntelligence: Generating report for league {league_id}, GW{current_gw}")

    # Generate report sections
    full_report = []

    # 1. Standings
    standings_report = generate_standings_report(league_service, league_id, current_gw)
    full_report.append(standings_report)
    print(standings_report)

    # 2. Chip analysis
    if ron_entry_id:
        chip_report = generate_chip_status_report(league_service, ron_entry_id)
        full_report.append(chip_report)
        print(chip_report)

    # 3. Differentials
    if ron_entry_id:
        diff_report = generate_differential_report(league_service, ron_entry_id, current_gw)
        full_report.append(diff_report)
        print(diff_report)

    # 4. Fixture-based chip optimization
    fixture_report = fixture_optimizer.generate_optimization_report(current_gw)
    full_report.append(fixture_report)
    print(fixture_report)

    # 5. Chip strategy
    if ron_entry_id:
        chip_report = chip_analyzer.generate_chip_report(ron_entry_id, league_id, current_gw)
        full_report.append(chip_report)
        print(chip_report)

    # 6. Transfer intelligence
    transfer_report = generate_transfer_intel_report(league_service, current_gw)
    full_report.append(transfer_report)
    print(transfer_report)

    # 7. Competitive advice
    if ron_entry_id:
        advice_report = generate_competitive_advice(league_service, ron_entry_id, league_id, current_gw)
        full_report.append(advice_report)
        print(advice_report)

    # Save report to file
    output_dir = project_root / 'reports' / 'league_intelligence'
    output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / f'league_{league_id}_gw{current_gw}_{start_time.strftime("%Y%m%d_%H%M%S")}.txt'

    with open(report_file, 'w') as f:
        f.write("\n".join(full_report))

    # Also save as latest
    latest_file = output_dir / f'league_{league_id}_latest.txt'
    with open(latest_file, 'w') as f:
        f.write("\n".join(full_report))

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("REPORT GENERATION COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Saved to: {report_file}")
    print(f"Latest: {latest_file}")

    logger.info(f"LeagueIntelligence: Report complete - Duration: {duration:.1f}s, Saved to {report_file}")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nReport generation cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"LeagueIntelligence: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
