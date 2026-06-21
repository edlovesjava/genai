---
id: genesis.state-machine
title: Task State Machine
status: active
abstraction: model
source: [../../src/genesis/state/machine.py]
depends: []
---

# Task State Machine

A reverse-engineered, high-fidelity model of Genesis's existing task state
machine. It demonstrates that the speckit format describes **shipped code** as
faithfully as it plans new work: every claim below is true of
`src/genesis/state/machine.py` today.

## Intent

Govern the lifecycle of a task through the V-Model workflow, enforcing that only
legal status transitions occur and that every transition is recorded. Genesis
uses a richer six-state model than quick-task; this component owns the mapping
between the two and is the single authority on "what state is this task in, and
where may it go next."

## Structure

- **`StateMachine`** — constructed with a `MessageBus` and a `task_file` path.
  Holds an in-memory `bookmark → status` cache richer than what quick-task
  persists.
- **`VALID_TRANSITIONS`** — the legal transition graph:
  `TODO→ASSIGNED→IN_PROGRESS→{BLOCKED, IN_REVIEW}`, `BLOCKED→IN_PROGRESS`,
  `IN_REVIEW→{DONE, REJECTED}`, `REJECTED→IN_PROGRESS`.
- **`QT_STATUS_MAP`** — lowers each of the six Genesis states onto one of
  quick-task's four storage statuses (`TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`).
- **`InvalidTransitionError`** — raised on an illegal transition request.
- Operations: `get_status`, `can_transition`, `transition`, `get_history`.

## Behavior

### Scenario: a legal transition is recorded
Given a task currently in `IN_PROGRESS`
When `transition` is called to move it to `IN_REVIEW` with an actor and reason
Then the quick-task file is updated to the mapped storage status
And the Genesis status cache reflects `IN_REVIEW`
And a `state-transition` message is published to the bus with from, to, and reason

### Scenario: an illegal transition is refused
Given a task currently in `TODO`
When `transition` is called to move it directly to `DONE`
Then an `InvalidTransitionError` is raised
And neither the task file nor the cache is modified

### Scenario: checking a transition without performing it
Given a task in a known status
When `can_transition` is called with a candidate target status
Then it returns whether that target is in the allowed set for the current status
And no state is changed and no message is published

### Scenario: bookmarks are normalized
Given a bookmark passed without a leading '#'
When any operation receives it
Then it is normalized to include the '#' prefix before use

### Scenario: history is reconstructable from the bus
Given a task that has undergone several transitions
When `get_history` is called for that task
Then it returns only the `state-transition` messages for that task

## Qualities

- **Invariant:** every transition is logged with timestamp, actor, and reason —
  there is no code path that changes state without publishing to the bus.
- **Lossy-down, rich-up:** the six-state model is collapsed to four for storage,
  so reading status back from quick-task alone (`_qt_to_genesis`) is a best-guess
  for states that share a storage status (`ASSIGNED`/`IN_PROGRESS`/`IN_REVIEW`).
  The in-memory cache is authoritative within a session.
- **Fail safe:** an illegal transition raises rather than silently coercing.
- **No distributed coordination:** state is single-process; concurrency safety is
  delegated to quick-task's file handling.

## Validation

- The existing suite in `tests/test_state_machine.py` exercises legal and illegal
  transitions, bookmark normalization, and history retrieval.
- The source-anchoring check confirms `../../src/genesis/state/machine.py` exists.
- Conformance claim: `VALID_TRANSITIONS` in the source equals the graph in
  *Structure*; a drift between them is a spec violation to be reconciled.
