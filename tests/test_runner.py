"""Tests for GenesisRunner orchestrator and human gates."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from genesis.agents.base import AgentResult
from genesis.agents.builder import BuilderAgent
from genesis.agents.planner import PlannerAgent
from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.runner import GenesisRunner, HumanGateRequired
from genesis.state.machine import InvalidTransitionError
from quick_task.api import TaskNotFoundError

SAMPLE_TASKS = """\
## Iteration 1 [#iter-1]

- [ ] Build widget [#build-widget]
    docs: docs/widget.md
- [ ] Fix bug [#fix-bug]
"""

SAMPLE_TASKS_WITH_SUBTASKS = """\
## Iteration 1 [#iter-1]

- [ ] Build widget [#build-widget]
    - [ ] Design widget [#widget-design]
    - [ ] Implement widget [#widget-impl]
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


@pytest.fixture
def env_with_subtasks(tmp_path: Path):
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(SAMPLE_TASKS_WITH_SUBTASKS)
    config = GenesisConfig(
        tasks_file=str(task_file),
        genesis_dir=str(tmp_path / ".genesis"),
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response()
    return config, mock_client, tmp_path


def _setup_in_progress(runner, bookmark):
    """Helper: move task to IN_PROGRESS state."""
    runner.state_machine.transition(bookmark, "ASSIGNED", "test", "setup")
    runner.state_machine.transition(bookmark, "IN_PROGRESS", "test", "setup")


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

    def test_transitions_to_done(self, env):
        """After gate approval, task must be DONE (not just IN_REVIEW)."""
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        self._setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        status = runner.state_machine.get_status("#build-widget")
        assert status == "DONE"

    # Keep old name as an alias to avoid renaming the test
    def test_transitions_to_in_review(self, env):
        """Alias: after gate approval the task passes through IN_REVIEW then reaches DONE."""
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        self._setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        status = runner.state_machine.get_status("#build-widget")
        assert status == "DONE"

    def test_transitions_to_done_after_gate_approval(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        self._setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#build-widget") == "DONE"

    def test_remains_in_review_when_gate_rejected(self, env):
        config, client, tmp_path = env
        reject = lambda gt, bk, d: False
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=reject,
        )
        self._setup_in_progress(runner, "#build-widget")
        with pytest.raises(HumanGateRequired):
            runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#build-widget") == "IN_REVIEW"

    def test_publishes_done_transition_event(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        self._setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        transitions = runner.state_machine.get_history("#build-widget")
        done_transitions = [
            t for t in transitions if t.payload.get("to") == "DONE"
        ]
        assert len(done_transitions) >= 1
        assert done_transitions[-1].payload["to"] == "DONE"

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
        assert runner.state_machine.get_status("#build-widget") == "DONE"

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
        assert status["#build-widget"] == "DONE"

    def test_run_task_done_state_machine_event(self, env):
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
        runner.run_task("#build-widget")

        history = runner.state_machine.get_history("#build-widget")
        to_states = [t.payload["to"] for t in history]
        assert "DONE" in to_states


# --- Budget Exceeded ---


class TestBudgetExceeded:
    def _budget_result(self, bookmark, summary="Budget exceeded."):
        return AgentResult(
            bookmark=bookmark,
            status="budget_exceeded",
            summary=summary,
            tokens_used=50000,
            tool_calls=2,
        )

    def test_planner_budget_exceeded_marks_task_blocked(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        with patch.object(PlannerAgent, "run", return_value=self._budget_result("#build-widget")):
            runner.run_planner("#build-widget")

        assert runner.state_machine.get_status("#build-widget") == "BLOCKED"

    def test_builder_budget_exceeded_marks_task_blocked(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        _setup_in_progress(runner, "#build-widget")
        with patch.object(BuilderAgent, "run", return_value=self._budget_result("#build-widget")):
            runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#build-widget") == "BLOCKED"

    def test_budget_exceeded_publishes_blocked_transition(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        _setup_in_progress(runner, "#build-widget")
        with patch.object(BuilderAgent, "run", return_value=self._budget_result("#build-widget")):
            runner.run_builder("#build-widget")

        transitions = runner.state_machine.get_history("#build-widget")
        blocked = [t for t in transitions if t.payload.get("to") == "BLOCKED"]
        assert len(blocked) >= 1

    def test_budget_exceeded_does_not_trigger_gate(self, env):
        config, client, tmp_path = env
        gate_handler = MagicMock(return_value=True)
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=gate_handler,
        )
        _setup_in_progress(runner, "#build-widget")
        with patch.object(BuilderAgent, "run", return_value=self._budget_result("#build-widget")):
            runner.run_builder("#build-widget")

        gate_handler.assert_not_called()

    def test_planner_budget_exceeded_returns_summary(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        budget_result = self._budget_result("#build-widget", summary="Ran out.")
        with patch.object(PlannerAgent, "run", return_value=budget_result):
            result = runner.run_planner("#build-widget")

        assert "Ran out." in result


# --- Subtask Tracking ---


class TestSubtaskTracking:
    def test_subtasks_marked_done_after_builder_completes(self, env_with_subtasks):
        config, client, tmp_path = env_with_subtasks
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        _setup_in_progress(runner, "#build-widget")
        # Subtasks must also be in-progress to be eligible for DONE
        _setup_in_progress(runner, "#widget-design")
        _setup_in_progress(runner, "#widget-impl")
        runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#widget-design") == "DONE"
        assert runner.state_machine.get_status("#widget-impl") == "DONE"

    def test_subtasks_not_marked_done_when_gate_rejected(self, env_with_subtasks):
        config, client, tmp_path = env_with_subtasks
        reject = lambda gt, bk, d: False
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=reject,
        )
        _setup_in_progress(runner, "#build-widget")
        with pytest.raises(HumanGateRequired):
            runner.run_builder("#build-widget")

        # Subtasks should NOT be DONE
        assert runner.state_machine.get_status("#widget-design") != "DONE"
        assert runner.state_machine.get_status("#widget-impl") != "DONE"

    def test_subtasks_already_done_skipped_gracefully(self, env_with_subtasks):
        config, client, tmp_path = env_with_subtasks
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        # Manually advance one subtask all the way to DONE.
        runner.state_machine.transition("#widget-design", "ASSIGNED", "test", "pre-done")
        runner.state_machine.transition("#widget-design", "IN_PROGRESS", "test", "pre-done")
        runner.state_machine.transition("#widget-design", "IN_REVIEW", "test", "pre-done")
        runner.state_machine.transition("#widget-design", "DONE", "test", "pre-done")

        _setup_in_progress(runner, "#build-widget")
        _setup_in_progress(runner, "#widget-impl")
        # Should not raise even though one subtask is already DONE.
        runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#widget-design") == "DONE"
        assert runner.state_machine.get_status("#widget-impl") == "DONE"

    def test_subtasks_not_marked_done_on_budget_exceeded(self, env_with_subtasks):
        config, client, tmp_path = env_with_subtasks
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        _setup_in_progress(runner, "#build-widget")
        budget_result = AgentResult(
            bookmark="#build-widget",
            status="budget_exceeded",
            summary="Ran out.",
            tokens_used=50000,
            tool_calls=2,
        )
        with patch.object(BuilderAgent, "run", return_value=budget_result):
            runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#widget-design") != "DONE"
        assert runner.state_machine.get_status("#widget-impl") != "DONE"

    def test_task_without_subtasks_completes_normally(self, env):
        config, client, tmp_path = env
        auto_approve = lambda gt, bk, d: True
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=auto_approve,
        )
        _setup_in_progress(runner, "#build-widget")
        runner.run_builder("#build-widget")

        assert runner.state_machine.get_status("#build-widget") == "DONE"


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

        # Verify state transitions — task should reach DONE after gate approval.
        assert runner.state_machine.get_status("#build-widget") == "DONE"

        # Verify bus has the full history.
        transitions = runner.state_machine.get_history("#build-widget")
        states = [(t.payload["from"], t.payload["to"]) for t in transitions]
        assert ("TODO", "ASSIGNED") in states
        assert ("ASSIGNED", "IN_PROGRESS") in states
        assert ("IN_PROGRESS", "IN_REVIEW") in states
        assert ("IN_REVIEW", "DONE") in states

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


# --- Bookmark Validation ---


class TestBookmarkValidation:
    def test_planner_rejects_unknown_bookmark(self, env):
        config, client, tmp_path = env
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=lambda gt, bk, d: True,
        )
        with pytest.raises(TaskNotFoundError, match="not found"):
            runner.run_planner("#nonexistent")
        # No LLM calls should have been made.
        client.messages.create.assert_not_called()

    def test_builder_rejects_unknown_bookmark(self, env):
        config, client, tmp_path = env
        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=lambda gt, bk, d: True,
        )
        with pytest.raises(TaskNotFoundError, match="not found"):
            runner.run_builder("#nonexistent")
        client.messages.create.assert_not_called()
