#!/usr/bin/env python3
"""
Process Email Newsletter (.eml files)

Extracts text content from email files and processes with Claude.
"""

import sys
from pathlib import Path
import email
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.news_processor import NewsIntelligenceProcessor
from data.database import Database


def clean_email_text(text):
    """Remove email headers, image placeholders, and other junk."""
    lines = text.split('\n')
    cleaned = []

    skip_patterns = [
        'view image:',
        'caption:',
        '----------',
        '--------------------',
        'unsubscribe',
        'manage preferences',
        'view in browser',
        'click here',
        'http://',
        'https://',
        'mailto:',
        'powered by',
        'sent to',
        'beehiiv',
        'media.beehiiv.com'
    ]

    for line in lines:
        line_lower = line.lower()

        # Skip lines with junk patterns
        if any(pattern in line_lower for pattern in skip_patterns):
            continue

        # Skip empty lines
        if not line.strip():
            continue

        # Skip very short lines (likely formatting)
        if len(line.strip()) < 3:
            continue

        cleaned.append(line)

    return '\n'.join(cleaned)


def extract_text_from_eml(eml_path):
    """Extract readable text from .eml file."""
    with open(eml_path, 'rb') as f:
        msg = BytesParser(policy=policy.default).parse(f)

    subject = msg['subject']

    # Try to get text content
    text_content = None
    html_content = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()

            if content_type == 'text/plain':
                text_content = part.get_content()
            elif content_type == 'text/html':
                html_content = part.get_content()
    else:
        content_type = msg.get_content_type()
        if content_type == 'text/plain':
            text_content = msg.get_content()
        elif content_type == 'text/html':
            html_content = msg.get_content()

    # Prefer plain text, fall back to converting HTML
    if text_content:
        return subject, text_content
    elif html_content:
        # Convert HTML to text using BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script and style elements
        for script in soup(['script', 'style']):
            script.decompose()

        # Get text
        text_content = soup.get_text(separator='\n')

        # Clean up whitespace
        lines = [line.strip() for line in text_content.splitlines()]
        text_content = '\n'.join(line for line in lines if line)

        # Remove common email junk
        text_content = clean_email_text(text_content)

        return subject, text_content
    else:
        return subject, None


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/process_email_newsletter.py <email_file.eml>")
        return 1

    eml_path = Path(sys.argv[1])

    if not eml_path.exists():
        print(f"❌ File not found: {eml_path}")
        return 1

    print("\n" + "=" * 80)
    print("EMAIL NEWSLETTER PROCESSING")
    print("=" * 80)
    print()
    print(f"📧 File: {eml_path.name}")
    print()

    # Extract text
    print("📝 Extracting text from email...")
    try:
        subject, text_content = extract_text_from_eml(eml_path)

        if not text_content:
            print("❌ Could not extract text content from email")
            return 1

        print(f"✓ Subject: {subject}")
        print(f"✓ Content length: {len(text_content)} characters")
        print()

        # Show preview
        print("CONTENT PREVIEW (first 800 chars):")
        print("-" * 80)
        print(text_content[:800])
        print("-" * 80)
        print()

    except Exception as e:
        print(f"❌ Error reading email: {e}")
        return 1

    # Process with Claude
    db = Database()
    processor = NewsIntelligenceProcessor()

    if not processor.enabled:
        print("❌ Anthropic API key not configured!")
        return 1

    print("🤖 Processing with Claude Haiku...")
    print(f"   Content length: {len(text_content)} characters")

    if len(text_content) > 20000:
        print(f"   Large content - will process in batches")

    print()

    intelligence = processor.process_news_article(
        title=subject,
        content=text_content,  # Full content - batching handled automatically
        source=f'Email: {eml_path.name}',
        url=None
    )

    # Display results
    print("=" * 80)
    print("EXTRACTED INTELLIGENCE")
    print("=" * 80)
    print()

    if intelligence['players']:
        print(f"📊 Found intelligence on {len(intelligence['players'])} players:\n")

        # Group by status
        injured = [p for p in intelligence['players'] if p['status'] == 'INJURED']
        doubts = [p for p in intelligence['players'] if p['status'] == 'DOUBT']
        suspended = [p for p in intelligence['players'] if p['status'] == 'SUSPENDED']
        positive = [p for p in intelligence['players'] if p['status'] == 'AVAILABLE' and p['sentiment'] == 'POSITIVE']

        if injured:
            print("🚑 INJURED:")
            for p in injured:
                print(f"   {p['name']} (conf: {p['confidence']:.0%})")
                print(f"      {p['details']}")
            print()

        if suspended:
            print("🟥 SUSPENDED:")
            for p in suspended:
                print(f"   {p['name']} (conf: {p['confidence']:.0%})")
                print(f"      {p['details']}")
            print()

        if doubts:
            print("⚠️  DOUBTS:")
            for p in doubts:
                print(f"   {p['name']} (conf: {p['confidence']:.0%})")
                print(f"      {p['details']}")
            print()

        if positive:
            print("✅ POSITIVE MENTIONS (top 10):")
            for p in positive[:10]:
                print(f"   {p['name']}: {p['details'][:100]}...")
            print()

    else:
        print("⚠️  No player-specific intelligence extracted")
        print()

    if intelligence.get('general_insights'):
        print("💡 GENERAL INSIGHTS:")
        for insight in intelligence['general_insights']:
            print(f"   • {insight}")
        print()

    # Store in database
    print("-" * 80)
    print("💾 STORING IN DATABASE")
    print()

    stored_count = 0
    if intelligence['players']:
        for player in intelligence['players']:
            try:
                db.execute_update("""
                    INSERT INTO decisions (
                        gameweek, decision_type, decision_data, reasoning,
                        agent_source, created_at
                    ) VALUES (11, 'news_intelligence', ?, ?, 'email_processor', CURRENT_TIMESTAMP)
                """, (
                    f"Player: {player['name']}, Status: {player['status']}, Sentiment: {player['sentiment']}",
                    f"Confidence: {int(player['confidence']*100)}%, Sources: Email Newsletter, Details: {player['details']}"
                ))
                stored_count += 1
            except Exception as e:
                print(f"   ⚠️  Error storing {player['name']}: {e}")

        print(f"✓ Stored intelligence on {stored_count} players")
    else:
        print("   No player intelligence to store")

    print()
    print("=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
