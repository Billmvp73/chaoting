# AGENT-SKILL-MAPPING.md — 朝廷各部门 Agent Skill 配置规范

> 版本：v1.0  
> 制定日期：2026-03-11  
> 适用范围：朝廷系统所有 Agent 部门  
> 依据奏折：ZZ-20260311-007

---

## 一、设计原则

### 1.1 最小权限原则（Principle of Least Privilege）

每个 Agent 只应配置完成其职责所必需的 tools 和 skills，不多不少。

| 规则 | 说明 |
|------|------|
| ✅ **按角色分级** | leader > planner > reviewer > executor，权限依次收窄 |
| ✅ **按职责裁剪** | 不需要写文件的 Agent 不配 `write_file` / `edit_file` |
| ✅ **空列表 = 继承全量** | `tools: []` 和 `skills: []` 表示继承 defaults，即拥有所有工具 |
| ❌ **禁止过度授权** | reviewer 类 Agent 不应有 `write_file` / `edit_file` / `exec` 写操作 |
| ✅ **message 工具专属司礼监** | 只有 leader 角色需要向 Discord 发送通知 |

### 1.2 角色匹配原则（Role-Aligned Tooling）

朝廷系统有四类角色，每类角色的 tool 需求不同：

| 角色 | 核心职责 | 典型 Tool 需求 |
|------|---------|--------------|
| `leader`（司礼监） | 监察、裁决、通知、Merge PR | 全量 tools + Discord 通知 |
| `planner`（中书省） | 调研、规划、提交方案 | 读取 + 搜索，无需写文件 |
| `reviewer`（给事中） | 审核方案、投票 | 只读 + 搜索，最小权限 |
| `executor`（六部） | 编码实现、提交 PR | 读写 + exec + gh CLI |

### 1.3 Workspace Skills 使用原则

Workspace skills 是业务领域专用工具，应按「谁用谁配」原则：

- **Tetration 相关 skills**（`access-tetration-cluster`、`tetration-cluster-ui`、`federation-rca`、`forensic-ticket-rca`、`pr-failure-rca`）：仅需要访问 Tetration 集群的执行部门配置
- **通用流程 skills**（`cherry-pick-workflow`、`skill-sync`）：所有执行部门可配置
- **给事中（reviewer）**：不配置 workspace skills（审核不需要执行业务操作）
- **中书省（planner）**：不配置 workspace skills（规划不需要执行业务操作）

---

## 二、可用 Tool 清单（共 13 个）

| Tool 名称 | 类型 | 说明 |
|-----------|------|------|
| `read_file` | 只读 | 读取文件内容 |
| `write_file` | 写入 | 创建或覆盖文件 |
| `edit_file` | 写入 | 精确替换文件片段 |
| `list_dir` | 只读 | 列出目录内容 |
| `exec` | 执行 | 运行 shell 命令（含 git、gh CLI、chaoting CLI） |
| `web_search` | 网络 | 搜索互联网 |
| `web_fetch` | 网络 | 抓取网页内容 |
| `message` | 通知 | 向 Discord / Telegram 等发送消息 |
| `spawn` | 委托 | 生成子 Agent 处理复杂任务 |
| `memory_search` | 记忆 | 搜索长期记忆 |
| `jira` | 集成 | Jira 工单操作 |
| `jenkins` | 集成 | Jenkins CI/CD 操作 |
| `github` | 集成 | GitHub API 操作（非 gh CLI） |

---

## 三、可用 Workspace Skill 清单（共 7 个）

| Skill 名称 | 用途 | 适用部门 |
|-----------|------|---------|
| `access-tetration-cluster` | 访问 Tetration 集群 | 兵部、工部、户部 |
| `cherry-pick-workflow` | Cherry-pick 工作流 | 所有执行部门 |
| `federation-rca` | Federation 故障根因分析 | 兵部、工部 |
| `forensic-ticket-rca` | Forensic 工单根因分析 | 兵部、工部 |
| `pr-failure-rca` | PR 失败根因分析 | 兵部、工部、刑部 |
| `skill-sync` | Skill 同步工具 | 吏部（HR）、司礼监 |
| `tetration-cluster-ui` | Tetration 集群 UI 操作 | 兵部、工部、户部 |

