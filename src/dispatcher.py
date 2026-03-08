#!/usr/bin/env python3
"""Chaoting Dispatcher — polls DB and dispatches agents."""

import json
import logging
import os
import sqlite3
import subprocess
import threading
import time

CHAOTING_DIR = os.environ.get("CHAOTING_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(CHAOTING_DIR, "chaoting.db")
CHAOTING_CLI = os.path.join(CHAOTING_DIR, "src", "chaoting") if os.path.isfile(os.path.join(CHAOTING_DIR, "src", "chaoting")) else os.path.join(CHAOTING_DIR, "chaoting")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("chaoting-dispatcher")

STATE_TRANSITIONS = {
    "created":  ("planning", "zhongshu"),
    "revising": ("planning", "zhongshu"),
}

POLL_INTERVAL = 5
TIMEOUT_CHECK_INTERVAL = 30

REVIEW_AGENT_MAP = {
    "jishi_tech": "jishi_tech",
    "jishi_risk": "jishi_risk",
    "jishi_resource": "jishi_resource",
    "jishi_compliance": "jishi_compliance",
}

ROLE_DESCRIPTIONS = {
    "jishi_tech": "技术给事中：审核技术可行性、架构合理性、依赖风险、实现路径",
    "jishi_risk": "风险给事中：审核回滚方案、数据安全、破坏性操作、副作用",
    "jishi_resource": "资源给事中：审核工时合理性、token 预算、Agent 可用性",
    "jishi_compliance": "合规给事中：审核安全合规、权限边界、敏感数据处理",
}

DEFAULT_REVIEW_AGENTS = ["jishi_tech", "jishi_risk"]

OPENCLAW_CLI = os.environ.get("OPENCLAW_CLI", "openclaw")


def get_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def dispatch_agent(agent_id: str, zouzhe_id: str, timeout_sec: int, msg: str = None):
    if msg is None:
        msg = (
            f"\U0001f4dc 奏折 {zouzhe_id} 已派发给你。请立即执行以下步骤：\n\n"
            f"步骤一：接旨，运行这个命令查看任务详情：\n"
            f"{CHAOTING_CLI} pull {zouzhe_id}\n\n"
            f"步骤二：根据任务内容，制定执行方案并提交（这是必须完成的操作）：\n"
            f"{CHAOTING_CLI} plan {zouzhe_id} '<plan_json>'\n\n"
            f"其他可用命令：\n"
            f"奏报: {CHAOTING_CLI} progress {zouzhe_id} '进展'\n"
            f"完成: {CHAOTING_CLI} done {zouzhe_id} '产出' '摘要'\n"
            f"失败: {CHAOTING_CLI} fail {zouzhe_id} '原因'\n\n"
            f"⚠️ 你必须用 exec 工具运行上述命令。先 pull 查看任务，完成后用 done 或 fail 汇报。"
        )

    def _run():
        try:
            logfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"dispatch-{agent_id}-{zouzhe_id}.log")
            with open(logfile, 'w') as f:
                result = subprocess.run(
                    [OPENCLAW_CLI, "agent", "--agent", agent_id,
                     "-m", msg, "--timeout", str(timeout_sec)],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_sec + 60,
                )
                log.info("Agent %s for %s exited with code %d", agent_id, zouzhe_id, result.returncode)
        except Exception as e:
            log.error("Dispatch error for %s to %s: %s", zouzhe_id, agent_id, e)
            try:
                err_db = get_db()
                err_db.execute(
                    "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                    "VALUES (?, 'dispatcher', ?, 'dispatch_error', ?)",
                    (zouzhe_id, agent_id, str(e)),
                )
                err_db.commit()
                err_db.close()
            except Exception as db_err:
                log.error("Failed to log dispatch error: %s", db_err)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    log.info("Dispatched %s to agent %s (timeout=%ds)", zouzhe_id, agent_id, timeout_sec)


