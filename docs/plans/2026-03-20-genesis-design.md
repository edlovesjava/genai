# Design Document: Project Genesis — Bootstrap Kernel

**Version:** 0.1.0
**Date:** 2026-03-20
**Status:** Draft
**Spec Reference:** `spec/bootstrap-spec.md` v0.2.0-alpha

---

## 1. Overview

This document defines the technical design for the Genesis bootstrap kernel — a minimal system where a Planner agent and Builder agent collaborate on tasks under human supervision, proving the V-Model agentic SDLC loop.

**Design Goals:**
- Prove the end-to-end task loop (spec §2) with real quick-task improvements
- Fail fast: every component is testable in isolation before integration
- Minimal viable infrastructure: no containers, no external services, local-first
- Every decision logged and traceable

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|:---|:---|:---|
| **Language** | Python 3.11+ | Single-language stack, matches quick-task |
| **LLM SDK** | `anthropic` (Python) | Direct Claude API access for agents |
| **CLI Framework** | `click` | Consistent with quick-task |
| **Task Management** | `quick-task` (local import) | Dogfooding — agents use the tool they improve |
| **Message Format** | JSON files | Inspectable, grep-able, version-controllable |
| **VCS/Artifacts** | Git + GitHub (`gh` CLI) | PR-based workflow, CI via GitHub Actions |
| **Testing** | `pytest` | Already used in quick-task, well-known |
| **Config** | TOML (`genesis.toml`) | Standard Python config, human-readable |
| **Linting** | `ruff` | Fast, single-tool for lint + format |

### Dependencies (Bootstrap Only)

```toml
[project]
dependencies = [
    "anthropic>=0.40.0",
    "click>=8.0",
    "rich>=13.0",
    "quick-task @ file:///../quick-task",  # local editable
]
```

---

## 3. Project Structure

```
genai/
├── spec/
│   └── bootstrap-spec.md              # The specification (exists)
├── docs/
│   ├── plans/
│   │   └── 2026-03-20-genesis-design.md  # This document
│   ├── templates/                      # Doc templates (spec, design, plan)
│   └── guides/                         # Process guides
├── process/
│   ├── process-flow.md                 # SDLC process definition
│   └── feedback-loops.md               # How we detect right/wrong
├── src/genesis/
│   ├── __init__.py
│   ├── config.py                       # Load genesis.toml, defaults
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseAgent: LLM call, tool use, context
│   │   ├── planner.py                  # PlannerAgent: design + test spec
│   │   └── builder.py                  # BuilderAgent: implement + PR
│   ├── bus/
│   │   ├── __init__.py
│   │   └── message_bus.py              # Read/write JSON messages
│   ├── state/
│   │   ├── __init__.py
│   │   └── machine.py                  # Task state machine + transitions
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── file_ops.py                 # Read/write files
│   │   ├── git_ops.py                  # Git/GitHub operations
│   │   ├── task_ops.py                 # quick-task Python API wrapper
│   │   └── test_runner.py              # Run pytest, capture results
│   ├── context/
│   │   ├── __init__.py
│   │   └── manager.py                  # Build focused context for agents
│   └── runner.py                       # Orchestrator: run agent loop
├── prompts/
│   ├── planner_system.md               # Planner system prompt
│   └── builder_system.md               # Builder system prompt
├── tests/
│   ├── test_message_bus.py
│   ├── test_state_machine.py
│   ├── test_tools.py
│   ├── test_context.py
│   ├── test_agents.py                  # With mocked LLM
│   └── test_integration.py            # End-to-end with real/mock LLM
├── genesis.toml                        # Runtime configuration
├── pyproject.toml
├── TASKS.md                            # Genesis project tasks
└── .gitignore                          # (exists)
```

---

## 4. Component Design

### 4.1 Message Bus (`src/genesis/bus/message_bus.py`)

The foundation — all other components publish events here.

```python
@dataclass
class Message:
    timestamp: str          # ISO 8601
    agent: str              # "planner", "builder", "human"
    event: str              # "task-assigned", "design-complete", etc.
    task_bookmark: str      # Reference to task (e.g., "#python-api")
    payload: dict           # Freeform data + artifacts list

class MessageBus:
    def __init__(self, root: Path):           # .genesis/messages/
    def publish(self, msg: Message) -> Path:  # Write JSON, return path
    def query(self, **filters) -> list[Message]:  # Filter by agent, event, task
    def recent(self, n: int) -> list[Message]:    # Last N messages
    def for_task(self, bookmark: str) -> list[Message]:  # All messages for a task
```

