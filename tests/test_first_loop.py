"""First-loop integration test — simulates genesis running on a real quick-task
improvement (#qt-metadata) with realistic multi-step tool-using LLM responses.

This test validates the full pipeline:
  1. Planner reads existing code, writes design doc + test spec
  2. Human gate (auto-approved) for design review
  3. Builder reads design, writes implementation + tests, commits
  4. Human gate (auto-approved) for PR review
  5. State transitions traced through the full lifecycle
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from genesis.config import GenesisConfig
from genesis.runner import GenesisRunner

TASKS_MD = """\
## quick-task Improvements [#qt-improvements]

- [ ] Agent-oriented metadata fields [#qt-metadata]
    docs: spec/bootstrap-spec.md#agent-oriented-metadata
    - [ ] First-class fields: assignee, priority, created, updated [#qt-metadata-fields]
    - [ ] CLI flags: --assignee, --priority [#qt-metadata-cli]
    - [ ] Filter support: qt list --assignee @builder [#qt-metadata-filter]
"""

EXISTING_MODELS_PY = '''\
"""quick-task data models."""

from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    TODO = " "
    IN_PROGRESS = "~"
    BLOCKED = "!"
    DONE = "x"


@dataclass
class Task:
    title: str
    status: TaskStatus = TaskStatus.TODO
    bookmark: str = ""
    metadata: dict = field(default_factory=dict)
    children: list["Task"] = field(default_factory=list)
'''

DESIGN_DOC = """\
# Design: Agent-Oriented Metadata Fields (#qt-metadata)

## Overview
Add first-class metadata fields (assignee, priority, created, updated) to Task.

## Changes
- `src/quick_task/models.py`: Add fields to Task dataclass
- `src/quick_task/api.py`: Update add_task/update_status to set timestamps
- `tests/test_metadata.py`: Tests for metadata fields

## Decisions
- Fields stored in existing metadata dict for backward compatibility
- Property accessors on Task for typed access
- Timestamps in ISO 8601 format
"""

TEST_SPEC = """\
# Test Spec: Agent-Oriented Metadata Fields

## test_task_assignee
- Create task with assignee="@planner"
- Verify task.metadata["assignee"] == "@planner"

## test_task_priority
- Create task with priority=1
- Verify task.metadata["priority"] == 1

## test_task_timestamps
- Create task, verify "created" in metadata
- Update status, verify "updated" in metadata

## test_filter_by_assignee
- Create tasks with different assignees
- Filter by assignee, verify correct subset returned
"""

IMPL_CODE = '''\
"""quick-task data models with agent-oriented metadata."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TaskStatus(Enum):
    TODO = " "
    IN_PROGRESS = "~"
    BLOCKED = "!"
    DONE = "x"


@dataclass
class Task:
    title: str
    status: TaskStatus = TaskStatus.TODO
    bookmark: str = ""
    metadata: dict = field(default_factory=dict)
    children: list["Task"] = field(default_factory=list)

    @property
    def assignee(self) -> str | None:
        return self.metadata.get("assignee")

    @property
    def priority(self) -> int | None:
        return self.metadata.get("priority")

    @property
    def created(self) -> str | None:
        return self.metadata.get("created")

    @property
    def updated(self) -> str | None:
        return self.metadata.get("updated")
'''

TEST_CODE = '''\
"""Tests for agent-oriented metadata fields."""
from quick_task.models import Task, TaskStatus


def test_task_assignee():
    t = Task(title="Test", metadata={"assignee": "@planner"})
    assert t.assignee == "@planner"


def test_task_priority():
    t = Task(title="Test", metadata={"priority": 1})
    assert t.priority == 1


def test_task_no_metadata():
    t = Task(title="Test")
    assert t.assignee is None
    assert t.priority is None
    assert t.created is None
'''


def _resp(text="", stop_reason="end_turn", tool_calls=None, itok=200, otok=100):
    """Build a mock LLM response."""
    content = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    if tool_calls:
        for i, tc in enumerate(tool_calls):
            content.append(SimpleNamespace(
                type="tool_use", id=f"call_{i}",
                name=tc["name"], input=tc.get("input", {}),
            ))
    return SimpleNamespace(
        content=content, stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=itok, output_tokens=otok),
    )


@pytest.fixture
def project(tmp_path: Path):
    """Set up a minimal project tree for the first loop."""
    # TASKS.md
    (tmp_path / "TASKS.md").write_text(TASKS_MD)

    # Existing quick-task source the planner will read.
    src = tmp_path / "src" / "quick_task"
    src.mkdir(parents=True)
    (src / "models.py").write_text(EXISTING_MODELS_PY)
    (src / "__init__.py").write_text("")

    config = GenesisConfig(
        tasks_file=str(tmp_path / "TASKS.md"),
        genesis_dir=str(tmp_path / ".genesis"),
    )
    client = MagicMock()
    return config, client, tmp_path


class TestFirstLoop:
    """Simulate the genesis first-loop on #qt-metadata."""

    def test_full_planner_builder_pipeline(self, project):
        config, client, tmp_path = project

        # --- Planner LLM responses (3 turns) ---
        # Turn 1: read existing models.py
        planner_read = _resp(
            stop_reason="tool_use",
            tool_calls=[{"name": "read_file", "input": {"path": "src/quick_task/models.py"}}],
        )
        # Turn 2: write design doc + test spec
        planner_write = _resp(
            stop_reason="tool_use",
            tool_calls=[
                {
                    "name": "write_file",
                    "input": {
                        "path": "docs/designs/qt-metadata.md",
                        "content": DESIGN_DOC,
                    },
                },
                {
                    "name": "write_file",
                    "input": {
                        "path": "docs/designs/qt-metadata-tests.md",
                        "content": TEST_SPEC,
                    },
                },
            ],
        )
        # Turn 3: done
        planner_done = _resp("Design and test spec written for #qt-metadata.")

        # --- Builder LLM responses (3 turns) ---
        # Turn 1: read design doc
        builder_read = _resp(
            stop_reason="tool_use",
            tool_calls=[
                {"name": "read_file", "input": {"path": "docs/designs/qt-metadata.md"}},
                {"name": "read_file", "input": {"path": "docs/designs/qt-metadata-tests.md"}},
            ],
        )
        # Turn 2: write implementation + tests
        builder_write = _resp(
            stop_reason="tool_use",
            tool_calls=[
                {
                    "name": "write_file",
                    "input": {
                        "path": "src/quick_task/models.py",
                        "content": IMPL_CODE,
                    },
                },
                {
                    "name": "write_file",
                    "input": {
                        "path": "tests/test_metadata.py",
                        "content": TEST_CODE,
                    },
                },
            ],
        )
        # Turn 3: done
        builder_done = _resp("Implementation complete. Added metadata properties to Task.")

        client.messages.create.side_effect = [
            planner_read, planner_write, planner_done,
            builder_read, builder_write, builder_done,
        ]

        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=lambda gt, bk, d: True,
        )

        summary = runner.run_task("#qt-metadata")

        # --- Verify artifacts ---
        # Design doc created by planner.
        design = tmp_path / "docs" / "designs" / "qt-metadata.md"
        assert design.exists()
        assert "Agent-Oriented Metadata" in design.read_text()

        # Test spec created by planner.
        test_spec = tmp_path / "docs" / "designs" / "qt-metadata-tests.md"
        assert test_spec.exists()
        assert "test_task_assignee" in test_spec.read_text()

        # Implementation updated by builder.
        models = tmp_path / "src" / "quick_task" / "models.py"
        assert "assignee" in models.read_text()
        assert "priority" in models.read_text()

        # Tests written by builder.
        tests = tmp_path / "tests" / "test_metadata.py"
        assert tests.exists()
        assert "test_task_assignee" in tests.read_text()

        # --- Verify state transitions ---
        assert runner.state_machine.get_status("#qt-metadata") == "IN_REVIEW"
        history = runner.state_machine.get_history("#qt-metadata")
        transitions = [(h.payload["from"], h.payload["to"]) for h in history]
        assert transitions == [
            ("TODO", "ASSIGNED"),
            ("ASSIGNED", "IN_PROGRESS"),
            ("IN_PROGRESS", "IN_REVIEW"),
        ]

        # --- Verify bus activity ---
        all_msgs = runner.bus.for_task("#qt-metadata")
        agents_involved = {m.agent for m in all_msgs}
        assert "runner" in agents_involved
        assert "planner" in agents_involved
        assert "builder" in agents_involved

        # Gate events published.
        gate_events = [m for m in all_msgs if m.event.startswith("gate-")]
        assert len(gate_events) == 2
        gate_types = {m.payload["gate_type"] for m in gate_events}
        assert gate_types == {"design_review", "pr_review"}

    def test_planner_reads_existing_code(self, project):
        """Verify the planner's read_file tool returns actual file contents."""
        config, client, tmp_path = project

        read_results = []

        # Intercept: planner reads models.py, we capture what the tool returns.
        client.messages.create.side_effect = [
            _resp(
                stop_reason="tool_use",
                tool_calls=[{"name": "read_file", "input": {"path": "src/quick_task/models.py"}}],
            ),
            _resp("Read the models file."),
        ]

        runner = GenesisRunner(
            config=config, client=client, project_root=tmp_path,
            gate_handler=lambda gt, bk, d: True,
        )

        runner.run_planner("#qt-metadata")

        # Verify the LLM was called twice (tool call + completion).
        assert client.messages.create.call_count == 2

        # The second call should include tool results with the file contents.
        second_call = client.messages.create.call_args_list[1]
        messages = second_call.kwargs.get("messages", second_call[1].get("messages", []))
        # Find the tool_result message.
        tool_result_msgs = [
            m for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        assert len(tool_result_msgs) > 0
        # The tool result should contain the actual models.py content.
        result_content = tool_result_msgs[-1]["content"][0]["content"]
        assert "class TaskStatus" in result_content
        assert "class Task" in result_content

    def test_cli_entry_point_importable(self):
        """Verify the CLI entry point can be imported."""
        from genesis.__main__ import main
        assert callable(main)
