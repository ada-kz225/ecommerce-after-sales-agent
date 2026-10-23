"""Mock-only tests for the V0 Agent's LLM and Tool-Calling boundary."""

import pytest
from tau2.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.domains.retail.environment import get_environment
from tau2.registry import registry
from tau2.runner.build import build_agent

from ecommerce_after_sales_agent.registration import V0_AGENT_NAME, register_v0_agent
from ecommerce_after_sales_agent.v0_agent import V0Agent, create_v0_agent
import ecommerce_after_sales_agent.v0_agent as v0_module


def _tool_message(tool_id: str, content: str = "tool result") -> ToolMessage:
    return ToolMessage(
        id=tool_id,
        role="tool",
        requestor="assistant",
        content=content,
    )


def _install_mock_generate(
    monkeypatch: pytest.MonkeyPatch, response: AssistantMessage
) -> list[dict]:
    calls: list[dict] = []

    def fake_generate(**kwargs: object) -> AssistantMessage:
        calls.append(kwargs)
        return response

    monkeypatch.setattr(v0_module, "generate", fake_generate)
    return calls


def test_v0_state_includes_instruction_and_complete_domain_policy() -> None:
    agent = create_v0_agent([], "Retail policy text", llm="mock/model")
    state = agent.get_init_state([UserMessage.text("Earlier message")])

    assert len(state.system_messages) == 1
    prompt = state.system_messages[0].content or ""
    assert "e-commerce after-sales" in prompt
    assert "Retail policy text" in prompt
    assert [message.content for message in state.messages] == ["Earlier message"]


def test_user_message_calls_llm_and_persists_text_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v0_agent([], "Policy", llm="mock/model", llm_args={"temperature": 0})
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch, AssistantMessage.text("I can help."))

    response, state = agent.generate_next_message(UserMessage.text("Need help"), state)

    response.validate()
    assert response.content == "I can help."
    assert calls[0]["model"] == "mock/model"
    assert calls[0]["tools"] == []
    assert calls[0]["call_name"] == "ecommerce_after_sales_v0"
    assert calls[0]["temperature"] == 0
    assert [message.role for message in state.messages] == ["user", "assistant"]


def test_tool_call_is_returned_but_not_executed_by_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v0_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state()
    tool_call = ToolCall(id="call-1", name="find_user", arguments={})
    calls = _install_mock_generate(
        monkeypatch,
        AssistantMessage(role="assistant", tool_calls=[tool_call]),
    )

    response, state = agent.generate_next_message(UserMessage.text("Find my account"), state)

    response.validate()
    assert response.tool_calls == [tool_call]
    assert not any(isinstance(message, ToolMessage) for message in state.messages)
    assert len(calls) == 1


def test_tool_result_and_multi_tool_result_are_flattened_before_next_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v0_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch, AssistantMessage.text("Thanks."))

    _, state = agent.generate_next_message(_tool_message("one"), state)
    multi = MultiToolMessage(
        role="tool",
        tool_messages=[_tool_message("two"), _tool_message("three")],
    )
    response, state = agent.generate_next_message(multi, state)

    response.validate()
    assert [message.id for message in state.messages if isinstance(message, ToolMessage)] == [
        "one",
        "two",
        "three",
    ]
    assert [message.role for message in calls[1]["messages"]] == [
        "system",
        "tool",
        "assistant",
        "tool",
        "tool",
    ]


def test_v0_history_preserves_multi_turn_message_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v0_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state()
    _install_mock_generate(monkeypatch, AssistantMessage.text("Reply"))

    _, state = agent.generate_next_message(UserMessage.text("First"), state)
    _, state = agent.generate_next_message(_tool_message("result"), state)
    _, state = agent.generate_next_message(UserMessage.text("Second"), state)

    assert [(message.role, getattr(message, "content", None)) for message in state.messages] == [
        ("user", "First"),
        ("assistant", "Reply"),
        ("tool", "tool result"),
        ("assistant", "Reply"),
        ("user", "Second"),
        ("assistant", "Reply"),
    ]


def test_v0_factory_registry_and_builder_are_compatible() -> None:
    name = register_v0_agent()
    assert name == V0_AGENT_NAME
    assert registry.get_agent_factory(name) is create_v0_agent

    environment = get_environment()
    agent = build_agent(
        name,
        environment,
        llm="mock/model",
        llm_args={"temperature": 0},
    )

    assert isinstance(agent, V0Agent)
    assert agent.llm == "mock/model"
    assert agent.llm_args == {"temperature": 0}
    assert [tool.name for tool in agent.tools] == [
        tool.name for tool in environment.get_tools()
    ]
    assert agent.tools[0].openai_schema == environment.get_tools()[0].openai_schema
    assert agent.domain_policy == environment.get_policy()
