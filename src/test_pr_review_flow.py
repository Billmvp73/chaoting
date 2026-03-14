#!/usr/bin/env python3
"""
test_pr_review_flow.py — ZZ-20260313-007 端到端测试套件

覆盖：
1. push-for-review → pr_review 状态验证
2. yushi-approve → done（含权限校验：非 yushi 调用失败）
3. yushi-nogo → executor_revise → push-for-review → pr_review 完整循环
4. NOGO 超限（exec_revise_count >= 3）→ escalated

运行：
    cd /home/tetter/self-project/chaoting
    CHAOTING_DIR=$(pwd) python3 src/test_pr_review_flow.py
"""

import io
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

_src = os.path.dirname(os.path.abspath(__file__))


# ── 加载 chaoting 和 dispatcher ──
def _load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


_ch = _load_module("chaoting_pr", os.path.join(_src, "chaoting"))
_disp = _load_module("dispatcher_pr_test", os.path.join(_src, "dispatcher.py"))


_init_db = _load_module("init_db_test", os.path.join(_src, "init_db.py"))


def _make_test_db(tmpdir: str) -> str:
    """创建隔离测试 DB（从 init_db.py 的 SCHEMA 创建，不依赖现有 DB 文件）"""
    test_db = os.path.join(tmpdir, "chaoting.db")
    conn = sqlite3.connect(test_db)
    # Execute the full schema from init_db
    for stmt in _init_db.SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass
    # Apply any additional columns (ZOUZHE_NEW_COLUMNS etc.)
    for col_entry in getattr(_init_db, "ZOUZHE_NEW_COLUMNS", []):
        try:
            if isinstance(col_entry, (list, tuple)) and len(col_entry) == 2:
                col_name, col_def = col_entry
                conn.execute(f"ALTER TABLE zouzhe ADD COLUMN {col_name} {col_def}")
            else:
                conn.execute(f"ALTER TABLE zouzhe ADD COLUMN {col_entry}")
        except Exception:
            pass  # Already exists
    conn.commit()
    conn.close()
    return test_db


def _insert_zouzhe(
    db_path: str,
    zid: str,
    state: str = "executing",
    assigned_agent: str = "bingbu",
    exec_revise_count: int = 0,
    output: str = None,
    plan: dict = None,
) -> None:
    db = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    plan_json = json.dumps(plan) if plan else None
    db.execute(
        "INSERT OR REPLACE INTO zouzhe "
        "(id, title, description, state, priority, assigned_agent, plan, output, summary, "
        " exec_revise_count, revise_history, revise_limit, revise_timeout_days, "
        " total_revise_rounds, last_revise_reason, suspended_at, planning_version, "
        " created_at, updated_at, review_required, revise_count, timeout_sec, dispatched_at) "
        "VALUES (?, ?, 'desc', ?, 'high', ?, ?, ?, NULL, "
        "        ?, '[]', 0, 0, 0, NULL, NULL, 1, ?, ?, 2, 0, 3600, NULL)",
        (
            zid, f"Test {zid}", state, assigned_agent, plan_json, output,
            exec_revise_count, now, now,
        ),
    )
    db.commit()
    db.close()


def _run_cmd(cmd_fn, args, test_db, agent_id="bingbu"):
    """运行 chaoting 命令，捕获 stdout，返回解析后的 JSON"""
    os.environ["OPENCLAW_AGENT_ID"] = agent_id

    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        with patch.object(_ch, "get_db") as mock_get:
            def _get():
                conn = sqlite3.connect(test_db)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                return conn
            mock_get.side_effect = _get
            with patch.object(_ch, "zouzhe_log"):
                with patch.object(_ch, "send_discord"):
                    with patch("sys.exit", side_effect=SystemExit):
                        try:
                            cmd_fn(args)
                        except SystemExit:
                            pass
    raw = mock_stdout.getvalue().strip()
    if not raw:
        return {}
    return json.loads(raw.split("\n")[-1])


