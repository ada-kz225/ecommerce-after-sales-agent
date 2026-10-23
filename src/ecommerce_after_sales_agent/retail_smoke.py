"""Explicitly gated Retail V0 smoke-test entry point.

Run without ``--run`` to validate registration, configuration, task selection,
and the official result location without contacting a model provider.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from tau2.data_model.simulation import TextRunConfig
from tau2.data_model.tasks import Task
from tau2.runner.batch import run_domain
from tau2.runner.helpers import get_tasks
from tau2.utils.utils import DATA_DIR

from .registration import V0_AGENT_NAME, register_v0_agent

SMOKE_TASK_ID = "0"
SMOKE_SAVE_TO = "retail-v0-smoke-task0"
SMOKE_OUTPUT_PATH = DATA_DIR / "simulations" / SMOKE_SAVE_TO / "results.json"


@dataclass(frozen=True)
class RetailSmokePlan:
    """The fully resolved no-API plan used for preflight and explicit execution."""

    config: TextRunConfig
    task: Task
    output_path: Path


def build_smoke_config() -> TextRunConfig:
    """Return the fixed, comparable configuration for the first V0 smoke test."""
    return TextRunConfig(
        domain="retail",
        agent=V0_AGENT_NAME,
        llm_agent="openai/gpt-4.1-mini",
        llm_args_agent={"temperature": 0.0},
        user="user_simulator",
        llm_user="openai/gpt-4.1-mini",
        llm_args_user={"temperature": 0.0},
        task_ids=[SMOKE_TASK_ID],
        num_trials=1,
        max_steps=30,
        max_errors=10,
        max_concurrency=1,
        workers=0,
        max_retries=0,
        seed=42,
        auto_review=False,
        save_to=SMOKE_SAVE_TO,
    )


def build_smoke_plan() -> RetailSmokePlan:
    """Register V0 and resolve exactly Retail Task 0 without starting a Simulation."""
    config = build_smoke_config()
    registered_name = register_v0_agent()
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from smoke-test configuration")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    if len(tasks) != 1 or tasks[0].id != SMOKE_TASK_ID:
        raise RuntimeError(f"Smoke test must resolve only Retail Task {SMOKE_TASK_ID}")
    return RetailSmokePlan(config=config, task=tasks[0], output_path=SMOKE_OUTPUT_PATH)


def preflight_payload(plan: RetailSmokePlan) -> dict:
    """Return JSON-safe, non-sensitive preflight details without task transcript data."""
    return {
        "mode": "preflight",
        "registered_agent": plan.config.agent,
        "task_id": plan.task.id,
        "output_path": str(plan.output_path),
        "config": plan.config.model_dump(mode="json"),
        "will_call_model_provider": False,
    }


def main(argv: Sequence[str] | None = None) -> None:
    """Print a preflight plan, or execute it only when ``--run`` is explicit."""
    parser = argparse.ArgumentParser(description="Retail V0 Task 0 smoke-test entry")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the paid Simulation after printing the preflight plan.",
    )
    args = parser.parse_args(argv)
    plan = build_smoke_plan()
    payload = preflight_payload(plan)
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if not args.run:
        return

    print("Starting explicit Retail V0 smoke Simulation; model-provider charges may apply.")
    run_domain(plan.config)


if __name__ == "__main__":
    main()
