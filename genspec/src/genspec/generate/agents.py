"""The independent generation agents.

The generator derives **two artifacts from one spec, independently**: a test
module (from the spec's behavior and qualities) and a production module (from the
spec's intent and structure). The agents are kept structurally apart — each is
handed a *brief* containing only its slice of the spec, never the other agent's
output — so that agreement between the two is real evidence the spec is
unambiguous, and disagreement is a spec fault surfaced early.

This mirrors the Genesis Triad split (Test Author vs Coder) and the project's
testing convention: the LLM is always behind an interface so the orchestration is
deterministically testable. ``TestAuthor`` and ``Coder`` are Protocols; a real
implementation calls Claude, while tests use scripted stand-ins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from genspec.model import Specification


@dataclass(frozen=True)
class TestBrief:
    """What the Test Author is allowed to see: the spec's *behavioral* surface.

    Deliberately excludes any production code. The author derives tests purely
    from what the system must *do* (scenarios) and the constraints it must hold
    (qualities).
    """

    spec_id: str
    module_name: str
    title: str
    intent: str
    behavior: str
    qualities: str


@dataclass(frozen=True)
class CoderBrief:
    """What the Coder is allowed to see for its first, independent draft.

    Excludes the tests entirely. The first draft is derived from intent and
    structure alone — only during reconciliation does the coder see test output.
    """

    spec_id: str
    module_name: str
    title: str
    intent: str
    structure: str
    qualities: str


@dataclass(frozen=True)
class Artifact:
    """A generated source file: a logical module name and its source text."""

    module_name: str
    source: str


def test_brief(spec: Specification, module_name: str) -> TestBrief:
    """Project a spec down to what the Test Author may see."""
    return TestBrief(
        spec_id=spec.id,
        module_name=module_name,
        title=spec.title,
        intent=_body(spec, "intent"),
        behavior=_body(spec, "behavior"),
        qualities=_body(spec, "qualities"),
    )


def coder_brief(spec: Specification, module_name: str) -> CoderBrief:
    """Project a spec down to what the Coder may see for its first draft."""
    return CoderBrief(
        spec_id=spec.id,
        module_name=module_name,
        title=spec.title,
        intent=_body(spec, "intent"),
        structure=_body(spec, "structure"),
        qualities=_body(spec, "qualities"),
    )


def _body(spec: Specification, name: str) -> str:
    section = spec.section(name)
    return section.body if section else ""


@runtime_checkable
class TestAuthor(Protocol):
    """Derives a test module from a spec's behavior — never sees the code."""

    def author(self, brief: TestBrief) -> Artifact: ...


@runtime_checkable
class Coder(Protocol):
    """Derives a production module from a spec, and reconciles against failures.

    ``draft`` is the independent first pass (spec only). ``revise`` is the TDD
    reconciliation pass: the coder is shown the *failure output* (not the test
    source's intent beyond what the failure reveals) and attempts to converge.
    """

    def draft(self, brief: CoderBrief) -> Artifact: ...

    def revise(self, brief: CoderBrief, current: Artifact, failure: str) -> Artifact: ...
