# Auto-Deploy 规格：deploy 命令 + 触发判断 + 回滚机制

> 奏折：ZZ-20260314-009  
> 撰写：礼部（libu）  
> 日期：2026-03-14  
> 配套文档：[p23-self-loop-design.md](./p23-self-loop-design.md) | [troubleshoot-decision-tree.md](./troubleshoot-decision-tree.md) | [roadmap-p23.md](./roadmap-p23.md)

---

## 一、设计目标

当 chaoting 自身的 PR 被 Squash Merge 到 master 后，系统能自动完成：
1. 将新版本 binary / 源码部署到生产位置
2. 重启 dispatcher 服务
3. 运行健康检查验证部署成功
4. 若失败，自动回滚到上一个已知正常版本

**关键约束**
- Deploy 是 **yushi-approve（Squash Merge）之后的自动触发动作**，不新增独立状态（见 p23-self-loop-design.md § 状态机扩展决策）
- Deploy 动作本身由 dispatcher 驱动，不依赖执行 agent 在线
- 回滚策略必须在 deploy 前确认可用

---

## 二、`chaoting deploy` 命令规格

### 2.1 命令签名

```bash
chaoting deploy ZZ-XXXXXXXX-NNN [OPTIONS]
```

### 2.2 参数表（完整）

| 参数 | 类型 | 必选 | 默认值 | 说明 |
|------|------|------|--------|------|
| `ZZ-XXXXXXXX-NNN` | positional | ✅ 必选 | — | 触发 deploy 的奏折 ID，用于日志追溯和幂等检测 |
| `--dry-run` | flag | 否 | false | 只打印操作步骤，不实际执行（Step 1-6 全部模拟）|
| `--skip-health` | flag | 否 | false | 跳过 Layer 1+2 健康检查（**仅限紧急回滚场景，正常 deploy 禁用**）|
| `--force` | flag | 否 | false | 强制重新 deploy，即使 commit SHA 与当前版本相同（覆盖幂等跳过） |
| `--timeout` | int（秒） | 否 | 300 | deploy 命令整体超时时间，超过后返回退出码 1（触发回滚） |
| `--backup-dir` | path | 否 | `${CHAOTING_DIR}/backups/` | 快照存储目录（覆盖默认路径） |

### 2.3 退出码枚举（完整）

| 退出码 | 含义 | 后续动作 |
|--------|------|---------|
| `0` | Deploy 成功（Layer 1+2 通过，deploy_state=deployed） | dispatch smoke test（异步） |
| `1` | 健康检查失败，已完成自动回滚 | 通知司礼监；下次 deploy 需人工触发 |
| `2` | 健康检查失败且**回滚也失败** | CRITICAL 告警；人工 SSH 恢复 |
| `3` | 幂等跳过：当前版本 commit SHA 与目标相同，且 `--force` 未设置 | deploy_state=skipped，state=done |
| `4` | 权限错误：无法 `systemctl --user restart` 或写入 binary 路径 | 告警；不自动重试 |
| `5` | 前置验证失败：repo 未更新、快照目录不可写、磁盘空间不足 | 告警；不执行任何部署操作 |

### 2.4 标准输出格式（JSON）

成功：
```json
{
  "ok": true,
  "exit_code": 0,
  "deploy_result": "success",
  "zouzhe_id": "ZZ-20260314-009",
  "from_commit": "prev_sha",
  "to_commit": "abc1234",
  "backup_path": "/path/to/chaoting-backup-20260314T042000",
  "deploy_duration_sec": 8.3,
  "health_check": {
    "layer1_passed": true,
    "layer2_passed": true,
    "checks": ["dispatcher_running", "db_writable", "cli_responsive", "pull_ok", "poll_ok"]
  }
}
```

幂等跳过（退出码 3）：
```json
{
  "ok": true,
  "exit_code": 3,
  "deploy_result": "skipped_idempotent",
  "zouzhe_id": "ZZ-20260314-009",
  "current_commit": "abc1234",
  "reason": "commit SHA matches deployed version; use --force to override"
}
```

失败（退出码 1）：
```json
{
  "ok": false,
  "exit_code": 1,
  "deploy_result": "failed",
  "zouzhe_id": "ZZ-20260314-009",
  "step_failed": "health_check_layer2",
  "error": "dispatcher not responding after 10s",
  "rollback_triggered": true,
  "rollback_result": "success",
  "rolled_back_to": "prev_sha"
}
```

---

## 三、执行步骤规格（顺序严格）