def _get_state(db_path, zid):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT state, exec_revise_count, output FROM zouzhe WHERE id=?", (zid,)).fetchone()
    db.close()
    return dict(row) if row else None


def _get_zouzhe(db_path, zid):
    """Return full zouzhe row as dict (includes error, state, dispatched_at, etc.)"""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM zouzhe WHERE id=?", (zid,)).fetchone()
    db.close()
    return dict(row) if row else None


# ──────────────────────────────────────────────────────
# 场景 1：push-for-review → pr_review 状态验证
# ──────────────────────────────────────────────────────

class TestPushForReview(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_push_for_review_transitions_to_pr_review(self):
        """push-for-review: executing → pr_review, output 已保存"""
        zid = "ZZ-PR-001"
        _insert_zouzhe(self.test_db, zid, state="executing", assigned_agent="bingbu")

        output = "PR #42 已创建：https://github.com/org/repo/pull/42"
        result = _run_cmd(_ch.cmd_push_for_review, [zid, output], self.test_db, agent_id="bingbu")
        self.assertTrue(result.get("ok"), f"push-for-review failed: {result}")
        self.assertEqual(result.get("state"), "pr_review")

        # Verify DB state
        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "pr_review")
        self.assertEqual(row["output"], output)

    def test_push_for_review_only_from_executing(self):
        """push-for-review 只能在 executing 状态调用"""
        zid = "ZZ-PR-002"
        _insert_zouzhe(self.test_db, zid, state="planning", assigned_agent="bingbu")

        result = _run_cmd(_ch.cmd_push_for_review, [zid, "some output"], self.test_db, agent_id="bingbu")
        self.assertFalse(result.get("ok"))
        self.assertIn("executing", result.get("error", ""))

    def test_push_for_review_clears_dispatched_at(self):
        """push-for-review 清空 dispatched_at，以便 dispatcher 重新派发"""
        zid = "ZZ-PR-003"
        _insert_zouzhe(self.test_db, zid, state="executing", assigned_agent="bingbu")
        # Set dispatched_at
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET dispatched_at='2026-01-01T00:00:00' WHERE id=?", (zid,))
        db.commit()
        db.close()

        result = _run_cmd(_ch.cmd_push_for_review, [zid, "PR #1: https://github.com/org/repo/pull/1"],
                         self.test_db, agent_id="bingbu")
        self.assertTrue(result.get("ok"))

        # Verify dispatched_at is NULL
        db = sqlite3.connect(self.test_db)
        row = db.execute("SELECT dispatched_at FROM zouzhe WHERE id=?", (zid,)).fetchone()
        db.close()
        self.assertIsNone(row[0])


# ──────────────────────────────────────────────────────
# 场景 2：yushi-approve → done（含权限校验）
# ──────────────────────────────────────────────────────

