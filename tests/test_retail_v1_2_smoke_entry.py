"""V1-2 多 Tool Call 恢复 Smoke 入口的无 API 测试。"""

import json

from ecommerce_after_sales_agent import retail_v1_2_smoke
from ecommerce_after_sales_agent.registration import V1_2_AGENT_NAME


def test_smoke_preflight_builds_v1_2_with_the_fixed_task_and_configuration() -> None:
    preflight = retail_v1_2_smoke.build_v1_2_smoke_preflight()
    config = preflight.repeat.plan.config

    assert preflight.repeat.built_agent_type == "V1_2Agent"
    assert config.agent == V1_2_AGENT_NAME
    assert [task.id for task in preflight.repeat.plan.tasks] == ["2"]
    assert config.num_trials == 1
    assert config.seed == 42
    assert config.effective_max_steps == 30
    assert config.llm_agent == config.llm_user == "openai/gpt-4.1-mini"
    assert config.llm_args_agent == config.llm_args_user == {"temperature": 0.0}
    assert preflight.repeat.trial_seeds == (670487,)
    assert preflight.fresh_text_budget_exact is True
    assert str(preflight.repeat.plan.output_path).endswith(
        "retail-v1-2-multi-tool-recovery-smoke-task2-t1/results.json"
    )


def test_smoke_configuration_only_differs_from_v1_2_pilot_in_scope_and_output() -> None:
    smoke = retail_v1_2_smoke.build_v1_2_smoke_preflight().repeat.plan.config
    from ecommerce_after_sales_agent.retail_v1_2_pilot import build_v1_2_pilot_config

    pilot = build_v1_2_pilot_config()
    assert smoke.model_dump(mode="json") == {
        **pilot.model_dump(mode="json"),
        "task_ids": ["2"],
        "num_trials": 1,
        "save_to": smoke.save_to,
    }


def test_default_smoke_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_v1_2_smoke,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("未传入 --run 时不得调用 run_domain")
        ),
    )

    retail_v1_2_smoke.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V1_2_AGENT_NAME
    assert payload["task_ids"] == ["2"]
    assert payload["trials_per_task"] == 1
    assert payload["planned_simulations"] == 1
    assert payload["will_call_model_provider"] is False
    assert "each Environment-bound AssistantMessage has at most one Tool Call" in payload[
        "post_run_checks"
    ]


def test_smoke_run_flag_is_the_only_path_that_invokes_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_v1_2_smoke, "run_domain", received.append)
    monkeypatch.setattr(retail_v1_2_smoke, "set_llm_log_mode", modes.append)

    retail_v1_2_smoke.main(["--run"])

    assert len(received) == 1
    assert received[0].agent == V1_2_AGENT_NAME
    assert received[0].task_ids == ["2"]
    assert received[0].num_trials == 1
    assert received[0].save_to == "retail-v1-2-multi-tool-recovery-smoke-task2-t1"
    assert modes == ["all"]
    assert "Agent、User 和 Judge 可能产生费用" in capsys.readouterr().out
