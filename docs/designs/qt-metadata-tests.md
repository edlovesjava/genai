# Test Specification: Agent-Oriented Metadata Fields (`qt-metadata`)

## Testing Strategy

- **Unit tests** for isolated logic in `metadata.py` and `operations.py`.
- **CLI integration tests** using `click.testing.CliRunner` with `runner.isolated_filesystem()` (matches the existing pattern in `test_cli.py`).
- **API tests** for the updated `list_tasks()` filter in `test_api.py`.
- **No mocking of the filesystem** — `CliRunner.isolated_filesystem()` handles that.
- **Monkeypatching `now_iso`** for deterministic timestamp assertions.

---

## 1. `tests/test_metadata.py` — **New file**

### `validate_priority`

| Test | Input | Expected |
|------|-------|----------|
| `test_validate_priority_valid_low` | `"low"` | Returns `"low"` |
| `test_validate_priority_valid_high` | `"HIGH"` | Returns `"high"` (case-normalised) |
| `test_validate_priority_valid_critical` | `"critical"` | Returns `"critical"` |
| `test_validate_priority_invalid` | `"urgent"` | Raises `ValueError` with message listing valid values |
| `test_validate_priority_empty_string` | `""` | Raises `ValueError` |

### `now_iso`

| Test | Expected |
|------|----------|
| `test_now_iso_format` | Returns a string matching regex `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z` |
| `test_now_iso_is_utc` | Parsed datetime has `tzinfo` of UTC (verify `+00:00` offset when parsed back) |

---

## 2. `tests/test_operations.py` — **Additions**

### `add_task` with metadata

All tests use `make_empty_task_file()` helper (already defined in the file).

```python
@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr("quick_task.metadata.now_iso", lambda: "2026-01-01T00:00:00Z")
```

| Test | Setup / Call | Assertions |
|------|-------------|------------|
| `test_add_task_with_assignee` | `add_task(tf, "T", assignee="@builder")` | `task.metadata["assignee"] == "@builder"` |
| `test_add_task_sets_created_and_updated` | `add_task(tf, "T", assignee="@builder")` | Both `created` and `updated` are `"2026-01-01T00:00:00Z"` |
| `test_add_task_with_priority` | `add_task(tf, "T", priority="high")` | `task.metadata["priority"] == "high"` |
| `test_add_task_priority_case_normalised` | `add_task(tf, "T", priority="HIGH")` | `task.metadata["priority"] == "high"` |
| `test_add_task_with_assignee_and_priority` | `add_task(tf, "T", assignee="@x", priority="low")` | Both fields set |
| `test_add_task_invalid_priority_raises` | `add_task(tf, "T", priority="urgent")` | Raises `ValueError`; no task added to list |
| `test_add_task_no_metadata_no_timestamps` | `add_task(tf, "T")` (no metadata args) | `task.metadata` is `{}` (no `created`/`updated`) |

### `set_metadata`

```python
def make_tf_with_task(title="My Task"):
    return TaskFile(
        path="test.md",
        lists=[TaskList(name="Tasks", tasks=[Task(title=title, status=TaskStatus.TODO)])]
    )
```

| Test | Call | Assertions |
|------|------|------------|
| `test_set_metadata_assignee` | `set_metadata(tf, "My Task", assignee="@planner")` | `task.metadata["assignee"] == "@planner"` |
| `test_set_metadata_priority` | `set_metadata(tf, "My Task", priority="medium")` | `task.metadata["priority"] == "medium"` |
| `test_set_metadata_stamps_updated` | `set_metadata(tf, "My Task", assignee="@x")` | `task.metadata["updated"] == "2026-01-01T00:00:00Z"` |
| `test_set_metadata_does_not_overwrite_created` | Task already has `created="2025-01-01T00:00:00Z"`, call `set_metadata(tf, "My Task", assignee="@x")` | `task.metadata["created"] == "2025-01-01T00:00:00Z"` (unchanged) |
| `test_set_metadata_overwrites_existing_assignee` | Task already has `assignee="@old"`, call `set_metadata(tf, "My Task", assignee="@new")` | `task.metadata["assignee"] == "@new"` |
| `test_set_metadata_no_args_no_stamp` | `set_metadata(tf, "My Task")` (no kwargs) | `task.metadata` is `{}`, returns task |
| `test_set_metadata_invalid_priority` | `set_metadata(tf, "My Task", priority="bad")` | Raises `ValueError`; `task.metadata` unchanged |
| `test_set_metadata_task_not_found` | `set_metadata(tf, "Nonexistent")` | Raises `TaskNotFoundError` (or equivalent) |
| `test_set_metadata_returns_task` | `result = set_metadata(tf, "My Task", assignee="@x")` | Returns the mutated `Task` object |

