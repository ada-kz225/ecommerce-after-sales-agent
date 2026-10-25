"""修复后 V0/V1 的 Tasks 2–4 Grounding 稳定性重复实验入口。"""

import argparse
import json
from typing import Sequence

from tau2.runner.batch import run_domain
from tau2.utils.llm_utils import set_llm_log_mode
from tau2.utils.utils import DATA_DIR

from .retail_exchange_repeat import (
    AgentVersion,
    ExchangeRepeatPreflight,
    build_repeat_config,
    build_repeat_preflight,
    preflight_repeat_payload,
)
from .retail_pilot import LLM_LOG_MODE

GROUNDING_TASK_IDS = ["2", "3", "4"]
GROUNDING_SAVE_TO = {
    "v0": "retail-v0-seed-protocol-fixed-grounding-repeat-2-4-t3",
    "v1": "retail-v1-seed-protocol-fixed-grounding-repeat-2-4-t3",
}


def build_grounding_repeat_config(agent_version: AgentVersion):
    """构建 Tasks 2–4 的固定三次试验配置。"""
    return build_repeat_config(
        agent_version,
        task_ids=GROUNDING_TASK_IDS,
        save_to=GROUNDING_SAVE_TO[agent_version],
    )


def build_grounding_repeat_preflight(
    agent_version: AgentVersion,
) -> ExchangeRepeatPreflight:
    """构建、注册并解析 Grounding 稳定性实验，但不调用模型。"""
    return build_repeat_preflight(
        agent_version,
        task_ids=GROUNDING_TASK_IDS,
        save_to=GROUNDING_SAVE_TO[agent_version],
    )


def preflight_grounding_payload(preflight: ExchangeRepeatPreflight) -> dict:
    """返回不含任务对话的 Grounding 实验预检信息。"""
    payload = preflight_repeat_payload(preflight)
    payload.update(
        {
            "experiment_focus": "availability-grounding-stability",
            "post_run_checks": [
                "grounding context in real agent request",
                "available versus total variants answer",
                "DB Check and Action Checks",
                "max_steps and premature evaluation",
                "available token, cost, and latency records",
            ],
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """默认仅输出预检；只有显式 --run 才启动真实 Simulation。"""
    parser = argparse.ArgumentParser(
        description="Retail Tasks 2–4、三次试验的修复后 V0/V1 Grounding 对照"
    )
    parser.add_argument("--agent-version", choices=("v0", "v1"), default="v0")
    parser.add_argument(
        "--run",
        action="store_true",
        help="输出预检后执行会产生费用的 Simulation。",
    )
    args = parser.parse_args(argv)
    preflight = build_grounding_repeat_preflight(args.agent_version)
    print(json.dumps(preflight_grounding_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("开始显式 Grounding 重复实验；Agent、User 和 Judge 可能产生费用。")
    run_domain(preflight.plan.config)


if __name__ == "__main__":
    main()
