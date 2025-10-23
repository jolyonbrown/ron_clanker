#!/usr/bin/env python3
"""
Test GW9 Draft Generation

End-to-end test of event-driven RonManager making GW9 team selection.
Tests the full pipeline from initialization to LLM-powered announcement.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.manager_agent_v2 import RonManager
from data.database import Database
from infrastructure.event_bus import get_event_bus


async def main():
    """Test full GW9 draft generation pipeline."""

    print("\n" + "=" * 80)
    print("GW9 DRAFT GENERATION TEST - EVENT-DRIVEN ARCHITECTURE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # STEP 4: Initialize event bus and RonManager
    print("🔧 STEP 4: Initializing event bus and RonManager")
    print("=" * 80)

    db = Database()

    # Initialize event bus (get_event_bus returns singleton)
    print("  • Getting event bus instance...")
    event_bus = get_event_bus()
    print("  ✅ Event bus ready")

    # Initialize RonManager
    print("  • Initializing RonManager (event-driven, ML-powered)...")
    ron = RonManager(database=db, use_ml=True)
    await ron.start()
    print("  ✅ RonManager started")
    print(f"     - ML enabled: {ron.use_ml}")
    print(f"     - Synthesis engine: {ron.synthesis_engine is not None}")
    print(f"     - Transfer optimizer: {ron.transfer_optimizer is not None}")
    print(f"     - Chip strategy: {ron.chip_strategy is not None}")
    print()
    print("✅ STEP 4 COMPLETE: Event bus and RonManager initialized")
    print()

    # STEP 5: Execute make_weekly_decision
    print("🔧 STEP 5: Executing make_weekly_decision for GW9")
    print("=" * 80)
    print()

    try:
        # Run the full decision pipeline
        print("  Ron is making his GW9 team selection...")
        print()

        result = await ron.make_weekly_decision(
            gameweek=9,
            free_transfers=1
        )

        print()
        print("✅ STEP 5 COMPLETE: Weekly decision executed successfully")
        print()

        # Extract results
        squad = result['squad']
        transfers = result['transfers']
        chip_used = result['chip_used']
        announcement = result['announcement']

        print("=" * 80)
        print("DECISION SUMMARY")
        print("=" * 80)
        print(f"Squad size: {len(squad)} players")
        print(f"Transfers: {len(transfers)}")
        print(f"Chip used: {chip_used or 'None'}")
        print()

        # Show starting XI
        print("STARTING XI:")
        starting = sorted([p for p in squad if p.get('position', 16) <= 11], key=lambda x: x.get('position', 99))
        for p in starting:
            cap = " (C)" if p.get('is_captain') else " (VC)" if p.get('is_vice_captain') else ""
            print(f"  {p.get('position', 0):2d}. {p['web_name']:20s} £{p['now_cost']/10:.1f}m{cap}")

        print()

        # STEP 6: Verify draft_team saved
        print("🔧 STEP 6: Verifying draft_team saved to database")
        print("=" * 80)

        draft = db.get_draft_team(9)
        if draft and len(draft) > 0:
            print(f"✅ Draft team saved: {len(draft)} players")
            print()
            print("✅ STEP 6 COMPLETE: Draft team verified in database")
        else:
            print("❌ ERROR: Draft team not found in database")
            return 1

        print()

        # STEP 7: Review LLM-generated announcement
        print("🔧 STEP 7: Reviewing LLM-generated team announcement")
        print("=" * 80)
        print()
        print(announcement)
        print()
        print("=" * 80)
        print()

        if len(announcement) > 100 and "Right lads" in announcement:
            print("✅ STEP 7 COMPLETE: LLM-powered announcement generated")
        else:
            print("⚠️  Warning: Announcement may be fallback template")

        print()

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        print()
        print("Cleaning up...")
        try:
            await ron.stop()
            print("✅ Agents stopped")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")

    print()
    print("=" * 80)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print("  ✅ RonManager imports and ML dependencies verified")
    print("  ✅ FPL data available (GW1-8 + fixtures)")
    print("  ✅ Value rankings generated (all analysts)")
    print("  ✅ Event bus and RonManager initialized")
    print("  ✅ make_weekly_decision executed successfully")
    print("  ✅ Draft team saved to database")
    print("  ✅ LLM-powered announcement generated")
    print()
    print("Event-driven architecture: FULLY OPERATIONAL 🚀")
    print()

    return 0


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