---

## 四、各部门 Tool 配置清单

### 4.1 司礼监（Silijian）— `leader`

**职责**：监察总管，创建奏折，裁决，Merge PR，发送 Discord 通知

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 审阅代码、文档 |
| `write_file` | ✅ | 紧急修复、配置更新 |
| `edit_file` | ✅ | 紧急修复 |
| `list_dir` | ✅ | 查看目录结构 |
| `exec` | ✅ | 运行 chaoting CLI、gh CLI（merge PR）、诊断命令 |
| `web_search` | ✅ | 调研背景信息 |
| `web_fetch` | ✅ | 获取网页内容 |
| `message` | ✅ **专属** | 向 Discord 发送分派通知、催办、裁决结果 |
| `spawn` | ✅ | 委托子 Agent 处理复杂任务 |
| `memory_search` | ✅ | 查阅历史记忆 |
| `jira` | ✅ | 关联 Jira 工单 |
| `jenkins` | ✅ | 查看 CI/CD 状态 |
| `github` | ✅ | GitHub API 操作 |

**推荐配置**：`tools: []`（空列表 = 全量，leader 无需限制）

---

### 4.2 中书省（Zhongshu）— `planner`

**职责**：分析需求，制定执行方案，选择执行部门，被封驳后修改重提

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读代码和文档，理解上下文 |
| `write_file` | ❌ | 规划者不直接修改代码 |
| `edit_file` | ❌ | 规划者不直接修改代码 |
| `list_dir` | ✅ | 了解仓库结构 |
| `exec` | ✅ | 运行 chaoting CLI（pull/plan）、查看仓库状态 |
| `web_search` | ✅ | 调研技术方案、查阅文档 |
| `web_fetch` | ✅ | 获取详细技术文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ❌ | 规划者不委托子 Agent |
| `memory_search` | ✅ | 查阅历史规划经验 |
| `jira` | ✅ | 查阅 Jira 工单背景 |
| `jenkins` | ❌ | 规划阶段不需要 CI/CD |
| `github` | ✅ | 查阅 PR/Issue 历史 |

**推荐配置**：
```json
"tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search", "jira", "github"]
```

---

### 4.3 技术给事中（Jishi Tech）— `reviewer`

**职责**：审核中书省方案的技术可行性，投票 go/nogo

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读目标文件，评估实现路径 |
| `write_file` | ❌ | 审核者不修改文件 |
| `edit_file` | ❌ | 审核者不修改文件 |
| `list_dir` | ✅ | 查看目录结构辅助评估 |
| `exec` | ✅ | 运行 chaoting CLI（pull/vote）、查阅代码验证可行性 |
| `web_search` | ✅ | 核实技术细节、验证依赖版本兼容性 |
| `web_fetch` | ✅ | 获取技术文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ❌ | 审核者不委托子 Agent |
| `memory_search` | ✅ | 查阅历史审核记录 |
| `jira` | ❌ | 审核阶段不需要 |
| `jenkins` | ❌ | 审核阶段不需要 |
| `github` | ❌ | 审核阶段不需要 |

**推荐配置**：
```json
"tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"]
```

---

### 4.4 风险给事中（Jishi Risk）— `reviewer`

