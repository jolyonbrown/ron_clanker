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
    prediction_date DATE NOT NULL,
    current_price INTEGER NOT NULL,
    predicted_change INTEGER NOT NULL,  -- -1, 0, or 1
    confidence REAL,
    actual_change INTEGER,
    was_correct BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

CREATE TABLE IF NOT EXISTS price_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    old_price INTEGER NOT NULL,
    new_price INTEGER NOT NULL,
    change_date DATE NOT NULL,
    net_transfers INTEGER,
    selected_by_percent REAL,
    FOREIGN KEY (player_id) REFERENCES players(id)
);

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
CREATE INDEX IF NOT EXISTS idx_price_predictions_date ON price_predictions(prediction_date);
CREATE INDEX IF NOT EXISTS idx_history_player_gameweek ON player_gameweek_history(player_id, gameweek);
CREATE INDEX IF NOT EXISTS idx_price_changes_date ON price_changes(change_date);
CREATE INDEX IF NOT EXISTS idx_agent_performance_gameweek ON agent_performance(gameweek);
CREATE INDEX IF NOT EXISTS idx_agent_performance_agent ON agent_performance(agent_name);
