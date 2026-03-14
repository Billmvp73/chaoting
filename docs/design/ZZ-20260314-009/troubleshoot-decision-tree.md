# 失败处理树：Auto-Troubleshoot + 人类介入边界

> 奏折：ZZ-20260314-009  
> 撰写：礼部（libu）  
> 日期：2026-03-14  
> 配套文档：[p23-self-loop-design.md](./p23-self-loop-design.md) | [auto-deploy-spec.md](./auto-deploy-spec.md) | [roadmap-p23.md](./roadmap-p23.md)

---

## 一、设计目标

定义 chaoting 系统在各类故障场景下的**自动处理路径**和**人类介入边界**，使系统在绝大多数故障中能自我恢复，只在真正需要判断力的场景升级给司礼监。

---

## 二、L1/L2/L3 三级处理框架

### 2.1 分级定义

| 级别 | 名称 | 含义 | 人类介入 | 通知级别 |
|------|------|------|---------|---------|
| **L1** | 自动修复 | 系统完全自主处理，无需通知 | 无 | 无/日志 |
| **L2** | 自动创建修复奏折 + 通知 | 自动处理但需要司礼监知晓，可异步跟进 | 可选（不紧急） | 🟡 中 |
| **L3** | 立即升级，等待人类决策 | 超出自动化能力，必须人工介入 | 必须 | 🔴 高 / 🚨 CRITICAL |

### 2.2 故障场景分级映射

| 故障场景 | 原分类 | L 级别 | 理由 |
|---------|-------|--------|------|
| Dispatcher crash + systemd 自动重启成功 | C1 | **L1** | 秒级自愈，无感知 |
| DB busy timeout 自动等待 | C2 | **L1** | 毫秒级，透明处理 |
| 主机重启后服务自动恢复 | D1 | **L1** | 正常运维，systemd 处理 |
| 奏折首次超时重试（count < max_retries）| B1（部分）| **L1** | 常见，通知反而是噪音 |
| Deploy 失败 + 自动回滚成功 | A1 | **L2** | 系统安全，但需要修复后重新 deploy |
| Smoke Test 失败（已创建 bug 奏折）| A2 | **L2** | 基本可用，修复奏折在处理 |
| 奏折自动重试/接力 | B1/B2/B3a | **L2** | 系统自我修复，知晓即可 |
| 奏折自动返工（退回中书省）| B3b | **L2** | 流程正常，可异步跟进 |
| reviewing 超时提醒 | C3（提醒阶段）| **L2** | 流程提醒，非故障 |
| 回滚失败（CRITICAL）| A3 | **L3** | 系统不一致，必须人工恢复 |
| yushi NOGO × 3 | B4 | **L3** | 质量判断超出自动化能力 |
| Dispatcher 自动重启失败 | C4 | **L3** | 任务队列停摆，需立即恢复 |
| DB 文件损坏 | D2 | **L3** | 数据恢复不可自动决策 |
| 连续 5+ 奏折失败（批量故障）| D3 | **L3** | 系统性问题，自动重试掩盖根因 |
| 不可恢复 fail × 2（1小时内同类型）| B3c（聚合）| **L3** | 模式性故障，需架构决策 |
| reviewing 超时 > 4h 无响应 | C3（升级阶段）| **L3** | 流程卡死，需人工推进 |

---

