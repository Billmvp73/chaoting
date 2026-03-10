# Agent Teams Reviewer 协作模式对比报告

**奏折 ID**: ZZ-20260310-006  
**完成日期**: 2026-03-09  
**执行者**: 兵部 (bingbu)  
**测试任务**: 实现 `chaoting stats` CLI 命令（mock 实现）  
**环境**: Claude Code v2.1.39 | ACPx v0.1.15 | In-process backend

---

## 一、实验设计

### 测试任务

两种模式均测试同一任务：「实现 `chaoting stats` CLI 命令」
- 查询 SQLite DB，统计各状态奏折数量
- 只写到 `/tmp/` 目录（mock），不修改真实代码库

### 模式定义

| 模式 | 描述 | Teammates |
|------|------|-----------|
| **A — 并行** | Coder 编码的同时 Reviewer 等待并即时审查 | coder + reviewer（同时启动）|
| **B — 顺序迭代** | Coder 完成 → Reviewer 审查 → Coder 改进 → 重复 | coder-r1 → reviewer-r1 → coder-r2 → reviewer-r2 |

---

## 二、模式 A 实验：并行工作流

### 2.1 执行记录

```
03:44:09 UTC  TeamCreate("mode-a-parallel")
03:44:09 UTC  Task(coder) + Task(reviewer) — 同时启动（并行）
              └─ reviewer 立即开始 polling coder 的输出文件

03:44:53 UTC  coder 完成 (44s)
              └─ 写入 /tmp/reviewer-test-a/coder-draft.txt (63行 Python)
              └─ sentinel-write ZZ-TEST-MODE-A coder --status done

03:44:53 UTC  reviewer 检测到 coder-draft.txt 存在
              └─ 开始 code review

03:45:34 UTC  reviewer 完成 (41s after coder done, 85s total)
              └─ 写入 /tmp/reviewer-test-a/reviewer-feedback.txt (110行)
              └─ sentinel-write ZZ-TEST-MODE-A reviewer --status done

03:45:42 UTC  lead 确认两个哨兵都存在，写入 lead-summary.txt

总耗时: 93 秒
```

### 2.2 产出质量

**Coder Draft (v1) — 4.5/5**：
- 63 行 Python，含类型注解和 docstring
- 正确使用 `try/finally` 清理数据库连接
- 提前初始化所有 state → 0
- `get_stats()` + `print_stats()` 职责分离

**Reviewer Feedback — 5/5**：
- 4 个维度评分（SQL 注入 5/5、错误处理 4/5、边界情况 4/5、代码风格 5/5）
- 整体 4.5/5 = APPROVE
- 3 条具体改进建议（含代码示例）
- 正确识别真实问题：`OperationalError` 未捕获、NULL state、`__main__` 缺少错误处理

### 2.3 并行性分析

**是否真正并行？是的，但有内在数据依赖：**

```
时间轴:
T+0s   Lead 同时发出 Task(coder) 和 Task(reviewer)
        │                              │
        ▼                              ▼
T+0s   coder: 开始编码             reviewer: 开始轮询 coder 输出文件
        │                              │
T+44s  coder: 写入文件 + 写哨兵       reviewer: 检测到文件！开始 review
                                        │
T+85s                              reviewer: 写结果 + 写哨兵
```

**关键优势**：reviewer 不是在 coder 完成后才被"创建"，而是"创建后等待"。
因此总耗时 = max(coder_time, reviewer_wait + review_time) = 85s
而非顺序 = coder_time + spawn_overhead + review_time。

### 2.4 文件哨兵表现

✅ 运行完美：
- Coder 写入文件 → 写哨兵（有序）
- Reviewer polling 文件（独立于哨兵，用 `ls` 检测）
- Lead polling 哨兵（用 `chaoting teams sentinel-status`）
- 无竞争条件，无信号丢失

---

## 三、模式 B 实验：顺序迭代工作流

### 3.1 执行记录

