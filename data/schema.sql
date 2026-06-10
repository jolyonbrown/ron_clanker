-- Ron Clanker FPL Management System - Database Schema

-- ============================================================================
-- CORE FPL DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    code INTEGER UNIQUE,
    first_name TEXT NOT NULL,
    second_name TEXT NOT NULL,
    web_name TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    element_type INTEGER NOT NULL,  -- 1=GK, 2=DEF, 3=MID, 4=FWD
    now_cost INTEGER NOT NULL,
    selected_by_percent REAL,
    form REAL,
    points_per_game REAL,
    total_points INTEGER DEFAULT 0,
    minutes INTEGER DEFAULT 0,
    goals_scored INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    clean_sheets INTEGER DEFAULT 0,
    goals_conceded INTEGER DEFAULT 0,
    own_goals INTEGER DEFAULT 0,
    penalties_saved INTEGER DEFAULT 0,
    penalties_missed INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    bonus INTEGER DEFAULT 0,
    bps INTEGER DEFAULT 0,
    influence REAL,
    creativity REAL,
    threat REAL,
    ict_index REAL,
    -- NEW 2025/26 stats
    tackles INTEGER DEFAULT 0,
    interceptions INTEGER DEFAULT 0,
    clearances_blocks_interceptions INTEGER DEFAULT 0,
    recoveries INTEGER DEFAULT 0,
    status TEXT,  -- available, injured, suspended, etc.
    news TEXT,
    chance_of_playing_next_round INTEGER,
    -- Set piece responsibility (from FPL API)
    penalties_order INTEGER,  -- 1 = first choice penalty taker, NULL = not on pens
    corners_and_indirect_freekicks_order INTEGER,  -- 1 = first choice, NULL = not assigned
    direct_freekicks_order INTEGER,  -- 1 = first choice, NULL = not assigned
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    code INTEGER UNIQUE,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    strength INTEGER,
    strength_overall_home INTEGER,
    strength_overall_away INTEGER,
    strength_attack_home INTEGER,
    strength_attack_away INTEGER,
    strength_defence_home INTEGER,
    strength_defence_away INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY,
    code INTEGER UNIQUE,
    event INTEGER,  -- gameweek number
    team_h INTEGER NOT NULL,
    team_a INTEGER NOT NULL,
    team_h_difficulty INTEGER,
    team_a_difficulty INTEGER,
    kickoff_time TIMESTAMP,
    started BOOLEAN DEFAULT FALSE,
    finished BOOLEAN DEFAULT FALSE,
    team_h_score INTEGER,
    team_a_score INTEGER,
    h_att INTEGER, h_def INTEGER, a_att INTEGER, a_def INTEGER,
    FOREIGN KEY (team_h) REFERENCES teams(id),
    FOREIGN KEY (team_a) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS gameweeks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    deadline_time TIMESTAMP NOT NULL,
    finished BOOLEAN DEFAULT FALSE,
    is_current BOOLEAN DEFAULT FALSE,
    is_next BOOLEAN DEFAULT FALSE,
    chip_plays TEXT,  -- JSON array of allowed chips
    most_selected INTEGER,
    most_transferred_in INTEGER,
    most_captained INTEGER,
    most_vice_captained INTEGER,
    FOREIGN KEY (most_selected) REFERENCES players(id),
    FOREIGN KEY (most_transferred_in) REFERENCES players(id),
    FOREIGN KEY (most_captained) REFERENCES players(id),
    FOREIGN KEY (most_vice_captained) REFERENCES players(id)
);

-- ============================================================================
-- TEAM STATE
-- ============================================================================

CREATE TABLE IF NOT EXISTS my_team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    position INTEGER NOT NULL,  -- 1-15 (1-11 starting, 12-15 bench)
    purchase_price INTEGER NOT NULL,
    selling_price INTEGER NOT NULL,
    is_captain BOOLEAN DEFAULT FALSE,
    is_vice_captain BOOLEAN DEFAULT FALSE,
    multiplier INTEGER DEFAULT 1,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id)
);

CREATE TABLE IF NOT EXISTS chips_used (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chip_name TEXT NOT NULL,  -- wildcard, bench_boost, triple_captain, free_hit
    gameweek INTEGER NOT NULL,
    chip_half INTEGER NOT NULL,  -- 1 or 2 (first/second half of season)
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id)
);

CREATE TABLE IF NOT EXISTS team_value (
    gameweek INTEGER PRIMARY KEY,
    team_value INTEGER NOT NULL,
    bank INTEGER NOT NULL,
    total_value INTEGER NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id)
);

