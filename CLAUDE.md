# CLAUDE.md — Genesis

## Build & Test

```bash
# Install (editable, with dev dependencies)
pip install -e ".[dev]"
pip install -e ../quick-task

# Run all tests
pytest

# Run specific test file
pytest tests/test_runner.py -v

# Run tests matching a keyword
pytest -k "planner"
```

## Project Structure

- `src/genesis/` — Main package
  - `runner.py` — GenesisRunner orchestrator (entry point for agent loops)
  - `__main__.py` — CLI: `python -m genesis plan|build|run|status`
  - `config.py` — Loads `genesis.toml`, provides `GenesisConfig` dataclass
  - `agents/base.py` — BaseAgent with LLM loop, tool dispatch, budget tracking
  - `agents/planner.py` — PlannerAgent (tools: read_file, write_file, list_tasks, update_task_status, add_task)
  - `agents/builder.py` — BuilderAgent (tools: + git_create_branch, git_commit, git_open_pr, run_tests)
  - `bus/message_bus.py` — File-based JSON message bus (.genesis/messages/)
  - `state/machine.py` — Task state machine (TODO→ASSIGNED→IN_PROGRESS→IN_REVIEW→DONE)
  - `tools/` — FileOps, GitOps, TaskOps, TestRunner
  - `context/manager.py` — Builds focused context windows for planner/builder
- `tests/` — pytest tests (115 total), all use mocked LLM via `unittest.mock`
- `prompts/` — System prompts for planner and builder agents (markdown)
- `genesis.toml` — Runtime configuration (models, budgets, gates, agent tools)
- `TASKS.md` — Project backlog managed by quick-task

## Architecture Patterns

- **Agents** subclass `BaseAgent` and register tools in `__init__`. The base `run()` method handles the LLM tool-use loop, budget tracking, and checkpointing.
- **State machine** maps 6 Genesis states to quick-task's 4 statuses. All transitions are logged to the message bus.
- **Human gates** are pluggable via `gate_handler` callback on GenesisRunner. Raising `HumanGateRequired` pauses execution.
- **Tools** are plain Python classes instantiated with `GenesisConfig`. Agents register them via `register_tool(name, description, handler, input_schema)`.

## Conventions

- Python 3.11+, type hints throughout
- Tests use `pytest` with `tmp_path` fixtures and `unittest.mock.MagicMock` for the Anthropic client
- LLM responses are mocked as `SimpleNamespace` objects matching the Anthropic SDK shape
- Config uses dataclasses with defaults — `GenesisConfig()` works with no file
- All bus messages are JSON files named `{timestamp}_{agent}_{event}.json`

## Dependencies

- `anthropic` — Claude API SDK (agents call `client.messages.create`)
- `click` / `rich` — CLI (declared but CLI uses argparse in `__main__.py`)
- `quick-task` — Task management (local editable install)
