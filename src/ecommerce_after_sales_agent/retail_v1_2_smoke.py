"""修复多 Tool Call 恢复机制后的 V1-2 Retail Smoke 入口。"""

import argparse
import json
from typing import Sequence

from tau2.runner.batch import run_domain
from tau2.utils.llm_utils import set_llm_log_mode

from .retail_pilot import LLM_LOG_MODE
from .retail_v1_2_pilot import (
    V1_2PilotPreflight,
    build_v1_2_pilot_preflight,
    preflight_v1_2_payload,
)

SMOKE_TASK_IDS = ["2"]
SMOKE_NUM_TRIALS = 1
SMOKE_SAVE_TO = "retail-v1-2-multi-tool-recovery-smoke-task2-t1"


def build_v1_2_smoke_preflight() -> V1_2PilotPreflight:
    """复用 V1-2 Pilot 的真实 Builder 预检，固定为 Task 2 单次试验。"""
    return build_v1_2_pilot_preflight(
        task_ids=SMOKE_TASK_IDS,
        num_trials=SMOKE_NUM_TRIALS,
        save_to=SMOKE_SAVE_TO,
    )


def preflight_smoke_payload(preflight: V1_2PilotPreflight) -> dict:
    """添加真实 Smoke 后的检查清单，但不包含任务对话或客户数据。"""
    payload = preflight_v1_2_payload(preflight)
    payload.update(
        {
            "experiment_focus": "multi-tool-recovery-smoke",
            "post_run_checks": [
                "infrastructure error and termination reason",
                "multi-tool drafts and whether one retry or safe fallback occurred",
                "each Environment-bound AssistantMessage has at most one Tool Call",
                "Budget Context and Grounding Context in Agent LLM debug requests",
                "Reward, DB Check, NL Assertion, Action Checks, and step consumption",
                "Agent, User, and Judge token, latency, and cost records when available",
            ],
        }
    )
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    """默认只预检；显式 --run 才会进行可能收费的 Smoke Simulation。"""
    parser = argparse.ArgumentParser(
        description="Retail Task 2 单次试验的 V1-2 多 Tool Call 恢复 Smoke"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="输出预检后执行会产生费用的 Simulation。",
    )
    args = parser.parse_args(argv)
    preflight = build_v1_2_smoke_preflight()
    print(json.dumps(preflight_smoke_payload(preflight), indent=2, ensure_ascii=False))

    if not args.run:
        return

    set_llm_log_mode(LLM_LOG_MODE)
    print("开始显式 V1-2 多 Tool Call 恢复 Smoke；Agent、User 和 Judge 可能产生费用。")
    run_domain(preflight.repeat.plan.config)


if __name__ == "__main__":
    main()
