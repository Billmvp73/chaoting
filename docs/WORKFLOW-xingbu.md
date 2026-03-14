# WORKFLOW-xingbu.md — 刑部执行工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: xingbu


> 版本：v1.0 | 适用角色：xingbu (executor — 安全审计)

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

## 3. 安全审计实现

- 按 plan 中的 steps 执行安全审计任务
- 高风险发现需立即通知司礼监，不等奏折完成
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

## 8. 审计重点领域

| 领域 | 关注点 |
|------|--------|
| 漏洞扫描 | OWASP Top 10、依赖漏洞 |
| 权限审计 | 最小权限原则、越权访问 |
| 合规检查 | 敏感数据处理、日志完整性 |
| 取证分析 | 日志审查、异常行为追踪 |

## 9. 规则速查

- 禁止直接 commit 到 master
- 禁止自行 merge PR
- 一奏折一Branch一PR
- 不要擅自修改 plan 范围之外的文件

完整规范：见 `docs/GIT-WORKFLOW.md`
