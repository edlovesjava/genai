"""genspec.bid — forced-divergence competitive bidding over a design.

Intent-first: a spec states *what* and *why* (intent + constraints); competing,
persona-biased bidders propose *how* (structure / ADRs); a judge picks, synthesizes,
or rejects. This decorrelates the agents on purpose, so a choice between designs is
meaningful rather than a coin flip between two near-identical answers.
"""

from __future__ import annotations

from genspec.bid.market import (
    Bid,
    Bidder,
    BidMarket,
    DivergenceFn,
    InsufficientDivergence,
    IntentBrief,
    Judge,
    MarketResult,
    Outcome,
    Verdict,
    token_divergence,
)
from genspec.bid.personas import DEFAULT_PERSONAS, INNOVATOR, STEADY_EDDIE, Persona

__all__ = [
    "Bid",
    "Bidder",
    "BidMarket",
    "DivergenceFn",
    "InsufficientDivergence",
    "IntentBrief",
    "Judge",
    "MarketResult",
    "Outcome",
    "Verdict",
    "token_divergence",
    "Persona",
    "STEADY_EDDIE",
    "INNOVATOR",
    "DEFAULT_PERSONAS",
]
