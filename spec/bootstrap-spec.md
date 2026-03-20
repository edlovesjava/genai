
# Specification: Project Genesis

**Version:** 0.2.0-alpha
**Status:** Bootstrapping
**Primary Objective:** Build a "Heavy" SDLC Agentic Kernel to orchestrate software development.

## 1. The Backstory (Contextual Traceability)

This project originated from a hypothesis that **Agentic Coding** requires "heavy" SDLC-based orchestration to be reliable. We are moving away from simple chat-to-code and toward a **Cognitive Architecture** based on the **V-Model**.

* **The Inspiration:** Pairing build activities with verify activities (V-Model) to ensure clear traceability from Specification → Design → Implementation → Verification.
* **The "Heavy" Philosophy:** Agents must be governed by a **State Machine** with shared knowledge, prioritized task queues, and inter-agent communication.
* **The Driving Principle:** "Build the car while driving it." We will use the system to build the system (Dogfooding).

---

## 2. MVP Success Criteria

The bootstrap is validated when the following end-to-end loop completes successfully:

1. A task exists in `TASKS.md` (created by human or Planner agent).
2. The Planner agent reads the task, produces a design and test spec.
3. The Builder agent implements the code and tests.
4. Tests pass in CI (GitHub Actions).
5. A human reviews and approves the PR.
6. The PR is merged, and the task status is updated to Done.

**One full loop on a real quick-task improvement proves the kernel works.** The hypothesis is disproven if agents cannot reliably complete this loop without constant human intervention beyond the approval gate.

---

## 3. The Bootstrap System (The Kernel)

The first goal is to spawn a minimal environment where two agents can collaborate on a task under human supervision.

### Tech Stack