```
Step 1: 前置验证（Pre-flight）
  - 检查 chaoting.db 可写
  - 确认 repo master 是最新（git fetch + compare HEAD）
  - 确认上一版本快照已存在（否则先创建快照再继续）

Step 2: 创建回滚快照
  - 保存当前 binary 到 ${CHAOTING_DIR}/backups/chaoting-backup-<timestamp>
  - 保存 DB schema hash（不备份数据，避免状态回退）
  - 写入快照元数据：backups/latest-backup.json
    { "timestamp": "...", "binary_path": "...", "commit": "..." }

Step 3: 部署
  - git checkout master && git pull origin master（在 chaoting repo）
  - cp <CHAOTING_DIR>/src/chaoting <CHAOTING_CLI_PATH>（覆盖 CLI binary）
  - 如有 init_db 变更（检测 schema version），运行 migrate

Step 4: 重启服务
  - systemctl --user restart chaoting-dispatcher
  - 等待 5 秒（给 dispatcher 启动时间）

Step 5: 健康检查
  - 见 § 四（Health Check 规格）

Step 6: 写入部署记录
  - 写入 liuzhuan：action="deploy", remark="deploy ok, commit=<sha>"
  - 更新 zouzhe.deploy_state = "deployed"（进入健康检查流程）
```

完整 JSON 输出格式见 §2.4，失败时返回退出码 1/2（详见 §2.3）。

---

## 四、健康检查规格（Post-Deploy Smoke Test）

健康检查分三层，按顺序执行，任意层失败即触发回滚：

### Layer 1：基础存活检查（< 5秒）

```bash
# 检查 1：dispatcher 进程是否运行
systemctl --user is-active chaoting-dispatcher

# 检查 2：DB 可读写
chaoting health --check db

# 检查 3：CLI 可响应
chaoting version  # 返回版本号即通过
```

### Layer 2：功能性检查（< 30秒）

```bash
# 检查 4：pull 命令可正常返回（用最近一个 done 的奏折）
chaoting pull <LAST_DONE_ZZ_ID> --read-only

# 检查 5：dispatcher 能检测到 pending 任务（不 dispatch，只检测）
chaoting health --check dispatcher-poll
```

### Layer 3：端到端 Smoke Test（< 120秒，可选）

```bash
# 检查 6：创建测试奏折 → 规划 → done（全流程走一遍）
# 使用特殊前缀 ZZ-SMOKE-TEST，dispatcher 识别后快速流转
chaoting health --e2e-smoke
```

Layer 3 默认**不阻塞** deploy 完成（异步执行），结果写入日志供后续分析。  
若 Layer 3 失败，触发告警但**不自动回滚**（已通过 Layer 1+2 的 deploy 认为基本可用）。

---

## 五、触发判断：需要 Deploy vs 仅文档/配置变更

dispatcher 在检测到奏折进入 `done` 状态且 PR 已 merge 时，判断是否需要触发 deploy：

### 5.1 判断规则（优先级顺序）

```python
def needs_deploy(pr_diff_files: list[str], zouzhe: dict) -> bool:
    """
    判断是否需要重新部署 chaoting 本身
    """
    # 规则 1：plan 中显式标记 deploy=True（最高优先级）
    if zouzhe.get("plan", {}).get("requires_deploy", False):
        return True

    # 规则 2：修改了核心可执行文件
    DEPLOY_TRIGGER_PATTERNS = [
        "src/chaoting",        # CLI binary
        "src/dispatcher.py",   # 调度器
        "src/config.py",       # 配置
        "src/init_db.py",      # DB schema（需要 migrate）
    ]
    for f in pr_diff_files:
        for pattern in DEPLOY_TRIGGER_PATTERNS:
            if pattern in f:
                return True

    # 规则 3：仅文档/设计文档/SOUL.md 变更 → 不需要 deploy
    DOC_ONLY_PATTERNS = [
        "docs/", ".design_doc/", "SOUL.md", "AGENTS.md",
        ".md", "README"
    ]
    # 如果所有变更文件都匹配文档模式 → skip deploy
    if all(any(p in f for p in DOC_ONLY_PATTERNS) for f in pr_diff_files):
        return False

    # 默认：保守策略，触发 deploy
    return True
```

### 5.2 plan 中的 `requires_deploy` 字段

中书省（zhongshu）在规划时，若判断奏折涉及 chaoting 自身的代码变更，在 plan JSON 中标注：

```json
{
  "steps": [...],
  "target_agent": "bingbu",
  "requires_deploy": true,
  "deploy_notes": "修改了 dispatcher.py，需要重启服务"
}
```

