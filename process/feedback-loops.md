# Feedback Loops: How We Know Right From Wrong

**Principle:** Every action should produce a signal. If you can't tell whether something worked, you're flying blind.

---

## Feedback Loop Inventory

### Immediate (Seconds to Minutes)

| Signal | Source | What It Tells You | Action on Failure |
|:---|:---|:---|:---|
| **Syntax check** | Python/ruff | Code is valid | Fix before committing |
| **Unit test** | pytest | Component works in isolation | Fix the code or fix the test |
| **Type check** | Type annotations + runtime | Interfaces match | Fix the interface |
| **Lint** | ruff | Code meets style standards | Auto-fix or manual fix |

### Short-cycle (Minutes to Hours)

| Signal | Source | What It Tells You | Action on Failure |
|:---|:---|:---|:---|
| **Integration test** | pytest (integration suite) | Components work together | Investigate interaction, fix |
| **CI pipeline** | GitHub Actions | Code works in clean environment | Fix env-specific issues |
| **Agent output validation** | Schema check on LLM response | Agent produced usable output | Re-prompt or BLOCKED |
| **Token budget check** | Usage counter | Agent is within cost limits | Checkpoint + BLOCKED |

### Medium-cycle (Hours to Days)

| Signal | Source | What It Tells You | Action on Failure |
|:---|:---|:---|:---|
| **Design review** | Human review of design doc | Approach is sound before building | Revise design |
| **PR review** | Human review of code | Implementation is correct and clean | Address feedback |
| **Iteration acceptance** | Run iteration criteria | Iteration delivers what was planned | Reassess scope or approach |

### Long-cycle (Days to Weeks)

| Signal | Source | What It Tells You | Action on Failure |
|:---|:---|:---|:---|
| **End-to-end loop** | Full task lifecycle completes | The kernel works | Revisit architecture |
| **Agent autonomy %** | Human intervention count | Agents are reliable | Improve prompts, tools, or guards |
| **Dogfooding quality** | Using quick-task improvements | Improvements actually help | Reprioritize backlog |

---

## Fail-Fast Rules

1. **If a test fails, stop and fix it.** Don't accumulate broken tests.
2. **If an agent produces garbage twice, BLOCK the task.** Don't burn tokens retrying.
3. **If a design is rejected, don't start coding.** Redesign first.
4. **If an iteration can't be validated, don't start the next one.** Fix the foundation.
5. **If the end-to-end loop fails, question the architecture.** Not just the code.

---

## Metrics We Track

### Bootstrap Phase Metrics

| Metric | Target | How Measured |
|:---|:---|:---|
| **Test pass rate** | 100% on merge | CI results |
| **Code coverage** | >80% kernel code | pytest-cov |
| **Agent success rate** | >70% tasks complete without BLOCKED | Message bus events |
| **Token cost per task** | <$5 for routine tasks | Budget tracker |
| **Human interventions per task** | ≤3 (gates only) | Message bus events |
| **Time from TODO to DONE** | Decreasing trend | Task history timestamps |

---

## Anti-Patterns to Watch For

| Anti-Pattern | Signal | Correction |
|:---|:---|:---|
| **Silent failure** | No BLOCKED transition, task just stalls | Add timeout detection, enforce BLOCKED |
| **Retry storm** | Agent retries same failing approach | Lower retry limits, require strategy change |
| **Context bloat** | Agent gets confused by too much context | Tighten context manager, improve focus |
| **Gold plating** | Agent over-engineers beyond spec | Constrain in system prompt, review scope |
| **Specification drift** | Code doesn't match spec | Trace every PR to spec section |
| **Process theater** | Process docs exist but aren't followed | Automate checks, make process the path of least resistance |
