# Yushi PR Code Review Agent — Design Document

> **Task ID**: ZZ-20260313-006
> **Date**: 2026-03-13
> **Author**: libu (Documentation Executor)
> **Document Type**: Design Document (repo-facing, English)
> **References**: ZZ-20260310-006 (Agent Teams Reviewer Modes), ZZ-20260310-009 (Planner Integration Research)

---

## 1. Background

The original P1-1 design named the automated code review agent `jishi_review`. However, this creates a naming conflict: `jishi` (给事中) is already the identifier for the **plan review** role in the review gate (Menxia / Gate Review), which operates in the `reviewing` state to evaluate task plans.

A PR code review agent operates at a completely different stage — after code execution, when a PR has been submitted — and serves a different purpose: **code quality auditing**, not plan approval. Using `jishi_review` blurs this boundary.

This document resolves two problems:

1. **Naming**: Select a clear, conflict-free role name for the PR code review agent.
2. **State Machine Design**: Define how PR code review integrates into the existing task state machine.

---

## 2. Role Naming — Candidate Evaluation

### 2.1 Evaluation Dimensions

| Dimension | Description |
|-----------|-------------|
| **Role Fit** | How closely the historical role's function maps to PR code review duties |
| **Naming Conflict Risk** | Risk of confusion with existing system roles (`jishi`, `silijian`, `zhongshu`, etc.) |
| **Historical Semantic Accuracy** | Accuracy of the Ming Dynasty role analogy |

**PR code review duties:**
- Independent from the executor (does not write code)
- Audits code quality, security risks, and standards compliance
- Issues **APPROVE** or **NOGO** (can block PR merge)
- No administrative authority over executors; quality-review authority only

### 2.2 Four-Candidate Comparison Table

| Role | Institution | Historical Function | Role Fit | Conflict Risk | Semantic Accuracy | **Score** |
|------|-------------|---------------------|----------|---------------|-------------------|-----------|
| **yushi (御史)** | Censorate / Duchayuan | Auditing officials, impeaching violations, independent of the Six Ministries, reports directly to the Emperor | ⭐⭐⭐⭐⭐ | 🟢 Low | ⭐⭐⭐⭐⭐ | **14/15** |
| **jiandao (检讨)** | Hanlin Academy | Reviewing documents, checking for omissions and errors | ⭐⭐⭐ | 🟡 Medium | ⭐⭐⭐ | **9/15** |
| **duchayuan (都察院)** | Supreme Censorate | The institution overseeing all censors (yushi) | ⭐⭐⭐ | 🟢 Low | ⭐⭐⭐ | **9/15** |
| **hanlin (翰林)** | Hanlin Academy | Drafting imperial documents, format and style review | ⭐⭐ | 🟢 Low | ⭐⭐ | **6/15** |

### 2.3 Detailed Analysis

#### yushi (御史) — Recommended ✅

**Historical role**: In the Ming Dynasty, censors (yushi) operated under the Censorate (都察院), independent of the Six Ministries. Their duty was to audit the conduct and compliance of officials, impeach violations, and report directly to the Emperor. They did not participate in administration — they only evaluated results.

**Why it maps to PR code review:**
- **Independence**: yushi is not part of the executing ministries; a PR reviewer does not write the code they review
- **Post-execution auditing**: yushi reviewed officials after they acted; PR review happens after code is committed
- **Blocking authority**: yushi could impeach and halt — PR reviewer can issue NOGO to block merges
- **Quality focus**: yushi asked "does this comply with the rules?"; PR reviewer asks "does this meet quality standards?"

**Naming conflict analysis:**
- `yushi` vs `jishi`: clearly distinct in both pronunciation and meaning
- Semantic boundary is clean: `jishi` reviews **plans** (in the `reviewing` state), `yushi` reviews **code** (after execution, at the PR stage)

#### jiandao (检讨) — Runner-Up

The Hanlin Academy's jiandao role had a "re-review" connotation that partially maps to code review. However:
- In modern Chinese, "检讨" carries a strong connotation of self-criticism, which creates semantic confusion
- The Hanlin Academy focused on literary and ceremonial documents, not quality enforcement
- The role was low-ranking (seventh grade), which does not reflect the importance of code review

#### duchayuan (都察院) — Institution Name, Not Suitable for a Single Agent

