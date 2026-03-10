#!/usr/bin/env python3
"""tests/test_workspace_isolation.py — Workspace isolation tests.

Tests that multiple Chaoting workspaces are fully isolated:
  - Independent DB per workspace
  - Independent log/sentinel directories
  - Independent systemd service names
  - No data leakage between workspaces
  - Backward compatibility without CHAOTING_WORKSPACE

Run:
  python3 -m pytest tests/test_workspace_isolation.py -v
  # or
  python3 tests/test_workspace_isolation.py
"""

import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure src/ is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


class TestChaotingConfig(unittest.TestCase):
    """Unit tests for ChaotingConfig path derivation."""

    def setUp(self):
        # Remove env overrides that may leak across tests
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DIR", "CHAOTING_DB_PATH"]:
            os.environ.pop(k, None)

    def _get_config(self, **kwargs):
        """Import config fresh (avoids singleton cache between tests)."""
        if "config" in sys.modules:
            del sys.modules["config"]
        from config import ChaotingConfig
        return ChaotingConfig(**kwargs)

    # ── Backward compatibility ────────────────────────────────────────────

    def test_no_workspace_uses_chaoting_dir(self):
        """Without CHAOTING_WORKSPACE, data_dir == chaoting_dir."""
        cfg = self._get_config(chaoting_dir=str(REPO_ROOT))
        self.assertEqual(cfg.data_dir, str(REPO_ROOT))
        self.assertEqual(cfg.db_path, str(REPO_ROOT / "chaoting.db"))
        self.assertEqual(cfg.log_dir, str(REPO_ROOT / "logs"))
        self.assertEqual(cfg.sentinel_dir, str(REPO_ROOT / "sentinels"))

    def test_no_workspace_service_name(self):
        cfg = self._get_config(chaoting_dir=str(REPO_ROOT))
        self.assertEqual(cfg.service_name, "chaoting-dispatcher")

    # ── Workspace isolation ───────────────────────────────────────────────

    def test_workspace_data_dir_under_chaoting(self):
        """With workspace, data lives under {workspace}/.chaoting/."""
        with tempfile.TemporaryDirectory() as ws:
            cfg = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws)
            self.assertEqual(cfg.data_dir, str(Path(ws) / ".chaoting"))
            self.assertEqual(cfg.db_path, str(Path(ws) / ".chaoting" / "chaoting.db"))
            self.assertEqual(cfg.log_dir, str(Path(ws) / ".chaoting" / "logs"))
            self.assertEqual(cfg.sentinel_dir, str(Path(ws) / ".chaoting" / "sentinels"))

    def test_workspace_service_name_derived_from_basename(self):
        """Service name uses sanitized workspace basename."""
        with tempfile.TemporaryDirectory(suffix="-workspace-alpha") as ws:
            cfg = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws)
            expected_name = Path(ws).name.lower().replace(" ", "-").replace("_", "-")
            self.assertEqual(cfg.service_name, f"chaoting-dispatcher-{expected_name}")

    def test_two_workspaces_have_different_service_names(self):
        with tempfile.TemporaryDirectory(suffix="-ws-a") as ws_a, \
             tempfile.TemporaryDirectory(suffix="-ws-b") as ws_b:
            cfg_a = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws_a)
            cfg_b = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws_b)
            self.assertNotEqual(cfg_a.service_name, cfg_b.service_name)

    def test_two_workspaces_have_different_db_paths(self):
        with tempfile.TemporaryDirectory(suffix="-ws-x") as ws_x, \
             tempfile.TemporaryDirectory(suffix="-ws-y") as ws_y:
            cfg_x = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws_x)
            cfg_y = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws_y)
            self.assertNotEqual(cfg_x.db_path, cfg_y.db_path)
            self.assertNotEqual(cfg_x.log_dir, cfg_y.log_dir)
            self.assertNotEqual(cfg_x.sentinel_dir, cfg_y.sentinel_dir)

    def test_env_var_workspace(self):
        """CHAOTING_WORKSPACE env var is picked up by ChaotingConfig."""
        with tempfile.TemporaryDirectory() as ws:
            with patch.dict(os.environ, {"CHAOTING_WORKSPACE": ws}):
                if "config" in sys.modules:
                    del sys.modules["config"]
                from config import ChaotingConfig
                cfg = ChaotingConfig(chaoting_dir=str(REPO_ROOT))
                self.assertEqual(cfg.workspace, ws)
                self.assertIn(".chaoting", cfg.db_path)

    def test_ensure_dirs_creates_structure(self):
        with tempfile.TemporaryDirectory() as ws:
            cfg = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws)
            cfg.ensure_dirs()
            self.assertTrue(Path(cfg.data_dir).is_dir())
            self.assertTrue(Path(cfg.log_dir).is_dir())
            self.assertTrue(Path(cfg.sentinel_dir).is_dir())

    def test_write_config_json(self):
        with tempfile.TemporaryDirectory() as ws:
            cfg = self._get_config(chaoting_dir=str(REPO_ROOT), workspace=ws)
            cfg.ensure_dirs()
            path = cfg.write_config_json()
            self.assertTrue(Path(path).is_file())
            import json
            data = json.loads(Path(path).read_text())
            self.assertEqual(data["workspace"], ws)
            self.assertEqual(data["service_name"], cfg.service_name)


