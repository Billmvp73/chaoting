#!/usr/bin/env python3
"""config.py — Chaoting workspace configuration manager.

Provides ChaotingConfig: a single source of truth for all path-related
settings. Supports workspace isolation via CHAOTING_WORKSPACE env var.

Priority (highest → lowest):
  1. Explicit constructor arguments
  2. CHAOTING_* environment variables
  3. {workspace}/.chaoting/config.json
  4. {repo}/.env
  5. Built-in defaults

Usage:
    from config import ChaotingConfig
    cfg = ChaotingConfig()
    db = sqlite3.connect(cfg.db_path)
    log_dir = cfg.log_dir
"""

import json
import os
from pathlib import Path


def _detect_chaoting_dir() -> str:
    """Auto-detect the Chaoting repo root from this file's location."""
    this_file = Path(__file__).resolve()
    # src/config.py → parent.parent = repo root
    repo_root = this_file.parent.parent
    return str(repo_root)


def _load_dotenv(path: str) -> dict:
    """Parse a .env file into a dict. Does not override os.environ."""
    result = {}
    p = Path(path)
    if not p.is_file():
        return result
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip()
    return result


def _load_config_json(path: str) -> dict:
    """Load a config.json file. Returns {} on error."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


class ChaotingConfig:
    """Chaoting path configuration with workspace isolation support.

    All paths are absolute strings. Use this class as the single
    source of truth for DB_PATH, LOGS_DIR, SENTINEL_DIR, etc.
    """

    def __init__(
        self,
        chaoting_dir: str | None = None,
        workspace: str | None = None,
    ):
        # ── Step 1: repo / code dir ──────────────────────────────────────
        self.chaoting_dir: str = (
            chaoting_dir
            or os.environ.get("CHAOTING_DIR", "")
            or _detect_chaoting_dir()
        )

        # ── Step 2: load .env (lowest priority, don't override env) ──────
        dotenv = _load_dotenv(os.path.join(self.chaoting_dir, ".env"))

        def _env(key: str, fallback: str = "") -> str:
            return os.environ.get(key) or dotenv.get(key) or fallback

        # ── Step 3: workspace path ────────────────────────────────────────
        self.workspace: str = (
            workspace
            or os.environ.get("CHAOTING_WORKSPACE", "")
            or ""
        )

        # ── Step 4: data dir (where DB/logs/sentinels live) ──────────────
        if self.workspace:
            self.data_dir: str = os.path.join(self.workspace, ".chaoting")
        else:
            self.data_dir = self.chaoting_dir

        # ── Step 5: load workspace config.json (if present) ──────────────
        config_json = _load_config_json(os.path.join(self.data_dir, "config.json"))

        def _cfg(key: str, fallback: str = "") -> str:
            """Env > config.json > fallback."""
            env_key = f"CHAOTING_{key.upper()}"
            return os.environ.get(env_key) or config_json.get(key) or fallback

        # ── Step 6: derive all paths ──────────────────────────────────────
        self.db_path: str = _cfg(
            "db_path",
            os.path.join(self.data_dir, "chaoting.db"),
        )
        self.log_dir: str = _cfg(
            "log_dir",
            os.path.join(self.data_dir, "logs"),
        )
        self.sentinel_dir: str = _cfg(
            "sentinel_dir",
            os.path.join(self.data_dir, "sentinels"),
        )

        # ── Step 7: OpenClaw / Discord settings ──────────────────────────
        self.openclaw_cli: str = _env("OPENCLAW_CLI", "themachine")
        self.openclaw_state_dir: str = _env(
            "OPENCLAW_STATE_DIR",
            os.path.join(Path.home(), ".openclaw"),
        )
        self.discord_fallback_channel_id: str = _env(
            "DISCORD_FALLBACK_CHANNEL_ID", ""
        )

        # ── Step 8: service name ──────────────────────────────────────────
        if self.workspace:
            ws_name = (
                Path(self.workspace).name.lower()
                .replace(" ", "-")
                .replace("_", "-")
            )
            self.service_name: str = f"chaoting-dispatcher-{ws_name}"
        else:
            self.service_name = "chaoting-dispatcher"

    # ── Directory helpers ─────────────────────────────────────────────────

    def ensure_dirs(self) -> None:
        """Create all required data directories if they don't exist."""
        for d in [self.data_dir, self.log_dir, self.sentinel_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)

    def write_config_json(self) -> str:
        """Serialize this config to {data_dir}/config.json. Returns path."""
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        config_path = os.path.join(self.data_dir, "config.json")
        data = {
            "_version": 1,
            "_generated_by": "chaoting config.py",
            "workspace": self.workspace,
            "chaoting_dir": self.chaoting_dir,
            "data_dir": self.data_dir,
            "db_path": self.db_path,
            "log_dir": self.log_dir,
            "sentinel_dir": self.sentinel_dir,
            "service_name": self.service_name,
        }
        Path(config_path).write_text(json.dumps(data, indent=2))
        return config_path

    # ── Repr ──────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"ChaotingConfig("
            f"workspace={self.workspace!r}, "
            f"db={self.db_path!r}, "
            f"service={self.service_name!r})"
        )


# ── Module-level singleton (used by CLI / dispatcher) ────────────────────

_default_config: ChaotingConfig | None = None


def get_config(**kwargs) -> ChaotingConfig:
    """Return the module-level ChaotingConfig singleton.

    Accepts the same kwargs as ChaotingConfig.__init__ for override.
    Subsequent calls without kwargs return the cached singleton.
    """
    global _default_config
    if _default_config is None or kwargs:
        _default_config = ChaotingConfig(**kwargs)
    return _default_config