---

## 六、回滚机制

### 6.1 回滚触发条件（完整枚举）

以下条件**触发自动回滚**：

| 触发事件 | 具体判断 | 自动回滚 | 通知司礼监 | 告警级别 |
|---------|---------|---------|---------|---------|
| Layer 1 失败：dispatcher 未运行 | `systemctl --user is-active chaoting-dispatcher` ≠ active | ✅ 立即 | ✅ | 🔴 高 |
| Layer 1 失败：DB 不可写 | `chaoting health --check db` 返回非零 | ✅ 立即 | ✅ | 🔴 高 |
| Layer 1 失败：CLI 无响应 | `chaoting version` 超时 5s | ✅ 立即 | ✅ | 🔴 高 |
| Layer 2 失败：pull 命令异常 | `chaoting pull <LAST_DONE> --read-only` 返回非零 | ✅ 立即 | ✅ | 🔴 高 |
| Layer 2 失败：dispatcher poll 无响应 | `chaoting health --check dispatcher-poll` 超时 30s | ✅ 立即 | ✅ | 🔴 高 |
| deploy 命令整体超时 | deploy 执行时间 > `--timeout`（默认 300s） | ✅ 立即 | ✅ | 🔴 高 |
| deploy 步骤中断（SIGKILL/SIGTERM） | 进程异常退出，deploy_state=deploying 悬空 | ✅（下次 dispatcher 检测） | ✅ | 🟡 中 |

以下条件**不触发回滚**（仅告警）：

| 事件 | 原因 | 处理 |
|------|------|------|
| Layer 3 smoke test 失败 | Layer 1+2 通过 → 系统基本可用，回滚代价 > 收益 | 创建 bug 奏折 + 告警 |
| Layer 3 smoke test 超时 | 视为暂时性问题 | 告警 + 下次重试 |
| deploy 成功但通知发送失败 | 非系统性故障 | 记录日志 |

### 6.2 版本存储策略（完整规格）

**目录结构：**
```
${CHAOTING_DIR}/backups/
├── chaoting-backup-20260314T040000   ← 最旧保留
├── chaoting-backup-20260314T041500
├── chaoting-backup-20260314T042000   ← 最新
└── latest-backup.json
```

**latest-backup.json 格式：**
```json
{
  "timestamp": "2026-03-14T04:20:00",
  "backup_path": ".../chaoting-backup-20260314T042000",
  "commit": "abc1234",
  "git_log": "fix: dispatcher timeout handling",
  "deploy_zouzhe_id": "ZZ-20260314-007",
  "file_size_bytes": 48320
}
```

**保留策略：**
- 保留最近 **3 个**快照（滚动覆盖）
- 每次 deploy 前创建快照（Step 2），deploy 成功后删除最旧的超出数量的快照
- 快照**仅备份 CLI binary**（`src/chaoting`），不备份 DB 数据（避免数据状态回退）
- 预估磁盘占用：单个快照约 50-100KB，3 个快照合计 < 1MB
- deploy 前检查 backups/ 目录可写且磁盘剩余 > 10MB（否则退出码 5）

**回滚时使用 `latest-backup.json` 指向的路径**：

```python
def rollback():
    meta_path = os.path.join(BACKUP_DIR, "latest-backup.json")
    if not os.path.exists(meta_path):
        raise RollbackError("latest-backup.json not found — cannot rollback")

    with open(meta_path) as f:
        meta = json.load(f)

    backup_binary = meta["backup_path"]
    if not os.path.exists(backup_binary):
        raise RollbackError(f"Backup binary missing: {backup_binary}")

    shutil.copy2(backup_binary, CHAOTING_CLI_PATH)  # 原子性替换
    subprocess.run(["systemctl", "--user", "restart", "chaoting-dispatcher"], check=True)
```

### 6.3 快照步骤与 deploy 步骤的原子性保证

| 步骤 | 操作 | 失败处理 |
|------|------|---------|
| 保存 latest-backup.json | 先写临时文件，再 rename（原子） | 若失败则终止 deploy（快照不可用时拒绝 deploy）|
| 备份 binary | `shutil.copy2(src, backup_path)` | 若失败则终止 deploy |
| 覆盖 production binary | `shutil.copy2(new_binary, CLI_PATH)` | 若失败则从备份恢复 |
| restart dispatcher | `systemctl --user restart` | 失败则直接触发 rollback |

### 6.4 回滚失败处理

