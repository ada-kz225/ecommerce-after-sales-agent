# 阶段 2：τ²-bench 架构与执行机制笔记

> 范围：官方 `tau2-bench/` **v2.0.0**（commit `989d3285`）的 Retail 文本流程。本文件是后续开发参考，不记录完整用户对话、订单标识或 LLM debug log。实验数值与复现命令见 [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md)。

## 1. 系统架构

| 组件 | 已确认职责 | 关键实现 |
| --- | --- | --- |
| LLM | 根据消息历史、Prompt 和 Tool schema 生成文本或 Tool Call。 | `../tau2-bench/src/tau2/utils/llm_utils.py`：`generate()`、`_generate_once()` |
| `LLMAgent` | 维护 Agent 消息状态，组装 system prompt 与可用 Tool，调用 LLM。 | `../tau2-bench/src/tau2/agent/llm_agent.py`：`LLMAgent`、`get_init_state()`、`generate_next_message()` |
| Orchestrator | 在 User、Agent、Environment 之间半双工调度；将 Tool Call 交给 Environment；限制 step/error/time。 | `../tau2-bench/src/tau2/orchestrator/orchestrator.py`：`run()`、`step()` |
| Retail Environment | 持有 Retail DB 和 `RetailTools`；执行 Orchestrator 转交的 Tool Call，并转换结果/异常。 | `../tau2-bench/src/tau2/domains/retail/environment.py`：`get_environment()`；`../tau2-bench/src/tau2/environment/environment.py`：`get_response()` |
| Evaluator | Simulation 结束后进入评测；正常终止时按 task 的 `reward_basis` 检查 DB、动作和自然语言目标并计算 Reward。 | `../tau2-bench/src/tau2/evaluator/evaluator.py`：`evaluate_simulation()` |

文字流程图：

```text
User Simulator ──用户消息──> Orchestrator ──> LLMAgent
LLMAgent ────────文本──────> Orchestrator ──> User Simulator
LLMAgent ───── Tool Call ───> Orchestrator ──> Retail Environment / RetailTools
LLMAgent <── ToolMessage ─── Orchestrator <── Retail Environment / RetailTools

Orchestrator：调度上述消息、请求 Environment 执行 Tool、控制终止条件。

SimulationRun（trajectory + termination） ──> Evaluator ──> RewardInfo / results
```

构建入口位于 `../tau2-bench/src/tau2/runner/build.py`：`build_agent()`（100-175 行）取得 Environment 提供的 Tool，再通过 registry 创建 `llm_agent`；`build_text_orchestrator()`（570-655 行）组装文本 Simulation。`../tau2-bench/src/tau2/registry.py:302` 注册名称 `llm_agent`。

## 2. Agent 执行流程

### 消息状态、Prompt 与 LLM

`LLMAgentState`（`../tau2-bench/src/tau2/agent/llm_agent.py:44-49`）分为两部分：`system_messages` 保存由 `system_prompt` 构造的 `SystemMessage`，用于放置 Agent instruction 与 domain policy；`messages` 保存可追加的会话 history（User、Assistant、Tool message）。`get_init_state()`（94-113 行）初始化两者；`generate_next_message()`（115-145 行）将新输入加入 `messages`，把 `system_messages + messages` 一并交给 LLM，并将生成的 AssistantMessage 再追加到 `messages`。

生成时，Agent 使用 domain policy / system prompt、已保存 history 和 Environment 下发的 Tool schema，调用 `llm_utils.generate()`；后者将 `Tool.openai_schema` 交给 LiteLLM（`../tau2-bench/src/tau2/utils/llm_utils.py:643-682`）。模型以 `tool_choice="auto"` 决定文本或 Tool Call（648-650 行）。

```text
上一条 User/Tool 消息
  → LLMAgent state history
  → policy + prompt + Tool schemas
  → LLM response
  → AssistantMessage（文本或 Tool Call）
  → Orchestrator 路由
```

Tool Result 返回后，Orchestrator 将其作为下一轮的输入重新传给 `agent.generate_next_message()`（`../tau2-bench/src/tau2/orchestrator/orchestrator.py:875-916`）。因此 Agent 能基于 `Error: ...` 修正参数；是否真的修正是 LLM 的决策，不由 Harness 保证。

