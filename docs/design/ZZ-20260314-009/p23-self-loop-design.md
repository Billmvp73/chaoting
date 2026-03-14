# P2-3 Self Loop 设计：端到端自主循环

> 奏折：ZZ-20260314-009  
> 撰写：礼部（libu）  
> 日期：2026-03-14  
> 配套文档：[auto-deploy-spec.md](./auto-deploy-spec.md) | [troubleshoot-decision-tree.md](./troubleshoot-decision-tree.md) | [roadmap-p23.md](./roadmap-p23.md)

---

## 一、设计背景

当前 chaoting 的状态机有 6 个状态（`created → planning → executing → done/failed/timeout`），司礼监需要手动 Squash Merge 每个 PR，是系统吞吐量的唯一人类瓶颈。

P2-3 目标：在 yushi-approve 之后，系统能自动完成 deploy → verify → done 全流程，司礼监仅处理 escalated 问题和架构决策。

---

## 二、状态机扩展方案对比

### 方案 A：新增状态 `deploying → deployed → verified`

```
created → planning → executing → deploying → deployed → verified → done
                                    ↑
                        （yushi Squash Merge 后触发）
```

**优点：**
- 每个阶段状态明确可见，`chaoting list` 一眼知道"现在在部署中"
- 失败可精确定位（`deploying` 失败 vs `deployed` 失败）
- dispatcher 的超时检测可覆盖每个新状态

**缺点：**
- DB schema 变更（state 枚举扩展），需要 migrate
- 所有 CAS 保护的 `WHERE state = 'executing'` 条件需要同步更新
- 对于不需要 deploy 的奏折（纯文档变更），需要 `executing → verified → done` 的快速通道
- 增加系统复杂度，稳定期内有引入新 bug 的风险

### 方案 B：Deploy 作为 yushi-approve 后的自动触发动作（不增加新状态）

```
existing: executing → done
new flow: executing → [yushi approve + auto-deploy + verify] → done
                        （过渡期：这些步骤在 done 之前异步执行）
```

deploy/verify 的状态通过以下机制反映：
- `liuzhuan` 表记录：`action="deploy_started" | "deploy_ok" | "deploy_failed" | "verified"`
- `zouzhe.summary` 字段包含 deploy 结果摘要
- 新增 `deploy_state` 字段（不影响主 state 机）：`pending | deploying | deployed | verified | skipped`

**优点：**
- 不破坏现有状态机，无需 schema migrate（仅加一列）
- 所有现有 CAS 保护代码无需修改
- 对不需要 deploy 的奏折，`deploy_state = skipped`，流程完全透明
- 迭代风险低，Phase A 可独立交付而不影响其他功能

**缺点：**
- deploy 状态不在主 state 字段，`chaoting list` 不直接显示
- 需要 `chaoting status ZZ-ID` 才能看到 deploy 进度
- 若 deploy 耗时较长，奏折"卡在 executing"看起来像超时（需调整 timeout_sec）

### 决策：推荐方案 B

**理由：**
1. 风险更低：不破坏现有 6 状态模型，稳定性优先
2. 迭代友好：Phase A 可独立交付，Phase B/C 可根据反馈决定是否升级到方案 A
3. 足够可见：`chaoting status` 命令补充展示 `deploy_state`，可观测性不损失

**升级路径：** Phase C 验证稳定后，可选择将 `deploy_state` 提升为主 state（方案 A），此时作为一次独立的 schema migration 奏折处理。

---

### 完整状态机总览（ASCII Art）

#### 现有主状态机（实际 11 个状态）

> 注：SPEC.md 早期版本描述 6 状态，现行系统（含 SPEC-menxia.md + ZZ-20260313-007）已扩展为 11 状态。

