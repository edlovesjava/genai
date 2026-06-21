"""Tests for the genspec parser and validator.

These exercise the format end to end and confirm the shipped example specs are
both parseable and valid — including that they stay anchored to real code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from genspec import (
    Abstraction,
    Status,
    StepKind,
    parse_file,
    parse_text,
    validate,
    validate_all,
)
from genspec.parser import SpecParseError
from genspec.validator import Level, has_errors

SPECS_DIR = Path(__file__).resolve().parent.parent / "specs"

WELL_FORMED = """\
---
id: example.thing
title: Example Thing
status: active
abstraction: model
source: [a.py, b.py]
depends:
  - other.spec
---

# Example Thing

## Intent
Do a thing well.

## Structure
A component named Thing.

## Behavior

### Scenario: it does the thing
Given a Thing
When the thing is invoked
Then the outcome holds
And a further outcome holds

## Qualities
Fast and safe.

## Validation
Covered by tests.
"""


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_parse_frontmatter_fields():
    spec = parse_text(WELL_FORMED)
    assert spec.id == "example.thing"
    assert spec.title == "Example Thing"
    assert spec.status is Status.ACTIVE
    assert spec.abstraction is Abstraction.MODEL
    assert spec.source == ["a.py", "b.py"]
    assert spec.depends == ["other.spec"]


def test_parse_sections_present():
    spec = parse_text(WELL_FORMED)
    assert set(spec.sections) >= {
        "intent",
        "structure",
        "behavior",
        "qualities",
        "validation",
    }
    assert spec.section("intent").body == "Do a thing well."


def test_parse_scenarios_and_steps():
    spec = parse_text(WELL_FORMED)
    scenarios = spec.scenarios
    assert len(scenarios) == 1
    sc = scenarios[0]
    assert sc.name == "it does the thing"
    assert [s.kind for s in sc.steps] == [
        StepKind.GIVEN,
        StepKind.WHEN,
        StepKind.THEN,
        StepKind.AND,
    ]
    # 'And' resolves to the preceding kind (THEN).
    assert sc.kinds() == {StepKind.GIVEN, StepKind.WHEN, StepKind.THEN}


def test_inline_and_block_lists_equivalent():
    inline = parse_text(WELL_FORMED.replace("depends:\n  - other.spec", "depends: [other.spec]"))
    assert inline.depends == ["other.spec"]


def test_missing_id_raises():
    with pytest.raises(SpecParseError):
        parse_text("---\ntitle: No Id\n---\n\n# No Id\n")


def test_unknown_enum_falls_back_to_default():
    spec = parse_text(WELL_FORMED.replace("status: active", "status: bogus"))
    assert spec.status is Status.DRAFT


def test_document_without_frontmatter_is_recoverable():
    # No frontmatter -> no id -> parse error (id is mandatory).
    with pytest.raises(SpecParseError):
        parse_text("# Just a title\n\n## Intent\nstuff\n")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_well_formed_spec_validates_clean(tmp_path):
    # Anchor the source files so the anchoring check passes.
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    spec = parse_text(WELL_FORMED)
    diags = validate(spec, root=tmp_path)
    assert not has_errors(diags), [str(d) for d in diags]


def test_missing_section_is_error():
    text = WELL_FORMED.replace("## Qualities\nFast and safe.\n\n", "")
    spec = parse_text(text)
    diags = validate(spec, root=Path("/"))
    msgs = [d.message for d in diags if d.level is Level.ERROR]
    assert any("qualities" in m for m in msgs)


def test_incomplete_scenario_is_error():
    text = WELL_FORMED.replace("Then the outcome holds\n", "")
    spec = parse_text(text)
    diags = validate(spec, root=Path("/"))
    assert any(
        d.level is Level.ERROR and "missing clause" in d.message for d in diags
    )


def test_missing_source_is_error(tmp_path):
    spec = parse_text(WELL_FORMED)  # a.py / b.py do not exist under tmp_path
    diags = validate(spec, root=tmp_path)
    assert any(
        d.level is Level.ERROR and "not anchored" in d.message for d in diags
    )


def test_unresolved_dependency_is_error(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    spec = parse_text(WELL_FORMED)  # depends on 'other.spec', not in the set
    diags = validate_all([spec], root=tmp_path)
    assert any("unknown spec" in d.message for d in diags)


def test_duplicate_ids_detected(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    s1 = parse_text(WELL_FORMED)
    s2 = parse_text(WELL_FORMED)
    diags = validate_all([s1, s2], root=tmp_path)
    assert any("duplicate spec id" in d.message for d in diags)


# --------------------------------------------------------------------------- #
# The shipped example specs must be valid
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("spec_path", sorted(SPECS_DIR.glob("*.spec.md")))
def test_shipped_specs_parse_and_validate(spec_path):
    spec = parse_file(spec_path)
    diags = validate(spec)  # root defaults to the spec's own directory
    errors = [str(d) for d in diags if d.level is Level.ERROR]
    assert not errors, errors
