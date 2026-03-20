"""Tests for the context manager."""

from pathlib import Path

import pytest

from genesis.bus.message_bus import Message, MessageBus
from genesis.config import GenesisConfig
from genesis.context.manager import ContextManager

SAMPLE_TASKS = """\
## Iteration 0 [#iter-0]

- [ ] Build API module [#build-api]
    depends: #iter-0
    docs: docs/design.md
    - [ ] Create api.py [#create-api]
    - [x] Write tests [#write-tests]
- [~] Active task [#active]
"""


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
    return cm, bus, tmp_path


class TestBuildPlannerContext:
    def test_includes_task_info(self, setup):
        cm, _, _ = setup
        context = cm.build_planner_context("#build-api")
        assert any("Build API module" in m["content"] for m in context)

    def test_includes_subtasks(self, setup):
        cm, _, _ = setup
        context = cm.build_planner_context("#build-api")
        combined = " ".join(m["content"] for m in context)
        assert "Create api.py" in combined
        assert "Write tests" in combined

    def test_includes_recent_messages(self, setup):
        cm, bus, _ = setup
        bus.publish(Message.create(
            agent="planner", event="assigned", task_bookmark="#build-api"
        ))
        context = cm.build_planner_context("#build-api")
        combined = " ".join(m["content"] for m in context)
        assert "planner" in combined

    def test_no_messages_still_works(self, setup):
        cm, _, _ = setup
        context = cm.build_planner_context("#active")
        assert len(context) >= 1  # At least the task info


class TestBuildBuilderContext:
    def test_includes_task_info(self, setup):
        cm, _, _ = setup
        context = cm.build_builder_context("#build-api")
        assert any("Build API module" in m["content"] for m in context)

    def test_returns_user_role_messages(self, setup):
        cm, _, _ = setup
        context = cm.build_builder_context("#active")
        for msg in context:
            assert msg["role"] == "user"


class TestSummarizeForCheckpoint:
    def test_extracts_assistant_messages(self, setup):
        cm, _, _ = setup
        messages = [
            {"role": "user", "content": "Do the thing."},
            {"role": "assistant", "content": "I'll start by reading the file."},
            {"role": "user", "content": "ok"},
            {"role": "assistant", "content": "Done. Created the module."},
        ]
        summary = cm.summarize_for_checkpoint(messages)
        assert "reading the file" in summary
        assert "Created the module" in summary

    def test_empty_messages(self, setup):
        cm, _, _ = setup
        summary = cm.summarize_for_checkpoint([])
        assert "No progress" in summary

    def test_limits_to_10(self, setup):
        cm, _, _ = setup
        messages = [
            {"role": "assistant", "content": f"Step {i}"}
            for i in range(20)
        ]
        summary = cm.summarize_for_checkpoint(messages)
        # Should only have last 10.
        assert "Step 10" in summary
        assert "Step 19" in summary
