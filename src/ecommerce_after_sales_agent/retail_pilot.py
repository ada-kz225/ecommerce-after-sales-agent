"""Explicitly gated 5-task Retail V0 Pilot entry point.

Run without ``--run`` to inspect the exact, comparable plan.  ``--run`` is
required before the official Runner can contact any model provider.
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
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import V0_AGENT_NAME, register_v0_agent

PILOT_TASK_IDS = ["0", "1", "2", "3", "4"]
PILOT_SAVE_TO = "retail-v0-pilot-0-4"
PILOT_OUTPUT_PATH = DATA_DIR / "simulations" / PILOT_SAVE_TO / "results.json"
LLM_LOG_MODE = "all"


@dataclass(frozen=True)
class RetailPilotPlan:
    """Fully resolved Pilot plan; building it performs no LLM call."""

    config: TextRunConfig
    tasks: list[Task]
    output_path: Path


def build_pilot_config(
    *, agent_name: str = V0_AGENT_NAME, save_to: str = PILOT_SAVE_TO
) -> TextRunConfig:
    """Return the fixed configuration shared by comparable 0--4 Pilots."""
    return TextRunConfig(
        domain="retail",
        task_split_name="base",
        agent=agent_name,
        llm_agent="openai/gpt-4.1-mini",
        llm_args_agent={"temperature": 0.0},
        user="user_simulator",
        llm_user="openai/gpt-4.1-mini",
        llm_args_user={"temperature": 0.0},
        task_ids=PILOT_TASK_IDS,
        num_trials=1,
        max_steps=30,
        max_errors=10,
        max_concurrency=1,
        workers=0,
        max_retries=0,
        seed=42,
        verbose_logs=True,
        auto_review=False,
        save_to=save_to,
    )


def build_pilot_plan() -> RetailPilotPlan:
    """Register V0 and resolve exactly the fixed five Retail tasks."""
    config = build_pilot_config()
    registered_name = register_v0_agent()
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from Pilot configuration")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    actual_task_ids = [task.id for task in tasks]
    if actual_task_ids != PILOT_TASK_IDS:
        raise RuntimeError(
            f"Pilot must resolve Retail tasks {PILOT_TASK_IDS}, got {actual_task_ids}"
        )
    return RetailPilotPlan(config=config, tasks=tasks, output_path=PILOT_OUTPUT_PATH)


def preflight_payload(plan: RetailPilotPlan) -> dict:
    """Return non-sensitive configuration and the possible semantic-Judge cost."""
    scoring = plan.config.communicate_scoring
    return {
        "mode": "preflight",
        "registered_agent": plan.config.agent,
        "task_ids": [task.id for task in plan.tasks],
        "output_path": str(plan.output_path),
        "config": plan.config.model_dump(mode="json"),
        "llm_log_mode": LLM_LOG_MODE,
        "judge": {
            "type": "communicate_scoring semantic",
            "model": scoring.judge.model,
            "model_args": scoring.judge.model_args,
            "may_call_provider": True,
            "note": (
                "A semantic Judge is configured by default; it is invoked only "
                "when the completed task has applicable communication criteria."
            ),
        },
        "auto_review": plan.config.auto_review,
        "will_call_model_provider": False,
    }


def main(argv: Sequence[str] | None = None) -> None:
    """Print preflight by default; run only after the explicit ``--run`` flag."""
    parser = argparse.ArgumentParser(description="Retail V0 Tasks 0--4 Pilot entry")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the paid five-task Simulation after printing preflight.",
    )
    args = parser.parse_args(argv)
    plan = build_pilot_plan()
    print(json.dumps(preflight_payload(plan), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("Starting explicit Retail V0 Pilot; Agent, User, and Judge charges may apply.")
    run_domain(plan.config)


if __name__ == "__main__":
    main()