The Duchayuan was the **institution** overseeing all censors. Naming a single agent "Duchayuan" would be a category error (naming an individual after their organization). It is better suited as the name for a **multi-yushi team** in future extensions:
- Single agent: `yushi`
- Future multi-reviewer team: `duchayuan`

#### hanlin (翰林) — Not Recommended

The Hanlin Academy's role centered on drafting literary documents and ceremonial text. This maps more naturally to documentation work (which `libu` already handles), not to code quality auditing.

### 2.4 Recommendation

> **Recommended name: `yushi` (御史)**

Summary:
1. **Best role fit**: The censor's defining trait — independent auditing after execution — directly mirrors PR code review
2. **Lowest conflict risk**: Clearly distinct from `jishi` (plan review); the two roles have non-overlapping scopes
3. **Most accurate historical analogy**: The Censorate is the Ming Dynasty's canonical "independent third-party auditor" institution
4. **Extensible**: If multiple specialized reviewers are needed in the future, `duchayuan` can serve as the team name

---

## 3. State Machine Design — Three Options

### 3.1 Current State Machine Overview

```
created → planning (zhongshu)
              ↓
          reviewing (jishi votes)
              ↓
          executing (executor)
              ↓
            done ✓

Special paths:
  reviewing → revising (jishi NOGO) → planning (re-plan)
  any state → failed / timeout
```

**Current PR flow**: After the executor completes work in `executing`:
1. Calls `chaoting done ZZ-ID` → state changes to `done`
2. Creates GitHub Issue + PR + self-review (three-step double-link)
3. Waits for silijian (the merge authority) to review and Squash Merge

**The problem**: Once `done` is called, the state is already closed. There is no mechanism to block the PR merge before yushi completes its review.

---

### 3.2 Option A: Sub-Task (sub-zouzhe)

#### Mechanism

After the executor calls `done`, the main task closes. The dispatcher automatically creates a child task assigned to yushi. The yushi verdict (APPROVE/NOGO) is reflected in the child task; the main task is unaffected.

```
executing → done (main task closed)
                ↓ dispatcher auto-creates
            child-task (yushi PR review)
                ↓
          child done (APPROVE) → silijian may merge
                ↓
          child fail (NOGO) → silijian notifies executor to fix
```

#### Evaluation

| Dimension | Assessment |
|-----------|------------|
| **Observability** | 🟡 Medium: child task is visible, but main task is already done; the association requires extra fields |
| **Autonomous loop** | 🔴 Low: main task is done; NOGO cannot auto-trigger executor revision without additional logic |
| **Implementation cost** | 🟡 Medium: needs sub-task association mechanism + auto-creation logic in dispatcher |
| **Blocking capability** | 🔴 Weak: main task is done; silijian may merge before yushi finishes; NOGO cannot technically block merge |
| **Implementation risk** | 🟡 Medium | |
| **NOGO handling** | Requires manual intervention or extra logic | |
| **State machine compatibility** | ✅ Compatible (no changes to main flow) | |

**Core problem**: After the main task reaches `done`, blocking relies on **convention** ("wait for the child task to complete before merging"), not a technical guarantee. In high-volume scenarios this is easily bypassed.

---

### 3.3 Option B: New `pr_review` State

#### Mechanism

The executor does not call `done` directly. Instead, it calls `push-for-review` (or a modified `done` flow that transitions to `pr_review`). The dispatcher detects the `pr_review` state and assigns yushi. Only after yushi issues APPROVE does the state advance to `done`; on NOGO, the task returns to the executor for revision.

```
executing
    ↓ executor calls: chaoting push-for-review ZZ-ID
pr_review (dispatcher assigns to yushi)
    ↓                         ↓
  APPROVE                   NOGO
    ↓                         ↓
  done ✓              executor_revise (re-assigned to executor)
                               ↓
                          pr_review (re-review, loop)
```

#### New CLI Commands

```bash
# Executor calls after completing work (replaces done)
chaoting push-for-review ZZ-ID 'output description (including PR URL)'
# Effect: executing → pr_review

# yushi calls after approving
chaoting yushi-approve ZZ-ID
# Effect: pr_review → done

# yushi calls on rejection
chaoting yushi-nogo ZZ-ID 'reason'
# Effect: pr_review → executor_revise (re-assigned to executor)
```

#### NOGO Loop Limit

```
pr_review → (yushi NOGO) → executor_revise
                                 ↓ executor fixes code, pushes new commit
                         (executor calls push-for-review)
                                 ↓
                             pr_review (re-assigned to yushi)
                                 ↓
                             APPROVE → done ✓

Max loops: reuse existing exec_revise_count, default limit 3
Over limit: escalated → human intervention
```

