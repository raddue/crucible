"""Pilot tasks for the minimalism-ladder eval.

A `Task` bundles a prompt (what a live codegen step would be asked to build in
Phase 2), a fixed entry module (`solution.py`), and a list of `Assertion`s the
generated solution must satisfy. Each assertion's `check` is called with the
imported solution module and either returns `None` (pass) or raises (fail) — the
scorer counts ANY exception escaping a check as a FAIL.

Carve-out assertions (`carve_out=True`) are the eval's quality anchor: absolute
behaviours a minimal-but-correct solution must keep (input validation / safety
guards) so the ladder cannot "win" by deleting them. A carve-out check that
asserts a REJECTION must catch the expected exception INTERNALLY and raise only
when the rejection did NOT occur — otherwise the expected exception would escape
and be miscounted as a carve-out failure against a correct solution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

ENTRY_MODULE = "solution.py"


@dataclass(frozen=True)
class Assertion:
    name: str
    check: Callable[[object], None]  # raises on fail, returns None on pass
    carve_out: bool = False


@dataclass(frozen=True)
class Task:
    name: str
    prompt: str
    entry_module: str
    assertions: list[Assertion] = field(default_factory=list)

    @property
    def carve_out_assertions(self) -> list[Assertion]:
        return [a for a in self.assertions if a.carve_out]


# Imported after the model classes are defined so the submodules can
# `from tasks import Assertion, Task` without a circular-import failure.
from . import cli_wordcount, fixture_loader  # noqa: E402

TASKS: dict[str, Task] = {
    cli_wordcount.TASK.name: cli_wordcount.TASK,
    fixture_loader.TASK.name: fixture_loader.TASK,
}


def load_task(name: str) -> Task:
    try:
        return TASKS[name]
    except KeyError:
        raise KeyError(f"unknown task: {name!r}") from None
