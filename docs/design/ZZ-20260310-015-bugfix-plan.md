# ZZ-20260310-015 Bug Fix Plan — 返工流转闭环问题

> 制定日期：2026-03-10 | 依据奏折：ZZ-20260310-015

## 一、问题复现（已在 ZZ-013 记录）

**症状**：皇上 revise 后中书省仍提交含旧 target_agent 的规划。  
**根因**（双重断路，已在 ZZ-014 修复）：
1. `dispatcher.py format_revising_message()` 不读 `revise_history`
2. `chaoting pull` 不返回 `revise_history`

**日志痕迹确认**：revise_history 字段正确写入 DB，但从未流向中书省。

## 二、变更项（本 PR 新增 planning_version 锁定）

### 2.1 新字段
```sql
ALTER TABLE zouzhe ADD COLUMN planning_version INTEGER DEFAULT 1;
```
每次 `chaoting revise` 时 `planning_version = planning_version + 1`。

### 2.2 DB 变更安全规程
1. `systemctl --user stop chaoting-dispatcher`
2. `cp chaoting.db chaoting.db.bak-$(date +%s)`
3. `python3 -c "import sqlite3; db=sqlite3.connect('chaoting.db'); db.execute('ALTER TABLE zouzhe ADD COLUMN planning_version INTEGER DEFAULT 1'); db.commit()"`
4. `systemctl --user start chaoting-dispatcher`
5. 验证：`PRAGMA table_info(zouzhe)` 确认 planning_version 存在

**回滚**：`cp chaoting.db.bak-XXXX chaoting.db && restart`

### 2.3 planning_version 锁定逻辑

```python
# cmd_plan 中校验（向后兼容：无 version 字段则跳过）
plan_version_in_plan = plan.get("planning_version")
db_version = zouzhe["planning_version"] or 1
if plan_version_in_plan is not None and int(plan_version_in_plan) != db_version:
    → 拒绝，返回错误 "planning_version 不匹配"
```

**中书省提交 plan 时应附带版本号**（从 `chaoting pull` 获取）：
```json
{
  "target_agent": "bingbu",
  "steps": ["..."],
  "planning_version": 2
}
```

## 三、版本对照表

| 事件 | planning_version | 说明 |
|------|-----------------|------|
| 奏折创建 | 1 | 初始版本 |
| 皇上 revise（第1次）| 2 | plan 必须携带 version=2 |
| 皇上 revise（第2次）| 3 | plan 必须携带 version=3 |
| jishi 封驳/重规划 | 不变 | 封驳不改变 version |

## 四、验收标准 ✅

✅ revise_reason 在发给中书省的消息中可见（路径 B 修复）  
✅ planning_version 锁定机制：旧版规划被拒绝，正确版本被接受  
✅ DB 变更含完整安全规程  
✅ 3+ 轮 revise 回归测试（4 轮，每轮 planning_version 递增）  
✅ 2 workspace 并行隔离测试  
✅ 审计日志：revise_history 完整 + last_revise_reason 实时更新