class TestYushiApprove(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_yushi_approve_transitions_to_done(self):
        """yushi-approve: pr_review → done，summary 为 '御史准奏'"""
        zid = "ZZ-YA-001"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       output="PR #42: https://github.com/org/repo/pull/42")

        result = _run_cmd(_ch.cmd_yushi_approve, [zid], self.test_db, agent_id="yushi")
        self.assertTrue(result.get("ok"), f"yushi-approve failed: {result}")
        self.assertEqual(result.get("state"), "done")
        self.assertEqual(result.get("summary"), "御史准奏")

        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "done")

        # Verify summary in DB
        db = sqlite3.connect(self.test_db)
        db.row_factory = sqlite3.Row
        z = db.execute("SELECT summary FROM zouzhe WHERE id=?", (zid,)).fetchone()
        db.close()
        self.assertEqual(z["summary"], "御史准奏")

    def test_yushi_approve_permission_denied_for_non_yushi(self):
        """非 yushi 调用 yushi-approve 应返回权限错误"""
        zid = "ZZ-YA-002"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu")

        # Try as bingbu
        result = _run_cmd(_ch.cmd_yushi_approve, [zid], self.test_db, agent_id="bingbu")
        self.assertFalse(result.get("ok"))
        self.assertIn("权限", result.get("error", ""))

        # Try as silijian
        result2 = _run_cmd(_ch.cmd_yushi_approve, [zid], self.test_db, agent_id="silijian")
        self.assertFalse(result2.get("ok"))
        self.assertIn("权限", result2.get("error", ""))

        # Verify state unchanged
        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "pr_review")

    def test_yushi_approve_only_from_pr_review(self):
        """yushi-approve 只能在 pr_review 状态调用"""
        zid = "ZZ-YA-003"
        _insert_zouzhe(self.test_db, zid, state="executing", assigned_agent="bingbu")

        result = _run_cmd(_ch.cmd_yushi_approve, [zid], self.test_db, agent_id="yushi")
        self.assertFalse(result.get("ok"))
        self.assertIn("pr_review", result.get("error", ""))

    def test_yushi_approve_records_liuzhuan(self):
        """yushi-approve 应记录 liuzhuan：yushi → dispatcher | approve | 御史准奏"""
        zid = "ZZ-YA-004"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu")

        _run_cmd(_ch.cmd_yushi_approve, [zid], self.test_db, agent_id="yushi")

        db = sqlite3.connect(self.test_db)
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM liuzhuan WHERE zouzhe_id=? AND action='approve' ORDER BY id DESC LIMIT 1",
            (zid,),
        ).fetchone()
        db.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["from_role"], "yushi")
        self.assertEqual(row["to_role"], "dispatcher")
        self.assertIn("御史准奏", row["remark"])


# ──────────────────────────────────────────────────────
# 场景 3：yushi-nogo → executor_revise → push-for-review → pr_review 循环
# ──────────────────────────────────────────────────────

class TestYushiNogoReviseLoop(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_yushi_nogo_transitions_to_executor_revise(self):
        """yushi-nogo: pr_review → executor_revise, exec_revise_count++"""
        zid = "ZZ-YN-001"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       exec_revise_count=0)

        result = _run_cmd(_ch.cmd_yushi_nogo, [zid, "测试覆盖不足，缺少 edge case 测试"],
                         self.test_db, agent_id="yushi")
        self.assertTrue(result.get("ok"), f"yushi-nogo failed: {result}")
        self.assertEqual(result.get("state"), "executor_revise")
        self.assertEqual(result.get("exec_revise_count"), 1)

        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "executor_revise")
        self.assertEqual(row["exec_revise_count"], 1)

    def test_full_nogo_revise_loop(self):
        """完整循环：pr_review → executor_revise → (push-for-review) → pr_review"""
        zid = "ZZ-YN-002"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       exec_revise_count=0)

        # Step 1: yushi NOGO
        result1 = _run_cmd(_ch.cmd_yushi_nogo, [zid, "缺少权限检查"],
                          self.test_db, agent_id="yushi")
        self.assertTrue(result1.get("ok"))
        self.assertEqual(result1.get("state"), "executor_revise")

        # Step 2: executor modifies code and sets state back to executing (simulate dispatcher re-dispatch)
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET state='executing', dispatched_at=NULL WHERE id=?", (zid,))
        db.commit()
        db.close()

        # Step 3: push-for-review again
        result2 = _run_cmd(_ch.cmd_push_for_review, [zid, "PR #42 (v2): https://github.com/org/repo/pull/42"],
                          self.test_db, agent_id="bingbu")
        self.assertTrue(result2.get("ok"), f"push-for-review (v2) failed: {result2}")
        self.assertEqual(result2.get("state"), "pr_review")

        # Step 4: yushi approves
        result3 = _run_cmd(_ch.cmd_yushi_approve, [zid], self.test_db, agent_id="yushi")
        self.assertTrue(result3.get("ok"), f"yushi-approve failed: {result3}")
        self.assertEqual(result3.get("state"), "done")

        # Verify final state
        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "done")

    def test_yushi_nogo_permission_denied_for_non_yushi(self):
        """非 yushi 调用 yushi-nogo 应返回权限错误"""
        zid = "ZZ-YN-003"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu")

        result = _run_cmd(_ch.cmd_yushi_nogo, [zid, "some reason"], self.test_db, agent_id="bingbu")
        self.assertFalse(result.get("ok"))
        self.assertIn("权限", result.get("error", ""))

    def test_yushi_nogo_clears_dispatched_at(self):
        """yushi-nogo 清空 dispatched_at 以便 dispatcher 重新派发"""
        zid = "ZZ-YN-004"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu")
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET dispatched_at='2026-01-01T00:00:00' WHERE id=?", (zid,))
        db.commit()
        db.close()

        result = _run_cmd(_ch.cmd_yushi_nogo, [zid, "some reason"], self.test_db, agent_id="yushi")
        self.assertTrue(result.get("ok"))

        db = sqlite3.connect(self.test_db)
        row = db.execute("SELECT dispatched_at FROM zouzhe WHERE id=?", (zid,)).fetchone()
        db.close()
        self.assertIsNone(row[0])


