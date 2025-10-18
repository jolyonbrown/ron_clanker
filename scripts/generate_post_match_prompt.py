#!/usr/bin/env python3
"""
Generate Post-Match Analysis Prompt for Claude

Collects gameweek data and creates a ready-to-use prompt for Claude
to generate Ron's post-match analysis.

Usage:
    python scripts/generate_post_match_prompt.py --gw 8
    python scripts/generate_post_match_prompt.py --gw 8 --copy-clipboard
    python scripts/generate_post_match_prompt.py --gw 8 --save
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.collect_gameweek_data import GameweekDataCollector
from data.database import Database
from utils.gameweek import get_current_gameweek
from utils.config import load_config


def load_prompt_template() -> str:
    """Load the prompt template."""
    template_path = project_root / 'prompts' / 'post_match_analysis.md'
    with open(template_path, 'r') as f:
        return f.read()


def generate_prompt(gameweek_data: dict, template: str) -> str:
    """Generate the full prompt by substituting data into template."""

    gameweek = gameweek_data['gameweek']
    day_time = datetime.now().strftime('%A night, %d %B %Y, %H:%M')

    # Substitute placeholders
    prompt = template.replace('{{GAMEWEEK}}', str(gameweek))
    prompt = prompt.replace('{{GAMEWEEK_DATA}}', json.dumps(gameweek_data, indent=2, default=str))
    prompt = prompt.replace('{{DAY_TIME}}', day_time)

    return prompt


def main():
    parser = argparse.ArgumentParser(description='Generate post-match analysis prompt')
    parser.add_argument('--gw', '--gameweek', type=int, dest='gameweek',
                       help='Gameweek to analyze (default: most recent finished)')
    parser.add_argument('--save', action='store_true',
                       help='Save prompt to file')
    parser.add_argument('--output-dir', type=str, default='prompts/generated',
                       help='Output directory for saved prompts')
    parser.add_argument('--copy-clipboard', action='store_true',
                       help='Copy prompt to clipboard (requires pyperclip)')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("POST-MATCH ANALYSIS PROMPT GENERATOR")
    print("=" * 70)

    # Initialize
    db = Database()

    # Load config (from .env and ron_config.json)
    config = load_config()

    # Determine gameweek
    if args.gameweek:
        gameweek = args.gameweek
    else:
        current_gw = get_current_gameweek(db)
        gameweek = current_gw - 1 if current_gw and current_gw > 1 else 1

    print(f"Gameweek: {gameweek}")
    print("=" * 70)

    # Step 1: Collect data
    print("\n📊 Collecting gameweek data...")
    collector = GameweekDataCollector(db, config)
    gameweek_data = collector.collect_all(gameweek)

    if not gameweek_data.get('ron_performance'):
        print(f"❌ No data available for GW{gameweek}")
        print("   Make sure the gameweek has finished and data is in the database.")
        return 1

    perf = gameweek_data['ron_performance']
    print(f"   ✓ Ron's points: {perf['points']} ({perf['points_vs_average']:+d} vs avg)")

    # Step 2: Load template
    print("\n📝 Loading prompt template...")
    template = load_prompt_template()
    print(f"   ✓ Template loaded ({len(template)} chars)")

    # Step 3: Generate prompt
    print("\n🎭 Generating Ron's prompt...")
    prompt = generate_prompt(gameweek_data, template)
    print(f"   ✓ Prompt generated ({len(prompt)} chars)")

    # Display summary
    print("\n" + "=" * 70)
    print("PROMPT READY!")
    print("=" * 70)
    print(f"\nGameweek: {gameweek}")
    print(f"Ron's Points: {perf['points']}")
    print(f"vs Average: {perf['points_vs_average']:+d}")

    if gameweek_data.get('mini_league'):
        league = gameweek_data['mini_league']
        print(f"League Position: {league['ron_position']} of {league['total_managers']}")

    # Save to file
    if args.save:
        output_dir = project_root / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f'gw{gameweek}_post_match_prompt_{timestamp}.md'

        with open(output_file, 'w') as f:
            f.write(prompt)

        print(f"\n💾 Saved to: {output_file}")

    # Copy to clipboard
    if args.copy_clipboard:
        try:
            import pyperclip
            pyperclip.copy(prompt)
            print("\n📋 Copied to clipboard!")
        except ImportError:
            print("\n⚠️  pyperclip not installed. Install with: pip install pyperclip")

    # Display prompt
    print("\n" + "=" * 70)
    print("FULL PROMPT (ready to paste into Claude):")
    print("=" * 70)
    print(prompt)
    print("\n" + "=" * 70)

    print("\n✅ Ready to generate Ron's analysis!")
    print("   Copy the prompt above and paste into Claude.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
