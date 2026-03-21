# Design Document: [Feature/Component Name]

**Version:** 0.1.0
**Date:** YYYY-MM-DD
**Status:** Draft | Review | Approved
**Spec Reference:** [Link to spec section or document]
**Author:** [human | planner-agent]

---

## 1. Overview

One paragraph: what is being built and why. Reference the spec.

## 2. Tech Stack / Dependencies

| Component | Choice | Rationale |
|:---|:---|:---|
| ... | ... | ... |

## 3. Architecture / Structure

How components are organized. Include directory layout if relevant.

## 4. Component Design

### 4.1 [Component Name]

**Responsibility:** What it does
**Interface:**
```python
class ComponentName:
    def method(self, param: Type) -> ReturnType:
        """What this does."""
```
**Design decisions:** Why this approach over alternatives.

### 4.2 [Component Name]
...

## 5. Data Flow

How data moves through the system. A simple diagram or step list:

```
Input → Component A → Component B → Output
```

## 6. Interfaces / Contracts

Key interfaces between components. What each component expects and provides.

## 7. Non-Functional Requirements

### Testability
How each component will be tested.

### Observability
How to see what's happening at runtime.

### Error Handling
How failures are detected and recovered.

## 8. Risks

| Risk | Impact | Mitigation |
|:---|:---|:---|
| ... | ... | ... |

## 9. Explicit Non-Goals

What this design intentionally does NOT do.

---

## Quality Checklist (for reviewers)

- [ ] Design traces to spec requirements
- [ ] Components have clear responsibilities (no god objects)
- [ ] Interfaces are defined before implementation details
- [ ] Error cases are handled (not just happy path)
- [ ] Testability is addressed (can each component be tested in isolation?)
- [ ] Risks are identified with mitigations
- [ ] Non-goals are explicit (prevents scope creep)