**职责**：审核方案的风险边界、回滚方案、影响范围

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读方案文档和相关代码 |
| `write_file` | ❌ | 审核者不修改文件 |
| `edit_file` | ❌ | 审核者不修改文件 |
| `list_dir` | ✅ | 了解影响范围 |
| `exec` | ✅ | 运行 chaoting CLI（pull/vote） |
| `web_search` | ✅ | 查阅风险案例、CVE 数据库 |
| `web_fetch` | ✅ | 获取风险评估文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ❌ | 审核者不委托子 Agent |
| `memory_search` | ✅ | 查阅历史风险记录（qianche） |
| `jira` | ❌ | 审核阶段不需要 |
| `jenkins` | ❌ | 审核阶段不需要 |
| `github` | ❌ | 审核阶段不需要 |

**推荐配置**：
```json
"tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"]
```

---

### 4.5 资源给事中（Jishi Resource）— `reviewer`

**职责**：审核方案的资源消耗（计算、存储、网络、人力）

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读方案文档 |
| `write_file` | ❌ | 审核者不修改文件 |
| `edit_file` | ❌ | 审核者不修改文件 |
| `list_dir` | ✅ | 了解项目规模 |
| `exec` | ✅ | 运行 chaoting CLI（pull/vote） |
| `web_search` | ✅ | 查阅资源定价、容量规划参考 |
| `web_fetch` | ✅ | 获取资源相关文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ❌ | 审核者不委托子 Agent |
| `memory_search` | ✅ | 查阅历史资源使用记录 |
| `jira` | ❌ | 审核阶段不需要 |
| `jenkins` | ❌ | 审核阶段不需要 |
| `github` | ❌ | 审核阶段不需要 |

**推荐配置**：
```json
"tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"]
```

---

### 4.6 合规给事中（Jishi Compliance）— `reviewer`

**职责**：审核方案的合规性（安全规范、数据隐私、流程合规）

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读方案文档和规范文件 |
| `write_file` | ❌ | 审核者不修改文件 |
| `edit_file` | ❌ | 审核者不修改文件 |
| `list_dir` | ✅ | 了解文档结构 |
| `exec` | ✅ | 运行 chaoting CLI（pull/vote） |
| `web_search` | ✅ | 查阅合规标准（SOC2、GDPR 等） |
| `web_fetch` | ✅ | 获取合规文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ❌ | 审核者不委托子 Agent |
| `memory_search` | ✅ | 查阅历史合规记录 |
| `jira` | ❌ | 审核阶段不需要 |
| `jenkins` | ❌ | 审核阶段不需要 |
| `github` | ❌ | 审核阶段不需要 |

**推荐配置**：
```json
"tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"]
```

---

### 4.7 兵部（Bingbu）— `executor`（后端/系统编码）

**职责**：后端代码开发、系统功能实现、API 开发

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读代码文件 |
| `write_file` | ✅ | 创建新代码文件 |
| `edit_file` | ✅ | 修改现有代码 |
| `list_dir` | ✅ | 查看目录结构 |
| `exec` | ✅ | 运行 chaoting CLI、git、gh CLI、测试命令 |
| `web_search` | ✅ | 查阅 API 文档、解决方案 |
| `web_fetch` | ✅ | 获取详细技术文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ✅ | 委托 Claude Code 处理 M/L 复杂度任务 |
| `memory_search` | ✅ | 查阅历史实现经验 |
| `jira` | ✅ | 关联 Jira 工单（CRF/CSW） |
| `jenkins` | ✅ | 查看 CI/CD 构建状态 |
| `github` | ✅ | GitHub API 操作 |

**推荐配置**：`tools: []`（全量，executor 需要完整工具链）

---

### 4.8 工部（Gongbu）— `executor`（基础设施/部署）

**职责**：基础设施管理、服务部署、容器运维、系统配置

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读配置文件 |
| `write_file` | ✅ | 创建配置文件 |
| `edit_file` | ✅ | 修改配置文件 |
| `list_dir` | ✅ | 查看目录结构 |
| `exec` | ✅ | 运行 chaoting CLI、git、gh CLI、systemctl、docker、ssh |
| `web_search` | ✅ | 查阅运维文档 |
| `web_fetch` | ✅ | 获取详细运维文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ✅ | 委托子 Agent 处理复杂部署任务 |
| `memory_search` | ✅ | 查阅历史运维经验 |
| `jira` | ✅ | 关联 Jira 工单 |
| `jenkins` | ✅ | 触发和查看 CI/CD 流水线 |
| `github` | ✅ | GitHub API 操作 |

