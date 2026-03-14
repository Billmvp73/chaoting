"""Unit tests for chaoting observability commands: logs, health, push-for-review gating."""

import importlib.util
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Allow importing src/chaoting (a script without .py extension)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
_CHAOTING_PATH = os.path.join(_REPO_ROOT, "src", "chaoting")


def _load_chaoting():
    """Load src/chaoting as a Python module (no .py extension — use SourceFileLoader)."""
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("chaoting_cli", _CHAOTING_PATH)
    spec = importlib.util.spec_from_loader("chaoting_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    os.environ.setdefault("CHAOTING_NO_DISCORD", "1")
    spec.loader.exec_module(mod)
    return mod


def _run_cmd(mod, fn, args):
    """Call a chaoting cmd function, capture stdout as parsed JSON."""
    buf = io.StringIO()
    with patch("sys.stdout", buf), patch("sys.exit", side_effect=SystemExit):
        try:
            fn(args)
        except SystemExit:
            pass
    raw = buf.getvalue().strip()
    return json.loads(raw)


class TestCmdLogs(unittest.TestCase):
    """Tests for cmd_logs()."""

    def setUp(self):
        self.mod = _load_chaoting()

    @patch("subprocess.run")
    def test_logs_basic_returns_lines(self, mock_run):
        """cmd_logs returns JSON with lines array and count."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="line1\nline2\nline3\n", stderr=""
        )
        result = _run_cmd(self.mod, self.mod.cmd_logs, ["my-service"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["service"], "my-service")
        self.assertEqual(result["lines"], ["line1", "line2", "line3"])
        self.assertEqual(result["count"], 3)

    @patch("subprocess.run")
    def test_logs_tail_flag_passes_n(self, mock_run):
        """--tail N passes -n N to journalctl."""
        mock_run.return_value = MagicMock(returncode=0, stdout="x\n", stderr="")
        _run_cmd(self.mod, self.mod.cmd_logs, ["svc", "--tail", "10"])
        call_args = mock_run.call_args[0][0]
        self.assertIn("-n", call_args)
        self.assertIn("10", call_args)

    @patch("subprocess.run")
    def test_logs_grep_flag_passes_g(self, mock_run):
        """--grep PATTERN passes -g PATTERN to journalctl."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(self.mod, self.mod.cmd_logs, ["svc", "--grep", "ERROR"])
        call_args = mock_run.call_args[0][0]
        self.assertIn("-g", call_args)
        self.assertIn("ERROR", call_args)

    @patch("subprocess.run")
    def test_logs_since_flag_appends_ago(self, mock_run):
        """--since Xs passes --since=Xs ago to journalctl."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(self.mod, self.mod.cmd_logs, ["svc", "--since", "60s"])
        call_args = mock_run.call_args[0][0]
        self.assertTrue(any("60s ago" in a for a in call_args))

    @patch("subprocess.run")
    def test_logs_default_tail_is_50(self, mock_run):
        """Default tail when not specified is 50."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(self.mod, self.mod.cmd_logs, ["svc"])
        call_args = mock_run.call_args[0][0]
        self.assertIn("-n", call_args)
        idx = call_args.index("-n")
        self.assertEqual(call_args[idx + 1], "50")


class TestCmdHealth(unittest.TestCase):
    """Tests for cmd_health()."""

    def setUp(self):
        self.mod = _load_chaoting()

    @patch("subprocess.run")
    def test_health_active_service(self, mock_run):
        """Returns {ok:true, active:true, status:'active'} for an active service."""
        mock_run.return_value = MagicMock(returncode=0, stdout="active\n", stderr="")
        result = _run_cmd(self.mod, self.mod.cmd_health, ["my-service"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["active"])
        self.assertEqual(result["status"], "active")
        self.assertIsNone(result["endpoint_ok"])

    @patch("subprocess.run")
    def test_health_inactive_service(self, mock_run):
        """Returns {ok:false, active:false} for an inactive service."""
        mock_run.return_value = MagicMock(returncode=3, stdout="inactive\n", stderr="")
        result = _run_cmd(self.mod, self.mod.cmd_health, ["dead-service"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["active"])
        self.assertEqual(result["status"], "inactive")

    @patch("subprocess.run")
    def test_health_with_port_endpoint_ok(self, mock_run):
        """endpoint_ok is True when both systemctl and curl succeed."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="active\n", stderr=""),   # systemctl
            MagicMock(returncode=0, stdout="{}", stderr=""),          # curl
        ]
        result = _run_cmd(self.mod, self.mod.cmd_health, ["svc", "--port", "8080"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["endpoint_ok"])

    @patch("subprocess.run")
    def test_health_with_port_endpoint_fail(self, mock_run):
        """ok is False when service is active but endpoint is unreachable."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="active\n", stderr=""),    # systemctl
            MagicMock(returncode=7, stdout="", stderr="refused"),     # curl /health
            MagicMock(returncode=7, stdout="", stderr="refused"),     # curl / fallback
        ]
        result = _run_cmd(self.mod, self.mod.cmd_health, ["svc", "--port", "9999"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["endpoint_ok"])


class TestPushForReviewGating(unittest.TestCase):
    """Tests for push-for-review health check gating and --skip-health-check."""

    def setUp(self):
        self.mod = _load_chaoting()

    @patch("subprocess.run")
    def test_push_blocks_on_unhealthy_service(self, mock_run):
        """push-for-review with --service blocks when service is inactive."""
        mock_run.return_value = MagicMock(returncode=3, stdout="inactive\n", stderr="")
        result = _run_cmd(self.mod, self.mod.cmd_push_for_review, [
            "ZZ-20260314-TEST", "PR #1: https://github.com/...",
            "--service", "dead-service",
        ])
        self.assertFalse(result["ok"])
        self.assertIn("Health check failed", result["error"])
        self.assertIn("dead-service", result["error"])
        self.assertIn("--skip-health-check", result["error"])

    @patch("subprocess.run")
    def test_push_skip_health_check_bypasses(self, mock_run):
        """push-for-review with --skip-health-check does not call systemctl."""
        # Simulate: systemctl would say inactive, but we skip the check.
        # DB returns "not found" to short-circuit without a real DB.
        mock_run.return_value = MagicMock(returncode=3, stdout="inactive\n", stderr="")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None  # not found

        result = _run_cmd(
            self.mod,
            lambda a: self.mod.cmd_push_for_review.__wrapped__(a)  # noqa: ignore
            if hasattr(self.mod.cmd_push_for_review, "__wrapped__")
            else (
                patch.object(self.mod, "get_db", return_value=mock_db).__enter__()
                and self.mod.cmd_push_for_review(a)
            ),
            [],
        ) if False else None  # placeholder

        # Simpler: directly patch get_db
        buf = io.StringIO()
        with patch("sys.stdout", buf), \
             patch("sys.exit", side_effect=SystemExit), \
             patch.object(self.mod, "get_db", return_value=mock_db):
            try:
                self.mod.cmd_push_for_review([
                    "ZZ-20260314-TEST", "PR #1: https://github.com/...",
                    "--service", "dead-service",
                    "--skip-health-check",
                ])
            except SystemExit:
                pass

        result = json.loads(buf.getvalue().strip())
        # Should fail with "not found", NOT with "Health check failed"
        self.assertNotIn("Health check failed", result.get("error", ""))
        # systemctl should NOT have been called
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
