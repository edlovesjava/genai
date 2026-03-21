"""Task operations tool — wraps quick-task API for agent use."""

from __future__ import annotations

from quick_task.api import (
    add_task as qt_add_task,
    get_task,
    list_tasks as qt_list_tasks,
    load_file,
)
from quick_task.models import TaskStatus

from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.state.machine import StateMachine


class TaskOps:
    """Tool interface for task operations."""

    def __init__(self, config: GenesisConfig, bus: MessageBus) -> None:
        self.config = config
        self.state_machine = StateMachine(bus, str(config.tasks_path))

    def list_tasks(
        self,
        list_name: str | None = None,
        status: str | None = None,
        flat: bool = False,
    ) -> str:
        """List tasks, optionally filtered by list name and status."""
        task_file = load_file(self.config.tasks_path)
        qt_status = _parse_status(status) if status else None
        tasks = qt_list_tasks(task_file, list_name=list_name, status=qt_status, flat=flat)
        if not tasks:
            return "No tasks found."
        lines = []
        for t in tasks:
            bookmark = f" [{t.bookmark}]" if t.bookmark else ""
            lines.append(f"- [{t.status.value}] {t.title}{bookmark}")
        return "\n".join(lines)

    def update_task_status(
        self, bookmark: str, to_status: str, actor: str, reason: str
    ) -> str:
        """Transition a task's status via the state machine."""
        self.state_machine.transition(bookmark, to_status, actor, reason)
        return f"Task {bookmark} transitioned to {to_status}."

    def add_task(
        self, title: str, list_name: str | None = None, parent: str | None = None
    ) -> str:
        """Add a new task to a list."""
        task_file = load_file(self.config.tasks_path)
        qt_add_task(task_file, title, list_name, parent_query=parent)
        return f"Added task: {title}"

    def get_task_status(self, bookmark: str) -> str:
        """Get the current Genesis status for a task."""
        status = self.state_machine.get_status(bookmark)
        return f"Task {bookmark} is {status}."

    def get_task_history(self, bookmark: str) -> str:
        """Get the transition history for a task."""
        history = self.state_machine.get_history(bookmark)
        if not history:
            return f"No transitions recorded for {bookmark}."
        lines = []
        for msg in history:
            lines.append(
                f"  {msg.timestamp}: {msg.payload['from']} → {msg.payload['to']} "
                f"by {msg.agent} ({msg.payload.get('reason', '')})"
            )
        return f"History for {bookmark}:\n" + "\n".join(lines)


def _parse_status(status: str) -> TaskStatus:
    """Parse a status string to TaskStatus enum."""
    mapping = {
        "todo": TaskStatus.TODO,
        "in_progress": TaskStatus.IN_PROGRESS,
        "in-progress": TaskStatus.IN_PROGRESS,
        "done": TaskStatus.DONE,
        "blocked": TaskStatus.BLOCKED,
    }
    key = status.lower().strip()
    if key not in mapping:
        raise ValueError(f"Unknown status: {status}. Valid: {list(mapping.keys())}")
    return mapping[key]
