#!/usr/bin/env python3
"""
teams.py — Chaoting Agent Teams V0.4

提供高层抽象组件，简化 Agent Teams 工作流编排：

- IterationCoordinator  — 封装模式 B（顺序迭代）的重复逻辑
- ParallelCodeReview    — 模式 A（并行）工作流模板
- IterativeCodeReview   — 模式 B（迭代）工作流模板
- generate_lead_prompt  — 自动生成 Lead agent 系统提示
- TaskDAG               — 有向无环图任务依赖管理

依赖：sentinel.py（同目录）
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import sys as _sys
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from sentinel import (
    SentinelWatcher,
    write_sentinel,
    SENTINEL_DONE,
    SENTINEL_FAILED,
    SENTINEL_TIMEOUT,
    SENTINEL_RUNNING,
    DEFAULT_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
)

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────

DEFAULT_MAX_ROUNDS = 3
DEFAULT_QUALITY_THRESHOLD = 12  # 满分 15 的 80%


# ──────────────────────────────────────────────────────
# IterationCoordinator — 迭代协调器
# ──────────────────────────────────────────────────────

class IterationCoordinator:
    """
    迭代协调器：封装模式 B（Coder → Reviewer → Loop）的重复逻辑。

    使用示例：
        coord = IterationCoordinator(
            zouzhe_id="ZZ-20260310-XXX",
            chaoting_dir=CHAOTING_DIR,
            max_rounds=3,
            converge_fn=lambda s: s.get("total", 0) >= 12,
        )

        while not coord.converged():
            # 构建本轮 coder 指令（自动包含上轮反馈）
            instructions = coord.build_coder_instructions(base_task, feedback_file)
            coder_sentinel = coord.next_coder_id()
            # ... 启动 coder teammate ...

            coord.wait_coder()

            reviewer_sentinel = coord.next_reviewer_id()
            # ... 启动 reviewer teammate ...
            coord.wait_reviewer()

            # 从 reviewer 输出提取 score（应用程序层逻辑）
            score = parse_score(coord.last_reviewer_output())
            coord.record_score(score)

        print("Converged at round", coord.current_round)
        print("Score history:", coord.score_history)
    """

    def __init__(
        self,
        zouzhe_id: str,
        chaoting_dir: Optional[str] = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        converge_fn: Optional[Callable[[Dict], bool]] = None,
        timeout_per_round: int = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        self.zouzhe_id = zouzhe_id
        self.chaoting_dir = chaoting_dir or os.environ.get(
            "CHAOTING_DIR",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.max_rounds = max_rounds
        self.converge_fn = converge_fn or (
            lambda s: s.get("total", 0) >= DEFAULT_QUALITY_THRESHOLD
        )
        self.timeout_per_round = timeout_per_round
        self.poll_interval = poll_interval

        self._round: int = 0
        self._converged: bool = False
        self._score_history: List[Dict] = []
        self._last_feedback_file: Optional[str] = None
        self._watchers: Dict[str, SentinelWatcher] = {}
        self._start_time: float = time.time()

    # ── 状态查询 ──

    @property
    def current_round(self) -> int:
        """当前轮次（0 = 未开始，1 = 第一轮，...）"""
        return self._round

    @property
    def score_history(self) -> List[Dict]:
        """每轮的分数记录：[{"round": 1, "scores": {...}, "approved": False}, ...]"""
        return list(self._score_history)

    def converged(self) -> bool:
        """是否已达到收敛条件或超过最大轮次。"""
        return self._converged

    # ── 轮次 ID ──

    def coder_id(self, round_num: Optional[int] = None) -> str:
        """返回指定轮次的 coder teammate ID。"""
        r = round_num or self._round
        return f"coder-r{r}"

    def reviewer_id(self, round_num: Optional[int] = None) -> str:
        """返回指定轮次的 reviewer teammate ID。"""
        r = round_num or self._round
        return f"reviewer-r{r}"

    def coder_output_file(self, round_num: Optional[int] = None) -> str:
        """返回当前轮次 coder 的输出文件路径。"""
        r = round_num or self._round
        return f"/tmp/{self.zouzhe_id}-code-v{r}.txt"

    def reviewer_output_file(self, round_num: Optional[int] = None) -> str:
        """返回当前轮次 reviewer 的输出文件路径。"""
        r = round_num or self._round
        return f"/tmp/{self.zouzhe_id}-review-v{r}.txt"

    # ── 轮次生命周期 ──

    def start_round(self) -> int:
        """开始新一轮，返回轮次编号。"""
        if self._converged:
            raise RuntimeError("IterationCoordinator: already converged, cannot start new round")
        self._round += 1
        log.info("[Round %d] Starting (max_rounds=%d)", self._round, self.max_rounds)
        return self._round

    def wait_coder(self, timeout: Optional[int] = None) -> Dict:
        """等待当前轮次的 coder 完成。Returns sentinel data."""
        cid = self.coder_id()
        watcher = SentinelWatcher(self.zouzhe_id, self.chaoting_dir)
        watcher.register([cid])
        result = watcher.wait_all(
            timeout=timeout or self.timeout_per_round,
            poll_interval=self.poll_interval,
        )
        self._watchers[cid] = watcher
        if result["status"] != "complete":
            raise TimeoutError(f"Round {self._round}: coder timed out ({cid})")
        log.info("[Round %d] coder done (%s)", self._round, cid)
        return result["results"].get(cid, {})

    def wait_reviewer(self, timeout: Optional[int] = None) -> Dict:
        """等待当前轮次的 reviewer 完成。Returns sentinel data."""
        rid = self.reviewer_id()
        watcher = SentinelWatcher(self.zouzhe_id, self.chaoting_dir)
        watcher.register([rid])
        result = watcher.wait_all(
            timeout=timeout or self.timeout_per_round,
            poll_interval=self.poll_interval,
        )
        self._watchers[rid] = watcher
        if result["status"] != "complete":
            raise TimeoutError(f"Round {self._round}: reviewer timed out ({rid})")
        data = result["results"].get(rid, {})
        self._last_feedback_file = data.get("output")
        log.info("[Round %d] reviewer done (%s)", self._round, rid)
        return data

    def last_reviewer_output(self) -> Optional[str]:
        """返回最后一轮 reviewer 的输出文件路径。"""
        return self._last_feedback_file

    def record_score(self, scores: Dict, approved: Optional[bool] = None) -> None:
        """
        记录本轮评分，检查是否收敛。

        Args:
            scores: 评分 dict，必须包含 "total" 键（或 converge_fn 能处理的结构）
            approved: 是否通过审查（可选）
        """
        entry = {
            "round": self._round,
            "scores": scores,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if approved is not None:
            entry["approved"] = approved
        self._score_history.append(entry)

        if self.converge_fn(scores):
            self._converged = True
            log.info(
                "[Round %d] Converged! scores=%s", self._round, scores
            )
        elif self._round >= self.max_rounds:
            self._converged = True
            log.warning(
                "[Round %d] Max rounds reached (%d), stopping", self._round, self.max_rounds
            )
        else:
            log.info(
                "[Round %d] Not yet converged, scores=%s", self._round, scores
            )

    def build_coder_instructions(
        self,
        base_task: str,
        output_file: Optional[str] = None,
        sentinel_cmd_prefix: Optional[str] = None,
    ) -> str:
        """
        构建当前轮次的 coder 指令，自动包含上轮反馈（如有）。

        Args:
            base_task: 基础任务描述
            output_file: 覆盖默认输出文件路径
            sentinel_cmd_prefix: 覆盖默认哨兵写入命令前缀

        Returns:
            完整的 coder 指令字符串（直接传给 Task 工具）
        """
        out = output_file or self.coder_output_file()
        cid = self.coder_id()
        chaoting_dir = self.chaoting_dir
        prefix = sentinel_cmd_prefix or (
            f"CHAOTING_DIR={chaoting_dir} "
            f"{os.path.join(chaoting_dir, 'src', 'chaoting')} teams sentinel-write "
            f"{self.zouzhe_id} {cid} --status done --output {out}"
        )

        if self._round == 1 or not self._last_feedback_file:
            # 第一轮：只有基础任务
            return (
                f"{base_task}\n\n"
                f"Write your output to: {out}\n"
                f"When done, run: {prefix}"
            )
        else:
            # 后续轮：包含上轮反馈
            feedback_ref = self._last_feedback_file
            prev_code = self.coder_output_file(self._round - 1)
            return (
                f"REVISION ROUND {self._round}:\n\n"
                f"Original task: {base_task}\n\n"
                f"Previous code (Round {self._round - 1}): {prev_code}\n"
                f"Reviewer feedback (Round {self._round - 1}): {feedback_ref}\n\n"
                f"Read both files, apply ALL improvements listed in the feedback.\n"
                f"Write improved version to: {out}\n"
                f"When done, run: {prefix}"
            )

    def get_metrics(self) -> Dict[str, Any]:
        """返回迭代过程的性能指标。"""
        elapsed = time.time() - self._start_time
        quality_progression = [
            entry["scores"].get("total", 0) for entry in self._score_history
        ]
        return {
            "zouzhe_id": self.zouzhe_id,
            "total_time_s": round(elapsed, 1),
            "rounds_completed": self._round,
            "max_rounds": self.max_rounds,
            "converged": self._converged,
            "quality_progression": quality_progression,
            "score_history": self._score_history,
            "final_score": quality_progression[-1] if quality_progression else None,
            "improvement": (
                quality_progression[-1] - quality_progression[0]
                if len(quality_progression) >= 2 else 0
            ),
        }


# ──────────────────────────────────────────────────────
# 工作流模板
# ──────────────────────────────────────────────────────

class ParallelCodeReview:
    """
    模式 A（并行）工作流模板。

    封装「Coder 和 Reviewer 同时启动，Reviewer 等待 Coder 输出文件」的模式。

    使用示例：
        workflow = ParallelCodeReview("ZZ-20260310-XXX", CHAOTING_DIR)
        prompt = workflow.generate_lead_prompt(
            coder_task="Write get_stats() function...",
            reviewer_criteria="Check: SQL injection, error handling, code quality",
        )
        # 将 prompt 传给 claude --print
    """

    def __init__(self, zouzhe_id: str, chaoting_dir: Optional[str] = None):
        self.zouzhe_id = zouzhe_id
        self.chaoting_dir = chaoting_dir or os.environ.get(
            "CHAOTING_DIR",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self._watcher: Optional[SentinelWatcher] = None

    @property
    def coder_output(self) -> str:
        return f"/tmp/{self.zouzhe_id}-parallel-code.txt"

    @property
    def reviewer_output(self) -> str:
        return f"/tmp/{self.zouzhe_id}-parallel-review.txt"

    def _sentinel_cmd(self, name: str, out: str) -> str:
        chaoting_bin = os.path.join(self.chaoting_dir, "src", "chaoting")
        return (
            f"CHAOTING_DIR={self.chaoting_dir} {chaoting_bin} teams sentinel-write "
            f"{self.zouzhe_id} {name} --status done --output {out}"
        )

    def generate_lead_prompt(
        self,
        coder_task: str,
        reviewer_criteria: str,
        team_name: Optional[str] = None,
    ) -> str:
        """生成模式 A 的 Lead 系统提示（可直接传给 claude --print）。"""
        tname = team_name or f"{self.zouzhe_id}-parallel"
        sentinel_dir = os.path.join(self.chaoting_dir, "sentinels", self.zouzhe_id)
        return f"""You are the lead agent coordinating a PARALLEL Coder+Reviewer workflow.

