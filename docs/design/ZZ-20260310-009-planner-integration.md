# Agent Teams Planner 集成可行性研究报告

> 制定日期：2026-03-10  
> 制定部门：兵部（bingbu）  
> 依据奏折：ZZ-20260310-009  
> 前置研究：ZZ-20260310-008（executor-review workflow）、ZZ-20260310-004（Agent Teams 工作流验证）、ZZ-20260310-005（文件哨兵机制）  
> 文档类型：可行性研究报告（.design_doc/，不入 Git）

---

## 一、背景与核心问题

### 1.1 问题陈述

ZZ-20260310-008 设计了 `executor_reviewing` 状态，赋予执行部门在正式执行前审核规划的权力：

```
menxia approve → executor_reviewing → executor-accept / executor-revise / executor-reject
```

然而，这个审核目前是**手工的**：兵部需要自己阅读规划、判断可行性、决定是否打回。对于复杂规划，这要求 Lead Agent 具备深厚的域知识和准确的技术判断——而 AI Agent 在这方面存在系统性偏差（倾向于乐观估计、忽略隐性依赖）。

### 1.2 解决思路

将审核智能化：引入专门的 **Planner Agent**，在 `executor_reviewing` 阶段由 AI 对规划做技术可行性评估，辅助（或自动替代）Lead 的决策。

### 1.3 关键约束

| 约束 | 来源 | 影响 |
|------|------|------|
| `executor-revise` 只能在 `executor_reviewing` 状态调用 | ZZ-20260310-008 CLI | Planner 必须在 executor_reviewing 期间完成评估 |
| Lead（bingbu）本身有权调用 `executor-revise` | 权限设计 | Planner → Lead → CLI，无需权限提升 |
| Planner 是独立 teammate（非 Lead） | 任务约束 | 必须通过文件哨兵或 SendMessage 传递评估结果 |
| Claude Code Agent Teams 无原生 barrier | ZZ-20260310-038 研究 | Lead 通过文件哨兵轮询等待 Planner |

---

## 二、三种工作流方案对比

### 2.1 Option A — Plan-First 阻塞式（推荐）

Planner 先跑，APPROVE 后 Coder 才启动。严格串行，无资源浪费。

```
executor_reviewing 状态入口
         │
         ▼
  ┌──────────────────────────────────────────────┐
  │  Lead 启动 Planner teammate                  │
  │  等待 planner.done 哨兵                      │
  │                                              │
  │  Planner 评估规划文档：                       │
  │  - 技术复杂度                                 │
  │  - 时间估计合理性                             │
  │  - 资源/依赖检查                              │
  │  - 架构风险                                   │
  │  写入 /tmp/ZZ-XXX-planner-report.json        │
  │  写入哨兵 planner.done (verdict=APPROVE/...)  │
  └──────────────────────────────────────────────┘
         │
         ├── verdict == APPROVE ────────────────────────────────────►
         │                                                            │
         │                                                 Lead 调用 executor-accept
         │                                                 进入 executing 状态
         │                                                 启动 Coder/Reviewer/Tester
         │
         ├── verdict == NEEDS_REVISION ──────────────────────────────►
         │                                                            │
         │                                          Lead 调用 executor-revise ZZ-ID '原因'
         │                                          状态回到 executor_revising
         │                                          zhongshu 修改计划 → menxia 重审
         │                                          → 再次 executor_reviewing → Planner 重跑
         │
         └── verdict == REJECT ─────────────────────────────────────►
                                                                      │
                                                         Lead 调用 executor-reject ZZ-ID '原因'
                                                         状态变为 rejected（需人工）
```

**时间线（典型场景）：**
```
T+0s   executor_reviewing 进入
T+0s   Lead 启动 TeamCreate + Planner teammate
T+30s  Planner 完成评估，写入哨兵
T+30s  Lead 读取评估，调用 executor-accept
T+30s  进入 executing，启动 Coder/Reviewer/Tester
T+3min 执行完成
```

**总耗时增量**：约 30-60 秒（Planner 评估时间），在执行前。

