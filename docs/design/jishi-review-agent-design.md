# Agent-to-Agent Code Review Design

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: libu

## Overview

### Motivation

Currently, human reviewers act as the final gate before merging pull requests. This creates a bottleneck: review latency varies, standards are inconsistently applied, and routine checks (format compliance, acceptance criteria coverage) occupy reviewer attention that could be better spent on architecture and judgment calls.

**Goal**: Introduce an automated `jishi_review` agent that performs a first-pass code review on every PR immediately after the executing agent submits it. The agent checks code correctness, acceptance criteria coverage, PR format compliance, and obvious regressions — then posts a structured review comment on the PR. Human reviewers (silijian) then make the final merge decision with the benefit of this pre-screening.

## Architecture

### jishi_review Agent Role

`jishi_review` is a **review-only** automated agent in the chaoting system. It:

- Has read access to GitHub PRs and plan files
- Posts review comments on PRs via `gh pr review`
- Cannot merge PRs, modify code, or send direct messages
- Escalates blockers to silijian via chaoting done/fail

### Trigger Mechanism

When an executing agent calls `chaoting done <ZZ-ID> <pr_url> <summary>`, the dispatcher:

1. Detects the `pr_url` field in the done event
2. Creates a new sub-zouzhe of type `review` for the same task
3. Assigns the review sub-zouzhe to `jishi_review`
4. Passes `pr_url` and `acceptance_criteria` from the original plan

## Flow

```
Executor submits PR
        │
        ▼
chaoting done ZZ-ID pr_url summary
        │
        ▼
Dispatcher detects pr_url
        │
        ▼
Create review sub-zouzhe
Assign to jishi_review
        │
        ▼
jishi_review pulls review task
        │
        ▼
gh pr diff <pr_url>
        │
        ▼
Read acceptance_criteria from plan file
(CHAOTING_DATA_DIR/docs/plans/ZZ-ID.md)
        │
        ▼
Analyze diff vs acceptance_criteria
        │
   ┌────┴────┐
PASS        NEEDS WORK
   │             │
   ▼             ▼
gh pr review  gh pr review
--approve     --request-changes
   │             │
   └────┬────────┘
        │
        ▼
chaoting done (review task)
        │
        ▼
silijian notified for final merge decision
```

## Dispatcher Integration

### Proposed `done` Event Extension

Add an optional `pr_url` field to `chaoting done`:

```bash
# Current usage
chaoting done ZZ-ID 'PR #42' 'summary text'

# Extended usage (backward compatible)
chaoting done ZZ-ID 'PR #42' 'summary text' --pr-url https://github.com/org/repo/pull/42
```

When `--pr-url` is present, the dispatcher:

1. Reads the original plan's `acceptance_criteria` from the plan file
2. Creates a new zouzhe with:
   - `title`: `"Review: <original_title>"`
   - `description`: contains `pr_url` and `acceptance_criteria`
   - `target_agent`: `jishi_review`
   - `priority`: same as parent
   - `parent_zouzhe_id`: original ZZ-ID (new DB column, optional for Phase 1)

## jishi_review Responsibilities

1. **Code Correctness**: Does the diff implement what the plan describes? Are there obvious bugs, missing error handling, or unsafe patterns?
2. **Acceptance Criteria**: For each item in `acceptance_criteria`, verify it is addressed in the diff. Flag any unaddressed items.
3. **PR Format**: Title is descriptive, body has Summary section, `Closes #N` present, no internal terminology (chaoting/zouzhe/etc.)
4. **No Obvious Regressions**: Check for deleted tests, removed error handling, or changes outside stated scope.

## Constraints

- **Read-only**: Cannot merge PRs, cannot push commits, cannot modify source code
- **Non-blocking**: If `jishi_review` fails/times out, silijian can still merge manually
- **Escalation**: Blockers or ambiguities escalated to silijian via `chaoting done` summary
- **Scope**: Reviews only the specific PR diff; does not audit unrelated code

## Open Questions

1. **Re-review on PR update**: If executor pushes a new commit after `jishi_review` posts, should a second review be triggered automatically? (Proposed: yes, on force-push or new commits)
2. **Timeout for large PRs**: Large diffs may exceed context limits. Proposed: chunk diff by file, review top N changed files.
3. **Passing acceptance_criteria**: Plan file must exist at review time. If plan file is missing (older tasks), fall back to the description field in the review sub-zouzhe.
4. **Parallel reviews**: Can multiple review sub-zouzhe exist for the same PR? (Proposed: no — dispatcher checks for existing active review sub-zouzhe before creating)

## Next Steps

Implementation of `jishi_review` is tracked in a follow-up task. This document serves as the design specification.

Key implementation items:
- [ ] Add `--pr-url` flag to `chaoting done`
- [ ] Dispatcher: detect `pr_url`, create review sub-zouzhe
- [ ] Create `jishi_review` agent session in chaoting
- [ ] Implement review workflow: pull → diff → analyze → comment
- [ ] Add `parent_zouzhe_id` column to zouzhe table (optional Phase 1)
- [ ] Integration test: end-to-end review trigger
