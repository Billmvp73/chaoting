# Bug 报告：中书省循环分配失效 (ZZ-20260310-012)

> 报告日期：2026-03-10  
> 报告部门：兵部（bingbu）  
> 依据奏折：ZZ-20260310-013  
> 严重级别：**CRITICAL** — 影响核心流转引擎，导致皇上旨意被静默丢弃

---

## 一、事故摘要

皇上通过 `chaoting revise` 明确指示：**Revert 工部代码，改由兵部用 Agent Teams 重写**。但 dispatcher 在后续两次（第 3 轮、第 4 轮）仍将任务派发给工部，导致无效执行循环。

**根本原因**：`dispatcher.py` 和 `chaoting pull` 各自存在独立代码 Bug，共同导致中书省在重新规划时**无法获取**皇上的返工原因。中书省不是故意无视旨意，而是从未收到这条旨意。

---

## 二、事故时间线（精确还原）

| 时间 | 事件 | 说明 |
|------|------|------|
| 05:00:56 | ZZ-20260310-012 创建 | Workspace 隔离化部署需求 |
| 05:00:59 | dispatcher → zhongshu | 初次规划 |
| 05:01:19 | zhongshu → menxia | 方案提交（target_agent: gongbu） |
| 05:01:19 | 派发 jishi_tech/jishi_risk | 审核 |
| 05:01:49 | **menxia 封驳第1次** | 进入 revising（plan_history 更新）|
| 05:01:54 | dispatcher → zhongshu | **[路径 A]** `format_revising_message` 正确传递封驳原因 |
| 05:02:09 | zhongshu 重新规划 | 修正 install.sh 路径问题 |
| 05:02:24 | menxia 准奏 | 进入 executing |
| 05:02:34 | dispatcher → **gongbu** | ✅ 正常：工部执行 |
| 05:08:37 | gongbu 完成第1轮 | workspace 隔离化部署 |
| 05:08:40 | → silijian 通知 done | |
| 05:10:39 | **silijian 返工第1次（exec_revise）** | `chaoting revise` 调用，revise_history 写入：「扩展任务：兵部通过 Agent Teams 进行代码 Review」|
| 05:10:40 | dispatcher → zhongshu | **[路径 B — BUG]** `format_revising_message` 仅传封驳历史，NOT revise reason |
| 05:11:05 | zhongshu 重新规划 | ⚠️ 未收到旨意，仍用 target_agent: gongbu |
| 05:11:15 | menxia 准奏 | |
| 05:11:26 | dispatcher → **gongbu** | ❌ 工部再次执行（应为兵部）|
| 05:15:04 | gongbu 完成第2轮 | |
| 05:17:00 | **silijian 返工第2次（exec_revise）** | `chaoting revise`，revise_history：「Revert 工部代码 + 兵部用 Agent Teams 重写」|
| 05:17:01 | dispatcher → zhongshu | **[路径 B — BUG 再次触发]** 同上 |
| 05:17:18 | zhongshu 重新规划 | ⚠️ 仍未收到旨意，target_agent: gongbu（第3次！）|
| 05:17:32 | menxia 准奏 | |
| 05:17:43 | dispatcher → **gongbu** | ❌ 工部第3次执行 |
| 05:18:23 | gongbu 完成第3轮 | 无效执行，PR#32 仍是工部的代码 |

**总结**：皇上两次发出明确旨意，两次被静默丢弃。

---

## 三、根本原因分析

### 两条路径的本质区别

状态 `revising` 可以由**两种不同机制**触发：

| 路径 | 触发机制 | 原因存储位置 | `format_revising_message` 处理 |
|------|---------|------------|-------------------------------|
| **路径 A** | menxia 封驳（jishi nogo 投票）| `plan_history[-1].votes` | ✅ 正确读取并传递 |
| **路径 B** | silijian/皇上调用 `chaoting revise` | `revise_history[-1].reason` | ❌ **完全未读取** |

---

### RC-1（主因）：`dispatcher.py` `format_revising_message()` 不读 `revise_history`

**文件**：`src/dispatcher.py`  
**函数**：`format_revising_message()`  
**行号**：第 404–443 行

