# 实验记录

## 2026-10-22 — Retail 5-task Pilot Baseline

### 范围与复现信息

- **状态：** 已完成；这是一次 **5-task Pilot Baseline**，不是完整 Retail benchmark 分数。
- **官方 harness：** τ²-bench `v2.0.0`，commit `989d3285ae669e49503324bdb9981bf14fccedeb`。
- **Domain / language：** `retail` / `en`；默认 task set，`base` split。
- **任务：** `0, 1, 2, 3, 4`；每个任务运行一个 trial。
- **Agent：** `llm_agent`，`openai/gpt-4.1-mini`，`{"temperature": 0.0}`。
- **User simulator：** `user_simulator`，`openai/gpt-4.1-mini`，`{"temperature": 0.0}`。
- **Seed：** `42`。
- **限制：** `max_steps=30`、`max_errors=10`、`max_concurrency=1`、`max_retries=0`。
- **结果 artifact：** `../tau2-bench/data/simulations/retail-baseline-0-4/results.json`。

本次 Pilot 使用的命令：

```bash
uv run tau2 run \
  --domain retail \
  --agent llm_agent \
  --agent-llm openai/gpt-4.1-mini \
  --agent-llm-args '{"temperature":0.0}' \
  --user user_simulator \
  --user-llm openai/gpt-4.1-mini \
  --user-llm-args '{"temperature":0.0}' \
  --task-ids 0 1 2 3 4 \
  --num-trials 1 \
  --max-steps 30 \
  --max-concurrency 1 \
  --max-retries 0 \
  --seed 42 \
  --verbose-logs \
  --llm-log-mode all \
  --save-to retail-baseline-0-4
```

### 结果概览

**通过数：1/5；平均 Reward：0.20。** 这只是一次探索性 Pilot 结果；不得将其表述为完整 Retail baseline 或 leaderboard 分数。

| Task | Reward | 耗时 | Termination | 已确认的评测结果 |
| --- | ---: | ---: | --- | --- |
| 0 | 0.0 | 25.22 s | `user_stop` | DB check 失败；4/5 action checks 通过；所需 exchange write 未匹配。 |
| 1 | 1.0 | 17.80 s | `user_stop` | DB check 通过；全部 5 个 action checks 通过。 |
| 2 | 0.0 | 27.28 s | `user_stop` | DB check 失败；3/11 action checks 通过；所需 return write 未匹配；NL assertion 失败。 |
| 3 | 0.0 | 24.34 s | `max_steps` | 在评测前结束；结果记录为在 30-step 上限处提前终止。 |
| 4 | 0.0 | 24.27 s | `user_stop` | DB check 通过；12/13 action checks 通过；NL assertion 失败。 |

### 基于已保存 trajectory 的失败分析

以下仅记录简要的行为事实。不会将完整 transcript、tool results、客户标识、地址、订单 ID 或 LLM debug logs 复制到本仓库。

#### Task 0 — exchange variant 不匹配

**已确认事实**

- Authentication 以及全部四个所需 read checks 都通过。
- RGB variant 不可用后，用户选择了带 **white backlight** 的 clicky keyboard variant。
- Trajectory 显示 Agent 对该 white-backlight variant 执行了 exchange；所需 exchange action 期望的是另一个 keyboard item。
- 因此，write action 和最终 DB state 失败（`DB=0.0`）。

**推测 / 仍需调查**

- 该现象与 task 的 fallback rule 和 Agent 对用户后续选择的理解存在差异相一致。仅凭已保存结果，不能确定根因是 task expectation、policy interpretation，还是 Agent decision policy。
- Task 0 曾在单任务 Smoke Test 中通过（Reward `1.0`，5/5 actions）。同一任务在本批量运行中失败。这是已观察到的差异，不代表已确认原因；在归因于 model nondeterminism 或其他因素前，应对比两次保存的 trajectory 与 resolved runtime settings。

#### Task 2 — availability 表述错误且 return 路径未成功

**已确认事实**

- Agent 表述有 12 个可用 T-shirt options。已保存的 NL judge verdict 指出 product data 中有 10 个可用 variants，因此 assertion 失败。
- Agent 完成用户 authentication 后，尝试查询用户提供的 order IDs；environment 返回未找到，最终将用户转交给 human agent。
- 最终 DB check 失败，仅 3/11 expected action checks 通过，expected return write 未匹配。

**推测 / 仍需调查**

- 此失败与 Agent 跟随未经验证的 order IDs、而没有通过可用 account/order tools 恢复相关 orders 相一致。该恢复路径是否为预期路径，仍需结合 task/policy 复核。
- 需调查 availability count 为什么是 12 而不是 10，包括 unavailable variants 的计数方式。

#### Task 3 — step budget 耗尽

**已确认事实**

- 运行在配置的 30-step 上限处以 `max_steps` 终止；由于 evaluator 将其记录为 premature termination，Reward 为 0。
- 停止前，Agent 已完成用户 authentication、检查 product 和 order data、修改一个 pending T-shirt order，并随后表述有 12 个可用 T-shirt variants。

**推测 / 仍需调查**

- 对这个 trajectory 而言，30-step Pilot cap 不足。目前未知提高上限后是否能正确完成任务，因为这将是不同的 experimental configuration。
- 在选择后续 step budget 前，应复核不必要的 reads/turns，以及 task 的 multiple-order requirement 的处理方式。

#### Task 4 — state change 正确，但事实回答不完整

**已确认事实**

- Agent 修改了两个 pending T-shirt orders；DB evaluation 通过，12/13 expected action checks 通过。
- 它将可用 T-shirt options 数量描述为“several”，而没有给出所需值 10。
- 已保存的 NL judge verdict 明确将此 assertion 标记为失败；因此即使 `DB=1.0`，总 Reward 仍为 0。

**推测 / 仍需调查**

- Agent 能完成 state-changing workflow，但不能可靠完成 precision-sensitive informational subtask。在完成 source 和 evaluation review 后，确认是否需要 Agent-side availability-counting rule。

### Cost 与 judge evidence

- 已记录 `user_cost` 的总和约为 **$0.01199**：`$0.0020248 + $0.0022984 + $0.0034200 + $0.0021260 + $0.0021208`。
- 所有 `agent_cost` 字段均为 `null`。这表示 accounting 不完整，**不等于 Agent cost 为零**；因此 aggregate report 的 average conversation cost 不可用。
- 运行配置包含 semantic communication judge（`gpt-5.5`，low reasoning），但五个已保存的 `communicate_checks` 均为 `null`/empty。没有已保存证据表明该 judge 在本次 Pilot 中给出过 verdict。
- Tasks 2 和 4 有直接保存的 NL assertion judge activity 证据：二者均包含 NL verdict 和 explanatory justification。Tasks 0 和 1 没有 NL assertions；Task 3 提前结束，因此也没有。结果 artifact 未提供独立的 judge token/cost total，因此不能仅据此文件确定总 API cost。

