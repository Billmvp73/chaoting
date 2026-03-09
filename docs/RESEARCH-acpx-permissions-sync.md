# ACPx + Claude Code Agent Teams：权限传递与 Lead 同步 Await 研究报告

**任务 ID**: ZZ-20260309-038  
**完成日期**: 2026-03-09  
**研究范围**: ACPx v0.1.15 + Claude Code v2.1.39  
**研究方法**: 直接阅读 npm 包 minified 源码 + Claude Code CLI 源码

---

## 执行摘要

| 问题 | 结论 |
|------|------|
| 权限不传递根因 | ACPx 启动 Claude Code 时不传递 `--dangerously-skip-permissions`，导致 lead 的 `toolPermissionContext.mode` 为 "default"，teammate 继承此 "default" 模式 |
| 是否有修复方案 | ✅ 有：在 ACPx `agentCommand` 中手动添加权限 flag，或使用 `CLAUDE_CODE_TEAMMATE_COMMAND` |
| Lead 同步 Await | ❌ 原生不支持阻塞等待；需通过 idle_notification 机制 + 轮询模拟 |
| 短期可用性 | ⚠️ 权限问题有 workaround，但同步 await 无法完美解决，实用性有限 |
| 建议 | 短期用 `--dangerously-skip-permissions` workaround，中期开发 task-based wrapper |

---

## 一、权限问题根因分析

### 1.1 当前权限流转路径

```
[ACPx config: defaultPermissions=approve-all]
          │
          ▼
ACPx AcpClient.start()
  → buildAgentEnvironment(authCredentials)  ← 只传 auth 凭据，无权限 flag
  → spawn2(command, args, {env: ...})       ← command = "claude --resume <sessionId>"
          │                                    (无 --dangerously-skip-permissions)
          ▼
Lead Claude Code 进程
  toolPermissionContext.mode = "default"    ← 未设置 bypass
  sessionBypassPermissionsMode = false
          │
          ▼ (用户触发 SpawnTeammate)
ou4({planModeRequired, permissionMode: J.toolPermissionContext.mode})
  → mode = "default"                       ← 既不是 "bypassPermissions" 也不是 "acceptEdits"
  → 不添加任何权限 flag
          │
          ▼
Teammate Claude Code 进程 (via tmux sendCommandToPane)
  command = "claude --agent-id X --agent-name Y --team-name Z ..."  ← 无权限 flag
  toolPermissionContext.mode = "default"   ← 交互式权限提示
  → 执行文件操作时阻塞等待权限确认 ❌
```

### 1.2 代码层级定位

**ACPx 层** (`/home/tetter/.nvm/versions/node/v24.13.1/lib/node_modules/acpx/dist/cli.js`)：

```javascript
// Line 1057-1076: buildAgentEnvironment
function buildAgentEnvironment(authCredentials) {
  const env = { ...process.env };
  // 只设置 ACPX_AUTH_* 环境变量
  // ❌ 没有 CLAUDE_CODE_BYPASS_PERMISSIONS 或任何权限相关设置
  return env;
}

// Line 1162-1168: spawn agent
const child = spawn2(command, args, {
  cwd: this.options.cwd,
  env: buildAgentEnvironment(this.options.authCredentials),  // ← 无权限传递
  stdio: ["pipe", "pipe", "pipe"]
});
```

**ACPx 的 `permissionMode=approve-all` 作用范围**：
- ACPx 的 `permissionMode` 只用于 ACPx 自己的 `handlePermissionRequest()` 方法（line 1564-1601）
- 当 lead Claude Code 通过 **ACP 协议**请求权限时，ACPx 会根据自己的 `permissionMode` 自动批准
- 但 **teammate 的权限请求不走 ACP 协议**，而是走 Claude Code 内部的 `toolPermissionContext`
- 因此 ACPx 的 `approve-all` 对 teammate 完全无效

**Claude Code 层** (`/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js`)：