-- ============================================================================
-- DECISION TRACKING & LEARNING
-- ============================================================================

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gameweek INTEGER NOT NULL,
    decision_type TEXT NOT NULL,  -- transfer, captain, chip, formation, etc.
    decision_data TEXT NOT NULL,  -- JSON with details
    reasoning TEXT NOT NULL,
    expected_value REAL,
    actual_value REAL,
    agent_source TEXT,  -- which agent recommended this
    confidence REAL,  -- 0-1 confidence in decision
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id)
);

CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gameweek INTEGER NOT NULL,
    player_out_id INTEGER NOT NULL,
    player_in_id INTEGER NOT NULL,
    transfer_cost INTEGER DEFAULT 0,  -- points hit taken
    is_free_transfer BOOLEAN DEFAULT TRUE,
    reasoning TEXT,
    expected_gain REAL,
    actual_gain REAL,
    status TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id),
    FOREIGN KEY (player_out_id) REFERENCES players(id),
    FOREIGN KEY (player_in_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS player_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    predicted_points REAL NOT NULL,
    predicted_minutes INTEGER,
    prediction_confidence REAL,
    actual_points INTEGER,
    prediction_error REAL,
    model_version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id),
    UNIQUE(player_id, gameweek)
);

CREATE TABLE IF NOT EXISTS price_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prediction_for_date DATE NOT NULL,  -- When we expect the change
    predicted_change INTEGER NOT NULL,  -- -1 (fall), 0 (hold), +1 (rise)
    confidence REAL NOT NULL,  -- 0.0 to 1.0
    model_version TEXT,
    features TEXT,  -- JSON of features used
    actual_change INTEGER,  -- -1, 0, +1 (NULL if not happened yet)
    prediction_correct BOOLEAN,
    FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS learning_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    gameweek INTEGER,
    value REAL NOT NULL,
    trend TEXT,
    notes TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- HISTORICAL DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_gameweek_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    fixture_id INTEGER,
    minutes INTEGER DEFAULT 0,
    goals_scored INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    clean_sheets INTEGER DEFAULT 0,
    goals_conceded INTEGER DEFAULT 0,
    own_goals INTEGER DEFAULT 0,
    penalties_saved INTEGER DEFAULT 0,
    penalties_missed INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    bonus INTEGER DEFAULT 0,
    bps INTEGER DEFAULT 0,
    influence REAL,
    creativity REAL,
    threat REAL,
    ict_index REAL,
    -- NEW 2025/26 stats
    tackles INTEGER DEFAULT 0,
    interceptions INTEGER DEFAULT 0,
    clearances_blocks_interceptions INTEGER DEFAULT 0,
    recoveries INTEGER DEFAULT 0,
    defensive_contribution_points INTEGER DEFAULT 0,
    expected_goals REAL DEFAULT 0,
    expected_assists REAL DEFAULT 0,
    expected_goal_involvements REAL DEFAULT 0,
    expected_goals_conceded REAL DEFAULT 0,
    total_points INTEGER DEFAULT 0,
    value INTEGER,
    selected INTEGER,
    transfers_in INTEGER,
    transfers_out INTEGER,
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id),
    FOREIGN KEY (fixture_id) REFERENCES fixtures(id),
    UNIQUE(player_id, gameweek, fixture_id)
);

-- Shape matches migrations/003_add_price_tracking.sql (the live table).
-- An older definition here (change_date/net_transfers) diverged from
-- what the migration actually created — fresh installs got a table the
-- price pipeline couldn't write to.
CREATE TABLE IF NOT EXISTS price_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    old_price INTEGER NOT NULL,
    new_price INTEGER NOT NULL,
    change_amount INTEGER NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gameweek INTEGER
);

