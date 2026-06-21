---
id: genspec.format
title: The genspec Specification Format
status: active
abstraction: model
source: [../src/genspec/parser.py, ../src/genspec/validator.py, ../src/genspec/model.py]
depends: []
---

# The genspec Specification Format

This document specifies the genspec format *in its own format* — it is
self-hosting. Reading it is the fastest way to learn what a valid spec looks
like, and validating it exercises the very rules it describes.

## Intent

Define a single, human-readable but semi-structured document format that can
serve as the durable source of truth for a software system. The format must be
comprehensive enough to determine an implementation, structured enough to be
mechanically validated, and uniform whether it describes existing code or plans
a new feature.

Out of scope: the *generator* that lowers a spec into source code. This format
defines the source artifact; lowering it is a separate concern.

## Structure

A specification is a UTF-8 markdown file named `*.spec.md` with two parts:

1. **Frontmatter** — a `---`-delimited block of `key: value` metadata:
   - `id` *(required)* — a stable dotted identifier, unique within a library.
   - `title` — human-readable name; defaults to `id`.
   - `status` — `draft` | `active` | `deprecated`.
   - `abstraction` — `model` (durable design) | `implementation` (bound to one
     realization).
   - `source` — list of files this spec describes, as inline `[a, b]` or a block
     list. The anchor that ties the spec to real code.
   - `depends` — list of other spec `id`s this spec builds upon.
2. **Body** — markdown organized into five canonical `##` sections, in order:
   `Intent`, `Structure`, `Behavior`, `Qualities`, `Validation`.

Each section maps to a dimension of the model: Intent is functional purpose,
Structure is structural, Behavior is behavioral, Qualities is non-functional,
and Validation closes the traceability loop.

## Behavior

### Scenario: parsing a well-formed spec
Given a `*.spec.md` file with frontmatter declaring an `id`
When the parser reads the file
Then it returns a `Specification` whose fields mirror the frontmatter
And each `##` heading becomes a section keyed by its lowercased name

### Scenario: behavioral scenarios are extracted
Given a `## Behavior` section containing `### Scenario:` blocks
When the parser processes that section
Then each scenario is captured with its ordered Given/When/Then steps
And an `And` clause continues the kind of the clause before it

### Scenario: a spec missing an id is rejected
Given a document whose frontmatter has no `id`
When the parser attempts to parse it
Then a `SpecParseError` is raised

### Scenario: an incomplete scenario fails validation
Given a spec whose scenario has a `Given` and a `When` but no `Then`
When the validator checks the spec
Then it emits an error diagnostic naming the missing clause

## Qualities

- **Zero runtime dependencies** — the reader is hand-written so specs stay
  portable and the format stays inspectable.
- **Lossless** — section bodies preserve the author's raw markdown verbatim.
- **Tolerant input, strict validation** — parsing accepts case-insensitive
  headings and `- ` list-style steps; conformance is enforced by the validator,
  not the parser, so partial drafts still load.
- **Order is meaningful** — the canonical section order is the reading order.

## Validation

- `python -m genspec validate specs/` parses this file and reports zero errors.
- The required-section check confirms all five canonical sections are present
  and non-empty.
- The source-anchoring check confirms every path in `source:` exists relative to
  this document's directory.
- `tests/test_genspec.py` round-trips this document through parse → validate.