class TestChaotingLogWorkspace(unittest.TestCase):
    """Tests for chaoting_log.py LOGS_DIR respecting CHAOTING_WORKSPACE."""

    def setUp(self):
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def _reload_log_module(self):
        for m in list(sys.modules.keys()):
            if "chaoting_log" in m:
                del sys.modules[m]
        import chaoting_log
        return chaoting_log

    def test_without_workspace_logs_in_chaoting_dir(self):
        os.environ["CHAOTING_DIR"] = str(REPO_ROOT)
        log = self._reload_log_module()
        self.assertEqual(log.LOGS_DIR, str(REPO_ROOT / "logs"))

    def test_with_workspace_logs_under_dot_chaoting(self):
        with tempfile.TemporaryDirectory() as ws:
            os.environ["CHAOTING_WORKSPACE"] = ws
            log = self._reload_log_module()
            expected = str(Path(ws) / ".chaoting" / "logs")
            self.assertEqual(log.LOGS_DIR, expected)
            del os.environ["CHAOTING_WORKSPACE"]


class TestInitDbWorkspace(unittest.TestCase):
    """Tests that init_db.py creates DB in the right location."""

    def _run_init_db(self, env: dict) -> subprocess.CompletedProcess:
        merged = {**os.environ, **env}
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "src" / "init_db.py")],
            env=merged,
            capture_output=True,
            text=True,
        )

    def test_init_db_without_workspace_uses_chaoting_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_init_db({
                "CHAOTING_DIR": str(REPO_ROOT),
                "CHAOTING_DB_PATH": str(Path(tmp) / "test.db"),
            })
            # init_db uses CHAOTING_DB_PATH override when set
            self.assertEqual(result.returncode, 0)
            self.assertTrue((Path(tmp) / "test.db").is_file())

    def test_init_db_with_workspace_creates_db_in_dot_chaoting(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / ".chaoting").mkdir()
            result = self._run_init_db({
                "CHAOTING_DIR": str(REPO_ROOT),
                "CHAOTING_WORKSPACE": ws,
            })
            self.assertEqual(result.returncode, 0)
            self.assertTrue((Path(ws) / ".chaoting" / "chaoting.db").is_file())


class TestWorkspaceIsolationIntegration(unittest.TestCase):
    """Integration: 3 workspaces created, DB contents are isolated."""

    def _init_workspace(self, ws_path: str) -> str:
        """Initialize a workspace DB and return its path."""
        data_dir = Path(ws_path) / ".chaoting"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "chaoting.db"
        env = {**os.environ,
               "CHAOTING_DIR": str(REPO_ROOT),
               "CHAOTING_WORKSPACE": ws_path}
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "src" / "init_db.py")],
            env=env, check=True, capture_output=True,
        )
        return str(db_path)

    def test_three_workspaces_have_independent_dbs(self):
        """Three workspaces: inserting a zouzhe in one doesn't appear in others."""
        tmp_dirs = [tempfile.mkdtemp(suffix=f"-ws-{i}") for i in range(3)]
        try:
            db_paths = [self._init_workspace(d) for d in tmp_dirs]

            # Insert a unique row into workspace 0's DB
            conn0 = sqlite3.connect(db_paths[0])
            conn0.execute(
                "INSERT INTO zouzhe (id, title, state) VALUES (?, ?, ?)",
                ("TEST-ISOLATION-001", "Isolation test", "created")
            )
            conn0.commit()
            conn0.close()

            # Verify it does NOT appear in workspace 1 or 2
            for db_path in db_paths[1:]:
                conn = sqlite3.connect(db_path)
                row = conn.execute(
                    "SELECT id FROM zouzhe WHERE id = 'TEST-ISOLATION-001'"
                ).fetchone()
                conn.close()
                self.assertIsNone(row, f"Data leaked to {db_path}!")

        finally:
            for d in tmp_dirs:
                shutil.rmtree(d, ignore_errors=True)

    def test_three_workspaces_service_names_unique(self):
        """Verify 3 workspace service names are all distinct."""
        from config import ChaotingConfig
        names = []
        for suffix in ["-alpha", "-beta", "-gamma"]:
            with tempfile.TemporaryDirectory(suffix=suffix) as ws:
                cfg = ChaotingConfig(chaoting_dir=str(REPO_ROOT), workspace=ws)
                names.append(cfg.service_name)
        # All 3 should be unique
        self.assertEqual(len(names), len(set(names)))


class TestInstallShDryRun(unittest.TestCase):
    """Smoke test install.sh --dry-run in both modes."""

    def _run_install(self, extra_args: list[str]) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "OPENCLAW_CLI": os.environ.get(
                "OPENCLAW_CLI",
                str(next(
                    (Path(d) / "themachine"
                     for d in os.environ.get("PATH", "").split(":")
                     if (Path(d) / "themachine").is_file()),
                    "/usr/bin/false",
                ))
            ),
        }
        return subprocess.run(
            ["bash", str(REPO_ROOT / "install.sh"), "--dry-run"] + extra_args,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_dry_run_legacy_mode(self):
        """--dry-run without --workspace shows legacy service description."""
        result = self._run_install([])
        self.assertEqual(result.returncode, 0, result.stderr)
        # Legacy mode: service description is "Chaoting Dispatcher" (no workspace suffix)
        self.assertIn("Chaoting Dispatcher\n", result.stdout)
        self.assertNotIn("WORKSPACE:", result.stdout)

    def test_dry_run_workspace_mode(self):
        """--dry-run --workspace shows workspace-specific service name."""
        with tempfile.TemporaryDirectory(suffix="-test-ws") as ws:
            result = self._run_install(["--workspace", ws])
            self.assertEqual(result.returncode, 0, result.stderr)
            ws_name = Path(ws).name.lower()
            self.assertIn(ws_name, result.stdout)
            self.assertIn("WORKSPACE:", result.stdout)
            self.assertIn("chaoting-dispatcher-", result.stdout)


# ── Self-test runner ──────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestChaotingConfig,
        TestChaotingLogWorkspace,
        TestInitDbWorkspace,
        TestWorkspaceIsolationIntegration,
        TestInstallShDryRun,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