```
故障发生
│
├─ [A] Deploy 相关故障
│   ├─ A1: Health Check Layer 1/2 失败 → 自动回滚 → 通知司礼监
│   ├─ A2: Smoke Test (Layer 3) 失败 → 告警 + 创建 bug 奏折 → 等待修复
│   └─ A3: 回滚本身失败 → ⚠️ 立即升级司礼监（人工介入）
│
├─ [B] 奏折执行故障（运行时）
│   ├─ B1: Agent 超时（timeout）→ dispatcher 自动重试（≤ max_retries）
│   ├─ B2: 重试耗尽仍超时 → 创建 reroute 奏折给同类 agent → 通知司礼监
│   ├─ B3: Agent 主动 fail → 分析 error 类型 → 路由到 B3a/B3b/B3c
│   │   ├─ B3a: 可重试错误（网络/临时）→ 创建重新执行奏折
│   │   ├─ B3b: 需返工错误（方案有误）→ 退回中书省重新规划
│   │   └─ B3c: 不可恢复错误 → 通知司礼监决策
│   └─ B4: 奏折 yushi NOGO × 3 → 升级司礼监
│
├─ [C] Dispatcher 运行时故障
│   ├─ C1: Dispatcher 进程崩溃 → systemd auto-restart（RestartSec=5）
│   ├─ C2: DB 锁定/WAL 超时 → busy_timeout=5000ms 自动等待
│   ├─ C3: 僵死奏折（reviewing 状态超时）→ 自动检测 + 处理
│   └─ C4: Dispatcher 长期无响应 → ⚠️ 升级司礼监
│
└─ [D] 系统级故障
    ├─ D1: 主机重启 → systemd WantedBy=default.target 自动恢复
    ├─ D2: DB 文件损坏 → ⚠️ 升级司礼监（数据恢复需人工）
    └─ D3: 连续多个奏折失败（批量故障）→ ⚠️ 升级司礼监（系统性问题）
```

---

## 三、场景 A：Deploy 相关故障

### A1：Health Check Layer 1/2 失败

**触发条件：** deploy 后 dispatcher 不响应、DB 不可写，或 CLI 无法执行

```
检测：chaoting deploy 内置 health check（Layer 1/2）
  ↓
自动动作：
  1. 触发回滚（见 auto-deploy-spec.md § 五）
  2. 等待回滚完成
  3. 重新运行 Layer 1 确认回滚成功
  ↓
通知司礼监：
  频道：dispatcher → TheMachine 告警
  内容：
    【⚠️ Deploy 失败 + 自动回滚】
    奏折：{ZZ-ID}
    失败步骤：{step_failed}
    错误：{error}
    回滚结果：{rollback_result}
    当前版本：{backup_commit}（已回滚）
    建议：检查代码后重新发起部署
  ↓
写入 liuzhuan：action="deploy_failed_rollback_ok"
```

**人类需要做什么：** 阅读告警 → 决定是否修复后重新 deploy（不需要立即响应，系统已安全回滚）

---

### A2：Smoke Test (Layer 3) 失败

**触发条件：** Layer 1/2 通过但端到端流程异常

```
检测：chaoting health --e2e-smoke（异步，Layer 3）
  ↓
自动动作：
  1. 创建 bug 奏折（高优先级）：
     title: "🐛 [Auto] Deploy Smoke Test 失败 - {ZZ-ID}"
     description: 测试失败详情 + 触发 deploy 的 PR 链接
     priority: high
     assigned: bingbu（自动分派修复）
  2. 写入 liuzhuan：action="smoke_test_failed"
  ↓
通知司礼监：
  【🔶 Smoke Test 失败（系统基本可用）】
  deploy 成功但端到端测试失败，已自动创建修复奏折 {BUG-ZZ-ID}
```

**人类需要做什么：** 知晓即可，监控修复奏折进展

---

### A3：回滚失败

**触发条件：** 快照文件损坏、磁盘空间不足、权限问题

```
检测：回滚步骤中 cp 或 systemctl 失败
  ↓
自动动作：
  1. 停止所有自动操作
  2. 写入 liuzhuan：action="rollback_failed"
  ↓
⚠️ 立即升级司礼监（CRITICAL）：
  【🚨 CRITICAL: 回滚失败，需要人工介入】
  deploy 失败且自动回滚也失败
  原因：{error}
  当前状态：dispatcher 可能处于不一致状态
  需要：人工 SSH 登录，手动恢复
```

**人类需要做什么：** 立即介入，手动恢复（这是必须升级的场景）

---

## 四、场景 B：奏折执行故障

### B1：Agent 超时（≤ max_retries）

**现有机制（dispatcher.py 已实现）**

```
dispatcher.check_timeouts() 检测到 dispatched_at 超时
  ↓
retry_count < max_retries：
  重置 dispatched_at = NULL（触发重新 dispatch）
  retry_count += 1
  写入 liuzhuan：action="retry"
  ↓
下一次 poll 周期自动重新 dispatch 给同一 agent
```

无需额外处理，现有逻辑已覆盖。

---

### B2：重试耗尽仍超时

**触发条件：** retry_count >= max_retries，dispatcher 将状态置为 timeout