-- Daily transfer/price snapshots feeding the price model (was only in
-- migrations/003 — fresh installs lacked it entirely)
CREATE TABLE IF NOT EXISTS player_transfer_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    transfers_in INTEGER DEFAULT 0,
    transfers_out INTEGER DEFAULT 0,
    net_transfers INTEGER DEFAULT 0,
    transfers_in_event INTEGER DEFAULT 0,
    transfers_out_event INTEGER DEFAULT 0,
    selected_by_percent REAL DEFAULT 0.0,
    form REAL DEFAULT 0.0,
    points_per_game REAL DEFAULT 0.0,
    total_points INTEGER DEFAULT 0,
    now_cost INTEGER NOT NULL,
    cost_change_event INTEGER DEFAULT 0,
    cost_change_start INTEGER DEFAULT 0,
    gameweek INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_player_date
    ON player_transfer_snapshots(player_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_date
    ON player_transfer_snapshots(snapshot_date);

-- ============================================================================
-- AGENT PERFORMANCE TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    gameweek INTEGER NOT NULL,
    recommendation_type TEXT,
    recommendation_data TEXT,  -- JSON
    was_followed BOOLEAN,
    expected_outcome REAL,
    actual_outcome REAL,
    accuracy_score REAL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gameweek) REFERENCES gameweeks(id)
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
CREATE INDEX IF NOT EXISTS idx_players_type ON players(element_type);
CREATE INDEX IF NOT EXISTS idx_players_cost ON players(now_cost);
CREATE INDEX IF NOT EXISTS idx_fixtures_gameweek ON fixtures(event);
CREATE INDEX IF NOT EXISTS idx_fixtures_teams ON fixtures(team_h, team_a);
CREATE INDEX IF NOT EXISTS idx_my_team_gameweek ON my_team(gameweek);
CREATE INDEX IF NOT EXISTS idx_my_team_player ON my_team(player_id);
CREATE INDEX IF NOT EXISTS idx_decisions_gameweek ON decisions(gameweek);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_transfers_gameweek ON transfers(gameweek);
CREATE INDEX IF NOT EXISTS idx_player_predictions_gameweek ON player_predictions(gameweek);
CREATE INDEX IF NOT EXISTS idx_price_predictions_date ON price_predictions(prediction_for_date);
CREATE INDEX IF NOT EXISTS idx_history_player_gameweek ON player_gameweek_history(player_id, gameweek);
CREATE INDEX IF NOT EXISTS idx_price_changes_date ON price_changes(detected_at);
CREATE INDEX IF NOT EXISTS idx_agent_performance_gameweek ON agent_performance(gameweek);
CREATE INDEX IF NOT EXISTS idx_agent_performance_agent ON agent_performance(agent_name);

