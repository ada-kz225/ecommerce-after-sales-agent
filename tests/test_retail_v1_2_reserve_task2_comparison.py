"""V1-2/Reserve Task 2 对照入口的无 API 测试。"""

import json

from ecommerce_after_sales_agent import retail_v1_2_reserve_task2_comparison as comparison
from ecommerce_after_sales_agent.registration import (
    V1_2_AGENT_NAME,
    V1_2_RESERVE_AGENT_NAME,
)


def test_task2_comparison_preflight_builds_both_current_agents() -> None:
    control = comparison.build_task2_comparison_preflight("v1_2")
    reserve = comparison.build_task2_comparison_preflight("reserve")

    assert control.repeat.built_agent_type == "V1_2Agent"
    assert reserve.repeat.built_agent_type == "V1_2ReserveAgent"
    assert control.repeat.plan.config.agent == V1_2_AGENT_NAME
    assert reserve.repeat.plan.config.agent == V1_2_RESERVE_AGENT_NAME
    assert control.repeat.plan.config.task_ids == reserve.repeat.plan.config.task_ids == ["2"]
    assert control.repeat.plan.config.num_trials == reserve.repeat.plan.config.num_trials == 3
    assert control.repeat.trial_seeds == reserve.repeat.trial_seeds == (
        670487,
        116739,
        26225,
    )


def test_task2_comparison_configs_only_differ_by_agent_and_output_path() -> None:
    control = comparison.build_task2_comparison_preflight("v1_2")
    reserve = comparison.build_task2_comparison_preflight("reserve")
    control_config = control.repeat.plan.config.model_dump(mode="json")
    reserve_config = reserve.repeat.plan.config.model_dump(mode="json")

    assert {
        key: value
        for key, value in control_config.items()
        if key not in {"agent", "save_to"}
    } == {
        key: value
        for key, value in reserve_config.items()
        if key not in {"agent", "save_to"}
    }
    assert control_config["save_to"] != reserve_config["save_to"]


def test_default_comparison_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        comparison,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("未传入 --run 时不得调用 run_domain")
        ),
    )

    comparison.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["will_call_model_provider"] is False
    assert payload["configs_match_except_agent_and_save_to"] is True
    assert payload["planned_simulations"] == 6
    assert payload["guard_event_diagnostic"]["structured_event_available"] is False


def test_run_flag_only_runs_selected_variant(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(comparison, "run_domain", received.append)
    monkeypatch.setattr(comparison, "set_llm_log_mode", modes.append)

    comparison.main(["--variant", "reserve", "--run"])

    assert len(received) == 1
    assert received[0].agent == V1_2_RESERVE_AGENT_NAME
    assert received[0].task_ids == ["2"]
    assert received[0].num_trials == 3
    assert received[0].save_to == comparison.RESERVE_SAVE_TO
    assert modes == ["all"]
    assert "Agent、User 和 Judge 可能产生费用" in capsys.readouterr().out
