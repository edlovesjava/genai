"""Tests for the SpecRunner lifecycle orchestration layer.

The lifecycle is driven through a ``FakeLifecycle`` that enforces the *real*
Genesis six-state transition graph, so an illegal transition fails the test the
same way the genesis ``StateMachine`` would.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from genspec.generate import Artifact, ConformanceResult, Generator
from genspec.orchestrate import (
    ASSIGNED,
    BLOCKED,
    DONE,
    IN_PROGRESS,
    IN_REVIEW,
    REJECTED,
    TODO,
    SpecRunner,
)
from genspec.parser import parse_text

# The genesis transition graph, replicated to keep the fake faithful.
GRAPH = {
    TODO: [ASSIGNED],
    ASSIGNED: [IN_PROGRESS],
    IN_PROGRESS: [BLOCKED, IN_REVIEW],
    BLOCKED: [IN_PROGRESS],
    IN_REVIEW: [DONE, REJECTED],
    REJECTED: [IN_PROGRESS],
}

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
# Doubles
# --------------------------------------------------------------------------- #


class FakeLifecycle:
    """Enforces the real Genesis transition graph; status is per-bookmark.

    Mirrors ``StateMachine``'s per-bookmark status cache: each task tracks its
    own state, so running multiple specs through one lifecycle is faithful.
    """

    def __init__(self, start: str = TODO) -> None:
        self.start = start
        self._status: dict[str, str] = {}
        self.history: list[tuple[str, str, str, str]] = []  # (bookmark, to, actor, reason)

    def get_status(self, bookmark: str) -> str:
        return self._status.get(bookmark, self.start)

    def transition(self, bookmark: str, to_status: str, actor: str, reason: str) -> None:
        current = self.get_status(bookmark)
        if to_status not in GRAPH.get(current, []):
            raise ValueError(f"illegal transition {current} -> {to_status}")
        self._status[bookmark] = to_status
        self.history.append((bookmark, to_status, actor, reason))

    def states_for(self, bookmark: str) -> list[str]:
        return [to for bk, to, _, _ in self.history if bk == bookmark]

    @property
    def states(self) -> list[str]:
        return [to for _, to, _, _ in self.history]


class ScriptedTestAuthor:
    def __init__(self, source: str) -> None:
        self.source = source

    def author(self, brief) -> Artifact:
        return Artifact(brief.module_name, self.source)


class ScriptedCoder:
    def __init__(self, *drafts: str) -> None:
        self.drafts = list(drafts)
        self.revisions = 0

    def draft(self, brief) -> Artifact:
        return Artifact(brief.module_name, self.drafts[0])

    def revise(self, brief, current, failure) -> Artifact:
        self.revisions += 1
        return Artifact(brief.module_name, self.drafts[min(self.revisions, len(self.drafts) - 1)])


class FakeRunner:
    def __init__(self, passes_when) -> None:
        self.passes_when = passes_when

    def run(self, code: Artifact, tests: Artifact) -> ConformanceResult:
        ok = self.passes_when(code.source)
        return ConformanceResult(ok, "" if ok else "AssertionError", 0 if ok else 1)


def make_runner(tmp_path, coder, runner, *, gate_handler=None, emit=None, **gen_kw):
    """Build a SpecRunner whose Generator never self-gates (None => SpecRunner owns gates)."""
    events: list[tuple[str, str, dict]] = []
    generator = Generator(
        test_author=ScriptedTestAuthor(ADD_TESTS),
        coder=coder,
        runner=runner,
        gate_handler=None,
        **gen_kw,
    )
    lifecycle = FakeLifecycle()
    sr = SpecRunner(
        generator=generator,
        lifecycle=lifecycle,
        output_dir=tmp_path / "generated",
        emit=(emit if emit is not None else lambda e, s, p: events.append((e, s, p))),
        gate_handler=gate_handler,
    )
    return sr, lifecycle, events


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_validated_spec_runs_to_done_and_persists(tmp_path):
    spec = parse_text(VALID_SPEC)
    sr, lifecycle, events = make_runner(tmp_path, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: "+" in s))

    record = sr.run(spec)

    assert record.final_state == DONE
    assert record.accepted
    # The full legal lifecycle was walked, in order.
    assert lifecycle.states == [ASSIGNED, IN_PROGRESS, IN_REVIEW, DONE]
    # Artifacts were committed to the tracked output dir.
    code = tmp_path / "generated" / "demo_adder.py"
    tests = tmp_path / "generated" / "test_demo_adder.py"
    assert code.exists() and tests.exists()
    assert "Generated by genspec" in code.read_text()
    assert {e for e, _, _ in events} >= {"generation-started", "generation-complete", "accepted"}


def test_persisted_artifacts_are_runnable(tmp_path):
    """'The repo always has runnable code' — pytest passes on the committed output."""
    spec = parse_text(VALID_SPEC)
    sr, _, _ = make_runner(tmp_path, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: "+" in s))
    sr.run(spec)

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(tmp_path / "generated")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_reconciled_spec_runs_to_done(tmp_path):
    spec = parse_text(VALID_SPEC)
    sr, lifecycle, _ = make_runner(
        tmp_path, ScriptedCoder(WRONG_CODE, ADD_CODE), FakeRunner(lambda s: "+" in s)
    )

    record = sr.run(spec)

    assert record.final_state == DONE
    assert record.generation.iterations == 1


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #


def test_acceptance_decline_moves_to_rejected(tmp_path):
    spec = parse_text(VALID_SPEC)
    sr, lifecycle, _ = make_runner(
        tmp_path,
        ScriptedCoder(ADD_CODE),
        FakeRunner(lambda s: "+" in s),
        gate_handler=lambda gt, sid, d: False,
    )

    record = sr.run(spec)

    assert record.final_state == REJECTED
    assert lifecycle.states == [ASSIGNED, IN_PROGRESS, IN_REVIEW, REJECTED]
    assert not (tmp_path / "generated").exists()  # nothing persisted on rejection


# --------------------------------------------------------------------------- #
# Faults -> BLOCKED escalation
# --------------------------------------------------------------------------- #


def test_invalid_spec_is_blocked(tmp_path):
    text = VALID_SPEC.replace("## Qualities\nPure and total.\n\n", "")
    spec = parse_text(text)
    sr, lifecycle, events = make_runner(tmp_path, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: True))

    record = sr.run(spec)

    assert record.final_state == BLOCKED
    assert record.escalated
    assert lifecycle.states[-1] == BLOCKED
    assert any(e == "blocked" for e, _, _ in events)


def test_unreconcilable_spec_fault_is_blocked(tmp_path):
    spec = parse_text(VALID_SPEC)
    sr, lifecycle, _ = make_runner(
        tmp_path, ScriptedCoder(WRONG_CODE), FakeRunner(lambda s: False), max_reconcile=2
    )

    record = sr.run(spec)  # generator raises HumanGateRequired; SpecRunner catches -> BLOCKED

    assert record.final_state == BLOCKED
    assert record.escalated


# --------------------------------------------------------------------------- #
# Library
# --------------------------------------------------------------------------- #


def test_run_library_in_dependency_order(tmp_path):
    base = parse_text(VALID_SPEC.replace("id: demo.adder", "id: demo.base"))
    dependent = parse_text(
        VALID_SPEC.replace("id: demo.adder\n", "id: demo.dependent\ndepends: [demo.base]\n")
    )
    sr, _, _ = make_runner(tmp_path, ScriptedCoder(ADD_CODE), FakeRunner(lambda s: "+" in s))

    records = sr.run_library([dependent, base])  # reversed on purpose

    assert [r.spec_id for r in records] == ["demo.base", "demo.dependent"]
    assert all(r.final_state == DONE for r in records)


# --------------------------------------------------------------------------- #
# Genesis adapter
# --------------------------------------------------------------------------- #


def test_genesis_adapter_errors_clearly_without_genesis(tmp_path):
    from genspec.orchestrate_genesis import build_spec_runner

    generator = Generator(
        test_author=ScriptedTestAuthor(ADD_TESTS),
        coder=ScriptedCoder(ADD_CODE),
        runner=FakeRunner(lambda s: True),
    )
    with pytest.raises(RuntimeError, match="requires the 'genesis' package"):
        build_spec_runner(
            generator,
            task_file=tmp_path / "TASKS.md",
            messages_dir=tmp_path / "messages",
            output_dir=tmp_path / "generated",
        )
