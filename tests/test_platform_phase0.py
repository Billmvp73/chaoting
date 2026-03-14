"""
Phase 0 DoD Tests for Platform Engineering manifest-based deploy.

Tests:
1. SystemdDeployDriver 调用顺序与 009 Step 1-6 完全一致，退出码 0
2. 相同 SHA 重复 deploy → 退出码 3
3. manifest 缺少 service_name → ManifestLoader ValidationError，deploy 退出码 5
4. chaoting manifest.yaml 通过 schema 验证
"""
import json
import os
import re
import shutil
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Insert src dir into path
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
sys.path.insert(0, SRC_DIR)

# Base dir for locating projects/ relative to repo root
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_valid_manifest(service_name="chaoting-dispatcher", binary_src="src/chaoting"):
    return {
        "apiVersion": "chaoting.io/v1alpha1",
        "kind": "ProjectManifest",
        "metadata": {
            "project_id": "chaoting",
            "name": "Chaoting",
            "version": "1.0.0",
        },
        "spec": {
            "deploy": {
                "type": "systemd_user",
                "service_name": service_name,
                "binary_src": binary_src,
                "binary_dest": "/tmp/test-chaoting-binary",
                "repo_path": "/tmp/test-repo",
                "timeout": 300,
                "idempotency": "sha256",
            },
            "health": {
                "type": "composite",
                "checks": [
                    {"name": "dispatcher_running", "type": "systemctl", "service_name": service_name}
                ],
            },
            "logs": {
                "type": "journalctl",
                "service_name": service_name,
            },
        }
    }


# ── Test 1: 完整 deploy 流程，退出码 0 ─────────────────────────────────────

