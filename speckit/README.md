# speckit — the spec is the code

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

A speckit specification is **human-readable but semi-structured**, and it spans
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
speckit/
├── README.md                    # this file — the paradigm
├── pyproject.toml               # isolated, zero-runtime-dependency package
├── specs/
│   ├── format.spec.md           # the spec format, written in its own format (self-hosting)
│   └── state-machine.spec.md     # a model of existing Genesis code
├── src/speckit/
│   ├── model.py                 # the high-fidelity model: typed dataclasses
│   ├── parser.py                # .spec.md  ──▶  Specification
│   └── validator.py             # Specification ──▶ diagnostics (spec as source of validation)
└── tests/
    └── test_speckit.py
```

## Use

```bash
cd speckit
pip install -e ".[dev]"

# Parse a spec and print its structured model
python -m speckit show specs/state-machine.spec.md

# Validate specs: required sections, Given/When/Then completeness,
# and that every `source:` file the spec claims to describe actually exists.
python -m speckit validate specs/

pytest
```

`speckit` has **no runtime dependencies** — the parser is a small hand-written
reader so the format stays inspectable and the package stays portable.

## Status

This is the foundation: the format, the model, the parser, and the validator —
the parts that make a spec *checkable*. The next layer (not yet built) is the
**generator**: the agent path that lowers a validated spec into source code, the
"compiler" half of the analogy.
