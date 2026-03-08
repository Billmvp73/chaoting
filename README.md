# 朝廷 (Chaoting) — 多智能体任务协调系统

> 以古代中国朝廷官制为原型的 OpenClaw 多智能体任务编排框架。

---

## 项目简介

**朝廷**是一套运行于 OpenClaw 环境的多智能体任务协调系统。它借鉴古代朝廷的官僚架构，将复杂任务拆解后分派给不同职能的 AI 智能体（"部门"）协作完成。

各智能体通过共享 SQLite 数据库进行协调（Stigmergy 模式），**无需直接通信**，任务流转全部通过数据库状态机驱动。

### 核心特性

- 📜 **奏折驱动** — 每个任务以"奏折（ZZ）"为单位流转
- 🏛️ **职能分离** — 规划、审核、编码、运维、数据、文档各司其职
- 🗳️ **门下省审核** — Go/No-Go 投票机制，多给事中并行审核方案
- ⚙️ **状态机保护** — CAS（Compare-And-Swap）防止并发冲突
- 🔄 **封驳重提** — 方案被否决后自动退回修改，最多三轮
- 🗃️ **上下文积累** — 智能体间共享领域知识（典籍/dianji）

---

## 架构说明

### 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                         朝廷系统                               │
│                                                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────────┐ │
│  │ 司礼监    │───▶│ 调度器    │───▶│  中书省 (zhongshu)       │ │
│  │ (用户入口) │    │(dispatcher│    │  规划·拆解任务            │ │
│  └──────────┘    │  .py)    │    └───────────┬──────────────┘ │
│                  └──────────┘                │ plan            │
│                       ▲                      ▼                │
│                       │            ┌──────────────────────┐   │
│                       │            │  门下省 (给事中)       │   │
│                       │            │  🔬 技术 ⚠️ 风险       │   │
│                       │            │  📦 资源 🛡️ 合规       │   │
│                       │            └───────────┬──────────┘   │
│                       │               go/nogo  │              │
│                       │                        ▼              │
│                       │            ┌──────────────────────┐   │
│                       │            │  六部 (执行)          │   │
│                       │            │  ⚔️兵 🔨工 📊户       │   │
│                       └────────────│  📚礼 ⚖️刑 👔吏       │   │
│                      状态轮询       └──────────────────────┘   │
│                                                                │
│                共享: chaoting.db (SQLite WAL)                  │
└──────────────────────────────────────────────────────────────┘
```

### 任务状态机

```
                    ┌─────────────────────────────┐
                    │          封驳退回             │
                    ▼                              │
created → planning → reviewing → executing → done │
              ▲         │                    ↘     │
              │         ▼                  failed  │
              │      revising ─────────────────────┘
              │         │
              └─────────┘  (三驳 → failed)
```

| 状态 | 说明 | 负责方 |
|------|------|--------|
| `created` | 任务已创建，等待调度 | 司礼监 |
| `planning` | 已派发给中书省，规划中 | 中书省 |
| `reviewing` | 门下省审议中，等待给事中投票 | 给事中 |
| `revising` | 被封驳，退回中书省修改 | 系统 → 中书省 |
| `executing` | 审核通过，执行中 | 六部 |
| `done` | 任务完成 | 六部 |
| `failed` | 任务失败（含三驳失败） | 各方 |
| `timeout` | 超时后重试耗尽 | 调度器 |

---

## 门下省 — Go/No-Go 审核机制

中书省规划完成后，奏折不直接执行，而是先经门下省审议。

### 给事中角色

| ID | 角色 | Emoji | 审核视角 |
|----|------|-------|---------|
| `jishi_tech` | 技术给事中 | 🔬 | 技术可行性、架构合理性、依赖风险 |
| `jishi_risk` | 风险给事中 | ⚠️ | 回滚方案、数据安全、破坏性操作 |
| `jishi_resource` | 资源给事中 | 📦 | 工时合理性、token 预算 |
| `jishi_compliance` | 合规给事中 | 🛡️ | 安全合规、权限边界 |

### 审核级别

创建奏折时通过 `review_required` 设定审核级别：

| review_required | 级别 | 给事中 |
|----------------|------|--------|
| 0 | 免审（小事） | 跳过门下省，直接执行 |
| 1 | 普通 | jishi_tech |
| 2 | 重要 | jishi_tech + jishi_risk |
| 3 | 军国大事 | 全部四位给事中 |

> 也可通过 `review_agents` JSON 数组自定义审核人，覆盖默认映射。

### 投票流程

```bash
# 准奏
chaoting vote ZZ-20260308-001 go "方案可行，风险可控" --as jishi_tech

