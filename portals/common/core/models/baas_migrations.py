# -*- coding: utf-8 -*-
"""Shared BaaS DDL for SQLite and PostgreSQL backends."""

BAAS_SERVICES_V1_SQL = """
CREATE TABLE IF NOT EXISTS baas_services (
    service_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    env_key TEXT NOT NULL DEFAULT 'development',
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    feature_flags TEXT DEFAULT '{}',
    api_secret_hash TEXT DEFAULT '',
    config_version INTEGER DEFAULT 1,
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baas_services_project ON baas_services(project_id, env_key);

CREATE TABLE IF NOT EXISTS baas_feature_configs (
    service_id TEXT NOT NULL,
    feature_key TEXT NOT NULL,
    config_json TEXT DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (service_id, feature_key)
);

CREATE TABLE IF NOT EXISTS baas_players (
    player_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    auth_provider TEXT NOT NULL DEFAULT 'guest',
    external_id TEXT NOT NULL DEFAULT '',
    display_name TEXT DEFAULT '',
    profile_json TEXT DEFAULT '{}',
    token TEXT NOT NULL DEFAULT '',
    token_expires_at TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baas_players_service ON baas_players(service_id, external_id);

CREATE TABLE IF NOT EXISTS baas_player_data (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    data_key TEXT NOT NULL,
    value_json TEXT DEFAULT 'null',
    version INTEGER DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (service_id, player_id, data_key)
);

CREATE TABLE IF NOT EXISTS baas_announcements (
    announcement_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    body TEXT DEFAULT '',
    audience TEXT DEFAULT 'all',
    effective_at TEXT DEFAULT '',
    expires_at TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baas_mail_messages (
    mail_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    body TEXT DEFAULT '',
    attachments_json TEXT DEFAULT '[]',
    status TEXT DEFAULT 'unread',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    claimed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS baas_leaderboard_scores (
    service_id TEXT NOT NULL,
    board_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    score REAL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (service_id, board_id, player_id)
);

CREATE TABLE IF NOT EXISTS baas_wallets (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    currency_id TEXT NOT NULL,
    balance INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (service_id, player_id, currency_id)
);

CREATE TABLE IF NOT EXISTS baas_shop_orders (
    order_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    price INTEGER DEFAULT 0,
    currency_id TEXT DEFAULT 'gold',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baas_player_achievements (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    achievement_id TEXT NOT NULL,
    status TEXT DEFAULT 'locked',
    progress INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL,
    claimed_at TEXT DEFAULT '',
    PRIMARY KEY (service_id, player_id, achievement_id)
);

CREATE TABLE IF NOT EXISTS baas_gift_redemptions (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    code TEXT NOT NULL,
    rewards_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    PRIMARY KEY (service_id, player_id, code)
);

CREATE TABLE IF NOT EXISTS baas_guilds (
    guild_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    name TEXT NOT NULL,
    leader_player_id TEXT NOT NULL,
    member_count INTEGER DEFAULT 1,
    payload_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baas_guild_members (
    guild_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    joined_at TEXT NOT NULL,
    PRIMARY KEY (service_id, player_id)
);

CREATE TABLE IF NOT EXISTS baas_battlepass_progress (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    premium INTEGER DEFAULT 0,
    claimed_levels_json TEXT DEFAULT '[]',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (service_id, player_id, season_id)
);

CREATE TABLE IF NOT EXISTS baas_periodic_tasks (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_type TEXT DEFAULT 'daily',
    progress INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    updated_at TEXT NOT NULL,
    claimed_at TEXT DEFAULT '',
    PRIMARY KEY (service_id, player_id, task_id)
);

CREATE TABLE IF NOT EXISTS baas_compliance_sessions (
    service_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_heartbeat_at TEXT NOT NULL,
    total_minutes INTEGER DEFAULT 0,
    payload_json TEXT DEFAULT '{}',
    PRIMARY KEY (service_id, player_id)
);

CREATE TABLE IF NOT EXISTS baas_gift_codes (
    service_id TEXT NOT NULL,
    code TEXT NOT NULL,
    rewards_json TEXT DEFAULT '[]',
    max_uses INTEGER DEFAULT 0,
    use_count INTEGER DEFAULT 0,
    expires_at TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (service_id, code)
);
"""

BAAS_SERVICES_V2_ALTER_SQL = """
ALTER TABLE baas_services ADD COLUMN description TEXT DEFAULT '';
ALTER TABLE baas_services ADD COLUMN icon_url TEXT DEFAULT '';
ALTER TABLE baas_services ADD COLUMN disabled INTEGER DEFAULT 0;
"""
