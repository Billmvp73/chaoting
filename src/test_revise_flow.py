#!/usr/bin/env python3
"""
test_revise_flow.py — ZZ-20260310-015 回归测试套件

覆盖：
- planning_version 锁定机制
- revise_reason 在 prompt 中可见（dispatcher 路径 A/B）
- chaoting pull 返回完整返工上下文
- 3+ 轮 revise 回归测试
- 旧版 plan 被拒绝（planning_version 不匹配）
- 正确版本 plan 被接受

运行：
    cd /home/tetter/self-project/chaoting
    CHAOTING_DIR=$(pwd) python3 src/test_revise_flow.py
"""

import json
import os
import sys
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import io
import importlib.machinery
import importlib.util

_src = os.path.dirname(os.path.abspath(__file__))

# ── 加载 chaoting 和 dispatcher ──
def _load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod

_ch = _load_module("chaoting", os.path.join(_src, "chaoting"))
_disp = _load_module("dispatcher_test_mod", os.path.join(_src, "dispatcher.py"))


def _make_test_db(tmpdir: str) -> str:
    """创建隔离测试 DB（仅 schema，无数据）"""
    chaoting_dir = os.environ.get("CHAOTING_DIR", os.path.dirname(_src))
    src_db = os.path.join(chaoting_dir, "chaoting.db")
    test_db = os.path.join(tmpdir, "chaoting.db")
    src_conn = sqlite3.connect(src_db)
    dst_conn = sqlite3.connect(test_db)
    for line in src_conn.iterdump():
        if "INSERT INTO" not in line:
            try:
                dst_conn.execute(line)
            except Exception:
                pass
    dst_conn.commit()
    src_conn.close()
    dst_conn.close()
    return test_db


def _insert_zouzhe(db_path: str, zid: str, state: str = "done",
                   exec_revise_count: int = 0,
                   planning_version: int = 1,
                   revise_history: list = None,
                   output: str = "x") -> None:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    db.execute(
        "INSERT OR REPLACE INTO zouzhe "
        "(id, title, description, state, priority, assigned_agent, plan, output, summary, "
        " exec_revise_count, revise_history, revise_limit, revise_timeout_days, "
        " total_revise_rounds, last_revise_reason, suspended_at, planning_version, "
        " created_at, updated_at, review_required, revise_count, timeout_sec) "
        "VALUES (?, ?, 'desc', ?, 'high', 'gongbu', NULL, ?, NULL, "
        "        ?, ?, 0, 0, 0, NULL, NULL, ?, ?, ?, 2, 0, 3600)",
        (
            zid, f"Test {zid}", state, output,
            exec_revise_count,
            json.dumps(revise_history or []),
            planning_version,
            now, now,
        ),
    )
    db.commit()
    db.close()


def _run_cmd(cmd_fn, args, test_db):
    """运行 chaoting 命令，捕获 stdout，返回解析后的 JSON"""
    os.environ["OPENCLAW_AGENT_ID"] = "silijian"

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


# ──────────────────────────────────────────────────────
# 测试 1：planning_version 锁定
# ──────────────────────────────────────────────────────

