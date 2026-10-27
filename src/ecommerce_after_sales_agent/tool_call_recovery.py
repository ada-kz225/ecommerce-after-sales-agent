"""Retail 单 Tool Call 约束与有限恢复的共享实现。"""

from collections.abc import Callable
from typing import Optional

from tau2.data_model.message import AssistantMessage, Message, SystemMessage
from tau2.environment.tool import Tool

GenerateFunction = Callable[..., AssistantMessage]


def _retry_instruction() -> SystemMessage:
    """返回仅用于本次重生的临时约束，不写入正式 history。"""
    return SystemMessage(
        role="system",
        content=(
            "The immediately previous draft was rejected before any tool execution "
            "because it contained multiple Tool Calls. Regenerate this turn with "
            "either ordinary text or exactly one Tool Call. Do not claim that any "
            "tool ran, and do not combine Tool Calls with user-facing text."
        ),
    )


def _combined_usage(first: Optional[dict], second: Optional[dict]) -> Optional[dict]:
    """仅在两次调用均有可加 usage 时保留合计，避免伪造缺失统计。"""
    if first is None or second is None:
        return None
    combined: dict = {}
    for key in set(first) | set(second):
        first_value = first.get(key)
        second_value = second.get(key)
        if isinstance(first_value, (int, float)) and isinstance(
            second_value, (int, float)
        ):
            combined[key] = first_value + second_value
        else:
            return None
    return combined


def _include_retry_metadata(
    first: AssistantMessage, final: AssistantMessage
) -> AssistantMessage:
    """把未进入 history 的首次调用成本合并到最终可追踪消息。"""
    if first.cost is not None and final.cost is not None:
        final.cost = first.cost + final.cost
    else:
        final.cost = None
    final.usage = _combined_usage(first.usage, final.usage)
    if (
        first.generation_time_seconds is not None
        and final.generation_time_seconds is not None
    ):
        final.generation_time_seconds = (
            first.generation_time_seconds + final.generation_time_seconds
        )
    else:
        final.generation_time_seconds = None
    return final


def _safe_multi_tool_fallback(
    first: AssistantMessage, second: AssistantMessage
) -> AssistantMessage:
    """两次不合规时仅说明当前回合未执行新操作，不截取任一 Tool Call。"""
    fallback = AssistantMessage.text(
        "I could not complete that step because it requires one tool request at a time. "
        "No new tool action was performed for this turn. Please let me continue with one necessary step.",
        cost=second.cost,
        usage=second.usage,
        generation_time_seconds=second.generation_time_seconds,
    )
    return _include_retry_metadata(first, fallback)


def generate_with_single_tool_call_recovery(
    *,
    generate_fn: GenerateFunction,
    model: str,
    tools: list[Tool],
    messages: list[Message],
    llm_args: dict,
    call_name: str,
) -> AssistantMessage:
    """限制并恢复多 Tool Call；最多额外调用一次 LLM。"""
    # GPT-4.1 与当前 LiteLLM completion 均支持该参数，作为首道 Provider 约束。
    request_args = {**llm_args, "parallel_tool_calls": False}
    first = generate_fn(
        model=model,
        tools=tools,
        messages=messages,
        call_name=call_name,
        **request_args,
    )
    if not isinstance(first, AssistantMessage):
        raise TypeError("Agent LLM response must be an AssistantMessage")
    first.validate()
    if not first.tool_calls or len(first.tool_calls) == 1:
        return first

    # 违规草稿不进入 Agent state，避免留下未匹配 Tool Result 的 history。
    second = generate_fn(
        model=model,
        tools=tools,
        messages=[*messages, _retry_instruction()],
        call_name=f"{call_name}_multi_tool_retry",
        **request_args,
    )
    if not isinstance(second, AssistantMessage):
        raise TypeError("Agent retry response must be an AssistantMessage")
    second.validate()
    if not second.tool_calls or len(second.tool_calls) == 1:
        return _include_retry_metadata(first, second)
    return _safe_multi_tool_fallback(first, second)
