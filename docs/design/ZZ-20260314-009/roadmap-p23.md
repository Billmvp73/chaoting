# P2-3 实现路线图：端到端自主循环分阶段计划

> 奏折：ZZ-20260314-009  
> 撰写：礼部（libu）  
> 日期：2026-03-14  
> 配套文档：[p23-self-loop-design.md](./p23-self-loop-design.md) | [auto-deploy-spec.md](./auto-deploy-spec.md) | [troubleshoot-decision-tree.md](./troubleshoot-decision-tree.md)

---

## 概述

P2-3 端到端自主循环分三个阶段交付，每个阶段**独立可交付**，前一阶段不完成不阻塞后续阶段的规划，但后续阶段依赖前一阶段的能力。

```
Phase A（2周）  ─── Auto-Deploy 基础能力
    │
    ↓（依赖）
Phase B（3周）  ─── Auto-Troubleshoot + Agent-to-Agent Review
    │
    ↓（依赖）
Phase C（4周）  ─── 完整 Self Loop + 司礼监角色演变
```

---

## Phase A：Auto-Deploy 基础能力

**目标：** chaoting 合并后能自动部署自身，司礼监不再需要手动执行部署命令

**工期：** 约 2 周  
**负责部门：** bingbu（核心编码）+ libu（文档更新）  
**依赖前置：** 无（可立即开始）

### A.1 交付物

| 交付物 | 说明 | 负责 |
|-------|------|------|
| `chaoting deploy` 命令 | cp binary + systemctl restart + health check | bingbu |
| Health Check 三层实现 | Layer 1（存活）+ Layer 2（功能）+ Layer 3（E2E，异步） | bingbu |
| 快照/回滚机制 | backups/ 目录 + latest-backup.json + rollback 逻辑 | bingbu |
| `needs_deploy()` 判断函数 | dispatcher 中判断 PR 是否触发 deploy | bingbu |
| `deploy_state` DB 字段 | zouzhe 表新增列（migration script） | bingbu |
| dispatcher 检测 `deploy_state=pending` | poll 循环中新增检测逻辑 | bingbu |
| `auto-deploy-spec.md` 更新 | 按实现结果更新规格文档 | libu |
| `docs/OBSERVABILITY.md` | 新建，记录 health check 命令和监控方式 | libu |

### A.2 实现步骤

```
Sprint A-1（第 1 周）：
  ☐ 实现 chaoting deploy 命令（含 --dry-run）
  ☐ 实现快照创建/清理逻辑（backups/ 目录）
  ☐ 实现回滚命令（从快照恢复）
  ☐ 实现 Health Check Layer 1 + Layer 2
  ☐ DB migration：添加 deploy_state + parent_zouzhe_id + requires_deploy

Sprint A-2（第 2 周）：
  ☐ 实现 needs_deploy() 判断函数
  ☐ dispatcher：新增 check_pending_deploys() 逻辑
  ☐ 实现 Health Check Layer 3（E2E smoke，异步）
  ☐ 通知机制：告警格式 + TheMachine 集成
  ☐ 在 libu 类奏折（文档变更）上端到端验证（低风险试跑）
  ☐ 在 bingbu 类奏折上验证（代码变更）
  ☐ 文档更新
```

### A.2b Phase A 子任务列表（可直接下旨执行）

以下是 Phase A 的 **9 个子任务**，每个可作为独立奏折下旨给相应部门：

