"""No-API tests for the explicitly gated V0 Retail 0--4 Pilot entry."""

import json

from tau2.registry import registry

from ecommerce_after_sales_agent import retail_pilot
from ecommerce_after_sales_agent.registration import V0_AGENT_NAME


def test_preflight_resolves_fixed_v0_retail_pilot_config() -> None:
    plan = retail_pilot.build_pilot_plan()
    config = plan.config

    assert registry.get_agent_factory(V0_AGENT_NAME) is not None
    assert [task.id for task in plan.tasks] == ["0", "1", "2", "3", "4"]
    assert config.domain == "retail"
    assert config.task_split_name == "base"
    assert config.agent == V0_AGENT_NAME
    assert config.llm_agent == config.llm_user == "openai/gpt-4.1-mini"
    assert config.llm_args_agent == config.llm_args_user == {"temperature": 0.0}
    assert config.num_trials == 1
    assert config.max_steps == 30
    assert config.max_errors == 10
    assert config.max_concurrency == 1
    assert config.workers == 0
    assert config.max_retries == 0
    assert config.seed == 42
    assert config.verbose_logs is True
    assert config.auto_review is False
    assert config.save_to == "retail-v0-pilot-0-4"
    assert str(plan.output_path).endswith(
        "data/simulations/retail-v0-pilot-0-4/results.json"
    )


def test_default_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_pilot,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("run_domain must not run without --run")
        ),
    )

    retail_pilot.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["task_ids"] == ["0", "1", "2", "3", "4"]
    assert payload["registered_agent"] == V0_AGENT_NAME
    assert payload["judge"]["type"] == "communicate_scoring semantic"
    assert payload["will_call_model_provider"] is False


def test_run_flag_is_the_only_path_that_invokes_official_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_pilot, "run_domain", lambda config: received.append(config))
    monkeypatch.setattr(retail_pilot, "set_llm_log_mode", modes.append)

    retail_pilot.main(["--run"])

    assert len(received) == 1
    assert received[0].agent == V0_AGENT_NAME
    assert received[0].task_ids == ["0", "1", "2", "3", "4"]
    assert modes == ["all"]
    assert "Agent, User, and Judge charges may apply" in capsys.readouterr().out
