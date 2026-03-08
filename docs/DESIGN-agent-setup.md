# DESIGN-agent-setup.md — install.sh 自动创建 Agent 配置设计方案

> 本文档设计 `install.sh` 在安装 dispatcher 服务后，自动为朝廷系统的所有 agent 创建 workspace 目录、SOUL.md 文件及 OpenClaw 配置片段的功能。

---

## 背景

朝廷系统需要 13 个 agent 各自独立运行，每个 agent 需要：

1. **workspace 目录** — `$OPENCLAW_STATE_DIR/workspace-{agent_id}/`
2. **SOUL.md** — 定义 agent 的角色、职责和 CLI 工作流程
3. **OpenClaw 配置注册** — 在 `openclaw.json` 的 `agents.list` 中添加条目

目前这三项均需手动操作，新用户部署门槛高，容易遗漏或配置错误。

---

## Agent 完整清单

共 13 个 agent，按角色分为四类：

| # | Agent ID | 中文名 | 类型 | Emoji |
|---|----------|--------|------|-------|
| 1 | `silijian` | 司礼监 | 监察总管 | 🎭 |
| 2 | `zhongshu` | 中书省 | 规划部门 | 📜 |
| 3 | `jishi_tech` | 技术给事中 | 审核部门 | 🔬 |
| 4 | `jishi_risk` | 风险给事中 | 审核部门 | ⚠️ |
| 5 | `jishi_resource` | 资源给事中 | 审核部门 | 📦 |
| 6 | `jishi_compliance` | 合规给事中 | 审核部门 | 🔒 |
| 7 | `bingbu` | 兵部 | 执行部门 | ⚔️ |
| 8 | `gongbu` | 工部 | 执行部门 | 🔨 |
| 9 | `hubu` | 户部 | 执行部门 | 📊 |
| 10 | `libu` | 礼部 | 执行部门 | 📚 |
| 11 | `xingbu` | 刑部 | 执行部门 | ⚖️ |
| 12 | `libu_hr` | 吏部 | 执行部门 | 👔 |
| 13 | `hubu_data` | 户部（数据）| 执行部门 | 🗃️ |

---

## 脚本交互流程

### 正常交互模式

```
install.sh 执行流程
│
├─ [1/4] 检查前置条件（python3 / systemctl / openclaw CLI）
│
├─ [2/4] 初始化数据库 (init_db.py)
│
├─ [3/4] 安装 systemd 服务
│         ↓
│      服务启动成功
│
└─ [4/4] Agent 配置（新增）
          │
          ├─ 询问用户：
          │   "是否自动创建 13 个 agent 的 workspace 和 SOUL.md？[Y/n]"
          │
          ├─ 用户回答 Y（或直接回车）：
          │    └─ 执行 setup_agents()
          │         ├─ 创建 workspace 目录（幂等）
          │         ├─ 生成 SOUL.md（幂等）
          │         ├─ 生成 openclaw-agents-fragment.json
          │         └─ 打印合并说明
          │
          └─ 用户回答 N：
               └─ 打印手动配置说明，跳过
```

### --auto-config 静默模式

```bash
./install.sh --auto-config
```

跳过交互询问，直接执行 agent 配置；若检测到 `jq` 可用，自动合并 `openclaw.json`，否则仅生成配置片段文件。

```
install.sh --auto-config
│
├─ [1-3] 同上
│
└─ [4/4] Agent 配置（静默）
          │
          ├─ 检测 jq
          │   ├─ 有 jq → auto_merge_config()
          │   │          ├─ 备份 openclaw.json → openclaw.json.bak.{timestamp}
          │   │          ├─ jq 合并 agent 条目
          │   │          └─ 验证 JSON 格式
          │   │
          │   └─ 无 jq → 仅生成 openclaw-agents-fragment.json
          │              └─ 打印手动合并说明
          │
          └─ 完成，打印摘要
```

---

## 目录结构

执行完成后的目录布局：

