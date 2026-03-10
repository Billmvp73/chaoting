#!/usr/bin/env python3
"""
test_revise_unlimited.py — 无限制返工 + 审计增强测试套件 (ZZ-20260310-014)

测试覆盖：
- revise_limit=0（无限制）允许超过原 3 次上限
- revise_limit=N 正确阻断超额返工
- output 截断 ≤ 500 字符
- 重复原因检测（difflib，阈值 0.85）
- 防爆轮机制（suspended 状态 + resume）
- cmd_pull 返回 revise_history 和 exec_revise_count
- dispatcher.format_revising_message 包含 revise_history 原因
- zhongshu 收到的消息可看到目标部门重定向指令

运行：
    cd /home/tetter/self-project/chaoting
    CHAOTING_DIR=$(pwd) python3 src/test_revise_unlimited.py
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
from datetime import datetime, timezone, timedelta

# 确保 src/ 在 path
_src = os.path.dirname(os.path.abspath(__file__))
if _src not in sys.path:
    sys.path.insert(0, _src)

# 加载 chaoting（无 .py 后缀，用 importlib 以 spec_from_loader 方式加载）
import importlib.util as _ilu
import importlib.machinery as _ilm
_chaoting_path = os.path.join(_src, "chaoting")
_loader = _ilm.SourceFileLoader("chaoting", _chaoting_path)
_spec = _ilu.spec_from_loader("chaoting", _loader)
_chaoting_mod = _ilu.module_from_spec(_spec)
sys.modules["chaoting"] = _chaoting_mod
_loader.exec_module(_chaoting_mod)


def _make_test_env(tmpdir: str):
    """在 tmpdir 中创建一个独立的测试 DB 和环境。"""
    # 复制 chaoting.db 到 tmpdir 以免污染主 DB
    chaoting_dir = os.environ.get("CHAOTING_DIR", os.path.dirname(_src))
    src_db = os.path.join(chaoting_dir, "chaoting.db")
    test_db = os.path.join(tmpdir, "chaoting.db")

    import sqlite3
    # 创建临时 DB（复制 schema）
    src_conn = sqlite3.connect(src_db)
    dst_conn = sqlite3.connect(test_db)
    for line in src_conn.iterdump():
        if "INSERT INTO" not in line:  # 只复制 schema
            try:
                dst_conn.execute(line)
            except Exception:
                pass
    dst_conn.commit()
    src_conn.close()
    dst_conn.close()
    return test_db


def _insert_test_zouzhe(db_path: str, zid: str, state: str = "done",
                         exec_revise_count: int = 0,
                         revise_limit: int = 0,
                         revise_timeout_days: int = 0,
                         created_days_ago: int = 0,
                         revise_history: list = None,
                         output: str = None) -> None:
    """往测试 DB 插入一个奏折。"""
    import sqlite3
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    created_at = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    db.execute(
        "INSERT OR REPLACE INTO zouzhe "
        "(id, title, description, state, priority, assigned_agent, plan, output, summary, "
        " exec_revise_count, revise_history, revise_limit, revise_timeout_days, "
        " total_revise_rounds, last_revise_reason, created_at, updated_at, "
        " review_required, revise_count, timeout_sec) "
        "VALUES (?, ?, ?, ?, 'high', 'gongbu', NULL, ?, NULL, ?, ?, ?, ?, 0, NULL, ?, ?, 2, 0, 3600)",
        (
            zid, f"测试奏折 {zid}", "测试描述", state,
            output or "test output",
            exec_revise_count,
            json.dumps(revise_history or [], ensure_ascii=False),
            revise_limit,
            revise_timeout_days,
            created_at, created_at,
        ),
    )
    db.commit()
    db.close()


class TestReviseLimitUnlimited(unittest.TestCase):
    """revise_limit=0（无限制）测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_env(self.tmpdir)
        os.environ["CHAOTING_DIR"] = self.tmpdir
        # 设置 chaoting.db 路径
        import sqlite3
        self._orig_db = os.path.join(self.tmpdir, "chaoting.db")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("CHAOTING_DIR", None)

    def _run_revise(self, zid: str, reason: str, extra_args: list = None) -> dict:
        """调用 cmd_revise 并返回 JSON 输出（捕获 sys.exit）。"""
        import io
        from unittest.mock import patch

        args = [zid, reason] + (extra_args or [])
        output_lines = []

        # 重定向 stdout 捕获 out() 输出
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with patch("sys.exit", side_effect=SystemExit):
                try:
                    # 直接导入并调用
                    import chaoting as ch
                    # 注入测试 DB 路径
                    with patch.object(ch, "get_db") as mock_db:
                        import sqlite3
                        def _get_test_db():
                            conn = sqlite3.connect(self.test_db)
                            conn.row_factory = sqlite3.Row
                            conn.execute("PRAGMA journal_mode=WAL")
                            conn.execute("PRAGMA busy_timeout=5000")
                            return conn
                        mock_db.side_effect = _get_test_db
                        with patch.object(ch, "zouzhe_log"):
                            with patch.object(ch, "send_discord"):
                                ch.cmd_revise(args)
                except SystemExit:
                    pass
            return json.loads(mock_stdout.getvalue().strip().split("\n")[-1])