| # | 子任务描述 | 预估工时 | 依赖 | 产出物 | target_agent |
|---|-----------|---------|------|-------|-------------|
| A-1 | **DB Migration**：zouzhe 表新增 `deploy_state`、`parent_zouzhe_id`、`requires_deploy` 三列；编写 migration script；更新 `init_db.py` 确保新建 DB 也包含这三列；编写 rollback script（DROP COLUMN）| 2h | 无 | `src/init_db.py` 更新 + `migrations/add_deploy_fields.py` + 回滚脚本 | bingbu |
| A-2 | **`chaoting deploy` 命令实现**：按 auto-deploy-spec.md § 二~三规格，实现 Step 1-6；含 `--dry-run`、`--force`、`--timeout`、`--skip-health` 四个参数；退出码 0/1/2/3/4/5；JSON 输出格式 | 4h | A-1 | `src/chaoting`：新增 `cmd_deploy()` | bingbu |
| A-3 | **Health Check 三层实现**：Layer 1（dispatcher running + DB writable + CLI responsive）、Layer 2（pull read-only + dispatcher poll）、Layer 3（E2E smoke，异步，`ZZ-SMOKE-TEST` 前缀）；独立函数 `run_health_check(layer: int) -> HealthResult` | 3h | A-2 | `src/chaoting`：`run_health_check()` + `cmd_health()` | bingbu |
| A-4 | **快照 + 回滚机制**：backups/ 目录管理（保留最近 3 个）、`latest-backup.json` 格式、`create_snapshot()` + `execute_rollback()` 函数；磁盘空间前置检测（> 10MB）；幂等性（同 commit SHA 检测） | 3h | A-2 | `src/chaoting`：`create_snapshot()` + `execute_rollback()` | bingbu |
| A-5 | **`needs_deploy()` 判断函数 + `yushi-approve` 集成**：实现 `needs_deploy(pr_diff_files, zouzhe)` 按文件路径模式判断；在 `cmd_yushi_approve()` 中集成：通过则设置 `deploy_state=pending` 或 `skipped`；`requires_deploy=True` 时优先触发 | 2h | A-1, A-2 | `src/chaoting`：`needs_deploy()` + `cmd_yushi_approve()` 更新 | bingbu |
| A-6 | **Dispatcher `check_pending_deploys()` 集成**：在 `poll_and_dispatch()` 末尾新增 `check_pending_deploys()`；CAS 串行化（全局同一时刻只有一个 deploying）；`check_deploy_timeouts()` 检测超过 300s 的悬空 deploying；`recover_stale_deployments()` 在 dispatcher 启动时调用 | 4h | A-1, A-5 | `src/dispatcher.py`：3 个新函数 | bingbu |
| A-7 | **告警通知集成**：实现 `notify_silijian(zouzhe_id, level, message)` 函数（通过 TheMachine 告警机制）；统一告警格式（见 troubleshoot-decision-tree.md § 七）；集成 L3 升级逻辑（退出码 2 时）；dispatcher `check_deploy_timeouts()` 集成告警 | 2h | A-6 | `src/dispatcher.py`：`notify_silijian()` + 告警集成 | bingbu |
| A-8 | **端到端验证 + 文档更新**：在 libu 类奏折（文档变更）上执行一次完整 deploy 流程（dry-run + 真实 run）；验证幂等性（相同 SHA 第 2 次跳过）；验证 `deploy_state=skipped` 路径；更新 `auto-deploy-spec.md` 以反映实现细节差异；新建 `docs/OBSERVABILITY.md` | 3h | A-1 ~ A-7 | 测试报告 + 文档更新 | bingbu（编码）+ libu（文档）|
| A-9 | **`chaoting status` 命令扩展：展示 deploy_state 字段**：在 `chaoting status ZZ-ID` 输出中新增 `deploy_state` 行（`not_applicable / pending / deploying / deployed / verified / failed / skipped`）及 `deploy_zouzhe_id`；方便操作员通过 CLI 直接查看 deploy 进度（见 p23-self-loop-design.md §二：「chaoting status ZZ-ID 才能看到 deploy 进度」）；同步更新 `docs/SPEC.md` 中 `status` 命令文档 | 1.5h | A-1 | `src/chaoting`：`cmd_status()` 更新 + `docs/SPEC.md` | bingbu |

### A.3 Definition of Done（Phase A）

**Given** chaoting PR 被 Squash Merge 到 master，且 yushi-approve 后 `needs_deploy()=True`，  
**When** dispatcher 下一次 poll 周期（≤ 10s），  
**Then** 满足以下全部条件才算 Phase A DoD：

- [ ] `chaoting deploy ZZ-ID` 可成功执行（Layer 1+2 健康检查通过），退出码为 0
- [ ] `zouzhe.deploy_state` 自动从 `not_applicable → pending → deploying → deployed → verified`（正常路径）
- [ ] 纯文档类奏折（仅修改 `.md` 文件）：`deploy_state=skipped`，state 直接变为 `done`
- [ ] 模拟 Layer 1 健康检查失败（kill dispatcher 进程）：系统在 60s 内自动回滚到上一版本，Layer 1 再次通过
- [ ] 回滚成功后，司礼监在 5 分钟内收到告警通知（🔴 Deploy 失败 + 回滚成功）
- [ ] 相同 commit SHA 重复执行 `chaoting deploy`：退出码 3（幂等跳过），无双重 backup
- [ ] `--dry-run` 模式：打印所有步骤但不执行，0 个副作用
- [ ] DB migration 执行后：存量数据（所有现有奏折）的 `deploy_state` 为 `not_applicable`，`state` 字段无变化

### A.4 风险评估（Phase A）