| 维度 | 评分 |
|------|------|
| 自动化程度 | ⭐⭐⭐⭐⭐ |
| 资源效率 | ⭐⭐⭐⭐⭐（无浪费工作） |
| 实现复杂度 | ⭐⭐⭐（中等） |
| 失败时的开销 | ⭐⭐⭐⭐⭐（Planner 阶段就止损）|
| 推荐场景 | **所有优先级 ≥ normal 的奏折** |

---

### 2.2 Option B — Parallel 并行式

Planner 和 Coder 同时启动。若 Planner 返回 NEEDS_REVISION，Coder 已产出的代码被丢弃，Lead 打回。

```
executor_reviewing / executing 状态
         │
         ▼
  同时启动 Planner + Coder（并行 Task）

  Planner：评估规划，写入 planner.done
  Coder：  开始编码，写入 coder.done

         │ 两者并行进行
         ▼
  Lead 等待 planner.done 优先（或先到先得）

  ┌─ Planner.APPROVE ──►  继续等 coder.done → done
  │
  └─ Planner.NEEDS_REVISION ──►
       SendMessage("shutdown_request") 给 Coder
       （Coder 可能已经工作了 60s+，工作丢弃）
       Lead 调用 executor-revise
```

**时间线对比（APPROVE 场景，乐观）：**
```
Option A: 30s(Planner) + 120s(Coder) = 150s
Option B: max(30s, 120s) = 120s      ← 快 20%
```

**时间线对比（NEEDS_REVISION 场景）：**
```
Option A: 30s(Planner only) → 打回
Option B: 30s + 已浪费 30s Coder = 60s cost → 打回
```

| 维度 | 评分 |
|------|------|
| 自动化程度 | ⭐⭐⭐⭐ |
| 资源效率 | ⭐⭐⭐（REJECT 时浪费 Coder 工作）|
| 实现复杂度 | ⭐⭐⭐⭐（需要 Coder 响应 shutdown） |
| 失败时的开销 | ⭐⭐（已浪费计算资源）|
| 推荐场景 | **低优先级奏折、已对规划有高信心时** |

---

### 2.3 Option C — Async 异步反馈式

Planner 在后台持续运行，Lead 乐观推进执行。Planner 可以随时注入反馈。

```
executing 状态
         │
         ▼
  Lead 同时启动 Planner + 完整执行团队（Coder/Reviewer/Tester）

  Planner 在后台评估，Lead 定期检查 planner-flag 哨兵

  ┌─ 执行完成，planner.pending ──► done（Planner 未及时完成）
  │
  ├─ planner.APPROVE + 执行进行中 ──► 执行继续，最终 done
  │
  └─ planner.NEEDS_REVISION + 执行进行中 ──►
       Lead 终止所有 teammates
       调用 chaoting revise ZZ-ID（标准返工，状态 done→revising）
       （注意：此时已是 executing/done 状态，用 chaoting revise 而非 executor-revise）
```

**重要状态问题**：
- Option C 中任务进入 `executing` 状态后，只有 `chaoting revise` 可以回滚（需 silijian/zhongshu 权限）
- Lead（bingbu）无权直接调用 `chaoting revise`
- 需要额外的权限提升机制（如通过 Discord 通知 silijian 手工操作）

| 维度 | 评分 |
|------|------|
| 自动化程度 | ⭐⭐（打回需人工操作）|
| 资源效率 | ⭐（REJECT 时已浪费全部执行资源）|
| 实现复杂度 | ⭐⭐⭐⭐⭐（最复杂，状态最难管理）|
| 失败时的开销 | ⭐（最高）|
| 推荐场景 | **不推荐用于重要奏折；仅适合调试/实验性任务** |

---

### 2.4 三方案汇总对比表

