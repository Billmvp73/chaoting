# POLICY-thread-format.md — 全部门 Discord Thread 标注格式规范

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: libu


> 版本：v1.0  
> 制定日期：2026-03-09  
> 制定部门：吏部（libu_hr）  
> 适用范围：朝廷全部 12 个部门  
> 依据奏折：ZZ-20260309-011  
> 相关文档：[POLICY-thread-feedback.md](./POLICY-thread-feedback.md)（执行部门完成反馈详细规范）

---

## 一、核心原则

**所有部门在 Discord Thread 里发送消息，必须以 【部门名】 开头。**

格式：`【部门名】{emoji} {动作摘要}`

---

## 二、部门格式对照表

| 部门 | 标注前缀 | Emoji | 主要内容 | 时间要求 |
|------|---------|-------|---------|---------|
| 司礼监 | `【司礼监】` | 🏛️ | 任务分派、进度追踪、最终裁决 | 实时 |
| 中书省 | `【中书省】` | 📝 | 规划方案、任务分解、步骤明确 | 规划完成后 1h 内 |
| 技术给事中 | `【技术给事中】` | 🔍 | 技术审查意见、可行性评估 | 审查完成后 30min 内 |
| 风险给事中 | `【风险给事中】` | ⚠️ | 风险识别、缓解方案、约束提醒 | 审查完成后 30min 内 |
| 合规给事中 | `【合规给事中】` | ✔️ | 合规性审查、标准符合性 | 审查完成后 30min 内 |
| 资源给事中 | `【资源给事中】` | 💰 | 资源需求评估、预算审查 | 审查完成后 30min 内 |
| 吏部 | `【吏部】` | 👥 | 任务完成状态、管理产出、进度汇报 | 完成后 30min 内 **必须** |
| 户部 | `【户部】` | 💼 | 数据处理完成、变更说明、验证情况 | 完成后 30min 内 **必须** |
| 礼部 | `【礼部】` | 🎖️ | 文档产出、内容摘要、链接 | 完成后 30min 内 **必须** |
| 兵部 | `【兵部】` | ⚔️ | 编码完成、改动说明、commit/PR | 完成后 30min 内 **必须** |
| 刑部 | `【刑部】` | ⚖️ | 审计结果、发现项、整改建议 | 完成后 30min 内 **必须** |
| 工部 | `【工部】` | 🔧 | 部署/运维完成、配置说明、服务状态 | 完成后 30min 内 **必须** |

---

## 三、三类标准模板

### 类型 A：执行部门（六部）

适用：兵部 / 工部 / 户部 / 吏部 / 礼部 / 刑部

**完成时：**

```
【{部门名}】{emoji} 任务完成

【工作内容】
- {做了什么，1-3 条}
- {改动文件 / 数据量 / 文档路径}
- Commit: {SHA}（如适用）/ PR: #{N} {链接}（如适用）

【验证情况】
✓ {验证方式}
✓ 验收标准：{已满足 / 部分满足（说明）}

【状态】
- {后续行动，如：等待 PR review / 无遗留问题 / 风险说明}
```

**失败时：**

```
【{部门名}】{emoji} 任务失败

【失败原因】
- {具体原因}

【已尝试】
- {方案 A → 结果}
- {方案 B → 结果}

【建议】
- {处置建议，是否需要升级}
```

---

### 类型 B：规划部门（中书省）

适用：中书省

```
【中书省】📝 规划方案已提出

【任务分解】
1. {步骤 A：具体内容}
2. {步骤 B：具体内容}
3. {步骤 C：具体内容}

【资源评估】
- 预计工时：{X 天}
- 负责部门：{bingbu / gongbu / ...}
- 审核等级：review_required = {0/1/2/3}
- repo_path：{/absolute/path}

【验收标准】
✓ {标准 1}
✓ {标准 2}
```

**被封驳重提时：**

```
【中书省】📝 方案已修订（第 {N} 次）

【本次修改】
- 针对 {给事中} 封驳意见：{原意见}
- 修改内容：{具体修改}

【更新后的关键步骤】
{...}
```

---

### 类型 C：审查部门（门下省给事中）

适用：技术给事中 / 风险给事中 / 合规给事中 / 资源给事中

