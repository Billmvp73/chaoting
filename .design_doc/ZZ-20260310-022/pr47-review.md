# PR #47 全朝审核报告 — ZZ-20260310-022

> 审核对象：https://github.com/Billmvp73/chaoting/pull/47
> 审核日期：2026-03-10 | 执行：bingbu（代全朝四维度）

---

## 一、中书省审核（架构完整性）

### ✅ 设计对齐度：高

| ZZ-021 设计规格 | PR #47 实现 | 对齐状态 |
|----------------|------------|---------|
| P0: `chaoting lesson` 命令 | `cmd_lesson` + COMMANDS 注册 | ✅ |
| P0: `--dianji/--lesson` 参数到 `cmd_done` | `_parse_done_extras` + `cmd_done` 扩展 | ✅ |
| P1: dispatch 携带 dianji limit=5，value 截断 200 | `_build_dianji_qianche_section` | ✅ |
| P1: qianche limit=3 | 同上 | ✅ |
| P1: stale 老化机制 | `mark_stale_dianji` | ✅ |

### ⚠️ 架构问题 1：qianche dispatch 查询语义模糊

```python
# dispatcher.py _build_dianji_qianche_section
qianche_rows = db.execute(
    "SELECT lesson FROM qianche "
    "WHERE agent_role = ? OR zouzhe_id = ? "   # ← zouzhe_id 是当前正在派发的任务
    "ORDER BY id DESC LIMIT 3",
    (agent_id, zouzhe_id),  # zouzhe_id = 新任务，历史教训不可能来自这里
).fetchall()
```

**问题**：`zouzhe_id` 参数是当前正在派发的新任务 ID，这个任务刚开始执行，不可能有教训记录。`OR zouzhe_id = ?` 这个条件永远不会命中，查询等同于 `WHERE agent_role = ?`。

**建议**：直接改为 `WHERE agent_role = ? ORDER BY id DESC LIMIT 3`，语义更清晰。

### ✅ 架构问题 2：向后兼容性

- `cmd_done(args)` 中 `args[3:]` 传给 `_parse_done_extras`，老调用 `cmd_done ZZ-XXX '产出' '摘要'` 时 `args[3:]` 为 `[]`，`_parse_done_extras([])` 返回 `([], [])` → 完全向后兼容 ✅
- 已有历史奏折 DB 不受影响：qianche/dianji 表本就存在，无 schema 变更 ✅

### ✅ 与 ZZ-021 设计文档的差异评估

ZZ-021 建议 `stale_days` 可配置（env var），PR #47 中硬编码 `stale_days=30`。属于 P2 优化，当前实现可接受。

---

## 二、门下省审核（安全性 + 成本）

### 🔴 安全问题（高优先级）：异常被完全吞掉

```python
# src/chaoting cmd_done — dianji/qianche 写入部分
for entry in dianji_entries:
    try:
        db.execute(...)
    except Exception:
        pass  # ← 问题：异常被完全吞掉，用户不知道典籍写入失败
for lesson in lesson_entries:
    try:
        db.execute(...)
    except Exception:
        pass  # ← 同上
```

**风险**：用户调用 `chaoting done --dianji key=val` 以为典籍写入了，但实际写入失败（如 DB 锁），没有任何反馈。数据静默丢失。

**建议**：改为 `except Exception as e: print(f"[WARN] dianji write failed: {e}", file=sys.stderr)`

### ⚠️ 安全问题（中等）：dispatch 消息长度无上限保证

最坏情况：5 条 dianji × 200 字 + 3 条 qianche × 200 字 = 最多 ~1600 字额外内容，加上原始消息约 500 字，总计 ~2100 字。

OpenClaw `themachine agent -m` 的消息大小限制未知。Discord 通知有 2000 字截断（`_cli_notify` 中 `body[:2000]`），但 dispatch 消息本身走 `--agent` 路径不走 notify，无截断。

**建议**：在 `_build_dianji_qianche_section` 末尾确保整个 section 不超过 1000 字：
```python
result = "\n\n" + "\n\n".join(parts)
return result[:1000] if len(result) > 1000 else result
```

### ✅ 安全问题：已有历史奏折不受影响

- 无 schema 变更，无 migration
- dianji/qianche 写入只在有 `--dianji/--lesson` 参数时触发
- 现有 `chaoting done` 调用无任何影响 ✅

### ✅ 成本评估

| 项目 | 正常情况 | 最坏情况 |
|------|---------|---------|
| 无 dianji/qianche 数据时 | +0 字 | 同左 |
| 有 5 条 dianji | +~200-1000 字 | ~1000 字 |
| 有 3 条 qianche | +~100-600 字 | ~600 字 |
| 总 dispatch 消息增量 | 0-1600 字 | ~1600 字 |
| `mark_stale_dianji` 额外 DB 写 | 1 UPDATE/小时 | 同左，O(n) |

成本可接受，无爆炸性增长风险。

---

## 三、兵部审核（代码质量）

### 🔴 代码问题 1：`_parse_done_extras` 静默丢弃无效 dianji

```python
if "=" in kv:
    k, _, v = kv.partition("=")
    dianji_entries.append(...)
# else: 静默忽略，不警告
```