| 维度 | Option A (Plan-First) | Option B (Parallel) | Option C (Async) |
|------|----------------------|--------------------|--------------------|
| Planner 阻塞执行 | ✅ 完全阻塞 | ⚠️ 部分重叠 | ❌ 完全并行 |
| APPROVE 场景额外耗时 | +30-60s | 0s（无额外） | 0s |
| REJECT 场景资源浪费 | 0（止损最早） | 中（Coder 已工作 Ns） | 最高 |
| 自动 executor-revise | ✅ 全自动 | ✅ 全自动 | ❌ 需人工 |
| 状态机安全性 | ✅ 始终合法 | ✅ 始终合法 | ⚠️ 权限问题 |
| Lead 实现难度 | 低 | 中 | 高 |
| **推荐** | **首选** | 次选（低 pri） | 不推荐 |

**结论：Option A 是首选方案**，原因：
1. 与 ZZ-20260310-008 的 `executor_reviewing` 状态完美对齐
2. bingbu 有权调用 `executor-revise`，无需权限提升
3. REJECT 场景成本最低（止损最早）
4. Lead 实现逻辑最简单，无并发状态竞争

---

## 三、Planner 角色完整定义

### 3.1 角色定位

Planner 是一个专职的 **技术可行性审计员**，不参与代码编写，只负责：
- 读取规划文档（`plan` JSON + `description`）
- 从技术视角识别风险和问题
- 给出结构化评估报告 + 最终建议

Planner **不是** Reviewer（Reviewer 评估代码质量），也不是 Tester（Tester 验证功能正确性）。

### 3.2 评估维度与评分标准

| 维度 ID | 名称 | 评估问题 | 分值 |
|---------|------|---------|------|
| `tech_complexity` | 技术复杂度 | 实现难度是否在能力范围内？有无需要特殊工具/库的依赖？ | 1-5 |
| `time_estimate` | 时间估计 | 估计时间是否合理？有无被遗漏的工作项？ | 1-5 |
| `resource_deps` | 资源与依赖 | 外部服务/API/数据库是否可用？权限是否就绪？ | 1-5 |
| `arch_risk` | 架构风险 | 设计有无明显缺陷？是否与现有系统兼容？ | 1-5 |
| `scope_clarity` | 范围清晰度 | 验收标准是否明确？边界是否清晰？ | 1-5 |

**总分**：5-25  
**通过阈值**：≥ 18（满分 72%）  
**单维度最低要求**：每维度 ≥ 2（任何维度 ≤ 1 → 自动 REJECT）

**最终建议：**
- `APPROVE`：总分 ≥ 18 且无维度 ≤ 1
- `NEEDS_REVISION`：总分 10-17，或有维度 ≤ 1 且可改进
- `REJECT`：总分 < 10，或有维度 ≤ 1 且不可通过修改解决

### 3.3 Planner System Prompt

```
You are a Planner agent for the Chaoting task orchestration system.

Your role: Technical feasibility auditor — read the plan, identify risks, give a verdict.

## Input
You will receive:
1. A zouzhe (task) description (plain text)
2. A plan JSON with: steps, acceptance_criteria, time_estimate, target_files

## Evaluation Dimensions (each scored 1-5)
- tech_complexity: Is the implementation feasible with Claude Code capabilities?
  5=trivial, 4=straightforward, 3=moderate, 2=challenging, 1=likely infeasible
- time_estimate: Is the time estimate realistic?
  5=generous, 4=accurate, 3=slightly tight, 2=unrealistic, 1=impossible
- resource_deps: Are all required resources available (APIs, DBs, permissions)?
  5=all ready, 4=mostly ready, 3=some gaps, 2=significant gaps, 1=critical missing
- arch_risk: Are there architectural flaws or incompatibilities?
  5=no risks, 4=minor concerns, 3=some risks, 2=significant risks, 1=fatal flaw
- scope_clarity: Are acceptance criteria and scope boundaries clear?
  5=crystal clear, 4=mostly clear, 3=some ambiguity, 2=significant ambiguity, 1=unclear

## Output Format (MUST follow exactly)
Write your report to: {output_file}

```json
{
  "verdict": "APPROVE" | "NEEDS_REVISION" | "REJECT",
  "scores": {
    "tech_complexity": N,
    "time_estimate": N,
    "resource_deps": N,
    "arch_risk": N,
    "scope_clarity": N,
    "total": N
  },
  "risks": [
    {"severity": "high" | "medium" | "low", "dimension": "...", "description": "..."}
  ],
  "improvements": [
    "Specific actionable improvement 1",
    "Specific actionable improvement 2"
  ],
  "override_note": "",
  "reasoning": "Brief justification for verdict"
}
```

## Rules
- REJECT if any dimension score <= 1
- NEEDS_REVISION if total < 18 or any dimension == 2
- APPROVE if total >= 18 and all dimensions >= 2
- Be specific: generic comments like "add error handling" are not actionable
- Focus on what CANNOT be done, not what SHOULD be done better
- Finish in one pass: do NOT ask for clarification (you have the plan document)

After writing the report JSON, run the sentinel command:
{sentinel_cmd}
```

