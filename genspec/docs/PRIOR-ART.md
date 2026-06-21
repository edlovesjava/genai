# Prior Art & Differentiation

> Purpose: situate genspec against existing work so we can decide where to
> **focus** (defensible differentiation), where to **adopt** (solved elsewhere,
> don't reinvent), and where to **pivot** (someone already owns it better).
>
> Status: living document. Last surveyed 2026-06.

genspec's thesis — *the spec is the source of truth; generated code is a
disposable build artifact, the way machine code is to a 3GL* — is **not novel in
isolation**. A current commercial tool (Tessl) ships almost this exact framing,
two large vendors (GitHub, Amazon) ship adjacent products, and nearly every
component idea has decades of lineage. The interesting question is therefore not
"is this new?" but "**what, specifically, is ours to own?**" This document answers
that.

---

## 1. The current wave: spec-driven AI development (2024–2025)

genspec is recognizably the same species as three tools that define the moment.

### Tessl — closest to our thesis
Tessl's "AI-Native / spec-centric development" is, almost verbatim, genspec's
pitch: *the spec is the source of truth, implementations are regenerated as specs
evolve, tests are bound to spec assertions,* and *"comprehensive specs and tests
make the code disposable — regenerate it whenever needed."* They run a spec
**registry** and a framework around this.
→ Implication: **the disposable-code / spec-as-truth high ground is already
claimed.** We should not position genspec as "the first to make code disposable."

### GitHub Spec Kit — the process spine
`Spec → Plan → Tasks → Implement`, each phase a markdown artifact feeding the
next; the spec is "the source of truth for tools and AI agents to generate, test,
and validate code." Templates + CLI + prompts, 30+ agent integrations.
→ Implication: the **workflow/CLI surface is commoditized and open-source.**
Competing on "a nicer spec→tasks pipeline" is a losing battle.

### Amazon Kiro — the IDE incumbent
An AI IDE (powered by Claude) that generates a structured `spec.md` (user stories
+ EARS-style acceptance criteria, a design doc with Mermaid diagrams, then
trackable tasks) before writing code. Backed by AWS distribution.
→ Implication: **don't compete on IDE/UX or breadth.** Vendor distribution wins
that.

Martin Fowler's team has a comparative analysis of all three (see Sources).

**What these three mostly do NOT do** (our opening):
- Their specs are **prose templates**, not **mechanically validatable** artifacts.
- Generation is a **one-shot scaffold**, not an **iterative typecheck** that
  localizes faults to *spec vs code*.
- They do not treat **independent re-derivation** as a correctness oracle.

---

## 2. Deeper traditions each genspec component draws on

Every building block has prior art. Knowing the lineage tells us what's textbook
(adopt) vs genuinely combinable (focus).

| genspec choice | Prior art | Verdict |
|---|---|---|
| `abstraction: model` vs `implementation` | **Model-Driven Architecture** (OMG MDA/MDE): PIM vs PSM; "never edit generated code" | Adopt the discipline; nothing to invent |
| `Given/When/Then` scenarios | **BDD / Gherkin / Cucumber** (North, Hellesøy); **Specification by Example** & living documentation (Adzic); **ATDD / FIT** (Cunningham) | Adopt the syntax outright; consider Gherkin-compat |
| Spec as *source of validation* | **Formal methods**: TLA+ (Lamport), Alloy, Z/VDM/B; **Design by Contract** (Meyer/Eiffel) | Our validator is shallow vs these — a **focus** area (see §4) |
| Spec → code/tests, code disposable | **OpenAPI**, **Protocol Buffers / IDL** codegen, declarative **Infrastructure-as-Code** | Everyday prior art for "schema is source, stubs regenerated" |
| `format.spec.md` in its own format | **Self-hosting / metacircular** bootstrapping; **literate programming** (Knuth) | Nice property, not a moat |
| verification vs validation kept distinct | **Boehm's V&V** ("build the product right" vs "build the right product"); the **V-Model** Genesis already uses | Our framing is correct and worth keeping explicit |

---

## 3. The freshest twist — and its prior art (with a real caveat)

The most distinctive mechanism is **independent re-derivation as a spec-fault
oracle**: a Test-Author and a Coder derive from the same spec *without seeing each
other's output*; agreement is evidence the spec is unambiguous, and disagreement
that cannot be reconciled is flagged as a spec fault.

**Prior art:** this is **N-version programming** (Chen & Avizienis, 1977) ported
to LLM code generation — independently produce N versions from one spec, compare,
treat divergence as a fault signal. It also formalizes the old TDD intuition of
tests and code as "double-entry bookkeeping."

**The caveat that must shape our claims.** NVP's own empirical history is a
warning: Knight & Leveson showed that *independently developed versions still
exhibit correlated ("common-mode") failures*. For LLM agents this is **worse**,
not better — two agents share training data, tokenizers, and inductive biases, so
they are far from independent. Therefore:

- **Agreement is weaker evidence than the NVP voter model assumes.** Two agents
  can be *consistently wrong*. This is precisely why genspec keeps the human
  acceptance gate even on agreement, and why a spec fault *escalates* rather than
  auto-resolving. Keep this non-negotiable.
- **Disagreement is the more trustworthy signal** (a divergence almost always
  indicates real spec ambiguity), so genspec's value leans on the *negative*
  result more than the positive one. Worth stating plainly.

---

## 4. Where to focus — candidate axes of differentiation

Ordered by defensibility. These are hypotheses for the pivot/focus discussion,
not commitments.

1. **Mechanically validatable specs (the formal-methods bridge).**
   Spec Kit / Kiro / Tessl specs are largely prose. genspec already parses specs
   into a typed model and validates structure + source-anchoring. The open lane is
   to push *toward formal methods without their cost*: machine-checkable
   invariants, cross-spec consistency, contract/property extraction, coverage of
   scenarios over the structural surface. "Lint + typecheck for specs" is a real,
   underserved niche.

2. **Generation-as-typecheck with fault localization (spec vs code vs test).**
   Others scaffold; genspec *diagnoses*. The disposition lattice (`INVALID` →
   `VALIDATED` → `RECONCILED` → `SPEC_SUSPECT`) that pins a failure to a **layer**
   is unusual and useful. Deepening this — better classification, minimized
   counter-examples that show *why* the spec is ambiguous — is differentiated.

3. **Independent-agent oracle, done honestly.**
   Lean into the N-version framing *with* the common-mode caveat as a feature:
   deliberately **decorrelate** the agents (different models, prompts, temperatures,
   even providers) to make agreement meaningful, and quantify confidence rather
   than asserting it. Nobody in the SDD wave is doing rigorous independence.

4. **Native to a governed kernel (gates, state machine, audit bus).**
   genspec rides Genesis's human gates, six-state lifecycle, and append-only
   message bus. The SDD tools are largely ungoverned "generate and hope." A
   **traceable, gated, auditable** spec→code pipeline (V-Model provenance from
   spec assertion → test → code → review) is a credible enterprise wedge.

5. **Reverse-spec of existing code (brownfield).**
   genspec already demonstrates describing *shipped* code (`state-machine.spec.md`).
   Most SDD tooling is greenfield-first. "Specify the system you already have, then
   regenerate it safely" is a harder, stickier problem.

### Where NOT to compete (adopt or cede)
- The **spec→plan→tasks workflow and CLI** — commoditized by Spec Kit (OSS).
- **IDE / UX / agent breadth** — Kiro (AWS) and Spec Kit's 30+ integrations win.
- **The disposable-code narrative** — Tessl owns the mindshare; we differentiate
  on *rigor*, not slogan.
- **Gherkin syntax** — adopt it (or stay compatible), don't invent a rival.

---

## 5. One-line positioning hypotheses (to test)

- "**A typechecker for specifications**" — validatable specs + generation that
  fails the spec early, with fault localization. (Leans on §4.1–4.2.)
- "**Governed spec-to-code**" — the only spec-driven pipeline with gates, state,
  and an audit trail built in. (Leans on §4.4.)
- "**Honest N-version generation**" — independence you can actually trust, with
  confidence instead of hand-waving. (Leans on §4.3.)

The first is the most defensible and closest to what genspec already is.

---

## Sources

- GitHub Spec Kit — <https://github.com/github/spec-kit> · spec-driven.md:
  <https://github.com/github/spec-kit/blob/main/spec-driven.md>
- Tessl, "From Code-Centric to Spec-Centric" —
  <https://tessl.io/blog/from-code-centric-to-spec-centric/> · "How Tessl's
  products pioneer SDD" —
  <https://tessl.io/blog/how-tessls-products-pioneer-spec-driven-development/>
- Martin Fowler, "Understanding Spec-Driven Development: Kiro, spec-kit, and
  Tessl" — <https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html>
- Amazon Kiro — <https://kiro.dev/blog/introducing-kiro/> · InfoQ coverage —
  <https://www.infoq.com/news/2025/08/aws-kiro-spec-driven-agent/>
- N-version programming (overview & critique) —
  <https://en.wikipedia.org/wiki/N-version_programming>
- Background traditions (textbook, no link needed): OMG MDA/MDE; Gherkin/Cucumber
  (BDD); Adzic, *Specification by Example*; Lamport, *TLA+*; Meyer, *Design by
  Contract*; Knight & Leveson (1986), common-mode failures in N-version software;
  Boehm, verification vs validation.