class TestPlanningVersionLock(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def _set_planning_state(self, zid: str, planning_version: int):
        """把奏折设为 planning 状态，设置指定版本"""
        db = sqlite3.connect(self.test_db)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "INSERT OR REPLACE INTO zouzhe "
            "(id, title, description, state, priority, assigned_agent, plan, output, "
            " exec_revise_count, revise_history, revise_limit, revise_timeout_days, "
            " total_revise_rounds, last_revise_reason, suspended_at, planning_version, "
            " created_at, updated_at, review_required, revise_count, timeout_sec) "
            "VALUES (?, 'test', 'desc', 'planning', 'high', 'gongbu', NULL, NULL, "
            "        0, '[]', 0, 0, 0, NULL, NULL, ?, ?, ?, 0, 0, 3600)",
            (zid, planning_version, now, now),
        )
        db.commit()
        db.close()

    def test_stale_version_rejected(self):
        """旧版规划（planning_version 不匹配）应被拒绝"""
        zid = "ZZ-PV-STALE"
        self._set_planning_state(zid, planning_version=3)

        # 提交版本 1（已过时，DB 是 3）
        plan = json.dumps({
            "target_agent": "bingbu",
            "steps": ["step1"],
            "planning_version": 1,
        })
        result = _run_cmd(_ch.cmd_plan, [zid, plan], self.test_db)
        self.assertFalse(result.get("ok"), f"Should reject stale version: {result}")
        self.assertIn("不匹配", result.get("error", ""))
        self.assertEqual(result.get("plan_version_required"), 3)

    def test_correct_version_accepted(self):
        """正确版本号的规划应被接受"""
        zid = "ZZ-PV-OK"
        self._set_planning_state(zid, planning_version=2)

        plan = json.dumps({
            "target_agent": "bingbu",
            "steps": ["step1"],
            "planning_version": 2,
        })
        result = _run_cmd(_ch.cmd_plan, [zid, plan], self.test_db)
        self.assertTrue(result.get("ok"), f"Should accept correct version: {result}")

    def test_no_version_in_plan_accepted(self):
        """计划中没有 planning_version 字段时，不校验（向后兼容）"""
        zid = "ZZ-PV-NOVERSION"
        self._set_planning_state(zid, planning_version=5)

        plan = json.dumps({
            "target_agent": "gongbu",
            "steps": ["step1"],
            # 没有 planning_version 字段
        })
        result = _run_cmd(_ch.cmd_plan, [zid, plan], self.test_db)
        self.assertTrue(result.get("ok"), f"Should accept plan without version (backward compat): {result}")

    def test_revise_increments_planning_version(self):
        """每次 revise 后 planning_version 应 +1"""
        zid = "ZZ-PV-INCR"
        _insert_zouzhe(self.test_db, zid, state="done", exec_revise_count=0, planning_version=1)

        result = _run_cmd(_ch.cmd_revise, [zid, "First revise"], self.test_db)
        self.assertTrue(result.get("ok"), f"revise failed: {result}")
        self.assertEqual(result.get("planning_version"), 2)

        # 再次 revise（需要先设回 done）
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET state='done', output='x' WHERE id=?", (zid,))
        db.commit()
        db.close()

        result2 = _run_cmd(_ch.cmd_revise, [zid, "Second revise"], self.test_db)
        self.assertTrue(result2.get("ok"), f"Second revise failed: {result2}")
        self.assertEqual(result2.get("planning_version"), 3)

    def test_pull_returns_planning_version(self):
        """chaoting pull 返回 planning_version"""
        zid = "ZZ-PV-PULL"
        _insert_zouzhe(self.test_db, zid, state="done", planning_version=4)

        fake_row = {
            "id": zid, "title": "t", "description": "d", "state": "done",
            "priority": "high", "plan": None, "exec_revise_count": 0,
            "revise_history": "[]", "revise_limit": 0, "total_revise_rounds": 0,
            "last_revise_reason": None, "suspended_at": None, "planning_version": 4,
            "assigned_agent": "gongbu",
        }

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with patch.object(_ch, "get_db") as mock_get:
                mock_conn = MagicMock()
                mock_conn.row_factory = None
                mock_row = MagicMock()
                mock_row.__getitem__ = lambda s, k: fake_row[k]
                mock_row.get = lambda k, d=None: fake_row.get(k, d)
                mock_conn.execute.return_value.fetchone.return_value = mock_row
                mock_conn.execute.return_value.fetchall.return_value = []
                mock_get.return_value = mock_conn
                with patch("sys.exit", side_effect=SystemExit):
                    try:
                        _ch.cmd_pull([zid])
                    except SystemExit:
                        pass

        data = json.loads(mock_stdout.getvalue().strip())
        self.assertEqual(data["zouzhe"]["planning_version"], 4)


# ──────────────────────────────────────────────────────
# 测试 2：revise_reason 在 dispatcher prompt 中可见
# ──────────────────────────────────────────────────────

