#!/usr/bin/env python3
"""
Decision Logger - Real-time visibility into Ron's decisions

Subscribes to the event bus and logs all important decisions:
- Team selections
- Transfers
- Captain choices
- Chip usage
- Gameweek planning triggers
- Analysis completions

Outputs to both console (for tmux/screen) and log file.
"""

import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.event_bus import EventBus
from infrastructure.events import Event, EventType

# Configure logging
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f'decisions_{datetime.now().strftime("%Y%m%d")}.log'

# Dual logging: console (INFO) and file (DEBUG)
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding='utf-8')
    ]
)

logger = logging.getLogger('decision_logger')


class DecisionLogger:
    """
    Logs Ron's decisions in real-time by listening to event bus.
    """

    def __init__(self):
        self.event_bus = EventBus()
        self.start_time = datetime.now()
        self.events_logged = 0

    async def start(self):
        """Start logging decisions."""
        await self.event_bus.connect()

        # Subscribe to all decision-relevant events
        important_events = [
            EventType.DATA_UPDATED,
            EventType.GAMEWEEK_PLANNING,
            EventType.DC_ANALYSIS_COMPLETED,
            EventType.FIXTURE_ANALYSIS_COMPLETED,
            EventType.XG_ANALYSIS_COMPLETED,
            EventType.VALUE_RANKINGS_COMPLETED,
            EventType.TEAM_SELECTED,
            EventType.TRANSFER_RECOMMENDED,
            EventType.TRANSFER_EXECUTED,
            EventType.CAPTAIN_SELECTED,
            EventType.CHIP_USED,
            EventType.PRICE_CHANGE_DETECTED,
            EventType.GAMEWEEK_COMPLETE,
            EventType.DECISION_MADE,
        ]

        for event_type in important_events:
            await self.event_bus.subscribe(event_type, self._handle_event)

        self._print_header()
        await self.event_bus.start_listening()

    async def stop(self):
        """Stop logging."""
        await self.event_bus.stop_listening()
        await self.event_bus.disconnect()

    def _print_header(self):
        """Print startup banner."""
        logger.info("=" * 80)
        logger.info("RON CLANKER DECISION LOGGER")
        logger.info(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 80)
        logger.info("\nListening for decisions...\n")

    async def _handle_event(self, event_data: Dict[str, Any]):
        """Handle incoming event and log appropriately."""
        self.events_logged += 1

        event_type = event_data.get('event_type')
        payload = event_data.get('payload', {})
        timestamp = event_data.get('timestamp', datetime.now().isoformat())
        source = event_data.get('source', 'unknown')

        # Parse timestamp
        try:
            if isinstance(timestamp, str):
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                ts = timestamp
            time_str = ts.strftime('%H:%M:%S')
        except:
            time_str = datetime.now().strftime('%H:%M:%S')

        # Route to appropriate handler
        if event_type == EventType.DATA_UPDATED.value:
            self._log_data_update(time_str, payload)
        elif event_type == EventType.GAMEWEEK_PLANNING.value:
            self._log_gameweek_planning(time_str, payload)
        elif event_type == EventType.DC_ANALYSIS_COMPLETED.value:
            self._log_dc_analysis(time_str, payload)
        elif event_type == EventType.FIXTURE_ANALYSIS_COMPLETED.value:
            self._log_fixture_analysis(time_str, payload)
        elif event_type == EventType.XG_ANALYSIS_COMPLETED.value:
            self._log_xg_analysis(time_str, payload)
        elif event_type == EventType.VALUE_RANKINGS_COMPLETED.value:
            self._log_value_rankings(time_str, payload)
        elif event_type == EventType.TEAM_SELECTED.value:
            self._log_team_selection(time_str, payload)
        elif event_type == EventType.TRANSFER_RECOMMENDED.value:
            self._log_transfer_recommendation(time_str, payload)
        elif event_type == EventType.TRANSFER_EXECUTED.value:
            self._log_transfer_execution(time_str, payload)
        elif event_type == EventType.CAPTAIN_SELECTED.value:
            self._log_captain_selection(time_str, payload)
        elif event_type == EventType.CHIP_USED.value:
            self._log_chip_usage(time_str, payload)
        elif event_type == EventType.PRICE_CHANGE_DETECTED.value:
            self._log_price_change(time_str, payload)
        elif event_type == EventType.GAMEWEEK_COMPLETE.value:
            self._log_gameweek_complete(time_str, payload)
        elif event_type == EventType.DECISION_MADE.value:
            self._log_decision(time_str, payload)
        else:
            # Generic event logging
            logger.debug(f"[{time_str}] {event_type}: {json.dumps(payload, indent=2)}")

    def _log_data_update(self, time_str: str, payload: Dict):
        """Log data refresh."""
        gw = payload.get('gameweek', '?')
        trigger = payload.get('trigger', 'unknown')
        logger.info(f"[{time_str}] 📊 DATA REFRESH - GW{gw} ({trigger})")

    def _log_gameweek_planning(self, time_str: str, payload: Dict):
        """Log gameweek planning trigger."""
        gw = payload.get('gameweek', '?')
        trigger_point = payload.get('trigger_point', '?')
        hours_until = payload.get('hours_until', 0)

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"[{time_str}] 🎯 GAMEWEEK {gw} PLANNING - {trigger_point} TRIGGER")
        logger.info(f"  Deadline in {hours_until:.1f} hours")
        logger.info("=" * 80)
        logger.info("")

    def _log_dc_analysis(self, time_str: str, payload: Dict):
        """Log DC analysis completion."""
        gw = payload.get('gameweek', '?')
        top_players = payload.get('top_dc_players', [])[:3]

        logger.info(f"[{time_str}] 🛡️  DIGGER: DC Analysis Complete (GW{gw})")
        if top_players:
            logger.info(f"  Top DC picks:")
            for i, player in enumerate(top_players, 1):
                name = player.get('name', 'Unknown')
                dc_pts = player.get('dc_points', 0)
                logger.info(f"    {i}. {name} ({dc_pts} DC pts)")

    def _log_fixture_analysis(self, time_str: str, payload: Dict):
        """Log fixture analysis completion."""
        gw = payload.get('gameweek', '?')
        logger.info(f"[{time_str}] 📅 PRIYA: Fixture Analysis Complete (GW{gw})")

    def _log_xg_analysis(self, time_str: str, payload: Dict):
        """Log xG analysis completion."""
        gw = payload.get('gameweek', '?')
        logger.info(f"[{time_str}] ⚽ SOPHIA: xG Analysis Complete (GW{gw})")

    def _log_value_rankings(self, time_str: str, payload: Dict):
        """Log value rankings completion."""
        gw = payload.get('gameweek', '?')
        top_overall = payload.get('top_value_picks', [])[:5]

        logger.info(f"[{time_str}] 💎 JIMMY: Value Rankings Complete (GW{gw})")
        if top_overall:
            logger.info(f"  Top 5 value picks:")
            for i, player in enumerate(top_overall, 1):
                name = player.get('name', 'Unknown')
                pos = player.get('position', '?')
                value = player.get('value_score', 0)
                price = player.get('price', 0) / 10
                logger.info(f"    {i}. {name} ({pos}) £{price:.1f}m - Value: {value:.1f}")

    def _log_team_selection(self, time_str: str, payload: Dict):
        """Log team selection - THE BIG ONE."""
        gw = payload.get('gameweek', '?')
        squad = payload.get('squad', [])
        captain = payload.get('captain', {})
        vice = payload.get('vice_captain', {})
        total_cost = payload.get('total_cost', 0) / 10
        reasoning = payload.get('reasoning', '')

        logger.info("")
        logger.info("🏆" * 40)
        logger.info(f"[{time_str}] RON'S TEAM SELECTION - GAMEWEEK {gw}")
        logger.info("🏆" * 40)
        logger.info("")
        logger.info(f"Total Cost: £{total_cost:.1f}m")
        logger.info("")

        # Group by position
        positions = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
        for pos_id in [1, 2, 3, 4]:
            pos_players = [p for p in squad if p.get('position_id') == pos_id]
            if pos_players:
                logger.info(f"{positions[pos_id]}:")
                for player in pos_players:
                    name = player.get('name', 'Unknown')
                    price = player.get('price', 0) / 10
                    is_captain = player.get('is_captain', False)
                    is_vice = player.get('is_vice_captain', False)

                    suffix = ""
                    if is_captain:
                        suffix = " (C)"
                    elif is_vice:
                        suffix = " (VC)"

                    logger.info(f"  • {name} £{price:.1f}m{suffix}")
                logger.info("")

        if captain:
            logger.info(f"Captain: {captain.get('name', 'Unknown')}")
        if vice:
            logger.info(f"Vice-Captain: {vice.get('name', 'Unknown')}")

        if reasoning:
            logger.info(f"\nRon's Reasoning:")
            logger.info(f"{reasoning}")

        logger.info("")
        logger.info("🏆" * 40)
        logger.info("")

    def _log_transfer_recommendation(self, time_str: str, payload: Dict):
        """Log transfer recommendation."""
        player_out = payload.get('player_out', 'Unknown')
        player_in = payload.get('player_in', 'Unknown')
        reasoning = payload.get('reasoning', '')

        logger.info(f"[{time_str}] 🔄 TRANSFER RECOMMENDED")
        logger.info(f"  OUT: {player_out}")
        logger.info(f"  IN:  {player_in}")
        if reasoning:
            logger.info(f"  Why: {reasoning}")

    def _log_transfer_execution(self, time_str: str, payload: Dict):
        """Log executed transfer."""
        player_out = payload.get('player_out', 'Unknown')
        player_in = payload.get('player_in', 'Unknown')
        cost = payload.get('cost', 0)
        gw = payload.get('gameweek', '?')

        logger.info("")
        logger.info(f"[{time_str}] ✅ TRANSFER EXECUTED - GW{gw}")
        logger.info(f"  OUT: {player_out}")
        logger.info(f"  IN:  {player_in}")
        if cost > 0:
            logger.info(f"  Cost: -{cost} points")
        else:
            logger.info(f"  Free transfer")
        logger.info("")

    def _log_captain_selection(self, time_str: str, payload: Dict):
        """Log captain choice."""
        captain = payload.get('captain', 'Unknown')
        vice = payload.get('vice_captain', 'Unknown')
        reasoning = payload.get('reasoning', '')

        logger.info(f"[{time_str}] ⭐ CAPTAIN SELECTED")
        logger.info(f"  Captain: {captain}")
        logger.info(f"  Vice: {vice}")
        if reasoning:
            logger.info(f"  Why: {reasoning}")

    def _log_chip_usage(self, time_str: str, payload: Dict):
        """Log chip usage."""
        chip = payload.get('chip_name', 'Unknown')
        gw = payload.get('gameweek', '?')
        reasoning = payload.get('reasoning', '')

        logger.info("")
        logger.info(f"[{time_str}] 🃏 CHIP PLAYED - GW{gw}")
        logger.info(f"  Chip: {chip.upper()}")
        if reasoning:
            logger.info(f"  Why: {reasoning}")
        logger.info("")

    def _log_price_change(self, time_str: str, payload: Dict):
        """Log price change."""
        player_name = payload.get('player_name', 'Unknown')
        old_price = payload.get('old_price', 0) / 10
        new_price = payload.get('new_price', 0) / 10
        change = payload.get('change_type', 'change')

        emoji = "📈" if change == 'rise' else "📉"
        logger.info(f"[{time_str}] {emoji} PRICE {change.upper()}: {player_name} £{old_price:.1f}m → £{new_price:.1f}m")

    def _log_gameweek_complete(self, time_str: str, payload: Dict):
        """Log gameweek completion."""
        gw = payload.get('gameweek', '?')

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"[{time_str}] 🏁 GAMEWEEK {gw} COMPLETE")
        logger.info("  Starting post-gameweek review...")
        logger.info("=" * 80)
        logger.info("")

    def _log_decision(self, time_str: str, payload: Dict):
        """Log generic decision."""
        decision_type = payload.get('decision_type', 'unknown')
        reasoning = payload.get('reasoning', '')

        logger.info(f"[{time_str}] 🤔 DECISION: {decision_type}")
        if reasoning:
            logger.info(f"  {reasoning}")


async def main():
    """Main entry point."""
    decision_logger = DecisionLogger()

    try:
        await decision_logger.start()

        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n\nShutting down decision logger...")
        logger.info(f"Total events logged: {decision_logger.events_logged}")
        await decision_logger.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
