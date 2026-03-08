# 门下省 (Menxia) — Go/No-Go 审核机制 Spec v2

> 经多轮审核修订。所有 Critical/High 问题已修复。

## 概述

门下省是朝廷系统的审核层。中书省规划完成后，奏折不直接进入执行，而是先经门下省审议。门下省由多个"给事中"组成，每人从不同专业角度审核，投票决定准奏（Go）或封驳（No-Go）。

## 状态机变更

```
Created → Planning → Reviewing → Executing → Done/Failed/Timeout
                       ↓
                    Revising → Planning (重新规划，带封驳意见)
```

新增两个状态：
- **reviewing** — 门下省审议中，等待给事中投票
- **revising** — 被封驳，退回中书省修改

## Schema 变更

### zouzhe 表新增字段

```sql
ALTER TABLE zouzhe ADD COLUMN review_required INTEGER DEFAULT 0;
-- 注意：DEFAULT 0，避免影响存量数据
-- 新建奏折时由司礼监在代码层面设置 0 或 1

ALTER TABLE zouzhe ADD COLUMN review_agents TEXT;
-- JSON array: ["jishi_tech","jishi_risk"]
-- NULL 时使用 DEFAULT_REVIEW_AGENTS

ALTER TABLE zouzhe ADD COLUMN revise_count INTEGER DEFAULT 0;
-- 被封驳次数

ALTER TABLE zouzhe ADD COLUMN plan_history TEXT;
-- JSON array: 被封驳的历史 plan + 封驳意见存档
-- [{"round":1, "plan":{...}, "votes":[...]}]
```

### 新增表：投票记录

```sql
CREATE TABLE toupiao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    round       INTEGER DEFAULT 1,
    jishi_id    TEXT NOT NULL,       -- 给事中角色 ID（jishi_tech, jishi_risk 等）
    agent_id    TEXT NOT NULL,       -- 实际执行的 agent ID（jishi_tech, jishi_risk 等）
    vote        TEXT NOT NULL,       -- "go" 或 "nogo"
    reason      TEXT,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    FOREIGN KEY (zouzhe_id) REFERENCES zouzhe(id)
);

-- 防止并发重复投票（Critical fix #3）
CREATE UNIQUE INDEX idx_toupiao_unique ON toupiao(zouzhe_id, round, jishi_id);
CREATE INDEX idx_toupiao_zouzhe ON toupiao(zouzhe_id);
```

**关键：** UNIQUE 约束在 `(zouzhe_id, round, jishi_id)` 上，用 `INSERT OR IGNORE` 防止并发重复投票。

## 给事中角色 → Agent 映射

给事中是**角色**，实际由现有 agent 扮演：

```python
REVIEW_AGENT_MAP = {
    "jishi_tech": "jishi_tech",         # 独立 agent
    "jishi_risk": "jishi_risk",         # 独立 agent
    "jishi_resource": "jishi_resource", # 独立 agent
    "jishi_compliance": "jishi_compliance" # 独立 agent
}

ROLE_DESCRIPTIONS = {
    "jishi_tech": "技术给事中：审核技术可行性、架构合理性、依赖风险、实现路径",
    "jishi_risk": "风险给事中：审核回滚方案、数据安全、破坏性操作、副作用",
    "jishi_resource": "资源给事中：审核工时合理性、token 预算、Agent 可用性",
    "jishi_compliance": "合规给事中：审核安全合规、权限边界、敏感数据处理"
}

DEFAULT_REVIEW_AGENTS = ["jishi_tech", "jishi_risk"]
```

### 身份映射方案（Critical fix #1）

Dispatcher 派发时在消息里注入 `jishi_id`，agent 投票时显式传递：

```bash
# 给事中投票时必须指定角色
chaoting vote ZZ-20260308-001 go "方案可行" --as jishi_tech
chaoting vote ZZ-20260308-001 nogo "缺回滚方案" --as jishi_risk
```

toupiao 表同时记录 `jishi_id`（角色）和 `agent_id`（实际 agent）。check_votes 按 `jishi_id` 匹配，不按 `agent_id`。

## 审核规格

司礼监创建奏折时决定：

```python
# 代码层面，新建奏折时设置
if 小事:
    review_required = 0           # 跳过门下省
elif 普通:
    review_required = 1
    review_agents = '["jishi_tech"]'
elif 重要:
    review_required = 1
    review_agents = '["jishi_tech","jishi_risk"]'
elif 军国大事:
    review_required = 1
    review_agents = '["jishi_tech","jishi_risk","jishi_resource","jishi_compliance"]'
```

