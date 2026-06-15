#!/usr/bin/env python3
"""Function-scoped drift check for the inquisitor eval-harness helpers (#424).

Invocation (from repo root):
    python3 scripts/check_inquisitor_helper_drift.py            # check the tree
    python3 scripts/check_inquisitor_helper_drift.py --selftest # built-in logic tests

The inquisitor eval harness copies temper's `_dispatch_paths.py` / `_runid.py`
helpers (the design's "link/derive, never copy" rule is relaxed for these tiny
path/hash/validation utilities — copying with a machine-checked no-drift invariant
is cheaper than a shared-package refactor). This check replaces the retired
"byte-identical at copy time" invariant with a structural one that tolerates the
copy's *legitimate* edits yet still catches a logic fork.

It is **function-scoped**: it diffs ONLY the bodies of the functions inquisitor
actually imports —
  - `resolve_dispatch_dir`, `fixture_sha`, `template_sha` from `_dispatch_paths.py`
  - `validate_run_id` from `_runid.py`
— against temper's, parsing each side with `ast` and comparing those named function
nodes by `ast.dump` (whitespace/comment/line-number insensitive). It does NOT compare
the whole file, so the inquisitor copy may freely omit temper-only helpers
(`validate_prefix`, `sanitize_summary`) and inquisitor CI never reddens when temper
edits a function inquisitor never calls (SP3).

**Referenced module-level constants are in scope too (S2):** a compared function's
real logic can live in a module constant it references by name — `validate_run_id`'s
run-id cap is the regex constant `_RUN_ID_RE`, not code in the body. So in addition
to each function body, this check diffs the module-level single-target `Assign`
nodes (`NAME = …`) that a compared function *loads* (e.g. `_RUN_ID_RE`). A forked
constant (widening `{0,31}`→`{0,99}`, dropping the leading-`-` guard) therefore
registers as drift even though the function body is byte-identical. Scoping stays
surgical — only constants a compared function references, not every module global
(so inquisitor's intentional omission of `_PREFIX_RE`, referenced solely by the
omitted `validate_prefix`, does not redden CI).

**Docstring handling is by structural/AST position, NOT a blanket triple-quote
regex (S-A):** a function's docstring is stripped before comparison ONLY for the
sites the inquisitor copy legitimately rewrites — the module docstring (never in the
compared set: we compare function nodes only) and `template_sha` (whose docstring
names the hashed template). Every OTHER compared function (`resolve_dispatch_dir`,
`fixture_sha`, `validate_run_id`) keeps its docstring in the comparison, so a
logic-altering rewrite of a non-{module,template_sha} docstring still FAILS the
check — an "all-docstrings" stripper would silently tolerate it.

Exits 0 if the copies are faithful, 1 with a per-drift list otherwise. Stdlib only.
"""
from __future__ import annotations
import ast
import copy
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (reference helper, inquisitor copy, the function names inquisitor imports)
PAIRS = [
    ("skills/temper/evals/_dispatch_paths.py",
     "skills/inquisitor/evals/_dispatch_paths.py",
     ("resolve_dispatch_dir", "fixture_sha", "template_sha")),
    ("skills/temper/evals/_runid.py",
     "skills/inquisitor/evals/_runid.py",
     ("validate_run_id",)),
]

# Compared functions whose docstring the inquisitor copy legitimately rewrites;
# their docstring is stripped (by AST position) before comparison. The module-level
# docstring is likewise rewritten in the copy but is never in the compared set (we
# compare only the named FunctionDef nodes), so it needs no entry here.
DOCSTRING_REWRITTEN = {"template_sha"}


def _functions(src: str) -> dict:
    """Map function name -> FunctionDef node for the top-level defs in `src`."""
    return {n.name: n for n in ast.parse(src).body
            if isinstance(n, ast.FunctionDef)}


def _module_assigns(src: str) -> dict:
    """Map single-target module-level constant name -> its `Assign` node. Covers
    only `NAME = …` top-level assignments (the `_RUN_ID_RE = re.compile(...)` shape);
    tuple/attribute/annotated targets are out of scope (none of the compared
    helpers reference such)."""
    out: dict = {}
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name):
            out[n.targets[0].id] = n
    return out


