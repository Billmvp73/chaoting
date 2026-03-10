#!/usr/bin/env python3
"""
dianji (典籍) 表 CRUD 激活验证
ZZ-20260310-020 — bingbu

验证项：
1. INSERT 写入典籍记录
2. SELECT 读取/查询
3. UPSERT 覆盖更新（ON CONFLICT DO UPDATE）
4. DELETE 删除记录
5. workspace DB 路径隔离（CHAOTING_WORKSPACE env 生效）
6. chaoting context CLI 命令端到端
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
import shutil

# ── 路径配置 ────────────────────────────────────────────
CHAOTING_DIR = os.environ.get("CHAOTING_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WORKSPACE = os.environ.get("CHAOTING_WORKSPACE", "")
_DATA_DIR = os.path.join(_WORKSPACE, ".chaoting") if _WORKSPACE else CHAOTING_DIR
DB_PATH = os.environ.get("CHAOTING_DB_PATH", os.path.join(_DATA_DIR, "chaoting.db"))
CLI = os.path.join(CHAOTING_DIR, "src", "chaoting")

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


def get_db(path=None):
    p = path or DB_PATH
    db = sqlite3.connect(p, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db


# ── Test 1: 直接 DB — INSERT ────────────────────────────
def test_insert(db):
    print("\n[Test 1] INSERT 写入典籍记录")
    try:
        db.execute(
            "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value, source) "
            "VALUES (?, ?, ?, ?)",
            ("bingbu_test", "test_key_1", "test_value_1", "ZZ-20260310-020"),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM dianji WHERE agent_role=? AND context_key=?",
            ("bingbu_test", "test_key_1"),
        ).fetchone()
        assert row is not None, "row not found after INSERT"
        assert row["context_value"] == "test_value_1"
        assert row["source"] == "ZZ-20260310-020"
        ok("INSERT + SELECT 验证通过")
    except Exception as e:
        fail(f"INSERT 失败: {e}")


# ── Test 2: UPSERT 覆盖更新 ────────────────────────────
def test_upsert(db):
    print("\n[Test 2] UPSERT 覆盖更新")
    try:
        db.execute(
            "INSERT INTO dianji (agent_role, context_key, context_value, source, updated_at) "
            "VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%S','now')) "
            "ON CONFLICT(agent_role, context_key) DO UPDATE SET "
            "context_value = excluded.context_value, source = excluded.source, "
            "confidence = 'fresh', updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')",
            ("bingbu_test", "test_key_1", "updated_value", "ZZ-UPSERT-TEST"),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM dianji WHERE agent_role=? AND context_key=?",
            ("bingbu_test", "test_key_1"),
        ).fetchone()
        assert row["context_value"] == "updated_value", f"expected updated_value, got {row['context_value']}"
        assert row["confidence"] == "fresh"
        assert row["source"] == "ZZ-UPSERT-TEST"
        ok("UPSERT 覆盖 context_value + confidence='fresh' 验证通过")
    except Exception as e:
        fail(f"UPSERT 失败: {e}")


# ── Test 3: 多记录 INSERT + 按 agent_role 查询 ─────────
def test_multi_insert_query(db):
    print("\n[Test 3] 多记录 INSERT + 按 agent_role 查询")
    try:
        for i in range(3):
            db.execute(
                "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value) VALUES (?, ?, ?)",
                ("bingbu_test", f"multi_key_{i}", f"multi_val_{i}"),
            )
        db.commit()
        rows = db.execute(
            "SELECT * FROM dianji WHERE agent_role=? AND context_key LIKE 'multi_key_%'",
            ("bingbu_test",),
        ).fetchall()
        assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"
        keys = {r["context_key"] for r in rows}
        assert keys == {"multi_key_0", "multi_key_1", "multi_key_2"}
        ok(f"多记录查询通过，共 {len(rows)} 条")
    except Exception as e:
        fail(f"多记录查询失败: {e}")


# ── Test 4: DELETE ─────────────────────────────────────
def test_delete(db):
    print("\n[Test 4] DELETE 删除记录")
    try:
        db.execute(
            "DELETE FROM dianji WHERE agent_role=?",
            ("bingbu_test",),
        )
        db.commit()
        rows = db.execute(
            "SELECT * FROM dianji WHERE agent_role=?",
            ("bingbu_test",),
        ).fetchall()
        assert len(rows) == 0, f"expected 0 rows after DELETE, got {len(rows)}"
        ok("DELETE 验证通过，所有测试记录已清理")
    except Exception as e:
        fail(f"DELETE 失败: {e}")


# ── Test 5: workspace DB 路径隔离 ─────────────────────
def test_workspace_isolation():
    print("\n[Test 5] workspace DB 路径隔离")
    tmp_dir = tempfile.mkdtemp(prefix="chaoting_dianji_test_")
    try:
        ws_data = os.path.join(tmp_dir, ".chaoting")
        os.makedirs(ws_data)
        tmp_db = os.path.join(ws_data, "chaoting.db")

        # Init schema in temp DB
        env = os.environ.copy()
        env["CHAOTING_WORKSPACE"] = tmp_dir
        result = subprocess.run(
            [sys.executable, os.path.join(CHAOTING_DIR, "src", "init_db.py")],
            env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, f"init_db failed: {result.stderr}"

        # Insert into temp DB
        tmp_conn = get_db(tmp_db)
        tmp_conn.execute(
            "INSERT INTO dianji (agent_role, context_key, context_value) VALUES (?, ?, ?)",
            ("ws_test", "ws_key", "ws_value"),
        )
        tmp_conn.commit()
        row = tmp_conn.execute(
            "SELECT * FROM dianji WHERE agent_role='ws_test'"
        ).fetchone()
        assert row["context_value"] == "ws_value"
        tmp_conn.close()

        # Verify main DB is NOT polluted
        main_conn = get_db()
        row_main = main_conn.execute(
            "SELECT * FROM dianji WHERE agent_role='ws_test'"
        ).fetchone()
        assert row_main is None, "workspace isolation FAILED — ws_test found in main DB"
        main_conn.close()

        ok("workspace DB 隔离验证通过（temp workspace 不污染主 DB）")
    except Exception as e:
        fail(f"workspace 隔离验证失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 6: chaoting context CLI 端到端 ───────────────
def test_cli_context():
    print("\n[Test 6] chaoting context CLI 端到端")
    try:
        env = os.environ.copy()
        if _WORKSPACE:
            env["CHAOTING_WORKSPACE"] = _WORKSPACE

        # Write via CLI
        result = subprocess.run(
            [CLI, "context", "bingbu_cli_test", "cli_key", "cli_value", "--source", "ZZ-20260310-020"],
            env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, f"CLI returned {result.returncode}: {result.stdout} {result.stderr}"

        import json
        out = json.loads(result.stdout.strip())
        assert out["ok"] is True
        assert out["agent_role"] == "bingbu_cli_test"
        assert out["context_key"] == "cli_key"
        ok("CLI write 通过")

        # Verify via DB
        db = get_db()
        row = db.execute(
            "SELECT * FROM dianji WHERE agent_role='bingbu_cli_test' AND context_key='cli_key'"
        ).fetchone()
        assert row is not None
        assert row["context_value"] == "cli_value"
        assert row["source"] == "ZZ-20260310-020"
        db.close()
        ok("CLI write → DB read 验证通过")

        # UPSERT via CLI
        result2 = subprocess.run(
            [CLI, "context", "bingbu_cli_test", "cli_key", "updated_via_cli"],
            env=env, capture_output=True, text=True
        )
        assert result2.returncode == 0
        db2 = get_db()
        row2 = db2.execute(
            "SELECT * FROM dianji WHERE agent_role='bingbu_cli_test' AND context_key='cli_key'"
        ).fetchone()
        assert row2["context_value"] == "updated_via_cli"
        assert row2["confidence"] == "fresh"
        db2.close()
        ok("CLI UPSERT 更新验证通过")

        # Cleanup
        db3 = get_db()
        db3.execute("DELETE FROM dianji WHERE agent_role='bingbu_cli_test'")
        db3.commit()
        db3.close()
        ok("测试记录已清理")

    except Exception as e:
        fail(f"CLI 端到端测试失败: {e}")
        import traceback
        traceback.print_exc()


# ── Test 7: confidence 字段默认值和更新 ───────────────
def test_confidence(db):
    print("\n[Test 7] confidence 字段默认值与 UPSERT 重置")
    try:
        db.execute(
            "INSERT OR REPLACE INTO dianji (agent_role, context_key, context_value, confidence) "
            "VALUES (?, ?, ?, 'stale')",
            ("bingbu_conf_test", "conf_key", "conf_val"),
        )
        db.commit()
        row = db.execute(
            "SELECT confidence FROM dianji WHERE agent_role='bingbu_conf_test'"
        ).fetchone()
        assert row["confidence"] == "stale"

        # UPSERT should reset confidence to fresh
        db.execute(
            "INSERT INTO dianji (agent_role, context_key, context_value, confidence, updated_at) "
            "VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%S','now')) "
            "ON CONFLICT(agent_role, context_key) DO UPDATE SET "
            "context_value = excluded.context_value, "
            "confidence = 'fresh', updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')",
            ("bingbu_conf_test", "conf_key", "new_val", "ignored"),
        )
        db.commit()
        row2 = db.execute(
            "SELECT confidence FROM dianji WHERE agent_role='bingbu_conf_test'"
        ).fetchone()
        assert row2["confidence"] == "fresh", f"expected fresh, got {row2['confidence']}"
        db.execute("DELETE FROM dianji WHERE agent_role='bingbu_conf_test'")
        db.commit()
        ok("confidence stale → UPSERT → fresh 验证通过")
    except Exception as e:
        fail(f"confidence 字段测试失败: {e}")


# ── Main ───────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Chaoting dianji (典籍) CRUD 激活验证")
    print(f"  DB: {DB_PATH}")
    print(f"  Workspace: {_WORKSPACE or '(legacy mode)'}")
    print("=" * 60)

    db = get_db()

    test_insert(db)
    test_upsert(db)
    test_multi_insert_query(db)
    test_delete(db)
    test_confidence(db)

    db.close()

    test_workspace_isolation()
    test_cli_context()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过")
    if FAIL > 0:
        print(f"  ❌ {FAIL} 个测试失败")
        sys.exit(1)
    else:
        print("  ✅ 全部通过！dianji 典籍机制验证成功")
    print("=" * 60)


if __name__ == "__main__":
    main()
