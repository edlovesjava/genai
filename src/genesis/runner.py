"""Genesis runner / orchestrator — drives the planner→builder task loop.

Coordinates state transitions, agent execution, and human gates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import anthropic

from genesis.agents.builder import BuilderAgent
from genesis.agents.planner import PlannerAgent
from genesis.bus.message_bus import Message, MessageBus
from genesis.config import GenesisConfig, load_config
from genesis.context.manager import ContextManager
from genesis.state.machine import StateMachine

logger = logging.getLogger(__name__)


class HumanGateRequired(Exception):
    """Raised when a human approval gate is required before continuing."""

    def __init__(self, gate_type: str, bookmark: str, detail: str = "") -> None:
        self.gate_type = gate_type
        self.bookmark = bookmark
        self.detail = detail
        super().__init__(f"Human gate '{gate_type}' required for {bookmark}: {detail}")


class GenesisRunner:
    """Entry point that drives the planner→builder agent loop."""

    def __init__(
        self,
        config: GenesisConfig | None = None,
        config_path: str | Path = "genesis.toml",
        client: anthropic.Anthropic | None = None,
        gate_handler: Callable[[str, str, str], bool] | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.config = config or load_config(config_path)
        self.project_root = project_root or Path.cwd()
        self.bus = MessageBus(self.config.messages_path)
        self.context_manager = ContextManager(self.config, self.bus)
        self.state_machine = StateMachine(self.bus, str(self.config.tasks_path))
        self.client = client
        self._gate_handler = gate_handler

    def run_planner(self, task_bookmark: str) -> str:
        """Run the planner phase for a task.

        1. TODO → ASSIGNED
        2. Run PlannerAgent
        3. ASSIGNED → IN_PROGRESS
        4. Trigger design review gate

        Returns the planner's summary.
        """
        # Step 1: transition to ASSIGNED.
        self.state_machine.transition(
            task_bookmark, "ASSIGNED", "runner", "Starting planner phase."
        )

        # Step 2: run planner agent.
        planner = PlannerAgent(
            config=self.config,
            bus=self.bus,
            context_manager=self.context_manager,
            client=self.client,
            max_tokens_budget=self.config.budget.planner_max_tokens,
            project_root=self.project_root,
        )
        result = planner.run(task_bookmark)

        if result.status != "completed":
            logger.warning(
                "Planner did not complete for %s: %s", task_bookmark, result.summary
            )
            return result.summary

        # Step 3: transition to IN_PROGRESS.
        self.state_machine.transition(
            task_bookmark, "IN_PROGRESS", "runner", "Planner completed design."
        )

        # Step 4: human design review gate.
        self._notify_gate("design_review", task_bookmark, result.summary)

        return result.summary

    def run_builder(self, task_bookmark: str) -> str:
        """Run the builder phase for a task.

        1. Run BuilderAgent (task should already be IN_PROGRESS)
        2. IN_PROGRESS → IN_REVIEW
        3. Trigger PR review gate

        Returns the builder's summary.
        """
        # Verify task is in the right state.
        current = self.state_machine.get_status(task_bookmark)
        if current != "IN_PROGRESS":
            return f"Cannot run builder: task {task_bookmark} is {current}, expected IN_PROGRESS."

        # Run builder agent.
        builder = BuilderAgent(
            config=self.config,
            bus=self.bus,
            context_manager=self.context_manager,
            client=self.client,
            max_tokens_budget=self.config.budget.builder_max_tokens,
            project_root=self.project_root,
        )
        result = builder.run(task_bookmark)

        if result.status != "completed":
            logger.warning(
                "Builder did not complete for %s: %s", task_bookmark, result.summary
            )
            return result.summary

        # Transition to IN_REVIEW.
        self.state_machine.transition(
            task_bookmark, "IN_REVIEW", "runner", "Builder completed implementation."
        )

        # Human PR review gate.
        self._notify_gate("pr_review", task_bookmark, result.summary)

        return result.summary

    def run_task(self, task_bookmark: str) -> str:
        """Run the full planner→builder loop for a task.

        Returns the final summary.
        """
        planner_summary = self.run_planner(task_bookmark)

        # Check if planner completed successfully (task should be IN_PROGRESS).
        current = self.state_machine.get_status(task_bookmark)
        if current != "IN_PROGRESS":
            return f"Planner phase did not complete. Status: {current}. {planner_summary}"

        builder_summary = self.run_builder(task_bookmark)
        return f"Planner: {planner_summary}\nBuilder: {builder_summary}"

    def status(self) -> dict[str, str]:
        """Return current Genesis status for all known tasks."""
        result: dict[str, str] = {}
        for bookmark, status in self.state_machine._status_cache.items():
            result[bookmark] = status
        return result

    def _notify_gate(self, gate_type: str, bookmark: str, detail: str) -> None:
        """Notify that a human gate is required.

        If a gate_handler was provided, call it. If it returns False,
        raise HumanGateRequired. If no handler, publish event and raise.
        """
        # Publish gate event to bus.
        msg = Message.create(
            agent="runner",
            event=f"gate-{gate_type}",
            task_bookmark=bookmark,
            payload={"gate_type": gate_type, "detail": detail},
        )
        self.bus.publish(msg)

        if self._gate_handler is not None:
            approved = self._gate_handler(gate_type, bookmark, detail)
            if not approved:
                raise HumanGateRequired(gate_type, bookmark, detail)
        else:
            # No handler — raise so caller can handle manually.
            raise HumanGateRequired(gate_type, bookmark, detail)