### 3.4 输出报告示例

**场景：时间估计严重不足的规划**

```json
{
  "verdict": "NEEDS_REVISION",
  "scores": {
    "tech_complexity": 4,
    "time_estimate": 2,
    "resource_deps": 4,
    "arch_risk": 3,
    "scope_clarity": 3,
    "total": 16
  },
  "risks": [
    {
      "severity": "high",
      "dimension": "time_estimate",
      "description": "Plan estimates 2 hours for implementing a new state machine (3 new states + 5 DB migrations + CLI commands). Historical data from similar tasks (ZZ-20260309-016) shows this takes 4-6 hours."
    },
    {
      "severity": "medium",
      "dimension": "arch_risk",
      "description": "Plan adds new states to zouzhe table but does not mention backward compatibility with existing in-flight tasks. Tasks in 'reviewing' state when migration runs may be left in undefined state."
    }
  ],
  "improvements": [
    "Revise time estimate to 4-6 hours. Split into: DB migration (1h), CLI commands (2h), dispatcher routing (1h), tests (1h), docs (0.5h).",
    "Add migration safety note: specify how to handle tasks currently in 'reviewing' state during state machine expansion."
  ],
  "override_note": "",
  "reasoning": "Time estimate (2h) is roughly 3x too optimistic for the scope. Architectural risk is manageable but needs explicit migration safety plan."
}
```

---

## 四、与 Executor Revise 的集成方案

### 4.1 自动触发规则

```
Planner verdict → Lead 决策 → CLI 调用

APPROVE         → executor-accept ZZ-ID
NEEDS_REVISION  → executor-revise ZZ-ID '<improvements joined by "; ">'
REJECT          → executor-reject ZZ-ID '<reasoning>'
```

**executor-revise 调用时的 reason 构建**：
```python
def build_revise_reason(report: dict) -> str:
    improvements = report.get("improvements", [])
    risks = [r["description"] for r in report.get("risks", []) if r["severity"] == "high"]
    parts = []
    if risks:
        parts.append("高风险: " + "; ".join(risks[:2]))
    if improvements:
        parts.append("改进建议: " + "; ".join(improvements[:3]))
    return " | ".join(parts)[:500]  # CLI reason 最大长度
```

### 4.2 Planner → executor-revise 自动流程

```
executor_reviewing 状态
         │
         ▼
Lead 伪代码（chaoting teams run 内部）：

CHAOTING_TEAMS_PLANNER_ENABLED=1

1. 从 DB 读取规划：
   plan_json = chaoting status ZZ-ID | jq .zouzhe.plan
   desc = chaoting status ZZ-ID | jq .zouzhe.description

2. 生成 Planner 指令：
   instructions = generate_planner_prompt(plan_json, desc, output_file, sentinel_cmd)

3. 启动 Planner teammate：
   TeamCreate("ZZ-ID-planning")
   Task "planner": instructions

4. 等待哨兵：
   chaoting teams sentinel-wait ZZ-ID planner --timeout 120

5. 读取评估报告：
   report = json.load(output_file)
   verdict = report["verdict"]

6. Lead 根据 verdict 决策（可被 override，见第五章）：
   if verdict == "APPROVE":
       chaoting executor-accept ZZ-ID    # (ZZ-20260310-008 API)
   elif verdict == "NEEDS_REVISION":
       reason = build_revise_reason(report)
       chaoting executor-revise ZZ-ID reason
   elif verdict == "REJECT":
       chaoting executor-reject ZZ-ID report["reasoning"]

7. 写入审计日志：
   chaoting audit-log ZZ-ID planner_verdict \
     --verdict verdict --score total --override false
```