class TestReviseReasonInDispatchPrompt(unittest.TestCase):

    def test_path_b_reason_in_message(self):
        """路径 B：revise_history 的原因出现在发给中书省的消息中"""
        zouzhe = {
            "id": "ZZ-015-MSG-TEST",
            "revise_history": json.dumps([{
                "round": 2,
                "reason": "返工：Revert 工部代码 + 兵部用 Agent Teams 重写",
                "revised_by": "silijian",
                "revised_at": "2026-03-10T05:17:00",
                "dup_similarity": 0.0,
            }]),
            "exec_revise_count": 2,
            "plan_history": json.dumps([]),
            "revise_count": 0,
        }
        msg = _disp.format_revising_message(zouzhe)
        # 验证：旨意内容必须出现
        self.assertIn("Revert 工部代码", msg)
        self.assertIn("兵部用 Agent Teams 重写", msg)
        # 验证：target_agent 提示必须出现
        self.assertIn("target_agent", msg)
        # 验证：最高优先级标记
        self.assertIn("最高优先级", msg)
        # 验证：round 编号出现
        self.assertIn("第 2 次", msg)

    def test_path_b_agent_redirection_instruction(self):
        """路径 B 消息必须包含'不得沿用原方案 target_agent'的警告"""
        zouzhe = {
            "id": "ZZ-015-AGENT-REDIRECT",
            "revise_history": json.dumps([{
                "round": 1,
                "reason": "任务必须由兵部（bingbu）执行，工部不适合此任务",
                "revised_by": "silijian",
                "revised_at": "2026-03-10T00:00:00",
                "dup_similarity": 0.0,
            }]),
            "exec_revise_count": 1,
            "plan_history": json.dumps([]),
            "revise_count": 0,
        }
        msg = _disp.format_revising_message(zouzhe)
        self.assertIn("不得沿用原方案", msg)

    def test_path_a_jishi_votes_preserved(self):
        """路径 A（jishi 封驳）：封驳意见仍完整传递"""
        zouzhe = {
            "id": "ZZ-015-JISHI-TEST",
            "revise_history": json.dumps([]),
            "exec_revise_count": 0,
            "plan_history": json.dumps([{
                "round": 1,
                "plan": {"target_agent": "gongbu", "steps": ["s1"]},
                "votes": [
                    {"jishi": "jishi_tech", "vote": "nogo", "reason": "install.sh 不在 repo 根目录"},
                    {"jishi": "jishi_risk", "vote": "go", "reason": "其他方面没有风险"},
                ],
            }]),
            "revise_count": 1,
        }
        msg = _disp.format_revising_message(zouzhe)
        self.assertIn("install.sh 不在 repo 根目录", msg)
        self.assertIn("封驳", msg)
        # 不应混入路径 B 的标记
        self.assertNotIn("最高优先级", msg)


# ──────────────────────────────────────────────────────
# 测试 3：3+ 轮 revise 回归测试
# ──────────────────────────────────────────────────────

class TestMultiRoundRevise(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def _revise_then_done(self, zid: str, reason: str) -> dict:
        """执行 revise，然后手动将状态设回 done（模拟重新执行完成）"""
        result = _run_cmd(_ch.cmd_revise, [zid, reason], self.test_db)
        if result.get("ok") and result.get("state") in ("revising",):
            # 模拟完成一轮
            db = sqlite3.connect(self.test_db)
            db.execute("UPDATE zouzhe SET state='done', output='completed', dispatched_at=NULL WHERE id=?", (zid,))
            db.commit()
            db.close()
        return result

    def test_three_revise_rounds_unlimited(self):
        """revise_limit=0 允许 3+ 轮，每轮 planning_version 正确递增"""
        zid = "ZZ-3ROUND-TEST"
        _insert_zouzhe(self.test_db, zid, state="done", exec_revise_count=0,
                       planning_version=1, revise_history=[])

        expected_pv = 2
        for i in range(1, 5):  # 4 轮
            reason = f"返工第 {i} 轮：修改要求 {i}"
            result = self._revise_then_done(zid, reason)
            self.assertTrue(result.get("ok"), f"Round {i} failed: {result}")
            self.assertEqual(result.get("exec_revise_count"), i)
            self.assertEqual(result.get("planning_version"), expected_pv)
            self.assertEqual(result.get("total_revise_rounds"), i)
            expected_pv += 1

        # 验证 DB 最终状态
        db = sqlite3.connect(self.test_db)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM zouzhe WHERE id=?", (zid,)).fetchone()
        db.close()
        self.assertEqual(row["exec_revise_count"], 4)
        self.assertEqual(row["planning_version"], 5)
        self.assertEqual(row["total_revise_rounds"], 4)

    def test_planning_version_prevents_old_plan_reuse(self):
        """模拟中书省提交旧版规划被拒绝的完整流程"""
        zid = "ZZ-STALE-FLOW"
        # 1. 初始 planning_version=1
        _insert_zouzhe(self.test_db, zid, state="done", planning_version=1)

        # 2. revise → planning_version 变为 2
        result = _run_cmd(_ch.cmd_revise, [zid, "第一次返工：需要改用兵部"], self.test_db)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("planning_version"), 2)

        # 3. 手动将状态设为 planning（模拟 dispatcher 收到 revising→planning）
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET state='planning', dispatched_at=NULL WHERE id=?", (zid,))
        db.commit()
        db.close()

        # 4. 中书省提交旧版规划（version=1）→ 应被拒绝
        old_plan = json.dumps({"target_agent": "gongbu", "steps": ["old step"], "planning_version": 1})
        reject_result = _run_cmd(_ch.cmd_plan, [zid, old_plan], self.test_db)
        self.assertFalse(reject_result.get("ok"), f"Should reject stale plan: {reject_result}")
        self.assertIn("不匹配", reject_result.get("error", ""))

        # 5. 中书省提交新版规划（version=2）→ 应被接受
        new_plan = json.dumps({"target_agent": "bingbu", "steps": ["new step"], "planning_version": 2})
        accept_result = _run_cmd(_ch.cmd_plan, [zid, new_plan], self.test_db)
        self.assertTrue(accept_result.get("ok"), f"Should accept new plan: {accept_result}")

    def test_revise_history_audit_trail(self):
        """每轮 revise 后 revise_history 完整记录"""
        zid = "ZZ-AUDIT-TEST"
        _insert_zouzhe(self.test_db, zid, state="done", exec_revise_count=0, planning_version=1)

        reasons = ["第一次：A 问题", "第二次：B 问题", "第三次：C 问题"]
        for r in reasons:
            self._revise_then_done(zid, r)

        db = sqlite3.connect(self.test_db)
        row = db.execute("SELECT revise_history, last_revise_reason FROM zouzhe WHERE id=?", (zid,)).fetchone()
        db.close()

        history = json.loads(row[0])
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["reason"], reasons[0])
        self.assertEqual(history[1]["reason"], reasons[1])
        self.assertEqual(history[2]["reason"], reasons[2])
        self.assertEqual(history[0]["round"], 1)
        self.assertEqual(history[2]["round"], 3)
        # last_revise_reason 应是最后一轮
        self.assertEqual(row[1], reasons[2])


