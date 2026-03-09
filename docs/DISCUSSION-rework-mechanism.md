# DISCUSSION-rework-mechanism.md — 已完成奏折返工机制可行性研讨

> 文档性质：可行性分析讨论稿（不涉及代码实施）  
> 撰写部门：吏部（libu_hr）  
> 日期：2026-03-09  
> 依据奏折：ZZ-20260309-013  
> 讨论参与方：司礼监 / 兵部 / 中书省 / 运维方（chaoting 维护者）

---

## 一、现状与问题

### 当前状态机（涉及 done 的部分）

```
created → planning → reviewing → executing → done ✅（终态，不可逆）
                                           → failed ❌（终态，不可逆）
```

`done` 一旦触发，依赖 CAS 保护：
```python
UPDATE zouzhe SET state='done'
WHERE id=? AND state='executing'   # CAS：只有 executing 才能转 done
```

**问题：** 司礼监若对结果不满，唯有两条路：
1. 新建奏折（上下文割裂，历史分散）
2. 口头要求修改（无记录，无追踪）

### 已有的可复用基础设施

> **关键发现：** `revising` 状态在门下省封驳流程中已经存在并经过生产验证。

| 现有字段/机制 | 用途 | 返工机制可复用性 |
|------------|------|----------------|
| `zouzhe.revise_count` | 记录封驳次数（门下省封驳） | ✅ 直接复用，记录返工轮次 |
| `zouzhe.plan_history` | 存档历史 plan + 封驳意见 | ✅ 参考结构，存档历史 output + 返工原因 |
| `state = 'revising'` | 门下省封驳后退回中书省重规划 | ✅ 语义可复用，但需区分"执行层返工"与"规划层封驳" |
| `liuzhuan` 流转记录 | 记录每次状态转换 | ✅ 返工操作自然写入，天然有审计链 |

---

## 二、返工场景分析

### 真实使用场景

| 场景 | 描述 | 频率预估 | 适合方案 |
|------|------|---------|---------|
| **小幅修改** | 完成后发现有轻微 bug，需要 hot-fix | 高 | A（直接返工） |
| **功能遗漏** | 验收时发现某个需求没有实现 | 中 | A 或 C |
| **方向偏差** | 实现方向与预期不符，需重新规划 | 低 | C（返回 planning） |
| **质量不达标** | 代码质量、测试覆盖率不符要求 | 中 | B（评审闭环） |
| **重大返工** | 整体推翻重来 | 极低 | 新建奏折更合适 |

### 返工与新建奏折的边界

以下情况**建议新建奏折而非返工**：
- 需求彻底变更（原有 plan 完全不适用）
- 涉及不同执行部门（原任务兵部做，新需求属于工部）
- 返工次数已达上限

---

## 三、三方案详细对比

### 方案 A：轻量级 Rollback（推荐）

**流程：**
```
done → (chaoting revise ZZ-xxx "修改原因") → executing
                                           ↗ 执行部门收到通知，继续迭代
                                           ↘ 完成后重新 chaoting done
```

**状态转移（新增一条）：**
```
done → executing   （发起返工，revise_count +1）
```

**最小数据库改动：**
```sql
-- 新增字段（可选，已有 plan_history 类似结构）
ALTER TABLE zouzhe ADD COLUMN revise_history TEXT;
-- JSON array: [{"round":1,"output":"旧产出","reason":"修改原因","revised_at":"..."}]

-- state 转换（CAS 保护）
UPDATE zouzhe
SET state = 'executing',
    revise_count = revise_count + 1,
    revise_history = ?,       -- 存档旧 output + 原因
    output = NULL,            -- 清空旧 output，防止被误认为已完成
    summary = NULL,
    dispatched_at = NULL,
    updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')
WHERE id = ? AND state = 'done'  -- CAS
RETURNING id
```

**CLI 接口设计：**
```bash
# 基础用法
chaoting revise ZZ-20260309-001 "通知命令参数格式错误，需修复 _send_discord_thread()"

# 指定返回目标状态（可选）
chaoting revise ZZ-20260309-001 "需要重新规划" --to planning
# 默认 --to executing（继续执行原 plan）
# --to planning 时 dispatcher 重新派发给中书省
```

