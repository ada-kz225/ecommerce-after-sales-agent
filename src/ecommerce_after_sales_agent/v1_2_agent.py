"""V1-2 Agent：在 V1 Grounding 之上提供保守的 step-budget planning。"""

import json
from dataclasses import dataclass, field
from typing import Optional

from tau2.agent.base_agent import ValidAgentInputMessage
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

from .tool_call_recovery import generate_with_single_tool_call_recovery
from .v1_agent import V1Agent, VariantAvailabilityFact


class MultipleToolCallsError(ValueError):
    """保留异常类型以兼容旧调用方；V1-2 不再将其抛给 Runner。"""


# 除了history 和 fact 之外，额外保存step预算状态
# 一个 step：Orchestrator 把当前消息从一个角色交给下一个角色处理一次。
# 角色：Agent，User，Environment
@dataclass
class V1_2AgentState:
    """V1 facts、原始 history 与仅供规划使用的本地预算估计。"""

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage] = field(default_factory=list)
    availability_facts: dict[str, VariantAvailabilityFact] = field(default_factory=dict)
    max_steps: int = 30
    exact_budget: bool = False
    decision_count: int = 0
    estimated_steps_used: Optional[int] = None
    processed_message_keys: set[str] = field(default_factory=set)
    candidate_order_count: int = 0