| 风险项 | 影响级别 | 概率 | 缓解策略 |
|-------|---------|------|---------|
| `systemctl --user` 权限问题（linger 未开启）| 高（Phase A 完全无法运行）| 中 | 实施前运行 `loginctl enable-linger $USER` + 健康检查验证 |
| DB migration（ADD COLUMN）破坏现有数据 | 高（数据不一致）| 低 | 仅使用 `ADD COLUMN ... DEFAULT`；migration 前备份 DB |
| `needs_deploy()` 误判：应 deploy 但跳过 | 中（新版本未生效，用户无感知）| 中 | 初期使用保守策略（默认 `True`）；逐步收紧规则 |
| 磁盘空间不足导致 backup 失败 | 中（deploy 失败，系统停在旧版本）| 低 | deploy 前检查剩余空间 > 10MB（Step 1 前置验证） |
| deploy 期间 dispatcher 新 poll 写入旧状态 | 低（竞态条件）| 低 | deploy 过程中不修改主 state，CAS 锁保护 deploy_state 字段 |
| Layer 3 smoke test 误报（CI 环境不稳定）| 低（创建不必要的 bug 奏折）| 中 | Layer 3 为异步非阻塞，误报只增加噪音，不影响功能 |

---

---

## Phase B：Auto-Troubleshoot + Agent-to-Agent Review

**目标：** 系统能自动处理大多数故障；代码 review 由 jishi_review agent 先过滤，减少司礼监 PR review 负担

**工期：** 约 3 周  
**负责部门：** bingbu（dispatcher 增强）+ xingbu（jishi_review agent）+ libu（文档）  
**依赖前置：** Phase A 完成（尤其是通知机制）

### B.1 交付物

| 交付物 | 说明 | 负责 |
|-------|------|------|
| `jishi_review` agent | 代码 review agent：拉 PR diff、对照 acceptance_criteria、发 review comment | xingbu |
| dispatcher `classify_failure()` | 故障分类函数（retryable/rework/unrecoverable） | bingbu |
| 自动接力奏折（B2 场景） | 重试耗尽后自动创建接力奏折 | bingbu |
| 自动返工路由（B3b 场景） | fail 后退回中书省重新规划 | bingbu |
| 僵死 reviewing 检测（C3 场景） | dispatcher 每 30 分钟扫描 reviewing 超时 | bingbu |
| Anti-Spiral 检测 | parent chain 深度检测（> 3 升级） | bingbu |
| follow-up 奏折创建 | smoke test 失败时自动创建 bug 奏折 | bingbu |
| `docs/AGENT-TEAMS-GUIDE.md` 更新 | 记录 jishi_review 角色和触发时机 | libu |
| `troubleshoot-decision-tree.md` 更新 | 按实现结果更新 | libu |

### B.2 实现步骤

```
Sprint B-1（第 1 周）：
  ☐ jishi_review agent SOUL.md + WORKFLOW 文档
  ☐ dispatcher：集成 jishi_review 触发（PR 创建后自动 dispatch）
  ☐ 实现 classify_failure() + 错误路由逻辑
  ☐ 实现 B3a（自动重试新奏折）

Sprint B-2（第 2 周）：
  ☐ 实现 B3b（返工路由：fail → planning）
  ☐ 实现 B2（接力奏折：timeout 超次数后接力）
  ☐ 实现 C3（reviewing 超时扫描）
  ☐ 实现 follow-up 奏折自动创建（smoke test 失败）

Sprint B-3（第 3 周）：
  ☐ 实现 Anti-Spiral（parent chain 深度检测）
  ☐ 实现 D3（批量失败检测：5+ 奏折失败 → 升级）
  ☐ jishi_review agent 端到端测试（选几个已有 PR 验证）
  ☐ 集成测试：B3a/B3b/B3c 故障注入验证
  ☐ 文档更新
```

### B.3 Definition of Done（Phase B）

**Given** Phase A 已稳定运行 ≥ 2 周，所有 Phase A DoD 条件持续满足，  
**When** Phase B 所有交付物部署到生产，  
**Then** 满足以下全部条件才算 Phase B DoD：