### 后续 checklist

- [ ] 对比成功的 Task 0 Smoke Test trajectory 与本次失败的 Task 0 trajectory，包括 task data 和 resolved configuration。
- [ ] 检查 Tasks 2–4 的 T-shirt availability-count semantics 与 expected order-recovery workflow。
- [ ] 为提高 Task 3 step limit 的实验单独制定并记录配置。
- [ ] 在进行 cost comparison 前，建立完整的 Agent 和 judge Token/cost capture。
- [ ] 定义更大的固定 task set 并重复 baseline trials，再报告更广泛的 Retail performance number。

## 2026-10-23 — V0 Retail Task 0 End-to-end Smoke Test

### 范围与配置

- **目的：** 验证个人仓库的 `ecommerce_after_sales_v0` 能通过官方 Harness 完成一次真实 Retail 任务；这是一条 Smoke Test，不是性能比较或批量基准。
- **官方源码：** 当前 `../tau2-bench/` 为 `v2.0.0`，commit `989d3285ae669e49503324bdb9981bf14fccedeb`。
- **Agent / User：** `ecommerce_after_sales_v0` / `user_simulator`；双方均为 `openai/gpt-4.1-mini`，`{"temperature": 0.0}`。
- **任务与限制：** Retail Task `0`、`base` split、`seed=42`、`num_trials=1`、`max_steps=30`、`max_errors=10`、`max_retries=0`、`max_concurrency=1`、`workers=0`、`auto_review=false`。
- **原始结果：** `../tau2-bench/data/simulations/retail-v0-smoke-task0/results.json`。

artifact 的 `info.agent_info.implementation` 为 `ecommerce_after_sales_v0`，确认实际使用的是个人 V0 Agent。该 artifact 的 `info.git_commit` 是 `e5df92d…`；官方 `get_commit_hash()` 读取运行时当前目录的 Git commit，因此它记录的是个人项目 provenance，不应当作官方 τ²-bench commit。官方版本以上述单独核验的 `989d3285` 为准。

### 结果与真实执行链路

| 指标 | 已确认结果 |
| --- | --- |
| Reward | `1.0` |
| DB Check | `1.0`（`db_match=true`） |
| Action Checks | `5/5` 全部通过 |
| Duration | `28.26 s` |
| Termination | `user_stop` |
| trajectory | 20 条 message；全部 Tool Result 的 `error=false` |

保存的 trajectory 证实实际链路为：V0 Agent 先发起 authentication、order/product 查询等 Tool Call；官方 Environment 返回 Tool Result；V0 Agent 继续基于结果决策；最后发起 `exchange_delivered_order_items`，Environment 成功返回写入结果，Agent 再向 User 完成回复。该结论只描述组件交互和成功结果，不复制客户标识、订单号、地址或完整对话。

### 与官方 `llm_agent` Task 0 Smoke Test 的简要对比

此前官方 Smoke artifact 为 `../tau2-bench/data/simulations/retail-smoke-001/results.json`，Agent 为 `llm_agent`，同为 Task `0`、`gpt-4.1-mini`、`temperature=0.0`、`seed=42`、`max_steps=30`。

| 项目 | 官方 `llm_agent` Smoke | 个人 V0 Smoke |
| --- | ---: | ---: |
| Reward / DB Check / Action Checks | `1.0` / `1.0` / `5/5` | `1.0` / `1.0` / `5/5` |
| Duration | `24.52 s` | `28.26 s` |
| Tool Call | 4 个 required read + 1 个 exchange write | 相同 5 个 required calls，另有 1 个 `get_user_details` read |

两者都完成该单次任务；V0 多一次 read 且本次耗时更长约 `3.74 s`。单个 task、单个 trial 不能用于推断 V0 的性能优势、稳定性或成本优势。

### Cost 与未覆盖范围

- 保存的 `user_cost` 为 `$0.0020748`（约 `$0.0021`），只是 User Simulator 的已记录费用，**不是总费用**。
- `agent_cost` 为 `null`，不表示 V0 Agent 费用为零；artifact 没有独立完整的 Agent / Judge Token 与费用总计。
- 此任务没有 NL assertions，`communicate_checks` 为空；保存结果没有独立 Judge verdict/cost。不得据此推断所有后续任务不存在 Judge 费用。
- 本次证明 V0 的一次端到端 Harness / Environment / Evaluator 接入可运行；尚未覆盖批量任务、重复 trial、外部 CLI 自动加载、完整成本 capture 或任何 V1 可靠性增强。

### 后续 V0 / V1 实验记录约定

V0 已有一条 Smoke Test；V1 尚无结果。后续每次个人 Agent 实验应另起记录，明确：代码版本、Agent 版本（V0 / V1）、与官方 Baseline 是否使用相同 task set / model / parameters / evaluation rule、开发调试或独立评估用途、trial / seed、Reward / Pass^k、Tool error、延迟、Token 与可获得的 API cost。

若 V1 使用可靠性机制，应同时记录对应的测试、失败案例和局限性；不得把开发调试任务或单次结果表述为独立性能提升。

## 2026-10-23 — V0 Retail 5-task Pilot

### 范围与可比性

- **状态：** 已完成；这是个人 `ecommerce_after_sales_v0` 的首次 **5-task Pilot**，不是完整 Retail benchmark，也不是已证明的性能提升。
- **官方环境：** `../tau2-bench/` 已核验为 `v2.0.0`，commit `989d3285ae669e49503324bdb9981bf14fccedeb`；Domain 为 `retail` / `en`、默认 task set、`base` split。
- **Agent / User：** `ecommerce_after_sales_v0` / `user_simulator`；双方均为 `openai/gpt-4.1-mini`、`{"temperature": 0.0}`。
- **任务与运行限制：** Tasks `0–4`、`num_trials=1`、`seed=42`、`max_steps=30`、`max_errors=10`、`max_concurrency=1`、`workers=0`、`max_retries=0`、`timeout=null`、`auto_review=false`。
- **其他运行设置：** `verbose_logs=true`、LLM log mode `all`；默认 semantic `communicate_scoring` 配置为 `gpt-5.5` / low reasoning。结果中 `communicate_checks` 都为空，不能据此断言该 Judge 实际未调用。
- **原始 artifact：** `../tau2-bench/data/simulations/retail-v0-pilot-0-4/results.json`；其中 `agent_info.implementation=ecommerce_after_sales_v0`，确认使用的是个人 V0 Agent。artifact 的 `git_commit=3ff6f310…` 是运行时个人项目目录的 provenance，不是官方源码版本。

本次运行入口为：

```bash
PYTHONPATH=src ../tau2-bench/.venv/bin/python \
  -m ecommerce_after_sales_agent.retail_pilot --run
```

