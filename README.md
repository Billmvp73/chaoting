# 朝廷 (Chaoting) — Multi-Agent Task Orchestration System

> A multi-agent task orchestration framework inspired by ancient Chinese imperial bureaucracy, built for [TheMachine](https://github.com/phuang/themachine) (formerly OpenClaw).

---

## Overview

**Chaoting** coordinates multiple AI agents to collaboratively complete complex tasks. Each task ("奏折/zouzhe") flows through planning, review, and execution stages — mirroring the historical Three Departments and Six Ministries (三省六部) system.

Agents communicate exclusively through a shared SQLite database (stigmergy pattern) — **no direct agent-to-agent communication**. A central dispatcher daemon polls the database and dispatches agents via the TheMachine gateway.

### Key Features

- **Zouzhe-driven workflow** — Each task flows as a "zouzhe" (memorial to the throne) through a well-defined state machine
- **Separation of concerns** — Planning, review, coding, ops, data, and documentation handled by specialized agents
- **Go/No-Go review gate** — Menxiasheng (門下省) reviewers vote on plans before execution
- **CAS-protected state machine** — Compare-And-Swap prevents concurrent state conflicts
- **Auto-retry with timeout** — Failed or timed-out tasks are automatically retried
- **Self-contained workspace deploy** — Each workspace is independent with its own code, DB, and agent configs
- **Discord notifications** — Per-zouzhe thread notifications for status updates

---

## Architecture

### System Overview

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

### Task State Machine

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

| State | Description | Owner |
|-------|-------------|-------|
| `created` | Task created, awaiting dispatch | Silijian |
| `planning` | Dispatched to Zhongshu for planning | Zhongshu |
| `reviewing` | Under Menxiasheng review, awaiting votes | Jishi (reviewers) |
| `revising` | Rejected, returned to Zhongshu for revision | System → Zhongshu |
| `executing` | Approved, being executed | Six Ministries |
| `done` | Task completed | Six Ministries |
| `failed` | Task failed (including 3 consecutive rejections) | Various |
| `timeout` | Timed out after max retries exhausted | Dispatcher |

### Concurrency Model

- All state transitions use **CAS** (Compare-And-Swap): `UPDATE ... WHERE state = <expected> RETURNING id`
- SQLite **WAL mode** + `busy_timeout=5000` for concurrent reads
- `BEGIN IMMEDIATE` for voting transactions
- Dispatcher spawns agent processes in **daemon threads**
- Gateway sessions survive CLI process death — dispatcher trusts gateway and relies on timeout for recovery

---

## Agents

### Three Departments (三省)

| Department | Agent ID | Role |
|------------|----------|------|
| 司礼監 (Silijian) | `silijian` | User proxy, oversight, creates zouzhe |
| 中書省 (Zhongshu) | `zhongshu` | Task planning and decomposition |
| 門下省 (Menxia) | `jishi_*` | Plan review (see below) |

### Reviewers (给事中)

| ID | Role | Review Focus |
|----|------|-------------|
| `jishi_tech` | Technical Reviewer | Feasibility, architecture, dependencies |
| `jishi_risk` | Risk Reviewer | Rollback plans, data safety, destructive ops |
| `jishi_resource` | Resource Reviewer | Effort estimation, token budget |
| `jishi_compliance` | Compliance Reviewer | Security, permissions |

### Six Ministries (六部)

| Ministry | Agent ID | Responsibility |
|----------|----------|---------------|
| 兵部 (War) | `bingbu` | Coding & development |
| 工部 (Works) | `gongbu` | Ops & deployment |
| 戶部 (Revenue) | `hubu` | Data processing |
| 禮部 (Rites) | `libu` | Documentation |
| 刑部 (Justice) | `xingbu` | Security audit |
| 吏部 (Personnel) | `libu_hr` | Project management |

---

## Review Mechanism (門下省)

### Review Levels

| `review_required` | Level | Reviewers |
|-------------------|-------|-----------|
| 0 | Skip (trivial) | Bypass review, execute directly |
| 1 | Standard | jishi_tech |
| 2 | Important | jishi_tech + jishi_risk |
| 3 | Critical | All 4 reviewers |

Custom reviewers can be specified via `review_agents` JSON array.

### Rejection & Rework

- Any `nogo` vote → `revising` state, old plan archived to `plan_history`, `plan` cleared
- Dispatcher returns task to Zhongshu with rejection feedback
- Zhongshu revises and resubmits for another round of review
- **Three consecutive rejections → `failed`**, escalated to Silijian for manual decision

### Timeout Handling

- Standard tasks: reviewer timeout → default `go`, with notification to Silijian
- Critical tasks (`priority=critical`): timeout → `failed`, requires manual intervention

---

## Database Tables

| Table | Pinyin | Purpose |
|-------|--------|---------|
| `zouzhe` | 奏折 | Task master table (state machine, plan, output, review fields) |
| `toupiao` | 投票 | Reviewer votes (UNIQUE per zouzhe + round + reviewer) |
| `liuzhuan` | 流转 | State transition audit log |
| `zoubao` | 奏报 | Progress reports from agents |
| `dianji` | 典籍 | Cross-task domain knowledge (key-value per agent role) |
| `qianche` | 前車 | Lessons learned |
| `tongzhi` | 通知 | Notification queue (Discord) |

---

## Installation

### Quick Start

```bash
git clone https://github.com/Billmvp73/chaoting.git
cd chaoting

# Interactive install (prompts for config)
./install.sh

# Non-interactive with defaults
./install.sh --auto-config

# Preview without making changes
./install.sh --dry-run
```

### Workspace Deploy (Recommended)

Self-contained deployment that copies all code to the workspace directory:

```bash
# Deploy to a TheMachine workspace
./install.sh --workspace ~/.themachine

# Non-interactive workspace deploy
./install.sh --workspace ~/.themachine --auto-config
```

This creates `{workspace}/.chaoting/` with its own copy of `src/`, `docs/`, `examples/souls/`, database, and logs — fully independent of the source repo.

### What `install.sh` Does

1. **Copies code** to workspace (workspace mode)
2. **Initializes/migrates** SQLite database
3. **Installs systemd user service** for the dispatcher daemon
4. **Sets up agent workspaces** — generates SOUL.md for each agent from templates
5. **Registers agents** in gateway config (`themachine.json`) with model and identity

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `CHAOTING_WORKSPACE` | Workspace root (auto-detected from CWD) |
| `CHAOTING_DIR` | Chaoting data directory (auto: `{workspace}/.chaoting`) |
| `OPENCLAW_CLI` | Path to TheMachine CLI binary |
| `OPENCLAW_AGENT_ID` | Agent identity for CLI commands |
| `AGENT_MODEL` | Override default model for agents |
| `DISCORD_FALLBACK_CHANNEL_ID` | Discord channel for notifications |

The CLI auto-detects the workspace by walking up from the current working directory, so agents don't need explicit environment configuration.

### Service Management

```bash
# Check status
systemctl --user status chaoting-dispatcher-.themachine

# Restart
systemctl --user restart chaoting-dispatcher-.themachine

# View logs
journalctl --user -u chaoting-dispatcher-.themachine -f

# Uninstall
systemctl --user disable --now chaoting-dispatcher-.themachine
rm ~/.config/systemd/user/chaoting-dispatcher-.themachine.service
```

---

## CLI Reference

```bash
# Create a new zouzhe
chaoting new --title "Task title" --desc "Description" --review 2

# Pull task details (for agents)
chaoting pull ZZ-20260308-001

# Submit plan (Zhongshu)
chaoting plan ZZ-20260308-001 '{"steps":[...],"target_agent":"bingbu",...}'

# Vote (reviewers)
chaoting vote ZZ-20260308-001 go "Feasible, risks mitigated" --as jishi_tech
chaoting vote ZZ-20260308-001 nogo "Missing rollback plan" --as jishi_risk

# Report progress
chaoting progress ZZ-20260308-001 "Progress update"

# Mark complete
chaoting done ZZ-20260308-001 "Output" "Summary"

# Mark failed
chaoting fail ZZ-20260308-001 "Failure reason"

# Update domain knowledge
chaoting context bingbu "key" "value" --source ZZ-20260308-001
```

---

## Project Structure

```
chaoting/
├── src/
│   ├── dispatcher.py      # Dispatcher daemon (~1500 lines)
│   ├── chaoting           # Agent CLI tool
│   ├── chaoting_log.py    # Audit logging module
│   ├── config.py          # Shared configuration
│   ├── init_db.py         # DB schema & migrations
│   └── sentinel.py        # Sentinel utilities
├── docs/
│   ├── SPEC.md            # Core technical spec
│   ├── SPEC-menxia.md     # Review mechanism spec
│   ├── GIT-WORKFLOW.md    # Git workflow conventions
│   ├── ROADMAP.md         # Version roadmap
│   └── CHANGELOG.md       # Change log
├── examples/
│   └── souls/             # SOUL.md templates for all 12 agents
├── install.sh             # Installer (workspace deploy + systemd + gateway config)
├── CLAUDE.md              # Claude Code project instructions
├── ACKNOWLEDGEMENTS.md
├── LICENSE                # MIT License
└── README.md
```

---

## Naming Conventions

- **States, CLI commands** → English (`created`, `planning`, `reviewing`, `executing`)
- **Table/column names, agent IDs** → Pinyin (`zouzhe`, `toupiao`, `zhongshu`, `bingbu`)
- **Task IDs** → `ZZ-YYYYMMDD-NNN`
- **Branch naming** → `pr/<ZZ-ID>-<description>`
- **Commit messages** → Conventional Commits with ZZ ID

---

## Acknowledgements

Design inspiration from these open-source projects (see [ACKNOWLEDGEMENTS.md](./ACKNOWLEDGEMENTS.md)):

- [菠萝王朝 (boluobobo-ai-court-tutorial)](https://github.com/wanikua/boluobobo-ai-court-tutorial) — Pioneered applying the Three Departments system to OpenClaw
- [三省六部 (edict)](https://github.com/cft0808/edict) — Complete Three Departments pipeline, core reference for the rejection mechanism

## License

[MIT](./LICENSE) © 2026 Bill Huang