```
dispatcher 将 state=timeout
  ↓
Auto-Troubleshoot 增强（新增逻辑）：
  1. 分析奏折类型（plan 中的 target_agent）
  2. 若有同类可用 agent：
     创建"接力"奏折（fork 原奏折 plan，新 ZZ-ID，state=created）
     原奏折保持 timeout（不覆盖）
  3. 若无同类可用 agent，或原奏折已是接力奏折（检查 parent_zouzhe_id）：
     跳过自动接力 → 通知司礼监
  ↓
通知司礼监：
  【⚠️ 奏折超时（已接力/需人工）】
  原奏折：{ZZ-ID}，超时 {N} 次
  接力奏折：{NEW-ZZ-ID}（或"无法自动接力"）
```

---

### B3：Agent 主动 fail

dispatcher 监听到 `state=failed`，触发故障分类路由：

```python
def classify_failure(error_text: str) -> str:
    """
    根据 error 文本分类故障类型
    """
    RETRYABLE_KEYWORDS = ["timeout", "network", "connection", "rate limit", "temporary"]
    REWORK_KEYWORDS = ["plan is wrong", "方案有误", "需返工", "acceptance_criteria unclear"]

    error_lower = error_text.lower()
    if any(k in error_lower for k in RETRYABLE_KEYWORDS):
        return "retryable"
    if any(k in error_lower for k in REWORK_KEYWORDS):
        return "rework"
    return "unrecoverable"
```

**B3a：可重试错误**
```
classify → "retryable"
  ↓
创建重新执行奏折（相同 plan，新 ZZ-ID，state=created）
写入 liuzhuan：action="auto_retry_new_zouzhe"
通知司礼监（低优先级）：【ℹ️ 临时错误，已自动重试】
```

**B3b：需返工错误**
```
classify → "rework"
  ↓
将奏折退回规划阶段：state=planning，assigned_agent=zhongshu
写入 liuzhuan：action="rework", remark="退回中书省重新规划"
附上 fail 原因作为 rework 上下文（写入 plan 的 rework_reason 字段）
通知司礼监（中优先级）：【🔄 方案返工，已退回中书省】
```

**B3c：不可恢复错误**
```
classify → "unrecoverable"
  ↓
保持 state=failed（不自动重试）
通知司礼监（高优先级）：
  【❌ 奏折执行失败（不可恢复）】
  奏折：{ZZ-ID}
  错误：{error}
  已尝试：{retry_count} 次
  建议：需人工判断是否取消/重新规划/升级
```

---

### B4：奏折 yushi NOGO × 3

**触发条件：** 门下省 yushi（御史）连续 3 次投 NOGO

```
门下省记录第 3 次 NOGO
  ↓
⚠️ 升级司礼监（必须）：
  【🚨 奏折 yushi NOGO × 3，需决策】
  奏折：{ZZ-ID}
  NOGO 原因（摘要）：{reasons}
  建议：(a) 取消奏折 (b) 大幅返工 (c) 人工覆写通过（慎重）
```

**人类需要做什么：** 必须决策（这是系统性质量问题，不能自动处理）

---

## 五、场景 C：Dispatcher 运行时故障

### C1：Dispatcher 进程崩溃
systemd `Restart=always` + `RestartSec=5` 自动处理，无需额外逻辑。  
恢复后 `recover_orphans()` 清理僵死分派。

### C2：DB 锁定
`PRAGMA busy_timeout=5000` 自动等待 5 秒，无需额外逻辑。

### C3：僵死奏折（reviewing 状态超时）

**问题背景：** 若 yushi 审核流程存在 `reviewing` 中间状态，该状态没有 timeout 检测覆盖（现有 SPEC.md 只检测 planning/executing）。

```
新增 dispatcher 检测逻辑：
  每 30 分钟扫描：state='reviewing' AND 
  (julianday('now') - julianday(dispatched_at)) * 86400 > REVIEWING_TIMEOUT_SEC (默认 7200 = 2h)
  ↓
自动处理：
  若在工作时间（8:00-22:00）：
    发送提醒给门下省（ping yushi agent 重新处理）
  若超过 4 小时：
    通知司礼监：【⚠️ 奏折 reviewing 超时 {N}h，可能需要人工干预】
```

### C4：Dispatcher 长期无响应

