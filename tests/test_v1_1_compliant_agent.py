"""合规 V1-1 对照 Agent 的无 API 测试。"""

import json

import pytest
from tau2.data_model.message import AssistantMessage, ToolCall, ToolMessage
from tau2.domains.retail.environment import get_environment
from tau2.registry import registry
from tau2.runner.build import build_agent

from ecommerce_after_sales_agent.registration import (
    V1_1_COMPLIANT_AGENT_NAME,
    register_v1_1_compliant_agent,
)
from ecommerce_after_sales_agent.v1_1_compliant_agent import (
    V1_1CompliantAgent,
    create_v1_1_compliant_agent,
)
import ecommerce_after_sales_agent.v1_1_compliant_agent as v1_1_module


def test_v1_1_compliant_keeps_grounding_but_does_not_add_budget_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_1_compliant_agent(
        [], "Retail policy", llm="mock/model", llm_args={"temperature": 0.0}
    )
    state = agent.get_init_state()
    captured: list[dict] = []

    def fake_generate(**kwargs: object) -> AssistantMessage:
        captured.append(kwargs)
        return AssistantMessage.text("Grounded response")

    monkeypatch.setattr(v1_1_module, "generate", fake_generate)
    agent.set_seed(42)
    product = ToolMessage(
        id="product",
        role="tool",
        requestor="assistant",
        content=json.dumps(
            {
                "name": "Generic Product",
                "product_id": "product-1",
                "variants": {"a": {"available": True}, "b": {"available": False}},
            }
        ),
    )
    _, state = agent.generate_next_message(product, state)

    system_content = [
        message.content or ""
        for message in captured[0]["messages"]
        if message.role == "system"
    ]
    assert any("<verified_inventory_facts>" in content for content in system_content)
    assert not any("<step_budget>" in content for content in system_content)
    assert captured[0]["parallel_tool_calls"] is False
    assert captured[0]["seed"] == 42
    assert state.availability_facts["product-1"].available_variants == 1


def test_v1_1_compliant_uses_the_shared_one_retry_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_1_compliant_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state()
    responses = iter(
        [
            AssistantMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(id="bad-a", name="read_a", arguments={}),
                    ToolCall(id="bad-b", name="read_b", arguments={}),
                ],
            ),
            AssistantMessage(
                role="assistant",
                tool_calls=[ToolCall(id="good", name="read_a", arguments={})],
            ),
        ]
    )
    captured: list[dict] = []

    def fake_generate(**kwargs: object) -> AssistantMessage:
        captured.append(kwargs)
        return next(responses)

    monkeypatch.setattr(v1_1_module, "generate", fake_generate)
    response, state = agent.generate_next_message(
        ToolMessage(id="input", role="tool", requestor="assistant", content="ok"), state
    )

    assert len(captured) == 2
    assert response.tool_calls == [ToolCall(id="good", name="read_a", arguments={})]
    assert all(call["parallel_tool_calls"] is False for call in captured)
    assert len([message for message in state.messages if isinstance(message, AssistantMessage)]) == 1


def test_v1_1_compliant_factory_registry_and_builder_are_compatible() -> None:
    name = register_v1_1_compliant_agent()
    assert name == V1_1_COMPLIANT_AGENT_NAME
    assert registry.get_agent_factory(name) is create_v1_1_compliant_agent

    agent = build_agent(
        name,
        get_environment(),
        llm="mock/model",
        llm_args={"temperature": 0.0},
    )

    assert isinstance(agent, V1_1CompliantAgent)
    assert agent.llm_args == {"temperature": 0.0}
