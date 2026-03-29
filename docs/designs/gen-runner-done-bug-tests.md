# Test Specification: Runner Never Transitions Tasks to DONE

**Bookmark:** `#gen-runner-done-bug`
**Test file:** `tests/test_runner.py` (extend existing)

---

## 1. Test Strategy

All tests use the existing `env` fixture pattern:
- `tmp_path` with a written `TASKS.md`
- A `GenesisConfig` pointing at that file
- A `MagicMock` Anthropic client with configurable `side_effect`

No real LLM calls. State machine and bus use real implementations (no mocks) so transitions are properly validated.

Helper `_setup_in_progress(runner, bookmark)` is already defined in `TestRunBuilder` — reuse or promote to module-level fixture.

---

## 2. Fixture Additions

```python
SAMPLE_TASKS_WITH_SUBTASKS = """\
## Iteration 1 [#iter-1]

- [ ] Build widget [#build-widget]
    - [ ] Design widget [#widget-design]
    - [ ] Implement widget [#widget-impl]
- [ ] Fix bug [#fix-bug]
"""
```

Add a second fixture `env_with_subtasks` that uses `SAMPLE_TASKS_WITH_SUBTASKS` instead of `SAMPLE_TASKS`.

---

## 3. Test Cases

### 3.1 `TestRunBuilder` — DONE transition after gate approval

#### `test_transitions_to_done_after_gate_approval`
- **Arrange**: `gate_handler = lambda gt, bk, d: True` (auto-approve)
- **Act**: `_setup_in_progress(runner, "#build-widget")` → `runner.run_builder("#build-widget")`
- **Assert**: `runner.state_machine.get_status("#build-widget") == "DONE"`

#### `test_remains_in_review_when_gate_rejected`
- **Arrange**: `gate_handler = lambda gt, bk, d: False` (reject)
- **Act**: `_setup_in_progress(runner, "#build-widget")` → `pytest.raises(HumanGateRequired)` calling `runner.run_builder("#build-widget")`
- **Assert**: `runner.state_machine.get_status("#build-widget") == "IN_REVIEW"` (not DONE, not rolled back)

#### `test_publishes_done_transition_event`
- **Arrange**: auto-approve gate
- **Act**: full `run_builder`
- **Assert**: bus contains a `state-transition` message for `#build-widget` with `payload["to"] == "DONE"`

#### **Update existing test** `test_transitions_to_in_review`
- Change assertion from `status == "IN_REVIEW"` → `status == "DONE"` (since gate is auto-approved in that test)

---

### 3.2 `TestRunTask` — terminal state is DONE

#### **Update existing test** `test_full_loop_planner_then_builder`
- Change final assertion from `status == "IN_REVIEW"` → `status == "DONE"`

#### **Update existing test** `test_status_returns_cached_states`
- Change assertion from `status["#build-widget"] == "IN_REVIEW"` → `status["#build-widget"] == "DONE"`

#### `test_run_task_done_state_machine_event`
- **Arrange**: auto-approve gate, two LLM responses (planner done, builder done)
- **Act**: `runner.run_task("#build-widget")`
- **Assert**: `runner.state_machine.get_history("#build-widget")` contains a transition with `to == "DONE"`

---

### 3.3 `TestBudgetExceeded` — new class

#### `test_planner_budget_exceeded_marks_task_blocked`
- **Arrange**: configure mock client to return a response that causes the agent to report `budget_exceeded`. Best approach: set `config.budget.planner_max_tokens = 1` so the budget is exceeded on the first LLM response (the `BudgetTracker` will detect `tokens_used >= max_tokens` at start of next turn, or we can mock the agent directly).
  - Simpler: monkeypatch `PlannerAgent.run` to return `AgentResult(status="budget_exceeded", ...)`
- **Act**: `runner.run_planner("#build-widget")`
- **Assert**: `runner.state_machine.get_status("#build-widget") == "BLOCKED"`

#### `test_builder_budget_exceeded_marks_task_blocked`
- **Arrange**: monkeypatch `BuilderAgent.run` to return `AgentResult(status="budget_exceeded", ...)`
- **Act**: `_setup_in_progress(runner, "#build-widget")` → `runner.run_builder("#build-widget")`
- **Assert**: `runner.state_machine.get_status("#build-widget") == "BLOCKED"`

#### `test_budget_exceeded_publishes_blocked_transition`
- **Arrange**: monkeypatch builder as above
- **Act**: `run_builder`
- **Assert**: bus contains `state-transition` event with `payload["to"] == "BLOCKED"` for `#build-widget`

#### `test_budget_exceeded_does_not_trigger_gate`
- **Arrange**: monkeypatch builder to return budget_exceeded; gate_handler is a `MagicMock`
- **Act**: `run_builder`
- **Assert**: `gate_handler.assert_not_called()`

