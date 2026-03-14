from .manifest_loader import ManifestLoader
from .drivers.base import DeployResult, HealthCheckResult, LogResult
from .drivers.systemd_deploy_driver import SystemdDeployDriver
from .drivers.systemd_health_driver import SystemdHealthDriver
from .drivers.journalctl_log_driver import JournalctlLogDriver


class PlatformInterface:
    """
    统一接口层：根据 manifest.deploy.type 选择 Driver，Dispatcher 不感知 Driver 实现。

    用法（dispatcher.py 中）：
        from chaoting_platform.interface import PlatformInterface
        platform = PlatformInterface()
        result = platform.deploy(project_id="chaoting", zouzhe_id=zouzhe_id)
    """

    def deploy(self, project_id: str = "chaoting", zouzhe_id: str = "",
               dry_run: bool = False, force: bool = False, timeout: int = None) -> DeployResult:
        """读取 manifest，按 deploy.type 选 Driver，执行 deploy。"""
        manifest = ManifestLoader.load(project_id)
        driver = self._get_deploy_driver(manifest, zouzhe_id)
        return driver.deploy(dry_run=dry_run, force=force)

    def health_check(self, project_id: str = "chaoting", layer: int = 1) -> HealthCheckResult:
        """读取 manifest，按 health.type 选 HealthDriver，执行健康检查。"""
        manifest = ManifestLoader.load(project_id)
        driver = self._get_health_driver(manifest)
        return driver.check(layer=layer)

    def logs(self, project_id: str = "chaoting", lines: int = 100, since: str = None) -> LogResult:
        """读取 manifest，按 logs.type 选 LogDriver，拉取日志。"""
        manifest = ManifestLoader.load(project_id)
        driver = self._get_log_driver(manifest)
        return driver.tail(lines=lines, since=since)

    def _get_deploy_driver(self, manifest: dict, zouzhe_id: str):
        deploy_type = manifest.get("spec", {}).get("deploy", {}).get("type", "")
        if deploy_type == "systemd_user":
            return SystemdDeployDriver(manifest, zouzhe_id)
        # Future: DockerDeployDriver, ScriptDeployDriver, GitPullDeployDriver
        raise NotImplementedError(f"Deploy type not yet implemented: {deploy_type}")

    def _get_health_driver(self, manifest: dict):
        # composite 和 systemctl 都由 SystemdHealthDriver 处理
        return SystemdHealthDriver(manifest)

    def _get_log_driver(self, manifest: dict):
        log_type = manifest.get("spec", {}).get("logs", {}).get("type", "")
        if log_type == "journalctl":
            return JournalctlLogDriver(manifest)
        raise NotImplementedError(f"Log type not yet implemented: {log_type}")