```
 ┌──────────┐    ┌──────────┐
 │ created  │───▶│ planning │◀─────────────────────────┐
 └──────────┘    └────┬─────┘                          │
                      │ chaoting plan                   │
           ┌──────────┴──────────┐                     │
     review=0                 review=1                  │
           │                     │                      │
           ▼                     ▼                      │
    ┌───────────┐       ┌─────────────┐    NOGO         │
    │ executing │       │  reviewing  │────────▶ ┌──────────┐
    │           │◀──────└─────────────┘          │ revising │
    │           │       all Go                   └──────────┘
    └─────┬─────┘                                (back to zhongshu)
          │
    ┌─────┴────────────────────┐
    │ chaoting push-for-review │
    ▼
 ┌───────────┐
 │ pr_review │──────────────────────────────────────┐
 └─────┬─────┘                                      │
       │                                            │ yushi-nogo
  yushi-approve                              ┌──────┴──────────┐
       │                                     │ count < 3       │ count ≥ 3
       ▼                                     ▼                 ▼
  needs_deploy?                    ┌──────────────┐    ┌───────────┐
       │                           │executor_revise│   │ escalated │
  No ──┼──▶ state=done             └──────┬───────┘    └───────────┘
       │                                  │ push-for-review
  Yes──┼──▶ deploy_state=pending          └──▶ [pr_review] (循环)
       │    (state 仍=executing)
       │    dispatcher 触发 deploy
       ▼
   state=done (deploy 完成后)

  ─────────────────────────────────────────────────────
  Exception paths（任何活跃状态均可触发）：
    Any ──chaoting fail──▶ [failed]
    Any ──dispatcher timeout check──▶ [timeout]
    pr_review timeout ──▶ [escalated]
    executor_revise timeout ──▶ [escalated]
  ─────────────────────────────────────────────────────
```

#### 新增旁路状态机：deploy_state（方案 B）

```
  yushi-approve 内部逻辑：
  ┌─────────────────────────────────┐
  │ needs_deploy() == False?        │
  │   → deploy_state = skipped      │
  │   → state = done  (快速通道)    │
  │                                 │
  │ needs_deploy() == True?         │
  │   → deploy_state = pending      │
  │   → state 保持 executing        │
  └─────────────────────────────────┘

  旁路状态机流转：

  [not_applicable]
       │ needs_deploy()=True
       ▼
  [pending] ──────────────────────────────────────────────┐
       │ dispatcher CAS: pending→deploying                 │ CAS 失败
       ▼                                                   │ (已被抢占，忽略)
  [deploying]
       │
  ┌────┴────────────────────────────────┐
  │ Layer 1+2 OK                        │ Layer 1+2 FAIL
  ▼                                     ▼
[deployed]                      [自动回滚]──▶ [failed]
       │                                         │
  Layer 3 smoke                          rollback FAIL?
  (async, 不阻塞 done)                           │
  ┌────┴──────────────┐                          ▼
  │ OK      │ FAIL    │                   [CRITICAL 升级]
  ▼         ▼         │
[verified] (创建 bug 奏折)
  │
  ▼
  state = done （dispatcher 更新）

  [skipped] ──▶ state = done（直接）
```

---

## 三、完整端到端 Loop 设计

### 3.1 正常路径（Happy Path）

```
[人类/系统] 创建奏折 (state=created)
    ↓
[dispatcher] 分派给中书省 (state=planning)
    ↓
[zhongshu] 规划 steps + 写 plan.md → chaoting plan (state=executing)
    ↓
[dispatcher] 分派给执行部门 (assigned_agent=bingbu/libu/...)
    ↓
[执行部门] 编码/文档 → push → Issue + PR + self-review
    ↓
[jishi_review] 代码互审（Phase B 新增）
    ↓
[menxia] yushi 投票（已有机制）
    ↓  yushi 通过 (yushi-approve)
[dispatcher] 检测到 yushi OK → 调用 chaoting deploy ZZ-ID
    ↓  deploy_state=deploying
[auto-deploy] cp binary + systemctl restart + health check
    ↓  若通过 → deploy_state=deployed
[auto-verify] smoke test (Layer 3, async)
    ↓  若通过 → deploy_state=verified
[dispatcher] chaoting done ZZ-ID "自动部署验证通过" (state=done)
    ↓
[通知] 告知司礼监 + 发 Thread 反馈
```

### 3.2 验证失败路径（自动修复循环）

