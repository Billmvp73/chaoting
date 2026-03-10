#!/usr/bin/env python3
"""
回归测试：ZZ-20260310-029 修复验证
- format_revising_message 路径选择在 emperor_revise + gate_reject 混合场景下的正确性
- cmd_revise 清空 plan_history（防止旧 nogo 污染路径判断）
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
CLI = os.path.join(SRC, "chaoting")
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


def make_workspace():
    tmp = tempfile.mkdtemp(prefix="chaoting_revising_test_")
    ws_data = os.path.join(tmp, ".chaoting")
    os.makedirs(ws_data)
    db_path = os.path.join(ws_data, "chaoting.db")
    env = os.environ.copy()
    env["CHAOTING_WORKSPACE"] = tmp
    env["CHAOTING_DIR"] = REPO
    result = subprocess.run(
        [sys.executable, os.path.join(SRC, "init_db.py")],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, f"init_db failed: {result.stderr}"
    return tmp, db_path, env


def get_format_revising_message(db_path, zouzhe_id, env):
    """Run format_revising_message via subprocess and return the result string."""
    result = subprocess.run(
        [sys.executable, "-c", f"""
import sys, os, json
sys.path.insert(0, '{SRC}')
os.environ['CHAOTING_WORKSPACE'] = '{os.path.dirname(os.path.dirname(db_path))}'
os.environ['CHAOTING_DIR'] = '{REPO}'
os.environ['CHAOTING_DB_PATH'] = '{db_path}'
import importlib.util
spec = importlib.util.spec_from_file_location("dispatcher", "{DISPATCHER}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import sqlite3
db = sqlite3.connect('{db_path}')
db.row_factory = sqlite3.Row
row = db.execute('SELECT * FROM zouzhe WHERE id=?', ('{zouzhe_id}',)).fetchone()
db.close()
msg = mod.format_revising_message(dict(row))
print(json.dumps(msg))
"""],
        env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, f"subprocess error: {result.stderr[:300]}"
    return json.loads(result.stdout.strip())


def seed_zouzhe_with_scenario(db_path, scenario):
    """Seed a zouzhe with the given scenario data."""
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        INSERT OR REPLACE INTO zouzhe
        (id, title, state, assigned_agent, revise_count, exec_revise_count,
         plan_history, revise_history, plan)
        VALUES (?, ?, 'revising', 'bingbu', ?, ?, ?, ?, ?)
    """, (
        scenario["id"],
        scenario.get("title", "Test task"),
        scenario.get("revise_count", 0),
        scenario.get("exec_revise_count", 0),
        json.dumps(scenario.get("plan_history", []), ensure_ascii=False) if scenario.get("plan_history") else None,
        json.dumps(scenario.get("revise_history", []), ensure_ascii=False) if scenario.get("revise_history") else None,
        json.dumps(scenario.get("plan", {}), ensure_ascii=False) if scenario.get("plan") else None,
    ))
    db.commit()
    db.close()


