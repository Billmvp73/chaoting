# POLICY-thread-feedback.md — 执行部门 Thread 反馈规范

> 版本：v1.1  
> 制定日期：2026-03-09  
> 制定部门：吏部（libu_hr）  
> 适用范围：所有执行部门（bingbu / gongbu / hubu / libu / xingbu / libu_hr / hubu_data）  
> 依据奏折：ZZ-20260309-010  
> 相关文档：[POLICY-thread-format.md](./POLICY-thread-format.md)（全部门 Thread 标注格式统一规范）

> **本文档专注于执行部门的完成反馈要求、超时处置机制和合规评估标准。**  
> **Thread 消息的标注格式（前缀、emoji、模板结构）请统一参见 POLICY-thread-format.md。**

---

## 一、规范目的

执行部门完成任务后，**必须在对应的 Discord Thread 里发送完成反馈消息**。

制定本规范的原因：

- ✅ **透明化**：司礼监和其他部门能实时掌握进度
- ✅ **可追溯**：所有工作都有记录，便于事后审计
- ✅ **协作化**：其他部门了解做了什么，便于后续衔接

> **背景**：兵部（bingbu）在完成 ZZ-20260308-006 和 ZZ-20260309-002 后，均及时在对应 Thread 发送了完成反馈，是标准范例。工部（gongbu）未遵守此规范，导致司礼监无法及时了解进度。

---

## 二、强制要求

### 触发条件

执行部门调用以下命令后，**必须立即**在对应 Discord Thread 发送完成反馈：

```bash
chaoting done ZZ-XXXXXXXX-NNN "产出" "摘要"
chaoting fail ZZ-XXXXXXXX-NNN "原因"
```

### 时间要求

- `chaoting done` 或 `chaoting fail` 执行后，**30 分钟内**必须发出 Thread 反馈消息
- 反馈消息必须发在**奏折对应的 Discord Thread** 中（Thread ID 在任务描述或派发消息中提供）

---

## 三、标准反馈格式

### 完成时（done）的标准格式

```
✅ ZZ-XXXXXXXX-NNN 已完成

**做了什么（What）**
• [功能/修复的简述，1-3 条]
• 改动文件：[文件路径，+N/-N 行]
• Commit：[SHA]（如适用）
• PR：[#N 链接]（如适用）

**验证情况（Validation）**
• [测试方法，如：在测试环境运行，输出符合预期]
• 验收标准：[已满足 / 部分满足（说明原因）]

**后续（Next）**
• [下一步行动，如：等待 PR review、可直接合并、无需后续]
• [遗留问题或风险（如有）]
```

### 失败时（fail）的标准格式

```
❌ ZZ-XXXXXXXX-NNN 执行失败

**失败原因（Why）**
• [具体失败原因]

**已尝试的方案（Tried）**
• [尝试了什么，结果如何]

**建议（Suggestion）**
• [建议如何解决，或是否需要升级处理]
```

---

## 四、标准示例

### 示例一：编码任务完成（bingbu）

```
✅ ZZ-20260309-002 已完成

**做了什么（What）**
• 新增 tongzhi（通知）表，支持任务完成/失败时推送消息
• 改动文件：src/chaoting（+258 行），init_db.py（+32 行）
• Commit：72b741b
• PR：#15 https://github.com/.../pull/15

**验证情况（Validation）**
• 在本地测试环境运行 chaoting done ZZ-20260309-002，Discord 频道成功收到通知
• 已覆盖 done / fail / timeout 三种事件，验收标准全部满足

**后续（Next）**
• PR #15 已提交，等待 review 后 merge
• 注意：通知开关默认开启，如需关闭需在配置中设置 notify=false
```

### 示例二：运维任务完成（gongbu）

