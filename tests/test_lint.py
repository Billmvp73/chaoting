"""tests/test_lint.py — Unit tests for chaoting_lint.py and chaoting_drift.py.

Coverage areas:
    1. Rule 1: SOUL line count (TestRule1LineCount)
    2. Rule 2: SOUL structure — Chinese + English fields, executor-only timeout (TestRule2EnglishAndChineseFields)
    3. Rule 4: WORKFLOW push-for-review detection (TestRule4WorkflowPushForReview)
    4. Drift check 2: INDEX.md consistency (TestDriftCheck2IndexConsistency)

Usage:
    python3 -m pytest tests/test_lint.py -v
    python3 -m unittest tests.test_lint -v
"""

import os
import sys
import textwrap
import tempfile
import unittest
from unittest.mock import patch

# Add repo src/ to path so we can import directly
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(TESTS_DIR), "src")
sys.path.insert(0, SRC_DIR)

import chaoting_lint
import chaoting_drift


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path, content):
    """Write content to path, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# 1. TestRule1LineCount
# ---------------------------------------------------------------------------

class TestRule1LineCount(unittest.TestCase):
    """Rule 1: soul files with >80 lines fail; <=80 lines pass."""

    def test_81_lines_fails(self):
        """A SOUL file with 81 lines should trigger a Rule 1 violation."""
        with tempfile.TemporaryDirectory() as tmp:
            soul_path = os.path.join(tmp, "bigbob.md")
            _write(soul_path, "\n" * 81)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule1_soul_line_count()
            self.assertFalse(ok, "Expected FAIL for 81-line soul")
            self.assertIn("bigbob.md", msg)
            self.assertIn("81 lines", msg)

    def test_80_lines_passes(self):
        """A SOUL file with exactly 80 lines should pass Rule 1."""
        with tempfile.TemporaryDirectory() as tmp:
            soul_path = os.path.join(tmp, "slim.md")
            _write(soul_path, "line\n" * 80)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule1_soul_line_count()
            self.assertTrue(ok, f"Expected PASS for 80-line soul, got: {msg}")

    def test_empty_souls_dir_passes(self):
        """No soul files → Rule 1 passes (nothing to violate)."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule1_soul_line_count()
            self.assertTrue(ok)


# ---------------------------------------------------------------------------
# 2. TestRule2EnglishAndChineseFields
# ---------------------------------------------------------------------------

class TestRule2EnglishAndChineseFields(unittest.TestCase):
    """Rule 2: responsibilities and CLI accept both Chinese and English equivalents.
    Timeout check is only required for executor agents.
    """

    # --- responsibilities ---

    def test_english_responsibilities_passes(self):
        """Non-executor file with 'Responsibilities' (no 职责) should pass Rule 2."""
        content = textwrap.dedent("""\
            ## Responsibilities
            Does things.
            ## CLI Commands
            ```
            chaoting pull
            ```
        """)
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "jishi_test.md"), content)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule2_soul_structure()
        self.assertTrue(ok, f"Expected PASS with 'Responsibilities', got: {msg}")

    def test_role_heading_passes(self):
        """Non-executor file with '## Role' (no 职责) should pass Rule 2."""
        content = textwrap.dedent("""\
            ## Role
            Reviewer.
            ## CLI
            `chaoting lint`
        """)
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "jishi_test.md"), content)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule2_soul_structure()
        self.assertTrue(ok, f"Expected PASS with '## Role', got: {msg}")

    def test_missing_responsibilities_fails(self):
        """File missing all responsibility headings should fail Rule 2."""
        content = textwrap.dedent("""\
            ## Overview
            Does nothing useful.
            ## CLI
            `chaoting lint`
            timeout 300
        """)
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "nobody.md"), content)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule2_soul_structure()
        self.assertFalse(ok, "Expected FAIL when no responsibility heading")
        self.assertIn("missing '职责' section", msg)

    # --- timeout (executor vs non-executor) ---

    def test_executor_missing_timeout_fails(self):
        """An executor soul (bingbu.md) missing 'timeout' should fail Rule 2."""
        content = textwrap.dedent("""\
            ## 职责
            编码执行。
            ## CLI 命令示例
            `chaoting pull`
        """)
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "bingbu.md"), content)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule2_soul_structure()
        self.assertFalse(ok, "Expected FAIL: executor bingbu.md missing timeout")
        self.assertIn("timeout", msg)

    def test_non_executor_missing_timeout_passes(self):
        """A non-executor soul (jishi_review.md) is exempt from timeout requirement."""
        content = textwrap.dedent("""\
            ## Responsibilities
            Reviews code quality.
            ## CLI Commands
            `chaoting lint`
        """)
        with tempfile.TemporaryDirectory() as tmp:
            _write(os.path.join(tmp, "jishi_review.md"), content)
            with patch.object(chaoting_lint, "SOULS_DIR", tmp):
                ok, msg = chaoting_lint.rule2_soul_structure()
        self.assertTrue(ok, f"Expected PASS: non-executor jishi_review.md exempt from timeout; got: {msg}")


# ---------------------------------------------------------------------------
# 3. TestRule4WorkflowPushForReview
# ---------------------------------------------------------------------------

