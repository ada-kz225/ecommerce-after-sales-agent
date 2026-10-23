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