```javascript
// Line 7943266: ou4() — teammate 启动命令构建函数
function ou4(A) {
  let q = [], {planModeRequired: K, permissionMode: Y} = A || {};
  if (K);
  else if (Y === "bypassPermissions" || Og())  // Og() = sessionBypassPermissionsMode
    q.push("--dangerously-skip-permissions");
  else if (Y === "acceptEdits")
    q.push("--permission-mode acceptEdits");
  // 其余情况：不添加任何权限 flag（mode = "default"）
  // ...
}

// VNY() — SpawnTeammate 工具实现
let J = await getAppState();
let y = ou4({planModeRequired: O, permissionMode: J.toolPermissionContext.mode});
// → J.toolPermissionContext.mode = "default"（因为 ACPx 没传 flag）
// → y = "" (无权限 flag)
sendCommandToPane(paneId, `claude ${k} ${y}`);
```

### 1.3 为什么 `defaultPermissions=approve-all` 不帮 teammates

| 层级 | 机制 | 覆盖 teammate? |
|------|------|---------------|
| ACPx `permissionMode=approve-all` | 拦截 ACP 协议中的 `requestPermission` 事件 | ❌ 仅 lead 的 ACP 权限请求 |
| Claude Code `toolPermissionContext` | 进程内部状态，决定是否提示用户 | ✅ 但需要对 lead 和 teammate 都设置 |
| `--dangerously-skip-permissions` flag | 设置 `sessionBypassPermissionsMode=true` | ✅ 设置后 `ou4()` 会传递给 teammate |

### 1.4 解决方案

#### 方案 A：修改 ACPx agentCommand（推荐，成本低）

在 ACPx 配置中修改 `agentCommand` 为 `claude --dangerously-skip-permissions`：

```json
// ~/.config/acpx/config.json 或等效配置
{
  "agentCommand": "claude --dangerously-skip-permissions",
  "defaultPermissions": "approve-all"
}
```

**优点**：
- 零代码修改，只需配置
- Lead 和 teammate 都会自动 bypass 权限

**缺点**：
- `--dangerously-skip-permissions` 需要非 root 用户或沙箱环境
- 影响所有通过该 ACPx 实例启动的 lead

**工作量**：⭐ 最低（5分钟）  
**风险**：低（sandbox 内使用是设计用途）

---

#### 方案 B：使用 `CLAUDE_CODE_TEAMMATE_COMMAND` 环境变量

```bash
export CLAUDE_CODE_TEAMMATE_COMMAND="claude --dangerously-skip-permissions"
```

或在 ACPx 启动时注入：

```javascript
// buildAgentEnvironment 中可以添加
env.CLAUDE_CODE_TEAMMATE_COMMAND = "claude --dangerously-skip-permissions";
```

**注意**：当前 ACPx 的 `buildAgentEnvironment()` 不支持自定义环境变量，需要修改 ACPx 源码或在父进程环境中设置。

**工作量**：⭐⭐ 低  
**风险**：低  

---

#### 方案 C：本地 patch ACPx `buildAgentEnvironment`

修改 `/home/tetter/.nvm/versions/node/v24.13.1/lib/node_modules/acpx/dist/cli.js`，在 `buildAgentEnvironment` 中当 `permissionMode=approve-all` 时设置相应环境变量。

**工作量**：⭐⭐⭐ 中（修改 minified 源码，升级后失效）  
**风险**：中（维护成本高，非官方支持）  

---

#### 方案 D：等待官方支持

ACPx 或 Claude Code 官方将权限传递作为一等公民支持。目前无 ETA。

**工作量**：0  
**风险**：无法控制时间线  

---

## 二、Lead 同步 Await 可行性分析

### 2.1 当前设计：基于 idle_notification 的异步模型

Claude Code Agent Teams 的核心通信机制：

```
Lead                                    Teammate
  │                                        │
  │─── SpawnTeammate(name, prompt) ──────▶ │ 启动独立进程
  │                                        │ 执行任务...
  │                                        │
  │ ◀── idle_notification(Rg1()) ───────── │ 完成后发送 idle_notification
  │    {type:"idle_notification",          │
  │     from: agentName,                   │
  │     summary: "...",                    │
  │     completedStatus: "success"} │
  │                                        │
  │ (lead 继续其他工作，无需轮询)              │
```

