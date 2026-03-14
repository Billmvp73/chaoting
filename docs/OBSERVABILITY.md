# Observability Infrastructure

> Added in ZZ-20260314-004  
> Covers three layers: log querying, test-results persistence, and service health checks.

---

## Overview

The chaoting observability infrastructure provides three complementary layers for monitoring and
validating executor work before it enters the PR review pipeline:

| Layer | Command / Feature | Purpose |
|-------|-------------------|---------|
| 1 | `chaoting logs <service>` | Query journalctl service logs with filters |
| 2 | push-for-review auto-commit | Persist test results into the PR branch |
| 3 | `chaoting health <service>` + push-for-review gate | Enforce service health before code review |

---

## Layer 1 — Log Querying

### Command

```bash
chaoting logs <service> [--tail N] [--grep pattern] [--since Xs|Xm|Xh]
```

### Options

| Flag | Type | Description |
|------|------|-------------|
| `--tail N` | integer | Show only the last N log lines |
| `--grep pattern` | string | Filter lines matching a regex pattern |
| `--since Xs\|Xm\|Xh` | string | Show logs from the last X seconds/minutes/hours |

### Examples

```bash
# Last 50 lines from the chaoting dispatcher
chaoting logs chaoting-dispatcher-.themachine --tail 50

# Search for ERRORs in the last hour
chaoting logs beebot --grep "ERROR" --since 1h

# Last 30 minutes of gateway logs
chaoting logs themachine-gateway --since 30m

# Combine all filters
chaoting logs chaoting-dispatcher-.themachine --tail 100 --grep "dispatch" --since 2h
```

### Output Format

```json
{
  "ok": true,
  "service": "chaoting-dispatcher-.themachine",
  "line_count": 42,
  "logs": "Mar 13 18:00:01 host chaoting[1234]: INFO Dispatched ZZ-20260314-004...\n...",
  "filters": {
    "tail": 50,
    "grep": "dispatch",
    "since": "1h"
  }
}
```

---

## Layer 2 — Test Results Persistence

When `push-for-review` is called, it automatically detects and commits
`docs/test-results/<ZZ-ID>.md` into the current PR branch (if the file exists in
the task's `repo_path`).

### Workflow

1. **Before calling `push-for-review`**, the executor writes test output to:
   ```
   docs/test-results/<ZZ-ID>.md
   ```
   inside the repository root.

2. **`push-for-review` auto-commits the file** into the PR branch:
   ```bash
   git add docs/test-results/<ZZ-ID>.md
   git commit -m "test: add test results for <ZZ-ID>"
   ```

3. The response includes a `test_results_note` field describing the outcome.

### Example Response

```json
{
  "ok": true,
  "zouzhe_id": "ZZ-20260314-004",
  "state": "pr_review",
  "note": "dispatcher will dispatch to yushi on next poll",
  "test_results_note": "test results committed: docs/test-results/ZZ-20260314-004.md",
  "test_results_committed": true
}
```

### Test Results File Format

No strict schema is required — the file is free-form Markdown. Recommended structure:

```markdown
# Test Results for ZZ-20260314-004

## Summary

- Total: 15
- Passed: 15
- Failed: 0

## Output

```
...test output here...
```

## Verdict

✅ All tests PASS
```

---

## Layer 3 — Service Health Checks

### Standalone Health Command

```bash
chaoting health <service> [--endpoint URL]
```

#### Options

| Flag | Description |
|------|-------------|
| `--endpoint URL` | Optional HTTP endpoint to curl; result included in `endpoint_ok` |

#### Examples

```bash
# Check if the chaoting dispatcher is active
chaoting health chaoting-dispatcher-.themachine

# Check beebot with HTTP endpoint
chaoting health beebot --endpoint http://localhost:8080/health

# Check the TheMachine gateway
chaoting health themachine-gateway
```

#### Output Format

```json
{
  "ok": true,
  "service": "chaoting-dispatcher-.themachine",
  "active": true,
  "healthy": true,
  "details": [
    "systemctl status: active"
  ]
}
```

With `--endpoint`:

```json
{
  "ok": true,
  "service": "beebot",
  "active": true,
  "healthy": true,
  "endpoint_ok": true,
  "details": [
    "systemctl status: active",
    "endpoint http://localhost:8080/health: OK"
  ]
}
```

On failure:

```json
{
  "ok": true,
  "service": "my-service",
  "active": false,
  "healthy": false,
  "details": [
    "systemctl status: inactive"
  ]
}
```

### Health Gate in push-for-review

`push-for-review` enforces a health gate when `--service <name>` is specified:

```bash
chaoting push-for-review <zouzhe_id> '<output>' --service <service-name>
```

If the service is **not healthy**, the command aborts before any state transition:

```
Error: Health gate FAILED for service 'my-service': systemctl status: inactive.
       Use --skip-health-check to bypass.
```

#### Bypass

```bash
chaoting push-for-review <zouzhe_id> '<output>' \
  --service my-service \
  --skip-health-check
```

When bypassed, the response includes:

```json
{
  "ok": true,
  "health_note": "health gate skipped (--skip-health-check) for service 'my-service'"
}
```

#### No `--service` Flag

If `--service` is not specified, the health gate is not applied and the command
proceeds silently.

---

## Common Services

| Service Name | Description |
|--------------|-------------|
| `chaoting-dispatcher-.themachine` | Main chaoting dispatcher |
| `chaoting-dispatcher-.beebot` | BeeBot chaoting dispatcher |
| `beebot.service` | BeeBot Gateway |
| `themachine-gateway.service` | TheMachine Gateway |

---

## Related Documents

- [docs/INDEX.md](INDEX.md) — document index
- [docs/WORKFLOW-bingbu.md](WORKFLOW-bingbu.md) — executor workflow including push-for-review steps
- [docs/GIT-WORKFLOW.md](GIT-WORKFLOW.md) — branch and commit conventions
