"""Tests for the base agent with mocked LLM."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from genesis.agents.base import AgentResult, BaseAgent, BudgetTracker
from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.context.manager import ContextManager

SAMPLE_TASKS = """\
## Tasks [#tasks]

- [ ] Test task [#test-task]
"""


def _make_response(text: str, stop_reason: str = "end_turn", tool_calls=None,
                    input_tokens: int = 100, output_tokens: int = 50):
    """Create a mock LLM response."""
    content = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    if tool_calls:
        for tc in tool_calls:
            content.append(SimpleNamespace(
                type="tool_use",
                id=tc.get("id", "call_123"),
                name=tc["name"],
                input=tc.get("input", {}),
            ))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def setup(tmp_path: Path):
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(SAMPLE_TASKS)
    bus = MessageBus(tmp_path / "messages")
    config = GenesisConfig(
        tasks_file=str(task_file),
        genesis_dir=str(tmp_path / ".genesis"),
    )
    cm = ContextManager(config, bus)
    mock_client = MagicMock()
    agent = BaseAgent(
        config=config,
        bus=bus,
        context_manager=cm,
        client=mock_client,
        max_tokens_budget=10_000,
    )
    agent.set_system_prompt("You are a test agent.")
    return agent, mock_client, bus


class TestBudgetTracker:
    def test_initial_state(self):
        bt = BudgetTracker(max_tokens=1000)
        assert bt.remaining == 1000
        assert bt.usage_ratio == 0.0
        assert not bt.warning
        assert not bt.exceeded

    def test_record_tokens(self):
        bt = BudgetTracker(max_tokens=1000)
        bt.record(300, 200)
        assert bt.tokens_used == 500
        assert bt.remaining == 500

    def test_warning_threshold(self):
        bt = BudgetTracker(max_tokens=1000, warn_threshold=0.8)
        bt.record(400, 400)
        assert bt.warning is True
        assert bt.exceeded is False

    def test_exceeded(self):
        bt = BudgetTracker(max_tokens=1000)
        bt.record(600, 500)
        assert bt.exceeded is True
        assert bt.remaining == 0


class TestBaseAgentRun:
    def test_simple_completion(self, setup):
        agent, mock_client, _ = setup
        mock_client.messages.create.return_value = _make_response(
            "Task completed successfully."
        )
        result = agent.run("#test-task")
        assert result.status == "completed"
        assert "completed" in result.summary.lower()
        assert result.tokens_used == 150
        assert result.tool_calls == 0

    def test_tool_use_then_completion(self, setup):
        agent, mock_client, _ = setup

        # Register a tool.
        agent.register_tool(
            name="read_file",
            description="Read a file",
            handler=lambda path: f"Contents of {path}",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )

        # First call: tool use. Second call: end_turn.
        mock_client.messages.create.side_effect = [
            _make_response(
                "",
                stop_reason="tool_use",
                tool_calls=[{"name": "read_file", "input": {"path": "foo.py"}}],
            ),
            _make_response("Done reading the file."),
        ]

        result = agent.run("#test-task")
        assert result.status == "completed"
        assert result.tool_calls == 1
        assert mock_client.messages.create.call_count == 2

    def test_unknown_tool_returns_error(self, setup):
        agent, mock_client, _ = setup

        mock_client.messages.create.side_effect = [
            _make_response(
                "",
                stop_reason="tool_use",
                tool_calls=[{"name": "nonexistent", "input": {}}],
            ),
            _make_response("OK, that tool doesn't exist."),
        ]

        result = agent.run("#test-task")
        assert result.status == "completed"

    def test_budget_exceeded_stops_loop(self, setup):
        agent, mock_client, _ = setup
        agent.budget = BudgetTracker(max_tokens=100, warn_threshold=0.8)

        # First call uses 150 tokens (over 100 budget).
        mock_client.messages.create.return_value = _make_response(
            "",
            stop_reason="tool_use",
            tool_calls=[{"name": "x", "input": {}}],
            input_tokens=80,
            output_tokens=70,
        )
        agent.tool_map["x"] = lambda: "ok"

        result = agent.run("#test-task")
        assert result.status == "budget_exceeded"

    def test_max_turns_limit(self, setup):
        agent, mock_client, _ = setup
        agent.tool_map["x"] = lambda: "ok"

        # Always return tool_use to force max turns.
        mock_client.messages.create.return_value = _make_response(
            "",
            stop_reason="tool_use",
            tool_calls=[{"name": "x", "input": {}}],
            input_tokens=1,
            output_tokens=1,
        )

        result = agent.run("#test-task", max_turns=3)
        assert result.status == "completed"
        assert "max turns" in result.summary.lower()
        assert result.tool_calls == 3

    def test_publishes_checkpoint_on_completion(self, setup):
        agent, mock_client, bus = setup
        mock_client.messages.create.return_value = _make_response("All done.")

        agent.run("#test-task")
        msgs = bus.for_task("#test-task")
        events = [m.event for m in msgs]
        assert "checkpoint" in events

    def test_compacts_messages_after_threshold(self, setup):
        """Verify message list is compacted during long-running loops."""
        agent, mock_client, _ = setup
        agent.register_tool(
            name="noop",
            description="Does nothing",
            handler=lambda: "ok",
            input_schema={"type": "object", "properties": {}},
        )

        call_count = 0
        def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 10:
                return _make_response(
                    "",
                    stop_reason="tool_use",
                    tool_calls=[{"name": "noop", "input": {}}],
                    input_tokens=50,
                    output_tokens=50,
                )
            return _make_response("All done.", input_tokens=50, output_tokens=50)

        mock_client.messages.create.side_effect = mock_create

        result = agent.run("#test-task", max_turns=15)
        assert result.status == "completed"

        # Check that later LLM calls received compacted messages.
        # The last call's messages arg should be shorter than 2*call_count + initial.
        last_call_kwargs = mock_client.messages.create.call_args
        last_messages = last_call_kwargs.kwargs.get("messages") or last_call_kwargs[1].get("messages")
        # Without compaction: 1 initial + 9*2 turn msgs = 19.
        # With compaction (keep_recent=4): should be much less than 19.
        assert len(last_messages) < 19


class TestBaseAgentPrompt:
    def test_load_system_prompt_from_file(self, setup, tmp_path):
        agent, _, _ = setup
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("You are a specialized agent.")
        agent.load_system_prompt(prompt_file)
        assert agent._system_prompt == "You are a specialized agent."

    def test_load_missing_prompt_uses_fallback(self, setup):
        agent, _, _ = setup
        agent.load_system_prompt("/nonexistent/prompt.md")
        assert "base" in agent._system_prompt

    def test_set_system_prompt(self, setup):
        agent, _, _ = setup
        agent.set_system_prompt("Custom prompt.")
        assert agent._system_prompt == "Custom prompt."


class TestBaseAgentRetry:
    def test_retries_on_api_error(self, setup):
        agent, mock_client, _ = setup
        import anthropic as anth

        # Fail twice, succeed on third.
        mock_client.messages.create.side_effect = [
            anth.APIError(message="server error", request=MagicMock(), body=None),
            anth.APIError(message="server error", request=MagicMock(), body=None),
            _make_response("Finally worked."),
        ]

        with patch("genesis.agents.base.time.sleep"):  # Skip actual sleep.
            result = agent.run("#test-task")
        assert result.status == "completed"

    def test_returns_error_after_max_retries(self, setup):
        agent, mock_client, _ = setup
        import anthropic as anth

        mock_client.messages.create.side_effect = anth.APIError(
            message="persistent error", request=MagicMock(), body=None
        )

        with patch("genesis.agents.base.time.sleep"):
            result = agent.run("#test-task")
        assert result.status == "error"
        assert "failed" in result.summary.lower()


class TestToolExecution:
    def test_tool_error_returns_message(self, setup):
        agent, _, _ = setup

        def failing_tool():
            raise ValueError("Something broke")

        agent.tool_map["bad_tool"] = failing_tool
        result = agent._execute_tool("bad_tool", {})
        assert "Error" in result
        assert "Something broke" in result

    def test_tool_with_kwargs(self, setup):
        agent, _, _ = setup
        agent.tool_map["greet"] = lambda name, greeting="hi": f"{greeting} {name}"
        result = agent._execute_tool("greet", {"name": "world", "greeting": "hello"})
        assert result == "hello world"


class TestCompactMessages:
    def test_compacts_old_turns_keeps_recent(self, setup):
        agent, _, _ = setup
        # 2 initial context messages + 6 turn messages (3 assistant + 3 tool_result)
        messages = [
            {"role": "user", "content": "## Current Task\nTest task"},
            {"role": "user", "content": "## Design Documentation\nSome docs"},
            # Turn 1
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Reading the file."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "file contents"},
            ]},
            # Turn 2
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Updating the task."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "2", "content": "task updated"},
            ]},
            # Turn 3
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Writing the plan."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "3", "content": "plan written"},
            ]},
        ]
        compacted = agent._compact_messages(messages, n_initial=2, keep_recent=2)
        # Should have: 2 initial + 1 summary + 2 recent turn pairs (4 msgs) = 7
        assert len(compacted) == 7
        # Initial context preserved
        assert compacted[0]["content"] == "## Current Task\nTest task"
        assert compacted[1]["content"] == "## Design Documentation\nSome docs"
        # Summary message inserted
        assert "Progress so far" in compacted[2]["content"]
        assert compacted[2]["role"] == "user"
        # Recent turns preserved (turn 2 and 3)
        assert compacted[3]["role"] == "assistant"
        assert compacted[5]["role"] == "assistant"

    def test_no_compaction_when_few_messages(self, setup):
        agent, _, _ = setup
        messages = [
            {"role": "user", "content": "## Current Task\nTest task"},
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Done."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "ok"},
            ]},
        ]
        compacted = agent._compact_messages(messages, n_initial=1, keep_recent=2)
        # Nothing to compact — only 1 turn pair, keep_recent=2
        assert len(compacted) == len(messages)
