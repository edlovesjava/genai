"""Tests for the generation loop.

The loop is driven with scripted agents and a fake runner so every branch is
deterministic, plus two end-to-end tests that exercise the real ``PytestRunner``.
"""

from __future__ import annotations

import pytest

from speckit.generate import (
    Artifact,
    ConformanceResult,
    Disposition,
    Fault,
    Generator,
    HumanGateRequired,
    PytestRunner,
)
from speckit.parser import parse_text

VALID_SPEC = """\
---
id: demo.adder
title: Adder
status: active
abstraction: model
---

# Adder

## Intent
Add two numbers.

## Structure
A function add(a, b) returning a + b.

## Behavior

### Scenario: adds two numbers
Given two integers
When add is called
Then their sum is returned

## Qualities
Pure and total.

## Validation
Covered by generated tests.
"""

ADD_CODE = "def add(a, b):\n    return a + b\n"
ADD_TESTS = "from demo_adder import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
WRONG_CODE = "def add(a, b):\n    return a - b\n"


# --------------------------------------------------------------------------- #
# Scripted doubles
# --------------------------------------------------------------------------- #


class ScriptedTestAuthor:
    def __init__(self, source: str) -> None:
        self.source = source

    def author(self, brief) -> Artifact:
        return Artifact(brief.module_name, self.source)


class ScriptedCoder:
    """Emits ``drafts[0]`` first, then successive drafts on each revise()."""

    def __init__(self, *drafts: str) -> None:
        self.drafts = list(drafts)
        self.revisions = 0
        self.saw_failure: list[str] = []

    def draft(self, brief) -> Artifact:
        return Artifact(brief.module_name, self.drafts[0])

    def revise(self, brief, current, failure) -> Artifact:
        self.saw_failure.append(failure)
        self.revisions += 1
        idx = min(self.revisions, len(self.drafts) - 1)
        return Artifact(brief.module_name, self.drafts[idx])


class FakeRunner:
    """Pass/fail decided by a predicate over the code source."""

    def __init__(self, passes_when) -> None:
        self.passes_when = passes_when
        self.runs = 0

    def run(self, code: Artifact, tests: Artifact) -> ConformanceResult:
        self.runs += 1
        ok = self.passes_when(code.source)
        return ConformanceResult(passed=ok, output="" if ok else "AssertionError", exit_code=0 if ok else 1)


def make_generator(test_src, coder, runner, **kw) -> Generator:
    return Generator(
        test_author=ScriptedTestAuthor(test_src),
        coder=coder,
        runner=runner,
        **kw,
    )


# --------------------------------------------------------------------------- #
# Static pre-validation short-circuits generation
# --------------------------------------------------------------------------- #


def test_invalid_spec_is_refused_before_generation():
    text = VALID_SPEC.replace("## Qualities\nPure and total.\n\n", "")  # drop a section
    spec = parse_text(text)
    coder = ScriptedCoder(ADD_CODE)
    gen = make_generator(ADD_TESTS, coder, FakeRunner(lambda s: True))

    result = gen.generate(spec)

    assert result.disposition is Disposition.INVALID
    assert result.fault is Fault.SPEC
    assert coder.revisions == 0  # never invoked the agents


# --------------------------------------------------------------------------- #
# Independent agreement
# --------------------------------------------------------------------------- #


def test_first_pass_agreement_is_validated():
    spec = parse_text(VALID_SPEC)
    gen = make_generator(ADD_TESTS, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: "+" in s))

    result = gen.generate(spec)

    assert result.disposition is Disposition.VALIDATED
    assert result.fault is Fault.NONE
    assert result.iterations == 0


# --------------------------------------------------------------------------- #
# Reconciliation (a code gap, closed by TDD)
# --------------------------------------------------------------------------- #


def test_disagreement_reconciled_is_code_fault():
    spec = parse_text(VALID_SPEC)
    coder = ScriptedCoder(WRONG_CODE, ADD_CODE)  # first wrong, then fixed
    gen = make_generator(ADD_TESTS, coder, FakeRunner(lambda s: "+" in s))

    result = gen.generate(spec)

    assert result.disposition is Disposition.RECONCILED
    assert result.fault is Fault.CODE
    assert result.iterations == 1
    assert coder.saw_failure  # coder was shown the failure output


