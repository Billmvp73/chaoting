# WORKFLOW-libu.md — 礼部执行工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: libu


> 版本：v1.0 | 适用角色：libu (executor — 文档撰写)

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

## 3. 文档撰写

- 按 plan 中的 steps 撰写/修改文档
- 遵循 Conventional Commits 格式：`docs: <description> (ZZ-XXXXXXXX-NNN)`
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
$CHAOTING_CLI push-for-review ZZ-XXXXXXXX-NNN "PR #N: <链接>" --skip-health-check
$CHAOTING_CLI fail ZZ-XXXXXXXX-NNN "原因"
```

> ⚠️ **禁止直接调用 `chaoting done`**。提交 push-for-review 后，yushi 御史审核通过后任务自动进入 done。
> 文档任务通常无服务健康检查，使用 `--skip-health-check` 跳过。

## 7. Thread 反馈

调用 push-for-review/fail 后 30 分钟内在 Discord Thread 发送反馈。格式见 `docs/POLICY-thread-feedback.md`。

## 8. 文档存放规则

| 文档类型 | 存放位置 | Git 操作 |
|---------|---------|---------|
| 调研报告、设计文档 | `$CHAOTING_DIR/.design_doc/<ZZ-ID>/` | 本地保存，不入 repo |
| 永久性规范文档 | `docs/` | feature branch + PR |

## 9. 规则速查

- 禁止直接 commit 到 master
- 禁止自行 merge PR
- 一奏折一Branch一PR
- 不要擅自修改 plan 范围之外的文件

完整规范：见 `docs/GIT-WORKFLOW.md`