关键函数（Claude Code source）：
- `Rg1(A, q)` — 构建 idle_notification 对象（line 2055）
- `$MY(A, q)` — 标记 teammate 为 idle（line 2019）
- `OMY(A, q)` — 标记 teammate 为非 idle（line 2021）

### 2.2 ACPx 的 `waitForCompletion` 机制

ACPx 有 `waitForCompletion` 参数，但它用于 **ACPx 自己的任务队列**，不是 Agent Teams 的 teammate 同步：

```javascript
// ACPx line 5101-5125: runQueuedTask
async function runQueuedTask(sessionRecordId, task, options) {
  const outputFormatter = task.waitForCompletion 
    ? new QueueTaskOutputFormatter(task) 
    : DISCARD_OUTPUT_FORMATTER;
  const result = await runSessionPrompt({...});  // 等待 lead 完成
  if (task.waitForCompletion) {
    task.send({ type: "result", requestId: task.requestId, result });
  }
}
```

这是 ACPx 等待整个 lead session 完成的机制，**不是 lead 等待 teammate 完成**。

### 2.3 实现同步 Await 的技术方案

#### 方案 1：利用 idle_notification 实现 lead 侧等待（最可行）

Lead 可以在 system prompt 中被指示：

```
在分配任务给 teammate 后，进入等待循环：
1. 使用 SendMessage 通知 teammate 开始任务
2. 轮询检查 teammate 是否发来 idle_notification
3. 收到 idle_notification 后读取结果
4. 综合结果并报告
```

**本质**：Lead 自己实现轮询逻辑（通过 LLM 控制流，不是 CPU 自旋）  
**token 消耗估计**：
- 每次 lead turn ≈ 500-2000 tokens
- 等待 1 个 teammate，平均 10 turns ≈ 5,000-20,000 tokens
- 等待 3 个 teammates ≈ 15,000-60,000 tokens

**工作量**：⭐⭐ 低（通过 system prompt 指示即可）  
**风险**：中（LLM 不一定严格遵守等待逻辑，可能提前总结）

---

#### 方案 2：文件系统哨兵（File Sentinel）

Teammate 完成时写入一个 sentinel 文件：

```
/tmp/teammate-results/agent-alice.done
/tmp/teammate-results/agent-alice.json
```

Lead 在 system prompt 中被指示轮询这些文件。

**优点**：可靠，不依赖消息系统  
**缺点**：需要 teammate 遵守协议写文件；在 in-process 模式下不适用（无独立进程）

**工作量**：⭐⭐ 低  
**风险**：低（文件系统操作可靠）  
**token 消耗**：比方案 1 低（lead 只需检查文件，不需要"理解"消息）

---

#### 方案 3：Chaoting 层面的同步控制（推荐用于生产）

由 Chaoting 而非 Claude Code 控制并发：

```python
# Chaoting dispatcher 同步等待多个 sub-agent
results = {}
for agent_id, task in tasks.items():
    spawn_subagent(agent_id, task)

# 轮询直到所有 agent 完成
while not all(r['done'] for r in results.values()):
    for agent_id in pending:
        status = check_subagent_status(agent_id)
        if status['done']:
            results[agent_id] = status
    time.sleep(POLL_INTERVAL)
```

**优点**：
- Chaoting 有完整的 zouzhe 状态机
- 不依赖 Claude Code 内部机制
- 可以处理超时、重试

**缺点**：
- 不在 Agent Teams 框架内
- 需要跨 session 通信（ACPx 没有原生支持）

**工作量**：⭐⭐⭐⭐ 较高  
**风险**：中  

---

#### 方案 4：ACP 规范中的同步点（理论研究）

查阅 ACP 规范（Model Context Protocol 扩展）：
- ACP 1.0 规范中没有定义 "sync barrier" 或 "barrier synchronization" 原语
- `submit_prompt` with `waitForCompletion=true` 只适用于 ACPx 队列，不适用 Agent Teams
- Claude Code 的 Agent Teams 是**实验性功能**，规范不完整

**结论**：ACP 规范层面没有同步 await 原语，需要应用层实现。

---

### 2.4 方案对比

