# GIT-WORKFLOW.md — 朝廷系统 Git 开发工作流规范

> 版本：v1.0  
> 制定日期：2026-03-09  
> 适用范围：所有执行部门（bingbu / gongbu / 及未来加入的部门）  
> 依据奏折：ZZ-20260309-021

---

## 一、核心原则

| 规则 | 说明 |
|------|------|
| ❌ **禁止直接 commit 到 master** | master 分支只接受通过 PR 合并的内容 |
| ✅ **所有开发在 feature branch 上进行** | 每个奏折对应一个独立分支 |
| ✅ **PR 使用 Squash Merge** | 保持 master 历史清洁，每个奏折一个 commit |
| 🏛️ **Merge 权限仅属司礼监** | 执行部门创建 PR 后等待司礼监 review 和 merge，**禁止自行 merge** |
| ✅ **Merge 后立即同步本地 master** | 防止分歧积累 |

---

## 二、分支命名规范

```
pr/<ZZ-ID>-<简短描述>
```

**示例：**
```
pr/ZZ-20260309-014-revise-mechanism
pr/ZZ-20260309-015-audit-log-thread
pr/ZZ-20260309-020-cmd-new-notify
```

**规则：**
- 前缀固定为 `pr/`
- 包含奏折 ID（便于追踪）
- 描述用连字符分隔，全小写
- 不超过 60 个字符

---

## 三、标准开发流程

### 步骤一：接旨，创建 feature branch

```bash
# 确保本地 master 与 origin 同步
git checkout master
git pull origin master

# 从最新 master 创建 feature branch
git checkout -b pr/ZZ-XXXXXXXX-NNN-feature-name

# 验证
git log --oneline -3  # 确认从正确的 commit 开始
```

### 步骤二：在 feature branch 上开发

```bash
# 正常开发、commit
git add -p   # 或 git add <files>
git commit -m "feat: <描述> (ZZ-XXXXXXXX-NNN)"

# 可以有多个 commit，后续会 squash merge
git commit -m "fix: <修复描述>"
git commit -m "test: <测试描述>"
```

**Commit 消息规范（Conventional Commits）：**
```
<type>: <description> (ZZ-XXXXXXXX-NNN)

类型：
  feat     新功能
  fix      Bug 修复
  docs     文档变更
  refactor 重构（不改功能）
  test     测试
  chore    构建/工具链
```

### 步骤三：推送并创建 PR

```bash
# 推送 feature branch
git push origin pr/ZZ-XXXXXXXX-NNN-feature-name

# 创建 PR（gh CLI）
gh pr create \
  --title "feat: <功能描述> (ZZ-XXXXXXXX-NNN)" \
  --body "奏折: ZZ-XXXXXXXX-NNN

## 变更说明
<做了什么>

## 验收标准
- [ ] <标准1>
- [ ] <标准2>

## 测试验证
<如何验证>"
```

### 步骤四：等待 Review，按意见修改

```bash
# 如有修改意见，在同一 feature branch 上继续 commit
git commit -m "fix: address review comment — <说明>"
git push origin pr/ZZ-XXXXXXXX-NNN-feature-name
```

### 步骤五：等待司礼监 Review 和 Merge

**⚠️ 重要：Merge 权限仅属司礼监（silijian）。执行部门创建 PR 后，禁止自行 merge。**

执行部门在创建 PR 后的职责：
1. 在 PR 对应的 Discord Thread 发送通知，格式见 `docs/POLICY-thread-format.md`
2. 等待司礼监（或指定 reviewer）审阅
3. 如有修改意见，在同一 feature branch 上追加 commit 后 push

司礼监 merge 时：
1. 确认 PR 通过 Review
2. 选择 **"Squash and merge"**（不要用 Merge commit 或 Rebase）
3. Squash commit 消息格式：
   ```
   feat: <功能描述> (ZZ-XXXXXXXX-NNN)
   
   Squash merge of PR #N — N commits covering:
   1. <主要变更1>
   2. <主要变更2>
   
   Related: ZZ-XXXXXXXX-NNN
   ```

