"""Explicit, process-local registration entry point for the minimal Agent."""
# 流程：
# create_fixed_response_agent
#   → register_fixed_response_agent()
#   → 官方 registry
#   → build_agent(name, environment)
#   → FixedResponseAgent(...)

from tau2.registry import registry

from .minimal_agent import create_fixed_response_agent
from .v0_agent import create_v0_agent

AGENT_NAME = "ecommerce_after_sales_fixed_response"
# 这是 官方 Builder 查找我的 Agent 时使用的名字
V0_AGENT_NAME = "ecommerce_after_sales_v0"


def register_fixed_response_agent(name: str = AGENT_NAME) -> str:
    """Register this project's factory in the currently running tau2 process.

    tau2's registry is process-local.  Repeating this call with the same
    factory is safe for tests and notebook-like entry points; a different
    existing factory remains an explicit error rather than being overwritten.
    """
    existing = registry.get_agent_factory(name)
    if existing is None:
        registry.register_agent_factory(create_fixed_response_agent, name)
    elif existing is not create_fixed_response_agent:
        raise ValueError(f"Agent name '{name}' is already registered by another factory")
    return name


# 把 "ecommerce_after_sales_v0" → create_v0_agent 写入 Registry
def register_v0_agent(name: str = V0_AGENT_NAME) -> str:
    """Register the real-LLM V0 factory in the currently running tau2 process."""
    existing = registry.get_agent_factory(name)
    if existing is None:
        registry.register_agent_factory(create_v0_agent, name)
    elif existing is not create_v0_agent:
        raise ValueError(f"Agent name '{name}' is already registered by another factory")
    return name


def main() -> None:
    """Register the Agent and prove discovery without running a Simulation."""
    fixed_name = register_fixed_response_agent()
    v0_name = register_v0_agent()
    if registry.get_agent_factory(fixed_name) is not create_fixed_response_agent:
        raise RuntimeError("Fixed-response Agent factory could not be discovered")
    if registry.get_agent_factory(v0_name) is not create_v0_agent:
        raise RuntimeError("V0 Agent factory could not be discovered")
    print(f"Registered tau2 Agent factories: {fixed_name}, {v0_name}")


if __name__ == "__main__":
    main()
