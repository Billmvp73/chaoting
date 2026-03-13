# TIMEOUT-GUIDE.md — Task Timeout Selection Guide

> Version: v1.0 | Updated: 2026-03-13

---

## Overview

Agents that default to `--timeout 600` for all tasks will fail on complex or long-running work. Use this guide to select the right timeout size before creating a task.

Choosing too small a timeout means the task may terminate mid-execution, leaving partial state that requires manual cleanup. **When in doubt, choose the larger size.**

---

## Size Reference Table

| Size | `--timeout` (s) | Typical Duration | Example Tasks |
|------|----------------|-----------------|---------------|
| XS | 300 | < 5 min | Simple queries, single-line fixes, read-only inspections |
| S | 600 | 5–15 min | Single-file changes (default) |
| M | 1800 | 15–45 min | Multi-file feature implementations, documentation updates |
| L | 3600 | 45–90 min | Complex features, Agent Teams pipelines, multi-module changes |
| XL | 7200 | 90–180 min | Large refactors, multi-module migrations, system-wide changes |

---

## Decision Checklist

Use the following questions to size a task:

1. **How many files will change?** — More than 3 files → M or larger
2. **How many modules are touched?** — More than 2 modules → L or larger
3. **Does it involve Agent Teams sub-agents?** — Yes → L or larger
4. **Does it include a DB migration or schema change?** — Yes → L or larger

If any item pushes the task to a larger size, use that larger size.

---

## Worktree Requirement

All tasks sized **L or XL** must use `git worktree` isolation as required by `docs/GIT-WORKFLOW.md`.

When estimating timeout for L/XL tasks:

1. **Account for worktree setup and teardown time** (~1–2 min each).
2. **Agent Teams tasks (L+) may spawn parallel sub-agents** — ensure the timeout covers the full coordination cycle, not just a single agent's execution time.
3. **If a task grows from M to L mid-execution**, prefer restarting with a higher timeout rather than retrying at the same size. Partial state from a timed-out run may require cleanup before restarting.

---

## CLI Examples

**XS — Simple query or single-line fix (300s):**

```bash
export CHAOTING_WORKSPACE=/path/to/workspace CHAOTING_DIR=/path/to/.chaoting OPENCLAW_AGENT_ID=<dept>
$CHAOTING_CLI new "XS task title" "description" --review 1 --priority normal --timeout 300
```

**S — Single-file change (600s, default):**

```bash
export CHAOTING_WORKSPACE=/path/to/workspace CHAOTING_DIR=/path/to/.chaoting OPENCLAW_AGENT_ID=<dept>
$CHAOTING_CLI new "S task title" "description" --review 1 --priority normal --timeout 600
```

**M — Multi-file feature (1800s):**

```bash
export CHAOTING_WORKSPACE=/path/to/workspace CHAOTING_DIR=/path/to/.chaoting OPENCLAW_AGENT_ID=<dept>
$CHAOTING_CLI new "M task title" "description" --review 2 --priority normal --timeout 1800
```

**L — Complex feature or Agent Teams (3600s):**

```bash
export CHAOTING_WORKSPACE=/path/to/workspace CHAOTING_DIR=/path/to/.chaoting OPENCLAW_AGENT_ID=<dept>
$CHAOTING_CLI new "L task title" "description" --review 2 --priority normal --timeout 3600
```

**XL — Large refactor or multi-module migration (7200s):**

```bash
export CHAOTING_WORKSPACE=/path/to/workspace CHAOTING_DIR=/path/to/.chaoting OPENCLAW_AGENT_ID=<dept>
$CHAOTING_CLI new "XL task title" "description" --review 2 --priority normal --timeout 7200
```

---

## When in Doubt

When unsure between two sizes, always choose the larger one. A task that completes early wastes nothing; a task that times out mid-execution may leave partial state requiring cleanup.
