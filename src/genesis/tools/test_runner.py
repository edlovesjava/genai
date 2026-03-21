"""Test runner tool — execute pytest and return results."""

from __future__ import annotations

import subprocess
from pathlib import Path

from genesis.config import GenesisConfig


class TestRunner:
    """Tool interface for running tests."""

    def __init__(self, config: GenesisConfig, project_root: Path | None = None) -> None:
        self.config = config
        self.project_root = project_root or Path.cwd()

    def run_tests(
        self,
        path: str | None = None,
        verbose: bool = False,
        keyword: str | None = None,
    ) -> str:
        """Run pytest and return the output."""
        cmd = ["python", "-m", "pytest"]
        if path:
            cmd.append(path)
        if verbose:
            cmd.append("-v")
        if keyword:
            cmd.extend(["-k", keyword])

        result = subprocess.run(
            cmd,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        status = "PASSED" if result.returncode == 0 else "FAILED"
        return f"Tests {status}:\n{output}"