def _referenced_names(node: ast.FunctionDef) -> set:
    """The set of bare Name ids loaded inside a function body (e.g. `_RUN_ID_RE`).
    Used to scope the module-constant drift diff to ONLY constants a compared
    function actually references — not every module global (S2)."""
    return {sub.id for sub in ast.walk(node)
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)}


def _strip_docstring(node: ast.FunctionDef) -> ast.FunctionDef:
    """Return a copy of `node` with a leading docstring statement removed by AST
    position (the first stmt iff it is a bare string Constant Expr) — NOT by a
    triple-quote regex over the source."""
    node = copy.deepcopy(node)
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        node.body = body[1:]
    return node


def _dump(node: ast.FunctionDef, strip: bool) -> str:
    if strip:
        node = _strip_docstring(node)
    return ast.dump(node)


def compare_sources(ref_src: str, copy_src: str, names) -> list:
    """Return a list of drift descriptions for the named functions (empty == faithful).

    Besides each function's body, this also diffs the module-level constant
    `Assign` nodes that the function *references by name* (e.g. `validate_run_id`'s
    `_RUN_ID_RE`). A compared function's real logic can live in such a constant
    (the run-id cap regex), so a forked constant referenced by a faithful-looking
    body must still register as drift (S2). Scoping is surgical: only constants a
    compared function loads, not every module global."""
    ref = _functions(ref_src)
    cp = _functions(copy_src)
    ref_assigns = _module_assigns(ref_src)
    cp_assigns = _module_assigns(copy_src)
    drift = []
    for name in names:
        if name not in ref:
            drift.append(f"{name}: missing from reference (temper) helper")
            continue
        if name not in cp:
            drift.append(f"{name}: missing from inquisitor copy")
            continue
        strip = name in DOCSTRING_REWRITTEN
        if _dump(ref[name], strip) != _dump(cp[name], strip):
            note = " (docstring-stripped)" if strip else ""
            drift.append(f"{name}: body diverged from temper{note}")
        # Diff module-level constants this function references (S2: catch a logic
        # fork that lives in a referenced constant, not the function body).
        refd = _referenced_names(ref[name]) | _referenced_names(cp[name])
        for const in sorted(refd & (set(ref_assigns) | set(cp_assigns))):
            in_ref, in_cp = const in ref_assigns, const in cp_assigns
            if in_ref and in_cp:
                if ast.dump(ref_assigns[const]) != ast.dump(cp_assigns[const]):
                    drift.append(
                        f"{name}: referenced module constant {const} diverged "
                        f"from temper")
            elif in_ref != in_cp:
                where = "inquisitor copy" if in_ref else "reference (temper) helper"
                drift.append(
                    f"{name}: referenced module constant {const} missing from "
                    f"{where}")
    return drift


def main() -> int:
    all_drift = []
    for ref_rel, copy_rel, names in PAIRS:
        ref_src = (ROOT / ref_rel).read_text(encoding="utf-8")
        copy_src = (ROOT / copy_rel).read_text(encoding="utf-8")
        for d in compare_sources(ref_src, copy_src, names):
            all_drift.append(f"{copy_rel}: {d}")
    if all_drift:
        print("INQUISITOR HELPER DRIFT — the copied helpers diverged from temper:")
        for d in all_drift:
            print(f"  {d}")
        print("\nRe-sync the copied function bodies with "
              "skills/temper/evals/, or update this check if the divergence is "
              "intentional. See scripts/check_inquisitor_helper_drift.py docstring.")
        return 1
    print("OK — inquisitor's copied helpers match temper for every imported "
          "function and each module constant they reference (e.g. _RUN_ID_RE); "
          "module + template_sha docstrings excepted.")
    return 0