对照 artifact 为 `../tau2-bench/data/simulations/retail-baseline-0-4/results.json`。与 2026-10-22 官方 Pilot 相比，任务、split、模型、temperature、seed、step/error/retry/concurrency 限制和评测规则一致。设计上必要的差异是 Agent 实现、process-local 注册/程序入口和新的 `save_to` 目录；二者的 `verbose_logs` 与 LLM log mode 均为 `all`。因此可作初步行为对比，但单 trial、5 个 task 不足以隔离模型输出随机性或证明 Agent 优劣。

### 逐任务对比

| Task | V0 Reward / Termination | 官方 Reward / Termination | V0 DB / Action / NL | 官方 DB / Action / NL | V0 / 官方耗时 |
| --- | --- | --- | --- | --- | ---: |
| 0 | `1.0` / `user_stop` | `0.0` / `user_stop` | `1.0` / `5/5` / 无 assertion | `0.0` / `4/5` / 无 assertion | 30.19 / 25.22 s |
| 1 | `1.0` / `user_stop` | `1.0` / `user_stop` | `1.0` / `5/5` / 无 assertion | `1.0` / `5/5` / 无 assertion | 16.52 / 17.80 s |
| 2 | `0.0` / `max_steps` | `0.0` / `user_stop` | 未评分 / 未评分 / 未评分 | `0.0` / `3/11` / `0/1` | 23.61 / 27.28 s |
| 3 | `0.0` / `user_stop` | `0.0` / `max_steps` | `1.0` / `11/12` / `0/1` | 未评分 / 未评分 / 未评分 | 19.15 / 24.34 s |
| 4 | `0.0` / `user_stop` | `0.0` / `user_stop` | `1.0` / `12/13` / `0/1` | `1.0` / `12/13` / `0/1` | 26.81 / 24.27 s |

**V0 通过数为 2/5、平均 Reward 为 0.40；官方 Pilot 为 1/5、0.20。** 两个数均只来自同一固定 task set 的一个 trial，不可描述为稳定提升或完整基准成绩。Action Checks 是诊断指标；本组任务的 `reward_basis` 为 `DB + NL_ASSERTION`，且 premature termination 会绕过正常评测。

### Task 2–4 trajectory 事实与分析

以下内容来自保存的 messages、Tool Result 与 `reward_info`；不复制客户资料、订单号、item ID 或完整对话。

#### Task 2 — write 成功但在 step cap 处提前终止

**已确认事实**

- V0 trace 共 31 条 messages。它完成 authentication、商品类型/商品详情查询、profile 查询、5 次**依次**的 `get_order_details`，然后完成确认和 `return_delivered_order_items`。
- 该 return Tool Result 为成功（无 Tool Error），且 Agent 随后发送完成回复；但 Simulation 的 `termination_reason=max_steps`，`reward_info` 明确标为 premature termination，DB、Action Checks 与 NL Assertions 都没有执行。
- 五次单独 order read 连同各自 Tool Result 占 10 条 messages；再加上前置 read、确认和用户往返，是本次 30-step budget 的主要交互消耗。

**与官方的对比与解释边界**

- 官方同题也把可用 T-shirt 数说为 12；之后跟随用户给出的不存在订单号，两批查询均得到 Tool Error，最终 transfer，正常进入评测但 return write/DB/NL 均失败。
- V0 改从已认证 profile 中查询账户订单，找到了可处理订单并成功写入；这解释了两条 trace 的路径差异，但由于 V0 未通过正常终止，不能把成功 Tool Result 当作该任务成功或性能提升。
- step 计数的精确内部规则需以 Harness 代码和更小的可复现实验验证；artifact 足以确认的是：该任务在配置的 cap 处终止，而非 Tool Error 导致终止。

#### Task 3 — 未给出明确的 10

**已确认事实**

- V0 完成 write，DB Check 为 `1.0`，随后正常 `user_stop`；但其面对“exactly how many”时只说 T-shirt 有多个 variants，未说出数值。保存的 NL verdict 因未给出 `10` 而失败。
- V0 只缺一项诊断性 Action Check（`11/12`）；其余 action 与 DB 状态通过。该 action 指标不在本任务的 reward basis。
- 官方在相同任务中完成 write 后，用户再次询问数量时回答 `12`，随后触发 `max_steps`，因此也未得到正常评分。

**结论**

两种 Agent 都没有把 Product Tool Result 中的 availability 过滤结果可靠地转成所需事实；V0 此次是遗漏数值，官方此次是错误总数。不能仅由这一条 trace 判定是 Prompt、上下文顺序还是模型决策的唯一根因。

#### Task 4 — 将总 variants 数误作 available 数

**已确认事实**

- V0 从 T-shirt Product Tool Result 得到 12 个 variants，其中 **10 个 `available=true`、2 个 `available=false`**；随后对用户回答“12”。这是总 variants 计数，而非可用 variants 计数。
- 两个 pending-order write 均成功，DB Check 为 `1.0`，Action Checks 为 `12/13`；但 NL verdict 明确指出应答 `10`，所以 `NL_ASSERTION=0`、最终 Reward 为 `0.0`。
- 官方本题也完成相同 DB/action 结果，但只回答“several options”，同样未满足数字 assertion。

**结论**

这不是 Tool 返回 unavailable variants 错误：artifact 直接显示了 12 / 10 / 2 的数据结构。已确认的问题是 Agent 对 Tool Result 的 availability-aware counting/事实表达不可靠；尚不能仅据此把根因归为某个单独 Prompt 文本。

### 实现与行为差异、成本局限

- **实现边界：** V0 是个人实现的 `HalfDuplexAgent`，自管 system prompt 与 message history，并调用官方 `generate()`；官方 `llm_agent` 是官方实现。两者都把 Tool Call 交由官方 Harness / Environment 执行。
- **观察到的行为：** V0 在 Task 2 从 authenticated profile 发现订单，而官方反复查询用户提供的无效 ID；V0 在 Task 3 将五个 order reads 作为一批 Tool Call，官方 trace 则逐次调用。这些是本次 trace 事实，不足以概括所有任务的稳定行为。
- **共同失败模式：** 两者在含 T-shirt 数量 assertion 的任务中都未基于 `available=true` 得出/表达正确的 10；Task 4 的 DB write 都正确而 NL assertion 失败。
- **V0 特有的本次问题：** Task 2 在实际 write 后耗尽 step budget；Task 3 未给出任何明确数量；Task 4 给出总数 12。官方特有的本次 Task 2 路径是无效订单号重试后 transfer，Task 3 是在回答 12 后达 step cap。
- **费用/Token：** V0 保存的 User Cost 总和为 **$0.0089176**；各任务 `agent_cost=null`、`agent_usage=null`，结果中没有 User token usage 字段，也没有独立 Judge token/cost 字段。这些缺失不等于相应成本为零。Tasks 3、4 的 NL verdict 是存在 NL judging 的实际证据；`communicate_checks` 均为空，`auto_review=false` 且 `review=null`，故没有保存的 semantic communication Judge verdict 或 auto-review 成本证据。

### 阶段 3B 的证据驱动优先级（2026-10-23；当时尚未实现）

