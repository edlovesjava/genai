"""Base agent with LLM loop, tool dispatch, budget tracking, and retry.

Subclasses (planner, builder) provide system prompts and tool sets.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import anthropic

from genesis.bus.message_bus import Message, MessageBus
from genesis.config import GenesisConfig
from genesis.context.manager import ContextManager

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result of an agent run."""

    bookmark: str
    status: str  # "completed", "blocked", "budget_exceeded", "error"
    summary: str
    tokens_used: int = 0
    tool_calls: int = 0


@dataclass
class BudgetTracker:
    """Tracks token usage against budget limits."""

    max_tokens: int
    warn_threshold: float = 0.8
    tokens_used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.tokens_used)

    @property
    def usage_ratio(self) -> float:
        if self.max_tokens == 0:
            return 1.0
        return self.tokens_used / self.max_tokens

    @property
    def warning(self) -> bool:
        return self.usage_ratio >= self.warn_threshold

    @property
    def exceeded(self) -> bool:
        return self.tokens_used >= self.max_tokens

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.tokens_used += input_tokens + output_tokens


class BaseAgent:
    """Base agent implementing the LLM tool-use loop.

    Subclasses should set `name`, `system_prompt`, and `tool_map`.
    """

    name: str = "base"

    def __init__(
        self,
        config: GenesisConfig,
        bus: MessageBus,
        context_manager: ContextManager,
        tool_map: dict[str, Callable[..., str]] | None = None,
        client: anthropic.Anthropic | None = None,
        max_tokens_budget: int | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.context_manager = context_manager
        self.tool_map: dict[str, Callable[..., str]] = tool_map or {}
        self.client = client or anthropic.Anthropic()
        self.budget = BudgetTracker(
            max_tokens=max_tokens_budget or 100_000,
            warn_threshold=config.budget.warn_threshold,
        )
        self._system_prompt: str = ""
        self._tool_definitions: list[dict] = []

    def load_system_prompt(self, path: str | Path) -> None:
        """Load system prompt from a markdown file."""
        p = Path(path)
        if p.exists():
            self._system_prompt = p.read_text()
        else:
            logger.warning("System prompt not found: %s", path)
            self._system_prompt = f"You are the {self.name} agent."

    def set_system_prompt(self, prompt: str) -> None:
        """Set system prompt directly."""
        self._system_prompt = prompt

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., str],
        input_schema: dict,
    ) -> None:
        """Register a tool for the agent to use."""
        self.tool_map[name] = handler
        self._tool_definitions.append({
            "name": name,
            "description": description,
            "input_schema": input_schema,
        })

    def run(self, task_bookmark: str, max_turns: int = 20) -> AgentResult:
        """Main loop: build context -> call LLM -> execute tools -> repeat."""
        messages = self._build_context(task_bookmark)
        n_initial = len(messages)
        tool_call_count = 0
        compact_every = 4  # Compact every N turns.

        for turn in range(max_turns):
            if self.budget.exceeded:
                self._publish_event(task_bookmark, "budget-exceeded", {
                    "tokens_used": self.budget.tokens_used,
                    "max_tokens": self.budget.max_tokens,
                })
                return AgentResult(
                    bookmark=task_bookmark,
                    status="budget_exceeded",
                    summary=f"Budget exceeded after {tool_call_count} tool calls.",
                    tokens_used=self.budget.tokens_used,
                    tool_calls=tool_call_count,
                )

            if self.budget.warning:
                logger.warning(
                    "%s: budget at %.0f%% (%d/%d tokens)",
                    self.name, self.budget.usage_ratio * 100,
                    self.budget.tokens_used, self.budget.max_tokens,
                )

            # Compact older messages periodically.
            if turn > 0 and turn % compact_every == 0:
                messages = self._compact_messages(
                    messages, n_initial=n_initial, keep_recent=4,
                )

            response = self._call_llm(messages)
            if response is None:
                return AgentResult(
                    bookmark=task_bookmark,
                    status="error",
                    summary="LLM call failed after retries.",
                    tokens_used=self.budget.tokens_used,
                    tool_calls=tool_call_count,
                )

            # Append assistant response.
            messages.append({"role": "assistant", "content": response.content})

            # Process any tool_use blocks in the response, regardless of
            # stop_reason.  When stop_reason is "max_tokens" the response may
            # still contain completed tool_use blocks that need tool_results;
            # omitting them corrupts the conversation and causes a 400 error.
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call_count += 1
                    result = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # If no tool calls were made, the agent is done.
            if not tool_results:
                summary = self._extract_text(response.content)
                self._checkpoint(task_bookmark, summary)
                return AgentResult(
                    bookmark=task_bookmark,
                    status="completed",
                    summary=summary,
                    tokens_used=self.budget.tokens_used,
                    tool_calls=tool_call_count,
                )

        return AgentResult(
            bookmark=task_bookmark,
            status="completed",
            summary=f"Reached max turns ({max_turns}).",
            tokens_used=self.budget.tokens_used,
            tool_calls=tool_call_count,
        )

    def _build_context(self, bookmark: str) -> list[dict]:
        """Build initial messages for the LLM. Override in subclasses."""
        return self.context_manager.build_planner_context(bookmark)

    def _compact_messages(
        self,
        messages: list[dict],
        n_initial: int = 0,
        keep_recent: int = 4,
    ) -> list[dict]:
        """Summarize older turns, keeping initial context and recent turns.

        Args:
            messages: Full message list.
            n_initial: Number of initial context messages to always preserve.
            keep_recent: Number of recent turn pairs (assistant+tool_result) to keep.
        """
        # Count turn pairs (assistant + tool_result = 2 messages per turn).
        turn_messages = messages[n_initial:]
        n_turn_msgs = keep_recent * 2

        if len(turn_messages) <= n_turn_msgs:
            return messages  # Nothing to compact.

        old_turns = turn_messages[:-n_turn_msgs]
        recent_turns = turn_messages[-n_turn_msgs:]

        summary = self.context_manager.summarize_for_checkpoint(old_turns)
        summary_msg = {"role": "user", "content": f"## Conversation Summary\n{summary}"}

        return messages[:n_initial] + [summary_msg] + recent_turns

    def _call_llm(
        self, messages: list[dict], max_retries: int = 0
    ) -> anthropic.types.Message | None:
        """Call the LLM with retry logic."""
        if max_retries == 0:
            max_retries = self.config.llm.max_retries

        for attempt in range(max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.config.llm.default_model,
                    "max_tokens": 16384,
                    "system": self._system_prompt,
                    "messages": messages,
                }
                if self._tool_definitions:
                    kwargs["tools"] = self._tool_definitions

                response = self.client.messages.create(**kwargs)

                self.budget.record(
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                self._publish_event("_internal", "llm-call", {
                    "model": self.config.llm.default_model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "attempt": attempt + 1,
                })
                return response

            except anthropic.RateLimitError:
                wait = 2 ** attempt
                logger.warning("Rate limited, retrying in %ds (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
            except anthropic.APIError as e:
                logger.error("API error on attempt %d: %s", attempt + 1, e)
                if attempt == max_retries - 1:
                    return None
                time.sleep(2 ** attempt)

        return None

    def _execute_tool(self, name: str, input_data: dict) -> str:
        """Dispatch a tool call to the registered handler."""
        if self.config.verbose.tool_trace:
            args_summary = ", ".join(f"{k}={v!r}" for k, v in input_data.items())
            logger.info("[%s] tool: %s(%s)", self.name, name, args_summary)
        handler = self.tool_map.get(name)
        if handler is None:
            return f"Error: Unknown tool '{name}'"
        try:
            return handler(**input_data)
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            return f"Error executing {name}: {e}"

    def _checkpoint(self, bookmark: str, summary: str) -> None:
        """Save a progress checkpoint to the bus."""
        self._publish_event(bookmark, "checkpoint", {"summary": summary})

    def _publish_event(self, bookmark: str, event: str, payload: dict) -> None:
        """Publish an event to the message bus."""
        msg = Message.create(
            agent=self.name,
            event=event,
            task_bookmark=bookmark,
            payload=payload,
        )
        self.bus.publish(msg)

    @staticmethod
    def _extract_text(content: list) -> str:
        """Extract text from response content blocks."""
        parts = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts) if parts else "No text response."
