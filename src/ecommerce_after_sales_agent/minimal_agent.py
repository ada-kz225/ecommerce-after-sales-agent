"""A no-API Agent used only to validate the tau2 half-duplex integration contract."""

from dataclasses import dataclass, field
from typing import Optional

from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
)
from tau2.environment.tool import Tool


@dataclass
class FixedResponseAgentState:
    """State split into a stable system prompt and append-only conversation history."""

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage] = field(default_factory=list)


# 继承官方 HalfDuplexAgent
# 接收 UserMessage、ToolMessage 或 MultiToolMessage
# 返回 AssistantMessage
# 自己维护 State
class FixedResponseAgent(HalfDuplexAgent[FixedResponseAgentState]):
    """Minimal text Agent that records official messages and returns fixed text.

    It deliberately makes no LLM request and no Tool Call.  The class verifies
    the Agent-side protocol only; the official Harness remains responsible for
    routing messages and executing Tools.
    """

    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        *,
        response_text: str = "Integration contract verified.",
    ) -> None:
        super().__init__(tools=tools, domain_policy=domain_policy)
        self.response_text = response_text

    # 把 domain_policy 放入 SystemMessage
    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> FixedResponseAgentState:
        """Create state from the policy and any official history supplied by Harness."""
        system_message = SystemMessage(
            role="system",
            content=(
                "You are a fixed-response integration-test agent.\n\n"
                f"## Domain Policy\n{self.domain_policy}"
            ),
        )
        # 过滤 MultiToolMessage
        history = list(message_history) if message_history is not None else []
        # A resumed half-duplex Agent should not receive MultiToolMessage in
        # history: Orchestrator validates and expands it before initialization.
        api_history = [message for message in history if not isinstance(message, MultiToolMessage)]
        return FixedResponseAgentState(
            system_messages=[system_message], messages=api_history
        )

    # 每一回合 Agent 的核心入口：
    # 收到单个 User 或 Tool 消息：追加一条。
    # 收到多个 Tool 结果：展开成多条 ToolMessage 存入 history。
    # 不思考、不调模型，直接生成固定文本的 AssistantMessage。
    # 校验返回消息合法，再把自己的回复也记进 history。
    # 返回 (response, state)。
    def generate_next_message(
        self,
        message: ValidAgentInputMessage,
        state: FixedResponseAgentState,
    ) -> tuple[AssistantMessage, FixedResponseAgentState]:
        """Accept User/Tool inputs, update history, and return valid fixed text."""
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)

        response = AssistantMessage.text(self.response_text)
        response.validate()
        state.messages.append(response)
        return response, state


# 根据官方传来的 Tool 和 policy，创建一只 Agent
def create_fixed_response_agent(
    tools: list[Tool], domain_policy: str, **_: object
) -> FixedResponseAgent:
    """Factory signature required by ``registry.register_agent_factory``."""
    return FixedResponseAgent(tools=tools, domain_policy=domain_policy)