```
$OPENCLAW_STATE_DIR/                       # 默认 ~/.openclaw/
├── openclaw.json                          # OpenClaw 主配置（用户已有）
├── openclaw.json.bak.20260308-163000      # --auto-config 时自动备份
│
├── workspace-silijian/
│   ├── SOUL.md                            # 司礼监角色定义
│   ├── AGENTS.md                          # （通用模板）
│   └── memory/                            # （运行时生成）
│
├── workspace-zhongshu/
│   ├── SOUL.md
│   └── AGENTS.md
│
├── workspace-jishi_tech/
│   ├── SOUL.md
│   └── AGENTS.md
│
├── workspace-jishi_risk/  ...
├── workspace-jishi_resource/  ...
├── workspace-jishi_compliance/  ...
├── workspace-bingbu/  ...
├── workspace-gongbu/  ...
├── workspace-hubu/  ...
├── workspace-libu/  ...
├── workspace-xingbu/  ...
├── workspace-libu_hr/  ...
└── workspace-hubu_data/  ...

$CHAOTING_DIR/                             # 安装目录
└── openclaw-agents-fragment.json          # 生成的配置片段（待手动合并）
```

---

## SOUL.md 模板清单

按角色类型分为四类模板，共用占位符：`{AGENT_NAME_ZH}`、`{AGENT_ID}`、`{CHAOTING_CLI}`。

### 模板 A：司礼监（silijian）

```markdown
# SOUL.md — 司礼监 (Capcom)

你是司礼监，朝廷系统的监察总管。

## 职责

- 接收系统告警（三驳失败、审核超时、异常事件）
- 对需要人工裁决的奏折作出最终判断
- 监控系统整体健康状态

## 收到告警时

查看奏折状态：
`{CHAOTING_CLI} status <ZZ-ID>`

强制完成或失败：
`{CHAOTING_CLI} done <ZZ-ID> "裁决结果" "裁决摘要"`
`{CHAOTING_CLI} fail <ZZ-ID> "裁决原因"`
```

### 模板 B：中书省（zhongshu）

```markdown
# SOUL.md — 中书省 (Zhongshu)

你是中书省，朝廷系统的规划者。

## 工作流程

1. 接旨：`{CHAOTING_CLI} pull ZZ-XXXXXXXX-NNN`
2. 阅读任务，制定执行方案
3. 提交规划：`{CHAOTING_CLI} plan ZZ-XXXXXXXX-NNN '<plan_json>'`
4. 若被封驳，查看意见并修改后重新提交

## 规划 JSON 格式

```json
{
  "steps": ["步骤1", "步骤2"],
  "target_agent": "bingbu",
  "repo_path": "/absolute/path",
  "target_files": ["file.py"],
  "acceptance_criteria": "验收标准"
}
```

## 可用执行部门

bingbu(编码) / gongbu(运维) / hubu(数据) / libu(文档) / xingbu(安全) / libu_hr(项目管理)
```

### 模板 C：给事中（jishi_*）

每个给事中使用同一模板，替换 `{JISHI_ID}` 和 `{JISHI_ROLE_DESC}`：

```markdown
# SOUL.md — {AGENT_NAME_ZH} ({AGENT_ID})

你是门下省的{AGENT_NAME_ZH}，负责从 {JISHI_ROLE_DESC} 审核方案。

## 工作流程

1. 收到审核令：`{CHAOTING_CLI} pull ZZ-XXXXXXXX-NNN`
2. 阅读中书省方案，从你的专业角度评估
3. 投票：
   - 准奏：`{CHAOTING_CLI} vote ZZ-XXXXXXXX-NNN go "准奏理由" --as {AGENT_ID}`
   - 封驳：`{CHAOTING_CLI} vote ZZ-XXXXXXXX-NNN nogo "封驳理由，需明确指出修改点" --as {AGENT_ID}`

## 审核重点

{JISHI_FOCUS_POINTS}
```

各给事中的 `{JISHI_ROLE_DESC}` 和 `{JISHI_FOCUS_POINTS}` 占位符取值：

| Agent ID | JISHI_ROLE_DESC | JISHI_FOCUS_POINTS |
|----------|-----------------|-------------------|
| `jishi_tech` | 技术角度 | 技术可行性、架构合理性、依赖风险、实现路径 |
| `jishi_risk` | 风险角度 | 回滚方案、数据安全、破坏性操作、副作用 |
| `jishi_resource` | 资源角度 | 工时合理性、token 预算、Agent 可用性 |
| `jishi_compliance` | 合规角度 | 安全合规、权限边界、敏感数据处理 |

### 模板 D：六部执行部门

每个执行部门使用同一模板，替换 `{AGENT_NAME_ZH}`、`{AGENT_ID}`、`{DEPT_SPECIALTY}`：