| 方案 | 可靠性 | token 成本 | 实现难度 | 推荐度 |
|------|--------|-----------|---------|--------|
| idle_notification 轮询 | 中 | 高 | 低 | ⭐⭐⭐ |
| 文件系统哨兵 | 高 | 低 | 低 | ⭐⭐⭐⭐ |
| Chaoting 层控制 | 高 | 低 | 高 | ⭐⭐⭐⭐ (长期) |
| ACP 同步原语 | N/A | N/A | N/A | ❌ 不存在 |

---

## 三、对 Chaoting 的建议

### 3.1 短期（立即可行）

**权限问题**：在 ACPx `agentCommand` 中加入 `--dangerously-skip-permissions`：
```
agentCommand = "claude --dangerously-skip-permissions"
```
这样 lead 的 `toolPermissionContext.mode` 会是 "bypassPermissions"，`ou4()` 会自动为 teammate 添加同样的 flag。

**同步等待**：使用文件系统哨兵方案。在分配 Agent Teams 任务时：
1. Teammate system prompt 中规定完成后写入 `/tmp/chaoting-results/{task_id}.json`
2. Lead 或 Chaoting dispatcher 检查文件存在

### 3.2 中期（1-2周）

开发 **Chaoting AgentTeams Wrapper**：
- `chaoting spawn-team` 命令，启动多个 subagent（每个是独立 ACPx session）
- Dispatcher 维护 team 状态，汇总结果
- 每个 subagent 完成后调用 `chaoting done <task_id>` 通报结果
- Lead session 汇总 subagent 结果

这比 Claude Code 原生 Agent Teams 更可靠，因为：
1. 利用已有的 Chaoting 状态机（zouzhe/liuzhuan）
2. 不依赖实验性功能
3. 天然支持超时、重试、监控

### 3.3 长期（待官方支持）

等待 Claude Code 或 ACPx 官方支持：
1. 权限继承（`permissionMode` 透明传递给 teammate）
2. 同步 await primitive（`WaitForTeammate(name, timeout)` 工具）
3. 稳定的 Agent Teams API（不再需要 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`）

---

## 四、结论

**短期是否可用 Agent Teams？**  
⚠️ **有条件可用**——权限问题通过配置 workaround 可解，但同步 await 不可靠，适合"fire and forget"型并行任务，不适合"gather and synthesize"型任务。

**推荐用途**：
- ✅ 并行代码搜索（多 teammate 各找各的，异步汇报）
- ✅ 并行文档生成（不需要互相等待）
- ❌ 顺序依赖任务（A 的结果是 B 的输入）
- ❌ 需要精确协调的任务

**对 Chaoting 的最终建议**：优先建设 Chaoting 层面的并发控制（方案 3），而不是深度依赖 Claude Code Agent Teams 实验性 API。在 Chaoting 框架内，每个 subagent 是一个独立的 zouzhe，状态管理、超时、重试都有完整支持，远比 Agent Teams 更可靠。

---

## 五、参考资源

| 资源 | 路径/链接 |
|------|-----------|
| ACPx CLI 源码 | `/home/tetter/.nvm/versions/node/v24.13.1/lib/node_modules/acpx/dist/cli.js` |
| Claude Code CLI 源码 | `/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js` |
| ACPx `buildAgentEnvironment` | ACPx cli.js line 1057-1076 |
| ACPx `handlePermissionRequest` | ACPx cli.js line 1564-1602 |
| Claude Code `ou4()` (teammate permission flags builder) | claude-code cli.js, 包含 `"--dangerously-skip-permissions"` 的函数 |
| Claude Code `VNY()` (SpawnTeammate 实现) | claude-code cli.js, 包含 `sendCommandToPane` 的函数 |
| Claude Code `Rg1()` (idle_notification 构造) | claude-code cli.js line 2055 |
| ACPx `runQueuedTask` (waitForCompletion) | ACPx cli.js line 5101-5125 |
| ACPx npm | `acpx@0.1.15` |
| Claude Code npm | `@anthropic-ai/claude-code@2.1.39` |
| Agent Teams 实验 flag | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |
| Teammate 命令 env var | `CLAUDE_CODE_TEAMMATE_COMMAND` |

---

*报告生成：兵部 (bingbu)，2026-03-09*
