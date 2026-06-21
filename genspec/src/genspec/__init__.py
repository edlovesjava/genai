"""genspec — specifications as first-class, validatable source of truth.

The spec is the code: the generated implementation is a disposable build
artifact, and this package owns the durable side of that relationship — the
model, the parser, and the validator that keep specs high-fidelity.
"""

from __future__ import annotations

from genspec.model import (
    Abstraction,
    Kind,
    Scenario,
    Section,
    Specification,
    Status,
    Step,
    StepKind,
)
from genspec.parser import SpecParseError, parse_file, parse_text
from genspec.validator import Diagnostic, Level, has_errors, validate, validate_all

__all__ = [
    "Abstraction",
    "Kind",
    "Scenario",
    "Section",
    "Specification",
    "Status",
    "Step",
    "StepKind",
    "SpecParseError",
    "parse_file",
    "parse_text",
    "Diagnostic",
    "Level",
    "validate",
    "validate_all",
    "has_errors",
]

__version__ = "0.1.0"
