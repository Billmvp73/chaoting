# 朝廷 (chaoting) — Multi-Agent Task Orchestration System

## Overview

A task orchestration system for OpenClaw multi-agent workflows. Agents coordinate through a shared SQLite database (stigmergy pattern) — no direct agent-to-agent communication.

**Directory:** `<CHAOTING_DIR>/`

## Components

1. `chaoting.db` — SQLite database (auto-created by init_db.py)
2. `dispatcher.py` — Python daemon, polls DB, dispatches agents via CLI
3. `chaoting` — CLI tool for agents to read/write tasks (executable Python script)
4. `init_db.py` — Database initialization script

## Naming Convention

- **States, CLI commands** → English (created, planning, executing, done, failed, timeout)
- **Table names, department names** → Pinyin (zouzhe, liuzhuan, zhongshu, bingbu, etc.)
- **Task ID format** → `ZZ-YYYYMMDD-NNN` (e.g., ZZ-20260308-001)

## SQLite Schema

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE zouzhe (
    id            TEXT PRIMARY KEY,       -- ZZ-YYYYMMDD-NNN
    title         TEXT NOT NULL,
    description   TEXT,
    state         TEXT NOT NULL DEFAULT 'created',
    -- states: created, planning, executing, done, failed, timeout
    priority      TEXT DEFAULT 'normal',  -- low/normal/high/critical
    assigned_agent TEXT,                  -- current agent role (zhongshu, bingbu, etc.)
    plan          TEXT,                   -- JSON: planning result from zhongshu
    output        TEXT,                   -- final output
    summary       TEXT,                   -- completion summary
    error         TEXT,                   -- failure reason
    retry_count   INTEGER DEFAULT 0,
    max_retries   INTEGER DEFAULT 2,
    timeout_sec   INTEGER DEFAULT 600,    -- per-task timeout
    dispatched_at TEXT,                   -- ISO timestamp, used for timeout detection
    created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE liuzhuan (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    from_role   TEXT,
    to_role     TEXT,
    action      TEXT,    -- dispatch, complete, fail, retry, timeout, recover, dispatch_error
    remark      TEXT,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    FOREIGN KEY (zouzhe_id) REFERENCES zouzhe(id)
);

CREATE TABLE zoubao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    agent_id    TEXT,
    text        TEXT,
    todos_json  TEXT,     -- optional: [{"title":"xxx","status":"done"}]
    tokens_used INTEGER,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    FOREIGN KEY (zouzhe_id) REFERENCES zouzhe(id)
);

CREATE TABLE dianji (
    agent_role    TEXT,
    context_key   TEXT,
    context_value TEXT,
    source        TEXT,       -- which zouzhe produced this
    confidence    TEXT DEFAULT 'fresh',  -- fresh/stale/unverified
    created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    PRIMARY KEY (agent_role, context_key)
);