```
auto-verify smoke test 失败
    ↓
[auto-troubleshoot] 创建 follow-up bug 奏折 (state=created)
    title: "🐛 [Auto] ZZ-ID 部署后验证失败"
    plan: 继承原奏折的 acceptance_criteria，附加失败原因
    parent_zouzhe_id: 原 ZZ-ID（记录血缘关系）
    ↓
[dispatcher] 正常流转新奏折（重复 loop）
    ↓
修复完成 + 再次 deploy + 再次 verify
    ↓  若通过
[dispatcher] 将 follow-up 奏折 done
原 ZZ-ID 保持 done（已部署，问题由 follow-up 处理）
```

### 3.3 最大循环深度限制（Anti-Spiral）

```
follow-up 奏折携带 parent_zouzhe_id
dispatcher 检测 parent chain 深度（通过 liuzhuan 追溯）
若深度 > 3（即修复奏折的修复奏折的修复奏折）：
  ⚠️ 升级司礼监（递归修复失效，需架构决策）
  停止自动创建 follow-up
```

---

## 四、yushi-approve 触发 Deploy 的机制设计

### 4.1 触发时机

门下省（menxia）完成投票，所有 yushi 通过后，在 `chaoting yushi-approve` 命令中：

```python
# menxia agent 调用
chaoting yushi-approve ZZ-XXXXXXXX-NNN

# 内部逻辑（新增）：
def yushi_approve(zouzhe_id):
    # 现有逻辑：标记 yushi 通过
    mark_yushi_approved(zouzhe_id)

    # 新增逻辑：判断是否需要 deploy
    zouzhe = get_zouzhe(zouzhe_id)
    pr_files = get_pr_diff_files(zouzhe)  # 从 PR 拉取变更文件列表

    if needs_deploy(pr_files, zouzhe):
        # 设置 deploy_state = pending，dispatcher 下次 poll 触发
        set_deploy_state(zouzhe_id, "pending")
    else:
        # 无需 deploy，直接完成
        set_deploy_state(zouzhe_id, "skipped")
        chaoting_done(zouzhe_id, "yushi approved, no deploy needed", "auto-done")
```

### 4.2 Dispatcher 检测 deploy_state=pending

```python
# dispatcher.py 新增检测（在 poll_and_dispatch 末尾）
def check_pending_deploys():
    rows = db.execute("""
        SELECT id, timeout_sec FROM zouzhe
        WHERE state = 'executing'
          AND deploy_state = 'pending'
          AND dispatched_at IS NOT NULL
    """).fetchall()

    for row in rows:
        # 乐观锁：防止重复触发
        claimed = db.execute(
            "UPDATE zouzhe SET deploy_state='deploying' "
            "WHERE id=? AND deploy_state='pending' RETURNING id",
            (row["id"],)
        ).fetchone()
        if claimed:
            trigger_deploy(row["id"])  # 异步，不阻塞 poll
```

---

## 五、司礼监角色演变路径

### 5.1 当前角色（Pre-P2-3）

| 职责 | 频率 | 负担 |
|------|------|------|
| Review 每个 PR 代码 | 每奏折 1 次 | 高 |
| Squash Merge | 每 PR 1 次 | 高 |
| 处理 fail/timeout 通知 | 偶发 | 中 |
| 架构决策 | 偶发 | 低频但高价值 |

### 5.2 Phase A 后（Auto-Deploy）

| 职责 | 变化 |
|------|------|
| Review 每个 PR | ✅ 不变（yushi 已自动审代码，但司礼监保留 final merge 权） |
| Squash Merge | ✅ 不变（人工触发） |
| 处理 deploy 告警 | 🆕 新增（但大多数是"收到即可"） |
| 处理 CRITICAL 告警 | 🆕 新增（需快速响应） |

司礼监工作量小幅增加（告警处理），但 deploy 不再需要手动操作。

### 5.3 Phase B 后（Agent-to-Agent Review + Auto-Troubleshoot）

| 职责 | 变化 |
|------|------|
| Review 每个 PR | 🔄 减少：jishi_review 先过滤，司礼监只看 "jushi OK" 的 PR |
| Squash Merge | ✅ 不变 |
| 处理自动修复奏折 | 📉 减少：B3a/B3b 自动处理，只处理 B3c |

