# News Processing Usage Guide

## Memory-Optimized News Intelligence Processing

This system processes FPL news from multiple formats while keeping memory usage under 4GB (critical for Raspberry Pi deployments).

---

## Supported Formats

### 1. Simplified Press Conferences (Recommended)

**Format**: Structured team-by-team injury/availability lists

**File Pattern**: `premier_league_press_conferences_gw{N}.txt`

**Memory Usage**: ~1-2MB

**Processing Time**: Fast (~10-15 seconds)

**Example**:
```
Arsenal
OUT
Gabriel Martinelli – out, hamstring
Martin Ødegaard – knee

DOUBT
William Saliba – "wait and see" after minor issue

Aston Villa
OUT
Emiliano Buendía – foot (back next week)
...
```

**Usage**:
```bash
python scripts/process_press_conferences.py data/news_input/premier_league_press_conferences_gw10.txt 10
```

**Best For**: Official team news, injury updates, availability status

---

### 2. Email Newsletters (.eml files)

**Format**: Email files (with HTML/headers)

**File Pattern**: `*.eml`

**Memory Usage**: ~1-2MB (after cleanup)

**Processing Time**: Moderate (~15-30 seconds)

**Features**:
- Automatic HTML extraction
- Removes email headers, images, JavaScript
- Cleans Beehiiv/marketing content
- Limits content to 8000 chars for safety

**Usage**:
```bash
python scripts/process_email_newsletter.py data/news_input/GW10_your_fpl_cheat_sheet.eml
```

**Best For**: FPL newsletters, expert opinions, cheat sheets

---

### 3. Big Five / Long-Form Articles

**Format**: Paragraph-based articles (100-120 paragraphs)

**Memory Usage**: ~2-3MB (with batching)

**Processing Time**: Slower (~60-90 seconds for 120 paragraphs)

**Features**:
- **Automatic batching**: Splits 120 paragraphs into 6 batches of 20
- Processes each batch separately (6KB tokens instead of 36KB)
- Prevents Pi memory crashes
- Combines results automatically

**Usage**:
```python
from intelligence.news_processor import NewsIntelligenceProcessor

processor = NewsIntelligenceProcessor()

with open('big_five_article.txt', 'r') as f:
    content = f.read()

# Automatically detects format and batches if needed
result = processor.process_news_article(
    title="Big Five GW10 Analysis",
    content=content,
    source="The Big Five",
    url=None
)
```

**Batching Trigger**:
- Content > 15,000 chars AND
- 50-200 paragraphs (detects "big five" format)
- Automatically batches into groups of 20 paragraphs

**Best For**: Detailed FPL analysis, "Big Five" articles, comprehensive gameweek previews

---

## Testing Memory Usage

Run the comprehensive test:

```bash
python scripts/test_news_memory.py
```

This tests all three formats and reports:
- Memory usage per format
- Number of players extracted
- Memory delta (should be <5MB per operation)
- Total memory (should stay well under 4GB)

---

## Implementation Details

### Batching Strategy

The `_process_large_content` method:

1. **Detects format**:
   - Counts paragraphs (split on `\n\n`)
   - If 50-200 paragraphs → "big five" format
   - Otherwise → character-based chunking

2. **Batches big five**:
   - Groups into batches of 20 paragraphs
   - Processes each batch separately
   - Combines results

3. **Character chunking** (fallback):
   - Splits at 10,000 char boundaries
   - Keeps related content together

### Truncation Recovery

All processing methods include JSON truncation recovery:
- Detects incomplete JSON responses
- Finds last complete player object
- Closes unclosed brackets/braces
- Logs partial extraction
- Returns all successfully parsed players

---

## Database Storage

All extracted intelligence is stored in the `decisions` table:

```sql
INSERT INTO decisions (
    gameweek,
    decision_type,
    decision_data,
    reasoning,
    agent_source,
    created_at
) VALUES (?, 'news_intelligence', ?, ?, ?, CURRENT_TIMESTAMP)
```

**Query Example**:
```sql
SELECT * FROM decisions
WHERE decision_type = 'news_intelligence'
AND gameweek = 10
ORDER BY created_at DESC;
```

---

## Performance Benchmarks (Raspberry Pi)

| Format | File Size | Players | Time | Memory |
|--------|-----------|---------|------|--------|
| Press Conf | 3KB | 68 | 12s | +1.2MB |
| Email (cleaned) | 8KB | 17 | 18s | +1.1MB |
| Big Five (batched) | 19KB (120¶) | 120 | 75s | +2.3MB |

**Total Memory Delta**: ~2-3MB per operation

✅ **Pi Safe**: All formats stay well under 4GB target

---

## MCP Integration (Future)

The news processor is ready for MCP tool integration:

```python
# In your MCP server
@tool()
async def process_press_conferences(gameweek: int, file_path: str):
    """Process simplified press conference format for injury/availability intel."""
    with open(file_path, 'r') as f:
        content = f.read()

    processor = NewsIntelligenceProcessor()
    return processor.process_simple_press_conferences(
        content=content,
        gameweek=gameweek
    )
```

---

## Troubleshooting

### Out of Memory Errors

**Symptom**: Pi crashes or freezes during processing

**Solution**:
1. Check file size: `wc -c your_file.txt`
2. If >50KB, manually split the file
3. Reduce batch size in `_process_large_content`:
   ```python
   result = processor._process_large_content(
       ...,
       batch_size=15  # Reduce from 20 to 15
   )
   ```

### JSON Parsing Errors

**Symptom**: "Failed to parse JSON from Claude response"

**Check**: The truncation recovery should handle this automatically

**Manual Fix**: Increase `max_tokens` in the processing method (but beware memory impact)

### Missing Players

**Symptom**: Some players not extracted

**Causes**:
- Player name too ambiguous ("Son" vs "Heung-Min Son")
- Mentioned in passing without status update
- Truncation (check logs for "Recovered N players from truncated response")

**Solution**: The system prioritizes quality over completeness - only extracts players with clear FPL-relevant intelligence

---

## Next Steps

1. ✅ Batched processing for big five format
2. ✅ Simplified press conference support
3. ✅ Email newsletter cleanup
4. 🔄 MCP tool integration for automated fetching
5. 🔄 Scheduled processing via cron
6. 🔄 Intelligence aggregation across sources

---

**Last Updated**: November 2025
**Memory Target**: <4GB (Raspberry Pi 4)
**Status**: Production Ready ✅
