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

# Load .env from CHAOTING_DIR (does not override existing env vars)
_dotenv_path = os.path.join(CHAOTING_DIR, ".env")
if os.path.isfile(_dotenv_path):
    with open(_dotenv_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                if _k.strip() not in os.environ:
                    os.environ[_k.strip()] = _v.strip()

# ── workspace 隔离支持（ZZ-20260310-016）──
# CHAOTING_WORKSPACE 设置后 DB/logs/sentinels 隔离到 {workspace}/.chaoting/
# Dispatcher gets CHAOTING_WORKSPACE from systemd Environment=
_WORKSPACE = os.environ.get("CHAOTING_WORKSPACE", "")
CHAOTING_DATA_DIR = os.path.join(_WORKSPACE, ".chaoting") if _WORKSPACE else CHAOTING_DIR

DB_PATH = os.environ.get("CHAOTING_DB_PATH", os.path.join(CHAOTING_DATA_DIR, "chaoting.db"))
CHAOTING_CLI = os.path.join(CHAOTING_DIR, "src", "chaoting") if os.path.isfile(os.path.join(CHAOTING_DIR, "src", "chaoting")) else os.path.join(CHAOTING_DIR, "chaoting")

# ── 门下省封驳上限（超过此次数后 escalate 至司礼监，而非 failed）──
# 皇上通过 CLI `chaoting revise` 下旨的次数不受此限制
GATE_REJECT_LIMIT = int(os.environ.get("CHAOTING_GATE_REJECT_LIMIT", "3"))

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

OPENCLAW_CLI = os.environ.get("OPENCLAW_CLI", "themachine")

# ── 每奏折独立 session（ZZ-20260311-003）──
# CHAOTING_ISOLATED_SESSIONS=1 时，每次 dispatch 前 reset agent 主 session，
# 确保每个奏折在全新 context 中执行（无跨任务 context 污染）
CHAOTING_ISOLATED_SESSIONS = os.environ.get("CHAOTING_ISOLATED_SESSIONS", "1") == "1"
# Gateway password 用于调用 sessions.reset API
# 优先读取 CHAOTING_GATEWAY_PASSWORD，否则从 themachine.json 中读取
GATEWAY_PASSWORD: str = os.environ.get("CHAOTING_GATEWAY_PASSWORD", "")
if not GATEWAY_PASSWORD:
    try:
        _tm_config_path = os.path.expanduser("~/.themachine/themachine.json")
        if os.path.isfile(_tm_config_path):
            with open(_tm_config_path) as _f:
                _tm = json.load(_f)
            GATEWAY_PASSWORD = _tm.get("gateway", {}).get("auth", {}).get("password", "")
    except Exception:
        pass


def _reset_agent_session(agent_id: str) -> str | None:
    """Reset agent's main session for per-task isolation.

    Calls 'gateway call sessions.reset' to create a fresh context for agent_id.
    This ensures each dispatched zouzhe runs in a clean session without
    cross-task context contamination.

    Returns the new sessionId (UUID) on success, or None on failure.
    Never raises — failure is logged as WARNING and dispatch proceeds normally.

    ZZ-20260311-003：每奏折独立 session 机制
    """
    if not GATEWAY_PASSWORD:
        log.warning("GATEWAY_PASSWORD not configured — skipping session reset for %s", agent_id)
        return None
    try:
        key = f"agent:{agent_id}:main"
        result = subprocess.run(
            [OPENCLAW_CLI, "gateway", "call", "sessions.reset",
             "--password", GATEWAY_PASSWORD,
             "--params", json.dumps({"key": key}),
             "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            new_uuid = data.get("entry", {}).get("sessionId", "")
            log.info("Session reset for %s: new UUID=%s", agent_id, new_uuid[:8] if new_uuid else "?")
            return new_uuid or None
        else:
            log.warning("sessions.reset failed for %s (rc=%d): %s",
                        agent_id, result.returncode, result.stderr[:200])
    except subprocess.TimeoutExpired:
        log.warning("sessions.reset timed out for %s", agent_id)
    except Exception as e:
        log.warning("sessions.reset error for %s: %s", agent_id, e)
    return None


# ──────────────────────────────────────────────────────
# 审计日志系统 — 结构化奏折生命周期追踪
# ──────────────────────────────────────────────────────


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


def mark_stale_dianji(stale_days: int = 30):
    """Mark dianji entries older than stale_days as confidence='stale'.

    Runs in a background thread. Safe to call hourly. Never raises.
    """
    def _worker():
        try:
            db = get_db()
            result = db.execute(
                "UPDATE dianji SET confidence = 'stale' "
                "WHERE confidence = 'fresh' "
                "AND julianday('now') - julianday(updated_at) > ?",
                (stale_days,),
            )
            updated = result.rowcount
            db.commit()
            db.close()
            if updated > 0:
                log.info("mark_stale_dianji: marked %d entries as stale (>%d days)", updated, stale_days)
        except Exception as e:
            log.warning("mark_stale_dianji failed: %s", e)

    t = threading.Thread(target=_worker, daemon=True, name="stale-dianji")
    t.start()


def get_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def _build_dianji_qianche_section(agent_id: str, zouzhe_id: str) -> str:
    """Query dianji (limit=5) and qianche (limit=3) for agent_id and return a formatted section.

    Returns empty string if nothing found. Truncates dianji values to 200 chars.
    """
    try:
        db = get_db()
        dianji_rows = db.execute(
            "SELECT context_key, context_value, confidence FROM dianji "
            "WHERE agent_role = ? ORDER BY updated_at DESC LIMIT 5",
            (agent_id,),
        ).fetchall()
        qianche_rows = db.execute(
            "SELECT lesson FROM qianche "
            "WHERE agent_role = ? "
            "ORDER BY id DESC LIMIT 3",
            (agent_id,),
        ).fetchall()
        db.close()

        parts = []
        if dianji_rows:
            lines = ["📚 典籍参考（该部门历史经验，最近 5 条）："]
            for r in dianji_rows:
                marker = "🟡" if r["confidence"] == "stale" else "🟢"
                val = (r["context_value"] or "")[:200]
                lines.append(f"  {marker} {r['context_key']}: {val}")
            parts.append("\n".join(lines))
        if qianche_rows:
            lines = ["📖 历史教训（最近 3 条）："]
            for r in qianche_rows:
                lesson = (r["lesson"] or "")[:200]
                lines.append(f"  ⚠️ {lesson}")
            parts.append("\n".join(lines))

        return ("\n\n" + "\n\n".join(parts)) if parts else ""
    except Exception as e:
        log.warning("_build_dianji_qianche_section failed for %s/%s: %s", agent_id, zouzhe_id, e)
        return ""


def dispatch_agent(agent_id: str, zouzhe_id: str, timeout_sec: int, msg: str = None):
    if msg is None:
        knowledge_section = _build_dianji_qianche_section(agent_id, zouzhe_id)
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
            f"{knowledge_section}"
        )

    def _run():
        try:
            # ── ZZ-20260311-003：每奏折独立 session ──
            # 在 dispatch 前 reset agent 的 main session，确保每个奏折在全新 context 中执行
            # 失败时降级为 persistent 模式（不阻塞 dispatch）
            if CHAOTING_ISOLATED_SESSIONS:
                new_session_id = _reset_agent_session(agent_id)
                if new_session_id:
                    log.info("Isolated session ready for %s/%s: %s...", agent_id, zouzhe_id, new_session_id[:8])
                else:
                    log.warning("Session reset failed for %s/%s — falling back to persistent session", agent_id, zouzhe_id)

            logfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"dispatch-{agent_id}-{zouzhe_id}.log")
            with open(logfile, 'w') as f:
                proc = subprocess.Popen(
                    [OPENCLAW_CLI, "agent", "--agent", agent_id,
                     "-m", msg, "--timeout", str(timeout_sec)],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                )
            log.info("Agent %s for %s started (cli_pid=%d)", agent_id, zouzhe_id, proc.pid)
            try:
                proc.wait(timeout=timeout_sec + 60)
            except subprocess.TimeoutExpired:
                log.warning("Agent %s for %s CLI timed out (cli_pid=%d), killing", agent_id, zouzhe_id, proc.pid)
                proc.kill()
                proc.wait()
            log.info("Agent %s for %s CLI exited with code %d (cli_pid=%d)", agent_id, zouzhe_id, proc.returncode, proc.pid)
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





def _cli_notify(zouzhe_id: str, body: str):
    """Send a Discord notification via `chaoting notify`. Non-blocking, never raises."""
    try:
        subprocess.run(
            [CHAOTING_CLI, "notify", zouzhe_id, body[:2000]],
            timeout=30,
            capture_output=True,
            check=False,
        )
    except Exception as e:
        log.warning("_cli_notify failed for %s: %s", zouzhe_id, e)




def _check_new_done_failed(db):
    """Notify silijian about newly done/failed/timeout zouzhe.

    Uses liuzhuan to dedup via INSERT OR IGNORE: a UNIQUE INDEX on
    (zouzhe_id, action, remark) prevents duplicate entries even across
    concurrent dispatchers or restarts.
    CLI handles Discord notifications directly.
    """
    for target_state in ('done', 'failed', 'timeout'):
        rows = db.execute(
            "SELECT z.* FROM zouzhe z "
            "WHERE z.state = ? "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM liuzhuan l "
            "  WHERE l.zouzhe_id = z.id AND l.action = 'silijian_notify' "
            "  AND l.remark = ?"
            ")",
            (target_state, target_state),
        ).fetchall()
        for row in rows:
            zid = row["id"]
            title = row["title"]
            agent = row["assigned_agent"] or "?"
            if target_state == "done":
                summary = (row["summary"] or "(无)")[:300]
                msg = f"✅ 奏折已完成\n\n奏折：{zid}\n标题：{title}\n执行者：{agent}\n摘要：{summary}"
            else:
                kind = "超时" if target_state == "timeout" else "失败"
                error = (row["error"] or "(未说明)")[:300]
                msg = f"❌ 奏折{kind}\n\n奏折：{zid}\n标题：{title}\n执行者：{agent}\n原因：{error}"
            try:
                # INSERT OR IGNORE: safe against duplicate rows even under concurrent dispatchers
                result = db.execute(
                    "INSERT OR IGNORE INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                    "VALUES (?, 'dispatcher', 'silijian', 'silijian_notify', ?)",
                    (row['id'], target_state),
                )
                db.commit()
                # Only send notification if this INSERT actually created a new row
                if result.rowcount > 0:
                    _cli_notify(zid, msg)
                else:
                    log.debug("_check_new_done_failed: dedup skip for %s/%s", zid, target_state)
            except Exception as e:
                log.warning('_check_new_done_failed failed for %s/%s: %s', row['id'], target_state, e)



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
    """Build the revising dispatch message for zhongshu.

    V0.4 修复（ZZ-20260310-013 RC-1）：
    - 路径 A（menxia 封驳）：从 plan_history 读取 jishi 意见
    - 路径 B（皇上/silijian exec_revise）：从 revise_history 读取返工原因（最高优先级）

    V0.4.1 修复（ZZ-20260310-029）：
    - 原 bug：只要曾经有 emperor_revise（exec_revise_count > 0），所有后续 revising
      （包括 jishi gate_reject 触发的）均走路径 B，导致 jishi 封驳意见完全不传达给中书省
    - 修复：增加 last_round_has_nogo 检查：若 plan_history[-1] 含 nogo 投票，
      说明本次触发是 gate_reject → 强制走路径 A（含 emperor 背景）
    - 配合 cmd_revise 的 plan_history = NULL 清空：确保 emperor_revise 时路径判断不被
      旧 nogo 数据干扰
    """
    # ── 路径 B 优先：检查 revise_history（皇上/silijian revise 原因）──
    revise_hist = []
    try:
        revise_hist = json.loads(zouzhe.get("revise_history") or "[]")
    except Exception:
        pass
    exec_revise_count = zouzhe.get("exec_revise_count") or 0

    # ── ZZ-20260310-029 fix：判断本次 revising 实际触发原因 ──
    # gate_reject 会将 nogo 投票 archive 到 plan_history[-1]
    # emperor_revise 会清空 plan_history（cmd_revise 修复配合）
    # 若 plan_history[-1] 有 nogo → 本次是 gate_reject → 必须走路径 A
    _plan_hist_raw = []
    try:
        _plan_hist_raw = json.loads(zouzhe.get("plan_history") or "[]")
    except Exception:
        pass
    _last_round_has_nogo = bool(_plan_hist_raw) and any(
        v.get("vote") == "nogo"
        for v in _plan_hist_raw[-1].get("votes", [])
    )

    if revise_hist and exec_revise_count > 0 and not _last_round_has_nogo:
        latest = revise_hist[-1]
        revise_reason = latest.get("reason", "(无原因)")
        revised_by = latest.get("revised_by", "silijian")
        revised_at = latest.get("revised_at", "")
        dup_sim = latest.get("dup_similarity", 0.0)

        # 包含上轮规划（如有）供参考
        plan_history = []
        try:
            plan_history = json.loads(zouzhe.get("plan_history") or "[]")
        except Exception:
            pass
        previous_plan_section = ""
        if plan_history:
            last_plan = plan_history[-1].get("plan")
            if last_plan:
                previous_plan_section = (
                    f"\n\n【上轮规划（已作废，供参考）】\n"
                    f"```json\n{json.dumps(last_plan, ensure_ascii=False, indent=2)[:800]}\n```"
                )

        dup_note = ""
        if dup_sim >= 0.85:
            dup_note = (
                f"\n\n⚠️ 注意：此次返工原因与上轮高度相似（相似度 {dup_sim:.0%}）。"
                f"请在新方案中提供实质性改进，而不是重复相同方向。"
            )

        return (
            f"⚠️ 【上旨返工（第 {exec_revise_count} 次）】\n"
            f"来自：{revised_by}  时间：{revised_at}\n\n"
            f"【皇上旨意（最高优先级，必须完整体现在新方案中）】\n"
            f"{revise_reason}\n\n"
            f"⚠️ 若旨意指定了新的执行部门（target_agent），必须在 plan JSON 中遵循。"
            f"不得沿用原方案的 target_agent。"
            f"{dup_note}"
            f"{previous_plan_section}\n\n"
            f"请制定新方案后提交:\n"
            f"  {CHAOTING_CLI} pull {zouzhe['id']}\n"
            f"  {CHAOTING_CLI} plan {zouzhe['id']} '{{new_plan_json}}'"
        )

    # ── 路径 A（jishi 封驳）── 包含 jishi 封驳意见；若有 emperor 背景则附加
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

    # ── ZZ-20260310-029：若有皇上旨意背景，附加在封驳消息末尾（不覆盖，作为上下文）──
    if revise_hist and exec_revise_count > 0:
        emperor_bg = revise_hist[-1].get("reason", "")[:300]
        parts.append(
            f"\n【历史背景：皇上已下旨 {exec_revise_count} 次（当前任务方向）】\n"
            f"{emperor_bg}\n"
            f"⚠️ 注意：以上是任务整体方向，但本次首要任务是修复上方封驳意见。"
        )

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
        _cli_notify(zouzhe["id"], f"✅ 门下省准奏\n\n📜 `{zouzhe['id']}` — {zouzhe['title']}\n🎉 全票通过，进入执行阶段")
    else:
        # Has nogo votes
        # ── 门下省封驳上限逻辑（ZZ-20260310-014 v2）──
        # revise_count 统计门下省封驳次数（0-indexed → 已封驳 N 次）
        # 当已封驳次数 >= GATE_REJECT_LIMIT-1 时（即本次是第 GATE_REJECT_LIMIT 次），
        # 不再回中书省，改为 escalate 至司礼监裁决
        # ⚠️ 注意：此限制仅针对门下省封驳（gate_reject）
        #    皇上通过 CLI `chaoting revise` 下旨的 exec_revise_count 不受此限制
        if (zouzhe["revise_count"] or 0) >= GATE_REJECT_LIMIT - 1:
            # 门下省封驳已达上限 → escalate 至司礼监，不再退回中书省
            escalated_msg = (
                f"门下省连续封驳 {GATE_REJECT_LIMIT} 次，已呈司礼监/皇上裁决\n"
                f"（如皇上有旨意，请使用 `chaoting revise {zouzhe['id']} <旨意>` 下旨，不受此限制）"
            )
            affected = db.execute(
                "UPDATE zouzhe SET state = 'escalated', "
                "error = ?, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE id = ? AND state = 'reviewing'",
                (escalated_msg, zouzhe["id"]),
            ).rowcount
            if affected == 0:
                return
            db.execute(
                "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
                "VALUES (?, 'menxia', 'silijian', 'escalate', ?)",
                (zouzhe["id"], f"门下省第 {GATE_REJECT_LIMIT} 次封驳，呈司礼监裁决"),
            )
            db.commit()
            # Log nogo votes + ESCALATED block
            for v in votes:
                zouzhe_log(zouzhe["id"], v["jishi_id"], "VOTE",
                           v["vote"].upper(),
                           jishi=v["jishi_id"], reason=(v["reason"] or ""))
            zouzhe_log(zouzhe["id"], "menxia", "GATE_REJECT_ESCALATED",
                       f"⚠️ 门下省封驳达上限（{GATE_REJECT_LIMIT}次），呈司礼监裁决",
                       content=_format_votes_content(votes))
            zouzhe_log(zouzhe["id"], "menxia", "STATE",
                       "reviewing -> escalated",
                       actor="menxia", remark=f"gate_reject × {GATE_REJECT_LIMIT} → escalate")
            log.warning("门下省封驳达上限 %s，escalate → 司礼监", zouzhe["id"])
            _cli_notify(zouzhe["id"],
                        f"⚠️ 门下省封驳达上限\n\n"
                        f"📜 `{zouzhe['id']}` — {zouzhe['title']}\n"
                        f"🏛️ 已连续封驳 {GATE_REJECT_LIMIT} 次，呈司礼监/皇上裁决\n"
                        f"💡 皇上可使用 `chaoting revise {zouzhe['id']} <旨意>` 直接下旨（不受封驳次数限制）")
        else:
            # 封驳未达上限 → archive 并退回中书省重新规划
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
                "VALUES (?, 'menxia', 'zhongshu', 'gate_reject', ?)",
                (zouzhe["id"], f"门下省封驳（第{current_round}次），退回中书省重新规划 ({current_round}/{GATE_REJECT_LIMIT})"),
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
        _cli_notify(zouzhe["id"], f"⏰ 审核超时\n\n📜 `{zouzhe['id']}` — {zouzhe['title']}\n👥 军国大事超时，{len(missing)} 名给事中未投票")
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
        _cli_notify(zouzhe["id"], f"⏰ 审核超时\n\n📜 `{zouzhe['id']}` — {zouzhe['title']}\n👥 {len(missing)} 名给事中默认准奏")
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

        # 2a. Detect planning with dispatched_at=NULL (retry after timeout)
        rows = db.execute(
            "SELECT id, assigned_agent, timeout_sec FROM zouzhe "
            "WHERE state = 'planning' AND dispatched_at IS NULL AND assigned_agent IS NOT NULL"
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
                    (row["id"], row["assigned_agent"], "planning retry dispatch"),
                )
                db.commit()
                log.info("Re-dispatching %s to %s (planning retry)", row["id"], row["assigned_agent"])
                dispatch_agent(row["assigned_agent"], row["id"], row["timeout_sec"])

        # 2b. Detect executing with dispatched_at=NULL (after zhongshu plans)
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
                _cli_notify(zid, f"⏰ 执行超时\n\n📜 `{zid}` — 重试次数耗尽\n👤 {row['assigned_agent'] or '?'}")

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


def _log_inflight_on_startup():
    """Log any in-flight zouzhe on startup (informational only).

    Gateway agent sessions survive dispatcher restarts, so we do NOT
    reset dispatched_at.  The existing check_timeouts() handles the
    case where an agent truly dies without reporting back.
    """
    db = get_db()
    try:
        rows = db.execute("""
            SELECT id, assigned_agent, state, dispatched_at FROM zouzhe
            WHERE state IN ('planning', 'executing', 'reviewing')
              AND dispatched_at IS NOT NULL
        """).fetchall()
        if rows:
            for row in rows:
                log.info("In-flight on startup: %s (agent=%s, state=%s, dispatched=%s)",
                         row["id"], row["assigned_agent"], row["state"], row["dispatched_at"])
        log.info("Startup: %d in-flight zouzhe (trusting gateway sessions)", len(rows))
    finally:
        db.close()


def main():
    log.info("Chaoting dispatcher starting")

    if not os.path.exists(DB_PATH):
        log.error("Database not found at %s — run init_db.py first", DB_PATH)
        return

    _log_inflight_on_startup()

    last_timeout_check = 0.0
    last_archive_check = 0.0
    log.info("Entering main loop (poll=%ds, timeout_check=%ds)", POLL_INTERVAL, TIMEOUT_CHECK_INTERVAL)

    while True:
        try:
            poll_and_dispatch()

            now = time.time()
            if now - last_timeout_check >= TIMEOUT_CHECK_INTERVAL:
                check_timeouts()
                last_timeout_check = now

            if now - last_archive_check >= 3600:   # 每小时归档一次
                archive_old_logs()
                mark_stale_dianji()              # P1: 标记过期典籍
                last_archive_check = now

        except Exception:
            log.exception("Error in main loop")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
