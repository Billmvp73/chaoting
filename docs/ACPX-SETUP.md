# ACPX-SETUP.md — ACPx 安装与配置说明

> 版本：v1.0  
> 安装日期：2026-03-09  
> 执行部门：工部（gongbu）  
> 依据奏折：ZZ-20260309-037

---

## 一、什么是 ACPx

ACPx 是 [Agent Client Protocol (ACP)](https://github.com/i-am-bee/acp) 的 headless CLI 客户端，用于驱动 Claude Code、Codex、Gemini 等 AI 编码工具。

核心特性：
- **持久化会话**：`acpx claude prompt` — 在已有会话中追加对话
- **单次调用**：`acpx claude exec` — 无状态单次执行
- **权限控制**：可配置 approve-all / approve-reads / deny-all
- **结构化输出**：支持 text / json / quiet 格式

---

## 二、安装信息

### 安装命令

```bash
/home/tetter/.nvm/versions/node/v24.13.1/bin/npm install -g acpx@0.1.15 \
  --prefix /home/tetter/.nvm/versions/node/v24.13.1
```

> **注意**：需使用 nvm 管理的 npm，系统 npm（`/usr/bin/npm`）无 `/usr/lib/node_modules` 写权限。

### 安装路径

```
/home/tetter/.nvm/versions/node/v24.13.1/bin/acpx
```

### 验证版本

```bash
/home/tetter/.nvm/versions/node/v24.13.1/bin/acpx --version
# => 0.1.15
```

---

## 三、支持的编码工具

| 工具 | 状态 | 路径 | 备注 |
|------|------|------|------|
| **claude** | ✅ 可用 | `/usr/local/bin/claude` | Claude Code 2.1.39 |
| codex | ❌ 未安装 | — | 如需使用需另行安装 |
| opencode | ❌ 未安装 | — | 如需使用需另行安装 |
| gemini | ❌ 未安装 | — | 如需使用需另行安装 |

> **defaultAgent 设为 `claude`**（非任务原计划的 codex），因 claude 是本机唯一可用的编码工具。

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
| `defaultPermissions` | `approve-all` | 自动批准所有权限请求（适合 CI/headless 环境）|
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

因此，**兵部（bingbu）和工部（gongbu）都能直接调用 `acpx`**，无需额外配置。

---

## 六、常用命令

### 单次执行（无状态）

```bash
acpx claude exec "你的提示词"
acpx claude exec --file prompt.txt
```

### 持久化会话（有状态）

```bash
# 在当前目录的默认会话中追加 prompt
acpx claude prompt "继续上一步..."

# 使用指定会话名
acpx claude prompt --session my-session "..."

# 取消正在运行的 prompt
acpx claude cancel
```

### 指定工作目录

```bash
# 默认 cwd 为 ~/.themachine/workspace-gongbu
acpx --cwd /home/tetter/self-project/chaoting claude exec "查看 src/dispatcher.py"
```

### 输出格式

```bash
acpx claude exec --format json "..."    # JSON 结构化输出
acpx claude exec --format quiet "..."  # 静默模式（仅返回结果）
```

---

## 七、与 Chaoting 的集成点

### 当前状态

ACPx 已安装，但**尚未与 Chaoting dispatcher 深度集成**。目前各部门（bingbu、gongbu）作为 OpenClaw agent 独立运行，通过 TheMachine 接收任务。

### 潜在集成场景

1. **AI-assisted 编码**：部门接收奏折后，通过 `acpx claude exec` 驱动 Claude Code 执行具体代码修改，而非完全依赖 agent 推理
2. **验收测试自动化**：部门完成后用 `acpx claude exec` 运行验收标准检查
3. **多工具协作**：未来安装 codex 后，可在同一奏折中串联 codex（规划）+ claude（执行）

### 调用示例（未来集成参考）

```bash
# gongbu 接到修改代码的奏折后：
acpx --cwd /home/tetter/self-project/chaoting \
  claude exec \
  "修改 src/dispatcher.py：在 notify_enqueue 中添加重试逻辑..."
```

---

## 八、已知问题与限制

1. **系统 npm 无写权限**：安装必须使用 nvm 的 npm + `--prefix` 参数（见第二节）
2. **`--approve-all` 是顶级选项**，不是子命令选项：需要 `acpx --approve-all claude exec "..."` 而非 `acpx claude --approve-all exec "..."`
3. **codex/opencode/gemini 未安装**：当前仅 claude 可用

---

## 九、回滚方法

```bash
/home/tetter/.nvm/versions/node/v24.13.1/bin/npm uninstall -g acpx \
  --prefix /home/tetter/.nvm/versions/node/v24.13.1
rm -rf ~/.acpx
```
