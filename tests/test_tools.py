"""Tests for all tool modules."""

from pathlib import Path

import pytest

from genesis.bus.message_bus import MessageBus
from genesis.config import GenesisConfig, HumanGatesConfig, load_config
from genesis.tools.file_ops import FileOps, ProtectedPathError
from genesis.tools.task_ops import TaskOps

SAMPLE_TASKS = """\
## Tasks [#tasks]

- [ ] First task [#t1]
- [~] Active task [#t2]
"""


@pytest.fixture
def config(tmp_path: Path) -> GenesisConfig:
    task_file = tmp_path / "TASKS.md"
    task_file.write_text(SAMPLE_TASKS)
    return GenesisConfig(
        tasks_file=str(task_file),
        genesis_dir=str(tmp_path / ".genesis"),
        human_gates=HumanGatesConfig(
            protected_paths=[".github/", "genesis.toml"],
            require_approval=["merge"],
        ),
    )


@pytest.fixture
def bus(tmp_path: Path) -> MessageBus:
    return MessageBus(tmp_path / ".genesis" / "messages")


class TestTaskOps:
    def test_list_tasks(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        result = ops.list_tasks()
        assert "t1" in result
        assert "t2" in result

    def test_list_tasks_empty_filter(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        result = ops.list_tasks(status="done")
        assert result == "No tasks found."

    def test_get_task_status(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        result = ops.get_task_status("#t1")
        assert "TODO" in result

    def test_update_task_status(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        result = ops.update_task_status("#t1", "ASSIGNED", "planner", "starting")
        assert "ASSIGNED" in result

    def test_add_task(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        result = ops.add_task("New task", "Tasks")
        assert "New task" in result

    def test_get_task_history_empty(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        result = ops.get_task_history("#t1")
        assert "No transitions" in result

    def test_get_task_history_with_transitions(self, config: GenesisConfig, bus: MessageBus):
        ops = TaskOps(config, bus)
        ops.update_task_status("#t1", "ASSIGNED", "planner", "starting")
        result = ops.get_task_history("#t1")
        assert "TODO" in result
        assert "ASSIGNED" in result


class TestFileOps:
    def test_read_file(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        (tmp_path / "hello.txt").write_text("hello world")
        result = ops.read_file("hello.txt")
        assert result == "hello world"

    def test_read_missing_file(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        result = ops.read_file("nope.txt")
        assert "not found" in result.lower()

    def test_write_file(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        result = ops.write_file("output.txt", "data")
        assert "Wrote" in result
        assert (tmp_path / "output.txt").read_text() == "data"

    def test_write_creates_directories(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        ops.write_file("deep/nested/file.txt", "content")
        assert (tmp_path / "deep" / "nested" / "file.txt").read_text() == "content"

    def test_protected_path_blocked(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        with pytest.raises(ProtectedPathError):
            ops.write_file(".github/workflows/ci.yml", "malicious")

    def test_protected_path_exact_match(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        with pytest.raises(ProtectedPathError):
            ops.write_file("genesis.toml", "overwrite")

    def test_protected_path_with_approval(self, config: GenesisConfig, tmp_path: Path):
        ops = FileOps(config, project_root=tmp_path)
        result = ops.write_file("genesis.toml", "approved content", approved=True)
        assert "Wrote" in result

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


class TestTestRunner:
    def test_run_tests_returns_output(self, config: GenesisConfig, tmp_path: Path):
        from genesis.tools.test_runner import TestRunner

        # Create a trivial test file.
        (tmp_path / "test_trivial.py").write_text("def test_pass(): assert True\n")
        runner = TestRunner(config, project_root=tmp_path)
        result = runner.run_tests()
        assert "PASSED" in result

    def test_run_tests_failure(self, config: GenesisConfig, tmp_path: Path):
        from genesis.tools.test_runner import TestRunner

        (tmp_path / "test_fail.py").write_text("def test_fail(): assert False\n")
        runner = TestRunner(config, project_root=tmp_path)
        result = runner.run_tests()
        assert "FAILED" in result


class TestToolsConfig:
    def test_default_max_read_chars(self):
        config = GenesisConfig()
        assert config.tools.max_read_chars == 10_000

    def test_load_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "genesis.toml"
        toml_file.write_text('[tools]\nmax_read_chars = 5000\n')
        config = load_config(toml_file)
        assert config.tools.max_read_chars == 5000