1. **Grounded factual response / availability-aware aggregation。** 在 Agent 准备陈述 inventory count 前，按 Tool Result 的结构化 `available` 字段计算并验证，而不是让 LLM 凭总 variants 或模糊措辞回答。测试应使用合成的 Product Tool Result（含不同总数和不可用 variants），断言 Agent 对可用数的自然语言结论正确；再以 Task 2–4 类场景做回归测试，避免写死“10”。
2. **Step-budget-aware planning and completion。** 维护可见的剩余 interaction budget，避免在多实体售后流程中消耗完 budget 后才发出最终回复或完成写入。测试应使用 Mock Harness/message sequence 模拟接近 cap 的多订单流程，验证 Agent 记录 budget、减少非必要轮次并在成功 Tool Result 后优先给出完成回复；不得改变官方 step cap 后把结果混作本对照实验。

这两项建议都来自当前 Pilot 的失败证据。当时尚未实现、尚无 V1 对照成绩；Availability-aware Factual Grounding 的后续 Mock 工程验证见下一节。Tool Error recovery 虽值得后续研究，但 V0 本次没有 Tool Error，不应排在本轮 V1 的证据优先级之前。

## 2026-10-24 — V1 Availability-aware Factual Grounding 工程回归

### 范围与缺陷发现

- **范围：** 对 `ecommerce_after_sales_v1` 的结构化 inventory fact state 做本地 Mock 回归；不调用 API、不运行 Retail Simulation、不修改官方 τ²-bench 或 V0 实验结果。
- **发现方式：** 代码审查发现旧实现将每个成功 Product Tool Result 的 fact 用 `list.extend()` 追加到 state。新增回归测试后，旧实现出现 **4 项失败**：同一 `product_id` 的旧统计仍出现在 grounding、相同结果重复、以及 `MultiToolMessage` 中同商品后值不能替换前值。
- **真实数据兼容性前提：** 前一轮只读检查已用保存的 V0 Pilot Product Tool Result 验证解析器可读取官方 Retail 的 `name`、`product_id`、`variants` 和布尔 `available` 结构；本次没有重新运行该 artifact。

### 根因与修复

- **根因：** `V1AgentState.availability_facts` 是 append-only list，`generate_next_message()` 对新 facts 执行 `extend()`；grounding 因而包含相同商品的全部历史版本。
- **修复：** state 改为有序 `dict[product_id, VariantAvailabilityFact]`。可信新 fact 按 `product_id` assignment/update 替换旧 value；Python dict 保留首次出现的 key 顺序，因此同一输入 history 的 grounding 顺序稳定。不同商品使用不同 key，不发生数量合并。
- **异常边界：** 无效 JSON、缺失/非布尔 `available`、Tool Error 都不会生成更新项，因此不能覆盖已有可信 fact。`MultiToolMessage` 仍按官方 message 顺序展开；同一批内同商品的最后一个有效结果获胜。
- **保留项：** 原始 ToolMessage、完整 messages history、基础 system prompt 中的 Retail Policy 和官方 Harness/Tool 边界均未改写。动态 grounding 只包含每个商品当前最新的可信统计。

### 回归结果与限制

- 新增/更新的测试覆盖：同商品更新与去重、不同商品独立、MultiToolMessage 顺序、无效结果不覆盖、完整 Policy/原始 history 保留，以及既有解析/Factory/Registry/Builder 场景。
- 先在旧代码上运行 V1 测试，确认 4 项新增回归测试失败；实施修复后运行完整 pytest：**31 passed，1 个上游 `audioop` deprecation warning**。
- 这只证明本地 state、context 构造和 Mock protocol 行为。尚未验证真实 LLM 是否遵循 grounding、实际 Retail Task 的 NL assertion / Reward、Token/延迟/费用影响，或更长对话中的产品事实选择效果。

## 2026-10-25 — V1 Availability-aware Factual Grounding 首次 Retail 5-task Pilot

### 范围、配置与可比性

- **状态：** 已完成。这是 `ecommerce_after_sales_v1` 的首次真实 Retail Pilot；固定 5 个任务、单个 trial 的结果，不是完整 benchmark，也不证明稳定的性能提升。
- **官方环境：** `../tau2-bench/` 为 τ²-bench `v2.0.0`，commit `989d3285ae669e49503324bdb9981bf14fccedeb`；`retail`、`base` split、Tasks `0–4`。
- **运行配置：** V1 / `user_simulator` 都使用 `openai/gpt-4.1-mini`、`temperature=0.0`；`seed=42`、`num_trials=1`、`max_steps=30`、`max_errors=10`、`max_retries=0`、`max_concurrency=1`、`workers=0`、`timeout=null`、`auto_review=false`、`verbose_logs=true`、LLM log mode `all`。评测规则和默认 semantic communication 配置与 V0 Pilot 相同。
- **原始 artifacts：** V0 为 `../tau2-bench/data/simulations/retail-v0-pilot-0-4/results.json`；V1 为 `../tau2-bench/data/simulations/retail-v1-pilot-0-4/results.json`。V1 的 `info.agent_info.implementation` 为 `ecommerce_after_sales_v1`，确认没有误用 V0。
- **唯一预期的实现差异：** V1 在保留 V0 的 Agent/Harness/Environment 边界的前提下，向 LLM 请求加入由 Product Tool Result 计算出的 latest availability facts。两个 artifact 的实际 conversation 仍是独立运行；即使固定 seed，也不能将任一对话差异直接归因于该 Context。

### 逐任务对比

`Action Checks` 是诊断信息。本组任务的 Reward 由 `DB + NL_ASSERTION` 的 `reward_basis` 决定；未正常完成的 V0 Task 2 没有正常评分结果。

| Task | V0 Reward / Termination | V1 Reward / Termination | V0 DB / Action / NL | V1 DB / Action / NL | V0 / V1 耗时 | 关键 Tool Call 差异 |
| --- | --- | --- | --- | --- | ---: | --- |
| 0 | `1.0` / `user_stop` | `0.0` / `user_stop` | `1.0` / `5/5` / 无 assertion | `0.0` / `4/5` / 无 assertion | 30.19 / 21.80 s | 两者都成功 exchange；keyboard replacement variant 不同。 |
| 1 | `1.0` / `user_stop` | `0.0` / `user_stop` | `1.0` / `5/5` / 无 assertion | `0.0` / `4/5` / 无 assertion | 16.52 / 16.51 s | V0 只 exchange thermostat；V1 成功执行 keyboard + thermostat exchange。 |
| 2 | `0.0` / `max_steps` | `1.0` / `user_stop` | 未评分 / 未评分 / 未评分 | `1.0` / `9/11` / `1/1` | 23.61 / 21.07 s | 都成功 return；V1 将五个 order reads 合并为一批 Tool Call。 |
| 3 | `0.0` / `user_stop` | `1.0` / `user_stop` | `1.0` / `11/12` / `0/1` | `1.0` / `11/12` / `1/1` | 19.15 / 18.80 s | 两者完成同类 order modification；V1 明确回答 availability 数。 |
| 4 | `0.0` / `user_stop` | `1.0` / `user_stop` | `1.0` / `12/13` / `0/1` | `1.0` / `12/13` / `1/1` | 26.81 / 17.48 s | 两者完成两个 order modification；V1 区分 total 与 available 数。 |

