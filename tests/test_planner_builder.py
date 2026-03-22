"""Tests for Planner and Builder agents with mocked LLM."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from genesis.agents.builder import BuilderAgent
from genesis.agents.planner import PlannerAgent
from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.context.manager import ContextManager

SAMPLE_TASKS = """\
## Iteration 1 [#iter-1]

- [ ] Build widget [#build-widget]
    docs: docs/widget.md
- [~] Active widget [#active-widget]
"""


def _make_response(text="", stop_reason="end_turn", tool_calls=None,
                    input_tokens=100, output_tokens=50):
    content = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    if tool_calls:
        for i, tc in enumerate(tool_calls):
            content.append(SimpleNamespace(
                type="tool_use",
                id=tc.get("id", f"call_{i}"),
                name=tc["name"],
                input=tc.get("input", {}),
            ))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def env(tmp_path: Path):
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(SAMPLE_TASKS)
    bus = MessageBus(tmp_path / "messages")
    config = GenesisConfig(
        tasks_file=str(task_file),
        genesis_dir=str(tmp_path / ".genesis"),
    )
    cm = ContextManager(config, bus)
    mock_client = MagicMock()
    return config, bus, cm, mock_client, tmp_path


# --- Planner Agent Tests ---


class TestPlannerAgent:
    def test_has_planner_tools(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert "read_file" in agent.tool_map
        assert "write_file" in agent.tool_map
        assert "list_tasks" in agent.tool_map
        assert "update_task_status" not in agent.tool_map
        assert "add_task" in agent.tool_map

    def test_does_not_have_builder_tools(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert "git_create_branch" not in agent.tool_map
        assert "git_commit" not in agent.tool_map
        assert "git_open_pr" not in agent.tool_map
        assert "run_tests" not in agent.tool_map

    def test_name_is_planner(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert agent.name == "planner"

    def test_system_prompt_loaded(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert "Planner Agent" in agent._system_prompt

    def test_uses_planner_context(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        context = agent._build_context("#build-widget")
        combined = " ".join(m["content"] for m in context)
        assert "Build widget" in combined

    def test_run_simple_completion(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        client.messages.create.return_value = _make_response(
            "Design document written to docs/designs/build-widget.md"
        )
        result = agent.run("#build-widget")
        assert result.status == "completed"
        assert result.bookmark == "#build-widget"

    def test_run_with_tool_calls(self, env):
        config, bus, cm, client, tmp_path = env
        agent = PlannerAgent(
            config=config, bus=bus, context_manager=cm, client=client,
            project_root=tmp_path,
        )
        # Write a file the agent can read.
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "widget.py").write_text("class Widget: pass")

        client.messages.create.side_effect = [
            _make_response(
                stop_reason="tool_use",
                tool_calls=[{"name": "read_file", "input": {"path": "src/widget.py"}}],
            ),
            _make_response("Done planning."),
        ]

        result = agent.run("#build-widget")
        assert result.status == "completed"
        assert result.tool_calls == 1

    def test_publishes_events_to_bus(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        client.messages.create.return_value = _make_response("Planning complete.")

        agent.run("#build-widget")
        msgs = bus.for_task("#build-widget")
        assert len(msgs) > 0
        assert any(m.agent == "planner" for m in msgs)


# --- Builder Agent Tests ---


class TestBuilderAgent:
    def test_has_builder_tools(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert "read_file" in agent.tool_map
        assert "write_file" in agent.tool_map
        assert "list_tasks" in agent.tool_map
        assert "update_task_status" not in agent.tool_map
        assert "git_create_branch" in agent.tool_map
        assert "git_commit" in agent.tool_map
        assert "git_open_pr" in agent.tool_map
        assert "run_tests" in agent.tool_map

    def test_does_not_have_add_task(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert "add_task" not in agent.tool_map

    def test_name_is_builder(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert agent.name == "builder"

    def test_system_prompt_loaded(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert "Builder Agent" in agent._system_prompt

    def test_uses_builder_context(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        context = agent._build_context("#build-widget")
        combined = " ".join(m["content"] for m in context)
        assert "Build widget" in combined

    def test_run_simple_completion(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        client.messages.create.return_value = _make_response(
            "Implementation complete. All tests pass."
        )
        result = agent.run("#build-widget")
        assert result.status == "completed"
        assert result.bookmark == "#build-widget"

    def test_run_with_file_write(self, env):
        config, bus, cm, client, tmp_path = env
        agent = BuilderAgent(
            config=config, bus=bus, context_manager=cm, client=client,
            project_root=tmp_path,
        )

        client.messages.create.side_effect = [
            _make_response(
                stop_reason="tool_use",
                tool_calls=[{
                    "name": "write_file",
                    "input": {"path": "src/widget.py", "content": "class Widget:\n    pass\n"},
                }],
            ),
            _make_response("Wrote widget.py."),
        ]

        result = agent.run("#build-widget")
        assert result.status == "completed"
        assert (tmp_path / "src" / "widget.py").exists()

    def test_tool_definitions_registered(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        tool_names = [t["name"] for t in agent._tool_definitions]
        assert "read_file" in tool_names
        assert "git_commit" in tool_names
        assert "run_tests" in tool_names

    def test_publishes_events_to_bus(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        client.messages.create.return_value = _make_response("Build complete.")

        agent.run("#build-widget")
        msgs = bus.for_task("#build-widget")
        assert len(msgs) > 0
        assert any(m.agent == "builder" for m in msgs)


# --- Tool Schema Tests ---


class TestToolSchemas:
    def test_planner_tool_definitions_valid(self, env):
        config, bus, cm, client, _ = env
        agent = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        for tool_def in agent._tool_definitions:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def
            assert tool_def["input_schema"]["type"] == "object"

    def test_builder_tool_definitions_valid(self, env):
        config, bus, cm, client, _ = env
        agent = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        for tool_def in agent._tool_definitions:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def
            assert tool_def["input_schema"]["type"] == "object"

    def test_builder_has_more_tools_than_planner(self, env):
        config, bus, cm, client, _ = env
        planner = PlannerAgent(config=config, bus=bus, context_manager=cm, client=client)
        builder = BuilderAgent(config=config, bus=bus, context_manager=cm, client=client)
        assert len(builder._tool_definitions) > len(planner._tool_definitions)
