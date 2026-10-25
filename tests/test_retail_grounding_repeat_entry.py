"""修复后 Tasks 2–4 Grounding 重复实验的无 API 测试。"""

import json

from ecommerce_after_sales_agent import retail_grounding_repeat
from ecommerce_after_sales_agent.registration import V0_AGENT_NAME, V1_AGENT_NAME


def test_grounding_preflight_builds_expected_agents_tasks_seeds_and_paths() -> None:
    v0 = retail_grounding_repeat.build_grounding_repeat_preflight("v0")
    v1 = retail_grounding_repeat.build_grounding_repeat_preflight("v1")

    assert v0.built_agent_type == "V0Agent"
    assert v1.built_agent_type == "V1Agent"
    assert [task.id for task in v0.plan.tasks] == ["2", "3", "4"]
    assert [task.id for task in v1.plan.tasks] == ["2", "3", "4"]
    assert v0.plan.config.num_trials == v1.plan.config.num_trials == 3
    assert v0.trial_seeds == v1.trial_seeds == (670487, 116739, 26225)
    assert str(v0.plan.output_path).endswith(
        "retail-v0-seed-protocol-fixed-grounding-repeat-2-4-t3/results.json"
    )
    assert str(v1.plan.output_path).endswith(
        "retail-v1-seed-protocol-fixed-grounding-repeat-2-4-t3/results.json"
    )


def test_grounding_configs_differ_only_by_agent_and_save_directory() -> None:
    v0 = retail_grounding_repeat.build_grounding_repeat_config("v0")
    v1 = retail_grounding_repeat.build_grounding_repeat_config("v1")

    assert v0.agent == V0_AGENT_NAME
    assert v1.agent == V1_AGENT_NAME
    assert v0.model_dump(mode="json") == {
        **v1.model_dump(mode="json"),
        "agent": V0_AGENT_NAME,
        "save_to": v0.save_to,
    }
    assert v0.task_ids == v1.task_ids == ["2", "3", "4"]
    assert v0.llm_args_agent == v1.llm_args_agent == {"temperature": 0.0}
    assert v0.llm_args_user == v1.llm_args_user == {"temperature": 0.0}


def test_default_grounding_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_grounding_repeat,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("未传入 --run 时不得调用 run_domain")
        ),
    )

    retail_grounding_repeat.main(["--agent-version", "v1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V1_AGENT_NAME
    assert payload["built_agent_type"] == "V1Agent"
    assert payload["task_ids"] == ["2", "3", "4"]
    assert payload["trials_per_task"] == 3
    assert payload["planned_simulations"] == 9
    assert payload["trial_seeds"] == [670487, 116739, 26225]
    assert payload["will_call_model_provider"] is False
    assert payload["experiment_focus"] == "availability-grounding-stability"


def test_grounding_run_flag_is_the_only_path_that_invokes_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_grounding_repeat, "run_domain", received.append)
    monkeypatch.setattr(retail_grounding_repeat, "set_llm_log_mode", modes.append)

    retail_grounding_repeat.main(["--agent-version", "v0", "--run"])

    assert len(received) == 1
    assert received[0].agent == V0_AGENT_NAME
    assert received[0].task_ids == ["2", "3", "4"]
    assert received[0].num_trials == 3
    assert received[0].save_to == "retail-v0-seed-protocol-fixed-grounding-repeat-2-4-t3"
    assert modes == ["all"]
    assert "Agent、User 和 Judge 可能产生费用" in capsys.readouterr().out