若回滚本身也失败（快照文件损坏/丢失/权限不足）：
- 停止所有自动操作
- 写入 liuzhuan：`action="rollback_failed"`
- **立即升级给司礼监**（CRITICAL，退出码 2）
- 输出详细诊断信息（当前 binary 路径、backup 路径、权限状态）

---

## 七、幂等性深度设计

### 7.1 问题场景

以下情况可能导致 deploy 命令被重复调用：
1. dispatcher poll 异常重启，deploy_state=deploying 悬空后被重新 trigger
2. 人工手动重新执行 deploy 命令
3. smoke test 失败后尝试重新 deploy 同一版本

### 7.2 Commit SHA 幂等检测

```python
def check_idempotent(zouzhe_id: str, force: bool) -> bool:
    """
    返回 True = 需要 deploy（不幂等或强制）
    返回 False = 跳过（幂等，退出码 3）

    规则：
    - deploy_state=verified + 同SHA → 跳过（已成功部署）
    - deploy_state=failed + 同SHA  → 允许重试（失败可能是环境问题，修复后需重试）
    - 不同SHA → 正常 deploy
    - --force → 强制重新 deploy（覆盖 verified 幂等保护）
    """
    # 获取当前已部署的状态
    current_state = get_current_deploy_state(zouzhe_id)
    current_sha = get_current_deployed_sha()  # 读取 deploy_state=verified 的最后记录

    # 获取目标 commit SHA（PR merge 后 master 的 HEAD）
    target_sha = subprocess.run(
        ["git", "-C", CHAOTING_REPO, "rev-parse", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip()

    # 已成功部署同一版本 → 幂等跳过（除非 --force）
    if current_sha == target_sha and current_state == "verified" and not force:
        write_liuzhuan(zouzhe_id, action="deploy_skipped_idempotent",
                       remark=f"commit {target_sha} already deployed and verified")
        return False  # 跳过，退出码 3

    # 失败状态同一版本 → 允许重试（不幂等跳过）
    # current_state == "failed" + same SHA → fall through to normal deploy

    return True  # 需要 deploy（新版本 or 失败重试 or --force）
```

### 7.3 deploy_state=deploying 悬空处理

若 dispatcher 重启后检测到 `deploy_state=deploying`，说明上次 deploy 中途中断：

```python
def recover_stale_deployments():
    """dispatcher 启动时调用（类似 recover_orphans）"""
    stale = db.execute("""
        SELECT id, updated_at FROM zouzhe
        WHERE deploy_state = 'deploying'
          AND (julianday('now') - julianday(updated_at)) * 86400 > 60
    """).fetchall()
    # 超过 60s 的 deploying 视为悬空

    for row in stale:
        # 检查当前服务状态
        if is_service_healthy():
            # 服务可能已恢复（deploy 成功但进程被 kill before writing result）
            db.execute(
                "UPDATE zouzhe SET deploy_state='deployed' WHERE id=?",
                (row["id"],)
            )
            # 补触发 smoke test
        else:
            # 服务异常，执行 rollback
            db.execute(
                "UPDATE zouzhe SET deploy_state='failed' WHERE id=?",
                (row["id"],)
            )
            trigger_rollback(row["id"])
```

### 7.4 幂等性保证矩阵

| 场景 | `--force` 未设置 | `--force` 已设置 |
|------|----------------|----------------|
| 同 commit SHA，deploy_state=verified | 退出码 3（跳过：已成功部署，无需重复） | 重新 deploy |
| 同 commit SHA，deploy_state=failed | **正常 deploy（允许重试）**：失败可能由环境问题（网络、磁盘、服务启动竞态）引起，环境修复后应允许重新尝试同一版本，而非永久屏蔽 | 正常 deploy（与未设置相同） |
| 不同 commit SHA | 正常 deploy | 正常 deploy |
| deploy_state=deploying（悬空） | `recover_stale_deployments()` 处理 | 强制重新 deploy |
| 重复 restart dispatcher | 无害（systemd restart 幂等） | 无害 |
| 重复创建 backup 同一 commit | 以 timestamp 为文件名去重 | 以 timestamp 为文件名去重 |

**设计决策说明（failed 状态允许重试）：**  
`deploy_state=failed` 表示上次 deploy 执行时遇到错误（如健康检查超时、磁盘满、服务启动竞争等），这些故障往往是**环境性**而非**代码性**。如果将 `failed + 同SHA` 也归入幂等跳过，则在操作员修复环境问题后，必须使用 `--force` 才能重试，增加操作负担且不直观。因此：
- `deploy_state=verified`（已成功）→ 幂等跳过（退出码 3）：成功后无需重复
- `deploy_state=failed`（已失败）→ **允许正常重试**：失败后应可重新尝试
- 若已知是代码问题需要覆盖已验证版本，使用 `--force`