**Design decisions:**
- One file per message, filename = `{timestamp}_{agent}_{event}.json`
- Files are append-only (never modified after write)
- Query scans directory — fine for bootstrap volume (<1000 messages)

### 4.2 State Machine (`src/genesis/state/machine.py`)

Enforces the task lifecycle from spec §4.

```python
VALID_TRANSITIONS: dict[str, list[str]] = {
    "TODO":        ["ASSIGNED"],
    "ASSIGNED":    ["IN_PROGRESS"],
    "IN_PROGRESS": ["BLOCKED", "IN_REVIEW"],
    "BLOCKED":     ["IN_PROGRESS"],
    "IN_REVIEW":   ["DONE", "REJECTED"],
    "REJECTED":    ["IN_PROGRESS"],
}

class StateMachine:
    def __init__(self, bus: MessageBus, task_ops: TaskOps):
    def transition(self, bookmark: str, to_status: str, actor: str, reason: str) -> None:
    def can_transition(self, bookmark: str, to_status: str) -> bool:
    def get_status(self, bookmark: str) -> str:
    def get_history(self, bookmark: str) -> list[Message]:
```

**Design decisions:**
- Every transition publishes a message to the bus (traceability invariant)
- Invalid transitions raise `InvalidTransitionError`
- Maps Genesis states to quick-task statuses: `TODO→TODO`, `ASSIGNED→IN_PROGRESS`, `IN_PROGRESS→IN_PROGRESS`, `IN_REVIEW→IN_PROGRESS`, `BLOCKED→BLOCKED`, `DONE→DONE`, `REJECTED→TODO`

### 4.3 Base Agent (`src/genesis/agents/base.py`)

Common agent infrastructure.

```python
class BaseAgent:
    def __init__(self, name: str, config: GenesisConfig, bus: MessageBus, tools: list[Tool]):
    def run(self, task_bookmark: str) -> AgentResult:
        """Main loop: build context → call LLM → execute tools → repeat until done or budget."""
    def _build_context(self, bookmark: str) -> list[dict]:  # System + task context
    def _call_llm(self, messages: list[dict]) -> Response:   # With retry + budget tracking
    def _execute_tool(self, tool_call: ToolCall) -> str:     # Dispatch to tool implementations
    def _checkpoint(self, bookmark: str, summary: str):      # Save progress for context refresh
```

**Budget enforcement:**
- Track input + output tokens per LLM call
- Warn at 80%, BLOCKED at 100% (per spec §10)
- Log token usage to message bus

### 4.4 Tool Definitions (`src/genesis/tools/`)

Tools are functions agents can call via the Claude tool_use API.

| Tool | Module | Purpose |
|:---|:---|:---|
| `read_file` | `file_ops.py` | Read file contents |
| `write_file` | `file_ops.py` | Write/create file (with human gate for protected paths) |
| `list_tasks` | `task_ops.py` | Query tasks via quick-task API |
| `update_task_status` | `task_ops.py` | Change task status (via state machine) |
| `add_task` | `task_ops.py` | Create subtask |
| `git_create_branch` | `git_ops.py` | Create feature branch |
| `git_commit` | `git_ops.py` | Stage + commit changes |
| `git_open_pr` | `git_ops.py` | Open PR via `gh` CLI |
| `run_tests` | `test_runner.py` | Execute pytest, return results |

**Human gates:** `write_file` to protected paths (CI config, main branch) requires confirmation.

### 4.5 Context Manager (`src/genesis/context/manager.py`)

Builds focused context windows for each agent call.

```python
class ContextManager:
    def build_planner_context(self, bookmark: str) -> list[dict]:
        # Task details + metadata + recent messages + related design docs
    def build_builder_context(self, bookmark: str) -> list[dict]:
        # Task + design spec + test spec + existing code + recent messages
    def summarize_for_checkpoint(self, messages: list[dict]) -> str:
        # Compress conversation into a progress summary
```

**Design decisions:**
- Agents get only task-relevant context, not entire project history
- Context budget: reserve tokens for system prompt + response, fill remainder with task context
- Prioritize: task spec > design doc > recent messages > code files

### 4.6 Runner / Orchestrator (`src/genesis/runner.py`)

The entry point that drives the agent loop.

