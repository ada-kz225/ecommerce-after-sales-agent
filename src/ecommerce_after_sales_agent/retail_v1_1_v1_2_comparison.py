"""合规 V1-1 与 V1-2 Step Budget 的显式门控 Retail 对照入口。"""

import argparse
import json
from dataclasses import dataclass
from typing import Literal, Sequence

from tau2.agent.base.llm_config import LLMConfigMixin
from tau2.runner.batch import run_domain
from tau2.runner.build import build_agent
from tau2.runner.helpers import get_tasks
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .registration import (
    V1_1_COMPLIANT_AGENT_NAME,
    V1_2_AGENT_NAME,
    register_v1_1_compliant_agent,
    register_v1_2_agent,
)
from .retail_exchange_repeat import _runner_trial_seeds
from .retail_pilot import LLM_LOG_MODE, RetailPilotPlan, preflight_payload
from .retail_v1_2_pilot import build_v1_2_pilot_config
from .v1_1_compliant_agent import V1_1CompliantAgent
from .v1_2_agent import V1_2Agent

ComparisonVersion = Literal["v1_1", "v1_2"]
COMPARISON_TASK_IDS = ["2", "3", "4"]
COMPARISON_NUM_TRIALS = 3
COMPARISON_SAVE_TO = {
    "v1_1": "retail-v1-1-compliant-grounding-repeat-2-4-t3",
    "v1_2": "retail-v1-2-compliant-step-budget-repeat-2-4-t3",
}


@dataclass(frozen=True)
class ComparisonPreflight:
    """无 API 的对照版本构建结果与固定 trial seed。"""

    plan: RetailPilotPlan
    built_agent_type: str
    trial_seeds: tuple[int, ...]


def build_comparison_config(version: ComparisonVersion):
    """从 V1-2 Pilot 基础配置生成两组可比的三次试验配置。"""
    agent_name = (
        V1_1_COMPLIANT_AGENT_NAME if version == "v1_1" else V1_2_AGENT_NAME
    )
    config = build_v1_2_pilot_config(
        task_ids=COMPARISON_TASK_IDS,
        num_trials=COMPARISON_NUM_TRIALS,
        save_to=COMPARISON_SAVE_TO[version],
    )
    return config.model_copy(update={"agent": agent_name})


def build_comparison_preflight(version: ComparisonVersion) -> ComparisonPreflight:
    """注册、构建并解析对照任务，不调用模型或 Runner。"""
    config = build_comparison_config(version)
    if version == "v1_1":
        registered_name = register_v1_1_compliant_agent()
        expected_type = V1_1CompliantAgent
    else:
        registered_name = register_v1_2_agent(max_steps=config.effective_max_steps)
        expected_type = V1_2Agent
    if registered_name != config.agent:
        raise RuntimeError("Registered Agent name differs from comparison configuration")

    from tau2.domains.retail.environment import get_environment

    agent = build_agent(
        config.agent,
        get_environment(),
        llm=config.llm_agent,
        llm_args=config.llm_args_agent,
    )
    if not isinstance(agent, expected_type):
        raise RuntimeError("Official Builder did not construct the expected comparison Agent")
    if not isinstance(agent, LLMConfigMixin):
        raise RuntimeError("Comparison Agent cannot receive Harness seeds")
    if version == "v1_2" and agent.max_steps != config.effective_max_steps:
        raise RuntimeError("V1-2 comparison Agent max_steps differs from configuration")

    tasks = get_tasks(
        config.domain,
        task_split_name=config.task_split_name,
        task_ids=config.task_ids,
    )
    if [task.id for task in tasks] != COMPARISON_TASK_IDS:
        raise RuntimeError("Comparison did not resolve the fixed Retail task set")
    plan = RetailPilotPlan(
        config=config,
        tasks=tasks,
        output_path=DATA_DIR / "simulations" / config.save_to / "results.json",
    )
    return ComparisonPreflight(
        plan=plan,
        built_agent_type=type(agent).__name__,
        trial_seeds=_runner_trial_seeds(config),
    )


def preflight_comparison_payload(preflight: ComparisonPreflight) -> dict:
    """输出可比性边界、单 Tool Call 保护与真实运行检查项。"""
    payload = preflight_payload(preflight.plan)
    payload.update(
        {
            "built_agent_type": preflight.built_agent_type,
            "trials_per_task": preflight.plan.config.num_trials,
            "planned_simulations": len(preflight.plan.tasks)
            * preflight.plan.config.num_trials,
            "trial_seeds": list(preflight.trial_seeds),
            "comparison_boundary": {
                "shared": "V1 Availability Grounding, GPT-4.1-mini, temperature, seed strategy, Retail policy/tools/harness/evaluator, parallel_tool_calls=false, and one-retry safe recovery.",
                "only_mechanism_difference": "V1-2 additionally injects local Step Budget Context; V1-1 compliant does not.",
            },
            "post_run_checks": [
                "Reward, DB Check, Action Checks, and NL Assertions",
                "termination, max_steps, and actual step consumption",
                "multi-tool drafts, recovery requests, and Environment-bound call counts",
                "Agent/User/Judge token, latency, and cost records when available",
            ],
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """默认只预检；显式 --run 才执行一个版本的真实对照实验。"""
    parser = argparse.ArgumentParser(
        description="Retail Tasks 2–4、三次试验的合规 V1-1/V1-2 对照"
    )
    parser.add_argument("--agent-version", choices=("v1_1", "v1_2"), default="v1_1")
    parser.add_argument(
        "--run",
        action="store_true",
        help="输出预检后执行会产生费用的 Simulation。",
    )
    args = parser.parse_args(argv)
    preflight = build_comparison_preflight(args.agent_version)
    print(json.dumps(preflight_comparison_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("开始显式合规 V1-1/V1-2 对照；Agent、User 和 Judge 可能产生费用。")
    run_domain(preflight.plan.config)


if __name__ == "__main__":
    main()
