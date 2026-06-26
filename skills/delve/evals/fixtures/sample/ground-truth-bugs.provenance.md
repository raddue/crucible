# Blind-author input for the `sample` delve fixture (#373)

This is the VERBATIM context handed to the blind ground-truth author. It describes
the feature under review and the codebase facts only. The planted bugs' signature
tokens and their `desc` strings in `ground-truth-bugs.json` are deliberately
WITHHELD here, so the author cannot reverse-engineer the answer key from this file.
`scripts/check_delve_gt_provenance.py` machine-verifies that none of those withheld
strings appear below.

## Feature under review

A two-module inventory toolkit:

- `inventory.py` — helpers for a small store: returning the most recent items, a
  cart total with an optional adjustments list, an availability check, and a stock
  top-up routine.
- `report.py` — writes a per-row text report to a path and computes an arithmetic
  mean over a list of numbers.

## Codebase facts

- Pure Python, standard library only; no external packages.
- Each public function is a few lines; there is no shared mutable state across
  modules.
- The store callers pass ordinary Python lists and dicts; SKUs are dict keys.
- The report writer is expected to persist every row it is given and hand back the
  path it wrote to.

## Task for the reviewer

Review these two modules for defects a careful engineer would flag in code review.
Report each issue you find with the file, the line, a one-line summary, and the
failure scenario it produces.
