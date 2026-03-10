#!/usr/bin/env python3
"""
test_workspace_isolation.py — ZZ-20260310-016 workspace 隔离测试

覆盖：
- 向后兼容：无 CHAOTING_WORKSPACE 时行为不变
- workspace 模式：DB/logs/sentinels 隔离到 {workspace}/.chaoting/
- 两个并行 workspace 完全独立（不互相干扰）
- CHAOTING_DB_PATH 显式覆盖优先级最高
- config.py ChaotingConfig 正确性

运行：
    cd /home/tetter/self-project/chaoting
    CHAOTING_DIR=$(pwd) python3 tests/test_workspace_isolation.py
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import importlib.machinery
import importlib.util
from pathlib import Path

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def _load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


# ──────────────────────────────────────────────────────────
# 测试 1：ChaotingConfig（config.py）
# ──────────────────────────────────────────────────────────

class TestChaotingConfig(unittest.TestCase):
    """config.py ChaotingConfig 逻辑"""

    def setUp(self):
        # 清理 config singleton
        if "config" in sys.modules:
            del sys.modules["config"]
        # 清理相关 env vars
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def _load_config(self):
        return _load_module("config", os.path.join(_src, "config.py"))

    def test_no_workspace_data_dir_equals_chaoting_dir(self):
        """无 CHAOTING_WORKSPACE 时 data_dir == chaoting_dir（向后兼容）"""
        config_mod = self._load_config()
        cfg = config_mod.ChaotingConfig(chaoting_dir="/tmp/test-chaoting")
        self.assertEqual(cfg.data_dir, "/tmp/test-chaoting")
        self.assertEqual(cfg.service_name, "chaoting-dispatcher")

    def test_workspace_sets_data_dir_under_chaoting(self):
        """设置 workspace 后 data_dir = {workspace}/.chaoting"""
        config_mod = self._load_config()
        cfg = config_mod.ChaotingConfig(
            chaoting_dir="/opt/chaoting",
            workspace="/home/user/project-a",
        )
        self.assertEqual(cfg.data_dir, "/home/user/project-a/.chaoting")
        self.assertEqual(cfg.db_path, "/home/user/project-a/.chaoting/chaoting.db")
        self.assertEqual(cfg.log_dir, "/home/user/project-a/.chaoting/logs")
        self.assertEqual(cfg.sentinel_dir, "/home/user/project-a/.chaoting/sentinels")

    def test_workspace_service_name(self):
        """workspace 模式下 service_name 包含 workspace 名（空格转连字符）"""
        config_mod = self._load_config()
        cfg = config_mod.ChaotingConfig(workspace="/home/user/My Project")
        # config.py 将空格转为连字符（systemd-safe）
        self.assertEqual(cfg.service_name, "chaoting-dispatcher-my-project")

    def test_env_var_workspace(self):
        """CHAOTING_WORKSPACE env var 被 ChaotingConfig 读取"""
        os.environ["CHAOTING_WORKSPACE"] = "/tmp/ws-env-test"
        config_mod = self._load_config()
        try:
            cfg = config_mod.ChaotingConfig(chaoting_dir="/opt/chaoting")
            self.assertEqual(cfg.workspace, "/tmp/ws-env-test")
            self.assertEqual(cfg.data_dir, "/tmp/ws-env-test/.chaoting")
        finally:
            os.environ.pop("CHAOTING_WORKSPACE", None)

    def test_db_path_without_workspace(self):
        """无 workspace 时 db_path = {chaoting_dir}/chaoting.db"""
        config_mod = self._load_config()
        cfg = config_mod.ChaotingConfig(chaoting_dir="/opt/chaoting")
        self.assertEqual(cfg.db_path, "/opt/chaoting/chaoting.db")

    def test_ensure_dirs_creates_data_dir(self):
        """ensure_dirs() 创建 data_dir/logs/sentinels"""
        tmpdir = tempfile.mkdtemp()
        try:
            ws = os.path.join(tmpdir, "myworkspace")
            os.makedirs(ws)
            config_mod = self._load_config()
            cfg = config_mod.ChaotingConfig(chaoting_dir="/opt/chaoting", workspace=ws)
            cfg.ensure_dirs()
            self.assertTrue(os.path.isdir(cfg.data_dir))
            self.assertTrue(os.path.isdir(cfg.log_dir))
            self.assertTrue(os.path.isdir(cfg.sentinel_dir))
        finally:
            shutil.rmtree(tmpdir)

    def test_write_config_json(self):
        """write_config_json() 写入 {data_dir}/config.json"""
        tmpdir = tempfile.mkdtemp()
        try:
            ws = os.path.join(tmpdir, "myworkspace")
            os.makedirs(ws)
            config_mod = self._load_config()
            cfg = config_mod.ChaotingConfig(chaoting_dir="/opt/chaoting", workspace=ws)
            cfg.ensure_dirs()
            path = cfg.write_config_json()
            self.assertTrue(os.path.exists(path))
            data = json.loads(Path(path).read_text())
            self.assertEqual(data["workspace"], ws)
            self.assertEqual(data["service_name"], cfg.service_name)
        finally:
            shutil.rmtree(tmpdir)


# ──────────────────────────────────────────────────────────
# 测试 2：DB 路径隔离
# ──────────────────────────────────────────────────────────

class TestDBPathIsolation(unittest.TestCase):
    """DB_PATH 根据 CHAOTING_WORKSPACE 正确路由"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def _reload_init_db(self):
        if "init_db" in sys.modules:
            del sys.modules["init_db"]
        return _load_module("init_db", os.path.join(_src, "init_db.py"))

    def test_no_workspace_db_in_chaoting_dir(self):
        """无 workspace：DB 在 CHAOTING_DIR/chaoting.db"""
        os.environ["CHAOTING_DIR"] = self.tmpdir
        mod = self._reload_init_db()
        self.assertEqual(mod.DB_PATH, os.path.join(self.tmpdir, "chaoting.db"))

    def test_workspace_db_in_workspace_chaoting(self):
        """CHAOTING_WORKSPACE 设置后：DB 在 {workspace}/.chaoting/chaoting.db"""
        ws = os.path.join(self.tmpdir, "workspace-a")
        os.makedirs(ws)
        os.environ["CHAOTING_DIR"] = self.tmpdir
        os.environ["CHAOTING_WORKSPACE"] = ws
        mod = self._reload_init_db()
        expected = os.path.join(ws, ".chaoting", "chaoting.db")
        self.assertEqual(mod.DB_PATH, expected)

    def test_explicit_db_path_overrides_workspace(self):
        """CHAOTING_DB_PATH 显式覆盖优先级最高"""
        ws = os.path.join(self.tmpdir, "workspace-b")
        os.makedirs(ws)
        custom_db = os.path.join(self.tmpdir, "custom.db")
        os.environ["CHAOTING_DIR"] = self.tmpdir
        os.environ["CHAOTING_WORKSPACE"] = ws
        os.environ["CHAOTING_DB_PATH"] = custom_db
        mod = self._reload_init_db()
        self.assertEqual(mod.DB_PATH, custom_db)

    def test_init_db_creates_tables_in_workspace(self):
        """init_db.py 初始化 workspace DB（带所有 V0.4 字段）"""
        ws = os.path.join(self.tmpdir, "workspace-init")
        chaoting_dir = os.path.join(self.tmpdir, "src")
        os.makedirs(ws)
        ws_data = os.path.join(ws, ".chaoting")
        os.makedirs(ws_data)

        os.environ["CHAOTING_DIR"] = chaoting_dir
        os.environ["CHAOTING_WORKSPACE"] = ws
        mod = self._reload_init_db()

        # 初始化 DB
        mod.init_db()

        db_path = os.path.join(ws_data, "chaoting.db")
        self.assertTrue(os.path.exists(db_path), f"DB not created at {db_path}")

        db = sqlite3.connect(db_path)
        cols = {c[1] for c in db.execute("PRAGMA table_info(zouzhe)").fetchall()}
        db.close()

        # 验证 V0.4 字段存在
        for col in ["revise_limit", "revise_timeout_days", "last_revise_reason",
                    "suspended_at", "total_revise_rounds", "planning_version"]:
            self.assertIn(col, cols, f"Column {col} missing from workspace DB")


