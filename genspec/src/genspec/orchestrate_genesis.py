"""Wire a :class:`~genspec.orchestrate.SpecRunner` onto real Genesis primitives.

This is the only module that imports Genesis. It is kept separate (and imports
lazily) so that the rest of genspec installs and tests without Genesis or its
``quick_task`` dependency present. In a full Genesis kernel — where
``quick_task`` and ``genesis`` are installed — this builds a SpecRunner backed by
the kernel's file message bus and six-state task machine.

Each spec is tracked as a task whose bookmark is the spec id, so a spec's
lifecycle shows up in ``TASKS.md`` and the bus exactly like any other Genesis
task. Generation events are published as Genesis ``Message`` files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from genspec.generate.loop import Generator
from genspec.orchestrate import Emit, SpecRunner


def build_spec_runner(
    generator: Generator,
    *,
    task_file: str | Path,
    messages_dir: str | Path,
    output_dir: str | Path,
    gate_handler: Callable[[str, str, str], bool] | None = None,
    actor: str = "genspec",
) -> SpecRunner:
    """Construct a SpecRunner backed by Genesis's ``MessageBus`` + ``StateMachine``.

    Raises a clear error if Genesis (and its ``quick_task`` dependency) is not
    installed in the current environment.
    """
    try:
        from genesis.bus.message_bus import Message, MessageBus
        from genesis.state.machine import StateMachine
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "genspec.orchestrate_genesis requires the 'genesis' package (and its "
            "'quick_task' dependency) to be installed. Install Genesis, or use a "
            "standalone Lifecycle/Emit with genspec.orchestrate.SpecRunner directly."
        ) from exc

    bus = MessageBus(Path(messages_dir))
    state_machine = StateMachine(bus, str(task_file))

    def emit(event: str, spec_id: str, payload: dict) -> None:
        bus.publish(
            Message.create(agent=actor, event=event, task_bookmark=spec_id, payload=payload)
        )

    return SpecRunner(
        generator=generator,
        lifecycle=state_machine,
        output_dir=Path(output_dir),
        emit=emit,
        gate_handler=gate_handler,
        actor=actor,
    )


__all__ = ["build_spec_runner", "Emit"]
