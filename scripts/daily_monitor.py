#!/usr/bin/env python3
"""
Daily FPL Monitoring Script

Runs daily (via cron) to:
- Sync latest FPL data
- Detect price changes
- Monitor injury news
- Track squad player status
- Alert on important changes
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.data_collector import DataCollector
from data.database import Database


class DailyMonitor:
    """Daily monitoring and alerting system."""

    def __init__(self):
        self.db = Database()
        self.collector = DataCollector()
        self.alerts = []

    async def run(self):
        """Run daily monitoring routine."""
        print("=" * 80)
        print("RON CLANKER - DAILY MONITORING")
        print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        try:
            # Fetch latest data
            print("\n📡 Fetching latest FPL data...")
            fpl_data = await self.collector.update_all_data()

            # Get current gameweek
            current_gw = fpl_data.get('current_gameweek')
            if current_gw:
                print(f"Current Gameweek: {current_gw['id']} ({current_gw['name']})")
                print(f"Deadline: {current_gw.get('deadline_time', 'N/A')}")

            # Check for price changes
            print("\n💰 Checking for price changes...")
            price_changes = self.detect_price_changes(fpl_data['players'])

            if price_changes:
                print(f"Found {len(price_changes)} price changes:")
                for change in price_changes[:10]:  # Show top 10
                    direction = "📈" if change['change'] > 0 else "📉"
                    print(f"  {direction} {change['name']:<20} "
                          f"£{change['old_price']/10:.1f}m → £{change['new_price']/10:.1f}m")

                # Log all changes
                for change in price_changes:
                    self.log_price_change(change)
            else:
                print("  No price changes detected")

            # Check injury news
            print("\n🏥 Checking injury/availability updates...")
            injury_updates = self.detect_injury_news(fpl_data['players'])

            if injury_updates:
                print(f"Found {len(injury_updates)} status updates:")
                for update in injury_updates:
                    status_emoji = "❌" if update['status'] != 'a' else "⚠️"
                    print(f"  {status_emoji} {update['name']:<20} "
                          f"Status: {update['status']} - {update['news']}")
            else:
                print("  No injury updates")

            # Check squad impact
            print("\n👥 Checking impact on current squad...")
            squad_impact = self.check_squad_impact(
                price_changes,
                injury_updates,
                current_gw['id'] if current_gw else 8
            )

            if squad_impact['affected_players']:
                print(f"⚠️  {len(squad_impact['affected_players'])} squad players affected:")
                for player in squad_impact['affected_players']:
                    print(f"  • {player['name']}: {player['issue']}")
                    self.alerts.append(f"SQUAD ALERT: {player['name']} - {player['issue']}")
            else:
                print("  ✅ No squad players affected")

            # Update database
            print("\n💾 Updating database...")
            self.update_database(fpl_data)
            print("  ✅ Database updated")

            # Generate summary report
            print("\n" + "=" * 80)
            print("DAILY SUMMARY")
            print("=" * 80)
            print(f"Price Changes: {len(price_changes)}")
            print(f"Injury Updates: {len(injury_updates)}")
            print(f"Squad Alerts: {len(self.alerts)}")

            if self.alerts:
                print("\n🚨 ALERTS:")
                for alert in self.alerts:
                    print(f"  {alert}")

            # Save report
            self.save_report(price_changes, injury_updates, squad_impact)

            print("\n✅ Daily monitoring complete!")
            return 0

        except Exception as e:
            print(f"\n❌ Error during monitoring: {e}")
            import traceback
            traceback.print_exc()
            return 1

        finally:
            await self.collector.close()

    def detect_price_changes(self, players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect price changes since last sync."""
        changes = []

        for player in players:
            # Get previous price from database
            db_player = self.db.get_player(player['id'])

            if db_player:
                old_price = db_player['now_cost']
                new_price = player['now_cost']

                if old_price != new_price:
                    changes.append({
                        'player_id': player['id'],
                        'name': player['web_name'],
                        'old_price': old_price,
                        'new_price': new_price,
                        'change': new_price - old_price,
                        'selected_by_percent': player.get('selected_by_percent', 0)
                    })

        # Sort by absolute change
        changes.sort(key=lambda x: abs(x['change']), reverse=True)
        return changes

    def detect_injury_news(self, players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect injury/availability changes."""
        updates = []

        for player in players:
            # Only report players with news
            if player.get('news'):
                db_player = self.db.get_player(player['id'])

                # Check if news is new or status changed
                is_new = not db_player or db_player.get('news') != player['news']

                if is_new:
                    updates.append({
                        'player_id': player['id'],
                        'name': player['web_name'],
                        'status': player.get('status', 'a'),
                        'news': player.get('news', ''),
                        'chance_of_playing': player.get('chance_of_playing_next_round')
                    })

        return updates

    def check_squad_impact(
        self,
        price_changes: List[Dict[str, Any]],
        injury_updates: List[Dict[str, Any]],
        gameweek: int
    ) -> Dict[str, Any]:
        """Check if changes affect current squad."""
        # Get current squad
        squad = self.db.get_current_team(gameweek)

        if not squad:
            return {'affected_players': [], 'squad_value_change': 0}

        squad_ids = {p['player_id'] for p in squad}
        affected_players = []
        total_value_change = 0

        # Check price changes
        for change in price_changes:
            if change['player_id'] in squad_ids:
                affected_players.append({
                    'name': change['name'],
                    'issue': f"Price change: £{change['old_price']/10:.1f}m → £{change['new_price']/10:.1f}m"
                })
                total_value_change += change['change']

        # Check injuries
        for update in injury_updates:
            if update['player_id'] in squad_ids:
                affected_players.append({
                    'name': update['name'],
                    'issue': f"Injury/News: {update['news']} ({update['chance_of_playing']}% likely to play)"
                })

        return {
            'affected_players': affected_players,
            'squad_value_change': total_value_change / 10  # Convert to £m
        }

    def log_price_change(self, change: Dict[str, Any]):
        """Log price change to database."""
        from datetime import date

        query = """
            INSERT INTO price_changes
            (player_id, old_price, new_price, change_date, selected_by_percent)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            change['player_id'],
            change['old_price'],
            change['new_price'],
            date.today().isoformat(),
            change['selected_by_percent']
        )
        self.db.execute_update(query, params)

    def update_database(self, fpl_data: Dict[str, Any]):
        """Update database with latest FPL data."""
        # Update players
        for player in fpl_data['players']:
            self.db.upsert_player(player)

        # Update fixtures
        for fixture in fpl_data['fixtures']:
            self.db.upsert_fixture(fixture)

    def save_report(
        self,
        price_changes: List[Dict[str, Any]],
        injury_updates: List[Dict[str, Any]],
        squad_impact: Dict[str, Any]
    ):
        """Save daily report to file."""
        report_dir = Path("data/daily_reports")
        report_dir.mkdir(exist_ok=True)

        report_file = report_dir / f"report_{datetime.now().strftime('%Y%m%d')}.txt"

        with open(report_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write(f"RON CLANKER - DAILY REPORT\n")
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"PRICE CHANGES ({len(price_changes)}):\n")
            f.write("-" * 80 + "\n")
            for change in price_changes[:20]:  # Top 20
                direction = "↑" if change['change'] > 0 else "↓"
                f.write(f"{direction} {change['name']:<20} "
                       f"£{change['old_price']/10:.1f}m → £{change['new_price']/10:.1f}m "
                       f"({change['selected_by_percent']:.1f}% owned)\n")

            f.write(f"\nINJURY/NEWS UPDATES ({len(injury_updates)}):\n")
            f.write("-" * 80 + "\n")
            for update in injury_updates:
                f.write(f"{update['name']:<20} [{update['status']}] {update['news']}\n")

            f.write(f"\nSQUAD IMPACT:\n")
            f.write("-" * 80 + "\n")
            if squad_impact['affected_players']:
                for player in squad_impact['affected_players']:
                    f.write(f"⚠️  {player['name']}: {player['issue']}\n")
                f.write(f"\nTotal squad value change: £{squad_impact['squad_value_change']:.1f}m\n")
            else:
                f.write("No squad players affected\n")

            if self.alerts:
                f.write(f"\nALERTS:\n")
                f.write("-" * 80 + "\n")
                for alert in self.alerts:
                    f.write(f"{alert}\n")

        print(f"\n📄 Report saved: {report_file}")


async def main():
    """Main entry point."""
    monitor = DailyMonitor()
    exit_code = await monitor.run()
    return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