### 步骤六：司礼监 Merge 后，执行部门同步本地 master（⚠️ 必须立即执行）

```bash
# 切回 master
git checkout master

# 同步远端（司礼监 merge 后必须立即执行）
git pull origin master

# 验证状态
git log --oneline -3  # 确认 squash commit 出现在顶端
git status            # 确认 "Your branch is up to date"

# 删除已合并的 feature branch（本地 + 远端）
git branch -D pr/ZZ-XXXXXXXX-NNN-feature-name
git push origin --delete pr/ZZ-XXXXXXXX-NNN-feature-name
```

### 步骤七：汇报完成

```bash
chaoting done ZZ-XXXXXXXX-NNN "PR #N 已由司礼监 squash merge 到 master" "摘要"
```

---

## 四、如何处理分歧（Diverged Master）

**症状：**
```
Your branch and 'origin/master' have diverged,
and have N and M different commits each, respectively.
```

**原因：** 本地 master 有未推送的 commits，同时 origin/master 也有新的 squash merge。

**修复步骤：**

```bash
# 1. 创建安全备份
git branch backup/pre-fix-$(date +%Y%m%d)

# 2. 找到分歧点和最后一个已被 squash 的 commit
git log --oneline master...origin/master
# 找到 origin/master 的 squash commit 描述，对应本地哪些 commit

# 3. 识别"真正新"的 commit（未被 squash 的）
# 假设本地最后一个"已被 squash"的 commit 是 <last-squashed-SHA>

# 4. Rebase 新 commits 到 origin/master 上
git rebase --onto origin/master <last-squashed-SHA> master
# 这将把 <last-squashed-SHA> 之后的 commits 移到 origin/master 顶端

# 5. 验证结果
git log --oneline -5
git status  # 应为 "ahead of origin/master by N commit(s)"

# 6. 推送
git push origin master
```

**实际案例（ZZ-20260309-021 修复记录）：**
```bash
# 问题：本地 11 commits，origin 有 squash commit f4cddea（含其中 10 个）
# 解决：
git branch backup/pre-rebase-021
git rebase --onto origin/master e71f842 master
# 结果：本地 master 领先 origin 1 个新 commit，clean
git push origin master  # fast-forward push 成功
```

---

## 五、worktree 模式（可选，长周期任务推荐）

对于涉及多文件、多 commit 的长周期任务，推荐使用 `git worktree` 隔离工作空间：

```bash
# 在独立目录开发，不影响主 checkout
git worktree add ../worktree-ZZ-XXXXXXXX-NNN -b pr/ZZ-XXXXXXXX-NNN-feature-name
cd ../worktree-ZZ-XXXXXXXX-NNN

# 正常开发...

# 完成后清理
cd /home/tetter/self-project/chaoting
git worktree remove ../worktree-ZZ-XXXXXXXX-NNN
```

---

## 六、快速参考卡

```
日常流程（三步）：
  1. git checkout -b pr/ZZ-xxx-描述     # 开分支
  2. <开发 + commit>
  3. git push + gh pr create            # 提 PR

Merge 后（两步，必须做）：
  1. git checkout master && git pull origin master
  2. git branch -d pr/ZZ-xxx-描述       # 删分支

发现分歧时：
  git branch backup/fix-$(date +%Y%m%d)
  git rebase --onto origin/master <last-squashed> master
  git push origin master
```

---

## 七、常见错误与解决

| 错误 | 原因 | 解决方法 |
|------|------|---------|
| `Your branch has diverged` | Merge 后未 pull | `git rebase --onto origin/master <SHA>` |
| `rejected (non-fast-forward)` | 本地落后于 origin | `git pull --rebase origin master` 后再 push |
| `error: cannot delete currently checked out branch` | 在要删除的分支上 | `git checkout master` 后再 `git branch -d` |
| PR 创建后发现 bug | 需要追加 commit | 在同一 feature branch 继续 commit + push，PR 自动更新 |

---

*本文档由吏部（libu_hr）依据奏折 ZZ-20260309-021 制定。*