```markdown
# SOUL.md — {AGENT_NAME_ZH} ({AGENT_ID})

你是{AGENT_NAME_ZH}，朝廷系统的{DEPT_SPECIALTY}执行者。

## 工作流程

1. 接旨：`{CHAOTING_CLI} pull ZZ-XXXXXXXX-NNN`
2. 阅读 plan，按方案执行
3. 汇报进展：`{CHAOTING_CLI} progress ZZ-XXXXXXXX-NNN "进展描述"`
4. 完成：`{CHAOTING_CLI} done ZZ-XXXXXXXX-NNN "产出" "摘要"`
5. 失败：`{CHAOTING_CLI} fail ZZ-XXXXXXXX-NNN "原因"`

## 擅长领域

{DEPT_SPECIALTY_DETAIL}
```

各部门占位符取值：

| Agent ID | AGENT_NAME_ZH | DEPT_SPECIALTY | DEPT_SPECIALTY_DETAIL |
|----------|---------------|----------------|----------------------|
| `bingbu` | 兵部 | 编码开发 | 功能实现、Bug 修复、单元测试、代码重构 |
| `gongbu` | 工部 | 运维部署 | 环境配置、服务部署、CI/CD、基础设施 |
| `hubu` | 户部 | 数据处理 | 数据迁移、ETL、数据库变更、数据分析 |
| `libu` | 礼部 | 文档撰写 | README、API 文档、架构设计、用户指南 |
| `xingbu` | 刑部 | 安全审计 | 漏洞扫描、权限审计、合规检查、日志审查 |
| `libu_hr` | 吏部 | 项目管理 | 里程碑规划、任务拆解、进度跟踪 |
| `hubu_data` | 户部（数据）| 数据专项处理 | 大规模数据处理、数仓、报表生成 |

---

## OpenClaw 配置片段格式

生成文件：`$CHAOTING_DIR/openclaw-agents-fragment.json`

```json
{
  "_comment": "将 agents 数组合并到你的 openclaw.json 中的 agents.list 下",
  "_generated_at": "2026-03-08T16:31:00",
  "_chaoting_dir": "/home/user/.themachine/chaoting",
  "agents": [
    {
      "id": "silijian",
      "workspace": "/home/user/.openclaw/workspace-silijian",
      "model": "anthropic/claude-sonnet-4-6",
      "identity": {
        "name": "司礼监",
        "emoji": "🎭"
      }
    },
    {
      "id": "zhongshu",
      "workspace": "/home/user/.openclaw/workspace-zhongshu",
      "model": "anthropic/claude-sonnet-4-6",
      "identity": {
        "name": "中书省",
        "emoji": "📜"
      }
    },
    // ... 其余 11 个 agent
  ]
}
```

### 手动合并说明

```bash
# 查看生成的配置片段
cat $CHAOTING_DIR/openclaw-agents-fragment.json

# 手动将 agents 数组合并到 openclaw.json
# 找到 agents.list 字段，追加上述条目
# 然后重启 OpenClaw 服务
```

---

## --auto-config 自动合并设计

### 检测流程

```bash
if command -v jq >/dev/null 2>&1; then
    # jq 可用，执行自动合并
    auto_merge_config
else
    echo "⚠️  jq 未安装，跳过自动合并。"
    echo "   配置片段已生成：$CHAOTING_DIR/openclaw-agents-fragment.json"
    echo "   安装 jq 后可重新运行：./install.sh --auto-config"
fi
```

### 自动合并步骤

```
1. 检测 openclaw.json 路径
   - 优先：$OPENCLAW_STATE_DIR/openclaw.json
   - 备选：$HOME/.openclaw/openclaw.json
   - 找不到 → 报错退出，提示手动合并

2. 备份
   cp openclaw.json openclaw.json.bak.$(date +%Y%m%d-%H%M%S)

3. jq 合并
   jq --argjson new_agents "$(cat fragment.json | jq .agents)" \
     '.agents.list += $new_agents | .agents.list |= unique_by(.id)' \
     openclaw.json > openclaw.json.tmp

4. 验证
   python3 -c "import json; json.load(open('openclaw.json.tmp'))"
   （验证通过后替换原文件）

5. 完成
   mv openclaw.json.tmp openclaw.json
   echo "✅ 已合并 13 个 agent 配置到 openclaw.json"
```

**关键设计：** `unique_by(.id)` 保证幂等性——已存在的 agent ID 不会重复添加。

---

## 幂等性设计

所有创建操作遵循"已存在则跳过"原则，确保重复执行 install.sh 不会破坏用户自定义配置。

