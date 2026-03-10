#!/usr/bin/env python3
"""
sentinel.py — 文件哨兵模块 (File Sentinel) V0.4

为 Chaoting Agent Teams 并发机制提供基础设施：
- 创建/写入哨兵文件，标记子任务完成状态
- V0.4 新增：Progress 信号（running + progress% + message）
- V0.4 新增：Iteration Metadata（round/score/approved）
- V0.4 新增：状态机强制化：pending → running → done/failed/timeout
- 轮询检测多个哨兵文件是否全部完成
- 超时和异常处理
- 重启恢复：检查已有哨兵文件恢复状态
"""

import json
import os
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

log = logging.getLogger(__name__)

# 哨兵状态常量
SENTINEL_PENDING = "pending"
SENTINEL_RUNNING = "running"
SENTINEL_DONE = "done"
SENTINEL_FAILED = "failed"
SENTINEL_TIMEOUT = "timeout"

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 600      # 10 分钟
DEFAULT_POLL_INTERVAL = 2  # 2 秒轮询


def _sentinel_dir(chaoting_dir: str, zouzhe_id: str) -> Path:
    """返回指定奏折的哨兵目录路径。"""
    return Path(chaoting_dir) / "sentinels" / zouzhe_id


def _sentinel_path(chaoting_dir: str, zouzhe_id: str, teammate_id: str) -> Path:
    """返回指定 teammate 的哨兵文件路径。"""
    return _sentinel_dir(chaoting_dir, zouzhe_id) / f"{teammate_id}.done"


def create_sentinel_dir(chaoting_dir: str, zouzhe_id: str) -> Path:
    """创建哨兵目录，返回目录路径。"""
    d = _sentinel_dir(chaoting_dir, zouzhe_id)
    d.mkdir(parents=True, exist_ok=True)
    log.debug("Created sentinel dir: %s", d)
    return d


