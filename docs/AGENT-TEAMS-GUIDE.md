# Chaoting Agent Teams 使用指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: bingbu


**版本**: V0.3  
**日期**: 2026-03-09  
**适用版本**: Claude Code v2.1.39 + ACPx v0.1.15

---

## 概述

Chaoting V0.3 集成了 Claude Code Agent Teams 能力，通过**文件哨兵机制**（File Sentinel Pattern）实现可靠的并发任务编排：

```
Lead Agent
  ├── 分配子任务 → Teammate A → 完成后写入 sentinels/<id>/A.done
  ├── 分配子任务 → Teammate B → 完成后写入 sentinels/<id>/B.done
  └── 分配子任务 → Teammate C → 完成后写入 sentinels/<id>/C.done
                                         ↑
                               Lead 轮询检测，全部完成后整合结果
```

---

## 环境要求

### 必要配置

**1. ACPx 权限修复**（首次运行必须）：

```bash
# 编辑 ~/.acpx/config.json
{
  "defaultAgent": "claude --dangerously-skip-permissions",  # ← 加此 flag
  "defaultPermissions": "approve-all",
  ...
}
```

原因：ACPx 的 `approve-all` 仅作用于 ACP 协议层，不传递给 teammates。
`--dangerously-skip-permissions` 使 lead 的 `toolPermissionContext.mode = "bypassPermissions"`，
Claude Code 的 `ou4()` 函数会自动将此 flag 传递给所有 teammates。

**2. 环境变量**：

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1  # 必须
export CHAOTING_DIR=/path/to/chaoting          # 必须（指向哨兵目录父级）
```

**3. Backend 说明**：
- 非交互模式（`--print`/ACPx）→ **In-process backend**（无需 tmux）
- 交互模式（`claude` 终端）→ **Tmux pane backend**（需要 tmux）

---

## 文件哨兵机制

### 目录结构

```
$CHAOTING_DIR/
└── sentinels/
    └── <zouzhe_id>/
        ├── coder.done      # Coder 完成后写入
        ├── tester.done     # Tester 完成后写入
        └── docs.done       # Docs 完成后写入
```

### 哨兵文件格式（JSON）

```json
{
  "teammate_id": "coder",
  "zouzhe_id": "ZZ-20260310-004",
  "status": "done",
  "timestamp": "2026-03-09T02:12:39.819829+00:00",
  "output": "/tmp/coder.txt",
  "error": null,
  "metadata": {}
}
```

`status` 取值：
- `done` — 成功完成
- `failed` — 失败（含 `error` 字段）
- `timeout` — 超时（由 Lead 写入）
- `running` — 运行中（可选，通常省略）

---

## CLI 命令参考

### `chaoting teams sentinel-write`

Teammate 完成后调用，写入完成标记：

```bash
CHAOTING_DIR=/path/to/chaoting chaoting teams sentinel-write \
  <zouzhe_id> <teammate_id> \
  [--status done|failed] \
  [--output "输出文件路径或摘要"] \
  [--error "错误信息"]
```

示例：
```bash
# Coder 完成后写入
CHAOTING_DIR=$CHAOTING_DIR chaoting teams sentinel-write \
  ZZ-20260310-004 coder --status done --output "/tmp/coder.txt"
  
# {"ok": true, "path": ".../sentinels/ZZ-20260310-004/coder.done", ...}
```

### `chaoting teams sentinel-read`

读取单个哨兵：

```bash
chaoting teams sentinel-read <zouzhe_id> <teammate_id>
```

### `chaoting teams sentinel-status`

查看所有 teammates 状态：

```bash
chaoting teams sentinel-status <zouzhe_id> --teammates coder tester docs
```

输出：
```json
{
  "ok": true,
  "zouzhe_id": "ZZ-20260310-004",
  "total": 3,
  "done": 2,
  "failed": 0,
  "pending": 1,
  "details": {"coder": "done", "tester": "done", "docs": "pending"}
}
```

### `chaoting teams sentinel-wait`

阻塞等待所有 teammates 完成：

```bash
chaoting teams sentinel-wait <zouzhe_id> <t1> [t2 ...] \
  [--timeout 600] \
  [--poll 2.0]
```

输出（完成时）：
```json
{
  "ok": true,
  "status": "complete",
  "results": {"coder": {...}, "tester": {...}, "docs": {...}},
  "pending": [],
  "failed": [],
  "elapsed": 0.0005
}
```

超时时 `status` 为 `"timeout"`，已超时的 teammates 自动写入 `timeout` 哨兵（防止重启后重复等待）。

### `chaoting teams sentinel-list`

列出已完成的哨兵：

```bash
chaoting teams sentinel-list <zouzhe_id>
# ["coder", "tester"]
```

### `chaoting teams sentinel-cleanup`

清理所有哨兵文件：

```bash
chaoting teams sentinel-cleanup <zouzhe_id>
# {"ok": true, "deleted": 3}
```

### `chaoting teams run`

通过 ACPx/claude 运行 Agent Teams 任务：

```bash
chaoting teams run <zouzhe_id> \
  --prompt "Your lead agent prompt here" \
  --max-turns 80 \
  --timeout 600 \
  --cwd /path/to/working/dir
```

---

## Python API 参考

```python
from sentinel import SentinelWatcher, write_sentinel, SENTINEL_DONE

# Lead 端使用
watcher = SentinelWatcher(zouzhe_id="ZZ-20260310-004",
                           chaoting_dir="/path/to/chaoting")
