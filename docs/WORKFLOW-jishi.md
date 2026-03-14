# WORKFLOW-jishi.md — 给事中审核工作流详细指南

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: jishi


> 版本：v1.0 | 适用角色：jishi_tech, jishi_risk, jishi_resource, jishi_compliance (reviewer)

---

## 1. 接取审核令

```bash
$CHAOTING_CLI pull ZZ-XXXXXXXX-NNN
```

输出包含 plan JSON（中书省方案）、dianji（领域知识）、qianche（经验教训）、liuzhuan（流转历史）。

## 2. 审核方案

阅读 plan 内容，根据自身角色进行审核评估。

### 各角色审核侧重

#### jishi_tech（技术给事中）
- 技术方案是否可行
- 架构设计是否合理
- 依赖关系是否明确、版本是否兼容
- 实现路径是否清晰、步骤是否完整
- 是否有更优的技术方案

#### jishi_risk（风险给事中）
- 是否有回滚方案
- 数据安全：是否可能导致数据丢失或损坏
- 破坏性操作：rm、DROP、DELETE 等是否有保护措施
- 副作用：对其他系统或服务的影响
- 是否需要先备份再操作

#### jishi_resource（资源给事中）
- 工时预估是否合理
- Token 预算是否可控
- 目标 Agent 是否具备所需能力
- 是否存在资源浪费（过度设计、不必要的步骤）
- 并行任务是否存在资源竞争风险

#### jishi_compliance（合规给事中）
- 安全合规：是否涉及敏感数据、是否符合安全策略
- 权限边界：操作是否在授权范围内
- 敏感数据处理：密钥、token、密码是否妥善保护
- 外部通信：是否有未授权的外部请求
- 数据隐私：是否有 PII 泄露风险

## 3. 投票

### 准奏

```bash
$CHAOTING_CLI vote ZZ-XXXXXXXX-NNN go "准奏理由" --as <role_id>
```

### 封驳

```bash
$CHAOTING_CLI vote ZZ-XXXXXXXX-NNN nogo "封驳理由，需明确指出修改点" --as <role_id>
```

## 4. Thread 消息格式

### 消息标头

| 角色 | 标头 |
|------|------|
| jishi_tech | 【技术给事中】 |
| jishi_risk | 【风险给事中】 |
| jishi_resource | 【资源给事中】 |
| jishi_compliance | 【合规给事中】 |

### 审查完成格式

```
【{角色标头}】审查完成
【审查意见】{通过项} / {注意项} / {问题项}
【建议】- {改进建议1} - {改进建议2}
【投票结果】GO / NOGO / GO with caveats — {一句话理由}
```

完整格式规范：见 `docs/POLICY-thread-format.md`

## 5. 典籍查询权限

| 表 | 权限 | 说明 |
|----|------|------|
| `zouzhe` | 全部 | 查看奏折描述和历史 |
| `liuzhuan` | 全部 | 查看历史审核链 |
| `zoubao` | 全部 | 了解执行进展 |
| `toupiao` | 仅自己 | 查看自己历史投票记录 |
| `dianji` | 全部 | 查阅领域知识辅助审核 |
| `qianche` | 全部 | 参考历史教训 |

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