| Component | Bootstrap (Phase 1) | Phase 2 |
|:---|:---|:---|
| **Language** | Python 3.11 (single language) | Add TypeScript if needed |
| **Task Management** | [quick-task](https://github.com/edlovesjava/quick-task) CLI + Python API | Enhanced with event history |
| **Message Bus** | Local message log (JSON files in ``.genesis/messages/``) | Slack integration |
| **Artifact Store** | GitHub (managed via `gh` CLI) | Same |
| **CI/CD** | GitHub Actions | Same |
| **Environment** | Local Python venv | Docker / Dev Containers |
| **LLM** | Claude API (via Anthropic SDK) | Configurable provider |

### Why This Stack

* **Single language** eliminates cross-runtime coordination complexity.
* **Local message bus** removes external API dependencies — every message is a JSON file, inspectable and version-controllable.
* **No containers at bootstrap** — agents are Python processes, not services. Containerize when isolation is actually needed.
* **Claude API** is the LLM backbone. Agents use the Anthropic Python SDK to reason, plan, and generate code. Each agent gets its own system prompt and context strategy.

### Agent Roles (Bootstrap Pair)

| Role | Responsibility |
|:---|:---|
| **Planner** | Reads a task from `TASKS.md`, breaks it into subtasks, writes a design doc and test specification. Transitions task to `IN_PROGRESS`. |
| **Builder** | Implements code and tests based on the Planner's spec. Creates a branch, commits, opens a PR. Transitions task to `IN_REVIEW`. |

**Phase 2 expansion** splits these into the full Triad + 1:

| Role | Responsibility |
|:---|:---|
| **Coach** | Prioritizes backlog, manages human-in-the-loop triggers, monitors agent health. |
| **Coder** | Implements logic based on design specs. |
| **Test Author** | Writes tests aimed at breaking the Coder's implementation. |
| **Reviewer** | Evaluates code quality, test coverage, and design adherence. |

---

## 4. State Machine

Every task follows this lifecycle:

```
TODO ──→ ASSIGNED ──→ IN_PROGRESS ──→ IN_REVIEW ──→ DONE
  │                       │                │
  │                       ▼                ▼
  │                    BLOCKED          REJECTED
  │                       │                │
  │                       ▼                ▼
  └──────────────────── (human) ──→ IN_PROGRESS
```

### State Transition Rules

| From | To | Trigger | Actor |
|:---|:---|:---|:---|
| `TODO` | `ASSIGNED` | Planner picks task from backlog | Planner |
| `ASSIGNED` | `IN_PROGRESS` | Planner produces design + test spec | Planner |
| `IN_PROGRESS` | `BLOCKED` | Agent cannot proceed (missing info, dependency, failure) | Any agent |
| `BLOCKED` | `IN_PROGRESS` | Human unblocks (provides info, resolves dependency) | Human |
| `IN_PROGRESS` | `IN_REVIEW` | Builder opens PR with passing tests | Builder |
| `IN_REVIEW` | `DONE` | Human approves and merges PR | Human |
| `IN_REVIEW` | `REJECTED` | Human requests changes | Human |
| `REJECTED` | `IN_PROGRESS` | Builder addresses feedback | Builder |

**Invariant:** Every transition is logged with timestamp, actor, and reason in the message bus.

---

## 5. Communication Protocol

### Local Message Bus

Agents communicate via JSON message files stored in `.genesis/messages/`. This replaces Slack for the bootstrap.

```
.genesis/
├── messages/
│   ├── 2026-03-19T10-30-00_planner_task-assigned.json
│   ├── 2026-03-19T10-35-12_planner_design-complete.json
│   └── 2026-03-19T11-02-44_builder_pr-opened.json
└── state/
    └── agent-status.json
```

**Message format:**

```json
{
  "timestamp": "2026-03-19T10:30:00Z",
  "agent": "planner",
  "event": "task-assigned",
  "task_bookmark": "#add-priority-field",
  "payload": {
    "description": "Picked task from backlog, starting design phase",
    "artifacts": []
  }
}
```

**Why not Slack for MVP:**
* Zero external dependencies — works offline, no API keys, no rate limits.
* Every message is a file — `git log`, `grep`, `jq` all work on it.
* Trivially replaceable: a Slack adapter reads these files and posts them, or writes incoming Slack messages as files.

### Phase 2: Slack Integration

Add a **Slack Bridge** that:
1. Mirrors `.genesis/messages/` to a Slack channel (one message per event).
2. Routes threaded Slack replies back as message files for agent consumption.
3. Supports human commands in Slack (e.g., "unblock #task-name").

---

## 6. Human-in-the-Loop Gates

The bootstrap requires human approval at these checkpoints:

| Gate | When | What Human Does |
|:---|:---|:---|
| **Task Approval** | Before Planner starts a task | Reviews that the task is well-defined and appropriately scoped |
| **Design Review** | After Planner produces design + test spec | Reviews approach before Builder begins implementation |
| **PR Approval** | After Builder opens PR with passing tests | Reviews code, approves or requests changes |
| **Unblock** | When any agent transitions to BLOCKED | Provides missing information or resolves the dependency |

**Default policy:** Agents may NOT merge code, delete files, push to main, or modify CI configuration without human approval. This is non-negotiable in the bootstrap phase.

**Phase 2:** Introduce configurable trust levels where proven-reliable operations can be auto-approved.

---

## 7. LLM Strategy

### Agent Prompting

Each agent has:
* A **system prompt** defining its role, constraints, and output format.
* **Task context** injected from `TASKS.md` metadata, design docs, and message history.
* A **tool set** (file read/write, `qt` CLI, `gh` CLI, `git`, test runners).

### Context Management

* Agents receive **focused context** — only the task, its subtasks, related design docs, and recent messages. Not the entire project history.
* Long-running tasks use **context checkpoints** — the agent summarizes its progress into a message before context is refreshed.

### Model Selection

* **Bootstrap:** Claude API (Sonnet for routine operations, Opus for complex reasoning).
* **Cost control:** Set a per-task token budget. If an agent exceeds its budget, it transitions the task to BLOCKED with a reason.

---

## 8. The First Project: Improving quick-task

The agents' first assignment is to improve [quick-task](https://github.com/edlovesjava/quick-task) — the very tool that manages their backlog. This is direct dogfooding.

### Target Improvements

These are ordered by priority for enabling the Genesis kernel:

#### 8.1 Python API (Programmatic Access)

**Why:** Agents currently must shell out to `qt` via subprocess. A Python API lets agents import and call operations directly — faster, type-safe, and testable.

**Scope:**
* Expose `quick_task.operations` as a stable public API.
* Functions: `load_file()`, `add_task()`, `update_status()`, `list_tasks()`, `find_task()`, `get_task()`.
* Return typed dataclasses (already exist in `models.py`).
* CLI becomes a thin wrapper over the API.

#### 8.2 Agent-Oriented Metadata Fields

**Why:** Agents need to track who is assigned, priority, estimates, and timestamps. quick-task has generic `key: value` metadata but no first-class support.

**Scope:**
* First-class fields: `assignee`, `priority`, `created`, `updated`.
* `qt add "Task name" --assignee @planner --priority 1`
* `qt list --assignee @builder --status in-progress`
* Backward-compatible: these are stored as metadata, parsed with awareness.

#### 8.3 Transition History (Audit Log)

**Why:** The V-Model requires traceability. When did a task move from TODO to IN_PROGRESS? Who did it?

**Scope:**
* Append a `history` metadata block on each status change.
* Format: `history: 2026-03-19T10:30:00 TODO→IN_PROGRESS by @planner`
* `qt show --history` displays the full transition log.
* `qt list --json` includes history in output.

#### 8.4 File Locking (Concurrent Access)

**Why:** Two agents writing `TASKS.md` simultaneously will corrupt it.

**Scope:**
* Advisory file locking using a `.TASKS.md.lock` file.
* Lock acquired before write, released after.
* Timeout + stale lock detection (lock older than N seconds is broken).
* Minimal — not distributed locking, just single-machine process safety.

#### 8.5 Filter/Query Enhancements

**Why:** Agents need to find tasks by compound criteria.

**Scope:**
* `qt list --assignee @builder --status in-progress --priority 1`
* `qt list --has-metadata depends` (find tasks with dependencies)
* JSON output already exists — ensure filters apply before serialization.

### V-Model Trace for quick-task Improvements

Each improvement follows the full trace:

```
Spec (this document, §8.x)
  → Design (Planner produces design doc in docs/plans/)
    → Implementation (Builder writes code + tests)
      → Verification (tests pass, human reviews PR)
        → Acceptance (merged to main, task marked DONE)
```

---

## 9. Error Recovery

### Agent Failure Modes

| Failure | Detection | Recovery |
|:---|:---|:---|
| LLM API error (rate limit, timeout) | HTTP error code | Exponential backoff, max 3 retries, then BLOCKED |
| Agent produces invalid output | Output validation against expected schema | Re-prompt with error context, max 2 retries, then BLOCKED |
| Tests fail | Non-zero exit code from test runner | Builder analyzes failure, attempts fix (max 3 cycles), then BLOCKED |
| Token budget exceeded | Token counter hits threshold | Checkpoint progress, transition to BLOCKED |
| File conflict | Git merge conflict on `TASKS.md` or source files | Agent attempts auto-resolve, falls back to BLOCKED |

**BLOCKED is the safe default.** Any unrecoverable error transitions the task to BLOCKED and notifies the human via the message bus. Agents never silently fail or retry indefinitely.

---

## 10. Cost and Rate-Limit Awareness

* **Per-task token budget:** Each task has a configurable max token spend (default: 100K tokens for Planner, 200K for Builder).
* **Budget tracking:** Token usage is logged in the message bus after each LLM call.
* **Alerts:** When an agent reaches 80% of its budget, it logs a warning. At 100%, it checkpoints and BLOCKs.
* **Daily cap:** A global daily spend limit prevents runaway costs during development.
* **Model tiering:** Routine operations (status updates, file reads) use cheaper models. Complex reasoning (design, code generation) uses capable models.

---

## 11. Phased Rollout

| Phase | Focus | Agents | Infra | Success Metric |
|:---|:---|:---|:---|:---|
| **Phase 1: Bootstrap** | Prove the loop works | Planner + Builder | Local Python, JSON messages, GitHub | One quick-task improvement completed end-to-end |
| **Phase 2: Expand** | Richer collaboration | Coach + Coder + Tester + Reviewer | Add Slack bridge, Docker | Three tasks completed with <20% human intervention beyond gates |
| **Phase 3: Dashboard** | Visibility and monitoring | Full team | Web dashboard, persistent history | Real-time view of task flow and V-Model traces |
| **Phase 4: Autonomy** | Reduce human gates | Full team + trust levels | Configurable auto-approval | Tasks completed with human involved only at final PR review |

---

## Next Steps

1. **Set up the Genesis project structure** — `.genesis/` directory, agent entry points, message bus scaffolding.
2. **Build the Python API for quick-task** (§8.1) — this is the first task the agents will eventually do for themselves, but we build it manually first to bootstrap the tooling.
3. **Write the Planner agent's system prompt and tool definitions.**
4. **Write the Builder agent's system prompt and tool definitions.**
5. **Run the first loop manually** — human plays both agent roles using the tooling to validate the workflow before adding LLM automation.
