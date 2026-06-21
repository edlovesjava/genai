"""SpecRunner — the lifecycle orchestration layer for spec-is-code.

``Generator`` (in :mod:`genspec.generate`) is the *inner* loop: it builds one
spec once. ``SpecRunner`` is the *outer* loop: it drives a spec through its SDLC
over time, reusing the Genesis kernel's primitives rather than reinventing them —
the file-based message bus, the six-state task machine, and the human-gate
pattern (``gate_handler`` + escalation).

The mechanical generation disposition is mapped onto the Genesis state machine:

    TODO ──ASSIGNED──▶ IN_PROGRESS ──┬─ VALIDATED/RECONCILED ─▶ IN_REVIEW ─┬─ accept ─▶ DONE
                                     │                                     └─ decline ▶ REJECTED
                                     └─ INVALID / spec fault ─────────────▶ BLOCKED (escalate)

Generated code is a build artifact, but per project decision it is **committed**
(written to a tracked output dir on acceptance) so the repository always holds
runnable code alongside its specs.

This module imports nothing from Genesis. It depends only on the small API
*shapes* below (``Lifecycle``, ``Emit``); the real Genesis ``StateMachine`` and
``MessageBus`` satisfy them and are wired in by :mod:`genspec.orchestrate_genesis`.
That keeps genspec installable and testable on its own while still running on
Genesis primitives in a full kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from genspec.generate.agents import Artifact
from genspec.generate.loop import (
    Disposition,
    GenerationResult,
    Generator,
    HumanGateRequired,
    _module_name,
    _topological,
)
from genspec.model import Specification

# Genesis state names (kept as plain strings so this module needs no genesis import).
TODO, ASSIGNED, IN_PROGRESS, IN_REVIEW, BLOCKED, REJECTED, DONE = (
    "TODO",
    "ASSIGNED",
    "IN_PROGRESS",
    "IN_REVIEW",
    "BLOCKED",
    "REJECTED",
    "DONE",
)


class Lifecycle(Protocol):
    """The slice of the Genesis ``StateMachine`` that SpecRunner drives."""

    def get_status(self, bookmark: str) -> str: ...

    def transition(self, bookmark: str, to_status: str, actor: str, reason: str) -> None: ...


# An emit callback records a genspec-specific event. In a Genesis wiring it builds
# a Message and publishes it to the bus; in isolation it can be a no-op or a sink.
Emit = Callable[[str, str, dict], None]


def _noop_emit(event: str, spec_id: str, payload: dict) -> None:  # pragma: no cover
    pass


@dataclass
class RunRecord:
    """The outcome of driving one spec through its lifecycle."""

    spec_id: str
    final_state: str
    disposition: Disposition | None = None
    generation: GenerationResult | None = None
    artifacts: list[Path] = field(default_factory=list)
    escalated: bool = False  # True when a spec fault forced a human escalation

    @property
    def accepted(self) -> bool:
        return self.final_state == DONE


@dataclass
class SpecRunner:
    """Drives specs through the Genesis lifecycle using genspec generation."""

    generator: Generator
    lifecycle: Lifecycle
    output_dir: Path
    emit: Emit = _noop_emit
    gate_handler: Callable[[str, str, str], bool] | None = None
    actor: str = "genspec"

    # ----------------------------------------------------------------- spec --
    def run(self, spec: Specification, *, root=None) -> RunRecord:
        bookmark = spec.id

        # Move into the working states. ASSIGNED = picked up; IN_PROGRESS =
        # generating. BLOCKED is only reachable from IN_PROGRESS in the Genesis
        # graph, so we enter IN_PROGRESS before any fault can be recorded.
        self._move(bookmark, ASSIGNED, "spec picked up for generation")
        self._move(bookmark, IN_PROGRESS, "generation started")
        self.emit("generation-started", spec.id, {"title": spec.title})

        try:
            result = self.generator.generate(spec, root=root)
        except HumanGateRequired as gate:
            # An unreconcilable disagreement: the spec under-determines behavior.
            return self._block(bookmark, spec, "spec-fault", gate.detail, None)

        self.emit(
            "generation-complete",
            spec.id,
            {
                "disposition": result.disposition.value,
                "fault": result.fault.value,
                "iterations": result.iterations,
            },
        )

        if result.disposition is Disposition.INVALID:
            return self._block(
                bookmark, spec, "static-validation", _diag_summary(result), result
            )

        # Mechanical agreement reached — hand to a human to confirm the spec is
        # *correct*, not merely consistent.
        self._move(
            bookmark,
            IN_REVIEW,
            f"{result.disposition.value} after {result.iterations} round(s)",
        )
        approved = self._gate("acceptance", spec.id, result.disposition.value)
        if not approved:
            self._move(bookmark, REJECTED, "human declined the generated result")
            return RunRecord(spec.id, REJECTED, result.disposition, result)

        artifacts = self._persist(spec, result)
        self._move(bookmark, DONE, f"accepted; {len(artifacts)} artifact(s) committed")
        self.emit("accepted", spec.id, {"artifacts": [str(p) for p in artifacts]})
        return RunRecord(spec.id, DONE, result.disposition, result, artifacts=artifacts)

    # -------------------------------------------------------------- library --
    def run_library(self, specs: list[Specification], *, root=None) -> list[RunRecord]:
        """Drive a whole spec library in dependency-topological order."""
        return [self.run(spec, root=root) for spec in _topological(specs)]

    # --------------------------------------------------------------- helpers --
    def _block(
        self,
        bookmark: str,
        spec: Specification,
        kind: str,
        detail: str,
        result: GenerationResult | None,
    ) -> RunRecord:
        self._move(bookmark, BLOCKED, f"{kind}: {detail}")
        self.emit("blocked", spec.id, {"kind": kind, "detail": detail})
        disposition = result.disposition if result else Disposition.SPEC_SUSPECT
        return RunRecord(spec.id, BLOCKED, disposition, result, escalated=True)

    def _persist(self, spec: Specification, result: GenerationResult) -> list[Path]:
        """Write the accepted code + tests to the tracked output dir."""
        if result.code is None or result.tests is None:
            return []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        module = _module_name(spec.id)
        return [
            self._write(self.output_dir / f"{module}.py", result.code),
            self._write(self.output_dir / f"test_{module}.py", result.tests),
        ]

    @staticmethod
    def _write(path: Path, artifact: Artifact) -> Path:
        header = f"# Generated by genspec from spec '{artifact.module_name}'. Do not edit by hand.\n"
        path.write_text(header + artifact.source, encoding="utf-8")
        return path

    def _move(self, bookmark: str, to_status: str, reason: str) -> None:
        self.lifecycle.transition(bookmark, to_status, self.actor, reason)

    def _gate(self, gate_type: str, spec_id: str, detail: str) -> bool:
        if self.gate_handler is None:
            return True
        return self.gate_handler(gate_type, spec_id, detail)


def _diag_summary(result: GenerationResult) -> str:
    errors = [d.message for d in result.diagnostics if d.level.value == "error"]
    return "; ".join(errors[:3]) or "spec failed validation"