# ──────────────────────────────────────────────────────────
# 测试 3：两个 workspace 并行隔离
# ──────────────────────────────────────────────────────────

class TestTwoWorkspacesParallel(unittest.TestCase):
    """两个 workspace 完全独立，互不干扰"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ws_a = os.path.join(self.tmpdir, "workspace-a")
        self.ws_b = os.path.join(self.tmpdir, "workspace-b")
        os.makedirs(os.path.join(self.ws_a, ".chaoting"))
        os.makedirs(os.path.join(self.ws_b, ".chaoting"))
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def _init_db(self, workspace: str) -> str:
        """初始化 workspace DB，返回 db_path"""
        if "init_db" in sys.modules:
            del sys.modules["init_db"]
        os.environ["CHAOTING_DIR"] = self.tmpdir
        os.environ["CHAOTING_WORKSPACE"] = workspace
        os.environ.pop("CHAOTING_DB_PATH", None)
        mod = _load_module("init_db", os.path.join(_src, "init_db.py"))
        mod.init_db()
        return mod.DB_PATH

    def test_two_workspaces_have_separate_dbs(self):
        """两个 workspace 各有独立的 chaoting.db"""
        db_a = self._init_db(self.ws_a)
        db_b = self._init_db(self.ws_b)

        self.assertEqual(db_a, os.path.join(self.ws_a, ".chaoting", "chaoting.db"))
        self.assertEqual(db_b, os.path.join(self.ws_b, ".chaoting", "chaoting.db"))
        self.assertNotEqual(db_a, db_b)
        self.assertTrue(os.path.exists(db_a))
        self.assertTrue(os.path.exists(db_b))

    def test_writes_to_ws_a_not_visible_in_ws_b(self):
        """在 ws_a 写入的奏折在 ws_b 中不可见"""
        db_a = self._init_db(self.ws_a)
        db_b = self._init_db(self.ws_b)

        # 向 ws_a 写入一条奏折
        conn_a = sqlite3.connect(db_a)
        conn_a.execute(
            "INSERT INTO zouzhe (id, title, description, state, priority, "
            "assigned_agent, revise_count, review_required, timeout_sec) "
            "VALUES ('ZZ-WS-A-001', 'Test A', 'desc', 'planning', 'high', "
            "'bingbu', 0, 2, 3600)"
        )
        conn_a.commit()
        conn_a.close()

        # ws_b 中不应存在此奏折
        conn_b = sqlite3.connect(db_b)
        row = conn_b.execute("SELECT id FROM zouzhe WHERE id='ZZ-WS-A-001'").fetchone()
        conn_b.close()
        self.assertIsNone(row, "ws_a 的奏折不应出现在 ws_b 中")

    def test_same_id_in_different_workspaces(self):
        """两个 workspace 可以有相同 zouzhe_id，互不干扰"""
        db_a = self._init_db(self.ws_a)
        db_b = self._init_db(self.ws_b)
        shared_id = "ZZ-SHARED-001"

        for db_path, title in [(db_a, "WS-A Title"), (db_b, "WS-B Title")]:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO zouzhe (id, title, description, state, priority, "
                "assigned_agent, revise_count, review_required, timeout_sec) "
                "VALUES (?, ?, 'desc', 'planning', 'high', 'bingbu', 0, 2, 3600)",
                (shared_id, title),
            )
            conn.commit()
            conn.close()

        conn_a = sqlite3.connect(db_a)
        title_a = conn_a.execute("SELECT title FROM zouzhe WHERE id=?", (shared_id,)).fetchone()[0]
        conn_a.close()

        conn_b = sqlite3.connect(db_b)
        title_b = conn_b.execute("SELECT title FROM zouzhe WHERE id=?", (shared_id,)).fetchone()[0]
        conn_b.close()

        self.assertEqual(title_a, "WS-A Title")
        self.assertEqual(title_b, "WS-B Title")
        self.assertNotEqual(title_a, title_b)


# ──────────────────────────────────────────────────────────
# 测试 4：向后兼容性
# ──────────────────────────────────────────────────────────

class TestBackwardCompatibility(unittest.TestCase):
    """不设 CHAOTING_WORKSPACE 时，行为与原来完全一致"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH"]:
            os.environ.pop(k, None)
        os.environ["CHAOTING_DIR"] = self.tmpdir

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        for k in ["CHAOTING_WORKSPACE", "CHAOTING_DB_PATH", "CHAOTING_DIR"]:
            os.environ.pop(k, None)

    def test_legacy_db_path_in_chaoting_dir(self):
        """向后兼容：DB 在 CHAOTING_DIR/chaoting.db"""
        if "init_db" in sys.modules:
            del sys.modules["init_db"]
        mod = _load_module("init_db", os.path.join(_src, "init_db.py"))
        self.assertEqual(mod.DB_PATH, os.path.join(self.tmpdir, "chaoting.db"))

    def test_legacy_logs_in_chaoting_dir(self):
        """向后兼容：logs 在 CHAOTING_DIR/logs"""
        if "chaoting_log" in sys.modules:
            del sys.modules["chaoting_log"]
        mod = _load_module("chaoting_log", os.path.join(_src, "chaoting_log.py"))
        self.assertEqual(mod.LOGS_DIR, os.path.join(self.tmpdir, "logs"))

    def test_no_chaoting_dir_created_in_legacy(self):
        """向后兼容：无 workspace 时不创建 .chaoting/ 目录"""
        dotchaoting = os.path.join(self.tmpdir, ".chaoting")
        self.assertFalse(os.path.exists(dotchaoting),
                         f".chaoting/ should not be created in legacy mode")


# ──────────────────────────────────────────────────────────
# 测试 5：install.sh --dry-run（bash 语法检查）
# ──────────────────────────────────────────────────────────

class TestInstallShSyntax(unittest.TestCase):
    """install.sh 语法正确"""

    def test_install_sh_bash_syntax(self):
        """install.sh bash -n 语法检查通过"""
        import subprocess
        install_sh = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "install.sh"
        )
        result = subprocess.run(
            ["bash", "-n", install_sh],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"install.sh syntax error: {result.stderr}")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
