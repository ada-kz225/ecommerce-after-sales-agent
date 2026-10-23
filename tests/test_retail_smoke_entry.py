"""No-API tests for the explicitly gated Retail V0 smoke-test entry."""

import json

from tau2.registry import registry

from ecommerce_after_sales_agent.registration import V0_AGENT_NAME
from ecommerce_after_sales_agent import retail_smoke


def test_preflight_resolves_the_fixed_v0_retail_task_and_config() -> None:
    plan = retail_smoke.build_smoke_plan()
    config = plan.config

    assert registry.get_agent_factory(V0_AGENT_NAME) is not None
    assert plan.task.id == "0"
    assert config.domain == "retail"
    assert config.agent == V0_AGENT_NAME
    assert config.task_ids == ["0"]
    assert config.llm_agent == "openai/gpt-4.1-mini"
    assert config.llm_user == "openai/gpt-4.1-mini"
    assert config.llm_args_agent == {"temperature": 0.0}
    assert config.llm_args_user == {"temperature": 0.0}
    assert config.num_trials == 1
    assert config.max_steps == 30
    assert config.max_errors == 10
    assert config.max_concurrency == 1
    assert config.workers == 0
    assert config.max_retries == 0
    assert config.seed == 42
    assert config.auto_review is False
    assert config.save_to == "retail-v0-smoke-task0"
    assert str(plan.output_path).endswith(
        "data/simulations/retail-v0-smoke-task0/results.json"
    )


def test_default_main_is_preflight_only(monkeypatch, capsys) -> None:
    def fail_if_run(*_args, **_kwargs):
        raise AssertionError("run_domain must not run without --run")

    monkeypatch.setattr(retail_smoke, "run_domain", fail_if_run)

    retail_smoke.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V0_AGENT_NAME
    assert payload["task_id"] == "0"
    assert payload["will_call_model_provider"] is False


def test_run_flag_is_the_only_path_that_invokes_official_runner(monkeypatch, capsys) -> None:
    received = []
    monkeypatch.setattr(retail_smoke, "run_domain", lambda config: received.append(config))

    retail_smoke.main(["--run"])

    assert len(received) == 1
    assert received[0].agent == V0_AGENT_NAME
    assert received[0].task_ids == ["0"]
    assert "charges may apply" in capsys.readouterr().out
