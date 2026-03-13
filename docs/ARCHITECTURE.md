# Architecture Overview

> Last updated: 2026-03-13
> Maintained by: libu (Documentation Executor)

This document provides a high-level overview of the Chaoting task orchestration system: its agent roles, state machine, and key architectural components.

---

## 1. System Overview

Chaoting is a multi-agent task orchestration platform modeled on the administrative structure of the Ming Dynasty imperial court. Human operators submit tasks ("memorials" / zouzhe) via CLI; the system routes each task through a structured lifecycle involving planning, review, execution, and completion.

Each agent in the system occupies a distinct administrative role with defined responsibilities, permissions, and tools. No single agent has unconstrained write access — every significant action is gated by role-appropriate checks.

---

## 2. Agent Roles

| Agent ID | Role Type | Chinese Name | Responsibility |
|----------|-----------|--------------|----------------|
| `silijian` | leader | 司礼监 | Creates tasks, issues final rulings, sole merge authority for all PRs |
| `zhongshu` | planner | 中书省 | Analyzes task requirements, selects executor, submits execution plans |
| `jishi_tech` | reviewer | 给事中（技术）| Technical feasibility review of plans |
| `jishi_risk` | reviewer | 给事中（风险）| Risk assessment review of plans |
| `jishi_compliance` | reviewer | 给事中（合规）| Compliance and policy review of plans |
| `jishi_resource` | reviewer | 给事中（资源）| Resource estimation review of plans |
| `bingbu` | executor | 兵部 | Code development and bug fixes |
| `gongbu` | executor | 工部 | DevOps, deployment, CI/CD |
| `hubu` | executor | 户部 | Data processing, database changes |
| `libu` | executor | 礼部 | Documentation authoring |
| `libu_hr` | executor | 吏部 | Project management, HR |
| `xingbu` | executor | 刑部 | Security auditing |
| `yushi` | reviewer | 御史 | PR code review — independent post-execution code quality auditor *(planned, Phase A/B)* |

---

## 3. State Machine

### 3.1 Standard Task Flow

```
created
   │
   ▼
planning ──────────────────────────────────────────────┐
   │ zhongshu submits plan                             │
   ▼                                                   │
reviewing                                              │
   │ jishi agents vote (Go / No-Go)                   │
   │                                                   │
   ├── NOGO → revising ──────────────────────────────►┘
   │            (zhongshu re-plans)
   ▼
executing
   │ executor implements, pushes PR
   │
   ├──────────────────────────────────────────────────┐
   │                                                   │
   ▼                                                   │
pr_review  ← [PLANNED — not yet implemented]          │
   │ yushi reviews PR code quality                    │
   │                                                   │
   ├── NOGO → executor_revise ──────────────────────►┘
   │            (executor fixes and re-submits)
   ▼
done ✓
```

### 3.2 Special Paths

```
reviewing  ──(3 NOGO votes)──► escalated ──► silijian ruling ──► done / failed
any state  ──(timeout)────────► timeout
any state  ──(critical error)─► failed
escalated  ──(decide approve)─► executing
escalated  ──(decide reject)──► failed
```

### 3.3 State Descriptions

| State | Description |
|-------|-------------|
| `created` | Task submitted, awaiting planning |
| `planning` | zhongshu is analyzing requirements and drafting a plan |
| `reviewing` | jishi agents are voting on the plan |
| `revising` | Plan returned to zhongshu for revision after NOGO |
| `executing` | Executor agent is implementing the task |
| `executor_revise` | Executor revising code after yushi NOGO *(planned)* |
| `pr_review` | yushi is reviewing the submitted PR *(planned)* |
| `done` | Task complete; PR merged |
| `failed` | Task failed (technical error or silijian ruling) |
| `timeout` | Task exceeded configured time limit |
| `escalated` | Reached NOGO vote limit; awaiting silijian's ruling |

---

## 4. Yushi — PR Code Review Agent

> **Status**: Planned (Phase A and Phase B, see [yushi PR Review Design](design/yushi-pr-review-design.md))

### 4.1 Role Summary

`yushi` (御史) is an independent code quality auditor modeled on the Ming Dynasty Censorate. Its role is to review submitted PRs after execution completes, before the merge authority (silijian) performs the final merge.

Unlike the `jishi` reviewers (who evaluate **plans** in the `reviewing` state), `yushi` evaluates **code** at the PR stage. The two roles have non-overlapping scopes:

| Role | Reviews | Stage |
|------|---------|-------|
| `jishi` | Task plan feasibility | `reviewing` state |
| `yushi` | Code quality, security, and compliance | After `executing`, at PR stage |

### 4.2 Permissions

| Permission | Status | Notes |
|------------|--------|-------|
| Modify code | ❌ No | Reviews only; never edits files |
| Issue APPROVE | ✅ Yes | Allows PR to proceed to merge |
| Issue NOGO | ✅ Yes (Phase B) | Blocks PR; returns task to executor for revision |
| Merge PR | ❌ No | Merge authority belongs exclusively to silijian |

### 4.3 Implementation Phases

**Phase A (MVP, ~2 days):** Bypass notification only (Option C). After a task reaches `done`, the dispatcher sends a parallel notification to yushi. Yushi reviews the PR asynchronously and posts its verdict to the task's Discord Thread. No state machine changes required. Purpose: validate yushi's review quality before committing to deeper integration.

**Phase B (Full, ~5 days):** New `pr_review` state (Option B). Executors call `push-for-review` instead of `done`; the task enters `pr_review`; yushi must APPROVE before the state advances to `done`. NOGO returns the task to `executor_revise`, enabling a fully autonomous revision loop.

For the full design, see [docs/design/yushi-pr-review-design.md](design/yushi-pr-review-design.md).

---

## 5. Key Design Principles

1. **Role separation**: Each agent has a single, well-defined responsibility. Reviewers do not execute; executors do not review; only silijian may merge.
2. **Audit trail**: Every state transition is logged in the `liuzhuan` (流转) table. All task actions are traceable.
3. **Convention over configuration**: Role permissions and workflows are encoded in each agent's `SOUL.md` file. Behavioral changes are made through documentation updates, not code flags.
4. **Progressive autonomy**: New capabilities (e.g., yushi) are introduced via low-risk MVP phases before full state machine integration.

---

*This document provides a structural overview. For detailed workflow instructions, see the role-specific `docs/WORKFLOW-*.md` files and `examples/souls/` directory.*
