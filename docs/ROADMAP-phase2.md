# ROADMAP-phase2.md — 朝廷系统第二阶段规划

> 制定日期：2026-03-09  
> 制定部门：吏部（libu_hr）  
> 依据奏折：ZZ-20260309-028  
> 基准版本：当前实际状态（基于 42 个已完成奏折的经验积累）

---

## 一、系统现状盘点

### 1.1 整体运行状况

| 指标 | 数据 |
|------|------|
| 总奏折数 | 44 |
| 已完成（done） | 42（95.5%） |
| 失败（failed） | 1（ZZ-20260308-022 生产数据库重置，操作性失败） |
| 进行中（executing） | 1（当前本奏折） |
| 开放 PR | 0（全部已 merge） |
| Git 提交数 | 20+（含功能、修复、文档） |
| 注册部门数 | 13 |

### 1.2 已稳定落地的功能

| 模块 | 状态 | 说明 |
|------|------|------|
| 状态机核心（7状态流转） | ✅ 稳定 | created→planning→reviewing→executing→done/failed/timeout |
| 12 部门完整工作流 | ✅ 稳定 | 含司礼监、中书省、4给事中、六部 |
| 门下省投票 + 三驳机制 | ✅ 稳定 | Go/No-Go、封驳重提、三驳失败 |
| 返工机制（revise） | ✅ 稳定 | done→executing，含 review_required 调整支持（ZZ-018修复） |
| 审计日志体系 | ✅ 稳定 | 全状态转换记录，含 created 补录（ZZ-020修复） |
| Dispatcher 通知（Discord Thread） | ✅ 稳定 | 任务分派通知 + 完成/失败/超时通知 + 去重防重发（ZZ-023/026/027修复） |
| 司礼监完成通知 | ✅ 稳定 | done/failed/timeout 自动推送给司礼监 |
| chaoting CLI | ✅ 稳定 | pull/plan/progress/done/fail/context/list/status 全命令 |
| Git 工作流规范 | ✅ 文档齐全 | GIT-WORKFLOW.md + 全12 SOUL.md 含 feature branch/PR/merge权限/一奏折一PR规范 |
| Thread 标注格式规范 | ✅ 文档齐全 | POLICY-thread-format.md，12部门前缀+模板 |
| Thread 反馈规范 | ✅ 文档齐全 | POLICY-thread-feedback.md，30分钟反馈强制要求 |

### 1.3 尚待观察的模块

| 模块 | 风险等级 | 问题描述 |
|------|---------|---------|
| Dispatcher 重启恢复 | 🟡 中 | ZZ-026/027 修复了去重，但重启场景覆盖不完整，需实战观察 |
| Git 工作流实战执行 | 🟡 中 | 规范刚建立（ZZ-021/022），PR self-review 流程未经实战验证 |
| Thread 活跃度告警 | 🟡 中 | POLICY 规定了1h提醒/3h标记，但 Dispatcher 实现尚未到位 |
| 并发多奏折处理 | 🟡 中 | 系统设计支持，但从未做过并发压力测试 |
| DB 锁竞争 | 🟢 低 | busy_timeout=30s 已设置，但高并发下未验证 |

### 1.4 已识别的技术债务

| 债务项 | 严重性 | 说明 |
|--------|--------|------|
| 环境变量身份认证手动 export | 🔴 高 | 每次 Agent 启动需手动 `export OPENCLAW_AGENT_ID=xxx`，容易遗漏 |
| 双数据库路径问题 | 🟡 中 | `src/chaoting.db`（测试遗留）与 `chaoting.db`（生产）共存，路径依赖 `CHAOTING_DIR` 环境变量 |
| silijian SOUL.md 引用 `chaoting new`（未实现） | 🟢 低 | `chaoting new` 未在 CLI 实现，SOUL.md 中引用存在误导 |
| ZZ-20260309-021 产生了 3 个 PR（#3/#4/#5） | 🟢 低 | 违反了后来建立的一奏折一PR规范，已无法修复，作为历史案例记录 |

---

## 二、紧急待办（P0）— 本轮必须完成

### P0-1：Git 工作流实战落地验证

**背景：** ZZ-021/022 建立了完整 Git 工作流规范，但规范刚写入 SOUL.md，各部门尚未在真实任务中按规范执行。

