# Architecture

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: libu

## Overview

Chaoting is a stigmergic multi-agent task orchestration system. Agents don't communicate directly — they coordinate through shared state (zouzhe/tasks) stored in SQLite. The chaoting CLI is the sole interface for all agent interactions with the system.

In a stigmergic architecture, intelligence emerges from agents responding to environmental state rather than direct messaging. Each agent polls for tasks assigned to it, executes work, and updates state — creating a traceable, auditable workflow without tight coupling between departments.

## Component Map

- **CLI Tool** (`src/chaoting`): Python CLI used by all agents; commands: new/pull/plan/progress/done/fail/status/teams
- **SQLite Database** (`chaoting.db`): Single source of truth; tables: zouzhe, zoubao, toupiao, liuzhuan
- **Dispatcher Daemon** (`src/dispatcher.py`): Polls DB, routes tasks to agents, manages review cycles
- **Agent Departments**: zhongshu (planning), menxia (gate review), jishi_* (risk/tech/resource/compliance review), bingbu (execution), gongbu (infrastructure), libu (HR/onboarding), silijian (final merge approval)
- **Agent Teams** (`chaoting teams`): Planner+Coders+Reviewer pattern for parallel execution
- **Plan Files** (`docs/plans/ZZ-ID.md`): Markdown artifacts capturing plan details, steps (checkbox format), acceptance criteria

## Data Flow

Zouzhe lifecycle:

```
created → planning (zhongshu) → reviewing (menxia + jishi_*) → executing (bingbu/gongbu/etc.) → done
                                        ↓
                                    revising (if rejected)
```

## Key Design Principles

1. **Stigmergy**: No direct agent-to-agent messaging; all coordination via shared DB state
2. **Plan-as-Artifact**: Plans written to markdown files for human readability and step tracking
3. **Gate Review**: Every task passes through menxia + jishi review before execution
4. **Separation of Concerns**: Planning, reviewing, and executing are distinct roles