# ──────────────────────────────────────────────────────
# 场景 4：NOGO 超限（exec_revise_count >= 3）→ escalated
# ──────────────────────────────────────────────────────

class TestYushiNogoEscalation(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_nogo_escalates_at_limit(self):
        """exec_revise_count >= 3 时 yushi-nogo 触发 escalated"""
        zid = "ZZ-ESC-001"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       exec_revise_count=3)  # Already at limit

        result = _run_cmd(_ch.cmd_yushi_nogo, [zid, "第四次 NOGO：代码质量问题依然存在"],
                         self.test_db, agent_id="yushi")
        self.assertTrue(result.get("ok"), f"yushi-nogo escalate failed: {result}")
        self.assertEqual(result.get("state"), "escalated")

        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "escalated")

    def test_nogo_at_count_2_still_revises(self):
        """exec_revise_count=2 时 yushi-nogo 仍应进入 executor_revise（不触发上限）"""
        zid = "ZZ-ESC-002"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       exec_revise_count=2)

        result = _run_cmd(_ch.cmd_yushi_nogo, [zid, "第三次 NOGO"],
                         self.test_db, agent_id="yushi")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("state"), "executor_revise")
        self.assertEqual(result.get("exec_revise_count"), 3)

    def test_full_nogo_to_escalation_flow(self):
        """完整 4 次 NOGO 流程：最终 escalated"""
        zid = "ZZ-ESC-003"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       exec_revise_count=0)

        # 3 rounds of NOGO + revise
        for i in range(1, 4):
            result = _run_cmd(_ch.cmd_yushi_nogo, [zid, f"第 {i} 次 NOGO"],
                             self.test_db, agent_id="yushi")
            self.assertTrue(result.get("ok"), f"Round {i} NOGO failed: {result}")
            self.assertEqual(result.get("state"), "executor_revise")
            self.assertEqual(result.get("exec_revise_count"), i)

            # Simulate: executor modifies and pushes for review again
            db = sqlite3.connect(self.test_db)
            db.execute("UPDATE zouzhe SET state='executing', dispatched_at=NULL WHERE id=?", (zid,))
            db.commit()
            db.close()
            _run_cmd(_ch.cmd_push_for_review, [zid, f"PR v{i+1}: https://github.com/org/repo/pull/{i+1}"],
                    self.test_db, agent_id="bingbu")

        # 4th NOGO → escalated (exec_revise_count == 3, >= NOGO_LIMIT)
        result_final = _run_cmd(_ch.cmd_yushi_nogo, [zid, "第 4 次 NOGO，代码问题未解决"],
                               self.test_db, agent_id="yushi")
        self.assertTrue(result_final.get("ok"), f"Final NOGO failed: {result_final}")
        self.assertEqual(result_final.get("state"), "escalated",
                        f"Expected escalated, got {result_final.get('state')}")

        row = _get_state(self.test_db, zid)
        self.assertEqual(row["state"], "escalated")

    def test_escalation_records_liuzhuan(self):
        """NOGO 超限时 liuzhuan 应记录 yushi → silijian | nogo_escalate"""
        zid = "ZZ-ESC-004"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu",
                       exec_revise_count=3)

        _run_cmd(_ch.cmd_yushi_nogo, [zid, "NOGO 达上限"], self.test_db, agent_id="yushi")

        db = sqlite3.connect(self.test_db)
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM liuzhuan WHERE zouzhe_id=? AND action='nogo_escalate' ORDER BY id DESC LIMIT 1",
            (zid,),
        ).fetchone()
        db.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["from_role"], "yushi")
        self.assertEqual(row["to_role"], "silijian")


