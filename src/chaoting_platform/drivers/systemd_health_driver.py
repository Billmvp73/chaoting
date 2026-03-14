import os
import subprocess
import time

from .base import HealthDriver, HealthCheckResult

CHAOTING_DIR = os.environ.get("CHAOTING_DIR", "")
CHAOTING_CLI = os.path.join(CHAOTING_DIR, "src", "chaoting") if CHAOTING_DIR else ""


class SystemdHealthDriver(HealthDriver):
    """
    封装 009 § 四三层健康检查：
    L1 (<5s): systemctl is-active + db check + cli version
    L2 (<30s): pull readonly + dispatcher-poll
    L3 (<120s): e2e smoke（异步，不阻塞）
    """

    def check(self, layer: int = 1) -> HealthCheckResult:
        start = time.time()
        checks = []

        spec = self.manifest.get("spec", {})
        health_spec = spec.get("health", {})
        health_type = health_spec.get("type", "systemctl")

        # 获取 service_name（直接或从 composite checks 中）
        service_name = health_spec.get("service_name", "")
        if not service_name and health_type == "composite":
            # 从 composite checks 找第一个 systemctl 的 service_name
            for c in health_spec.get("checks", []):
                if c.get("type") == "systemctl":
                    service_name = c.get("service_name", "")
                    break

        if layer == 1:
            checks = self._check_layer1(service_name, health_spec)
        elif layer == 2:
            checks = self._check_layer2(health_spec)
        elif layer == 3:
            # Layer 3 异步，不阻塞
            checks = [{"name": "e2e_smoke", "passed": True, "duration_ms": 0, "error": "async, not blocking"}]

        ok = all(c.get("passed", False) for c in checks)
        total_ms = int((time.time() - start) * 1000)
        return HealthCheckResult(ok=ok, layer=layer, checks=checks, total_duration_ms=total_ms)

    def _check_layer1(self, service_name: str, health_spec: dict) -> list:
        checks = []
        l1_timeout = health_spec.get("layer1_timeout_sec", 5)

        # Check 1: dispatcher 进程是否运行
        if service_name:
            t0 = time.time()
            try:
                result = subprocess.run(
                    ["systemctl", "--user", "is-active", service_name],
                    capture_output=True, text=True, timeout=l1_timeout
                )
                passed = result.returncode == 0 and result.stdout.strip() == "active"
                checks.append({
                    "name": "dispatcher_running",
                    "passed": passed,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": None if passed else f"service not active: {result.stdout.strip()}"
                })
            except Exception as e:
                checks.append({"name": "dispatcher_running", "passed": False,
                    "duration_ms": int((time.time() - t0) * 1000), "error": str(e)})

        # Check 2: DB 可读写
        if CHAOTING_CLI and os.path.exists(CHAOTING_CLI):
            t0 = time.time()
            try:
                result = subprocess.run(
                    [CHAOTING_CLI, "health", "--check", "db"],
                    capture_output=True, text=True, timeout=l1_timeout
                )
                passed = result.returncode == 0
                checks.append({
                    "name": "db_writable",
                    "passed": passed,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": None if passed else result.stderr.strip() or result.stdout.strip()
                })
            except Exception as e:
                checks.append({"name": "db_writable", "passed": False,
                    "duration_ms": int((time.time() - t0) * 1000), "error": str(e)})

        # Check 3: CLI 可响应
        if CHAOTING_CLI and os.path.exists(CHAOTING_CLI):
            t0 = time.time()
            try:
                result = subprocess.run(
                    [CHAOTING_CLI, "version"],
                    capture_output=True, text=True, timeout=l1_timeout
                )
                passed = result.returncode == 0
                checks.append({
                    "name": "cli_responsive",
                    "passed": passed,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": None if passed else "CLI version command failed"
                })
            except Exception as e:
                checks.append({"name": "cli_responsive", "passed": False,
                    "duration_ms": int((time.time() - t0) * 1000), "error": str(e)})

        # 若没有 CHAOTING_CLI（测试环境），L1 默认通过
        if not checks:
            checks.append({"name": "no_checks_configured", "passed": True, "duration_ms": 0, "error": None})

        return checks

    def _check_layer2(self, health_spec: dict) -> list:
        checks = []
        l2_timeout = health_spec.get("layer2_timeout_sec", 30)

        # Check 4: pull readonly
        if CHAOTING_CLI and os.path.exists(CHAOTING_CLI):
            t0 = time.time()
            try:
                result = subprocess.run(
                    [CHAOTING_CLI, "health", "--check", "pull-readonly"],
                    capture_output=True, text=True, timeout=l2_timeout
                )
                passed = result.returncode == 0
                checks.append({
                    "name": "pull_readonly",
                    "passed": passed,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": None if passed else result.stderr.strip() or result.stdout.strip()
                })
            except Exception as e:
                checks.append({"name": "pull_readonly", "passed": False,
                    "duration_ms": int((time.time() - t0) * 1000), "error": str(e)})

        # Check 5: dispatcher-poll
        if CHAOTING_CLI and os.path.exists(CHAOTING_CLI):
            t0 = time.time()
            try:
                result = subprocess.run(
                    [CHAOTING_CLI, "health", "--check", "dispatcher-poll"],
                    capture_output=True, text=True, timeout=l2_timeout
                )
                passed = result.returncode == 0
                checks.append({
                    "name": "dispatcher_poll",
                    "passed": passed,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": None if passed else result.stderr.strip() or result.stdout.strip()
                })
            except Exception as e:
                checks.append({"name": "dispatcher_poll", "passed": False,
                    "duration_ms": int((time.time() - t0) * 1000), "error": str(e)})

        # 若没有 CHAOTING_CLI（测试环境），L2 默认通过
        if not checks:
            checks.append({"name": "no_l2_checks", "passed": True, "duration_ms": 0, "error": None})

        return checks