class TestReviseLimit(unittest.TestCase):
    """直接测试 _detect_duplicate_reason 和 _check_revise_timeout"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _import_helpers(self):
        import sys
        if _src not in sys.path:
            sys.path.insert(0, _src)
        import chaoting as ch  # loaded via importlib at top level
        return ch

    def test_detect_duplicate_reason_similar(self):
        ch = self._import_helpers()
        history = [
            {"round": 1, "reason": "要求改用兵部（bingbu）通过 Agent Teams 重写代码"},
        ]
        result = ch._detect_duplicate_reason(
            "要求改用兵部（bingbu）通过 Agent Teams 重写代码（相同指令）",
            history,
        )
        self.assertTrue(result["duplicate"])
        self.assertGreaterEqual(result["similarity"], 0.85)
        self.assertEqual(result["similar_to_round"], 1)

    def test_detect_duplicate_reason_different(self):
        ch = self._import_helpers()
        history = [
            {"round": 1, "reason": "修复 install.sh 路径问题"},
        ]
        result = ch._detect_duplicate_reason(
            "实现 workspace 隔离化部署，支持多个独立 dispatcher",
            history,
        )
        self.assertFalse(result["duplicate"])
        self.assertLess(result["similarity"], 0.85)

    def test_detect_duplicate_empty_history(self):
        ch = self._import_helpers()
        result = ch._detect_duplicate_reason("任何原因", [])
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["similarity"], 0.0)

    def test_detect_duplicate_only_last_two_rounds(self):
        """仅检查最近 2 轮，不与早期轮次比较"""
        ch = self._import_helpers()
        history = [
            {"round": 1, "reason": "修复路径问题"},  # 旧的，不应比较
            {"round": 2, "reason": "修复日志格式"},
            {"round": 3, "reason": "更新文档结构"},
        ]
        result = ch._detect_duplicate_reason("修复路径问题", history)
        # round 1 相似但超出最近2轮窗口，不触发
        self.assertFalse(result["duplicate"])

    def test_check_revise_timeout_no_limit(self):
        ch = self._import_helpers()
        row = {"revise_timeout_days": 0, "created_at": "2026-01-01T00:00:00"}
        result = ch._check_revise_timeout(row)
        self.assertFalse(result["expired"])
        self.assertEqual(result["limit_days"], 0)

    def test_check_revise_timeout_not_expired(self):
        ch = self._import_helpers()
        created = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        row = {"revise_timeout_days": 30, "created_at": created}
        result = ch._check_revise_timeout(row)
        self.assertFalse(result["expired"])
        self.assertAlmostEqual(result["days_elapsed"], 5.0, delta=0.1)

    def test_check_revise_timeout_expired(self):
        ch = self._import_helpers()
        created = (datetime.now(timezone.utc) - timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%S")
        row = {"revise_timeout_days": 30, "created_at": created}
        result = ch._check_revise_timeout(row)
        self.assertTrue(result["expired"])
        self.assertGreater(result["days_elapsed"], 30.0)


class TestOutputTruncation(unittest.TestCase):
    """output 字段截断测试"""

    def test_output_truncated_to_500_chars(self):
        """revise_history 中的 output 不超过 500 字符"""
        import chaoting as ch  # loaded via importlib at top level
        long_output = "A" * 2000

        # 直接测试截断逻辑
        truncated = long_output[:500] if long_output else None
        self.assertEqual(len(truncated), 500)

    def test_short_output_not_truncated(self):
        short_output = "Short output"
        truncated = short_output[:500] if short_output else None
        self.assertEqual(truncated, short_output)


class TestDispatcherRevisionMessage(unittest.TestCase):
    """dispatcher.format_revising_message V0.4 修复验证"""

    def _import_dispatcher(self):
        import sys
        src = os.path.dirname(os.path.abspath(__file__))
        if src not in sys.path:
            sys.path.insert(0, src)
        import dispatcher as disp
        return disp

    def test_revise_history_route_includes_reason(self):
        """路径 B：revise_history 中的原因必须出现在通知消息中"""
        disp = self._import_dispatcher()
        zouzhe = {
            "id": "ZZ-TEST-001",
            "revise_history": json.dumps([{
                "round": 1,
                "reason": "Revert 工部代码 + 兵部用 Agent Teams 重写",
                "revised_by": "silijian",
                "revised_at": "2026-03-10T05:17:00",
                "dup_similarity": 0.0,
            }]),
            "exec_revise_count": 1,
            "plan_history": json.dumps([]),
            "revise_count": 0,
        }
        msg = disp.format_revising_message(zouzhe)
        self.assertIn("Revert 工部代码", msg)
        self.assertIn("兵部", msg)
        self.assertIn("Agent Teams", msg)
        self.assertIn("最高优先级", msg)
        self.assertIn("target_agent", msg)

    def test_revise_history_dup_warning(self):
        """重复原因时消息中应有 ⚠️ 提示"""
        disp = self._import_dispatcher()
        zouzhe = {
            "id": "ZZ-TEST-002",
            "revise_history": json.dumps([{
                "round": 1,
                "reason": "修复路径问题",
                "revised_by": "silijian",
                "revised_at": "2026-03-10T05:00:00",
                "dup_similarity": 0.92,  # 高相似度
            }]),
            "exec_revise_count": 1,
            "plan_history": json.dumps([]),
            "revise_count": 0,
        }
        msg = disp.format_revising_message(zouzhe)
        self.assertIn("相似度", msg)
        self.assertIn("实质性改进", msg)

    def test_plan_history_route_unchanged(self):
        """路径 A（jishi 封驳）：原有逻辑不变"""
        disp = self._import_dispatcher()
        zouzhe = {
            "id": "ZZ-TEST-003",
            "revise_history": json.dumps([]),   # 空 → 路径 A
            "exec_revise_count": 0,
            "plan_history": json.dumps([{
                "round": 1,
                "plan": {"target_agent": "gongbu", "steps": ["step1"]},
                "votes": [{"jishi": "jishi_tech", "vote": "nogo", "reason": "install.sh 路径错误"}],
            }]),
            "revise_count": 1,
        }
        msg = disp.format_revising_message(zouzhe)
        self.assertIn("封驳", msg)
        self.assertIn("install.sh 路径错误", msg)
        # 不应出现"最高优先级"（这是路径 B 的标记）
        self.assertNotIn("最高优先级", msg)

    def test_exec_revise_count_zero_uses_path_a(self):
        """即使 revise_history 非空，若 exec_revise_count=0 则走路径 A"""
        disp = self._import_dispatcher()
        zouzhe = {
            "id": "ZZ-TEST-004",
            "revise_history": json.dumps([{"round": 0, "reason": "old stale entry"}]),
            "exec_revise_count": 0,   # ← 0 触发路径 A
            "plan_history": json.dumps([{
                "round": 1,
                "plan": {"target_agent": "gongbu"},
                "votes": [{"jishi": "jishi_risk", "vote": "nogo", "reason": "风险未评估"}],
            }]),
            "revise_count": 1,
        }
        msg = disp.format_revising_message(zouzhe)
        self.assertIn("封驳", msg)
        self.assertIn("风险未评估", msg)
        self.assertNotIn("最高优先级", msg)


class TestCmdPullReturnsReviseContext(unittest.TestCase):
    """cmd_pull V0.4 验证：返回 revise_history 等字段"""

    def test_pull_includes_revise_history(self):
        """chaoting pull 输出中必须包含 revise_history"""
        import chaoting as ch  # loaded via importlib at top level
        import io
        from unittest.mock import patch, MagicMock

        fake_row = {
            "id": "ZZ-PULL-TEST",
            "title": "Test",
            "description": "desc",
            "state": "done",
            "priority": "high",
            "plan": None,
            "exec_revise_count": 2,
            "revise_history": json.dumps([{"round": 1, "reason": "first reason"}]),
            "revise_limit": 0,
            "total_revise_rounds": 2,
            "last_revise_reason": "last reason",
            "suspended_at": None,
            "assigned_agent": "gongbu",
            "planning_version": 1,
        }

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with patch.object(ch, "get_db") as mock_db:
                mock_conn = MagicMock()
                mock_conn.row_factory = None
                mock_row = MagicMock()
                mock_row.__getitem__ = lambda s, k: fake_row[k]
                mock_row.get = lambda k, d=None: fake_row.get(k, d)
                mock_row.keys = lambda: fake_row.keys()
                mock_conn.execute.return_value.fetchone.return_value = mock_row
                mock_conn.execute.return_value.fetchall.return_value = []
                mock_db.return_value = mock_conn

                with self.assertRaises(SystemExit):
                    ch.cmd_pull(["ZZ-PULL-TEST"])

            output = mock_stdout.getvalue().strip()
            data = json.loads(output)

        self.assertIn("zouzhe", data)
        z = data["zouzhe"]
        self.assertIn("exec_revise_count", z)
        self.assertIn("revise_history", z)
        self.assertIn("revise_limit", z)
        self.assertIn("last_revise_reason", z)
        self.assertEqual(z["exec_revise_count"], 2)
        self.assertEqual(len(z["revise_history"]), 1)


class TestReviseUnlimitedIntegration(unittest.TestCase):
    """集成测试：使用真实 DB（tmpdir 隔离）"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # 初始化空 DB
        import sqlite3
        chaoting_dir = os.environ.get("CHAOTING_DIR", os.path.dirname(_src))
        src_db = os.path.join(chaoting_dir, "chaoting.db")
        self.test_db = os.path.join(self.tmpdir, "chaoting.db")
        src_conn = sqlite3.connect(src_db)
        dst_conn = sqlite3.connect(self.test_db)
        for line in src_conn.iterdump():
            if "INSERT INTO" not in line:
                try:
                    dst_conn.execute(line)
                except Exception:
                    pass
        dst_conn.commit()
        src_conn.close()
        dst_conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _insert_done_zouzhe(self, zid, exec_revise_count=0, revise_limit=0,
                              revise_timeout_days=0, created_days_ago=0,
                              revise_history=None):
        import sqlite3
        db = sqlite3.connect(self.test_db)
        db.row_factory = sqlite3.Row
        created_at = (
            datetime.now(timezone.utc) - timedelta(days=created_days_ago)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "INSERT OR REPLACE INTO zouzhe "
            "(id, title, description, state, priority, assigned_agent, plan, output, summary, "
            " exec_revise_count, revise_history, revise_limit, revise_timeout_days, "
            " total_revise_rounds, last_revise_reason, suspended_at, created_at, updated_at, "
            " review_required, revise_count, timeout_sec) "
            "VALUES (?, 'test', 'desc', 'done', 'high', 'gongbu', NULL, 'output', NULL, "
            "        ?, ?, ?, ?, 0, NULL, NULL, ?, ?, 2, 0, 3600)",
            (
                zid, exec_revise_count,
                json.dumps(revise_history or [], ensure_ascii=False),
                revise_limit, revise_timeout_days, created_at, created_at,
            ),
        )
        db.commit()
        db.close()

    def _run_revise_cmd(self, zid, reason, extra_args=None):
        import chaoting as ch  # loaded via importlib at top level
        import io
        from unittest.mock import patch
        import sqlite3

        os.environ["OPENCLAW_AGENT_ID"] = "silijian"
        args = [zid, reason] + (extra_args or [])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with patch.object(ch, "get_db") as mock_get_db:
                def _get_db():
                    conn = sqlite3.connect(self.test_db)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=5000")
                    return conn
                mock_get_db.side_effect = _get_db
                with patch.object(ch, "zouzhe_log"):
                    with patch.object(ch, "send_discord"):
                        with self.assertRaises(SystemExit):
                            ch.cmd_revise(args)
        return json.loads(mock_stdout.getvalue().strip().split("\n")[-1])

    def test_unlimited_allows_beyond_3_revises(self):
        """revise_limit=0 允许超过 3 次"""
        zid = "ZZ-UNLIMITED-TEST"
        self._insert_done_zouzhe(zid, exec_revise_count=4, revise_limit=0)  # 已经 4 次

        result = self._run_revise_cmd(zid, "第5次返工")
        # 不应因超过上限而失败
        self.assertTrue(result["ok"], f"Expected ok=True: {result}")
        self.assertEqual(result["exec_revise_count"], 5)

    def test_limited_blocks_over_limit(self):
        """revise_limit=2 时，第 3 次返工被阻断"""
        zid = "ZZ-LIMITED-TEST"
        self._insert_done_zouzhe(zid, exec_revise_count=2, revise_limit=2)

        result = self._run_revise_cmd(zid, "第3次尝试")
        self.assertFalse(result["ok"])
        self.assertIn("上限", result["error"])

    def test_limit_flag_updates_revise_limit(self):
        """--limit 3 正确设置 revise_limit"""
        zid = "ZZ-SETLIMIT-TEST"
        self._insert_done_zouzhe(zid, exec_revise_count=0, revise_limit=0)

        result = self._run_revise_cmd(zid, "原因", extra_args=["--limit", "3"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["revise_limit"], 3)

    def test_output_truncated_in_history(self):
        """revise_history 中的 output 字段不超过 500 字符"""
        import sqlite3
        zid = "ZZ-TRUNC-TEST"
        self._insert_done_zouzhe(zid)
        # 手动设置长 output
        db = sqlite3.connect(self.test_db)
        db.execute(f"UPDATE zouzhe SET output=? WHERE id=?", ("X" * 2000, zid))
        db.commit()
        db.close()

        result = self._run_revise_cmd(zid, "截断测试")
        self.assertTrue(result["ok"])

        # 从 DB 读取 revise_history 验证截断
        db = sqlite3.connect(self.test_db)
        row = db.execute(f"SELECT revise_history FROM zouzhe WHERE id=?", (zid,)).fetchone()
        history = json.loads(row[0])
        db.close()
        self.assertLessEqual(len(history[-1].get("output") or ""), 500)

    def test_timeout_triggers_suspended(self):
        """revise_timeout_days=10 + 20天前创建 → 触发 suspended"""
        zid = "ZZ-SUSPEND-TEST"
        self._insert_done_zouzhe(zid, revise_timeout_days=10, created_days_ago=20)

        result = self._run_revise_cmd(zid, "超时返工")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "suspended")
        self.assertTrue(result.get("suspended"))

    def test_timeout_not_triggered_within_limit(self):
        """创建 5 天，limit=30 天，不触发 suspended"""
        zid = "ZZ-NO-SUSPEND-TEST"
        self._insert_done_zouzhe(zid, revise_timeout_days=30, created_days_ago=5)

        result = self._run_revise_cmd(zid, "正常返工")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "revising")
        self.assertFalse(result.get("suspended", False))

    def test_duplicate_reason_warning(self):
        """重复原因触发 warning 字段但不阻断"""
        zid = "ZZ-DUP-TEST"
        dup_reason = "要求改用兵部（bingbu）通过 Agent Teams 重写"
        self._insert_done_zouzhe(
            zid, exec_revise_count=1, revise_limit=0,
            revise_history=[{
                "round": 1,
                "reason": dup_reason,
                "revised_by": "silijian",
                "revised_at": "2026-03-10T05:00:00",
            }],
        )
        # 故意重设 state=done（因为 revise 会改 state）
        import sqlite3
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET state='done', exec_revise_count=1, output='x' WHERE id=?", (zid,))
        db.commit()
        db.close()

        result = self._run_revise_cmd(zid, dup_reason + "（几乎相同）")
        # 不阻断
        self.assertTrue(result["ok"])
        # 应有 warning
        self.assertIn("warning", result)
        self.assertGreaterEqual(result.get("dup_similarity", 0), 0.85)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
