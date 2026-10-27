"""V1-2 Reserve Agent：在 V1-2 之上为变更型 Tool Call 预留收尾转移。"""

from typing import Optional

from tau2.agent.base_agent import ValidAgentInputMessage
from tau2.data_model.message import AssistantMessage, SystemMessage
from tau2.environment.tool import Tool
from tau2.environment.toolkit import MUTATES_STATE_ATTR
from tau2.utils.llm_utils import generate

from .tool_call_recovery import generate_with_single_tool_call_recovery
from .v1_2_agent import V1_2Agent, V1_2AgentState


class V1_2ReserveAgent(V1_2Agent):
    """保留 V1-2 行为，并在预算不足时拒绝尚未执行的变更型调用。"""

    # 对 fresh text run 而言，当前 Agent decision 完成后，一次变更至少还需要：
    # AGENT→ENV、ENV→AGENT（接收 Tool Result）以及 AGENT→USER（正常收尾）。
    WRITE_COMPLETION_TRANSITIONS = 3
    # Harness 会在每次 step 后检查上限；因此还需一格余量，避免正常收尾恰好被 max_steps 覆盖。
    WRITE_CLOSURE_RESERVE_STEPS = WRITE_COMPLETION_TRANSITIONS + 1

    @staticmethod
    def _budget_message(state: V1_2AgentState) -> SystemMessage:
        """在原 Budget Context 上补充可验证的变更收尾条件。"""
        base = V1_2Agent._budget_message(state)
        content = base.content or ""
        reserve_lines = [
            "For a mutating Tool Call in this fresh text run, reserve at least "
            "four remaining budget steps: three post-decision role transitions "
            "(AGENT->ENV, ENV->AGENT for the Tool Result, and AGENT->USER for "
            "a truthful completion) plus one step of margin before the Harness cutoff.",
            "This is only a minimum closure reserve, not a Harness counter or a "
            "guarantee that the user will stop immediately.",
            "Submit a mutating Tool Call only after authentication, required "
            "business validation, complete action details, and explicit user "
            "confirmation are already present. If the reserve is unavailable, "
            "do not submit the change or claim success.",
        ]
        if state.candidate_order_count:
            reserve_lines.append(
                "When the authenticated user's request and existing history already "
                "authorize inspection of candidate orders, do not ask the user to "
                "repeat those identifiers or ask a redundant permission question. "
                "Continue with one necessary read at a time and stop reading once "
                "the request can be resolved."
            )
        return SystemMessage(
            role="system",
            content=content.replace("</step_budget>", "\n".join(reserve_lines) + "\n</step_budget>"),
        )

    def _is_mutating_tool(self, tool_name: str) -> bool:
        """从官方 Tool 元数据识别 mutation；缺失元数据时采用安全默认值。"""
        for tool in self.tools:
            if tool.name == tool_name:
                function = getattr(tool, "_func", None)
                return bool(getattr(function, MUTATES_STATE_ATTR, True))
        return True

    @classmethod
    def _has_write_completion_reserve(cls, state: V1_2AgentState) -> bool:
        """仅在可精确重构的 fresh run 中批准最小的 write 收尾预算。"""
        if not state.exact_budget or state.estimated_steps_used is None:
            return False
        remaining = state.max_steps - state.estimated_steps_used
        return remaining >= cls.WRITE_CLOSURE_RESERVE_STEPS

    @staticmethod
    def _budget_exhausted_write_response(response: AssistantMessage) -> AssistantMessage:
        """保留本次模型用量，但不把未执行的变更 Tool Call 写入 history。"""
        return AssistantMessage.text(
            "I have not submitted the requested change in this turn because there "
            "is not enough remaining conversation budget to safely process its tool "
            "result and provide a truthful completion. I cannot claim that the change "
            "was completed.",
            cost=response.cost,
            usage=response.usage,
            generation_time_seconds=response.generation_time_seconds,
        )

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: V1_2AgentState
    ) -> tuple[AssistantMessage, V1_2AgentState]:
        """保留 Grounding/History/Seed，并在 Tool 提交前应用收尾预算保护。"""
        self._validate_input_message(message)
        is_new_input = self._record_budget_input(message, state)
        if is_new_input:
            incoming = self._incoming_messages(message)
            state.messages.extend(incoming)
            state.availability_facts.update(self._facts_by_product(incoming))
            state.candidate_order_count = max(
                state.candidate_order_count, self._candidate_order_count(incoming)
            )

        context = list(state.system_messages)
        grounding_message = self._grounding_message(state)  # type: ignore[arg-type]
        if grounding_message is not None:
            context.append(grounding_message)
        context.append(self._budget_message(state))
        response = generate_with_single_tool_call_recovery(
            generate_fn=generate,
            model=self.llm,
            tools=self.tools,
            messages=context + state.messages,
            llm_args=self.llm_args,
            call_name="ecommerce_after_sales_v1_2_reserve",
        )
        if (
            response.tool_calls
            and len(response.tool_calls) == 1
            and self._is_mutating_tool(response.tool_calls[0].name)
            and not self._has_write_completion_reserve(state)
        ):
            response = self._budget_exhausted_write_response(response)
        state.messages.append(response)
        return response, state


def create_v1_2_reserve_agent(
    tools: list[Tool],
    domain_policy: str,
    **kwargs: object,
) -> V1_2ReserveAgent:
    """独立 Factory：不改变既有 V1-2 Agent 或其历史实验。"""
    llm = kwargs.get("llm") or "openai/gpt-4.1-mini"
    if not isinstance(llm, str):
        raise TypeError("llm must be a model-name string")
    llm_args = kwargs.get("llm_args")
    if llm_args is not None and not isinstance(llm_args, dict):
        raise TypeError("llm_args must be a dictionary or None")
    max_steps = kwargs.get("max_steps", 30)
    if not isinstance(max_steps, int):
        raise TypeError("max_steps must be an integer")
    fresh_start = kwargs.get("fresh_start", True)
    if not isinstance(fresh_start, bool):
        raise TypeError("fresh_start must be a boolean")
    return V1_2ReserveAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=llm,
        llm_args=llm_args,
        max_steps=max_steps,
        fresh_start=fresh_start,
    )