**结果：V0 为 2/5、平均 Reward `0.40`；V1 为 3/5、平均 Reward `0.60`。** V1 在本次固定小样本中使 Tasks 2–4 的 NL assertion 均通过，同时 Tasks 0、1 从成功变为失败。这是需要继续调查的 trade-off，不是已证明的整体提升。

### Grounding 在真实请求中的证据与正向观察

**已确认事实**

- V1 保存的 `llm_debug` 中，Tasks 2、3、4 的实际 Agent LLM request 均包含 `<verified_inventory_facts>`，其中 T-shirt 的聚合为 `total=12`、`available=10`、`unavailable=2`。这直接证明动态 Context 进入了真实 LLM 请求，而不只是 Mock 测试。
- 这三题的 Product Tool Result 同样支持 12 / 10 / 2；V1 的最终相关回复均明确给出 **10 available**，三个 NL assertions 都通过。
- Task 3、4 的 DB / Action 诊断与 V0 基本相同而 NL 由失败变为通过，因此“已提供正确、可用的事实并与正确回答同时出现”是 grounding 的正向证据。

**不能由本次数据确认的结论**

- 真实 request 中存在 Context，不能单独证明它是 LLM 正确回答、批量 Tool Call 或最终 Reward 变化的唯一原因；两个 run 的生成轨迹和 User Simulator 对话均不同。
- 没有发现 Retail Policy 被覆盖、截断或与新增 facts 明确冲突的 artifact 证据；也没有一个可将任意工具决策偏移直接归因于 Context 的对照诊断。

### Task 0、1：成功写入但与静态目标不匹配

#### Task 0

**已确认事实**

- V1 与 V0 都完成了 authentication、所需 reads 和 `exchange_delivered_order_items`；两次该 write 的 Tool Result 都成功，未见 Tool Error。
- 两者交换的原 item 和 thermostat replacement 一致，但 V1 选择了与 V0 不同的 keyboard replacement variant。V0 的 variant 与 golden write action 相符；V1 的 variant 不符，故 `Action Checks=4/5` 且最终 DB state 不匹配（`DB=0.0`）。
- V1 先向 User 提供可选 keyboard fallback，User 选择其中一个并确认；V0 提供/执行的是另一个 fallback。也就是说，失败不是 exchange Tool 执行失败，而是成功执行了与该 task 静态目标不同的 variant 选择。

**尚不能确认的归因**

- Task 0 的 V1 request 确实含 keyboard / thermostat 的 availability facts，但这些统计不指定该选哪个 variant。没有直接证据证明 grounding 导致了 V1 的 offer、User 的选择或 write 参数变化。
- 这可能反映 LLM 对 fallback 和对话分支的决策差异；也可能受独立生成轨迹影响。需经重复/受控实验才能将其认定为 V1 回归缺陷。

#### Task 1

**已确认事实**

- V0 成功执行 thermostat-only exchange，并匹配 golden write；V1 成功执行了 keyboard + thermostat 的 exchange，但该 write 不匹配，因而 `Action Checks=4/5`、`DB=0.0`。
- V1 先把 keyboard fallback 作为可选方案，User 随后选择 keyboard + thermostat 并确认；V0 的对话最终只处理 thermostat。两次 Tool Result 均为成功。
- 任务的静态期望与 V0 的 thermostat-only 路径相符，V1 的额外 keyboard 写入导致 DB mismatch。

**尚不能确认的归因**

- V1 request 也含两个商品的 availability facts，但没有证据显示其中的 total/available 数直接要求或诱发额外 keyboard exchange。只能确认 V1 的对话/写入路径改变，不应把相关性写成 grounding 的确定性副作用。

### Task 2：正常评分与 Action Check 差异

**已确认事实**

- V0 已成功调用 return Tool，但在 `max_steps` 提前终止，未得到 DB / Action / NL 正常评分。V1 正常以 `user_stop` 结束，并完成 `DB=1.0`、`NL=1/1`。
- V1 trace 中的五个 order reads 是一批 MultiTool Call；V0 为依次发起的 reads。这是 V1 能在 cap 前结束的可见交互差异，但本次没有因果实验，不能断言它由 grounding 造成。
- V1 的 return write Tool Result 成功，且最终 DB 与 golden replay 一致，所以 DB Check 为 `1.0`。但其 item ID list 的前两个元素与 expected action 的顺序相反，导致 return write 的 Action Check 未匹配，合计为 `9/11`。
- 官方 `../tau2-bench/src/tau2/data_model/tasks.py` 的 `Action.compare_with_tool_call()`（约 178–195 行）对选择的参数使用直接相等比较；list 顺序不同即不等。`evaluator_env.py` 的 Environment evaluator 则重放 golden action 后比较 DB state。因此同一条 write 可以 **DB 相同但 Action Check 不同**。由于 Action 不在本题 `reward_basis`，该诊断失败不阻止 Reward `1.0`（组合逻辑见 `evaluator.py` 约 238–284 行）。

### Token、费用与 Judge 边界

- `results.json` 中 V1 的 `agent_cost` / `agent_usage` 仍为 `null`，但 verbose `llm_debug` 的 Agent response records 含可汇总 usage/cost。按这些 debug records 汇总，V1 Agent 为 51 次调用、`278,952` prompt tokens、`3,276` completion tokens、约 **$0.0467424**；V0 为 57 次、`311,005` / `2,838`、约 **$0.0467668**。这些是已保存的 Agent 调用记录，而不是零成本。
- V1 保存的 User Cost 合计约 **$0.0110004**；结果 artifact 没有 User token usage，也没有可汇总的 Judge token/cost。NL assertions 的 verdict 是 Tasks 2–4 存在 NL judging 的实际证据；`communicate_checks` 为空，`auto_review=false`，没有保存的 semantic communication Judge verdict / cost 证据。
- V1 总 Agent prompt tokens 较 V0 少，主要同时伴随较少的 Agent 调用（51 vs 57）；Tasks 0、1 的 V1 prompt tokens 则略高。两次 trajectory 长度不同，无法从这些 aggregate 判断新增 Context 是否造成异常 Token 增长或成本变化，也不能将缺失的 Judge 费用当作零。

### 局限与下一步

- 本次只有固定 Tasks `0–4`、一个 trial、一个 seed；不报告 Pass^k，也不能将 `0.60` 相比 `0.40` 表述为稳定提升。
- 下一步优先选择 **B：扩大/重复 V0–V1 对照实验**，并预先记录 Agent/User/Judge usage。理由是 Tasks 0、1 的结果回归已被观察到，但尚未证明为 Grounding 的确定性代码缺陷；先重复和分析相同配置下的分支稳定性，才能判断是否需要修复。此时开始 V1-2 step-budget 机制会混入新的变量，尚不宜优先进行。

