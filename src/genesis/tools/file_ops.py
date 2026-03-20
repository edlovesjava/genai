"""File operations tool — read and write files with human gate support."""

from __future__ import annotations

from pathlib import Path

from genesis.config import GenesisConfig


class ProtectedPathError(Exception):
    """Raised when writing to a path that requires human approval."""


class FileOps:
    """Tool interface for file operations."""

    def __init__(self, config: GenesisConfig, project_root: Path | None = None) -> None:
        self.config = config
        self.project_root = project_root or Path.cwd()

    def read_file(self, path: str) -> str:
        """Read and return file contents."""
        resolved = self._resolve(path)
        if not resolved.exists():
            return f"Error: File not found: {path}"
        return resolved.read_text()

    def write_file(self, path: str, content: str, approved: bool = False) -> str:
        """Write content to a file, checking human gates for protected paths."""
        resolved = self._resolve(path)
        if self._is_protected(path) and not approved:
            raise ProtectedPathError(
                f"Writing to protected path '{path}' requires human approval."
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return f"Wrote {len(content)} bytes to {path}."

    def _resolve(self, path: str) -> Path:
        """Resolve a path relative to project root."""
        p = Path(path)
        if p.is_absolute():
            return p
        return self.project_root / p

    def _is_protected(self, path: str) -> bool:
        """Check if a path matches any protected path patterns."""
        for pattern in self.config.human_gates.protected_paths:
            if pattern.endswith("/"):
                if path.startswith(pattern) or f"/{pattern}" in path:
                    return True
            elif path == pattern or path.endswith(f"/{pattern}"):
                return True
        return False
