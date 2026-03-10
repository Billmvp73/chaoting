#!/usr/bin/env python3
"""
test_teams_v04.py — Chaoting Agent Teams V0.4 单元和集成测试

测试覆盖：
- SentinelWatcher V0.4 扩展（progress、metadata、状态机）
- IterationCoordinator 收敛逻辑
- TaskDAG 拓扑排序
- generate_lead_prompt 生成结果
- CLI 新命令（metrics、generate-prompt）

运行：
    cd /home/tetter/self-project/chaoting
    python3 src/test_teams_v04.py
"""

import json
import os
import sys
import tempfile
import unittest

# 确保 src/ 在 path 上
_src = os.path.dirname(os.path.abspath(__file__))
if _src not in sys.path:
    sys.path.insert(0, _src)

from sentinel import (
    SentinelWatcher,
    write_sentinel,
    read_sentinel,
    SENTINEL_DONE,
    SENTINEL_FAILED,
    SENTINEL_RUNNING,
    SENTINEL_TIMEOUT,
)
from teams import (
    IterationCoordinator,
    ParallelCodeReview,
    IterativeCodeReview,
    TaskDAG,
    generate_lead_prompt,
)


# ──────────────────────────────────────────────────────
# Sentinel V0.4 Tests
# ──────────────────────────────────────────────────────

class TestSentinelV04(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.zid = "ZZ-TEST-V04"

    def test_write_running_progress(self):
        """write_running 写入 running 状态 + progress 字段"""
        w = SentinelWatcher(self.zid, self.tmpdir)
        w.register(["coder"])
        w.write_running("coder", progress=0.5, message="halfway")
        data = read_sentinel(self.tmpdir, self.zid, "coder")
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], SENTINEL_RUNNING)
        self.assertAlmostEqual(data["metadata"]["progress"], 0.5)
        self.assertEqual(data["metadata"]["message"], "halfway")

    def test_write_done_with_iteration_metadata(self):
        """write_done 支持 round/score/approved metadata"""
        w = SentinelWatcher(self.zid, self.tmpdir)
        w.register(["reviewer"])
        w.write_done(
            "reviewer",
            output="/tmp/review.txt",
            round_num=2,
            score=13,
            approved=True,
        )
        data = read_sentinel(self.tmpdir, self.zid, "reviewer")
        self.assertEqual(data["status"], SENTINEL_DONE)
        self.assertEqual(data["metadata"]["round"], 2)
        self.assertEqual(data["metadata"]["score"], 13)
        self.assertTrue(data["metadata"]["approved"])

    def test_get_metrics(self):
        """get_metrics 返回正确的统计数据"""
        w = SentinelWatcher(self.zid, self.tmpdir)
        w.register(["a", "b", "c"])

        write_sentinel(self.tmpdir, self.zid, "a", status=SENTINEL_DONE, output="/tmp/a.txt")
        write_sentinel(self.tmpdir, self.zid, "b", status=SENTINEL_FAILED, error="err")
        # c 还是 pending

        m = w.get_metrics()
        self.assertEqual(m["zouzhe_id"], self.zid)
        self.assertEqual(m["total"], 3)
        self.assertEqual(m["done"], 1)
        self.assertEqual(m["failed"], 1)
        self.assertEqual(m["pending"], 1)
        self.assertIn("a", m["outputs"])
        self.assertEqual(m["outputs"]["a"], "/tmp/a.txt")

    def test_get_metrics_with_scores(self):
        """get_metrics 提取 score 和 round 字段"""
        w = SentinelWatcher(self.zid, self.tmpdir)
        w.register(["reviewer-r1", "reviewer-r2"])

        write_sentinel(self.tmpdir, self.zid, "reviewer-r1",
                       status=SENTINEL_DONE, metadata={"round": 1, "score": 5})
        write_sentinel(self.tmpdir, self.zid, "reviewer-r2",
                       status=SENTINEL_DONE, metadata={"round": 2, "score": 13})

        m = w.get_metrics()
        self.assertEqual(m["scores"]["reviewer-r1"], 5)
        self.assertEqual(m["scores"]["reviewer-r2"], 13)
        self.assertEqual(m["rounds"]["reviewer-r1"], 1)
        self.assertEqual(m["rounds"]["reviewer-r2"], 2)

    def test_progress_summary_string(self):
        """progress_summary 返回人类可读字符串"""
        w = SentinelWatcher(self.zid, self.tmpdir)
        w.register(["coder", "reviewer"])

        write_sentinel(self.tmpdir, self.zid, "coder", status=SENTINEL_DONE)
        write_sentinel(self.tmpdir, self.zid, "reviewer",
                       status=SENTINEL_RUNNING, metadata={"progress": 0.7, "message": "reviewing"})

        summary = w.progress_summary()
        self.assertIn("✅", summary)   # coder done
        self.assertIn("🔄", summary)   # reviewer running
        self.assertIn("70%", summary)

    def test_progress_clamp(self):
        """write_running progress 值被限制到 0.0-1.0"""
        w = SentinelWatcher(self.zid, self.tmpdir)
        w.register(["x"])
        w.write_running("x", progress=1.5)  # should be clamped to 1.0
        data = read_sentinel(self.tmpdir, self.zid, "x")
        self.assertAlmostEqual(data["metadata"]["progress"], 1.0)


