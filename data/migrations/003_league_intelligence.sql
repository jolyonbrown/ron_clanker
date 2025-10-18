-- League Intelligence Schema
-- Tracks mini-league rivals for competitive analysis

-- ============================================================================
-- LEAGUE TRACKING
-- ============================================================================

-- Rivals in Ron's mini-league
CREATE TABLE IF NOT EXISTS league_rivals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,             -- FPL team ID
    player_name TEXT NOT NULL,             -- Manager name
    team_name TEXT NOT NULL,               -- FPL team name
    league_id INTEGER NOT NULL,            -- Which league they're in
    first_seen_gw INTEGER NOT NULL,        -- When we started tracking
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entry_id, league_id)
);

CREATE INDEX idx_league_rivals_entry ON league_rivals(entry_id);

-- Historical league standings snapshots
CREATE TABLE IF NOT EXISTS league_standings_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    entry_id INTEGER NOT NULL,             -- FPL team ID
    gameweek INTEGER NOT NULL,
    rank INTEGER NOT NULL,                 -- Position in league
    last_rank INTEGER,                     -- Previous GW rank
    total_points INTEGER NOT NULL,         -- Overall points
    event_points INTEGER,                  -- Points this GW
    bank_value INTEGER,                    -- Team value in £x10 (e.g., 1000 = £100.0m)
    value INTEGER,                         -- Actual squad value
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_id) REFERENCES league_rivals(entry_id),
    UNIQUE(league_id, entry_id, gameweek)
);

CREATE INDEX idx_league_standings_gw ON league_standings_history(league_id, gameweek);
CREATE INDEX idx_league_standings_entry ON league_standings_history(entry_id, gameweek);

-- ============================================================================
-- CHIP TRACKING
-- ============================================================================

-- Rival chip usage
CREATE TABLE IF NOT EXISTS rival_chip_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    chip_name TEXT NOT NULL,               -- wildcard, bencboost, 3xc, freehit
    chip_number INTEGER,                   -- 1 or 2 (for tracking 1st/2nd half usage)
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_id) REFERENCES league_rivals(entry_id),
    UNIQUE(entry_id, gameweek, chip_name)
);

CREATE INDEX idx_rival_chips ON rival_chip_usage(entry_id, gameweek);

-- ============================================================================
-- SQUAD TRACKING
-- ============================================================================

-- Rival team picks per gameweek
CREATE TABLE IF NOT EXISTS rival_team_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    player_id INTEGER NOT NULL,            -- FPL player ID
    position INTEGER NOT NULL,             -- 1-15 (squad position)
    is_captain BOOLEAN DEFAULT FALSE,
    is_vice_captain BOOLEAN DEFAULT FALSE,
    multiplier INTEGER DEFAULT 1,          -- 0=benched, 1=playing, 2=captain, 3=TC
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_id) REFERENCES league_rivals(entry_id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    UNIQUE(entry_id, gameweek, player_id)
);

CREATE INDEX idx_rival_picks_gw ON rival_team_picks(entry_id, gameweek);
CREATE INDEX idx_rival_picks_player ON rival_team_picks(player_id, gameweek);

-- ============================================================================
-- TRANSFER TRACKING
-- ============================================================================

-- Rival transfers
CREATE TABLE IF NOT EXISTS rival_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    player_in INTEGER NOT NULL,            -- Player brought in
    player_out INTEGER NOT NULL,           -- Player sold
    transfer_cost INTEGER DEFAULT 0,        -- 0 for free, 4 for hit
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_id) REFERENCES league_rivals(entry_id),
    FOREIGN KEY (player_in) REFERENCES players(id),
    FOREIGN KEY (player_out) REFERENCES players(id)
);

CREATE INDEX idx_rival_transfers_gw ON rival_transfers(entry_id, gameweek);
CREATE INDEX idx_rival_transfers_in ON rival_transfers(player_in, gameweek);
CREATE INDEX idx_rival_transfers_out ON rival_transfers(player_out, gameweek);