watcher.register(["coder", "tester", "docs"])

# ... 启动 teammates ...

# 阻塞等待（带进度回调）
results = watcher.wait_all(
    timeout=300,
    poll_interval=2,
    on_progress=lambda pending, done: print(f"  {len(pending)} pending, {len(done)} done"),
)

if results["status"] == "complete":
    for tid, data in results["results"].items():
        print(f"{tid}: {data['output']}")
elif results["status"] == "timeout":
    print(f"Timeout! Still pending: {results['pending']}")

# Teammate 端使用
watcher.write_done("coder", output="/tmp/coder.txt")
# 或直接：
write_sentinel("/path/to/chaoting", "ZZ-xxx", "coder",
               status=SENTINEL_DONE, output="/tmp/coder.txt")

# 清理
watcher.cleanup()
```

---

## 完整工作流示例

### Lead Agent System Prompt 模板

```
You are the lead agent for a parallel coding task.

SENTINEL SETUP:
- Chaoting dir: ${CHAOTING_DIR}
- Task ID: ${ZOUZHE_ID}
- Write command format: 
  CHAOTING_DIR=${CHAOTING_DIR} chaoting teams sentinel-write ${ZOUZHE_ID} <name> --status done --output <file>

TASK: [Task description here]

WORKFLOW:
1. Create team "${ZOUZHE_ID}-team"
2. Spawn teammates in parallel:
   - "coder": [implement feature], write output to /tmp/${ZOUZHE_ID}-coder.txt, then write sentinel
   - "tester": [write tests], write output to /tmp/${ZOUZHE_ID}-tester.txt, then write sentinel  
   - "docs": [write docs], write output to /tmp/${ZOUZHE_ID}-docs.txt, then write sentinel

3. Wait for sentinel files:
   Check: ls ${CHAOTING_DIR}/sentinels/${ZOUZHE_ID}/
   Wait until all 3 .done files appear (poll every 5s)

4. Read all output files and produce integration summary

5. Gracefully shut down all teammates (SendMessage shutdown_request × 3)

6. TeamDelete("${ZOUZHE_ID}-team")
```

### 实测结果参考（ZZ-20260310-004）

| 指标 | 值 |
|------|----|
| 并行 teammates | 3（coder/tester/docs）|
| 总产出 | 773 行（Python+pytest+Markdown）|
| 完成时间 | ~2 分钟 |
| 通信延迟 | < 1s（文件哨兵 polling）|
| 接口对齐问题 | 有（Lead 需要提供精确接口规范）|

---

## 故障排查

### Q: Teammate 权限被拒绝

**原因**: `--dangerously-skip-permissions` 未传递给 teammate。

**解法**: 检查 `~/.acpx/config.json`，确认 `defaultAgent` 为：
```json
"defaultAgent": "claude --dangerously-skip-permissions"
```

### Q: Agent Teams 工具不可用

**原因**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 未设置。

**解法**: 
```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```
或在 `chaoting teams run` 中自动设置（已内置）。

### Q: sentinel-wait 超时

**原因**: Teammate 执行时间超过 `--timeout` 设置，或 teammate 未正确写入哨兵。

**解法**:
1. 增加 timeout：`--timeout 1200`
2. 检查 teammate system prompt 是否包含哨兵写入指令
3. 查看日志：`chaoting teams sentinel-list <zouzhe_id>`
4. 超时哨兵已自动写入，重启后不会重复等待

### Q: In-process teammate 崩溃影响整个进程

**原因**: 非交互模式下，所有 teammates 在同一进程内运行。

**解法**: 
- 尽量保持 teammate 任务简单、可快速完成
- 对关键任务使用独立 zouzhe（Chaoting 正式流程），而非 Agent Teams

### Q: 哨兵文件损坏

**原因**: 写入过程中进程崩溃，可能产生 `.tmp` 临时文件。

**解法**: `sentinel.py` 使用原子写（写临时文件后 rename），即使崩溃也不会产生损坏的 `.done` 文件。清理 `.tmp` 文件后重新运行即可。

---

## 已知限制

| 限制 | 严重度 | 说明 |
|------|--------|------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 必需 | 中 | 实验性功能，随时可能 API 变化 |
| In-process 模式下 teammate 崩溃影响 lead | 低 | 任务设计应保持简单 |
| Teammate 接口不一致 | 中 | Lead 需在 system prompt 中提供精确接口规范 |
| 无原生超时 barrier | 低 | 文件哨兵 + timeout 参数已覆盖此需求 |
| Sentinel 写入需在 teammate system prompt 中明确指示 | 中 | 一次性配置，模板化后可复用 |

---

## 适用场景

**✅ 推荐使用 Agent Teams**：
- 并行代码搜索（多模块同时搜索）
- 并行生成（代码+测试+文档同时产出）
- 独立子系统分析

**❌ 不推荐**：
- 强顺序依赖任务（A 的结果是 B 的输入）
- 长时间任务（>30 分钟）→ 改用独立 zouzhe
- 生产关键路径 → 改用 Chaoting 正式流程

---

## V0.4 规划

- [ ] Sentinel 写入自动化（teammate 无需手写命令）
- [ ] 并发度控制（最大同时 teammate 数量）
- [ ] 基于 zouzhe 的 team 生命周期管理
- [ ] Prometheus metrics（并发任务监控）

---

*文档由兵部 (bingbu) 撰写，2026-03-09*  
*参考实验：ZZ-20260310-004、ZZ-20260309-038*
