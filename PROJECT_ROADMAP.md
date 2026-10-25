# E-commerce After-sales Agent — Project Roadmap

## 项目目标

基于官方 [τ²-bench Retail](https://github.com/sierra-research/tau2-bench) v2.0.0，自主开发一个可靠、可评测、可观测的电商售后 AI Agent，用于 AI Agent 研发和服务端开发岗位求职。官方代码位于 `../tau2-bench/`；本仓库是独立开发项目，不是官方 Fork，两个 Git 仓库保持独立。

**开发原则：** 自己实现 Agent 核心；复用官方 Retail business environment、Tools、Harness 与 Evaluator。先复现 → 再理解 → 再实现 → 再评测 → 最后整理成果；不从零重写整个 τ²-bench，也不把“简单继承官方 `LLMAgent`”作为默认方案。

## 当前状态

- **当前阶段：** 阶段 2 已完成；阶段 3A 的 V0 已完成一次真实 Retail Smoke Test 和固定 Tasks `0–4` 的首次 Pilot；阶段 3B 的 V1-1 Availability-aware Factual Grounding 已完成首次真实 Pilot。
- **当前进度：** 已完成官方 Retail Smoke Test、官方 5-task Pilot Baseline、官方源码梳理、个人 V0 的 Task `0` Smoke Test / 5-task Pilot，以及 V1 availability grounding 的去重/过期事实修复、单元测试和首次真实 5-task Pilot。详见 [实验记录](docs/EXPERIMENT_LOG.md)；V1 本次为 `3/5`、V0 为 `2/5`，但均是单 trial 小样本，不能证明稳定提升。
- **下一步：** 先以 **seed/protocol compatibility-fixed** 的 V0/V1 在固定配置下扩大或重复对照，并完整保留 Agent/User/Judge usage 与成本边界；修复前后 artifact 必须分开记录。在确认 Tasks `0`、`1` 的写入路径回归是否可复现前，不优先开始 step-budget-aware planning。

## Milestone 总览

| Milestone | 阶段 | 状态 | 完成标志 |
| --- | --- | --- | --- |
| M1 | 官方 Baseline 复现 | 进行中 | 已完成 5-task Pilot；仍需完成更大、可比较的批量评测与结果记录 |
| M2 | Agent 架构与源码理解 | 已完成 | 已输出官方 Agent、Tool、Harness 与 Evaluation 调用关系笔记 |
| M3 | 自主 Agent 开发 | 进行中 | 已验证最小接入契约、V0 Task 0 Smoke Test / 首次 5-task Pilot；V1 availability grounding 已完成 Mock 与首次真实 5-task Pilot |
| M4 | Evaluation 与可靠性测试 | 未开始 | 建立对比、Golden Set 与回归测试 |
| M5 | RAG 扩展（可选） | 未开始 | 完成有对照的检索增强实验 |
| M6 | Observability | 未开始 | 可查询的端到端 Trace 与成本指标 |
| M7 | 项目交付 | 未开始 | 文档、演示、报告与求职材料就绪 |

## 1. 官方 Baseline 复现（必做）

**目标：** 在不修改官方源码的前提下，稳定复现官方 Retail 环境和基线评测。

### Checklist

- [x] 安装官方 τ²-bench v2.0.0。
- [x] 运行 Retail Smoke Test（任务 ID `0`；Reward `1.0`；`5/5` 动作检查通过；`24.52` 秒）。
- [x] 初步查看该任务的 Agent 对话与工具调用轨迹。
- [x] 确认 Pilot 批量评测命令、模型配置、任务范围和结果输出位置。
- [x] 运行 5 任务 Pilot Baseline 评测（任务 `0–4`；非完整基准）。
- [x] 记录 Pilot 的配置、结果、耗时、失败任务、成本边界与可复现命令。
- [ ] 对比 Task 0 的单任务成功与批量失败轨迹，确认差异来源。
- [ ] 检查 Tasks 2–4 的 T-shirt 可用变体计数与订单恢复路径。
- [ ] 设计并执行更大固定任务集的 Baseline；单独记录任何 step-limit 变更。
- [ ] 完整记录 Agent 与 judge 的 Token/费用，再进行成本比较。

**验收标准：** 能以记录的命令和配置重复运行批量 Retail 评测；结果包含任务范围、Reward/成功率、耗时及失败案例索引。

**当前状态：** Pilot 已完成；正式、可比较的更大批量 Baseline 待完成。其剩余调查可与阶段 3 的接口研究并行，但任何对比实验须使用单独记录的固定配置。

## 2. Agent 架构与源码理解（必做）

**目标：** 建立从 Agent 执行到 Retail 工具与任务评分的完整心智模型。

### Checklist

- [x] 梳理 Agent 的入口、执行循环和消息状态流转。
- [x] 梳理 Tool Calling 的定义、参数校验和结果返回路径。
- [x] 梳理 Retail 环境可用工具及关键业务约束。
- [x] 梳理 Harness 的任务加载、运行、异常处理和结果收集流程。
- [x] 梳理任务目标、动作检查和 Reward 计算机制。
- [x] 输出关键模块与调用关系笔记：[架构笔记](docs/ARCHITECTURE_NOTES.md)。

**验收标准：** 可说明一个 Retail 任务从加载、Agent 工具调用到动作检查和 Reward 产出的路径，并能定位对应官方代码模块。

**当前状态：** 已完成。结论限于官方 v2.0.0 的已检查路径；自定义实现方案仍留待阶段 3 验证。

## 3. 自主 Agent 开发（必做）

**目标：** 自主实现 Agent 核心逻辑，同时保持对官方 Retail Environment、Tools、Harness、Evaluator 和消息协议的兼容；不在 Agent 内重复实现 Tool 执行或角色调度。

### 3A. 最小 Agent（V0）

**范围：** 先追求正确接入和完整运行，不要求立即超过官方 Baseline。官方最小示例 `../tau2-bench/examples/agents/minimal_text_agent.py` 可作为接口参考，不直接复制完整官方 `LLMAgent`。

#### Checklist

- [x] 核实并记录 `HalfDuplexAgent` 接口、Agent State、消息类型、factory 与 registry 的最小契约。
- [x] 验证独立仓库通过 Python entry point 进行 process-local registry 注册，并由官方 `build_agent()` 构建自定义 Agent；外部 CLI 的自动加载方式仍未验证。
- [x] 自主实现 V0 的 Prompt 构造、消息状态管理、官方 `generate()` 调用、Tool Call / Tool Result 接收和下一步决策；已完成 Mock 测试、真实 Task `0` Smoke Test 和首次 5-task Pilot 验证。
- [x] 保持官方 `AssistantMessage`、Tool schema 与 history 协议兼容；复用官方 LLM 调用封装，避免重复开发基础设施。
- [x] 明确 Agent 与 Harness 的边界：Agent 产生消息/决策，官方 Harness 负责角色调度，官方 Environment / Tools 负责实际执行。
- [x] 编写不依赖付费 API 的接口与单元测试。
- [x] 以 Retail Task `0` 完成 V0 Smoke Test，并单独记录配置和结果（Reward `1.0`；非性能结论）。
- [x] 使用与官方 Pilot 可比的固定 Tasks `0–4` 完成首次 V0 5-task Pilot（`2/5`、平均 Reward `0.40`；单 trial，非性能结论）。

**验收标准：** V0 可被官方文本 Harness 构建和运行；至少有接口/单元测试证明消息与 Tool schema 兼容，并有一条独立记录的 Retail Smoke Test。该 Smoke Test 不作为性能结论。

### 3B. Agent 可靠性增强（V1）

**前置条件：** V0 已可运行。仅基于真实失败案例选择 2–3 项机制，不预设所有功能都必须实现，也不强制引入 LangGraph。

#### Checklist

- [x] 实现并以 Mock 回归测试 **availability-aware factual grounding**：从结构化 Tool Result 的 `available` 字段得出 inventory 事实；按 `product_id` 替换过期事实、不写死某个 task 的答案。
- [x] 在可比的首次真实 Retail 5-task Pilot 验证 V1-1：Tasks `2–4` 的 availability NL assertions 通过；同时发现 Tasks `0`、`1` 的 exchange write / DB 回归，尚未证明其因果来源或稳定性。
- [x] 修复 V0/V1 的 Harness seed 传递和 Retail text message/requestor compatibility，并以 Mock 回归验证；该修复可能改变后续 LLM 行为，修复后实验须使用新 artifact。
- [ ] 在扩大/重复 V0–V1 对照后，再决定是否实现并测试 **step-budget-aware planning and completion**。
- [ ] Tool Error 结构化恢复、重复失败 Tool Call 检测/合理终止、写操作前 confirmation / permission 检查与关键写操作后状态验证，待出现 V0 对应失败证据后再排序选择。
- [ ] 为每项选定机制编写测试，并保留触发它的失败案例或最小复现。
- [ ] 扩大或重复可比的 V0 / V1 对照，记录收益、Tasks `0`/`1` 回归是否复现、Agent/User/Judge 代价和局限性。
- [ ] 仅在复杂状态编排被证明确有收益时评估 LangGraph。

**验收标准：** V1 的每项增强有可运行测试；对照实验不将单次随机结果表述为稳定提升。

**当前状态：** 3A 的固定响应 Agent、V0 Mock 接口测试、真实 Task `0` Smoke Test 与首次可比的 5-task Pilot 均已完成；3B 的 availability grounding 已完成去重/过期事实修复、Mock 回归和首次真实 V1 Pilot（`3/5`）。该首次结果同时出现 Tasks `0`、`1` 的 write/DB 回归，故更大/重复对比、完整成本记录以及对回归因果的确认仍待完成。

## 4. Evaluation 与可靠性测试（必做）

**目标：** 用可重复的实验验证自定义 Agent 的能力、可靠性与代价。

### Checklist

- [ ] 在固定任务、模型、参数和评测规则下，对比官方 Agent、个人 V0 与 V1。
- [ ] 建立覆盖高风险售后场景的 Golden Set。
- [ ] 为规则、确认、异常与重试逻辑编写 pytest 回归测试。
- [ ] 统计 Success Rate、Pass^k、Tool error、规则违规、延迟、Token 与 API 成本。
- [ ] 区分开发调试任务与独立评估任务，避免针对测试答案优化。
- [ ] 保留失败模式、修复后的回归案例和实验局限性。

**验收标准：** 有一份可复跑的对比结果，包含 Baseline 与自定义 Agent 的相同指标、Golden Set 结果、回归测试结果及成本/延迟分析。

**当前状态：** 未开始。

## 5. RAG 扩展（可选）

**目标：** 基于可合法使用的官方 Retail policy document，验证政策检索是否能提升政策一致性与任务表现。

### Checklist

- [ ] 准备可追溯的官方售后政策知识库；不引入真实客户数据。
- [ ] 按实际需要评估 LangChain、FAISS 或更轻量的实现。
- [ ] 实现检索、引用返回与引用有效性验证。
- [ ] 与无 RAG 版本进行对照实验。

**验收标准：** 完成相同评测设置下的 RAG/非 RAG 对照，并记录检索质量、引用有效性及对任务指标的影响。

**当前状态：** 未开始。

## 6. Observability（必做）

**目标：** 让每次 Agent 执行可追踪、可诊断、可度量成本。

### Checklist

- [ ] 设计 Trace 与 Span 的最小字段规范。
- [ ] 记录 Agent Trace、模型调用、Tool Call、关键状态与错误日志。
- [ ] 记录 Token 用量、延迟和 API 成本。
- [ ] 评估并选择 Langfuse 或 Phoenix 等观测方案。
- [ ] 接入并验证单任务与批量任务的链路查询能力。

**验收标准：** 能根据一次任务运行定位模型调用和工具调用链路，并查询其耗时、Token 与成本。

**当前状态：** 未开始。

## 7. 项目交付（必做）

**目标：** 将研发过程整理为可审阅、可演示、可用于求职的项目成果；定位为可运行、可评测的电商售后 Agent 工程原型，不宣称已接入真实电商生产系统。

### Checklist

- [ ] 完善 README：问题、架构、运行方式、评测结果与限制。
- [ ] 绘制系统架构图和关键执行流程图。
- [ ] 准备可复现的演示场景与演示说明。
- [ ] 整理实验报告与关键结论。
- [ ] 检查 GitHub 仓库的代码、配置与文档可复现性。
- [ ] 撰写基于已验证事实的简历项目描述。

**验收标准：** 新读者可按 README 完成安装、运行演示和复现核心评测；仓库包含架构说明、实验结论与真实的简历描述素材。

**当前状态：** 未开始。

## 实验记录索引

| 记录 | 内容 | 状态 |
| --- | --- | --- |
| [实验记录](docs/EXPERIMENT_LOG.md) | 2026-10-22 官方 Retail 5-task Pilot Baseline；2026-10-23 V0 Retail 5-task Pilot：配置、对比、失败分析与成本边界 | 已更新 |
| [架构笔记](docs/ARCHITECTURE_NOTES.md) | 阶段 2：官方 v2.0.0 的 Agent、Retail Tool、Harness 与 Evaluation 技术参考 | 已创建 |

> 新实验应在该索引对应记录中注明日期、代码版本/配置、任务范围、指标和结论；尚未创建该文件前，此链接仅作为后续约定。