- [ ] 奏折创建 PR 后，`jishi_review` agent 在 10 分钟内发布 review comment（含对 acceptance_criteria 的逐项检查）
- [ ] 注入 `"方案有误"` 类型 fail（error 含 "plan is wrong"）：奏折自动退回 `state=planning`，state 变化写入 liuzhuan
- [ ] 注入可重试错误（error 含 "timeout"）：自动创建重试奏折，原奏折 liuzhuan 记录 `action="auto_retry_new_zouzhe"`
- [ ] 手动将奏折置于 `state=reviewing` 超 2 小时：dispatcher 在 30 分钟内发出提醒通知
- [ ] parent chain 深度达 4（A → B → C → D）：D 不再创建 follow-up 奏折，司礼监收到 Anti-Spiral L3 告警
- [ ] 在 2 周观测期内，司礼监收到的"需立即处理"通知数量 ≤ Phase A 基线的 50%
- [ ] 所有 `classify_failure()` 路由逻辑通过 10 个历史 fail 奏折的回放测试（准确率 ≥ 80%）

### B.4 风险评估（Phase B）

| 风险项 | 影响级别 | 概率 | 缓解策略 |
|-------|---------|------|---------|
| `jishi_review` 误判 NOGO（误报良好 PR）| 中（司礼监需额外处理误报）| 中 | jishi_review 仅提建议，不自动 NOGO；最终决策权保留给司礼监 |
| `classify_failure()` 误判，B3c → B3b（触发错误路由）| 中（退回规划浪费资源）| 中 | 分类器 fallback 为 B3c（不可恢复），只通知不自动路由 |
| 接力奏折无限创建（B2 循环）| 高（资源耗尽）| 低 | 接力次数上限 2 次（通过 parent_zouzhe_id 检测）；超出则 L3 |
| reviewing 超时检测误触发（奏折正在正常审核中）| 低（发出多余提醒）| 低 | 工作时间检测（8:00-22:00 才提醒）；提醒非阻塞操作 |
| Anti-Spiral 误判正常 chain（合理多层修复）| 低（阻止合理修复）| 低 | chain > 3 仅 L3 升级通知，不自动终止奏折 |

---

---

## Phase C：完整 Self Loop + 司礼监角色演变

**目标：** 满足条件的 PR 可半自动 merge；司礼监时间聚焦于架构决策和例外处理

**工期：** 约 4 周  
**负责部门：** bingbu（半自动 merge 逻辑）+ zhongshu（规划增强）+ libu（文档/规范）  
**依赖前置：** Phase A + Phase B 均完成，并在生产稳定运行 ≥ 2 周

### C.1 交付物

| 交付物 | 说明 | 负责 |
|-------|------|------|
| 半自动 merge 条件引擎 | 可配置的 merge 条件（jishi OK + smoke OK + NOGO=0）| bingbu |
| `chaoting auto-merge` 命令 | 满足条件后自动触发 gh pr merge --squash | bingbu |
| 可配置的自动化开关 | `auto_deploy`, `auto_merge`, `auto_troubleshoot` 配置项 | bingbu |
| 司礼监 Dashboard | `chaoting dashboard` — 展示 CRITICAL 告警 + pending 决策 | bingbu |
| 渐进信任验证流程 | 先在 libu 奏折验证，再推广到 bingbu | 规范文档 |
| `docs/WORKFLOW-sijlujian.md` | 司礼监新工作流：只处理 escalated + 架构 | libu |
| `docs/SPEC.md` 更新 | 更新状态机图（含 deploy_state）+ 新命令文档 | libu |
| Phase C 验证报告 | 2 周运行数据分析，司礼监介入次数统计 | libu |

### C.2 实现步骤

```
Sprint C-1（第 1-2 周）：
  ☐ 设计半自动 merge 条件引擎（配置文件驱动）
  ☐ 实现 chaoting auto-merge 命令（内部调用 gh pr merge --squash）
  ☐ 在 libu 类奏折启用半自动 merge（先试点，风险最低）
  ☐ 配置开关实现（默认全关，逐步开启）

Sprint C-2（第 3 周）：
  ☐ 司礼监 Dashboard（chaoting dashboard，CLI 版本即可）
  ☐ 渐进信任：在 bingbu 奏折启用半自动 merge（经司礼监确认）
  ☐ 运行 2 周，收集数据

Sprint C-3（第 4 周）：
  ☐ 数据分析：人类介入次数、平均 PR 生命周期、故障率
  ☐ 撰写 Phase C 验证报告
  ☐ docs/SPEC.md 全量更新
  ☐ 决策：是否将 deploy_state 提升为主状态（方案 A）
  ☐ 文档全量复核（WORKFLOW 文档更新）
```

### C.3 Definition of Done（Phase C）

**Given** Phase A + B 均稳定运行 ≥ 2 周，半自动 merge 功能在 libu 类奏折先行试点 2 周，  
**When** Phase C 所有交付物部署到生产，  
**Then** 满足以下全部条件才算 Phase C DoD：