```
【{给事中名称}】{emoji} 审查完成

【审查意见】
✓ {通过项}
⚠️ {注意项（有保留的准奏）}
❌ {问题项（封驳理由）}

【建议】
- {具体改进建议 1}
- {具体改进建议 2}

【投票结果】
{GO ✅ / NOGO ❌ / GO with caveats ⚠️}
理由：{一句话说明}
```

---

### 类型 D：司礼监

适用：司礼监（silijian）

**分派奏折时：**

```
【司礼监】🏛️ 奏折已分派

奏折：{ZZ-ID}《{标题}》
分派至：{部门名}
优先级：{high / normal / low}
审核等级：review_required = {0/1/2/3}
预期完成：{时间或"尽快"}
```

**最终裁决时（三驳或异常）：**

```
【司礼监】🏛️ 御前裁决

奏折：{ZZ-ID}
裁决：{准奏 ✅ / 驳回 ❌}
理由：{裁决原因}
后续：{行动要求}
```

**进度催办时：**

```
【司礼监】🏛️ ⏰ 进度催办

@{部门} {ZZ-ID} 已完成超过 {N} 小时，尚未收到 Thread 反馈，请尽快补发。
```

---

## 四、示例

### 示例 1：兵部完成编码任务

```
【兵部】⚔️ 任务完成

【工作内容】
- 新增 tongzhi 表，支持任务完成/失败时推送消息
- 改动：dispatcher.py +258 行，init_db.py +32 行
- Commit: 72b741b
- PR: #15 https://github.com/.../pull/15

【验证情况】
✓ 本地测试环境验证：chaoting done 触发后 Discord 成功收到通知
✓ 覆盖 done / fail / timeout 三种事件，验收标准全部满足

【状态】
- PR #15 已提交，等待 review 后 merge
- 注意：通知开关默认开启，如需关闭需配置 notify=false
```

### 示例 2：中书省提交规划

```
【中书省】📝 规划方案已提出

【任务分解】
1. 在 init_db.py 新增 tongzhi 表
2. 修改 chaoting CLI：done/fail 命令触发通知
3. 修改 dispatcher.py：超时事件触发通知
4. 写单元测试验证通知流程

【资源评估】
- 预计工时：2 天
- 负责部门：bingbu
- 审核等级：review_required = 1
- repo_path：/home/tetter/.themachine/chaoting

【验收标准】
✓ chaoting done 触发后 Discord 收到通知
✓ 支持 done / fail / timeout 三种事件
✓ 通知开关可配置
```

### 示例 3：技术给事中审查

```
【技术给事中】🔍 审查完成

【审查意见】
✓ 数据库 Schema 设计合理，tongzhi 表字段完整
✓ 触发机制与 dispatcher 现有架构兼容
⚠️ 需补充通知失败时的降级处理（不影响主流程）
❌ 缺少对 Discord API 限流（rate limit）的处理

【建议】
- 通知发送加 try/except，失败写入日志但不阻断主流程
- 添加发送间隔限制，避免短时间内大量通知触发 Discord 限流

【投票结果】
GO with caveats ⚠️
理由：方案可行，需在实现中补充上述两点容错处理
```

### 示例 4：风险给事中封驳

```
【风险给事中】⚠️ 审查完成

【审查意见】
✓ 通知功能本身为只读/附加操作，不影响核心流程
❌ 缺少回滚方案：若通知功能引入 bug，如何快速禁用？
❌ Discord webhook token 存储方式未说明，可能存在安全风险

【建议】
- 方案中需明确 notify=false 配置开关的实现方式
- Discord token 应通过环境变量注入，不得硬编码

【投票结果】
NOGO ❌
理由：需补充快速禁用机制和 token 安全存储方案后重新提交
```

### 示例 5：工部完成运维任务

```
【工部】🔧 任务完成

【工作内容】
- 更新 chaoting-dispatcher.service，添加 CHAOTING_CLI 环境变量
- 修改 install.sh +12 行，service 模板 +3 行
- 已重启 systemd 服务

【验证情况】
✓ systemctl --user status chaoting-dispatcher 显示 active (running)
✓ 测试奏折 ZZ-TEST-001 派发成功，验收标准满足

【状态】
- 无遗留问题，服务运行正常
```

