#!/usr/bin/env python3
"""chaoting_log — shared audit log module for CLI and dispatcher.

Provides zouzhe_log() to write structured per-role log blocks under
  logs/{zouzhe_id}/{role}.log  (RotatingFileHandler, 10 MB / 3 backups)

Both the CLI (src/chaoting) and the dispatcher import from this module.
"""

import logging
import os
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler

CHAOTING_DIR = os.environ.get(
    "CHAOTING_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

# ── workspace 隔离支持（ZZ-20260310-016）──
# 若 CHAOTING_WORKSPACE 已设置，日志写入 {workspace}/.chaoting/logs/
# 否则沿用原有 {CHAOTING_DIR}/logs/（向后兼容）
_workspace = os.environ.get("CHAOTING_WORKSPACE", "")
if _workspace:
    LOGS_DIR = os.path.join(_workspace, ".chaoting", "logs")
else:
    LOGS_DIR = os.path.join(CHAOTING_DIR, "logs")

LOG_SEPARATOR = "━" * 42   # Visual block separator used in log blocks

_audit_loggers: dict = {}         # (zouzhe_id, role) -> logging.Logger
_audit_lock = threading.Lock()    # Protects _audit_loggers dict

_log = logging.getLogger("chaoting.audit")


def _get_audit_logger(zouzhe_id: str, role: str) -> logging.Logger:
    """Get or create a RotatingFileHandler-backed logger for (zouzhe_id, role)."""
    key = (zouzhe_id, role)
    with _audit_lock:
        if key not in _audit_loggers:
            log_dir = os.path.join(LOGS_DIR, zouzhe_id)
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f"{role}.log")

            logger_name = f"chaoting.audit.{zouzhe_id}.{role}"
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.propagate = False   # Don't bubble to root logger

            if not logger.handlers:
                handler = RotatingFileHandler(
                    log_file,
                    maxBytes=10 * 1024 * 1024,   # 10 MB
                    backupCount=3,
                    encoding="utf-8",
                    mode="a",
                )
                handler.setFormatter(logging.Formatter("%(message)s"))
                logger.addHandler(handler)

            _audit_loggers[key] = logger
        return _audit_loggers[key]


def zouzhe_log(
    zouzhe_id: str,
    role: str,
    event_type: str,
    headline: str,
    content: str = "",
    **kwargs,
):
    """Write a structured log block to logs/{zouzhe_id}/{role}.log.

    Block format:
        [YYYY-MM-DD HH:MM:SS] ▶ EVENT_TYPE
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        headline

        KEY: value
        ...

        content (multi-line, optional)

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    Never raises — all exceptions are swallowed with a log.warning.
    """
    # Parameter guard — invalid inputs silently skipped, never crash caller
    if not zouzhe_id or not role:
        _log.warning(
            "zouzhe_log: invalid params zouzhe_id=%r role=%r — skipping",
            zouzhe_id,
            role,
        )
        return
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"\n[{timestamp}] ▶ {event_type}",
            LOG_SEPARATOR,
            "",
            headline,
        ]

        kv_lines = [
            f"{k.upper()}: {v}"
            for k, v in kwargs.items()
            if v is not None and v != ""
        ]
        if kv_lines:
            lines.append("")
            lines.extend(kv_lines)

        if content:
            lines.append("")
            lines.append(content[:3000])   # Truncate very large blobs

        lines.append("")
        lines.append(LOG_SEPARATOR)

        block = "\n".join(lines)
        logger = _get_audit_logger(zouzhe_id, role)
        logger.info(block)
    except Exception as exc:
        _log.warning(
            "zouzhe_log failed for %s/%s/%s: %s", zouzhe_id, role, event_type, exc
        )
