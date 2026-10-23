"""No-API contract tests for the project's minimal tau2 Agent integration."""

from tau2.agent.base_agent import HalfDuplexAgent
from tau2.data_model.message import MultiToolMessage, ToolMessage, UserMessage
from tau2.domains.retail.environment import get_environment
from tau2.registry import registry
from tau2.runner.build import build_agent

from ecommerce_after_sales_agent.minimal_agent import (
    FixedResponseAgent,
    create_fixed_response_agent,
)
from ecommerce_after_sales_agent.registration import (
    AGENT_NAME,
    register_fixed_response_agent,
)


def _tool_message(tool_id: str, content: str = "tool result") -> ToolMessage:
    return ToolMessage(
        id=tool_id,
        role="tool",
        requestor="assistant",
        content=content,
    )


def test_factory_receives_retail_tools_and_domain_policy() -> None:
    environment = get_environment()
    tools = environment.get_tools()
    agent = create_fixed_response_agent(tools, environment.get_policy())

    assert isinstance(agent, FixedResponseAgent)
    assert isinstance(agent, HalfDuplexAgent)
    assert agent.tools is tools
    assert agent.domain_policy == environment.get_policy()
    assert tools and tools[0].openai_schema["type"] == "function"


def test_state_initializes_with_policy_and_history() -> None:
    agent = create_fixed_response_agent([], "Policy text")
    history = [UserMessage.text("Earlier customer message")]

    state = agent.get_init_state(history)

    assert len(state.system_messages) == 1
    assert "Policy text" in (state.system_messages[0].content or "")
    assert state.messages == history


def test_agent_accepts_user_and_tool_messages_and_returns_valid_assistant_message() -> None:
    agent = create_fixed_response_agent([], "Policy text")
    state = agent.get_init_state()

    user_response, state = agent.generate_next_message(UserMessage.text("Help me"), state)
    tool_response, state = agent.generate_next_message(_tool_message("tool-1"), state)

    assert user_response.role == "assistant"
    assert user_response.content == "Integration contract verified."
    user_response.validate()
    tool_response.validate()
    assert [message.role for message in state.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


def test_agent_flattens_multi_tool_message_into_official_tool_history() -> None:
    agent = create_fixed_response_agent([], "Policy text")
    state = agent.get_init_state()
    multi_result = MultiToolMessage(
        role="tool",
        tool_messages=[_tool_message("tool-1"), _tool_message("tool-2", "second")],
    )

    response, state = agent.generate_next_message(multi_result, state)

    response.validate()
    assert [message.id for message in state.messages[:-1]] == ["tool-1", "tool-2"]
    assert state.messages[-1] == response


def test_registration_and_official_builder_construct_the_project_agent() -> None:
    name = register_fixed_response_agent()
    assert name == AGENT_NAME
    assert registry.get_agent_factory(name) is create_fixed_response_agent

    environment = get_environment()
    agent = build_agent(
        name,
        environment,
        llm="not-used-by-fixed-response-agent",
        llm_args={"temperature": 0.0},
    )

    assert isinstance(agent, FixedResponseAgent)
    assert [tool.name for tool in agent.tools] == [
        tool.name for tool in environment.get_tools()
    ]
    assert agent.tools[0].openai_schema == environment.get_tools()[0].openai_schema
    assert agent.domain_policy == environment.get_policy()
