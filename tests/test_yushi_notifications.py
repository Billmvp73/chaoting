#!/usr/bin/env python3
"""
test_yushi_notifications.py — ZZ-20260314-002 yushi Discord notification tests

Covers:
1. _dispatch_to_yushi() calls _cli_notify with '御史审核开始', ZZ-ID, title, PR URL
2. cmd_yushi_approve notification contains title and 'done'
3. cmd_yushi_nogo (normal path) notification contains title, reason, '驳回'
4. cmd_yushi_nogo (escalated path) notification contains '审核超限' and 'escalated'

Run:
    cd /home/tetter/self-project/chaoting
    CHAOTING_DIR=$(pwd) python3 tests/test_yushi_notifications.py
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

# Paths
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(os.path.dirname(_tests_dir), "src")


# ── Module loader ──
def _load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


_ch = _load_module("chaoting_notif", os.path.join(_src, "chaoting"))
_disp = _load_module("dispatcher_notif", os.path.join(_src, "dispatcher.py"))
_init_db = _load_module("init_db_notif", os.path.join(_src, "init_db.py"))


# ── DB helpers ──
def _make_test_db(tmpdir: str) -> str:
    """Create an isolated test DB using SCHEMA from init_db.py."""
    test_db = os.path.join(tmpdir, "chaoting.db")
    conn = sqlite3.connect(test_db)
    for stmt in _init_db.SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass
    for col_entry in getattr(_init_db, "ZOUZHE_NEW_COLUMNS", []):
        try:
            if isinstance(col_entry, (list, tuple)) and len(col_entry) == 2:
                col_name, col_def = col_entry
                conn.execute(f"ALTER TABLE zouzhe ADD COLUMN {col_name} {col_def}")
            else:
                conn.execute(f"ALTER TABLE zouzhe ADD COLUMN {col_entry}")
        except Exception:
            pass
    conn.commit()
    conn.close()
    return test_db


def _insert_zouzhe(
    db_path: str,
    zid: str,
    title: str = "Test Task",
    state: str = "pr_review",
    assigned_agent: str = "bingbu",
    exec_revise_count: int = 0,
    output: str = None,
    plan: dict = None,
    discord_thread_id: str = None,
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
            zid, title, state, assigned_agent, plan_json, output,
            exec_revise_count, now, now,
        ),
    )
    db.commit()
    # Set discord_thread_id if provided
    if discord_thread_id:
        db.execute(
            "UPDATE zouzhe SET discord_thread_id = ? WHERE id = ?",
            (discord_thread_id, zid),
        )
        db.commit()
    db.close()


def _make_disp_db(db_path: str):
    """Return a dispatcher-compatible sqlite3 connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _run_cmd(cmd_fn, args, test_db, agent_id="yushi"):
    """Run a chaoting command, capture stdout, return parsed JSON and captured send_discord calls."""
    os.environ["OPENCLAW_AGENT_ID"] = agent_id
    captured_discord = []

    def _fake_send_discord(zid, body, thread_id=None):
        captured_discord.append({"zid": zid, "body": body, "thread_id": thread_id})

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
                with patch.object(_ch, "send_discord", side_effect=_fake_send_discord):
                    with patch("sys.exit", side_effect=SystemExit):
                        try:
                            cmd_fn(args)
                        except SystemExit:
                            pass
    raw = mock_stdout.getvalue().strip()
    result = {}
    if raw:
        try:
            result = json.loads(raw.split("\n")[-1])
        except Exception:
            pass
    return result, captured_discord


# ══════════════════════════════════════════════════════════════════
# Test 1: _dispatch_to_yushi() calls _cli_notify with correct format
# ══════════════════════════════════════════════════════════════════

