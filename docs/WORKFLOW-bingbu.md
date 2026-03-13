# WORKFLOW-bingbu.md — 兵部执行工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: bingbu


> 版本：v1.0 | 适用角色：bingbu (executor — 编码开发)

---

## 1. 接旨

```bash
$CHAOTING_CLI pull ZZ-XXXXXXXX-NNN
```

输出包含：zouzhe 详情、plan、dianji、qianche、liuzhuan、plan_file、worktree_path。

## 2. 创建隔离工作空间（必须）

**必须使用 git worktree 隔离工作空间**，防止与其他任务冲突：

```bash
cd <repo_path>
git checkout master && git pull origin master
git worktree add ../worktree-ZZ-XXXXXXXX-NNN -b pr/ZZ-XXXXXXXX-NNN-feature-name
cd ../worktree-ZZ-XXXXXXXX-NNN
```

## 3. 编码实现

- 按 plan 中的 steps 逐步实现
- 在 feature branch 上 commit（Conventional Commits 格式）：
  ```
  <type>: <description> (ZZ-XXXXXXXX-NNN)
  类型：feat / fix / docs / refactor / test / chore
  ```
- 定期汇报进展：`$CHAOTING_CLI progress ZZ-XXXXXXXX-NNN "进展描述"`

## 4. 创建 Issue + PR（三步双联）

```bash
git push origin pr/ZZ-XXXXXXXX-NNN-feature-name

# Step A：创建 Issue
gh issue create \
  --title "feat: <描述> (ZZ-XXXXXXXX-NNN)" \
  --body "奏折: ZZ-XXXXXXXX-NNN

## 任务背景
{奏折 plan 描述}

## 验收标准
{acceptance_criteria}

## 改动范围
{影响的文件/模块}"

# Step B：创建 PR（Closes #N 关联 Issue）
gh pr create \
  --title "feat: <描述> (ZZ-XXXXXXXX-NNN)" \
  --body "Closes #<issue-number>

奏折: ZZ-XXXXXXXX-NNN

## 变更说明
<做了什么>

## 测试验证
<验证方式>"

# Step C：Issue 中 mention PR
gh issue comment <issue-number> --body "Implemented in PR #<pr-number>"
```

## 5. Self-Review

在 PR 上添加 self-review comment：

```bash
gh pr comment <pr-number> --body "## Self-Review

**Related Issue**: #<issue-number>

### What problem does this solve?
<问题描述>

### Why this approach?
<方案理由>

### What changed?
<改动列表>

### Edge cases / risks
<风险点>"
```

## 6. 等待 Merge + 同步

- 禁止自行 merge — merge 权限仅属司礼监
- 如有修改意见，在同一分支追加 commit 后 `git push`
- 司礼监 Merge 后立即同步：
  ```bash
  cd <repo_path>
  git checkout master && git pull origin master
  git branch -D pr/ZZ-XXXXXXXX-NNN-feature-name
  git worktree remove ../worktree-ZZ-XXXXXXXX-NNN
  ```

## 7. 完成/失败

```bash
$CHAOTING_CLI done ZZ-XXXXXXXX-NNN "PR #N: <链接>" "摘要"
$CHAOTING_CLI fail ZZ-XXXXXXXX-NNN "原因"
```

## 8. Thread 反馈（30 分钟内必须发送）

### 完成

```
【兵部】 {ZZ-ID} 已完成
**做了什么（What）**：[改动概述 + commit SHA + PR 链接]
**验证情况（Validation）**：[测试方式 + 是否满足验收标准]
**后续（Next）**：[下一步 / 遗留问题]
```

### 失败

```
【兵部】 {ZZ-ID} 执行失败
**失败原因**：[具体原因]
**已尝试**：[尝试方案及结果]
**建议**：[处置建议]
```

完整格式规范：见 `docs/POLICY-thread-feedback.md`

## 9. 规则速查

- 禁止直接 commit 到 master
- 禁止自行 merge PR
- 一奏折一Branch一PR
- PR 必须使用 Squash Merge
- 不要擅自修改 plan 范围之外的文件

完整规范：见 `docs/GIT-WORKFLOW.md`