def selftest() -> int:
    """Built-in logic tests, in-memory, against the real temper reference.

    Two negative legs (R4-docstring) pin the structural docstring strip:
      case-A — a non-docstring body-line fork in resolve_dispatch_dir must be caught;
      case-B — a reworded NON-{module,template_sha} docstring (fixture_sha's) must be
               caught (an "all-docstrings" stripper would false-PASS this).
    A third negative leg (S2) pins the referenced-constant teeth:
      case-D — a forked module constant `_RUN_ID_RE` (cap {0,31}->{0,99}) referenced
               by an otherwise byte-identical validate_run_id must be caught.
    Plus a positive leg (the real clean copy is faithful) and a tolerance leg (a
    template_sha docstring reword is tolerated)."""
    ref_rel, copy_rel, names = PAIRS[0]  # _dispatch_paths pair
    ref_src = (ROOT / ref_rel).read_text(encoding="utf-8")
    clean_copy = (ROOT / copy_rel).read_text(encoding="utf-8")

    failures = []

    # positive leg — the committed copy is faithful
    drift = compare_sources(ref_src, clean_copy, names)
    if drift:
        failures.append(f"positive: clean copy unexpectedly drifted: {drift}")

    # case-A — fork a non-docstring body line in resolve_dispatch_dir → must FAIL
    case_a = clean_copy.replace(
        'f"{user}-crucible-dispatch-{run_id}"',
        'f"{user}-MUTATED-dispatch-{run_id}"')
    if case_a == clean_copy:
        failures.append("case-A: mutation anchor not found (test is vacuous)")
    drift = compare_sources(ref_src, case_a, names)
    if not any("resolve_dispatch_dir" in d for d in drift):
        failures.append(f"case-A: body fork in resolve_dispatch_dir NOT caught: {drift}")

    # case-B — reword fixture_sha's (non-stripped) docstring → must FAIL
    case_b = clean_copy.replace(
        '"""S-A: sha256 of canonical JSON of the evals.json fixture record."""',
        '"""Reworded: hash the canonical fixture record."""')
    if case_b == clean_copy:
        failures.append("case-B: docstring anchor not found (test is vacuous)")
    drift = compare_sources(ref_src, case_b, names)
    if not any("fixture_sha" in d for d in drift):
        failures.append(f"case-B: fixture_sha docstring reword NOT caught "
                        f"(over-strip): {drift}")

    # tolerance leg — rewording template_sha's docstring is tolerated (no drift)
    case_c = clean_copy.replace(
        "sha256 of a committed prompt template",
        "sha256 of an inquisitor prompt template")
    if case_c == clean_copy:
        failures.append("tolerance: template_sha docstring anchor not found")
    drift = compare_sources(ref_src, case_c, names)
    if drift:
        failures.append(f"tolerance: template_sha docstring reword should be "
                        f"tolerated, got drift: {drift}")

    # case-D (S2) — fork the referenced module constant _RUN_ID_RE (widen the cap
    # {0,31}->{0,99}, a real behavior fork) with a byte-identical validate_run_id
    # body → must FAIL on the constant, not the body. Uses the _runid pair (PAIRS[1]).
    runid_ref_rel, runid_copy_rel, runid_names = PAIRS[1]
    runid_ref_src = (ROOT / runid_ref_rel).read_text(encoding="utf-8")
    runid_clean_copy = (ROOT / runid_copy_rel).read_text(encoding="utf-8")
    # sanity: the clean copy is faithful (constant included)
    drift = compare_sources(runid_ref_src, runid_clean_copy, runid_names)
    if drift:
        failures.append(f"case-D positive: clean _runid copy unexpectedly "
                        f"drifted: {drift}")
    case_d = runid_clean_copy.replace(
        r"[A-Za-z0-9_-]{0,31}$", r"[A-Za-z0-9_-]{0,99}$")
    if case_d == runid_clean_copy:
        failures.append("case-D: _RUN_ID_RE cap anchor not found (test is vacuous)")
    drift = compare_sources(runid_ref_src, case_d, runid_names)
    if not any("_RUN_ID_RE" in d for d in drift):
        failures.append(f"case-D: forked _RUN_ID_RE constant NOT caught "
                        f"(referenced-constant blindness): {drift}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("SELFTEST OK — function-scoped comparison catches body forks (case-A), "
          "non-{module,template_sha} docstring rewrites (case-B), and a forked "
          "referenced module constant _RUN_ID_RE (case-D); tolerates the "
          "template_sha docstring reword.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