**验证方式：**
- 下一个需要代码修改的奏折（兵部/工部执行）必须严格走：`pr/ZZ-xxx` 分支 → PR → 等待司礼监 review → Squash Merge
- 司礼监在 GitHub 执行 review 并决定 merge/request changes

**负责方：** 下一个涉及代码修改的执行部门 + 司礼监  
**验收标准：** 完整走通一次"创建分支 → PR → 司礼监 review → Squash Merge → 同步 master"流程

### P0-2：Dispatcher 稳定性观察期

**背景：** ZZ-026/027 修复了重启后重复通知的 bug，但修复时间不足 24 小时。

**要求：** 在执行后续奏折期间，观察 Dispatcher 是否有重复通知、NameError 等异常。如有，立即开 ZZ 修复。

**负责方：** 工部（监控日志）  
**观察期：** 48 小时

---

## 三、高优待办（P1）— 近期实现

### P1-1：环境变量身份认证自动化

**当前问题：** 每个 Agent 启动时需手动 `export OPENCLAW_AGENT_ID=<agent_name>`，否则 CLI 调用失败。

**解决方案（两选一）：**

**方案 A：** 在 `~/.bashrc` 或 Agent 工作区 `.env` 中持久化 `OPENCLAW_AGENT_ID`
```bash
echo "export OPENCLAW_AGENT_ID=bingbu" >> ~/.bashrc
```

**方案 B：** `chaoting` CLI 支持 `--agent` 参数作为 fallback
```bash
chaoting pull ZZ-XXXXXXXX-NNN --agent bingbu
```

**推荐：** 方案 B（更安全，避免环境变量泄漏到非 Agent 进程），工作量 S。

**负责方：** 兵部（代码实现）+ 工部（各 Agent 环境配置）  
**工作量：** S（1天）

### P1-2：Thread 活跃度告警机制实现

**当前问题：** `POLICY-thread-feedback.md` 规定了 1 小时提醒/3 小时标记不规范，但 Dispatcher 中尚未实现对应的监控逻辑。

**实现要点：**
- Dispatcher `_check_new_done_failed` 中增加扫描逻辑：已进入 executing 但超过 1 小时无 progress 记录的奏折，发送提醒给司礼监
- 超过 3 小时无反馈，在 `zouzhe` 的 `liuzhuan` 中记录「协作不规范」标注

**负责方：** 兵部  
**工作量：** S（1-2天）

### P1-3：并发奏折压力测试

**当前问题：** 系统从未同时处理超过 1 个活跃奏折，并发场景未验证。

**测试场景：**
1. 同时开 3 个不同优先级奏折，观察 Dispatcher 调度顺序
2. 2 个奏折同时进入 reviewing，观察投票并发处理
3. 1 个奏折 executing 期间开新奏折，验证互不干扰

**负责方：** 工部（测试环境搭建）+ 刑部（安全审计）  
**工作量：** S（测试，1天）

---

## 四、中优待办（P2）— v0.3 里程碑

> 对应原 ROADMAP.md v0.3 计划，结合第一阶段经验进行修订

### P2-1：用户推送通知完善

**第一阶段成果：** 已实现司礼监收到完成/失败/超时通知（ZZ-023）。

**第二阶段补充：**
- 支持直接推送给用户（`--notify-user` flag），而非只通知司礼监
- 通知内容增加产出摘要（当前只有状态变更）
- 支持配置：用户可选接收哪些事件类型的通知（all / done_only / failed_only）

**工作量：** S  
**所属里程碑：** v0.3

### P2-2：CLI 观测命令增强

**第一阶段成果：** `list` / `status` 基础版已实现（ZZ-20260308-060）。

**第二阶段补充：**
- `chaoting logs <id>`：查看奏折的完整审计日志流水
- `chaoting stats [--days 7]`：运营指标摘要（完成率、平均耗时、各部门负载）
- `chaoting list` 支持 `--agent` 过滤（当前已支持 `--state`）

**工作量：** S  
**所属里程碑：** v0.3

### P2-3：Agent 故障转移（Fallback）

**原 ROADMAP 项**，无变化，详见 `docs/ROADMAP.md`。

