"""Context manager for building focused agent context.

Agents get only task-relevant context, not entire project history.
Priority: task spec > design doc > recent messages > code files.
"""

from __future__ import annotations

from pathlib import Path

from quick_task.api import get_task, load_file

from genesis.bus.message_bus import Message, MessageBus
from genesis.config import GenesisConfig


class ContextManager:
    """Builds focused context windows for planner and builder agents."""

    def __init__(self, config: GenesisConfig, bus: MessageBus) -> None:
        self.config = config
        self.bus = bus

    def build_planner_context(self, bookmark: str) -> list[dict]:
        """Build context for planner: task details + metadata + recent messages + docs."""
        parts: list[dict] = []

        # 1. Task details.
        task_info = self._get_task_info(bookmark)
        parts.append({"role": "user", "content": f"## Current Task\n{task_info}"})

        # 2. Design doc (if linked).
        doc_content = self._get_linked_docs(bookmark)
        if doc_content:
            parts.append({"role": "user", "content": f"## Design Documentation\n{doc_content}"})

        # 3. Recent bus messages for this task.
        messages_summary = self._get_recent_messages(bookmark, n=10)
        if messages_summary:
            parts.append({"role": "user", "content": f"## Recent Activity\n{messages_summary}"})

        return parts

    def build_builder_context(self, bookmark: str) -> list[dict]:
        """Build context for builder: task + design + tests + code + messages."""
        parts: list[dict] = []

        # 1. Task details.
        task_info = self._get_task_info(bookmark)
        parts.append({"role": "user", "content": f"## Current Task\n{task_info}"})

        # 2. Design doc.
        doc_content = self._get_linked_docs(bookmark)
        if doc_content:
            parts.append({"role": "user", "content": f"## Design Documentation\n{doc_content}"})

        # 3. Recent bus messages.
        messages_summary = self._get_recent_messages(bookmark, n=5)
        if messages_summary:
            parts.append({"role": "user", "content": f"## Recent Activity\n{messages_summary}"})

        return parts

    def summarize_for_checkpoint(self, messages: list[dict]) -> str:
        """Compress a conversation into a progress summary."""
        progress_lines = []
        for msg in messages:
            content = msg.get("content")
            if msg.get("role") == "assistant":
                if isinstance(content, str):
                    first_line = content.split("\n")[0].strip()
                    if first_line:
                        progress_lines.append(f"- {first_line}")
                elif isinstance(content, list):
                    for block in content:
                        if hasattr(block, "text") and block.text:
                            first_line = block.text.split("\n")[0].strip()
                            progress_lines.append(f"- {first_line}")
                        elif hasattr(block, "type") and block.type == "tool_use":
                            args = ", ".join(f"{k}={v}" for k, v in
                                             (block.input or {}).items())
                            progress_lines.append(f"- Called {block.name}({args})")
        if not progress_lines:
            return "No progress recorded yet."
        return "Progress so far:\n" + "\n".join(progress_lines[-10:])

    def _get_task_info(self, bookmark: str) -> str:
        """Get task details from the task file."""
        try:
            task_file = load_file(self.config.tasks_path)
            task = get_task(task_file, bookmark)
            lines = [
                f"Title: {task.title}",
                f"Bookmark: {task.bookmark or 'none'}",
                f"Status: {task.status.value}",
            ]
            depends = task.metadata.get("depends", "")
            if depends:
                lines.append(f"Dependencies: {depends}")
            docs = task.metadata.get("docs", "")
            if docs:
                lines.append(f"Docs: {docs}")
            if task.children:
                lines.append("Subtasks:")
                for child in task.children:
                    lines.append(f"  - [{child.status.value}] {child.title}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error loading task {bookmark}: {e}"

    def _get_linked_docs(self, bookmark: str) -> str:
        """Read linked documentation files for a task."""
        try:
            task_file = load_file(self.config.tasks_path)
            task = get_task(task_file, bookmark)
            docs = task.metadata.get("docs", "")
            if not docs:
                return ""
            limit = self.config.tools.max_read_chars
            parts = []
            for doc_path in docs.split(","):
                resolved = Path(doc_path)
                if resolved.exists():
                    content = resolved.read_text()
                    if len(content) > limit:
                        content = (
                            f"{content[:limit]}\n\n"
                            f"[Truncated: showing {limit:,} of {len(content):,} characters.]"
                        )
                    parts.append(f"### {doc_path}\n{content}")
                else:
                    parts.append(f"### {doc_path}\n(file not found)")
            return "\n\n".join(parts)
        except Exception:
            return ""

    def _get_recent_messages(self, bookmark: str, n: int = 10) -> str:
        """Get recent bus messages for a task."""
        messages = self.bus.for_task(bookmark)
        if not messages:
            return ""
        recent = messages[-n:]
        lines = []
        for msg in recent:
            lines.append(f"- [{msg.timestamp}] {msg.agent}: {msg.event}")
            if msg.payload:
                for key, value in msg.payload.items():
                    if isinstance(value, str) and len(value) < 200:
                        lines.append(f"    {key}: {value}")
        return "\n".join(lines)
