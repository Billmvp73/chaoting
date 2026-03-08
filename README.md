# 朝廷 (Chaoting) — 多智能体任务协调系统

> 以古代中国朝廷官制为原型的 OpenClaw 多智能体任务编排框架。

---

## 项目简介

**朝廷**是一套运行于 OpenClaw 环境的多智能体任务协调系统。它借鉴古代朝廷的官僚架构，将复杂任务拆解后分派给不同职能的 AI 智能体（"部门"）协作完成。

各智能体通过共享 SQLite 数据库进行协调（Stigmergy 模式），**无需直接通信**，任务流转全部通过数据库状态机驱动。

### 核心特性

- 📜 **奏折驱动** — 每个任务以"奏折（ZZ）"为单位流转
- 🏛️ **职能分离** — 规划、编码、运维、数据、文档各司其职
- ⚙️ **状态机保护** — CAS（Compare-And-Swap）防止并发冲突
- 🔄 **自动重试** — 超时任务自动恢复，支持最大重试次数
- 🗃️ **上下文积累** — 智能体间共享领域知识（典籍/dianji）

---

## 架构说明

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     朝廷系统                              │
│                                                           │
│  ┌──────────┐    ┌──────────┐    ┌─────────────────────┐ │
│  │ 用户/触发 │───▶│ 调度器   │───▶│  中书省 (zhongshu)  │ │
│  └──────────┘    │(dispatcher│    │  规划·拆解任务       │ │
│                  │  .py)    │    └──────────┬──────────┘ │
│                  └──────────┘               │ plan       │
│                       ▲                     ▼            │
│                       │            ┌─────────────────┐   │
│                       │            │  执行部门        │   │
│                       │            │  bingbu / gongbu│   │
│                       └────────────│  hubu / libu 等  │   │
│                      状态轮询       └─────────────────┘   │
│                                                           │
│              共享: chaoting.db (SQLite WAL)               │
└─────────────────────────────────────────────────────────┘
```

### 任务状态机

```
created → planning → executing → done
                ↘               ↘
                 └──────────────→ failed
                                  timeout
```

| 状态 | 说明 | 负责方 |
|------|------|--------|
| `created` | 任务已创建，等待调度 | 用户/API |
| `planning` | 已派发给中书省，规划中 | 中书省 (zhongshu) |
| `executing` | 规划完成，执行中 | 目标部门 |
| `done` | 任务完成 | 执行部门 |
| `failed` | 任务失败 | 执行部门 / 系统 |
| `timeout` | 超时后重试耗尽 | 调度器 |

### 核心组件

| 文件 | 说明 |
|------|------|
| `chaoting.db` | SQLite 数据库（WAL 模式） |
| `dispatcher.py` | 调度守护进程，每 5 秒轮询 |
| `chaoting` | 智能体 CLI 工具（可执行 Python 脚本） |
| `init_db.py` | 数据库 Schema 初始化脚本 |
| `SPEC.md` | 系统详细技术规范 |

### 数据库表

| 表名 | 含义 | 用途 |
|------|------|------|
| `zouzhe` | 奏折 | 任务主表 |
| `liuzhuan` | 流转 | 状态变更日志 |
| `zoubao` | 奏报 | 进度上报记录 |
| `dianji` | 典籍 | 跨任务领域知识积累 |
| `qianche` | 前车 | 智能体经验教训 |

### 可用执行部门

| 部门 ID | 名称 | 职责 |
|---------|------|------|
| `zhongshu` | 中书省 | 任务规划与拆解（固定入口） |
| `bingbu` | 兵部 | 编码开发 |
| `gongbu` | 工部 | 运维部署 |
| `hubu` | 户部 | 数据处理 |
| `libu` | 礼部 | 文档撰写 |
| `xingbu` | 刑部 | 审计安全 |
| `libu_hr` | 吏部 | 项目管理 |

---

## 使用方法

### 安装

```bash
# 初始化数据库
python3 ~/.themachine/chaoting/init_db.py

# 将 CLI 加入 PATH（二选一）
ln -s ~/.themachine/chaoting/chaoting /usr/local/bin/chaoting
# 或者
export PATH="$PATH:$HOME/.themachine/chaoting"

# 启动调度器（systemd 用户服务）
systemctl --user enable --now chaoting-dispatcher

# 验证服务运行
systemctl --user status chaoting-dispatcher
```

### 任务 ID 格式

```
ZZ-YYYYMMDD-NNN
例: ZZ-20260308-001
```

### 智能体 CLI 命令

#### 接取任务

```bash
chaoting pull ZZ-20260308-001
```

返回任务详情、历史典籍（dianji）、前车之鉴（qianche）和流转记录。

#### 中书省提交规划

```bash
chaoting plan ZZ-20260308-001 '{
  "steps": ["步骤1", "步骤2"],
  "target_agent": "bingbu",
  "repo_path": "/absolute/path/to/repo",
  "target_files": ["src/main.py"],
  "acceptance_criteria": "单元测试全部通过"
}'
```

提交后任务进入 `executing` 状态，调度器自动派发给目标部门。

#### 上报进度

```bash
chaoting progress ZZ-20260308-001 "已完成第一阶段，正在处理边界情况"
```

#### 标记完成

```bash
chaoting done ZZ-20260308-001 "PR #42 已合并" "功能上线，含单元测试"
```

#### 上报失败

```bash
chaoting fail ZZ-20260308-001 "依赖版本冲突，无法在 Python 3.11 下编译"
```

#### 更新领域知识

```bash
chaoting context bingbu "repo:myproject:auth.py" \
  "JWT 验证逻辑在 verify_token()，密钥从环境变量读取" \
  --source ZZ-20260308-001
```

### 典型任务流程

```
1. 用户创建任务 (state: created)
         ↓
2. 调度器检测到 created 状态，派发给中书省 (state: planning)
         ↓
3. 中书省接旨: chaoting pull ZZ-XXXXXXXX-NNN
         ↓
4. 中书省分析任务，提交规划: chaoting plan ...
         ↓
5. 调度器检测到 executing + target_agent，派发给目标部门
         ↓
6. 目标部门接旨: chaoting pull ZZ-XXXXXXXX-NNN
         ↓
7. 目标部门执行，定期上报: chaoting progress ...
         ↓
8. 目标部门完成: chaoting done ... / chaoting fail ...
```

### 超时与重试

- 默认超时：600 秒（可在任务中配置 `timeout_sec`）
- 默认最大重试：2 次（可配置 `max_retries`）
- 调度器每 30 秒检测超时，自动重置 `dispatched_at` 触发重试
- 重试耗尽后进入 `timeout` 状态

---

## 任务命名约定

- **状态、CLI 命令** → 英文（created, planning, executing, done, failed）
- **表名、部门名** → 拼音（zouzhe, liuzhuan, zhongshu, bingbu）
- **任务 ID** → `ZZ-YYYYMMDD-NNN`

---

## 详细规范

完整技术规范见 [`SPEC.md`](./SPEC.md)，包含：
- 完整 SQLite Schema
- 调度器并发控制实现
- CAS 保护机制说明
- systemd 服务配置
