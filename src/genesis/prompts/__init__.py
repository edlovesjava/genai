"""Prompt templates for Genesis agents.

Use load_prompt() to read prompt files — works for both editable and
non-editable installs via importlib.resources.
"""

from __future__ import annotations

from importlib import resources as _res


def load_prompt(filename: str) -> str:
    """Load a prompt markdown file from this package.

    Args:
        filename: e.g. "planner_system.md"

    Returns:
        The prompt text, or None-safe empty string if not found.
    """
    ref = _res.files(__package__).joinpath(filename)
    return ref.read_text(encoding="utf-8")
