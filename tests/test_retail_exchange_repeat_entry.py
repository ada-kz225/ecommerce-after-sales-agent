"""No-API tests for the post seed/protocol-fix V0/V1 exchange repeat entry."""

import json

from tau2.agent.base.llm_config import LLMConfigMixin

from ecommerce_after_sales_agent import retail_exchange_repeat
from ecommerce_after_sales_agent.registration import V0_AGENT_NAME, V1_AGENT_NAME


def test_repeat_preflight_builds_the_expected_agents_tasks_and_trial_seeds() -> None:
    v0 = retail_exchange_repeat.build_exchange_repeat_preflight("v0")
    v1 = retail_exchange_repeat.build_exchange_repeat_preflight("v1")

    assert v0.built_agent_type == "V0Agent"
    assert v1.built_agent_type == "V1Agent"
    assert [task.id for task in v0.plan.tasks] == ["0", "1"]
    assert [task.id for task in v1.plan.tasks] == ["0", "1"]
    assert v0.plan.config.num_trials == v1.plan.config.num_trials == 3
    # This is the exact sequence from random.Random(42), matching batch.py.
    assert v0.trial_seeds == v1.trial_seeds == (670487, 116739, 26225)
    assert str(v0.plan.output_path).endswith(
        "retail-v0-seed-protocol-fixed-repeat-0-1-t3/results.json"
    )
    assert str(v1.plan.output_path).endswith(
        "retail-v1-seed-protocol-fixed-repeat-0-1-t3/results.json"
    )


def test_repeat_configs_are_identical_except_agent_and_save_to() -> None:
    v0 = retail_exchange_repeat.build_exchange_repeat_preflight("v0").plan.config
    v1 = retail_exchange_repeat.build_exchange_repeat_preflight("v1").plan.config

    assert v0.agent == V0_AGENT_NAME
    assert v1.agent == V1_AGENT_NAME
    assert v0.model_dump(mode="json") == {
        **v1.model_dump(mode="json"),
        "agent": V0_AGENT_NAME,
        "save_to": v0.save_to,
    }
    assert v0.save_to != v1.save_to
    assert v0.llm_args_agent == v1.llm_args_agent == {"temperature": 0.0}
    assert v0.llm_args_user == v1.llm_args_user == {"temperature": 0.0}


def test_built_repeat_agents_support_harness_seed_without_changing_temperature() -> None:
    for version in ("v0", "v1"):
        config = retail_exchange_repeat.build_repeat_config(version)
        preflight = retail_exchange_repeat.build_exchange_repeat_preflight(version)
        # The production assertion occurs in the preflight builder; this test
        # additionally verifies the same official mixin behavior on a fresh build.
        assert preflight.built_agent_type in {"V0Agent", "V1Agent"}
        assert config.llm_args_agent == {"temperature": 0.0}

    # Direct generate-kwargs capture is covered for both Agent versions in
    # test_v0_agent.py and test_v1_availability_grounding.py; this entry test
    # keeps the plan-level no-API contract explicit.
    assert issubclass(retail_exchange_repeat.V0Agent, LLMConfigMixin)
    assert issubclass(retail_exchange_repeat.V1Agent, LLMConfigMixin)


def test_default_repeat_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_exchange_repeat,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("run_domain must not run without --run")
        ),
    )

    retail_exchange_repeat.main(["--agent-version", "v1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V1_AGENT_NAME
    assert payload["built_agent_type"] == "V1Agent"
    assert payload["task_ids"] == ["0", "1"]
    assert payload["trials_per_task"] == 3
    assert payload["planned_simulations"] == 6
    assert payload["trial_seeds"] == [670487, 116739, 26225]
    assert payload["agent_supports_harness_seed"] is True
    assert payload["will_call_model_provider"] is False


def test_repeat_run_flag_is_the_only_path_that_invokes_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_exchange_repeat, "run_domain", received.append)
    monkeypatch.setattr(retail_exchange_repeat, "set_llm_log_mode", modes.append)

    retail_exchange_repeat.main(["--agent-version", "v0", "--run"])

    assert len(received) == 1
    assert received[0].agent == V0_AGENT_NAME
    assert received[0].task_ids == ["0", "1"]
    assert received[0].num_trials == 3
    assert received[0].save_to == "retail-v0-seed-protocol-fixed-repeat-0-1-t3"
    assert modes == ["all"]
    assert "Agent, User, and Judge charges may apply" in capsys.readouterr().out
