"""Parse a ``.spec.md`` document into a :class:`~genspec.model.Specification`.

The reader is hand-written and dependency-free on purpose: the spec format must
stay portable and human-inspectable, so we accept a small, well-defined subset of
markdown + YAML-style frontmatter rather than pulling in heavyweight parsers.

Grammar (informal):

    ---
    id: some.identifier
    title: Human Title
    status: active            # draft | active | deprecated
    abstraction: model        # model | implementation
    source: [path/a.py, path/b.py]
    depends:
      - other.spec.id
    ---

    # Human Title

    ## Intent
    ...prose...

    ## Behavior

    ### Scenario: a thing happens
    Given some context
    When an action occurs
    Then an outcome is asserted
    And a further outcome holds

Section headings are matched case-insensitively against the canonical section
names; unknown ``##`` headings are preserved under their lowercased heading key.
"""

from __future__ import annotations

import re
from pathlib import Path

from genspec.model import (
    Abstraction,
    Kind,
    Scenario,
    Section,
    Specification,
    Status,
    Step,
    StepKind,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_STEP_RE = re.compile(r"^(given|when|then|and)\b[:\s]*(.*)$", re.IGNORECASE)
_SCENARIO_RE = re.compile(r"^scenario\s*:\s*(.*)$", re.IGNORECASE)


class SpecParseError(Exception):
    """Raised when a document cannot be parsed as a specification."""


def parse_file(path: str | Path) -> Specification:
    """Read and parse a ``.spec.md`` file from disk."""
    p = Path(path)
    spec = parse_text(p.read_text(encoding="utf-8"))
    spec.path = str(p)
    return spec


def parse_text(text: str) -> Specification:
    """Parse the full text of a specification document."""
    frontmatter, body = _split_frontmatter(text)
    meta = _parse_frontmatter(frontmatter)

    spec_id = meta.get("id")
    if not spec_id:
        raise SpecParseError("specification is missing required 'id' in frontmatter")

    spec = Specification(
        id=str(spec_id),
        title=str(meta.get("title") or spec_id),
        kind=_coerce_enum(Kind, meta.get("kind"), Kind.COMPONENT),
        status=_coerce_enum(Status, meta.get("status"), Status.DRAFT),
        abstraction=_coerce_enum(Abstraction, meta.get("abstraction"), Abstraction.MODEL),
        source=_as_list(meta.get("source")),
        depends=_as_list(meta.get("depends")),
    )
    spec.sections = _parse_sections(body)
    return spec


# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a document into (frontmatter, body). Frontmatter is optional."""
    match = _FRONTMATTER_RE.match(text.lstrip("﻿"))
    if not match:
        return "", text
    return match.group(1), match.group(2)


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse the YAML-subset frontmatter we support.

    Supports ``key: scalar``, ``key: [a, b]`` inline lists, and block lists::

        key:
          - a
          - b
    """
    meta: dict[str, object] = {}
    pending_key: str | None = None
    pending_list: list[str] = []

    def flush() -> None:
        nonlocal pending_key, pending_list
        if pending_key is not None:
            meta[pending_key] = pending_list
            pending_key = None
            pending_list = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        # Continuation of a block list: "  - item"
        stripped = line.lstrip()
        if pending_key is not None and stripped.startswith("- "):
            pending_list.append(_strip_scalar(stripped[2:]))
            continue
        flush()

        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value == "":
            # Begin a block list (or empty value); decide on next lines.
            pending_key = key
            pending_list = []
            continue
        meta[key] = _parse_scalar_or_inline_list(value)

    flush()
    return meta


def _parse_scalar_or_inline_list(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_scalar(part) for part in inner.split(",")]
    return _strip_scalar(value)


def _strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


def _coerce_enum(enum_cls, value, default):
    if value is None:
        return default
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# Body / sections
# --------------------------------------------------------------------------- #


def _canonical_key(heading: str) -> str:
    return heading.strip().lower()


def _parse_sections(body: str) -> dict[str, Section]:
    """Split the body into ``##`` sections, parsing scenarios in 'behavior'."""
    sections: dict[str, Section] = {}
    current: Section | None = None
    buffer: list[str] = []

    def commit() -> None:
        if current is None:
            return
        current.body = "\n".join(buffer).strip()
        if current.name == "behavior":
            current.scenarios = _parse_scenarios(current.body)
        sections[current.name] = current

    for line in body.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            commit()
            heading = line[3:].strip()
            current = Section(name=_canonical_key(heading), heading=heading)
            buffer = []
        elif current is not None:
            buffer.append(line)
        # Lines before the first ## (e.g. the # Title) are ignored here.

    commit()
    return sections


def _parse_scenarios(behavior_body: str) -> list[Scenario]:
    """Extract ``### Scenario: ...`` blocks and their Given/When/Then steps."""
    scenarios: list[Scenario] = []
    current: Scenario | None = None

    for raw in behavior_body.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            heading = line[4:].strip()
            sc_match = _SCENARIO_RE.match(heading)
            name = sc_match.group(1).strip() if sc_match else heading
            current = Scenario(name=name)
            scenarios.append(current)
            continue
        if current is None:
            continue
        # Allow steps written as list items: "- Given ..."
        candidate = line[2:].strip() if line.startswith("- ") else line
        step_match = _STEP_RE.match(candidate)
        if step_match:
            kind = StepKind(step_match.group(1).lower())
            current.steps.append(Step(kind=kind, text=step_match.group(2).strip()))

    return scenarios
