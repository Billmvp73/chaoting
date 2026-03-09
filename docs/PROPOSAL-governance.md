# 朝廷核心职能与部门分工——建议方案

> 奏折编号：ZZ-20260308-003  
> 撰写部门：吏部（libu_hr）  
> 日期：2026-03-08  
> 状态：提案草案，供各部门参考审议

---

## 第一问：职能定位与司礼监监察权限

### 朝廷核心职能

朝廷系统应聚焦以下三大核心职能，超出此范围的事务不属于系统管辖：

| 职能 | 描述 | 关键指标 |
|------|------|----------|
| **任务编排** | 接收奏折 → 中书省规划 → 门下省审核（可选）→ 六部执行 | 任务流转无卡点，超时自动重试 |
| **质量审核** | 门下省给事中对执行方案进行多维度审议，确保方案可行、风险可控 | 漏审率为 0，封驳意见可追溯 |
| **知识积累** | 通过 `dianji`（典籍）和 `qianche`（前车之鉴）沉淀经验，减少重复踩坑 | 每次任务完成后 context 有效写回 |

**不属于朝廷职能的事项：**
- 业务逻辑实现（由六部各自负责）
- 外部服务调用（由各部门 agent 自行处理）
- 用户权限管理（由宿主系统 OpenClaw 负责）

---

### 司礼监（silijian）监察权限边界

司礼监是朝廷的**监察总管**，不参与日常任务流转，仅在以下三类情形介入：

#### 权限范围（有权干预）

| 场景 | 触发条件 | 可执行操作 |
|------|----------|------------|
| **三驳呈御前** | 奏折被门下省连续封驳 3 次，状态变为 `failed`，`error = '三驳失败，呈御前裁决'` | 人工审阅方案，强制 `done` 或 `fail` |
| **审核超时告警** | 给事中超时未投票，系统自动准奏但需知会司礼监 | 补充投票记录，或事后追责 |
| **系统异常告警** | dispatcher 出现 `dispatch_error`、orphan 数量异常等 | 排查日志，手动恢复卡住的奏折 |

#### 权限边界（不得越权）

- ❌ **不得直接派发奏折**：创建奏折走 `created` 状态，由 dispatcher 自动分发给中书省
- ❌ **不得绕过门下省审核**：如需紧急执行，应将 `review_required = 0` 写入奏折创建时，而非事后绕过
- ❌ **不得修改已执行中的方案**：`plan` 字段一旦进入 `executing` 状态即视为锁定
- ❌ **不得直接操作六部 agent**：司礼监只监察朝廷系统本身，不干涉六部具体执行过程

#### 司礼监操作工具

```bash
# 查看奏折状态
chaoting status <ZZ-ID>

# 强制裁决（三驳场景）
chaoting done <ZZ-ID> "裁决结果" "裁决摘要"
chaoting fail <ZZ-ID> "裁决原因"

# 查看系统日志（建议直接查 DB）
sqlite3 chaoting.db "SELECT * FROM liuzhuan WHERE zouzhe_id='<ZZ-ID>' ORDER BY timestamp DESC"
```

---

## 第二问：review_required 四级审核标准

### 标准定义

现行 `review_required` 字段为 0/1 布尔值，建议**升级为 0/1/2/3 四级标准**，以支持更细粒度的风险控制：

| 等级 | 名称 | 适用场景 | 审核人 | 状态跳过 |
|------|------|----------|--------|----------|
| **0** | 免审执行 | 低风险、幂等操作（查询、文档生成、日志分析）| — | `planning → executing` 直通 |
| **1** | 单审 | 中等风险、可回滚操作（代码修改、配置变更）| 风险给事中（jishi_risk）| `planning → reviewing → executing` |
| **2** | 双审（默认）| 较高风险、涉及外部依赖或数据变更 | 技术给事中 + 风险给事中 | `planning → reviewing → executing` |
| **3** | 全审 | 高风险、不可逆操作（DB 迁移、生产部署、安全审计）| 全部四名给事中 | `planning → reviewing → executing` |

### 各等级详细说明

#### 等级 0 — 免审直接执行

**适用条件（满足以下任一）：**
- 操作完全幂等（重复执行不产生副作用）
- 操作范围仅限只读（查询、分析、报告生成）
- 紧急修复且操作者已人工确认方案

**典型任务：**
- 生成周报 / 月报
- 读取 Git 历史分析趋势
- 查询数据库（SELECT ONLY）
- 文档更新（README、注释）

**风险提示：** 免审不代表免责。六部执行结果仍需写入 `zoubao`，出问题通过 `qianche` 学习。

---

#### 等级 1 — 风险单审

**适用条件：**
- 修改代码逻辑，但有完整测试覆盖
- 配置文件变更，有回滚方案

**审核人：** 风险给事中（`jishi_risk`）

**审核重点：**
- 是否有回滚方案？
- 是否有破坏性操作（删除、截断）？
- 是否影响生产环境？

**review_agents 设置：**
```json
{"review_required": 1, "review_agents": ["jishi_risk"]}
```

---

#### 等级 2 — 技术+风险双审（推荐默认）

