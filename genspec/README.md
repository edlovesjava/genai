# genspec — the spec is the code

> A radical shift for Genesis: the **specification** is the source of truth.
> Generated source code is a build artifact — disposable and replaceable.

## The thesis

In a 3GL toolchain, you write source code and a compiler lowers it to machine
code. Nobody hand-edits the machine code; it is regenerated from source on every
build. The **source is the durable artifact; the binary is disposable.**

Agentic coding introduces the same relationship one level up:

```
  3GL world:        source code  ──(compiler)──▶   machine code   (disposable)
  Agentic world:    specification ──(agents)────▶  source code     (disposable)
```

The implication is the inversion this package is built around:

- The **spec** is the true source. It is what humans author, review, and own.
- The **generated code** is an artifact. It can be regenerated, thrown away,
  re-targeted to another language, or rebuilt by a better model — without loss,
  because the spec carries the intent.

For this to hold, a spec cannot be a loose prose sketch. It must be a
**high-fidelity model** of the system: comprehensive enough that the
implementation it produces is determined by it, and structured enough that it
can be mechanically validated.

## What a spec must capture

A genspec specification is **human-readable but semi-structured**, and it spans
the full surface of a system across two axes:

| Axis | One end | Other end |
|------|---------|-----------|
| **Concern**     | Functional (what it does) | Non-functional (qualities, constraints) |
| **Perspective** | Structural (what it is)   | Behavioral (how it acts)                |

It also declares its **level of abstraction** — `model` (the durable design) vs
`implementation` (a spec pinned to a concrete realization) — so the model layer
stays free of incidental implementation detail.

A single spec is organized into five canonical sections:

| Section        | Axis it serves            | Contents                                              |
|----------------|---------------------------|-------------------------------------------------------|
| **Intent**     | Functional / why          | Purpose, the problem it solves, scope                 |
| **Structure**  | Structural                | Components, types, relationships, contracts           |
| **Behavior**   | Behavioral                | `Given / When / Then` scenarios                       |
| **Qualities**  | Non-functional            | Invariants, constraints, budgets, performance, safety |
| **Validation** | Traceability              | How conformance to this spec is checked               |

Because specs describe **existing code** as readily as **planned features**, the
same format reverse-documents the current system and forward-plans the next one.
`specs/state-machine.spec.md` is a real example: it is a faithful model of the
already-shipped `src/genesis/state/machine.py`.

## Layout

```
genspec/
├── README.md                    # this file — the paradigm
├── pyproject.toml               # isolated, zero-runtime-dependency package
├── specs/
│   ├── format.spec.md           # the spec format, written in its own format (self-hosting)
│   ├── state-machine.spec.md     # a model of existing Genesis code
│   └── generate.spec.md         # a model of the generator (self-describing)
├── src/genspec/
│   ├── model.py                 # the high-fidelity model: typed dataclasses
│   ├── parser.py                # .spec.md  ──▶  Specification
│   ├── validator.py             # Specification ──▶ diagnostics (spec as source of validation)
│   └── generate/                # the "compiler" half — spec ──▶ disposable code
│       ├── agents.py            # independent TestAuthor / Coder (Protocols)
│       ├── conformance.py       # run generated tests against generated code
│       └── loop.py              # the iterative TDD loop + fault classification + gates
└── tests/
    ├── test_genspec.py
    └── test_generate.py
```

## Use

```bash
cd genspec
pip install -e ".[dev]"

# Parse a spec and print its structured model
python -m genspec show specs/state-machine.spec.md

# Validate specs: required sections, Given/When/Then completeness,
# and that every `source:` file the spec claims to describe actually exists.
python -m genspec validate specs/

pytest
```

`genspec` has **no runtime dependencies** — the parser is a small hand-written
reader so the format stays inspectable and the package stays portable.

## Generation — the compiler half

`genspec.generate` lowers a validated spec into code the way a compiler lowers
source, and it treats *generate* as a **typecheck on the spec**: its purpose is
to find faults in the spec early, cheapest-first.

```bash
python -m genspec validate specs/    # 1. is the spec internally consistent?
# then, in code:
Generator(test_author, coder, runner).generate(spec)
```

The loop derives **two artifacts from one spec, independently** — a test module
(from behavior + qualities) and a production module (from intent + structure) —
by two agents that never see each other's output. What happens next *is* the
typecheck:

| Stage | Question | Outcome |
|-------|----------|---------|
| Static pre-validation | Is the spec internally consistent? | `INVALID` → SPEC fault, nothing generated |
| Independent derivation | Do the two interpretations agree? | tests pass → `VALIDATED` |
| Bounded reconciliation | Is the gap just a code error? | TDD converges → `RECONCILED` (CODE fault) |
| — | …or a spec ambiguity? | can't converge → `SPEC_SUSPECT`, escalate to human |
| Acceptance gate | Is the spec *correct*, not merely consistent? | human may `REJECT` |

Two questions stay distinct: **does the code match the spec** (verification, via
conformance) and **is the spec correct** (validation, only a human gate can
answer — both agents can be consistently wrong). So the gate always runs, and a
suspected spec fault always escalates rather than auto-resolving. This is where
the paradigm reconnects to Genesis's own primitives: **human gates** and
**dependency-ordered decomposition** (a spec library is generated in
`depends`-topological order).

## Status

The durable half (format, model, parser, validator) and the compiler half
(independent-agent TDD generation with gates) are in place and tested. The agents
themselves are Protocols: a real Claude-backed `TestAuthor`/`Coder` plugs into the
same loop the tests drive with deterministic doubles.