**推荐配置**：`tools: []`（全量，工部需要完整工具链含 exec 远程操作）

---

### 4.9 户部（Hubu）— `executor`（数据/财务/报表）

**职责**：数据处理、报表生成、数据库操作、数据分析

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读数据文件和脚本 |
| `write_file` | ✅ | 创建数据处理脚本和报表 |
| `edit_file` | ✅ | 修改数据处理脚本 |
| `list_dir` | ✅ | 查看数据目录 |
| `exec` | ✅ | 运行 chaoting CLI、git、gh CLI、sqlite3、python3 |
| `web_search` | ✅ | 查阅数据处理方案 |
| `web_fetch` | ✅ | 获取数据源文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ✅ | 委托子 Agent 处理大规模数据任务 |
| `memory_search` | ✅ | 查阅历史数据处理经验 |
| `jira` | ✅ | 关联 Jira 工单 |
| `jenkins` | ✅ | 查看数据流水线状态 |
| `github` | ✅ | GitHub API 操作 |

**推荐配置**：`tools: []`（全量）

---

### 4.10 礼部（Libu）— `executor`（文档撰写）

**职责**：README、API 文档、架构设计文档、CHANGELOG、用户指南

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读代码和现有文档 |
| `write_file` | ✅ | 创建新文档 |
| `edit_file` | ✅ | 修改现有文档 |
| `list_dir` | ✅ | 查看目录结构 |
| `exec` | ✅ | 运行 chaoting CLI、git、gh CLI |
| `web_search` | ✅ | 查阅技术文档和规范 |
| `web_fetch` | ✅ | 获取参考文档内容 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ✅ | 委托子 Agent 处理复杂文档任务 |
| `memory_search` | ✅ | 查阅历史文档经验 |
| `jira` | ❌ | 文档任务通常不需要 Jira 集成 |
| `jenkins` | ❌ | 文档任务不需要 CI/CD |
| `github` | ✅ | GitHub API 操作（PR/Issue） |

**推荐配置**：
```json
"tools": ["read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch", "spawn", "memory_search", "github"]
```

---

### 4.11 吏部（Libu HR）— `executor`（人员/规范管理）

**职责**：AGENT.md 维护、规范文档、人员配置、工作负载分析

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读 AGENT.md 和规范文档 |
| `write_file` | ✅ | 创建/更新 AGENT.md |
| `edit_file` | ✅ | 修改规范文档 |
| `list_dir` | ✅ | 查看 agents 目录 |
| `exec` | ✅ | 运行 chaoting CLI（含 list/status 查看全局负载）、git、gh CLI |
| `web_search` | ✅ | 查阅管理规范 |
| `web_fetch` | ✅ | 获取参考文档 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ✅ | 委托子 Agent 处理复杂管理任务 |
| `memory_search` | ✅ | 查阅历史管理经验 |
| `jira` | ❌ | 人员管理通常不需要 Jira |
| `jenkins` | ❌ | 人员管理不需要 CI/CD |
| `github` | ✅ | GitHub API 操作（PR/Issue） |

**推荐配置**：
```json
"tools": ["read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch", "spawn", "memory_search", "github"]
```

---

### 4.12 刑部（Xingbu）— `executor`（安全/审计）

**职责**：安全审计、漏洞检测、权限审查、合规执行