# --------------------------------------------------------------------------- #
# Unreconcilable disagreement => spec fault, escalates to a human
# --------------------------------------------------------------------------- #


def test_unreconcilable_raises_human_gate_by_default():
    spec = parse_text(VALID_SPEC)
    coder = ScriptedCoder(WRONG_CODE)  # never converges
    gen = make_generator(ADD_TESTS, coder, FakeRunner(lambda s: False), max_reconcile=2)

    with pytest.raises(HumanGateRequired) as exc:
        gen.generate(spec)
    assert exc.value.gate_type == "spec_fault"


def test_unreconcilable_with_gate_handler_returns_spec_suspect():
    spec = parse_text(VALID_SPEC)
    seen = []
    gen = make_generator(
        ADD_TESTS,
        ScriptedCoder(WRONG_CODE),
        FakeRunner(lambda s: False),
        max_reconcile=2,
        gate_handler=lambda gt, sid, detail: seen.append((gt, sid)) or True,
    )

    result = gen.generate(spec)

    assert result.disposition is Disposition.SPEC_SUSPECT
    assert result.fault is Fault.SPEC
    assert result.iterations == 2
    assert ("spec_fault", "demo.adder") in seen


# --------------------------------------------------------------------------- #
# Acceptance gate: spec consistent but a human may still reject it
# --------------------------------------------------------------------------- #


def test_acceptance_gate_can_reject_a_consistent_result():
    spec = parse_text(VALID_SPEC)
    gen = make_generator(
        ADD_TESTS,
        ScriptedCoder(ADD_CODE),
        FakeRunner(lambda s: True),
        gate_handler=lambda gt, sid, detail: False,  # human says "not the right thing"
    )

    result = gen.generate(spec)

    assert result.disposition is Disposition.REJECTED


# --------------------------------------------------------------------------- #
# Library decomposition: dependency-ordered, with library-level checks
# --------------------------------------------------------------------------- #


def _spec(spec_id: str, depends: list[str] | None = None):
    dep_line = f"depends: [{', '.join(depends)}]\n" if depends else ""
    text = VALID_SPEC.replace("id: demo.adder\n", f"id: {spec_id}\n{dep_line}")
    return parse_text(text)


def test_library_generates_in_dependency_order():
    base = _spec("demo.base")
    dependent = _spec("demo.dependent", depends=["demo.base"])
    gen = make_generator(ADD_TESTS, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: True))

    results = gen.generate_library([dependent, base])  # deliberately reversed

    assert [r.spec_id for r in results] == ["demo.base", "demo.dependent"]


def test_library_unresolved_dependency_is_invalid():
    dependent = _spec("demo.dependent", depends=["demo.missing"])
    gen = make_generator(ADD_TESTS, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: True))

    results = gen.generate_library([dependent])

    assert len(results) == 1
    assert results[0].disposition is Disposition.INVALID
    assert results[0].fault is Fault.SPEC


# --------------------------------------------------------------------------- #
# End-to-end through the real pytest runner
# --------------------------------------------------------------------------- #


def test_real_pytest_runner_passes_on_correct_pair():
    runner = PytestRunner()
    result = runner.run(Artifact("demo_adder", ADD_CODE), Artifact("demo_adder", ADD_TESTS))
    assert result.passed, result.output


def test_real_pytest_runner_fails_on_wrong_code():
    runner = PytestRunner()
    result = runner.run(Artifact("demo_adder", WRONG_CODE), Artifact("demo_adder", ADD_TESTS))
    assert not result.passed


def test_full_loop_with_real_runner_validates():
    spec = parse_text(VALID_SPEC)
    gen = Generator(
        test_author=ScriptedTestAuthor(ADD_TESTS),
        coder=ScriptedCoder(ADD_CODE),
        runner=PytestRunner(),
    )
    result = gen.generate(spec)
    assert result.disposition is Disposition.VALIDATED
    assert result.ok