TASK ID: {self.zouzhe_id}
CHAOTING_DIR: {self.chaoting_dir}
SENTINEL DIR: {sentinel_dir}

WORKFLOW — MODE A: PARALLEL

1. TeamCreate("{tname}")

2. Spawn BOTH teammates simultaneously (parallel Task calls):

   Task "coder":
   "{coder_task}
   Write output to: {self.coder_output}
   When done, run: {self._sentinel_cmd('coder', self.coder_output)}"

   Task "reviewer" (poll for coder output, start reviewing when it appears):
   "Wait until {self.coder_output} exists (check with: ls {self.coder_output}).
   Once it exists, review it for:
   {reviewer_criteria}
   Write review to: {self.reviewer_output}
   When done, run: {self._sentinel_cmd('reviewer', self.reviewer_output)}"

3. Wait for BOTH sentinel files to exist:
   {sentinel_dir}/coder.done
   {sentinel_dir}/reviewer.done
   (Check every 5s with: ls {sentinel_dir}/)

4. Read both output files and write a brief integration summary.

5. Send shutdown_request to all teammates, then TeamDelete("{tname}").
"""

    def wait(self, timeout: int = DEFAULT_TIMEOUT) -> Dict:
        """等待并行工作流完成，返回两个哨兵的数据。"""
        self._watcher = SentinelWatcher(self.zouzhe_id, self.chaoting_dir)
        self._watcher.register(["coder", "reviewer"])
        return self._watcher.wait_all(timeout=timeout)


class IterativeCodeReview:
    """
    模式 B（顺序迭代）工作流模板。

    封装「Coder → Reviewer → Loop」的编排逻辑，
    并提供 Lead 系统提示生成器。

    使用示例：
        workflow = IterativeCodeReview(
            zouzhe_id="ZZ-20260310-XXX",
            chaoting_dir=CHAOTING_DIR,
            max_rounds=3,
            quality_threshold=12,
        )
        prompt = workflow.generate_lead_prompt(
            base_task="Implement get_stats() ...",
            review_criteria="Score: error_handling, edge_cases, code_quality (each 1-5)",
        )
    """

    def __init__(
        self,
        zouzhe_id: str,
        chaoting_dir: Optional[str] = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        quality_threshold: int = DEFAULT_QUALITY_THRESHOLD,
    ):
        self.zouzhe_id = zouzhe_id
        self.chaoting_dir = chaoting_dir or os.environ.get(
            "CHAOTING_DIR",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.max_rounds = max_rounds
        self.quality_threshold = quality_threshold

    def _sentinel_cmd(self, name: str, out: str) -> str:
        chaoting_bin = os.path.join(self.chaoting_dir, "src", "chaoting")
        return (
            f"CHAOTING_DIR={self.chaoting_dir} {chaoting_bin} teams sentinel-write "
            f"{self.zouzhe_id} {name} --status done --output {out}"
        )

    def code_file(self, r: int) -> str:
        return f"/tmp/{self.zouzhe_id}-code-v{r}.txt"

    def review_file(self, r: int) -> str:
        return f"/tmp/{self.zouzhe_id}-review-v{r}.txt"

    def generate_lead_prompt(
        self,
        base_task: str,
        review_criteria: str,
        team_name: Optional[str] = None,
    ) -> str:
        """生成模式 B 的 Lead 系统提示（可直接传给 claude --print）。"""
        tname = team_name or f"{self.zouzhe_id}-iterative"
        sentinel_dir = os.path.join(self.chaoting_dir, "sentinels", self.zouzhe_id)
        # Build per-round template (show rounds 1-2 explicitly)
        round_prompts = []
        for r in range(1, self.max_rounds + 1):
            prev_ref = ""
            if r > 1:
                prev_ref = (
                    f"Previous code: {self.code_file(r-1)}\n"
                    f"Reviewer feedback: {self.review_file(r-1)}\n"
                    f"Read both files. Apply ALL improvements listed in the review."
                )
            round_prompts.append(
                f"Round {r}:\n"
                f"  Coder task \"coder-r{r}\":\n"
                f"  \"{('Apply improvements from Round ' + str(r-1) + ' feedback. ') if r > 1 else ''}"
                f"{base_task}\n"
                f"  {prev_ref}\n"
                f"  Write to: {self.code_file(r)}\n"
                f"  Sentinel: {self._sentinel_cmd(f'coder-r{r}', self.code_file(r))}\"\n\n"
                f"  Wait for sentinel: {sentinel_dir}/coder-r{r}.done\n\n"
                f"  Reviewer task \"reviewer-r{r}\":\n"
                f"  \"Read {self.code_file(r)}. {review_criteria}\n"
                f"  Output format: SCORES: dim1=X dim2=X TOTAL=X/15 VERDICT: APPROVE|NEEDS_REVISION\n"
                f"  Write to: {self.review_file(r)}\n"
                f"  Sentinel: {self._sentinel_cmd(f'reviewer-r{r}', self.review_file(r))}\"\n\n"
                f"  Wait for sentinel: {sentinel_dir}/reviewer-r{r}.done\n\n"
                f"  Read review file. IF VERDICT==APPROVE OR round=={r}>={self.max_rounds}: STOP."
            )

        return f"""You are the lead agent coordinating an ITERATIVE Coder+Reviewer workflow.

