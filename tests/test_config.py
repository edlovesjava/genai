"""Tests for the config loader."""

from pathlib import Path

from genesis.config import GenesisConfig, load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path: Path):
        config = load_config(tmp_path / "missing.toml")
        assert config.project_name == "genesis"
        assert config.tasks_file == "TASKS.md"
        assert config.llm.provider == "anthropic"
        assert config.budget.daily_cap_tokens == 1_000_000

    def test_loads_from_file(self, tmp_path: Path):
        toml = tmp_path / "genesis.toml"
        toml.write_text("""\
[genesis]
project_name = "my-project"
tasks_file = "TODO.md"

[llm]
default_model = "claude-haiku-4-5-20251001"
max_retries = 5

[budget]
daily_cap_tokens = 500000

[agents.planner]
system_prompt = "prompts/planner.md"
tools = ["read_file", "list_tasks"]

[human_gates]
protected_paths = [".github/"]
require_approval = ["merge"]
""")
        config = load_config(toml)
        assert config.project_name == "my-project"
        assert config.tasks_file == "TODO.md"
        assert config.llm.default_model == "claude-haiku-4-5-20251001"
        assert config.llm.max_retries == 5
        assert config.llm.provider == "anthropic"  # default preserved
        assert config.budget.daily_cap_tokens == 500_000
        assert "planner" in config.agents
        assert config.agents["planner"].tools == ["read_file", "list_tasks"]
        assert config.human_gates.protected_paths == [".github/"]

    def test_partial_config(self, tmp_path: Path):
        toml = tmp_path / "genesis.toml"
        toml.write_text("[genesis]\nproject_name = \"partial\"\n")
        config = load_config(toml)
        assert config.project_name == "partial"
        assert config.llm.provider == "anthropic"  # default
        assert config.agents == {}

    def test_verbose_config_from_file(self, tmp_path: Path):
        toml = tmp_path / "genesis.toml"
        toml.write_text("[verbose]\ntool_trace = true\n")
        config = load_config(toml)
        assert config.verbose.tool_trace is True

    def test_verbose_config_defaults_to_off(self, tmp_path: Path):
        config = load_config(tmp_path / "missing.toml")
        assert config.verbose.tool_trace is False

    def test_path_properties(self):
        config = GenesisConfig(tasks_file="TASKS.md", genesis_dir=".genesis")
        assert config.tasks_path == Path("TASKS.md")
        assert config.genesis_path == Path(".genesis")
        assert config.messages_path == Path(".genesis/messages")
