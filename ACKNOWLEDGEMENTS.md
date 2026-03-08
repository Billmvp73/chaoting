# 致谢 / Acknowledgements

## 灵感来源

朝廷（Chaoting）的设计深受以下两个项目启发。感谢它们开创性的探索：

### 🍍 菠萝王朝 (boluobobo-ai-court-tutorial)

- **作者：** [wanikua](https://github.com/wanikua)
- **仓库：** [wanikua/boluobobo-ai-court-tutorial](https://github.com/wanikua/boluobobo-ai-court-tutorial)
- **贡献：** 率先将中国古代朝廷官制（三省六部制）引入 OpenClaw 多智能体框架，以直观的教程形式展示了"每个部门 = 一个独立 Agent"的扁平化架构思路。

### 📜 三省六部 (edict)

- **作者：** [cft0808](https://github.com/cft0808)
- **仓库：** [cft0808/edict](https://github.com/cft0808/edict)
- **贡献：** 实现了完整的三省六部 pipeline（太子→中书省→门下省→尚书省→六部），尤其是门下省的封驳/审核机制为我们的 Go/No-Go 投票设计提供了核心参考。edict 的三层通信模式（subagent spawn → JSON shared state → CLI dispatch）分析也直接影响了我们选择 CLI dispatch + SQLite 作为协调模型。

## 架构灵感

除上述项目外，朝廷的设计还借鉴了以下概念：

- **NASA Mission Control** — CAPCOM 单一入口、Go/No-Go 投票共识机制
- **Stigmergy（蚁群协作）** — 共享环境信号而非直接通信的协调模式
- **CAS（Compare-And-Swap）** — 数据库层面的乐观并发控制

## 工具

- **[OpenClaw](https://github.com/openclaw/openclaw)** — 本项目运行于 OpenClaw 多智能体框架之上