---

## 八、安全风险分析与最小权限方案

### 8.1 问题描述

`chaoting deploy` 需要：
1. 覆盖 production binary（写文件系统）
2. `systemctl --user restart chaoting-dispatcher`（控制服务）
3. 读取 chaoting.db（读写数据库）

这些操作由 **agent 进程**（TheMachine 调用 openclaw agent）自动触发，存在安全风险。

### 8.2 权限模型选项对比

| 方案 | 描述 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **A: sudo + sudoers 白名单** | agent 调用 `sudo systemctl restart chaoting-dispatcher` | 实现简单 | sudo 规则误配置可能扩大权限；需要 NOPASSWD | ⚠️ 可接受 |
| **B: systemd --user service** | dispatcher 以当前用户身份运行，agent 用 `systemctl --user` 无需 sudo | 无需 root 权限 | 用户必须启用 `loginctl enable-linger` | ✅ 推荐 |
| **C: 专用 deploy 脚本 + setuid** | 只有 deploy.sh 有 setuid 权限，agent 调用它 | 最小权限 | setuid 维护复杂；路径注入风险 | ⚠️ 备选 |
| **D: D-Bus socket activation** | dispatcher 通过 D-Bus 接收 reload 信号 | 完全无权限提升 | 实现复杂度高 | ❌ 过度工程 |

### 8.3 推荐方案：方案 B（systemd --user service）

**当前 chaoting-dispatcher 已以 user service 运行**（见 SPEC.md）。agent 以同一用户身份执行：

```bash
systemctl --user restart chaoting-dispatcher
# 不需要 sudo，不需要 root，仅需用户有对自己服务的控制权
```

**前提条件：**
```bash
# 用户级 systemd 需要 linger 支持（系统重启后也能运行）
loginctl enable-linger $USER
```

### 8.4 注入攻击面分析

| 攻击面 | 风险 | 缓解措施 |
|--------|------|---------|
| `ZZ-XXXXXXXX-NNN` 参数注入 | 攻击者构造恶意 ID，使 deploy 读取错误 Git 分支 | ID 格式严格校验：`^ZZ-\d{8}-\d{3}$`，匹配失败立即拒绝 |
| `git pull origin master` 中 master 可被改写 | 攻击者 push 恶意代码到 master | 仅 dispatcher（可信进程）触发 deploy；PR 需 yushi-approve；与人工审核流程一致 |
| `backup_path` 路径遍历 | 若 backup_path 含 `../`，可能覆盖系统文件 | backup 路径必须在 `${CHAOTING_DIR}/backups/` 内（os.path.realpath 校验） |
| binary 替换为恶意文件 | 攻击者替换 chaoting CLI | deploy 只从 chaoting 自己的 Git repo 获取 binary，不接受外部输入 |
| deploy 命令被非授权主体调用 | 其他 agent 可以调用 `chaoting deploy` | deploy 命令校验 `OPENCLAW_AGENT_ID` 必须为 dispatcher（不允许 agent 直接调用） |

### 8.5 最小权限清单

运行 chaoting deploy 所需的最小权限集：

```
文件系统权限：
  - ${CHAOTING_DIR}/          读写（backups/ + chaoting.db）
  - ${CHAOTING_CLI_PATH}      写（覆盖 binary）
  - ${CHAOTING_REPO}/         读（git pull）

进程权限：
  - systemctl --user restart chaoting-dispatcher（用户级，无需 sudo）
  - git fetch + git pull（网络访问，仅 GitHub）

禁止的权限：
  - sudo 或 su（不需要 root）
  - 写 /etc/ 或系统目录
  - 访问其他用户的文件
```

### 8.6 安全审计日志

每次 deploy（无论成功/失败）必须写入 liuzhuan：

```python
write_liuzhuan(zouzhe_id,
    from_role="dispatcher",
    to_role="system",
    action="deploy_audit",
    remark=json.dumps({
        "triggered_by": "yushi-approve",
        "from_commit": from_sha,
        "to_commit": to_sha,
        "deploy_result": "success|failed|rollback",
        "executor_uid": os.getuid(),
        "timestamp": datetime.utcnow().isoformat()
    })
)
```

---

*本文档由礼部（libu）撰写，依据奏折 ZZ-20260314-009*
