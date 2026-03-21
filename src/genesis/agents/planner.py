"""Planner agent — reads tasks and produces design docs + test specs."""

from __future__ import annotations

from pathlib import Path

import anthropic

from genesis.agents.base import BaseAgent
from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.context.manager import ContextManager
from genesis.tools import FileOps, TaskOps

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"


class PlannerAgent(BaseAgent):
    """Agent that analyses a task and produces design + test spec documents."""

    name = "planner"

    def __init__(
        self,
        config: GenesisConfig,
        bus: MessageBus,
        context_manager: ContextManager,
        client: anthropic.Anthropic | None = None,
        max_tokens_budget: int | None = None,
        project_root: Path | None = None,
    ) -> None:
        super().__init__(
            config=config,
            bus=bus,
            context_manager=context_manager,
            client=client,
            max_tokens_budget=max_tokens_budget,
        )
        self._project_root = project_root or Path.cwd()

        # Load system prompt.
        prompt_path = PROMPTS_DIR / "planner_system.md"
        self.load_system_prompt(prompt_path)

        # Register planner tools.
        self._register_planner_tools(config, bus)

    def _build_context(self, bookmark: str) -> list[dict]:
        """Use planner-specific context."""
        return self.context_manager.build_planner_context(bookmark)

    def _register_planner_tools(self, config: GenesisConfig, bus: MessageBus) -> None:
        """Register the tools available to the planner."""
        file_ops = FileOps(config, self._project_root)
        task_ops = TaskOps(config, bus)

        self.register_tool(
            name="read_file",
            description="Read the contents of a file at the given path.",
            handler=file_ops.read_file,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read."},
                    "max_chars": {"type": "integer", "description": "Max characters to return. Defaults to config value (10000)."},
                },
                "required": ["path"],
            },
        )

        self.register_tool(
            name="write_file",
            description="Write content to a file at the given path.",
            handler=file_ops.write_file,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write."},
                    "content": {"type": "string", "description": "Content to write."},
                },
                "required": ["path", "content"],
            },
        )

        self.register_tool(
            name="list_tasks",
            description="List tasks from TASKS.md, optionally filtered by list name or status.",
            handler=task_ops.list_tasks,
            input_schema={
                "type": "object",
                "properties": {
                    "list_name": {"type": "string", "description": "Filter by list name."},
                    "status": {"type": "string", "description": "Filter by status (todo, in_progress, done, blocked)."},
                    "flat": {"type": "boolean", "description": "Flatten nested tasks."},
                },
            },
        )

        self.register_tool(
            name="update_task_status",
            description="Transition a task to a new status via the state machine.",
            handler=task_ops.update_task_status,
            input_schema={
                "type": "object",
                "properties": {
                    "bookmark": {"type": "string", "description": "Task bookmark (e.g. #my-task)."},
                    "to_status": {"type": "string", "description": "Target status."},
                    "actor": {"type": "string", "description": "Who is making this transition."},
                    "reason": {"type": "string", "description": "Why this transition is happening."},
                },
                "required": ["bookmark", "to_status", "actor", "reason"],
            },
        )

        self.register_tool(
            name="add_task",
            description="Add a new task or subtask to TASKS.md.",
            handler=task_ops.add_task,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title."},
                    "list_name": {"type": "string", "description": "Which list to add to."},
                    "parent": {"type": "string", "description": "Parent task bookmark for subtasks."},
                },
                "required": ["title"],
            },
        )
