"""合规 V1-1/V1-2 对照入口的无 API 测试。"""

import json

from ecommerce_after_sales_agent import retail_v1_1_v1_2_comparison
from ecommerce_after_sales_agent.registration import (
    V1_1_COMPLIANT_AGENT_NAME,
    V1_2_AGENT_NAME,
)


def test_comparison_preflight_builds_both_expected_agent_types() -> None:
    v1_1 = retail_v1_1_v1_2_comparison.build_comparison_preflight("v1_1")
    v1_2 = retail_v1_1_v1_2_comparison.build_comparison_preflight("v1_2")

    assert v1_1.built_agent_type == "V1_1CompliantAgent"
    assert v1_2.built_agent_type == "V1_2Agent"
    assert [task.id for task in v1_1.plan.tasks] == ["2", "3", "4"]
    assert [task.id for task in v1_2.plan.tasks] == ["2", "3", "4"]
    assert v1_1.trial_seeds == v1_2.trial_seeds == (670487, 116739, 26225)


def test_comparison_configs_differ_only_by_agent_and_output_directory() -> None:
    v1_1 = retail_v1_1_v1_2_comparison.build_comparison_config("v1_1")
    v1_2 = retail_v1_1_v1_2_comparison.build_comparison_config("v1_2")

    assert v1_1.agent == V1_1_COMPLIANT_AGENT_NAME
    assert v1_2.agent == V1_2_AGENT_NAME
    assert v1_1.model_dump(mode="json") == {
        **v1_2.model_dump(mode="json"),
        "agent": V1_1_COMPLIANT_AGENT_NAME,
        "save_to": v1_1.save_to,
    }


def test_default_comparison_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_v1_1_v1_2_comparison,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("未传入 --run 时不得调用 run_domain")
        ),
    )
    retail_v1_1_v1_2_comparison.main(["--agent-version", "v1_1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["registered_agent"] == V1_1_COMPLIANT_AGENT_NAME
    assert payload["built_agent_type"] == "V1_1CompliantAgent"
    assert payload["planned_simulations"] == 9
    assert payload["will_call_model_provider"] is False


def test_run_flag_is_the_only_path_that_invokes_comparison_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_v1_1_v1_2_comparison, "run_domain", received.append)
    monkeypatch.setattr(retail_v1_1_v1_2_comparison, "set_llm_log_mode", modes.append)

    retail_v1_1_v1_2_comparison.main(["--agent-version", "v1_2", "--run"])

    assert len(received) == 1
    assert received[0].agent == V1_2_AGENT_NAME
    assert received[0].task_ids == ["2", "3", "4"]
    assert received[0].num_trials == 3
    assert modes == ["all"]
    assert "Agent、User 和 Judge 可能产生费用" in capsys.readouterr().out
