"""Tiny reporting module for the delve eval fixture (#373). Hermetic, stdlib-only.

Contains deliberately PLANTED defects at known lines — see ground-truth-bugs.json.
"""


def write_report(path, rows):
    # PLANTED b5 (line 10): resource leak — the file handle is never closed (no
    # context manager, no .close()).
    f = open(path, "w")
    for row in rows:
        f.write(str(row) + "\n")
    return path


def average(values):
    # PLANTED b6 (line 19): unguarded division — an empty `values` raises
    # ZeroDivisionError instead of returning 0.
    return sum(values) / len(values)
