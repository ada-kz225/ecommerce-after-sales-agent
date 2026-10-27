"""V1-2 Reserve 的显式门控 Retail Task 2 Smoke 入口。"""

import argparse
import json
from typing import Sequence

from tau2.orchestrator.orchestrator import Orchestrator
from tau2.runner.batch import run_domain
from tau2.runner.build import build_agent, build_text_orchestrator
from tau2.runner.helpers import get_tasks
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import V1_2_RESERVE_AGENT_NAME, register_v1_2_reserve_agent
from .retail_exchange_repeat import ExchangeRepeatPreflight, _runner_trial_seeds
from .retail_pilot import LLM_LOG_MODE, RetailPilotPlan, preflight_payload
from .retail_v1_2_pilot import V1_2PilotPreflight, build_v1_2_pilot_config
from .v1_2_agent import V1_2AgentState
from .v1_2_reserve_agent import V1_2ReserveAgent

RESERVE_SMOKE_TASK_IDS = ["2"]
RESERVE_SMOKE_NUM_TRIALS = 1
RESERVE_SMOKE_SAVE_TO = "retail-v1-2-reserve-smoke-task2-t1"


def build_v1_2_reserve_smoke_preflight() -> V1_2PilotPreflight:
    """构造 Reserve Smoke 并验证官方 Builder/fresh Text 初始化，不调用模型。"""
    base_config = build_v1_2_pilot_config(
        task_ids=RESERVE_SMOKE_TASK_IDS,
        num_trials=RESERVE_SMOKE_NUM_TRIALS,
        save_to=RESERVE_SMOKE_SAVE_TO,
    )
    config = base_config.model_copy(update={"agent": V1_2_RESERVE_AGENT_NAME})
    max_steps = config.effective_max_steps
    registered_name = register_v1_2_reserve_agent(max_steps=max_steps)
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from Reserve Smoke configuration")

    from tau2.domains.retail.environment import get_environment

    environment = get_environment()
    built_agent = build_agent(
        config.agent,
        environment,
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    if not isinstance(built_agent, V1_2ReserveAgent):
        raise RuntimeError("Official Builder did not construct V1_2ReserveAgent")
    if built_agent.max_steps != max_steps:
        raise RuntimeError("Reserve Agent max_steps differs from TextRunConfig")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    actual_task_ids = [task.id for task in tasks]
    if actual_task_ids != RESERVE_SMOKE_TASK_IDS:
        raise RuntimeError(
            f"Reserve Smoke must resolve Retail tasks {RESERVE_SMOKE_TASK_IDS}, got {actual_task_ids}"
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
        orchestrator.agent, V1_2ReserveAgent
    ):
        raise RuntimeError("Text Runner did not construct V1_2ReserveAgent")
    if orchestrator.agent.max_steps != orchestrator.max_steps:
        raise RuntimeError("Reserve Agent and Orchestrator max_steps differ")
    if not isinstance(orchestrator.agent_state, V1_2AgentState):
        raise RuntimeError("Text Runner did not initialize Reserve Agent state")
    exact_budget = bool(getattr(orchestrator.agent_state, "exact_budget", False))
    if not exact_budget:
        raise RuntimeError("Fresh Retail text initialization did not enable exact budget")
    return V1_2PilotPreflight(
        repeat=repeat,
        fresh_text_budget_exact=exact_budget,
        initialized_step_count=orchestrator.step_count,
    )


def preflight_reserve_smoke_payload(preflight: V1_2PilotPreflight) -> dict:
    """输出配置与真实运行后的审查项目，不包含任务对话或客户数据。"""
    payload = preflight_payload(preflight.repeat.plan)
    payload.update(
        {
            "experiment_focus": "v1-2-reserve-write-closure-smoke",
            "built_agent_type": preflight.repeat.built_agent_type,
            "trials_per_task": preflight.repeat.plan.config.num_trials,
            "planned_simulations": len(preflight.repeat.plan.tasks)
            * preflight.repeat.plan.config.num_trials,
            "trial_seeds": list(preflight.repeat.trial_seeds),
            "step_budget": {
                "agent_max_steps": preflight.repeat.plan.config.effective_max_steps,
                "fresh_text_initialization_verified": preflight.fresh_text_budget_exact,
                "initialized_official_step_count": preflight.initialized_step_count,
                "write_closure_reserve": "four remaining local budget steps: three required role transitions plus one Harness-cutoff margin",
                "scope_limit": "local fresh-run estimate only; not a Harness real-time counter",
            },
            "post_run_checks": [
                "infrastructure error, termination reason, inferred Harness steps, and reward",
                "whether a mutation Tool Call was blocked by the closure reserve and whether the User continued after the explanatory text",
                "each Environment-bound AssistantMessage has at most one Tool Call",
                "Budget Context, Grounding Context, trial seed, and parallel_tool_calls=false in Agent LLM debug requests",
                "write Tool Calls, Tool Results, DB Check, NL Assertion, and Action Checks",
                "Agent, User, and Judge token, latency, and cost records when available",
            ],
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """默认只预检；显式 --run 才会执行可能收费的真实 Smoke。"""
    parser = argparse.ArgumentParser(
        description="Retail Task 2 单次试验的 V1-2 Reserve Smoke"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="输出预检后执行会产生费用的 Simulation。",
    )
    args = parser.parse_args(argv)
    preflight = build_v1_2_reserve_smoke_preflight()
    print(json.dumps(preflight_reserve_smoke_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("开始显式 V1-2 Reserve Smoke；Agent、User 和 Judge 可能产生费用。")
    run_domain(preflight.repeat.plan.config)


if __name__ == "__main__":
    main()