```
Round 1:
T+0s    TeamCreate("mode-b-iterative")
T+0s    Task(coder-r1) — 简单初稿（故意不加错误处理）
T+~40s  coder-r1 完成 → coder-v1.txt (16行，极简版)
         sentinel ZZ-TEST-MODE-B/coder-r1.done ✓
T+40s   Lead 检测到 coder-r1 哨兵 → Task(reviewer-r1)
T+~80s  reviewer-r1 完成 → review-v1.txt
         分数: error_handling=1, edge_cases=2, code_quality=2, TOTAL=5/15
         sentinel ZZ-TEST-MODE-B/reviewer-r1.done ✓

Round 2:
T+80s   Lead 读取 review-v1.txt 获取 3 条反馈 → Task(coder-r2)
T+~140s coder-r2 完成 → coder-v2.txt (33行，改进版)
         sentinel ZZ-TEST-MODE-B/coder-r2.done ✓
T+140s  Lead 检测到 coder-r2 哨兵 → Task(reviewer-r2)
T+~200s reviewer-r2 完成 → review-v2.txt
         分数: error_handling=4, edge_cases=4, code_quality=5, TOTAL=13/15
         VERDICT: APPROVE
         sentinel ZZ-TEST-MODE-B/reviewer-r2.done ✓

T+270s  Lead 写入 lead-summary.txt，团队关闭

总耗时: ~270 秒 (4.5 分钟)
```

### 3.2 收敛曲线

```
质量分数 (满分 15)
    15 |                         ★ (理想)
    14 |
    13 |                    ●── 13 (Round 2, APPROVED)
    12 |
    11 |
    10 |
     9 |
     8 |
     7 |
     6 |
     5 |──  5 (Round 1)
     4 |
     3 |
     2 |
     1 |
       └─────────────────────
         Round 1           Round 2
         
改进: +8 points (+160%), 2 轮即收敛至 APPROVE
```

### 3.3 迭代改进详情

| 维度 | Round 1 | Round 2 | 改进 |
|------|---------|---------|------|
| 错误处理 | 1/5 | 4/5 | **+3** |
| 边界情况 | 2/5 | 4/5 | **+2** |
| 代码质量 | 2/5 | 5/5 | **+3** |
| **总分** | **5/15** | **13/15** | **+8 (+160%)** |
| 裁决 | — | **APPROVE** | — |

**3 条改进全部应用（3/3, 100%）**：
1. ✅ `try/except` for `OperationalError`+`DatabaseError`，context manager
2. ✅ `None` state → "unknown" fallback，空结果 → "No records found"
3. ✅ 类型注解、docstring、可配置 `db_path` 参数

**Round 2 遗留（非阻塞）**：
- `FileNotFoundError/OSError` 未捕获
- 错误输出到 stdout 而非 stderr

### 3.4 文件哨兵表现

✅ 每轮间的协调可靠：
- Lead 顺序等待 4 个哨兵（coder-r1 → reviewer-r1 → coder-r2 → reviewer-r2）
- 哨兵命名规范 (`<role>-r<round>`) 清晰区分轮次
- 没有混淆前后轮输出的情况

---

## 四、对比分析

### 4.1 完整对比表

| 维度 | 模式 A（并行） | 模式 B（顺序迭代） |
|------|-------------|----------------|
| **总耗时** | 93s (~1.5 min) | 270s (~4.5 min) |
| **最终质量** | 4.5/5 (one-shot) | 13/15 = 4.3/5 (2 rounds) |
| **质量起点** | 4.5/5（已经很高） | 5/15（故意设低）|
| **改进幅度** | N/A（一次成稿）| +160% (5→13/15) |
| **Lead 编排复杂度** | 低（1 步等待）| 高（4 步顺序等待）|
| **Teammate 数量** | 2（同时活跃）| 2（顺序激活）|
| **哨兵数量** | 2 | 4（每轮各 2）|
| **代码最终质量** | 高（初稿即高质）| 高（迭代后高质）|
| **适合 Lead 控制** | 简单 | 需要循环逻辑 |
| **可扩展迭代** | ❌ 无迭代概念 | ✅ 可扩展至 N 轮 |

### 4.2 适用场景建议

**选用模式 A（并行）当**：
- 任务定义清晰，预期 Coder 一次性产出质量较高
- 时间敏感，需要最短总耗时
- Reviewer 可以预先知道审查标准（不依赖 Coder 先完成）
- 示例：代码重构、添加明确定义的功能、修复已知 bug

