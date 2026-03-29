# Design: Agent-Oriented Metadata Fields (`qt-metadata`)

## Overview

Add first-class metadata fields (`assignee`, `priority`, `created`, `updated`) to quick-task tasks, with CLI flags to set them on `qt add`, and filter support in `qt list`.

These fields live in the task's existing `metadata: dict[str, str]` (see `models.py:Task`) — no schema changes to the `Task` model are required. The parser, writer, and checker already handle arbitrary metadata key/value pairs. This feature is purely additive: a new helper module, new `operations.py` function, extended `add_task()`, updated `api.list_tasks()`, and new CLI options.

> **Status:** Implementation is complete. All source files and test files have been written. This document reflects the as-built design.

---

## Current Architecture (Grounding)

| File | Relevance |
|------|-----------|
| `src/quick_task/models.py` | `Task.metadata: dict[str, str]` + convenience properties `assignee`, `priority`, `created`, `updated` |
| `src/quick_task/metadata.py` | Constants `FIELD_*`, `VALID_PRIORITIES`, `validate_priority()`, `now_iso()` |
| `src/quick_task/operations.py` | `add_task()` with `assignee`/`priority`/`stamp_created`; `set_task_metadata()` |
| `src/quick_task/api.py` | `list_tasks()` filters by `assignee`, `priority` (case-insensitive); all metadata symbols in `__all__` |
| `src/quick_task/cli.py` | `add` has `--assignee`/`--priority`; `list` has `--assignee`/`--priority` filters |

---

## What Was Built

### 1. `src/quick_task/models.py` — **Modified**

Added four constants and four convenience property pairs on `Task`:

```python
# Constants
METADATA_ASSIGNEE = "assignee"
METADATA_PRIORITY = "priority"
METADATA_CREATED  = "created"
METADATA_UPDATED  = "updated"
PRIORITY_LEVELS   = ("low", "medium", "high", "critical")

# Task properties (get/set on task.metadata dict)
task.assignee  # str | None
task.priority  # str | None  — setter validates against PRIORITY_LEVELS
task.created   # str | None  — ISO-8601 string
task.updated   # str | None  — ISO-8601 string
```

The `Task` dataclass stores everything in `metadata: dict[str, str]`. The properties are thin wrappers that get/set/pop keys in that dict.

---

### 2. `src/quick_task/metadata.py` — **New file**

Centralises metadata key names and validation to avoid magic strings:

```python
# Re-exports from models.py (single source of truth)
FIELD_ASSIGNEE  = "assignee"   # re-exported as METADATA_ASSIGNEE
FIELD_PRIORITY  = "priority"
FIELD_CREATED   = "created"
FIELD_UPDATED   = "updated"
VALID_PRIORITIES = ("low", "medium", "high", "critical")   # re-exported as PRIORITY_LEVELS

def validate_priority(value: str) -> str:
    """Lowercase and validate. Returns lowercased value or raises ValueError."""

def now_iso() -> str:
    """Return current UTC time as ISO-8601 string, e.g. '2026-03-21T01:38:07Z'."""
```

`now_iso()` wraps `datetime.datetime.now(tz=datetime.timezone.utc).strftime(...)` as a standalone function so tests can monkeypatch it.

---

### 3. `src/quick_task/operations.py` — **Modified**

#### New function: `set_task_metadata()`

```python
def set_task_metadata(
    task_file: TaskFile,
    query: str,
    *,
    assignee: str | None = None,
    priority: str | None = None,
    stamp_updated: bool = True,
) -> Task:
```

- Finds task by bookmark or title substring; raises `TaskNotFoundError` if not found.
- Sets `assignee` and/or `priority` on the task (via property setters).
- Passing `""` (empty string) **clears** a field (sets it to `None`); passing `None` **leaves** it unchanged.
- Validates priority via `PRIORITY_LEVELS`; raises `ValueError` on bad input before any mutation.
- Stamps `task.updated` with `now_iso()` when `stamp_updated=True` (default).
- Does **not** touch `task.created`.
- If neither `assignee` nor `priority` is given and `stamp_updated=False`, returns task unchanged.

#### Extended: `add_task()`

```python
def add_task(
    task_file: TaskFile,
    title: str,
    list_name: str | None = None,
    parent_query: str | None = None,
    *,
    assignee: str | None = None,
    priority: str | None = None,
    stamp_created: bool = True,
) -> Task:
```

- Validates `priority` first (raises `ValueError` before mutating state).
- Sets `assignee` and `priority` on the new task if provided.
- Stamps `task.created` (and `task.updated`) with `now_iso()` when `stamp_created=True` (default).
- `stamp_created=True` always runs regardless of whether `assignee`/`priority` are provided — timestamps are stamped unconditionally.

