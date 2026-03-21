# Design: Agent-Oriented Metadata Fields (`qt-metadata`)

## Overview

Add first-class metadata fields (`assignee`, `priority`, `created`, `updated`) to quick-task tasks, with CLI flags to set them on `qt add`, and filter support in `qt list`.

These fields live in the task's existing `metadata: dict[str, str]` (see `models.py:Task`) — no schema changes to the `Task` model are required. The parser, writer, and checker already handle arbitrary metadata key/value pairs. This feature is purely additive: a new helper module, new `operations.py` function, extended `add_task()`, updated `api.list_tasks()`, and new CLI options.

---

## Current Architecture (Grounding)

| File | Relevance |
|------|-----------|
| `src/quick_task/models.py` | `Task.metadata: dict[str, str]` — already exists |
| `src/quick_task/operations.py` | `add_task()` creates plain `Task(title, status=TODO)` with no metadata |
| `src/quick_task/api.py` | `list_tasks()` filters by `list_name` and `status` only |
| `src/quick_task/cli.py` | `add` command has `--list`, `--parent` only; `list` command has `--status`, `--list`, `--json`, `--verbose` |

---

## What Needs to Be Built

### 1. `src/quick_task/metadata.py` — **New file**

Centralise metadata key names and validation to avoid magic strings.

```python
FIELD_ASSIGNEE = "assignee"
FIELD_PRIORITY = "priority"
FIELD_CREATED  = "created"
FIELD_UPDATED  = "updated"

VALID_PRIORITIES = ("low", "medium", "high", "critical")

def validate_priority(value: str) -> str:
    """Lowercase and validate. Raises ValueError on bad input."""

def now_iso() -> str:
    """Return current UTC time as ISO-8601 string, e.g. '2026-03-21T01:38:07Z'."""
```

`now_iso()` wraps `datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` as a standalone function so tests can monkeypatch it.

---

### 2. `src/quick_task/operations.py` — **Modified**

#### New function: `set_metadata()`

```python
def set_metadata(
    task_file: TaskFile,
    query: str,
    *,
    assignee: str | None = None,
    priority: str | None = None,
) -> Task:
    """
    Set assignee and/or priority on a matched task.
    Stamps metadata["updated"] with now_iso().
    If neither assignee nor priority is supplied, returns the task unchanged (no stamp).
    Raises TaskNotFoundError if query doesn't match.
    Raises ValueError if priority is invalid (via validate_priority).
    """
```

#### Extended: `add_task()`

Add two new keyword-only parameters:

```python
def add_task(
    task_file: TaskFile,
    title: str,
    list_name: str | None = None,
    parent_query: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
) -> Task:
```

When `assignee` or `priority` is provided:
- Validates priority first (raises `ValueError` before mutating state).
- Sets the metadata fields on the new task.
- Stamps both `created` and `updated` with `now_iso()`.

When neither is provided, behaviour is identical to the current implementation (no timestamp noise).

**Import in operations.py**: `from quick_task.metadata import validate_priority, now_iso, FIELD_ASSIGNEE, FIELD_PRIORITY, FIELD_CREATED, FIELD_UPDATED`

---

### 3. `src/quick_task/cli.py` — **Modified**

#### `qt add` — new options

```python
@click.option("--assignee", help="Assign to an agent or person (e.g. @builder)")
@click.option("--priority", type=click.Choice(["low","medium","high","critical"], case_sensitive=False), help="Task priority")
```

Updated command body:
```python
def add(ctx, title, list_name, parent_query, assignee, priority):
    ...
    try:
        task = op_add_task(task_file, title, list_name=list_name,
                           parent_query=parent_query, assignee=assignee, priority=priority)
        write_file(task_file)
        console.print(f"[green]Added:[/green] {task.title}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)
```