| Tool | 配置 | 理由 |
|------|------|------|
| `read_file` | ✅ | 阅读代码进行安全审计 |
| `write_file` | ✅ | 创建安全报告 |
| `edit_file` | ✅ | 修复安全漏洞 |
| `list_dir` | ✅ | 扫描目录结构 |
| `exec` | ✅ | 运行 chaoting CLI、git、gh CLI、安全扫描工具 |
| `web_search` | ✅ | 查阅 CVE 数据库、安全最佳实践 |
| `web_fetch` | ✅ | 获取安全公告和漏洞详情 |
| `message` | ❌ | 通知由司礼监负责 |
| `spawn` | ✅ | 委托子 Agent 处理大规模安全扫描 |
| `memory_search` | ✅ | 查阅历史安全记录 |
| `jira` | ✅ | 关联安全工单 |
| `jenkins` | ✅ | 查看 CI/CD 安全扫描结果 |
| `github` | ✅ | GitHub API 操作（安全 PR） |

**推荐配置**：`tools: []`（全量，安全审计需要完整工具链）

---

## 五、各部门 Skill 配置清单

### 5.1 Skill 配置汇总表

| 部门 | 角色 | `access-tetration-cluster` | `cherry-pick-workflow` | `federation-rca` | `forensic-ticket-rca` | `pr-failure-rca` | `skill-sync` | `tetration-cluster-ui` |
|------|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 司礼监 | leader | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| 中书省 | planner | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 技术给事中 | reviewer | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 风险给事中 | reviewer | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 资源给事中 | reviewer | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 合规给事中 | reviewer | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 兵部 | executor | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| 工部 | executor | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| 户部 | executor | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 礼部 | executor | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| 吏部 | executor | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| 刑部 | executor | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |

### 5.2 各部门 Skill 配置说明

**司礼监**：配置 `skill-sync` 用于同步和管理各部门 skill 配置。不需要业务执行类 skills。

**中书省**：规划阶段不执行业务操作，不配置任何 workspace skills。

**给事中（4个）**：审核阶段不执行业务操作，不配置任何 workspace skills。

**兵部**：作为核心后端执行部门，需要访问 Tetration 集群（`access-tetration-cluster`、`tetration-cluster-ui`）、故障分析（`federation-rca`、`forensic-ticket-rca`、`pr-failure-rca`）和 cherry-pick 工作流。

**工部**：基础设施部门，与兵部类似，需要集群访问和故障分析能力。

**户部**：数据部门，需要集群访问（数据采集）和 UI 操作，但不需要故障分析 skills。

**礼部**：文档部门，只需要 `cherry-pick-workflow`（文档 cherry-pick）和 `pr-failure-rca`（分析 PR 失败原因以改进文档流程）。

**吏部**：人员管理部门，需要 `cherry-pick-workflow` 和 `skill-sync`（管理各部门 skill 配置）。

**刑部**：安全部门，需要 `cherry-pick-workflow` 和 `pr-failure-rca`（安全 PR 失败分析）。

---

## 六、config.json 配置示例片段

> ⚠️ **安全说明**：以下示例不含任何 secrets（API Key、Token、密码等）。实际 config.json 中的 secrets 字段应通过 secret store 管理，不得明文存储。

```json
{
  "agents": {
    "defaults": {
      "model": "claude-sonnet-4-5",
      "workspace": "~/.beebot",
      "maxTokens": 8192,
      "maxToolIterations": 50
    },
    "named": {
      "silijian": {
        "tools": [],
        "skills": ["skill-sync"]
      },
      "zhongshu": {
        "tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search", "jira", "github"],
        "skills": []
      },
      "jishi_tech": {
        "tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"],
        "skills": []
      },
      "jishi_risk": {
        "tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"],
        "skills": []
      },
      "jishi_resource": {
        "tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"],
        "skills": []
      },
      "jishi_compliance": {
        "tools": ["read_file", "list_dir", "exec", "web_search", "web_fetch", "memory_search"],
        "skills": []
      },
      "bingbu": {
        "tools": [],
        "skills": ["access-tetration-cluster", "cherry-pick-workflow", "federation-rca", "forensic-ticket-rca", "pr-failure-rca", "tetration-cluster-ui"]
      },
      "gongbu": {
        "tools": [],
        "skills": ["access-tetration-cluster", "cherry-pick-workflow", "federation-rca", "forensic-ticket-rca", "pr-failure-rca", "tetration-cluster-ui"]
      },
      "hubu": {
        "tools": [],
        "skills": ["access-tetration-cluster", "cherry-pick-workflow", "tetration-cluster-ui"]
      },
      "libu": {
        "tools": ["read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch", "spawn", "memory_search", "github"],
        "skills": ["cherry-pick-workflow", "pr-failure-rca"]
      },
      "libu_hr": {
        "tools": ["read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch", "spawn", "memory_search", "github"],
        "skills": ["cherry-pick-workflow", "skill-sync"]
      },
      "xingbu": {
        "tools": [],
        "skills": ["cherry-pick-workflow", "pr-failure-rca"]
      }
    }
  }
}
```

