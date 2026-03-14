from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeployResult:
    ok: bool
    exit_code: int
    deploy_result: str   # success / failed / skipped_idempotent
    project_id: str = ""
    zouzhe_id: str = ""
    from_commit: Optional[str] = None
    to_commit: Optional[str] = None
    backup_path: Optional[str] = None
    duration_sec: float = 0.0
    error: Optional[str] = None
    health_check: Optional[dict] = None
    step_failed: Optional[str] = None
    rollback_triggered: bool = False
    rollback_result: Optional[str] = None


@dataclass
class HealthCheckResult:
    ok: bool
    layer: int
    checks: list = field(default_factory=list)  # [{name, passed, duration_ms, error}]
    total_duration_ms: int = 0


@dataclass
class LogResult:
    lines: list = field(default_factory=list)
    source: str = ""
    total_lines: int = 0


class DeployDriver(ABC):
    def __init__(self, manifest: dict, zouzhe_id: str):
        self.manifest = manifest
        self.zouzhe_id = zouzhe_id

    @abstractmethod
    def deploy(self, dry_run: bool = False, force: bool = False) -> DeployResult:
        pass

    @abstractmethod
    def rollback(self, backup_path: str) -> bool:
        pass

    @abstractmethod
    def create_backup(self) -> str:
        pass


class HealthDriver(ABC):
    def __init__(self, manifest: dict):
        self.manifest = manifest

    @abstractmethod
    def check(self, layer: int = 1) -> HealthCheckResult:
        pass


class LogDriver(ABC):
    def __init__(self, manifest: dict):
        self.manifest = manifest

    @abstractmethod
    def tail(self, lines: int = 100, since: str = None) -> LogResult:
        pass
