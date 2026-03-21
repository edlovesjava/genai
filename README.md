# Genesis

An agentic kernel for SDLC-driven code generation. Genesis uses a V-Model workflow where a **Planner Agent** designs solutions and a **Builder Agent** implements them, all under human supervision via approval gates.

## How It Works

```
Task (TASKS.md)
  → Planner reads code, writes design doc + test spec
    → Human reviews design (gate)
      → Builder implements code, writes tests, opens PR
        → Human reviews PR (gate)
          → Done
```

The system manages task lifecycle through six states:

```
TODO → ASSIGNED → IN_PROGRESS → IN_REVIEW → DONE
                       ↕              ↓
                    BLOCKED       REJECTED → IN_PROGRESS
```

## Architecture

```
src/genesis/
├── runner.py          # Orchestrator — drives planner→builder loop
├── __main__.py        # CLI entry point
├── config.py          # TOML config loader
├── agents/
│   ├── base.py        # LLM loop, tool dispatch, budget tracking
│   ├── planner.py     # Reads tasks, produces design docs
│   └── builder.py     # Implements code, runs tests, opens PRs
├── bus/
│   └── message_bus.py # File-based JSON message bus
├── state/
│   └── machine.py     # Task state machine with transition rules
├── tools/
│   ├── file_ops.py    # File read/write with protected path gates
│   ├── git_ops.py     # Branch, commit, PR via subprocess
│   ├── task_ops.py    # quick-task API wrapper
│   └── test_runner.py # pytest execution
└── context/
    └── manager.py     # Builds focused context windows for agents
```

## Installation

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

Genesis depends on [quick-task](https://github.com/edlovesjava/quick-task) for task management:

```bash
pip install -e ../quick-task
```

## Usage

### CLI

```bash
# Run the full planner→builder loop on a task
python -m genesis run "#qt-metadata"

# Run just the planner or builder phase
python -m genesis plan "#qt-metadata"
python -m genesis build "#qt-metadata"

# Auto-approve human gates (non-interactive)
python -m genesis run "#qt-metadata" --auto-approve

# Check task statuses
python -m genesis status
```

### Configuration

Settings are in `genesis.toml`:

```toml
[llm]
default_model = "claude-sonnet-4-6"
reasoning_model = "claude-opus-4-6"

[budget]
planner_max_tokens = 100000
builder_max_tokens = 200000
warn_threshold = 0.8

[human_gates]
protected_paths = [".github/", "genesis.toml", "pyproject.toml"]
```

## Testing

```bash
pytest                    # Run all tests
pytest -v                 # Verbose output
pytest tests/test_runner.py  # Specific test file
```

115 tests cover the full stack: message bus, state machine, tools, config, context, base agent, planner/builder agents, runner orchestration, and end-to-end integration.

## Key Design Decisions

- **File-based message bus** — inspectable, version-controllable, no external services
- **Token budgets** — per-agent limits with warnings at 80%, hard stop at 100%
- **Human gates** — agents cannot merge, push to main, or modify CI without approval
- **Dogfooding** — uses quick-task to manage its own backlog

## Documentation

- `spec/bootstrap-spec.md` — Full specification
- `docs/plans/2026-03-20-genesis-design.md` — Component design
- `docs/plans/2026-03-20-implementation-plan.md` — Implementation plan
- `process/process-flow.md` — V-Model workflow
- `prompts/` — Agent system prompts