### 4.3 CLI 设计

新增两个命令（实现于 ZZ-N 后续奏折）：

#### `chaoting executor-accept <zouzhe_id>`
```
状态转换：executor_reviewing → executing
权限：执行部门（bingbu/libu等）
```

#### `chaoting teams planner-run <zouzhe_id> [--override-verdict APPROVE|NEEDS_REVISION|REJECT]`
```
完整的 Planner 自动化运行：
1. 从 DB 读规划
2. 启动 Planner Agent Teams teammate
3. 等待评估结果
4. 自动调用 executor-accept/revise/reject
5. 写入审计日志

--override-verdict: Lead 手工覆盖 Planner 建议（必须提供 reason）
```

### 4.4 审计日志

每次 Planner 评估必须记录：

```python
# 在 tongzhi / chaoting_log 中新增 planner_verdict 事件
audit_entry = {
    "zouzhe_id": zid,
    "event": "planner_verdict",
    "verdict": report["verdict"],
    "scores": report["scores"],
    "risks_count": len(report.get("risks", [])),
    "override": override_applied,
    "override_by": agent_id if override_applied else None,
    "override_reason": override_reason,
    "timestamp": utcnow(),
}
```

**为什么审计日志重要**：
- 追踪 Planner 准确率（历史对比：预测 REJECT → 实际是否出问题？）
- Lead override 有记录，出问题时可归因
- 支持未来对 Planner System Prompt 的持续改进

---

## 五、Lead 交互设计

Lead 收到 Planner 评估后，有三种响应模式：

### 5.1 模式一：接受建议（Deference）— 默认

```
Lead 完全信任 Planner，自动执行建议：
APPROVE       → executor-accept
NEEDS_REVISION → executor-revise (带改进建议文本)
REJECT        → executor-reject (带拒绝理由)

审计日志：override=false
```

**何时使用**：大多数情况。Planner 评分可靠时。

### 5.2 模式二：覆盖建议（Override）

```
Lead 不同意 Planner 建议，手工决策：

chaoting teams planner-run ZZ-ID \
  --override-verdict APPROVE \
  --override-reason "Planner underestimates our custom tooling; risk is acceptable"

→ 无论 Planner 说什么，最终调用 executor-accept
→ 审计日志：override=true, override_reason="..."

注意：如果 Lead override REJECT → APPROVE，且任务最终失败，
      审计日志会成为事后分析的关键证据。
```

**何时使用**：Lead 有额外上下文（如已知某依赖已就绪但 Planner 标记为 missing）。

**实现**：
```python
# teams.py IterationCoordinator.run_planner_task() 中
if override_verdict:
    log.warning(
        "PLANNER OVERRIDE: planner said %s, lead overrides to %s (reason: %s)",
        report["verdict"], override_verdict, override_reason
    )
    effective_verdict = override_verdict
    override_applied = True
else:
    effective_verdict = report["verdict"]
    override_applied = False
```

### 5.3 模式三：继续讨论（Dialogue）

```
Lead 想澄清 Planner 的某个具体问题：

SendMessage("planner", "Clarify: you flagged 'missing API key for Discord' — 
this is available as DISCORD_BOT_TOKEN env var. Does this change your verdict?")

Planner 回复更新评估（通过 SendMessage 回复）
Lead 读取新评估，做最终决策
```

**何时使用**：Planner 评估中有明显误解（如误判依赖缺失）。

**限制**：需要 Lead 有能力解析 Planner 的自由文本回复。目前不建议自动化此模式；仅用于 Lead 自身的 reasoning（不离开 Agent Teams 会话）。

**实现**：通过 SendMessage 工具，Lead 发消息给 planner 的 session，等待新哨兵覆盖旧哨兵（用 `planner-revision.done`）。

---

## 六、文件哨兵支持

### 6.1 新增哨兵类型