## 2026-10-25 — V0/V1 Seed 与消息协议兼容性修复（无 API）

- **发现与依据：** 官方 Text `Orchestrator.initialize()` 会对 Agent 调用 `set_seed(self.seed)`（`../tau2-bench/src/tau2/orchestrator/orchestrator.py` 约 542–545 行）。旧 V0 没有 `LLMConfigMixin`，因此实际继承的是 Participant 的仅告警空实现；其后续 `generate()` 不会获得 Harness seed。V1 继承 V0，受同一问题影响。
- **修复：** V0 改为以官方 `LLMConfigMixin` 为首个基类；该 mixin 将每个 simulation 的 seed 写入 `llm_args["seed"]`，而不覆盖已有 `temperature` 等参数。V1 通过继承自动采用相同实现。未修改 Prompt、Grounding 算法、Retail Tool、Harness 或 Evaluator。
- **消息协议：** V0/V1 的 resumable history 现使用官方 `is_valid_agent_history_message()` 规则：只接受 AssistantMessage、非 Tool Call 的 UserMessage 与 `requestor="assistant"` 的 ToolMessage；运行时也拒绝 user-requested Tool Result 或非 Agent 输入。合法 `MultiToolMessage` 仍逐条展开并保留原始 Tool Result。
- **回归：** Mock 捕获验证 V0/V1 的 `generate()` 参数包含 Harness seed，并保留已有 LLM 参数；覆盖合法 history / ToolMessage / MultiToolMessage、非法 history / requestor / message type，以及 V1 grounding。运行 `PYTHONPATH=src ../tau2-bench/.venv/bin/python -m pytest -q`：**39 passed，1 个上游 `audioop` deprecation warning**。
- **后续 multi-trial 随机性：** 官方 `runner/batch.py` 先以 run-level `config.seed` 初始化 Python RNG，再为每个 `trial` 生成一个 seed；同一 trial 的所有 task 共用该 trial seed，随后 `Orchestrator` 将它分别传给 Agent 和 User。修复后 V0/V1 遵从此路径。对照实验应固定相同 task IDs、task 顺序、`config.seed`、`num_trials`、模型和 LLM 参数；不应把自定义的 `llm_args_agent.seed` 当成独立控制量，因为官方会按 trial seed 覆盖它。
- **实验边界：** 此修复可能改变后续 V0/V1 的 LLM 采样行为。既有 V0/V1 Pilot artifacts 保留为修复前结果，不覆盖、不删除；之后的对照实验必须另存并明确标记为 **seed/protocol compatibility-fixed**，不得直接把新旧结果混作同一代码版本的重复 trial。

## 2026-10-25 — 修复后 V0/V1 换货重复对照（Tasks 0–1，3 trials）

### 范围、配置与完整性

- **目的：** 检查 Seed/History compatibility-fixed 后的 V0/V1 在换货路径上的稳定性；这是独立于旧 Pilot 的新代码版本实验。
- **Artifacts：** V0 为 `../tau2-bench/data/simulations/retail-v0-seed-protocol-fixed-repeat-0-1-t3/results.json`，V1 为 `../tau2-bench/data/simulations/retail-v1-seed-protocol-fixed-repeat-0-1-t3/results.json`。两份各有 6 条完整 simulation，且 `agent_info.implementation` 分别为 `ecommerce_after_sales_v0` / `ecommerce_after_sales_v1`。
- **可比配置：** Retail `base` split、Tasks `0, 1`、每 task `3` trials、`openai/gpt-4.1-mini`（Agent/User，`temperature=0.0`）、run seed `42`、`max_steps=30`、`max_errors=10`、`max_retries=0`、`max_concurrency=1`、`workers=0`、`auto_review=false`、`verbose_logs=true`、LLM log mode `all`，以及与旧 Pilot 相同的默认 semantic communication 配置。除 Agent 实现和新 `save_to` 目录外，两个 `TextRunConfig` 相同。
- **Trial seed：** 官方 artifact 的零起始 `trial=0/1/2` 分别使用 `670487`、`116739`、`26225`；同一 trial 的 Tasks 0、1 共用 seed。所有 12 个 simulation 均为 `user_stop`，无 Tool Error。

### 结果

| Task | V0 成功 / DB / Action | V1 成功 / DB / Action | V0 / V1 平均耗时 | 观察 |
| --- | --- | --- | ---: | --- |
| 0 | `3/3` / `3/3` / `15/15` | `2/3` / `2/3` / `14/15` | 16.65 / 17.49 s | V1 有一次成功 Tool write 但 replacement variant 不匹配。 |
| 1 | `1/3` / `1/3` / `13/15` | `3/3` / `3/3` / `15/15` | 16.45 / 15.66 s | V0 两次成功 Tool write 但多交换 keyboard。 |
| 合计 | **4/6** / `4/6` / `28/30` | **5/6** / `5/6` / `29/30` | 16.55 / 16.57 s | 6 个 sample/版本，不能作为稳定性能结论。 |

这两个 task 没有 NL assertion；`reward_basis=DB + NL_ASSERTION` 中的 NL 部分为空，故 Reward 差异由 DB Check 决定。失败条目的四项 read Action Checks 均通过，唯一不匹配项都是 `exchange_delivered_order_items`。

### 三个失败 trajectory（脱敏）

以下 `trial` 均使用官方结果的零起始编号；若按日常序号计数，`trial=1` 是第二次运行。

| Agent / Task / trial / seed | 已确认的写入与确认过程 | 为什么 DB / Action 失败 |
| --- | --- | --- |
| V1 / Task 0 / `1` / `116739` | 已认证、读取 order/product，列明两个 replacement 和支付方式；User 显式确认；exchange Tool `executed` 且 `error=false`。 | keyboard replacement 是一个可用的 clicky + RGB variant，但与静态 gold action 的 keyboard variant 不同；thermostat replacement 一致。因此 write Action Check 与最终 DB 都不匹配。 |
| V0 / Task 1 / `0` / `670487` | 已认证、检查目标 exact keyboard variant 不可用后，列出替代项；User 选择 white-backlight keyboard + thermostat 并再次显式确认；Tool 成功执行。 | 静态目标要求只 exchange thermostat。实际 call 同时交换 keyboard 和 thermostat，故 write / DB 不匹配。 |
| V0 / Task 1 / `1` / `116739` | 与上一条相同的 fallback、User 选择和显式确认链路；Tool 成功执行。 | 同样执行了 keyboard + thermostat，而非 gold 的 thermostat-only write。 |

