---
id: genspec.generate
title: Spec-to-Code Generation Loop
status: active
abstraction: model
source: [../src/genspec/generate/loop.py, ../src/genspec/generate/agents.py, ../src/genspec/generate/conformance.py]
depends: [genspec.format]
---

# Spec-to-Code Generation Loop

The "compiler" half of *the spec is the code*: it lowers a validated spec into a
disposable implementation. Generation is treated as a typecheck on the spec —
its job is to find faults in the spec early, in escalating order of cost, and to
escalate to a human when the source of truth itself is in question.

## Intent

Produce, from one spec, both a test module and a production module, and establish
two distinct facts: that the code matches the spec (verification) and that the
spec is correct (validation). The first is answered mechanically; the second can
only be answered at a human gate, because two agents can be consistently wrong.
Faults are surfaced as early and cheaply as possible.

## Structure

- **Independent agents** — `TestAuthor` derives tests from a `TestBrief`
  (intent + behavior + qualities); `Coder` derives code from a `CoderBrief`
  (intent + structure + qualities). Each brief is a projection of the spec that
  excludes the other agent's concern: the author never sees code, the coder's
  first draft never sees tests.
- **`Runner`** — runs the generated tests against the generated code
  (`PytestRunner` materializes both in a temp package and invokes pytest).
- **`Generator`** — orchestrates the loop; carries `max_reconcile` and an
  optional `gate_handler`.
- **`GenerationResult`** — `Disposition` (validated | reconciled | spec_suspect |
  invalid | rejected), a located `Fault` (none | spec | code), iteration count,
  diagnostics, and a transcript.
- A library of specs is decomposed and generated in `depends`-topological order.

## Behavior

### Scenario: an inconsistent spec is refused before any generation
Given a spec that fails static validation
When generation is requested
Then no agent is invoked
And the result disposition is INVALID with a SPEC fault

### Scenario: independent agreement validates the spec
Given a consistent spec
When the test author and coder derive their artifacts independently
And the generated tests pass against the generated code on the first pass
Then the disposition is VALIDATED with no fault

### Scenario: a code gap is reconciled by TDD
Given independently generated tests that initially fail against the code
When the coder is shown the failure output and revises within the budget
And the tests then pass
Then the disposition is RECONCILED with a CODE fault

### Scenario: an unreconcilable disagreement is a spec fault
Given independently generated tests that the coder cannot satisfy within the reconcile budget
When the budget is exhausted
Then the disposition is SPEC_SUSPECT with a SPEC fault
And the result escalates to a human via a spec_fault gate

### Scenario: a consistent result can still be rejected by a human
Given a spec whose generation reaches agreement
When the acceptance gate handler declines the result
Then the disposition is REJECTED

### Scenario: a library is generated in dependency order
Given a set of specs where one depends on another
When the library is generated
Then each spec is generated only after the specs it depends on

## Qualities

- **Determinism under test** — the LLM agents and the test runner are Protocols;
  the orchestration has no hidden I/O and is fully exercised with doubles.
- **Escalating cost** — checks run cheapest-first: static validation, then
  independent derivation, then bounded reconciliation, then a human gate.
- **Separation of verification and validation** — mechanical agreement never
  closes the "is the spec correct?" question; the acceptance gate always runs.
- **Bounded reconciliation** — the coder may revise at most `max_reconcile`
  times before a disagreement is declared a spec fault; the loop never spins.
- **Spec faults escalate, never auto-resolve** — a suspected fault in the source
  of truth is a human decision.

## Validation

- `tests/test_generate.py` drives every disposition with scripted agents and a
  fake runner, and exercises the real `PytestRunner` end to end.
- The source-anchoring check confirms the three `source:` modules exist.
- `depends: [genspec.format]` resolves within this spec library.