**执行部门收到的通知消息：**
```
📜 奏折 ZZ-XXXXXXXX-NNN 已被退回修改（第 N 次）

原产出：{旧 output}
返工原因：{reason}

请继续执行，完成后重新提交：
  chaoting done ZZ-XXXXXXXX-NNN "新产出" "新摘要"
```

| 维度 | 评估 |
|------|------|
| **实现复杂度** | 🟢 低：1 个新 CLI 命令 + 1 条新状态转换 + 1 个新字段 |
| **状态机一致性** | 🟢 高：复用现有 executing 状态，dispatcher 无需改动 |
| **历史追踪** | 🟡 中：revise_history 记录每轮产出和原因，liuzhuan 有流转记录 |
| **用户体验** | ⭐ 好：一条命令搞定，直觉符合"退回修改"语义 |
| **适用场景** | 小幅 bug 修复、功能遗漏、热修复 |

---

### 方案 B：完整评审闭环

**流程：**
```
done → (司礼监批示) → post_review → (给事中评审) → approved → done（重新确认）
                                                 → rejected → executing（退回修改）
```

**新增状态：**
- `post_review`：执行完成后等待评审（类似 reviewing，但在 done 之后）

**新增数据库表（类似 toupiao）：**
```sql
CREATE TABLE post_review_votes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zouzhe_id   TEXT NOT NULL,
    round       INTEGER DEFAULT 1,
    jishi_id    TEXT NOT NULL,
    vote        TEXT NOT NULL,  -- "approved" / "rejected"
    reason      TEXT,
    timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE (zouzhe_id, round, jishi_id)
);
```

| 维度 | 评估 |
|------|------|
| **实现复杂度** | 🔴 高：新状态 + 新表 + dispatcher 大量改动 + 新 CLI 命令 |
| **状态机一致性** | 🔴 低：`done` 不再是终态，与 CAS 保护的"done 即完成"语义冲突 |
| **历史追踪** | ⭐ 完整：投票记录 + 意见 + 审核人，审计链最完整 |
| **用户体验** | 🔴 差：司礼监需要等给事中审查，流程最长 |
| **适用场景** | 生产级合规场景；当前朝廷系统规模不匹配 |

---

### 方案 C：混合模式（按优先级分流）

**流程：**
- review=0/1（低风险）：走方案 A（直接 `done → executing`）
- review=2/3（高风险）：走方案 B（`done → post_review → ...`）

**判断逻辑：**
```python
def cmd_revise(args):
    zouzhe = fetch(zouzhe_id)
    if zouzhe["review_required"] >= 2:
        # 进入 post_review 状态
        transition_to_post_review(zouzhe_id, reason)
    else:
        # 直接回到 executing
        transition_to_executing(zouzhe_id, reason)
```

| 维度 | 评估 |
|------|------|
| **实现复杂度** | 🔴 高：需实现方案 A + 方案 B 全部逻辑，双倍开销 |
| **状态机一致性** | 🟡 中：同一命令行为不一致（视 review 等级不同），文档和理解成本高 |
| **历史追踪** | ⭐ 完整（高风险）/ 🟡 中（低风险） |
| **用户体验** | 🟡 中：行为不可预期（同一命令结果不同） |
| **适用场景** | 适合未来成熟阶段，现阶段不建议 |

---

## 四、方案综合对比表

| 维度 | 方案 A（轻量 Rollback） | 方案 B（评审闭环） | 方案 C（混合模式） |
|------|----------------------|-----------------|-----------------|
| **实现复杂度** | 🟢 低 | 🔴 高 | 🔴 高 |
| **状态机一致性** | ⭐ 高 | 🔴 低 | 🟡 中 |
| **历史追踪** | 🟡 中 | ⭐ 完整 | ⭐/🟡 视等级 |
| **用户体验** | ⭐ 好 | 🔴 差 | 🟡 中 |
| **与现有体系兼容** | ⭐ 无缝 | 🔴 需大改 | 🔴 需大改 |
| **综合推荐** | ⭐ **推荐** | ❌ 不推荐（现阶段）| 🟡 未来可考虑 |

