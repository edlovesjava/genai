"""Personas — deliberate, contrasting stances that force divergence.

The common-mode failure of N-version generation is that two agents given the same
prompt converge on the same solution, so agreement carries little information.
The bidding paradigm answers this the way the *multivator* experiment did: assign
each bidder a distinct **persona** with opposing priorities, so the proposals
genuinely diverge and a judge has a real choice to make.

A ``Persona`` is just biasing material — a stance plus concrete directives — that
a real LLM bidder folds into its prompt. The two defaults mirror multivator's
Conservative/Experimental split.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """A named design temperament used to bias a bidder toward a corner of the
    design space."""

    name: str
    stance: str
    directives: tuple[str, ...]

    def brief_suffix(self) -> str:
        """Prompt fragment a real bidder appends to bias its proposal."""
        lines = [f"You are the '{self.name}' designer. {self.stance}", "Directives:"]
        lines += [f"- {d}" for d in self.directives]
        return "\n".join(lines)


# "Steady Eddie": reliability over novelty — the multivator Conservative track.
STEADY_EDDIE = Persona(
    name="steady-eddie",
    stance="Favor reliability, simplicity, and proven patterns over novelty.",
    directives=(
        "Minimize dependencies; prefer the standard library.",
        "Write explicit, obvious code over clever abstractions.",
        "Choose defensive, well-understood patterns with low operational risk.",
        "Optimize for maintainability and ease of review.",
    ),
)

# "Innovator": novelty and performance — the multivator Experimental track.
INNOVATOR = Persona(
    name="innovator",
    stance="Favor performance, modern techniques, and bold structural bets.",
    directives=(
        "Prefer the most capable tool even if it adds a dependency.",
        "Use modern patterns and abstractions that reduce code over the long run.",
        "Optimize for performance and expressiveness.",
        "Take a structural risk if it materially improves the design.",
    ),
)

DEFAULT_PERSONAS: tuple[Persona, Persona] = (STEADY_EDDIE, INNOVATOR)
