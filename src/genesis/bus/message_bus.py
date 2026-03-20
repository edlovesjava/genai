"""Message bus for inter-agent communication.

One JSON file per message in .genesis/messages/.
Files are append-only (never modified after write).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Message:
    """A single message on the bus."""

    timestamp: str
    agent: str
    event: str
    task_bookmark: str
    payload: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        agent: str,
        event: str,
        task_bookmark: str,
        payload: dict | None = None,
    ) -> Message:
        """Create a message with the current UTC timestamp."""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            event=event,
            task_bookmark=task_bookmark,
            payload=payload or {},
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> Message:
        return cls(**json.loads(text))

    @property
    def filename(self) -> str:
        """Generate filename: {timestamp}_{agent}_{event}.json"""
        safe_ts = self.timestamp.replace(":", "-").replace("+", "p")
        return f"{safe_ts}_{self.agent}_{self.event}.json"


class MessageBus:
    """File-backed message bus using one JSON file per message."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def publish(self, msg: Message) -> Path:
        """Write a message to disk and return the file path."""
        path = self.root / msg.filename
        path.write_text(msg.to_json())
        return path

    def query(
        self,
        agent: str | None = None,
        event: str | None = None,
        task_bookmark: str | None = None,
    ) -> list[Message]:
        """Filter messages by agent, event, and/or task_bookmark."""
        messages = self._load_all()
        if agent is not None:
            messages = [m for m in messages if m.agent == agent]
        if event is not None:
            messages = [m for m in messages if m.event == event]
        if task_bookmark is not None:
            messages = [m for m in messages if m.task_bookmark == task_bookmark]
        return messages

    def recent(self, n: int) -> list[Message]:
        """Return the last N messages, ordered by timestamp."""
        messages = self._load_all()
        return messages[-n:]

    def for_task(self, bookmark: str) -> list[Message]:
        """Return all messages for a given task bookmark."""
        return self.query(task_bookmark=bookmark)

    def _load_all(self) -> list[Message]:
        """Load and sort all messages from disk."""
        messages = []
        for path in self.root.glob("*.json"):
            messages.append(Message.from_json(path.read_text()))
        messages.sort(key=lambda m: m.timestamp)
        return messages
