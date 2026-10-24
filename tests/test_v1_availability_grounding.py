"""Mock-only tests for V1 availability-grounded inventory facts."""

import json

import pytest
from tau2.data_model.message import AssistantMessage, MultiToolMessage, ToolMessage
from tau2.domains.retail.environment import get_environment
from tau2.registry import registry
from tau2.runner.build import build_agent

from ecommerce_after_sales_agent.registration import V1_AGENT_NAME, register_v1_agent
from ecommerce_after_sales_agent.v1_agent import (
    V1Agent,
    create_v1_agent,
    extract_variant_availability_fact,
)
import ecommerce_after_sales_agent.v1_agent as v1_module


def _product_result(
    name: str, product_id: str, availability: list[bool | None]
) -> str:
    variants = {
        f"variant-{index}": (
            {"item_id": f"item-{index}", "available": value}
            if value is not None
            else {"item_id": f"item-{index}"}
        )
        for index, value in enumerate(availability)
    }
    return json.dumps({"name": name, "product_id": product_id, "variants": variants})


def _tool_message(tool_id: str, content: str, *, error: bool = False) -> ToolMessage:
    return ToolMessage(
        id=tool_id,
        role="tool",
        requestor="assistant",
        content=content,
        error=error,
    )


def _install_mock_generate(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake_generate(**kwargs: object) -> AssistantMessage:
        calls.append(kwargs)
        return AssistantMessage.text("Grounded reply.")

    monkeypatch.setattr(v1_module, "generate", fake_generate)
    return calls


def test_extracts_all_available_variants_for_any_product_category() -> None:
    fact = extract_variant_availability_fact(
        _product_result("Coffee Maker", "coffee-1", [True, True, True])
    )

    assert fact is not None
    assert fact.product_name == "Coffee Maker"
    assert (fact.total_variants, fact.available_variants, fact.unavailable_variants) == (
        3,
        3,
        0,
    )


def test_distinguishes_total_from_available_variants() -> None:
    fact = extract_variant_availability_fact(
        _product_result("Backpack", "bag-2", [True, False, True, False, False])
    )

    assert fact is not None
    assert (fact.total_variants, fact.available_variants, fact.unavailable_variants) == (
        5,
        2,
        3,
    )


@pytest.mark.parametrize(
    "content",
    [
        _product_result("Lamp", "lamp-1", [True, None]),
        json.dumps({"name": "Lamp", "product_id": "lamp-1", "variants": {}}),
        json.dumps({"name": "Lamp", "variants": {}}),
        "not JSON",
    ],
)
def test_incomplete_or_unidentifiable_results_do_not_create_facts(content: str) -> None:
    # An empty, identified variants mapping is a valid known zero; the other
    # cases lack a required availability/identity field or are not JSON.
    fact = extract_variant_availability_fact(content)
    if content == json.dumps({"name": "Lamp", "product_id": "lamp-1", "variants": {}}):
        assert fact is not None
        assert fact.total_variants == fact.available_variants == 0
    else:
        assert fact is None


def test_v1_keeps_raw_tool_result_and_injects_only_verified_grounding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch)
    raw = _product_result("Backpack", "bag-2", [True, False, True])
    tool_message = _tool_message("product-call", raw)

    response, state = agent.generate_next_message(tool_message, state)

    assert response.content == "Grounded reply."
    assert state.messages[0] is tool_message
    assert state.messages[0].content == raw
    assert len(state.availability_facts) == 1
    messages = calls[0]["messages"]
    assert messages[-1] is tool_message
    grounding = next(message.content for message in messages if message.role == "system" and message is not state.system_messages[0])
    assert "total_variants=3" in grounding
    assert "available_variants=2" in grounding
    assert "unavailable_variants=1" in grounding


def test_v1_rebuilds_facts_from_flattened_resumable_history() -> None:
    raw = _product_result("Desk Lamp", "lamp-4", [True, False])
    tool_message = _tool_message("prior-product", raw)
    state = create_v1_agent([], "Policy", llm="mock/model").get_init_state([tool_message])

    assert state.messages == [tool_message]
    assert [
        (fact.product_name, fact.available_variants)
        for fact in state.availability_facts.values()
    ] == [
        ("Desk Lamp", 1)
    ]


def test_multi_tool_history_is_preserved_and_invalid_or_error_results_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch)
    valid = _tool_message("one", _product_result("Bicycle", "bike-1", [False, True]))
    missing_availability = _tool_message("two", _product_result("Lamp", "lamp-1", [None]))
    failed = _tool_message("three", _product_result("Bookcase", "book-1", [True]), error=True)

    _, state = agent.generate_next_message(
        MultiToolMessage(role="tool", tool_messages=[valid, missing_availability, failed]),
        state,
    )

    assert state.messages[:3] == [valid, missing_availability, failed]
    assert [fact.product_name for fact in state.availability_facts.values()] == ["Bicycle"]
    assert [message.role for message in calls[0]["messages"]] == [
        "system",
        "system",
        "tool",
        "tool",
        "tool",
    ]