- [ ] 满足半自动 merge 条件（jishi OK + smoke OK + NOGO=0 + whitelist agent）的 PR 在 30 分钟内完成 squash merge + deploy + verify，无需司礼监手动操作
- [ ] 设置 `auto_merge=false` 后：半自动 merge 立即停止（不影响已在 deploying 的奏折），恢复人工 merge 流程
- [ ] 所有 CRITICAL 级别故障在 5 分钟内触发告警（通过注入 rollback 失败场景验证）
- [ ] `chaoting dashboard` 命令可运行（CLI 版本），展示：活跃 CRITICAL 告警数 + 待处理 L3 升级数 + 过去 24h deploy 成功/失败统计
- [ ] 相比 Phase A 基线，司礼监"需立即处理"通知再减少 50%（总计比初始基线减少 ≥ 75%）
- [ ] `docs/SPEC.md` 已更新：含 deploy_state 旁路状态机图、`chaoting deploy` 命令文档
- [ ] `docs/WORKFLOW-silijian.md` 已创建：描述 Phase C 后司礼监的新工作流（仅处理 escalated + 架构决策）
- [ ] Phase C 验证报告已撰写：2 周运行数据分析（含 PR 生命周期中位数、人工介入次数、故障自愈率）

### C.4 风险评估（Phase C）

| 风险项 | 影响级别 | 概率 | 缓解策略 |
|-------|---------|------|---------|
| 半自动 merge 合并了有质量问题的代码 | 高（生产故障）| 中 | 渐进开启（先 libu → 后 bingbu）；配置开关随时可关；smoke test 兜底 |
| 司礼监对系统"失去感觉"（自动化过度）| 中（疏于监控，问题积累）| 中 | Dashboard 每日摘要；每周人工抽查 2 个 auto-merged PR |
| `auto_merge` 开关恢复人工流程不及时 | 中（紧急情况下无法快速切换）| 低 | 配置变更立即生效（不需要重启）；提供 CLI 快捷命令 `chaoting pause-auto-merge` |
| jishi_review 安全漏洞未检出（如注入攻击）| 高（安全风险）| 低 | jishi_review 为过滤层非唯一检查；security 审核类奏折强制要求司礼监 review |
| Phase C 推进过快（B 未稳定就开始 C）| 中（不成熟的 auto-troubleshoot 影响 C）| 低 | 严格前置依赖：B 稳定 ≥ 2 周后才立项 C |

---

---

## 总览路线图

```
2026-Q1（当前）
  ├── ZZ-20260314-009 调研设计完成（本奏折）
  ├── Phase A 奏折立项 → bingbu 执行 → 约 2 周
  └── Phase A 交付：chaoting deploy + health check + rollback

2026-Q2（目标）
  ├── Phase A 稳定运行 ≥ 2 周
  ├── Phase B 奏折立项 → bingbu + xingbu 并行 → 约 3 周
  └── Phase B 交付：jishi_review + auto-troubleshoot

2026-Q3（目标）
  ├── Phase B 稳定运行 ≥ 2 周
  ├── Phase C 奏折立项 → 约 4 周
  └── Phase C 交付：完整 self loop + 司礼监角色演变
```

### 关键里程碑

| 里程碑 | 目标日期 | 标志事件 |
|-------|---------|---------|
| M1：Deploy 自动化 | Phase A 末 | 第一个奏折完成全自动 deploy + health check |
| M2：故障自愈 | Phase B 末 | 第一个奏折从 fail 自动恢复（无人工介入）|
| M3：半自动 merge | Phase C 初 | 第一个 PR 通过半自动 merge 流程 |
| M4：Self Loop 验证 | Phase C 末 | 连续 2 周，司礼监介入次数 < 每周 5 次 |

---

## 依赖关系总结

```
Phase A 依赖：
  ✅ yushi-approve 机制（menxia，已有）
  ✅ systemd user service（chaoting-dispatcher，已有）
  ✅ TheMachine 告警机制（dispatcher → 告警，需确认接口）

Phase B 依赖：
  ✅ Phase A 的通知机制
  ✅ Phase A 的 deploy_state 字段
  🔧 需新建 xingbu/jishi_review agent（新工作量）

Phase C 依赖：
  ✅ Phase A + B 全部完成
  ✅ gh CLI 的 --squash merge 权限（需确认 bot token 权限）
  ✅ 生产稳定运行数据（2 周）
```

---

*本文档由礼部（libu）撰写，依据奏折 ZZ-20260314-009*
