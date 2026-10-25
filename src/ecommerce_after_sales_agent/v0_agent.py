"""V0 Agent core: policy-aware state plus official LLM and Tool-Calling boundary."""
# 功能：理解消息、保存上下文、请求 LLM、返回文本或 Tool Call

from dataclasses import dataclass, field
from typing import Optional

from tau2.agent.base.llm_config import LLMConfigMixin
from tau2.agent.base_agent import (
    HalfDuplexAgent,
    ValidAgentInputMessage,
    is_valid_agent_history_message,
)
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


# 基础行为说明，目的是告诉LLM：你是售后客服，遵守policy，需要时使用Tool，每回合只能输出“给用户的文字”或者“Tool call“
BASE_AGENT_INSTRUCTION = """You are an e-commerce after-sales customer-service Agent.
Help the user according to the supplied domain policy. Use the supplied tools
when they are needed. In each turn, return either a user-facing response or
Tool Call(s), following the message protocol."""


@dataclass
class V0AgentState:
    """Stable system context and append-only API-compatible conversation history."""

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage] = field(default_factory=list)


class V0Agent(LLMConfigMixin, HalfDuplexAgent[V0AgentState]):
    """Minimal real-LLM Agent without Tool execution or V1 reliability policies."""

    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        *,
        llm: str,
        llm_args: Optional[dict] = None,
    ) -> None:
        # Keep the official mixin first in the MRO: Text Orchestrator calls
        # ``set_seed()`` before the first turn, and the mixin carries that
        # per-trial seed into the subsequent official ``generate()`` call.
        super().__init__(
            tools=tools,
            domain_policy=domain_policy,
            llm=llm,
            llm_args=llm_args,
        )

    # 把开头定义的基础指令 和 官方retail policy合在一起
    # 真实 LLM 调用时，这个会作为 system message发送
    @property
    def system_prompt(self) -> str:
        """Build the V0 prompt from instructions and the complete domain policy."""
        return (
            f"<instructions>\n{BASE_AGENT_INSTRUCTION}\n</instructions>\n"
            f"<policy>\n{self.domain_policy}\n</policy>"
        )

    # 输入 message_history，输出 V0AgentState
    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> V0AgentState:
        """Initialize system context and preserve valid resumable message history."""
        history = list(message_history) if message_history is not None else []
        self._validate_history(history)
        return V0AgentState(
            system_messages=[SystemMessage(role="system", content=self.system_prompt)],
            messages=history,
        )

    @staticmethod
    def _validate_history(history: list[Message]) -> None:
        """Apply the official text-agent resumable-history contract."""
        if not all(is_valid_agent_history_message(message) for message in history):
            raise ValueError(
                "Message history must contain only AssistantMessage, non-tool-call "
                "UserMessage, or ToolMessage requested by assistant."
            )

    @staticmethod
    def _validate_input_message(message: object) -> None:
        """Reject inputs that the text Harness must never route to an Agent."""
        if isinstance(message, UserMessage):
            if message.is_audio:
                raise ValueError("User message cannot be audio in Retail text mode")
            if message.is_tool_call():
                raise ValueError("Agent cannot receive a UserMessage tool call")
            return
        if isinstance(message, ToolMessage):
            if message.requestor != "assistant":
                raise ValueError("Agent can only receive ToolMessage requested by assistant")
            return
        if isinstance(message, MultiToolMessage):
            for tool_message in message.tool_messages:
                if tool_message.requestor != "assistant":
                    raise ValueError(
                        "Agent can only receive MultiToolMessage entries requested by assistant"
                    )
            return
        raise TypeError(
            "V0 Agent input must be UserMessage, ToolMessage, or MultiToolMessage"
        )

    # 每一回合 Agent 被 Harness 调用时的入口
    def generate_next_message(
        self, message: ValidAgentInputMessage, state: V0AgentState
    ) -> tuple[AssistantMessage, V0AgentState]:
        """Store a User/Tool result, ask the LLM, and retain its response.

        This method intentionally does not execute Tool Calls.  When the LLM
        returns a Tool Call, the official Orchestrator routes it to the
        Environment and later supplies its ToolMessage back to this method.
        """
        self._validate_input_message(message)

        # 1. 保存新输入（如遇 MultiToolMessage，先展开再逐条追加）
        # 例如 "我想更换订单中的机械键盘。"
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)

        # 2. 调用官方 LLM 封装
        response = generate(
            model=self.llm,
            tools=self.tools,
            messages=state.system_messages + state.messages,
            call_name="ecommerce_after_sales_v0",
            **self.llm_args,
        )
        # 3. 检查并保存输出
        if not isinstance(response, AssistantMessage):
            raise TypeError("V0 Agent LLM response must be an AssistantMessage")
        # 确保回复至少包含：有内容文本 or Tool Call
        response.validate()
        state.messages.append(response)
        return response, state


# 使用 Factory 按官方统一格式“造出一个 Agent”
def create_v0_agent(
    tools: list[Tool],
    domain_policy: str,
    **kwargs: object,
) -> V0Agent:
    """Factory used by the official registry and Builder."""
    llm = kwargs.get("llm") or "openai/gpt-4.1-mini"
    if not isinstance(llm, str):
        raise TypeError("llm must be a model-name string")
    llm_args = kwargs.get("llm_args")
    if llm_args is not None and not isinstance(llm_args, dict):
        raise TypeError("llm_args must be a dictionary or None")
    return V0Agent(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
