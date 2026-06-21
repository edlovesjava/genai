"""Conformance: run the generated tests against the generated code.

Static validation proves a spec is internally consistent; conformance questions
reality — does the independently-generated code actually satisfy the
independently-generated tests? The two were derived from the same spec without
seeing each other, so the result is meaningful:

* **pass** — the two interpretations agree; evidence the spec is well-determined.
* **fail** — they disagree; a candidate spec fault (or a code gap to reconcile).

The runner is a Protocol so the orchestration is testable without spawning
processes. ``PytestRunner`` is the real implementation: it materializes both
artifacts in a temp package and runs pytest.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from speckit.generate.agents import Artifact


@dataclass(frozen=True)
class ConformanceResult:
    passed: bool
    output: str
    exit_code: int


class Runner(Protocol):
    """Runs a test artifact against a code artifact and reports conformance."""

    def run(self, code: Artifact, tests: Artifact) -> ConformanceResult: ...


class PytestRunner:
    """Materialize code + tests in an isolated temp dir and run pytest.

    The test module imports the code module by ``module_name``, so the two
    artifacts must agree on that name — the only contract shared between the
    otherwise-independent agents.
    """

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def run(self, code: Artifact, tests: Artifact) -> ConformanceResult:
        with tempfile.TemporaryDirectory(prefix="speckit-conf-") as tmp:
            root = Path(tmp)
            (root / f"{code.module_name}.py").write_text(code.source, encoding="utf-8")
            (root / f"test_{code.module_name}.py").write_text(tests.source, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", str(root)],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as exc:
                return ConformanceResult(
                    passed=False,
                    output=f"timed out after {self.timeout}s\n{exc.stdout or ''}",
                    exit_code=-1,
                )
            output = (proc.stdout or "") + (proc.stderr or "")
            return ConformanceResult(passed=proc.returncode == 0, output=output, exit_code=proc.returncode)