def write_sentinel(
    chaoting_dir: str,
    zouzhe_id: str,
    teammate_id: str,
    status: str = SENTINEL_DONE,
    output: Optional[str] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    写入哨兵文件，标记 teammate 完成。

    Args:
        chaoting_dir: CHAOTING_DIR 路径
        zouzhe_id: 奏折 ID（用于目录隔离）
        teammate_id: Teammate 名称（如 "coder"、"tester"）
        status: 完成状态（done/failed）
        output: 输出文件路径或结果摘要
        error: 失败时的错误信息
        metadata: 额外的 JSON 可序列化数据

    Returns:
        写入的哨兵文件路径
    """
    create_sentinel_dir(chaoting_dir, zouzhe_id)
    path = _sentinel_path(chaoting_dir, zouzhe_id, teammate_id)
    payload = {
        "teammate_id": teammate_id,
        "zouzhe_id": zouzhe_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "output": output,
        "error": error,
        "metadata": metadata or {},
    }
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp_path.rename(path)
        log.info("Sentinel written: %s (%s)", path, status)
    except Exception as exc:
        log.warning("Failed to write sentinel %s: %s", path, exc)
        raise
    return path


def read_sentinel(
    chaoting_dir: str,
    zouzhe_id: str,
    teammate_id: str,
) -> Optional[Dict[str, Any]]:
    """
    读取哨兵文件内容。

    Returns:
        哨兵数据 dict，或 None（文件不存在时）
    """
    path = _sentinel_path(chaoting_dir, zouzhe_id, teammate_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        log.warning("Failed to read sentinel %s: %s", path, exc)
        return None


def check_all_complete(
    chaoting_dir: str,
    zouzhe_id: str,
    teammate_ids: List[str],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    检查所有哨兵文件是否存在。

    Returns:
        {teammate_id: sentinel_data_or_None} 字典
        如果某个 teammate 的哨兵不存在，值为 None
    """
    result = {}
    for tid in teammate_ids:
        result[tid] = read_sentinel(chaoting_dir, zouzhe_id, tid)
    return result


def all_done(statuses: Dict[str, Optional[Dict]]) -> bool:
    """判断是否所有哨兵都已完成（存在且 status 为 done 或 failed）。"""
    for data in statuses.values():
        if data is None:
            return False
        if data.get("status") not in (SENTINEL_DONE, SENTINEL_FAILED):
            return False
    return True


def any_failed(statuses: Dict[str, Optional[Dict]]) -> bool:
    """是否有任何哨兵标记为 failed。"""
    return any(
        data is not None and data.get("status") == SENTINEL_FAILED
        for data in statuses.values()
    )


def list_sentinels(chaoting_dir: str, zouzhe_id: str) -> List[str]:
    """列出指定奏折目录下所有已写入的哨兵文件（不含后缀）。"""
    d = _sentinel_dir(chaoting_dir, zouzhe_id)
    if not d.exists():
        return []
    return [f.stem for f in d.glob("*.done")]


def cleanup_sentinels(chaoting_dir: str, zouzhe_id: str) -> int:
    """删除指定奏折的所有哨兵文件，返回删除数量。"""
    d = _sentinel_dir(chaoting_dir, zouzhe_id)
    if not d.exists():
        return 0
    count = 0
    for f in d.glob("*.done"):
        try:
            f.unlink()
            count += 1
        except Exception as exc:
            log.warning("Failed to delete sentinel %s: %s", f, exc)
    try:
        d.rmdir()  # 仅当目录为空时删除
    except OSError:
        pass
    log.info("Cleaned up %d sentinels for %s", count, zouzhe_id)
    return count


# ──────────────────────────────────────────────────────
# SentinelWatcher — 高层封装，供 Lead Agent 使用
# ──────────────────────────────────────────────────────

class SentinelWatcher:
    """
    文件哨兵监视器：供 Lead Agent 使用的高层 API。

    使用示例：
        watcher = SentinelWatcher("ZZ-20260310-004", "/path/to/chaoting")
        watcher.register(["coder", "tester", "docs"])
        
        # ... 启动 teammates ...
        
        results = watcher.wait_all(timeout=300, poll_interval=2)
        if results["status"] == "complete":
            for tid, data in results["results"].items():
                print(f"{tid}: {data['output']}")
    """

    def __init__(
        self,
        zouzhe_id: str,
        chaoting_dir: Optional[str] = None,
    ):
        self.zouzhe_id = zouzhe_id
        self.chaoting_dir = chaoting_dir or os.environ.get(
            "CHAOTING_DIR",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self._registered: List[str] = []

    def register(self, teammate_ids: List[str]) -> None:
        """注册期望完成的 teammate 列表。"""
        self._registered = list(teammate_ids)
        create_sentinel_dir(self.chaoting_dir, self.zouzhe_id)
        log.info("Registered %d teammates: %s", len(teammate_ids), teammate_ids)

    def write_running(
        self,
        teammate_id: str,
        progress: float = 0.0,
        message: Optional[str] = None,
    ) -> Path:
        """
        V0.4: 写入 running 进度哨兵（供 Teammate 在执行中调用）。

        Args:
            teammate_id: Teammate 名称
            progress: 完成进度 0.0-1.0
            message: 进度描述（如 "Applying improvement 2/3"）
        """
        return write_sentinel(
            self.chaoting_dir,
            self.zouzhe_id,
            teammate_id,
            status=SENTINEL_RUNNING,
            metadata={"progress": max(0.0, min(1.0, progress)), "message": message or ""},
        )

    def write_done(
        self,
        teammate_id: str,
        status: str = SENTINEL_DONE,
        output: Optional[str] = None,
        error: Optional[str] = None,
        round_num: Optional[int] = None,
        score: Optional[int] = None,
        approved: Optional[bool] = None,
        **metadata,
    ) -> Path:
        """
        写入完成哨兵（供 Teammate 调用）。

        V0.4 新增参数：
            round_num: 当前迭代轮次（用于 IterationCoordinator）
            score: 质量评分（reviewer 使用）
            approved: 是否通过审查（reviewer 使用）
        """
        iter_meta: Dict[str, Any] = dict(metadata)
        if round_num is not None:
            iter_meta["round"] = round_num
        if score is not None:
            iter_meta["score"] = score
        if approved is not None:
            iter_meta["approved"] = approved
        return write_sentinel(
            self.chaoting_dir,
            self.zouzhe_id,
            teammate_id,
            status=status,
            output=output,
            error=error,
            metadata=iter_meta,
        )

    def status(self) -> Dict[str, Optional[Dict]]:
        """返回当前所有注册 teammates 的哨兵状态。"""
        return check_all_complete(
            self.chaoting_dir, self.zouzhe_id, self._registered
        )

    def recover(self) -> List[str]:
        """
        从磁盘恢复已完成的哨兵状态（重启恢复）。

        Returns:
            已恢复的 teammate_id 列表
        """
        existing = list_sentinels(self.chaoting_dir, self.zouzhe_id)
        recovered = [t for t in existing if t in self._registered]
        if recovered:
            log.info("Recovered %d completed sentinels: %s", len(recovered), recovered)
        return recovered

    def wait_all(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_progress: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        阻塞等待所有注册 teammates 完成。

        Args:
            timeout: 最大等待秒数（0 表示永不超时）
            poll_interval: 轮询间隔秒数
            on_progress: 可选回调，每次轮询时调用 on_progress(pending, done)

        Returns:
            {
              "status": "complete" | "timeout" | "partial_failure",
              "results": {teammate_id: sentinel_data},
              "pending": [teammate_id, ...],
              "failed": [teammate_id, ...],
              "elapsed": seconds,
            }
        """
        if not self._registered:
            log.warning("No teammates registered; returning immediately")
            return {
                "status": "complete",
                "results": {},
                "pending": [],
                "failed": [],
                "elapsed": 0.0,
            }

        start = time.time()
        # 先尝试从磁盘恢复
        self.recover()

        while True:
            statuses = self.status()
            done_ids = [
                t for t, d in statuses.items()
                if d is not None and d.get("status") in (SENTINEL_DONE, SENTINEL_FAILED)
            ]
            pending_ids = [t for t, d in statuses.items() if d is None]
            failed_ids = [
                t for t, d in statuses.items()
                if d is not None and d.get("status") == SENTINEL_FAILED
            ]
            elapsed = time.time() - start

            if on_progress:
                try:
                    on_progress(pending=pending_ids, done=done_ids)
                except Exception:
                    pass

            if all_done(statuses):
                final_status = "partial_failure" if failed_ids else "complete"
                log.info(
                    "All sentinels resolved in %.1fs: %d done, %d failed",
                    elapsed, len(done_ids), len(failed_ids)
                )
                return {
                    "status": final_status,
                    "results": {t: d for t, d in statuses.items()},
                    "pending": [],
                    "failed": failed_ids,
                    "elapsed": elapsed,
                }

            if timeout > 0 and elapsed >= timeout:
                log.warning(
                    "Sentinel timeout (%.0fs) — %d still pending: %s",
                    elapsed, len(pending_ids), pending_ids
                )
                # 写入超时哨兵，避免下次重启重复等待
                for tid in pending_ids:
                    try:
                        write_sentinel(
                            self.chaoting_dir, self.zouzhe_id, tid,
                            status=SENTINEL_TIMEOUT,
                            error=f"Timeout after {timeout}s",
                        )
                    except Exception:
                        pass
                return {
                    "status": "timeout",
                    "results": {t: d for t, d in statuses.items()},
                    "pending": pending_ids,
                    "failed": failed_ids,
                    "elapsed": elapsed,
                }

            log.debug(
                "Waiting: %d pending (%s), %d done — %.0fs elapsed",
                len(pending_ids), pending_ids, len(done_ids), elapsed
            )
            time.sleep(poll_interval)

    def cleanup(self) -> int:
        """删除所有哨兵文件（任务完成后清理）。"""
        return cleanup_sentinels(self.chaoting_dir, self.zouzhe_id)

    def get_metrics(self) -> Dict[str, Any]:
        """
        V0.4: 收集性能指标（用于 chaoting teams metrics 命令）。

        Returns:
            {
              "zouzhe_id": str,
              "total": int,
              "done": int,
              "failed": int,
              "pending": int,
              "running": int,
              "timestamps": {teammate_id: timestamp_str},
              "scores": {teammate_id: score_int},       # 如有 metadata.score
              "rounds": {teammate_id: round_int},       # 如有 metadata.round
              "outputs": {teammate_id: output_path},
            }
        """
        statuses = self.status()
        metrics: Dict[str, Any] = {
            "zouzhe_id": self.zouzhe_id,
            "total": len(self._registered),
            "done": 0,
            "failed": 0,
            "timeout": 0,
            "running": 0,
            "pending": 0,
            "timestamps": {},
            "progress": {},
            "scores": {},
            "rounds": {},
            "outputs": {},
        }
        for tid, data in statuses.items():
            if data is None:
                metrics["pending"] += 1
                continue
            st = data.get("status", "")
            if st == SENTINEL_DONE:
                metrics["done"] += 1
            elif st == SENTINEL_FAILED:
                metrics["failed"] += 1
            elif st == SENTINEL_TIMEOUT:
                metrics["timeout"] += 1
            elif st == SENTINEL_RUNNING:
                metrics["running"] += 1
                p = data.get("metadata", {}).get("progress")
                if p is not None:
                    metrics["progress"][tid] = p
            ts = data.get("timestamp")
            if ts:
                metrics["timestamps"][tid] = ts
            out = data.get("output")
            if out:
                metrics["outputs"][tid] = out
            meta = data.get("metadata") or {}
            if "score" in meta:
                metrics["scores"][tid] = meta["score"]
            if "round" in meta:
                metrics["rounds"][tid] = meta["round"]
        return metrics

    def progress_summary(self) -> str:
        """V0.4: 返回人类可读的进度摘要行（用于 follow 模式）。"""
        statuses = self.status()
        parts = []
        for tid, data in sorted(statuses.items()):
            if data is None:
                parts.append(f"⏳ {tid}")
            elif data.get("status") == SENTINEL_RUNNING:
                pct = data.get("metadata", {}).get("progress", 0)
                msg = data.get("metadata", {}).get("message", "")
                bar = "=" * int(pct * 10) + ">" + " " * (9 - int(pct * 10))
                parts.append(f"🔄 {tid} [{bar}] {int(pct*100)}% {msg[:30]}")
            elif data.get("status") == SENTINEL_DONE:
                parts.append(f"✅ {tid}")
            elif data.get("status") == SENTINEL_FAILED:
                parts.append(f"❌ {tid}")
            elif data.get("status") == SENTINEL_TIMEOUT:
                parts.append(f"⏰ {tid}")
        return " | ".join(parts)

    # ── 打印辅助 ──

    def print_status(self) -> None:
        """打印当前哨兵状态概览（供 CLI 展示）。"""
        statuses = self.status()
        total = len(self._registered)
        done_count = sum(1 for d in statuses.values() if d is not None)
        print(f"Sentinels [{self.zouzhe_id}]: {done_count}/{total} complete")
        for tid, data in statuses.items():
            if data is None:
                marker = "⏳"
            elif data.get("status") == SENTINEL_DONE:
                marker = "✅"
            elif data.get("status") == SENTINEL_FAILED:
                marker = "❌"
            elif data.get("status") == SENTINEL_TIMEOUT:
                marker = "⏰"
            else:
                marker = "🔄"
            ts = data.get("timestamp", "")[:19] if data else "-"
            out = data.get("output", "") or "" if data else ""
            print(f"  {marker} {tid:<20} {ts}  {out[:60]}")


# ──────────────────────────────────────────────────────
# CLI 入口（直接运行时）
# ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    CHAOTING_DIR_DEFAULT = os.environ.get(
        "CHAOTING_DIR",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    parser = argparse.ArgumentParser(description="Chaoting 文件哨兵工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # write
    p_write = sub.add_parser("write", help="写入哨兵文件（标记 teammate 完成）")
    p_write.add_argument("zouzhe_id")
    p_write.add_argument("teammate_id")
    p_write.add_argument("--status", default="done")
    p_write.add_argument("--output")
    p_write.add_argument("--error")
    p_write.add_argument("--chaoting-dir", default=CHAOTING_DIR_DEFAULT)

    # read
    p_read = sub.add_parser("read", help="读取哨兵文件")
    p_read.add_argument("zouzhe_id")
    p_read.add_argument("teammate_id")
    p_read.add_argument("--chaoting-dir", default=CHAOTING_DIR_DEFAULT)

    # status
    p_status = sub.add_parser("status", help="显示指定奏折的所有哨兵状态")
    p_status.add_argument("zouzhe_id")
    p_status.add_argument("--teammates", nargs="*")
    p_status.add_argument("--chaoting-dir", default=CHAOTING_DIR_DEFAULT)

    # wait
    p_wait = sub.add_parser("wait", help="等待所有哨兵完成")
    p_wait.add_argument("zouzhe_id")
    p_wait.add_argument("teammates", nargs="+")
    p_wait.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    p_wait.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL)
    p_wait.add_argument("--chaoting-dir", default=CHAOTING_DIR_DEFAULT)

    # cleanup
    p_clean = sub.add_parser("cleanup", help="清理哨兵文件")
    p_clean.add_argument("zouzhe_id")
    p_clean.add_argument("--chaoting-dir", default=CHAOTING_DIR_DEFAULT)

    # list
    p_list = sub.add_parser("list", help="列出已完成的哨兵")
    p_list.add_argument("zouzhe_id")
    p_list.add_argument("--chaoting-dir", default=CHAOTING_DIR_DEFAULT)

    args = parser.parse_args()

    if args.cmd == "write":
        path = write_sentinel(
            args.chaoting_dir, args.zouzhe_id, args.teammate_id,
            status=args.status, output=args.output, error=args.error
        )
        print(json.dumps({"ok": True, "path": str(path)}))

    elif args.cmd == "read":
        data = read_sentinel(args.chaoting_dir, args.zouzhe_id, args.teammate_id)
        print(json.dumps(data or {"ok": False, "error": "not found"}))

    elif args.cmd == "status":
        teammate_ids = args.teammates or list_sentinels(args.chaoting_dir, args.zouzhe_id)
        watcher = SentinelWatcher(args.zouzhe_id, args.chaoting_dir)
        watcher.register(teammate_ids)
        watcher.print_status()

    elif args.cmd == "wait":
        watcher = SentinelWatcher(args.zouzhe_id, args.chaoting_dir)
        watcher.register(args.teammates)
        result = watcher.wait_all(
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            on_progress=lambda pending, done: print(
                f"  Waiting: {len(pending)} pending, {len(done)} done"
            ),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if result["status"] != "complete":
            sys.exit(1)

    elif args.cmd == "cleanup":
        n = cleanup_sentinels(args.chaoting_dir, args.zouzhe_id)
        print(json.dumps({"ok": True, "deleted": n}))

    elif args.cmd == "list":
        items = list_sentinels(args.chaoting_dir, args.zouzhe_id)
        print(json.dumps(items))
