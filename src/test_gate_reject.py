#!/usr/bin/env python3
"""
test_gate_reject.py — ZZ-20260310-014 v2 回归测试

验证：
- 门下省封驳 1/2 次 → revising（退回中书省）
- 门下省封驳第 3 次（达 GATE_REJECT_LIMIT）→ escalated（通知司礼监）
- 皇上下旨 emperor_revise 不受 gate_reject 次数影响
- liuzhuan action 正确区分 gate_reject vs emperor_revise
- CHAOTING_GATE_REJECT_LIMIT 环境变量可配置

运行：
    cd /home/tetter/self-project/chaoting
    CHAOTING_DIR=$(pwd) python3 src/test_gate_reject.py
"""

import json
import os
import sys
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import io
import importlib.machinery
import importlib.util

_src = os.path.dirname(os.path.abspath(__file__))


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
                   revise_count: int = 0,
                   planning_version: int = 1) -> None:
    db = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    db.execute(
        "INSERT OR REPLACE INTO zouzhe "
        "(id, title, description, state, priority, assigned_agent, plan, output, summary, "
        " exec_revise_count, revise_count, revise_history, revise_limit, revise_timeout_days, "
        " total_revise_rounds, last_revise_reason, suspended_at, planning_version, "
        " created_at, updated_at, review_required, timeout_sec) "
        "VALUES (?, ?, 'desc', ?, 'high', 'gongbu', NULL, 'output', NULL, "
        "        ?, ?, '[]', 0, 0, 0, NULL, NULL, ?, ?, ?, 2, 3600)",
        (
            zid, f"Test {zid}", state,
            exec_revise_count, revise_count,
            planning_version,
            now, now,
        ),
    )
    db.commit()
    db.close()


def _run_cmd(cmd_fn, args, test_db):
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


def _simulate_gate_reject(db_path: str, zid: str) -> dict:
    """模拟门下省封驳一次 — 向 toupiao 插入 nogo 投票，然后调用 check_votes"""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")

    # 设置奏折为 reviewing 状态（含 plan JSON）
    db.execute(
        "UPDATE zouzhe SET state='reviewing', plan=? WHERE id=?",
        (json.dumps({"target_agent": "gongbu", "steps": ["step1"]}), zid),
    )
    db.commit()

    zouzhe = dict(db.execute("SELECT * FROM zouzhe WHERE id=?", (zid,)).fetchone())
    current_round = (zouzhe["revise_count"] or 0) + 1
    jishi_list = _disp.get_review_agents(zouzhe)

    # 插入 nogo 投票（所有 jishi 均投 nogo，确保 check_votes 可以执行）
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for jishi_id in jishi_list:
        db.execute(
            "INSERT OR REPLACE INTO toupiao (zouzhe_id, round, jishi_id, agent_id, vote, reason, timestamp) "
            "VALUES (?, ?, ?, 'unknown', 'nogo', ?, ?)",
            (zid, current_round, jishi_id, f"测试封驳 {jishi_id}", now),
        )
    db.commit()

    with patch.object(_disp, "zouzhe_log"):
        with patch.object(_disp, "_cli_notify"):
            with patch("subprocess.run"), patch("subprocess.Popen"):
                _disp.check_votes(db, zouzhe)

    db.commit()
    row = db.execute("SELECT state, revise_count FROM zouzhe WHERE id=?", (zid,)).fetchone()
    liuzhuan = db.execute(
        "SELECT action FROM liuzhuan WHERE zouzhe_id=? ORDER BY id DESC LIMIT 1",
        (zid,),
    ).fetchone()
    result = {
        "state": row["state"],
        "revise_count": row["revise_count"],
        "liuzhuan_action": liuzhuan["action"] if liuzhuan else None,
    }
    db.close()
    return result


