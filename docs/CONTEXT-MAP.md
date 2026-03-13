# CONTEXT-MAP.md — 朝廷系统全局知识地图

> 版本：v1.0 | 更新日期：2026-03-13

---

## 系统架构

| 层级 | 组件 | 说明 |
|------|------|------|
| 中央 | 司礼监 (silijian) | 最高监督，merge 权限，紧急干预 |
| 中央 | 中书省 (zhongshu) | 规划者，分析需求、制定方案 |
| 审核 | 门下省 (menxia) | 给事中集体审核，投票准奏/封驳 |
| 执行 | 六部 | 各领域执行部门 |

## Agent 一览

| Agent ID | 角色 | 职责 | SOUL 模板 | 工作流文档 |
|----------|------|------|-----------|-----------|
| `silijian` | supervisor | 系统监督、merge、紧急干预 | `examples/souls/silijian.md` | (特殊角色) |
| `zhongshu` | planner | 需求分析、方案规划 | `examples/souls/zhongshu.md` | `docs/WORKFLOW-zhongshu.md` |
| `jishi_tech` | reviewer | 技术可行性审核 | `examples/souls/jishi_tech.md` | `docs/WORKFLOW-jishi.md` |
| `jishi_risk` | reviewer | 风险评估审核 | `examples/souls/jishi_risk.md` | `docs/WORKFLOW-jishi.md` |
| `jishi_resource` | reviewer | 资源合理性审核 | `examples/souls/jishi_resource.md` | `docs/WORKFLOW-jishi.md` |
| `jishi_compliance` | reviewer | 安全合规审核 | `examples/souls/jishi_compliance.md` | `docs/WORKFLOW-jishi.md` |
| `bingbu` | executor | 编码开发、Bug 修复 | `examples/souls/bingbu.md` | `docs/WORKFLOW-bingbu.md` |
| `gongbu` | executor | 运维部署、CI/CD | `examples/souls/gongbu.md` | `docs/WORKFLOW-gongbu.md` |
| `hubu` | executor | 数据处理、DB 变更 | `examples/souls/hubu.md` | `docs/WORKFLOW-hubu.md` |
| `libu` | executor | 文档撰写 | `examples/souls/libu.md` | `docs/WORKFLOW-libu.md` |
| `libu_hr` | executor | 项目管理 | `examples/souls/libu_hr.md` | `docs/WORKFLOW-libu_hr.md` |
| `xingbu` | executor | 安全审计 | `examples/souls/xingbu.md` | `docs/WORKFLOW-xingbu.md` |

## 关键文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 系统规范 | `docs/SPEC.md` | chaoting 核心 spec |
| 门下省规范 | `docs/SPEC-menxia.md` | 审核流程详细规范 |
| Git 工作流 | `docs/GIT-WORKFLOW.md` | 分支、PR、worktree 规范 |
| Timeout 选择指南 | `docs/TIMEOUT-GUIDE.md` | Task timeout size reference (XS/S/M/L/XL), decision checklist, worktree requirements for L/XL |
| Thread 格式 | `docs/POLICY-thread-format.md` | Discord 消息格式 |
| Thread 反馈 | `docs/POLICY-thread-feedback.md` | 完成/失败反馈格式 |
| Agent Teams | `docs/AGENT-TEAMS-GUIDE.md` | 多 agent 协作指南 |
| CHANGELOG | `docs/CHANGELOG.md` | 版本更新记录 |
| ROADMAP | `docs/ROADMAP.md` | 项目路线图 |

## 数据存储

| 位置 | 用途 |
|------|------|
| `$CHAOTING_DATA_DIR/chaoting.db` | SQLite 主数据库 |
| `$CHAOTING_DATA_DIR/docs/plans/` | 规划 Markdown 文件 |
| `$CHAOTING_DATA_DIR/.design_doc/` | 设计文档（不入 git） |
| `$CHAOTING_DATA_DIR/logs/` | Agent 审计日志 |

## 数据库表

| 表名 | 用途 |
|------|------|
| `zouzhe` | 奏折（任务）主表 |
| `liuzhuan` | 流转记录（状态变更） |
| `zoubao` | 奏报（进度报告） |
| `toupiao` | 投票记录 |
| `dianji` | 典籍（领域知识） |
| `qianche` | 牵扯（经验教训） |
| `tongzhi` | 通知管理 |
