"""V1-2 write 收尾预算保护的无 API 回归测试。"""

import json
import time
from types import SimpleNamespace

import pytest
from tau2.data_model.message import AssistantMessage, ToolCall, ToolMessage, UserMessage
from tau2.domains.retail.environment import get_environment
from tau2.environment.toolkit import MUTATES_STATE_ATTR
from tau2.orchestrator.orchestrator import Orchestrator, Role
from tau2.runner.build import build_agent
from tau2.data_model.simulation import TerminationReason

from ecommerce_after_sales_agent.registration import register_v1_2_reserve_agent
from ecommerce_after_sales_agent.v1_2_reserve_agent import (
    V1_2ReserveAgent,
    create_v1_2_reserve_agent,
)
import ecommerce_after_sales_agent.v1_2_reserve_agent as reserve_module


def _opening() -> AssistantMessage:
    return AssistantMessage.text("Hi! How can I help you today?")


def _tool_message(tool_id: str, content: str = "result") -> ToolMessage:
    return ToolMessage(
        id=tool_id, role="tool", requestor="assistant", content=content
    )


def _tool(name: str, *, mutates_state: bool) -> SimpleNamespace:
    def function() -> None:
        return None

    setattr(function, MUTATES_STATE_ATTR, mutates_state)
    return SimpleNamespace(name=name, _func=function)


def _install_generate(
    monkeypatch: pytest.MonkeyPatch, responses: list[AssistantMessage]
) -> list[dict]:
    calls: list[dict] = []
    response_iter = iter(responses)

    def fake_generate(**kwargs: object) -> AssistantMessage:
        calls.append(kwargs)
        return next(response_iter)

    monkeypatch.setattr(reserve_module, "generate", fake_generate)
    return calls


def _budget_context(call: dict) -> str:
    return next(
        message.content
        for message in call["messages"]
        if message.role == "system" and "<step_budget>" in (message.content or "")
    )


def test_write_at_or_below_closure_reserve_is_not_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_reserve_agent(
        [_tool("change_record", mutates_state=True)],
        "Policy",
        llm="mock/model",
        max_steps=4,
    )
    state = agent.get_init_state([_opening()])
    draft = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="change", name="change_record", arguments={})],
        cost=0.25,
        usage={"prompt_tokens": 8, "completion_tokens": 2},
    )
    calls = _install_generate(monkeypatch, [draft])

    response, state = agent.generate_next_message(UserMessage.text("Confirmed"), state)

    assert state.estimated_steps_used == 2
    assert response.tool_calls is None
    assert "have not submitted" in (response.content or "")
    assert response.cost == pytest.approx(0.25)
    assert response.usage == {"prompt_tokens": 8, "completion_tokens": 2}
    assert draft not in state.messages
    assert state.messages[-1] is response
    assert "four remaining budget steps" in _budget_context(calls[0])


def test_write_with_minimum_closure_reserve_is_kept_after_policy_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_reserve_agent(
        [_tool("change_record", mutates_state=True)],
        "Policy",
        llm="mock/model",
        max_steps=6,
    )
    state = agent.get_init_state([_opening()])
    draft = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="change", name="change_record", arguments={})],
    )
    calls = _install_generate(monkeypatch, [draft])

    response, state = agent.generate_next_message(UserMessage.text("Confirmed"), state)

    assert state.estimated_steps_used == 2
    assert response is draft
    assert response.tool_calls == [ToolCall(id="change", name="change_record", arguments={})]
    context = _budget_context(calls[0])
    assert "authentication, required business validation" in context
    assert "explicit user confirmation" in context


@pytest.mark.parametrize(
    ("remaining", "permitted"),
    [(3, False), (4, True), (5, True)],
)
def test_write_closure_boundary_requires_four_remaining_steps(
    remaining: int, permitted: bool
) -> None:
    """四步预留来自 Harness cutoff 边界，而不是任意常数。"""
    state = create_v1_2_reserve_agent(
        [], "Policy", llm="mock/model", max_steps=30
    ).get_init_state([_opening()])
    state.estimated_steps_used = state.max_steps - remaining

    assert V1_2ReserveAgent._has_write_completion_reserve(state) is permitted


