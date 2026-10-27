"""V1-2 与 Reserve 在 Retail Task 2 的有限规模对照入口。"""

import argparse
import json
from dataclasses import dataclass
from typing import Callable, Sequence

from tau2.data_model.simulation import TextRunConfig
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.runner.batch import run_domain
from tau2.runner.build import build_agent, build_text_orchestrator
from tau2.runner.helpers import get_tasks
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import (
    V1_2_AGENT_NAME,
    V1_2_RESERVE_AGENT_NAME,
    register_v1_2_agent,
    register_v1_2_reserve_agent,
)
from .retail_exchange_repeat import ExchangeRepeatPreflight, _runner_trial_seeds
from .retail_pilot import LLM_LOG_MODE, RetailPilotPlan, preflight_payload
from .retail_v1_2_pilot import build_v1_2_pilot_config
from .v1_2_agent import V1_2Agent, V1_2AgentState
from .v1_2_reserve_agent import V1_2ReserveAgent

TASK2_IDS = ["2"]
TASK2_TRIALS = 3
CONTROL_SAVE_TO = "retail-v1-2-current-control-task2-t3"
RESERVE_SAVE_TO = "retail-v1-2-reserve-closure-task2-t3"


@dataclass(frozen=True)
class Task2ComparisonVariant:
    """单个对照组的不可变配置。"""

    key: str
    agent_name: str
    save_to: str
    register: Callable[..., str]
    agent_type: type[V1_2Agent]


@dataclass(frozen=True)
class Task2ComparisonPreflight:
    """无 API 的 Builder、任务和 fresh budget 初始化检查结果。"""

    variant: Task2ComparisonVariant
    repeat: ExchangeRepeatPreflight
    fresh_text_budget_exact: bool
    initialized_step_count: int


VARIANTS = {
    "v1_2": Task2ComparisonVariant(
        key="v1_2",
        agent_name=V1_2_AGENT_NAME,
        save_to=CONTROL_SAVE_TO,
        register=register_v1_2_agent,
        agent_type=V1_2Agent,
    ),
    "reserve": Task2ComparisonVariant(
        key="reserve",
        agent_name=V1_2_RESERVE_AGENT_NAME,
        save_to=RESERVE_SAVE_TO,
        register=register_v1_2_reserve_agent,
        agent_type=V1_2ReserveAgent,
    ),
}


def build_task2_comparison_config(variant_key: str) -> TextRunConfig:
    """复用旧 V1-2 Pilot 配置，只改变当前 Agent 和新的结果目录。"""
    try:
        variant = VARIANTS[variant_key]
    except KeyError as error:
        raise ValueError(f"Unknown comparison variant: {variant_key}") from error
    base_config = build_v1_2_pilot_config(
        task_ids=TASK2_IDS,
        num_trials=TASK2_TRIALS,
        save_to=variant.save_to,
    )
    return base_config.model_copy(update={"agent": variant.agent_name})


