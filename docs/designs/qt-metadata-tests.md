# Test Specification: Agent-Oriented Metadata Fields (`qt-metadata`)

> **Status:** Implementation is complete. All tests have been written. This document describes the tests that exist and what they cover.

## Testing Strategy

- **Unit tests** for isolated logic in `metadata.py` and `operations.py`.
- **CLI integration tests** using `click.testing.CliRunner` with `runner.isolated_filesystem()` (matches the existing pattern in `test_cli.py`).
- **API tests** for the updated `list_tasks()` filter in `test_api.py`.
- **No mocking of the filesystem** — `CliRunner.isolated_filesystem()` handles that.
- **Monkeypatching `quick_task.metadata.now_iso`** for deterministic timestamp assertions.

---

## 1. `tests/test_metadata.py` — **New file** (complete)

### Constants

| Test | What it checks |
|------|----------------|
| `test_field_constants_have_correct_string_values` | `FIELD_ASSIGNEE == "assignee"`, `FIELD_PRIORITY == "priority"`, `FIELD_CREATED == "created"`, `FIELD_UPDATED == "updated"` |
| `test_valid_priorities_contains_expected_levels` | `"low"`, `"medium"`, `"high"`, `"critical"` all in `VALID_PRIORITIES` |
| `test_valid_priorities_length` | Exactly 4 entries |
| `test_field_constants_match_models` | `FIELD_*` match `models.METADATA_*`; `VALID_PRIORITIES is PRIORITY_LEVELS` |

### `validate_priority`

| Test | Input | Expected |
|------|-------|----------|
| `test_validate_priority_accepts_low` | `"low"` | Returns `"low"` |
| `test_validate_priority_accepts_medium` | `"medium"` | Returns `"medium"` |
| `test_validate_priority_accepts_high` | `"high"` | Returns `"high"` |
| `test_validate_priority_accepts_critical` | `"critical"` | Returns `"critical"` |
| `test_validate_priority_lowercases_input` | `"HIGH"`, `"Critical"` | Returns `"high"`, `"critical"` |
| `test_validate_priority_rejects_invalid` | `"urgent"` | Raises `ValueError` matching `"Invalid priority"` |
| `test_validate_priority_error_message_includes_value` | `"bogus"` | Error message contains `"'bogus'"` |
| `test_validate_priority_error_message_lists_valid` | `"nope"` | Error message contains `"low"` |

### `now_iso`

| Test | Expected |
|------|----------|
| `test_now_iso_returns_string` | Returns a `str` |
| `test_now_iso_format` | Matches regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` |
| `test_now_iso_is_utc` | Monkeypatched to return fixed value; confirms function is patchable |

---

## 2. `tests/test_operations.py` — **Additions** (complete)

All tests use a `@pytest.fixture` or equivalent setup that monkeypatches `quick_task.metadata.now_iso` (or `quick_task.operations._now_iso`) to return `"2026-01-01T00:00:00Z"` for deterministic assertions.

### `add_task` with metadata

| Test | Call | Assertions |
|------|------|------------|
| `test_add_task_with_assignee` | `add_task(tf, "T", assignee="@builder")` | `task.metadata["assignee"] == "@builder"` |
| `test_add_task_sets_created_and_updated` | `add_task(tf, "T", assignee="@builder")` | `task.created` and `task.updated` are the fixed timestamp |
| `test_add_task_with_priority` | `add_task(tf, "T", priority="high")` | `task.metadata["priority"] == "high"` |
| `test_add_task_priority_case_normalised` | `add_task(tf, "T", priority="HIGH")` | `task.metadata["priority"] == "high"` |
| `test_add_task_with_assignee_and_priority` | `add_task(tf, "T", assignee="@x", priority="low")` | Both fields set |
| `test_add_task_invalid_priority_raises` | `add_task(tf, "T", priority="urgent")` | Raises `ValueError`; no task added to list |
| `test_add_task_no_timestamps_if_stamp_created_false` | `add_task(tf, "T", stamp_created=False)` | `task.metadata` has no `created`/`updated` keys |

### `set_task_metadata`

| Test | Call | Assertions |
|------|------|------------|
| `test_set_task_metadata_assignee` | `set_task_metadata(tf, "My Task", assignee="@planner")` | `task.metadata["assignee"] == "@planner"` |
| `test_set_task_metadata_priority` | `set_task_metadata(tf, "My Task", priority="medium")` | `task.metadata["priority"] == "medium"` |
| `test_set_task_metadata_stamps_updated` | `set_task_metadata(tf, "My Task", assignee="@x")` | `task.metadata["updated"] == "2026-01-01T00:00:00Z"` |
| `test_set_task_metadata_does_not_overwrite_created` | Task has `created="2025-01-01T00:00:00Z"`; call `set_task_metadata(tf, ..., assignee="@x")` | `task.metadata["created"]` unchanged |
| `test_set_task_metadata_overwrites_existing_assignee` | Task has `assignee="@old"`; call `set_task_metadata(tf, ..., assignee="@new")` | `task.metadata["assignee"] == "@new"` |
| `test_set_task_metadata_no_stamp_when_false` | `set_task_metadata(tf, "My Task", stamp_updated=False)` | No `updated` key added |
| `test_set_task_metadata_invalid_priority` | `set_task_metadata(tf, "My Task", priority="bad")` | Raises `ValueError`; `task.metadata` unchanged |
| `test_set_task_metadata_task_not_found` | `set_task_metadata(tf, "Nonexistent")` | Raises `TaskNotFoundError` |
| `test_set_task_metadata_returns_task` | `result = set_task_metadata(tf, "My Task", assignee="@x")` | Returns the mutated `Task` object |
| `test_set_task_metadata_clear_with_empty_string` | `set_task_metadata(tf, "My Task", assignee="")` | `task.assignee is None` |

---

## 3. `tests/test_cli.py` — **Additions** (complete)

All tests use `CliRunner` with `isolated_filesystem()`.

### `qt add` with metadata flags

TASKS.md fixture:
```markdown
## Tasks

