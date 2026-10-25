"""No-API tests for the explicitly gated Retail V1 0--4 Pilot entry."""

import json

from tau2.registry import registry

from ecommerce_after_sales_agent import retail_pilot, retail_v1_pilot
from ecommerce_after_sales_agent.registration import V1_AGENT_NAME


def test_v1_preflight_registers_and_builds_v1_with_v0_comparable_config() -> None:
    preflight = retail_v1_pilot.build_v1_pilot_plan()
    config = preflight.plan.config
    v0_config = retail_pilot.build_pilot_config()

    assert registry.get_agent_factory(V1_AGENT_NAME) is not None
    assert preflight.built_agent_type == "V1Agent"
    assert [task.id for task in preflight.plan.tasks] == ["0", "1", "2", "3", "4"]
    assert config.agent == V1_AGENT_NAME
    assert config.save_to == "retail-v1-pilot-0-4"
    assert str(preflight.plan.output_path).endswith(
        "data/simulations/retail-v1-pilot-0-4/results.json"
    )
    assert config.model_dump(mode="json") == {
        **v0_config.model_dump(mode="json"),
        "agent": V1_AGENT_NAME,
        "save_to": "retail-v1-pilot-0-4",
    }


def test_default_v1_main_is_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        retail_v1_pilot,
        "run_domain",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("run_domain must not run without --run")
        ),
    )

    retail_v1_pilot.main([])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "preflight"
    assert payload["registered_agent"] == V1_AGENT_NAME
    assert payload["built_agent_type"] == "V1Agent"
    assert payload["task_ids"] == ["0", "1", "2", "3", "4"]
    assert payload["grounding_context"]["verified_in_this_preflight"] is False
    assert payload["will_call_model_provider"] is False


def test_v1_run_flag_is_the_only_path_that_invokes_official_runner(monkeypatch, capsys) -> None:
    received = []
    modes = []
    monkeypatch.setattr(retail_v1_pilot, "run_domain", lambda config: received.append(config))
    monkeypatch.setattr(retail_v1_pilot, "set_llm_log_mode", modes.append)

    retail_v1_pilot.main(["--run"])

    assert len(received) == 1
    assert received[0].agent == V1_AGENT_NAME
    assert received[0].task_ids == ["0", "1", "2", "3", "4"]
    assert received[0].save_to == "retail-v1-pilot-0-4"
    assert modes == ["all"]
    assert "Agent, User, and Judge charges may apply" in capsys.readouterr().out
