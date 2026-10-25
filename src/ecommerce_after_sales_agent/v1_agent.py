"""V1 Agent: V0 execution boundary plus availability-grounded inventory facts."""

import json
from collections.abc import Mapping
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
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

from .v0_agent import V0Agent


# 这是已经核实的库存摘要，这里 frozen=True 可以防止后面不小心把“10 个 available”改成“12 个”。
@dataclass(frozen=True)
class VariantAvailabilityFact:
    """A count derived only from a complete Product-shaped Tool Result."""

    product_name: str
    product_id: str
    total_variants: int
    available_variants: int
    unavailable_variants: int


# 从 Retail Tool 返回的原始商品 JSON 中，确认数据是否完整；
# 如果完整，就用 Python 准确算出“总共有多少 variants、多少可用、多少不可用”
# 官方的 LLMAgent 面对不完整JSON 可能尝试自己推断，我的实现不接受不完整的信息
def extract_variant_availability_fact(content: Optional[str]) -> Optional[VariantAvailabilityFact]:
    """Return a verified availability summary, or ``None`` for incomplete data.

    The official Retail ``get_product_details`` result is JSON with a product
    name/id and a mapping of variants.  Every mapping value must explicitly
    carry a boolean ``available`` field before a count is trusted.  This is
    intentionally schema-shaped rather than product- or task-specific.
    """
    if not isinstance(content, str):
        return None
    try:
        product = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(product, Mapping):
        return None

    product_name = product.get("name")
    product_id = product.get("product_id")
    variants = product.get("variants")
    if (
        not isinstance(product_name, str)
        or not product_name.strip()
        or not isinstance(product_id, str)
        or not product_id.strip()
        or not isinstance(variants, Mapping)
    ):
        return None

    availability: list[bool] = []
    for variant in variants.values():
        if not isinstance(variant, Mapping):
            return None
        value = variant.get("available")
        # ``bool`` is deliberate: values such as 1, "true", or null are not
        # evidence of a complete Retail availability result.
        if not isinstance(value, bool):
            return None
        availability.append(value)

    available_variants = sum(availability)
    total_variants = len(availability)
    return VariantAvailabilityFact(
        product_name=product_name,
        product_id=product_id,
        total_variants=total_variants,
        available_variants=available_variants,
        unavailable_variants=total_variants - available_variants,
    )


# V1 比 V0 多一个 availability_facts：按 product_id 保存每个商品最新的可信库存摘要。
@dataclass
class V1AgentState:
    """V0-compatible history plus trusted inventory facts from Tool Results."""

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage] = field(default_factory=list)
    # dict preserves first-seen product order while assignment replaces stale data.
    availability_facts: dict[str, VariantAvailabilityFact] = field(default_factory=dict)


# V1 继承 V0
class V1Agent(V0Agent):
    """V0-derived Agent that supplies validated availability facts to its LLM.

    It neither calls Retail tools nor alters their results.  The official
    Harness still executes Tool Calls and returns ToolMessage objects.
    """

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> V1AgentState:
        history = list(message_history) if message_history is not None else []
        self._validate_history(history)
        return V1AgentState(
            system_messages=[SystemMessage(role="system", content=self.system_prompt)],
            messages=history,
            availability_facts=self._facts_by_product(history),
        )

    @staticmethod
    def _incoming_messages(message: ValidAgentInputMessage) -> list[APICompatibleMessage]:
        if isinstance(message, MultiToolMessage):
            # 展开 MultiToolMessage 成列表
            return list(message.tool_messages)
        return [message]

    # 只从满足下列条件的 message 生成 fact；同一批中后出现的可信结果覆盖前值。
    @staticmethod
    def _facts_by_product(
        messages: list[APICompatibleMessage],
    ) -> dict[str, VariantAvailabilityFact]:
        facts: dict[str, VariantAvailabilityFact] = {}
        for message in messages:
            if isinstance(message, ToolMessage) and not message.error:
                fact = extract_variant_availability_fact(message.content)
                if fact is not None:
                    facts[fact.product_id] = fact
        return facts

    # 将已验证的 facts 变成额外 SystemMessage
    # 可以理解成给 LLM 提供“可靠事实材料”
    @staticmethod
    def _grounding_message(state: V1AgentState) -> Optional[SystemMessage]:
        if not state.availability_facts:
            return None
        lines = [
            "<verified_inventory_facts>",
            "The following counts were calculated from complete successful tool results.",
            "Use available_variants for questions about what is available; do not substitute total_variants.",
        ]
        for fact in state.availability_facts.values():
            lines.append(
                f"Product {fact.product_name!r} ({fact.product_id}): "
                f"total_variants={fact.total_variants}; "
                f"available_variants={fact.available_variants}; "
                f"unavailable_variants={fact.unavailable_variants}."
            )
        lines.append("Do not infer a count for products not listed above.")
        lines.append("</verified_inventory_facts>")
        return SystemMessage(role="system", content="\n".join(lines))

    # 保存原始 message 再结合前面的可靠事实
    def generate_next_message(
        self, message: ValidAgentInputMessage, state: V1AgentState
    ) -> tuple[AssistantMessage, V1AgentState]:
        """Keep raw input, add only trusted facts, then call the official LLM helper."""
        self._validate_input_message(message)
        incoming = self._incoming_messages(message)
        state.messages.extend(incoming)
        # Invalid/error results produce no entry, so they cannot erase a prior fact.
        # Updating an existing dict key keeps its first-seen order and replaces its value.
        state.availability_facts.update(self._facts_by_product(incoming))

        grounding_message = self._grounding_message(state)
        context = list(state.system_messages)
        if grounding_message is not None:
            context.append(grounding_message)
        response = generate(
            model=self.llm,
            tools=self.tools,
            messages=context + state.messages,
            call_name="ecommerce_after_sales_v1",
            **self.llm_args,
        )
        if not isinstance(response, AssistantMessage):
            raise TypeError("V1 Agent LLM response must be an AssistantMessage")
        response.validate()
        state.messages.append(response)
        return response, state


def create_v1_agent(
    tools: list[Tool],
    domain_policy: str,
    **kwargs: object,
) -> V1Agent:
    """Factory for the separately registered availability-grounded V1 Agent."""
    llm = kwargs.get("llm") or "openai/gpt-4.1-mini"
    if not isinstance(llm, str):
        raise TypeError("llm must be a model-name string")
    llm_args = kwargs.get("llm_args")
    if llm_args is not None and not isinstance(llm_args, dict):
        raise TypeError("llm_args must be a dictionary or None")
    return V1Agent(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
