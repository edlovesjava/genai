# Design: Runner Never Transitions Tasks to DONE

**Bookmark:** `#gen-runner-done-bug`
**Status:** Draft
**Subtasks:**
- `#gen-done-transition` — Add IN_REVIEW → DONE transition after human gate approval
- `#gen-budget-blocked` — Mark task BLOCKED on budget_exceeded instead of silent warning
- `#gen-subtask-tracking` — Runner should mark subtasks done as builder completes them

---

## 1. Problem Summary

The `GenesisRunner` in `src/genesis/runner.py` never reaches a terminal DONE state for tasks. Three concrete gaps:

1. **No IN_REVIEW → DONE transition.** After `run_builder()` triggers the `pr_review` gate, the task stays in `IN_REVIEW` indefinitely. Even when the gate handler approves, no transition to DONE is performed.

2. **Budget exceeded is silent.** When `BaseAgent.run()` returns `status="budget_exceeded"` the runner logs a warning and returns the summary — but the task stays in its current Genesis state rather than being marked `BLOCKED`.

3. **Subtasks are never marked done.** When the builder completes, only the parent task transitions to IN_REVIEW. Individual subtasks listed in `TASKS.md` remain untouched.

---

## 2. Changes Required

### 2.1 `src/genesis/runner.py` — `run_builder()`

**Fix 1 — IN_REVIEW → DONE on gate approval.**

After the builder finishes and the `pr_review` gate is triggered, the gate handler's return value already indicates approval (returns `True`) or rejection (raises `HumanGateRequired`). So if `_notify_gate` returns without raising, the gate was approved and we must transition to DONE.

```python
# After _notify_gate call in run_builder():
self.state_machine.transition(
    task_bookmark, "DONE", "runner", "PR review approved."
)
```

**Fix 2 — BLOCKED on budget_exceeded.**