| 操作 | 幂等策略 |
|------|---------|
| 创建 workspace 目录 | `mkdir -p`（目录已存在无副作用） |
| 生成 SOUL.md | 检查文件是否存在，存在则跳过并打印 `[skip]` |
| 生成配置片段 | 每次覆盖生成（片段文件，非用户直接编辑） |
| --auto-config 合并 | `jq unique_by(.id)` 去重，已有 agent 不重复添加 |

```bash
# 伪代码示例
for agent_id in "${AGENTS[@]}"; do
    soul_path="$OPENCLAW_STATE_DIR/workspace-${agent_id}/SOUL.md"
    if [ -f "$soul_path" ]; then
        echo "  [skip] $agent_id — SOUL.md 已存在"
    else
        mkdir -p "$(dirname "$soul_path")"
        generate_soul "$agent_id" > "$soul_path"
        echo "  [create] $agent_id"
    fi
done
```

---

## 边界情况处理

| 情况 | 处理方式 |
|------|---------|
| `OPENCLAW_STATE_DIR` 未设置 | 默认使用 `$HOME/.openclaw`；若 `$HOME` 也未设置则报错退出 |
| workspace 目录权限不足 | 捕获 `mkdir` 错误，报错打印路径，跳过该 agent，继续其余创建 |
| `jq` 未安装（--auto-config）| 仅生成配置片段，跳过自动合并，打印安装提示 |
| `openclaw.json` 不存在 | --auto-config 模式下跳过合并，提示用户先初始化 OpenClaw；非 auto-config 模式正常生成片段 |
| `openclaw.json` 格式损坏 | 合并前 python3 验证，损坏则中止合并，保留备份，提示用户修复 |
| SOUL.md 已存在 | 跳过，不覆盖，打印 `[skip]` 日志（保护用户自定义内容） |
| 部分 agent 已存在 | 仅创建缺失的部分，已存在的跳过，最终打印创建/跳过各多少个 |
| 磁盘空间不足 | 依赖 shell `set -e`，写文件失败时自动退出并报错 |
| 非 systemd 环境 | 本步骤不依赖 systemd，即使无 systemd 也可单独执行 agent 配置 |

---

## 执行完成输出示例

```
=== [4/4] Agent 配置 ===

创建 workspace 目录和 SOUL.md：
  [create] silijian        → ~/.openclaw/workspace-silijian/SOUL.md
  [create] zhongshu      → ~/.openclaw/workspace-zhongshu/SOUL.md
  [create] jishi_tech    → ~/.openclaw/workspace-jishi_tech/SOUL.md
  [create] jishi_risk    → ~/.openclaw/workspace-jishi_risk/SOUL.md
  [create] jishi_resource→ ~/.openclaw/workspace-jishi_resource/SOUL.md
  [create] jishi_compliance→ ~/.openclaw/workspace-jishi_compliance/SOUL.md
  [create] bingbu        → ~/.openclaw/workspace-bingbu/SOUL.md
  [create] gongbu        → ~/.openclaw/workspace-gongbu/SOUL.md
  [create] hubu          → ~/.openclaw/workspace-hubu/SOUL.md
  [create] libu          → ~/.openclaw/workspace-libu/SOUL.md
  [create] xingbu        → ~/.openclaw/workspace-xingbu/SOUL.md
  [create] libu_hr       → ~/.openclaw/workspace-libu_hr/SOUL.md
  [create] hubu_data     → ~/.openclaw/workspace-hubu_data/SOUL.md

已创建 13 个 workspace（0 个跳过）

OpenClaw 配置片段已生成：
  ~/.themachine/chaoting/openclaw-agents-fragment.json

下一步：将片段内容合并到 openclaw.json
  自动合并（需要 jq）：./install.sh --auto-config
  手动合并：查看 openclaw-agents-fragment.json，添加到 openclaw.json 的 agents.list

完成！运行 'openclaw reload' 使配置生效。
```

---

## 不在本次范围

| 功能 | 原因 |
|------|------|
| 自动生成各 agent 的 `AGENTS.md`、`USER.md` 等文件 | 这些是运行时文件，由 agent 自己在首次启动时创建 |
| 自动配置 agent 使用的 model | 用户可能有不同 API Key 和偏好，应由用户手动指定 |
| 从 UI 选择部分 agent 安装 | 过度设计，全量安装更简单且幂等 |
| Windows/macOS 支持 | 当前系统已限定 Linux/systemd 环境 |

---

*本文件由礼部（libu）撰写，依据 `install.sh`、`examples/agent-souls.md` 及 `examples/openclaw-agents.yaml` 整理。*