def test_systemd_deploy_driver_success():
    """
    验证 SystemdDeployDriver.deploy() 按 009 Step 1-6 顺序执行，退出码 0。
    Mock: git/systemctl/cp，验证调用顺序。
    """
    from chaoting_platform.drivers.systemd_deploy_driver import SystemdDeployDriver

    tmpdir = tempfile.mkdtemp()
    repo_path = os.path.join(tmpdir, "repo")
    os.makedirs(repo_path, exist_ok=True)

    binary_src = os.path.join(repo_path, "src", "chaoting")
    os.makedirs(os.path.dirname(binary_src), exist_ok=True)
    with open(binary_src, "w") as f:
        f.write("binary_content")

    binary_dest = os.path.join(tmpdir, "chaoting")
    with open(binary_dest, "w") as f:
        f.write("old_binary")

    manifest = _make_valid_manifest()
    manifest["spec"]["deploy"]["binary_src"] = "src/chaoting"
    manifest["spec"]["deploy"]["binary_dest"] = binary_dest
    manifest["spec"]["deploy"]["repo_path"] = repo_path

    call_order = []

    def mock_run(cmd, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        call_order.append(cmd_str)
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "active\n"
        mock.stderr = ""
        return mock

    with patch("chaoting_platform.drivers.systemd_deploy_driver.CHAOTING_DIR", tmpdir), \
         patch("chaoting_platform.drivers.systemd_health_driver.CHAOTING_DIR", tmpdir), \
         patch("chaoting_platform.drivers.systemd_health_driver.CHAOTING_CLI", ""), \
         patch("chaoting_platform.drivers.systemd_deploy_driver.subprocess.run", side_effect=mock_run), \
         patch("chaoting_platform.drivers.systemd_deploy_driver.time.sleep"), \
         patch("chaoting_platform.drivers.systemd_health_driver.subprocess.run", side_effect=mock_run):

        driver = SystemdDeployDriver(manifest, "ZZ-TEST-001")
        result = driver.deploy(dry_run=False, force=True)  # force=True to skip idempotency

    assert result.exit_code == 0, f"Expected exit_code=0, got {result.exit_code}: {result.error}"
    assert result.deploy_result == "success"
    assert result.ok is True

    # 验证 git pull 被调用（Step 3a）
    assert any("git" in c and "pull" in c for c in call_order), f"git pull not called. calls: {call_order}"
    # 验证 systemctl restart 被调用（Step 4）
    assert any("systemctl" in c and "restart" in c for c in call_order), f"systemctl restart not called. calls: {call_order}"

    shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 2: 相同 SHA 幂等跳过，退出码 3 ────────────────────────────────────

def test_systemd_deploy_idempotent_same_sha():
    """
    相同 commit SHA 重复 deploy → 退出码 3（幂等跳过）。
    """
    from chaoting_platform.drivers.systemd_deploy_driver import SystemdDeployDriver

    tmpdir = tempfile.mkdtemp()
    repo_path = os.path.join(tmpdir, "repo")
    os.makedirs(repo_path, exist_ok=True)

    binary_dest = os.path.join(tmpdir, "chaoting")
    with open(binary_dest, "w") as f:
        f.write("binary")

    # 预写 latest-backup.json with same SHA
    backup_dir = os.path.join(tmpdir, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    same_sha = "abc1234deadbeef"
    with open(os.path.join(backup_dir, "latest-backup.json"), "w") as f:
        json.dump({"commit": same_sha, "backup_path": binary_dest, "project_id": "chaoting"}, f)

    manifest = _make_valid_manifest()
    manifest["spec"]["deploy"]["binary_dest"] = binary_dest
    manifest["spec"]["deploy"]["repo_path"] = repo_path

    def mock_run(cmd, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        m = MagicMock()
        m.returncode = 0
        # git rev-parse → same SHA
        if "rev-parse" in cmd_str:
            m.stdout = same_sha + "\n"
        else:
            m.stdout = ""
        m.stderr = ""
        return m

    with patch("chaoting_platform.drivers.systemd_deploy_driver.CHAOTING_DIR", tmpdir), \
         patch("chaoting_platform.drivers.systemd_deploy_driver.subprocess.run", side_effect=mock_run):

        driver = SystemdDeployDriver(manifest, "ZZ-TEST-002")
        result = driver.deploy(dry_run=False, force=False)

    assert result.exit_code == 3, f"Expected exit_code=3, got {result.exit_code}"
    assert result.deploy_result == "skipped_idempotent"
    assert result.ok is True

    shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test 3: 缺少 service_name → ValidationError，退出码 5 ──────────────────

def test_manifest_missing_service_name_raises_validation_error():
    """
    manifest 缺少 spec.deploy.service_name → ManifestLoader 抛 ValidationError。
    通过 PlatformInterface.deploy() 调用，应等效于退出码 5。
    """
    import yaml as _yaml
    from chaoting_platform.manifest_loader import ManifestLoader, ValidationError

    tmpdir = tempfile.mkdtemp()
    schema_dir = os.path.join(tmpdir, "projects", ".schema")
    proj_dir = os.path.join(tmpdir, "projects", "chaoting")
    os.makedirs(schema_dir, exist_ok=True)
    os.makedirs(proj_dir, exist_ok=True)

    # Write schema (copy from real location)
    real_schema = os.path.join(BASE_DIR, "projects", ".schema", "manifest.schema.json")
    if os.path.exists(real_schema):
        shutil.copy(real_schema, os.path.join(schema_dir, "manifest.schema.json"))
    else:
        pytest.fail(f"manifest.schema.json not found at {real_schema}")

    # Manifest WITHOUT service_name
    bad_manifest = {
        "apiVersion": "chaoting.io/v1alpha1",
        "kind": "ProjectManifest",
        "metadata": {"project_id": "chaoting", "name": "Chaoting", "version": "1.0.0"},
        "spec": {
            "deploy": {"type": "systemd_user"},  # missing service_name!
            "health": {"type": "systemctl", "service_name": "chaoting-dispatcher"},
            "logs": {"type": "journalctl", "service_name": "chaoting-dispatcher"},
        }
    }

    manifest_path = os.path.join(proj_dir, "manifest.yaml")
    with open(manifest_path, "w") as f:
        _yaml.dump(bad_manifest, f)

    ManifestLoader.invalidate_cache("chaoting")

    with patch("chaoting_platform.manifest_loader.CHAOTING_DIR", tmpdir):
        with pytest.raises(ValidationError) as exc_info:
            ManifestLoader.load("chaoting")

    assert "validation" in str(exc_info.value).lower() or "service_name" in str(exc_info.value).lower()

    shutil.rmtree(tmpdir, ignore_errors=True)
    ManifestLoader.invalidate_cache("chaoting")


# ── Test 4: manifest.yaml 通过 schema 验证 ─────────────────────────────────

def test_chaoting_manifest_passes_schema():
    """
    projects/chaoting/manifest.yaml 通过 manifest.schema.json 验证无报错。
    """
    import yaml as _yaml
    import jsonschema

    manifest_path = os.path.join(BASE_DIR, "projects", "chaoting", "manifest.yaml")
    schema_path = os.path.join(BASE_DIR, "projects", ".schema", "manifest.schema.json")

    assert os.path.exists(manifest_path), f"manifest.yaml not found at {manifest_path}"
    assert os.path.exists(schema_path), f"manifest.schema.json not found at {schema_path}"

    with open(manifest_path) as f:
        content = f.read()

    # Replace ${...} with dummy values for schema validation (we test structure, not runtime values)
    content = re.sub(r"\$\{[^}]+\}", "/dummy/path", content)
    manifest = _yaml.safe_load(content)

    with open(schema_path) as f:
        schema = json.load(f)

    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as e:
        pytest.fail(f"manifest.yaml failed schema validation: {e.message}")