In both `run_planner()` and `run_builder()`, when the agent result has `status == "budget_exceeded"`, the runner should transition the task to `BLOCKED` (from its current state, which is `IN_PROGRESS` for planner's builder run, or `ASSIGNED` transitioning to `IN_PROGRESS` for planner) and publish an explanatory message. Currently the code falls through to `logger.warning` only.

```python
if result.status == "budget_exceeded":
    self.state_machine.transition(
        task_bookmark, "BLOCKED", "runner",
        f"Budget exceeded: {result.summary}"
    )
    return result.summary
```

The state machine already supports `IN_PROGRESS → BLOCKED`. We need to ensure the planner path handles this too.

**Fix 3 — Subtask tracking.**

The builder receives the parent `task_bookmark`. Subtasks are listed in `TASKS.md` under the parent. When the builder completes successfully (before the gate transition), the runner should iterate the parent task's children and mark each subtask `DONE` via `state_machine.transition()`.

We need a helper in `TaskOps` (or use the quick-task API directly in the runner) to fetch child tasks. The quick-task `load_file()` / `get_task()` API returns a `Task` object; we need to check if it exposes `subtasks` or `children`.

#### Subtask lookup strategy

Looking at the existing code (`src/genesis/tools/task_ops.py` and `quick_task.api`), `get_task()` returns a `Task` that has a `.subtasks` list (the quick-task model). The runner will:

1. Call `get_task(task_file, parent_bookmark)` to retrieve the parent.
2. Iterate `task.subtasks` — each has a `.bookmark` attribute.
3. For each subtask whose current status is NOT already `DONE`, transition it to `DONE`.

This must happen **after** the builder's `IN_PROGRESS → IN_REVIEW` transition (all subtasks implicitly become done when the parent moves to review). However, subtask transitions must be guarded: if the subtask bookmark isn't in the state machine cache it will derive from quick-task status, so we call `can_transition` first.

---

## 3. Detailed File Changes

### `src/genesis/runner.py`

#### `run_planner()` — budget guard

```python
result = planner.run(task_bookmark, max_turns=planner_max_turns)

if result.status == "budget_exceeded":
    # Task is currently ASSIGNED; we can't go to BLOCKED from ASSIGNED,
    # so first complete transition to IN_PROGRESS, then block.
    self.state_machine.transition(
        task_bookmark, "IN_PROGRESS", "runner",
        "Planner budget exceeded — moving to IN_PROGRESS before blocking."
    )
    self.state_machine.transition(
        task_bookmark, "BLOCKED", "runner",
        f"Planner budget exceeded: {result.summary}"
    )
    return result.summary

if result.status != "completed":
    logger.warning(...)
    return result.summary
```

> **Note on ASSIGNED → BLOCKED**: The current `VALID_TRANSITIONS` does NOT allow `ASSIGNED → BLOCKED` directly. Rather than modifying the state machine (risk of wider side-effects), we perform a two-hop transition: `ASSIGNED → IN_PROGRESS → BLOCKED`. This is semantically accurate (the agent started work but ran out of budget).

#### `run_builder()` — budget guard

```python
result = builder.run(task_bookmark, max_turns=builder_max_turns)

if result.status == "budget_exceeded":
    self.state_machine.transition(
        task_bookmark, "BLOCKED", "runner",
        f"Builder budget exceeded: {result.summary}"
    )
    return result.summary

if result.status != "completed":
    logger.warning(...)
    return result.summary
```

Task is `IN_PROGRESS` when builder runs, so `IN_PROGRESS → BLOCKED` is valid.

#### `run_builder()` — DONE transition after gate

```python
# Human PR review gate.
self._notify_gate("pr_review", task_bookmark, result.summary)

# Gate approved (no exception raised) — mark subtasks then parent DONE.
self._mark_subtasks_done(task_bookmark)
self.state_machine.transition(
    task_bookmark, "DONE", "runner", "PR review approved."
)

return result.summary
```

#### New private method `_mark_subtasks_done()`

```python
def _mark_subtasks_done(self, task_bookmark: str) -> None:
    """Mark all subtasks of a task as DONE if not already done."""
    try:
        task_file = load_file(str(self.config.tasks_path))
        task = get_task(task_file, task_bookmark)
    except TaskNotFoundError:
        return

    for subtask in getattr(task, "subtasks", []):
        bm = getattr(subtask, "bookmark", None)
        if not bm:
            continue
        try:
            current = self.state_machine.get_status(bm)
            if current == "DONE":
                continue
            # Ensure subtask is in a state that can reach DONE.
            if self.state_machine.can_transition(bm, "IN_REVIEW"):
                self.state_machine.transition(
                    bm, "IN_REVIEW", "runner",
                    "Parent task completed — marking subtask in review."
                )
            if self.state_machine.can_transition(bm, "DONE"):
                self.state_machine.transition(
                    bm, "DONE", "runner",
                    "Parent task approved — marking subtask done."
                )
        except Exception as exc:
            logger.warning("Could not mark subtask %s done: %s", bm, exc)
```

> **Design decision**: Subtask state promotion uses a two-hop `→ IN_REVIEW → DONE` because the state machine requires valid transitions. Swallowing individual subtask errors (via the `except`) prevents one bad subtask from blocking the whole parent completion.

---

## 4. State Machine — No Changes Required

`VALID_TRANSITIONS` already contains:
- `IN_REVIEW → DONE` ✓
- `IN_PROGRESS → BLOCKED` ✓

No changes to `src/genesis/state/machine.py` needed.

---

## 5. `run_task()` — Expected Terminal State After Fix

```
run_planner() → IN_PROGRESS (gate approved)
run_builder() → IN_REVIEW → DONE (gate approved)
```

The existing `test_runner.py::TestRunTask::test_full_loop_planner_then_builder` asserts `status == "IN_REVIEW"` at the end — this test must be updated to expect `"DONE"`.

---

## 6. Trade-offs & Constraints

| Decision | Rationale |
|---|---|
| Two-hop `ASSIGNED → IN_PROGRESS → BLOCKED` for planner budget | Avoids widening VALID_TRANSITIONS; semantically correct |
| Subtask errors are swallowed with a warning | Resilience: one bad bookmark shouldn't break parent completion |
| Subtask DONE done via `IN_REVIEW → DONE` hops | State machine invariant: every state must follow valid edges |
| DONE transition happens **after** gate approval, inside `run_builder` | Gate approval is the signal for completion; keeps gate logic self-contained |

---

## 7. Files Modified

| File | Change |
|---|---|
| `src/genesis/runner.py` | `run_builder()` DONE transition + subtask loop; `run_planner()` + `run_builder()` budget guard; new `_mark_subtasks_done()` |
| `tests/test_runner.py` | Update `IN_REVIEW` assertions → `DONE`; add new test cases |
