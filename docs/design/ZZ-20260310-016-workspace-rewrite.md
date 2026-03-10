# ZZ-20260310-016 Workspace 隔离部署 — 兵部重写方案

> 制定日期：2026-03-10 | 依据奏折：ZZ-20260310-016

## 一、背景与工部对比

工部（ZZ-20260310-012）实现了 workspace 隔离，但 PR 未合并到 master，且在 ZZ-014/015
的大量更改之前，存在 merge 冲突风险。

兵部重写在最新 master（包含 ZZ-014/015 所有改动）基础上实现，与现有代码完全兼容。

### 兵部 vs 工部差异

| 方面 | 工部实现 | 兵部重写 |
|------|---------|---------|
| 基础分支 | 旧 master（ZZ-014/015 前）| 最新 master（已含 gate_reject/planning_version 等）|
| 核心逻辑 | 相同（采纳工部设计）| 相同，无需重新发明轮子 |
| `src/config.py` | 原创 | 直接沿用（工部设计良好）|
| `src/chaoting-workspace` | 原创 | 直接沿用 |
| 兼容性 | ZZ-014/015 冲突 | 无冲突 |
| 测试覆盖 | 17 tests | 18 tests |

## 二、核心机制

### 2.1 路径隔离（`CHAOTING_WORKSPACE` env）

```
无 workspace（向后兼容）：
  DB:       {CHAOTING_DIR}/chaoting.db
  Logs:     {CHAOTING_DIR}/logs/
  Sentinel: {CHAOTING_DIR}/sentinels/

workspace 模式：
  DB:       {CHAOTING_WORKSPACE}/.chaoting/chaoting.db
  Logs:     {CHAOTING_WORKSPACE}/.chaoting/logs/
  Sentinel: {CHAOTING_WORKSPACE}/.chaoting/sentinels/
  Service:  chaoting-dispatcher-{workspace-name}.service
```

### 2.2 优先级链

```
CHAOTING_DB_PATH（显式覆盖）
    > CHAOTING_WORKSPACE（workspace mode）
    > CHAOTING_DIR（legacy mode）
    > auto-detect（repo root）
```

### 2.3 两个并行 workspace 示例

```bash
# workspace A
./install.sh --workspace /home/user/project-a
CHAOTING_WORKSPACE=/home/user/project-a chaoting list

# workspace B
./install.sh --workspace /home/user/project-b
CHAOTING_WORKSPACE=/home/user/project-b chaoting list

# 两个 dispatcher 独立运行
systemctl --user status chaoting-dispatcher-project-a
systemctl --user status chaoting-dispatcher-project-b
```

## 三、变更文件

| 文件 | 变更 |
|------|------|
| `src/config.py` | 新增（ChaotingConfig 单一路径配置来源）|
| `src/chaoting` | `CHAOTING_DATA_DIR` + `DB_PATH` workspace-aware |
| `src/dispatcher.py` | `CHAOTING_DATA_DIR` + `DB_PATH` workspace-aware |
| `src/init_db.py` | `DB_PATH` workspace-aware |
| `src/chaoting_log.py` | `LOGS_DIR` workspace-aware |
| `src/chaoting-workspace` | 新增（workspace 管理 CLI）|
| `install.sh` | `--workspace` 参数 + 动态 SERVICE_NAME |
| `tests/test_workspace_isolation.py` | 新增（18 测试）|

## 四、向后兼容

- 不设 `CHAOTING_WORKSPACE`：行为与之前完全一致
- 现有 systemd service `chaoting-dispatcher` 不受影响
- 现有 DB、logs、sentinels 路径不变

## 五、验收标准 ✅

✅ 工部改动未合并 master，无需 revert（branch 级别隔离）  
✅ 兵部重写基于最新 master，无 merge 冲突  
✅ 2 workspace 并行测试通过（互不干扰）  
✅ 向后兼容验证（3 tests）  
✅ config.py 单一配置来源  
✅ 18/18 测试通过