# ──────────────────────────────────────────────────────
# 测试 4：并行 workspace（逻辑隔离测试）
# ──────────────────────────────────────────────────────

class TestWorkspaceIsolation(unittest.TestCase):
    """两个 workspace（独立 DB）的并行操作不互相干扰"""

    def setUp(self):
        self.tmpdir1 = tempfile.mkdtemp()
        self.tmpdir2 = tempfile.mkdtemp()
        self.db1 = _make_test_db(self.tmpdir1)
        self.db2 = _make_test_db(self.tmpdir2)

    def tearDown(self):
        shutil.rmtree(self.tmpdir1)
        shutil.rmtree(self.tmpdir2)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_two_workspaces_independent_versions(self):
        """两个 workspace 的 planning_version 独立递增"""
        zid = "ZZ-WS-TEST"
        _insert_zouzhe(self.db1, zid, state="done", planning_version=1)
        _insert_zouzhe(self.db2, zid, state="done", planning_version=1)

        # workspace 1 revise 2 次
        _run_cmd(_ch.cmd_revise, [zid, "ws1 revise 1"], self.db1)
        db = sqlite3.connect(self.db1)
        db.execute("UPDATE zouzhe SET state='done',output='x' WHERE id=?", (zid,))
        db.commit()
        db.close()
        r1 = _run_cmd(_ch.cmd_revise, [zid, "ws1 revise 2"], self.db1)
        self.assertEqual(r1.get("planning_version"), 3)

        # workspace 2 revise 1 次（独立）
        r2 = _run_cmd(_ch.cmd_revise, [zid, "ws2 revise 1"], self.db2)
        self.assertEqual(r2.get("planning_version"), 2)

        # 验证两个 DB 独立
        db1 = sqlite3.connect(self.db1)
        pv1 = db1.execute("SELECT planning_version FROM zouzhe WHERE id=?", (zid,)).fetchone()[0]
        db1.close()
        db2 = sqlite3.connect(self.db2)
        pv2 = db2.execute("SELECT planning_version FROM zouzhe WHERE id=?", (zid,)).fetchone()[0]
        db2.close()

        self.assertEqual(pv1, 3)  # ws1: 3
        self.assertEqual(pv2, 2)  # ws2: 2（独立）


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