**Policy 边界：** 三个失败 trace 都包含 authentication、order/product 查询、写入前对 action details 的明确确认，且 Tool 成功接受了 order、可用 replacement 与 payment method。没有保存的证据显示违反 Retail policy 的硬性换货条件。Task 1 的 User 初始条件在 exact keyboard variant 不可用时倾向 thermostat-only，但随后的模拟 User 明确选择并确认了替代 keyboard；这与静态 gold action 不一致，不能仅据此断定为 policy violation 或 Tool defect。

### Seed、Token 与费用

- 每条 simulation 的 verbose Agent `llm_debug` request 都包含与该 simulation `seed` 相同的 `kwargs.seed`，且同一 simulation 内全部 Agent request 一致。这验证了修复后的 Harness → Agent → `generate()` 参数传递。
- 这只证明请求携带 seed；未调用 provider 的可重复性审计接口，不能证明模型服务对相同 seed / prompt 的输出在跨运行时绝对确定。
- V0：55 次 Agent LLM 调用、`284,272` prompt tokens、`3,144` completion tokens、debug records 汇总 Agent Cost **$0.0424384**；User Cost **$0.0120716**；耗时合计 `99.28 s`。
- V1：56 次 Agent LLM 调用、`293,965` prompt tokens、`3,340` completion tokens、debug records 汇总 Agent Cost **$0.0545396**；User Cost **$0.0117816**；耗时合计 `99.43 s`。
- `results.json` 的 `agent_cost` / `agent_usage` 仍为 `null`；上述 Agent 数据来自保存的 debug records。两份结果均没有可汇总的 Judge token/cost，且 `communicate_checks=null`；缺失不等于零成本。

### 结论与下一步

- 这组证据**不支持**“V1 存在已确认的系统性换货退化”：V1 在 Task 1 为 `3/3`，总体为 `5/6`；但 V1 Task 0 仍有 `1/3` 的静态 write mismatch，样本不足以排除更广泛回归。
- 也没有因果证据表明 Grounding 导致 V1 的 Task 0 replacement 选择。V1 request 中会加入 Product availability facts，但这些 aggregate facts 不指定应选哪个具体 variant；V0 和 V1 的独立 LLM/User trajectories 也不能作为受控消融。
- 未发现需要立即修复的 Agent 代码缺陷。建议将 Tasks 0–1 保留为回归 sentinel，下一步转向修复后 Tasks 2–4 的多 trial Grounding stability 对照；这是该机制的目标失败模式，且尚未在修复后版本重复验证。

## 2026-10-25 — 修复后 V1-1 Grounding 稳定性重复对照（Tasks 2–4，3 trials）

### 范围与可比性

- **目的：** 验证 Seed/History compatibility-fixed 后，V1-1 Availability-aware Factual Grounding 在其目标失败模式（可用 T-shirt variant 数）上的重复表现；不是全 Retail Benchmark。
- **Artifacts：** V0 为 `../tau2-bench/data/simulations/retail-v0-seed-protocol-fixed-grounding-repeat-2-4-t3/results.json`；V1 为 `../tau2-bench/data/simulations/retail-v1-seed-protocol-fixed-grounding-repeat-2-4-t3/results.json`。两份各含 9 条 simulation；保存的 Agent `llm_debug` record 的 `call_name` 分别为 `ecommerce_after_sales_v0` 与 `ecommerce_after_sales_v1`。
- **相同配置：** Retail `base` split、Tasks `2,3,4`、每 task `3` trials、Agent/User 均为 `openai/gpt-4.1-mini`、双方 `temperature=0.0`、run seed `42`、`max_steps=30`、`max_errors=10`、`max_retries=0`、`max_concurrency=1`、`workers=0`、`auto_review=false`、`verbose_logs=true` 与 LLM log mode `all`。除 Agent 和 `save_to` 外，配置相同；trial `0/1/2` 的 seed 均为 `670487/116739/26225`。
- **评分边界：** 正常 `user_stop` 的 8 条/版本进入评测；各版本各有 1 条 `max_steps`，该条的 DB、Action、NL 均为未评分（不是失败的 NL assertion）。Reward 仍由本组任务的 `DB + NL_ASSERTION` 决定，Action Checks 仅作诊断。

### 逐 task / trial 结果

`—` 表示 Harness 因 `max_steps` 未进入正常评测，并非零分的 DB/Action/NL 指标。

| Agent | Task / trial / seed | Reward / Termination | DB | Action | NL | 耗时 |
| --- | --- | --- | ---: | --- | --- | ---: |
| V0 | 2 / 0 / 670487 | `0.0` / `user_stop` | 1.0 | 10/11 | 0/1 | 23.73 s |
| V0 | 2 / 1 / 116739 | `0.0` / `user_stop` | 1.0 | 10/11 | 0/1 | 21.05 s |
| V0 | 2 / 2 / 26225 | `0.0` / `user_stop` | 0.0 | 3/11 | 0/1 | 12.64 s |
| V0 | 3 / 0 / 670487 | `0.0` / `user_stop` | 1.0 | 11/12 | 0/1 | 24.48 s |
| V0 | 3 / 1 / 116739 | `0.0` / `user_stop` | 1.0 | 11/12 | 0/1 | 17.23 s |
| V0 | 3 / 2 / 26225 | `0.0` / `user_stop` | 1.0 | 11/12 | 0/1 | 21.21 s |
| V0 | 4 / 0 / 670487 | `0.0` / `user_stop` | 1.0 | 12/13 | 0/1 | 17.02 s |
| V0 | 4 / 1 / 116739 | `0.0` / `user_stop` | 1.0 | 12/13 | 0/1 | 17.50 s |
| V0 | 4 / 2 / 26225 | `0.0` / `max_steps` | — | — | — | 21.20 s |
| V1 | 2 / 0 / 670487 | `1.0` / `user_stop` | 1.0 | 10/11 | 1/1 | 23.04 s |
| V1 | 2 / 1 / 116739 | `0.0` / `max_steps` | — | — | — | 24.70 s |
| V1 | 2 / 2 / 26225 | `1.0` / `user_stop` | 1.0 | 9/11 | 1/1 | 23.64 s |
| V1 | 3 / 0 / 670487 | `1.0` / `user_stop` | 1.0 | 11/12 | 1/1 | 19.11 s |
| V1 | 3 / 1 / 116739 | `1.0` / `user_stop` | 1.0 | 11/12 | 1/1 | 19.91 s |
| V1 | 3 / 2 / 26225 | `1.0` / `user_stop` | 1.0 | 11/12 | 1/1 | 17.40 s |
| V1 | 4 / 0 / 670487 | `1.0` / `user_stop` | 1.0 | 12/13 | 1/1 | 18.50 s |
| V1 | 4 / 1 / 116739 | `0.0` / `user_stop` | 0.0 | 10/13 | 1/1 | 20.44 s |
| V1 | 4 / 2 / 26225 | `1.0` / `user_stop` | 1.0 | 12/13 | 1/1 | 18.00 s |

**汇总：** V0 为 **0/9** Reward 成功，V1 为 **7/9**。在可评分的 8 条中，V0/V1 的 DB 均为 `7/8`，但 NL assertion 分别是 **0/8** 与 **8/8**。因此 V1 的收益集中在本次目标事实陈述，不足以外推为全 benchmark 的稳定提升。