**检测方式：** cron job（每小时）检查 dispatcher 最后一次 poll 时间

```
chaoting health --check dispatcher-last-poll
  ↓
若超过 10 分钟无 poll：
  尝试 systemctl --user restart chaoting-dispatcher
  等待 30 秒，再次检查
  若仍无响应：
    ⚠️ 升级司礼监（必须）：
    【🚨 Dispatcher 无响应，自动重启失败】
```

---

## 六、人类介入边界定义

### 必须升级给司礼监（人类必须介入）

| 场景 | 原因 | 紧急度 |
|------|------|--------|
| 回滚失败（A3） | 系统处于不一致状态，需人工 SSH 恢复 | 🚨 CRITICAL |
| yushi NOGO × 3（B4） | 质量判断问题，超出自动化能力 | 🔴 高 |
| Dispatcher 自动重启失败（C4） | 系统无法自愈，任务队列停摆 | 🚨 CRITICAL |
| DB 文件损坏（D2） | 数据恢复需人工，无法自动判断数据价值 | 🚨 CRITICAL |
| 连续 5+ 奏折失败（D3） | 系统性问题，自动重试会掩盖根因 | 🔴 高 |
| 不可恢复 fail（B3c）× 2 同类型（1小时内） | 模式性故障，需架构决策 | 🔴 高 |

### 通知即可（人类知晓，不需要立即行动）

| 场景 | 原因 | 紧急度 |
|------|------|--------|
| Deploy 失败 + 回滚成功（A1） | 系统已安全，等人类有空处理 | 🟡 中 |
| Smoke Test 失败（A2）| 已创建修复奏折 | 🟡 中 |
| 奏折自动重试/接力（B1/B2/B3a） | 系统自我修复，记录在案 | 🟢 低 |
| reviewing 超时提醒（C3） | 流程提醒，非故障 | 🟢 低 |

### 无需通知（系统完全自主处理）

| 场景 | 原因 |
|------|------|
| Dispatcher crash + 自动重启成功（C1） | systemd 自愈，秒级恢复 |
| DB busy timeout 自动等待（C2） | 毫秒级，透明处理 |
| 主机重启后自动恢复（D1） | 正常运维场景 |
| 奏折首次超时重试（B1，retry < max_retries） | 常见，噪音通知反而有害 |

---

## 七、故障通知格式

所有通知通过 TheMachine 告警机制发送，格式统一：

```
{emoji} {标题}
──────────────────
奏折：{ZZ-ID} "{title}"
时间：{ISO timestamp}
错误：{error_brief}
已执行：{auto_actions_taken}
需要：{human_action_required | 无需操作}
──────────────────
详情：chaoting status {ZZ-ID}
```

---

## 八、L3 升级精确判定标准

下列条件**任意一条满足**即触发 L3 升级（不可用"情况复杂"等模糊描述代替）：

| # | 判定条件 | 检测方式 | 退出码/信号 |
|---|---------|---------|-----------|
| 1 | **回滚命令退出码为 2**（`chaoting deploy` 退出码 2：health check 失败且回滚失败） | deploy 命令返回值 | `exit_code == 2` |
| 2 | **yushi NOGO 计数 ≥ 3**（同一奏折连续 3 次 yushi-nogo，经 `exec_revise_count` 字段确认） | `zouzhe.exec_revise_count >= 3` | `chaoting yushi-nogo` 内部 |
| 3 | **deploy_state=deploying 超时 > 300s**（deploy 命令卡死，未转为 deployed 或 failed） | `check_deploy_timeouts()` | 超时检测 |
| 4 | **Dispatcher 重启后 10 分钟内未出现 poll**（`chaoting health --check dispatcher-last-poll` 检测）| cron job 每 5 分钟检查 | `last_poll_age > 600s` |
| 5 | **DB WAL 文件大小 > 100MB**（可能表示 DB 损坏或写入循环）| `os.path.getsize('chaoting.db-wal') > 100*1024*1024` | cron 检查 |
| 6 | **同一 1 小时内 5+ 个不同奏折进入 failed/timeout**（批量故障模式）| `COUNT(state IN ('failed','timeout') AND updated_at > NOW()-3600) >= 5` | dispatcher 聚合检测 |
| 7 | **同类不可恢复错误（B3c）在 1 小时内重复 2 次**（相同 assigned_agent + 相似 error 关键词）| `error_dedup_key` 匹配 | 故障分类器 |
| 8 | **父奏折 → 子修复奏折 → 孙修复奏折（chain 深度 ≥ 3）** | `parent chain depth > 3`（通过 parent_zouzhe_id 追溯）| Anti-Spiral 检测 |