def test_unknown_or_resumed_budget_never_submits_a_mutating_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_reserve_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state([UserMessage.text("Resumed request")])
    draft = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="unknown", name="unknown_change", arguments={})],
    )
    _install_generate(monkeypatch, [draft])

    response, _ = agent.generate_next_message(UserMessage.text("Confirmed"), state)

    assert state.exact_budget is False
    assert response.tool_calls is None
    assert "have not submitted" in (response.content or "")


def test_old_task_two_terminal_write_position_is_blocked_without_claiming_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """复现旧 Task 2 最后 write decision 的本地预算位置，不复制任务数据。"""
    agent = create_v1_2_reserve_agent(
        [_tool("change_record", mutates_state=True)],
        "Policy",
        llm="mock/model",
        max_steps=30,
    )
    state = agent.get_init_state([_opening()])
    # 旧失败轨迹的最后决策为第 15 次 Agent decision；本次输入会使估计到 30。
    state.decision_count = 14
    state.estimated_steps_used = 28
    draft = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="late-change", name="change_record", arguments={})],
    )
    _install_generate(monkeypatch, [draft])

    response, state = agent.generate_next_message(UserMessage.text("Proceed"), state)

    assert state.estimated_steps_used == 30
    assert response.tool_calls is None
    assert "have not submitted" in (response.content or "")
    assert "###STOP###" not in (response.content or "")


def test_read_tool_remains_available_when_write_reserve_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_reserve_agent(
        [_tool("read_record", mutates_state=False)],
        "Policy",
        llm="mock/model",
        max_steps=4,
    )
    state = agent.get_init_state([_opening()])
    read = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="read", name="read_record", arguments={})],
    )
    _install_generate(monkeypatch, [read])

    response, _ = agent.generate_next_message(UserMessage.text("Find it"), state)

    assert response is read
    assert response.tool_calls == [ToolCall(id="read", name="read_record", arguments={})]


def test_retail_tool_mutation_classification_uses_official_metadata() -> None:
    """真实 Retail Tool 的 mutation 判断来自官方 decorator 元数据。"""
    tools = get_environment().get_tools()
    agent = create_v1_2_reserve_agent(tools, "Policy", llm="mock/model")
    expected = {
        tool.name: bool(getattr(getattr(tool, "_func", None), MUTATES_STATE_ATTR, True))
        for tool in tools
    }
    actual = {name: agent._is_mutating_tool(name) for name in expected}

    assert actual == expected
    assert any(actual.values())
    assert any(not value for value in actual.values())


def test_candidate_orders_strengthen_reuse_hint_without_exposing_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_reserve_agent([], "Policy", llm="mock/model")
    state = agent.get_init_state([_opening()])
    calls = _install_generate(monkeypatch, [AssistantMessage.text("Continue")])
    profile = _tool_message(
        "profile", json.dumps({"orders": ["order-alpha", "order-beta"]})
    )

    _, state = agent.generate_next_message(profile, state)

    assert state.candidate_order_count == 2
    context = _budget_context(calls[0])
    assert "do not ask the user to repeat those identifiers" in context
    assert "order-alpha" not in context and "order-beta" not in context


def test_tool_result_can_be_followed_by_truthful_completion_with_reserved_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = create_v1_2_reserve_agent([], "Policy", llm="mock/model", max_steps=5)
    state = agent.get_init_state([_opening()])
    calls = _install_generate(monkeypatch, [AssistantMessage.text("The change completed.")])

    response, state = agent.generate_next_message(_tool_message("change-result"), state)

    assert state.estimated_steps_used == 2
    assert response.tool_calls is None
    assert response.content == "The change completed."
    assert "estimated_remaining_steps=3" in _budget_context(calls[0])