#### Evaluation

| Dimension | Assessment |
|-----------|------------|
| **Observability** | ✅ Strong: main task state fully reflects PR review progress; silijian can see `pr_review` state |
| **Autonomous loop** | ✅ Strong: NOGO → executor_revise → pr_review loop is fully automatic |
| **Implementation cost** | 🔴 High: new state + new CLI commands + dispatcher routing + yushi pull template |
| **Blocking capability** | ✅ Strong: main task is not in `done`; silijian cannot merge (technical block) |
| **Implementation risk** | 🟡 Medium-High | |
| **NOGO handling** | Fully automatic loop | |
| **State machine compatibility** | 🟡 Requires extension (new state) | |

---

### 3.4 Option C: Notification Only (Bypass Check)

#### Mechanism

No changes to the state machine. After the executor calls `done`, the dispatcher notifies silijian as usual and simultaneously sends a **bypass notification** to yushi to perform an async PR review. Yushi posts results to the task's Discord Thread. Silijian references the yushi verdict when deciding whether to merge.

```
executing → done (main task complete)
                ↓ dispatcher bypass notification
            yushi async PR review
                ↓
            result posted to Discord Thread
                ↓
            silijian reviews opinion → decides to merge or reject
```

#### Evaluation

| Dimension | Assessment |
|-----------|------------|
| **Observability** | 🟡 Medium: visible in Thread, but not tracked in state machine or `chaoting stats` |
| **Autonomous loop** | 🔴 Low: NOGO requires silijian to intervene manually; no auto-revision loop |
| **Implementation cost** | ✅ Low: only add bypass notification logic in `_check_new_done_failed()`; zero routing changes |
| **Blocking capability** | 🔴 None: no technical block; relies entirely on silijian's judgment |
| **Implementation risk** | ✅ Low | |
| **NOGO handling** | Fully manual | |
| **State machine compatibility** | ✅ Fully compatible | |

**MVP value**: Option C's value is in **quickly validating yushi's effectiveness** — getting yushi running without touching the core state machine, then using its review quality data to inform Option B's integration.

---

### 3.5 Comparison Matrix

| Dimension | Option A (sub-task) | Option B (pr_review state) | Option C (notification only) |
|-----------|---------------------|---------------------------|------------------------------|
| **Observability** | 🟡 Medium | ✅ Strong | 🟡 Medium |
| **Autonomous loop** | 🔴 Low | ✅ Strong | 🔴 Low |
| **Implementation cost** | 🟡 Medium | 🔴 High | ✅ Low |
| **Blocking capability** | 🔴 Weak (convention) | ✅ Strong (technical) | 🔴 None |
| **Implementation risk** | 🟡 Medium | 🟡 Medium-High | ✅ Low |
| **NOGO handling** | Manual / extra logic | Fully automatic | Fully manual |
| **State machine compatibility** | ✅ Compatible | 🟡 Requires extension | ✅ Fully compatible |
| **Best for** | Not recommended | Full solution | MVP validation |

---

## 4. Recommended Path: Progressive Implementation

### 4.1 Summary Recommendation

> **Recommended: Option C as MVP → Option B as full integration**

```
Phase A (MVP): Option C — Bypass Notification
  Goal: get yushi running quickly, validate review quality
  Duration: ~2 days
  Risk: very low (no changes to core state machine)

Phase B (Full): Option B — pr_review State
  Goal: technical blocking + autonomous NOGO loop
  Prerequisite: Phase A validates yushi reliability
  Duration: ~5 days
  Risk: medium (changes to dispatcher + CLI)
```

### 4.2 Alignment with Observability and Autonomous Loop Goals

**Observability:**
- Option B is optimal: `pr_review` is a first-class task state; `chaoting status` tracks it; audit log is complete
- Option C is acceptable for MVP phase; must progress to Option B for the full solution

**Autonomous loop:**
- Option B fully implements: NOGO → executor_revise → pr_review runs without human intervention
- Option C does not support autonomous loops at all (all NOGO handling requires silijian to act manually)
- This is the primary reason Option B is the final target

**Why Option A is not recommended:**
The "main task already done" design means blocking relies on convention, not technical enforcement. In high-frequency scenarios this is easily skipped. The NOGO loop also requires extra parent-child association logic — comparable complexity to Option B but with weaker guarantees.

