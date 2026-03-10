# revise-unlimited 设计与实施方案

> 制定日期：2026-03-10  
> 依据奏折：ZZ-20260310-014  
> 实施分支：pr/ZZ-20260310-014-revise-unlimited

## 一、功能概述

取消皇上下旨 revise 的固定次数上限（原 3/5 次），改为可配置的 `revise_limit` 字段：
- `revise_limit=0`：无限制（默认，皇上下旨无上限）
- `revise_limit=N`：最多 N 次（可选约束）

同时新增审计增强、重复原因检测、防爆轮机制。

## 二、DB 变更

```sql
-- 5个新字段，均有安全默认值
ALTER TABLE zouzhe ADD COLUMN revise_limit INTEGER DEFAULT 0;
ALTER TABLE zouzhe ADD COLUMN revise_timeout_days INTEGER DEFAULT 0;
ALTER TABLE zouzhe ADD COLUMN last_revise_reason TEXT;
ALTER TABLE zouzhe ADD COLUMN suspended_at TEXT;
ALTER TABLE zouzhe ADD COLUMN total_revise_rounds INTEGER DEFAULT 0;
```

**DB 变更安全规程**：
1. `systemctl --user stop chaoting-dispatcher`
2. `cp chaoting.db chaoting.db.bak-$(date +%s)`
3. 执行 ALTER TABLE（幂等，重复运行不报错）
4. `systemctl --user start chaoting-dispatcher`
5. 验证：`PRAGMA table_info(zouzhe)` 确认字段存在

**回滚**：`cp chaoting.db.bak-XXXX chaoting.db && restart`

## 三、CLI 变更

```bash
# 无限制返工（默认行为，revise_limit=0）
OPENCLAW_AGENT_ID=silijian chaoting revise ZZ-XXX '原因'

# 设置最多 3 次
OPENCLAW_AGENT_ID=silijian chaoting revise ZZ-XXX '原因' --limit 3

# 取消限制
OPENCLAW_AGENT_ID=silijian chaoting revise ZZ-XXX '原因' --limit none

# 设置 30 天防爆轮
OPENCLAW_AGENT_ID=silijian chaoting revise ZZ-XXX '原因' --timeout-days 30

# 解除暂停（防爆轮触发后）
OPENCLAW_AGENT_ID=silijian chaoting resume ZZ-XXX '解除原因'
```

**权限**：仅 `silijian` 或 `zhongshu`（OPENCLAW_AGENT_ID）

## 四、新功能详解

### 4.1 重复原因检测

`_detect_duplicate_reason()` 使用 `difflib.SequenceMatcher`（阈值 0.85）检查当前原因与最近 2 轮的相似度。
- 相似度 ≥ 0.85：返回 warning，**不阻断**
- `revise_history` 中记录 `dup_similarity` 字段供审计
- 中书省收到的通知包含「建议提供实质性改进」提示

### 4.2 防爆轮机制

`_check_revise_timeout()` 检查奏折年龄：
- 若 `revise_timeout_days > 0` 且 `created_at` 超期 → 触发 `suspended` 状态
- `suspended` 奏折不可再 revise，直到 `chaoting resume` 解除
- `suspended` 和 `done` 之间只有 `silijian` 可以 resume

### 4.3 审计字段

每次 revise 自动更新：
- `last_revise_reason`：最后一次返工原因（500字符截断）
- `total_revise_rounds`：累计总返工次数
- `revise_history[]` 每轮记录 `dup_similarity`、`output`（≤500字符）

## 五、Dispatcher 修复（ZZ-20260310-013 RC-1/RC-2 同步修复）

本任务同时修复了 ZZ-013 报告的两个关键 Bug：

**RC-1**：`dispatcher.py` `format_revising_message()` 现在优先读 `revise_history`（皇上旨意），不再仅依赖 `plan_history`（jishi封驳）。

**RC-2**：`chaoting pull` 返回值现包含 `revise_history`、`exec_revise_count`、`revise_limit`、`last_revise_reason`、`suspended_at`。

## 六、测试覆盖

21 个测试全部通过（0.377s）：
- revise_limit=0 无限制测试（超过原3次上限）
- revise_limit=N 阻断超额
- --limit flag 更新 revise_limit
- output 截断 ≤ 500 字符
- revise_timeout_days 触发 suspended
- 未超时不触发 suspended
- 重复原因 warning（≥0.85相似度）
- dispatcher 路径 A（jishi封驳）保持不变
- dispatcher 路径 B（revise_history）包含旨意
- cmd_pull 返回 revise_history
