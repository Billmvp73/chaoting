# WORKFLOW-libu_hr.md — 吏部执行工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: libu


> 版本：v1.0 | 适用角色：libu_hr (executor — 项目管理)

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

## 3. 项目管理实现

- 按 plan 中的 steps 执行
- 可用 `chaoting list` 分析各部门工作负载
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

## 6. 完成/失败

```bash
$CHAOTING_CLI done ZZ-XXXXXXXX-NNN "PR #N: <链接>" "摘要"
$CHAOTING_CLI fail ZZ-XXXXXXXX-NNN "原因"
```

## 7. Thread 反馈

调用 done/fail 后 30 分钟内在 Discord Thread 发送反馈。格式见 `docs/POLICY-thread-feedback.md`。

## 8. 项目管理特有能力

| 能力 | 说明 |
|------|------|
| 里程碑规划 | 基于 zouzhe 分析项目进度 |
| 任务拆解 | 将大任务分解为可执行子任务 |
| 进度跟踪 | 通过 `chaoting list/status` 监控 |
| 团队协调 | 基于 dianji/qianche 辅助资源分配 |

## 9. 规则速查

- 禁止直接 commit 到 master
- 禁止自行 merge PR
- 一奏折一Branch一PR
- 不要擅自修改 plan 范围之外的文件

完整规范：见 `docs/GIT-WORKFLOW.md`
