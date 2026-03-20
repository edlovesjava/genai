"""Tests for GenesisRunner orchestrator and human gates."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.runner import GenesisRunner, HumanGateRequired
from genesis.state.machine import InvalidTransitionError

SAMPLE_TASKS = """\
## Iteration 1 [#iter-1]

- [ ] Build widget [#build-widget]
    docs: docs/widget.md
- [ ] Fix bug [#fix-bug]
"""


def _make_response(text="Done.", stop_reason="end_turn",
                    input_tokens=100, output_tokens=50):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def env(tmp_path: Path):
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(SAMPLE_TASKS)
    config = GenesisConfig(
        tasks_file=str(task_file),
        genesis_dir=str(tmp_path / ".genesis"),
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response()
    return config, mock_client, tmp_path


# --- Runner Construction ---


class TestRunnerInit:
    def test_creates_with_config(self, env):
        config, client, tmp_path = env
        runner = GenesisRunner(config=config, client=client, project_root=tmp_path)
        assert runner.config is config
        assert runner.bus is not None
        assert runner.state_machine is not None


# --- Planner Phase ---


class TestRunPlanner:
    def test_transitions_todo_to_in_progress(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        runner.run_planner("#build-widget")

        status = runner.state_machine.get_status("#build-widget")
        assert status == "IN_PROGRESS"

    def test_publishes_gate_event(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        runner.run_planner("#build-widget")

        gate_msgs = [
            m for m in runner.bus.for_task("#build-widget")
            if m.event == "gate-design_review"
        ]
        assert len(gate_msgs) == 1

    def test_raises_gate_when_rejected(self, env):
        config, client, tmp_path = env
        reject = lambda gt, bk, d: False
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=reject,
        )
        with pytest.raises(HumanGateRequired) as exc_info:
            runner.run_planner("#build-widget")

        assert exc_info.value.gate_type == "design_review"
        assert exc_info.value.bookmark == "#build-widget"

    def test_raises_gate_when_no_handler(self, env):
        config, client, tmp_path = env
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
        )
        with pytest.raises(HumanGateRequired):
            runner.run_planner("#build-widget")

    def test_returns_summary(self, env):
        config, client, tmp_path = env
        client.messages.create.return_value = _make_response("Design complete for widget.")
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        summary = runner.run_planner("#build-widget")
        assert "Design complete for widget." in summary


# --- Builder Phase ---


class TestRunBuilder:
    def _setup_in_progress(self, runner, bookmark):
        """Helper: move task to IN_PROGRESS state."""
        runner.state_machine.transition(bookmark, "ASSIGNED", "test", "setup")
        runner.state_machine.transition(bookmark, "IN_PROGRESS", "test", "setup")

    def test_transitions_to_in_review(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        self._setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        status = runner.state_machine.get_status("#build-widget")
        assert status == "IN_REVIEW"

    def test_rejects_wrong_state(self, env):
        config, client, tmp_path = env
        runner = GenesisRunner(config=config, client=client, project_root=tmp_path)
        # Task is still TODO.
        result = runner.run_builder("#build-widget")
        assert "expected IN_PROGRESS" in result

    def test_publishes_pr_review_gate(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        self._setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        gate_msgs = [
            m for m in runner.bus.for_task("#build-widget")
            if m.event == "gate-pr_review"
        ]
        assert len(gate_msgs) == 1


# --- Human Gate ---


class TestHumanGate:
    def test_gate_exception_has_fields(self):
        exc = HumanGateRequired("design_review", "#task-1", "needs review")
        assert exc.gate_type == "design_review"
        assert exc.bookmark == "#task-1"
        assert exc.detail == "needs review"

    def test_gate_handler_called_with_correct_args(self, env):
        config, client, tmp_path = env
        handler = MagicMock(return_value=True)
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=handler,
        )
        runner.run_planner("#build-widget")

        handler.assert_called_once()
        args = handler.call_args[0]
        assert args[0] == "design_review"
        assert args[1] == "#build-widget"


# --- Full Task Loop ---


class TestRunTask:
    def test_full_loop_planner_then_builder(self, env):
        config, client, tmp_path = env
        client.messages.create.side_effect = [
            _make_response("Design done."),
            _make_response("Build done."),
        ]
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        summary = runner.run_task("#build-widget")

        assert "Design done." in summary
        assert "Build done." in summary
        assert runner.state_machine.get_status("#build-widget") == "IN_REVIEW"

    def test_status_returns_cached_states(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        runner.run_task("#build-widget")
        status = runner.status()
        assert "#build-widget" in status
        assert status["#build-widget"] == "IN_REVIEW"


# --- End-to-End Integration Test (Mocked LLM) ---


class TestEndToEnd:
    """Full end-to-end test with mocked LLM simulating tool calls."""

    def test_planner_writes_design_then_builder_implements(self, env):
        """Simulate the full loop: planner writes a design doc, builder reads
        it and writes implementation code."""
        config, client, tmp_path = env

        # Planner response: calls write_file to create design doc, then completes.
        planner_tool_response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="call_1",
                    name="write_file",
                    input={
                        "path": "docs/designs/build-widget.md",
                        "content": "# Widget Design\n\nCreate a Widget class.\n",
                    },
                ),
            ],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=200, output_tokens=100),
        )
        planner_done = _make_response("Design document created.")

        # Builder response: calls write_file to create code, then completes.
        builder_tool_response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="call_2",
                    name="write_file",
                    input={
                        "path": "src/widget.py",
                        "content": "class Widget:\n    pass\n",
                    },
                ),
            ],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=200, output_tokens=100),
        )
        builder_done = _make_response("Implementation complete.")

        client.messages.create.side_effect = [
            planner_tool_response,
            planner_done,
            builder_tool_response,
            builder_done,
        ]

        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )

        summary = runner.run_task("#build-widget")

        # Verify files were created.
        design_file = tmp_path / "docs" / "designs" / "build-widget.md"
        assert design_file.exists()
        assert "Widget Design" in design_file.read_text()

        impl_file = tmp_path / "src" / "widget.py"
        assert impl_file.exists()
        assert "class Widget" in impl_file.read_text()

        # Verify state transitions.
        assert runner.state_machine.get_status("#build-widget") == "IN_REVIEW"

        # Verify bus has the full history.
        transitions = runner.state_machine.get_history("#build-widget")
        states = [(t.payload["from"], t.payload["to"]) for t in transitions]
        assert ("TODO", "ASSIGNED") in states
        assert ("ASSIGNED", "IN_PROGRESS") in states
        assert ("IN_PROGRESS", "IN_REVIEW") in states

    def test_planner_failure_stops_pipeline(self, env):
        """If planner fails (returns error), builder should not run."""
        config, client, tmp_path = env
        # Simulate LLM failure via API error.
        client.messages.create.side_effect = anthropic.APIError(
            message="server error",
            request=MagicMock(),
            body=None,
        )

        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        summary = runner.run_task("#fix-bug")
        assert "did not complete" in summary

        # Task should be ASSIGNED (planner didn't finish).
        assert runner.state_machine.get_status("#fix-bug") == "ASSIGNED"
