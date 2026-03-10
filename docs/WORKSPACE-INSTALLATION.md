# Chaoting Workspace 隔离安装指南

本指南说明如何将多个独立的 Chaoting 实例部署到不同的 OpenClaw workspace，实现完全的数据和服务隔离。

---

## 概念

**单部署（默认）**：一个 Chaoting 实例，数据存放在代码仓库根目录。

**Workspace 隔离部署**：多个 Chaoting 实例，每个绑定到一个 OpenClaw workspace，数据存放在 `{workspace}/.chaoting/`。

```
workspace-gongbu/
└── .chaoting/
    ├── chaoting.db      ← 独立数据库
    ├── logs/            ← 独立日志
    ├── sentinels/       ← 独立哨兵
    └── config.json      ← 可选配置覆盖

workspace-bingbu/
└── .chaoting/
    ├── chaoting.db      ← 完全独立，互不干扰
    ├── logs/
    └── sentinels/
```

---

## 快速安装

### 方法一：install.sh（推荐）

```bash
# 单部署（向后兼容，不指定 workspace）
./install.sh

# Workspace 隔离部署
./install.sh --workspace /path/to/workspace

# 示例：为 OpenClaw 的 gongbu workspace 安装
./install.sh --workspace ~/.themachine/workspace-gongbu

# 预览模式（不做任何变更）
./install.sh --dry-run --workspace ~/.themachine/workspace-gongbu
```

### 方法二：chaoting-workspace 管理工具

```bash
# 安装到指定 workspace
CHAOTING_DIR=/path/to/chaoting-repo \
python3 src/chaoting-workspace install ~/.themachine/workspace-gongbu

# 查看所有已安装的 workspace
python3 src/chaoting-workspace list

# 查看状态
python3 src/chaoting-workspace status ~/.themachine/workspace-gongbu

# 卸载（保留数据）
python3 src/chaoting-workspace uninstall ~/.themachine/workspace-gongbu
```

---

## 多 Workspace 并行部署

```bash
# 安装 3 个独立的 Chaoting 实例
./install.sh --workspace ~/.themachine/workspace-openclaw
./install.sh --workspace ~/.themachine/workspace-beebot
./install.sh --workspace ~/.themachine/workspace-custom

# 查看所有实例
python3 src/chaoting-workspace list
```

每个实例将有独立的：
- systemd service（`chaoting-dispatcher-{name}.service`）
- DB（`{workspace}/.chaoting/chaoting.db`）
- 日志目录
- 进程 PID

---

## 配置参数

### 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `CHAOTING_DIR` | Chaoting 代码仓库路径 | `/home/user/chaoting` |
| `CHAOTING_WORKSPACE` | 激活 workspace 隔离模式 | `~/.themachine/workspace-gongbu` |
| `OPENCLAW_CLI` | OpenClaw CLI 路径 | `~/.nvm/.../bin/themachine` |
| `OPENCLAW_STATE_DIR` | OpenClaw 状态目录 | `~/.themachine` |
| `DISCORD_FALLBACK_CHANNEL_ID` | Discord fallback channel | `1479959995520127160` |

### config.json 文件

workspace 安装后，可以在 `{workspace}/.chaoting/config.json` 中覆盖配置：

```json
{
  "db_path": "/custom/path/chaoting.db",
  "log_dir": "/custom/logs",
  "sentinel_dir": "/custom/sentinels"
}
```

---

## 管理命令

### 查看服务状态

```bash
# 查看所有 workspace
python3 src/chaoting-workspace status

# 查看指定 workspace
python3 src/chaoting-workspace status ~/.themachine/workspace-gongbu

# systemctl 直接查看
systemctl --user status chaoting-dispatcher-workspace-gongbu
```

### 服务控制

```bash
# 重启
systemctl --user restart chaoting-dispatcher-workspace-gongbu

# 停止
systemctl --user stop chaoting-dispatcher-workspace-gongbu

# 查看日志
journalctl --user -u chaoting-dispatcher-workspace-gongbu -f
```

### Chaoting CLI（指定 workspace）

使用 `CHAOTING_WORKSPACE` 环境变量指向目标 workspace：

```bash
# 在指定 workspace 中创建奏折
CHAOTING_WORKSPACE=~/.themachine/workspace-gongbu \
  /path/to/chaoting/src/chaoting new '任务标题'

# 查看指定 workspace 的奏折
CHAOTING_WORKSPACE=~/.themachine/workspace-beebot \
  /path/to/chaoting/src/chaoting pull ZZ-20260310-001
```

---

## 迁移旧部署

将现有的单部署 Chaoting 迁移到 workspace 模式：

```bash
# 预览（dry-run）
python3 src/chaoting-workspace migrate \
  /path/to/old-chaoting-repo \
  ~/.themachine/workspace-main \
  --force  # 如果目标已有 DB，需要此参数

# 完成迁移后，停止旧服务
systemctl --user disable --now chaoting-dispatcher

# 启动新的 workspace 服务
python3 src/chaoting-workspace install ~/.themachine/workspace-main
```

---

## 卸载

```bash
# 停止并移除 systemd service（保留数据）
python3 src/chaoting-workspace uninstall ~/.themachine/workspace-gongbu

# 完全清除数据
rm -rf ~/.themachine/workspace-gongbu/.chaoting
```

---

## 故障排查

### 服务无法启动

```bash
# 查看日志
journalctl --user -u chaoting-dispatcher-workspace-gongbu --no-pager -n 50

# 确认 CHAOTING_WORKSPACE 设置
systemctl --user cat chaoting-dispatcher-workspace-gongbu
```

### DB 未找到

```bash
# 手动初始化 DB
CHAOTING_DIR=/path/to/chaoting \
CHAOTING_WORKSPACE=~/.themachine/workspace-gongbu \
  python3 /path/to/chaoting/src/init_db.py
```

### 多个 workspace 冲突

Workspace service 名称由 workspace 目录名决定。若两个 workspace 目录名相同（不同父目录），会产生 service 名冲突。解决方案：

```bash
# 确认 service 名称
python3 src/chaoting-workspace status
# 手动重命名 workspace 目录，或使用 CHAOTING_WORKSPACE 配合不同的 service 名
```

---

## 运行测试

```bash
# 运行 workspace 隔离测试（17 个测试用例）
python3 tests/test_workspace_isolation.py

# 使用 pytest（如已安装）
python3 -m pytest tests/test_workspace_isolation.py -v
```
