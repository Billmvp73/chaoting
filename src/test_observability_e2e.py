"""E2E tests for the observability infrastructure (ZZ-20260314-004).

Covers:
  (a) logs command output format and filters
  (b) health check pass/fail states and JSON schema
  (c) test-results file creation and commit
  (d) push-for-review health gate block and --skip-health-check bypass
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Resolve paths
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
CHAOTING_CLI = os.path.join(SRC_DIR, "chaoting")
INIT_DB_PATH = os.path.join(SRC_DIR, "init_db.py")


def _load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


# Load init_db to get SCHEMA
_init_db = _load_module("init_db_obs", INIT_DB_PATH)


def _make_test_db(db_path: str) -> str:
    """Create an isolated test DB from init_db.py SCHEMA."""
    conn = sqlite3.connect(db_path)
    for stmt in _init_db.SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass
    conn.commit()
    conn.close()
    return db_path


def run_cli(*args, env=None):
    """Run the chaoting CLI and return (returncode, stdout, stderr)."""
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    result = subprocess.run(
        [CHAOTING_CLI, *args],
        capture_output=True, text=True, env=merged_env,
    )
    return result.returncode, result.stdout, result.stderr


def parse_json(stdout):
    """Parse JSON from CLI stdout, return dict."""
    return json.loads(stdout.strip())


class TestLogsCommand(unittest.TestCase):
    """(a) logs command output format and filters."""

    def test_logs_missing_service_arg(self):
        """logs with no args should return error."""
        rc, out, _ = run_cli("logs")
        self.assertNotEqual(rc, 0)
        data = parse_json(out)
        self.assertFalse(data["ok"])
        self.assertIn("usage", data["error"])

    def test_logs_nonexistent_service_returns_ok(self):
        """logs for a non-existent service should still return ok (journalctl outputs nothing)."""
        rc, out, _ = run_cli("logs", "nonexistent-service-xyz-999")
        # journalctl returns 0 even for unknown units (empty output)
        data = parse_json(out)
        self.assertTrue(data["ok"])
        self.assertIn("service", data)
        self.assertIn("line_count", data)
        self.assertIn("logs", data)
        self.assertIn("filters", data)
        self.assertEqual(data["service"], "nonexistent-service-xyz-999")

    def test_logs_output_schema(self):
        """logs output has correct JSON schema."""
        rc, out, _ = run_cli("logs", "nonexistent-service-xyz-999", "--tail", "5")
        data = parse_json(out)
        self.assertIn("ok", data)
        self.assertIn("service", data)
        self.assertIn("line_count", data)
        self.assertIn("logs", data)
        self.assertIn("filters", data)
        filters = data["filters"]
        self.assertIn("tail", filters)
        self.assertIn("grep", filters)
        self.assertIn("since", filters)

    def test_logs_tail_filter_recorded(self):
        """--tail N is recorded in output filters."""
        rc, out, _ = run_cli("logs", "nonexistent-service-xyz-999", "--tail", "20")
        data = parse_json(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["filters"]["tail"], 20)

    def test_logs_grep_filter_recorded(self):
        """--grep pattern is recorded in output filters."""
        rc, out, _ = run_cli("logs", "nonexistent-service-xyz-999", "--grep", "ERROR")
        data = parse_json(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["filters"]["grep"], "ERROR")

    def test_logs_since_filter_recorded(self):
        """--since Xs/Xm/Xh is recorded in output filters."""
        for since_val in ["30s", "5m", "1h"]:
            with self.subTest(since=since_val):
                rc, out, _ = run_cli("logs", "nonexistent-service-xyz-999", "--since", since_val)
                data = parse_json(out)
                self.assertTrue(data["ok"])
                self.assertEqual(data["filters"]["since"], since_val)


class TestHealthCommand(unittest.TestCase):
    """(b) health check pass/fail states and JSON schema."""

    def test_health_missing_service_arg(self):
        """health with no args should return error."""
        rc, out, _ = run_cli("health")
        self.assertNotEqual(rc, 0)
        data = parse_json(out)
        self.assertFalse(data["ok"])
        self.assertIn("usage", data["error"])

    def test_health_inactive_service(self):
        """health check on an inactive/unknown service returns active=False."""
        rc, out, _ = run_cli("health", "nonexistent-service-xyz-999")
        data = parse_json(out)
        self.assertTrue(data["ok"])
        self.assertFalse(data["active"])
        self.assertFalse(data["healthy"])
        self.assertIn("service", data)
        self.assertEqual(data["service"], "nonexistent-service-xyz-999")
        self.assertIn("details", data)
        self.assertIsInstance(data["details"], list)
        self.assertGreater(len(data["details"]), 0)

    def test_health_json_schema(self):
        """health output always has required JSON schema fields."""
        rc, out, _ = run_cli("health", "nonexistent-service-xyz-999")
        data = parse_json(out)
        for field in ["ok", "service", "active", "healthy", "details"]:
            self.assertIn(field, data, f"Missing field: {field}")

    def test_health_no_endpoint_ok_field_without_endpoint(self):
        """endpoint_ok field should NOT be present when no --endpoint given."""
        rc, out, _ = run_cli("health", "nonexistent-service-xyz-999")
        data = parse_json(out)
        self.assertNotIn("endpoint_ok", data)

    def test_health_with_bad_endpoint(self):
        """health with an unreachable endpoint sets endpoint_ok=False."""
        rc, out, _ = run_cli(
            "health", "nonexistent-service-xyz-999",
            "--endpoint", "http://127.0.0.1:19999/health-nonexistent",
        )
        data = parse_json(out)
        self.assertTrue(data["ok"])
        self.assertFalse(data["healthy"])
        self.assertIn("endpoint_ok", data)
        self.assertFalse(data["endpoint_ok"])

    def test_health_active_service(self):
        """health check on a known active service returns active=True."""
        # Use dbus.service which is always present on systemd hosts
        rc, out, _ = run_cli("health", "dbus.service")
        data = parse_json(out)
        self.assertTrue(data["ok"])
        # dbus.service should be active on any systemd desktop
        self.assertTrue(data["active"])
        self.assertTrue(data["healthy"])


class TestTestResultsPersistence(unittest.TestCase):
    """(c) test-results file creation and commit via push-for-review Layer 2."""

    def setUp(self):
        """Set up a temporary git repo and chaoting DB."""
        self.tmpdir = tempfile.mkdtemp(prefix="chaoting_test_")
        self.db_path = os.path.join(self.tmpdir, "chaoting.db")
        self.repo_path = os.path.join(self.tmpdir, "repo")

        # Create temp git repo
        os.makedirs(self.repo_path)
        subprocess.run(["git", "init", self.repo_path], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@chaoting.local"],
            cwd=self.repo_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Chaoting Test"],
            cwd=self.repo_path, capture_output=True,
        )
        # Initial commit so branch exists
        readme = os.path.join(self.repo_path, "README.md")
        Path(readme).write_text("# Chaoting Test Repo\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=self.repo_path, capture_output=True,
        )

        # Init chaoting DB using init_db SCHEMA directly
        _make_test_db(self.db_path)

        self.env = {
            "CHAOTING_DB_PATH": self.db_path,
            "CHAOTING_WORKSPACE": self.tmpdir,
            "CHAOTING_DIR": self.tmpdir,
            "OPENCLAW_AGENT_ID": "bingbu",
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_executing_zouzhe(self, zid="ZZ-TEST-OBS-001"):
        """Insert a zouzhe in executing state directly into the DB."""
        plan = json.dumps({
            "steps": ["implement"],
            "repo_path": self.repo_path,
            "acceptance_criteria": "tests pass",
        })
        db = sqlite3.connect(self.db_path)
        db.execute("""
            INSERT INTO zouzhe (id, title, description, state, plan, assigned_agent,
                                priority, timeout_sec, created_at, updated_at)
            VALUES (?, 'Test task', 'Test description', 'executing', ?, 'bingbu',
                    'normal', 600, strftime('%Y-%m-%dT%H:%M:%S','now'),
                    strftime('%Y-%m-%dT%H:%M:%S','now'))
        """, (zid, plan))
        db.commit()
        db.close()
        return zid

    def test_test_results_file_committed_on_push_for_review(self):
        """push-for-review auto-commits docs/test-results/<ZZ-ID>.md if it exists."""
        zid = self._insert_executing_zouzhe()

        # Create test results file in repo
        test_results_dir = os.path.join(self.repo_path, "docs", "test-results")
        os.makedirs(test_results_dir)
        results_file = os.path.join(test_results_dir, f"{zid}.md")
        Path(results_file).write_text(f"# Test Results for {zid}\n\nAll tests passed.\n")

        rc, out, _ = run_cli(
            "push-for-review", zid, "PR #1 https://github.com/test/repo/pull/1",
            "--skip-health-check",
            env=self.env,
        )
        data = parse_json(out)
        self.assertTrue(data.get("ok"), f"push-for-review failed: {data}")
        self.assertIn("test_results_note", data)
        # Either committed or already committed
        note_or_flag = data.get("test_results_note", "") + str(data.get("test_results_committed", ""))
        self.assertTrue(
            "committed" in note_or_flag.lower() or data.get("test_results_committed"),
            f"Expected commit confirmation, got: {data}",
        )

        # Verify the file is tracked in git
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            cwd=self.repo_path, capture_output=True, text=True,
        )
        self.assertIn(zid, git_log.stdout)

    def test_no_test_results_file_skipped_gracefully(self):
        """push-for-review proceeds fine when no test results file exists."""
        zid = self._insert_executing_zouzhe("ZZ-TEST-OBS-002")

        rc, out, _ = run_cli(
            "push-for-review", zid, "PR #2 https://github.com/test/repo/pull/2",
            "--skip-health-check",
            env=self.env,
        )
        data = parse_json(out)
        self.assertTrue(data.get("ok"), f"push-for-review failed: {data}")
        self.assertIn("test_results_note", data)
        self.assertIn("skipped", data["test_results_note"].lower())


class TestHealthGate(unittest.TestCase):
    """(d) push-for-review health gate block and --skip-health-check bypass."""

    def setUp(self):
        """Set up a temporary chaoting DB with an executing zouzhe."""
        self.tmpdir = tempfile.mkdtemp(prefix="chaoting_hg_")
        self.db_path = os.path.join(self.tmpdir, "chaoting.db")
        self.repo_path = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.repo_path)

        # Init chaoting DB using init_db SCHEMA directly
        _make_test_db(self.db_path)

        self.env = {
            "CHAOTING_DB_PATH": self.db_path,
            "CHAOTING_WORKSPACE": self.tmpdir,
            "CHAOTING_DIR": self.tmpdir,
            "OPENCLAW_AGENT_ID": "bingbu",
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_executing_zouzhe(self, zid="ZZ-TEST-HG-001"):
        plan = json.dumps({
            "steps": ["implement"],
            "repo_path": self.repo_path,
            "acceptance_criteria": "tests pass",
        })
        db = sqlite3.connect(self.db_path)
        db.execute("""
            INSERT INTO zouzhe (id, title, description, state, plan, assigned_agent,
                                priority, timeout_sec, created_at, updated_at)
            VALUES (?, 'Health gate test', 'Test', 'executing', ?, 'bingbu',
                    'normal', 600, strftime('%Y-%m-%dT%H:%M:%S','now'),
                    strftime('%Y-%m-%dT%H:%M:%S','now'))
        """, (zid, plan))
        db.commit()
        db.close()
        return zid

    def test_health_gate_blocks_on_inactive_service(self):
        """push-for-review with --service <inactive> should fail before state transition."""
        zid = self._insert_executing_zouzhe("ZZ-TEST-HG-001")
        rc, out, _ = run_cli(
            "push-for-review", zid, "PR #1 ...",
            "--service", "nonexistent-service-xyz-999",
            env=self.env,
        )
        data = parse_json(out)
        self.assertFalse(data["ok"])
        self.assertIn("Health gate FAILED", data["error"])
        self.assertIn("nonexistent-service-xyz-999", data["error"])

        # Verify state was NOT changed
        db = sqlite3.connect(self.db_path)
        row = db.execute("SELECT state FROM zouzhe WHERE id = ?", (zid,)).fetchone()
        db.close()
        self.assertEqual(row[0], "executing", "State should remain executing after health gate failure")

    def test_skip_health_check_bypasses_gate(self):
        """--skip-health-check allows push-for-review even with inactive service."""
        zid = self._insert_executing_zouzhe("ZZ-TEST-HG-002")
        rc, out, _ = run_cli(
            "push-for-review", zid, "PR #2 ...",
            "--service", "nonexistent-service-xyz-999",
            "--skip-health-check",
            env=self.env,
        )
        data = parse_json(out)
        self.assertTrue(data.get("ok"), f"Expected ok=True, got: {data}")
        self.assertIn("health_note", data)
        self.assertIn("skipped", data["health_note"].lower())

        # State should be pr_review
        db = sqlite3.connect(self.db_path)
        row = db.execute("SELECT state FROM zouzhe WHERE id = ?", (zid,)).fetchone()
        db.close()
        self.assertEqual(row[0], "pr_review", "State should be pr_review after bypass")

    def test_no_service_flag_skips_health_gate_silently(self):
        """push-for-review with no --service flag proceeds without health check."""
        zid = self._insert_executing_zouzhe("ZZ-TEST-HG-003")
        rc, out, _ = run_cli(
            "push-for-review", zid, "PR #3 ...",
            env=self.env,
        )
        data = parse_json(out)
        self.assertTrue(data.get("ok"), f"Expected ok=True, got: {data}")
        self.assertNotIn("health_note", data)

    def test_health_gate_passes_for_active_service(self):
        """push-for-review with --service <active-service> should pass health gate."""
        zid = self._insert_executing_zouzhe("ZZ-TEST-HG-004")
        # dbus.service is always active on systemd hosts
        rc, out, _ = run_cli(
            "push-for-review", zid, "PR #4 ...",
            "--service", "dbus.service",
            env=self.env,
        )
        data = parse_json(out)
        self.assertTrue(data.get("ok"), f"Expected ok=True for active service, got: {data}")
        self.assertIn("health_note", data)
        self.assertIn("passed", data["health_note"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)

