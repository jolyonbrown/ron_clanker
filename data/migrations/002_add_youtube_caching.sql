-- Migration: Add YouTube transcript caching tables
-- Purpose: Cache transcripts for efficiency, auto-detect new videos
-- Cache TTL: 7 days (transcripts invalidated after this)

-- YouTube channels to monitor
CREATE TABLE IF NOT EXISTS youtube_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE NOT NULL,
    channel_name TEXT NOT NULL,
    channel_handle TEXT,
    reliability REAL DEFAULT 0.85,
    enabled BOOLEAN DEFAULT 1,
    last_checked TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cached video metadata
CREATE TABLE IF NOT EXISTS youtube_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT UNIQUE NOT NULL,
    channel_id TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TIMESTAMP,
    duration INTEGER,  -- seconds
    has_transcript BOOLEAN DEFAULT 0,
    is_relevant BOOLEAN DEFAULT 0,  -- Has injury/team news keywords
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cached transcripts
CREATE TABLE IF NOT EXISTS youtube_transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT UNIQUE NOT NULL,
    transcript_text TEXT NOT NULL,
    word_count INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- Auto-calculated: fetched_at + 7 days
    intelligence_extracted BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Intelligence extracted from transcripts
CREATE TABLE IF NOT EXISTS youtube_intelligence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    player_id INTEGER,  -- NULL if not matched yet
    player_name TEXT NOT NULL,
    intelligence_type TEXT NOT NULL,  -- INJURY, ROTATION, etc
    details TEXT NOT NULL,
    context TEXT,  -- Surrounding sentence
    confidence REAL DEFAULT 0.85,
    severity TEXT,  -- CRITICAL, HIGH, MEDIUM, LOW
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_youtube_videos_channel ON youtube_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_published ON youtube_videos(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_relevant ON youtube_videos(is_relevant);
CREATE INDEX IF NOT EXISTS idx_youtube_transcripts_video ON youtube_transcripts(video_id);
CREATE INDEX IF NOT EXISTS idx_youtube_transcripts_expires ON youtube_transcripts(expires_at);
CREATE INDEX IF NOT EXISTS idx_youtube_intelligence_video ON youtube_intelligence(video_id);
CREATE INDEX IF NOT EXISTS idx_youtube_intelligence_player ON youtube_intelligence(player_id);

-- Insert FPL channels to monitor
-- Note: YouTube channel IDs can be found at: youtube.com/@Handle/about
-- Look for "Channel ID" in the page source or use YouTube Data API

INSERT OR IGNORE INTO youtube_channels (channel_id, channel_name, channel_handle, reliability) VALUES
-- FPL Harry (needs actual channel ID - this is placeholder)
('UCxxxxxxxxxxxx_FPLHarry', 'FPL Harry', '@FPLHarry', 0.85),
-- Let's Talk FPL (placeholder)
('UCxxxxxxxxxxxx_LetsTalkFPL', 'Let''s Talk FPL', '@LetsTalkFPL', 0.85),
-- FPL Focal (placeholder)
('UCxxxxxxxxxxxx_FPLFocal', 'FPL Focal', '@FPLFocal', 0.85);

-- Note: Actual channel IDs need to be found and updated
-- These are placeholders to establish the schema
