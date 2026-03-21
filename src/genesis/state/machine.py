"""Task state machine with bus-backed transition logging.

Genesis uses a richer state model than quick-task, mapping down to
quick-task's simpler statuses (TODO, IN_PROGRESS, BLOCKED, DONE) for storage.
"""

from __future__ import annotations

from quick_task.api import get_task, load_file, update_status
from quick_task.models import TaskStatus

from genesis.bus.message_bus import Message, MessageBus

VALID_TRANSITIONS: dict[str, list[str]] = {
    "TODO": ["ASSIGNED"],
    "ASSIGNED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["BLOCKED", "IN_REVIEW"],
    "BLOCKED": ["IN_PROGRESS"],
    "IN_REVIEW": ["DONE", "REJECTED"],
    "REJECTED": ["IN_PROGRESS"],
}

# Map Genesis states → quick-task TaskStatus for persistence.
QT_STATUS_MAP: dict[str, TaskStatus] = {
    "TODO": TaskStatus.TODO,
    "ASSIGNED": TaskStatus.IN_PROGRESS,
    "IN_PROGRESS": TaskStatus.IN_PROGRESS,
    "IN_REVIEW": TaskStatus.IN_PROGRESS,
    "BLOCKED": TaskStatus.BLOCKED,
    "DONE": TaskStatus.DONE,
    "REJECTED": TaskStatus.TODO,
}


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""


class StateMachine:
    """Manages task lifecycle with bus-logged transitions."""

    def __init__(self, bus: MessageBus, task_file: str) -> None:
        self.bus = bus
        self.task_file = task_file
        # In-memory map of bookmark → genesis status (richer than quick-task).
        self._status_cache: dict[str, str] = {}

    def get_status(self, bookmark: str) -> str:
        """Return the current Genesis status for a task."""
        if bookmark in self._status_cache:
            return self._status_cache[bookmark]
        # Derive from quick-task status on first access.
        tasks = load_file(self.task_file)
        task = get_task(tasks, bookmark)
        return _qt_to_genesis(task.status)

    def can_transition(self, bookmark: str, to_status: str) -> bool:
        """Check whether a transition is valid without performing it."""
        current = self.get_status(bookmark)
        return to_status in VALID_TRANSITIONS.get(current, [])

    def transition(
        self, bookmark: str, to_status: str, actor: str, reason: str
    ) -> None:
        """Perform a state transition, update quick-task, and publish to bus."""
        current = self.get_status(bookmark)
        allowed = VALID_TRANSITIONS.get(current, [])
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {bookmark} from {current} to {to_status}. "
                f"Allowed: {allowed}"
            )

        # Update quick-task file.
        qt_status = QT_STATUS_MAP[to_status]
        tasks = load_file(self.task_file)
        update_status(tasks, bookmark, qt_status, self.task_file)

        # Cache the genesis-level status.
        self._status_cache[bookmark] = to_status

        # Publish transition event.
        msg = Message.create(
            agent=actor,
            event="state-transition",
            task_bookmark=bookmark,
            payload={
                "from": current,
                "to": to_status,
                "reason": reason,
            },
        )
        self.bus.publish(msg)

    def get_history(self, bookmark: str) -> list[Message]:
        """Return all state-transition messages for a task."""
        return [
            m
            for m in self.bus.for_task(bookmark)
            if m.event == "state-transition"
        ]


def _qt_to_genesis(status: TaskStatus) -> str:
    """Map a quick-task status to a Genesis status (best guess)."""
    return {
        TaskStatus.TODO: "TODO",
        TaskStatus.IN_PROGRESS: "IN_PROGRESS",
        TaskStatus.BLOCKED: "BLOCKED",
        TaskStatus.DONE: "DONE",
    }.get(status, "TODO")