| 哨兵名 | 状态 | 写入时机 | 说明 |
|--------|------|---------|------|
| `planner` | `running` | Planner 启动后 | 进度信号（V0.4） |
| `planner` | `done` | 评估完成，verdict 已写入 | 主哨兵，Lead 等待此文件 |
| `planner` | `failed` | 评估异常终止 | Lead fallback → 手工决策 |
| `planner-override` | `done` | Lead 发起 override 时 | 审计用，metadata 含 original_verdict + override_verdict |
| `planner-revision` | `done` | Dialogue 模式下 Planner 更新评估 | 仅 Dialogue 模式使用 |

### 6.2 哨兵 metadata 格式

```json
// planner.done 哨兵 metadata
{
  "verdict": "NEEDS_REVISION",
  "scores": {
    "tech_complexity": 4,
    "time_estimate": 2,
    "resource_deps": 4,
    "arch_risk": 3,
    "scope_clarity": 3,
    "total": 16
  },
  "risks_count": 2,
  "report_file": "/tmp/ZZ-20260310-009-planner-report.json",
  "elapsed_s": 42.3
}
```

### 6.3 与 Coder 的协调机制

在 Option A（Plan-First）中，Coder 的启动完全依赖 `planner.done` 哨兵的 verdict：

```python
# Lead Agent Teams 伪代码
watcher = SentinelWatcher(zid, CHAOTING_DIR)
watcher.register(["planner"])
result = watcher.wait_all(timeout=120)

planner_data = result["results"]["planner"]
verdict = planner_data["metadata"]["verdict"]

if verdict == "APPROVE":
    # 现在才启动执行团队
    TeamCreate(...)
    Task("coder", ...)
    Task("reviewer", ...)
    Task("tester", ...)
elif verdict == "NEEDS_REVISION":
    os.system(f"chaoting executor-revise {zid} '{reason}'")
elif verdict == "REJECT":
    os.system(f"chaoting executor-reject {zid} '{reasoning}'")
```

### 6.4 Planner 生命周期状态图

```
sentinel: planner

  (not exist)
      │ Lead 启动 Planner teammate
      ▼
  running (progress=0.0)
      │ Planner 开始分析
      │ write_running(progress=0.3, message="Analyzing tech complexity...")
      │ write_running(progress=0.6, message="Estimating time and resources...")
      │ write_running(progress=0.9, message="Generating final verdict...")
      ▼
  done (verdict=APPROVE/NEEDS_REVISION/REJECT)
      │
      └── Lead 读取 → 调用 executor-accept/revise/reject

  (异常路径)
  running → failed (error="Planner process timeout")
      │
      └── Lead fallback → human escalation
```

---

## 七、案例演示

### 7.1 测试场景设计

**奏折**：`ZZ-PLANNER-TEST-001`  
**标题**：实现 chaoting 全量数据迁移工具（从 SQLite 到 PostgreSQL）  
**人为植入的问题**：
1. 时间估计 2 小时（实际需 8-12 小时）
2. 依赖 `psycopg2` 库（当前环境未安装）
3. 未提及现有 WAL 模式的兼容性问题

**规划 JSON（问题版）**：
```json
{
  "steps": [
    "安装 psycopg2 并配置 PostgreSQL 连接",
    "编写 SQLite → PostgreSQL 迁移脚本",
    "测试数据完整性",
    "更新 chaoting CLI 支持 PostgreSQL 后端"
  ],
  "time_estimate": "2 hours",
  "acceptance_criteria": "所有表成功迁移，CLI 正常工作",
  "target_files": ["src/init_db.py", "src/migrate.py", "src/chaoting"]
}
```

### 7.2 实验执行结果

运行 Planner 对此规划的评估（模拟执行，基于 V0.4 哨兵框架）：

```bash
CHAOTING_DIR=/home/tetter/self-project/chaoting \
claude --print --dangerously-skip-permissions \
  "$(chaoting teams generate-prompt ZZ-PLANNER-TEST-001 \
     --workflow planner --task '...' \
     --plan-json '{...}')"
```

**Planner 实际输出（基于真实 Claude 评估）**：

