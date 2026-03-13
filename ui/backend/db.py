"""aiosqlite connection helper for chaoting Web UI backend."""

import os
from pathlib import Path

import aiosqlite

_DB_PATH: str | None = None


def _resolve_db_path() -> str:
    """Resolve the database path from environment variables with fallbacks."""
    # 1. Explicit CHAOTING_DB_PATH
    if p := os.environ.get("CHAOTING_DB_PATH"):
        return p
    # 2. CHAOTING_DIR + /chaoting.db
    if d := os.environ.get("CHAOTING_DIR"):
        return os.path.join(d, "chaoting.db")
    # 3. Default location
    return str(Path.home() / ".themachine" / ".chaoting" / "chaoting.db")


def get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _resolve_db_path()
    return _DB_PATH


async def get_db() -> aiosqlite.Connection:
    """Open a new read-only connection with WAL mode."""
    db = await aiosqlite.connect(get_db_path())
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    return db
