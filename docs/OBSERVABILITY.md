# OBSERVABILITY.md — Agent Observability Infrastructure

> Version: v1.0 | Last updated: 2026-03-14

---

## Overview

Autonomous agent loops require closed-loop self-verification: an agent should be able to
**execute changes → verify results → self-correct** without depending on a human QA step.

The chaoting observability infrastructure provides three lightweight layers:

| Layer | Tool | Purpose |
|-------|------|---------|
| 1 | `chaoting logs` | Query service logs to detect errors after code changes |
| 2 | Test-results persistence | Persist test output to the PR branch for yushi review |
| 3 | `chaoting health` | Verify service liveness before submitting for review |

---

## Layer 1: Service Log Queries (`chaoting logs`)

Query application logs for a running service using journalctl.

### Usage

```bash
chaoting logs <service> [--tail N] [--grep PATTERN] [--since Xs]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--tail N` | Show last N lines | 50 |
| `--grep PATTERN` | Filter lines matching PATTERN (journalctl regex) | (none) |
| `--since Xs` | Show logs from the last X seconds | (journalctl default) |

### Examples

```bash
# Show last 20 lines from the dispatcher service
chaoting logs chaoting-dispatcher-.themachine --tail 20

# Check for errors in beebot logs from the last 60 seconds
chaoting logs beebot --tail 50 --grep "ERROR" --since 60s

# View recent beebot logs
chaoting logs beebot --tail 30
```

### Output Format

```json
{
  "ok": true,
  "service": "chaoting-dispatcher-.themachine",
  "lines": [
    "Mar 14 00:01:00 host dispatcher[1234]: INFO dispatching ZZ-001",
    "..."
  ],
  "count": 20
}
```

### Known Services

| Service Name | Description |
|-------------|-------------|
| `chaoting-dispatcher-.themachine` | Main chaoting dispatcher process |
| `beebot` | Beebot AI agent orchestration framework |

---

## Layer 2: Test Results Persistence

Agents write test output to `docs/test-results/<ZZ-ID>.md` before calling `push-for-review`.
When `push-for-review` is invoked with `--worktree <path>`, the file is automatically committed
to the PR branch so yushi can review it during code review.

### Convention

After running tests for a task, write results to:

```
docs/test-results/<ZZ-ID>.md
```

inside the worktree directory. Example content:

```markdown
# Test Results: ZZ-20260314-001

**Date**: 2026-03-14
**Commit**: abc1234

## Summary
- Total: 12 tests
- Passed: 12
- Failed: 0

## Output

​```
test_cmd_logs ... ok
test_cmd_health_active ... ok
...
Ran 12 tests in 0.847s
OK
​```
```

### Auto-Commit via --worktree

When the test-results file exists, `push-for-review --worktree <path>` automatically runs:

```bash
git -C <worktree> add docs/test-results/<ZZ-ID>.md
git -C <worktree> commit -m "test-results: <ZZ-ID>"
```

If the commit fails or there is nothing to commit, the command continues silently.

---

## Layer 3: Service Health Checks (`chaoting health`)

Verify that a service is running correctly before submitting for review.

### Usage

```bash
chaoting health <service> [--port PORT]
```

### Options

| Flag | Description |
|------|-------------|
| `--port PORT` | Additionally check `http://localhost:PORT/health` (falls back to `/`) |

### Examples

```bash
# Check if the dispatcher is running
chaoting health chaoting-dispatcher-.themachine

# Check beebot with HTTP endpoint
chaoting health beebot --port 8080
```

### Output Format

```json
{
  "ok": true,
  "service": "chaoting-dispatcher-.themachine",
  "active": true,
  "status": "active",
  "endpoint_ok": null
}
```

`ok` is `true` only when:
- `active` is `true`
- `endpoint_ok` is `true` or `null` (no port check requested)

### Integration with push-for-review

Use `--service` to gate `push-for-review` on a passing health check:

```bash
# Will abort if the service is not active
chaoting push-for-review ZZ-20260314-001 "PR #99: https://github.com/..." \
  --service chaoting-dispatcher-.themachine

# Bypass health check (use for tasks that do not involve a running service)
chaoting push-for-review ZZ-20260314-001 "PR #99: https://github.com/..." \
  --skip-health-check
```

---

## Recommended Verification Workflow

After implementing changes that affect a running service, follow this sequence
before calling `push-for-review`:

```bash
# 1. Run tests and save results
python -m pytest tests/ -v 2>&1 | tee docs/test-results/ZZ-XXXXXXXX-NNN.md

# 2. Check service health
chaoting health <service-name>

# 3. Inspect recent logs for errors
chaoting logs <service-name> --tail 20 --grep "ERROR"

# 4. Submit for review (with --worktree to auto-commit test results)
chaoting push-for-review ZZ-XXXXXXXX-NNN "PR #N: https://github.com/..." \
  --worktree /path/to/worktree \
  --service <service-name>
```

For tasks that do **not** involve a running service (e.g., pure library changes, docs):

```bash
# Run tests and save results
python -m pytest tests/ -v 2>&1 | tee docs/test-results/ZZ-XXXXXXXX-NNN.md

# Submit for review (skip health check)
chaoting push-for-review ZZ-XXXXXXXX-NNN "PR #N: https://github.com/..." \
  --worktree /path/to/worktree \
  --skip-health-check
```

---

## Known Services Reference

| Service | Health Check Command | Notes |
|---------|---------------------|-------|
| `chaoting-dispatcher-.themachine` | `chaoting health chaoting-dispatcher-.themachine` | Main dispatcher; no HTTP port |
| `beebot` | `chaoting health beebot --port <PORT>` | Check actual configured port |