class TestDispatchToYushiNotification(unittest.TestCase):
    """_dispatch_to_yushi() must call _cli_notify with the yushi review-start notification."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)
        _insert_zouzhe(
            self.test_db,
            "ZZ-NOTIF-001",
            title="Add OAuth support",
            state="pr_review",
            output="PR is ready: https://github.com/org/repo/pull/99",
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_dispatch_to_yushi_calls_cli_notify(self):
        """_dispatch_to_yushi() must call _cli_notify once with '御史审核开始', ZZ-ID, title, PR URL."""
        db = _make_disp_db(self.test_db)

        # Fetch the zouzhe row (as dict-like)
        row = db.execute("SELECT * FROM zouzhe WHERE id='ZZ-NOTIF-001'").fetchone()
        zouzhe = dict(row)
        # Patch dispatched_at=NULL so CAS check passes
        db.execute(
            "UPDATE zouzhe SET dispatched_at = NULL WHERE id = 'ZZ-NOTIF-001'"
        )
        db.commit()
        row = db.execute("SELECT * FROM zouzhe WHERE id='ZZ-NOTIF-001'").fetchone()
        zouzhe = dict(row)

        captured_notify = []

        def _fake_cli_notify(zid, body):
            captured_notify.append({"zid": zid, "body": body})

        with patch.object(_disp, "dispatch_agent"):
            with patch.object(_disp, "_cli_notify", side_effect=_fake_cli_notify):
                with patch.object(_disp, "zouzhe_log"):
                    _disp._dispatch_to_yushi(db, zouzhe)

        db.close()

        self.assertEqual(len(captured_notify), 1, "_cli_notify should be called exactly once")
        body = captured_notify[0]["body"]
        self.assertIn("御史审核开始", body, "body should contain '御史审核开始'")
        self.assertIn("ZZ-NOTIF-001", body, "body should contain the ZZ-ID")
        self.assertIn("Add OAuth support", body, "body should contain the task title")
        self.assertIn("https://github.com/org/repo/pull/99", body, "body should contain the PR URL")
        self.assertEqual(captured_notify[0]["zid"], "ZZ-NOTIF-001")

    def test_dispatch_to_yushi_cli_notify_no_github_url_uses_output_prefix(self):
        """When output has no GitHub URL, _cli_notify falls back to output[:100]."""
        _insert_zouzhe(
            self.test_db,
            "ZZ-NOTIF-001B",
            title="No URL task",
            state="pr_review",
            output="PR submitted via internal tracker, ticket #456",
        )
        db = _make_disp_db(self.test_db)
        db.execute("UPDATE zouzhe SET dispatched_at = NULL WHERE id = 'ZZ-NOTIF-001B'")
        db.commit()
        row = db.execute("SELECT * FROM zouzhe WHERE id='ZZ-NOTIF-001B'").fetchone()
        zouzhe = dict(row)

        captured_notify = []

        def _fake_cli_notify(zid, body):
            captured_notify.append({"zid": zid, "body": body})

        with patch.object(_disp, "dispatch_agent"):
            with patch.object(_disp, "_cli_notify", side_effect=_fake_cli_notify):
                with patch.object(_disp, "zouzhe_log"):
                    _disp._dispatch_to_yushi(db, zouzhe)

        db.close()

        self.assertEqual(len(captured_notify), 1)
        body = captured_notify[0]["body"]
        self.assertIn("御史审核开始", body)
        self.assertIn("ZZ-NOTIF-001B", body)
        # Should contain part of the output since no GitHub URL
        self.assertIn("PR submitted", body)


# ══════════════════════════════════════════════════════════════════
# Test 2: cmd_yushi_approve notification contains title and 'done'
# ══════════════════════════════════════════════════════════════════

class TestYushiApproveNotification(unittest.TestCase):
    """cmd_yushi_approve must send Discord notification containing title and 'done' state info."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)
        _insert_zouzhe(
            self.test_db,
            "ZZ-NOTIF-002",
            title="Implement OAuth login flow",
            state="pr_review",
            assigned_agent="bingbu",
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_yushi_approve_notification_contains_title_and_done(self):
        """yushi-approve Discord notification must contain title, '御史准奏', and 'done'."""
        result, discord_calls = _run_cmd(
            _ch.cmd_yushi_approve, ["ZZ-NOTIF-002"], self.test_db, agent_id="yushi"
        )
        self.assertTrue(result.get("ok"), f"yushi-approve failed: {result}")
        self.assertEqual(result.get("state"), "done")

        self.assertEqual(len(discord_calls), 1, "send_discord should be called once")
        body = discord_calls[0]["body"]
        self.assertIn("御史准奏", body, "notification should contain '御史准奏'")
        self.assertIn("Implement OAuth login flow", body, "notification should contain the task title")
        self.assertIn("done", body, "notification should reference 'done' state transition")
        self.assertIn("ZZ-NOTIF-002", body, "notification should contain the ZZ-ID")


# ══════════════════════════════════════════════════════════════════
# Test 3: cmd_yushi_nogo (normal path) contains title, reason, '驳回'
# ══════════════════════════════════════════════════════════════════

class TestYushiNogoNormalNotification(unittest.TestCase):
    """cmd_yushi_nogo (executor_revise path) must send Discord notification with title, reason, '驳回'."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)
        _insert_zouzhe(
            self.test_db,
            "ZZ-NOTIF-003",
            title="Refactor payment module",
            state="pr_review",
            exec_revise_count=0,
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_yushi_nogo_notification_contains_title_and_reason(self):
        """yushi-nogo (normal) notification must contain title, reason, and '驳回'."""
        reason = "Missing error handling in payment_service.py:42"
        result, discord_calls = _run_cmd(
            _ch.cmd_yushi_nogo, ["ZZ-NOTIF-003", reason], self.test_db, agent_id="yushi"
        )
        self.assertTrue(result.get("ok"), f"yushi-nogo failed: {result}")
        self.assertEqual(result.get("state"), "executor_revise")

        self.assertEqual(len(discord_calls), 1, "send_discord should be called once")
        body = discord_calls[0]["body"]
        self.assertIn("驳回", body, "notification should contain '驳回'")
        self.assertIn("Refactor payment module", body, "notification should contain the task title")
        self.assertIn(reason, body, "notification should contain the NOGO reason")
        self.assertIn("ZZ-NOTIF-003", body, "notification should contain the ZZ-ID")


# ══════════════════════════════════════════════════════════════════
# Test 4: cmd_yushi_nogo (escalated path) contains '审核超限' and 'escalated'
# ══════════════════════════════════════════════════════════════════

class TestYushiNogoEscalatedNotification(unittest.TestCase):
    """cmd_yushi_nogo with exec_revise_count>=3 must send '审核超限'/'escalated' notification."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_db = _make_test_db(self.tmpdir)
        # Set exec_revise_count to 3 to trigger escalation
        _insert_zouzhe(
            self.test_db,
            "ZZ-NOTIF-004",
            title="Fix memory leak in worker",
            state="pr_review",
            exec_revise_count=3,
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.environ.pop("OPENCLAW_AGENT_ID", None)

    def test_yushi_nogo_escalated_notification(self):
        """yushi-nogo escalated notification must contain '审核超限' and 'escalated'."""
        reason = "Still has race condition in worker_pool.go:88"
        result, discord_calls = _run_cmd(
            _ch.cmd_yushi_nogo, ["ZZ-NOTIF-004", reason], self.test_db, agent_id="yushi"
        )
        self.assertTrue(result.get("ok"), f"yushi-nogo escalated failed: {result}")
        self.assertEqual(result.get("state"), "escalated")

        self.assertEqual(len(discord_calls), 1, "send_discord should be called once")
        body = discord_calls[0]["body"]
        self.assertIn("审核超限", body, "notification should contain '审核超限'")
        self.assertIn("escalated", body, "notification should contain 'escalated'")
        self.assertIn("ZZ-NOTIF-004", body, "notification should contain the ZZ-ID")
        self.assertIn(reason, body, "notification should contain the NOGO reason")


if __name__ == "__main__":
    unittest.main(verbosity=2)
