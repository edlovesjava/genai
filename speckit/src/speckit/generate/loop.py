"""The iterative generation loop — generation as a spec typechecker.

The pipeline treats *generate* the way a compiler treats *compile*: it is the
step that finds faults in the spec early and cheaply, in escalating order of
cost.

    1. Static pre-validation   — is the spec internally consistent?      (cheapest)
    2. Independent derivation   — do two agents, deriving tests and code
                                  separately, agree?                      (the typecheck)
    3. Bounded reconciliation   — if they disagree, is it a mere code gap
                                  (TDD converges) or a spec ambiguity
                                  (it doesn't)?
    4. Human gate               — even on agreement, is the spec *correct*
                                  (the right thing), not merely consistent? (final)

Two questions are kept distinct throughout: *does the code match the spec*
(verification, answered by conformance) and *is the spec correct* (validation,
answered only by a human gate). Mechanical agreement can never answer the second
— both agents can be consistently wrong — so the gate always remains.

A library of specs is decomposed and ordered by its ``depends`` graph, each spec
generated independently. Gates and decomposition are the same primitives Genesis
already uses (``HumanGateRequired``, dependency-ordered tasks).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from speckit.generate.agents import Artifact, Coder, TestAuthor, coder_brief, test_brief
from speckit.generate.conformance import ConformanceResult, Runner
from speckit.model import Specification
from speckit.validator import Diagnostic, validate, validate_all

# A gate handler is called with (gate_type, spec_id, detail) and returns approval.
GateHandler = Callable[[str, str, str], bool]


class HumanGateRequired(Exception):
    """Raised when a human approval gate blocks generation from continuing."""

    def __init__(self, gate_type: str, spec_id: str, detail: str = "") -> None:
        self.gate_type = gate_type
        self.spec_id = spec_id
        self.detail = detail
        super().__init__(f"Human gate '{gate_type}' required for {spec_id}: {detail}")


class Fault(str, Enum):
    """Where a fault was located, if any."""

    NONE = "none"
    SPEC = "spec"   # internally inconsistent, or an unreconcilable disagreement
    CODE = "code"   # a code gap that reconciliation closed


class Disposition(str, Enum):
    """The terminal disposition of a generation attempt."""

    VALIDATED = "validated"        # independent agreement on the first pass
    RECONCILED = "reconciled"      # disagreement closed by revising code (TDD)
    SPEC_SUSPECT = "spec_suspect"  # disagreement could not be reconciled
    INVALID = "invalid"            # static pre-validation failed
    REJECTED = "rejected"          # a human gate denied the result


@dataclass
class GenerationResult:
    spec_id: str
    disposition: Disposition
    fault: Fault = Fault.NONE
    code: Artifact | None = None
    tests: Artifact | None = None
    iterations: int = 0                       # reconciliation rounds performed
    diagnostics: list[Diagnostic] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.disposition in (Disposition.VALIDATED, Disposition.RECONCILED)


@dataclass
class Generator:
    """Drives the iterative loop for one spec or a whole library."""

    test_author: TestAuthor
    coder: Coder
    runner: Runner
    max_reconcile: int = 3
    gate_handler: GateHandler | None = None

    # ----------------------------------------------------------------- spec --
    def generate(self, spec: Specification, *, root=None) -> GenerationResult:
        log: list[str] = []

        # 1. Static pre-validation — the cheapest fault to find.
        diags = validate(spec, root=root)
        if any(d.level.value == "error" for d in diags):
            log.append("pre-validation failed; refusing to generate")
            return GenerationResult(
                spec_id=spec.id,
                disposition=Disposition.INVALID,
                fault=Fault.SPEC,
                diagnostics=diags,
                transcript=log,
            )

        module = _module_name(spec.id)

        # 2. Independent derivation — the typecheck.
        tests = self.test_author.author(test_brief(spec, module))
        code = self.coder.draft(coder_brief(spec, module))
        log.append("derived tests and code independently from the spec")

        result = self.runner.run(code, tests)
        if result.passed:
            log.append("independent tests and code agree on first pass")
            return self._gate(
                spec,
                GenerationResult(
                    spec_id=spec.id,
                    disposition=Disposition.VALIDATED,
                    fault=Fault.NONE,
                    code=code,
                    tests=tests,
                    diagnostics=diags,
                    transcript=log,
                ),
            )

        # 3. Disagreement: candidate spec fault. Attempt bounded TDD reconciliation.
        log.append("disagreement detected — attempting bounded reconciliation")
        code, iterations, reconciled, result = self._reconcile(
            spec, module, code, tests, result, log
        )

        if reconciled:
            return self._gate(
                spec,
                GenerationResult(
                    spec_id=spec.id,
                    disposition=Disposition.RECONCILED,
                    fault=Fault.CODE,
                    code=code,
                    tests=tests,
                    iterations=iterations,
                    diagnostics=diags,
                    transcript=log,
                ),
            )

        # 4. Could not reconcile: two faithful interpretations of the spec
        #    contradict each other. The spec under-determines the behavior.
        log.append(
            f"unreconciled after {iterations} round(s): probable spec fault "
            f"(the spec admits contradictory interpretations)"
        )
        spec_fault = GenerationResult(
            spec_id=spec.id,
            disposition=Disposition.SPEC_SUSPECT,
            fault=Fault.SPEC,
            code=code,
            tests=tests,
            iterations=iterations,
            diagnostics=diags,
            transcript=log,
        )
        # A suspected spec fault always escalates to a human — this is a
        # decision about the source of truth, not something to auto-resolve.
        self._raise_gate("spec_fault", spec.id, result.output[:500])
        return spec_fault

    def _reconcile(
        self,
        spec: Specification,
        module: str,
        code: Artifact,
        tests: Artifact,
        result: ConformanceResult,
        log: list[str],
    ) -> tuple[Artifact, int, bool, ConformanceResult]:
        brief = coder_brief(spec, module)
        for i in range(1, self.max_reconcile + 1):
            code = self.coder.revise(brief, code, result.output)
            result = self.runner.run(code, tests)
            log.append(f"reconcile round {i}: {'pass' if result.passed else 'fail'}")
            if result.passed:
                return code, i, True, result
        return code, self.max_reconcile, False, result

    # -------------------------------------------------------------- library --
    def generate_library(
        self, specs: list[Specification], *, root=None
    ) -> list[GenerationResult]:
        """Generate a whole spec library, decomposed and dependency-ordered.

        A library-wide static check runs first (catches duplicate ids and
        unresolved dependencies), then specs are generated in topological order
        so a spec is only built after the specs it depends on.
        """
        results: list[GenerationResult] = []
        lib_diags = validate_all(specs, root=root)
        if any(d.level.value == "error" for d in lib_diags):
            # Surface library-level faults as a single INVALID result up front.
            results.append(
                GenerationResult(
                    spec_id="<library>",
                    disposition=Disposition.INVALID,
                    fault=Fault.SPEC,
                    diagnostics=lib_diags,
                    transcript=["library-level pre-validation failed"],
                )
            )
            return results

        for spec in _topological(specs):
            results.append(self.generate(spec, root=root))
        return results

    # ----------------------------------------------------------------- gates --
    def _gate(self, spec: Specification, result: GenerationResult) -> GenerationResult:
        """Acceptance gate: a human confirms the spec is *correct*, not just consistent."""
        detail = f"{result.disposition.value} after {result.iterations} round(s)"
        approved = self._ask_gate("acceptance", spec.id, detail)
        if not approved:
            result.disposition = Disposition.REJECTED
            result.transcript.append("human gate rejected the generated result")
        return result

    def _ask_gate(self, gate_type: str, spec_id: str, detail: str) -> bool:
        if self.gate_handler is None:
            return True  # no handler => permissive (mirrors GenesisRunner default)
        return self.gate_handler(gate_type, spec_id, detail)

    def _raise_gate(self, gate_type: str, spec_id: str, detail: str) -> None:
        if self.gate_handler is not None and self.gate_handler(gate_type, spec_id, detail):
            return
        raise HumanGateRequired(gate_type, spec_id, detail)


def _module_name(spec_id: str) -> str:
    """Turn a dotted spec id into a safe python module name."""
    return spec_id.replace(".", "_").replace("-", "_")


def _topological(specs: list[Specification]) -> list[Specification]:
    """Order specs so dependencies come before dependents (stable, cycle-safe)."""
    by_id = {s.id: s for s in specs}
    ordered: list[Specification] = []
    seen: set[str] = set()

    def visit(spec: Specification, stack: set[str]) -> None:
        if spec.id in seen:
            return
        for dep in spec.depends:
            dep_spec = by_id.get(dep)
            if dep_spec is not None and dep not in stack:
                visit(dep_spec, stack | {spec.id})
        seen.add(spec.id)
        ordered.append(spec)

    for spec in specs:
        visit(spec, {spec.id})
    return ordered