def build_task2_comparison_preflight(variant_key: str) -> Task2ComparisonPreflight:
    """验证当前 Agent 通过官方 Builder/Runner 建立，不调用模型。"""
    variant = VARIANTS[variant_key]
    config = build_task2_comparison_config(variant_key)
    max_steps = config.effective_max_steps
    registered_name = variant.register(max_steps=max_steps)
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from comparison configuration")

    from tau2.domains.retail.environment import get_environment

    environment = get_environment()
    built_agent = build_agent(
        config.agent,
        environment,
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    if not isinstance(built_agent, variant.agent_type):
        raise RuntimeError("Official Builder constructed an unexpected comparison Agent")
    if built_agent.max_steps != max_steps:
        raise RuntimeError("Comparison Agent max_steps differs from TextRunConfig")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    actual_task_ids = [task.id for task in tasks]
    if actual_task_ids != TASK2_IDS:
        raise RuntimeError(
            f"Task 2 comparison must resolve Retail tasks {TASK2_IDS}, got {actual_task_ids}"
        )
    plan = RetailPilotPlan(
        config=config,
        tasks=tasks,
        output_path=DATA_DIR / "simulations" / config.save_to / "results.json",
    )
    repeat = ExchangeRepeatPreflight(
        plan=plan,
        built_agent_type=type(built_agent).__name__,
        trial_seeds=_runner_trial_seeds(config),
    )

    orchestrator = build_text_orchestrator(config, tasks[0], seed=repeat.trial_seeds[0])
    orchestrator.initialize()
    if not isinstance(orchestrator, Orchestrator) or not isinstance(
        orchestrator.agent, variant.agent_type
    ):
        raise RuntimeError("Text Runner constructed an unexpected comparison Agent")
    if not isinstance(orchestrator.agent_state, V1_2AgentState):
        raise RuntimeError("Text Runner did not initialize comparison Agent state")
    exact_budget = bool(getattr(orchestrator.agent_state, "exact_budget", False))
    if not exact_budget:
        raise RuntimeError("Fresh Retail text initialization did not enable exact budget")
    return Task2ComparisonPreflight(
        variant=variant,
        repeat=repeat,
        fresh_text_budget_exact=exact_budget,
        initialized_step_count=orchestrator.step_count,
    )


def preflight_comparison_payload(
    preflights: list[Task2ComparisonPreflight],
) -> dict:
    """输出对照配置、可比性边界和后续只读诊断方案。"""
    configs = [preflight.repeat.plan.config for preflight in preflights]
    baseline = configs[0].model_dump(mode="json")
    comparable = all(
        {
            key: value
            for key, value in config.model_dump(mode="json").items()
            if key not in {"agent", "save_to"}
        }
        == {
            key: value
            for key, value in baseline.items()
            if key not in {"agent", "save_to"}
        }
        for config in configs[1:]
    )
    return {
        "mode": "preflight",
        "will_call_model_provider": False,
        "variants": [
            {
                **preflight_payload(preflight.repeat.plan),
                "variant": preflight.variant.key,
                "built_agent_type": preflight.repeat.built_agent_type,
                "trial_seeds": list(preflight.repeat.trial_seeds),
                "fresh_text_budget_exact": preflight.fresh_text_budget_exact,
                "initialized_official_step_count": preflight.initialized_step_count,
            }
            for preflight in preflights
        ],
        "configs_match_except_agent_and_save_to": comparable,
        "planned_simulations": sum(
            len(preflight.repeat.plan.tasks) * preflight.repeat.plan.config.num_trials
            for preflight in preflights
        ),
        "post_run_metrics": [
            "Reward, MAX_STEPS, USER_STOP, inferred Harness steps, and Infrastructure Error",
            "per-request local budget estimates and whether the closure guard blocked a mutation",
            "actual mutation Tool Calls, Tool Results, DB Check, NL Assertion, Action Checks, and policy-prompt deviations",
            "Agent/User/Judge token, latency, and cost records when available",
        ],
        "guard_event_diagnostic": {
            "structured_event_available": False,
            "limitation": "The current Agent stores only fallback text in trajectory; it has no dedicated guard-event field.",
            "read_only_plan": "After a run, correlate the exact fallback text in trajectory with the immediately preceding Agent llm_debug response that proposed one mutation Tool Call. Report an event only when both conditions hold; do not alter Agent behavior.",
        },
    }


def _selected_variants(choice: str) -> list[str]:
    if choice == "both":
        return ["v1_2", "reserve"]
    return [choice]


def main(argv: Sequence[str] | None = None) -> None:
    """默认仅预检；显式 --run 才会执行可能收费的对照 Simulation。"""
    parser = argparse.ArgumentParser(
        description="V1-2 与 V1-2 Reserve 的 Retail Task 2 三次试验对照"
    )
    parser.add_argument(
        "--variant",
        choices=["v1_2", "reserve", "both"],
        default="both",
        help="选择当前 V1-2 control、Reserve 或两者。默认仅预检两者。",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="输出预检后执行会产生费用的 Simulation。",
    )
    args = parser.parse_args(argv)
    preflights = [
        build_task2_comparison_preflight(variant)
        for variant in _selected_variants(args.variant)
    ]
    print(json.dumps(preflight_comparison_payload(preflights), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("开始显式 V1-2/Reserve Task 2 对照；Agent、User 和 Judge 可能产生费用。")
    for preflight in preflights:
        run_domain(preflight.repeat.plan.config)


if __name__ == "__main__":
    main()