# ──────────────────────────────────────────────────────
# IterationCoordinator Tests
# ──────────────────────────────────────────────────────

class TestIterationCoordinator(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.zid = "ZZ-TEST-COORD"

    def _make_coord(self, max_rounds=3, threshold=12):
        return IterationCoordinator(
            zouzhe_id=self.zid,
            chaoting_dir=self.tmpdir,
            max_rounds=max_rounds,
            converge_fn=lambda s: s.get("total", 0) >= threshold,
            timeout_per_round=5,   # short timeout for tests
            poll_interval=0.05,
        )

    def test_initial_state(self):
        coord = self._make_coord()
        self.assertEqual(coord.current_round, 0)
        self.assertFalse(coord.converged())
        self.assertEqual(coord.score_history, [])

    def test_converge_on_threshold(self):
        coord = self._make_coord(threshold=12)
        coord.start_round()
        coord.record_score({"total": 5})        # below threshold
        self.assertFalse(coord.converged())

        coord.start_round()
        coord.record_score({"total": 13})       # above threshold → converge
        self.assertTrue(coord.converged())
        self.assertEqual(coord.current_round, 2)

    def test_converge_on_max_rounds(self):
        coord = self._make_coord(max_rounds=2, threshold=15)
        coord.start_round()
        coord.record_score({"total": 5})
        self.assertFalse(coord.converged())

        coord.start_round()
        coord.record_score({"total": 8})       # still below but max_rounds=2
        self.assertTrue(coord.converged())

    def test_score_history(self):
        coord = self._make_coord()
        coord.start_round()
        coord.record_score({"total": 5, "error_handling": 1})
        coord.start_round()
        coord.record_score({"total": 13, "error_handling": 4})

        history = coord.score_history
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["round"], 1)
        self.assertEqual(history[0]["scores"]["total"], 5)
        self.assertEqual(history[1]["round"], 2)
        self.assertEqual(history[1]["scores"]["total"], 13)

    def test_build_coder_instructions_round1(self):
        coord = self._make_coord()
        coord._round = 1
        instructions = coord.build_coder_instructions("Implement get_stats()")
        self.assertIn("Implement get_stats()", instructions)
        self.assertNotIn("REVISION ROUND", instructions)
        self.assertIn("coder-r1", instructions)

    def test_build_coder_instructions_round2(self):
        coord = self._make_coord()
        coord._round = 2
        coord._last_feedback_file = "/tmp/review-v1.txt"
        instructions = coord.build_coder_instructions("Implement get_stats()")
        self.assertIn("REVISION ROUND 2", instructions)
        self.assertIn("review-v1.txt", instructions)
        self.assertIn("coder-r2", instructions)

    def test_round_ids(self):
        coord = self._make_coord()
        coord._round = 3
        self.assertEqual(coord.coder_id(), "coder-r3")
        self.assertEqual(coord.reviewer_id(), "reviewer-r3")
        self.assertIn("v3", coord.coder_output_file())
        self.assertIn("v3", coord.reviewer_output_file())

    def test_get_metrics(self):
        coord = self._make_coord()
        coord.start_round()
        coord.record_score({"total": 5})
        coord.start_round()
        coord.record_score({"total": 13})

        m = coord.get_metrics()
        self.assertEqual(m["rounds_completed"], 2)
        self.assertEqual(m["quality_progression"], [5, 13])
        self.assertEqual(m["improvement"], 8)
        self.assertTrue(m["converged"])
        self.assertEqual(m["final_score"], 13)

    def test_cannot_start_round_after_converge(self):
        coord = self._make_coord()
        coord.start_round()
        coord.record_score({"total": 15})
        self.assertTrue(coord.converged())
        with self.assertRaises(RuntimeError):
            coord.start_round()

    def test_wait_coder_with_prewritten_sentinel(self):
        """wait_coder 应快速返回如果哨兵已存在"""
        coord = self._make_coord()
        coord.start_round()
        # 预先写入哨兵
        write_sentinel(self.tmpdir, self.zid, "coder-r1",
                       status=SENTINEL_DONE, output="/tmp/code.txt")
        data = coord.wait_coder()
        self.assertEqual(data.get("output"), "/tmp/code.txt")