## Dispatcher 流程变更

### 状态转换表（完整）

```python
STATE_TRANSITIONS = {
    "created":   ("planning",  "zhongshu"),   # → 中书省规划
    "revising":  ("planning",  "zhongshu"),   # → 中书省重新规划（带封驳意见）
    # planning → reviewing/executing: 由 zhongshu 通过 chaoting plan 触发
    # reviewing → executing/revising: 由 dispatcher check_votes 触发
    # executing → done/failed: 由六部通过 chaoting done/fail 触发
}
```

### 中书省 plan 完成后（chaoting plan 命令内部）

```python
def cmd_plan(zouzhe_id, plan_json):
    zouzhe = db.execute("SELECT * FROM zouzhe WHERE id = ? AND state = 'planning'", ...).fetchone()
    
    if zouzhe["review_required"]:
        # 进入审议
        db.execute(
            "UPDATE zouzhe SET plan = ?, state = 'reviewing', "
            "dispatched_at = NULL, updated_at = ... "
            "WHERE id = ? AND state = 'planning' RETURNING id",
            (plan_json, zouzhe_id)
        )
    else:
        # 跳过审议，直接执行
        db.execute(
            "UPDATE zouzhe SET plan = ?, state = 'executing', "
            "dispatched_at = NULL, assigned_agent = target_agent, updated_at = ... "
            "WHERE id = ? AND state = 'planning' RETURNING id",
            (plan_json, zouzhe_id)
        )
```

### Dispatcher 检测 reviewing 状态 → 并行派发给事中

```python
def dispatch_reviewers(zouzhe):
    # 先用 CAS 抢锁，防止重复派发
    affected = db.execute(
        "UPDATE zouzhe SET dispatched_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
        "WHERE id = ? AND state = 'reviewing' AND dispatched_at IS NULL",
        (zouzhe["id"],)
    ).rowcount
    if affected == 0:
        return  # 已被派发
    
    agents_json = zouzhe["review_agents"]
    jishi_list = json.loads(agents_json) if agents_json else DEFAULT_REVIEW_AGENTS
    
    for jishi_id in jishi_list:
        actual_agent = REVIEW_AGENT_MAP[jishi_id]
        role_desc = ROLE_DESCRIPTIONS[jishi_id]
        
        msg = format_review_message(zouzhe, jishi_id, role_desc)
        dispatch_agent(actual_agent, zouzhe["id"], zouzhe["timeout_sec"])
```

### Dispatcher 轮询 check_votes（fix #5：明确用轮询）

```python
def poll_and_dispatch():
    # ... 现有逻辑 ...
    
    # 检查 reviewing 状态的奏折投票情况
    reviewing = db.execute(
        "SELECT * FROM zouzhe WHERE state = 'reviewing'"
    ).fetchall()
    
    for zouzhe in reviewing:
        check_votes(zouzhe)
```

### check_votes 逻辑（所有修复已整合）