-- ============================================================================
-- COMPETITIVE ANALYSIS VIEWS
-- ============================================================================

-- Current league standings
CREATE VIEW IF NOT EXISTS current_league_standings AS
SELECT
    lr.entry_id,
    lr.player_name,
    lr.team_name,
    lsh.gameweek,
    lsh.rank,
    lsh.total_points,
    lsh.event_points,
    lsh.bank_value / 10.0 as bank_m,
    lsh.value / 10.0 as value_m,
    (lsh.rank - lsh.last_rank) as rank_change
FROM league_rivals lr
JOIN league_standings_history lsh ON lr.entry_id = lsh.entry_id
WHERE lsh.gameweek = (SELECT MAX(gameweek) FROM league_standings_history WHERE league_id = lsh.league_id)
ORDER BY lsh.rank;

-- Chip status by rival
CREATE VIEW IF NOT EXISTS rival_chip_status AS
SELECT
    lr.entry_id,
    lr.player_name,
    lr.team_name,
    COUNT(DISTINCT CASE WHEN chip_name = 'wildcard' THEN chip_number END) as wildcards_used,
    COUNT(DISTINCT CASE WHEN chip_name = 'bencboost' THEN chip_number END) as bench_boosts_used,
    COUNT(DISTINCT CASE WHEN chip_name = '3xc' THEN chip_number END) as triple_captains_used,
    COUNT(DISTINCT CASE WHEN chip_name = 'freehit' THEN chip_number END) as free_hits_used,
    (2 - COUNT(DISTINCT CASE WHEN chip_name = 'wildcard' THEN chip_number END)) as wildcards_remaining,
    (2 - COUNT(DISTINCT CASE WHEN chip_name = 'bencboost' THEN chip_number END)) as bench_boosts_remaining,
    (2 - COUNT(DISTINCT CASE WHEN chip_name = '3xc' THEN chip_number END)) as triple_captains_remaining,
    (2 - COUNT(DISTINCT CASE WHEN chip_name = 'freehit' THEN chip_number END)) as free_hits_remaining
FROM league_rivals lr
LEFT JOIN rival_chip_usage rcu ON lr.entry_id = rcu.entry_id
GROUP BY lr.entry_id, lr.player_name, lr.team_name;

-- Player ownership within league
CREATE VIEW IF NOT EXISTS league_player_ownership AS
SELECT
    p.id as player_id,
    p.web_name,
    p.team_id,
    rtp.gameweek,
    COUNT(DISTINCT rtp.entry_id) as rival_count,
    ROUND(COUNT(DISTINCT rtp.entry_id) * 100.0 /
        (SELECT COUNT(DISTINCT entry_id) FROM rival_team_picks WHERE gameweek = rtp.gameweek), 1) as league_ownership_pct,
    SUM(CASE WHEN rtp.is_captain THEN 1 ELSE 0 END) as captain_count,
    SUM(CASE WHEN rtp.multiplier = 3 THEN 1 ELSE 0 END) as triple_captain_count
FROM players p
JOIN rival_team_picks rtp ON p.id = rtp.player_id
GROUP BY p.id, p.web_name, p.team_id, rtp.gameweek;

-- Most transferred players in league
CREATE VIEW IF NOT EXISTS league_transfer_trends AS
SELECT
    p.id as player_id,
    p.web_name,
    p.team_id,
    rt.gameweek,
    COUNT(*) as transfer_count,
    'IN' as direction
FROM players p
JOIN rival_transfers rt ON p.id = rt.player_in
GROUP BY p.id, p.web_name, p.team_id, rt.gameweek

UNION ALL

SELECT
    p.id as player_id,
    p.web_name,
    p.team_id,
    rt.gameweek,
    COUNT(*) as transfer_count,
    'OUT' as direction
FROM players p
JOIN rival_transfers rt ON p.id = rt.player_out
GROUP BY p.id, p.web_name, p.team_id, rt.gameweek;