```python
def format_revising_message(zouzhe) -> str:
    # 第406行 — 只读 plan_history（jishi 封驳轮次）
    history = json.loads(zouzhe["plan_history"]) if zouzhe["plan_history"] else []
    #                              ^^^^^^^^^^^^
    #                              BUG: 只有路径A（jishi封驳）的数据
    #                              路径B（皇上revise）的数据在 revise_history，从未读取

    # 第407–413行 — 如果 plan_history 为空，返回通用消息，同样无 revise reason
    if not history:
        return (
            f"📜 奏折 {zouzhe['id']} 被门下省封驳\n\n"
            ...
        )

    # 第415行 — last_round 是 jishi 封驳最后一轮，非皇上旨意
    last_round = history[-1]
    ...
    # revise_history 中的 "Revert 工部代码 + 兵部用 Agent Teams 重写" 永远不会出现在此消息中
```

**实际影响**：当状态因 `chaoting revise`（路径 B）进入 "revising" 时，dispatcher 发给中书省的通知只包含 jishi 的旧封驳意见（或空通知），**完全不包含皇上/silijian 的指示**。

---

### RC-2（次因）：`chaoting pull` 不返回 `revise_history`

**文件**：`src/chaoting`  
**函数**：`cmd_pull()`  
**行号**：第 662–677 行

```python
def cmd_pull(args):
    ...
    zouzhe = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "state": row["state"],
        "priority": row["priority"],
        "plan": json.loads(row["plan"]) if row["plan"] else None,
        # ❌ 缺失：revise_history、exec_revise_count、plan_history
    }
```

即使中书省注意到需要查询返工历史，调用 `chaoting pull` 也获取不到 `revise_history`。这是双重封锁的第二层——即使 dispatcher 的通知修了，zhongshu 也无法通过 pull 自行查阅。

---

### RC-3（辅因）：zhongshu SOUL.md 缺乏"返工旨意优先级最高"规则

**文件**：`examples/souls/zhongshu.md`

当前工作流程只规定：
> "若被门下省封驳，查看封驳意见并修改方案后重新提交"

**缺失规定**：
- 若是皇上/silijian 发起的 `exec_revise`（非封驳），其旨意优先级高于原方案
- 若旨意中指定了新的 `target_agent`，必须按照旨意修改
- `revise_history` 中的最新原因是最高优先级指令，不得被 jishi 意见或原方案覆盖

---

### RC-4（结构性问题）：`chaoting plan` 没有验证 `target_agent` 一致性

**文件**：`src/chaoting`  
**函数**：`cmd_plan()`  
**行号**：第 711–715 行

```python
target_agent = plan.get("target_agent")
if not target_agent:
    out({"ok": False, "error": "plan must include target_agent"}, ok=False)
# 验证只检查存在性，不检查是否与 revise_history 的指令一致
```

即使 `revise_history` 明确说"用 bingbu"，中书省提交 `target_agent: gongbu` 时系统也会接受，没有任何警告。

---

## 四、修复方案

### Fix 1（必须修复 — dispatcher.py）

**修改 `format_revising_message()` 优先读取 `revise_history`**

**文件**：`src/dispatcher.py`，行 404  
**估时**：30 分钟