**L3 通知必须包含**：判定条件编号（如"触发条件 #4"）、具体数值（如"last_poll 18 分钟前"）、建议的人工操作步骤。

---

## 九、告警防抖机制

### 9.1 问题场景

若不加防抖，可能出现无限循环：

```
deploy 失败 → 创建 bug 奏折 A
  → A 执行失败 → 创建 bug 奏折 B（修复 A 的修复）
    → B 部署失败 → 创建 bug 奏折 C（修复 B 的修复）
      → ... （无限）
```

### 9.2 防抖数据结构

```python
# 在 dianji 表存储（或独立的 alert_dedup 表）
# context_key = "alert_dedup:<dedup_key>"
# context_value = JSON: {"count": N, "first_seen": ts, "last_seen": ts, "cooldown_until": ts}

def get_dedup_key(event_type: str, zouzhe_id: str = None, agent: str = None) -> str:
    """
    构造去重 key，相同类型+相同上下文视为同一告警
    """
    if event_type == "deploy_failed":
        return f"deploy_failed:{zouzhe_id}"
    elif event_type == "smoke_failed":
        return f"smoke_failed:{zouzhe_id}"
    elif event_type == "b3c_unrecoverable":
        return f"b3c:{agent}:{event_type}"  # 按 agent 聚合
    elif event_type == "batch_failure":
        return "batch_failure:global"  # 全局唯一
    else:
        return f"{event_type}:{zouzhe_id or 'global'}"
```

### 9.3 冷却窗口设计

| 事件类型 | 冷却窗口 | 最大循环次数 | 达到上限后动作 |
|---------|---------|-----------|-------------|
| deploy 失败 + 创建修复奏折 | 30 分钟 | 3 次 | 停止创建修复奏折 → L3 升级 |
| smoke test 失败 + 创建 bug 奏折 | 60 分钟 | 3 次 | 停止创建 bug 奏折 → L3 升级 |
| B3a 自动重试 | 10 分钟 | 2 次 | 升级为 B3c（不可恢复）→ 通知 |
| reviewing 超时提醒（C3）| 2 小时 | 2 次提醒 | 第 3 次直接 L3 升级 |
| 批量失败检测 | 1 小时 | 1 次通知 | 冷却期内不重复通知 |

### 9.4 防抖实现

```python
def should_alert(dedup_key: str, cooldown_sec: int, max_count: int) -> tuple[bool, str]:
    """
    返回 (should_alert: bool, reason: str)
    """
    now = datetime.utcnow().timestamp()
    record = get_dedup_record(dedup_key)

    if record is None:
        # 第一次出现
        save_dedup_record(dedup_key, count=1, first_seen=now, last_seen=now,
                          cooldown_until=now + cooldown_sec)
        return True, "first_occurrence"

    if now < record["cooldown_until"]:
        # 在冷却期内，不重复告警
        return False, f"in_cooldown (until {record['cooldown_until']})"

    new_count = record["count"] + 1
    if new_count > max_count:
        # 超过最大次数，停止自动处理，触发 L3
        return False, f"max_count_exceeded ({new_count} > {max_count}) → escalate_l3"

    # 更新冷却记录
    save_dedup_record(dedup_key, count=new_count, last_seen=now,
                      cooldown_until=now + cooldown_sec)
    return True, f"count={new_count}"

# 使用示例：
def handle_deploy_failed(zouzhe_id: str):
    key = get_dedup_key("deploy_failed", zouzhe_id)
    ok, reason = should_alert(key, cooldown_sec=1800, max_count=3)

    if not ok and "max_count_exceeded" in reason:
        # 超限，升级 L3
        escalate_l3(zouzhe_id, "deploy_failed_loop",
                    detail=f"deploy 失败循环 > 3 次，已停止自动修复")
    elif ok:
        create_bug_zouzhe(zouzhe_id, "deploy 失败")
```

---

## 十、司礼监未响应 Fallback 策略