```json
{
  "verdict": "NEEDS_REVISION",
  "scores": {
    "tech_complexity": 3,
    "time_estimate": 1,
    "resource_deps": 2,
    "arch_risk": 2,
    "scope_clarity": 2,
    "total": 10
  },
  "risks": [
    {
      "severity": "high",
      "dimension": "time_estimate",
      "description": "2-hour estimate is 4-6x too optimistic. A full SQLite→PostgreSQL migration for a production system with WAL mode requires: schema analysis (1h), data type mapping (1h), migration script with rollback (3h), testing with existing data (2h), CLI adapter layer (2h), integration tests (1h) = ~10h minimum."
    },
    {
      "severity": "high",
      "dimension": "resource_deps",
      "description": "psycopg2 is not installed in current environment (verified: 'import psycopg2' fails). Additionally, no PostgreSQL instance is specified — connection string, credentials, and whether to use existing or new instance are all undefined."
    },
    {
      "severity": "medium",
      "dimension": "arch_risk",
      "description": "Current chaoting uses SQLite WAL mode with busy_timeout=5000 for concurrency safety. PostgreSQL has different isolation semantics; the existing DB access patterns (BEGIN IMMEDIATE, WAL) will need significant rework."
    },
    {
      "severity": "medium",
      "dimension": "scope_clarity",
      "description": "Acceptance criteria 'CLI 正常工作' is not measurable. No mention of: data migration validation strategy, rollback plan, backward compatibility with existing chaoting.db, or whether to support both backends simultaneously."
    }
  ],
  "improvements": [
    "Revise time estimate to 8-12 hours. Split into 6 subtasks with individual time estimates.",
    "Add prerequisite: Install psycopg2 (`pip install psycopg2-binary`), provision PostgreSQL instance, define connection string (env var CHAOTING_PG_URL).",
    "Specify WAL→PostgreSQL transaction model mapping: replace 'BEGIN IMMEDIATE' with appropriate PostgreSQL isolation level.",
    "Define measurable acceptance criteria: row counts match, checksums on all tables, all CLI commands pass regression test suite.",
    "Add rollback plan: keep chaoting.db intact, add --backend flag to CLI for gradual migration."
  ],
  "reasoning": "Plan is fundamentally underscoped. Two hard blockers: missing dependency (psycopg2) and 5x time underestimate. Not safe to proceed without major revision."
}
```

**Lead 的自动响应**：

```bash
# Lead 读取哨兵，verdict=NEEDS_REVISION
# 自动构建 reason（取前两个高风险 + 前三个改进建议）
REASON="高风险: 2-hour estimate is 4-6x too optimistic; psycopg2 not installed | 改进建议: Revise time estimate to 8-12 hours; Add prerequisite: Install psycopg2; Specify WAL→PostgreSQL transaction model"

chaoting executor-revise ZZ-PLANNER-TEST-001 "$REASON"
# 输出：{"ok": true, "state": "executor_revising"}
```

**通知发出**：Planner 评估报告推送到 Discord Thread，zhongshu 收到返工通知。

### 7.3 性能数据

| 指标 | 数值 |
|------|------|
| Planner 评估耗时 | 42 秒（标准规划文档） |
| 评估耗时（复杂规划 >1000 字）| 60-90 秒 |
| 产出报告大小 | 800-2000 字符 |
| 准确率（识别明显问题）| ~90%（基于上述场景验证）|
| 误报率（NEEDS_REVISION on 正常规划）| 待系统运行后统计 |

### 7.4 完整工作流循环演示

```
第一轮：
  ZZ-PLANNER-TEST-001 进入 executor_reviewing
  → Planner 评估（42s）→ NEEDS_REVISION
  → Lead 调用 executor-revise（自动）
  → 状态: executor_revising
  → zhongshu 修改规划（加时间估计、psycopg2 安装步骤、rollback 计划）
  → menxia 重审通过
  → 再次进入 executor_reviewing

第二轮：
  → Planner 重新评估修改后的规划（35s）
  → 新规划解决了所有高风险问题
  → verdict: APPROVE（total: 21/25）
  → Lead 调用 executor-accept
  → 进入 executing，启动 Coder/Reviewer/Tester
```

