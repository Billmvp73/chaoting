# DISCUSSION-phase2-planning.md — P0/P1 任务规划讨论结论

> 制定日期：2026-03-09  
> 制定部门：吏部（libu_hr）  
> 依据奏折：ZZ-20260309-030  
> 参考文档：docs/ROADMAP-phase2.md

---

## 前言：讨论背景

ROADMAP-phase2.md 制定后，系统又推进了几个重要变更：
- **PR #10**（ZZ-029）：Dispatcher 无 Thread ID 时回落 `#edict` 频道
- **PR #11**（非正式奏折）：`.env` 文件配置支持（dispatcher + CLI 均自动加载）

这两项变更部分提前解决了 ROADMAP-phase2 中的 P1-1，需在本次讨论中同步更新优先级判断。

---

## 一、P0 任务状态更新

### P0-1：Git 工作流实战落地验证

**讨论结论：此项 P0 任务已达成。**

**理由：**
- ZZ-20260309-027（Dispatcher NameError 修复）已走完完整流程：
  `pr/ZZ-20260309-027-fix-dispatcher-dedup` → PR #8 → 司礼监 review → Squash Merge ✅
- ZZ-20260309-029（Channel Fallback）同样走完：
  `pr/ZZ-20260309-029-channel-fallback` → PR #10 → 司礼监 review → Squash Merge ✅
- PR #11（.env 配置）亦走完完整流程

**验收结论：** P0-1 通过。Git 工作流（feature branch → PR → 司礼监 review → Squash Merge）已经过至少 3 次真实任务实战验证，执行部门（兵部）和司礼监均已熟悉流程。

**后续要求：**
- 全体执行部门继续严格遵守，不得回退
- 下一次出现违规（直接 commit master / 自行 merge）时，司礼监应退回并记录

---

### P0-2：Dispatcher 稳定性观察期

**当前状态：观察期进行中（启动于 ZZ-027 完成后，约 2026-03-09 05:18 PDT）**

**观察要点：**

| 检查项 | 频率 | 负责方 |
|--------|------|--------|
| `journalctl -u chaoting-dispatcher` ERROR/WARNING | 每 12 小时 | 工部 |
| Discord Thread 重复通知 | 实时观察 | 司礼监 |
| NameError / AttributeError | 实时观察 | 工部 |
| 奏折分派遗漏 | 每次新奏折触发后 | 司礼监 |

**观察期截止：** 2026-03-09 05:18 PDT + 48h = 2026-03-11 05:18 PDT

**通过标准：** 观察期内无 ERROR 级别日志、无重复通知、无 NameError / AttributeError。

**工部操作：** 如在观察期内发现异常，立即按如下流程处理：
1. 截图日志
2. 立即开奏折（高优先级）
3. 记录到 `docs/STABILITY-REPORT.md`（若不存在则创建）

---

## 二、P1 任务规划

### P1-1：环境变量身份认证自动化

**讨论结论：已部分解决，剩余操作为工部配置任务。**

**现状（PR #11 merge 后）：**
- `src/chaoting` 和 `src/dispatcher.py` 均自动加载 `<CHAOTING_DIR>/.env`
- `.env` 不覆盖已有环境变量（安全）
- `.env.example` 已提供模板

**剩余工作：** 各 Agent 工作区配置 `.env` 文件，写入 `OPENCLAW_AGENT_ID`：

```bash
# 每个 Agent 工作区（如 /home/tetter/.themachine/workspace-bingbu/）
echo "OPENCLAW_AGENT_ID=bingbu" >> /path/to/chaoting/.env
```

**方案选择：A（.env 持久化）vs B（CLI --agent flag）**

| 维度 | 方案 A（.env） | 方案 B（--agent flag） |
|------|--------------|----------------------|
| 实现成本 | **已实现（PR #11）** | 需兵部修改 CLI |
| 安全性 | .env gitignored，不泄漏 | 每次调用指定，更明确 |
| 易用性 | 一次配置，永久生效 | 每条命令需带参数 |
| Agent 识别准确性 | 依赖配置正确 | 调用方显式控制 |

**结论：方案 A 已就绪，优先推进 A；方案 B 作为后备增强项（非阻塞）。**

**执行计划：**

| 步骤 | 负责方 | 操作 | DDL |
|------|--------|------|-----|
| 各 Agent .env 配置 | 工部 | 为 13 个 Agent 工作区各配置 `.env` 中的 `OPENCLAW_AGENT_ID` | 1天内 |
| 验证认证正常 | 工部 | 执行 `chaoting list` 验证无"unknown" agent_id | 配置后即验 |
| （可选）CLI --agent flag | 兵部 | 为 `chaoting` CLI 增加 `--agent` 全局 flag | P2 阶段 |

---

### P1-2：Thread 活跃度告警机制实现

**问题确认：**
- POLICY-thread-feedback.md 规定：30min 内须反馈，1h 无响应提醒，3h 标记「协作不规范」
- Dispatcher 中 ZZ-017（工部）实现了 15min `log.warning`，但未触发 Thread 消息和数据库标记

**实现方案：**

