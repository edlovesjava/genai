"""The bidding market — forced-divergence competition over a design.

Flow (a Contract Net: announce → bid → adjudicate):

    intent spec ──▶ IntentBrief ──▶ N persona-biased bidders ──▶ bids
                                          │
                              forced-divergence gate (bids must actually differ)
                                          │
                                       Judge ──▶ Verdict (PICK | SYNTHESIZE | REJECT)

The winning (or synthesized) design is what then feeds genspec's existing
generation loop as the spec's Structure/Behavior. This module owns *choosing a
design*, not generating code.

As with the rest of genspec, the agents (``Bidder``, ``Judge``) are Protocols so
the market is deterministically testable; the divergence metric is a pluggable
pure function (default: token-set distance) so no embedding service is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Callable, Protocol, runtime_checkable

from genspec.bid.personas import Persona
from genspec.model import Specification


@dataclass(frozen=True)
class IntentBrief:
    """What every bidder sees: the durable intent and constraints (the RFP).

    Deliberately *excludes* any proposed structure — that is what bidders compete
    to provide.
    """

    spec_id: str
    title: str
    intent: str
    qualities: str
    acceptance: str  # the spec's validation/acceptance criteria

    @classmethod
    def from_spec(cls, spec: Specification) -> "IntentBrief":
        def body(name: str) -> str:
            section = spec.section(name)
            return section.body if section else ""

        return cls(
            spec_id=spec.id,
            title=spec.title,
            intent=body("intent"),
            qualities=body("qualities"),
            acceptance=body("validation"),
        )


@dataclass(frozen=True)
class Bid:
    """One bidder's proposed design (an ADR-style approach), tagged by persona."""

    persona: str
    approach: str          # the design narrative (multivator's APPROACH.md)
    decisions: tuple[str, ...] = ()  # key ADR-style decisions, one per entry

    def text(self) -> str:
        return self.approach + "\n" + "\n".join(self.decisions)


class Outcome(str, Enum):
    PICK = "pick"            # one bid wins outright
    SYNTHESIZE = "synthesize"  # combine the best of several
    REJECT = "reject"        # none satisfies the intent; re-announce


@dataclass
class Verdict:
    outcome: Outcome
    scores: dict[str, float] = field(default_factory=dict)
    winner: str | None = None        # persona name when PICK
    rationale: str = ""
    synthesis: Bid | None = None     # the merged design when SYNTHESIZE

    @property
    def design(self) -> Bid | None:
        """The chosen design, if any (the winning or synthesized bid)."""
        if self.outcome is Outcome.SYNTHESIZE:
            return self.synthesis
        return None  # PICK's design is resolved by MarketResult, which holds the bids


@runtime_checkable
class Bidder(Protocol):
    persona: Persona

    def bid(self, brief: IntentBrief) -> Bid: ...


@runtime_checkable
class Judge(Protocol):
    def adjudicate(self, brief: IntentBrief, bids: list[Bid]) -> Verdict: ...


# A divergence metric returns dissimilarity in [0, 1]; 1 == maximally different.
DivergenceFn = Callable[[Bid, Bid], float]


def token_divergence(a: Bid, b: Bid) -> float:
    """Default metric: 1 - Jaccard similarity over lowercased word tokens.

    Cheap, dependency-free, and good enough to catch *convergence* (the failure
    we care about). A real deployment can swap in an embedding-based metric.
    """
    ta = _tokens(a.text())
    tb = _tokens(b.text())
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return 1.0 - (inter / union if union else 0.0)


def _tokens(text: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w}


class InsufficientDivergence(Exception):
    """Raised when bids are too similar to constitute a real competition.

    This is itself a signal: the personas collapsed onto one solution (common-mode),
    so the choice is not yet meaningfully contested.
    """

    def __init__(self, min_observed: float, threshold: float) -> None:
        self.min_observed = min_observed
        self.threshold = threshold
        super().__init__(
            f"bids diverged by only {min_observed:.2f} < required {threshold:.2f}; "
            "personas converged (common-mode) — no real competition"
        )


@dataclass
class MarketResult:
    brief: IntentBrief
    bids: list[Bid]
    verdict: Verdict
    min_divergence: float

    @property
    def chosen(self) -> Bid | None:
        """The design to carry forward, or None if the market rejected all bids."""
        v = self.verdict
        if v.outcome is Outcome.SYNTHESIZE:
            return v.synthesis
        if v.outcome is Outcome.PICK:
            return next((b for b in self.bids if b.persona == v.winner), None)
        return None


@dataclass
class BidMarket:
    """Runs persona-biased bidders against an intent and adjudicates the winner."""

    bidders: list[Bidder]
    judge: Judge
    min_divergence: float = 0.25
    divergence_fn: DivergenceFn = token_divergence
    enforce_divergence: bool = True

    def run(self, spec: Specification) -> MarketResult:
        if len(self.bidders) < 2:
            raise ValueError("a bidding market needs at least two bidders")

        brief = IntentBrief.from_spec(spec)
        bids = [bidder.bid(brief) for bidder in self.bidders]

        min_div = min(self.divergence_fn(a, b) for a, b in combinations(bids, 2))
        if self.enforce_divergence and min_div < self.min_divergence:
            raise InsufficientDivergence(min_div, self.min_divergence)

        verdict = self.judge.adjudicate(brief, bids)
        return MarketResult(brief, bids, verdict, min_div)
