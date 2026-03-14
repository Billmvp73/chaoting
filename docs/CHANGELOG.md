# CHANGELOG

> Last verified: 2026-03-13 | Status: ✅ valid | Owner: libu


本文件记录朝廷（Chaoting）多智能体任务协调系统的版本历史。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [v0.2] — 门下省 (Menxia)

### 新增

#### 门下省审议机制
- 新增 **Go/No-Go 投票流程**：中书省规划完成后（`review_required=1`），奏折进入 `reviewing` 状态，由门下省给事中并行审核，全票准奏方可进入执行
- 新增 **四类给事中角色**：
  - `jishi_tech`（技术给事中）：审核技术可行性、架构合理性、依赖风险
  - `jishi_risk`（风险给事中）：审核回滚方案、数据安全、破坏性操作
  - `jishi_resource`（资源给事中）：审核工时合理性、token 预算、Agent 可用性
  - `jishi_compliance`（合规给事中）：审核安全合规、权限边界、敏感数据处理
- 默认审议阵容：`jishi_tech` + `jishi_risk`（普通任务）；军国大事四位全员参与
- 新增 **封驳-修订循环**：有给事中封驳则退回中书省重新规划，最多 2 次；三驳呈司礼监人工裁决

#### 新增状态
- `reviewing`：门下省审议中，等待给事中全员投票
- `revising`：被封驳，退回中书省修改（携带封驳意见及历史规划）

#### 新增 CLI 命令
- `chaoting vote <id> go|nogo "<理由>" --as <jishi_id>`：给事中投票，`--as` 参数必填，防止身份混淆

#### 数据库变更（`zouzhe` 表新增字段）
- `review_required INTEGER DEFAULT 0`：是否需要门下省审议
- `review_agents TEXT`：参与审议的给事中列表（JSON array）
- `revise_count INTEGER DEFAULT 0`：已被封驳次数
- `plan_history TEXT`：历次封驳的规划存档（JSON array，含封驳意见）

#### 新增数据库表
- **`toupiao`**（投票记录）：记录每轮每位给事中的投票（`go`/`nogo`）及理由
  - `UNIQUE(zouzhe_id, round, jishi_id)` + `INSERT OR IGNORE` 防止并发重复投票

#### 调度器增强
- 检测 `reviewing` 状态 → 并行派发各给事中（CAS 防重复派发）
- 轮询 `check_votes`：全票通过则转 `executing`；有封驳则转 `revising`
- 超时处理分级：
  - 普通任务：未投票的给事中默认准奏，通知司礼监
  - 军国大事（`priority=critical`）：超时直接转 `failed`，通知司礼监人工介入
- `revising` 状态自动重新派发中书省（带完整封驳意见）

### 变更
- 状态机扩展：`created → planning → reviewing → executing → done/failed/timeout`
- `chaoting plan` 命令：根据 `review_required` 决定后续状态为 `reviewing` 或直接 `executing`
- 调度器 `STATE_TRANSITIONS` 新增 `revising → planning`（zhongshu）

### 修复
- 给事中身份映射：`toupiao` 表同时存 `jishi_id`（角色）和 `agent_id`（实际 agent），`check_votes` 按角色匹配
- `revise_count` 直接在 SQL `UPDATE SET revise_count = revise_count + 1`，避免读-写竞态
- `revising` 时清空 `plan=NULL`，防止旧规划被幽灵执行
- 封驳后重新规划的消息包含原始规划及封驳意见，供中书省参考

---

## [v0.1] — MVP

### 新增

#### 核心架构
- **stigmergy 模式**：各智能体通过共享 SQLite 数据库协作，无需直接通信
- **奏折（ZZ）驱动**：任务以 `ZZ-YYYYMMDD-NNN` 格式编号，贯穿完整生命周期

#### 状态机
- 基础状态：`created → planning → executing → done / failed / timeout`
- CAS（Compare-And-Swap）乐观锁：`UPDATE WHERE state=<expected>` 防止并发冲突
- 自动重试：超时任务按 `max_retries`（默认 2 次）自动恢复

#### SQLite Schema（`chaoting.db`，WAL 模式）
- **`zouzhe`**（奏折）：任务主表，含状态、规划、产出、重试计数等字段
- **`liuzhuan`**（流转）：完整状态变更日志
- **`zoubao`**（奏报）：智能体进度上报记录
- **`dianji`**（典籍）：跨任务领域知识积累，按 `(agent_role, context_key)` 主键
- **`qianche`**（前车）：智能体经验教训存档

#### 调度器（`dispatcher.py`）
- 守护进程，每 5 秒轮询：`created → planning`（派发中书省）；`executing` + `dispatched_at=NULL` → 派发目标部门
- 每 30 秒检测超时，自动重置超时任务
- 启动时 `recover_orphans()`：恢复系统重启前的孤儿任务
- 幂等派发：`UPDATE WHERE dispatched_at IS NULL RETURNING id` 防止重复派发

#### CLI 工具（`chaoting`）
- `pull <id>`：接取任务，返回详情、典籍、前车之鉴及流转记录
- `plan <id> <json>`：中书省提交规划（含 `steps`、`target_agent`、`target_files`、`acceptance_criteria`）
- `progress <id> <text>`：上报执行进度
- `done <id> <output> <summary>`：标记任务完成
- `fail <id> <reason>`：上报任务失败
- `context <role> <key> <value>`：更新领域知识（典籍）

#### 执行部门
- `zhongshu`（中书省）：任务规划，固定入口
- `bingbu`（兵部）：编码开发
- `gongbu`（工部）：运维部署
- `hubu`（户部）：数据处理
- `libu`（礼部）：文档撰写
- `xingbu`（刑部）：审计安全
- `libu_hr`（吏部）：项目管理

#### 系统集成
- `chaoting-dispatcher.service`：systemd 用户服务，支持开机自启
- `init_db.py`：数据库 Schema 初始化脚本

---

*本文件由礼部（libu）撰写，依据 SPEC.md、SPEC-menxia.md 及 CHANGELOG-010.md 整理。*
