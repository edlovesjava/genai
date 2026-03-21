# Truncate read_file Tool Output — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a configurable character limit to the `read_file` tool so agents don't blow up their token budget reading large files.

**Architecture:** Add `max_read_chars` to `GenesisConfig` (default 10,000), loaded from `genesis.toml` under a new `[tools]` section. `FileOps.read_file` gains a `max_chars` parameter that defaults to the config value. When a file exceeds the limit, output is truncated with a notice showing total size. The tool schema in planner/builder is updated to expose the optional `max_chars` parameter so agents can override it per-call.

**Tech Stack:** Python, pytest, unittest.mock, dataclasses, tomllib

---

### Task 1: Add `ToolsConfig` to config and wire it up

**Files:**
- Modify: `src/genesis/config.py`
- Modify: `genesis.toml`
- Test: `tests/test_tools.py` (existing config tests are here)

**Step 1: Write the failing test**

Add to `tests/test_tools.py` after the existing imports:

```python
from genesis.config import GenesisConfig, load_config
```

Add a new test class at the end of the file:

```python
class TestToolsConfig:
    def test_default_max_read_chars(self):
        config = GenesisConfig()
        assert config.tools.max_read_chars == 10_000

    def test_load_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "genesis.toml"
        toml_file.write_text('[tools]\nmax_read_chars = 5000\n')
        config = load_config(toml_file)
        assert config.tools.max_read_chars == 5000
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools.py::TestToolsConfig -v`
Expected: FAIL — `GenesisConfig` has no `tools` attribute.

**Step 3: Write minimal implementation**

In `src/genesis/config.py`, add `ToolsConfig` dataclass after `HumanGatesConfig`:

```python
@dataclass
class ToolsConfig:
    max_read_chars: int = 10_000
```

Add it to `GenesisConfig`:

```python
@dataclass
class GenesisConfig:
    project_name: str = "genesis"
    tasks_file: str = "TASKS.md"
    genesis_dir: str = ".genesis"
    llm: LLMConfig = field(default_factory=LLMConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    human_gates: HumanGatesConfig = field(default_factory=HumanGatesConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
```

In `load_config`, add parsing after `gates_section`:

```python
tools_section = raw.get("tools", {})
```

And pass it to the constructor:

```python
tools=ToolsConfig(**{k: v for k, v in tools_section.items() if k in ToolsConfig.__dataclass_fields__}),
```

In `genesis.toml`, add after the `[human_gates]` section:

```toml
[tools]
max_read_chars = 10000
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tools.py::TestToolsConfig -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/genesis/config.py genesis.toml tests/test_tools.py
git commit -m "feat: add ToolsConfig with max_read_chars setting"
```

---

### Task 2: Add truncation to `FileOps.read_file`

**Files:**
- Modify: `src/genesis/tools/file_ops.py:21-26`
- Test: `tests/test_tools.py`

**Step 1: Write the failing test**

Add to `TestFileOps` in `tests/test_tools.py`:

```python
def test_read_file_truncates_large_file(self, config: GenesisConfig, tmp_path: Path):
    config.tools.max_read_chars = 50
    ops = FileOps(config, project_root=tmp_path)
    (tmp_path / "big.txt").write_text("x" * 200)
    result = ops.read_file("big.txt")
    assert len(result) < 200
    assert "x" * 50 in result
    assert "truncated" in result.lower()
    assert "200" in result  # Shows total file size

def test_read_file_no_truncation_when_under_limit(self, config: GenesisConfig, tmp_path: Path):
    config.tools.max_read_chars = 500
    ops = FileOps(config, project_root=tmp_path)
    (tmp_path / "small.txt").write_text("hello world")
    result = ops.read_file("small.txt")
    assert result == "hello world"

def test_read_file_max_chars_override(self, config: GenesisConfig, tmp_path: Path):
    config.tools.max_read_chars = 50
    ops = FileOps(config, project_root=tmp_path)
    (tmp_path / "big.txt").write_text("x" * 200)
    # Override with larger limit
    result = ops.read_file("big.txt", max_chars=300)
    assert result == "x" * 200  # No truncation since 200 < 300
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py::TestFileOps::test_read_file_truncates_large_file tests/test_tools.py::TestFileOps::test_read_file_max_chars_override -v`
Expected: FAIL — `read_file` doesn't accept `max_chars`.

**Step 3: Write minimal implementation**

Replace `read_file` in `src/genesis/tools/file_ops.py`:

```python
def read_file(self, path: str, max_chars: int | None = None) -> str:
    """Read and return file contents, truncating if over the limit."""
    resolved = self._resolve(path)
    if not resolved.exists():
        return f"Error: File not found: {path}"
    content = resolved.read_text()
    limit = max_chars if max_chars is not None else self.config.tools.max_read_chars
    if len(content) > limit:
        return (
            f"{content[:limit]}\n\n"
            f"[Truncated: showing {limit:,} of {len(content):,} characters. "
            f"Use max_chars parameter to read more.]"
        )
    return content
```

**Step 4: Run all FileOps tests**

Run: `pytest tests/test_tools.py::TestFileOps -v`
Expected: ALL PASS (new tests + existing `test_read_file` and `test_read_missing_file`)

**Step 5: Commit**

```bash
git add src/genesis/tools/file_ops.py tests/test_tools.py
git commit -m "feat: add truncation to read_file with configurable max_chars"
```

---

### Task 3: Update tool schema in planner and builder

**Files:**
- Modify: `src/genesis/agents/planner.py:57-66`
- Modify: `src/genesis/agents/builder.py:59-68`

**Step 1: Run existing tests as baseline**

Run: `pytest tests/test_planner_builder.py -v`
Expected: ALL PASS

**Step 2: Update tool schemas**

In both `src/genesis/agents/planner.py` (lines 61-65) and `src/genesis/agents/builder.py` (lines 63-67), update the `read_file` input_schema from:

```python
input_schema={
    "type": "object",
    "properties": {"path": {"type": "string", "description": "File path to read."}},
    "required": ["path"],
},
```

to:

```python
input_schema={
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path to read."},
        "max_chars": {"type": "integer", "description": "Max characters to return. Defaults to config value (10000)."},
    },
    "required": ["path"],
},
```

**Step 3: Run all tests**

Run: `pytest -v`
Expected: ALL PASS — no regressions

**Step 4: Commit**

```bash
git add src/genesis/agents/planner.py src/genesis/agents/builder.py
git commit -m "feat: expose max_chars parameter in read_file tool schema"
```
