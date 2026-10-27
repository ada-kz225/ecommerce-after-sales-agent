"""V1-2 Step-budget-aware Planning 的显式门控 Retail Pilot 入口。"""

import argparse
import json
from dataclasses import dataclass
from typing import Sequence

from tau2.data_model.simulation import TextRunConfig
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.runner.batch import run_domain
from tau2.runner.build import build_agent, build_text_orchestrator
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import V1_2_AGENT_NAME, register_v1_2_agent
from .retail_exchange_repeat import ExchangeRepeatPreflight, build_repeat_config
from .retail_pilot import LLM_LOG_MODE, RetailPilotPlan, preflight_payload
from .v1_2_agent import V1_2Agent, V1_2AgentState

V1_2_TASK_IDS = ["2", "3", "4"]
V1_2_SAVE_TO = "retail-v1-2-seed-protocol-fixed-step-budget-repeat-2-4-t3"


@dataclass(frozen=True)
class V1_2PilotPreflight:
    """无 API 的 V1-2 构建结果和 fresh text-run 预算契约检查。"""

    repeat: ExchangeRepeatPreflight
    fresh_text_budget_exact: bool
    initialized_step_count: int


def build_v1_2_pilot_config(
    *,
    task_ids: list[str] = V1_2_TASK_IDS,
    num_trials: int = 3,
    save_to: str = V1_2_SAVE_TO,
) -> TextRunConfig:
    """复用 V1 重复实验配置，只替换 V1-2 所需的可变字段。"""
    if num_trials <= 0:
        raise ValueError("num_trials must be positive")
    v1_config = build_repeat_config(
        "v1", task_ids=task_ids, save_to=save_to
    )
    return v1_config.model_copy(
        update={"agent": V1_2_AGENT_NAME, "num_trials": num_trials}
    )


def build_v1_2_pilot_preflight(
    *,
    task_ids: list[str] = V1_2_TASK_IDS,
    num_trials: int = 3,
    save_to: str = V1_2_SAVE_TO,
) -> V1_2PilotPreflight:
    """验证官方 Builder 和 fresh Text Orchestrator 路径，不调用模型。"""
    config = build_v1_2_pilot_config(
        task_ids=task_ids, num_trials=num_trials, save_to=save_to
    )
    max_steps = config.effective_max_steps
    registered_name = register_v1_2_agent(max_steps=max_steps)
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from V1-2 Pilot configuration")

    # 先沿用已有的无 API 任务解析与 trial seed 计算，避免复制 Runner 逻辑。
    from .retail_exchange_repeat import _runner_trial_seeds
    from tau2.domains.retail.environment import get_environment
    from tau2.runner.helpers import get_tasks

    environment = get_environment()
    built_agent = build_agent(
        config.agent,
        environment,
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    if not isinstance(built_agent, V1_2Agent):
        raise RuntimeError("Official Builder did not construct V1_2Agent")
    if built_agent.max_steps != max_steps:
        raise RuntimeError("V1-2 Agent max_steps differs from TextRunConfig")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    actual_task_ids = [task.id for task in tasks]
    if actual_task_ids != task_ids:
        raise RuntimeError(
            f"V1-2 Pilot must resolve Retail tasks {task_ids}, got {actual_task_ids}"
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

    # 这条路径与正式 Runner 一致：initialize 只构造首条 Agent opening，未调用 LLM。
    orchestrator = build_text_orchestrator(config, tasks[0], seed=repeat.trial_seeds[0])
    orchestrator.initialize()
    if not isinstance(orchestrator, Orchestrator) or not isinstance(
        orchestrator.agent, V1_2Agent
    ):
        raise RuntimeError("Text Runner did not construct V1_2Agent")
    if orchestrator.agent.max_steps != orchestrator.max_steps:
        raise RuntimeError("Agent and Orchestrator max_steps differ")
    if not isinstance(orchestrator.agent_state, V1_2AgentState):
        raise RuntimeError("Text Runner did not initialize Agent state")
    exact_budget = bool(getattr(orchestrator.agent_state, "exact_budget", False))
    if not exact_budget:
        raise RuntimeError("Fresh Retail text initialization did not enable exact budget")
    return V1_2PilotPreflight(
        repeat=repeat,
        fresh_text_budget_exact=exact_budget,
        initialized_step_count=orchestrator.step_count,
    )


def preflight_v1_2_payload(preflight: V1_2PilotPreflight) -> dict:
    """输出不包含任务对话的配置、预算前提和异常风险。"""
    payload = preflight_payload(preflight.repeat.plan)
    payload.update(
        {
            "built_agent_type": preflight.repeat.built_agent_type,
            "trials_per_task": preflight.repeat.plan.config.num_trials,
            "planned_simulations": len(preflight.repeat.plan.tasks)
            * preflight.repeat.plan.config.num_trials,
            "trial_seeds": list(preflight.repeat.trial_seeds),
            "seed_strategy": "tau2 v2.0.0 从 run seed 42 为每个 trial 派生一个 seed；Text Orchestrator 再传给 Agent 和 User。",
            "step_budget": {
                "agent_max_steps": preflight.repeat.plan.config.effective_max_steps,
                "fresh_text_initialization_verified": preflight.fresh_text_budget_exact,
                "initialized_official_step_count": preflight.initialized_step_count,
                "counting_scope": "预算数值表示本次 Agent 决策完成后的本地估计；不是 Harness 暴露的实时计数。",
                "degradation": "resume 或无法识别为单条 opening 的历史会切换为不精确的保守提示。",
            },
            "multiple_tool_call_risk": {
                "policy": "Retail policy permits at most one Tool Call per turn.",
                "provider_constraint": "V1-2 passes parallel_tool_calls=false to the Agent LLM request.",
                "handling": "A remaining multi-call draft is never executed: V1-2 regenerates once with an explicit constraint, then returns safe no-tool text if still noncompliant.",
                "cost_risk": "A multi-call recovery can make one extra Agent LLM request; when both calls report cost/usage, V1-2 aggregates them into the final AssistantMessage.",
            },
            "experiment_focus": "step-budget-aware-planning",
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """默认只预检；只有显式 --run 才启动可能产生费用的 Simulation。"""
    parser = argparse.ArgumentParser(
        description="Retail Tasks 2–4、三次试验的 V1-2 Step-budget Pilot"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="输出预检后执行会产生费用的 Simulation。",
    )
    args = parser.parse_args(argv)
    preflight = build_v1_2_pilot_preflight()
    print(json.dumps(preflight_v1_2_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("开始显式 V1-2 Pilot；Agent、User 和 Judge 可能产生费用。")
    run_domain(preflight.repeat.plan.config)


if __name__ == "__main__":
    main()