#### `test_planner_budget_exceeded_returns_summary`
- **Arrange**: monkeypatch planner to return `AgentResult(status="budget_exceeded", summary="Ran out.")`
- **Act**: `result = runner.run_planner("#build-widget")`
- **Assert**: `"Ran out." in result`

---

### 3.4 `TestSubtaskTracking` — new class

Uses `env_with_subtasks` fixture.

#### `test_subtasks_marked_done_after_builder_completes`
- **Arrange**: auto-approve gate; task `#build-widget` has subtasks `#widget-design` and `#widget-impl`
- **Act**: `_setup_in_progress(runner, "#build-widget")` → `runner.run_builder("#build-widget")`
- **Assert**:
  - `runner.state_machine.get_status("#widget-design") == "DONE"`
  - `runner.state_machine.get_status("#widget-impl") == "DONE"`

#### `test_subtasks_not_marked_done_when_gate_rejected`
- **Arrange**: gate_handler returns `False` (rejection)
- **Act**: `_setup_in_progress(runner, "#build-widget")` → expect `HumanGateRequired`
- **Assert**: subtasks are NOT `DONE` (they remain `TODO` or `IN_PROGRESS`)

#### `test_subtasks_already_done_skipped_gracefully`
- **Arrange**: auto-approve; manually mark one subtask `DONE` before running builder
  - Call `runner.state_machine.transition("#widget-design", "ASSIGNED", ...)` → `IN_PROGRESS` → `IN_REVIEW` → `DONE`
- **Act**: `run_builder("#build-widget")`
- **Assert**: No exception raised; `#widget-impl` is also `DONE`

#### `test_subtasks_not_marked_done_on_budget_exceeded`
- **Arrange**: monkeypatch builder to return `budget_exceeded`
- **Act**: `run_builder("#build-widget")`
- **Assert**: subtask states are NOT `DONE`

#### `test_task_without_subtasks_completes_normally`
- **Arrange**: use `env` (no subtasks), auto-approve gate
- **Act**: `run_builder("#build-widget")`
- **Assert**: `runner.state_machine.get_status("#build-widget") == "DONE"` (no error on empty subtask list)

---

### 3.5 `TestEndToEnd` — update

#### **Update** `test_planner_writes_design_then_builder_implements`
- Change final status assertion from `"IN_REVIEW"` → `"DONE"`

---

## 4. Mocking Strategy

| Component | Strategy |
|---|---|
| Anthropic client | `MagicMock` with `side_effect` list of `SimpleNamespace` responses (existing pattern) |
| `PlannerAgent.run` / `BuilderAgent.run` | `unittest.mock.patch` on the method to return a controlled `AgentResult` for budget tests |
| Gate handler | `lambda` or `MagicMock(return_value=True/False)` |
| File system | `pytest` `tmp_path` fixture (existing pattern) |
| State machine / bus | Real implementations (validates actual transition logic) |

### Monkeypatch helper for budget tests

```python
from unittest.mock import patch
from genesis.agents.base import AgentResult

budget_result = AgentResult(
    bookmark="#build-widget",
    status="budget_exceeded",
    summary="Budget exceeded after 2 tool calls.",
    tokens_used=50000,
    tool_calls=2,
)

with patch.object(BuilderAgent, "run", return_value=budget_result):
    runner.run_builder("#build-widget")
```

---

## 5. Edge Cases Covered

| Edge Case | Test |
|---|---|
| Gate rejects: task stays IN_REVIEW, not DONE | `test_remains_in_review_when_gate_rejected` |
| Gate rejects: subtasks not marked done | `test_subtasks_not_marked_done_when_gate_rejected` |
| Budget exceeded mid-planner (ASSIGNED state) | `test_planner_budget_exceeded_marks_task_blocked` |
| Budget exceeded mid-builder (IN_PROGRESS state) | `test_builder_budget_exceeded_marks_task_blocked` |
| Budget exceeded: no gate triggered | `test_budget_exceeded_does_not_trigger_gate` |
| Subtask already DONE before builder runs | `test_subtasks_already_done_skipped_gracefully` |
| Task has no subtasks | `test_task_without_subtasks_completes_normally` |
| Budget exceeded: subtasks not prematurely marked done | `test_subtasks_not_marked_done_on_budget_exceeded` |

---

## 6. Tests to Update (Existing)

| Test | Old Assertion | New Assertion |
|---|---|---|
| `TestRunBuilder::test_transitions_to_in_review` | `status == "IN_REVIEW"` | `status == "DONE"` |
| `TestRunTask::test_full_loop_planner_then_builder` | `status == "IN_REVIEW"` | `status == "DONE"` |
| `TestRunTask::test_status_returns_cached_states` | `status["#build-widget"] == "IN_REVIEW"` | `status["#build-widget"] == "DONE"` |
| `TestEndToEnd::test_planner_writes_design_then_builder_implements` | `status == "IN_REVIEW"` | `status == "DONE"` |