**适用条件：**
- 新功能开发
- 涉及外部 API 调用
- 数据库 DDL 变更（加字段、加索引）
- 第三方依赖升级

**审核人：** 技术给事中（`jishi_tech`）+ 风险给事中（`jishi_risk`）

**审核重点：**
- 技术可行性、架构合理性（`jishi_tech`）
- 回滚方案、数据安全（`jishi_risk`）

**review_agents 设置：**
```json
{"review_required": 2, "review_agents": ["jishi_tech", "jishi_risk"]}
```

**建议：** 新建奏折时若不确定等级，默认填 2。

---

#### 等级 3 — 全审（军国大事）

**适用条件（满足任一即触发）：**
- 生产数据库迁移 / DROP / 批量 UPDATE
- 生产环境部署（服务重启、版本发布）
- 安全相关变更（权限、密钥、证书）
- 合规敏感操作（用户数据导出、隐私处理）
- 预计耗时超过 4 小时的大型任务

**审核人：** 全部四名给事中并行审议

| 给事中 | 关注点 |
|--------|--------|
| `jishi_tech` | 技术可行性、架构合理性、实现路径 |
| `jishi_risk` | 回滚方案、数据安全、破坏性操作 |
| `jishi_resource` | 工时合理性、资源消耗、Agent 可用性 |
| `jishi_compliance` | 安全合规、权限边界、敏感数据处理 |

**超时策略：** 等级 3 对应 `priority = critical`，审核超时不默认准奏，直接标为 `failed` 并通知司礼监人工介入。

**review_agents 设置：**
```json
{"review_required": 3, "review_agents": ["jishi_tech", "jishi_risk", "jishi_resource", "jishi_compliance"]}
```

---

### 等级选择决策树

```
任务类型
├── 只读 / 幂等？
│    └── 是 → 等级 0（免审）
│
├── 有回滚方案 + 无数据变更？
│    └── 是 → 等级 1（风险单审）
│
├── 新功能 / 外部依赖 / DDL 变更？
│    └── 是 → 等级 2（技术+风险双审，默认）
│
└── 生产部署 / 不可逆 / 合规敏感？
     └── 是 → 等级 3（全审）
```

### 向下兼容说明

现有 `review_required = 0/1` 布尔字段与新标准兼容：
- 旧值 `0` → 新标准等级 0（免审）
- 旧值 `1` → 新标准等级 2（双审，取最安全的非全审选项）

代码层面，`cmd_plan` 和 dispatcher 的分支判断改为：

```python
if zouzhe["review_required"] == 0:
    # 直接执行
elif zouzhe["review_required"] in (1, 2, 3):
    # 进入 reviewing 状态
    # review_agents 已在奏折创建时设置
```

---

## 第三问：各部门接入方式与规范

### 接入流程总览

```
部门接入步骤
1. 确认 workspace 目录存在
   → $OPENCLAW_STATE_DIR/workspace-{agent_id}/

2. 编写 SOUL.md（角色定义文件）
   → 参见下方模板规范

3. 注册 OpenClaw agent 配置
   → openclaw.json agents.list

4. 验证接入
   → 手动发送测试奏折，确认 pull/done/fail 命令正常
```

### CLI 命令集

所有部门 agent 必须掌握以下命令：

```bash
# 接收奏折（必须）
chaoting pull <ZZ-ID>

# 汇报进展（建议每完成一个步骤调用一次）
chaoting progress <ZZ-ID> "进展描述"

# 完成任务（必须，执行成功时）
chaoting done <ZZ-ID> "产出摘要" "完整摘要"

# 标记失败（必须，无法完成时）
chaoting fail <ZZ-ID> "失败原因"

# 更新领域知识（可选，鼓励积累）
chaoting context {agent_id} "{context_key}" "{context_value}" --source <ZZ-ID>
```

**给事中额外命令：**
```bash
# 投票（给事中专用，--as 参数必填）
chaoting vote <ZZ-ID> go "准奏理由" --as {jishi_id}
chaoting vote <ZZ-ID> nogo "封驳理由（需明确指出修改点）" --as {jishi_id}
```

---

### JSON 输入输出格式

#### pull 返回格式

```json
{
  "ok": true,
  "zouzhe": {
    "id": "ZZ-YYYYMMDD-NNN",
    "title": "任务标题",
    "description": "任务描述",
    "state": "executing",
    "priority": "normal|high|critical",
    "plan": {
      "steps": ["步骤1", "步骤2"],
      "target_agent": "libu_hr",
      "repo_path": "/absolute/path",
      "target_files": ["file1.py"],
      "acceptance_criteria": "验收标准"
    }
  },
  "dianji": [
    {"key": "上下文键", "value": "上下文值", "confidence": "fresh|stale"}
  ],
  "qianche": ["前车之鉴1", "前车之鉴2"],
  "liuzhuan": [
    {"from": "dispatcher", "to": "libu_hr", "action": "dispatch", "remark": "..."}
  ]
}
```

**Agent 必须处理的字段：**
- `zouzhe.plan.steps` — 执行步骤清单
- `zouzhe.plan.acceptance_criteria` — 验收标准（done 时需确认已满足）
- `dianji` — 相关上下文，帮助理解任务背景
- `qianche` — 历史经验教训，避免重复踩坑