# ── Test 1: 纯 gate_reject（无 emperor_revise）→ 路径 A ─────────────────────
def test_pure_gate_reject():
    print("\n[Test 1] 纯 gate_reject（无 emperor_revise）→ 路径 A")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe_with_scenario(db_path, {
            "id": "ZZ-TEST-GR-001",
            "revise_count": 1,
            "exec_revise_count": 0,
            "plan_history": [
                {
                    "round": 1,
                    "plan": {"steps": ["原步骤"]},
                    "votes": [
                        {"jishi": "jishi_risk", "vote": "nogo", "reason": "缺少备份步骤"},
                        {"jishi": "jishi_tech", "vote": "go", "reason": "技术可行"},
                    ],
                }
            ],
            "revise_history": [],
        })
        msg = get_format_revising_message(db_path, "ZZ-TEST-GR-001", env)
        assert "门下省封驳" in msg, f"expected 门下省封驳 in msg, got: {msg[:200]}"
        assert "缺少备份步骤" in msg, f"nogo reason missing: {msg[:200]}"
        assert "皇上旨意" not in msg, f"unexpected 皇上旨意: {msg[:200]}"
        ok("纯 gate_reject → 路径 A，jishi 封驳意见正确传达")
    except Exception as e:
        fail("纯 gate_reject 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 2: 纯 emperor_revise（无 gate_reject）→ 路径 B ──────────────────────
def test_pure_emperor_revise():
    print("\n[Test 2] 纯 emperor_revise（无 gate_reject，plan_history=[]）→ 路径 B")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe_with_scenario(db_path, {
            "id": "ZZ-TEST-ER-001",
            "revise_count": 0,
            "exec_revise_count": 1,
            "plan_history": [],  # emperor_revise clears plan_history
            "revise_history": [
                {"round": 1, "reason": "皇上旨意：请加入备份步骤", "revised_by": "silijian", "revised_at": "2026-03-10T00:00:00"},
            ],
        })
        msg = get_format_revising_message(db_path, "ZZ-TEST-ER-001", env)
        assert "上旨返工" in msg or "皇上旨意" in msg, f"expected 皇上旨意 in msg, got: {msg[:200]}"
        assert "皇上旨意：请加入备份步骤" in msg, f"emperor reason missing: {msg[:200]}"
        ok("纯 emperor_revise → 路径 B，皇上旨意正确传达")
    except Exception as e:
        fail("纯 emperor_revise 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 3: 核心场景 — emperor_revise 后 gate_reject → 路径 A ─────────────────
def test_gate_reject_after_emperor_revise():
    print("\n[Test 3] ⭐ 核心场景：emperor_revise × 2 后 gate_reject → 路径 A（含皇上背景）")
    tmp, db_path, env = make_workspace()
    try:
        seed_zouzhe_with_scenario(db_path, {
            "id": "ZZ-TEST-MIXED-001",
            "revise_count": 1,
            "exec_revise_count": 2,
            "plan_history": [  # gate_reject 后 archive 到 plan_history
                {
                    "round": 1,
                    "plan": {"steps": ["清理 memory/：删除过时条目"]},
                    "votes": [
                        {"jishi": "jishi_risk", "vote": "nogo", "reason": "Step1 删除前缺备份：需先 cp -r memory/ memory.bak-timestamp/"},
                        {"jishi": "jishi_tech", "vote": "go", "reason": "准奏"},
                    ],
                }
            ],
            "revise_history": [
                {"round": 1, "reason": "皇上旨意：创建 silijian memory 文件", "revised_by": "silijian", "revised_at": "2026-03-10T00:00:00"},
                {"round": 2, "reason": "皇上旨意：同时创建中书省 memory", "revised_by": "silijian", "revised_at": "2026-03-10T00:01:00"},
            ],
        })
        msg = get_format_revising_message(db_path, "ZZ-TEST-MIXED-001", env)

        # 必须包含：jishi 封驳意见（主要）
        assert "门下省封驳" in msg, f"missing 门下省封驳: {msg[:300]}"
        assert "Step1 删除前缺备份" in msg, f"nogo reason missing: {msg[:300]}"
        assert "memory.bak-timestamp" in msg, f"specific fix missing: {msg[:300]}"

        # 必须包含：皇上旨意作为背景（次要）
        assert "皇上" in msg, f"missing emperor context: {msg[:300]}"

        # 不应出现"上旨返工"作为主消息标题
        assert "上旨返工（第" not in msg[:50], f"should not start with emperor revise: {msg[:100]}"

        ok("gate_reject 意见出现在消息中（主要）")
        ok("皇上旨意出现在消息中（背景）")
        ok("消息不以'上旨返工'开头（路径 B 被正确排除）")
    except Exception as e:
        fail("核心混合场景测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 4: stale plan_history（phase1 gate_reject 后 done → emperor_revise）→ 路径 B
def test_stale_plan_history_cleared_by_emperor_revise():
    print("\n[Test 4] ⭐ stale plan_history 清空验证：emperor_revise 后 plan_history=NULL → 路径 B")
    tmp, db_path, env = make_workspace()
    try:
        # Scenario: phase1 had gate_rejects, then done, then emperor_revise
        # After cmd_revise fix: plan_history is cleared to NULL
        seed_zouzhe_with_scenario(db_path, {
            "id": "ZZ-TEST-STALE-001",
            "revise_count": 0,
            "exec_revise_count": 1,
            "plan_history": None,  # cleared by cmd_revise (the fix)
            "revise_history": [
                {"round": 1, "reason": "皇上新旨意：全新任务方向", "revised_by": "silijian", "revised_at": "2026-03-10T00:00:00"},
            ],
        })
        msg = get_format_revising_message(db_path, "ZZ-TEST-STALE-001", env)
        assert "上旨返工" in msg or "皇上旨意" in msg, f"expected Path B: {msg[:200]}"
        assert "皇上新旨意：全新任务方向" in msg, f"emperor reason missing: {msg[:200]}"
        ok("plan_history=NULL 时正确走路径 B（emperor_revise message）")
    except Exception as e:
        fail("stale plan_history 场景测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 5: cmd_revise 清空 plan_history ─────────────────────────────────────
def test_cmd_revise_clears_plan_history():
    print("\n[Test 5] cmd_revise 清空 plan_history")
    tmp, db_path, env = make_workspace()
    try:
        # Seed a done zouzhe with stale plan_history
        db = sqlite3.connect(db_path)
        db.execute("""
            INSERT INTO zouzhe
            (id, title, state, assigned_agent, revise_count, exec_revise_count, plan_history, output, summary)
            VALUES ('ZZ-TEST-CLR-001', 'Test', 'done', 'bingbu', 2, 0,
                    '[{"round":1,"votes":[{"vote":"nogo"}]}]',
                    '产出', '摘要')
        """)
        db.commit()
        db.close()

        # Run cmd_revise
        result = subprocess.run(
            [CLI, "revise", "ZZ-TEST-CLR-001", "皇上下旨重做"],
            env={**env, "OPENCLAW_AGENT_ID": "silijian"},
            capture_output=True, text=True
        )
        out = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
        assert out.get("ok") is True, f"revise failed: {result.stdout} {result.stderr}"

        # Verify plan_history is cleared
        db2 = sqlite3.connect(db_path)
        row = db2.execute("SELECT plan_history, exec_revise_count FROM zouzhe WHERE id='ZZ-TEST-CLR-001'").fetchone()
        db2.close()

        plan_history_val = row[0]  # should be NULL or '[]'
        exec_count = row[1]

        assert plan_history_val is None or plan_history_val == '[]' or plan_history_val == 'null', \
            f"plan_history not cleared: {plan_history_val!r}"
        assert exec_count == 1, f"exec_revise_count should be 1, got {exec_count}"
        ok(f"cmd_revise 后 plan_history={plan_history_val!r}（已清空）")
        ok(f"exec_revise_count={exec_count}（正确）")
    except Exception as e:
        fail("cmd_revise 清空 plan_history 测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 6: ZZ-028 重现场景回归 ───────────────────────────────────────────────
def test_zz028_regression():
    print("\n[Test 6] ZZ-028 完整场景回归测试")
    tmp, db_path, env = make_workspace()
    try:
        # Replicate ZZ-028 state at gate_reject round 1
        seed_zouzhe_with_scenario(db_path, {
            "id": "ZZ-TEST-028-REG",
            "title": "研究各省各部 Memory 系统方案（回归）",
            "revise_count": 1,
            "exec_revise_count": 2,  # 2 emperor_revises happened
            "plan_history": [
                {
                    "round": 1,
                    "plan": {"steps": [
                        "创建中书省 MEMORY.md",
                        "司礼监 MEMORY.md 改造",
                        "司礼监 memory-chaoting.md",
                        "清理司礼监现有 memory/：审查 2026-03-08.md~10.md，删除/修正过时系统状态",
                        "各部门激活优先级建议",
                    ]},
                    "votes": [
                        {"jishi": "jishi_risk", "vote": "nogo", "reason": "Step4删除司礼监memory文件缺备份：需先cp -r memory/ memory.bak-timestamp/，再用trash或移至.archive/清理，禁止无备份直接删除。"},
                        {"jishi": "jishi_tech", "vote": "go", "reason": "准奏"},
                    ],
                }
            ],
            "revise_history": [
                {"round": 1, "reason": "返工方向调整：优先激活 OpenClaw memory", "revised_by": "silijian", "revised_at": "2026-03-10T00:00:00"},
                {"round": 2, "reason": "在原有成果基础上追加：司礼监也要做同样的结构化 memory", "revised_by": "silijian", "revised_at": "2026-03-10T00:01:00"},
            ],
        })

        msg = get_format_revising_message(db_path, "ZZ-TEST-028-REG", env)

        # The bug: before fix, zhongshu received Path B (emperor revise) and NEVER saw jishi_risk's nogo
        # After fix: should receive Path A (gate_reject) with jishi_risk's nogo prominently shown

        assert "memory.bak-timestamp" in msg, \
            f"❌ jishi_risk 备份要求未出现！fix 失败。msg={msg[:300]}"
        assert "Step4" in msg or "禁止无备份直接删除" in msg, \
            f"❌ 具体 nogo 原因未出现。msg={msg[:300]}"
        assert "门下省封驳" in msg, \
            f"❌ 路径 A 消息头未出现。msg={msg[:300]}"

        ok("jishi_risk 封驳原因（memory 备份要求）出现在消息中")
        ok("消息走路径 A（门下省封驳），不走路径 B（皇上旨意）")

        # Verify emperor context is still included as background
        if "皇上" in msg:
            ok("皇上旨意背景附加（作为上下文，不覆盖 jishi 封驳）")
        else:
            ok("（无皇上背景附加 — 可接受）")

    except Exception as e:
        fail("ZZ-028 回归测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 65)
    print("  ZZ-20260310-029 format_revising_message 路径修复测试")
    print("=" * 65)

    test_pure_gate_reject()
    test_pure_emperor_revise()
    test_gate_reject_after_emperor_revise()
    test_stale_plan_history_cleared_by_emperor_revise()
    test_cmd_revise_clears_plan_history()
    test_zz028_regression()

    print("\n" + "=" * 65)
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过")
    if FAIL > 0:
        print(f"  ❌ {FAIL} 个测试失败")
        sys.exit(1)
    else:
        print("  ✅ 全部通过！ZZ-029 路径修复验证成功")
    print("=" * 65)


if __name__ == "__main__":
    main()