**选用模式 B（顺序迭代）当**：
- 初稿质量不确定，需要 Reviewer 驱动改进
- 有明确的质量门控（如评分 ≥ 12/15 才 APPROVE）
- 任务复杂度高，需要多轮精炼
- Reviewer 的反馈对下一轮 Coder 的工作至关重要
- 示例：新架构设计、核心 API 实现、安全敏感代码

**对 Chaoting 系统的建议**：
- 普通代码奏折 → 模式 A（速度优先，Coder 通常产出高质量代码）
- 关键/安全相关奏折 → 模式 B（质量优先，需要迭代改进）
- 架构设计奏折 → 模式 B 的变体（设计师 + 审查人交替迭代）

---

## 五、文件哨兵适配度评估

### 5.1 现有哨兵满足两种模式了吗？

| 需求 | 模式 A | 模式 B | 现有哨兵 |
|------|--------|--------|---------|
| 完成信号 | ✅ 需要 | ✅ 需要 | ✅ 已支持 |
| 顺序等待 | N/A | ✅ 需要 | ✅ 已支持（`wait_all` 分批调用）|
| 并行等待 | ✅ 需要 | N/A | ✅ 已支持（`wait_all` 一次性）|
| 轮次标识 | N/A | ✅ 需要 | ✅ 已支持（命名约定 `<role>-r<n>`）|
| 反馈传递 | ✅ 通过文件 | ✅ 通过文件 | ✅ output 字段 |
| 实时进度 | ❌ 无 | ❌ 无 | ❌ 不支持 |
| 双向通信 | ❌ 无 | ❌ 无 | ❌ 不支持 |

**结论：现有哨兵机制已满足两种模式的基本需求。** 

### 5.2 可选扩展（非必须）

**短期改进（V0.4 候选）**：

1. **`progress` 信号**（运行中进度更新）：
   ```json
   {"status": "running", "progress": 0.6, "message": "Applying improvement 2/3"}
   ```
   用途：让 Lead 在等待时显示实时进度，提升可观测性。

2. **`iteration_metadata` 字段**：
   ```json
   {"status": "done", "metadata": {"round": 2, "score": 13, "approved": true}}
   ```
   用途：简化 Lead 判断是否需要再次迭代（直接读哨兵而不是解析 reviewer 输出文件）。

**长期架构建议（V0.5+）**：

3. **Sentinel 状态机**（明确状态转换）：
   ```
   pending → running → done/failed/timeout
   ```
   当前 `running` 状态存在但未被强制使用。可在 teammate 启动时写入 `running` 哨兵，实现更精细的生命周期追踪。

4. **迭代协调器**（`IterationCoordinator`）：
   ```python
   coord = IterationCoordinator(zouzhe_id, max_rounds=5, converge_fn=lambda scores: scores["total"] >= 12)
   while not coord.converged():
       coord.run_round(coder_task, reviewer_task)
   ```
   将模式 B 的重复逻辑封装为可复用组件。

### 5.3 当前无需扩展的原因

- 文件哨兵的「完成信号」 + 文件系统的「内容传递」组合已经很强大
- Lead 的 LLM 能力可以解析 reviewer 文件并决定是否继续迭代
- 过早抽象增加系统复杂度，当前 V0.3 的简洁性是优点

---

## 六、Lead 系统提示模板

### 6.1 模式 A（并行）Lead 模板

```
You are the lead agent coordinating a parallel Coder+Reviewer workflow.

TASK: [具体任务描述]

SENTINEL SETUP:
- CHAOTING_DIR: ${CHAOTING_DIR}
- Task ID: ${ZOUZHE_ID}
- Sentinel write command: CHAOTING_DIR=${CHAOTING_DIR} chaoting teams sentinel-write ${ZOUZHE_ID} <name> --status done --output <file>

WORKFLOW - PARALLEL MODE:

1. TeamCreate("${ZOUZHE_ID}-team")

2. Spawn BOTH teammates simultaneously:

   Task "coder":
   "[代码任务描述]
   Write output to /tmp/${ZOUZHE_ID}-code.txt
   When done: CHAOTING_DIR=${CHAOTING_DIR} chaoting teams sentinel-write ${ZOUZHE_ID} coder --status done --output /tmp/${ZOUZHE_ID}-code.txt"

   Task "reviewer" (start in parallel, poll for coder output):
   "Wait until /tmp/${ZOUZHE_ID}-code.txt exists (check with ls every 5s).
   Once it exists: [审查标准和评分维度]
   Write review to /tmp/${ZOUZHE_ID}-review.txt
   When done: CHAOTING_DIR=${CHAOTING_DIR} chaoting teams sentinel-write ${ZOUZHE_ID} reviewer --status done --output /tmp/${ZOUZHE_ID}-review.txt"

3. Wait: check every 5s until both sentinel files exist:
   /home/tetter/self-project/chaoting/sentinels/${ZOUZHE_ID}/coder.done
   /home/tetter/self-project/chaoting/sentinels/${ZOUZHE_ID}/reviewer.done

4. Read both output files and produce integration summary.

5. Shutdown teammates (SendMessage shutdown_request × 2), TeamDelete.
```

