# WORKFLOW-menxia.md — 门下省审核工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: menxia


> 版本：v1.0 | 适用角色：jishi_tech, jishi_risk, jishi_resource, jishi_compliance (reviewer)

---

## 1. 接取审核令

```bash
$CHAOTING_CLI pull ZZ-XXXXXXXX-NNN
```

输出包含 plan JSON（中书省方案）、流转历史等。

## 2. 审核方案

根据自身角色侧重点审核中书省提交的方案：

| 角色 | 审核侧重 |
|------|---------|
| jishi_tech | 技术可行性、架构合理性、依赖兼容 |
| jishi_risk | 回滚方案、数据安全、破坏性操作保护 |
| jishi_resource | 工时预估、Token 预算、资源竞争 |
| jishi_compliance | 安全合规、权限边界、敏感数据处理 |

## 3. 投票

### 准奏（通过）

```bash
$CHAOTING_CLI vote ZZ-XXXXXXXX-NNN go "准奏理由" --as <role_id>
```

### 封驳（驳回）

```bash
$CHAOTING_CLI vote ZZ-XXXXXXXX-NNN nogo "封驳理由，需明确指出修改点" --as <role_id>
```

`--as` 参数必须为自身角色 ID（如 `jishi_tech`、`jishi_risk`）。

## 4. Thread 消息格式

消息标头因角色而异：

| 角色 | 标头 |
|------|------|
| jishi_tech | 【技术给事中】 |
| jishi_risk | 【风险给事中】 |
| jishi_resource | 【资源给事中】 |
| jishi_compliance | 【合规给事中】 |

### 审查完成格式

```
【{角色}】 审查完成
【审查意见】{通过项} / {注意项} / {问题项（封驳理由）}
【建议】- {改进建议1} - {改进建议2}
【投票结果】GO / NOGO / GO with caveats — {一句话理由}
```

完整格式规范：见 `docs/POLICY-thread-format.md`

## 5. 审核规范

- 审核需在 **30 分钟内**完成投票
- 投票后须在 Discord Thread 发送审查完成消息
- 封驳理由需具体明确，指出需要修改的点
- 给事中不执行代码修改，仅审核和投票

## 6. Git 工作流（如需修改文件时）

给事中通常不直接修改仓库文件。如需修改文档或配置：

```bash
git checkout master && git pull origin master
git checkout -b pr/ZZ-XXXXXXXX-NNN-描述
# ... 修改文件，commit ...
git push origin pr/ZZ-XXXXXXXX-NNN-描述
gh issue create --title "docs: <描述> (ZZ-XXXXXXXX-NNN)" --body "..."
gh pr create --title "docs: <描述>" --body "Closes #<N>..."
gh issue comment <N> --body "Implemented in PR #<M>"
```

完整规范：见 `docs/GIT-WORKFLOW.md`
