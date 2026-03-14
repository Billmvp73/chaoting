# Document Index

> Last updated: 2026-03-14
> Maintained by: libu (Documentation Executor)

This index provides a categorized overview of all documentation in the Chaoting repository.

---

## Architecture and Overview

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture overview: agent roles table, state machine diagram (including planned `pr_review` state), and yushi code review agent summary |
| [docs/SPEC.md](docs/SPEC.md) | Core system specification: data model, state machine formal definition, CLI contract |
| [docs/SPEC-menxia.md](docs/SPEC-menxia.md) | Menxia (Gate Review) subsystem specification: voting rules, NOGO thresholds, escalation logic |
| [docs/CONTEXT-MAP.md](docs/CONTEXT-MAP.md) | Context map of system components and their relationships |
| [docs/AGENT-TEAMS-GUIDE.md](docs/AGENT-TEAMS-GUIDE.md) | Guide to multi-agent teamwork patterns within a single executor (Architect → Coder → Tester → Docs) |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | Observability infrastructure: `chaoting logs` (journalctl wrapper), `chaoting health` (systemctl + HTTP check), push-for-review health gate and test-results auto-commit |

---

## Design Documents

| Document | Description |
|----------|-------------|
| [docs/design/yushi-pr-review-design.md](docs/design/yushi-pr-review-design.md) | yushi PR code review agent: naming rationale (4-candidate comparison table, yushi recommendation), state machine design options (3-option comparison matrix across 7 dimensions), and recommended progressive implementation path (Phase A bypass notification → Phase B pr_review state) |
| [docs/design/ZZ-20260310-006-agent-teams-reviewer-modes.md](docs/design/ZZ-20260310-006-agent-teams-reviewer-modes.md) | Agent Teams reviewer collaboration modes experiment: parallel vs. sequential iteration patterns, results and recommendations |
| [docs/design/ZZ-20260310-009-planner-integration.md](docs/design/ZZ-20260310-009-planner-integration.md) | Planner agent integration feasibility study: three workflow options for integrating a planning agent into the executor review stage |
| [docs/design/ZZ-20260310-004-claude-code-teams-workflow.md](docs/design/ZZ-20260310-004-claude-code-teams-workflow.md) | Claude Code Agent Teams workflow validation report |
| [docs/design/ZZ-20260310-013-bug-report-zhongshu-loop.md](docs/design/ZZ-20260310-013-bug-report-zhongshu-loop.md) | Bug report: zhongshu infinite loop issue analysis |
| [docs/design/ZZ-20260310-014-revise-unlimited.md](docs/design/ZZ-20260310-014-revise-unlimited.md) | Design: remove revise count limit (unlimited emperor revisions) |
| [docs/design/ZZ-20260310-015-bugfix-plan.md](docs/design/ZZ-20260310-015-bugfix-plan.md) | Bug fix plan: dispatcher stability issues |
| [docs/design/ZZ-20260310-016-workspace-rewrite.md](docs/design/ZZ-20260310-016-workspace-rewrite.md) | Workspace isolation rewrite design |
| [docs/DISCUSSION-phase2-planning.md](docs/DISCUSSION-phase2-planning.md) | Phase 2 planning discussion: requirements gathering and prioritization |

---

## Workflow Guides

