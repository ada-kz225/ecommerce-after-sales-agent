"""V1-2 Step Budget 的无 API 回归测试。"""

import json
import time

import pytest
from tau2.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.domains.retail.environment import get_environment
from tau2.orchestrator.orchestrator import Orchestrator, Role
from tau2.data_model.simulation import TerminationReason
from tau2.runner.build import build_agent

from ecommerce_after_sales_agent.registration import register_v1_2_agent
from ecommerce_after_sales_agent.v1_2_agent import (
    MultipleToolCallsError,
    V1_2Agent,
    create_v1_2_agent,
)
import ecommerce_after_sales_agent.v1_2_agent as v1_2_module


def _opening() -> AssistantMessage:
    return AssistantMessage.text("Hi! How can I help you today?")


def _tool_message(tool_id: str, content: str = "result") -> ToolMessage:
    return ToolMessage(
        id=tool_id, role="tool", requestor="assistant", content=content
    )


def _install_mock_generate(
    monkeypatch: pytest.MonkeyPatch, response: AssistantMessage | None = None
) -> list[dict]:
    calls: list[dict] = []

    def fake_generate(**kwargs: object) -> AssistantMessage:
        calls.append(kwargs)
        return response or AssistantMessage.text("Mock reply")

    monkeypatch.setattr(v1_2_module, "generate", fake_generate)
    return calls


def _budget_context(call: dict) -> str:
    return next(
        message.content
        for message in call["messages"]
        if message.role == "system" and "<step_budget>" in (message.content or "")
    )


def test_fresh_text_budget_matches_two_transfers_per_agent_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model", max_steps=30)
    state = agent.get_init_state([_opening()])
    calls = _install_mock_generate(monkeypatch)

    _, state = agent.generate_next_message(UserMessage.text("First request"), state)
    _, state = agent.generate_next_message(UserMessage.text("Second request"), state)

    assert state.exact_budget is True
    assert state.decision_count == 2
    assert state.estimated_steps_used == 4
    assert "estimated_steps_used=2" in _budget_context(calls[0])
    assert "estimated_remaining_steps=28" in _budget_context(calls[0])
    assert "estimated_steps_used=4" in _budget_context(calls[1])


def test_local_budget_matches_official_mock_orchestrator_step_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不经 Runner 或 API，验证两次 Agent 决策后的官方计数与本地估计一致。"""

    class FakeUser:
        def generate_next_message(self, _message: object, _state: object) -> tuple[UserMessage, object]:
            return UserMessage.text("Continue"), _state

    class FakeEnvironment:
        def sync_tools(self) -> None:
            pass

    agent = create_v1_2_agent([], "Policy", llm="mock/model")
    _install_mock_generate(monkeypatch)
    opening = _opening()
    orchestrator = object.__new__(Orchestrator)
    orchestrator.done = False
    orchestrator.step_count = 0
    orchestrator.num_errors = 0
    orchestrator.from_role = Role.AGENT
    orchestrator.to_role = Role.USER
    orchestrator.solo_mode = False
    orchestrator.validate_communication = False
    orchestrator.agent = agent
    orchestrator.agent_state = agent.get_init_state([opening])
    orchestrator.user = FakeUser()
    orchestrator.user_state = object()
    orchestrator.environment = FakeEnvironment()
    orchestrator.message = opening
    orchestrator.trajectory = [opening]

    for _ in range(4):
        Orchestrator.step(orchestrator)

    assert orchestrator.step_count == 4
    assert orchestrator.agent_state.estimated_steps_used == 4
    assert orchestrator.agent_state.decision_count == 2


def test_environment_result_at_cap_is_saved_without_a_followup_agent_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证官方的 ENV 豁免检查边界，而不调用任何真实 Tool 或 LLM。"""

    class FakeUser:
        def generate_next_message(self, _message: object, _state: object) -> tuple[UserMessage, object]:
            return UserMessage.text("Need help"), _state

    class FakeEnvironment:
        def __init__(self) -> None:
            self.executed = 0

        def get_response(self, call: ToolCall) -> ToolMessage:
            self.executed += 1
            return ToolMessage(
                id=call.id, role="tool", requestor="assistant", content="result"
            )

        def sync_tools(self) -> None:
            pass

    tool_response = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="only", name="read", arguments={})],
    )
    agent = create_v1_2_agent([], "Policy", llm="mock/model", max_steps=3)
    _install_mock_generate(monkeypatch, tool_response)
    opening = _opening()
    orchestrator = object.__new__(Orchestrator)
    orchestrator.done = False
    orchestrator.step_count = 0
    orchestrator.num_errors = 0
    orchestrator.max_steps = 3
    orchestrator.max_errors = 10
    orchestrator.timeout = None
    orchestrator._run_start_perf = time.perf_counter()
    orchestrator.from_role = Role.AGENT
    orchestrator.to_role = Role.USER
    orchestrator.solo_mode = False
    orchestrator.validate_communication = False
    orchestrator.agent = agent
    orchestrator.agent_state = agent.get_init_state([opening])
    orchestrator.user = FakeUser()
    orchestrator.user_state = object()
    environment = FakeEnvironment()
    orchestrator.environment = environment
    orchestrator.message = opening
    orchestrator.trajectory = [opening]

    Orchestrator.step(orchestrator)  # 0: AGENT -> USER
    Orchestrator._check_termination(orchestrator)
    Orchestrator.step(orchestrator)  # 1: USER -> AGENT，产生单 Tool Call
    Orchestrator._check_termination(orchestrator)  # 下一站 ENV，官方跳过 cap 检查
    assert orchestrator.done is False
    Orchestrator.step(orchestrator)  # 2: AGENT -> ENV，Tool 已执行
    Orchestrator._check_termination(orchestrator)

    assert environment.executed == 1
    assert orchestrator.step_count == 3
    assert orchestrator.done is True
    assert orchestrator.termination_reason is TerminationReason.MAX_STEPS
    assert orchestrator.agent_state.decision_count == 1
    assert any(isinstance(message, ToolMessage) for message in orchestrator.trajectory)