司礼监工作量**显著下降**，主要时间转移到架构设计和质量规则制定。

### 5.4 Phase C 后（完整 Self Loop）

| 职责 | 变化 |
|------|------|
| Review PR | 🔄 可选：满足条件的 PR 可半自动 merge（司礼监设置条件） |
| Squash Merge | 🔄 可半自动（条件：jishi OK + smoke test OK + 无 NOGO） |
| 处理告警 | 📉 减少：只有 CRITICAL 级别需要响应 |
| 架构决策 | 📈 增加：更多时间专注于系统演进方向 |

**目标状态：** 司礼监从"流水线工人"转变为"技术 VP"——设计规则、处理例外、决定方向。

### 5.5 过渡期风险管理

- **不能一步到位**：半自动 merge 需要先在 Phase A/B 验证 health check 和 agent review 的质量
- **保留人类退出阀**：任何自动化步骤都可以通过配置关闭（`auto_deploy=false`, `auto_merge=false`）
- **渐进信任**：先在文档类奏折（libu）验证自动 deploy，再推广到代码类奏折（bingbu）

---

## 八、deploy_state 转换：触发条件 / 成功路径 / 失败路径

### 8.1 转换表（完整）

| 转换 | 触发条件 | 成功路径 | 失败路径 |
|------|---------|---------|---------|
| `not_applicable → pending` | yushi-approve 且 `needs_deploy()=True` | dispatch进入 deploying 队列 | 不可能失败（仅写 DB 字段） |
| `not_applicable → skipped` | yushi-approve 且 `needs_deploy()=False` | state 直接 → `done` | N/A |
| `pending → deploying` | dispatcher `check_pending_deploys()` CAS 成功 | 执行 `chaoting deploy ZZ-ID` | CAS 失败 → 另一 poll 抢占，安全忽略 |
| `deploying → deployed` | Layer 1+2 健康检查全部通过 | 异步触发 Layer 3 smoke test | Layer 1/2 任意失败 → 触发 rollback → `deploy_state=failed` |
| `deployed → verified` | Layer 3 smoke test 成功 | state → `done` | 创建 bug 奏折（不回滚）→ state 仍 → `done` |
| `deployed → verified`（smoke skip） | smoke test 未配置 / timeout | state → `done`（保守通过） | N/A |
| `deploying → failed` | Layer 1/2 失败 + rollback 成功 | `deploy_state=failed`，通知司礼监 | rollback 也失败 → CRITICAL 升级（见 troubleshoot §A3） |
| `deploying → failed`（不可回滚） | rollback 失败 | CRITICAL 告警，停止自动操作 | 人工 SSH 恢复 |

### 8.2 每个 deploy_state 值语义

| 值 | 含义 | 是否终态 |
|----|------|---------|
| `not_applicable` | 默认值，yushi-approve 尚未执行 | 否 |
| `pending` | yushi-approve 完成，等待 dispatcher 触发 deploy | 否 |
| `deploying` | deploy 命令正在执行 | 否 |
| `deployed` | binary 已替换 + 服务已重启 + Layer 1/2 通过 | 否 |
| `verified` | Layer 3 smoke test 通过（或跳过） | 是（正常结束） |
| `skipped` | 判断无需 deploy（文档/配置类变更） | 是（正常结束） |
| `failed` | deploy 或 rollback 失败 | 是（异常结束） |

---

## 九、与现有 reviewing / pr_review / executor_revise 的兼容性分析

### 9.1 新增 deploy_state 字段对现有流程的影响

**结论：零影响。** deploy_state 是独立的辅助字段，不参与主状态机 CAS 判断。

