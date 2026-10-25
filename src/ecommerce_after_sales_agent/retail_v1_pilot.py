"""Explicitly gated 5-task Retail V1 Pilot entry point.

The V1 plan intentionally shares all V0 Pilot settings except the registered
Agent name and an isolated result directory. Run without ``--run`` for a
strictly local, no-API preflight.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from tau2.domains.retail.environment import get_environment
from tau2.runner.batch import run_domain
from tau2.runner.build import build_agent
from tau2.runner.helpers import get_tasks
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import V1_AGENT_NAME, register_v1_agent
from .retail_pilot import (
    LLM_LOG_MODE,
    PILOT_TASK_IDS,
    RetailPilotPlan,
    build_pilot_config,
    preflight_payload as shared_preflight_payload,
)
from .v1_agent import V1Agent

PILOT_SAVE_TO = "retail-v1-pilot-0-4"
PILOT_OUTPUT_PATH = DATA_DIR / "simulations" / PILOT_SAVE_TO / "results.json"


@dataclass(frozen=True)
class V1PilotPreflight:
    """Resolved no-API Pilot plan plus the class built through official Builder."""

    plan: RetailPilotPlan
    built_agent_type: str


def build_v1_pilot_plan() -> V1PilotPreflight:
    """Register, build, and resolve V1 without invoking a model provider."""
    config = build_pilot_config(agent_name=V1_AGENT_NAME, save_to=PILOT_SAVE_TO)
    registered_name = register_v1_agent()
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from V1 Pilot configuration")

    environment = get_environment()
    agent = build_agent(
        config.agent,
        environment,
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    if not isinstance(agent, V1Agent):
        raise RuntimeError("Official Builder did not construct the expected V1Agent")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    actual_task_ids = [task.id for task in tasks]
    if actual_task_ids != PILOT_TASK_IDS:
        raise RuntimeError(
            f"V1 Pilot must resolve Retail tasks {PILOT_TASK_IDS}, got {actual_task_ids}"
        )
    plan = RetailPilotPlan(config=config, tasks=tasks, output_path=PILOT_OUTPUT_PATH)
    return V1PilotPreflight(plan=plan, built_agent_type=type(agent).__name__)


def preflight_payload(preflight: V1PilotPreflight) -> dict:
    """Return the shared plan with V1 Builder and grounding-verification facts."""
    payload = shared_preflight_payload(preflight.plan)
    payload.update(
        {
            "built_agent_type": preflight.built_agent_type,
            "grounding_context": {
                "enabled_by_agent": True,
                "verified_in_this_preflight": False,
                "verification_note": (
                    "Grounding is injected after a successful Product Tool Result; "
                    "this no-API preflight does not fabricate one. Its injection is "
                    "covered by Mock generate() tests, not yet by a real LLM call."
                ),
            },
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """Print V1 preflight by default; execute only with explicit ``--run``."""
    parser = argparse.ArgumentParser(description="Retail V1 Tasks 0--4 Pilot entry")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the paid five-task Simulation after printing preflight.",
    )
    args = parser.parse_args(argv)
    preflight = build_v1_pilot_plan()
    print(json.dumps(preflight_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("Starting explicit Retail V1 Pilot; Agent, User, and Judge charges may apply.")
    run_domain(preflight.plan.config)


if __name__ == "__main__":
    main()
