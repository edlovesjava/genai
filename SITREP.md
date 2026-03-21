# Situation Report — 2026-03-21

## Overview

Two related projects are being developed on the same feature branch:

| Project | Repo | Branch | Tests |
|---------|------|--------|-------|
| **Genesis** (agentic SDLC kernel) | `edlovesjava/genai` | `claude/genai-bootstrap-spec-Yo0T8` | 115 passed |
| **Quick Task** (markdown task CLI) | `edlovesjava/quick-task` | `claude/genai-bootstrap-spec-Yo0T8` | 116 passed |

Both repos are clean (no uncommitted changes) and pushed to remote.

## What's Done

### Genesis (`/home/user/genai`)
All 5 bootstrap iterations are complete:
- **Iter 0:** Foundation — project scaffolding, quick-task Python API
- **Iter 1:** Message bus (file-based JSON) + task state machine (6 states)
- **Iter 2:** Tools (file ops, git ops, task ops, test runner) + TOML config
- **Iter 3:** Base agent (LLM loop, tool dispatch, budget tracking) + context manager
- **Iter 4:** Planner agent + Builder agent with system prompts
- **Iter 5:** Runner/orchestrator, human gates, CLI entry point, end-to-end tests
- **Docs:** README.md, CLAUDE.md, spec, design doc, implementation plan, process docs

### Quick Task (`/home/user/quick-task`)
Full-featured CLI complete:
- Core: models, parser, writer, matcher, operations, discovery
- CLI commands: list, add, done/start/block/defer/cancel/reset, show, rename, remove, move, link, note, edit, check, init
- Python API (`api.py`): load_file, get_task, list_tasks, save + re-exports
- Validation: checker with syntax/duplicate/orphan detection
- Docs: README.md, CLAUDE.md, USAGE.md

## What's Next

The remaining work is the **quick-task improvements** from the Genesis bootstrap spec (§8). These are needed for Genesis to effectively manage tasks as an agentic system. Work should happen in the quick-task repo first, then the genai TASKS.md can be updated to reflect completion.

### Priority order (recommended):

1. **`#qt-api` — Python API module** (quick-task TASKS.md still shows `[ ]` but `api.py` already exists)
   - The code is done. The TASKS.md in quick-task needs to be updated to mark these subtasks `[x]`.

2. **`#qt-agent-meta` / `#qt-metadata` — Agent metadata fields**
   - Add first-class fields: `assignee`, `priority`, `created`, `updated`
   - CLI flags: `--assignee`, `--priority`
   - Filter support: `qt list --assignee @builder`
   - Spec: `spec/bootstrap-spec.md §8.2`

3. **`#qt-history` — Transition history / audit log**
   - Append history entries on status change
   - `qt show --history` display
   - JSON output includes history
   - Spec: `spec/bootstrap-spec.md §8.3`

4. **`#qt-locking` — File locking for concurrent access**
   - Advisory `.TASKS.md.lock` file
   - Timeout + stale lock detection
   - Spec: `spec/bootstrap-spec.md §8.4`

5. **`#qt-filters` — Filter/query enhancements**
   - Compound filters: `--assignee` + `--status` + `--priority`
   - `--has-metadata` flag
   - Spec: `spec/bootstrap-spec.md §8.5`

## Key Files to Read First

| Purpose | File |
|---------|------|
| Genesis spec (full system design) | `/home/user/genai/spec/bootstrap-spec.md` |
| Genesis design doc | `/home/user/genai/docs/plans/2026-03-20-genesis-design.md` |
| Genesis config | `/home/user/genai/genesis.toml` |
| Quick-task data models | `/home/user/quick-task/src/quick_task/models.py` |
| Quick-task operations | `/home/user/quick-task/src/quick_task/operations.py` |
| Quick-task API | `/home/user/quick-task/src/quick_task/api.py` |

## Notes

- Genesis depends on quick-task (`pip install -e ../quick-task`)
- The quick-task TASKS.md `#qt-api` section is stale — `api.py` already exists and works. Mark those subtasks done before starting new work.
- Both projects use Python 3.11+, pytest, hatchling builds
- Genesis uses the Anthropic SDK (`anthropic`) for LLM calls; all tests mock the LLM client
- The goal is for Genesis to eventually run its own task loop: pick a task from TASKS.md, plan it, implement it, test it, and open a PR — with human approval gates