| 场景 | 现有行为 | 引入 deploy_state 后 |
|------|---------|-------------------|
| reviewing → executing | all Go 票 → state=executing | 不变。deploy_state 在此阶段为 `not_applicable` |
| reviewing → revising | any NOGO 票 → state=revising | 不变。deploy_state 不参与门下省投票逻辑 |
| pr_review → executor_revise | yushi-nogo（count<3）→ state=executor_revise | 不变。deploy_state 不参与 yushi-nogo 路径 |
| executor_revise → pr_review | push-for-review → state=pr_review | 不变。deploy_state 不参与执行阶段循环 |
| pr_review → done（yushi-approve） | state=done | **新增**：yushi-approve 内部额外设置 deploy_state |
| executor_revise → escalated（timeout） | dispatcher check_timeouts 检测 | 不变。escalated 后 deploy_state 不再变更 |

### 9.2 状态机是否仍然是 DAG（有向无环图）？

**主状态机不是严格 DAG**（存在 pr_review → executor_revise → pr_review 循环），这是原有设计，与 deploy_state 无关。

新增的 deploy_state 旁路状态机**是严格 DAG**：
- not_applicable → pending → deploying → deployed → verified（单向链）
- not_applicable → skipped（单步）
- deploying → failed（终态，不可恢复）

**关键约束**：deploy_state 只在 `state=executing` 且 `yushi-approve` 之后才会流转。若奏折因 yushi-nogo 进入 executor_revise 循环，deploy_state 在整个循环期间始终保持 `not_applicable`，直到最终一轮 yushi-approve 触发。

### 9.3 yushi NOGO × 3 → escalated 与 deploy 的交互

```
第 1 次 yushi-nogo：executor_revise，deploy_state = not_applicable（不变）
第 2 次 yushi-nogo：executor_revise，deploy_state = not_applicable（不变）
第 3 次 yushi-nogo：escalated
  ↳ deploy_state = not_applicable（仍不变，不触发 deploy）
  ↳ 奏折进入终态 escalated，司礼监决策
```

**无冲突**：escalated 后 deploy 不会被触发，因为 deploy 触发点仅在 yushi-approve（全票通过）分支。

### 9.4 兼容性风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| deploy_state 字段 ALTER 破坏存量数据 | 低 | 低（仅加列，DEFAULT not_applicable） | 使用 `ALTER TABLE ADD COLUMN` + DEFAULT |
| deploy 在 executor_revise 循环中意外触发 | 极低 | 高 | deploy 触发点有双重判断：(1) yushi-approve 路径；(2) deploy_state=pending（非 not_applicable） |
| dispatcher 同时处理 reviewing 投票 + pending deploy | 低 | 中 | 两者检测独立，互不干扰；CAS 锁保证每次只有一个 poll 处理 |

---

## 十、并发 deploying 场景深度分析

### 10.1 问题描述

当多个奏折同时处于 `deploy_state=deploying` 时，会发生：
1. 多个 `chaoting deploy ZZ-ID` 命令并发执行
2. 多次 `cp binary + systemctl restart` 同时发生
3. 健康检查结果可能相互干扰

**风险**：两个 deploy 并发 restart 后，每个都认为自己的版本通过了 health check，实际可能是另一个版本。

### 10.2 串行化方案：全局 Deploy 队列

**设计**：dispatcher 维护一个全局 `deploy_queue`，确保同一时刻只有一个奏折在 deploying。

```python
# 方案：DB-level 串行化（不引入外部队列）

# 新增 DB 字段（或使用 dianji 表存储）
# context_key = "deploy_lock"
# context_value = "<ZZ-ID>" 或 NULL

def check_pending_deploys():
    # Step 1：检查是否有奏折正在 deploying（全局锁检测）
    deploying_now = db.execute(
        "SELECT id FROM zouzhe WHERE deploy_state = 'deploying'"
    ).fetchone()

    if deploying_now:
        # 全局同一时刻只允许一个 deploying
        # 等待下一个 poll 周期（5s 后重试）
        return

    # Step 2：从 pending 队列取下一个（FIFO，按 updated_at 排序）
    next_pending = db.execute("""
        SELECT id FROM zouzhe
        WHERE deploy_state = 'pending'
          AND state = 'executing'
        ORDER BY updated_at ASC
        LIMIT 1
    """).fetchone()

    if not next_pending:
        return

    # Step 3：CAS 原子性地将 pending → deploying（防止并发抢占）
    claimed = db.execute(
        "UPDATE zouzhe SET deploy_state = 'deploying', "
        "updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
        "WHERE id = ? AND deploy_state = 'pending' RETURNING id",
        (next_pending["id"],)
    ).fetchone()

    if claimed:
        trigger_deploy(claimed["id"])  # 异步，不阻塞 poll
```