---

## 五、状态转移图（方案 A）

### 现有状态机

```
created ──→ planning ──→ [reviewing] ──→ executing ──→ done ✅
                ↑                            │
                └────── revising ←───────────┘（门下省封驳）
                             │
                         ↓（超3次）
                          failed ❌
```

### 引入返工机制后

```
created ──→ planning ──→ [reviewing] ──→ executing ──→ done ✅
                ↑                            │              │
                └────── revising ←───────────┘         chaoting revise
                             │                              │
                         ↓（超3次）                         ↓
                          failed ❌              executing（返工中，revise_count +1）
                                                     │
                                                  chaoting done
                                                     │
                                                   done ✅（更新 revise_history）
```

**说明：**
- `done → executing` 是新增的唯一状态转换
- 返工后的 `executing` 与正常 `executing` 完全相同，dispatcher 无需区分
- `revise_count` 在门下省封驳和执行返工中共用计数，或分设 `exec_revise_count` 分别统计（推荐分设，语义更清晰）

---

## 六、权限与上限设计

### 权限：谁可以发起返工

| 角色 | 权限 | 理由 |
|------|------|------|
| **司礼监**（silijian） | ✅ 有权 | 最高权限，对结果负责 |
| **中书省**（zhongshu） | ✅ 有权（建议开放）| 作为规划者，若发现执行结果偏离方案，有权要求修改 |
| **执行部门**（六部） | ❌ 无权自我返工 | 执行部门完成即完成，不应自我推翻；若发现问题应 fail 后由上级决定 |
| **给事中** | ❌ 无权 | 给事中的职责是审核计划，不参与执行结果判断 |

**实现方式：** CLI 命令通过 `OPENCLAW_AGENT_ID` 环境变量校验发起方身份：
```python
initiator = os.environ.get("OPENCLAW_AGENT_ID", "unknown")
if initiator not in ("silijian", "zhongshu"):
    return {"ok": False, "error": "permission denied: only silijian or zhongshu can revise"}
```

### 返工次数上限

| 建议上限 | 理由 |
|---------|------|
| **最多 3 次返工**（exec_revise_count ≤ 3） | 超过 3 次说明需求不清晰或执行能力不足，应新建奏折重新规划 |
| 超限后的处理 | 自动进入 `failed` 状态，错误信息为"超过最大返工次数，请新建奏折"；通知司礼监 |

**上限豁免：** `priority = critical` 的紧急任务不受次数限制（生产故障场景不应被强制卡住）。

---

## 七、CLI 接口完整设计

### `chaoting revise` 命令规格

```bash
# 基础用法（退回执行）
chaoting revise <ZZ-ID> "<修改原因>"

# 退回重新规划（原 plan 已不适用）
chaoting revise <ZZ-ID> "<修改原因>" --to planning

# 指定重新派发给特定执行部门（可选，默认沿用原 assigned_agent）
chaoting revise <ZZ-ID> "<修改原因>" --agent gongbu
```

**命令行为：**
1. 校验 `state = 'done'`（CAS 保护）
2. 校验 `exec_revise_count < MAX_REVISE`（上限检查）
3. 校验发起方权限（`silijian` 或 `zhongshu`）
4. 将当前 `output` + `summary` 归档到 `revise_history`
5. 清空 `output`、`summary`
6. 更新 `state = 'executing'`（或 `planning`），`exec_revise_count +1`，`dispatched_at = NULL`
7. 写入 `liuzhuan`：`from=silijian, to=bingbu, action=revise, remark=<原因>`
8. dispatcher 下一次轮询时检测到 `executing + dispatched_at = NULL` → 重新派发

**返回值：**
```json
{
  "ok": true,
  "zouzhe_id": "ZZ-20260309-001",
  "state": "executing",
  "exec_revise_count": 1,
  "reason": "通知命令参数格式错误，需修复 _send_discord_thread()"
}
```

### `chaoting status` 展示变化

