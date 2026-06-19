"""Non-test source LOC counter — the minimalism-ladder headline metric.

Deliberately a simple line counter (no AST / string-literal parsing): a line
counts iff, after strip(), it is non-empty and does not start with `#`. This
coarseness (a "# ..." inside a string literal still counts; a trailing inline
comment still counts) is accepted by the design — do NOT "fix" it into a
tokenizer.
"""
from __future__ import annotations

from pathlib import Path

SOURCE_EXTENSIONS = (".py",)
COMMENT_PREFIX = "#"


def _is_test_file(path: Path) -> bool:
    return path.stem.startswith("test_") or path.stem.endswith("_test")


def count_non_test_source_loc(solution_dir: Path) -> int:
    """Count non-blank, non-comment-only lines across non-test source files.

    Recurses `solution_dir`; `__pycache__`/`.pyc` and other non-source files are
    skipped naturally by the extension filter.
    """
    total = 0
    for path in sorted(Path(solution_dir).rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_EXTENSIONS:
            continue
        if _is_test_file(path):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(COMMENT_PREFIX):
                total += 1
    return total