### 10.3 失败隔离：一个奏折的 deploy 失败不影响其他奏折

```
奏折 A deploying → Layer 1 FAIL → 自动回滚 → deploy_state=failed
    ↓
dispatcher 下次 poll：deploying_now = None（A 已是 failed）
    ↓
取出下一个 pending（奏折 B）→ 开始 deploy B
```

**关键**：A 的失败不阻塞 B 的 deploy（只要 A 的状态已流转到 failed/verified）。

**但是**：若 A 的回滚本身耗时较长（如正在等待 systemctl），则 B 会被阻塞等待。这是有意的——避免两个 deploy 并发操作 binary。

### 10.4 Starvation（饥饿）防止

若奏折 A 的 deploy 卡死（deploying 状态超时未变），后续所有 pending 奏折将被阻塞。

```python
# deploy 超时检测（新增，与 executing 超时检测类似）
def check_deploy_timeouts():
    # deploying 状态超时阈值：deploy 命令执行时间上限（默认 300s）
    DEPLOY_TIMEOUT_SEC = 300

    stuck = db.execute("""
        SELECT id FROM zouzhe
        WHERE deploy_state = 'deploying'
          AND (julianday('now') - julianday(updated_at)) * 86400 > ?
    """, (DEPLOY_TIMEOUT_SEC,)).fetchone()

    if stuck:
        # 将卡死的 deploying 强制转为 failed
        db.execute(
            "UPDATE zouzhe SET deploy_state = 'failed', "
            "error = 'deploy timeout after 300s' "
            "WHERE id = ? AND deploy_state = 'deploying'",
            (stuck["id"],)
        )
        # 通知司礼监
        notify_silijian(stuck["id"], "CRITICAL", "deploy timeout — 请检查服务状态")
```

### 10.5 并发场景汇总

| 场景 | 处理机制 | 结果 |
|------|---------|------|
| 多个奏折同时 pending | FIFO 队列，每次只取一个 | 串行 deploy |
| deploy 正在执行，新奏折变 pending | `deploying_now` 检测阻止新 deploy | 下一轮 poll 处理 |
| 两个 dispatcher poll 同时尝试 trigger deploy | CAS `WHERE deploy_state='pending' RETURNING id` | 只有一个成功 |
| deploy 卡死超 300s | `check_deploy_timeouts()` 强制 failed | 释放队列 |
| rollback 期间新 pending 奏折 | rollback 完成（failed）后再 trigger | 正确串行 |

---

## 六、新增 DB 字段（方案 B 实现）

```sql
-- 在 zouzhe 表新增（不影响现有字段）
ALTER TABLE zouzhe ADD COLUMN deploy_state TEXT DEFAULT 'not_applicable';
-- 枚举值：not_applicable / pending / deploying / deployed / verified / skipped / failed

ALTER TABLE zouzhe ADD COLUMN parent_zouzhe_id TEXT;
-- follow-up 奏折记录血缘，用于 anti-spiral 检测

ALTER TABLE zouzhe ADD COLUMN requires_deploy INTEGER DEFAULT 0;
-- plan 中显式标记（1=需要, 0=不需要）
```

---

## 七、关键设计约束总结

1. **一致性优先**：所有 deploy/verify 操作必须有 liuzhuan 记录，状态可追溯
2. **不阻塞主流程**：smoke test（Layer 3）异步执行，不阻塞 done
3. **幂等性**：deploy 命令、rollback 命令均支持重复执行无副作用
4. **人类退出阀**：所有自动化行为可通过配置关闭
5. **Anti-Spiral**：follow-up 奏折最多 3 层深度，防止无限循环
6. **最小变更原则**：Phase A 仅新增 deploy_state 字段，不改变核心状态机

---

*本文档由礼部（libu）撰写，依据奏折 ZZ-20260314-009*