---

## 3. `tests/test_cli.py` — **Additions**

All tests use `click.testing.CliRunner` with `runner.isolated_filesystem()`.

### `qt add` with metadata flags

```markdown
## Tasks

- [ ] Existing
```

| Test | Command | Assertions |
|------|---------|------------|
| `test_add_with_assignee` | `["add", "New task", "--assignee", "@builder"]` | exit_code == 0; written TASKS.md contains `assignee: @builder` |
| `test_add_with_priority` | `["add", "New task", "--priority", "high"]` | exit_code == 0; written TASKS.md contains `priority: high` |
| `test_add_with_assignee_and_priority` | `["add", "T", "--assignee", "@x", "--priority", "low"]` | Both metadata lines in file |
| `test_add_with_invalid_priority` | `["add", "T", "--priority", "urgent"]` | exit_code != 0; error message mentions invalid value |
| `test_add_no_metadata_no_timestamp_lines` | `["add", "T"]` | File does not contain `created:` or `updated:` |

### `qt list` with filter flags

TASKS.md fixture:
```markdown
## Tasks

- [ ] Task A [#a]
    assignee: @builder
    priority: high
- [ ] Task B [#b]
    assignee: @planner
    priority: low
- [ ] Task C [#c]
```

| Test | Command | Assertions |
|------|---------|------------|
| `test_list_filter_by_assignee` | `["list", "--assignee", "@builder"]` | "Task A" in output; "Task B" not in output; "Task C" not in output |
| `test_list_filter_by_assignee_no_match` | `["list", "--assignee", "@nobody"]` | exit_code == 0; no tasks listed |
| `test_list_filter_by_priority` | `["list", "--priority", "high"]` | "Task A" in output; "Task B" not in output |
| `test_list_filter_assignee_and_status` | `["list", "--assignee", "@builder", "--status", "todo"]` | "Task A" in output |
| `test_list_json_includes_metadata` | `["list", "--json"]` | JSON output includes `"metadata"` key; `metadata.assignee == "@builder"` for Task A |

---

## 4. `tests/test_api.py` — **Additions**

Helper:
```python
def make_task_file():
    return TaskFile(path="t.md", lists=[
        TaskList(name="Tasks", tasks=[
            Task(title="A", status=TaskStatus.TODO, metadata={"assignee": "@builder", "priority": "high"}),
            Task(title="B", status=TaskStatus.TODO, metadata={"assignee": "@planner", "priority": "low"}),
            Task(title="C", status=TaskStatus.TODO, metadata={}),
        ])
    ])
```

| Test | Call | Expected |
|------|------|----------|
| `test_list_tasks_filter_by_assignee` | `list_tasks(tf, assignee="@builder")` | Returns `[A]` |
| `test_list_tasks_filter_by_priority` | `list_tasks(tf, priority="high")` | Returns `[A]` |
| `test_list_tasks_filter_assignee_and_priority` | `list_tasks(tf, assignee="@builder", priority="high")` | Returns `[A]` |
| `test_list_tasks_filter_assignee_and_priority_no_match` | `list_tasks(tf, assignee="@builder", priority="low")` | Returns `[]` |
| `test_list_tasks_no_filters_unchanged` | `list_tasks(tf)` | Returns all 3 tasks |
| `test_list_tasks_filter_by_priority_case_insensitive` | `list_tasks(tf, priority="HIGH")` | Returns `[A]` (priority normalised to lowercase) |

---

## 5. Edge Cases

| Case | Where tested | Expected behaviour |
|------|-------------|-------------------|
| Assignee value contains spaces (`"Alice Smith"`) | `test_metadata.py` | Stored as-is (no special handling; metadata writer quotes if needed) |
| Task with no metadata dict key gets filtered out cleanly | `test_api.py` | `.get()` returns `None`; task excluded without error |
| Both `--assignee` and `--list` in `qt list` | `test_cli.py` | Both filters applied (AND semantics) |
| `qt add` with `--priority medium` writes lowercase to file | `test_cli.py` | File contains `priority: medium` not `priority: Medium` |
| `now_iso()` is called exactly once per `add_task` with metadata | `test_operations.py` | `created == updated` on new task |

---

## Mocking Strategy

- **`quick_task.metadata.now_iso`** — monkeypatched in `test_operations.py` and optionally in `test_cli.py` to produce a fixed timestamp string for deterministic assertions.
- **No filesystem mocking needed** — `CliRunner.isolated_filesystem()` creates a temp directory.
- **No network or subprocess mocking needed** — the feature is purely in-memory + file I/O.