CREATE TABLE qianche (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_role  TEXT,
    zouzhe_id   TEXT,
    lesson      TEXT,
    created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX idx_zouzhe_state ON zouzhe(state);
CREATE INDEX idx_liuzhuan_zouzhe ON liuzhuan(zouzhe_id);
CREATE INDEX idx_zoubao_zouzhe ON zoubao(zouzhe_id);
CREATE INDEX idx_dianji_role ON dianji(agent_role);
```

## State Machine

```
created → planning (dispatched to zhongshu)
planning → executing (zhongshu calls `chaoting plan`)
executing → done (agent calls `chaoting done`)

Any active state → failed (agent calls `chaoting fail`)
Any active state → timeout (dispatcher timeout detection)
```

## Dispatcher (dispatcher.py)

### Core Loop
- Poll every 5 seconds: `poll_and_dispatch()`
- Timeout check every 30 seconds: `check_timeouts()`
- On startup: `recover_orphans()`

### State Machine Transitions
```python
# Dispatcher only handles: created → planning
# Other transitions are driven by agents via chaoting CLI
STATE_TRANSITIONS = {
    "created": ("planning", "zhongshu"),
}

# When zhongshu completes planning (via `chaoting plan`),
# it sets state=executing and dispatched_at=NULL.
# Next poll cycle, dispatcher detects state=executing with dispatched_at=NULL
# and dispatches to the agent specified in the plan.
```

### Idempotent Dispatch (CRITICAL)
```python
# Use UPDATE WHERE as optimistic lock — prevents double dispatch
cursor = db.execute(
    "UPDATE zouzhe SET state = ?, dispatched_at = strftime('%Y-%m-%dT%H:%M:%S','now'), "
    "assigned_agent = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
    "WHERE state = ? AND dispatched_at IS NULL RETURNING id",
    (next_state, agent_role, current_state)
)
# If fetchone() returns None, another poll cycle already claimed it
```

### Async Dispatch (CRITICAL)
```python
def dispatch_agent(agent_id: str, zouzhe_id: str, timeout_sec: int):
    msg = (
        f"📜 奏折 {zouzhe_id} 已派发给你。\n"
        f"接旨: chaoting pull {zouzhe_id}\n"
        f"奏报: chaoting progress {zouzhe_id} '进展'\n"
        f"完成: chaoting done {zouzhe_id} '产出' '摘要'\n"
        f"失败: chaoting fail {zouzhe_id} '原因'"
    )

    def _run():
        try:
            subprocess.run(
                ["openclaw", "agent", "--agent", agent_id,
                 "-m", msg, "--deliver", "--timeout", str(timeout_sec)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_sec + 60  # grace period
            )
        except Exception as e:
            # Write dispatch error to flow log
            db = get_db()
            db.execute(
                "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                "VALUES (?, 'dispatcher', ?, 'dispatch_error', ?)",
                (zouzhe_id, agent_id, str(e))
            )
            db.commit()
            db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
```

### Timeout Detection
```python
def check_timeouts():
    # Find missions that have been dispatched longer than their timeout_sec
    rows = db.execute("""
        SELECT id, state, assigned_agent, dispatched_at, retry_count, max_retries, timeout_sec
        FROM zouzhe
        WHERE state IN ('planning', 'executing')
          AND dispatched_at IS NOT NULL
          AND (julianday('now') - julianday(dispatched_at)) * 86400 > timeout_sec
    """).fetchall()

    for row in rows:
        if row["retry_count"] < row["max_retries"]:
            # Retry: reset dispatched_at, increment retry_count
            # Next poll cycle will re-dispatch
            ...
        else:
            # Max retries exhausted → timeout state
            ...
```

### Orphan Recovery (on startup)
```python
def recover_orphans():
    # Recover missions stuck in active states longer than their timeout
    # Use timeout_sec from each mission, NOT a hardcoded value
    db.execute("""
        UPDATE zouzhe
        SET dispatched_at = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')
        WHERE state IN ('planning', 'executing')
          AND dispatched_at IS NOT NULL
          AND (julianday('now') - julianday(dispatched_at)) * 86400 > timeout_sec
    """)
    # Log recovery in liuzhuan
```

### Detecting "executing with no dispatcher" (after zhongshu plans)
```python
# Also check for: state=executing, dispatched_at=NULL, assigned_agent set from plan
# This means zhongshu finished planning, wrote the target agent, and we need to dispatch
rows = db.execute("""
    SELECT id, assigned_agent, timeout_sec FROM zouzhe
    WHERE state = 'executing' AND dispatched_at IS NULL AND assigned_agent IS NOT NULL
""").fetchall()
for row in rows:
    # Claim with optimistic lock and dispatch
    claimed = db.execute(
        "UPDATE zouzhe SET dispatched_at = strftime('%Y-%m-%dT%H:%M:%S','now'), "
        "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
        "WHERE id = ? AND dispatched_at IS NULL RETURNING id",
        (row["id"],)
    ).fetchone()
    if claimed:
        dispatch_agent(row["assigned_agent"], row["id"], row["timeout_sec"])
```

## chaoting CLI

Executable Python script. All output is JSON. Exit code 0 on success, 1 on error.

### Commands

**pull** — Agent pulls full task context
```bash
chaoting pull ZZ-20260308-001
```
Returns:
```json
{
    "ok": true,
    "zouzhe": {
        "id": "ZZ-20260308-001",
        "title": "重构风控模块",
        "description": "...",
        "state": "planning",
        "priority": "normal",
        "plan": null
    },
    "dianji": [
        {"key": "repo:tetration:enforce.c", "value": "...", "confidence": "fresh"}
    ],
    "qianche": ["拆任务不宜太细", "涉及DB改动必须有回滚方案"],
    "liuzhuan": [
        {"from": "dispatcher", "to": "zhongshu", "action": "dispatch", "remark": "..."}
    ]
}
```

**plan** — Zhongshu submits planning result, advances state to executing
```bash
chaoting plan ZZ-20260308-001 '{"steps":[...],"target_agent":"bingbu","repo_path":"/path/to/your/repo","target_files":["src/enforce.c"],"acceptance_criteria":"单测通过"}'
```
- Updates plan field, sets state=executing, sets assigned_agent from plan.target_agent
- Sets dispatched_at=NULL so dispatcher picks it up
- **CAS protection:** `WHERE state = 'planning'`

**progress** — Agent reports progress
```bash
chaoting progress ZZ-20260308-001 "已完成第一阶段"
```
- Inserts into zoubao table
- Updates zouzhe.updated_at (resets timeout clock in dispatched_at? No — dispatched_at stays, only updated_at changes)

**done** — Agent completes task
```bash
chaoting done ZZ-20260308-001 "PR #42 已提交" "风控模块重构完成，含单测"
```
- **CAS protection:** `UPDATE zouzhe SET state='done' WHERE id=? AND state='executing'`
- If affected_rows=0, task was already timed out or failed — return error, don't overwrite

**fail** — Agent reports failure
```bash
chaoting fail ZZ-20260308-001 "依赖包版本冲突无法解决"
```
- **CAS protection:** `UPDATE zouzhe SET state='failed' WHERE id=? AND state IN ('planning','executing')`

**context** — Update domain context
```bash
chaoting context bingbu "repo:tetration:enforce.c" "nftables enforcement, key fn: apply_rules()" --source ZZ-20260308-001
```

### CAS Protection on State Transitions (CRITICAL)
All state-changing commands MUST use `WHERE state = <expected>` to prevent race conditions between timeout detection and agent completion. If the UPDATE affects 0 rows, return `{"ok": false, "error": "state conflict"}`.

## Deployment

### systemd user service
```ini
# ~/.config/systemd/user/chaoting-dispatcher.service
[Unit]
Description=Chaoting Dispatcher
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${CHAOTING_DIR}/src/dispatcher.py
Restart=always
RestartSec=5
Environment=PATH=%h/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
```

### Installation
```bash
mkdir -p <CHAOTING_DIR>
# Copy files
python3 <CHAOTING_DIR>/init_db.py
# Make chaoting CLI available
ln -s <CHAOTING_DIR>/chaoting /usr/local/bin/chaoting
# or add to PATH
# Start dispatcher
systemctl --user enable --now chaoting-dispatcher
```

## File Structure
```
<CHAOTING_DIR>/
├── chaoting.db        # SQLite database (auto-created)
├── dispatcher.py      # Dispatcher daemon
├── chaoting           # CLI tool (executable, #!/usr/bin/env python3)
├── init_db.py         # DB schema initialization
├── SPEC.md            # This file
└── README.md          # Usage guide
```

## Deferred to v1.1
- 门下省 (menxia) Go/No-Go voting mechanism
- Dashboard UI (React)
- Flight Rules engine
- Agent fallback (bingbu → gongbu)
- Notification to user on timeout/failure (currently just writes to DB)