def notify_capcom(zouzhe, message: str):
    """Notify capcom (司礼监) about events requiring attention."""
    msg = f"⚠️ 司礼监通知\n\n奏折: {zouzhe['id']}\n{message}"
    try:
        subprocess.run(
            [OPENCLAW_CLI, "agent", "--agent", "capcom",
             "-m", msg, "--timeout", "120"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )
    except Exception as e:
        log.error("Failed to notify capcom for %s: %s", zouzhe["id"], e)


def format_review_message(zouzhe, jishi_id: str, role_desc: str) -> str:
    """Build the review dispatch message for a 给事中."""
    plan_text = zouzhe["plan"] or "(无方案)"
    try:
        plan_obj = json.loads(plan_text) if zouzhe["plan"] else None
        if plan_obj:
            plan_text = json.dumps(plan_obj, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        pass

    return (
        f"🗳️ 门下省 · 审议令\n\n"
        f"奏折: {zouzhe['id']}\n"
        f"标题: {zouzhe['title']}\n"
        f"描述: {zouzhe['description']}\n"
        f"优先级: {zouzhe['priority']}\n\n"
        f"📋 中书省方案:\n{plan_text}\n\n"
        f"🔍 你的角色: {role_desc}\n\n"
        f"投票（必须指定 --as 参数）:\n"
        f"  {CHAOTING_CLI} vote {zouzhe['id']} go \"准奏理由\" --as {jishi_id}\n"
        f"  {CHAOTING_CLI} vote {zouzhe['id']} nogo \"封驳理由（请明确指出需要修改什么）\" --as {jishi_id}\n\n"
        f"⚠️ 你必须用 exec 工具运行上面的 vote 命令来投票。审核后选择 go 或 nogo，然后执行对应的命令。"
    )


def format_revising_message(zouzhe) -> str:
    """Build the revising dispatch message for zhongshu, including nogo reasons."""
    history = json.loads(zouzhe["plan_history"]) if zouzhe["plan_history"] else []
    if not history:
        return (
            f"📜 奏折 {zouzhe['id']} 被门下省封驳\n\n"
            f"请修改方案后重新提交:\n"
            f"  {CHAOTING_CLI} pull {zouzhe['id']}\n"
            f"  {CHAOTING_CLI} plan {zouzhe['id']} '{{new_plan_json}}'"
        )

    last_round = history[-1]
    old_plan = last_round.get("plan")
    old_plan_text = json.dumps(old_plan, ensure_ascii=False, indent=2) if old_plan else "(无)"
    votes = last_round.get("votes", [])
    revise_count = zouzhe["revise_count"]

    nogo_lines = []
    go_lines = []
    for v in votes:
        if v["vote"] == "nogo":
            nogo_lines.append(f"- {v['jishi']} (封驳): {v.get('reason', '无理由')}")
        else:
            go_lines.append(f"- {v['jishi']} (准奏): {v.get('reason', '无理由')}")

    parts = [
        f"📜 奏折 {zouzhe['id']} 被门下省封驳（第 {revise_count} 次）\n",
        f"原方案:\n{old_plan_text}\n",
        "封驳意见:",
    ]
    parts.extend(nogo_lines)
    if go_lines:
        parts.append("")
        parts.extend(go_lines)
    parts.append(
        f"\n请修改方案后重新提交:\n"
        f"  {CHAOTING_CLI} pull {zouzhe['id']}\n"
        f"  {CHAOTING_CLI} plan {zouzhe['id']} '{{new_plan_json}}'"
    )
    return "\n".join(parts)


def dispatch_reviewers(db, zouzhe):
    """CAS lock + parallel dispatch to 给事中 agents."""
    affected = db.execute(
        "UPDATE zouzhe SET dispatched_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
        "WHERE id = ? AND state = 'reviewing' AND dispatched_at IS NULL",
        (zouzhe["id"],),
    ).rowcount
    if affected == 0:
        return  # Already dispatched
    db.commit()

    agents_json = zouzhe["review_agents"]
    jishi_list = json.loads(agents_json) if agents_json else DEFAULT_REVIEW_AGENTS

    for jishi_id in jishi_list:
        actual_agent = REVIEW_AGENT_MAP.get(jishi_id, jishi_id)
        role_desc = ROLE_DESCRIPTIONS.get(jishi_id, jishi_id)
        msg = format_review_message(zouzhe, jishi_id, role_desc)

        db.execute(
            "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
            "VALUES (?, 'dispatcher', ?, 'dispatch_review', ?)",
            (zouzhe["id"], actual_agent, f"reviewing dispatch to {jishi_id}"),
        )
        dispatch_agent(actual_agent, zouzhe["id"], zouzhe["timeout_sec"], msg=msg)

    db.commit()
    log.info("Dispatched reviewers for %s: %s", zouzhe["id"], jishi_list)


def check_votes(db, zouzhe):
    """Poll reviewing state, count votes, handle go/nogo/three-strikes."""
    jishi_list = json.loads(zouzhe["review_agents"]) if zouzhe["review_agents"] else DEFAULT_REVIEW_AGENTS
    current_round = zouzhe["revise_count"] + 1

    votes = db.execute(
        "SELECT jishi_id, vote, reason FROM toupiao "
        "WHERE zouzhe_id = ? AND round = ?",
        (zouzhe["id"], current_round),
    ).fetchall()

    voted_jishi = {v["jishi_id"] for v in votes}
    if not voted_jishi.issuperset(set(jishi_list)):
        return  # Still waiting for votes

    nogo_votes = [v for v in votes if v["vote"] == "nogo"]

    if not nogo_votes:
        # All go → executing (CAS)
        affected = db.execute(
            "UPDATE zouzhe SET state = 'executing', dispatched_at = NULL, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
            "WHERE id = ? AND state = 'reviewing'",
            (zouzhe["id"],),
        ).rowcount
        if affected == 0:
            return
        db.execute(
            "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
            "VALUES (?, 'menxia', 'dispatcher', 'approve', '门下省准奏，全票通过')",
            (zouzhe["id"],),
        )
        db.commit()
        log.info("门下省准奏 %s，全票通过", zouzhe["id"])
    else:
        # Has nogo votes
        if zouzhe["revise_count"] >= 2:
            # Three strikes → failed (CAS)
            affected = db.execute(
                "UPDATE zouzhe SET state = 'failed', "
                "error = '三驳失败，呈御前裁决', "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE id = ? AND state = 'reviewing'",
                (zouzhe["id"],),
            ).rowcount
            if affected == 0:
                return
            db.execute(
                "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                "VALUES (?, 'menxia', 'dispatcher', 'three_strikes', '三驳失败，呈御前裁决')",
                (zouzhe["id"],),
            )
            db.commit()
            log.warning("三驳失败 %s，呈御前裁决", zouzhe["id"])
            notify_capcom(dict(zouzhe), "奏折已被封驳3次，请人工决断")
        else:
            # Archive old plan + votes, enter revising
            archive_entry = {
                "round": current_round,
                "plan": json.loads(zouzhe["plan"]) if zouzhe["plan"] else None,
                "votes": [
                    {"jishi": v["jishi_id"], "vote": v["vote"], "reason": v["reason"]}
                    for v in votes
                ],
            }
            history = json.loads(zouzhe["plan_history"]) if zouzhe["plan_history"] else []
            history.append(archive_entry)

            # CAS: revise_count in SQL, plan=NULL
            affected = db.execute(
                "UPDATE zouzhe SET state = 'revising', "
                "revise_count = revise_count + 1, "
                "plan = NULL, "
                "plan_history = ?, "
                "dispatched_at = NULL, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE id = ? AND state = 'reviewing'",
                (json.dumps(history, ensure_ascii=False), zouzhe["id"]),
            ).rowcount
            if affected == 0:
                return
            db.execute(
                "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                "VALUES (?, 'menxia', 'zhongshu', 'reject', ?)",
                (zouzhe["id"], f"封驳（第{current_round}次），退回中书省"),
            )
            db.commit()
            log.info("封驳 %s（第%d次），退回中书省", zouzhe["id"], current_round)


def handle_review_timeout(db, zouzhe):
    """Handle reviewing state timeout: critical→failed, normal→auto-go."""
    jishi_list = json.loads(zouzhe["review_agents"]) if zouzhe["review_agents"] else DEFAULT_REVIEW_AGENTS
    current_round = zouzhe["revise_count"] + 1

    voted = db.execute(
        "SELECT jishi_id FROM toupiao WHERE zouzhe_id = ? AND round = ?",
        (zouzhe["id"], current_round),
    ).fetchall()
    voted_set = {v["jishi_id"] for v in voted}
    missing = set(jishi_list) - voted_set

    if not missing:
        return  # All voted, check_votes will handle

    if zouzhe["priority"] == "critical":
        # Military-grade: timeout → failed
        affected = db.execute(
            "UPDATE zouzhe SET state = 'failed', "
            "error = '审核超时，需人工介入', "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
            "WHERE id = ? AND state = 'reviewing'",
            (zouzhe["id"],),
        ).rowcount
        if affected == 0:
            return
        db.execute(
            "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
            "VALUES (?, 'menxia', 'dispatcher', 'review_timeout_critical', ?)",
            (zouzhe["id"], f"军国大事审核超时，{len(missing)} 名给事中未投票"),
        )
        db.commit()
        log.warning("军国大事审核超时 %s，标记失败", zouzhe["id"])
        notify_capcom(dict(zouzhe), f"军国大事审核超时，{len(missing)} 名给事中未投票")
    else:
        # Normal: auto-insert go votes for missing, notify capcom
        for jishi_id in missing:
            db.execute(
                "INSERT OR IGNORE INTO toupiao (zouzhe_id, round, jishi_id, agent_id, vote, reason) "
                "VALUES (?, ?, ?, 'system', 'go', '超时未投，默认准奏')",
                (zouzhe["id"], current_round, jishi_id),
            )
        db.execute(
            "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
            "VALUES (?, 'menxia', 'dispatcher', 'review_timeout_auto_go', ?)",
            (zouzhe["id"], f"审核超时，{len(missing)} 名给事中默认准奏"),
        )
        db.commit()
        log.info("审核超时 %s，%d 名给事中默认准奏", zouzhe["id"], len(missing))
        notify_capcom(dict(zouzhe), f"审核超时，{len(missing)} 名给事中默认准奏")
        # Next poll cycle check_votes will see all votes complete


def poll_and_dispatch():
    db = get_db()
    try:
        # 1. Handle STATE_TRANSITIONS: created → planning, revising → planning
        for current_state, (next_state, agent_role) in STATE_TRANSITIONS.items():
            rows = db.execute(
                "SELECT * FROM zouzhe WHERE state = ? AND dispatched_at IS NULL",
                (current_state,),
            ).fetchall()

            for row in rows:
                cursor = db.execute(
                    "UPDATE zouzhe SET state = ?, dispatched_at = strftime('%Y-%m-%dT%H:%M:%S','now'), "
                    "assigned_agent = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                    "WHERE state = ? AND dispatched_at IS NULL AND id = ? RETURNING id",
                    (next_state, agent_role, current_state, row["id"]),
                )
                claimed = cursor.fetchone()
                if claimed:
                    db.commit()
                    db.execute(
                        "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                        "VALUES (?, 'dispatcher', ?, 'dispatch', ?)",
                        (row["id"], agent_role, f"{current_state} -> {next_state}"),
                    )
                    db.commit()
                    # For revising → planning, include nogo reasons in the message
                    custom_msg = None
                    if current_state == "revising":
                        custom_msg = format_revising_message(dict(row))
                    dispatch_agent(agent_role, row["id"], row["timeout_sec"], msg=custom_msg)

        # 2. Detect executing with dispatched_at=NULL (after zhongshu plans)
        rows = db.execute(
            "SELECT id, assigned_agent, timeout_sec FROM zouzhe "
            "WHERE state = 'executing' AND dispatched_at IS NULL AND assigned_agent IS NOT NULL"
        ).fetchall()

        for row in rows:
            cursor = db.execute(
                "UPDATE zouzhe SET dispatched_at = strftime('%Y-%m-%dT%H:%M:%S','now'), "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE id = ? AND dispatched_at IS NULL RETURNING id",
                (row["id"],),
            )
            claimed = cursor.fetchone()
            if claimed:
                db.commit()
                db.execute(
                    "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                    "VALUES (?, 'dispatcher', ?, 'dispatch', ?)",
                    (row["id"], row["assigned_agent"], "executing -> agent dispatch"),
                )
                db.commit()
                dispatch_agent(row["assigned_agent"], row["id"], row["timeout_sec"])

        # 3. Detect reviewing + dispatched_at IS NULL → dispatch reviewers
        reviewing_undispatched = db.execute(
            "SELECT * FROM zouzhe WHERE state = 'reviewing' AND dispatched_at IS NULL"
        ).fetchall()
        for row in reviewing_undispatched:
            dispatch_reviewers(db, row)

        # 4. Check votes for all reviewing zouzhe
        reviewing_all = db.execute(
            "SELECT * FROM zouzhe WHERE state = 'reviewing'"
        ).fetchall()
        for row in reviewing_all:
            check_votes(db, row)
    finally:
        db.close()


def check_timeouts():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT id, state, assigned_agent, dispatched_at, retry_count, max_retries, timeout_sec
            FROM zouzhe
            WHERE state IN ('planning', 'executing')
              AND dispatched_at IS NOT NULL
              AND (julianday('now') - julianday(dispatched_at)) * 86400 > timeout_sec
        """).fetchall()

        for row in rows:
            zid = row["id"]
            if row["retry_count"] < row["max_retries"]:
                db.execute(
                    "UPDATE zouzhe SET dispatched_at = NULL, "
                    "retry_count = retry_count + 1, "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                    "WHERE id = ?",
                    (zid,),
                )
                db.execute(
                    "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                    "VALUES (?, 'dispatcher', ?, 'retry', ?)",
                    (zid, row["assigned_agent"],
                     f"timeout after {row['timeout_sec']}s, retry {row['retry_count'] + 1}/{row['max_retries']}"),
                )
                db.commit()
                log.info("Retry %s (attempt %d/%d)", zid, row["retry_count"] + 1, row["max_retries"])
            else:
                db.execute(
                    "UPDATE zouzhe SET state = 'timeout', "
                    "error = 'max retries exhausted', "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                    "WHERE id = ? AND state = ?",
                    (zid, row["state"]),
                )
                db.execute(
                    "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                    "VALUES (?, 'dispatcher', ?, 'timeout', ?)",
                    (zid, row["assigned_agent"],
                     f"max retries ({row['max_retries']}) exhausted after {row['timeout_sec']}s timeout"),
                )
                db.commit()
                log.warning("Timeout %s — max retries exhausted", zid)

        # Handle reviewing state timeouts
        reviewing_rows = db.execute("""
            SELECT * FROM zouzhe
            WHERE state = 'reviewing'
              AND dispatched_at IS NOT NULL
              AND (julianday('now') - julianday(dispatched_at)) * 86400 > timeout_sec
        """).fetchall()
        for row in reviewing_rows:
            handle_review_timeout(db, row)
    finally:
        db.close()


def recover_orphans():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT id, assigned_agent, timeout_sec FROM zouzhe
            WHERE state IN ('planning', 'executing')
              AND dispatched_at IS NOT NULL
              AND (julianday('now') - julianday(dispatched_at)) * 86400 > timeout_sec
        """).fetchall()

        if not rows:
            log.info("No orphans to recover")
            return

        for row in rows:
            db.execute(
                "UPDATE zouzhe SET dispatched_at = NULL, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE id = ?",
                (row["id"],),
            )
            db.execute(
                "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                "VALUES (?, 'dispatcher', ?, 'recover', ?)",
                (row["id"], row["assigned_agent"], "orphan recovery on startup"),
            )
            log.info("Recovered orphan %s (was assigned to %s)", row["id"], row["assigned_agent"])

        db.commit()
    finally:
        db.close()


def main():
    log.info("Chaoting dispatcher starting")

    if not os.path.exists(DB_PATH):
        log.error("Database not found at %s — run init_db.py first", DB_PATH)
        return

    recover_orphans()

    last_timeout_check = 0.0
    log.info("Entering main loop (poll=%ds, timeout_check=%ds)", POLL_INTERVAL, TIMEOUT_CHECK_INTERVAL)

    while True:
        try:
            poll_and_dispatch()

            now = time.time()
            if now - last_timeout_check >= TIMEOUT_CHECK_INTERVAL:
                check_timeouts()
                last_timeout_check = now
        except Exception:
            log.exception("Error in main loop")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
