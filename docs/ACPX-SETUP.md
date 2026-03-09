# ACPX-SETUP.md — ACPx 安装、配置与测试报告

> 版本：v2.0  
> 更新日期：2026-03-09  
> 执行部门：工部（gongbu）  
> 依据奏折：ZZ-20260309-037（第2轮）

---

## 一、什么是 ACPx

ACPx 是 [Agent Client Protocol (ACP)](https://github.com/i-am-bee/acp) 的 headless CLI 客户端，用于驱动 Claude Code、Codex、Gemini 等 AI 编码工具。

核心特性：
- **持久化会话**：`acpx claude prompt` — 在已有会话中追加对话
- **单次调用**：`acpx claude exec` — 无状态单次执行
- **Agent Teams**：实验性多 teammate 并行工作（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`）
- **权限控制**：支持 approve-all / approve-reads / deny-all
- **结构化输出**：支持 text / json / quiet 格式

---

## 二、安装信息

### 安装命令

```bash
/home/tetter/.nvm/versions/node/v24.13.1/bin/npm install -g acpx@0.1.15 \
  --prefix /home/tetter/.nvm/versions/node/v24.13.1
```

> **⚠️ 注意**：必须使用 nvm 管理的 npm，系统 npm（`/usr/bin/npm`）无 `/usr/lib/node_modules` 写权限。

### 安装路径

```
/home/tetter/.nvm/versions/node/v24.13.1/bin/acpx
```

### 验证安装

```bash
acpx --version  # => 0.1.15
```

---

## 三、支持的编码工具

| 工具 | 状态 | 路径 | 备注 |
|------|------|------|------|
| **claude** | ✅ 可用 | `/usr/local/bin/claude` | Claude Code 2.1.39 |
| codex | ❌ 未安装 | — | 如需使用需另行安装 |
| opencode | ❌ 未安装 | — | 如需使用需另行安装 |
| gemini | ❌ 未安装 | — | 如需使用需另行安装 |

> `defaultAgent` 设为 `claude`（本机唯一可用的编码工具）。

---

## 四、全局配置

### 配置文件路径

```
~/.acpx/config.json
```

### 当前配置

```json
{
  "defaultAgent": "claude",
  "defaultPermissions": "approve-all",
  "nonInteractivePermissions": "deny",
  "authPolicy": "skip",
  "ttl": 300,
  "timeout": null,
  "format": "text"
}
```

### 配置项说明

| 字段 | 值 | 说明 |
|------|----|------|
| `defaultAgent` | `claude` | 默认使用 Claude Code |
| `defaultPermissions` | `approve-all` | 自动批准所有权限请求（适合 headless 环境）|
| `nonInteractivePermissions` | `deny` | 无法交互时拒绝权限（安全保障）|
| `authPolicy` | `skip` | 跳过认证要求（不中断执行）|
| `ttl` | `300` | 会话闲置 300 秒后自动关闭 |
| `timeout` | `null` | 不设响应超时（由调用方控制）|
| `format` | `text` | 默认输出纯文本 |

---

## 五、PATH 配置

`/home/tetter/.nvm/versions/node/v24.13.1/bin` 已在以下环境的 PATH 中：

- **chaoting-dispatcher.service**：`Environment=PATH=/home/tetter/.nvm/versions/node/v24.13.1/bin:...`
- **openclaw agent 环境**：与 dispatcher 共享同一 PATH 配置

**兵部（bingbu）和工部（gongbu）都能直接调用 `acpx`，无需额外配置。**

---

## 六、功能测试结果

### 测试 1：基础 Claude Code 会话 ✅

```bash
acpx claude sessions new --name test-basic
acpx claude -s test-basic "Reply with only the text: ACPx_TEST_OK"
```

**结果：**
```
[acpx] created session test-basic (2fadcf04-e4aa-4d67-8bc6-a3ad0aceea1d)
[acpx] session reconnect → session/new → ACPx_TEST_OK
```

**观察：**
- ✅ 会话创建成功
- ✅ Claude Code 正确响应 prompt
- ✅ 会话自动重连（agent 重启后无缝 reconnect）
- ✅ 输出格式正确（text 模式）

---

### 测试 2：Claude Code Agent Teams 实验 ✅（部分成功）

```bash
acpx claude sessions new --name test-team
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 acpx claude -s test-team \
  "Create an agent team: code-reviewer + test-writer..."
```

**结果：**

**Agent Teams 基础功能工作正常：**
- ✅ `TeamCreate` 工具被调用，团队 `chaoting-review` 创建成功
- ✅ 两个 teammate 通过 `Task` 工具并行启动（`code-reviewer@chaoting-review`、`test-writer@chaoting-review`）
- ✅ `SendMessage` 工具可用，lead 可以向 teammate 发消息
- ✅ 关闭 teammate：`SendMessage` shutdown_request 成功

**局限性：**
- ⚠️ Teammate 因缺少 bash 权限（approve-all 配置仍需每次确认）无法自动完成文件搜索
- ⚠️ Teammate 结果需要通过 `SendMessage/CheckMailbox` 异步收集，lead 无法同步等待
- ⚠️ 当前配置下 teammate 的工具权限与 lead 独立，需要 approve-all 在每个 subagent 中单独生效

**Lead 直接分析结果（代替 teammate 输出）：**

#### Top 3 代码问题（`src/chaoting` CLI）

1. **DB 连接泄漏**：多处 `cmd_*` 函数在 `out(ok=False)` 前未调用 `db.close()`，`out()` 内部 `sys.exit()` 导致连接不能释放（如 `cmd_progress`）。建议改用 `with contextlib.closing(get_db()) as db:` 或 try/finally。

2. **`.env` 解析不处理引号**：第 19-22 行将整行 `_v.strip()` 作为值，若 `.env` 内容为 `KEY="value"` 则值包含引号本身，与标准 dotenv 行为不符。

3. **`cmd_fail` 无 agent 权限校验**：允许从 `planning` 状态 fail，且未检查 `OPENCLAW_AGENT_ID`，任何 agent 都可以将正在规划的奏折标记失败，存在安全漏洞。

#### 3 个 plan 命令测试用例

| # | 场景 | 操作 | 预期结果 |
|---|------|------|---------|
| 1 | 正常提交（需审核） | `review_required=2` 奏折提交 plan | `state=reviewing`，liuzhuan 有 submit_review 记录 |
| 2 | 免审直接执行 | `review_required=0` 奏折提交 plan | `state=executing`，liuzhuan 有 complete 记录 |
| 3 | 状态冲突拒绝 | 向非 planning 状态奏折提交 plan | `{"ok":false, "error":"state conflict"}`，DB 状态不变 |

---

### 测试 3：会话管理 ✅

```bash
acpx claude sessions list
acpx claude sessions close test-basic
acpx claude sessions close test-team
acpx claude sessions list
```

**结果：**
```
# 关闭前
76561496...  test-team   /workspace  2026-03-09T18:46:47Z
2fadcf04...  test-basic  /workspace  2026-03-09T18:43:21Z

# 关闭后
76561496... [closed]  test-team
2fadcf04... [closed]  test-basic
```

- ✅ 会话列表正常显示（ID、名称、cwd、创建时间）
- ✅ 会话关闭正常，`[closed]` 状态正确标记

---

## 七、常用命令

### 单次执行（无状态）

```bash
acpx claude exec "你的提示词"
acpx claude exec --file prompt.txt
```

### 持久化会话（有状态）

```bash
# 创建命名会话
acpx claude sessions new --name my-session

# 在命名会话中发送 prompt
acpx claude -s my-session "继续上一步..."

# 取消正在运行的 prompt
acpx claude cancel

# 查看会话状态
acpx claude sessions show my-session

# 关闭会话
acpx claude sessions close my-session
```

### 指定工作目录

```bash
# 默认 cwd 为 ~/.themachine/workspace-gongbu
acpx --cwd /home/tetter/self-project/chaoting claude exec "查看 src/dispatcher.py"
```

### Agent Teams（实验性）

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
acpx claude -s my-team "Create an agent team with 2 teammates: ..."
```

---

## 八、与 Chaoting 的集成点

### 当前状态

ACPx 已安装，基础功能和 Agent Teams 实验性功能已验证可用。目前各部门作为 OpenClaw agent 独立运行，通过 TheMachine 接收任务。

### 潜在集成场景

1. **AI-assisted 编码**：部门通过 `acpx claude exec` 驱动 Claude Code 执行具体代码修改
2. **验收测试自动化**：完成后用 `acpx claude exec` 运行验收标准检查
3. **并行代码审查**：Agent Teams 模式让 code-reviewer 和 test-writer 并行工作

### 调用示例

```bash
# gongbu 接到修改代码的奏折后：
acpx --cwd /home/tetter/self-project/chaoting \
  claude exec \
  "修改 src/dispatcher.py：在 notify_enqueue 中添加重试逻辑..."
```

---

## 九、已知问题与限制

1. **系统 npm 无写权限**：安装必须使用 `nvm npm --prefix` 参数
2. **`--approve-all` 是顶级选项**：用法为 `acpx --approve-all claude exec "..."` 而非 `acpx claude --approve-all`
3. **Agent Teams 异步**：teammate 结果需通过 mailbox 异步收集，lead 无法同步 await
4. **Teammate 权限独立**：`defaultPermissions=approve-all` 不自动传递给 subagent，每个 teammate 需单独配置

---

## 十、回滚方法

```bash
/home/tetter/.nvm/versions/node/v24.13.1/bin/npm uninstall -g acpx \
  --prefix /home/tetter/.nvm/versions/node/v24.13.1
rm -rf ~/.acpx
```
