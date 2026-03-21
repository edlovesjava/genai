"""Git operations tool — branch, commit, and PR via subprocess."""

from __future__ import annotations

import subprocess
from pathlib import Path

from genesis.config import GenesisConfig


class GitOps:
    """Tool interface for git operations."""

    def __init__(self, config: GenesisConfig, project_root: Path | None = None) -> None:
        self.config = config
        self.project_root = project_root or Path.cwd()

    def git_create_branch(self, branch_name: str) -> str:
        """Create and switch to a new git branch."""
        result = self._run(["git", "checkout", "-b", branch_name])
        if result.returncode != 0:
            return f"Error creating branch: {result.stderr}"
        return f"Created and switched to branch '{branch_name}'."

    def git_commit(self, message: str, files: list[str] | None = None) -> str:
        """Stage files and create a commit."""
        if files:
            add_result = self._run(["git", "add"] + files)
            if add_result.returncode != 0:
                return f"Error staging files: {add_result.stderr}"
        else:
            add_result = self._run(["git", "add", "-A"])
            if add_result.returncode != 0:
                return f"Error staging files: {add_result.stderr}"

        result = self._run(["git", "commit", "-m", message])
        if result.returncode != 0:
            return f"Error committing: {result.stderr}"
        return f"Committed: {message}"

    def git_open_pr(self, title: str, body: str, base: str = "main") -> str:
        """Open a pull request via the gh CLI."""
        result = self._run([
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--base", base,
        ])
        if result.returncode != 0:
            return f"Error opening PR: {result.stderr}"
        return result.stdout.strip()

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a command in the project root."""
        return subprocess.run(
            cmd,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