class TestRule4WorkflowPushForReview(unittest.TestCase):
    """Rule 4: executor WORKFLOW docs must contain 'push-for-review'."""

    _EXECUTOR_FILES = chaoting_lint.EXECUTOR_WORKFLOW_FILES

    def _make_docs_dir(self, tmp, include_push_for_review=True):
        """Write all executor WORKFLOW docs to tmp dir."""
        for filename in self._EXECUTOR_FILES:
            content = "# Workflow\n\n## push-for-review\nRun command.\n" if include_push_for_review else "# Workflow\n\nNo submission step.\n"
            _write(os.path.join(tmp, filename), content)

    def test_all_workflows_have_push_for_review(self):
        """All executor WORKFLOW docs with 'push-for-review' → Rule 4 PASS."""
        with tempfile.TemporaryDirectory() as tmp:
            self._make_docs_dir(tmp, include_push_for_review=True)
            with patch.object(chaoting_lint, "DOCS_DIR", tmp):
                ok, msg = chaoting_lint.rule4_workflow_push_for_review()
        self.assertTrue(ok, f"Expected PASS, got: {msg}")

    def test_workflow_missing_push_for_review_fails(self):
        """A WORKFLOW doc missing 'push-for-review' → Rule 4 FAIL."""
        with tempfile.TemporaryDirectory() as tmp:
            self._make_docs_dir(tmp, include_push_for_review=True)
            # Remove push-for-review from one file
            target = os.path.join(tmp, "WORKFLOW-bingbu.md")
            _write(target, "# Workflow\n\nNo submission step.\n")
            with patch.object(chaoting_lint, "DOCS_DIR", tmp):
                ok, msg = chaoting_lint.rule4_workflow_push_for_review()
        self.assertFalse(ok, "Expected FAIL when bingbu workflow lacks push-for-review")
        self.assertIn("WORKFLOW-bingbu.md", msg)

    def test_missing_workflow_file_fails(self):
        """A missing WORKFLOW file → Rule 4 FAIL (file not found)."""
        with tempfile.TemporaryDirectory() as tmp:
            # Only write some workflows, omit one
            for filename in self._EXECUTOR_FILES[:-1]:
                _write(os.path.join(tmp, filename), "push-for-review\n")
            with patch.object(chaoting_lint, "DOCS_DIR", tmp):
                ok, msg = chaoting_lint.rule4_workflow_push_for_review()
        self.assertFalse(ok, "Expected FAIL when a WORKFLOW file is missing")
        self.assertIn("not found", msg)


# ---------------------------------------------------------------------------
# 4. TestDriftCheck2IndexConsistency
# ---------------------------------------------------------------------------

class TestDriftCheck2IndexConsistency(unittest.TestCase):
    """Drift check 2: INDEX.md consistency — missing-from-index and orphan entries."""

    def _setup_docs(self, tmp):
        """Create a docs/ layout with:
        - ARCHITECTURE.md   → in INDEX.md AND on disk (clean)
        - GHOST.md          → in INDEX.md but NOT on disk (orphan index entry)
        - ORPHAN.md         → on disk but NOT in INDEX.md (missing from index)
        """
        index_content = textwrap.dedent("""\
            # INDEX

            | Doc | Path | Description |
            |-----|------|-------------|
            | ARCHITECTURE.md | docs/ARCHITECTURE.md | System overview |
            | GHOST.md | docs/GHOST.md | Haunted doc |
        """)
        _write(os.path.join(tmp, "INDEX.md"), index_content)
        _write(os.path.join(tmp, "ARCHITECTURE.md"), "# Architecture\n")
        _write(os.path.join(tmp, "ORPHAN.md"), "# Orphan\n")

    def test_missing_from_index_detected(self):
        """ORPHAN.md on disk but not in INDEX.md → 'MISSING FROM INDEX' in issues."""
        with tempfile.TemporaryDirectory() as tmp:
            self._setup_docs(tmp)
            with patch.object(chaoting_drift, "DOCS_DIR", tmp):
                issues, _ = chaoting_drift.check2_index_consistency()
        missing_msgs = [i for i in issues if "MISSING FROM INDEX" in i]
        self.assertTrue(
            any("ORPHAN.md" in m for m in missing_msgs),
            f"Expected ORPHAN.md in MISSING FROM INDEX issues; got: {issues}",
        )

    def test_index_entry_without_file_detected(self):
        """GHOST.md in INDEX.md but not on disk → 'INDEX ENTRY WITHOUT FILE' in issues."""
        with tempfile.TemporaryDirectory() as tmp:
            self._setup_docs(tmp)
            with patch.object(chaoting_drift, "DOCS_DIR", tmp):
                issues, _ = chaoting_drift.check2_index_consistency()
        ghost_msgs = [i for i in issues if "INDEX ENTRY WITHOUT FILE" in i]
        self.assertTrue(
            any("GHOST.md" in m for m in ghost_msgs),
            f"Expected GHOST.md in INDEX ENTRY WITHOUT FILE issues; got: {issues}",
        )

    def test_clean_file_not_in_issues(self):
        """ARCHITECTURE.md in both index and disk → should NOT appear in issues."""
        with tempfile.TemporaryDirectory() as tmp:
            self._setup_docs(tmp)
            with patch.object(chaoting_drift, "DOCS_DIR", tmp):
                issues, _ = chaoting_drift.check2_index_consistency()
        arch_issues = [i for i in issues if "ARCHITECTURE.md" in i]
        self.assertEqual(
            arch_issues,
            [],
            f"ARCHITECTURE.md should not appear in issues; got: {arch_issues}",
        )

    def test_no_index_file_returns_error(self):
        """Missing INDEX.md → error message returned, not a crash."""
        with tempfile.TemporaryDirectory() as tmp:
            # No INDEX.md, just a regular doc
            _write(os.path.join(tmp, "README.md"), "# Readme\n")
            with patch.object(chaoting_drift, "DOCS_DIR", tmp):
                issues, _ = chaoting_drift.check2_index_consistency()
        self.assertTrue(
            any("ERROR" in i or "not found" in i for i in issues),
            f"Expected an error about missing INDEX.md; got: {issues}",
        )


if __name__ == "__main__":
    unittest.main()
