#!/usr/bin/env python3
"""Doc/module drift check for `skills/shared/ledger-append.md`'s inlined Python
reference blocks (#460 round-4 quality-gate S4).

Invocation (from repo root):
    python3 scripts/check_ledger_append_doc_drift.py            # check the tree
    python3 scripts/check_ledger_append_doc_drift.py --selftest # built-in logic tests

`ledger-append.md` inlines full or abridged copies of live modules under
`## Reference Python — `scripts/<name>.py`` headings, so a reader never has to
leave the spec to see the real code. Those copies can silently go stale when
the module changes underneath them (the exact #460 round-4 S4 bug: the
`default_repo` copy was missing the #401 `os.path.realpath(top)` call and its
comment). This check catches that class of drift mechanically.

**Line-subset assertion, not exact-copy diff.** A reference block is allowed to
be an abridged excerpt (`scripts/uuid7.py`'s copy drops its module/function
docstring prose and its trailing `if __name__` block) — so this does not require
the doc block to equal the module byte-for-byte. Instead it parses BOTH sides
with `ast`, flattens each into an ordered list of statements (recursing into
every compound statement's body/orelse/handlers/finalbody, generically — not a
hardcoded per-node-type list — and dropping module/function/class docstrings,
which are prose, not logic), and asserts the doc's statement list is a
**subsequence** of the module's (every doc statement must appear in the module,
in the same relative order; the module may have additional statements the doc
omits). Comments are invisible to `ast` already, so cosmetic comment rewords
never trigger a false positive; a real logic fork (a changed line, a missing
line, a reordered line) has no match and is reported.

**Discovery is generic, not hardcoded.** Every `## Reference Python —
`scripts/<name>.py`` heading in the doc is found by regex and checked against
`scripts/<name>.py`; a heading whose module doesn't exist on disk is reported as
a skip, not a hard failure (a reference block for an already-deleted module,
like the L-9 `reduce()` block for the retired `ledger_reduce.py`, is
deliberately NOT written under this heading pattern for exactly that reason —
see the note in `ledger-append.md`'s L-9 section).

Exits 0 if every discovered block is a clean subsequence of its module, 1 with
a per-block drift list otherwise. Stdlib only.
"""
from __future__ import annotations
import ast
import copy
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "skills" / "shared" / "ledger-append.md"

_BLOCK_RE = re.compile(
    r"## Reference Python — `scripts/(?P<mod>[\w.]+\.py)`.*?```python\n(?P<code>.*?)\n```",
    re.DOTALL,
)

_BODY_FIELDS = ("body", "orelse", "handlers", "finalbody")


def extract_reference_blocks(doc_text: str) -> dict:
    """Map module relative filename (e.g. "uuid7.py") -> fenced code block text,
    for every `## Reference Python — `scripts/<name>.py`` heading found."""
    return {m.group("mod"): m.group("code") for m in _BLOCK_RE.finditer(doc_text)}


def _is_docstring_expr(node) -> bool:
    """True for a bare string-literal statement — a module/function/class
    docstring. These are prose, not logic, so they're excluded from the
    flattened comparison (an abridged doc copy is allowed to reword them)."""
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def _shallow_copy_clearing_body(node):
    """Deep-copy `node` with its statement-list fields (body/orelse/handlers/
    finalbody) emptied, so `ast.dump` on the copy describes only this node's
    own shape — its nested statements are separate entries in the flattened
    list, not baked into this one."""
    node = copy.deepcopy(node)
    for field in _BODY_FIELDS:
        if isinstance(getattr(node, field, None), list):
            setattr(node, field, [])
    return node


def _flatten_statements(nodes) -> list:
    """Recursively flatten a list of statement (or ExceptHandler) nodes into an
    ordered list of (dump, node) pairs, generically descending into every
    compound statement's body/orelse/handlers/finalbody fields — this reaches
    every nested function, if/try/for/while body without hardcoding node
    types. Docstring statements are skipped (prose, not logic)."""
    out = []
    for node in nodes:
        if _is_docstring_expr(node):
            continue
        out.append((ast.dump(_shallow_copy_clearing_body(node)), node))
        for field in _BODY_FIELDS:
            value = getattr(node, field, None)
            if isinstance(value, list):
                out.extend(_flatten_statements(value))
    return out


def compare_sources(doc_src: str, module_src: str) -> list:
    """Return a list of drift descriptions (empty == doc is a clean subsequence
    of the module). Each doc statement must match some module statement at or
    after the previous match's position, in order."""
    doc_flat = _flatten_statements(ast.parse(doc_src).body)
    mod_flat = _flatten_statements(ast.parse(module_src).body)
    mod_dumps = [d for d, _ in mod_flat]

    drift = []
    pos = 0
    for dump, node in doc_flat:
        try:
            idx = mod_dumps.index(dump, pos)
        except ValueError:
            try:
                snippet = ast.unparse(node)
            except Exception:  # noqa: BLE001 — unparse is best-effort for the message
                snippet = dump
            drift.append(
                f"doc statement not found in module (searching from module "
                f"position {pos}): {snippet}"
            )
            continue
        pos = idx + 1
    return drift


