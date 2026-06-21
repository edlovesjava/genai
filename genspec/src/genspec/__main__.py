"""genspec CLI: ``show`` a spec's model, or ``validate`` a spec library.

    python -m genspec show specs/state-machine.spec.md
    python -m genspec validate specs/ [--root DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from genspec.model import Specification
from genspec.parser import SpecParseError, parse_file
from genspec.validator import Level, validate_all


def _iter_spec_paths(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.extend(sorted(p.rglob("*.spec.md")))
        else:
            found.append(p)
    return found


def _load(paths: list[Path]) -> tuple[list[Specification], int]:
    specs: list[Specification] = []
    errors = 0
    for p in paths:
        try:
            specs.append(parse_file(p))
        except (SpecParseError, OSError) as exc:
            print(f"ERROR   could not parse {p}: {exc}", file=sys.stderr)
            errors += 1
    return specs, errors


def _cmd_show(args: argparse.Namespace) -> int:
    specs, parse_errors = _load(_iter_spec_paths(args.paths))
    for spec in specs:
        print(f"# {spec.title}  ({spec.id})")
        print(f"  status={spec.status.value}  abstraction={spec.abstraction.value}")
        if spec.source:
            print(f"  source: {', '.join(spec.source)}")
        if spec.depends:
            print(f"  depends: {', '.join(spec.depends)}")
        for name, section in spec.sections.items():
            line = f"  ## {name}"
            if section.scenarios:
                line += f"  ({len(section.scenarios)} scenario(s))"
            print(line)
            for sc in section.scenarios:
                kinds = "/".join(sorted(k.value for k in sc.kinds()))
                print(f"     - {sc.name}  [{kinds}]")
        print()
    return 1 if parse_errors else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    paths = _iter_spec_paths(args.paths)
    if not paths:
        print("no .spec.md files found", file=sys.stderr)
        return 1
    specs, parse_errors = _load(paths)

    diags = validate_all(specs, root=args.root)
    for diag in diags:
        stream = sys.stderr if diag.level is Level.ERROR else sys.stdout
        print(diag, file=stream)

    n_errors = sum(1 for d in diags if d.level is Level.ERROR) + parse_errors
    n_warnings = sum(1 for d in diags if d.level is Level.WARNING)
    print(
        f"\nchecked {len(specs)} spec(s): {n_errors} error(s), {n_warnings} warning(s)"
    )
    return 1 if n_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="genspec", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="parse specs and print their model")
    p_show.add_argument("paths", nargs="+", help="spec files or directories")
    p_show.set_defaults(func=_cmd_show)

    p_val = sub.add_parser("validate", help="validate specs and report diagnostics")
    p_val.add_argument("paths", nargs="+", help="spec files or directories")
    p_val.add_argument(
        "--root",
        default=None,
        help="base dir for resolving source: paths (default: each spec's own dir)",
    )
    p_val.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
