---
id: genspec.bidding.intent
title: Competitive Design Bidding (Intent)
kind: intent
status: active
abstraction: model
---

# Competitive Design Bidding (Intent)

An intent-first spec: it states *why* competitive bidding exists and the
constraints it must honor, but deliberately does **not** prescribe the structure
or behavior — those are exactly what competing designs propose. (The realized
design is described separately in `genspec.bidding`.)

## Intent

When a spec is reduced to its durable core — intent and constraints — there are
many valid ways to satisfy it. Choosing well is the high-leverage decision, and a
single agent (or two convergent ones) chooses poorly and invisibly. The intent is
to surface that decision: have several deliberately *different* designers propose
competing approaches to the same intent, and adjudicate between them, so the
design choice is explicit, contested, and recorded rather than implicit and
arbitrary.

## Qualities

- **Genuine divergence** — competing proposals must differ enough to constitute a
  real choice; convergence (common-mode agreement) is a failure to detect, not a
  success to celebrate.
- **Intent-anchored** — every proposal is judged on fidelity to this intent and
  its constraints, not on novelty for its own sake.
- **Adjudicated, not voted** — the outcome may be to pick one design, synthesize
  several, or reject all and re-announce; a human can always overrule.
- **Traceable** — the proposals, the divergence achieved, and the verdict are
  recorded as decision artifacts (ADR-like), not discarded.
- **Bounded** — the contest terminates; it does not spin generating proposals.

## Validation

- Given one intent and two deliberately contrasting designers, the system
  produces two materially different proposals and a single recorded verdict.
- Given two proposals that turn out near-identical, the system flags insufficient
  divergence rather than proceeding as if a real choice was made.
- The chosen (or synthesized) design is the one carried forward into generation.