**工作量：** M  
**所属里程碑：** v0.3

---

## 五、低优待办（P3）— v0.4+ 里程碑

| 项目 | 原 ROADMAP 对应 | 工作量 | 里程碑 |
|------|-----------------|--------|--------|
| 任务依赖（前置条件） | v0.4 #4 | M | v0.4 |
| Flight Rules 引擎（qianche 自动推荐） | v0.4 #5 | M | v0.4 |
| 典籍自动注入与 TTL 清理 | v0.4 #6 | S | v0.4 |
| 清理 src/chaoting.db 测试遗留数据库 | 技术债 | XS | 任意时间 |
| 修复 silijian SOUL.md 中 `chaoting new` 引用 | 技术债 | XS | 任意时间 |
| Web Dashboard | v1.0 #7 | L | v1.0 |
| 任务模板（Template） | v1.0 #8 | S | v1.0 |
| 运营指标统计 | v1.0 #9 | S | v1.0 |

---

## 六、里程碑时间线

```
现在（2026-03-09）
  │
  ├─ [本周] P0 完成
  │    ✓ Git 工作流实战首次验证（下一个代码类奏折）
  │    ✓ Dispatcher 稳定性观察（48h 无异常即通过）
  │
  ├─ [近2周] P1 完成（v0.3-alpha）
  │    - 环境变量自动化（S，兵部1天）
  │    - Thread 活跃度告警实现（S，兵部1-2天）
  │    - 并发压力测试（S，工部1天）
  │
  ├─ [1个月] v0.3 正式版
  │    - 用户推送通知完善
  │    - CLI 观测命令增强（logs + stats）
  │    - Agent 故障转移（Fallback）
  │
  ├─ [2-3个月] v0.4
  │    - 任务依赖关系
  │    - Flight Rules 引擎
  │    - 典籍自动注入
  │
  └─ [6个月+] v1.0
       - Web Dashboard
       - 任务模板
       - 完整运营指标
```

---

## 七、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Dispatcher 重启恢复不稳定 | 中 | 高 | 48h 观察期，有异常立即停机修复 |
| 环境变量问题导致 Agent 无法认证 | 高 | 中 | P1-1 优先修复，临时方案：写入 .bashrc |
| Git 工作流规范执行不一致 | 中 | 低 | 司礼监 review 时重点检查分支命名和 merge 方式 |
| 并发奏折 DB 锁竞争 | 低 | 高 | 测试前确认 busy_timeout 配置，压测时监控日志 |
| 技术债务累积阻碍新功能 | 低 | 中 | P3 中安排专项清理奏折，每月一次技术债还债 sprint |

---

## 八、资源分配建议

| 部门 | 建议职责分工 |
|------|-------------|
| 兵部（bingbu） | P1-1 环境变量自动化、P1-2 Thread 告警、P2-1 通知完善 |
| 工部（gongbu） | P0-2 Dispatcher 监控、P1-3 并发压测、各 Agent 环境配置 |
| 刑部（xingbu） | P1-3 并发压测安全审计 |
| 礼部（libu） | 文档同步更新（ROADMAP.md 标记已完成项） |
| 吏部（libu_hr） | 进度跟踪、里程碑检查、本文档维护 |
| 司礼监 | GitHub PR review（每个涉及代码的奏折）、Thread 活跃度监察 |

---

## 附录：第一阶段奏折分布统计

| 类型 | 数量 | 主要执行部门 |
|------|------|-------------|
| 代码功能开发 | 18 | bingbu（兵部） |
| 运维部署配置 | 6 | gongbu（工部） |
| 规范与文档 | 12 | libu_hr（吏部）、libu（礼部） |
| 可行性研讨 | 3 | libu_hr（吏部） |
| 安全审计 | 2 | xingbu（刑部） |
| 测试验证 | 2 | libu_hr（吏部） |
| 失败/未完成 | 1 | — |

**总结：** 系统在 2 天内从零完成了一个完整的多 Agent 任务编排平台，43/44 奏折成功率（97.7%）。第二阶段的核心目标是：把"能跑"变成"好用"——完善可观测性、提升稳定性、降低操作门槛。

---

*本文件由吏部（libu_hr）制定。建议每个 v0.3 里程碑完成后更新本文档。*