```python
# dispatcher.py 新增检查逻辑（在 _check_loop 中）
def _check_thread_activity(conn):
    """检查执行中奏折的 Thread 反馈活跃度"""
    now = time.time()
    executing = conn.execute(
        "SELECT id, assigned_agent, discord_thread_id, updated_at "
        "FROM zouzhe WHERE state='executing'"
    ).fetchall()
    for z in executing:
        elapsed = now - parse_ts(z['updated_at'])
        if elapsed > 3600 and not flagged_already(z['id'], '1h_alert'):
            # 发送 Thread 提醒 + 通知司礼监
            notify_thread(z, "⚠️ 执行超过 1 小时无反馈，请更新进展")
            mark_flagged(z['id'], '1h_alert')
        if elapsed > 10800 and not flagged_already(z['id'], '3h_flag'):
            # 在 liuzhuan 记录「协作不规范」
            log_liuzhuan(z['id'], 'system', '协作不规范', '超过 3 小时无 Thread 反馈')
            mark_flagged(z['id'], '3h_flag')
```

**所需 DB 变更：**
- `zouzhe` 表新增字段 `activity_flags TEXT`（JSON，记录已发送的提醒类型，防重发）
- 或使用 `zouzhe_log` 中的特殊 action 去重

**负责方：** 兵部  
**工作量：** S（1-2天）  
**验收标准：**
- 创建一个测试奏折，不发 progress，观察 1h 后是否收到 Thread 提醒
- 3h 后查看 `liuzhuan`，确认有「协作不规范」记录

---

### P1-3：并发奏折压力测试

**测试场景设计：**

| 场景 | 操作 | 预期结果 |
|------|------|---------|
| 并发投票 | 同时创建 2 个需要给事中审核的奏折 | 两个奏折的投票数据互不串扰 |
| 多奏折并行执行 | 3 个不同优先级奏折同时进入 executing | urgent 先派发，high 次之，normal 最后 |
| 执行中开新奏折 | 1 个奏折 executing 期间创建新奏折 | 新奏折正常进入规划流程，不影响已执行奏折 |
| DB 锁竞争 | 上述场景同时触发 | 无 SQLITE_BUSY 超时，busy_timeout=30s 应覆盖 |

**执行步骤：**
1. 工部在测试环境（或子目录）初始化测试 DB
2. 按场景依次触发，记录结果
3. 刑部审查：确认并发写入无数据污染、audit log 无缺漏
4. 产出：`docs/TEST-REPORT-concurrent.md`

**负责方：** 工部（执行） + 刑部（安全审计）  
**工作量：** S（1天）  
**前置条件：** P0-2 观察期通过（无已知 bug）后再执行

---

## 三、执行顺序与时间线

```
当前（2026-03-09 23:00 PDT）
  │
  ├─ ✅ P0-1 已达成（Git 工作流已实战验证 3 次）
  │
  ├─ [进行中] P0-2 Dispatcher 稳定观察期
  │    启动时间：2026-03-09 05:18 PDT
  │    截止时间：2026-03-11 05:18 PDT
  │    责任人：工部
  │
  ├─ [立即启动] P1-1a：工部为各 Agent 配置 .env
  │    DDL：P0-2 观察期内完成（不阻塞）
  │    责任人：工部
  │
  ├─ [P0-2 通过后启动] P1-3 并发压力测试
  │    DDL：P0-2 截止后 1 天
  │    责任人：工部 + 刑部
  │
  ├─ [独立推进] P1-2 Thread 活跃度告警
  │    DDL：P1-3 后 2 天
  │    责任人：兵部（代码） + 工部（部署）
  │
  └─ [完成标志] v0.3-alpha
       P0-1 ✅ + P0-2 通过 + P1-1 配置完成 + P1-3 无严重 bug
       P1-2 完成后升为 v0.3-beta
```

---

## 四、方案决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| P1-1 方案选择 | **方案 A（.env 持久化）** | PR #11 已实现，零额外开发成本；.env gitignored 安全 |
| P1-2 去重机制 | **zouzhe_log 记录特殊 action** | 无需 DB schema 变更，利用现有审计基础设施 |
| P1-3 测试环境 | **独立测试 DB（非生产）** | 避免测试数据污染生产数据库 |
| P1 执行顺序 | **P1-1 → P1-3 → P1-2** | P1-1 无需等待（工部配置即可），P1-3 依赖 P0-2 稳定，P1-2 依赖 P1-3 验证无并发 bug |

---

## 五、遗漏问题盘查

经过对当前系统的全面检查，发现以下 ROADMAP-phase2 未提及的问题：

| 问题 | 优先级 | 说明 |
|------|--------|------|
| `DISCORD_FALLBACK_CHANNEL_ID` 未配置时仅 warn，不推送 | P1（补充） | PR #11 后修复了硬编码 default，但各 Agent .env 需配置此值才能收到 fallback 通知 |
| `src/chaoting.db` 测试遗留文件 | P3 | 低风险但占用空间，建议下次工部清理 sprint 时一并处理 |
| `chaoting new` 命令 silijian SOUL.md 引用 | P3 | 已知问题，待 `chaoting new` 实现（v0.3 CLI 增强时一并处理） |

---

## 六、风险与缓解措施

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| P0-2 观察期内发现新 Dispatcher bug | 中 | 高 | 立即开高优奏折，工部先停机再修复 |
| .env 配置遗漏导致部分 Agent 仍需手动 export | 中 | 低 | 工部配置后统一验证，检查 `zouzhe.assigned_agent != 'unknown'` |
| P1-3 测试发现严重并发 bug | 低 | 高 | 压测在独立 DB 进行，不影响生产；发现 bug 立即开奏折 |
| P1-2 告警噪音过多 | 中 | 低 | 初始 1h 阈值可调整为 2h，3h 标记保持不变 |

---

*本文件由吏部（libu_hr）制定，作为 ROADMAP-phase2.md 的执行细化文档。*
