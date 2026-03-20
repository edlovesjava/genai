"""Configuration loader for Genesis.

Reads genesis.toml and provides typed access to settings.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-6"
    reasoning_model: str = "claude-opus-4-6"
    max_retries: int = 3


@dataclass
class BudgetConfig:
    planner_max_tokens: int = 100_000
    builder_max_tokens: int = 200_000
    daily_cap_tokens: int = 1_000_000
    warn_threshold: float = 0.8


@dataclass
class AgentConfig:
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)


@dataclass
class HumanGatesConfig:
    protected_paths: list[str] = field(default_factory=list)
    require_approval: list[str] = field(default_factory=list)


@dataclass
class GenesisConfig:
    project_name: str = "genesis"
    tasks_file: str = "TASKS.md"
    genesis_dir: str = ".genesis"
    llm: LLMConfig = field(default_factory=LLMConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    human_gates: HumanGatesConfig = field(default_factory=HumanGatesConfig)

    @property
    def tasks_path(self) -> Path:
        return Path(self.tasks_file)

    @property
    def genesis_path(self) -> Path:
        return Path(self.genesis_dir)

    @property
    def messages_path(self) -> Path:
        return self.genesis_path / "messages"


def load_config(path: str | Path = "genesis.toml") -> GenesisConfig:
    """Load configuration from a TOML file.

    Falls back to defaults for any missing keys.
    """
    config_path = Path(path)
    if not config_path.exists():
        return GenesisConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    genesis_section = raw.get("genesis", {})
    llm_section = raw.get("llm", {})
    budget_section = raw.get("budget", {})
    agents_section = raw.get("agents", {})
    gates_section = raw.get("human_gates", {})

    agents = {}
    for name, agent_raw in agents_section.items():
        agents[name] = AgentConfig(
            system_prompt=agent_raw.get("system_prompt", ""),
            tools=agent_raw.get("tools", []),
        )

    return GenesisConfig(
        project_name=genesis_section.get("project_name", "genesis"),
        tasks_file=genesis_section.get("tasks_file", "TASKS.md"),
        genesis_dir=genesis_section.get("genesis_dir", ".genesis"),
        llm=LLMConfig(**{k: v for k, v in llm_section.items() if k in LLMConfig.__dataclass_fields__}),
        budget=BudgetConfig(**{k: v for k, v in budget_section.items() if k in BudgetConfig.__dataclass_fields__}),
        agents=agents,
        human_gates=HumanGatesConfig(
            protected_paths=gates_section.get("protected_paths", []),
            require_approval=gates_section.get("require_approval", []),
        ),
    )