def test_low_budget_context_exposes_environment_result_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model", max_steps=6)
    state = agent.get_init_state([_opening()])
    calls = _install_mock_generate(monkeypatch)

    for content in ("one", "two", "three"):
        _, state = agent.generate_next_message(UserMessage.text(content), state)

    assert state.estimated_steps_used == 6
    context = _budget_context(calls[-1])
    assert "estimated_remaining_steps=0" in context
    assert "Budget is low" in context
    # 在此时发出的 Tool Call 即使由 Environment 执行，也不能保证回到下一次 Agent 决策。
    assert "Preserve enough turns" in context


def test_resume_or_unreconstructable_history_downgrades_to_conservative_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model", max_steps=30)
    state = agent.get_init_state([UserMessage.text("Resumed request")])
    calls = _install_mock_generate(monkeypatch)

    _, state = agent.generate_next_message(UserMessage.text("Continue"), state)

    assert state.exact_budget is False
    assert state.estimated_steps_used is None
    assert "cannot be reconstructed exactly" in _budget_context(calls[0])


def test_multi_tool_input_counts_once_and_keeps_official_flattened_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state([_opening()])
    _install_mock_generate(monkeypatch)
    multi = MultiToolMessage(
        role="tool", tool_messages=[_tool_message("one"), _tool_message("two")]
    )

    _, state = agent.generate_next_message(multi, state)

    assert state.decision_count == 1
    assert state.estimated_steps_used == 2
    assert [message.id for message in state.messages if isinstance(message, ToolMessage)] == [
        "one",
        "two",
    ]


def test_repeated_input_does_not_duplicate_budget_or_raw_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state([_opening()])
    _install_mock_generate(monkeypatch)
    result = _tool_message("stable-id")

    _, state = agent.generate_next_message(result, state)
    _, state = agent.generate_next_message(result, state)

    assert state.decision_count == 1
    assert state.estimated_steps_used == 2
    assert [message for message in state.messages if isinstance(message, ToolMessage)] == [result]


def test_candidate_orders_produce_general_single_read_planning_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state([_opening()])
    calls = _install_mock_generate(monkeypatch)
    profile = _tool_message(
        "profile", json.dumps({"orders": ["order-alpha-id", "order-beta-id"]})
    )

    _, state = agent.generate_next_message(profile, state)

    assert state.candidate_order_count == 2
    context = _budget_context(calls[0])
    assert "candidate order identifiers" in context
    assert "one necessary read at a time" in context
    assert "order-alpha-id" not in context and "order-beta-id" not in context


def test_unconfirmed_write_is_not_created_by_budget_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model", max_steps=4)
    state = agent.get_init_state([_opening()])
    calls = _install_mock_generate(monkeypatch, AssistantMessage.text("Need confirmation."))

    response, state = agent.generate_next_message(UserMessage.text("Please change it"), state)

    assert response.tool_calls is None
    assert "explicit user confirmation before any write" in _budget_context(calls[0])
    assert not any(isinstance(message, ToolMessage) for message in state.messages)


def test_multi_tool_llm_response_is_explicitly_rejected_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state([_opening()])
    response = AssistantMessage(
        role="assistant",
        tool_calls=[
            ToolCall(id="a", name="read_a", arguments={}),
            ToolCall(id="b", name="read_b", arguments={}),
        ],
    )
    _install_mock_generate(monkeypatch, response)

    with pytest.raises(MultipleToolCallsError, match="at most one Tool Call"):
        agent.generate_next_message(UserMessage.text("Read orders"), state)

    assert response not in state.messages
    assert not any(isinstance(message, ToolMessage) for message in state.messages)


def test_v1_grounding_and_seed_are_preserved_in_budget_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_agent(
        [], "Policy", llm="mock/model", llm_args={"temperature": 0.0}
    )
    state = agent.get_init_state([_opening()])
    calls = _install_mock_generate(monkeypatch)
    agent.set_seed(271828)
    product = _tool_message(
        "product",
        json.dumps(
            {
                "name": "Generic Product",
                "product_id": "product-1",
                "variants": {
                    "a": {"available": True},
                    "b": {"available": False},
                },
            }
        ),
    )

    _, state = agent.generate_next_message(product, state)

    assert calls[0]["seed"] == 271828
    assert calls[0]["temperature"] == 0.0
    assert state.availability_facts["product-1"].available_variants == 1
    assert any(
        "<verified_inventory_facts>" in (message.content or "")
        for message in calls[0]["messages"]
        if message.role == "system"
    )


def test_registration_injects_max_steps_without_putting_it_in_llm_args() -> None:
    name = "test_ecommerce_after_sales_v1_2_budget_17"
    register_v1_2_agent(max_steps=17, name=name)

    agent = build_agent(
        name,
        get_environment(),
        llm="mock/model",
        llm_args={"temperature": 0.0},
    )

    assert isinstance(agent, V1_2Agent)
    assert agent.max_steps == 17
    assert agent.llm_args == {"temperature": 0.0}
