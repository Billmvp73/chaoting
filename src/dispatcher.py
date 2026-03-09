#!/usr/bin/env python3
"""Chaoting Dispatcher — polls DB and dispatches agents."""

import gzip
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tarfile
import textwrap
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

CHAOTING_DIR = os.environ.get("CHAOTING_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(CHAOTING_DIR, "chaoting.db")
CHAOTING_CLI = os.path.join(CHAOTING_DIR, "src", "chaoting") if os.path.isfile(os.path.join(CHAOTING_DIR, "src", "chaoting")) else os.path.join(CHAOTING_DIR, "chaoting")

# Shared audit log module — also used by src/chaoting CLI
import sys as _sys
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in _sys.path:
    _sys.path.insert(0, _src_dir)
from chaoting_log import zouzhe_log, LOG_SEPARATOR  # noqa: E402
from chaoting_log import LOGS_DIR  # noqa: E402


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

# review_required levels → default 给事中 mapping
REVIEW_LEVEL_MAP = {
    0: [],                                                          # 免审
    1: ["jishi_tech"],                                              # 普通
    2: ["jishi_tech", "jishi_risk"],                                # 重要
    3: ["jishi_tech", "jishi_risk", "jishi_resource", "jishi_compliance"],  # 军国大事
}


def get_review_agents(zouzhe):
    """Resolve review agents: review_agents JSON override > review_required level."""
    agents_json = zouzhe["review_agents"]
    if agents_json:
        return json.loads(agents_json)
    level = zouzhe["review_required"] if zouzhe["review_required"] else 0
    return REVIEW_LEVEL_MAP.get(level, DEFAULT_REVIEW_AGENTS)

OPENCLAW_CLI = os.environ.get("OPENCLAW_CLI", "openclaw")


# ──────────────────────────────────────────────────────
# 审计日志系统 — 结构化奏折生命周期追踪
# ──────────────────────────────────────────────────────

_audit_logged: set = set()          # (zouzhe_id, event_label) — dedup for CLI-triggered events


def _wrap(text: str, width: int = 78, indent: str = "   ") -> str:
    """Wrap long text at width, indenting continuation lines."""
    if not text or len(text) <= width:
        return text
    return textwrap.fill(text, width=width, subsequent_indent=indent)


def _format_plan_content(plan_json_str: str) -> str:
    """Format plan JSON into sectioned, human-readable multi-line text."""
    if not plan_json_str:
        return "(无方案)"
    try:
        plan = json.loads(plan_json_str)
        sections = []

        # 【基本信息】
        info_lines = ["【基本信息】"]
        if plan.get("target_agent"):
            info_lines.append(f"• 目标部门：{plan['target_agent']}")
        if plan.get("repo_path"):
            info_lines.append(f"• 仓库：{plan['repo_path']}")
        if plan.get("target_files"):
            tf = plan["target_files"]
            files_str = ", ".join(tf) if isinstance(tf, list) else str(tf)
            info_lines.append(f"• 文件：{files_str}")
        if len(info_lines) > 1:
            sections.append("\n".join(info_lines))

        # 【执行步骤】
        steps = plan.get("steps") or []
        if steps:
            step_lines = [f"【执行步骤】（共 {len(steps)} 步）", ""]
            for i, step in enumerate(steps, 1):
                wrapped = _wrap(str(step), width=74, indent="   ")
                step_lines.append(f"{i}. {wrapped}")
            sections.append("\n".join(step_lines))

        # 【验收标准】
        ac = plan.get("acceptance_criteria")
        if ac:
            ac_lines = ["【验收标准】"]
            for criterion in str(ac).split("\n"):
                criterion = criterion.strip()
                if criterion:
                    ac_lines.append(f"• {_wrap(criterion, width=74, indent='  ')}")
            sections.append("\n".join(ac_lines))

        return "\n\n".join(sections) if sections else json.dumps(plan, ensure_ascii=False, indent=2)
    except Exception:
        return str(plan_json_str)[:2000]


def _format_votes_content(votes) -> str:
    """Format toupiao rows into human-readable vote summary."""
    lines = []
    for v in votes:
        jishi = v["jishi_id"] if hasattr(v, "__getitem__") else v.get("jishi_id", "?")
        vote_val = v["vote"] if hasattr(v, "__getitem__") else v.get("vote", "?")
        reason = (v["reason"] if hasattr(v, "__getitem__") else v.get("reason", "")) or ""
        symbol = "✅ GO" if vote_val == "go" else "❌ NOGO"
        lines.append(f"• {jishi}: {symbol}")
        if reason:
            wrapped_reason = _wrap(reason, width=74, indent="     ")
            lines.append(f"  REASON: {wrapped_reason}")
    return "\n".join(lines)


def _enforce_logs_limit(max_bytes: int = 500 * 1024 * 1024):
    """Delete oldest archives in logs/archive/ until total logs/ size < max_bytes."""
    try:
        archive_dir = os.path.join(LOGS_DIR, "archive")
        if not os.path.isdir(archive_dir):
            return

        total = sum(
            os.path.getsize(os.path.join(root, f))
            for root, _, files in os.walk(LOGS_DIR)
            for f in files
        )
        if total <= max_bytes:
            return

        archives = sorted(
            [os.path.join(archive_dir, f) for f in os.listdir(archive_dir) if f.endswith(".tar.gz")],
            key=os.path.getmtime,
        )
        for archive in archives:
            if total <= max_bytes:
                break
            sz = os.path.getsize(archive)
            os.remove(archive)
            total -= sz
            log.info("Deleted old archive %s (freed %d MB)", os.path.basename(archive), sz // (1024 * 1024))
    except Exception as e:
        log.warning("_enforce_logs_limit error: %s", e)


def _archive_old_logs_worker():
    """Background daemon: gzip-compress zouzhe log dirs older than 30 days."""
    try:
        archive_dir = os.path.join(LOGS_DIR, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        cutoff = time.time() - 30 * 86400

        if not os.path.isdir(LOGS_DIR):
            return

        for zid in os.listdir(LOGS_DIR):
            if zid == "archive":
                continue
            zid_path = os.path.join(LOGS_DIR, zid)
            if not os.path.isdir(zid_path):
                continue

            files = [os.path.join(zid_path, f) for f in os.listdir(zid_path) if os.path.isfile(os.path.join(zid_path, f))]
            if not files:
                continue
            newest_mtime = max(os.path.getmtime(f) for f in files)
            if newest_mtime >= cutoff:
                continue  # Still recent, skip

            # Close any open handlers for this zouzhe before archiving
            with _audit_lock:
                keys_to_remove = [k for k in _audit_loggers if k[0] == zid]
                for k in keys_to_remove:
                    try:
                        for h in _audit_loggers[k].handlers[:]:
                            h.close()
                            _audit_loggers[k].removeHandler(h)
                    except Exception:
                        pass
                    del _audit_loggers[k]

            tar_name = os.path.join(archive_dir, f"{zid}.tar.gz")
            tmp_name = tar_name + ".tmp"
            try:
                with tarfile.open(tmp_name, "w:gz") as tar:
                    tar.add(zid_path, arcname=zid)
                os.rename(tmp_name, tar_name)
                shutil.rmtree(zid_path)
                log.info("Archived logs for %s -> %s", zid, tar_name)
            except Exception as e:
                log.warning("Failed to archive %s: %s", zid, e)
                if os.path.exists(tmp_name):
                    try:
                        os.remove(tmp_name)
                    except Exception:
                        pass

        _enforce_logs_limit()
    except Exception as e:
        log.warning("_archive_old_logs_worker error: %s", e)


def archive_old_logs():
    """Spawn archive worker in a background daemon thread."""
    t = threading.Thread(target=_archive_old_logs_worker, daemon=True, name="archive-logs")
    t.start()


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


# ──────────────────────────────────────────────────────
# 通知系统 — 第一阶段：Discord 频道通知
# ──────────────────────────────────────────────────────

PRIORITY_EMOJI = {
    "urgent":   "🚨",
    "critical": "🚨",
    "high":     "⚡",
    "normal":   "📜",
}

EVENT_VERB = {
    "state_created":         "新建",
    "state_planning":        "规划中",
    "state_reviewing":       "审核中",
    "state_executing":       "执行中",
    "state_done":            "已完成 ✅",
    "state_failed":          "已失败 ❌",
    "state_timeout":         "已超时 ⏰",
    "review_approved":       "门下省准奏 ✅",
    "review_nogo":           "门下省封驳 🔴",
    "review_three_strikes":  "三驳失败 ⛔",
    "review_timeout":        "审核超时 ⏰",
    "assigned":              "已分配",
}


def _format_notification(zouzhe: dict, event_type: str, extra: str = "") -> str:
    """Format a notification body for Discord."""
    pid = zouzhe.get("id", "?")
    title = zouzhe.get("title", "?")
    priority = zouzhe.get("priority", "normal")
    pemoji = PRIORITY_EMOJI.get(priority, "📜")
    verb = EVENT_VERB.get(event_type, event_type)

    lines = [
        f"{pemoji} **朝廷通知 · {verb}**",
        f"",
        f"📜 `{pid}` — {title}",
    ]

    assigned = zouzhe.get("assigned_agent")
    if assigned:
        lines.append(f"👤 负责人：{assigned}")

    if event_type == "state_done":
        summary = zouzhe.get("summary") or ""
        if summary:
            lines.append(f"✍️ 摘要：{summary}")

    elif event_type in ("state_failed", "state_timeout"):
        error = zouzhe.get("error") or ""
        retry = zouzhe.get("retry_count") or 0
        max_r = zouzhe.get("max_retries") or 2
        if error:
            lines.append(f"💥 原因：{error}")
        lines.append(f"🔁 重试：{retry}/{max_r}")

    elif event_type == "review_three_strikes":
        revise = zouzhe.get("revise_count") or 0
        lines.append(f"🔄 封驳轮次：{revise}")
        lines.append("🏛️ 需要人工决断")

    elif event_type == "review_approved":
        lines.append("🎉 全票通过，进入执行阶段")

    elif event_type == "review_timeout":
        if extra:
            lines.append(f"👥 {extra}")

    if extra and event_type not in ("review_timeout",):
        lines.append(f"ℹ️ {extra}")

    lines.append(f"⚡ 优先级：{priority}")
    return "\n".join(lines)


def _send_discord_thread(thread_id: str, body: str) -> bool:
    """Send a message to a Discord Thread via openclaw CLI.

    Correct syntax: themachine message thread reply --channel discord -t THREAD_ID -m MSG
    """
    try:
        result = subprocess.run(
            [OPENCLAW_CLI, "message", "thread", "reply",
             "--channel", "discord", "-t", thread_id, "-m", body[:2000]],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.warning("Discord thread notify failed (rc=%d, thread=%s): %s",
                        result.returncode, thread_id, result.stderr[:200])
        return result.returncode == 0
    except Exception as e:
        log.warning("Discord thread notify exception (thread=%s): %s", thread_id, e)
        return False


def notify_enqueue(db, zouzhe_id: str, event_type: str, body: str,
                   channel: str = "discord_thread", recipient: str = None,
                   dedup_extra: str = ""):
    """Non-blocking: write notification to tongzhi queue.

    Uses INSERT OR IGNORE for deduplication via dedup_key UNIQUE constraint.
    Must be called within an active transaction; caller is responsible for commit.
    Exceptions are caught and logged — never raises.

    recipient is the Discord Thread ID. If not provided, looks up discord_thread_id
    from the zouzhe record. Notifications without a thread_id are silently skipped
    (no entry written to tongzhi).
    """
    # Resolve thread_id from zouzhe if not explicitly provided
    if recipient is None:
        try:
            row = db.execute(
                "SELECT discord_thread_id FROM zouzhe WHERE id = ?", (zouzhe_id,)
            ).fetchone()
            if row and row["discord_thread_id"]:
                recipient = row["discord_thread_id"]
        except Exception:
            pass

    # No thread_id — silently skip, no tongzhi entry
    if not recipient:
        log.debug("notify_enqueue: no discord_thread_id for %s/%s — skipping", zouzhe_id, event_type)
        return

    dedup_key = f"{zouzhe_id}:{event_type}:{channel}:{recipient or 'default'}"
    if dedup_extra:
        dedup_key = f"{dedup_key}:{dedup_extra}"
    try:
        db.execute(
            "INSERT OR IGNORE INTO tongzhi "
            "(zouzhe_id, event_type, channel, recipient, body, dedup_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (zouzhe_id, event_type, channel, recipient, body, dedup_key),
        )
    except Exception as e:
        log.warning("notify_enqueue failed for %s/%s: %s", zouzhe_id, event_type, e)


def notify_worker():
    """Poll tongzhi for pending notifications and send them. Called from main loop.

    All notifications are sent via _send_discord_thread().
    Entries without a valid recipient (thread_id) are skipped and marked 'skipped'.
    """
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM tongzhi WHERE state = 'pending' AND retry_count < max_retries "
            "ORDER BY created_at ASC LIMIT 20"
        ).fetchall()

        for row in rows:
            success = False
            try:
                thread_id = row["recipient"]
                if not thread_id:
                    # No thread_id — mark skipped, not an error
                    log.debug("No thread_id for tongzhi#%d — skipping", row["id"])
                    db.execute(
                        "UPDATE tongzhi SET state='skipped', "
                        "updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') WHERE id=?",
                        (row["id"],),
                    )
                    db.commit()
                    continue
                success = _send_discord_thread(thread_id, row["body"])
            except Exception as e:
                log.warning("notify_worker send error for tongzhi#%d: %s", row["id"], e)

            if success:
                db.execute(
                    "UPDATE tongzhi SET state='sent', "
                    "sent_at=strftime('%Y-%m-%dT%H:%M:%S','now'), "
                    "updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') WHERE id=?",
                    (row["id"],),
                )
                # Update last_thread_activity on the zouzhe record
                try:
                    db.execute(
                        "UPDATE zouzhe SET last_thread_activity = strftime('%Y-%m-%dT%H:%M:%S','now') "
                        "WHERE id = ?", (row["zouzhe_id"],)
                    )
                except Exception:
                    pass  # Column might not exist in older DBs; non-fatal
                log.info("Notification sent: tongzhi#%d %s/%s",
                         row["id"], row["zouzhe_id"], row["event_type"])
            else:
                new_count = (row["retry_count"] or 0) + 1
                new_state = "failed" if new_count >= (row["max_retries"] or 3) else "pending"
                db.execute(
                    "UPDATE tongzhi SET retry_count=?, state=?, "
                    "updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') WHERE id=?",
                    (new_count, new_state, row["id"]),
                )
                if new_state == "failed":
                    log.warning("Notification permanently failed: tongzhi#%d %s/%s",
                                row["id"], row["zouzhe_id"], row["event_type"])
            db.commit()

    except Exception as e:
        log.warning("notify_worker error: %s", e)
    finally:
        db.close()


def _check_new_done_failed(db):
    """Detect zouzhe in done/failed/timeout that lack notifications; enqueue them.

    Idempotent — dedup_key UNIQUE constraint prevents duplicate entries.
    Covers state changes made by CLI commands (cmd_done, cmd_fail) outside dispatcher.
    """
    for target_state in ("done", "failed", "timeout"):
        event_type = f"state_{target_state}"
        rows = db.execute(
            "SELECT z.* FROM zouzhe z "
            "WHERE z.state = ? "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM tongzhi t "
            "  WHERE t.zouzhe_id = z.id AND t.event_type = ?"
            ")",
            (target_state, event_type),
        ).fetchall()
        for row in rows:
            body = _format_notification(dict(row), event_type)
            notify_enqueue(db, row["id"], event_type, body)
            # Audit log for CLI-originated completions (dedup guard: avoid repeat on no thread_id)
            _event_label = {"done": "COMPLETED", "failed": "FAILED", "timeout": "TIMEOUT"}.get(target_state, target_state.upper())
            _audit_key = (row["id"], _event_label)
            if _audit_key not in _audit_logged:
                if target_state == "done":
                    _content = f"OUTPUT:\n{(row['output'] or '(无)')[:1000]}\n\nSUMMARY:\n{row['summary'] or '(无)'}"
                    _headline = f"✅ 执行完成 — {row['assigned_agent'] or '?'}"
                else:
                    _content = f"ERROR:\n{row['error'] or '(无)'}\n\nRETRY: {row['retry_count']}/{row['max_retries']}"
                    _headline = f"❌ 执行失败/超时 — {row['assigned_agent'] or '?'}"
                zouzhe_log(row["id"], row["assigned_agent"] or "dispatcher",
                           _event_label,
                           _headline,
                           content=_content,
                           actor=row["assigned_agent"] or "unknown")
                _audit_logged.add(_audit_key)
    db.commit()


def notify_silijian(zouzhe, message: str):
    """Notify silijian (司礼监) about events requiring attention."""
    msg = f"⚠️ 司礼监通知\n\n奏折: {zouzhe['id']}\n{message}"
    try:
        subprocess.run(
            [OPENCLAW_CLI, "agent", "--agent", "silijian",
             "-m", msg, "--timeout", "120"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )
    except Exception as e:
        log.error("Failed to notify silijian for %s: %s", zouzhe["id"], e)


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
    revise_count = zouzhe["revise_count"] or 0

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
    jishi_list = get_review_agents(zouzhe)

    for jishi_id in jishi_list:
        actual_agent = REVIEW_AGENT_MAP.get(jishi_id, jishi_id)
        role_desc = ROLE_DESCRIPTIONS.get(jishi_id, jishi_id)
        msg = format_review_message(zouzhe, jishi_id, role_desc)

        db.execute(
            "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
            "VALUES (?, 'dispatcher', ?, 'dispatch_review', ?)",
            (zouzhe["id"], actual_agent, f"reviewing dispatch to {jishi_id}"),
        )
        zouzhe_log(zouzhe["id"], "menxia", "DISPATCH",
                   f"📤 dispatcher -> {actual_agent}",
                   actor="dispatcher", remark=f"reviewing dispatch to {jishi_id}")
        dispatch_agent(actual_agent, zouzhe["id"], zouzhe["timeout_sec"], msg=msg)

    db.commit()
    log.info("Dispatched reviewers for %s: %s", zouzhe["id"], jishi_list)
    _revise_count = zouzhe["revise_count"] or 0
    if _revise_count == 0:
        _event = "PLAN_GENERATED"
        _headline = "📋 中书省方案已提交，转交门下省审核"
    else:
        _event = "PLAN_REVISED"
        _headline = f"📋 修改后方案（第 {_revise_count} 轮），转交门下省审核"
    zouzhe_log(zouzhe["id"], "zhongshu", _event, _headline,
               content=_format_plan_content(zouzhe["plan"]))


def _notify_state_change(zouzhe_id: str, event_type: str, extra: str = ""):
    """Helper: fetch zouzhe, format notification, enqueue in a short-lived DB connection."""
    try:
        db = get_db()
        row = db.execute("SELECT * FROM zouzhe WHERE id = ?", (zouzhe_id,)).fetchone()
        if row:
            body = _format_notification(dict(row), event_type, extra)
            notify_enqueue(db, zouzhe_id, event_type, body)
            db.commit()
        db.close()
    except Exception as e:
        log.warning("_notify_state_change failed for %s/%s: %s", zouzhe_id, event_type, e)


def check_votes(db, zouzhe):
    """Poll reviewing state, count votes, handle go/nogo/three-strikes."""
    jishi_list = get_review_agents(zouzhe)
    current_round = (zouzhe["revise_count"] or 0) + 1

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
        # Log individual votes
        for v in votes:
            zouzhe_log(zouzhe["id"], v["jishi_id"], "VOTE",
                       v["vote"].upper(),
                       jishi=v["jishi_id"], reason=(v["reason"] or ""))
        # Rich APPROVED block in menxia.log
        zouzhe_log(zouzhe["id"], "menxia", "APPROVED",
                   "✅ 门下省准奏，全票通过",
                   content=_format_votes_content(votes))
        zouzhe_log(zouzhe["id"], "menxia", "STATE",
                   "reviewing -> executing",
                   actor="menxia", remark="门下省准奏，全票通过")
        log.info("门下省准奏 %s，全票通过", zouzhe["id"])
        # 通知：审核通过
        _notify_state_change(zouzhe["id"], "review_approved")
    else:
        # Has nogo votes
        if (zouzhe["revise_count"] or 0) >= 2:
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
            # Log nogo votes + REJECTED block
            for v in votes:
                zouzhe_log(zouzhe["id"], v["jishi_id"], "VOTE",
                           v["vote"].upper(),
                           jishi=v["jishi_id"], reason=(v["reason"] or ""))
            zouzhe_log(zouzhe["id"], "menxia", "REJECTED",
                       "⛔ 三驳失败，呈御前裁决",
                       content=_format_votes_content(votes))
            zouzhe_log(zouzhe["id"], "menxia", "STATE",
                       "reviewing -> failed",
                       actor="menxia", remark="三驳失败，呈御前裁决")
            log.warning("三驳失败 %s，呈御前裁决", zouzhe["id"])
            notify_silijian(dict(zouzhe), "奏折已被封驳3次，请人工决断")
            # 通知：三驳失败
            _notify_state_change(zouzhe["id"], "review_three_strikes")
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
            # Log votes for this round
            for v in votes:
                zouzhe_log(zouzhe["id"], v["jishi_id"], "VOTE",
                           v["vote"].upper(),
                           jishi=v["jishi_id"], reason=(v["reason"] or ""))
            # Rich PLAN_REVISE_FEEDBACK block in zhongshu.log
            zouzhe_log(zouzhe["id"], "zhongshu", "PLAN_REVISE_FEEDBACK",
                       f"📥 收到门下省封驳意见（第 {current_round} 轮），计划需调整",
                       content=f"FEEDBACK_ROUND: {current_round}\n\n"
                               f"【投票详情】\n{_format_votes_content(votes)}\n\n"
                               f"ACTION: 修改计划后重新提交审核")
            zouzhe_log(zouzhe["id"], "menxia", "REVISE",
                       f"Plan archived to round {current_round}, entering revising",
                       actor="menxia", remark=f"封驳（第{current_round}次），退回中书省")
            log.info("封驳 %s（第%d次），退回中书省", zouzhe["id"], current_round)


def handle_review_timeout(db, zouzhe):
    """Handle reviewing state timeout: critical→failed, normal→auto-go."""
    jishi_list = get_review_agents(zouzhe)
    current_round = (zouzhe["revise_count"] or 0) + 1

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
        notify_silijian(dict(zouzhe), f"军国大事审核超时，{len(missing)} 名给事中未投票")
        _notify_state_change(zouzhe["id"], "review_timeout",
                             extra=f"军国大事超时，{len(missing)} 名给事中未投票")
    else:
        # Normal: auto-insert go votes for missing, notify silijian
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
        notify_silijian(dict(zouzhe), f"审核超时，{len(missing)} 名给事中默认准奏")
        _notify_state_change(zouzhe["id"], "review_timeout",
                             extra=f"{len(missing)} 名给事中默认准奏")
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
                    # Rich RECEIVED log for zhongshu (first time) or revising feedback loop
                    if current_state == "created":
                        _desc = (row["description"] or "")[:600]
                        _review_agents = row["review_agents"] or "default"
                        _review_lvl = row["review_required"] or 0
                        # silijian.log — records what was dispatched and why
                        zouzhe_log(row["id"], "silijian", "CREATED",
                                   "📜 奏折已创建，派发朝廷流程",
                                   content=f"【奏折信息】\n"
                                           f"• 奏折ID：{row['id']}\n"
                                           f"• 标题：{row['title']}\n"
                                           f"• 优先级：{row['priority']}\n"
                                           f"• 审核等级：{_review_lvl}\n"
                                           f"• 审核部门：{_review_agents}\n"
                                           f"• 超时设置：{row['timeout_sec']}s\n\n"
                                           f"【奏折描述】\n{_desc}")
                        # zhongshu.log — records arrival for planning
                        zouzhe_log(row["id"], "zhongshu", "RECEIVED",
                                   "📬 从 dispatcher 收到新奏折，开始制定方案",
                                   content=f"【基本信息】\n"
                                           f"• 奏折ID：{row['id']}\n"
                                           f"• 标题：{row['title']}\n"
                                           f"• 优先级：{row['priority']}\n"
                                           f"• 超时：{row['timeout_sec']}s\n\n"
                                           f"【任务描述】\n{_desc}")
                    zouzhe_log(row["id"], "dispatcher", "STATE",
                               f"{current_state} -> {next_state}",
                               actor="dispatcher", remark=f"dispatched to {agent_role}")
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
                zouzhe_log(row["id"], "dispatcher", "DISPATCH",
                           f"📤 派发给 {row['assigned_agent']} 执行",
                           content=f"TARGET_AGENT: {row['assigned_agent']}\n"
                                   f"TIMEOUT: {row['timeout_sec']}s",
                           actor="dispatcher", remark="executing -> agent dispatch")
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

        # 5. Detect done/failed/timeout from CLI commands and enqueue notifications
        _check_new_done_failed(db)
    finally:
        db.close()


def check_thread_activity_warning():
    """Warn in log when active zouzhe with discord_thread_id have no Thread activity for 15+ min.

    This detects cases where the CLI Thread push failed silently and the dispatcher's
    tongzhi fallback also hasn't fired yet. Called every 5 minutes from main loop.
    """
    db = get_db()
    try:
        rows = db.execute("""
            SELECT id, title, state, assigned_agent, discord_thread_id,
                   last_thread_activity, updated_at
            FROM zouzhe
            WHERE state IN ('planning', 'reviewing', 'executing')
              AND discord_thread_id IS NOT NULL
              AND (
                last_thread_activity IS NULL
                OR (julianday('now') - julianday(last_thread_activity)) * 1440 > 15
              )
        """).fetchall()
        for row in rows:
            last = row["last_thread_activity"] or "从未发送"
            log.warning(
                "Thread 活跃度告警 %s [%s] 超过 15 分钟无 Thread 消息 | assigned=%s | last_activity=%s",
                row["id"], row["state"], row["assigned_agent"] or "?", last,
            )
    except Exception as e:
        log.warning("check_thread_activity_warning error: %s", e)
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
                zouzhe_log(zid, "dispatcher", "TIMEOUT",
                           f"⏰ 超时，重试次数耗尽 — {row['assigned_agent'] or '?'}",
                           content=f"STATE: {row['state']}\n"
                                   f"TIMEOUT_SEC: {row['timeout_sec']}\n"
                                   f"RETRIES: {row['max_retries']}/{row['max_retries']} exhausted",
                           actor="dispatcher")
                log.warning("Timeout %s — max retries exhausted", zid)
                # 通知：执行超时
                _notify_state_change(zid, "state_timeout")

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
    last_archive_check = 0.0
    last_activity_check = 0.0
    log.info("Entering main loop (poll=%ds, timeout_check=%ds)", POLL_INTERVAL, TIMEOUT_CHECK_INTERVAL)

    while True:
        try:
            poll_and_dispatch()
            notify_worker()   # 发送队列中的待发通知

            now = time.time()
            if now - last_timeout_check >= TIMEOUT_CHECK_INTERVAL:
                check_timeouts()
                last_timeout_check = now

            if now - last_archive_check >= 3600:   # 每小时归档一次
                archive_old_logs()
                last_archive_check = now

            if now - last_activity_check >= 300:   # 每5分钟检查 Thread 活跃度
                check_thread_activity_warning()
                last_activity_check = now
        except Exception:
            log.exception("Error in main loop")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