## 3. Retail Tool 例：`exchange_delivered_order_items`

定义在 `../tau2-bench/src/tau2/domains/retail/tools.py:240-316`，方法为 `RetailTools.exchange_delivered_order_items()`。它接收 `order_id`、`item_ids`、`new_item_ids` 和 `payment_method_id`；成功时更新订单为换货请求状态并返回 `Order`。Environment 再将结果序列化为 Tool Result。具体 OpenAI Tool schema 由 Tool 注册/类型定义生成，Environment 在运行时提供给 Agent。

| 类别 | 已确认行为 |
| --- | --- |
| 订单与 item | 检查订单存在且为 `delivered`；原 item 属于订单；old/new item 数量相等。 |
| 商品与库存 | 从原 item 的 product 派生可换 variant；检查目标 variant 存在且 available。 |
| 支付 | 以 `order.user_id` 和传入的 `payment_method_id` 调用 `_get_payment_method()`；该方法要求该 ID 存在于该用户的 `payment_methods`（`../tau2-bench/src/tau2/domains/retail/tools.py:145-162`）。若该支付方式是 `GiftCard`，仅在其 balance 小于本次 price difference 时拒绝。 |
| 写入 | 写入 `exchange requested` 及相关 exchange 字段。 |
| 失败返回 | Environment 捕获异常，返回 `ToolMessage(error=True, content="Error: ...")`，而非直接中断 Simulation。 |

上述校验是 **Tool 层硬校验**。相对地，先完成用户 authentication、确认用户有权处理某订单、取得明确用户 confirmation 等政策要求主要来自 `../tau2-bench/data/tau2/domains/retail/policy.md` 与 Agent Prompt；该换货函数本身不逐项强制这些前置条件。应将“policy 要求存在”与“该 Tool 已在代码强制”区分开。

## 4. Harness：执行控制与异常处理

`Orchestrator.run()`（`../tau2-bench/src/tau2/orchestrator/orchestrator.py:274-305`）执行 `initialize → step 循环 → termination check → finalize`。`step()`（840-949 行）中：

- Agent/Environment 发往 User 时调用 `user.generate_next_message()`；User/Environment 发往 Agent 时调用 `agent.generate_next_message()`。
- Agent 或 User 的 Tool Call 发往 Environment；`_execute_tool_calls()`（327-343 行）逐个执行，随后将 Tool Result 发回原调用者。
- 每完成一次消息路由回合，才在 948 行执行一次 `step_count += 1`。一个 step 可包含多个并列 Tool Call；Tool Call 与其返回不是同一个 step。

| 控制项 | 已确认触发方式 |
| --- | --- |
| `max_steps` | 每步后 `step_count >= max_steps`，终止为 `max_steps`。 |
| `max_errors` | `ToolMessage.error=True` 每次加一；达到上限终止为 `too_many_errors`。 |
| `timeout` | 单调时钟超过秒数，终止为 `timeout`。这是循环间检查，不会强制取消阻塞中的 API request。 |
| LLM API retry | `llm_utils._generate_once()` 将异常向上抛出；未显式给 `num_retries` 时，传给 LiteLLM 的默认值为 `DEFAULT_MAX_RETRIES`（611-613 行）。 |
| Simulation retry | `../tau2-bench/src/tau2/runner/progress.py:run_with_retry()` 对未捕获异常重跑整条 Simulation；最大尝试数为 `max_retries + 1`（52 行）。耗尽后保存 `infrastructure_error`，含 error / traceback（105-132 行）。 |

`Environment.get_response()`（`../tau2-bench/src/tau2/environment/environment.py:473-498`）是 Tool 异常边界：捕获异常、生成 `Error: {e}`、标记 `error=True`。这类业务错误不会自动触发 Simulation retry；它会交回 Agent，并计入 `max_errors`。

## 5. Evaluation 与指标

Simulation 结束后，`../tau2-bench/src/tau2/runner/simulation.py:111-148` 会在 Orchestrator 返回 `SimulationRun` 后调用 `evaluate_simulation()`。核心逻辑在 `../tau2-bench/src/tau2/evaluator/evaluator.py:89-285`：正常的 `agent_stop` / `user_stop` 会按 task 的 `reward_basis` 计算并组合对应 Reward component；若 termination 不满足这两个正常条件，早期保护会直接返回 `Reward=0`（123-133 行）。因此被 `max_steps` 截断的运行没有完整评分组件。