TASK ID: {self.zouzhe_id}
CHAOTING_DIR: {self.chaoting_dir}
SENTINEL DIR: {sentinel_dir}
MAX ROUNDS: {self.max_rounds}
QUALITY THRESHOLD: TOTAL >= {self.quality_threshold}/15

WORKFLOW — MODE B: SEQUENTIAL ITERATION

Create team "{tname}" at start. TeamDelete at end.

{chr(10).join(round_prompts)}

FINALIZE:
- Write summary to /tmp/{self.zouzhe_id}-iteration-summary.txt including:
  score progression, rounds to convergence, improvements applied
- Shutdown all teammates, TeamDelete("{tname}")
"""


# ──────────────────────────────────────────────────────
# Lead prompt 生成工具函数
# ──────────────────────────────────────────────────────

def generate_lead_prompt(
    workflow: str,
    zouzhe_id: str,
    base_task: str,
    review_criteria: str = "Check: correctness, error handling, code quality (each 1-5)",
    chaoting_dir: Optional[str] = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    quality_threshold: int = DEFAULT_QUALITY_THRESHOLD,
    team_name: Optional[str] = None,
) -> str:
    """
    根据工作流类型自动生成 Lead agent 系统提示。

    Args:
        workflow: "parallel" (模式 A) 或 "iterative" (模式 B)
        zouzhe_id: 奏折 ID
        base_task: 基础任务描述
        review_criteria: 审查标准
        chaoting_dir: CHAOTING_DIR 路径
        max_rounds: 最大迭代轮次（仅模式 B）
        quality_threshold: 收敛质量阈值（仅模式 B，满分 15）
        team_name: 可选自定义团队名

    Returns:
        完整的 Lead 系统提示字符串
    """
    if workflow == "parallel":
        w = ParallelCodeReview(zouzhe_id, chaoting_dir)
        return w.generate_lead_prompt(base_task, review_criteria, team_name)
    elif workflow == "iterative":
        w = IterativeCodeReview(
            zouzhe_id, chaoting_dir,
            max_rounds=max_rounds,
            quality_threshold=quality_threshold,
        )
        return w.generate_lead_prompt(base_task, review_criteria, team_name)
    else:
        raise ValueError(f"Unknown workflow: {workflow!r}. Use 'parallel' or 'iterative'.")


# ──────────────────────────────────────────────────────
# TaskDAG — 有向无环图任务依赖管理
# ──────────────────────────────────────────────────────

class _DAGNode:
    def __init__(self, name: str, spec: str, depends_on: List[str]):
        self.name = name
        self.spec = spec
        self.depends_on = depends_on
        self.status: str = "pending"   # pending → running → done/failed
        self.output: Optional[str] = None


class TaskDAG:
    """
    有向无环图任务依赖管理。

    允许声明 teammate 任务的依赖关系，自动按拓扑顺序执行。

    使用示例：
        dag = TaskDAG("ZZ-20260310-XXX", CHAOTING_DIR)
        dag.add_task("coder",    spec="Write code...",        depends_on=[])
        dag.add_task("tester",   spec="Write tests...",       depends_on=["coder"])
        dag.add_task("reviewer", spec="Review code+tests...", depends_on=["coder", "tester"])
        dag.add_task("docs",     spec="Write docs...",        depends_on=["coder"])

        # 生成 Lead 提示（按拓扑顺序编排任务）
        prompt = dag.generate_lead_prompt()
    """

    def __init__(self, zouzhe_id: str, chaoting_dir: Optional[str] = None):
        self.zouzhe_id = zouzhe_id
        self.chaoting_dir = chaoting_dir or os.environ.get(
            "CHAOTING_DIR",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self._nodes: Dict[str, _DAGNode] = {}

    def add_task(
        self,
        name: str,
        spec: str,
        depends_on: Optional[List[str]] = None,
    ) -> "TaskDAG":
        """
        添加 DAG 节点。

        Args:
            name: Teammate 名称（唯一标识）
            spec: 任务描述字符串（传给 Task 工具）
            depends_on: 依赖的其他 teammate 名称列表

        Returns:
            self（支持链式调用）
        """
        self._nodes[name] = _DAGNode(name, spec, depends_on or [])
        return self

    def topological_sort(self) -> List[List[str]]:
        """
        拓扑排序，返回按层级分组的任务名称列表。
        同一层级的任务可以并行执行。

        Returns:
            [[layer0_tasks], [layer1_tasks], ...]

        Raises:
            ValueError: 存在循环依赖时
        """
        # Kahn's algorithm
        in_degree: Dict[str, int] = {n: 0 for n in self._nodes}
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep not in self._nodes:
                    raise ValueError(f"Unknown dependency: {dep!r} for task {node.name!r}")
                in_degree[node.name] += 1

        queue: List[str] = [n for n, d in in_degree.items() if d == 0]
        layers: List[List[str]] = []

        while queue:
            layers.append(sorted(queue))  # sort for determinism
            next_queue: List[str] = []
            for n in queue:
                for other in self._nodes:
                    if n in self._nodes[other].depends_on:
                        in_degree[other] -= 1
                        if in_degree[other] == 0:
                            next_queue.append(other)
            queue = next_queue

        if sum(len(l) for l in layers) != len(self._nodes):
            raise ValueError("Circular dependency detected in TaskDAG")

        return layers

    def generate_lead_prompt(self, team_name: Optional[str] = None) -> str:
        """
        生成按 DAG 依赖顺序编排的 Lead 系统提示。

        并行层中的任务同时启动，依赖层等待前层完成再启动。
        """
        layers = self.topological_sort()
        tname = team_name or f"{self.zouzhe_id}-dag"
        sentinel_dir = os.path.join(self.chaoting_dir, "sentinels", self.zouzhe_id)
        chaoting_bin = os.path.join(self.chaoting_dir, "src", "chaoting")

        def sentinel_cmd(name: str, out: str) -> str:
            return (
                f"CHAOTING_DIR={self.chaoting_dir} {chaoting_bin} teams sentinel-write "
                f"{self.zouzhe_id} {name} --status done --output {out}"
            )

        step_lines = []
        for layer_idx, layer in enumerate(layers):
            parallel_note = "simultaneously (parallel)" if len(layer) > 1 else "sequentially"
            step_lines.append(
                f"Layer {layer_idx + 1} — spawn {parallel_note}: {', '.join(layer)}"
            )
            for name in layer:
                node = self._nodes[name]
                out = f"/tmp/{self.zouzhe_id}-{name}.txt"
                step_lines.append(
                    f'  Task "{name}":\n'
                    f"  \"{node.spec}\n"
                    f"  Write to: {out}\n"
                    f"  When done: {sentinel_cmd(name, out)}\""
                )
            step_lines.append(
                f"  Wait for ALL sentinels in layer {layer_idx + 1}: "
                + ", ".join(f"{sentinel_dir}/{n}.done" for n in layer)
            )
            step_lines.append("")

        return f"""You are the lead agent coordinating a DAG-based workflow.

TASK ID: {self.zouzhe_id}
CHAOTING_DIR: {self.chaoting_dir}
SENTINEL DIR: {sentinel_dir}
TEAM: {tname}

DAG EXECUTION PLAN:

1. TeamCreate("{tname}")

{chr(10).join(step_lines)}

FINALIZE:
- Read all output files and write integration summary to /tmp/{self.zouzhe_id}-dag-summary.txt
- Shutdown all teammates, TeamDelete("{tname}")
"""