def test_newer_result_replaces_old_fact_for_the_same_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_agent([], "Retail policy", llm="mock/model")
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch)
    older = _tool_message("old", _product_result("Backpack", "bag-2", [True, True, False]))
    newer = _tool_message("new", _product_result("Backpack", "bag-2", [False, False, True]))

    _, state = agent.generate_next_message(older, state)
    _, state = agent.generate_next_message(newer, state)

    assert len(state.availability_facts) == 1
    fact = state.availability_facts["bag-2"]
    assert (fact.total_variants, fact.available_variants, fact.unavailable_variants) == (
        3,
        1,
        2,
    )
    latest_grounding = next(
        message.content
        for message in calls[-1]["messages"]
        if message.role == "system" and message is not state.system_messages[0]
    )
    assert "available_variants=1" in latest_grounding
    assert "total_variants=3; available_variants=2; unavailable_variants=1." not in latest_grounding


def test_repeated_identical_result_is_deduplicated_and_different_products_are_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_agent([], "Retail policy", llm="mock/model")
    state = agent.get_init_state()
    _install_mock_generate(monkeypatch)
    backpack = _tool_message("bag-first", _product_result("Backpack", "bag-2", [True, False]))
    backpack_repeat = _tool_message("bag-repeat", _product_result("Backpack", "bag-2", [True, False]))
    coffee = _tool_message("coffee", _product_result("Coffee Maker", "coffee-1", [True, True, True]))

    _, state = agent.generate_next_message(backpack, state)
    _, state = agent.generate_next_message(backpack_repeat, state)
    _, state = agent.generate_next_message(coffee, state)

    assert list(state.availability_facts) == ["bag-2", "coffee-1"]
    assert state.availability_facts["bag-2"].available_variants == 1
    assert state.availability_facts["coffee-1"].available_variants == 3
    assert state.messages[:3] == [backpack, AssistantMessage.text("Grounded reply."), backpack_repeat]


def test_multi_tool_updates_in_message_order_and_invalid_result_preserves_old_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_agent([], "Retail policy", llm="mock/model")
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch)
    original = _tool_message("original", _product_result("Bicycle", "bike-1", [True, True]))
    invalid = _tool_message("invalid", _product_result("Bicycle", "bike-1", [True, None]))
    failed_update = _tool_message(
        "failed-update", _product_result("Bicycle", "bike-1", [False, False]), error=True
    )
    older = _tool_message("older", _product_result("Lamp", "lamp-1", [True, True]))
    newer = _tool_message("newer", _product_result("Lamp", "lamp-1", [False, True]))

    _, state = agent.generate_next_message(original, state)
    _, state = agent.generate_next_message(
        MultiToolMessage(
            role="tool", tool_messages=[invalid, failed_update, older, newer]
        ),
        state,
    )

    assert list(state.availability_facts) == ["bike-1", "lamp-1"]
    assert state.availability_facts["bike-1"].available_variants == 2
    assert state.availability_facts["lamp-1"].available_variants == 1
    grounding = next(
        message.content
        for message in calls[-1]["messages"]
        if message.role == "system" and message is not state.system_messages[0]
    )
    assert grounding.index("Bicycle") < grounding.index("Lamp")


def test_llm_context_keeps_retail_policy_and_raw_history_while_replacing_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = "Retail policy must remain present."
    agent = create_v1_agent([], policy, llm="mock/model")
    state = agent.get_init_state()
    calls = _install_mock_generate(monkeypatch)
    older = _tool_message("old", _product_result("Backpack", "bag-2", [True, True]))
    newer = _tool_message("new", _product_result("Backpack", "bag-2", [False, False]))

    _, state = agent.generate_next_message(older, state)
    _, state = agent.generate_next_message(newer, state)

    messages = calls[-1]["messages"]
    assert messages[0] is state.system_messages[0]
    assert policy in (messages[0].content or "")
    assert older in messages and newer in messages
    grounding = messages[1].content or ""
    assert "available_variants=0" in grounding
    assert "total_variants=2; available_variants=2; unavailable_variants=0." not in grounding


def test_v1_factory_registry_and_builder_are_compatible() -> None:
    name = register_v1_agent()
    assert name == V1_AGENT_NAME
    assert registry.get_agent_factory(name) is create_v1_agent

    agent = build_agent(
        name,
        get_environment(),
        llm="mock/model",
        llm_args={"temperature": 0},
    )

    assert isinstance(agent, V1Agent)
    assert agent.llm == "mock/model"