```
✅ ZZ-20260309-005 已完成

**做了什么（What）**
• 更新 chaoting-dispatcher.service，添加 CHAOTING_CLI 环境变量
• 改动文件：install.sh（+12 行），service 模板文件（+3 行）
• 已重启 systemd 服务并验证

**验证情况（Validation）**
• systemctl --user status chaoting-dispatcher 显示 active (running)
• 新建测试奏折 ZZ-TEST-001，dispatcher 成功派发，验收标准满足

**后续（Next）**
• 无遗留问题，服务运行正常
```

### 示例三：任务失败（fail）

```
❌ ZZ-20260309-007 执行失败

**失败原因（Why）**
• Poetry 依赖冲突：requests>=2.28 与 urllib3<2.0 不兼容，无法解锁依赖

**已尝试的方案（Tried）**
• 尝试降级 requests 到 2.27.1 → 破坏其他依赖
• 尝试升级 urllib3 到 2.0.0 → 与 httpx 0.24 不兼容

**建议（Suggestion）**
• 需要整体评估依赖树，建议中书省重新规划，分步升级依赖
```

---

## 五、超时处置机制

### 阶段一：1 小时提醒

执行部门调用 `chaoting done/fail` 后，**1 小时内未在 Thread 发送反馈**：

- 司礼监（silijian）在对应 Thread 发出 ⏰ 提醒
- 提醒格式：`⏰ @{执行部门} ZZ-XXXXXXXX-NNN 已完成超过 1 小时，尚未收到 Thread 反馈，请尽快补发。`

### 阶段二：3 小时标记

**超过 3 小时仍未发送反馈**：

- 司礼监在 Thread 中标记：`⚠️ 协作不规范：{执行部门} 未按时发送 Thread 反馈`
- 在 `dianji` 表中记录该部门的响应性问题：
  ```bash
  chaoting context {agent_id} "compliance:thread_feedback" "超时未反馈（ZZ-XXXXXXXX-NNN，{日期}）" --source ZZ-XXXXXXXX-NNN
  ```
- 累计 3 次不规范记录，向管理层汇报

### 处置豁免

以下情况可申请豁免：

1. **紧急故障响应**：任务执行中发生系统故障，执行部门正在紧急处置
2. **系统不可用**：Discord 服务中断，无法发送消息
3. **明确说明延迟**：在 Thread 内提前说明"将于 X 小时内补发反馈"

---

## 六、执行部门 SOUL.md 要求

所有执行部门的 SOUL.md **必须包含** Thread 反馈规范引用段落，格式如下：

```markdown
## ⚠️ 完成后必须发 Thread 反馈

调用 `chaoting done` 或 `chaoting fail` 后，**30 分钟内**必须在对应 Discord Thread 发送完成反馈。

格式（完成时）：
✅ {ZZ-ID} 已完成
**做了什么（What）**：[改动概述 + commit/PR]
**验证情况（Validation）**：[测试方式 + 是否满足验收标准]
**后续（Next）**：[下一步 / 遗留问题]

格式（失败时）：
❌ {ZZ-ID} 执行失败
**失败原因**：[具体原因]
**已尝试**：[尝试方案及结果]
**建议**：[处置建议]

完整规范：见 docs/POLICY-thread-feedback.md
```

---

## 七、合规评估标准

### 合规（✅）

- `chaoting done/fail` 后 30 分钟内在 Thread 发送反馈
- 反馈包含四要素：What / Validation / Next（done）或 Why / Tried / Suggestion（fail）
- 内容具体可查（含 commit SHA、文件改动、测试方法）

### 部分合规（⚠️）

- 发送了反馈但超过 30 分钟
- 反馈缺少部分要素（如只说"完成了"但无详情）

### 不合规（❌）

- 完成后 1 小时内无任何 Thread 消息
- 反馈内容空洞（如仅"✅ 完成"无任何详情）

---

## 八、规范生效时间

本规范自 2026-03-09 起对所有执行部门生效。

各部门 SOUL.md 需在一周内完成更新，将 Thread 反馈规范纳入工作流程。

---

*本规范由吏部（libu_hr）依据奏折 ZZ-20260309-010 制定，经门下省审议通过。*
