"""V1-2 Reserve Smoke 入口的无 API 测试。"""

import json

from ecommerce_after_sales_agent import retail_v1_2_reserve_smoke
from ecommerce_after_sales_agent.registration import V1_2_RESERVE_AGENT_NAME


def test_reserve_smoke_preflight_builds_the_new_agent_with_fixed_scope() -> None:
    preflight = retail_v1_2_reserve_smoke.build_v1_2_reserve_smoke_preflight()
    config = preflight.repeat.plan.config

    assert preflight.repeat.built_agent_type == "V1_2ReserveAgent"
    assert config.agent == V1_2_RESERVE_AGENT_NAME
    assert [task.id for task in preflight.repeat.plan.tasks] == ["2"]
    assert config.num_trials == 1
    assert config.seed == 42
    assert config.effective_max_steps == 30
    assert config.llm_agent == config.llm_user == "openai/gpt-4.1-mini"
    assert config.llm_args_agent == config.llm_args_user == {"temperature": 0.0}
    assert preflight.repeat.trial_seeds == (670487,)
    assert preflight.fresh_text_budget_exact is True
    assert str(preflight.repeat.plan.output_path).endswith(
        "retail-v1-2-reserve-smoke-task2-t1/results.json"
    )


def test_reserve_smoke_only_changes_agent_and_output_from_old_v1_2_smoke() -> None:
    reserve = retail_v1_2_reserve_smoke.build_v1_2_reserve_smoke_preflight().repeat.plan.config
    from ecommerce_after_sales_agent.retail_v1_2_smoke import build_v1_2_smoke_preflight

    old = build_v1_2_smoke_preflight().repeat.plan.config
    assert reserve.model_dump(mode="json") == {
        **old.model_dump(mode="json"),
        "agent": V1_2_RESERVE_AGENT_NAME,
        "save_to": reserve.save_to,
    }


def test_reserve_smoke_default_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_v1_2_reserve_smoke,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("未传入 --run 时不得调用 run_domain")
        ),
    )

    retail_v1_2_reserve_smoke.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V1_2_RESERVE_AGENT_NAME
    assert payload["will_call_model_provider"] is False
    assert "four remaining local budget steps" in payload["step_budget"][
        "write_closure_reserve"
    ]


def test_reserve_smoke_run_flag_is_the_only_runner_path(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_v1_2_reserve_smoke, "run_domain", received.append)
    monkeypatch.setattr(retail_v1_2_reserve_smoke, "set_llm_log_mode", modes.append)

    retail_v1_2_reserve_smoke.main(["--run"])

    assert len(received) == 1
    assert received[0].agent == V1_2_RESERVE_AGENT_NAME
    assert received[0].task_ids == ["2"]
    assert received[0].num_trials == 1
    assert received[0].save_to == "retail-v1-2-reserve-smoke-task2-t1"
    assert modes == ["all"]
    assert "Agent、User 和 Judge 可能产生费用" in capsys.readouterr().out