class TestGateRejectLimit(unittest.TestCase):
    """门下省封驳次数上限机制"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)
        # 确保 GATE_REJECT_LIMIT = 3（默认值）
        os.environ.pop("CHAOTING_GATE_REJECT_LIMIT", None)
        # 重新加载 dispatcher 以应用 env
        _disp.GATE_REJECT_LIMIT = 3

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)
        os.environ.pop("CHAOTING_GATE_REJECT_LIMIT", None)

    def test_first_gate_reject_goes_to_revising(self):
        """第 1 次门下省封驳 → revising 状态，liuzhuan action = gate_reject"""
        zid = "ZZ-GR-ROUND1"
        _insert_zouzhe(self.test_db, zid, state="executing", revise_count=0)
        result = _simulate_gate_reject(self.test_db, zid)

        self.assertEqual(result["state"], "revising", f"Expected revising: {result}")
        self.assertEqual(result["revise_count"], 1)
        self.assertEqual(result["liuzhuan_action"], "gate_reject",
                         "liuzhuan action should be gate_reject, not reject")

    def test_second_gate_reject_goes_to_revising(self):
        """第 2 次门下省封驳 → 仍是 revising（还未达上限）"""
        zid = "ZZ-GR-ROUND2"
        _insert_zouzhe(self.test_db, zid, state="executing", revise_count=1)
        result = _simulate_gate_reject(self.test_db, zid)

        self.assertEqual(result["state"], "revising")
        self.assertEqual(result["revise_count"], 2)

    def test_third_gate_reject_escalates(self):
        """第 3 次门下省封驳（达 GATE_REJECT_LIMIT=3）→ escalated 状态，通知司礼监"""
        zid = "ZZ-GR-ESCALATE"
        _insert_zouzhe(self.test_db, zid, state="executing", revise_count=2)
        result = _simulate_gate_reject(self.test_db, zid)

        self.assertEqual(result["state"], "escalated",
                         f"3rd gate_reject should escalate, not fail: {result}")
        self.assertEqual(result["liuzhuan_action"], "escalate",
                         "liuzhuan action should be escalate")

    def test_escalated_not_failed(self):
        """escalated 状态 ≠ failed（皇上可以继续下旨）"""
        zid = "ZZ-GR-NOT-FAILED"
        _insert_zouzhe(self.test_db, zid, state="executing", revise_count=2)
        result = _simulate_gate_reject(self.test_db, zid)

        self.assertNotEqual(result["state"], "failed",
                            "Should be escalated, not failed — emperor can still revise")

    def test_configurable_limit(self):
        """CHAOTING_GATE_REJECT_LIMIT 环境变量可配置上限"""
        # 设置上限为 2
        _disp.GATE_REJECT_LIMIT = 2

        zid = "ZZ-GR-LIMIT2"
        # revise_count=1 表示已封驳 1 次，第 2 次应触发 escalate
        _insert_zouzhe(self.test_db, zid, state="executing", revise_count=1)
        result = _simulate_gate_reject(self.test_db, zid)

        self.assertEqual(result["state"], "escalated",
                         f"With limit=2, 2nd reject should escalate: {result}")


class TestEmperorReviseUnlimited(unittest.TestCase):
    """皇上下旨不受门下省封驳次数限制"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_emperor_revise_after_escalated(self):
        """即使奏折处于 escalated 状态（门下省封驳上限），皇上仍可通过 cmd_revise 下旨"""
        # 注意：cmd_revise 检查的是 state='done'；escalated 状态下直接下旨需要先恢复
        # 但关键是：exec_revise_count 与 revise_count 是独立的
        zid = "ZZ-ER-UNLIMITED"
        _insert_zouzhe(self.test_db, zid, state="done", exec_revise_count=5,
                       revise_count=0, planning_version=1)

        # 皇上下旨第 6 次（已经第 5 次了，无限制）
        result = _run_cmd(_ch.cmd_revise, [zid, "皇上下旨第 6 次旨意：必须重做"], self.test_db)
        self.assertTrue(result.get("ok"), f"Emperor revise should succeed regardless: {result}")
        self.assertEqual(result.get("exec_revise_count"), 6)
        self.assertEqual(result.get("revise_type"), "emperor_revise")
        self.assertIn("第 6 次旨意", result.get("revise_message", ""))

    def test_emperor_revise_message_contains_nth_count(self):
        """cmd_revise 返回中包含'当前是第 N 次旨意'的明确提示"""
        zid = "ZZ-ER-MSG"
        _insert_zouzhe(self.test_db, zid, state="done", exec_revise_count=2, planning_version=1)

        result = _run_cmd(_ch.cmd_revise, [zid, "需要修改接口设计"], self.test_db)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("revise_type"), "emperor_revise")
        msg = result.get("revise_message", "")
        self.assertIn("第 3 次旨意", msg)
        self.assertIn("不受门下省封驳次数限制", msg)

    def test_emperor_revise_liuzhuan_action(self):
        """cmd_revise 生成的 liuzhuan action 为 emperor_revise"""
        zid = "ZZ-ER-LIUZHUAN"
        _insert_zouzhe(self.test_db, zid, state="done", exec_revise_count=0, planning_version=1)

        _run_cmd(_ch.cmd_revise, [zid, "下旨修改"], self.test_db)

        db = sqlite3.connect(self.test_db)
        row = db.execute(
            "SELECT action FROM liuzhuan WHERE zouzhe_id=? ORDER BY id DESC LIMIT 1",
            (zid,),
        ).fetchone()
        db.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "emperor_revise",
                         f"liuzhuan action should be emperor_revise, got: {row[0]}")


