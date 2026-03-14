import os
import time
import json
import re

import yaml
import jsonschema

CHAOTING_DIR = os.environ.get("CHAOTING_DIR", "")


class ManifestNotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class SecretResolutionError(Exception):
    pass


class ManifestLoader:
    _cache: dict = {}  # {project_id: (manifest, expire_at)}
    CACHE_TTL_SEC = 60

    @classmethod
    def load(cls, project_id: str) -> dict:
        # 60s TTL cache
        now = time.time()
        cached = cls._cache.get(project_id)
        if cached and cached[1] > now:
            return cached[0]
        path = cls._manifest_path(project_id)
        if not os.path.exists(path):
            raise ManifestNotFoundError(f"No manifest for project: {project_id}")
        with open(path) as f:
            raw = yaml.safe_load(f)
        cls._validate(raw)
        manifest = cls._normalize(raw)
        cls._resolve_secrets(manifest)  # ${ENV_VAR} 替换
        cls._cache[project_id] = (manifest, now + cls.CACHE_TTL_SEC)
        return manifest

    @classmethod
    def invalidate_cache(cls, project_id: str):
        cls._cache.pop(project_id, None)

    @classmethod
    def _manifest_path(cls, project_id: str) -> str:
        return os.path.join(CHAOTING_DIR, "projects", project_id, "manifest.yaml")

    @classmethod
    def _validate(cls, raw: dict):
        schema_path = os.path.join(CHAOTING_DIR, "projects", ".schema", "manifest.schema.json")
        if not os.path.exists(schema_path):
            raise ValidationError(f"Schema not found: {schema_path}")
        with open(schema_path) as f:
            schema = json.load(f)
        try:
            jsonschema.validate(raw, schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"manifest validation failed: {e.message}") from e

    @classmethod
    def _normalize(cls, raw: dict) -> dict:
        spec = raw.get("spec", {})
        deploy = spec.get("deploy", {})
        deploy.setdefault("timeout", 300)
        deploy.setdefault("idempotency", "sha256")
        deploy.setdefault("requires_restart", True)
        health = spec.get("health", {})
        health.setdefault("check_interval_sec", 30)
        health.setdefault("layer1_timeout_sec", 5)
        health.setdefault("layer2_timeout_sec", 30)
        health.setdefault("layer3_timeout_sec", 120)
        logs = spec.get("logs", {})
        logs.setdefault("lines", 100)
        return raw

    @classmethod
    def _resolve_secrets(cls, obj):
        """递归替换 ${ENV_VAR} 占位符，缺失抛 SecretResolutionError"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    obj[k] = cls._replace_env_vars(v)
                else:
                    cls._resolve_secrets(v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str):
                    obj[i] = cls._replace_env_vars(v)
                else:
                    cls._resolve_secrets(v)

    @classmethod
    def _replace_env_vars(cls, s: str) -> str:
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(m):
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise SecretResolutionError(f"Environment variable not set: {var}")
            return val

        return pattern.sub(replacer, s)