```python
def check_votes(zouzhe):
    jishi_list = json.loads(zouzhe["review_agents"]) if zouzhe["review_agents"] else DEFAULT_REVIEW_AGENTS
    current_round = zouzhe["revise_count"] + 1
    
    votes = db.execute(
        "SELECT jishi_id, vote, reason FROM toupiao "
        "WHERE zouzhe_id = ? AND round = ?",
        (zouzhe["id"], current_round)
    ).fetchall()
    
    voted_jishi = {v["jishi_id"] for v in votes}
    
    if not voted_jishi.issuperset(set(jishi_list)):
        return  # 还有人没投，继续等
    
    # 全部投完
    nogo_votes = [v for v in votes if v["vote"] == "nogo"]
    
    if not nogo_votes:
        # 全部准奏 → 执行（CAS 保护，fix #6）
        affected = db.execute(
            "UPDATE zouzhe SET state = 'executing', dispatched_at = NULL, "
            "updated_at = ... WHERE id = ? AND state = 'reviewing'",
            (zouzhe["id"],)
        ).rowcount
        if affected == 0:
            return  # 已被其他进程处理
        log("门下省准奏，全票通过")
    else:
        # 有封驳
        if zouzhe["revise_count"] >= 2:
            # 朝规五：三驳呈御前（CAS 保护）
            affected = db.execute(
                "UPDATE zouzhe SET state = 'failed', "
                "error = '三驳失败，呈御前裁决', updated_at = ... "
                "WHERE id = ? AND state = 'reviewing'",
                (zouzhe["id"],)
            ).rowcount
            if affected == 0:
                return
            notify_capcom(zouzhe, "奏折已被封驳3次，请人工决断")
        else:
            # 存档旧 plan + 封驳意见（fix #7 + #11）
            archive_entry = {
                "round": current_round,
                "plan": json.loads(zouzhe["plan"]) if zouzhe["plan"] else None,
                "votes": [{"jishi": v["jishi_id"], "vote": v["vote"], "reason": v["reason"]} for v in votes]
            }
            history = json.loads(zouzhe["plan_history"]) if zouzhe["plan_history"] else []
            history.append(archive_entry)
            
            # 退回中书省（CAS 保护 + revise_count 写回 DB，fix #2）
            affected = db.execute(
                "UPDATE zouzhe SET state = 'revising', "
                "revise_count = revise_count + 1, "
                "plan = NULL, "  # 清空旧 plan 防幽灵执行（fix #7）
                "plan_history = ?, "
                "dispatched_at = NULL, updated_at = ... "
                "WHERE id = ? AND state = 'reviewing'",
                (json.dumps(history, ensure_ascii=False), zouzhe["id"])
            ).rowcount
            if affected == 0:
                return
            log(f"封驳（第{zouzhe['revise_count']+1}次），退回中书省")
```

### Dispatcher 检测 revising → 派发中书省（fix #4）

```python
# 在 STATE_TRANSITIONS 里已定义：
# "revising": ("planning", "zhongshu")
# 
# dispatcher poll 检测到 revising + dispatched_at=NULL → 派发 zhongshu
# 派发消息包含封驳意见（从 plan_history 读取最后一轮）
```

## 超时处理（fix #8 + #9）

```python
def handle_review_timeout(zouzhe):
    jishi_list = json.loads(zouzhe["review_agents"]) if zouzhe["review_agents"] else DEFAULT_REVIEW_AGENTS
    current_round = zouzhe["revise_count"] + 1
    
    voted = db.execute(
        "SELECT jishi_id FROM toupiao WHERE zouzhe_id = ? AND round = ?",
        (zouzhe["id"], current_round)
    ).fetchall()
    voted_set = {v["jishi_id"] for v in voted}
    
    missing = set(jishi_list) - voted_set
    
    if zouzhe["priority"] == "critical":
        # 军国大事：超时不准奏，标记失败
        db.execute(
            "UPDATE zouzhe SET state = 'failed', error = '审核超时，需人工介入' "
            "WHERE id = ? AND state = 'reviewing'",
            (zouzhe["id"],)
        )
        notify_capcom(zouzhe, f"军国大事审核超时，{len(missing)} 名给事中未投票")
    else:
        # 普通任务：超时视为准奏，但通知司礼监
        for jishi_id in missing:
            db.execute(
                "INSERT OR IGNORE INTO toupiao (zouzhe_id, round, jishi_id, agent_id, vote, reason) "
                "VALUES (?, ?, ?, 'system', 'go', '超时未投，默认准奏')",
                (zouzhe["id"], current_round, jishi_id)
            )
        notify_capcom(zouzhe, f"审核超时，{len(missing)} 名给事中默认准奏")
        # 下次 poll 时 check_votes 会检测到全部投完
```

## chaoting CLI 新增命令

### vote

```bash
chaoting vote ZZ-20260308-001 go "方案可行，依赖明确" --as jishi_tech
chaoting vote ZZ-20260308-001 nogo "缺少回滚方案" --as jishi_risk
```

实现要点：
- `--as` 参数必填，指定给事中角色
- 整个操作在 `BEGIN IMMEDIATE` 事务内
- 用 `INSERT OR IGNORE`（依赖 UNIQUE 约束）防重复
- 检查 `zouzhe.state = 'reviewing'`（CAS）
- `agent_id` 从 `OPENCLAW_AGENT_ID` 环境变量获取

