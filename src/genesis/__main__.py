"""CLI entry point for Genesis.

Usage:
    python -m genesis plan <bookmark>     Run planner on a task
    python -m genesis build <bookmark>    Run builder on a task
    python -m genesis run <bookmark>      Run full planner→builder loop
    python -m genesis status              Show task statuses
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from genesis.config import load_config
from genesis.runner import GenesisRunner, HumanGateRequired


def _prompt_gate(gate_type: str, bookmark: str, detail: str) -> bool:
    """Interactive human gate — prompts on stdin."""
    print(f"\n{'=' * 60}")
    print(f"HUMAN GATE: {gate_type}")
    print(f"Task: {bookmark}")
    print(f"Detail: {detail}")
    print(f"{'=' * 60}")
    response = input("Approve? [y/N] ").strip().lower()
    return response in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="genesis", description="Genesis agent runner.")
    parser.add_argument(
        "--config", default="genesis.toml", help="Path to genesis.toml config."
    )
    parser.add_argument(
        "--auto-approve", action="store_true", help="Auto-approve all human gates."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")

    sub = parser.add_subparsers(dest="command")

    plan_cmd = sub.add_parser("plan", help="Run planner on a task.")
    plan_cmd.add_argument("bookmark", help="Task bookmark (e.g. #my-task).")

    build_cmd = sub.add_parser("build", help="Run builder on a task.")
    build_cmd.add_argument("bookmark", help="Task bookmark.")

    run_cmd = sub.add_parser("run", help="Run full planner→builder loop.")
    run_cmd.add_argument("bookmark", help="Task bookmark.")

    sub.add_parser("status", help="Show task statuses.")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not args.command:
        parser.print_help()
        return 1

    config = load_config(args.config)
    gate_handler = (lambda gt, bk, d: True) if args.auto_approve else _prompt_gate
    runner = GenesisRunner(config=config, gate_handler=gate_handler)

    if args.command == "status":
        statuses = runner.status()
        if not statuses:
            print("No tracked tasks.")
        for bk, st in statuses.items():
            print(f"  {bk}: {st}")
        return 0

    bookmark = args.bookmark
    if not bookmark.startswith("#"):
        bookmark = f"#{bookmark}"

    try:
        if args.command == "plan":
            summary = runner.run_planner(bookmark)
        elif args.command == "build":
            summary = runner.run_builder(bookmark)
        elif args.command == "run":
            summary = runner.run_task(bookmark)
        else:
            parser.print_help()
            return 1
    except HumanGateRequired as e:
        print(f"\nPaused at gate: {e.gate_type} for {e.bookmark}")
        print(f"Detail: {e.detail}")
        print("Re-run with --auto-approve or resume after review.")
        return 2

    print(f"\n{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