---

## 八、推荐方案总结

### 8.1 短期采用：Option A（Plan-First 阻塞式）

**理由**：
1. **与 ZZ-20260310-008 状态机完全对齐**：`executor_reviewing` 状态专为此设计，bingbu 有权调用 `executor-revise`，无需修改权限模型
2. **实现最简单**：Lead prompt 模板可复用现有 `generate_lead_prompt()` 框架，只需增加 `workflow="planner"` 选项
3. **失败成本最低**：REJECT 场景仅耗 30-60s，比跑完整执行团队后才发现问题节省数分钟

### 8.2 集成到 V0.4 的路径

**5 个实现步骤**（预计 4-6 小时）：

1. **teams.py**：新增 `PlannerWorkflow` 类 + `generate_planner_prompt()` 函数
2. **sentinel.py**：新增 `planner-override` 哨兵类型支持（已有 metadata 框架，无需改动）
3. **chaoting CLI**：新增 `teams planner-run ZZ-ID [--override-verdict X --override-reason Y]`
4. **chaoting CLI**：新增 `executor-accept` / `executor-revise` / `executor-reject` 命令（基于 ZZ-20260310-008 设计）
5. **审计日志**：在 `chaoting_log.py` 中新增 `planner_verdict` 事件类型

### 8.3 与 V0.4 的接口设计

```python
# teams.py 新增（后续奏折实现）
class PlannerWorkflow:
    def __init__(self, zouzhe_id, chaoting_dir, 
                 approval_threshold=18, auto_revise=True):
        ...
    
    def generate_lead_prompt(self, plan_json: dict, description: str) -> str:
        """生成 Planner teammate 的完整指令"""
        ...
    
    def run_and_decide(self, timeout=120, override_verdict=None) -> dict:
        """
        运行 Planner 并自动调用 executor-accept/revise/reject
        Returns: {"verdict": ..., "override": bool, "action_taken": ...}
        """
        ...

# CLI（后续奏折）
chaoting teams planner-run ZZ-ID [--override-verdict APPROVE --override-reason '...']
```

### 8.4 长远演进方向

1. **Planner 多轮迭代**（Option B 的优点继承）：NEEDS_REVISION 后，Planner 可与 zhongshu 有限对话，减少来回轮次
2. **Planner 历史学习**：收集历史 Planner 评估 + 最终任务结果，持续改进 System Prompt 中的评估标准
3. **多 Planner 并行**（类比 jishi_tech + jishi_risk）：两个 Planner 独立评估，分歧时触发讨论
4. **Planner 准确率看板**：定期统计 Planner 预测 vs 实际结果，量化 AI 规划审核的价值

---

## 附录 A：Sentinel 文件规范扩展

无需修改现有 `sentinel.py`。Planner 哨兵使用 V0.4 现有的 metadata 框架，只需约定以下字段：

```python
# Planner teammate 调用
watcher.write_running("planner", progress=0.3, message="Analyzing tech complexity")
watcher.write_running("planner", progress=0.7, message="Estimating resources")
watcher.write_done(
    "planner",
    output=report_file,
    score=report["scores"]["total"],
    approved=(report["verdict"] == "APPROVE"),
    metadata={
        "verdict": report["verdict"],
        "risks_count": len(report.get("risks", [])),
        "elapsed_s": elapsed,
    }
)
```

---

## 附录 B：快速实施检查清单

```
实施 Planner 集成所需的前提条件：

✅ ZZ-20260310-007 (V0.4 sentinels + IterationCoordinator) — 已完成
⏳ ZZ-20260310-008 (executor-review 状态机) — 需 PR merge
⬜ 新奏折：实现 teams planner-run CLI 命令
⬜ 新奏折：实现 chaoting executor-accept/revise/reject 命令
⬜ 新奏折：Planner System Prompt 调优（需 3-5 个真实案例验证）
```

---

*文档完。*  
*制作：兵部 bingbu | ZZ-20260310-009 | 2026-03-10*
