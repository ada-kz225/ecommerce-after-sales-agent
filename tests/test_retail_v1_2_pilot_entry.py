"""V1-2 Step-budget Retail Pilot 入口的无 API 测试。"""

import json

from tau2.data_model.message import AssistantMessage, ToolMessage, UserMessage
from ecommerce_after_sales_agent import retail_v1_2_pilot
from ecommerce_after_sales_agent.registration import V1_2_AGENT_NAME
import ecommerce_after_sales_agent.v1_2_agent as v1_2_module


def test_v1_2_preflight_builds_runner_compatible_agent_and_exact_budget() -> None:
    preflight = retail_v1_2_pilot.build_v1_2_pilot_preflight()

    assert preflight.repeat.built_agent_type == "V1_2Agent"
    assert [task.id for task in preflight.repeat.plan.tasks] == ["2", "3", "4"]
    assert preflight.repeat.plan.config.agent == V1_2_AGENT_NAME
    assert preflight.repeat.plan.config.effective_max_steps == 30
    assert preflight.repeat.plan.config.llm_args_agent == {"temperature": 0.0}
    assert preflight.fresh_text_budget_exact is True
    assert preflight.initialized_step_count == 0
    assert preflight.repeat.trial_seeds == (670487, 116739, 26225)
    assert str(preflight.repeat.plan.output_path).endswith(
        "retail-v1-2-seed-protocol-fixed-step-budget-repeat-2-4-t3/results.json"
    )


def test_v1_and_v1_2_configs_differ_only_by_agent_and_save_directory() -> None:
    v1 = retail_v1_2_pilot.build_repeat_config(
        "v1",
        task_ids=retail_v1_2_pilot.V1_2_TASK_IDS,
        save_to="retail-v1-seed-protocol-fixed-grounding-repeat-2-4-t3",
    )
    v1_2 = retail_v1_2_pilot.build_v1_2_pilot_config()

    assert v1_2.model_dump(mode="json") == {
        **v1.model_dump(mode="json"),
        "agent": V1_2_AGENT_NAME,
        "save_to": v1_2.save_to,
    }


def test_v1_2_budget_context_reaches_generate_without_removing_grounding_or_llm_args(
    monkeypatch,
) -> None:
    preflight = retail_v1_2_pilot.build_v1_2_pilot_preflight()
    config = preflight.repeat.plan.config
    from tau2.domains.retail.environment import get_environment
    from tau2.runner.build import build_agent

    agent = build_agent(
        config.agent,
        get_environment(),
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    state = agent.get_init_state([AssistantMessage.text("Hello")])
    captured: list[dict] = []

    def fake_generate(**kwargs):
        captured.append(kwargs)
        return AssistantMessage.text("Mock reply")

    monkeypatch.setattr(v1_2_module, "generate", fake_generate)
    agent.set_seed(670487)
    product_result = ToolMessage(
        id="product-result",
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
    agent.generate_next_message(product_result, state)

    system_messages = [
        message.content or ""
        for message in captured[0]["messages"]
        if message.role == "system"
    ]
    assert any("<step_budget>" in message for message in system_messages)
    assert any("<verified_inventory_facts>" in message for message in system_messages)
    assert any("Retail" in message or "policy" in message.lower() for message in system_messages)
    assert captured[0]["temperature"] == 0.0
    assert captured[0]["seed"] == 670487


def test_default_v1_2_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_v1_2_pilot,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("未传入 --run 时不得调用 run_domain")
        ),
    )

    retail_v1_2_pilot.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V1_2_AGENT_NAME
    assert payload["built_agent_type"] == "V1_2Agent"
    assert payload["task_ids"] == ["2", "3", "4"]
    assert payload["will_call_model_provider"] is False
    assert payload["step_budget"]["fresh_text_initialization_verified"] is True


def test_run_flag_is_the_only_path_that_invokes_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_v1_2_pilot, "run_domain", received.append)
    monkeypatch.setattr(retail_v1_2_pilot, "set_llm_log_mode", modes.append)

    retail_v1_2_pilot.main(["--run"])

    assert len(received) == 1
    assert received[0].agent == V1_2_AGENT_NAME
    assert received[0].task_ids == ["2", "3", "4"]
    assert received[0].num_trials == 3
    assert received[0].save_to == "retail-v1-2-seed-protocol-fixed-step-budget-repeat-2-4-t3"
    assert modes == ["all"]
    assert "Agent、User 和 Judge 可能产生费用" in capsys.readouterr().out