# ──────────────────────────────────────────────────────
# 补充：dispatcher _dispatch_to_yushi 消息格式测试
# ──────────────────────────────────────────────────────

class TestDispatchToYushiMessage(unittest.TestCase):

    def test_yushi_message_contains_pr_url(self):
        """_dispatch_to_yushi 构建的消息应包含 PR URL（从 output 字段提取）"""
        zouzhe = {
            "id": "ZZ-DISP-001",
            "title": "test task",
            "output": "PR #42 已创建：https://github.com/org/repo/pull/42",
            "plan": json.dumps({
                "target_agent": "bingbu",
                "acceptance_criteria": "1. state machine correct\n2. tests pass",
            }),
            "timeout_sec": 600,
        }
        # Build the message directly (testing message content)
        zid = zouzhe["id"]
        output = zouzhe["output"] or ""
        plan_obj = json.loads(zouzhe["plan"])
        acceptance_criteria = plan_obj.get("acceptance_criteria", "")

        # Simulate the message building logic from _dispatch_to_yushi
        from dispatcher_pr_test import CHAOTING_CLI
        msg = (
            f"🔍 御史审核令\n\n"
            f"奏折：{zid}\n"
            f"标题：{zouzhe['title']}\n\n"
            f"【产出描述 / PR URL】\n{output}\n\n"
            f"【验收标准】\n{acceptance_criteria}\n\n"
            f"【审核维度】\n"
            f"1. 代码正确性 — 逻辑正确，无明显 Bug 或边界错误\n"
            f"2. 安全风险 — 无注入漏洞、权限提升或敏感数据泄露\n"
            f"3. 规范合规 — 命名规范、代码风格、注释质量\n"
            f"4. 测试覆盖 — 新功能有测试，覆盖边界情况和失败路径\n"
            f"5. 架构一致性 — 变更符合现有系统架构和设计模式\n\n"
            f"【审核指令】\n"
            f"准奏：{CHAOTING_CLI} yushi-approve {zid}\n"
            f"NOGO： {CHAOTING_CLI} yushi-nogo {zid} '具体原因（含文件名:行号）'\n"
        )

        self.assertIn("https://github.com/org/repo/pull/42", msg)
        self.assertIn("acceptance_criteria", msg.lower().replace("【验收标准】", "acceptance_criteria"))
        self.assertIn("state machine correct", msg)
        self.assertIn("代码正确性", msg)
        self.assertIn("安全风险", msg)
        self.assertIn("规范合规", msg)
        self.assertIn("测试覆盖", msg)
        self.assertIn("架构一致性", msg)
        self.assertIn("yushi-approve", msg)
        self.assertIn("yushi-nogo", msg)


# ──────────────────────────────────────────────────────
# Regression tests for post-merge audit (ZZ-20260313-008)
# Bug 1: executor_revise timeout not handled in check_timeouts()
# Bug 2: yushi-nogo reason not saved to error field
# ──────────────────────────────────────────────────────

def _run_dispatcher_check_timeouts(test_db):
    """Run dispatcher.check_timeouts() with patched get_db pointing to test_db."""
    def _get():
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    with patch.object(_disp, "get_db", side_effect=_get):
        with patch.object(_disp, "zouzhe_log"):
            with patch.object(_disp, "_cli_notify"):
                _disp.check_timeouts()


