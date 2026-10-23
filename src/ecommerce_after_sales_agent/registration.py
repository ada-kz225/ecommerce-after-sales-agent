"""Explicit, process-local registration entry point for the minimal Agent."""
# 流程：
# create_fixed_response_agent
#   → register_fixed_response_agent()
#   → 官方 registry
#   → build_agent(name, environment)
#   → FixedResponseAgent(...)

from tau2.registry import registry

from .minimal_agent import create_fixed_response_agent

AGENT_NAME = "ecommerce_after_sales_fixed_response"


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


def main() -> None:
    """Register the Agent and prove discovery without running a Simulation."""
    name = register_fixed_response_agent()
    if registry.get_agent_factory(name) is not create_fixed_response_agent:
        raise RuntimeError("Registered Agent factory could not be discovered")
    print(f"Registered tau2 Agent factory: {name}")


if __name__ == "__main__":
    main()
