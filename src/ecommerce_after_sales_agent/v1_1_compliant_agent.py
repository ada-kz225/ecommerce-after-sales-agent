"""V1-1 对照 Agent：保留 Availability Grounding，并加入单 Tool Call 合规恢复。"""

from typing import Optional

from tau2.agent.base_agent import ValidAgentInputMessage
from tau2.data_model.message import AssistantMessage
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

from .tool_call_recovery import generate_with_single_tool_call_recovery
from .v1_agent import V1Agent, V1AgentState


class V1_1CompliantAgent(V1Agent):
    """不含 Step Budget 的 V1 Grounding 对照，复用 V1-2 的合规恢复机制。"""

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: V1AgentState
    ) -> tuple[AssistantMessage, V1AgentState]:
        """保留 V1 的 Grounding 与 history，仅替换单 Tool Call 生成边界。"""
        self._validate_input_message(message)
        incoming = self._incoming_messages(message)
        state.messages.extend(incoming)
        state.availability_facts.update(self._facts_by_product(incoming))

        context = list(state.system_messages)
        grounding_message = self._grounding_message(state)
        if grounding_message is not None:
            context.append(grounding_message)
        response = generate_with_single_tool_call_recovery(
            generate_fn=generate,
            model=self.llm,
            tools=self.tools,
            messages=context + state.messages,
            llm_args=self.llm_args,
            call_name="ecommerce_after_sales_v1_1_compliant",
        )
        state.messages.append(response)
        return response, state


def create_v1_1_compliant_agent(
    tools: list[Tool],
    domain_policy: str,
    **kwargs: object,
) -> V1_1CompliantAgent:
    """独立注册的合规 V1-1 对照 Agent Factory。"""
    llm = kwargs.get("llm") or "openai/gpt-4.1-mini"
    if not isinstance(llm, str):
        raise TypeError("llm must be a model-name string")
    llm_args = kwargs.get("llm_args")
    if llm_args is not None and not isinstance(llm_args, dict):
        raise TypeError("llm_args must be a dictionary or None")
    return V1_1CompliantAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=llm,
        llm_args=llm_args,
    )