# ──────────────────────────────────────────────────────
# TaskDAG Tests
# ──────────────────────────────────────────────────────

class TestTaskDAG(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.zid = "ZZ-TEST-DAG"

    def test_topological_sort_linear(self):
        dag = TaskDAG(self.zid, self.tmpdir)
        dag.add_task("a", spec="A")
        dag.add_task("b", spec="B", depends_on=["a"])
        dag.add_task("c", spec="C", depends_on=["b"])

        layers = dag.topological_sort()
        self.assertEqual(layers, [["a"], ["b"], ["c"]])

    def test_topological_sort_parallel(self):
        dag = TaskDAG(self.zid, self.tmpdir)
        dag.add_task("coder", spec="Code")
        dag.add_task("tester", spec="Test", depends_on=["coder"])
        dag.add_task("docs", spec="Docs", depends_on=["coder"])
        dag.add_task("reviewer", spec="Review", depends_on=["coder", "tester"])

        layers = dag.topological_sort()
        self.assertEqual(layers[0], ["coder"])
        # Layer 1: tester and docs in parallel
        self.assertIn("tester", layers[1])
        self.assertIn("docs", layers[1])
        # Layer 2: reviewer after both
        self.assertEqual(layers[2], ["reviewer"])

    def test_topological_sort_cycle(self):
        dag = TaskDAG(self.zid, self.tmpdir)
        dag.add_task("a", spec="A", depends_on=["b"])
        dag.add_task("b", spec="B", depends_on=["a"])
        with self.assertRaises(ValueError):
            dag.topological_sort()

    def test_topological_sort_unknown_dep(self):
        dag = TaskDAG(self.zid, self.tmpdir)
        dag.add_task("a", spec="A", depends_on=["nonexistent"])
        with self.assertRaises(ValueError):
            dag.topological_sort()

    def test_chain_api(self):
        dag = (
            TaskDAG(self.zid, self.tmpdir)
            .add_task("a", spec="A")
            .add_task("b", spec="B", depends_on=["a"])
        )
        self.assertIn("a", dag._nodes)
        self.assertIn("b", dag._nodes)

    def test_generate_lead_prompt_contains_task_specs(self):
        dag = TaskDAG(self.zid, self.tmpdir)
        dag.add_task("coder", spec="Write the stats function")
        dag.add_task("reviewer", spec="Review the code", depends_on=["coder"])

        prompt = dag.generate_lead_prompt()
        self.assertIn("Write the stats function", prompt)
        self.assertIn("Review the code", prompt)
        self.assertIn("Layer 1", prompt)
        self.assertIn("Layer 2", prompt)


# ──────────────────────────────────────────────────────
# WorkflowTemplate Tests
# ──────────────────────────────────────────────────────

class TestWorkflowTemplates(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.zid = "ZZ-TEST-TMPL"

    def test_parallel_prompt_contains_parallel_keyword(self):
        w = ParallelCodeReview(self.zid, self.tmpdir)
        prompt = w.generate_lead_prompt(
            coder_task="Write code",
            reviewer_criteria="Check quality",
        )
        self.assertIn("PARALLEL", prompt)
        self.assertIn("Write code", prompt)
        self.assertIn("Check quality", prompt)
        self.assertIn("sentinel-write", prompt)

    def test_iterative_prompt_contains_rounds(self):
        w = IterativeCodeReview(self.zid, self.tmpdir, max_rounds=2, quality_threshold=10)
        prompt = w.generate_lead_prompt(
            base_task="Write code",
            review_criteria="Check quality",
        )
        self.assertIn("ITERATIVE", prompt)
        self.assertIn("Round 1", prompt)
        self.assertIn("Round 2", prompt)
        self.assertIn("10", prompt)   # quality threshold

    def test_generate_lead_prompt_parallel(self):
        prompt = generate_lead_prompt(
            workflow="parallel",
            zouzhe_id=self.zid,
            base_task="Write code",
            chaoting_dir=self.tmpdir,
        )
        self.assertIn("PARALLEL", prompt)
        self.assertIn(self.zid, prompt)

    def test_generate_lead_prompt_iterative(self):
        prompt = generate_lead_prompt(
            workflow="iterative",
            zouzhe_id=self.zid,
            base_task="Write code",
            chaoting_dir=self.tmpdir,
            max_rounds=3,
        )
        self.assertIn("ITERATIVE", prompt)
        self.assertIn("Round 3", prompt)

    def test_generate_lead_prompt_unknown_workflow(self):
        with self.assertRaises(ValueError):
            generate_lead_prompt(
                workflow="unknown",
                zouzhe_id=self.zid,
                base_task="x",
                chaoting_dir=self.tmpdir,
            )


# ──────────────────────────────────────────────────────
# Integration Test — Full IterationCoordinator flow (mock)
# ──────────────────────────────────────────────────────

class TestIterationCoordinatorIntegration(unittest.TestCase):
    """模拟两轮迭代流程（不启动实际 Agent Teams）"""

    def test_two_round_convergence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            coord = IterationCoordinator(
                zouzhe_id="ZZ-INTEG",
                chaoting_dir=tmpdir,
                max_rounds=3,
                converge_fn=lambda s: s.get("total", 0) >= 12,
                timeout_per_round=5,
                poll_interval=0.05,
            )

            # Round 1: coder 产出低质量代码（score 5）
            r = coord.start_round()
            self.assertEqual(r, 1)
            write_sentinel(tmpdir, "ZZ-INTEG", "coder-r1",
                           status=SENTINEL_DONE, output="/tmp/code-v1.txt")
            coder_data = coord.wait_coder()
            self.assertEqual(coder_data["output"], "/tmp/code-v1.txt")

            write_sentinel(tmpdir, "ZZ-INTEG", "reviewer-r1",
                           status=SENTINEL_DONE, output="/tmp/review-v1.txt",
                           metadata={"round": 1, "score": 5, "approved": False})
            reviewer_data = coord.wait_reviewer()
            coord.record_score({"total": 5}, approved=False)
            self.assertFalse(coord.converged())

            # Round 2: coder 改进后质量达标（score 13）
            r = coord.start_round()
            self.assertEqual(r, 2)
            instructions = coord.build_coder_instructions("Write stats function")
            self.assertIn("REVISION ROUND 2", instructions)

            write_sentinel(tmpdir, "ZZ-INTEG", "coder-r2",
                           status=SENTINEL_DONE, output="/tmp/code-v2.txt")
            coord.wait_coder()

            write_sentinel(tmpdir, "ZZ-INTEG", "reviewer-r2",
                           status=SENTINEL_DONE, output="/tmp/review-v2.txt",
                           metadata={"round": 2, "score": 13, "approved": True})
            coord.wait_reviewer()
            coord.record_score({"total": 13}, approved=True)
            self.assertTrue(coord.converged())

            # 验证指标
            metrics = coord.get_metrics()
            self.assertEqual(metrics["rounds_completed"], 2)
            self.assertEqual(metrics["quality_progression"], [5, 13])
            self.assertEqual(metrics["improvement"], 8)
            self.assertTrue(metrics["converged"])


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