#### done / fail 参数格式

```bash
# done：第一个参数为产出（简短，用于 liuzhuan 记录），第二个为摘要（详细）
chaoting done ZZ-20260308-001 \
  "PR #42 已合并" \
  "完成风控模块重构，含单元测试 12 条，覆盖率 92%"

# fail：说明失败原因及已尝试的方案
chaoting fail ZZ-20260308-001 \
  "依赖包版本冲突：requests>=2.28 与 urllib3<2.0 不兼容，已尝试降级 requests 无效"
```

---

### SOUL.md 模板规范

每个 agent 的 SOUL.md 必须包含以下三个部分：

#### 必填部分

```markdown
# SOUL.md — {中文名} ({agent_id})

你是{中文名}，朝廷系统的{职能描述}。

## 工作流程

1. 接旨：`chaoting pull ZZ-XXXXXXXX-NNN`
2. 阅读 plan，按方案执行
3. 汇报进展：`chaoting progress ZZ-XXXXXXXX-NNN "进展描述"`
4. 完成：`chaoting done ZZ-XXXXXXXX-NNN "产出" "摘要"`
5. 失败：`chaoting fail ZZ-XXXXXXXX-NNN "原因"`

## 擅长领域

{具体职能描述，2-5 条}
```

#### 推荐补充部分

```markdown
## 注意事项

- 执行前必须确认 acceptance_criteria，完成后核对是否满足
- 遇到不确定的变更，优先标记 fail 并说明原因，不要强行执行
- 每完成一个关键步骤，调用 chaoting progress 记录进展（防超时）
- 积累领域知识：用 chaoting context 写回重要发现

## 前车之鉴

{运行时由 chaoting pull 返回的 qianche 字段填充，此处留空}
```

---

### OpenClaw 配置注册规范

每个 agent 在 `openclaw.json` 的 `agents.list` 中需要以下字段：

```json
{
  "id": "libu_hr",
  "workspace": "/home/user/.openclaw/workspace-libu_hr",
  "model": "anthropic/claude-sonnet-4-6",
  "identity": {
    "name": "吏部",
    "emoji": "👔"
  }
}
```

**必填字段：**
- `id` — 与奏折 `target_agent` 字段对应，必须完全匹配
- `workspace` — 绝对路径，包含 SOUL.md 的目录
- `model` — 建议各部门统一使用同一模型，避免行为差异

**可选字段：**
- `identity.name` — 显示名称
- `identity.emoji` — 识别符号

---

### 快速验证接入流程

部门完成配置后，可通过以下方式验证接入是否正常：

```bash
# 步骤 1：创建测试奏折（review_required=0，直接执行）
sqlite3 chaoting.db "
  INSERT INTO zouzhe (id, title, description, state, priority, review_required)
  VALUES ('ZZ-TEST-001', '接入测试', '请执行 chaoting done 命令', 'executing', 'low', 0);
  
  INSERT INTO liuzhuan (zouzhe_id, from_role, to_role, action, remark)
  VALUES ('ZZ-TEST-001', 'dispatcher', 'libu_hr', 'dispatch', 'integration test');
"

# 步骤 2：agent 拉取并完成
chaoting pull ZZ-TEST-001
chaoting done ZZ-TEST-001 "接入验证通过" "工作流正常"

# 步骤 3：确认状态
sqlite3 chaoting.db "SELECT id, state, output FROM zouzhe WHERE id='ZZ-TEST-001'"
# 预期：state = done
```

---

## 附录：部门职责速查表

| Agent ID | 中文名 | 职能 | 典型任务 |
|----------|--------|------|----------|
| `silijian` | 司礼监 | 监察总管 | 三驳裁决、系统告警处理 |
| `zhongshu` | 中书省 | 任务规划 | 方案制定、封驳后修改 |
| `jishi_tech` | 技术给事中 | 技术审核 | 技术可行性、架构评审 |
| `jishi_risk` | 风险给事中 | 风险审核 | 回滚方案、安全影响 |
| `jishi_resource` | 资源给事中 | 资源审核 | 工时评估、预算审核 |
| `jishi_compliance` | 合规给事中 | 合规审核 | 权限边界、数据合规 |
| `bingbu` | 兵部 | 编码开发 | 功能实现、Bug 修复 |
| `gongbu` | 工部 | 运维部署 | 环境配置、服务部署 |
| `hubu` | 户部 | 数据处理 | 数据迁移、ETL |
| `libu` | 礼部 | 文档撰写 | README、API 文档 |
| `xingbu` | 刑部 | 安全审计 | 漏洞扫描、权限审计 |
| `libu_hr` | 吏部 | 项目管理 | 里程碑规划、进度跟踪 |
| `hubu_data` | 户部（数据）| 数据专项 | 报表生成、数仓 |

---

*本提案由吏部（libu_hr）依据 SPEC.md、SPEC-menxia.md 及 DESIGN-agent-setup.md 整理，供朝廷中枢制定统一标准参考。*