class TestAuditDistinction(unittest.TestCase):
    """审计日志可区分两种 revise 来源"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)
        _disp.GATE_REJECT_LIMIT = 3

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_liuzhuan_distinguishes_gate_vs_emperor(self):
        """liuzhuan 表中 gate_reject 和 emperor_revise 是不同的 action"""
        zid = "ZZ-AUDIT-DIST"
        _insert_zouzhe(self.test_db, zid, state="done", revise_count=0, planning_version=1)

        # 1. 皇上下旨
        _run_cmd(_ch.cmd_revise, [zid, "皇上旨意"], self.test_db)

        # 2. 模拟门下省封驳（需要先将状态改为 executing/reviewing）
        db = sqlite3.connect(self.test_db)
        db.execute("UPDATE zouzhe SET state='executing', output='x', exec_revise_count=1 WHERE id=?", (zid,))
        db.commit()
        db.close()
        _simulate_gate_reject(self.test_db, zid)

        # 查询所有 liuzhuan 记录
        db = sqlite3.connect(self.test_db)
        rows = db.execute(
            "SELECT action FROM liuzhuan WHERE zouzhe_id=? ORDER BY id",
            (zid,),
        ).fetchall()
        db.close()

        actions = [r[0] for r in rows]
        self.assertIn("emperor_revise", actions, f"emperor_revise not in liuzhuan: {actions}")
        self.assertIn("gate_reject", actions, f"gate_reject not in liuzhuan: {actions}")

    def test_gate_reject_limit_message_mentions_emperor_revise(self):
        """escalate 通知中应提示皇上可以通过 chaoting revise 下旨"""
        zid = "ZZ-ESCALATE-MSG"
        _insert_zouzhe(self.test_db, zid, state="executing", revise_count=2)

        notify_messages = []

        def _capture_notify(zid_arg, msg):
            notify_messages.append(msg)

        db = sqlite3.connect(self.test_db)
        db.row_factory = sqlite3.Row
        db.execute(
            "UPDATE zouzhe SET state='reviewing', plan=? WHERE id=?",
            (json.dumps({"target_agent": "gongbu", "steps": ["s1"]}), zid),
        )
        db.commit()

        zouzhe = dict(db.execute("SELECT * FROM zouzhe WHERE id=?", (zid,)).fetchone())
        jishi_list = _disp.get_review_agents(zouzhe)
        current_round = (zouzhe["revise_count"] or 0) + 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for jishi_id in jishi_list:
            db.execute(
                "INSERT OR REPLACE INTO toupiao (zouzhe_id, round, jishi_id, agent_id, vote, reason, timestamp) "
                "VALUES (?, ?, ?, 'unknown', 'nogo', '封驳', ?)",
                (zid, current_round, jishi_id, now),
            )
        db.commit()

        with patch.object(_disp, "zouzhe_log"):
            with patch.object(_disp, "_cli_notify", side_effect=_capture_notify):
                with patch("subprocess.run"), patch("subprocess.Popen"):
                    _disp.check_votes(db, zouzhe)
        db.close()

        self.assertTrue(len(notify_messages) > 0, "Should have sent notification")
        combined = " ".join(notify_messages)
        self.assertIn("chaoting revise", combined,
                      f"Notification should mention chaoting revise command. Got: {combined}")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
