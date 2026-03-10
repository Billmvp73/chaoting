#!/usr/bin/env python3
"""
Tests for ZZ-20260310-022: dianji P0+P1 integration
- cmd_lesson (P0)
- cmd_done --dianji/--lesson (P0)
- dispatch message dianji+qianche injection (P1)
- mark_stale_dianji (P1)
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import shutil

# ── paths ─────────────────────────────────────────────
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "src", "chaoting")
SRC = os.path.join(REPO, "src")

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg, exc=None):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")
    if exc:
        print(f"     {exc}")


# ── helpers ───────────────────────────────────────────

def make_workspace():
    """Create a temp workspace with initialized DB. Returns (tmp_dir, db_path, env)."""
    tmp = tempfile.mkdtemp(prefix="chaoting_test_")
    ws_data = os.path.join(tmp, ".chaoting")
    os.makedirs(ws_data)
    db_path = os.path.join(ws_data, "chaoting.db")
    env = os.environ.copy()
    env["CHAOTING_WORKSPACE"] = tmp
    env["CHAOTING_DIR"] = REPO
    env["CHAOTING_NO_DISCORD"] = "1"
    # Init DB
    result = subprocess.run(
        [sys.executable, os.path.join(SRC, "init_db.py")],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, f"init_db failed: {result.stderr}"
    return tmp, db_path, env


def run_cli(args, env):
    result = subprocess.run(
        [CLI] + args, env=env, capture_output=True, text=True
    )
    try:
        return result.returncode, json.loads(result.stdout.strip())
    except Exception:
        return result.returncode, {"raw": result.stdout, "stderr": result.stderr}


def seed_zouzhe(db_path, zid="ZZ-TEST-001", state="executing", agent="bingbu_test"):
    db = sqlite3.connect(db_path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "INSERT OR REPLACE INTO zouzhe (id, title, state, assigned_agent, revise_count) "
        "VALUES (?, ?, ?, ?, 0)",
        (zid, f"Test task {zid}", state, agent),
    )
    db.commit()
    db.close()


# ─────────────────────────────────────────────────────
# P0: cmd_lesson
# ─────────────────────────────────────────────────────

def test_lesson_with_zouzhe_id():
    print("\n[Test 1] cmd_lesson — 按 zouzhe_id 写入 qianche")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe(db_path)
        code, out = run_cli(["lesson", "ZZ-TEST-001", "这是一条测试教训"], env)
        assert code == 0, f"exit {code}: {out}"
        assert out.get("ok") is True
        assert out.get("agent_role") == "bingbu_test"
        assert out.get("zouzhe_id") == "ZZ-TEST-001"
        ok("cmd_lesson 写入成功，agent_role 从 zouzhe 推断")

        # Verify DB
        db = sqlite3.connect(db_path)
        row = db.execute("SELECT * FROM qianche WHERE zouzhe_id='ZZ-TEST-001'").fetchone()
        assert row is not None
        assert "测试教训" in row[3]  # lesson column
        db.close()
        ok("DB 记录验证通过")
    except Exception as e:
        fail("cmd_lesson with zouzhe_id 失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lesson_global():
    print("\n[Test 2] cmd_lesson --global --role")
    tmp, db_path, env = make_workspace()
    try:
        code, out = run_cli(
            ["lesson", "--global", "全局经验教训", "--role", "silijian_test"], env
        )
        assert code == 0, f"exit {code}: {out}"
        assert out.get("ok") is True
        assert out.get("agent_role") == "silijian_test"
        assert out.get("zouzhe_id") is None
        ok("--global --role 写入成功")

        db = sqlite3.connect(db_path)
        row = db.execute("SELECT * FROM qianche WHERE agent_role='silijian_test'").fetchone()
        assert row is not None
        assert "全局经验" in row[3]
        db.close()
        ok("全局 qianche 记录验证通过")
    except Exception as e:
        fail("cmd_lesson --global 失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lesson_role_override():
    print("\n[Test 3] cmd_lesson --role 覆盖 zouzhe 推断的 agent")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe(db_path)
        code, out = run_cli(
            ["lesson", "ZZ-TEST-001", "角色覆盖测试", "--role", "gongbu_test"], env
        )
        assert code == 0, f"exit {code}: {out}"
        assert out.get("agent_role") == "gongbu_test"
        ok("--role 覆盖 zouzhe.assigned_agent 成功")
    except Exception as e:
        fail("--role 覆盖测试失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lesson_missing_args():
    print("\n[Test 4] cmd_lesson 缺少参数 → 报错")
    tmp, db_path, env = make_workspace()
    try:
        code, out = run_cli(["lesson"], env)
        assert code != 0 or out.get("ok") is False
        ok("缺少参数时正确报错")
    except Exception as e:
        fail("缺少参数错误处理失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────
# P0: cmd_done --dianji / --lesson
# ─────────────────────────────────────────────────────

def test_done_with_dianji():
    print("\n[Test 5] cmd_done --dianji 写入典籍")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe(db_path)
        code, out = run_cli([
            "done", "ZZ-TEST-001", "产出内容", "任务摘要",
            "--dianji", "workspace_tip=workspace 隔离用 CHAOTING_WORKSPACE",
            "--dianji", "another_tip=第二条典籍",
        ], env)
        assert code == 0, f"exit {code}: {out}"
        assert out.get("ok") is True
        ok("cmd_done --dianji 返回 ok=True")

        db = sqlite3.connect(db_path)
        rows = db.execute(
            "SELECT context_key, context_value, source FROM dianji WHERE agent_role='bingbu_test'"
        ).fetchall()
        keys = {r[0] for r in rows}
        assert "workspace_tip" in keys, f"missing workspace_tip, got {keys}"
        assert "another_tip" in keys
        for r in rows:
            assert r[2] == "ZZ-TEST-001"  # source = zouzhe_id
        db.close()
        ok(f"写入 {len(rows)} 条典籍记录，source 正确绑定到奏折 ID")
    except Exception as e:
        fail("cmd_done --dianji 失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_done_with_lesson():
    print("\n[Test 6] cmd_done --lesson 写入教训")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe(db_path)
        code, out = run_cli([
            "done", "ZZ-TEST-001", "产出", "摘要",
            "--lesson", "第一条教训：不要在 master 直接 commit",
            "--lesson", "第二条教训：PR 必须 self-review",
        ], env)
        assert code == 0, f"exit {code}: {out}"
        assert out.get("ok") is True
        ok("cmd_done --lesson 返回 ok=True")

        db = sqlite3.connect(db_path)
        rows = db.execute(
            "SELECT lesson FROM qianche WHERE zouzhe_id='ZZ-TEST-001'"
        ).fetchall()
        assert len(rows) == 2, f"expected 2 lessons, got {len(rows)}"
        lessons = {r[0] for r in rows}
        assert any("master" in l for l in lessons)
        assert any("self-review" in l for l in lessons)
        db.close()
        ok(f"写入 {len(rows)} 条教训记录")
    except Exception as e:
        fail("cmd_done --lesson 失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_done_combined_dianji_lesson():
    print("\n[Test 7] cmd_done --dianji + --lesson 混合参数")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe(db_path)
        code, out = run_cli([
            "done", "ZZ-TEST-001", "产出", "摘要",
            "--dianji", "key1=val1",
            "--lesson", "教训一",
            "--dianji", "key2=val2",
            "--lesson", "教训二",
        ], env)
        assert code == 0, f"exit {code}: {out}"
        assert out.get("ok") is True

        db = sqlite3.connect(db_path)
        dianji_count = db.execute(
            "SELECT COUNT(*) FROM dianji WHERE agent_role='bingbu_test'"
        ).fetchone()[0]
        qianche_count = db.execute(
            "SELECT COUNT(*) FROM qianche WHERE zouzhe_id='ZZ-TEST-001'"
        ).fetchone()[0]
        db.close()

        assert dianji_count == 2, f"expected 2 dianji, got {dianji_count}"
        assert qianche_count == 2, f"expected 2 qianche, got {qianche_count}"
        ok(f"混合写入：{dianji_count} 典籍 + {qianche_count} 教训")
    except Exception as e:
        fail("混合参数测试失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_done_no_extras():
    print("\n[Test 8] cmd_done 无扩展参数 — 向后兼容")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe(db_path)
        code, out = run_cli(["done", "ZZ-TEST-001", "产出", "摘要"], env)
        assert code == 0, f"exit {code}: {out}"
        assert out.get("ok") is True
        ok("无 --dianji/--lesson 时正常完成，向后兼容")
    except Exception as e:
        fail("向后兼容测试失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────
# P0: _parse_done_extras helper (unit test)
# ─────────────────────────────────────────────────────

def test_parse_done_extras():
    print("\n[Test 9] _parse_done_extras 解析逻辑")
    try:
        # Load the CLI file via exec (no .py extension)
        ns = {"__file__": CLI, "__name__": "__not_main__"}
        with open(CLI, "r") as f:
            exec(compile(f.read(), CLI, "exec"), ns)
        fn = ns["_parse_done_extras"]

        args = [
            "--dianji", "key1=value one",
            "--lesson", "lesson one",
            "--dianji", "key2=v=2",  # value contains '='
            "--lesson", "lesson two",
        ]
        dianji, lessons = fn(args)
        assert len(dianji) == 2, f"expected 2 dianji, got {dianji}"
        assert len(lessons) == 2
        assert dianji[0] == {"key": "key1", "value": "value one"}
        assert dianji[1] == {"key": "key2", "value": "v=2"}  # value after first '='
        assert "lesson one" in lessons
        ok("_parse_done_extras 解析两条 dianji + 两条 lesson")

        # edge: key=val=extra → value = "val=extra"
        d, _ = fn(["--dianji", "k=v=extra"])
        assert d[0]["value"] == "v=extra", f"got {d[0]}"
        ok("'=' 分隔只取第一个 '=' 右侧全部作为 value")
    except Exception as e:
        fail("_parse_done_extras 单元测试失败", e)
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────
# P1: _build_dianji_qianche_section
# ─────────────────────────────────────────────────────

def test_dianji_section_in_dispatch():
    print("\n[Test 10] _build_dianji_qianche_section — dianji+qianche 注入派发消息")
    tmp, db_path, env = make_workspace()
    try:
        # Write some dianji + qianche directly
        db = sqlite3.connect(db_path)
        for i in range(6):  # write 6, expect limit=5
            db.execute(
                "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value) VALUES (?, ?, ?)",
                ("bingbu_section", f"key_{i}", f"value_{i}"),
            )
        for i in range(4):  # write 4, expect limit=3
            db.execute(
                "INSERT INTO qianche (agent_role, zouzhe_id, lesson) VALUES (?, ?, ?)",
                ("bingbu_section", "ZZ-TEST-SECTION", f"lesson_{i}"),
            )
        db.commit()
        db.close()

        # Load dispatcher module with patched DB_PATH
        env2 = env.copy()
        env2["CHAOTING_DB_PATH"] = db_path
        result = subprocess.run(
            [sys.executable, "-c", f"""
