# Design: Intent-First Specs + Forced-Divergence Bidding

> Folds the [multivator](https://github.com/edlovesjava/multivator) experiment
> into genspec, and resolves the common-mode-failure caveat from
> [PRIOR-ART.md](../PRIOR-ART.md §3) by replacing *consensus* with *adjudicated
> competition*.
>
> Status: foundation implemented (`genspec.bid`, intent-first `kind`); design loop
> integration is the open work (§5).

## 1. The shift in one paragraph

genspec's first generation model was **consensus** (N-version): a Test-Author and
a Coder derive independently, and *agreement* is read as evidence the spec is
sound. The honest critique (PRIOR-ART §3) is that two LLMs are not independent —
they share training data and biases — so agreement is weak evidence and
convergence is common. multivator demonstrated the better mechanism:
**deliberately force divergence** (Conservative vs Experimental implementors in
isolated worktrees from one RFP) and **adjudicate** with a judge that returns
`PICK A / PICK B / SYNTHESIZE / REJECT BOTH`. We adopt that. Disagreement stops
being a fault to reconcile and becomes the **product** to choose among.

This only coheres if the spec is **intent-first**: if structure and behavior are
things designers *propose*, the durable spec is just **intent + constraints** —
which is exactly an RFP.

## 2. Two changes, both landed as foundation

### 2.1 Intent-first spec kinds
A spec now declares a `kind`, and required sections follow from it:

| kind | required sections | role |
|------|-------------------|------|
| `intent` | intent, qualities, validation | the durable RFP — *why* and constraints; **no** structure/behavior |
| `design` | intent, structure, behavior, validation | one proposal/ADR bound to an intent |
| `component` (default) | all five | the full implementation-anchored model (original shape) |

`component` is the default, so every existing spec is unchanged. `specs/bidding-intent.spec.md`
is a worked `intent` spec; it legitimately omits structure/behavior because those
are what bidders compete to supply.

### 2.2 The bidding market (`genspec.bid`)
A Contract Net: announce (intent) → bid (persona-biased) → adjudicate (judge).

- **`Persona`** biases a bidder toward a design corner. Defaults `STEADY_EDDIE`
  (reliability, stdlib, low risk) and `INNOVATOR` (performance, modern, bold) —
  multivator's split.
- **`BidMarket`** collects one `Bid` per bidder, then **enforces a minimum
  pairwise divergence** before consulting the judge. If bids converged
  (common-mode), it raises `InsufficientDivergence` — the failure we previously
  could only hand-wave about is now a detectable, typed event.
- **`Judge`** returns a `Verdict`: `PICK` (winning persona), `SYNTHESIZE` (merged
  bid), or `REJECT` (re-announce).

Divergence is a pluggable pure function (default token-set distance) so there's
no embedding dependency; a real deployment swaps in semantic similarity.

## 3. How the two generation models now relate

These are complementary layers, not competitors:

```
intent spec ──▶ BidMarket (forced divergence, persona bids) ──▶ Verdict
                                                                  │ chosen design
                                                                  ▼
                                            design (structure + behavior)
                                                                  │
                              genspec.generate loop (Test-Author + Coder, conformance)
                                                                  │
                                          SpecRunner lifecycle (gates, state, bus)
```

- **Bidding** chooses *the design* (architecture / ADRs) under forced divergence.
- **Generation** lowers the chosen design into code, where the consensus check
  still has value *as a conformance test*, not as the primary correctness oracle.
- **Orchestration** (SpecRunner) is unchanged; bidding slots in before
  `IN_PROGRESS`, naturally as a new gate ("design review" — which Genesis's
  V-Model already calls for).

## 4. Why this is the differentiation, not just a feature

From PRIOR-ART §4, the defensible axes were "validatable specs," "fault
localization," and "honest N-version." This design advances all three at once and
is the part of the landscape **no one else is doing rigorously**:

- Spec Kit / Kiro / Tessl generate *a* design; none stage a **contested** design
  step with **enforced** divergence and a judge.
- multivator proved the mechanism but as a shell/worktree harness, not as a
  validatable spec pipeline with gates and state.
- Combining them — *intent-first validatable specs + forced-divergence adjudicated
  bidding + governed lifecycle* — is a genuinely distinct position:
  **"genspec doesn't generate the design, it runs a contest for it, honestly."**

### Prior art for the bidding paradigm specifically
- **Contract Net Protocol** (R. G. Smith, 1980) — announce → bid → award; the
  market structure here.
- **Multi-agent debate** (Du et al., 2023) — diverse agents improve outcomes by
  disagreeing then resolving.
- **Quality-Diversity / MAP-Elites** (Mouret & Clune) — value *diverse* high
  performers, not just the single best; the philosophical backing for forcing
  divergence rather than maximizing one score.
- **Architecture Decision Records** (Nygard, 2011) — bids emit ADR-style
  decisions, making the contest auditable.
- **LLM-as-judge** — the adjudication step.
- **multivator** — the working precedent for persona-forced divergence + judge.

## 5. Open work (the integration, deliberately not yet built)

1. **`design` spec emission** — turn a winning `Bid` into a `design`-kind spec
   (intent reference + proposed structure/behavior + ADRs) that the generate loop
   consumes. This is the seam that connects §2.2 to §2.1.
2. **Real bidders/judge** — Claude-backed `Bidder`s (one per persona, decorrelated
   by model/temperature/prompt) and a rubric `Judge`. The Protocols are ready.
3. **Semantic divergence** — an embedding-based `DivergenceFn` so "different
   words" becomes "different ideas."
4. **SpecRunner design gate** — add bidding as the design-review gate before
   `IN_PROGRESS`, recording the verdict on the bus and the ADRs to disk.
5. **Decorrelation evidence** — measure and report achieved divergence over runs,
   so the "honest N-version" claim is backed by data, not assertion.

The foundation (kinds + market + personas + divergence gate, fully tested) is in
place; the above is what turns it into the end-to-end design contest.
