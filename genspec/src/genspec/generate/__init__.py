"""genspec.generate — lower a validated spec into code, the TDD way.

Generation derives tests and production code *independently* from one spec, then
runs them against each other. Agreement is evidence the spec is well-determined;
disagreement is a spec fault found early. The orchestration lives in
:mod:`genspec.generate.loop`; the LLM agents and the test runner are Protocols so
the loop is deterministically testable.
"""

from __future__ import annotations

from genspec.generate.agents import (
    Artifact,
    Coder,
    CoderBrief,
    TestAuthor,
    TestBrief,
    coder_brief,
    test_brief,
)
from genspec.generate.conformance import ConformanceResult, PytestRunner, Runner
from genspec.generate.loop import (
    Disposition,
    Fault,
    GateHandler,
    Generator,
    GenerationResult,
    HumanGateRequired,
)

__all__ = [
    "Artifact",
    "Coder",
    "CoderBrief",
    "TestAuthor",
    "TestBrief",
    "coder_brief",
    "test_brief",
    "ConformanceResult",
    "PytestRunner",
    "Runner",
    "Disposition",
    "Fault",
    "GateHandler",
    "Generator",
    "GenerationResult",
    "HumanGateRequired",
]