```python
def cmd_vote(zouzhe_id, vote, reason, jishi_id):
    db.execute("BEGIN IMMEDIATE")
    
    zouzhe = db.execute(
        "SELECT id, revise_count FROM zouzhe WHERE id = ? AND state = 'reviewing'",
        (zouzhe_id,)
    ).fetchone()
    
    if not zouzhe:
        db.execute("ROLLBACK")
        return {"ok": False, "error": "zouzhe not in reviewing state"}
    
    current_round = zouzhe["revise_count"] + 1
    agent_id = os.environ.get("OPENCLAW_AGENT_ID", "unknown")
    
    # INSERT OR IGNORE — UNIQUE 约束防重复
    cursor = db.execute(
        "INSERT OR IGNORE INTO toupiao (zouzhe_id, round, jishi_id, agent_id, vote, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (zouzhe_id, current_round, jishi_id, agent_id, vote, reason)
    )
    
    if cursor.rowcount == 0:
        db.execute("ROLLBACK")
        return {"ok": False, "error": "already voted this round"}
    
    db.execute("COMMIT")
    return {"ok": True, "action": "vote", "vote": vote, "jishi_id": jishi_id}
```

## 给事中派发消息模板

```
🗳️ 门下省 · 审议令

奏折: {zouzhe_id}
标题: {title}
描述: {description}
优先级: {priority}

📋 中书省方案:
{plan JSON, formatted}

🔍 你的角色: {role_description}

投票（必须指定 --as 参数）:
  chaoting vote {zouzhe_id} go "准奏理由" --as {jishi_id}
  chaoting vote {zouzhe_id} nogo "封驳理由（请明确指出需要修改什么）" --as {jishi_id}
```

## 封驳后重新规划的消息模板

```
📜 奏折 {zouzhe_id} 被门下省封驳（第 {revise_count} 次）

原方案:
{plan_history[-1].plan, formatted}

封驳意见:
{for vote in plan_history[-1].votes where vote.vote == "nogo":}
- {vote.jishi} (封驳): {vote.reason}
{for vote in plan_history[-1].votes where vote.vote == "go":}
- {vote.jishi} (准奏): {vote.reason}

请修改方案后重新提交:
  chaoting pull {zouzhe_id}
  chaoting plan {zouzhe_id} '{new_plan_json}'
```

## 修复清单（对应审核编号）

| # | 问题 | 修复 | 状态 |
|---|------|------|------|
| 1 | 给事中身份映射 | vote 加 --as 参数，toupiao 存 jishi_id + agent_id，check_votes 按 jishi_id 匹配 | ✅ |
| 2 | revise_count 没写回 DB | UPDATE SET revise_count = revise_count + 1 在 SQL 里 | ✅ |
| 3 | toupiao 缺 UNIQUE | UNIQUE(zouzhe_id, round, jishi_id) + INSERT OR IGNORE | ✅ |
| 4 | revising→planning 缺逻辑 | STATE_TRANSITIONS 里加 revising → planning → zhongshu | ✅ |
| 5 | check_votes 触发时机 | 明确用 dispatcher 轮询，reviewing 状态每次 poll 都 check | ✅ |
| 6 | set_state 缺 CAS | 所有 UPDATE 加 WHERE state='reviewing'，检查 rowcount | ✅ |
| 7 | 旧 plan 幽灵执行 | 进入 revising 时 SET plan=NULL | ✅ |
| 8 | 军国大事超时 | priority=critical 时超时→failed+通知，普通→默认准奏 | ✅ |
| 9 | 超时无通知 | 所有超时准奏都 notify_capcom | ✅ |
| 10 | ALTER TABLE DEFAULT | DEFAULT 0，代码层面新建时设 1 | ✅ |
| 11 | 封驳消息缺原始 plan | plan_history 存档，封驳消息包含旧 plan + 意见 | ✅ |

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `init_db.py` | 添加 toupiao 表 + UNIQUE 约束 + zouzhe 新字段（review_required, review_agents, revise_count, plan_history） |
| `dispatcher.py` | 添加 reviewing/revising 状态处理、dispatch_reviewers、check_votes、handle_review_timeout、revising 派发带封驳意见 |
| `chaoting` | 添加 vote 命令（--as 参数、BEGIN IMMEDIATE、INSERT OR IGNORE） |
| `chaoting.db` | ALTER TABLE 迁移 |

## 不在本次范围

- Dashboard UI（投票面板）— v1.2
- 投票权重 — 暂不需要
- plan_version 追踪 — plan_history 已提供等效功能