| Document | Description |
|----------|-------------|
| [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) | Git workflow: feature branch naming, commit conventions, Issue + PR double-link requirement, Squash Merge rules |
| [docs/WORKFLOW-zhongshu.md](docs/WORKFLOW-zhongshu.md) | Planner (zhongshu) workflow: how to receive a task, draft a plan, and handle NOGO revisions |
| [docs/WORKFLOW-menxia.md](docs/WORKFLOW-menxia.md) | Gate review (menxia) workflow: how jishi agents receive plans, vote, and issue NOGO |
| [docs/WORKFLOW-bingbu.md](docs/WORKFLOW-bingbu.md) | Code executor (bingbu) workflow: implementing features, running tests, submitting PRs |
| [docs/WORKFLOW-gongbu.md](docs/WORKFLOW-gongbu.md) | DevOps executor (gongbu) workflow: deployment, CI/CD, infrastructure tasks |
| [docs/WORKFLOW-hubu.md](docs/WORKFLOW-hubu.md) | Data executor (hubu) workflow: database changes, data processing tasks |
| [docs/WORKFLOW-libu.md](docs/WORKFLOW-libu.md) | Documentation executor (libu) workflow: writing and updating docs, README, API guides |
| [docs/WORKFLOW-libu_hr.md](docs/WORKFLOW-libu_hr.md) | Project management executor (libu_hr) workflow: planning, tracking, milestone reviews |
| [docs/WORKFLOW-xingbu.md](docs/WORKFLOW-xingbu.md) | Security auditor (xingbu) workflow: security review, vulnerability assessment |
| [docs/WORKFLOW-jishi.md](docs/WORKFLOW-jishi.md) | Plan reviewer (jishi) workflow: receiving plans, evaluating, casting votes |
| [docs/TIMEOUT-GUIDE.md](docs/TIMEOUT-GUIDE.md) | Guide for selecting appropriate `--timeout` values when creating tasks |

---

## Policy Documents

| Document | Description |
|----------|-------------|
| [docs/POLICY-thread-feedback.md](docs/POLICY-thread-feedback.md) | Thread feedback policy: 30-minute post-completion feedback requirement, format rules |
| [docs/POLICY-thread-format.md](docs/POLICY-thread-format.md) | Thread message format policy: role-prefixed message templates for all 12 roles |

---

## Roadmap

| Document | Description |
|----------|-------------|
| [docs/ROADMAP.md](docs/ROADMAP.md) | Version roadmap: v0.2 through v0.4 milestone plans with completion status |
| [docs/ROADMAP-phase2.md](docs/ROADMAP-phase2.md) | Phase 2 detailed roadmap: current system inventory, P0 (completed), P1 (near-term including yushi agent), P2 (v0.3), P3 (v0.4+) items |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Changelog: version history and notable changes |

---

## Agent Soul Files

Soul files define each agent's identity, responsibilities, permissions, tools, and workflow. Located in `examples/souls/`.

| File | Agent | Role |
|------|-------|------|
| [examples/souls/silijian.md](examples/souls/silijian.md) | silijian | Leader — task creation, final rulings, sole merge authority |
| [examples/souls/zhongshu.md](examples/souls/zhongshu.md) | zhongshu | Planner — requirements analysis, plan submission |
| [examples/souls/jishi_tech.md](examples/souls/jishi_tech.md) | jishi_tech | Reviewer — technical feasibility of plans |
| [examples/souls/jishi_risk.md](examples/souls/jishi_risk.md) | jishi_risk | Reviewer — risk assessment of plans |
| [examples/souls/jishi_compliance.md](examples/souls/jishi_compliance.md) | jishi_compliance | Reviewer — compliance and policy review of plans |
| [examples/souls/jishi_resource.md](examples/souls/jishi_resource.md) | jishi_resource | Reviewer — resource estimation review of plans |
| [examples/souls/bingbu.md](examples/souls/bingbu.md) | bingbu | Executor — code development and bug fixes |
| [examples/souls/gongbu.md](examples/souls/gongbu.md) | gongbu | Executor — DevOps, deployment, CI/CD |
| [examples/souls/hubu.md](examples/souls/hubu.md) | hubu | Executor — data processing and database changes |
| [examples/souls/libu.md](examples/souls/libu.md) | libu | Executor — documentation authoring |
| [examples/souls/libu_hr.md](examples/souls/libu_hr.md) | libu_hr | Executor — project management |
| [examples/souls/xingbu.md](examples/souls/xingbu.md) | xingbu | Executor — security auditing |
| [examples/souls/yushi.md](examples/souls/yushi.md) | yushi | Reviewer — PR code review (independent post-execution auditor) *(planned)* |

---

*For questions about a specific document, refer to the task ID in its header or consult `docs/CONTEXT-MAP.md`.*
