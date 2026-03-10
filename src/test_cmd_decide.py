#!/usr/bin/env python3
"""
测试：ZZ-20260310-030 chaoting decide 命令
- approve / reject / revise 三条路径
- 权限检查（仅 silijian）
- 状态校验（仅 escalated）
- CAS 状态转换、liuzhuan 记录
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
    tmp = tempfile.mkdtemp(prefix="test_decide_")
    ws_data = os.path.join(tmp, ".chaoting")
    os.makedirs(ws_data)
    env = os.environ.copy()
    env["CHAOTING_WORKSPACE"] = tmp
    env["CHAOTING_DIR"] = REPO
    env["CHAOTING_NO_DISCORD"] = "1"
    result = subprocess.run(
        [sys.executable, os.path.join(SRC, "init_db.py")],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, f"init_db failed: {result.stderr}"
    db_path = os.path.join(ws_data, "chaoting.db")
    return tmp, db_path, env


def seed_escalated(db_path, zid="ZZ-TEST-ESC-001", agent="bingbu",
                   exec_revise_count=2, revise_history=None, plan=None):
    db = sqlite3.connect(db_path)
    plan_json = json.dumps(plan or {"steps": ["执行步骤1"], "target_agent": agent},
                           ensure_ascii=False)
    rh = json.dumps(revise_history or [], ensure_ascii=False) if revise_history is not None else None
    db.execute("""
        INSERT OR REPLACE INTO zouzhe
        (id, title, state, assigned_agent, revise_count, exec_revise_count,
         plan, plan_history, revise_history, planning_version)
        VALUES (?, ?, 'escalated', ?, 0, ?, ?, NULL, ?, 3)
    """, (zid, f"Test: {zid}", agent, exec_revise_count, plan_json, rh))
    db.commit()
    db.close()


def run_decide(zid, verdict, reason, env, agent_id="silijian"):
    e = {**env, "OPENCLAW_AGENT_ID": agent_id}
    result = subprocess.run(
        [CLI, "decide", zid, verdict, reason],
        env=e, capture_output=True, text=True
    )
    try:
        out = json.loads(result.stdout.strip())
    except Exception:
        out = {"ok": False, "_raw": result.stdout[:200], "_err": result.stderr[:200]}
    return out, result.returncode


def get_zouzhe(db_path, zid):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM zouzhe WHERE id=?", (zid,)).fetchone()
    db.close()
    return dict(row) if row else None


def get_liuzhuan(db_path, zid):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT * FROM liuzhuan WHERE zouzhe_id=? ORDER BY id", (zid,)).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Test 1: approve 路径 ───────────────────────────────────────────────────────
def test_approve():
    print("\n[Test 1] decide approve → escalated → executing")
    tmp, db_path, env = make_workspace()
    try:
        seed_escalated(db_path)
        out, rc = run_decide("ZZ-TEST-ESC-001", "approve", "裁决准奏：方案可行，直接执行", env)
        assert out.get("ok") is True, f"approve failed: {out}"
        assert out.get("state") == "executing", f"state should be executing: {out}"
        assert out.get("verdict") == "approve"
        ok(f"approve 返回 ok=True, state=executing")

        zh = get_zouzhe(db_path, "ZZ-TEST-ESC-001")
        assert zh["state"] == "executing", f"DB state: {zh['state']}"
        assert zh["dispatched_at"] is None, "dispatched_at should be NULL"
        ok("DB state=executing, dispatched_at=NULL（等待 dispatcher 派发）")

        lz = get_liuzhuan(db_path, "ZZ-TEST-ESC-001")
        decide_lz = [l for l in lz if l["action"] == "decide_approve"]
        assert decide_lz, f"no decide_approve liuzhuan: {lz}"
        assert decide_lz[0]["from_role"] == "silijian"
        ok(f"liuzhuan decide_approve 记录存在，from=silijian")
    except Exception as e:
        fail("approve 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 2: reject 路径 ───────────────────────────────────────────────────────
def test_reject():
    print("\n[Test 2] decide reject → escalated → failed")
    tmp, db_path, env = make_workspace()
    try:
        seed_escalated(db_path, "ZZ-TEST-ESC-002")
        out, rc = run_decide("ZZ-TEST-ESC-002", "reject", "裁决驳回：方案不可行", env)
        assert out.get("ok") is True, f"reject failed: {out}"
        assert out.get("state") == "failed"
        assert out.get("verdict") == "reject"
        ok("reject 返回 ok=True, state=failed")

        zh = get_zouzhe(db_path, "ZZ-TEST-ESC-002")
        assert zh["state"] == "failed", f"DB state: {zh['state']}"
        assert "裁决驳回" in (zh["error"] or ""), f"error field: {zh['error']}"
        ok("DB state=failed, error 字段含裁决理由")

        lz = get_liuzhuan(db_path, "ZZ-TEST-ESC-002")
        decide_lz = [l for l in lz if l["action"] == "decide_reject"]
        assert decide_lz, f"no decide_reject liuzhuan: {lz}"
        ok("liuzhuan decide_reject 记录存在")
    except Exception as e:
        fail("reject 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 3: revise 路径 ───────────────────────────────────────────────────────
def test_revise():
    print("\n[Test 3] decide revise → escalated → revising（中书省重新规划）")
    tmp, db_path, env = make_workspace()
    try:
        seed_escalated(db_path, "ZZ-TEST-ESC-003", exec_revise_count=2,
                       revise_history=[{"round": 2, "reason": "旧旨意", "revised_by": "silijian"}])
        out, rc = run_decide("ZZ-TEST-ESC-003", "revise", "司礼监裁决：需要全新方向", env)
        assert out.get("ok") is True, f"revise failed: {out}"
        assert out.get("state") == "revising"
        assert out.get("verdict") == "revise"
        assert out.get("exec_revise_count") == 3, f"exec_revise_count: {out}"
        ok("revise 返回 ok=True, state=revising, exec_revise_count=3")

        zh = get_zouzhe(db_path, "ZZ-TEST-ESC-003")
        assert zh["state"] == "revising", f"DB state: {zh['state']}"
        assert zh["plan"] is None, f"plan should be NULL: {zh['plan']}"
        assert zh["plan_history"] is None, f"plan_history should be NULL: {zh['plan_history']}"
        assert zh["revise_count"] == 0, f"revise_count should be 0: {zh['revise_count']}"
        assert zh["exec_revise_count"] == 3
        ok("DB state=revising, plan=NULL, plan_history=NULL, revise_count=0")

        # Verify planning_version incremented
        assert zh["planning_version"] == 4, f"planning_version should be 4: {zh['planning_version']}"
        ok(f"planning_version=4（从3+1）")

        # Verify revise_history updated
        rh = json.loads(zh["revise_history"])
        assert len(rh) == 2, f"revise_history should have 2 entries: {len(rh)}"
        assert rh[-1]["via"] == "decide_revise"
        assert rh[-1]["reason"] == "司礼监裁决：需要全新方向"
        ok(f"revise_history 新增 decide_revise 条目")

        lz = get_liuzhuan(db_path, "ZZ-TEST-ESC-003")
        decide_lz = [l for l in lz if l["action"] == "decide_revise"]
        assert decide_lz, f"no decide_revise liuzhuan: {lz}"
        assert decide_lz[0]["to_role"] == "zhongshu"
        ok("liuzhuan decide_revise 记录，to_role=zhongshu")
    except Exception as e:
        fail("revise 测试失败", str(e))
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 4: 权限检查 ──────────────────────────────────────────────────────────
def test_permission():
    print("\n[Test 4] 权限检查：非 silijian 调用应被拒绝")
    tmp, db_path, env = make_workspace()
    try:
        seed_escalated(db_path, "ZZ-TEST-ESC-004")
        for agent in ["bingbu", "zhongshu", "libu", ""]:
            out, rc = run_decide("ZZ-TEST-ESC-004", "approve", "测试", env, agent_id=agent)
            assert out.get("ok") is False, f"should fail for agent={agent!r}: {out}"
            assert "权限不足" in out.get("error", ""), f"error msg: {out.get('error')}"
        ok("bingbu/zhongshu/libu/空 均被权限拒绝")

        # silijian 应该成功
        out, rc = run_decide("ZZ-TEST-ESC-004", "approve", "silijian 准奏", env, agent_id="silijian")
        assert out.get("ok") is True, f"silijian should succeed: {out}"
        ok("silijian 可以成功执行")
    except Exception as e:
        fail("权限检查测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 5: 状态检查（非 escalated）───────────────────────────────────────────
def test_state_check():
    print("\n[Test 5] 状态检查：非 escalated 状态应被拒绝")
    tmp, db_path, env = make_workspace()
    try:
        for state in ["executing", "done", "failed", "revising", "planning"]:
            db = sqlite3.connect(db_path)
            db.execute("""
                INSERT OR REPLACE INTO zouzhe
                (id, title, state, assigned_agent, revise_count, exec_revise_count, planning_version)
                VALUES (?, ?, ?, 'bingbu', 0, 0, 1)
            """, (f"ZZ-TEST-STATE-{state}", f"state={state}", state))
            db.commit()
            db.close()

            out, rc = run_decide(f"ZZ-TEST-STATE-{state}", "approve", "测试", env)
            assert out.get("ok") is False, f"should fail for state={state}: {out}"
            error_msg = out.get("error", "")
            assert "escalated" in error_msg, f"error should mention escalated: {error_msg}"
        ok("executing/done/failed/revising/planning 均被状态拒绝")
    except Exception as e:
        fail("状态检查测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 6: 无效 verdict ─────────────────────────────────────────────────────
def test_invalid_verdict():
    print("\n[Test 6] 无效 verdict 应报错")
    tmp, db_path, env = make_workspace()
    try:
        seed_escalated(db_path, "ZZ-TEST-ESC-006")
        out, rc = run_decide("ZZ-TEST-ESC-006", "abstain", "测试", env)
        assert out.get("ok") is False
        assert "abstain" in out.get("error", "") or "无效" in out.get("error", "")
        ok("无效 verdict 'abstain' 被拒绝")
    except Exception as e:
        fail("无效 verdict 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 7: CAS 竞争保护 ──────────────────────────────────────────────────────
def test_cas():
    print("\n[Test 7] CAS 保护：状态被抢占后第二次 decide 应失败")
    tmp, db_path, env = make_workspace()
    try:
        seed_escalated(db_path, "ZZ-TEST-ESC-007")
        # First decide: approve
        out1, _ = run_decide("ZZ-TEST-ESC-007", "approve", "第一次裁决", env)
        assert out1.get("ok") is True, f"first decide failed: {out1}"
        # Second decide on same (now executing) zouzhe: should fail
        out2, _ = run_decide("ZZ-TEST-ESC-007", "reject", "第二次裁决", env)
        assert out2.get("ok") is False, f"second decide should fail: {out2}"
        ok("CAS 保护：同一奏折二次裁决被阻止")
    except Exception as e:
        fail("CAS 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Test 8: 参数不足报错 ─────────────────────────────────────────────────────
def test_usage():
    print("\n[Test 8] 参数不足时显示 usage")
    tmp, db_path, env = make_workspace()
    try:
        result = subprocess.run(
            [CLI, "decide"],
            env={**env, "OPENCLAW_AGENT_ID": "silijian"},
            capture_output=True, text=True
        )
        out = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
        assert out.get("ok") is False
        assert "usage" in out.get("error", "").lower() or "decide" in out.get("error", "")
        ok("参数不足时正确报错（含 usage 提示）")
    except Exception as e:
        fail("usage 测试失败", str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 65)
    print("  ZZ-20260310-030 chaoting decide 命令测试")
    print("=" * 65)

    test_approve()
    test_reject()
    test_revise()
    test_permission()
    test_state_check()
    test_invalid_verdict()
    test_cas()
    test_usage()

    print("\n" + "=" * 65)
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过")
    if FAIL > 0:
        print(f"  ❌ {FAIL} 个测试失败")
        sys.exit(1)
    else:
        print("  ✅ 全部通过！chaoting decide 命令实现验证成功")
    print("=" * 65)


if __name__ == "__main__":
    main()
