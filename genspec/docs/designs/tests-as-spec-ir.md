# Design: Tests Are the Compiled Spec (intent + design = tests)

> Reframes what tests *are* in genspec, and gives the bidding judge (see
> [intent-first-bidding.md](./intent-first-bidding.md)) an objective fitness
> function. Ties together the generate, bid, and orchestrate layers.
>
> Status: conceptual model + identified seams. Fitness-function wiring is the
> open build.

## The equation

    intent + design = tests

Not literal equality — a **compile relation**. Once the intent is fixed and a
design is chosen, the test suite is *determined*, not independently authored. It
decomposes:

| Source | Yields | Nature |
|--------|--------|--------|
| **intent** alone | acceptance / invariant tests (black-box) | design-**independent**, durable as the intent |
| **design** adds | contract / unit tests (structure, interfaces, ADR decisions) | design-**specific**, disposable with the design |

Full suite = intent-tests ∪ design-tests.

## Consequence 1 — tests are the IR, code is the object code

```
intent ──(bidding: choose design)──▶ design
intent ∧ design ──(compile)──▶ TESTS        # the executable form of the spec
tests ∧ design ──(generate)──▶ code          # disposable; must pass the tests
```

This is the cleanest statement of *the spec is the code*: the **tests** are the
compiled spec — the most concrete durable artifact — and code is regenerated to
satisfy them. The model-vs-implementation boundary lands exactly on the test
suite (cf. OpenAPI/protobuf: the contract is source, stubs regenerate).

## Consequence 2 — intent-tests are the bidding fitness function

Because intent-tests are design-independent, they score *any* design objectively:

```
for each bid:
    design  = bid
    code    = generate(intent ∧ design)
    fitness = pass_rate(code, intent_tests)     # design-independent oracle
judge picks argmax(fitness)   (with divergence guaranteeing a real contest)
```

Forced divergence (guaranteed a *real* choice) + intent-test pass-rate (decides
*which* choice) turns the judge from LLM-vibes into a measurable competition. This
is the concrete upgrade to the "honest N-version / honest bidding" differentiation
axis in [PRIOR-ART.md](../PRIOR-ART.md §4).

## Consequence 3 — it dissolves the common-mode anxiety

The old consensus model treated Test-Author and Coder as two *independent*
derivations and feared correlated failure. If tests = f(intent, design)
canonically, tests are not a competing oracle — they are **the target**. What's
required is not tester/coder independence but:

- tests are a faithful **compilation** of intent ∧ design, and
- code is **read-only** against the tests (generated from the spec, never from the
  tests' internals), so it cannot overfit by editing them.

The `genspec.generate` loop already enforces the second: the Coder never sees the
test source, only failure output. What changes is framing — tests move from
"independent second opinion" to "the compiled spec the code must satisfy."

## The honest caveat

The compile is **lossy** — an LLM performs it, so tests are the best executable
*proxy* for intent ∧ design, not a proof. Non-functional qualities (performance,
security) only partly reduce to tests (→ property/benchmark tests); the remainder
stays with the human acceptance gate, which is why the gate remains
non-negotiable. A useful pressure falls out of this: **intent specs must state
acceptance concretely (testably)**, or their intent-tests are weak — which aligns
"intent-first" with "testable intent."

## Seams in the current code

- `genspec.bid.IntentBrief` already carries `intent`, `qualities`, and
  `acceptance` (the spec's `validation` section) — the exact inputs for
  **intent-test** derivation.
- `genspec.generate.TestAuthor` derives tests from a brief; splitting it into an
  **IntentTestAuthor** (from `IntentBrief`, design-independent) and a
  **DesignTestAuthor** (from the chosen design) realizes the ∪ above.
- `genspec.bid.Judge` is where fitness-scoring plugs in: a scoring judge that runs
  each bid's generated code against the intent-tests and returns pass-rate scores.

## Open build

1. **IntentTestAuthor** — derive design-independent acceptance tests from an
   `intent` spec's Given/When/Then acceptance.
2. **Fitness judge** — a `Judge` that scores bids by intent-test pass-rate over
   generated code, combined with divergence for contest validity.
3. **Suite composition** — union intent-tests with design-tests in the generate
   loop; keep intent-tests as a stable regression contract across design changes.
4. **Non-functional coverage** — property/benchmark tests for qualities that don't
   reduce to example-based tests; everything else stays gate-checked.