Using `click.Choice` for `--priority` gives automatic validation with a clear error message — no need to call `validate_priority` explicitly in the CLI layer (it's still called inside `add_task()` as a belt-and-suspenders check).

#### `qt list` — new filter options

```python
@click.option("--assignee", help="Filter by assignee (exact match)")
@click.option("--priority", help="Filter by priority (exact match)")
```

Updated filter section in `list_tasks` command (after the existing status filter):
```python
if assignee:
    tasks = [t for t in tasks if t["task"].metadata.get("assignee") == assignee]
if priority:
    tasks = [t for t in tasks if t["task"].metadata.get("priority") == priority.lower()]
```

Note: `tasks` here is a list of dicts produced by `collect_with_list()` — access the `Task` object via `t["task"]`.

Also update the `--json` output to include `metadata`:
```python
output = [
    {
        "title": t["task"].title,
        "status": t["status"].name.lower(),
        "list": t["list"],
        "bookmark": t["task"].bookmark,
        "metadata": dict(t["task"].metadata),   # ADD THIS
    }
    for t in tasks
]
```

---

### 4. `src/quick_task/api.py` — **Modified**

#### Update `list_tasks()` signature

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

Add after the existing `status` filter:
```python
if assignee is not None:
    tasks = [t for t in tasks if t.metadata.get("assignee") == assignee]
if priority is not None:
    tasks = [t for t in tasks if t.metadata.get("priority") == priority.lower()]
```

#### Expose new symbols in `__all__`

```python
from quick_task.operations import (
    ...
    set_metadata,       # ADD
)
from quick_task.metadata import (   # ADD new import block
    FIELD_ASSIGNEE,
    FIELD_PRIORITY,
    FIELD_CREATED,
    FIELD_UPDATED,
    VALID_PRIORITIES,
    validate_priority,
)
```

Add these to `__all__`.

---

## File Paths Summary

| Path | Action |
|------|--------|
| `../quick-task/src/quick_task/metadata.py` | **Create** — constants + helpers |
| `../quick-task/src/quick_task/operations.py` | **Modify** — add `set_metadata()`, extend `add_task()` |
| `../quick-task/src/quick_task/cli.py` | **Modify** — new flags on `add` and `list` commands |
| `../quick-task/src/quick_task/api.py` | **Modify** — expose new symbols, extend `list_tasks()` |
| `../quick-task/tests/test_metadata.py` | **Create** — unit tests for `metadata.py` |
| `../quick-task/tests/test_operations.py` | **Modify** — new tests for `set_metadata`, extended `add_task` |
| `../quick-task/tests/test_cli.py` | **Modify** — tests for new CLI flags |
| `../quick-task/tests/test_api.py` | **Modify** — tests for extended `list_tasks()` |

---

## Key Design Decisions

1. **No model changes.** `Task.metadata: dict[str, str]` already exists. The four new fields (`assignee`, `priority`, `created`, `updated`) are simply well-known keys in that dict. Parser, writer, and checker are untouched.

2. **`updated` only on explicit metadata ops.** Auto-stamping on every status change would add noise to every existing task file. Only `set_metadata()` and `add_task(assignee=...|priority=...)` write timestamps.

3. **`created` only at `add_task` time.** `set_metadata()` writes `updated` but never backfills `created`. This keeps the invariant: `created` means "this task was added with metadata".

4. **Exact-match filtering.** `--assignee @builder` is a case-sensitive exact match on `task.metadata.get("assignee")`. Assignees are controlled identifiers; fuzzy matching adds complexity without clear benefit.

5. **`click.Choice` for `--priority` in CLI.** Gives a clean built-in error message for invalid values. `validate_priority()` is still called inside `operations.add_task()` for programmatic callers.

6. **No changes to `--json` format for `show`.** `task_to_dict()` already includes `"metadata": dict(task.metadata)`. The new fields appear automatically in `show --json`.

7. **`now_iso()` as a standalone function.** Makes it monkeypatchable in tests without needing `unittest.mock.patch` on `datetime`.

8. **`set_metadata()` with no args is a no-op.** If neither `assignee` nor `priority` is given, the function returns the task unchanged and does not stamp `updated`. This avoids silent side-effects.

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
