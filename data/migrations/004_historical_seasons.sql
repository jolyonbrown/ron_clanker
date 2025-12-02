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