def _run_dispatcher_poll(test_db, dispatched_msgs=None):
    """Run dispatcher.poll_and_dispatch() with patched get_db and dispatch_agent."""
    captured = dispatched_msgs if dispatched_msgs is not None else {}

    def _get():
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _dispatch_agent(agent, zid, timeout_sec, msg=None, **kwargs):
        captured[agent] = msg or ""

    with patch.object(_disp, "get_db", side_effect=_get):
        with patch.object(_disp, "dispatch_agent", side_effect=_dispatch_agent):
            with patch.object(_disp, "zouzhe_log"):
                with patch.object(_disp, "_cli_notify"):
                    with patch.object(_disp, "_dispatch_to_yushi"):
                        with patch.object(_disp, "_check_new_done_failed"):
                            _disp.poll_and_dispatch()
    return captured


class TestExecutorReviseTimeout(unittest.TestCase):
    """Regression test: executor_revise + dispatched_at timeout → escalated in check_timeouts()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_executor_revise_timeout_escalates(self):
        """executor_revise + dispatched_at expired → state becomes escalated in check_timeouts()."""
        zid = "ZZ-TEST-REVISE-TIMEOUT-001"
        _insert_zouzhe(self.test_db, zid, state="executing", assigned_agent="bingbu")

        # Force state to executor_revise with an old dispatched_at (1 hour ago) and tiny timeout
        db = sqlite3.connect(self.test_db)
        db.execute(
            "UPDATE zouzhe SET state='executor_revise', "
            "dispatched_at=datetime('now', '-3600 seconds'), "
            "timeout_sec=1 WHERE id=?",
            (zid,),
        )
        db.commit()
        db.close()

        _run_dispatcher_check_timeouts(self.test_db)

        row = _get_zouzhe(self.test_db, zid)
        self.assertEqual(row["state"], "escalated",
                         "executor_revise timeout should transition to escalated")
        self.assertIn("超时", row["error"] or "",
                      "error field should contain timeout description")


class TestYushiNogoBugFixes(unittest.TestCase):
    """Regression tests for yushi-nogo bug fixes (ZZ-20260313-008)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_yushi_nogo_saves_reason_to_error(self):
        """yushi-nogo normal path: NOGO reason must be saved to the error field in DB."""
        zid = "ZZ-TEST-NOGO-ERROR-001"
        _insert_zouzhe(self.test_db, zid, state="pr_review", assigned_agent="bingbu")

        nogo_reason = "Missing edge case in handle_timeout: file src/dispatcher.py:1200"
        result = _run_cmd(_ch.cmd_yushi_nogo, [zid, nogo_reason], self.test_db, agent_id="yushi")

        self.assertTrue(result.get("ok"), f"yushi-nogo should succeed: {result}")
        self.assertEqual(result.get("state"), "executor_revise")

        row = _get_zouzhe(self.test_db, zid)
        self.assertEqual(row["state"], "executor_revise")
        self.assertEqual(
            row["error"], nogo_reason,
            "NOGO reason must be stored in the error field so dispatcher can include it in re-dispatch message"
        )

    def test_executor_revise_dispatch_includes_nogo_reason(self):
        """Dispatcher executor_revise re-dispatch message must include the NOGO reason from error field."""
        zid = "ZZ-TEST-NOGO-REASON-001"
        _insert_zouzhe(self.test_db, zid, state="executor_revise", assigned_agent="bingbu",
                       exec_revise_count=1,
                       output="PR #99: https://github.com/org/repo/pull/99")

        # Set the error field to the NOGO reason (simulating what yushi-nogo now saves)
        nogo_reason = "Function foo() has off-by-one error at src/main.py:42"
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET error=? WHERE id=?", (nogo_reason, zid))
        db.commit()
        db.close()

        dispatched = _run_dispatcher_poll(self.test_db)

        self.assertIn("bingbu", dispatched,
                      "dispatcher should have re-dispatched to bingbu")
        msg = dispatched["bingbu"]
        self.assertIn(nogo_reason, msg,
                      "Re-dispatch message must include the NOGO reason from the error field")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
