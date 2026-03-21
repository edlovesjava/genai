# Implementation Plan: Genesis Bootstrap Kernel

**Date:** 2026-03-20
**Design Reference:** `docs/plans/2026-03-20-genesis-design.md`
**Spec Reference:** `spec/bootstrap-spec.md` §2, §3, §8

---

## Strategy

We build bottom-up in thin, testable slices. Each iteration adds one working layer. The first iteration should be runnable within hours, not days. If any iteration can't be validated, we stop and fix before moving on.

**Two parallel tracks:**
1. **Genesis kernel** (genai repo) — the agent infrastructure
2. **Quick-task Python API** (quick-task repo) — the tool agents need

These converge at Iteration 4 where agents use the API.

---

## Iteration 0: Foundation — Project Skeleton + Quick-Task API

**Goal:** Both repos have testable project scaffolding. Quick-task exposes a Python API that genesis can import.

**Acceptance Criteria:**
- [ ] `genai/` has pyproject.toml, src/genesis/, tests/, and passes `pytest` (even if tests are trivial)
- [ ] `quick-task` exposes `quick_task.api` module with `load_file()`, `add_task()`, `update_status()`, `list_tasks()`, `find_task()`, `get_task()`
- [ ] Quick-task API functions have tests
- [ ] `from quick_task.api import load_file` works from genesis (via editable install)
- [ ] CI green on both repos

### Tasks (genai repo)
- [ ] Create `pyproject.toml` with dependencies
- [ ] Create `src/genesis/__init__.py`
- [ ] Create minimal test that imports genesis
- [ ] Set up pytest configuration

### Tasks (quick-task repo)
- [ ] Create `src/quick_task/api.py` — public API module wrapping existing operations
- [ ] Add `load_file()` convenience function (wraps `Parser().parse_file()`)
- [ ] Add `get_task()` function (wraps `find_task` from matcher)
- [ ] Re-export `add_task`, `update_status`, `list_tasks` from operations
- [ ] Write tests for API module
- [ ] Ensure CLI imports from API (thin wrapper validation)

**Validation:**
```bash
cd quick-task && pytest tests/test_api.py -v
cd genai && pip install -e . && pytest -v
```

**Fail-fast checkpoint:** If quick-task's internal operations are too coupled to expose cleanly, we refactor operations.py first.

---

## Iteration 1: Message Bus + State Machine

**Goal:** The two core infrastructure components work independently with tests.

**Acceptance Criteria:**
- [ ] `MessageBus.publish()` writes a JSON file to `.genesis/messages/`
- [ ] `MessageBus.query()` filters messages by agent, event, task
- [ ] `StateMachine.transition()` enforces valid transitions and publishes events
- [ ] `StateMachine.transition()` rejects invalid transitions with clear error
- [ ] All state transitions from spec §4 are covered in tests
- [ ] >90% coverage on bus and state modules

### Tasks
- [ ] Implement `src/genesis/bus/message_bus.py` — Message dataclass, publish, query, recent, for_task
- [ ] Implement `src/genesis/state/machine.py` — VALID_TRANSITIONS, transition, can_transition, get_history
- [ ] Write `tests/test_message_bus.py` — publish, query, filtering, edge cases
- [ ] Write `tests/test_state_machine.py` — all valid transitions, invalid transitions, history

**Validation:**
```bash
pytest tests/test_message_bus.py tests/test_state_machine.py -v --cov=genesis.bus --cov=genesis.state
```

**Fail-fast checkpoint:** If the message bus file-per-message approach is too slow for testing, switch to in-memory bus with file persistence as optional.

---

## Iteration 2: Tools + Config

**Goal:** Agent tools work against real quick-task files and git repos. Config loads from TOML.

**Acceptance Criteria:**
- [ ] `task_ops.py` wraps quick-task API and routes status changes through state machine
- [ ] `file_ops.py` reads/writes files with path validation
- [ ] `git_ops.py` creates branches, commits, opens PRs (tested against local git repo)
- [ ] `test_runner.py` runs pytest and captures pass/fail results
- [ ] `config.py` loads `genesis.toml` with sensible defaults
- [ ] All tools have tests

### Tasks
- [ ] Implement `src/genesis/config.py` — load TOML, GenesisConfig dataclass, defaults
- [ ] Create `genesis.toml` with bootstrap defaults
- [ ] Implement `src/genesis/tools/task_ops.py` — wraps quick-task API + state machine
- [ ] Implement `src/genesis/tools/file_ops.py` — read_file, write_file with path guards
- [ ] Implement `src/genesis/tools/git_ops.py` — create_branch, commit, open_pr
- [ ] Implement `src/genesis/tools/test_runner.py` — run_tests, parse results
- [ ] Write tests for each tool module

**Validation:**
```bash
pytest tests/test_tools.py -v --cov=genesis.tools --cov=genesis.config
```

**Fail-fast checkpoint:** If tool testing requires too much mocking/setup, simplify tool interfaces.

---

## Iteration 3: Base Agent + Context Manager

**Goal:** An agent can call the LLM, use tools, and manage context — but with a mock/simple task, not the full workflow.

**Acceptance Criteria:**
- [ ] `BaseAgent.run()` calls Claude API with system prompt + tools
- [ ] Agent processes tool_use responses and executes tools
- [ ] Agent respects token budget (warns at 80%, stops at 100%)
- [ ] `ContextManager` builds focused context from task + messages + files
- [ ] Agent loop terminates (success, budget exceeded, or max iterations)
- [ ] Tests with mocked LLM responses validate the loop mechanics