# 封驳
chaoting vote ZZ-20260308-001 nogo "缺少回滚方案" --as jishi_risk
```

### 封驳与重提

- 有任何 nogo → 进入 `revising`，旧方案存入 `plan_history`，`plan` 清空
- 调度器自动退回中书省，附带封驳意见
- 中书省修改方案后重新提交，进入第二轮投票
- **朝规五：三驳呈御前** — 连续封驳 3 次后标记 `failed`，通知司礼监人工决断

### 超时处理

- 普通任务：给事中超时未投 → 默认准奏（go），但通知司礼监
- 军国大事（priority=critical）：超时 → 直接 failed，需人工介入

### 安全机制

- **CAS 保护**：所有状态转换用 `UPDATE WHERE state=expected`，检查 rowcount
- **UNIQUE 约束**：`toupiao(zouzhe_id, round, jishi_id)` 防止重复投票
- **BEGIN IMMEDIATE**：投票操作在事务内完成
- **plan=NULL**：进入 revising 时清空旧方案，防幽灵执行

---

## 组织编制

### 三省

| 机构 | Agent ID | 角色 |
|------|----------|------|
| 司礼监 | `main` | 用户入口（Mr. Reese） |
| 中书省 | `zhongshu` 📜 | 规划 |
| 门下省 | `jishi_*` | 审核（见上表） |

### 六部

| 部门 | Agent ID | Emoji | 职责 |
|------|----------|-------|------|
| 兵部 | `bingbu` | ⚔️ | 编码开发 |
| 工部 | `gongbu` | 🔨 | 运维部署 |
| 户部 | `hubu` | 📊 | 数据处理 |
| 礼部 | `libu` | 📚 | 文档撰写 |
| 刑部 | `xingbu` | ⚖️ | 安全审计 |
| 吏部 | `libu_hr` | 👔 | 项目管理 |

### 基础设施

| 组件 | 文件 | 说明 |
|------|------|------|
| 调度器 | `src/dispatcher.py` | systemd 常驻守护进程，5s 轮询 |
| CLI | `src/chaoting` | 智能体命令行工具 |
| 数据库 | `chaoting.db` | SQLite WAL 模式（运行时生成） |
| Schema | `src/init_db.py` | 数据库初始化/迁移 |

---

## 数据库表

| 表名 | 含义 | 用途 |
|------|------|------|
| `zouzhe` | 奏折 | 任务主表（含 review 字段） |
| `toupiao` | 投票 | 给事中投票记录 |
| `liuzhuan` | 流转 | 状态变更日志 |
| `zoubao` | 奏报 | 进度上报记录 |
| `dianji` | 典籍 | 跨任务领域知识 |
| `qianche` | 前车 | 智能体经验教训 |

---

## 使用方法

### 安装

```bash
# Clone
git clone https://github.com/Billmvp73/chaoting.git
cd chaoting

# Install (initializes DB + installs systemd service)
./install.sh

# Or specify OpenClaw CLI path explicitly
OPENCLAW_CLI=/path/to/openclaw ./install.sh

# Verify
systemctl --user status chaoting-dispatcher
```

### CLI 命令速查

```bash
# 接旨
chaoting pull ZZ-20260308-001

# 提交规划（中书省）
chaoting plan ZZ-20260308-001 '{"steps":[...],"target_agent":"bingbu",...}'

# 投票（给事中）
chaoting vote ZZ-20260308-001 go "理由" --as jishi_tech
chaoting vote ZZ-20260308-001 nogo "理由" --as jishi_risk

# 上报进度
chaoting progress ZZ-20260308-001 "进展描述"

# 标记完成
chaoting done ZZ-20260308-001 "产出" "摘要"

# 上报失败
chaoting fail ZZ-20260308-001 "失败原因"

# 更新领域知识
chaoting context bingbu "key" "value" --source ZZ-20260308-001
```

### 典型流程

```
1. 司礼监创建奏折 (created)
2. 调度器 → 中书省 (planning)
3. 中书省 pull → 分析 → plan (reviewing)
4. 门下省给事中投票 (go/nogo)
   ├─ 全票通过 → executing → 六部执行 → done
   └─ 有封驳 → revising → 退回中书省修改 → 重新 reviewing
      └─ 三驳 → failed（呈御前裁决）
```

---

## 命名约定

- **状态、CLI 命令** → 英文（created, planning, reviewing, executing）
- **表名、部门名** → 拼音（zouzhe, toupiao, zhongshu, bingbu）
- **任务 ID** → `ZZ-YYYYMMDD-NNN`

## 详细规范

- MVP 规范：[`docs/SPEC.md`](./docs/SPEC.md)
- 门下省规范：[`docs/SPEC-menxia.md`](./docs/SPEC-menxia.md)
- Roadmap：[`docs/ROADMAP.md`](./docs/ROADMAP.md)

## 项目结构

```
chaoting/
├── src/
│   ├── dispatcher.py      # 调度守护进程
│   ├── chaoting           # 智能体 CLI 工具
│   └── init_db.py         # 数据库初始化
├── docs/
│   ├── SPEC.md            # MVP 技术规范
│   ├── SPEC-menxia.md     # 门下省审核机制规范
│   ├── ROADMAP.md         # 版本规划
│   └── CHANGELOG.md       # 变更日志
├── examples/
│   ├── agent-souls.md     # Agent SOUL.md 模板
│   └── openclaw-agents.yaml  # OpenClaw agent 配置示例
├── install.sh             # 一键安装脚本
├── ACKNOWLEDGEMENTS.md    # 致谢与灵感来源
├── LICENSE                # MIT License
└── README.md
```

## 致谢

本项目的设计灵感来自以下开源项目，详见 [ACKNOWLEDGEMENTS.md](./ACKNOWLEDGEMENTS.md)：

- [菠萝王朝 (boluobobo-ai-court-tutorial)](https://github.com/wanikua/boluobobo-ai-court-tutorial) — 率先将三省六部制引入 OpenClaw
- [三省六部 (edict)](https://github.com/cft0808/edict) — 完整的三省六部 pipeline 实现，门下省封驳机制的核心参考

## License

[MIT](./LICENSE) © 2026 Bill Huang
