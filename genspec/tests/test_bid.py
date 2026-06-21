"""Tests for the forced-divergence bidding market and intent-first kinds."""

from __future__ import annotations

import pytest

from genspec.bid import (
    Bid,
    BidMarket,
    InsufficientDivergence,
    IntentBrief,
    Outcome,
    Verdict,
    token_divergence,
)
from genspec.bid.personas import INNOVATOR, STEADY_EDDIE
from genspec.model import Kind
from genspec.parser import parse_text
from genspec.validator import Level, has_errors, validate

INTENT_SPEC = """\
---
id: demo.cache
title: Result Cache
kind: intent
status: active
abstraction: model
---

# Result Cache

## Intent
Avoid recomputing expensive results by caching them, so repeated requests are fast.

## Qualities
Bounded memory; correctness over raw speed; no external services at bootstrap.

## Validation
A repeated request returns the cached result and does not recompute.
"""


# --------------------------------------------------------------------------- #
# Doubles
# --------------------------------------------------------------------------- #


class ScriptedBidder:
    def __init__(self, persona, bid: Bid) -> None:
        self.persona = persona
        self._bid = bid

    def bid(self, brief: IntentBrief) -> Bid:
        return self._bid


class ScriptedJudge:
    def __init__(self, verdict: Verdict) -> None:
        self._verdict = verdict
        self.saw: list[Bid] | None = None

    def adjudicate(self, brief: IntentBrief, bids: list[Bid]) -> Verdict:
        self.saw = bids
        return self._verdict


STEADY_BID = Bid(
    persona="steady-eddie",
    approach="Use a plain dict guarded by an LRU eviction policy from the standard library.",
    decisions=("dependency: none", "eviction: functools.lru_cache", "risk: low"),
)
INNOVATOR_BID = Bid(
    persona="innovator",
    approach="Adopt an async TTL cache backed by a high-performance third-party library.",
    decisions=("dependency: cachetools", "eviction: TTL", "concurrency: async"),
)


# --------------------------------------------------------------------------- #
# Intent-first kinds
# --------------------------------------------------------------------------- #


def test_intent_spec_validates_without_structure_or_behavior():
    spec = parse_text(INTENT_SPEC)
    assert spec.kind is Kind.INTENT
    assert spec.required_sections == ("intent", "qualities", "validation")
    diags = validate(spec, root="/")  # no source: anchoring needed
    assert not has_errors(diags), [str(d) for d in diags]


def test_component_spec_still_requires_all_five():
    # No kind => COMPONENT default => structure/behavior required.
    spec = parse_text(INTENT_SPEC.replace("kind: intent\n", ""))
    assert spec.kind is Kind.COMPONENT
    diags = validate(spec, root="/")
    msgs = [d.message for d in diags if d.level is Level.ERROR]
    assert any("structure" in m for m in msgs)
    assert any("behavior" in m for m in msgs)


# --------------------------------------------------------------------------- #
# Divergence metric
# --------------------------------------------------------------------------- #


def test_identical_bids_have_zero_divergence():
    assert token_divergence(STEADY_BID, STEADY_BID) == 0.0


def test_contrasting_bids_diverge():
    assert token_divergence(STEADY_BID, INNOVATOR_BID) > 0.5


# --------------------------------------------------------------------------- #
# The market
# --------------------------------------------------------------------------- #


def _market(verdict, **kw):
    judge = ScriptedJudge(verdict)
    market = BidMarket(
        bidders=[
            ScriptedBidder(STEADY_EDDIE, STEADY_BID),
            ScriptedBidder(INNOVATOR, INNOVATOR_BID),
        ],
        judge=judge,
        **kw,
    )
    return market, judge


def test_pick_resolves_to_the_winning_bid():
    verdict = Verdict(Outcome.PICK, scores={"steady-eddie": 8.0, "innovator": 6.0}, winner="steady-eddie")
    market, judge = _market(verdict)

    result = market.run(parse_text(INTENT_SPEC))

    assert result.verdict.outcome is Outcome.PICK
    assert result.chosen is STEADY_BID
    assert result.min_divergence > 0.5
    assert judge.saw is not None and len(judge.saw) == 2  # judge saw both bids


def test_synthesize_returns_the_merged_design():
    merged = Bid(persona="synthesis", approach="dict + optional TTL", decisions=("dependency: none",))
    market, _ = _market(Verdict(Outcome.SYNTHESIZE, synthesis=merged))

    result = market.run(parse_text(INTENT_SPEC))

    assert result.verdict.outcome is Outcome.SYNTHESIZE
    assert result.chosen is merged


def test_reject_yields_no_chosen_design():
    market, _ = _market(Verdict(Outcome.REJECT, rationale="neither bounds memory"))
    result = market.run(parse_text(INTENT_SPEC))
    assert result.chosen is None


def test_converged_bids_raise_insufficient_divergence():
    # Both bidders return the same approach: common-mode, no real contest.
    judge = ScriptedJudge(Verdict(Outcome.PICK, winner="steady-eddie"))
    market = BidMarket(
        bidders=[ScriptedBidder(STEADY_EDDIE, STEADY_BID), ScriptedBidder(INNOVATOR, STEADY_BID)],
        judge=judge,
    )
    with pytest.raises(InsufficientDivergence):
        market.run(parse_text(INTENT_SPEC))
    assert judge.saw is None  # never reached the judge


def test_divergence_enforcement_can_be_disabled():
    judge = ScriptedJudge(Verdict(Outcome.PICK, winner="steady-eddie"))
    market = BidMarket(
        bidders=[ScriptedBidder(STEADY_EDDIE, STEADY_BID), ScriptedBidder(INNOVATOR, STEADY_BID)],
        judge=judge,
        enforce_divergence=False,
    )
    result = market.run(parse_text(INTENT_SPEC))  # does not raise
    assert result.min_divergence == 0.0


def test_market_requires_at_least_two_bidders():
    market = BidMarket(bidders=[ScriptedBidder(STEADY_EDDIE, STEADY_BID)], judge=ScriptedJudge(Verdict(Outcome.REJECT)))
    with pytest.raises(ValueError, match="at least two bidders"):
        market.run(parse_text(INTENT_SPEC))


def test_intent_brief_excludes_structure():
    brief = IntentBrief.from_spec(parse_text(INTENT_SPEC))
    assert "cach" in brief.intent.lower()
    assert brief.acceptance  # validation/acceptance carried
    # IntentBrief has no structure field at all — structure is a bid output.
    assert not hasattr(brief, "structure")
