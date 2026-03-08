# CONTRIBUTORS.md — 朝廷系统参与者一览

> 本文件列出朝廷（Chaoting）多智能体任务协调系统的所有参与者及其职责。

---

## 总览

朝廷系统以古代中国官僚架构为原型，各参与者各司其职，通过共享数据库协作完成任务。任务以"奏折（ZZ）"为单位流转，经历 **创建 → 规划 → 审议 → 执行 → 完成** 的完整生命周期。

---

## 司礼监（Sili Jian）

> 总督全局，权柄在握

| 属性 | 说明 |
|------|------|
| **角色 ID** | `silijian` |
| **类型** | 监察总管 |
| **职责** | 创建奏折、接收系统告警（三驳后呈御前、审核超时等），负责人工决断和最终裁量 |
| **触发条件** | 奏折被封驳 3 次、军国大事审核超时、需人工介入的异常事件 |

---

## 调度器（Dispatcher）

> 枢机流转，任务居中调度

| 属性 | 说明 |
|------|------|
| **文件** | `dispatcher.py` |
| **类型** | 系统守护进程 |
| **职责** | 每 5 秒轮询数据库，检测任务状态并自动派发给对应部门；每 30 秒检测超时；系统启动时恢复孤儿任务 |
| **管理的状态转换** | `created → planning`、`revising → planning`、`reviewing → executing/revising`（超时处理） |

---

## 中书省（Zhongshu）

> 运筹帷幄，谋划全局

| 属性 | 说明 |
|------|------|
| **角色 ID** | `zhongshu` |
| **类型** | 规划部门（固定入口） |
| **职责** | 接收所有新奏折，分析任务内容，制定执行方案（steps、target_agent、target_files、acceptance_criteria），完成后提交 plan 推进任务流转 |
| **输入状态** | `planning`、`revising`（被封驳后重新规划） |
| **输出** | 规划 JSON，决定后续执行部门 |

---

## 门下省给事中（Menxia Jishizhong）

> 封驳审议，把关准奏

门下省由多名给事中组成，中书省规划完成后（`review_required=1`），奏折进入 `reviewing` 状态，给事中并行审核，全票准奏方可执行；有封驳则退回中书省修改（最多 2 次，三驳呈司礼监裁决）。

| 角色 ID | 职称 | 审核职责 |
|---------|------|---------|
| `jishi_tech` | 技术给事中 | 审核技术可行性、架构合理性、依赖风险、实现路径 |
| `jishi_risk` | 风险给事中 | 审核回滚方案、数据安全、破坏性操作、副作用 |
| `jishi_resource` | 资源给事中 | 审核工时合理性、token 预算、Agent 可用性 |
| `jishi_compliance` | 合规给事中 | 审核安全合规、权限边界、敏感数据处理 |

> **默认审议阵容：** `jishi_tech` + `jishi_risk`（普通任务）
> **军国大事：** 四名给事中全员参与

---

## 六部（Liu Bu）

> 分工执行，各守其职

六部为朝廷的执行层，由中书省在规划中指定具体执行部门，通过 `chaoting pull` 接旨并完成任务。

| 部门 ID | 中文名 | 职责 |
|---------|--------|------|
| `bingbu` | 兵部 | 编码开发——实现新功能、修复 Bug、编写单元测试、代码重构 |
| `gongbu` | 工部 | 运维部署——环境配置、服务部署、CI/CD 流水线、基础设施变更 |
| `hubu` | 户部 | 数据处理——数据迁移、ETL 流程、数据库变更、数据分析报告 |
| `libu` | 礼部 | 文档撰写——README、API 文档、架构设计文档（ADR）、用户指南、代码注释优化、中英双语文档 |
| `xingbu` | 刑部 | 审计安全——安全漏洞扫描、权限审计、合规检查、日志审查 |
| `libu_hr` | 吏部 | 项目管理——里程碑规划、任务拆解、进度跟踪、人员协调 |

---

## 任务流转全景

```
用户/司礼监
    │ 创建奏折
    ▼
调度器 ──── created ────▶ 中书省 (规划)
                              │ plan 提交
                              ▼
                    review_required?
                    ┌────── 否 ──────┐
                    ▼                ▼
              门下省审议          直接执行
              (reviewing)         (executing)
              ┌──┴──┐
              ▼     ▼
           准奏    封驳 (≤2次)
              │     │ 退回中书省
              │     ▼
              │   重新规划 (revising)
              │
              ▼
           六部执行
           (executing)
              │
          ┌───┴───┐
          ▼       ▼
        done    failed
```

---

## CLI 快速参考

```bash
# 接取任务
chaoting pull ZZ-YYYYMMDD-NNN

# 提交规划（中书省）
chaoting plan ZZ-YYYYMMDD-NNN '<plan_json>'

# 给事中投票（门下省）
chaoting vote ZZ-YYYYMMDD-NNN go "准奏理由" --as jishi_tech
chaoting vote ZZ-YYYYMMDD-NNN nogo "封驳理由" --as jishi_risk

# 上报进度（六部）
chaoting progress ZZ-YYYYMMDD-NNN "进展描述"

# 标记完成
chaoting done ZZ-YYYYMMDD-NNN "产出" "摘要"

# 上报失败
chaoting fail ZZ-YYYYMMDD-NNN "失败原因"
```

---

*本文件由礼部（libu）撰写，依据 README.md、SPEC.md 及 SPEC-menxia.md 整理。*
