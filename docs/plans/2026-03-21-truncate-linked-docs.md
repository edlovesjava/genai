# Truncate Linked Docs in Context Manager — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Truncate linked documentation files loaded into agent context so large design docs don't consume the entire token budget.

**Architecture:** `_get_linked_docs` in `context/manager.py` already reads full file contents via `resolved.read_text()`. Add truncation using `config.tools.max_read_chars`, with a notice when truncated. Single task — the config infrastructure already exists from the read_file truncation work.

**Tech Stack:** Python, pytest

---

### Task 1: Add truncation to `_get_linked_docs`

**Files:**
- Modify: `src/genesis/context/manager.py:111-120`
- Test: `tests/test_context.py`

**Step 1: Write the failing test**

Add to `tests/test_context.py` in `TestBuildPlannerContext`:

```python
def test_truncates_large_linked_docs(self, setup):
    cm, _, tmp_path = setup
    # Create a large doc file
    doc_path = tmp_path / "docs" / "design.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("x" * 20_000)
    # Create task file pointing to it
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(
        f"## Tasks [#tasks]\n\n"
        f"- [ ] My task [#my-task]\n"
        f"    docs: {doc_path}\n"
    )
    cm.config.tasks_file = str(task_file)
    cm.config.tools.max_read_chars = 500
    context = cm.build_planner_context("#my-task")
    combined = " ".join(m["content"] for m in context)
    assert "Design Documentation" in combined
    assert "truncated" in combined.lower()
    assert len(combined) < 20_000
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_context.py::TestBuildPlannerContext::test_truncates_large_linked_docs -v`
Expected: FAIL — linked doc is 20K chars, no truncation applied.

**Step 3: Write minimal implementation**

In `src/genesis/context/manager.py`, modify `_get_linked_docs` — replace the file reading block. Change:

```python
            for doc_path in docs.split(","):
                resolved = Path(doc_path)
                if resolved.exists():
                    content = resolved.read_text()
                    parts.append(f"### {doc_path}\n{content}")
                else:
                    parts.append(f"### {doc_path}\n(file not found)")
```

to:

```python
            limit = self.config.tools.max_read_chars
            for doc_path in docs.split(","):
                resolved = Path(doc_path)
                if resolved.exists():
                    content = resolved.read_text()
                    if len(content) > limit:
                        content = (
                            f"{content[:limit]}\n\n"
                            f"[Truncated: showing {limit:,} of {len(content):,} characters.]"
                        )
                    parts.append(f"### {doc_path}\n{content}")
                else:
                    parts.append(f"### {doc_path}\n(file not found)")
```

**Step 4: Run all context tests**

Run: `pytest tests/test_context.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/genesis/context/manager.py tests/test_context.py
git commit -m "feat: truncate linked docs in context manager"
```