```python
def format_revising_message(zouzhe) -> str:
    """Build the revising dispatch message for zhongshu.

    路径 A（menxia 封驳）：从 plan_history 读取 jishi 意见
    路径 B（皇上/silijian exec_revise）：从 revise_history 读取返工原因（优先级最高）
    """
    # --- 新增：先检查 revise_history（路径 B 优先）---
    revise_hist = json.loads(zouzhe.get("revise_history") or "[]")
    exec_revise_count = zouzhe.get("exec_revise_count") or 0

    if revise_hist and exec_revise_count > 0:
        latest = revise_hist[-1]
        revise_reason = latest.get("reason", "(无原因)")
        revised_by = latest.get("revised_by", "silijian")
        revised_at = latest.get("revised_at", "")

        # 同时包含 jishi 封驳历史（如有）
        plan_history = json.loads(zouzhe.get("plan_history") or "[]")
        previous_plan_section = ""
        if plan_history:
            last_plan = plan_history[-1].get("plan")
            if last_plan:
                previous_plan_section = (
                    f"\n\n【上轮规划（已作废）】\n"
                    f"```json\n{json.dumps(last_plan, ensure_ascii=False, indent=2)}\n```"
                )

        return (
            f"⚠️ 【上旨返工（第 {exec_revise_count} 次）】\n"
            f"来自：{revised_by}  时间：{revised_at}\n\n"
            f"【皇上旨意（最高优先级）】\n"
            f"{revise_reason}\n\n"
            f"⚠️ 以上返工旨意必须完整体现在新方案中。若旨意指定了新的执行部门或方法，"
            f"必须在 target_agent/steps 中遵循，不得沿用原方案。"
            f"{previous_plan_section}\n\n"
            f"请制定新方案后提交:\n"
            f"  {CHAOTING_CLI} pull {zouzhe['id']}\n"
            f"  {CHAOTING_CLI} plan {zouzhe['id']} '{{new_plan_json}}'"
        )

    # --- 原有逻辑（路径 A：jishi 封驳）---
    history = json.loads(zouzhe["plan_history"]) if zouzhe["plan_history"] else []
    if not history:
        return (
            f"📜 奏折 {zouzhe['id']} 被门下省封驳\n\n"
            f"请修改方案后重新提交:\n"
            f"  {CHAOTING_CLI} pull {zouzhe['id']}\n"
            f"  {CHAOTING_CLI} plan {zouzhe['id']} '{{new_plan_json}}'"
        )
    # ... 原有 jishi 封驳处理代码保持不变 ...
```

---

### Fix 2（必须修复 — src/chaoting）

**`cmd_pull` 返回值新增 `revise_history` 和 `exec_revise_count`**

**文件**：`src/chaoting`，行 662  
**估时**：15 分钟

```python
def cmd_pull(args):
    ...
    zouzhe = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "state": row["state"],
        "priority": row["priority"],
        "plan": json.loads(row["plan"]) if row["plan"] else None,
        # ✅ 新增：
        "exec_revise_count": row["exec_revise_count"] or 0,
        "revise_history": json.loads(row["revise_history"]) if row["revise_history"] else [],
    }
```

---

### Fix 3（强烈建议 — zhongshu SOUL.md）

**新增返工旨意处理规范**

**文件**：`examples/souls/zhongshu.md`，工作流程第 4 条后新增：

```markdown
## 返工旨意处理规范

⚠️ **当收到返工通知（exec_revise_count > 0）时，必须遵循以下优先级**：

1. **最高优先级：皇上/司礼监的返工旨意（revise reason）**
   - 完整阅读通知中的【皇上旨意】部分
   - `chaoting pull` 返回的 `revise_history` 中有详细原因
   
2. **若旨意中指定了新的执行部门**：
   - `target_agent` **必须**更新为旨意指定的部门
   - 不得沿用原方案的 `target_agent`
   - 示例：旨意说"由兵部（bingbu）用 Agent Teams 重写" → `target_agent: bingbu`
   
3. **若旨意中指定了新的实现方式**：
   - `steps` 必须反映新的实现方式
   - 原方案的 steps 作废

4. **低优先级：jishi 的封驳意见**（在不与返工旨意冲突的前提下仍需遵守）

> 助记：旨意 > 封驳意见 > 原方案。任何时候皇上旨意是最终指令。
```

---

### Fix 4（可选但推荐 — src/chaoting）

**`cmd_plan` 在有 `revise_history` 时警告 `target_agent` 不一致**

**文件**：`src/chaoting`，`cmd_plan()` 约行 711  
**估时**：30 分钟

```python
# 在 target_agent 校验之后、状态更新之前，新增：
revise_hist = json.loads(row["revise_history"]) if row["revise_history"] else []
exec_revise_count = row.get("exec_revise_count") or 0
if revise_hist and exec_revise_count > 0:
    latest_reason = revise_hist[-1].get("reason", "")
    # 简单启发式：如果旨意中明确提到了某个部门 ID 但 target_agent 不是该部门，发警告
    # （不阻断，只写入日志和 liuzhuan 供 silijian 审查）
    known_agents = {"bingbu", "gongbu", "hubu", "libu", "xingbu", "libu_hr"}
    mentioned_agents = {a for a in known_agents if a in latest_reason}
    if mentioned_agents and target_agent not in mentioned_agents:
        log.warning(
            "WARN: revise_history mentions %s but target_agent=%s. "
            "zhongshu may have ignored revise instruction.",
            mentioned_agents, target_agent
        )
        # 写入 liuzhuan 供 silijian 审查
        db.execute(
            "INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark) "
            "VALUES (?, 'chaoting', 'silijian', 'warn', ?)",
            (zid, f"[WARN] target_agent={target_agent} 可能与返工旨意不符（旨意提到: {mentioned_agents}）"),
        )
```

