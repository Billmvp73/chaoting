import os
import json
import logging
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

from .base import DeployDriver, DeployResult

CHAOTING_DIR = os.environ.get("CHAOTING_DIR", "")


class SystemdDeployDriver(DeployDriver):
    """
    封装 009 auto-deploy-spec.md § 三 Step 1-6 逻辑。

    退出码语义（与 009 § 2.3 完全一致）:
    0: 成功
    1: 健康检查失败，已回滚
    2: 健康检查失败且回滚失败
    3: 幂等跳过（同 SHA）
    4: 权限错误
    5: 前置验证失败
    """

    def deploy(self, dry_run: bool = False, force: bool = False) -> DeployResult:
        start_time = time.time()
        spec = self.manifest.get("spec", {})
        deploy_spec = spec.get("deploy", {})
        project_id = self.manifest.get("metadata", {}).get("project_id", "")

        service_name = deploy_spec.get("service_name", "")
        binary_src_rel = deploy_spec.get("binary_src", "")
        binary_dest = deploy_spec.get("binary_dest", "")
        repo_path = deploy_spec.get("repo_path", "")
        post_deploy_cmd = deploy_spec.get("post_deploy_cmd", "")
        branch = deploy_spec.get("branch", "main")
        backup_dir = os.path.join(CHAOTING_DIR, "backups")

        # Step 1: Pre-flight checks
        # 1a: 检查 CHAOTING_DIR DB 可写
        db_path = os.path.join(CHAOTING_DIR, "chaoting.db")
        if not dry_run:
            check_path = os.path.dirname(db_path) if not os.path.exists(db_path) else db_path
            if check_path and not os.access(check_path, os.W_OK):
                return DeployResult(ok=False, exit_code=5, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error="Pre-flight failed: DB not writable", step_failed="preflight_db")

        # 1b: 检查磁盘空间 > 10MB
        if not dry_run:
            stat = shutil.disk_usage(CHAOTING_DIR or "/")
            if stat.free < 10 * 1024 * 1024:
                return DeployResult(ok=False, exit_code=5, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error="Pre-flight failed: disk < 10MB", step_failed="preflight_disk")

        # 1c: 检查快照目录可写
        if not dry_run:
            os.makedirs(backup_dir, exist_ok=True)
            if not os.access(backup_dir, os.W_OK):
                return DeployResult(ok=False, exit_code=5, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error="Pre-flight failed: backup_dir not writable", step_failed="preflight_backup_dir")

        # Resolve binary_src absolute path
        binary_src = ""
        if repo_path and binary_src_rel:
            binary_src = os.path.join(repo_path, binary_src_rel)

        # Step 2a: Idempotency check (before git pull, check current deployed SHA)
        current_sha = self._get_deployed_sha(project_id, backup_dir)

        # Step 3a: git pull (to get new code first, then check new SHA)
        if repo_path and not dry_run:
            try:
                subprocess.run(
                    ["git", "-C", repo_path, "checkout", branch],
                    check=True, capture_output=True, timeout=60
                )
                subprocess.run(
                    ["git", "-C", repo_path, "pull", "origin", branch],
                    check=True, capture_output=True, timeout=120
                )
            except subprocess.CalledProcessError as e:
                return DeployResult(ok=False, exit_code=5, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error=f"git pull failed: {e}", step_failed="git_pull")

        # Get target SHA after pull
        target_sha = ""
        if repo_path and not dry_run:
            try:
                result = subprocess.run(
                    ["git", "-C", repo_path, "rev-parse", "HEAD"],
                    capture_output=True, text=True, check=True
                )
                target_sha = result.stdout.strip()
            except Exception:
                pass

        # Idempotency: 同 SHA + not force → 退出码 3
        if not force and current_sha and target_sha and current_sha == target_sha:
            return DeployResult(ok=True, exit_code=3, deploy_result="skipped_idempotent",
                project_id=project_id, zouzhe_id=self.zouzhe_id,
                from_commit=current_sha, to_commit=target_sha,
                duration_sec=time.time() - start_time,
                error="commit SHA matches deployed version; use --force to override")

        # Step 2b: Create backup
        backup_path = ""
        if binary_dest and os.path.exists(binary_dest) and not dry_run:
            try:
                backup_path = self.create_backup_for(project_id, binary_dest, backup_dir, current_sha)
            except Exception as e:
                return DeployResult(ok=False, exit_code=5, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error=f"Backup creation failed: {e}", step_failed="create_backup")

        if dry_run:
            return DeployResult(ok=True, exit_code=0, deploy_result="dry_run",
                project_id=project_id, zouzhe_id=self.zouzhe_id,
                from_commit=current_sha, to_commit=target_sha,
                duration_sec=time.time() - start_time)

        # Step 3b: cp binary
        if binary_src and binary_dest and os.path.exists(binary_src):
            try:
                os.makedirs(os.path.dirname(binary_dest), exist_ok=True)
                shutil.copy2(binary_src, binary_dest)
            except PermissionError as e:
                return DeployResult(ok=False, exit_code=4, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error=f"Permission error copying binary: {e}", step_failed="cp_binary")
            except Exception as e:
                return DeployResult(ok=False, exit_code=1, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error=f"Failed to copy binary: {e}", step_failed="cp_binary",
                    rollback_triggered=True, rollback_result=self._do_rollback(backup_path, service_name))

        # Step 3c: 条件性执行 post_deploy_cmd
        if post_deploy_cmd:
            try:
                cmd_args = shlex.split(post_deploy_cmd)
                subprocess.run(
                    cmd_args, shell=False, capture_output=True, text=True, timeout=60
                )
            except Exception as e:
                log.warning("post_deploy_cmd failed (non-fatal): %s", e)

        # Step 4: systemctl --user restart
        if service_name:
            try:
                subprocess.run(
                    ["systemctl", "--user", "restart", service_name],
                    check=True, capture_output=True, timeout=30
                )
            except subprocess.CalledProcessError as e:
                rollback_result = self._do_rollback(backup_path, service_name)
                return DeployResult(ok=False, exit_code=1, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    from_commit=current_sha, to_commit=target_sha,
                    error=f"systemctl restart failed: {e}", step_failed="systemctl_restart",
                    rollback_triggered=True, rollback_result=rollback_result)
            except subprocess.TimeoutExpired as e:
                rollback_result = self._do_rollback(backup_path, service_name)
                return DeployResult(ok=False, exit_code=1, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    from_commit=current_sha, to_commit=target_sha,
                    error=f"systemctl restart timed out: {e}", step_failed="systemctl_restart",
                    rollback_triggered=True, rollback_result=rollback_result)
            except PermissionError as e:
                return DeployResult(ok=False, exit_code=4, deploy_result="failed",
                    project_id=project_id, zouzhe_id=self.zouzhe_id,
                    error=f"Permission error: {e}", step_failed="systemctl_restart")

            # Step 4b: 等待 5 秒
            time.sleep(5)

        # Step 5: Health check (Layer 1+2)
        from chaoting_platform.drivers.systemd_health_driver import SystemdHealthDriver
        health_driver = SystemdHealthDriver(self.manifest)
        l1_result = health_driver.check(layer=1)
        if not l1_result.ok:
            rollback_result = self._do_rollback(backup_path, service_name)
            rc = 1 if rollback_result == "success" else 2
            return DeployResult(ok=False, exit_code=rc, deploy_result="failed",
                project_id=project_id, zouzhe_id=self.zouzhe_id,
                from_commit=current_sha, to_commit=target_sha,
                backup_path=backup_path,
                error="Health check Layer 1 failed", step_failed="health_check_layer1",
                rollback_triggered=True, rollback_result=rollback_result,
                health_check={"layer1_passed": False, "checks": l1_result.checks})

        l2_result = health_driver.check(layer=2)
        if not l2_result.ok:
            rollback_result = self._do_rollback(backup_path, service_name)
            rc = 1 if rollback_result == "success" else 2
            return DeployResult(ok=False, exit_code=rc, deploy_result="failed",
                project_id=project_id, zouzhe_id=self.zouzhe_id,
                from_commit=current_sha, to_commit=target_sha,
                backup_path=backup_path,
                error="Health check Layer 2 failed", step_failed="health_check_layer2",
                rollback_triggered=True, rollback_result=rollback_result,
                health_check={"layer1_passed": True, "layer2_passed": False, "checks": l2_result.checks})

        # Step 6: 写入 latest-backup.json 更新 SHA 记录
        self._save_deployed_sha(project_id, backup_dir, target_sha, backup_path, self.zouzhe_id)

        duration = time.time() - start_time
        return DeployResult(ok=True, exit_code=0, deploy_result="success",
            project_id=project_id, zouzhe_id=self.zouzhe_id,
            from_commit=current_sha, to_commit=target_sha,
            backup_path=backup_path, duration_sec=duration,
            health_check={
                "layer1_passed": True, "layer2_passed": True,
                "checks": [c.get("name", "") for c in l1_result.checks + l2_result.checks]
            })

    def create_backup(self) -> str:
        spec = self.manifest.get("spec", {})
        deploy_spec = spec.get("deploy", {})
        project_id = self.manifest.get("metadata", {}).get("project_id", "")
        binary_dest = deploy_spec.get("binary_dest", "")
        backup_dir = os.path.join(CHAOTING_DIR, "backups")
        return self.create_backup_for(project_id, binary_dest, backup_dir, "")

    def create_backup_for(self, project_id: str, binary_dest: str, backup_dir: str, current_sha: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_path = os.path.join(backup_dir, f"{project_id}-backup-{ts}")
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(binary_dest, backup_path)

        # 保留最近 N 个快照
        spec = self.manifest.get("spec", {})
        rollback_spec = spec.get("rollback", {})
        keep_versions = rollback_spec.get("keep_versions", 3)
        self._prune_old_backups(backup_dir, project_id, keep_versions)

        return backup_path

    def rollback(self, backup_path: str) -> bool:
        spec = self.manifest.get("spec", {})
        deploy_spec = spec.get("deploy", {})
        service_name = deploy_spec.get("service_name", "")
        binary_dest = deploy_spec.get("binary_dest", "")

        if not backup_path or not os.path.exists(backup_path):
            # Try latest-backup.json
            project_id = self.manifest.get("metadata", {}).get("project_id", "")
            backup_dir = os.path.join(CHAOTING_DIR, "backups")
            meta_path = os.path.join(backup_dir, "latest-backup.json")
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                backup_path = meta.get("backup_path", "")

        if not backup_path or not os.path.exists(backup_path):
            return False

        try:
            shutil.copy2(backup_path, binary_dest)
            if service_name:
                subprocess.run(
                    ["systemctl", "--user", "restart", service_name],
                    check=True, capture_output=True, timeout=30
                )
            return True
        except Exception:
            return False

    def _do_rollback(self, backup_path: str, service_name: str) -> str:
        """执行回滚，返回 "success" 或 "failed"。"""
        try:
            if self.rollback(backup_path):
                return "success"
            return "failed"
        except Exception:
            return "failed"

    def _get_deployed_sha(self, project_id: str, backup_dir: str) -> str:
        meta_path = os.path.join(backup_dir, "latest-backup.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                return meta.get("commit", "")
            except Exception:
                pass
        return ""

    def _save_deployed_sha(self, project_id: str, backup_dir: str, sha: str, backup_path: str, zouzhe_id: str):
        meta = {
            "project_id": project_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backup_path": backup_path,
            "commit": sha,
            "deploy_zouzhe_id": zouzhe_id,
        }
        meta_path = os.path.join(backup_dir, "latest-backup.json")
        tmp_path = meta_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp_path, meta_path)  # 原子性替换

    def _prune_old_backups(self, backup_dir: str, project_id: str, keep_versions: int):
        prefix = f"{project_id}-backup-"
        backups = sorted([
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith(prefix) and not f.endswith(".json")
        ])
        while len(backups) > keep_versions:
            oldest = backups.pop(0)
            try:
                os.remove(oldest)
            except Exception:
                pass