### 6.2 模式 B（顺序迭代）Lead 模板

```
You are the lead agent coordinating a sequential iterative Coder+Reviewer workflow.

TASK: [具体任务描述]
QUALITY THRESHOLD: [如 total >= 12/15 即 APPROVE]
MAX ROUNDS: [如 3]

SENTINEL SETUP:
- CHAOTING_DIR: ${CHAOTING_DIR}  
- Task ID: ${ZOUZHE_ID}

WORKFLOW - ITERATIVE MODE:

FOR each round r (1, 2, ..., MAX_ROUNDS):

  IF r == 1:
    instructions = "[初稿任务描述]"
  ELSE:
    improvements = <read from review-(r-1).txt>
    instructions = "[改进任务描述，要求应用 improvements 中的所有建议]"

  1. Task "coder-r${r}":
     "${instructions}
     Write to /tmp/${ZOUZHE_ID}-code-v${r}.txt
     When done: ... sentinel-write ${ZOUZHE_ID} coder-r${r} --status done --output ..."

  2. Wait for sentinel: coder-r${r}.done

  3. Task "reviewer-r${r}":
     "Read /tmp/${ZOUZHE_ID}-code-v${r}.txt
     [审查标准]
     Output format: SCORES: dim1=X dim2=X TOTAL=X/15 VERDICT: APPROVE|NEEDS_REVISION
     Write to /tmp/${ZOUZHE_ID}-review-v${r}.txt
     When done: ... sentinel-write ${ZOUZHE_ID} reviewer-r${r} ..."

  4. Wait for sentinel: reviewer-r${r}.done

  5. Read review. IF VERDICT == APPROVE OR r >= MAX_ROUNDS: BREAK

FINALIZE: Write summary, shutdown, TeamDelete.
```

### 6.3 何时用哪种模式——决策流程

```
问题：Reviewer 需要看到 Coder 的完整初稿才能开始审查吗？

YES → 模式 B（顺序迭代）
  问题：初稿质量可预测吗？
    YES（有明确规范）→ 1 轮即可
    NO（新架构/创新）→ 2-3 轮

NO → 模式 A（并行）
  前提：Reviewer 有预设审查标准（不依赖初稿内容）
  示例：代码风格检查、安全扫描、文档格式审查
```

---

## 七、实验数据汇总

| 指标 | 模式 A | 模式 B |
|------|--------|--------|
| 总耗时 | **93s** | 270s |
| 最终质量 | **4.5/5** | 4.3/5 (13/15) |
| 质量改进量 | N/A（一次成型）| **+8 points (+160%)** |
| Teammates 数量 | 2 | 4（跨 2 轮）|
| 哨兵数量 | 2 | 4 |
| Lead 编排复杂度 | **低** | 高 |
| 迭代能力 | ❌ | **✅** |
| 适合低质量初稿 | ❌ | **✅** |
| 适合时间敏感任务 | **✅** | ❌ |

**关键结论**：

> 模式 A 更适合日常开发任务（速度快、初稿质量高）；  
> 模式 B 更适合需要迭代精炼的高要求任务（质量改进明显，2 轮即收敛到 APPROVE）。  
> **现有文件哨兵机制已满足两种模式**，短期无需扩展，V0.4 可考虑增加 `progress` 信号和 `iteration_metadata` 字段。

---

*报告由兵部 (bingbu) 撰写，2026-03-09*  
*实验产出文件：`/tmp/reviewer-test-a/`（4 文件, 252 行）和 `/tmp/reviewer-test-b/`（5 文件, 138 行）*
