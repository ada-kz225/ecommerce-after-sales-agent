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

### 阶段 3B 的证据驱动优先级（尚未实现）

1. **Grounded factual response / availability-aware aggregation。** 在 Agent 准备陈述 inventory count 前，按 Tool Result 的结构化 `available` 字段计算并验证，而不是让 LLM 凭总 variants 或模糊措辞回答。测试应使用合成的 Product Tool Result（含不同总数和不可用 variants），断言 Agent 对可用数的自然语言结论正确；再以 Task 2–4 类场景做回归测试，避免写死“10”。
2. **Step-budget-aware planning and completion。** 维护可见的剩余 interaction budget，避免在多实体售后流程中消耗完 budget 后才发出最终回复或完成写入。测试应使用 Mock Harness/message sequence 模拟接近 cap 的多订单流程，验证 Agent 记录 budget、减少非必要轮次并在成功 Tool Result 后优先给出完成回复；不得改变官方 step cap 后把结果混作本对照实验。

这两项建议都来自当前 Pilot 的失败证据；尚未实现、尚无 V1 对照成绩。Tool Error recovery 虽值得后续研究，但 V0 本次没有 Tool Error，不应排在本轮 V1 的证据优先级之前。