返工后的 `status` 输出中应展示返工历史：
```
奏折: ZZ-20260309-001
状态: executing (返工第 1 次)
返工历史:
  [第1次] 2026-03-09 19:45 由 silijian 退回
  原因: 通知命令参数格式错误，需修复 _send_discord_thread()
  旧产出: PR #12: 通知功能上线...
```

---

## 八、讨论议题

**Q1（必要性）：** 真实使用中返工需求频率如何？

> 吏部观点：从近期案例看，ZZ-003 和 ZZ-009 都是发现 bug 后新建了修复奏折，而不是返工原奏折。当前"新建修复奏折"的模式虽有上下文割裂的问题，但也有好处：每个奏折职责单一，历史清晰。返工机制应作为补充手段，而非强制替代新建奏折。

**Q2（`--to planning` 的价值）：** 什么情况下需要重新规划而非继续执行？

> 吏部观点：若执行部门发现原 plan 方向错误（如选错了技术栈），应支持 `--to planning` 让中书省重新规划。但这种情况极少发生，不应是返工机制的主路径。

**Q3（`exec_revise_count` vs 复用 `revise_count`）：** 是否需要独立计数字段？

> 吏部观点：**建议分设 `exec_revise_count`**，理由：
> - `revise_count` 是门下省封驳计数（规划层），`exec_revise_count` 是执行结果返工计数（执行层）
> - 混用会导致统计指标混淆（一个高 revise_count 无法区分"门下省多次封驳"还是"执行多次返工"）
> - 两者独立上限更清晰

**Q4（通知范围）：** 返工时需要通知哪些部门？

> 吏部观点：最小通知范围——只通知**当前 assigned_agent**（执行部门），不需要通知给事中（执行层变化，与他们的审核职责无关）。司礼监作为发起方无需自我通知。

**Q5（Thread 记录）：** 返工信息如何在 Discord Thread 中体现？

> 吏部观点：在奏折对应的 Thread 里，司礼监发送返工通知时使用标准格式：
> ```
> 【司礼监】🏛️ 退回修改（第 N 次）
> 奏折：{ZZ-ID} / 退回原因：{reason}
> 请执行部门继续迭代并重新提交完成反馈。
> ```

---

## 九、推荐方案与实施路径

### 推荐：方案 A（轻量 Rollback），分两步实施

**第一步（最小可行版，v0.3 范围）：**
- 新增 `zouzhe.exec_revise_count` 字段
- 新增 `zouzhe.revise_history` 字段（JSON，存档历史 output + 原因）
- 新增 `chaoting revise` CLI 命令（`done → executing`，CAS 保护 + 权限校验）
- dispatcher 无需改动（`executing + dispatched_at = NULL` 逻辑已有）
- 更新 `status` 命令展示返工历史

**第二步（可选增强，v0.4）：**
- 支持 `chaoting revise --to planning`（退回重规划，需 dispatcher 处理 `done → planning` 转换）
- 超限自动 failed + 通知司礼监

**预估工作量：**
- 第一步：S（1-2 天），改动集中在 `chaoting` CLI 脚本
- 第二步：S（1 天），主要是 dispatcher 新增一条转换逻辑

---

## 十、结论

| 项目 | 建议 |
|------|------|
| **是否引入返工机制** | ✅ 是，方案 A 轻量可行 |
| **推荐方案** | 方案 A（`done → executing`，一条新 CLI 命令） |
| **权限** | 司礼监 + 中书省可发起，执行部门无权自我返工 |
| **上限** | 最多 3 次（`exec_revise_count ≤ 3`），critical 任务豁免 |
| **计数字段** | 新增独立 `exec_revise_count`，不复用门下省的 `revise_count` |
| **不建议** | 方案 B（成本过高）、方案 C（现阶段不成熟） |
| **优先于新建奏折的场景** | 小幅修改、热修复、功能遗漏（原 plan 仍有效） |
| **应新建奏折的场景** | 需求彻底变更、涉及不同部门、已达返工上限 |

---

*本分析报告仅讨论可行性与设计方案，不涉及任何代码实施。如各部门有异议，欢迎在 Thread 中补充意见。*  
*由吏部（libu_hr）依据奏折 ZZ-20260309-013 撰写。*