### Tasks
- [ ] Implement `src/genesis/agents/base.py` — BaseAgent with LLM loop
- [ ] Implement `src/genesis/context/manager.py` — build_context, summarize
- [ ] Define tool schemas for Claude tool_use format
- [ ] Implement budget tracking (token counter per call)
- [ ] Write `tests/test_agents.py` — mocked LLM, tool dispatch, budget enforcement
- [ ] Write `tests/test_context.py` — context building, prioritization

**Validation:**
```bash
pytest tests/test_agents.py tests/test_context.py -v
# Optional: real LLM smoke test (requires ANTHROPIC_API_KEY)
GENESIS_LIVE_TEST=1 pytest tests/test_agents.py -k "live" -v
```

**Fail-fast checkpoint:** If the tool_use loop is unreliable (agent doesn't stop, wrong tool calls), simplify to single-turn before attempting multi-turn.

---

## Iteration 4: Planner + Builder Agents

**Goal:** Specialized agents that can perform their roles on a real quick-task improvement.

**Acceptance Criteria:**
- [ ] `PlannerAgent` reads a task, produces a design doc and test spec in `docs/plans/`
- [ ] `BuilderAgent` reads a design doc, implements code, creates branch, opens PR
- [ ] Both agents use the state machine to transition tasks
- [ ] Both agents publish events to message bus throughout their work
- [ ] System prompts guide agents to stay in scope

### Tasks
- [ ] Write `prompts/planner_system.md` — role, constraints, output format, tools
- [ ] Write `prompts/builder_system.md` — role, constraints, output format, tools
- [ ] Implement `src/genesis/agents/planner.py` — PlannerAgent with design workflow
- [ ] Implement `src/genesis/agents/builder.py` — BuilderAgent with implementation workflow
- [ ] Write tests with mocked LLM for each agent's workflow
- [ ] Manual smoke test: run Planner on a real task from quick-task TASKS.md

**Validation:**
```bash
pytest tests/test_agents.py -v
# Manual validation with real LLM:
python -m genesis.runner plan "#python-api"
# Verify: design doc created, task transitioned, messages published
```

**Fail-fast checkpoint:** If agents can't stay on-task with the system prompt alone, add structured output constraints (JSON mode or stricter tool definitions).

---

## Iteration 5: Runner + End-to-End Loop

**Goal:** The full loop from spec §2 works: task → planner → builder → PR → review → merge → done.

**Acceptance Criteria:**
- [ ] `GenesisRunner.run_planner(bookmark)` executes full planner workflow
- [ ] `GenesisRunner.run_builder(bookmark)` executes full builder workflow
- [ ] Human gates pause execution and wait for approval
- [ ] End-to-end test: one quick-task improvement goes through the complete loop
- [ ] Message bus contains full audit trail of the loop
- [ ] Task in TASKS.md transitions through all states correctly

### Tasks
- [ ] Implement `src/genesis/runner.py` — orchestrate planner and builder workflows
- [ ] Implement human gate mechanism (CLI prompt or message bus event)
- [ ] Write `tests/test_integration.py` — end-to-end with mocked LLM
- [ ] Run the first real loop on quick-task improvement §8.2 (agent metadata fields)
- [ ] Document the loop results in the message bus

**Validation:**
```bash
# Integration test
pytest tests/test_integration.py -v
# Real end-to-end (human in the loop)
python -m genesis.runner plan "#agent-metadata"
# Review design doc, approve
python -m genesis.runner build "#agent-metadata"
# Review PR, approve, merge
```

**Fail-fast checkpoint:** This is THE checkpoint. If the end-to-end loop doesn't complete on a real task, we've disproven the hypothesis for this architecture and need to analyze what broke.

---

## Iteration Summary

| Iteration | What It Proves | Depends On | Estimated Complexity |
|:---|:---|:---|:---|
| **0: Foundation** | Projects build and import correctly | Nothing | Low |
| **1: Bus + State** | Core infrastructure works | Iteration 0 | Low-Medium |
| **2: Tools + Config** | Agents can interact with the world | Iteration 0, 1 | Medium |
| **3: Base Agent** | LLM loop mechanics work | Iteration 1, 2 | Medium-High |
| **4: Planner + Builder** | Specialized agents produce useful output | Iteration 3 | High |
| **5: End-to-End** | The kernel hypothesis is valid | Iteration 4 | Medium (integration) |

---

## Cross-Iteration Risk Checkpoints

After **Iteration 1:** Is the message bus adequate? Is file-per-message workable?
After **Iteration 3:** Can the agent loop reliably use tools? Is context management sufficient?
After **Iteration 5:** Does the full loop work? What's the human intervention rate?

---

## What We Learn Along the Way

Each iteration teaches us something we feed back into the process:

| Iteration | Learning | Updates To |
|:---|:---|:---|
| 0 | Is the quick-task API clean enough? | Quick-task API design |
| 1 | Is file-based messaging sufficient? | Design doc §4.1 |
| 2 | Are tool interfaces right for agents? | Tool definitions |
| 3 | Does the LLM loop converge? | Agent prompts, context strategy |
| 4 | Do agents stay on-task? | System prompts, guardrails |
| 5 | Does the V-Model loop actually work? | The spec itself |