-- ============================================================================
-- FOLDED-IN MIGRATIONS (2026-06-10): fresh installs previously missed every
-- table created only by data/migrations/*.sql. All statements are
-- IF NOT EXISTS, so this is a no-op on existing databases.
-- ============================================================================

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

-- Migration 004: Multi-Season Historical Data
--
-- Adds tables to store historical FPL data from previous seasons.
-- Uses player 'code' (not 'id') as the stable identifier across seasons.
--
-- Key design decisions:
-- 1. player_code is the stable identifier (persists across seasons)
-- 2. season_element_id is the season-specific ID used in that year's API
-- 3. Teams have season-specific IDs (promotion/relegation changes roster)
-- 4. All historical data is prefixed with 'historical_' to distinguish from current season
--
-- Data source: https://github.com/vaastav/Fantasy-Premier-League

-- ============================================================================
-- SEASONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,              -- e.g., '2024-25'
    name TEXT NOT NULL,               -- e.g., '2024/25'
    start_year INTEGER NOT NULL,      -- e.g., 2024
    end_year INTEGER NOT NULL,        -- e.g., 2025
    total_gameweeks INTEGER DEFAULT 38,
    is_current BOOLEAN DEFAULT FALSE,
    data_source TEXT,                 -- 'vaastav_github' or 'fpl_api'
    import_completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- HISTORICAL TEAMS
-- Teams can be promoted/relegated, so we track them per-season
-- ============================================================================

CREATE TABLE IF NOT EXISTS historical_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id TEXT NOT NULL,
    team_code INTEGER NOT NULL,           -- Stable team identifier
    season_team_id INTEGER NOT NULL,      -- ID used in that season's API
    name TEXT NOT NULL,
    short_name TEXT,
    strength INTEGER,
    strength_attack_home INTEGER,
    strength_attack_away INTEGER,
    strength_defence_home INTEGER,
    strength_defence_away INTEGER,
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    UNIQUE(season_id, team_code)
);

-- ============================================================================
-- HISTORICAL PLAYERS
-- Maps player codes to their season-specific data
-- ============================================================================

CREATE TABLE IF NOT EXISTS historical_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id TEXT NOT NULL,
    player_code INTEGER NOT NULL,         -- STABLE across seasons
    season_element_id INTEGER NOT NULL,   -- ID used in that season's gameweek data
    first_name TEXT,
    second_name TEXT,
    web_name TEXT NOT NULL,
    team_code INTEGER,                    -- Which team they played for
    element_type INTEGER NOT NULL,        -- 1=GK, 2=DEF, 3=MID, 4=FWD
    -- Season totals
    total_points INTEGER DEFAULT 0,
    total_minutes INTEGER DEFAULT 0,
    goals_scored INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    clean_sheets INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    bonus INTEGER DEFAULT 0,
    -- Season averages
    points_per_game REAL,
    -- Price info
    start_cost INTEGER,                   -- Cost at season start (in 0.1m units)
    end_cost INTEGER,                     -- Cost at season end
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    UNIQUE(season_id, player_code)
);

-- ============================================================================
-- HISTORICAL GAMEWEEK DATA
-- The core training data - player performance per gameweek per season
-- ============================================================================

CREATE TABLE IF NOT EXISTS historical_gameweek_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id TEXT NOT NULL,
    player_code INTEGER NOT NULL,         -- STABLE player identifier
    gameweek INTEGER NOT NULL,
    -- Basic stats
    minutes INTEGER DEFAULT 0,
    goals_scored INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    clean_sheets INTEGER DEFAULT 0,
    goals_conceded INTEGER DEFAULT 0,
    own_goals INTEGER DEFAULT 0,
    penalties_saved INTEGER DEFAULT 0,
    penalties_missed INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    bonus INTEGER DEFAULT 0,
    bps INTEGER DEFAULT 0,
    -- ICT metrics (available from ~2016)
    influence REAL,
    creativity REAL,
    threat REAL,
    ict_index REAL,
    -- xG metrics (available from ~2021)
    expected_goals REAL,
    expected_assists REAL,
    expected_goal_involvements REAL,
    expected_goals_conceded REAL,
    -- Points
    total_points INTEGER DEFAULT 0,
    -- Context
    opponent_team_code INTEGER,
    was_home BOOLEAN,
    fixture_difficulty INTEGER,           -- If available
    -- Value and ownership at that time
    value INTEGER,                        -- Cost at that gameweek (0.1m units)
    selected INTEGER,                     -- Number of managers who selected
    transfers_in INTEGER,
    transfers_out INTEGER,
    -- Metadata
    fixture_id INTEGER,                   -- Original fixture ID from that season
    kickoff_time TIMESTAMP,
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    UNIQUE(season_id, player_code, gameweek, fixture_id)
);

-- ============================================================================
-- PLAYER CODE MAPPING
-- Quick lookup to find current player_id from historical player_code
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_code_mapping (
    player_code INTEGER PRIMARY KEY,      -- Stable code
    current_player_id INTEGER,            -- Current season's player.id
    current_player_name TEXT,
    first_seen_season TEXT,               -- When did we first see this player
    last_seen_season TEXT,                -- Most recent season with data
    seasons_played INTEGER DEFAULT 1,
    total_historical_points INTEGER DEFAULT 0,
    FOREIGN KEY (current_player_id) REFERENCES players(id)
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_hist_gw_season ON historical_gameweek_data(season_id);
CREATE INDEX IF NOT EXISTS idx_hist_gw_player ON historical_gameweek_data(player_code);
CREATE INDEX IF NOT EXISTS idx_hist_gw_gameweek ON historical_gameweek_data(gameweek);
CREATE INDEX IF NOT EXISTS idx_hist_gw_lookup ON historical_gameweek_data(season_id, player_code, gameweek);
CREATE INDEX IF NOT EXISTS idx_hist_players_code ON historical_players(player_code);
CREATE INDEX IF NOT EXISTS idx_hist_players_season ON historical_players(season_id);
CREATE INDEX IF NOT EXISTS idx_hist_teams_season ON historical_teams(season_id);
CREATE INDEX IF NOT EXISTS idx_player_code_current ON player_code_mapping(current_player_id);

-- ============================================================================
-- VIEWS FOR CONVENIENT ACCESS
-- ============================================================================

-- All-seasons player performance (for training ML models)
CREATE VIEW IF NOT EXISTS v_all_seasons_player_history AS
SELECT
    h.season_id,
    h.player_code,
    hp.web_name as player_name,
    hp.element_type as position,
    h.gameweek,
    h.minutes,
    h.goals_scored,
    h.assists,
    h.clean_sheets,
    h.bonus,
    h.bps,
    h.influence,
    h.creativity,
    h.threat,
    h.ict_index,
    h.expected_goals,
    h.expected_assists,
    h.total_points,
    h.was_home,
    h.value,
    h.selected
FROM historical_gameweek_data h
JOIN historical_players hp ON h.season_id = hp.season_id AND h.player_code = hp.player_code;

-- Player career summary (for identifying consistent performers)
CREATE VIEW IF NOT EXISTS v_player_career_summary AS
SELECT
    player_code,
    COUNT(DISTINCT season_id) as seasons_played,
    SUM(total_points) as career_points,
    SUM(minutes) as career_minutes,
    AVG(total_points) as avg_points_per_gw,
    SUM(goals_scored) as career_goals,
    SUM(assists) as career_assists,
    SUM(clean_sheets) as career_clean_sheets
FROM historical_gameweek_data
GROUP BY player_code;

-- Model Registry Schema
-- Tracks ML model versions, metadata, and performance metrics
-- Created: 2025-12-02

-- ============================================================================
-- MODEL REGISTRY
-- ============================================================================

-- Main registry of trained models
CREATE TABLE IF NOT EXISTS model_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,              -- e.g., 'ensemble', 'price_predictor'
    model_type TEXT NOT NULL,              -- e.g., 'xp_prediction', 'price_change'
    version TEXT NOT NULL,                 -- e.g., 'historical_20251202', 'gw13_full'
    position INTEGER,                      -- 1-4 for position-specific models, NULL for general
    file_path TEXT NOT NULL,               -- relative path to model file
    feature_columns_path TEXT,             -- relative path to feature columns file

    -- Training metadata
    training_data_start TEXT,              -- earliest data point used
    training_data_end TEXT,                -- latest data point used
    training_samples INTEGER,              -- number of training samples
    training_duration_seconds REAL,        -- how long training took

    -- Model configuration (JSON)
    hyperparameters TEXT,                  -- JSON of hyperparameters used

    -- Evaluation metrics (JSON)
    metrics TEXT,                          -- JSON of evaluation metrics

    -- Status
    is_active BOOLEAN DEFAULT FALSE,       -- is this the current production model?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deactivated_at TIMESTAMP,

    -- Ensure unique version per model/position combo
    UNIQUE(model_name, model_type, version, position)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_model_registry_active
    ON model_registry(model_name, model_type, position, is_active);
CREATE INDEX IF NOT EXISTS idx_model_registry_version
    ON model_registry(version);

-- Track model performance over time
CREATE TABLE IF NOT EXISTS model_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    predicted_value REAL NOT NULL,
    actual_value REAL,                     -- filled in after GW completes
    prediction_error REAL,                 -- actual - predicted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES model_registry(id)
);

CREATE INDEX IF NOT EXISTS idx_model_predictions_lookup
    ON model_predictions(model_id, gameweek);

-- Aggregate performance metrics per gameweek
CREATE TABLE IF NOT EXISTS model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    metric_name TEXT NOT NULL,             -- 'rmse', 'mae', 'r2', 'accuracy'
    metric_value REAL NOT NULL,
    sample_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES model_registry(id),
    UNIQUE(model_id, gameweek, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_model_performance_lookup
    ON model_performance(model_id, gameweek);

-- View for getting current active models
CREATE VIEW IF NOT EXISTS v_active_models AS
SELECT
    mr.id,
    mr.model_name,
    mr.model_type,
    mr.version,
    mr.position,
    CASE mr.position
        WHEN 1 THEN 'Goalkeepers'
        WHEN 2 THEN 'Defenders'
        WHEN 3 THEN 'Midfielders'
        WHEN 4 THEN 'Forwards'
        ELSE 'General'
    END as position_name,
    mr.file_path,
    mr.training_samples,
    mr.metrics,
    mr.created_at
FROM model_registry mr
WHERE mr.is_active = TRUE;

-- View for model performance summary
CREATE VIEW IF NOT EXISTS v_model_performance_summary AS
SELECT
    mr.model_name,
    mr.version,
    mr.position,
    mp.gameweek,
    MAX(CASE WHEN mp.metric_name = 'rmse' THEN mp.metric_value END) as rmse,
    MAX(CASE WHEN mp.metric_name = 'mae' THEN mp.metric_value END) as mae,
    MAX(CASE WHEN mp.metric_name = 'r2' THEN mp.metric_value END) as r2,
    MAX(CASE WHEN mp.metric_name = 'accuracy' THEN mp.metric_value END) as accuracy,
    MAX(mp.sample_count) as sample_count
FROM model_registry mr
JOIN model_performance mp ON mr.id = mp.model_id
GROUP BY mr.model_name, mr.version, mr.position, mp.gameweek;

-- ============================================================================
-- LIVE-DB RECONCILIATION (2026-06-10): these tables existed only in the
-- live database (created ad-hoc during the 2025-26 season). A fresh
-- install could not run the pipeline at all without current_team/
-- draft_team. DDL extracted verbatim from the live sqlite_master.
-- ============================================================================

CREATE TABLE IF NOT EXISTS current_team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    purchase_price INTEGER NOT NULL,
    selling_price INTEGER NOT NULL,
    is_captain BOOLEAN DEFAULT FALSE,
    is_vice_captain BOOLEAN DEFAULT FALSE,
    multiplier INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS draft_team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    purchase_price INTEGER NOT NULL,
    selling_price INTEGER NOT NULL,
    is_captain BOOLEAN DEFAULT FALSE,
    is_vice_captain BOOLEAN DEFAULT FALSE,
    multiplier INTEGER DEFAULT 1,
    for_gameweek INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (for_gameweek) REFERENCES gameweeks(id)
);

CREATE TABLE IF NOT EXISTS draft_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    for_gameweek INTEGER NOT NULL,
    player_out_id INTEGER NOT NULL,
    player_in_id INTEGER NOT NULL,
    transfer_cost INTEGER DEFAULT 0,
    is_free_transfer BOOLEAN DEFAULT TRUE,
    reasoning TEXT,
    expected_gain REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (for_gameweek) REFERENCES gameweeks(id),
    FOREIGN KEY (player_out_id) REFERENCES players(id),
    FOREIGN KEY (player_in_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS elo_ratings (
                team_id INTEGER NOT NULL,
                gameweek INTEGER NOT NULL,
                attacking_elo REAL NOT NULL,
                defensive_elo REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, gameweek)
            );

CREATE INDEX IF NOT EXISTS idx_elo_ratings_team_gw
            ON elo_ratings(team_id, gameweek DESC)
        ;

CREATE TABLE IF NOT EXISTS elo_match_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gameweek INTEGER NOT NULL,
                home_team_id INTEGER NOT NULL,
                away_team_id INTEGER NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                home_elo_change REAL,
                away_elo_change REAL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS learned_thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position INTEGER NOT NULL,  -- 1=GK, 2=DEF, 3=MID, 4=FWD, 0=all
    threshold_type TEXT NOT NULL,  -- 'min_gain_per_gw', 'hit_threshold'
    threshold_value REAL NOT NULL,
    sample_size INTEGER DEFAULT 0,
    mean_error REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(position, threshold_type)
);

CREATE INDEX IF NOT EXISTS idx_learned_thresholds_type ON learned_thresholds(threshold_type);

CREATE TABLE IF NOT EXISTS price_model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version TEXT NOT NULL,
    evaluation_date DATE NOT NULL,

    -- Performance metrics
    accuracy REAL,  -- Overall accuracy
    precision_rise REAL,  -- Precision for predicting rises
    recall_rise REAL,  -- Recall for predicting rises
    precision_fall REAL,
    recall_fall REAL,
    f1_score REAL,

    -- Data size
    training_samples INTEGER,
    test_samples INTEGER,

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_perf_version ON price_model_performance(model_version);

CREATE INDEX IF NOT EXISTS idx_model_perf_date ON price_model_performance(evaluation_date);

CREATE TABLE IF NOT EXISTS season_team_history (
    season TEXT NOT NULL,
    gameweek INTEGER NOT NULL,
    pick_position INTEGER NOT NULL,  -- 1-15 (1-11 starting, 12-15 bench)
    player_id INTEGER NOT NULL,
    element_type INTEGER,            -- 1=GK 2=DEF 3=MID 4=FWD
    is_captain INTEGER NOT NULL DEFAULT 0,
    is_vice_captain INTEGER NOT NULL DEFAULT 0,
    multiplier INTEGER NOT NULL DEFAULT 1,  -- 0 if didn't play (autosubbed out), 2=cap, 3=TC
    active_chip TEXT,                -- wildcard|freehit|bboost|3xc|NULL
    event_points INTEGER,
    event_transfers INTEGER,
    event_transfers_cost INTEGER,
    bank INTEGER,                    -- in tenths of millions (FPL convention)
    value INTEGER,                   -- in tenths of millions
    points_on_bench INTEGER,
    overall_rank INTEGER,
    PRIMARY KEY (season, gameweek, pick_position)
);

CREATE INDEX IF NOT EXISTS idx_sth_player_gw ON season_team_history(player_id, gameweek);

CREATE INDEX IF NOT EXISTS idx_sth_gw ON season_team_history(gameweek);