- [ ] Existing
```

| Test | Command | Assertions |
|------|---------|------------|
| `test_add_with_assignee` | `["add", "New task", "--assignee", "@builder"]` | exit_code == 0; TASKS.md contains `assignee: @builder` |
| `test_add_with_priority` | `["add", "New task", "--priority", "high"]` | exit_code == 0; TASKS.md contains `priority: high` |
| `test_add_with_assignee_and_priority` | `["add", "T", "--assignee", "@x", "--priority", "low"]` | Both metadata lines in file |
| `test_add_with_invalid_priority` | `["add", "T", "--priority", "urgent"]` | exit_code != 0; error message mentions invalid value |
| `test_add_no_extra_metadata_without_flags` | `["add", "T"]` with `stamp_created=False` path | File does not contain spurious lines (timestamps still written by default — test verifies no crash) |

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
| `test_list_json_includes_metadata` | `["list", "--json"]` | JSON output has `"metadata"` key; `metadata["assignee"] == "@builder"` for Task A |
| `test_list_filter_assignee_case_insensitive` | `["list", "--assignee", "@Builder"]` | Matches `@builder` in file |

---

## 4. `tests/test_api.py` — **Additions** (complete)

Helper fixture `METADATA_MD`:
```markdown
## Tasks

- [ ] Alpha task [#alpha]
    assignee: @builder
    priority: high
- [ ] Beta task [#beta]
    assignee: @planner
    priority: low
- [ ] Gamma task [#gamma]
    assignee: @builder
    priority: critical
- [ ] Unassigned task [#unassigned]
```

| Test | Call | Expected |
|------|------|----------|
| `test_list_tasks_filter_by_assignee` | `list_tasks(tf, assignee="@builder")` | Alpha, Gamma in results; Beta, Unassigned not in results |
| `test_list_tasks_filter_by_priority` | `list_tasks(tf, priority="high")` | Alpha only |
| `test_list_tasks_filter_assignee_case_insensitive` | `list_tasks(tf, assignee="@builder")` on file with `@Builder` | Match found (1 result) |
| `test_list_tasks_filter_priority_case_insensitive` | `list_tasks(tf, priority="high")` on file with `priority: HIGH` | Match found |
| `test_list_tasks_filter_assignee_and_priority` | `list_tasks(tf, assignee="@builder", priority="high")` | Alpha only |
| `test_list_tasks_filter_assignee_no_match` | `list_tasks(tf, assignee="@nobody")` | `[]` |
| `test_list_tasks_filter_priority_no_match` | `list_tasks(tf, priority="medium")` | `[]` |

### API symbol exports

| Test | What it checks |
|------|----------------|
| `test_set_task_metadata_in_api` | `from quick_task.api import set_task_metadata` works and is callable |
| `test_set_task_metadata_via_api` | `set_task_metadata(tf, "#unassigned", assignee="@runner", stamp_updated=False)` sets field |
| `test_metadata_constants_in_api_all` | All 7 metadata symbols present in `api.__all__` |
| `test_metadata_constants_importable_from_api` | All constants importable; values are correct strings; `validate_priority` and `now_iso` callable |

---

## 5. Edge Cases

| Case | Where tested | Expected behaviour |
|------|-------------|-------------------|
| Task with no `assignee` key gets filtered out cleanly | `test_api.py` | `.get()` returns `None`; task excluded without error |
| Both `--assignee` and `--list` in `qt list` | `test_cli.py` | Both filters applied (AND semantics) |
| `qt add --priority medium` writes lowercase to file | `test_cli.py` | File contains `priority: medium` |
| `now_iso()` is monkeypatchable | `test_operations.py` | `monkeypatch.setattr("quick_task.operations._now_iso", ...)` or `"quick_task.metadata.now_iso"` |
| Clearing a field with `""` | `test_operations.py` | `task.assignee is None` after `set_task_metadata(..., assignee="")` |
| Priority setter validates on `Task` model directly | `test_models.py` (if it exists) or `test_operations.py` | `task.priority = "bad"` raises `ValueError` |

---

## Mocking Strategy

- **`quick_task.operations._now_iso`** — monkeypatched in `test_operations.py` for deterministic timestamp assertions. This is the internal helper used by `add_task` and `set_task_metadata` before they delegated to `metadata.now_iso`.
- **`quick_task.metadata.now_iso`** — the canonical patchpoint; monkeypatched in `test_metadata.py` and `test_cli.py` if timestamp assertions are needed.
- **No filesystem mocking needed** — `CliRunner.isolated_filesystem()` creates a temp directory.
- **No network or subprocess mocking needed** — the feature is purely in-memory + file I/O.
