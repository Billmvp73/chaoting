# EXPERIMENT: Claude Code Agent Teams
**Date:** 2026-03-09  
**Executor:** bingbu (ZZ-20260309-035)  
**Status:** ❌ 实验无法执行——环境未配置

---

## 实验目标

测试 Claude Code Agent Teams 功能，验证：
1. `sessions_spawn(runtime="acp", agentId="claude-code")` 是否可用
2. 两个 teammate 是否能独立分工（列文件 + 统计行数）
3. 能否作为未来兵部工作流基础

---

## 执行过程

### Step 1: 检查可用 Agent IDs

```
agents_list() →
{
  "requester": "bingbu",
  "allowAny": false,
  "agents": [{"id": "bingbu", "configured": true}]
}
```

结论：`agents_list` 仅返回 subagent allowlist（bingbu 自身），不含 ACP harness IDs。

### Step 2: 执行 sessions_spawn

```python
sessions_spawn(
  task="Create an agent team with 2 teammates. Teammate 1: list files in src/. Teammate 2: count lines in src/chaoting. Report both results.",
  runtime="acp",
  agentId="claude-code",
  mode="run",
  cwd="/home/tetter/self-project/chaoting",
  sandbox="inherit",
  env={"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
  runTimeoutSeconds=120
)
```

**返回结果：**
```json
{
  "status": "error",
  "error": "ACP runtime backend is not configured. Install and enable the acpx runtime plugin."
}
```

---

## 实验结论

### ❌ 当前环境不可用

| 检查项 | 结果 |
|--------|------|
| ACP runtime backend | ❌ 未安装/未启用（需 `acpx` 插件） |
| claude-code agentId | ❌ 无法路由（ACP未配置） |
| Agent Teams 功能 | ❌ 无法验证 |

### 根本原因

**ACP runtime backend 未配置。**  
`sessions_spawn` 的 `runtime="acp"` 需要 OpenClaw 安装并启用 `acpx` 插件。
当前部署中此插件未安装，所有 ACP harness 调用（claude-code、codex 等）均不可用。

---

## 替代方案

若目标是「多 agent 并行工作」，当前环境可用的替代方案：

| 方案 | 可用性 | 说明 |
|------|--------|------|
| `sessions_spawn(runtime="subagent")` | ✅ 有限可用 | 仅允许 `bingbu` 自身 |
| 直接 `exec` 并行子进程 | ✅ 可用 | 无 AI 能力，纯 shell |
| PTY + Claude Code CLI（本地） | ⚠️ 需验证 | `claude --print` 模式 |
| ACP via `acpx` plugin | ❌ 需安装配置 | 联系皇上安装 acpx |

---

## 建议

1. **短期**：如需多任务并行，使用 `exec` + `subprocess` 在单次 bingbu session 内串行执行
2. **中期**：请皇上安装 `acpx` 插件并配置 `acp.allowedAgents` 包含 `claude-code`
3. **长期**：ACP Agent Teams 是有潜力的工作流加速器，值得在配置完成后重新实验

---

## 附录：复现命令

```python
# 当 acpx 安装后，可用以下命令重新测试：
sessions_spawn(
  task="Create an agent team with 2 teammates. Teammate 1: list files in src/. Teammate 2: count lines in src/chaoting. Report both results.",
  runtime="acp",
  agentId="claude-code",
  mode="run",
  cwd="/home/tetter/self-project/chaoting",
  sandbox="inherit",
  env={"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
)
```