---

## 五、修复优先级与工作量

| Fix | 文件 | 行号 | 工作量 | 优先级 |
|-----|------|------|--------|--------|
| Fix 1 | `src/dispatcher.py` | 404–443 | 30 分钟 | 🔴 必须（根本原因）|
| Fix 2 | `src/chaoting` | 662–677 | 15 分钟 | 🔴 必须（双重保障）|
| Fix 3 | `examples/souls/zhongshu.md` | 工作流程后 | 20 分钟 | 🟠 强烈建议 |
| Fix 4 | `src/chaoting` | ~711 | 30 分钟 | 🟡 可选 |

**最小修复集**（45 分钟）：Fix 1 + Fix 2

---

## 六、复现测试方案

```bash
# 1. 创建测试奏折（指定 target_agent: gongbu）
CHAOTING_DIR=/home/tetter/self-project/chaoting
TEST_ID="ZZ-BUG-TEST-001"
$CHAOTING_DIR/src/chaoting new "bug复现测试" "测试描述" --priority low --agent gongbu

# 2. 中书省规划（target_agent: gongbu）
$CHAOTING_DIR/src/chaoting plan $TEST_ID '{"steps":["test"],"target_agent":"gongbu","acceptance_criteria":"test"}'

# 3. 模拟 menxia 准奏 → gongbu 执行 → done

# 4. 皇上 revise，要求改用 bingbu
OPENCLAW_AGENT_ID=silijian $CHAOTING_DIR/src/chaoting revise $TEST_ID \
  "转交兵部（bingbu）处理，工部代码作废"

# 5. 验证 Fix 1: format_revising_message 的输出是否包含旨意
# （dispatcher 调用 format_revising_message 时）
python3 -c "
import json
import sys
sys.path.insert(0, '$CHAOTING_DIR/src')
import sqlite3
db = sqlite3.connect('$CHAOTING_DIR/chaoting.db')
db.row_factory = sqlite3.Row
row = db.execute(\"SELECT * FROM zouzhe WHERE id='$TEST_ID'\").fetchone()
from dispatcher import format_revising_message
msg = format_revising_message(dict(row))
assert '兵部' in msg or 'bingbu' in msg, 'FIX 1 FAILED: 旨意未出现在消息中'
print('Fix 1 PASS: 旨意包含在 format_revising_message 输出中')
"

# 6. 验证 Fix 2: chaoting pull 返回 revise_history
RESULT=$($CHAOTING_DIR/src/chaoting pull $TEST_ID)
echo $RESULT | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'revise_history' in d.get('zouzhe', {}), 'FIX 2 FAILED: revise_history 不在 pull 输出中'
assert len(d['zouzhe']['revise_history']) > 0, 'FIX 2 FAILED: revise_history 为空'
print('Fix 2 PASS: revise_history 在 pull 输出中')
"

# 7. 验证最终效果：中书省规划后 target_agent 应为 bingbu
# （手工或通过集成测试验证）
```

---

## 七、附：为何两个独立 Bug 共同作用

```
皇上 revise
    │
    ▼
chaoting.db: revise_history=[{reason: "转交兵部"}]
    │
    ├── 路径 A (dispatcher → zhongshu 通知)
    │   format_revising_message() 读 plan_history ✅
    │   但不读 revise_history ❌
    │   → 中书省收到的消息：旧封驳意见（无旨意）
    │
    └── 路径 B (zhongshu 主动 pull)
        cmd_pull() 返回 {id, title, description, state, plan}
        但不返回 revise_history ❌
        → 中书省查到的数据：原方案（无旨意）

两条路径都堵死了。中书省即使想遵旨，也没有任何方式获取旨意内容。
```

这不是中书省的 LLM 问题，也不是 SOUL.md 规范不够清晰——是纯粹的**数据管道断路**：信息产生了（写入 `revise_history`），但从未流向中书省。

---

*报告完。*  
*制作：兵部 bingbu | ZZ-20260310-013 | 2026-03-10*
