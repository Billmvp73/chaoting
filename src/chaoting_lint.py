#!/usr/bin/env python3
"""chaoting_lint.py — Golden-rule linter for chaoting repo consistency.

Usage:
    python3 src/chaoting_lint.py

Checks 5 rules and prints PASS/FAIL per rule with a final summary.
Exits 0 if all rules pass, exits 1 if any rule fails.
"""

import os
import sys

# Repo root is two levels up from this script (src/chaoting_lint.py)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

SOULS_DIR = os.path.join(REPO_ROOT, "examples", "souls")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")

# Executor WORKFLOW docs (agents that submit PRs and must have push-for-review)
EXECUTOR_WORKFLOW_FILES = [
    "WORKFLOW-bingbu.md",
    "WORKFLOW-gongbu.md",
    "WORKFLOW-hubu.md",
    "WORKFLOW-libu.md",
    "WORKFLOW-libu_hr.md",
    "WORKFLOW-xingbu.md",
]

# Executor SOUL files — only these agents run long commands and require 'timeout'
# Reviewer/planner agents (jishi_*, yushi, zhongshu, silijian, menxia) skip timeout check
EXECUTOR_SOUL_FILES = [
    "bingbu.md",
    "gongbu.md",
    "hubu.md",
    "libu.md",
    "libu_hr.md",
    "xingbu.md",
]

SOUL_MAX_LINES = 80
SOUL_DOC_REF_THRESHOLD = 60


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_soul_files():
    """Return sorted list of (filename, filepath) for all souls/*.md files."""
    results = []
    if not os.path.isdir(SOULS_DIR):
        return results
    for name in sorted(os.listdir(SOULS_DIR)):
        if name.endswith(".md"):
            results.append((name, os.path.join(SOULS_DIR, name)))
    return results


# ---------------------------------------------------------------------------
# Rule 1: SOUL.md line count — all examples/souls/*.md must be <= 80 lines
# ---------------------------------------------------------------------------
def rule1_soul_line_count():
    """Rule 1: SOUL line count — each examples/souls/*.md must be <=80 lines."""
    violations = []
    for name, path in get_soul_files():
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        count = len(lines)
        if count > SOUL_MAX_LINES:
            violations.append(f"  {name}: {count} lines (max {SOUL_MAX_LINES})")
    if violations:
        return False, "FAIL — Rule 1: SOUL line count\n" + "\n".join(violations)
    return True, "PASS — Rule 1: SOUL line count (all files <= 80 lines)"


# ---------------------------------------------------------------------------
# Rule 2: SOUL structure — must contain responsibilities section, CLI keyword, timeout keyword
# ---------------------------------------------------------------------------
def rule2_soul_structure():
    """Rule 2: SOUL structure — must contain responsibilities section, CLI keyword, and 'timeout' (executors only)."""
    violations = []
    for name, path in get_soul_files():
        content = read_file(path)
        missing = []
        # Accept both Chinese and English responsibility headings
        has_responsibilities = (
            "职责" in content
            or "Responsibilities" in content
            or "## Role" in content
        )
        if not has_responsibilities:
            missing.append("missing '职责' section")
        has_cli = (
            ("命令示例" in content)
            or ("CLI" in content)
            or ("Commands" in content)
        )
        if not has_cli:
            missing.append("missing CLI/命令示例 section")
        # Timeout check: only required for executor agents
        if name in EXECUTOR_SOUL_FILES and "timeout" not in content.lower():
            missing.append("missing 'timeout' keyword")
        if missing:
            violations.append(f"  {name}: " + ", ".join(missing))
    if violations:
        return False, "FAIL — Rule 2: SOUL structure\n" + "\n".join(violations)
    return True, "PASS — Rule 2: SOUL structure (all files have required sections)"


# ---------------------------------------------------------------------------
# Rule 3: SOUL doc reference — files >60 lines must contain a docs/ reference
# ---------------------------------------------------------------------------
def rule3_soul_doc_reference():
    """Rule 3: SOUL doc reference — files >60 lines must contain a docs/ reference.

    Accepts both Chinese '见 docs/' and bare 'docs/' path occurrences (e.g. backtick
    format or English markdown links) to avoid false positives on non-Chinese souls.
    """
    violations = []
    for name, path in get_soul_files():
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        count = len(lines)
        if count > SOUL_DOC_REF_THRESHOLD:
            content = "".join(lines)
            if "见 docs/" not in content and "docs/" not in content:
                violations.append(f"  {name}: {count} lines but no '见 docs/' reference")
    if violations:
        return False, "FAIL — Rule 3: SOUL doc reference\n" + "\n".join(violations)
    return True, "PASS — Rule 3: SOUL doc reference (all long files reference docs/)"


# ---------------------------------------------------------------------------
# Rule 4: WORKFLOW push-for-review — executor WORKFLOW docs must contain it
# ---------------------------------------------------------------------------
def rule4_workflow_push_for_review():
    """Rule 4: Executor WORKFLOW docs must contain 'push-for-review'."""
    violations = []
    for filename in EXECUTOR_WORKFLOW_FILES:
        path = os.path.join(DOCS_DIR, filename)
        if not os.path.isfile(path):
            violations.append(f"  {filename}: file not found")
            continue
        content = read_file(path)
        if "push-for-review" not in content:
            violations.append(f"  {filename}: missing 'push-for-review' step")
    if violations:
        return False, "FAIL — Rule 4: WORKFLOW push-for-review\n" + "\n".join(violations)
    return True, "PASS — Rule 4: WORKFLOW push-for-review (all executor workflows have the step)"


# ---------------------------------------------------------------------------
# Rule 5: PR/Issue format — docs/GIT-WORKFLOW.md must contain 'Closes #'
# ---------------------------------------------------------------------------
def rule5_pr_issue_format():
    """Rule 5: docs/GIT-WORKFLOW.md must contain 'Closes #' format requirement."""
    path = os.path.join(DOCS_DIR, "GIT-WORKFLOW.md")
    if not os.path.isfile(path):
        return False, "FAIL — Rule 5: PR/Issue format (GIT-WORKFLOW.md not found)"
    content = read_file(path)
    if "Closes #" not in content:
        return False, "FAIL — Rule 5: PR/Issue format (GIT-WORKFLOW.md missing 'Closes #' requirement)"
    return True, "PASS — Rule 5: PR/Issue format (GIT-WORKFLOW.md contains 'Closes #' requirement)"


def main():
    rules = [
        rule1_soul_line_count,
        rule2_soul_structure,
        rule3_soul_doc_reference,
        rule4_workflow_push_for_review,
        rule5_pr_issue_format,
    ]

    passed = 0
    total = len(rules)
    results = []

    for rule_fn in rules:
        ok, message = rule_fn()
        results.append((ok, message))
        if ok:
            passed += 1

    print("=" * 60)
    print("chaoting golden-rule linter")
    print("=" * 60)
    for ok, message in results:
        print(message)
    print("=" * 60)
    print(f"Summary: {passed}/{total} rules passed")
    print("=" * 60)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