def main() -> int:
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    blocks = extract_reference_blocks(doc_text)
    if not blocks:
        print(f"NO reference blocks found in {DOC_PATH} — regex may be stale.")
        return 1

    all_drift = []
    skipped = []
    for mod_name, code in blocks.items():
        mod_path = ROOT / "scripts" / mod_name
        if not mod_path.exists():
            skipped.append(mod_name)
            continue
        module_src = mod_path.read_text(encoding="utf-8")
        for d in compare_sources(code, module_src):
            all_drift.append(f"scripts/{mod_name}: {d}")

    if all_drift:
        print("LEDGER-APPEND DOC DRIFT — a reference block diverged from its module:")
        for d in all_drift:
            print(f"  {d}")
        print("\nRe-sync the fenced block in skills/shared/ledger-append.md with "
              "the current module source, or update this check if the "
              "divergence is intentional. See "
              "scripts/check_ledger_append_doc_drift.py docstring.")
        return 1

    print(f"OK — {len(blocks)} reference block(s) in {DOC_PATH.relative_to(ROOT)} "
          f"are each a clean subsequence of their module "
          f"({', '.join(sorted(blocks))})."
          + (f" Skipped (no module on disk): {', '.join(skipped)}."
             if skipped else ""))
    return 0


def selftest() -> int:
    """Built-in logic tests, in-memory, against the real doc + modules.

    Positive leg: every reference block currently in the doc is a clean
    subsequence of its module (this is the steady-state the checker enforces).
    Negative leg: reconstructs the exact #460 round-4 S4 bug — a `default_repo`
    doc copy missing the #401 `os.path.realpath(top)` line — against the
    CURRENT (post-#401) module, and asserts it is caught."""
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    blocks = extract_reference_blocks(doc_text)
    failures = []

    if "ledger_append.py" not in blocks:
        failures.append("positive: ledger_append.py reference block not found "
                         "(regex may be stale)")
    else:
        module_src = (ROOT / "scripts" / "ledger_append.py").read_text(encoding="utf-8")
        drift = compare_sources(blocks["ledger_append.py"], module_src)
        if drift:
            failures.append(f"positive: ledger_append.py block unexpectedly "
                             f"drifted: {drift}")

        # case-A: reintroduce the exact S4 bug — strip the #401 realpath line
        # and its comment from the doc copy, and the parallel change in the
        # non-git fallback — and confirm the resulting stale copy is caught
        # against the current (fixed) module.
        stale = blocks["ledger_append.py"]
        stale = stale.replace(
            '            # #401: realpath for parity with grudge_append.resolve_repo. On the\n'
            '            # git path this is effectively a no-op — `git rev-parse --show-toplevel`\n'
            '            # already returns a canonicalized path — but it keeps the two\n'
            '            # resolvers textually aligned. The non-git fallback below is where the\n'
            '            # symlink-resolution drift actually mattered.\n'
            '            root = os.path.realpath(top)\n'
            '            return os.path.basename(root.rstrip("/")) or root\n',
            '            return os.path.basename(top.rstrip("/")) or top\n',
        )
        stale = stale.replace(
            '    # #401: realpath the fallback base so a non-git dir reached via a symlinked\n'
            '    # parent yields the SAME basename label the grudge store derives. The return\n'
            '    # SHAPE stays a bare basename (callers want a label, not the root tuple).\n'
            '    return os.path.basename(os.path.realpath(os.path.abspath(base))) or "unknown"\n',
            '    return os.path.basename(os.path.abspath(base)) or "unknown"\n',
        )
        if stale == blocks["ledger_append.py"]:
            failures.append("case-A: #401 mutation anchor not found (test is vacuous)")
        drift = compare_sources(stale, module_src)
        if not drift:
            failures.append("case-A: reverting the #401 fix in the doc copy was "
                             "NOT caught against the current module")

    if "uuid7.py" not in blocks:
        failures.append("positive: uuid7.py reference block not found "
                         "(regex may be stale)")
    else:
        module_src = (ROOT / "scripts" / "uuid7.py").read_text(encoding="utf-8")
        drift = compare_sources(blocks["uuid7.py"], module_src)
        if drift:
            failures.append(f"positive: uuid7.py block (a legitimately abridged "
                             f"excerpt — comments/docstring/trailing __main__ "
                             f"dropped) unexpectedly drifted: {drift}")

        # case-B: fork a real statement (not a comment/docstring) in the doc
        # copy and confirm it's caught even in an abridged reference block.
        forked = blocks["uuid7.py"].replace(
            'b[6] = (b[6] & 0x0F) | 0x70', 'b[6] = (b[6] & 0x0F) | 0x90')
        if forked == blocks["uuid7.py"]:
            failures.append("case-B: uuid7 mutation anchor not found (test is vacuous)")
        drift = compare_sources(forked, module_src)
        if not drift:
            failures.append("case-B: a forked statement in the abridged uuid7.py "
                             "doc copy was NOT caught")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("SELFTEST OK — both live reference blocks are clean subsequences of "
          "their modules; a reverted #401 fix (case-A) and a forked statement "
          "in the abridged uuid7.py excerpt (case-B) are both caught.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