```python
class GenesisRunner:
    def __init__(self, config_path: Path = "genesis.toml"):
    def run_planner(self, task_bookmark: str) -> None:
        # 1. Transition task TODO → ASSIGNED
        # 2. Run PlannerAgent
        # 3. Planner produces design doc + test spec
        # 4. Transition ASSIGNED → IN_PROGRESS
        # 5. Notify human for design review gate
    def run_builder(self, task_bookmark: str) -> None:
        # 1. Read design doc + test spec
        # 2. Run BuilderAgent
        # 3. Builder creates branch, implements, opens PR
        # 4. Transition IN_PROGRESS → IN_REVIEW
        # 5. Notify human for PR review gate
    def status(self) -> dict:
        # Current state of all tasks + agent health
```

---

## 5. Configuration (`genesis.toml`)

```toml
[genesis]
project_name = "genesis"
tasks_file = "TASKS.md"
genesis_dir = ".genesis"

[llm]
provider = "anthropic"
default_model = "claude-sonnet-4-6"
reasoning_model = "claude-opus-4-6"
max_retries = 3

[budget]
planner_max_tokens = 100000
builder_max_tokens = 200000
daily_cap_tokens = 1000000
warn_threshold = 0.8

[agents.planner]
system_prompt = "prompts/planner_system.md"
tools = ["read_file", "list_tasks", "update_task_status", "add_task", "write_file"]

[agents.builder]
system_prompt = "prompts/builder_system.md"
tools = ["read_file", "write_file", "list_tasks", "update_task_status", "git_create_branch", "git_commit", "git_open_pr", "run_tests"]

[human_gates]
protected_paths = [".github/", "genesis.toml", "pyproject.toml"]
require_approval = ["merge", "delete", "push_main"]
```

---

## 6. Non-Functional Requirements

### 6.1 Testability
- Every component has unit tests with no LLM dependency (mocked)
- Integration tests can run against real Claude API (gated by env var)
- Message bus is file-based: tests use tmp directories, no cleanup issues
- Target: >80% code coverage on kernel components

### 6.2 Observability
- All state transitions logged to message bus with timestamp + actor + reason
- Token usage logged per LLM call
- Agent results include success/failure + summary
- `genesis status` command shows current state of all tasks and agents

### 6.3 Reliability
- BLOCKED is the safe default for any unrecoverable error
- LLM API errors: exponential backoff, max 3 retries
- Invalid agent output: re-prompt with error context, max 2 retries
- File operations: advisory locking on TASKS.md (Phase 1 simple, Phase 2 robust)

### 6.4 Security
- No secrets in code — API keys via environment variables only
- Agents cannot push to main, merge PRs, or modify CI without human approval
- Tool execution sandboxed to project directories

### 6.5 Performance
- Not a concern at bootstrap scale
- Latency dominated by LLM API calls (~2-10s per call)
- Message bus query is O(n) file scan — acceptable for <1000 messages

### 6.6 Extensibility
- New tools: add a function + register in config
- New agents: subclass BaseAgent + add system prompt
- New state transitions: modify VALID_TRANSITIONS dict
- Slack bridge: adapter that reads/writes message files (no core changes)

---

## 7. Key Interfaces

### Quick-Task Python API (needed from §8.1)

The Genesis kernel depends on quick-task exposing a stable Python API:

```python
# What genesis/tools/task_ops.py needs to call:
from quick_task.operations import load_file, add_task, update_status, list_tasks, find_task
from quick_task.models import TaskFile, Task, TaskStatus
```

This API already exists in quick-task's `operations.py` and `parser.py`. The gap:
- `load_file()` convenience function (currently `Parser().parse_file()`)
- Stable public imports from package root
- Type-safe return values (already dataclasses)

### Claude Tool Use API

Agents interact with Claude via the Anthropic SDK's tool_use feature:

```python
response = client.messages.create(
    model=config.default_model,
    system=system_prompt,
    messages=conversation,
    tools=tool_definitions,
    max_tokens=4096,
)
# Process tool_use blocks → execute tools → append results → loop
```

---

## 8. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|:---|:---|:---|:---|
| Agents produce unusable output | High | Medium | Structured output validation, retry with error context, BLOCKED fallback |
| Token costs exceed budget | Medium | Medium | Per-task budgets, daily cap, model tiering |
| quick-task file corruption | High | Low | Advisory locking, git as safety net (revert) |
| Context window overflow | Medium | Medium | Focused context strategy, checkpointing |
| Circular agent failures | High | Low | Max retry limits, BLOCKED as circuit breaker |

---

## 9. What This Design Does NOT Include (Explicit Scope Boundaries)

- **No containers** — agents are Python processes
- **No Slack integration** — Phase 2
- **No web dashboard** — Phase 3
- **No auto-approval** — Phase 4
- **No multi-repo support** — single quick-task repo target
- **No persistent database** — files only
