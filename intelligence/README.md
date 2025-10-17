# Intelligence Gathering - The Scout

## Overview

The Scout monitors external sources for injury news, team news, rotation risks, and press conference updates. This gives Ron early competitive advantage before information appears in official FPL API.

## Current Status (Phase 2A)

### ✅ Implemented:
- **Scout Agent Framework** (`agents/scout.py`)
  - Event-driven intelligence gathering
  - Publishes intelligence events for other agents
  - Logs intelligence for reliability tracking

- **WebsiteMonitor** (`intelligence/website_monitor.py`)
  - Structured scraping of injury/team news sites
  - Async fetching with proper headers
  - Parser framework for multiple sources

### ⚠️ Known Issues:

**Bot Protection (HTTP 403)**

Many injury news sites (including premierinjuries.com) have bot protection that blocks automated scraping. This is standard practice.

**Current Status:**
- ✅ Framework working
- ✅ Headers configured
- ❌ Some sites block scrapers (403 errors)

## Alternative Approaches

### Option 1: RSS Feeds (Recommended - Phase 2B)

**Advantages:**
- Designed for programmatic access
- No bot detection
- Reliable and fast

**Sources:**
```python
RSS_FEEDS = {
    'bbc_football': 'http://feeds.bbci.co.uk/sport/football/rss.xml',
    'sky_sports': 'https://www.skysports.com/rss/12040',
    'premier_league_official': 'https://www.premierleague.com/news/rss',
    # Club-specific feeds
    'arsenal': 'https://www.arsenal.com/rss.xml',
    # ... etc
}
```

### Option 2: YouTube Transcripts (Planned - Phase 2B)

**Advantages:**
- Free API (`youtube-transcript-api`)
- FPL content creators do daily injury updates
- No authentication needed

**Implementation:**
```python
from youtube_transcript_api import YouTubeTranscriptApi

# Get transcript from latest FPL video
transcript = YouTubeTranscriptApi.get_transcript(video_id)
# Parse for injury mentions
```

**Trusted Channels:**
- FPL Focal
- Let's Talk FPL
- FPL Wire
- (Add your trusted sources)

### Option 3: Email Newsletters (Phase 2C)

**Sources:**
- LazyFPL (weekly, very reliable)
- FantasyFootballScout
- Official FPL newsletter

**Implementation:**
```python
# IMAP monitoring
import imaplib

# Connect to email
mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login(email, password)

# Check for new newsletters
mail.select('inbox')
_, messages = mail.search(None, 'FROM', '"LazyFPL"')

# Parse HTML emails (consistent structure)
```

### Option 4: Playwright/Selenium (Heavy, last resort)

If a source is critical and has no alternatives:

```python
from playwright.async_api import async_playwright

# Full browser automation - bypasses most bot detection
# But: Heavier, slower, more resource intensive
```

### Option 5: Manual Webhook (Hybrid Approach)

For critical breaking news:

```python
# Simple endpoint
@app.post("/intelligence/manual")
async def manual_intelligence(data: dict):
    # You (or community) manually post critical news
    # "Palmer out 6 weeks"
    # Scout processes and distributes
```

## Recommended Implementation Path

### Phase 2A (Complete): ✅
- Basic framework
- Website scraping structure
- Event publishing

### Phase 2B (Next):
1. **RSS Feed Monitor** (2 hours)
   - Add `RSSMonitor` class
   - Parse BBC, Sky Sports feeds
   - Extract injury/team news

2. **YouTube Transcript Monitor** (3 hours)
   - Add `YouTubeMonitor` class
   - Monitor 3-5 trusted FPL channels
   - Parse transcripts for injury mentions

### Phase 2C (Later):
3. **Email Newsletter Parser** (4 hours)
   - IMAP monitoring
   - Parse LazyFPL HTML emails
   - Extract structured intelligence

4. **Source Reliability Tracking** (2 hours)
   - Track which sources are accurate
   - Like Ellie tracks agent performance
   - Adjust confidence scores over time

## Testing

```bash
# Test WebsiteMonitor
python intelligence/website_monitor.py

# Test Scout agent
python scripts/test_scout.py  # TODO: Create this

# Monitor live with decision logger
python scripts/decision_logger.py
# Look for INJURY_INTELLIGENCE events
```

## Configuration

Edit `intelligence/website_monitor.py` to:
- Add/remove sources
- Adjust reliability scores
- Enable/disable specific monitors

## Notes for Human Developer

**Press Conference Today (Oct 17):**

The Palmer injury news you mentioned ("out 6 weeks") likely came from:
1. Official Chelsea press conference
2. Journalist tweets
3. FPL community Discord/Reddit

For immediate value, I recommend:
1. **Add RSS feeds** (quick win, no bot detection)
2. **YouTube transcripts** (free, reliable FPL creators)
3. **Manual webhook** for breaking news until automation ready

**Bot-Friendly Sources:**
- RSS feeds are always safe
- YouTube API is free and reliable
- Twitter alternatives (Nitter instances with RSS)
- Reddit (r/FantasyPL JSON API)

Let me know which approach you'd like to prioritize!

---

**Next Steps:**
1. Implement RSSMonitor
2. Test with live press conference data
3. Integrate with Hugo for transfer decisions