### Grounding 注入与库存回答

**已确认事实**

- V1 的 9 条 simulation 的实际 Agent `llm_debug` request 都在 Product Tool Result 之后含有 `<verified_inventory_facts>`；T-shirt 条目为 `total_variants=12`、`available_variants=10`、`unavailable_variants=2`。这是动态 Context 已进入真实 LLM request 的直接 artifact 证据。
- 8 条正常评分的 V1 trajectory 都明确回答 10 个 available variants，且 NL assertion 均通过；相同 8 条 V0 均未满足该 assertion（包含把总数当作可用数、给出其他数字或未明确给数字）。
- 这说明机制确实向真实请求提供了正确的结构化可用性统计，且与正确回答同时出现；但 V0/V1 是独立的 Agent/User LLM 轨迹，未做“同一轨迹移除 Context”的消融，不能把全部 Reward 差异单独归因于 Grounding。

### 两条 V1 失败轨迹（脱敏）

#### Task 2 / trial 1 / seed 116739：`max_steps`

**已确认事实**

- inventory 查询和“10 个可用”回答已经完成；Agent 随后在用户同意查询 profile 后，未批量读取订单，而是跟随 User 依次读取四个候选 order：三个不匹配，再发起第四个 order read。
- 最后一个 `get_order_details` 的 Tool Result 返回后，artifact 有 32 条 conversation message；Harness 已达到 `max_steps=30`，终止为 `max_steps`。没有后续 Agent turn，**没有调用** `return_delivered_order_items`，也没有完成关键 return write。
- 官方 HalfDuplex Orchestrator 的 `step()` 在 `../tau2-bench/src/tau2/orchestrator/orchestrator.py` 约 840–948 行按角色/消息转移后递增 `step_count`；`_check_termination()` 约 755–771 行在非 Environment 等待状态下以 `step_count >= max_steps` 结束。因此最后一个 Environment Tool Result 会被保存，但 Agent 没有剩余 turn 消化它并发起 write。

**解释边界与 Step Budget 启示**

- 可见的额外消耗是多次“询问/提供一个 order ID/单独 read/说明不匹配”的往返，而不是 Tool Error；成功的 V1 Task 2 trials 则一次 MultiTool Call 读取五个订单。不能仅据此认定批量读取必然最优或由 Grounding 导致路径差异。
- 该案例直接支持研究 Step-budget-aware planning：在进入多订单检索前让 Agent 看见剩余预算，并在已获得用户授权时优先合并独立 read，给确认、write 与最终回复保留 turn。它不证明应修改官方 `max_steps`。

#### Task 4 / trial 1 / seed 116739：NL 正确、DB 失败

**已确认事实**

- Agent 完成认证、T-shirt inventory 与订单 reads，并正确回答 10 个 available variants；Grounding Context 已存在，故 NL assertion 为 `1/1`。
- Agent 没有调用 `modify_pending_order_items`。当其说明修改需要 payment method 后，模拟 User 明确表示没有 Gift Card 或其他 payment method、不能继续；Agent 随后说明无法进行变更，User 正常结束会话。
- 静态 gold action 却包含两个 `modify_pending_order_items` writes（及一条未调用的额外 product read），所以实际 diagnostics 为 `10/13`，最终 DB 与 golden replay 不同（`DB=0.0`）。这里没有 Tool Result 失败，因为根本没有 write Tool Call。

**解释边界**

- 该失败可确认是实际 User 对话分支未执行 gold 指定的两次写入，与 Grounding 的库存回答无冲突。artifact 不足以判定是 Agent payment-flow 决策、模拟 User 分支还是静态目标与实际对话之间的目标张力所致；不能归因为 Grounding 回归或 Tool defect。

### Token、成本、延迟与 Judge 边界

| 指标 | V0 | V1 |
| --- | ---: | ---: |
| 总 simulation 耗时 / 平均 | 176.06 s / 19.56 s | 184.75 s / 20.53 s |
| Agent debug calls | 99 | 105 |
| Agent prompt / completion tokens | 550,235 / 6,635 | 582,281 / 6,512 |
| Agent debug-record Cost | $0.0832156 | $0.0907300 |
| User debug calls | 52 | 55 |
| User prompt / completion tokens | 57,348 / 1,994 | 60,902 / 1,949 |
| User Cost（artifact/debug 对应） | $0.0214064 | $0.0222952 |
| NL assertion Judge calls / Cost | 8 / $0.0300600 | 8 / $0.0301590 |

- `results.json` 的 `agent_cost` 与 `agent_usage` 均为 `null`；表中的 Agent/User/Judge usage 与 Cost 来自保存的 verbose `llm_debug` response records 的可复查汇总，不能把 results 字段的缺失视为零。
- 此次可见的 Judge 是每个正常评分条目的 `nl_assertions_eval`；`communicate_checks` 为空、`auto_review=false`，未发现 semantic communication Judge 或 auto-review 的额外调用/费用证据。以上金额是记录到的模型调用 Cost，未主张覆盖任何 provider 账单以外项目。

### 结论与 V1-2 设计建议（未实施）

- **V1-1 结论：** 在修复后、固定的 Tasks `2–4` 与 3 trials 中，真实 request 注入正确可用性统计，V1 的可评分 NL assertion 从 `0/8` 变为 `8/8`，Reward 从 `0/9` 变为 `7/9`。这是对目标机制的重复正向证据，但样本小、任务有选择性、存在独立随机对话，不能声称全 Retail Benchmark 的稳定提升或严格因果效应。
- **是否进入 V1-2：建议进入设计与最小实现。** Task 2 / trial 1 已显示一个明确的 budget 耗尽失败，且官方 Harness 的硬 cap 不会为最后 Tool Result 额外保留 Agent turn。机制应只向 Agent 提供可读的剩余 step 预算/阈值提示，并在低预算时要求合并彼此独立的 reads、优先完成已确认 write 或给出最终回复；不得自行修改 Harness 计数、跳过 User confirmation 或直接执行 Tool。
- **接口前提与最小测试：** 已检查的官方 Agent 调用路径没有把 Orchestrator 的 `step_count`/`max_steps` 直接传入 `generate_next_message()`；V1-2 实现前必须先验证如何在不改官方 Harness 的条件下提供准确预算（例如由个人 Agent 根据官方消息转移规则维护保守估计，或由独立启动入口只注入配置上限）。以 Mock `generate()` / message sequence 构造接近 cap 的多订单场景，断言低预算 context 出现、正常预算不改变既有消息/Tool schema；另覆盖 Tool Result 后优先收束、合法 MultiToolMessage、确认不足时不写入。先做无 API 单元测试，再以与 V0 同配置的独立 Retail 对照验证是否减少 `max_steps`，同时报告 DB/NL/Action、Token、成本和可能的写入回归。
