#!/usr/bin/env python3
"""chaoting_drift.py — Drift scanner for chaoting repo documentation consistency.

Usage:
    python3 src/chaoting_drift.py

Performs 3 drift checks and prints a drift report.
Always exits 0 (drift scanner is informational, not blocking).
"""

import os
import re
import sys
from datetime import date, datetime

# Repo root is two levels up from this script (src/chaoting_drift.py)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

SOULS_DIR = os.path.join(REPO_ROOT, "examples", "souls")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")

# Agents that are NOT executors (skipped for WORKFLOW coverage check)
NON_EXECUTOR_AGENTS = {"silijian", "yushi", "menxia", "zhongshu"}

# Pattern for metadata date header in docs
DATE_PATTERN = re.compile(
    r"(?:最后验证|Last verified)\s*[：:]\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

STALE_DAYS = 30


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Check 1: Stale metadata — docs/*.md with dates > 30 days old
# ---------------------------------------------------------------------------
def check1_stale_metadata():
    """Scan docs/*.md for stale or missing metadata headers."""
    warnings = []
    infos = []
    today = date.today()

    for name in sorted(os.listdir(DOCS_DIR)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(DOCS_DIR, name)
        if not os.path.isfile(path):
            continue
        content = read_file(path)
        match = DATE_PATTERN.search(content)
        if match:
            try:
                doc_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                delta = (today - doc_date).days
                if delta > STALE_DAYS:
                    warnings.append(
                        f"  WARNING: {name} — last verified {match.group(1)} ({delta} days ago)"
                    )
            except ValueError:
                infos.append(f"  INFO: {name} — could not parse date '{match.group(1)}'")
        else:
            infos.append(f"  INFO: {name} — no metadata date header found")

    return warnings, infos


# ---------------------------------------------------------------------------
# Check 2: Index consistency — docs/INDEX.md vs actual docs/ directory
# ---------------------------------------------------------------------------
def check2_index_consistency():
    """Compare docs/INDEX.md entries against actual docs/ files."""
    index_path = os.path.join(DOCS_DIR, "INDEX.md")
    if not os.path.isfile(index_path):
        return ["  ERROR: docs/INDEX.md not found — cannot perform index consistency check"], []

    index_content = read_file(index_path)

    # Extract file paths from INDEX.md — look for docs/*.md patterns
    indexed_files = set()
    for line in index_content.splitlines():
        # Match table rows like: | FILENAME.md | docs/FILENAME.md | ...
        # or bare references like docs/FILENAME.md
        matches = re.findall(r"\bdocs/([A-Za-z0-9_\-\.]+\.md)\b", line)
        for m in matches:
            if m != "INDEX.md":  # skip self-reference
                indexed_files.add(m)

    # Actual .md files in docs/ (excluding INDEX.md itself, subdirs)
    actual_files = set()
    for name in os.listdir(DOCS_DIR):
        if name.endswith(".md") and name != "INDEX.md":
            full_path = os.path.join(DOCS_DIR, name)
            if os.path.isfile(full_path):
                actual_files.add(name)

    missing_from_index = actual_files - indexed_files
    index_without_file = indexed_files - actual_files

    issues = []
    for name in sorted(missing_from_index):
        issues.append(f"  MISSING FROM INDEX: {name} exists in docs/ but is not listed in INDEX.md")
    for name in sorted(index_without_file):
        issues.append(f"  INDEX ENTRY WITHOUT FILE: {name} is in INDEX.md but does not exist in docs/")

    return issues, []


# ---------------------------------------------------------------------------
# Check 3: WORKFLOW coverage — each executor agent should have a WORKFLOW doc
# ---------------------------------------------------------------------------
def check3_workflow_coverage():
    """Check that each executor agent in examples/souls/ has a WORKFLOW-{agent}.md."""
    if not os.path.isdir(SOULS_DIR):
        return ["  ERROR: examples/souls/ directory not found"], []

    issues = []
    for name in sorted(os.listdir(SOULS_DIR)):
        if not name.endswith(".md"):
            continue
        agent = name[:-3]  # strip .md
        if agent in NON_EXECUTOR_AGENTS:
            continue
        workflow_file = f"WORKFLOW-{agent}.md"
        workflow_path = os.path.join(DOCS_DIR, workflow_file)
        if not os.path.isfile(workflow_path):
            issues.append(
                f"  MISSING WORKFLOW: {agent} has no docs/{workflow_file}"
            )
    return issues, []


def main():
    print("=" * 60)
    print("chaoting drift scanner")
    print("=" * 60)

    total_issues = 0

    # Check 1
    print("\n[Check 1] Stale metadata (docs/*.md date headers)")
    warnings, infos = check1_stale_metadata()
    for w in warnings:
        print(w)
        total_issues += 1
    for i in infos:
        print(i)
    if not warnings and not infos:
        print("  OK — all docs have up-to-date metadata headers")

    # Check 2
    print("\n[Check 2] Index consistency (docs/INDEX.md vs docs/ directory)")
    issues, _ = check2_index_consistency()
    for issue in issues:
        print(issue)
        total_issues += 1
    if not issues:
        print("  OK — INDEX.md is consistent with docs/ directory")

    # Check 3
    print("\n[Check 3] WORKFLOW coverage (executor agents in examples/souls/)")
    issues, _ = check3_workflow_coverage()
    for issue in issues:
        print(issue)
        total_issues += 1
    if not issues:
        print("  OK — all executor agents have WORKFLOW docs")

    # Summary
    print("\n" + "=" * 60)
    if total_issues == 0:
        print("Summary: No drift detected")
    else:
        print(f"Summary: {total_issues} drift issue(s) found — review above")
    print("=" * 60)

    sys.exit(0)  # drift scanner is always informational


if __name__ == "__main__":
    main()