| 项目 | 作用 | 是否必然决定最终 Reward |
| --- | --- | --- |
| `reward_basis` | task 声明哪些维度参与 reward；是最终门控来源。 | 是 |
| DB Check | 在新 Environment 重放实际动作与 gold actions，对比最终 DB state。`evaluator_env.py`。 | 仅当 task 的 basis 包含 DB。 |
| Action Checks | 对照参考 action 序列；可用于诊断。`evaluator_action.py`。 | 仅当 basis 包含 ACTION。 |
| NL Assertion | 用 LLM 判断 Agent 输出是否满足精确自然语言断言。`evaluator_nl_assertions.py`。 | 仅当 basis 包含 NL assertion。 |
| Communicate Scoring | 对指定沟通目标使用 semantic judge。`evaluator_communicate.py`。 | 仅当 basis 包含 COMMUNICATE。 |

在一般 ALL 评测路径中，已启用的 reward component 被组合为最终 Reward（`evaluator.py` 约 202-268 行）；未列入 `reward_basis` 的结果可以保存为诊断信息，却不应被误读为最终评分门槛。

Task Success 使用 `reward ≈ 1.0` 判定（`../tau2-bench/src/tau2/metrics/agent_metrics.py:is_successful()`，12 行）。每个 task 的 `Pass^k` 使用无放回组合公式 `C(success_count, k) / C(num_trials, k)`（`pass_hat_k()`，113-126 行），然后跨 task 求平均；单 trial 只能解释 `Pass^1`。

## 6. Retail Pilot 的可靠性观察

以下是 **实际实验观察** 的脱敏摘要，不是根因定论；详细 Reward、时长与 judge evidence 见实验记录。

| Task | 已确认观察 | 待验证的解释 |
| --- | --- | --- |
| 0 | Tool 成功执行了 exchange，但最终 DB Check / Reward 失败；单任务 Smoke Test 曾成功。 | 静态目标、模拟用户选择与 Agent 决策之间是否存在冲突，需对比两次 trajectory 与 resolved config。 |
| 2 | 出现 6 次 `Order not found` Tool error，未达到 `max_errors=10`，最终 `user_stop`。 | Agent 是否应从错误中转向 account/order recovery path，以及 options count 为什么错误。 |
| 3 | 在 30-step cap 处以 `max_steps` 终止，未产生完整常规评分。 | 更高 step budget 是否足够、以及哪些 reads/turns 可减少，尚未验证。 |
| 4 | DB Check 通过，但没有明确给出要求的 10 个 T-shirt options；NL Assertion 失败，Reward 为 0。 | 是否需要 Agent-side 的显式 availability counting rule，需先确认任务与数据语义。 |

### 已有保护与研究方向

**已确认已有：** 消息合法性检查、Tool 异常转 `ToolMessage`、`max_steps` / `max_errors` / `timeout`、有限的整任务 retry、Agent/User cleanup、结果 checkpoint 原子写入及按 `(trial, task_id, seed)` 去重（`../tau2-bench/src/tau2/runner/checkpoint.py:379-403`）。部分 Retail Tool 还有领域状态校验，能拒绝不符合状态的重复写入。

**本次检查范围内未发现的通用机制：** 按“相同 Tool + 相同参数”自动去重、自动改参、或语义化 Tool-loop detector。该结论仅针对已检查的 Orchestrator / runner 主路径；不排除个别 domain Tool 另有业务保护。

值得继续研究的是：如何让 Agent 将 Tool error 结构化进入 state、避免重复失败调用、维护写操作状态、分配剩余 step budget，并在停止前核验任务目标。这些是研究方向，不是对官方实现缺陷的定论。

## 7. 阶段 3：自定义 Agent 接入（待研究）

阶段 3 将以 `build_agent()`、registry factory 和 `LLMAgent` 的 message / Tool 接口为入口，确认自定义 Agent 所需的最小协议、状态持久化方式、Tool schema 兼容性、停止语义及评测可复现性。

本阶段**不预设**具体 Agent 架构、Prompt、memory、planner 或 retry 策略；应在固定 task set 与独立实验记录下逐项验证。
