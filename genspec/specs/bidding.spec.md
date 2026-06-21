---
id: genspec.bidding
title: Forced-Divergence Bidding Market
kind: component
status: active
abstraction: model
source: [../src/genspec/bid/market.py, ../src/genspec/bid/personas.py]
depends: [genspec.bidding.intent, genspec.generate]
---

# Forced-Divergence Bidding Market

The realization of `genspec.bidding.intent`. A Contract-Net-style market where
persona-biased bidders propose competing designs for one intent and a judge
adjudicates. It sits *above* the generation loop: it chooses a design; the loop
then lowers that design into code.

## Intent

Decorrelate the agents on purpose so a choice between designs is meaningful.
Replace "hope two agents independently agree" (weak evidence, common-mode prone)
with "force two agents to disagree, then adjudicate" (the disagreement is the
product). Carry the winning design forward into generation.

## Structure

- **`Persona`** — a named temperament (stance + directives) that biases a bidder
  toward a corner of the design space; defaults `STEADY_EDDIE` and `INNOVATOR`
  mirror multivator's Conservative/Experimental split.
- **`IntentBrief`** — the projection every bidder sees: intent, qualities, and
  acceptance, with **no** structure (structure is a bid output).
- **`Bid`** — a persona-tagged proposed approach plus ADR-style decisions.
- **`Bidder`** / **`Judge`** — Protocols; the judge returns a `Verdict`.
- **`Verdict`** — `Outcome` of `PICK` | `SYNTHESIZE` | `REJECT`, with scores and
  rationale, and a synthesized `Bid` when merging.
- **`BidMarket`** — collects bids, enforces a minimum pairwise divergence
  (`DivergenceFn`, default token-set distance), then adjudicates.
- **`InsufficientDivergence`** — raised when bids converge below threshold.

## Behavior

### Scenario: contrasting bidders produce a real contest
Given two bidders with opposing personas and an intent
When the market runs
Then it collects one bid per bidder
And the minimum pairwise divergence exceeds the threshold
And the judge is asked to adjudicate the bids

### Scenario: a pick resolves to the winning bid
Given a judge that returns a PICK verdict naming a persona
When the market runs
Then the chosen design is that persona's bid

### Scenario: a synthesis returns the merged design
Given a judge that returns a SYNTHESIZE verdict with a merged bid
When the market runs
Then the chosen design is the merged bid

### Scenario: converged bids are flagged, not accepted
Given two bidders that return near-identical proposals
When the market runs with divergence enforcement on
Then it raises InsufficientDivergence
And the judge is never consulted

### Scenario: rejection yields no design
Given a judge that rejects all bids
When the market runs
Then there is no chosen design and the intent must be re-announced

## Qualities

- **Forced divergence is enforced, not assumed** — a quantified gate rejects
  common-mode bids before any adjudication.
- **Pluggable, dependency-free metric** — divergence defaults to token-set
  distance; an embedding metric can be injected without changing the market.
- **Deterministic under test** — bidders and judge are Protocols; the market has
  no hidden I/O.
- **Bounded and total** — a market needs ≥2 bidders and terminates in one round
  with a verdict or an explicit divergence failure.
- **Composes with generation** — the chosen design becomes the Structure/Behavior
  that feeds the existing `genspec.generate` loop.

## Validation

- `tests/test_bid.py` drives every outcome (pick, synthesize, reject), the
  divergence gate (enforced and disabled), and the intent-first projection.
- The source-anchoring check confirms both `source:` modules exist;
  `depends: [genspec.bidding.intent, genspec.generate]` resolves in the library.
