#!/usr/bin/env python3
"""Initialize the chaoting SQLite database."""

import os
import sqlite3

CHAOTING_DIR = os.environ.get("CHAOTING_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(CHAOTING_DIR, "chaoting.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS zouzhe (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    state         TEXT NOT NULL DEFAULT 'created',
    priority      TEXT DEFAULT 'normal',
    assigned_agent TEXT,
    plan          TEXT,
    output        TEXT,
    summary       TEXT,
    error         TEXT,
    retry_count   INTEGER DEFAULT 0,
    max_retries   INTEGER DEFAULT 2,
    timeout_sec   INTEGER DEFAULT 600,
    dispatched_at TEXT,
    created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS liuzhuan (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    from_role   TEXT,
    to_role     TEXT,
    action      TEXT,
    remark      TEXT,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    FOREIGN KEY (zouzhe_id) REFERENCES zouzhe(id)
);

CREATE TABLE IF NOT EXISTS zoubao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    agent_id    TEXT,
    text        TEXT,
    todos_json  TEXT,
    tokens_used INTEGER,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    FOREIGN KEY (zouzhe_id) REFERENCES zouzhe(id)
);

CREATE TABLE IF NOT EXISTS dianji (
    agent_role    TEXT,
    context_key   TEXT,
    context_value TEXT,
    source        TEXT,
    confidence    TEXT DEFAULT 'fresh',
    created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    PRIMARY KEY (agent_role, context_key)
);

CREATE TABLE IF NOT EXISTS qianche (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_role  TEXT,
    zouzhe_id   TEXT,
    lesson      TEXT,
    created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS toupiao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    round       INTEGER DEFAULT 1,
    jishi_id    TEXT NOT NULL,
    agent_id    TEXT NOT NULL,
    vote        TEXT NOT NULL,
    reason      TEXT,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    FOREIGN KEY (zouzhe_id) REFERENCES zouzhe(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_toupiao_unique ON toupiao(zouzhe_id, round, jishi_id);
CREATE INDEX IF NOT EXISTS idx_toupiao_zouzhe ON toupiao(zouzhe_id);

CREATE TABLE IF NOT EXISTS tongzhi (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id    TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    channel      TEXT NOT NULL DEFAULT 'discord_channel',
    recipient    TEXT,
    body         TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'pending',
    retry_count  INTEGER NOT NULL DEFAULT 0,
    max_retries  INTEGER NOT NULL DEFAULT 3,
    error        TEXT,
    dedup_key    TEXT UNIQUE,
    created_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    sent_at      TEXT,
    updated_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_tongzhi_state ON tongzhi(state, created_at);
CREATE INDEX IF NOT EXISTS idx_tongzhi_zouzhe ON tongzhi(zouzhe_id);

CREATE INDEX IF NOT EXISTS idx_zouzhe_state ON zouzhe(state);
CREATE INDEX IF NOT EXISTS idx_liuzhuan_zouzhe ON liuzhuan(zouzhe_id);
CREATE INDEX IF NOT EXISTS idx_zoubao_zouzhe ON zoubao(zouzhe_id);
CREATE INDEX IF NOT EXISTS idx_dianji_role ON dianji(agent_role);
"""

# New columns to add to zouzhe for menxia review mechanism
ZOUZHE_NEW_COLUMNS = [
    ("review_required", "INTEGER DEFAULT 0"),
    ("review_agents", "TEXT"),
    ("revise_count", "INTEGER DEFAULT 0"),
    ("plan_history", "TEXT"),
]


def _get_existing_columns(db, table):
    """Return set of column names for a table."""
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def migrate_db(db):
    """Add new columns/tables to an existing database (safe to re-run)."""
    existing = _get_existing_columns(db, "zouzhe")
    for col_name, col_def in ZOUZHE_NEW_COLUMNS:
        if col_name not in existing:
            db.execute(f"ALTER TABLE zouzhe ADD COLUMN {col_name} {col_def}")
            print(f"  Added column zouzhe.{col_name}")

    # Ensure tongzhi table exists (for existing DBs created before this migration)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tongzhi (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            zouzhe_id    TEXT NOT NULL,
            event_type   TEXT NOT NULL,
            channel      TEXT NOT NULL DEFAULT 'discord_channel',
            recipient    TEXT,
            body         TEXT NOT NULL,
            state        TEXT NOT NULL DEFAULT 'pending',
            retry_count  INTEGER NOT NULL DEFAULT 0,
            max_retries  INTEGER NOT NULL DEFAULT 3,
            error        TEXT,
            dedup_key    TEXT UNIQUE,
            created_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
            sent_at      TEXT,
            updated_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tongzhi_state ON tongzhi(state, created_at);
        CREATE INDEX IF NOT EXISTS idx_tongzhi_zouzhe ON tongzhi(zouzhe_id);
    """)


def init_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript(SCHEMA)
    migrate_db(db)
    db.commit()
    db.close()
    print(f"Database initialized: {DB_PATH}")


if __name__ == "__main__":
    init_db()