### 4.3 Phase A: Option C MVP Implementation Notes

**Minimum-invasive change:**
```python
# dispatcher.py: in _check_new_done_failed(), add yushi notification
def _check_new_done_failed(db):
    for target_state in ('done', 'failed', 'timeout'):
        ...
        if target_state == 'done':
            # Existing: notify silijian
            # New: bypass-notify yushi for PR review
            _notify_yushi_for_pr_review(db, row)
```

**Notification format sent to yushi:**
```
📜 PR Code Review Request

Task ID: ZZ-XXXXXXXX-NNN
Title: <task title>
Executor: <agent_id>
PR URL: <extracted from done output>

Please review the above PR and post results to the corresponding Thread.
Review dimensions: code quality, security risks, standards compliance, test coverage
Final verdict: APPROVE / NOGO (with specific reasons)
```

### 4.4 Phase B: Option B Full Implementation Notes

**New state**: `pr_review` (between `executing` and `done`)

**dispatcher.py changes summary (~100-150 lines):**
```python
# Detect pr_review state → assign to yushi
pr_review_undispatched = db.execute(
    "SELECT * FROM zouzhe WHERE state = 'pr_review' AND dispatched_at IS NULL"
)
for row in pr_review_undispatched:
    _dispatch_to_yushi(db, row)

# New: executor_revise after NOGO → re-assign to executor
```

**Implementation milestones:**

```
Milestone 1: Phase A live → yushi begins bypass review
  Complete when: yushi reviews 5+ PRs; silijian confirms quality is acceptable

Milestone 2: Data collection (~2 weeks) → yushi NOGO accuracy evaluation
  Pass criteria: NOGO correctly identifies real issues > 80%; false positive rate < 20%

Milestone 3: Phase B implementation → pr_review state + technical blocking
  Prerequisites: Milestone 2 passed + executors familiar with new workflow

Milestone 4 (optional): Multiple yushi in parallel (similar to jishi_tech + jishi_risk)
  Use case: high-priority tasks requiring both technical and security review
```

---

## 5. Yushi Agent Role Definition

### 5.1 Responsibility Boundaries

| Responsibility | yushi | executor (executing ministry) |
|----------------|-------|-------------------------------|
| Write code | ❌ No | ✅ Yes |
| Review code quality | ✅ Yes | ❌ No |
| Block PR merge | ✅ Yes (Phase B) | ❌ No |
| Modify code | ❌ No (gives feedback only) | ✅ Yes (implements fixes based on feedback) |
| Create PR | ❌ No | ✅ Yes |

### 5.2 Review Dimensions

| Dimension | Description | Weight |
|-----------|-------------|--------|
| **Code correctness** | Logic correctness, absence of bugs | High |
| **Security risks** | Injection vulnerabilities, privilege escalation, sensitive data exposure | High |
| **Standards compliance** | Naming conventions, code style, comment quality | Medium |
| **Test coverage** | Presence of tests, coverage of edge cases | Medium |
| **Architectural consistency** | Alignment with existing architectural design | Medium |

### 5.3 APPROVE / NOGO Criteria

```
APPROVE: No high-risk issues in any dimension; code quality meets project standards

NOGO (must include specific, actionable feedback with line references):
  - Any security vulnerability present
  - Obvious logic errors present
  - Severely non-compliant code (unmaintainable)
  - Tests completely absent for high-risk changes
```

---

## 6. Summary

### 6.1 Naming Recommendation

**`yushi` (御史)** — The Censorate's defining trait of independent post-execution auditing maps perfectly to PR code review. The naming boundary with `jishi` (plan review) is clear and non-overlapping.

### 6.2 Implementation Path

| Phase | Option | Core Goal | Estimated Duration |
|-------|--------|-----------|-------------------|
| MVP | Option C (bypass notification) | Get yushi running, validate review quality | ~2 days |
| Full | Option B (pr_review state) | Technical blocking + autonomous NOGO loop | ~5 days |

### 6.3 Why Option A is Not Recommended

Once the main task reaches `done`, NOGO blocking relies on convention rather than a technical guarantee. The NOGO loop requires extra parent-child task association logic — comparable complexity to Option B but with significantly weaker guarantees.

---

*Document authored by libu (Documentation Executor), 2026-03-13*
*Based on: current dispatcher.py state machine analysis + ZZ-20260310-006/009 prior research*
