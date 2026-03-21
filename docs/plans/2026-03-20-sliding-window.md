# Sliding Window on Message History — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent unbounded message growth in the agent LLM loop by summarizing older turns and keeping only recent ones.

**Architecture:** After every N turns (compact threshold), compress older assistant+tool turn pairs into a single summary message. Preserve the initial context messages (task info, docs, activity) and the last K turn pairs. Uses the existing `summarize_for_checkpoint()` as a foundation, enhanced to also capture tool call names/results.

**Tech Stack:** Python, pytest, unittest.mock

---

### Task 1: Enhance `summarize_for_checkpoint` to include tool results

**Files:**
- Modify: `src/genesis/context/manager.py:64-76`
- Test: `tests/test_context.py`

**Step 1: Write the failing test**

Add to `TestSummarizeForCheckpoint` in `tests/test_context.py`:

```python
def test_includes_tool_call_summaries(self, setup):
    cm, _, _ = setup
    messages = [
        {"role": "assistant", "content": [
            SimpleNamespace(type="tool_use", name="read_file", id="1",
                            input={"path": "src/foo.py"}),
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "1",
             "content": "def foo(): pass"},
        ]},
        {"role": "assistant", "content": [
            SimpleNamespace(type="text", text="I've read the file and it has one function."),
        ]},
    ]
    summary = cm.summarize_for_checkpoint(messages)
    assert "read_file" in summary
    assert "I've read the file" in summary
```

Import `SimpleNamespace` at the top of the test file:

```python
from types import SimpleNamespace
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_context.py::TestSummarizeForCheckpoint::test_includes_tool_call_summaries -v`
Expected: FAIL — current code only looks at `str` content, ignores list content blocks.

**Step 3: Write minimal implementation**

Replace `summarize_for_checkpoint` in `src/genesis/context/manager.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_context.py::TestSummarizeForCheckpoint -v`
Expected: ALL PASS (including existing tests — verify no regressions)

**Step 5: Commit**

```bash
git add src/genesis/context/manager.py tests/test_context.py
git commit -m "feat: enhance summarize_for_checkpoint to include tool calls"
```

---

### Task 2: Add `_compact_messages` method to BaseAgent

**Files:**
- Modify: `src/genesis/agents/base.py`
- Test: `tests/test_base_agent.py`

**Step 1: Write the failing test**

Add a new test class in `tests/test_base_agent.py`:

```python
class TestCompactMessages:
    def test_compacts_old_turns_keeps_recent(self, setup):
        agent, _, _ = setup
        # 2 initial context messages + 6 turn messages (3 assistant + 3 tool_result)
        messages = [
            {"role": "user", "content": "## Current Task\nTest task"},
            {"role": "user", "content": "## Design Documentation\nSome docs"},
            # Turn 1
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Reading the file."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "file contents"},
            ]},
            # Turn 2
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Updating the task."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "2", "content": "task updated"},
            ]},
            # Turn 3
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Writing the plan."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "3", "content": "plan written"},
            ]},
        ]
        compacted = agent._compact_messages(messages, n_initial=2, keep_recent=2)
        # Should have: 2 initial + 1 summary + 2 recent turn pairs (4 msgs) = 7
        assert len(compacted) == 7
        # Initial context preserved
        assert compacted[0]["content"] == "## Current Task\nTest task"
        assert compacted[1]["content"] == "## Design Documentation\nSome docs"
        # Summary message inserted
        assert "Progress so far" in compacted[2]["content"]
        assert compacted[2]["role"] == "user"
        # Recent turns preserved (turn 2 and 3)
        assert compacted[3]["role"] == "assistant"
        assert compacted[5]["role"] == "assistant"

    def test_no_compaction_when_few_messages(self, setup):
        agent, _, _ = setup
        messages = [
            {"role": "user", "content": "## Current Task\nTest task"},
            {"role": "assistant", "content": [
                SimpleNamespace(type="text", text="Done."),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "ok"},
            ]},
        ]
        compacted = agent._compact_messages(messages, n_initial=1, keep_recent=2)
        # Nothing to compact — only 1 turn pair, keep_recent=2
        assert len(compacted) == len(messages)
```

Add `from types import SimpleNamespace` to imports if not already there.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_base_agent.py::TestCompactMessages -v`
Expected: FAIL — `_compact_messages` does not exist yet.

**Step 3: Write minimal implementation**

Add method to `BaseAgent` in `src/genesis/agents/base.py`, after `_build_context`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_base_agent.py::TestCompactMessages -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/genesis/agents/base.py tests/test_base_agent.py
git commit -m "feat: add _compact_messages method to BaseAgent"
```

---

### Task 3: Integrate compaction into the `run()` loop

**Files:**
- Modify: `src/genesis/agents/base.py:122-193`
- Test: `tests/test_base_agent.py`

**Step 1: Write the failing test**

Add to `TestBaseAgentRun` in `tests/test_base_agent.py`:

```python
def test_compacts_messages_after_threshold(self, setup):
    """Verify message list is compacted during long-running loops."""
    agent, mock_client, _ = setup
    agent.register_tool(
        name="noop",
        description="Does nothing",
        handler=lambda: "ok",
        input_schema={"type": "object", "properties": {}},
    )

    call_count = 0
    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 10:
            return _make_response(
                "",
                stop_reason="tool_use",
                tool_calls=[{"name": "noop", "input": {}}],
                input_tokens=50,
                output_tokens=50,
            )
        return _make_response("All done.", input_tokens=50, output_tokens=50)

    mock_client.messages.create.side_effect = mock_create

    result = agent.run("#test-task", max_turns=15)
    assert result.status == "completed"

    # Check that later LLM calls received compacted messages.
    # The last call's messages arg should be shorter than 2*call_count + initial.
    last_call_kwargs = mock_client.messages.create.call_args
    last_messages = last_call_kwargs.kwargs.get("messages") or last_call_kwargs[1].get("messages")
    # Without compaction: 1 initial + 9*2 turn msgs = 19.
    # With compaction (keep_recent=4): 1 initial + 1 summary + 8 recent = 10.
    assert len(last_messages) < 19
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_agent.py::TestBaseAgentRun::test_compacts_messages_after_threshold -v`
Expected: FAIL — `len(last_messages)` will be 19 (no compaction happening yet).

**Step 3: Write minimal implementation**

Modify `run()` in `src/genesis/agents/base.py`. Add compaction after appending tool results (after line 185), and track `n_initial`:

```python
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

        # Check if we're done (no tool use).
        if response.stop_reason == "end_turn":
            summary = self._extract_text(response.content)
            self._checkpoint(task_bookmark, summary)
            return AgentResult(
                bookmark=task_bookmark,
                status="completed",
                summary=summary,
                tokens_used=self.budget.tokens_used,
                tool_calls=tool_call_count,
            )

        # Process tool calls.
        if response.stop_reason == "tool_use":
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
            messages.append({"role": "user", "content": tool_results})

    return AgentResult(
        bookmark=task_bookmark,
        status="completed",
        summary=f"Reached max turns ({max_turns}).",
        tokens_used=self.budget.tokens_used,
        tool_calls=tool_call_count,
    )
```

**Step 4: Run all tests to verify they pass**

Run: `pytest tests/test_base_agent.py -v`
Expected: ALL PASS (new test + all existing tests)

**Step 5: Run full test suite for regressions**

Run: `pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/genesis/agents/base.py tests/test_base_agent.py
git commit -m "feat: integrate message compaction into agent run loop"
```
