"""Tests for the state machine."""

from pathlib import Path

import pytest

from genesis.bus.message_bus import MessageBus
from genesis.state.machine import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    StateMachine,
)

SAMPLE_TASKS = """\
## Tasks [#tasks]

- [ ] First task [#t1]
- [~] Active task [#t2]
- [?] Blocked task [#t3]
- [x] Done task [#t4]
"""


@pytest.fixture
def setup(tmp_path: Path):
    """Create a bus, task file, and state machine."""
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(SAMPLE_TASKS)
    bus = MessageBus(tmp_path / "messages")
    sm = StateMachine(bus, str(task_file))
    return sm, bus


class TestValidTransitions:
    def test_all_states_have_entries(self):
        expected = {"TODO", "ASSIGNED", "IN_PROGRESS", "BLOCKED", "IN_REVIEW", "REJECTED"}
        assert set(VALID_TRANSITIONS.keys()) == expected

    def test_done_is_terminal(self):
        assert "DONE" not in VALID_TRANSITIONS


class TestGetStatus:
    def test_todo_task(self, setup):
        sm, _ = setup
        assert sm.get_status("#t1") == "TODO"

    def test_in_progress_task(self, setup):
        sm, _ = setup
        assert sm.get_status("#t2") == "IN_PROGRESS"

    def test_blocked_task(self, setup):
        sm, _ = setup
        assert sm.get_status("#t3") == "BLOCKED"

    def test_done_task(self, setup):
        sm, _ = setup
        assert sm.get_status("#t4") == "DONE"


class TestCanTransition:
    def test_todo_to_assigned(self, setup):
        sm, _ = setup
        assert sm.can_transition("#t1", "ASSIGNED") is True

    def test_todo_to_done_invalid(self, setup):
        sm, _ = setup
        assert sm.can_transition("#t1", "DONE") is False

    def test_in_progress_to_blocked(self, setup):
        sm, _ = setup
        assert sm.can_transition("#t2", "BLOCKED") is True

    def test_in_progress_to_in_review(self, setup):
        sm, _ = setup
        assert sm.can_transition("#t2", "IN_REVIEW") is True


class TestTransition:
    def test_valid_transition(self, setup):
        sm, bus = setup
        sm.transition("#t1", "ASSIGNED", actor="planner", reason="Assigned for work")
        assert sm.get_status("#t1") == "ASSIGNED"
        # Check bus event was published.
        msgs = bus.for_task("#t1")
        assert len(msgs) == 1
        assert msgs[0].event == "state-transition"
        assert msgs[0].payload["from"] == "TODO"
        assert msgs[0].payload["to"] == "ASSIGNED"

    def test_invalid_transition_raises(self, setup):
        sm, _ = setup
        with pytest.raises(InvalidTransitionError, match="Cannot transition"):
            sm.transition("#t1", "DONE", actor="planner", reason="skip")

    def test_chained_transitions(self, setup):
        sm, bus = setup
        sm.transition("#t1", "ASSIGNED", actor="planner", reason="assign")
        sm.transition("#t1", "IN_PROGRESS", actor="builder", reason="start")
        sm.transition("#t1", "IN_REVIEW", actor="builder", reason="PR opened")
        sm.transition("#t1", "DONE", actor="human", reason="approved")
        assert sm.get_status("#t1") == "DONE"
        assert len(bus.for_task("#t1")) == 4

    def test_rejection_cycle(self, setup):
        sm, _ = setup
        sm.transition("#t1", "ASSIGNED", actor="planner", reason="assign")
        sm.transition("#t1", "IN_PROGRESS", actor="builder", reason="start")
        sm.transition("#t1", "IN_REVIEW", actor="builder", reason="PR opened")
        sm.transition("#t1", "REJECTED", actor="human", reason="needs changes")
        sm.transition("#t1", "IN_PROGRESS", actor="builder", reason="fixing")
        assert sm.get_status("#t1") == "IN_PROGRESS"

    def test_blocked_unblock_cycle(self, setup):
        sm, _ = setup
        sm.transition("#t2", "BLOCKED", actor="builder", reason="stuck")
        sm.transition("#t2", "IN_PROGRESS", actor="human", reason="unblocked")
        assert sm.get_status("#t2") == "IN_PROGRESS"


class TestGetHistory:
    def test_returns_only_transitions(self, setup):
        sm, bus = setup
        sm.transition("#t1", "ASSIGNED", actor="planner", reason="assign")
        # Publish a non-transition message.
        from genesis.bus.message_bus import Message
        bus.publish(Message.create(agent="planner", event="note", task_bookmark="#t1"))
        history = sm.get_history("#t1")
        assert len(history) == 1
        assert history[0].event == "state-transition"