---

## 七、安全边界说明

### 7.1 `message` 工具的安全边界

`message` 工具允许向外部渠道（Discord、Telegram 等）发送消息。**仅司礼监**应配置此工具，原因：
- 防止执行部门绕过司礼监直接对外通知，造成信息混乱
- 确保所有对外通知经过最高权限审核
- 避免敏感信息（如代码内容、配置细节）被意外发送到公开渠道

### 7.2 `exec` 工具的安全边界

`exec` 工具可执行任意 shell 命令，具有较高风险：
- **reviewer 类 Agent**：仅允许运行 chaoting CLI 命令（pull/vote），不应执行写操作
- **planner 类 Agent**：仅允许运行 chaoting CLI 和只读命令（cat/ls/git log）
- **executor 类 Agent**：允许完整 exec，但必须遵守「禁止直接 commit 到 master」规则

### 7.3 `write_file` / `edit_file` 的安全边界

- **reviewer 和 planner**：不应配置写文件工具，防止直接修改代码绕过 PR 流程
- **executor**：允许写文件，但所有变更必须通过 feature branch + PR 提交

### 7.4 空列表 vs 显式列表的语义

根据 beebot `AgentConfig` 结构体定义：
```go
Tools  []string `json:"tools,omitempty"`  // subset of available tools; empty = all
Skills []string `json:"skills,omitempty"` // subset of available skills; empty = all
```

- `tools: []`（空列表）= 继承 defaults = **拥有所有工具**
- `tools: ["read_file", "exec"]`（显式列表）= **仅拥有列出的工具**
- 因此，对于需要限制权限的 Agent（planner、reviewer），**必须使用显式列表**

### 7.5 Secrets 管理边界

- config.json 中的 `secrets` 字段内容**绝不能写入任何文档**
- API Key、Token、密码等敏感信息通过 secret store 管理
- 本文档中的配置示例均不含 secrets 字段

---

## 八、快速参考卡

```
角色权限层级：
  leader（司礼监）    → tools: []（全量）+ message 专属
  planner（中书省）   → 只读 + exec + 搜索，无写文件，无 message
  reviewer（给事中）  → 只读 + exec（仅 chaoting CLI）+ 搜索，最小权限
  executor（六部）    → 全量 tools（或按职责裁剪）+ 对应 workspace skills

Skill 分配原则：
  Tetration 相关    → 兵部、工部、户部
  故障分析 RCA      → 兵部、工部（核心执行部门）
  cherry-pick       → 所有执行部门
  skill-sync        → 司礼监、吏部
  pr-failure-rca    → 兵部、工部、礼部、刑部

安全红线：
  ❌ reviewer/planner 不得有 write_file / edit_file
  ❌ 非司礼监不得有 message 工具
  ❌ secrets 不得写入文档
  ✅ 显式列表 = 限制权限；空列表 = 全量权限
```

---

*本文档由礼部（libu）依据奏折 ZZ-20260311-007 撰写，2026-03-11*