class V1_2Agent(V1Agent):
    """在 V1 基础上加入新会话 step 估计和不改变 policy 的规划提示。"""

    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        *,
        llm: str,
        llm_args: Optional[dict] = None,
        max_steps: int = 30,
        fresh_start: bool = True,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        super().__init__(tools, domain_policy, llm=llm, llm_args=llm_args)
        self.max_steps = max_steps
        self.fresh_start = fresh_start

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> V1_2AgentState:
        """仅在可辨认的新会话 opening 下启用精确预算模式。"""
        history = list(message_history) if message_history is not None else []
        self._validate_history(history)
        # 新的 Text Orchestrator 会在首次 Agent 决策前只放入一条 opening。
        # 恢复历史、空 history 或 Tool Call opening 均不能可靠还原已消耗 step。
        exact_budget = (
            self.fresh_start
            and len(history) == 1
            and isinstance(history[0], AssistantMessage)
            and not history[0].is_tool_call()
        )
        facts = self._facts_by_product(history)  # type: ignore[arg-type]
        return V1_2AgentState(
            system_messages=[SystemMessage(role="system", content=self.system_prompt)],
            messages=history,  # type: ignore[arg-type]
            availability_facts=facts,
            max_steps=self.max_steps,
            exact_budget=exact_budget,
            estimated_steps_used=0 if exact_budget else None,
            candidate_order_count=self._candidate_order_count(history),
        )

    @staticmethod
    def _message_key(message: ValidAgentInputMessage) -> str:
        """为 Harness 不应重复投递的输入建立稳定标识。"""
        if isinstance(message, ToolMessage):
            return f"tool:{message.id}:{message.requestor}"
        if isinstance(message, MultiToolMessage):
            return "multi:" + ",".join(
                f"{item.id}:{item.requestor}" for item in message.tool_messages
            )
        assert isinstance(message, UserMessage)
        return f"user:{message.timestamp}:{message.content}:{message.tool_calls}"

    @staticmethod
    def _candidate_order_count(messages: list[Message]) -> int:
        """从成功 Tool Result 提取候选订单数量，不保存或重复订单标识。"""
        for message in reversed(messages):
            if not isinstance(message, ToolMessage) or message.error:
                continue
            try:
                payload = json.loads(message.content or "")
            except json.JSONDecodeError:
                continue
            orders = payload.get("orders") if isinstance(payload, dict) else None
            if isinstance(orders, list) and all(isinstance(order, str) for order in orders):
                return len(orders)
        return 0

    @staticmethod
    def _budget_message(state: V1_2AgentState) -> SystemMessage:
        """把预算信息变成额外 System Message """
        lines = ["<step_budget>"]
        if state.exact_budget and state.estimated_steps_used is not None:
            remaining = max(state.max_steps - state.estimated_steps_used, 0)
            lines.extend(
                [
                    "This is a locally reconstructed estimate for a fresh normal text run; it is not a Harness-provided counter.",
                    f"estimated_steps_used={state.estimated_steps_used}; max_steps={state.max_steps}; estimated_remaining_steps={remaining}.",
                ]
            )
            # 当剩余步骤 <= 8 时才加入 low-budget 提醒
            if remaining <= 8:
                lines.append(
                    "Budget is low: avoid nonessential explanations and repeated questions. Preserve enough turns for required validation, explicit confirmation, a single write, and the user-facing completion."
                )
        else:
            lines.append(
                "Step usage cannot be reconstructed exactly from this history. Treat the remaining budget as uncertain and plan conservatively."
            )
        lines.extend(
            [
                "Always follow the Retail policy: authenticate first; validate orders; never invent results; list write details and obtain explicit user confirmation before any write.",
                "Make at most one Tool Call in a turn. Do not combine Tool Calls with user-facing text.",
            ]
        )
        if state.candidate_order_count:
            lines.append(
                "A prior successful Tool Result contains candidate order identifiers. If the preceding user request and policy authorize lookup, use the information already in history and continue one necessary read at a time instead of asking the user to repeat identifiers."
            )
        lines.append("</step_budget>")
        return SystemMessage(role="system", content="\n".join(lines))

    @staticmethod
    def _record_budget_input(
        message: ValidAgentInputMessage, state: V1_2AgentState
    ) -> bool:
        """每次 Agent 收到新输入时，更新 decision 数和 step 估算"""
        key = V1_2Agent._message_key(message)
        if key in state.processed_message_keys:
            return False
        state.processed_message_keys.add(key)
        if state.exact_budget:
            state.decision_count += 1
            # fresh Text run 中一次 Agent 决策结束时已完成两个角色转移：
            # 上一条 Agent 输出的投递，以及当前 USER/ENV -> AGENT 决策转移。
            state.estimated_steps_used = 2 * state.decision_count
        return True

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: V1_2AgentState
    ) -> tuple[AssistantMessage, V1_2AgentState]:
        """保留 V1 facts，并向 LLM 提供预算提示但不执行 Tool。"""
        self._validate_input_message(message)
        is_new_input = self._record_budget_input(message, state)
        if is_new_input:
            incoming = self._incoming_messages(message)
            state.messages.extend(incoming)
            state.availability_facts.update(self._facts_by_product(incoming))
            state.candidate_order_count = max(
                state.candidate_order_count, self._candidate_order_count(incoming)
            )

        context = list(state.system_messages)
        grounding_message = self._grounding_message(state)  # type: ignore[arg-type]
        if grounding_message is not None:
            context.append(grounding_message)
        context.append(self._budget_message(state))
        response = generate_with_single_tool_call_recovery(
            generate_fn=generate,
            model=self.llm,
            tools=self.tools,
            messages=context + state.messages,
            llm_args=self.llm_args,
            call_name="ecommerce_after_sales_v1_2",
        )
        state.messages.append(response)
        return response, state


def create_v1_2_agent(
    tools: list[Tool],
    domain_policy: str,
    **kwargs: object,
) -> V1_2Agent:
    """独立注册的预算感知 V1-2 Agent Factory。"""
    llm = kwargs.get("llm") or "openai/gpt-4.1-mini"
    if not isinstance(llm, str):
        raise TypeError("llm must be a model-name string")
    llm_args = kwargs.get("llm_args")
    if llm_args is not None and not isinstance(llm_args, dict):
        raise TypeError("llm_args must be a dictionary or None")
    max_steps = kwargs.get("max_steps", 30)
    if not isinstance(max_steps, int):
        raise TypeError("max_steps must be an integer")
    fresh_start = kwargs.get("fresh_start", True)
    if not isinstance(fresh_start, bool):
        raise TypeError("fresh_start must be a boolean")
    return V1_2Agent(
        tools=tools,
        domain_policy=domain_policy,
        llm=llm,
        llm_args=llm_args,
        max_steps=max_steps,
        fresh_start=fresh_start,
    )