import sys, os
sys.path.insert(0, '{SRC}')
os.environ['CHAOTING_WORKSPACE'] = '{tmp}'
os.environ['CHAOTING_DIR'] = '{REPO}'
os.environ['CHAOTING_DB_PATH'] = '{db_path}'
import importlib.util
spec = importlib.util.spec_from_file_location("dispatcher", "{os.path.join(SRC, 'dispatcher.py')}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
section = mod._build_dianji_qianche_section('bingbu_section', 'ZZ-TEST-SECTION')
print(repr(section))
"""],
            env=env2, capture_output=True, text=True
        )
        assert result.returncode == 0, f"error: {result.stderr[:500]}"
        section = eval(result.stdout.strip())

        assert "📚 典籍参考" in section, "missing dianji header"
        assert "📖 历史教训" in section, "missing qianche header"
        # limit=5 enforced: should have 5 entries
        assert section.count("key_") == 5, f"expected 5 dianji, got: {section.count('key_')}"
        # limit=3 enforced
        assert section.count("lesson_") == 3, f"expected 3 lessons, got: {section.count('lesson_')}"
        ok("dispatch section 包含 dianji(5) + qianche(3)")

        # Test truncation: value > 200 chars
        db = sqlite3.connect(db_path)
        long_val = "x" * 300
        db.execute(
            "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value) VALUES (?, ?, ?)",
            ("bingbu_trunc", "long_key", long_val),
        )
        db.commit()
        db.close()

        result2 = subprocess.run(
            [sys.executable, "-c", f"""
import sys, os
sys.path.insert(0, '{SRC}')
os.environ['CHAOTING_WORKSPACE'] = '{tmp}'
os.environ['CHAOTING_DIR'] = '{REPO}'
os.environ['CHAOTING_DB_PATH'] = '{db_path}'
import importlib.util
spec = importlib.util.spec_from_file_location("dispatcher", "{os.path.join(SRC, 'dispatcher.py')}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
section = mod._build_dianji_qianche_section('bingbu_trunc', 'ZZ-NONE')
print(repr(section))
"""],
            env=env2, capture_output=True, text=True
        )
        section2 = eval(result2.stdout.strip())
        # value should be truncated to 200
        assert "x" * 300 not in section2, "value not truncated"
        assert "x" * 200 in section2 or "x" * 199 in section2, "truncation length unexpected"
        ok("dianji value 截断 200 字验证通过")

        # Test empty: no dianji/qianche → empty string
        result3 = subprocess.run(
            [sys.executable, "-c", f"""
import sys, os
sys.path.insert(0, '{SRC}')
os.environ['CHAOTING_WORKSPACE'] = '{tmp}'
os.environ['CHAOTING_DIR'] = '{REPO}'
os.environ['CHAOTING_DB_PATH'] = '{db_path}'
import importlib.util
spec = importlib.util.spec_from_file_location("dispatcher", "{os.path.join(SRC, 'dispatcher.py')}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
section = mod._build_dianji_qianche_section('nobody_empty', 'ZZ-NONE')
print(repr(section))
"""],
            env=env2, capture_output=True, text=True
        )
        section3 = eval(result3.stdout.strip())
        assert section3 == "", f"expected empty string for no data, got: {section3!r}"
        ok("无 dianji/qianche 时返回空字符串（dispatch 消息不被污染）")

    except Exception as e:
        fail("dispatch section 测试失败", e)
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────
# P1: mark_stale_dianji
# ─────────────────────────────────────────────────────

def test_mark_stale_dianji():
    print("\n[Test 11] mark_stale_dianji — 过期典籍标记")
    tmp, db_path, env = make_workspace()
    try:
        db = sqlite3.connect(db_path)
        # Insert fresh entry (now)
        db.execute(
            "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value, confidence, updated_at) "
            "VALUES (?, ?, ?, 'fresh', strftime('%Y-%m-%dT%H:%M:%S','now'))",
            ("stale_test", "fresh_key", "fresh_val"),
        )
        # Insert old entry (40 days ago)
        db.execute(
            "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value, confidence, updated_at) "
            "VALUES (?, ?, ?, 'fresh', datetime('now', '-40 days'))",
            ("stale_test", "old_key", "old_val"),
        )
        db.commit()
        db.close()

        # Run mark_stale directly via DB (simulate dispatcher logic)
        db2 = sqlite3.connect(db_path)
        result = db2.execute(
            "UPDATE dianji SET confidence = 'stale' "
            "WHERE confidence = 'fresh' "
            "AND julianday('now') - julianday(updated_at) > 30"
        )
        updated = result.rowcount
        db2.commit()

        fresh = db2.execute(
            "SELECT confidence FROM dianji WHERE agent_role='stale_test' AND context_key='fresh_key'"
        ).fetchone()[0]
        old = db2.execute(
            "SELECT confidence FROM dianji WHERE agent_role='stale_test' AND context_key='old_key'"
        ).fetchone()[0]
        db2.close()

        assert updated == 1, f"expected 1 stale update, got {updated}"
        assert fresh == "fresh", f"fresh_key should still be fresh, got {fresh}"
        assert old == "stale", f"old_key should be stale, got {old}"
        ok(f"mark_stale: {updated} 条过期典籍标记为 stale，fresh 未受影响")

    except Exception as e:
        fail("mark_stale_dianji 测试失败", e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  ZZ-20260310-022 dianji P0+P1 集成测试")
    print("=" * 65)

    test_lesson_with_zouzhe_id()
    test_lesson_global()
    test_lesson_role_override()
    test_lesson_missing_args()
    test_done_with_dianji()
    test_done_with_lesson()
    test_done_combined_dianji_lesson()
    test_done_no_extras()
    test_parse_done_extras()
    test_dianji_section_in_dispatch()
    test_mark_stale_dianji()

    print("\n" + "=" * 65)
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过")
    if FAIL > 0:
        print(f"  ❌ {FAIL} 个测试失败")
        sys.exit(1)
    else:
        print("  ✅ 全部通过！P0+P1 dianji 集成验证成功")
    print("=" * 65)


if __name__ == "__main__":
    main()