**场景**：用户打错命令 `chaoting done ZZ-XXX '产出' '摘要' --dianji workspace_isolation_tip`（忘了 `=`），典籍记录被静默丢弃，用户以为记录成功。

**建议**：
```python
if "=" in kv:
    ...
else:
    print(f"[WARN] --dianji '{kv}' 缺少 '='，格式应为 key=value，已跳过", file=sys.stderr)
```

### ✅ 代码问题 2：`db` 生命周期正确

`cmd_done` 中 `db` 的生命周期：`get_db()` → `execute UPDATE` → `commit()` → dianji/qianche writes → `commit()` → `db.close()`。完整正确，无过早关闭问题。

### ⚠️ 代码问题 3：`import time` 未使用（测试文件）

```python
# src/test_dianji_p0p1.py line 14
import time  # ← 从未使用
```

小问题，建议删除。

### ✅ 代码问题 4：`_parse_done_extras` 对 `key=val=extra` 处理正确

`"key=val=extra".partition("=")` → `("key", "=", "val=extra")`，`v = "val=extra"` ✅ 测试已覆盖。

### ⚠️ 代码问题 5：`cmd_lesson` 的 `filtered_args` index 假设

```python
is_global = filtered_args[0] == "--global"
zid = None if is_global else filtered_args[0]
lesson = filtered_args[1] if len(filtered_args) > 1 else None

if not lesson:
    out({"ok": False, "error": "lesson text is required"}, ok=False)
```

**场景**：`chaoting lesson --role bingbu '教训'`（用户忘了 zouzhe_id 或 --global）：
- `filtered_args = ['教训']`（`--role bingbu` 被 role_override 消耗）
- `is_global = ('教训' == '--global')` → False
- `zid = '教训'`（错误地把教训文本当成 zouzhe_id）
- `lesson = None`（因为 `len(filtered_args) == 1`）
- `not lesson` → 报错 "lesson text is required"

用户会看到令人迷惑的 "lesson text is required" 错误而不是 "invalid usage"。
**建议**：增加对 `zid` 格式的基本校验（如 `ZZ-` 前缀），或在 `is_global=False` 时检查 `filtered_args` 是否有足够元素。

### ✅ 测试质量总评

| 测试项 | 覆盖情况 |
|--------|---------|
| cmd_lesson 基本功能 | ✅ 3个测试 |
| cmd_lesson 错误处理 | ✅ 1个 |
| cmd_done --dianji | ✅ 2个 |
| cmd_done --lesson | ✅ 1个 |
| cmd_done 混合 + 兼容性 | ✅ 2个 |
| _parse_done_extras 单元测试 | ✅ 含边界 |
| _build_dianji_qianche_section | ✅ limit/truncation/empty |
| mark_stale_dianji 逻辑 | ✅ |
| 未覆盖：dianji 写入异常静默丢弃 | ❌ |
| 未覆盖：dispatch 消息长度边界 | ❌ |

---

## 四、吏部审核（文档）

### ❌ 文档问题 1：无 CHANGELOG 条目

`feat: dianji/qianche P0+P1 集成` 属于功能性变更，应在 CHANGELOG.md（若存在）中记录。

### ❌ 文档问题 2：无 README 更新

`chaoting lesson` 是新增 CLI 命令，应在 README.md 命令列表中补充。

### ✅ 文档问题 3：cmd_lesson docstring 质量良好

完整列出了三种使用方式，清晰易懂。

### ✅ 文档问题 4：error message 已更新

`cmd_done` 的 error message 已更新为含 `--dianji/--lesson` 提示，正确。

---

## 五、综合结论与建议

### 必须修复（Blocker）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| B1 | `except Exception: pass` 静默丢弃典籍写入错误 | 数据静默丢失，用户无感知 | 改为 `except Exception as e: sys.stderr.write(...)` |
| B2 | `_parse_done_extras` 无效 dianji 静默丢弃 | 用户误以为写入成功 | 增加 stderr warning |

### 建议修复（Non-Blocker）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| N1 | qianche dispatch 查询含无用 `OR zouzhe_id = ?` | 语义混乱 | 改为纯 `agent_role = ?` |
| N2 | dispatch 消息无总长度保护 | 极端情况可能过长 | section 截断至 1000 字 |
| N3 | `cmd_lesson` filtered_args 假设脆弱 | 误导性错误提示 | 增加参数校验 |
| N4 | `import time` 未使用（测试文件） | 代码整洁度 | 删除 |
| N5 | `stale_days=30` 硬编码 | 不可配置 | 支持 `CHAOTING_DIANJI_STALE_DAYS` env |

### 文档补充（可在后续任务处理）

| # | 问题 |
|---|------|
| D1 | README 缺 `chaoting lesson` 命令说明 |
| D2 | 无 CHANGELOG 条目 |

---

## 六、审核结论

**整体质量**：**良好**，核心功能完整、测试覆盖到位（18/18）、设计对齐度高。

**合并建议**：修复 B1（静默丢失）和 B2（无效参数丢失）后可 merge。N1-N5 可在后续 PR 处理。

**阻塞 merge 的最小改动**（约 10 行）：
1. `cmd_done` 中两处 `except Exception: pass` → `except Exception as e: print(f"[WARN] ...: {e}", file=sys.stderr)`
2. `_parse_done_extras` 中 `else:` 分支增加 stderr warning
