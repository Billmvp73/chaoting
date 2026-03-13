# WORKFLOW-zhongshu.md — 中书省规划工作流详细指南

> 版本：v1.0 | 适用角色：zhongshu (planner)

---

## 1. 接旨

```bash
$CHAOTING_CLI pull ZZ-XXXXXXXX-NNN
```

输出包含：zouzhe 详情、dianji（领域知识）、qianche（经验教训）、liuzhuan（流转历史）、plan_file、worktree_path。

## 2. 分析与规划

- 阅读任务 description 和 acceptance_criteria
- 查阅 dianji 了解目标 agent 的领域知识
- 查阅 qianche 规避已知风险
- 如有返工上下文（revise_history），重点阅读封驳原因

## 3. 提交 Plan JSON

```bash
$CHAOTING_CLI plan ZZ-XXXXXXXX-NNN '<plan_json>'
```

### Plan JSON 格式

```json
{
  "steps": ["步骤1", "步骤2", "步骤3"],
  "target_agent": "bingbu",
  "repo_path": "/absolute/path/to/repo",
  "target_files": ["src/main.py"],
  "acceptance_criteria": "验收标准描述",
  "planning_version": 1,
  "description": "任务描述",
  "title": "简短标题"
}
```

**必填字段**：`target_agent`, `steps`
**建议字段**：`repo_path`, `target_files`, `acceptance_criteria`, `planning_version`

### planning_version 锁定

- pull 返回的 `planning_version` 必须回传到 plan JSON
- 版本不匹配会被拒绝，需重新 pull

## 4. 可用执行部门

| 部门 | Agent ID | 适用场景 |
|------|----------|---------|
| 兵部 | bingbu | 编码开发、Bug 修复、单元测试 |
| 工部 | gongbu | 运维部署、环境配置、CI/CD |
| 户部 | hubu | 数据处理、数据库变更、ETL |
| 礼部 | libu | 文档撰写、README、API 文档 |
| 刑部 | xingbu | 安全审计、漏洞扫描、权限审查 |
| 吏部 | libu_hr | 项目管理、里程碑规划、进度跟踪 |

## 5. 封驳重提（gate-reject 处理）

当门下省封驳时：

1. 重新 `pull` 获取最新状态（含封驳原因在 `revise_history`）
2. 针对封驳意见修改方案
3. 重新 `plan` 提交

## 6. Thread 消息格式

所有 Thread 消息以 **【中书省】** 开头。

### 规划提出

```
【中书省】 规划方案已提出
【任务分解】1. {步骤A} 2. {步骤B} 3. {步骤C}
【资源评估】负责部门：{agent} / 审核等级：review_required={N} / repo_path：{path}
【验收标准】{标准1} {标准2}
```

### 封驳重提

```
【中书省】 方案已修订（第N次）
【本次修改】针对{给事中}封驳意见：{修改内容}
```

完整格式规范：见 `docs/POLICY-thread-format.md`

## 7. 选择原则

- 根据任务性质选择最匹配的部门
- 明确高风险操作，在方案中加入备份/回滚步骤
- 调研类任务（无代码修改）：`target_files: []`，产出写到 `$CHAOTING_DIR/.design_doc/<ZZ-ID>/`

## 8. 文档管理

| 文档类型 | 存放位置 | Git 操作 |
|---------|---------|---------|
| 设计文档、研究报告 | `$CHAOTING_DIR/.design_doc/<ZZ-ID>/` | 本地保存，不入 repo |
| 规范、政策文档 | `docs/` | feature branch + PR |
