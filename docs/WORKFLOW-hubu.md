# WORKFLOW-hubu.md — 户部执行工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: hubu


> 版本：v1.0 | 适用角色：hubu (executor — 数据/DB)

---

## 1. 接旨

```bash
$CHAOTING_CLI pull ZZ-XXXXXXXX-NNN
```

## 2. 创建隔离工作空间（必须）

**必须使用 git worktree 隔离工作空间**：

```bash
cd <repo_path>
git checkout master && git pull origin master
git worktree add ../worktree-ZZ-XXXXXXXX-NNN -b pr/ZZ-XXXXXXXX-NNN-feature-name
cd ../worktree-ZZ-XXXXXXXX-NNN
```

## 3. 数据/DB 实现

- 按 plan 中的 steps 执行
- **数据操作前必须备份** — DROP/DELETE 等破坏性操作需门下省 review=3 审核
- 遵循 Conventional Commits 格式
- 汇报进展：`$CHAOTING_CLI progress ZZ-XXXXXXXX-NNN "进展描述"`

## 4. 创建 Issue + PR + Self-Review

详细步骤见 `docs/WORKFLOW-bingbu.md` 第 4-5 节（流程相同）。

## 5. 等待 Merge + 同步

- 禁止自行 merge
- Merge 后同步 master 并清理 worktree：
  ```bash
  cd <repo_path>
  git checkout master && git pull origin master
  git branch -D pr/ZZ-XXXXXXXX-NNN-feature-name
  git worktree remove ../worktree-ZZ-XXXXXXXX-NNN
  ```

## 6. 提交 yushi 审核

```bash
$CHAOTING_CLI push-for-review ZZ-XXXXXXXX-NNN "PR #N: <链接>"
$CHAOTING_CLI fail ZZ-XXXXXXXX-NNN "原因"
```

> ⚠️ **禁止直接调用 `chaoting done`**。提交 push-for-review 后，yushi 御史审核通过后任务自动进入 done。

## 7. Thread 反馈

调用 push-for-review/fail 后 30 分钟内在 Discord Thread 发送反馈。格式见 `docs/POLICY-thread-feedback.md`。

## 8. 数据操作安全规范

| 操作 | 要求 |
|------|------|
| SELECT / 只读查询 | 无需特别审批 |
| INSERT / UPDATE | 需备份目标表 |
| DELETE / DROP | 需 review=3 审核 + 备份 |
| Schema 变更 | 需备份 + 回滚脚本 |

## 9. 规则速查

- 禁止直接 commit 到 master
- 禁止自行 merge PR
- 一奏折一Branch一PR
- 不要擅自修改 plan 范围之外的文件

完整规范：见 `docs/GIT-WORKFLOW.md`
