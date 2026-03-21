# Genesis SDLC Process Flow

**Version:** 0.1.0
**Philosophy:** Build the car while driving it. Fail fast, fix fast.

---

## The V-Model Flow

Every piece of work follows this trace, whether done by a human or an agent:

```
Specification          Acceptance
    \                    /
     Design        Verification
        \            /
      Implementation
```

**Left side (build):** Spec → Design → Implementation
**Right side (verify):** Each build artifact has a paired verification:
- Specification ↔ Acceptance (does the delivered thing match what was asked?)
- Design ↔ Verification (does the code match the design?)
- Implementation ↔ Unit Tests (does each piece work correctly?)

---

## Process Phases

### Phase 0: Specification
**Input:** Problem statement, user need, or improvement idea
**Output:** A spec entry (section in bootstrap-spec.md or standalone spec doc)
**Validation:** Spec is reviewable — another person/agent can read it and understand what "done" looks like

### Phase 1: Design
**Input:** Approved specification
**Output:** Design document in `docs/plans/`
**Validation:** Design is reviewable — covers tech stack, components, interfaces, NFRs, risks
**Template:** `docs/templates/design-template.md`

### Phase 2: Implementation Planning
**Input:** Approved design
**Output:** Implementation plan in `docs/plans/` + tasks in `TASKS.md`
**Validation:** Plan decomposes into iterations where each iteration is independently testable
**Template:** `docs/templates/implementation-plan-template.md`

### Phase 3: Implementation
**Input:** Task from TASKS.md with linked design and plan
**Output:** Code + tests on a feature branch
**Validation:** Tests pass, code review approved

### Phase 4: Verification
**Input:** Implementation + test results
**Output:** PR approved, merged to main
**Validation:** CI green, human sign-off

### Phase 5: Acceptance
**Input:** Merged code
**Output:** Task marked DONE, spec acceptance criteria verified
**Validation:** End-to-end behavior matches spec

---

## Feedback Loops

### Loop 1: Red/Green/Refactor (Minutes)
- Write a test (red)
- Make it pass (green)
- Clean up (refactor)
- **Signal:** Test runner output — immediate pass/fail

### Loop 2: Iteration Validation (Hours)
- Complete an iteration's tasks
- Run the iteration's acceptance criteria
- **Signal:** All iteration tests pass + manual smoke test
- **Fail fast:** If an iteration can't be validated, stop and reassess design

### Loop 3: Design Review (Days)
- Design doc reviewed before implementation starts
- **Signal:** Human approval on design doc
- **Fail fast:** Rejected design → revise before any code is written

### Loop 4: End-to-End Loop Proof (Milestone)
- Full spec §2 loop completes: task → plan → build → test → review → merge → done
- **Signal:** One real quick-task improvement delivered through the system
- **Fail fast:** If the loop can't complete, the kernel hypothesis needs revision

---

## Decision Log

All significant decisions are recorded with:
- **What** was decided
- **Why** (context and alternatives considered)
- **When** (date)
- **Reversibility** (easy/hard to change later)

Decisions live in the message bus as `decision` events and are summarized in design docs.

---

## Working Agreements

1. **No code without a linked task.** Every change traces to a TASKS.md entry.
2. **No task without a spec reference.** Every task traces to a spec section or design doc.
3. **Tests before merge.** No PR merges without passing tests.
4. **BLOCKED is safe.** When stuck, transition to BLOCKED rather than guessing.
5. **Human gates are non-negotiable in bootstrap.** Agents cannot merge, push to main, or modify CI.
6. **Update the process.** When we learn something, update these docs. The process is a living artifact.
