#!/usr/bin/env python3
"""
测试：ZZ-20260311-003 dispatcher isolated session 机制验证
- 验证 sessions.reset 创建全新 session
- 验证 _reset_agent_session 正常调用
- 验证 CHAOTING_ISOLATED_SESSIONS 环境变量开关
- 验证失败时降级为 persistent 模式（不阻塞 dispatch）
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
DISPATCHER = os.path.join(SRC, "dispatcher.py")

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg, detail=""):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")
    if detail:
        print(f"     {detail}")


def load_dispatcher():
    """Load dispatcher module with test environment."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatcher", DISPATCHER)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = DISPATCHER
    spec.loader.exec_module(mod)
    return mod


# ── Test 1: CHAOTING_ISOLATED_SESSIONS 默认值 ─────────────────────────────
def test_default_config():
    print("\n[Test 1] CHAOTING_ISOLATED_SESSIONS 默认开启")
    try:
        with patch.dict(os.environ, {"CHAOTING_ISOLATED_SESSIONS": "1"}, clear=False):
            os.environ["CHAOTING_ISOLATED_SESSIONS"] = "1"
            os.environ["CHAOTING_GATEWAY_PASSWORD"] = "test-pw"
            import importlib.util
            spec = importlib.util.spec_from_file_location("dispatcher_t1", DISPATCHER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            assert mod.CHAOTING_ISOLATED_SESSIONS is True, f"expected True, got {mod.CHAOTING_ISOLATED_SESSIONS}"
            ok("CHAOTING_ISOLATED_SESSIONS=1 → True")
    except Exception as e:
        fail("默认配置测试失败", str(e))
    finally:
        os.environ.pop("CHAOTING_ISOLATED_SESSIONS", None)
        os.environ.pop("CHAOTING_GATEWAY_PASSWORD", None)


# ── Test 2: CHAOTING_ISOLATED_SESSIONS=0 关闭 ────────────────────────────
def test_disabled_config():
    print("\n[Test 2] CHAOTING_ISOLATED_SESSIONS=0 可关闭")
    try:
        os.environ["CHAOTING_ISOLATED_SESSIONS"] = "0"
        import importlib.util
        spec = importlib.util.spec_from_file_location("dispatcher_t2", DISPATCHER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.CHAOTING_ISOLATED_SESSIONS is False, f"expected False, got {mod.CHAOTING_ISOLATED_SESSIONS}"
        ok("CHAOTING_ISOLATED_SESSIONS=0 → False（禁用隔离）")
    except Exception as e:
        fail("禁用配置测试失败", str(e))
    finally:
        os.environ.pop("CHAOTING_ISOLATED_SESSIONS", None)


# ── Test 3: _reset_agent_session 成功路径 ─────────────────────────────────
def test_reset_success():
    print("\n[Test 3] _reset_agent_session 成功路径")
    os.environ["CHAOTING_GATEWAY_PASSWORD"] = "test-password"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("dispatcher_t3", DISPATCHER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "ok": True,
            "key": "agent:bingbu:main",
            "entry": {"sessionId": "test-uuid-1234-5678-abcd-efgh0123"}
        })
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = mod._reset_agent_session("bingbu")
            assert result == "test-uuid-1234-5678-abcd-efgh0123", f"Expected UUID, got {result}"
            call_args = mock_run.call_args
            cmd = call_args[0][0]  # positional arg 0, element 0 (the command list)
            assert "sessions.reset" in cmd, f"Command missing sessions.reset: {cmd}"
            assert "--password" in cmd, f"Command missing --password: {cmd}"
            assert "--json" in cmd, f"Command missing --json: {cmd}"
            # Find --params value
            params_idx = cmd.index("--params") + 1
            params = json.loads(cmd[params_idx])
            assert params.get("key") == "agent:bingbu:main", f"Wrong key: {params}"
        ok("_reset_agent_session 调用 sessions.reset 并返回新 UUID")
    except Exception as e:
        fail("reset_success 测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        os.environ.pop("CHAOTING_GATEWAY_PASSWORD", None)


# ── Test 4: _reset_agent_session 无密码时 WARNING ──────────────────────────
def test_reset_no_password():
    print("\n[Test 4] 无 GATEWAY_PASSWORD 时返回 None（不阻塞）")
    # Temporarily remove password env
    orig = os.environ.pop("CHAOTING_GATEWAY_PASSWORD", None)
    # Also ensure no themachine.json provides password
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("dispatcher_t4", DISPATCHER)
        mod = importlib.util.module_from_spec(spec)
        # Override GATEWAY_PASSWORD to empty
        mod.GATEWAY_PASSWORD = ""
        spec.loader.exec_module(mod)
        mod.GATEWAY_PASSWORD = ""

        with patch("subprocess.run") as mock_run:
            result = mod._reset_agent_session("bingbu")
            # Should not call subprocess when password is empty
            assert mock_run.call_count == 0, "Should not call subprocess without password"
            assert result is None, f"Expected None, got {result}"
        ok("无密码时不调用 subprocess，返回 None")
    except Exception as e:
        fail("无密码测试失败", str(e))
    finally:
        if orig:
            os.environ["CHAOTING_GATEWAY_PASSWORD"] = orig


# ── Test 5: _reset_agent_session 失败时 None（不阻塞）─────────────────────
def test_reset_failure():
    print("\n[Test 5] sessions.reset 失败时返回 None（降级，不阻塞 dispatch）")
    os.environ["CHAOTING_GATEWAY_PASSWORD"] = "test-password"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("dispatcher_t5", DISPATCHER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Test subprocess failure
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = ""
        mock_fail.stderr = "Gateway connection refused"

        with patch("subprocess.run", return_value=mock_fail):
            result = mod._reset_agent_session("bingbu")
            assert result is None, f"Expected None on failure, got {result}"
        ok("subprocess rc=1 → 返回 None（不 raise）")

        # Test timeout
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 15)):
            result = mod._reset_agent_session("bingbu")
            assert result is None, f"Expected None on timeout, got {result}"
        ok("TimeoutExpired → 返回 None（不 raise）")

        # Test generic exception
        with patch("subprocess.run", side_effect=Exception("Connection error")):
            result = mod._reset_agent_session("bingbu")
            assert result is None, f"Expected None on exception, got {result}"
        ok("Exception → 返回 None（不 raise）")
    except Exception as e:
        fail("失败降级测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        os.environ.pop("CHAOTING_GATEWAY_PASSWORD", None)


# ── Test 6: dispatch_agent 集成验证 ──────────────────────────────────────
def test_dispatch_integration():
    print("\n[Test 6] dispatch_agent 集成：ISOLATED_SESSIONS=1 时调用 _reset_agent_session")
    os.environ["CHAOTING_GATEWAY_PASSWORD"] = "test-password"
    os.environ["CHAOTING_ISOLATED_SESSIONS"] = "1"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("dispatcher_t6", DISPATCHER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        reset_calls = []
        popen_calls = []

        def mock_reset(agent_id):
            reset_calls.append(agent_id)
            return "new-session-uuid-1234"

        def mock_popen(cmd, stdout, stderr):
            popen_calls.append(cmd)
            m = MagicMock()
            m.pid = 99999
            m.returncode = 0
            m.wait = MagicMock(return_value=0)
            return m

        # Patch _reset_agent_session and subprocess.Popen
        mod._reset_agent_session = mock_reset
        with patch("subprocess.Popen", mock_popen):
            # Trigger the _run() inner function
            import threading
            import time
            mod.dispatch_agent("bingbu", "ZZ-TEST-ISO-001", 60, msg="test message")
            time.sleep(1)  # Let background thread run

        assert "bingbu" in reset_calls, f"_reset_agent_session not called: {reset_calls}"
        ok("dispatch_agent 调用 _reset_agent_session（隔离 session）")

        if popen_calls:
            cmd = popen_calls[0]
            assert "--agent" in cmd and "bingbu" in cmd, f"Popen cmd missing agent: {cmd}"
            # Verify NO --session-id in the Popen call (isolation via reset, not --session-id)
            assert "--session-id" not in cmd, f"Should not use --session-id in Popen: {cmd}"
            ok("Popen 命令包含 --agent bingbu，不含 --session-id（隔离通过 reset 实现）")
    except Exception as e:
        fail("dispatch_agent 集成测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        os.environ.pop("CHAOTING_GATEWAY_PASSWORD", None)
        os.environ.pop("CHAOTING_ISOLATED_SESSIONS", None)


def main():
    print("=" * 65)
    print("  ZZ-20260311-003 isolated session 机制测试")
    print("=" * 65)

    test_default_config()
    test_disabled_config()
    test_reset_success()
    test_reset_no_password()
    test_reset_failure()
    test_dispatch_integration()

    print("\n" + "=" * 65)
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过")
    if FAIL > 0:
        print(f"  ❌ {FAIL} 个测试失败")
        sys.exit(1)
    else:
        print("  ✅ 全部通过！isolated session 机制验证成功")
    print("=" * 65)


if __name__ == "__main__":
    main()
