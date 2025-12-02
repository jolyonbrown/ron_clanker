#!/usr/bin/env python3
"""
Test News Processing Memory Usage

Tests all three news formats and monitors memory consumption:
1. Simplified press conferences (structured)
2. Email newsletter (after cleanup)
3. Big Five format (batched processing)
"""

import sys
import os
import resource
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor
from scripts.process_email_newsletter import extract_text_from_eml, clean_email_text


def get_memory_mb():
    """Get current process memory usage in MB using resource module."""
    # On Linux, ru_maxrss is in KB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main():
    print("\n" + "=" * 80)
    print("NEWS PROCESSING MEMORY TEST")
    print("=" * 80)
    print()

    processor = NewsIntelligenceProcessor()
    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        return 1

    initial_memory = get_memory_mb()
    print(f"📊 Initial memory: {initial_memory:.1f} MB")
    print()

    # Test 1: Simplified Press Conferences
    print("-" * 80)
    print("TEST 1: SIMPLIFIED PRESS CONFERENCES")
    print("-" * 80)

    press_conf_file = project_root / "data/news_input/premier_league_press_conferences_gw10.txt"
    if press_conf_file.exists():
        with open(press_conf_file, 'r') as f:
            content = f.read()

        print(f"📋 File size: {len(content)} chars, {len(content.splitlines())} lines")
        mem_before = get_memory_mb()
        print(f"   Memory before: {mem_before:.1f} MB")

        result = processor.process_simple_press_conferences(
            content=content,
            gameweek=10,
            source="Press Conferences Test"
        )

        mem_after = get_memory_mb()
        mem_delta = mem_after - mem_before

        print(f"   Memory after: {mem_after:.1f} MB")
        print(f"   ⚡ Memory delta: {mem_delta:+.1f} MB")
        print(f"   ✓ Extracted {len(result.get('players', []))} players")
        print()
    else:
        print("   ⚠️  File not found, skipping")
        print()

    # Test 2: Email Newsletter (with cleanup)
    print("-" * 80)
    print("TEST 2: EMAIL NEWSLETTER (CLEANED)")
    print("-" * 80)

    email_file = project_root / "data/news_input/GW10_your_fpl_cheat_sheet.eml"
    if email_file.exists():
        mem_before = get_memory_mb()
        print(f"   Memory before: {mem_before:.1f} MB")

        try:
            subject, text_content = extract_text_from_eml(email_file)
            cleaned = clean_email_text(text_content)

            print(f"📧 Original: {len(text_content)} chars → Cleaned: {len(cleaned)} chars")

            # Limit to 8000 chars as in process_email_newsletter.py
            if len(cleaned) > 8000:
                cleaned = cleaned[:8000]

            result = processor.process_news_article(
                title=subject,
                content=cleaned,
                source="Email Test",
                url=None
            )

            mem_after = get_memory_mb()
            mem_delta = mem_after - mem_before

            print(f"   Memory after: {mem_after:.1f} MB")
            print(f"   ⚡ Memory delta: {mem_delta:+.1f} MB")
            print(f"   ✓ Extracted {len(result.get('players', []))} players")
            print()
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print()
    else:
        print("   ⚠️  File not found, skipping")
        print()

    # Test 3: Big Five Format (if available)
    print("-" * 80)
    print("TEST 3: BIG FIVE FORMAT (BATCHED)")
    print("-" * 80)

    # Check if we have a big five format file
    big_five_files = list((project_root / "data/news_input").glob("*big_five*.txt"))
    if big_five_files:
        big_five_file = big_five_files[0]
        with open(big_five_file, 'r') as f:
            content = f.read()

        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        print(f"📄 File: {big_five_file.name}")
        print(f"📋 Paragraphs: {len(paragraphs)}")

        mem_before = get_memory_mb()
        print(f"   Memory before: {mem_before:.1f} MB")

        result = processor.process_news_article(
            title="Big Five Test",
            content=content,
            source="Big Five Test",
            url=None
        )

        mem_after = get_memory_mb()
        mem_delta = mem_after - mem_before

        print(f"   Memory after: {mem_after:.1f} MB")
        print(f"   ⚡ Memory delta: {mem_delta:+.1f} MB")
        print(f"   ✓ Extracted {len(result.get('players', []))} players")
        print()
    else:
        print("   ⚠️  No big five format file found")
        print()

    # Summary
    final_memory = get_memory_mb()
    total_delta = final_memory - initial_memory

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"📊 Initial memory: {initial_memory:.1f} MB")
    print(f"📊 Final memory:   {final_memory:.1f} MB")
    print(f"📊 Total delta:    {total_delta:+.1f} MB")
    print()

    if final_memory < 4000:
        print("✅ PASS: Memory usage stayed under 4GB target")
    else:
        print("⚠️  WARNING: Memory usage exceeded 4GB target")

    print()
    print("=" * 80)
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