### 10.1 问题场景

L3 升级通知发出后，如果司礼监长时间未响应（如睡眠、断网、外出），系统需要定义"等待多久后做什么"。

### 10.2 Fallback 时间阶梯

不同紧急度对应不同的等待时间和降级动作：

#### CRITICAL 级别（回滚失败 / Dispatcher 宕机 / DB 损坏）

```
T+0:   🚨 L3 告警发出（TheMachine 通知）
T+15m: 若无人响应：重复告警（第 2 次）
T+30m: 若无人响应：重复告警（第 3 次）+ 尝试备用通知渠道（如 email）
T+2h:  若无人响应：
         - 回滚失败场景：系统已停止自动操作，保持当前状态（freeze）
         - Dispatcher 宕机：尝试最后一次 systemctl restart（最多 1 次）
         - 写入 zouzhe.error: "L3_ESCALATED_NO_RESPONSE — 等待人工处理 {N}h"
T+8h:  若无人响应：最终告警 + 冻结所有自动 deploy/troubleshoot 行为
         （新奏折仍可进入 executing/pr_review，但 deploy 和故障修复全部暂停）
```

#### HIGH 级别（yushi NOGO×3 / 批量失败 / 模式性故障）

```
T+0:   🔴 L3 告警发出
T+2h:  若无人响应：重复告警（提醒）
T+8h:  若无人响应：
         - 相关奏折保持当前状态（不再自动创建修复奏折）
         - 记录 "awaiting_human_decision" 标记
T+24h: 若无人响应：最终告警 + 自动 suspend 涉及奏折（防止 timeout 循环）
```

### 10.3 Freeze 模式行为

进入 Freeze 模式后（L3 escalated + 2h CRITICAL 无响应）：

| 操作 | Freeze 模式下 |
|------|-------------|
| 新奏折 created → planning | ✅ 正常（允许新任务入队）|
| planning → reviewing/executing | ✅ 正常 |
| executing → pr_review → done | ✅ 正常 |
| deploy（deploy_state=pending → deploying）| ❌ 暂停（返回"系统处于 freeze 模式"）|
| 自动创建修复/接力奏折 | ❌ 暂停 |
| Smoke test 创建 bug 奏折 | ❌ 暂停 |
| L3 告警发送 | ✅ 继续（不能冻结告警本身）|

Freeze 模式由 `dianji` 表中 `context_key="system_freeze"` 控制，司礼监可通过写入 `context_value="off"` 解除。

### 10.4 Fallback 降级动作序列（实现代码骨架）

```python
class L3EscalationTracker:
    def check_and_fallback(self, escalation_id: str):
        record = get_escalation_record(escalation_id)
        elapsed_min = (now() - record["escalated_at"]).total_seconds() / 60

        if record["level"] == "CRITICAL":
            if elapsed_min >= 15 and not record.get("reminder_1_sent"):
                notify_silijian(escalation_id, "CRITICAL_REMINDER_1")
                record["reminder_1_sent"] = True
            if elapsed_min >= 30 and not record.get("reminder_2_sent"):
                notify_silijian(escalation_id, "CRITICAL_REMINDER_2", channel="email")
                record["reminder_2_sent"] = True
            if elapsed_min >= 120 and not record.get("freeze_applied"):
                apply_system_freeze(reason=escalation_id)
                record["freeze_applied"] = True
            if elapsed_min >= 480 and not record.get("final_alert_sent"):
                notify_silijian(escalation_id, "CRITICAL_FINAL_ALERT")
                record["final_alert_sent"] = True

        elif record["level"] == "HIGH":
            if elapsed_min >= 120 and not record.get("reminder_1_sent"):
                notify_silijian(escalation_id, "HIGH_REMINDER_1")
                record["reminder_1_sent"] = True
            if elapsed_min >= 480 and not record.get("suspend_applied"):
                suspend_related_zouzhe(escalation_id)
                record["suspend_applied"] = True
            if elapsed_min >= 1440 and not record.get("final_alert_sent"):
                notify_silijian(escalation_id, "HIGH_FINAL_ALERT")
                record["final_alert_sent"] = True

        save_escalation_record(escalation_id, record)
```

---

*本文档由礼部（libu）撰写，依据奏折 ZZ-20260314-009*
