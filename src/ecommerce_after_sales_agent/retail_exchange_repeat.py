"""Explicitly gated V0/V1 exchange-repeat Retail preflight and runner.

This module prepares the post seed/protocol-compatibility comparison only.
It never contacts a model provider unless ``--run`` is explicitly supplied.
"""

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from tau2.agent.base.llm_config import LLMConfigMixin
from tau2.data_model.simulation import TextRunConfig
from tau2.data_model.tasks import Task
from tau2.domains.retail.environment import get_environment
from tau2.runner.batch import run_domain
from tau2.runner.build import build_agent
from tau2.runner.helpers import get_tasks
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import (
    V0_AGENT_NAME,
    V1_AGENT_NAME,
    register_v0_agent,
    register_v1_agent,
)
from .retail_pilot import LLM_LOG_MODE, RetailPilotPlan, preflight_payload
from .v0_agent import V0Agent
from .v1_agent import V1Agent

AgentVersion = Literal["v0", "v1"]

REPEAT_TASK_IDS = ["0", "1"]
REPEAT_NUM_TRIALS = 3
REPEAT_RUN_SEED = 42
REPEAT_SAVE_TO = {
    "v0": "retail-v0-seed-protocol-fixed-repeat-0-1-t3",
    "v1": "retail-v1-seed-protocol-fixed-repeat-0-1-t3",
}


@dataclass(frozen=True)
class ExchangeRepeatPreflight:
    """No-API resolved plan, Builder result, and Runner-equivalent trial seeds."""

    plan: RetailPilotPlan
    built_agent_type: str
    trial_seeds: tuple[int, ...]


def build_repeat_config(
    agent_version: AgentVersion,
    *,
    task_ids: list[str] = REPEAT_TASK_IDS,
    save_to: str | None = None,
) -> TextRunConfig:
    """Build one post-fix config; V0/V1 differ only by agent and save target."""
    agent_name = V0_AGENT_NAME if agent_version == "v0" else V1_AGENT_NAME
    return TextRunConfig(
        domain="retail",
        task_split_name="base",
        agent=agent_name,
        llm_agent="openai/gpt-4.1-mini",
        llm_args_agent={"temperature": 0.0},
        user="user_simulator",
        llm_user="openai/gpt-4.1-mini",
        llm_args_user={"temperature": 0.0},
        task_ids=task_ids,
        num_trials=REPEAT_NUM_TRIALS,
        max_steps=30,
        max_errors=10,
        max_concurrency=1,
        workers=0,
        max_retries=0,
        seed=REPEAT_RUN_SEED,
        verbose_logs=True,
        auto_review=False,
        save_to=save_to or REPEAT_SAVE_TO[agent_version],
    )


def _runner_trial_seeds(config: TextRunConfig) -> tuple[int, ...]:
    """Mirror v2.0.0 batch.py's deterministic per-trial seed derivation."""
    rng = random.Random(config.seed)
    return tuple(rng.randint(0, 1_000_000) for _ in range(config.num_trials))


def build_repeat_preflight(
    agent_version: AgentVersion, *, task_ids: list[str], save_to: str
) -> ExchangeRepeatPreflight:
    """无 API 地注册、构建指定 Agent，并解析指定的 Retail 任务。"""
    config = build_repeat_config(agent_version, task_ids=task_ids, save_to=save_to)
    if agent_version == "v0":
        registered_name = register_v0_agent()
        expected_type = V0Agent
    else:
        registered_name = register_v1_agent()
        expected_type = V1Agent
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from repeat configuration")

    environment = get_environment()
    agent = build_agent(
        config.agent,
        environment,
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    if not isinstance(agent, expected_type):
        raise RuntimeError("Official Builder did not construct the expected Agent type")
    if not isinstance(agent, LLMConfigMixin):
        raise RuntimeError("Built Agent cannot receive Harness LLM seeds")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    actual_task_ids = [task.id for task in tasks]
    if actual_task_ids != task_ids:
        raise RuntimeError(
            f"Repeat run must resolve Retail tasks {task_ids}, got {actual_task_ids}"
        )
    plan = RetailPilotPlan(
        config=config,
        tasks=tasks,
        output_path=DATA_DIR / "simulations" / config.save_to / "results.json",
    )
    return ExchangeRepeatPreflight(
        plan=plan,
        built_agent_type=type(agent).__name__,
        trial_seeds=_runner_trial_seeds(config),
    )


def build_exchange_repeat_preflight(agent_version: AgentVersion) -> ExchangeRepeatPreflight:
    """无 API 地构建 Tasks 0–1 换货重复实验预检。"""
    return build_repeat_preflight(
        agent_version,
        task_ids=REPEAT_TASK_IDS,
        save_to=REPEAT_SAVE_TO[agent_version],
    )


def preflight_repeat_payload(preflight: ExchangeRepeatPreflight) -> dict:
    """Expose a non-sensitive, no-API plan including the exact seed strategy."""
    payload = preflight_payload(preflight.plan)
    payload.update(
        {
            "built_agent_type": preflight.built_agent_type,
            "trials_per_task": preflight.plan.config.num_trials,
            "planned_simulations": len(preflight.plan.tasks)
            * preflight.plan.config.num_trials,
            "trial_seeds": list(preflight.trial_seeds),
            "seed_strategy": (
                "tau2 v2.0.0 batch runner deterministically derives one seed per "
                "trial from run seed 42; all selected tasks share that trial seed, "
                "then the Text Orchestrator passes it to Agent and User."
            ),
            "agent_supports_harness_seed": True,
            "compatibility_label": "seed-protocol-compatibility-fixed",
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """Print a no-API preflight unless ``--run`` explicitly starts one version."""
    parser = argparse.ArgumentParser(
        description="Retail Tasks 0/1, three-trial post-fix V0/V1 comparison"
    )
    parser.add_argument("--agent-version", choices=("v0", "v1"), default="v0")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the paid Simulation after printing this version's preflight.",
    )
    args = parser.parse_args(argv)
    preflight = build_exchange_repeat_preflight(args.agent_version)
    print(json.dumps(preflight_repeat_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print(
        "Starting explicit post-fix Retail repeat; Agent, User, and Judge charges may apply."
    )
    run_domain(preflight.plan.config)


if __name__ == "__main__":
    main()
