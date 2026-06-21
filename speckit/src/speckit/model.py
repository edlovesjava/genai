"""The high-fidelity model of a specification.

A speckit ``Specification`` is the in-memory, typed form of a ``.spec.md`` file.
It is deliberately a *model*, not a string: every dimension a spec must capture
(intent, structure, behavior, qualities, validation) is a first-class field so
the document can be validated, queried, and ultimately lowered into code.

These classes carry no parsing or I/O logic — see ``parser.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# The five canonical sections every full specification is organized into.
# Order is meaningful: it is the reading order of a spec.
CANONICAL_SECTIONS: tuple[str, ...] = (
    "intent",      # functional / why — purpose, problem, scope
    "structure",   # structural — components, types, relationships, contracts
    "behavior",    # behavioral — Given/When/Then scenarios
    "qualities",   # non-functional — invariants, constraints, budgets, safety
    "validation",  # traceability — how conformance is checked
)


class Abstraction(str, Enum):
    """The level of abstraction a spec is pinned at.

    ``MODEL`` specs are the durable source of truth and stay free of incidental
    implementation detail. ``IMPLEMENTATION`` specs are bound to one concrete
    realization (a language, a library, a deployment).
    """

    MODEL = "model"
    IMPLEMENTATION = "implementation"


class Status(str, Enum):
    """Lifecycle of a specification document itself."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class StepKind(str, Enum):
    """A clause in a behavioral scenario."""

    GIVEN = "given"
    WHEN = "when"
    THEN = "then"
    AND = "and"


@dataclass(frozen=True)
class Step:
    """A single ``Given``/``When``/``Then``/``And`` clause of a scenario."""

    kind: StepKind
    text: str


@dataclass
class Scenario:
    """A behavioral example expressed as a sequence of steps.

    A well-formed scenario establishes context (``Given``), exercises the system
    (``When``), and asserts an outcome (``Then``). ``And`` continues the previous
    clause kind.
    """

    name: str
    steps: list[Step] = field(default_factory=list)

    def kinds(self) -> set[StepKind]:
        """Return the distinct *effective* step kinds in this scenario.

        ``And`` is resolved to whatever clause it continues, so a scenario of
        ``Given / And / When / Then`` reports ``{GIVEN, WHEN, THEN}``.
        """
        kinds: set[StepKind] = set()
        current: StepKind | None = None
        for step in self.steps:
            if step.kind is StepKind.AND:
                if current is not None:
                    kinds.add(current)
            else:
                current = step.kind
                kinds.add(step.kind)
        return kinds


@dataclass
class Section:
    """One canonical section of a specification.

    ``body`` preserves the raw markdown so nothing authored is lost. ``scenarios``
    is populated only for the ``behavior`` section.
    """

    name: str          # canonical key, e.g. "intent" (see CANONICAL_SECTIONS)
    heading: str       # the original heading text as written
    body: str = ""
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass
class Specification:
    """The complete, typed model of one ``.spec.md`` document."""

    id: str
    title: str
    status: Status = Status.DRAFT
    abstraction: Abstraction = Abstraction.MODEL
    # Source files this spec claims to describe — the linkage that lets the
    # validator confirm a spec is anchored to real code.
    source: list[str] = field(default_factory=list)
    # IDs of other specs this one builds upon.
    depends: list[str] = field(default_factory=list)
    sections: dict[str, Section] = field(default_factory=dict)
    path: str | None = None

    def section(self, name: str) -> Section | None:
        """Return a section by canonical name, or ``None`` if absent."""
        return self.sections.get(name)

    @property
    def scenarios(self) -> list[Scenario]:
        """All behavioral scenarios declared by this spec."""
        behavior = self.sections.get("behavior")
        return list(behavior.scenarios) if behavior else []