**Note:** The design originally said "only stamp when metadata provided", but the implementation stamps `created` by default (`stamp_created=True`). This is a deliberate simplification — callers that want no timestamps pass `stamp_created=False`.

---

### 4. `src/quick_task/api.py` — **Modified**

#### `list_tasks()` signature

```python
def list_tasks(
    task_file: TaskFile,
    *,
    list_name: str | None = None,
    status: TaskStatus | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    flat: bool = False,
) -> list[Task]:
```

Filtering:
- `assignee`: case-insensitive exact match on `task.assignee` (via `.lower()` comparison).
- `priority`: case-insensitive exact match on `task.priority`.

#### Symbols in `__all__`

`set_task_metadata`, `FIELD_ASSIGNEE`, `FIELD_PRIORITY`, `FIELD_CREATED`, `FIELD_UPDATED`, `VALID_PRIORITIES`, `validate_priority`, `now_iso` are all exported.

---

### 5. `src/quick_task/cli.py` — **Modified**

#### `qt add` — new options

```
--assignee TEXT               Assign to an agent or person (e.g. @builder)
--priority [low|medium|high|critical]   Task priority
```

`--priority` uses `click.Choice` for automatic validation with a clear error message.

#### `qt list` — new filter options

```
--assignee TEXT    Filter by assignee (case-insensitive exact match)
--priority TEXT    Filter by priority (low/medium/high/critical)
```

CLI filters operate on the dict-of-dicts produced by `collect_with_list()`, accessing `t["task"].metadata`.

JSON output (`--json`) includes `"metadata": dict(task.metadata)` for all tasks.

---

## File Paths Summary

| Path | Action |
|------|--------|
| `../quick-task/src/quick_task/models.py` | **Modified** — constants + Task properties |
| `../quick-task/src/quick_task/metadata.py` | **Created** — constants + helpers |
| `../quick-task/src/quick_task/operations.py` | **Modified** — `set_task_metadata()`, extended `add_task()` |
| `../quick-task/src/quick_task/cli.py` | **Modified** — new flags on `add` and `list` commands |
| `../quick-task/src/quick_task/api.py` | **Modified** — expose new symbols, extend `list_tasks()` |
| `../quick-task/tests/test_metadata.py` | **Created** — unit tests for `metadata.py` |
| `../quick-task/tests/test_operations.py` | **Modified** — tests for `set_task_metadata`, extended `add_task` |
| `../quick-task/tests/test_cli.py` | **Modified** — tests for new CLI flags |
| `../quick-task/tests/test_api.py` | **Modified** — tests for extended `list_tasks()` |

---

## Key Design Decisions

1. **No format changes.** `Task.metadata: dict[str, str]` already existed. The four new fields are simply well-known keys in that dict. Parser, writer, and checker are untouched.

2. **Properties on `Task` model.** `task.assignee`, `task.priority`, `task.created`, `task.updated` are thin property wrappers on `task.metadata`. This gives a clean API without duplicating storage.

3. **`metadata.py` re-exports from `models.py`.** Single source of truth for constants lives in `models.py`; `metadata.py` re-exports them under the public names (`FIELD_*`) so the API is clean.

4. **Case-insensitive filtering.** Both `list_tasks()` in `api.py` and the `list` command in `cli.py` normalise to lowercase for comparison. Assignees like `@Builder` and `@builder` match each other.

5. **`click.Choice` for `--priority` in CLI.** Gives a clean built-in error message for invalid values. `PRIORITY_LEVELS` check is also in the `priority` property setter on `Task` as belt-and-suspenders for programmatic callers.

6. **`set_task_metadata` name (not `set_metadata`).** More descriptive and consistent with `update_status` naming. All tests use `set_task_metadata`.

7. **`stamp_updated=True` default on `set_task_metadata`.** The `updated` field is always stamped when metadata is mutated; pass `stamp_updated=False` in tests for deterministic assertions.

8. **`now_iso()` as a standalone function.** Makes it monkeypatchable in tests without `unittest.mock.patch` on `datetime`.

9. **Empty string clears a field.** In `set_task_metadata`, passing `assignee=""` removes the field; passing `None` leaves it unchanged. This allows clearing without a separate API.

---

## Markdown Representation

Fields are stored as ordinary metadata lines beneath the task (already supported by the parser/writer):

```markdown
- [ ] Implement auth [#auth]
    assignee: @builder
    priority: high
    created: 2026-03-21T01:38:07Z
    updated: 2026-03-21T01:38:07Z
```
