"""Mock dispatcher for build-evals harness.

Read canned subagent return receipts and mock user-input turns from disk.
Used by build's Mock Dispatch Mode (in SKILL.md) when CRUCIBLE_BUILD_EVAL_MOCK_DIR
is set in the environment.
"""
from __future__ import annotations

from pathlib import Path


class MockNotFound(Exception):
    pass


class MockUserInputMissing(Exception):
    pass


def load(mock_dir: Path, seq: int, template_name: str) -> str:
    """Return the mock dispatch content for a given (seq, template_name) pair.

    Lookup order:
        1. <seq>-<template_name>.md
        2. <template_name>.md   (fallback when the orchestrator dispatched a different number of times)

    Raises MockNotFound if neither file exists.
    """
    mock_dir = Path(mock_dir)
    primary = mock_dir / f"{seq}-{template_name}.md"
    if primary.exists():
        return primary.read_text()
    fallback = mock_dir / f"{template_name}.md"
    if fallback.exists():
        return fallback.read_text()
    raise MockNotFound(
        f"no mock for seq={seq}, template={template_name!r} in {mock_dir} "
        f"(tried {primary.name} and {fallback.name})"
    )


def load_user_input(mock_user_input_dir: Path | None, turn_n: int) -> str:
    """Return the canned user input for turn N.

    Raises MockUserInputMissing when the directory is None or turn-<N>.md is absent.
    This exception, when raised inside build's process, causes build to halt for input —
    which is the b4 fixture's PASS signal (detected by the harness via absent on-disk
    artifacts, not by catching this exception across a process boundary).
    """
    if mock_user_input_dir is None:
        raise MockUserInputMissing(f"no mock user-input dir; cannot fetch turn-{turn_n}")
    mock_user_input_dir = Path(mock_user_input_dir)
    f = mock_user_input_dir / f"turn-{turn_n}.md"
    if not f.exists():
        raise MockUserInputMissing(f"missing turn-{turn_n}.md in {mock_user_input_dir}")
    return f.read_text()