---

## 五、与 POLICY-thread-feedback.md 的关系

| 文档 | 覆盖范围 | 核心内容 |
|------|---------|---------|
| 本文档（POLICY-thread-format.md） | **全部 12 个部门** | Thread 消息标注格式、前缀规范、各类模板 |
| [POLICY-thread-feedback.md](./POLICY-thread-feedback.md) | **执行六部** | 完成反馈的强制要求、超时处置机制、合规评估标准 |

**两份文档互为补充，不重复：**
- 格式问题看本文档
- 执行部门的超时处置和合规评估看 POLICY-thread-feedback.md

---

## 六、自动化强制执行机制（ZZ-20260309-017）

> 本节记录工部依据 ZZ-20260309-017 实现的自动化机制，与手动规范互为保障。

### 6.1 CLI 自动推送（已实现）

`chaoting` CLI 在以下命令执行后**自动**向 Discord Thread 推送消息：

| 命令 | 推送时机 | 消息格式函数 |
|------|---------|------------|
| `chaoting done` | 任务完成时 | `_fmt_done_thread()` — 【部门】✅ 前缀 + 工作内容 + 输出概述 |
| `chaoting fail` | 任务失败时 | `_fmt_fail_thread()` — 【部门】❌ 前缀 + 失败原因 |
| `chaoting plan` | 规划提交时 | `_fmt_plan_thread()` — 【中书省】📝 前缀 + 规划方向 |
| `chaoting vote` | 投票完成时 | `_fmt_vote_thread()` — 【给事中】🔍/⚠️ 前缀 + GO/NOGO + 审查意见 |
| `chaoting revise` | 发起返工时 | `_fmt_revise_thread()` — 【发起部门】🔄 前缀 + 返工原因 |

所有消息格式均遵循本文档第二节的部门前缀规范（`_dept_prefix()` 映射表）。

### 6.2 Dispatcher 兜底补发（已实现）

若 CLI 端 `_send_thread_notify()` 失败（网络抖动、进程中断等），dispatcher 在下一次 poll 循环中通过 `_check_new_done_failed()` 检测到状态变更但无 tongzhi 记录时，自动补发通知。

**触发条件：**
- 奏折状态为 done / failed / timeout
- tongzhi 表中无对应 event_type 条目

**补发机制：** `notify_enqueue()` → `notify_worker()` → `_send_discord_thread()`

### 6.3 Thread 活跃度监控（已实现）

Dispatcher 每 **5 分钟**检查一次所有活跃奏折（planning / reviewing / executing）：

- 若奏折有 `discord_thread_id` 但 `last_thread_activity` 超过 **15 分钟**无更新 → `log.warning`
- 告警格式：`Thread 活跃度告警 {ZZ-ID} [{state}] 超过 15 分钟无 Thread 消息 | assigned={agent}`

**`last_thread_activity` 更新时机：**
- CLI `done`/`fail` 成功推送后（`_update_last_thread_activity(db, zouzhe_id)`）
- Dispatcher `notify_worker()` 成功发送 tongzhi 后

### 6.4 部门前缀映射表（`_dept_prefix()` 实现）

```python
_MAP = {
    "bingbu":      "【兵部】⚔️",
    "gongbu":      "【工部】🔧",
    "hubu":        "【户部】💼",
    "libu":        "【吏部】👥",
    "xingbu":      "【刑部】⚖️",
    "zhongshu":    "【中书省】📝",
    "menxia":      "【门下省】🏛️",
    "silijian":    "【司礼监】🏛️",
    "jishi_tech":  "【技术给事中】🔍",
    "jishi_risk":  "【风险给事中】⚠️",
    "jishi_resource":   "【资源给事中】💰",
    "jishi_compliance": "【合规给事中】✔️",
}
```

---

## 七、规范生效时间

本规范自 2026-03-09 起对全体部门生效。

各部门 SOUL.md 需在一周内更新，将 Thread 标注规范纳入工作流。

---

*本规范由吏部（libu_hr）依据奏折 ZZ-20260309-011 制定，经门下省审议通过。*  
*第六节（自动化强制执行机制）由工部（gongbu）依据奏折 ZZ-20260309-017 补充，2026-03-09。*
