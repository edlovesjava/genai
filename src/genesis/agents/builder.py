"""Builder agent — implements code based on design docs, runs tests, opens PRs."""

from __future__ import annotations

from pathlib import Path

import anthropic

from genesis.agents.base import BaseAgent
from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig
from genesis.context.manager import ContextManager
from genesis.tools import FileOps, GitOps, TaskOps, TestRunner

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"


class BuilderAgent(BaseAgent):
    """Agent that implements code from a design doc, tests, commits, and opens PRs."""

    name = "builder"

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
        prompt_path = PROMPTS_DIR / "builder_system.md"
        self.load_system_prompt(prompt_path)

        # Register builder tools.
        self._register_builder_tools(config, bus)

    def _build_context(self, bookmark: str) -> list[dict]:
        """Use builder-specific context."""
        return self.context_manager.build_builder_context(bookmark)

    def _register_builder_tools(self, config: GenesisConfig, bus: MessageBus) -> None:
        """Register the tools available to the builder."""
        file_ops = FileOps(config, self._project_root)
        task_ops = TaskOps(config, bus)
        git_ops = GitOps(config, self._project_root)
        test_runner = TestRunner(config, self._project_root)

        self.register_tool(
            name="read_file",
            description="Read the contents of a file at the given path.",
            handler=file_ops.read_file,
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path to read."}},
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
                    "status": {"type": "string", "description": "Filter by status."},
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
                    "bookmark": {"type": "string", "description": "Task bookmark."},
                    "to_status": {"type": "string", "description": "Target status."},
                    "actor": {"type": "string", "description": "Who is making this transition."},
                    "reason": {"type": "string", "description": "Why."},
                },
                "required": ["bookmark", "to_status", "actor", "reason"],
            },
        )

        self.register_tool(
            name="git_create_branch",
            description="Create and switch to a new git branch.",
            handler=git_ops.git_create_branch,
            input_schema={
                "type": "object",
                "properties": {
                    "branch_name": {"type": "string", "description": "Name for the new branch."},
                },
                "required": ["branch_name"],
            },
        )

        self.register_tool(
            name="git_commit",
            description="Stage files and create a git commit.",
            handler=git_ops.git_commit,
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message."},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files to stage. If empty, stages all changes.",
                    },
                },
                "required": ["message"],
            },
        )

        self.register_tool(
            name="git_open_pr",
            description="Open a pull request via the gh CLI.",
            handler=git_ops.git_open_pr,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "PR title."},
                    "body": {"type": "string", "description": "PR description."},
                    "base": {"type": "string", "description": "Base branch (default: main)."},
                },
                "required": ["title", "body"],
            },
        )

        self.register_tool(
            name="run_tests",
            description="Run pytest and return the results.",
            handler=test_runner.run_tests,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Test file or directory."},
                    "verbose": {"type": "boolean", "description": "Verbose output."},
                    "keyword": {"type": "string", "description": "Filter tests by keyword."},
                },
            },
        )
