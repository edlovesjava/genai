---
id: genspec.orchestrate
title: SpecRunner Lifecycle Orchestration
status: active
abstraction: model
source: [../src/genspec/orchestrate.py, ../src/genspec/orchestrate_genesis.py]
depends: [genspec.generate]
---

# SpecRunner Lifecycle Orchestration

The outer orchestration layer. Where `Generator` builds one spec once,
`SpecRunner` drives a spec through its full SDLC over time, reusing the Genesis
kernel's primitives — the file message bus, the six-state task machine, and the
human-gate pattern — rather than reinventing them.

## Intent

Coordinate the lifecycle of a spec from pickup to acceptance: advance its task
state, log every phase to the bus, invoke generation, route the mechanical
disposition to either a human acceptance gate or a blocked escalation, and commit
the accepted artifacts. Keep verification (does code match the spec) and
validation (is the spec correct) as distinct events on the timeline.

## Structure

- **`SpecRunner`** — holds a `Generator`, a `Lifecycle` (the Genesis state
  machine's `transition`/`get_status` surface), a tracked `output_dir`, an
  `emit` callback for bus events, and an optional `gate_handler`.
- **`Lifecycle`** / **`Emit`** — narrow Protocols so the core imports nothing
  from Genesis; the real `StateMachine` and `MessageBus` satisfy them.
- **`orchestrate_genesis.build_spec_runner`** — the only Genesis-importing
  module; lazily wires a SpecRunner onto a real bus and state machine, tracking
  each spec as a task whose bookmark is the spec id.
- **`RunRecord`** — final state, disposition, generation result, committed
  artifact paths, and whether the run escalated.
- Disposition-to-state mapping: agreement → `IN_REVIEW` → (`DONE` | `REJECTED`);
  any fault → `BLOCKED`.

## Behavior

### Scenario: a validated spec is accepted and committed
Given a consistent spec whose generation reaches agreement
When the runner drives it and the acceptance gate approves
Then the task walks TODO→ASSIGNED→IN_PROGRESS→IN_REVIEW→DONE
And the generated code and tests are written to the tracked output dir

### Scenario: a human can decline a consistent result
Given a spec whose generation reaches agreement
When the acceptance gate declines
Then the task moves to REJECTED
And nothing is committed to the output dir

### Scenario: an inconsistent spec is blocked
Given a spec that fails static validation
When the runner drives it
Then the task moves to BLOCKED and the run is escalated
And no generation artifacts are produced

### Scenario: an unreconcilable disagreement is blocked
Given a spec whose independently generated tests and code cannot be reconciled
When the runner drives it
Then generation raises a spec-fault gate which the runner records as BLOCKED
And the run is marked escalated

### Scenario: a library runs in dependency order
Given a set of specs where one depends on another
When the runner drives the library
Then each spec is run only after the specs it depends on

## Qualities

- **Reuses kernel primitives** — lifecycle transitions and events go through the
  Genesis state machine and bus; genspec does not fork its own task model.
- **Import-clean core** — `orchestrate.py` imports no Genesis; the only coupling
  lives in `orchestrate_genesis.py`, which imports lazily and fails with a clear
  message if Genesis is absent, so genspec installs and tests standalone.
- **Legal transitions only** — the runner enters `IN_PROGRESS` before any fault
  so `BLOCKED` is always reachable; every emitted transition is valid in the
  six-state graph.
- **Commit on acceptance** — artifacts are persisted only when a human accepts,
  keeping the repository's runnable code in step with its accepted specs.
- **Faults escalate** — both static and spec faults terminate in `BLOCKED`, never
  silently auto-resolved.

## Validation

- `tests/test_orchestrate.py` drives every disposition through a `FakeLifecycle`
  that enforces the real six-state graph, asserts the exact legal state
  sequences, and runs pytest against the committed artifacts to prove they are
  runnable.
- A test confirms the Genesis adapter raises a clear error when Genesis is not
  installed.
- The source-anchoring check confirms both `source:` modules exist;
  `depends: [genspec.generate]` resolves within the library.
