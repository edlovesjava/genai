"""Validate specifications — the spec as the *source of validation*.

If the spec is the source of truth, it must be checkable. This module verifies
that a :class:`~genspec.model.Specification` is well-formed and faithfully
anchored to reality:

* **Completeness** — every canonical section is present and non-empty.
* **Behavioral soundness** — each scenario has Given *and* When *and* Then.
* **Anchoring** — every file in ``source:`` actually exists on disk, so a spec
  that claims to describe existing code cannot silently drift into fiction.
* **Resolvable dependencies** — when validating a set, ``depends:`` ids resolve.

Validation produces :class:`Diagnostic` records rather than raising, so a whole
spec library can be checked in one pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from genspec.model import CANONICAL_SECTIONS, Specification, StepKind


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    level: Level
    spec_id: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.value.upper():7} [{self.spec_id}] {self.message}"


# Scenarios are only meaningful if they establish context, act, and assert.
_REQUIRED_STEP_KINDS = (StepKind.GIVEN, StepKind.WHEN, StepKind.THEN)


def validate(spec: Specification, *, root: str | Path | None = None) -> list[Diagnostic]:
    """Validate a single specification.

    ``root`` is the base directory that ``source:`` paths are resolved against;
    it defaults to the directory containing the spec file (if known), else cwd.
    """
    diags: list[Diagnostic] = []
    base = _resolve_root(spec, root)

    _check_sections(spec, diags)
    _check_scenarios(spec, diags)
    _check_source_anchoring(spec, base, diags)

    return diags


def validate_all(specs: list[Specification], *, root: str | Path | None = None) -> list[Diagnostic]:
    """Validate a set of specs, including cross-spec ``depends:`` resolution."""
    diags: list[Diagnostic] = []
    known_ids = {s.id for s in specs}

    for spec in specs:
        diags.extend(validate(spec, root=root))
        for dep in spec.depends:
            if dep not in known_ids:
                diags.append(
                    Diagnostic(
                        Level.ERROR,
                        spec.id,
                        f"depends on unknown spec '{dep}'",
                    )
                )

    _check_duplicate_ids(specs, diags)
    return diags


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def _check_sections(spec: Specification, diags: list[Diagnostic]) -> None:
    for name in CANONICAL_SECTIONS:
        section = spec.section(name)
        if section is None:
            diags.append(
                Diagnostic(Level.ERROR, spec.id, f"missing required section '{name}'")
            )
        elif not section.body.strip():
            diags.append(
                Diagnostic(Level.WARNING, spec.id, f"section '{name}' is empty")
            )


def _check_scenarios(spec: Specification, diags: list[Diagnostic]) -> None:
    behavior = spec.section("behavior")
    if behavior is None:
        return  # already reported by _check_sections
    if not behavior.scenarios:
        diags.append(
            Diagnostic(
                Level.WARNING,
                spec.id,
                "behavior section declares no Given/When/Then scenarios",
            )
        )
        return
    for scenario in behavior.scenarios:
        present = scenario.kinds()
        missing = [k.value for k in _REQUIRED_STEP_KINDS if k not in present]
        if missing:
            diags.append(
                Diagnostic(
                    Level.ERROR,
                    spec.id,
                    f"scenario '{scenario.name}' is missing clause(s): "
                    f"{', '.join(missing)}",
                )
            )


def _check_source_anchoring(
    spec: Specification, base: Path, diags: list[Diagnostic]
) -> None:
    for src in spec.source:
        if not (base / src).exists():
            diags.append(
                Diagnostic(
                    Level.ERROR,
                    spec.id,
                    f"source '{src}' does not exist (spec is not anchored to real code)",
                )
            )


def _check_duplicate_ids(specs: list[Specification], diags: list[Diagnostic]) -> None:
    seen: dict[str, int] = {}
    for spec in specs:
        seen[spec.id] = seen.get(spec.id, 0) + 1
    for spec_id, count in seen.items():
        if count > 1:
            diags.append(
                Diagnostic(Level.ERROR, spec_id, f"duplicate spec id ({count} documents)")
            )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _resolve_root(spec: Specification, root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    if spec.path is not None:
        return Path(spec.path).resolve().parent
    return Path.cwd()


def has_errors(diags: list[Diagnostic]) -> bool:
    return any(d.level is Level.ERROR for d in diags)