def test_minimum_reserve_covers_write_result_and_normal_user_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """以官方半双工转移验证剩余三步是写入收尾的最小路径。"""

    class FakeUser:
        def __init__(self) -> None:
            self.responses = iter(
                [UserMessage.text("Confirmed"), UserMessage.text("###STOP###")]
            )

        def generate_next_message(
            self, _message: object, state: object
        ) -> tuple[UserMessage, object]:
            return next(self.responses), state

    class FakeEnvironment:
        def __init__(self) -> None:
            self.executed = 0

        def get_response(self, call: ToolCall) -> ToolMessage:
            self.executed += 1
            return _tool_message(call.id, "write completed")

        def sync_tools(self) -> None:
            pass

    write_tool = _tool("change_record", mutates_state=True)
    agent = create_v1_2_reserve_agent(
        [write_tool], "Policy", llm="mock/model", max_steps=6
    )
    state = agent.get_init_state([_opening()])
    write = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="change", name="change_record", arguments={})],
    )
    _install_generate(monkeypatch, [write, AssistantMessage.text("Completed.")])
    opening = _opening()
    environment = FakeEnvironment()
    orchestrator = object.__new__(Orchestrator)
    orchestrator.done = False
    orchestrator.step_count = 0
    orchestrator.num_errors = 0
    orchestrator.max_steps = 6
    orchestrator.max_errors = 10
    orchestrator.timeout = None
    orchestrator._run_start_perf = time.perf_counter()
    orchestrator.from_role = Role.AGENT
    orchestrator.to_role = Role.USER
    orchestrator.solo_mode = False
    orchestrator.validate_communication = False
    orchestrator.agent = agent
    orchestrator.agent_state = state
    orchestrator.user = FakeUser()
    orchestrator.user_state = object()
    orchestrator.environment = environment
    orchestrator.message = opening
    orchestrator.trajectory = [opening]

    for _ in range(5):
        Orchestrator._check_termination(orchestrator)
        if orchestrator.done:
            break
        Orchestrator.step(orchestrator)
        if orchestrator.done:
            break

    assert environment.executed == 1
    assert orchestrator.step_count == 5
    assert orchestrator.termination_reason is TerminationReason.USER_STOP


def test_grounding_seed_and_single_tool_recovery_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_tool = _tool("read_record", mutates_state=False)
    agent = create_v1_2_reserve_agent(
        [read_tool], "Policy", llm="mock/model", llm_args={"temperature": 0.0}
    )
    state = agent.get_init_state([_opening()])
    agent.set_seed(314159)
    first = AssistantMessage(
        role="assistant",
        tool_calls=[
            ToolCall(id="first", name="read_record", arguments={}),
            ToolCall(id="second", name="read_record", arguments={}),
        ],
    )
    second = AssistantMessage(
        role="assistant",
        tool_calls=[ToolCall(id="good", name="read_record", arguments={})],
    )
    calls = _install_generate(monkeypatch, [first, second])
    product = _tool_message(
        "product",
        json.dumps(
            {
                "name": "Generic Product",
                "product_id": "product-1",
                "variants": {"a": {"available": True}},
            }
        ),
    )

    response, state = agent.generate_next_message(product, state)

    assert response.tool_calls == [ToolCall(id="good", name="read_record", arguments={})]
    assert len(calls) == 2
    assert all(call["seed"] == 314159 for call in calls)
    assert all(call["temperature"] == 0.0 for call in calls)
    assert all(call["parallel_tool_calls"] is False for call in calls)
    assert state.availability_facts["product-1"].available_variants == 1


def test_reserve_factory_registers_without_mixing_max_steps_into_llm_args() -> None:
    name = "test_ecommerce_after_sales_v1_2_reserve_19"
    register_v1_2_reserve_agent(max_steps=19, name=name)

    agent = build_agent(
        name, get_environment(), llm="mock/model", llm_args={"temperature": 0.0}
    )

    assert isinstance(agent, V1_2ReserveAgent)
    assert agent.max_steps == 19
    assert agent.llm_args == {"temperature": 0.0}
