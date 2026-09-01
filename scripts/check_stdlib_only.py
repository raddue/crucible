#!/usr/bin/env python3
"""INV-C1 check: `scripts/complexity_index.py` imports stdlib modules only (#558).

Invocation (from repo root):
    python3 scripts/check_stdlib_only.py            # check the real complexity_index.py
    python3 scripts/check_stdlib_only.py --selftest # built-in logic tests (synthetic)

The rule is an ALLOWLIST, not a third-party blocklist: `ast.parse` the target,
collect the root of every `import X` / `import X.Y` / `from X.Y import Z`, and
accept a root ONLY if it is in `sys.stdlib_module_names` AND is not also a
top-level name present in this interpreter's site-packages. Three ways to fail:

  - root not in `sys.stdlib_module_names`, and a site-packages name -> third-party
    (`import requests`);
  - root not in `sys.stdlib_module_names`, and NOT a site-packages name -> local
    sibling / unknown module (`import complexity_index`) -- an allowlist rejects
    this too, so it can never pass silently just because it isn't pip-installed;
  - root IS a stdlib name but is ALSO shadowed by a site-packages distribution of
    the same name -> the import does not actually resolve to the stdlib.

Relative imports (`from . import x`) have no root and are rejected as non-stdlib.
A target that fails to parse, is missing, or contains zero imports is a FAIL, not
a silent pass -- each of those would otherwise turn this check permanently green.

Stdlib only (it would be absurd otherwise). Exit 0 clean / 1 on any violation.
"""
from __future__ import annotations

import ast
import os
import pathlib
import site
import sys
import sysconfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = "scripts/complexity_index.py"


def site_package_names() -> frozenset[str]:
    """Top-level importable names present in this interpreter's site-packages."""
    dirs: set[str] = set()
    for getter in (getattr(site, "getsitepackages", None),
                   getattr(site, "getusersitepackages", None)):
        if getter is None:
            continue
        try:
            got = getter()
        except Exception:  # pragma: no cover - virtualenv variants
            continue
        dirs.update([got] if isinstance(got, str) else got)
    for key in ("purelib", "platlib"):
        path = sysconfig.get_paths().get(key)
        if path:
            dirs.add(path)

    names: set[str] = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for entry in os.listdir(d):
            if entry.endswith((".dist-info", ".egg-info", ".egg-link", ".pth")):
                continue
            name = entry.split(".")[0]
            if name and not name.startswith("_") and name != "__pycache__":
                names.add(name)
    return frozenset(names)


def import_roots(source: str) -> list[tuple[str, int, str]]:
    """[(root, lineno, rendered-form)] for every import in `source`.

    The root of `import os.path` and of `from os.path import join` is both `os`.
    A relative import yields the empty root `""`. Raises SyntaxError if `source`
    does not parse -- callers must treat that as a failure, never as "no imports".
    """
    found: list[tuple[str, int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[0], node.lineno,
                              f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            form = f"from {'.' * node.level}{module} import ..."
            root = "" if node.level else module.split(".")[0]
            found.append((root, node.lineno, form))
    return sorted(found, key=lambda t: (t[1], t[0]))


def violations(roots, label: str, site_names) -> list[str]:
    """Violation strings for non-stdlib roots ([] == clean).

    Every line has the shape `<label>:<lineno>: <root> [<form>] -- <reason>`, so
    the reason is parseable (split on " -- ") independently of the label: a
    violation raised for the WRONG reason must not be able to satisfy a caller
    looking for the right one.
    """
    out: list[str] = []
    for root, lineno, form in roots:
        if not root:
            shown, reason = ".", "relative import: not a stdlib module"
        elif root not in sys.stdlib_module_names:
            shown = root
            reason = ("third-party: installed in site-packages"
                      if root in site_names
                      else "not stdlib and not installed: local sibling or "
                           "unknown module")
        elif root in site_names:
            shown = root
            reason = ("stdlib name shadowed by a site-packages distribution of "
                      "the same name")
        else:
            continue
        out.append(f"{label}:{lineno}: {shown} [{form}] -- {reason}")
    return out


def main() -> int:
    target = ROOT / TARGET
    if not target.exists():
        print(f"FAIL -- {TARGET} does not exist (nothing was checked).")
        return 1
    try:
        source = target.read_text(encoding="utf-8")
    except OSError as e:
        print(f"FAIL -- cannot read {TARGET}: {e}")
        return 1
    try:
        roots = import_roots(source)
    except SyntaxError as e:
        print(f"FAIL -- {TARGET} does not parse (line {e.lineno}): {e.msg}")
        return 1
    if not roots:
        print(f"FAIL -- no imports found in {TARGET}; the target imports several "
              "modules, so zero means this check is broken, not that it passed.")
        return 1

    bad = violations(roots, TARGET, site_package_names())
    if bad:
        print(f"INV-C1 VIOLATION -- {TARGET} imports outside the standard library:")
        for v in bad:
            print(f"  - {v}")
        print("  Fix: drop the dependency; complexity_index.py is stdlib-only by contract.")
        return 1
    print(f"OK -- {TARGET}: {len(roots)} import(s), every root stdlib "
          f"({', '.join(sorted({r for r, _, _ in roots}))}).")
    return 0


# --------------------------------------------------------------------------- #
# selftest -- synthetic sources, fixed site-name sets (no real environment)     #
# --------------------------------------------------------------------------- #

_FAKE_SITE = frozenset({"requests", "pytest", "numpy"})


def selftest() -> int:
    failures: list[str] = []

    def expect_clean(name, src, want_roots, site_names=_FAKE_SITE):
        try:
            roots = import_roots(src)
        except SyntaxError as e:
            failures.append(f"{name}: source did not parse: {e}")
            return
        got = [(r, ln) for r, ln, _ in roots]
        if got != want_roots:
            failures.append(f"{name}: roots {got} != expected {want_roots}")
        v = violations(roots, name, site_names)
        if v:
            failures.append(f"{name}: expected clean, got {v}")

    def expect_violation(name, src, want_root, want_reason, site_names=_FAKE_SITE,
                         want_collected=None):
        # want_root is the name the message must display ("." for a relative
        # import); want_collected is the AST root import_roots must have found.
        want_collected = want_root if want_collected is None else want_collected
        try:
            roots = import_roots(src)
        except SyntaxError as e:
            failures.append(f"{name}: source did not parse (wrong reason): {e}")
            return
        if not roots:
            failures.append(f"{name}: no imports collected (wrong reason)")
            return
        if want_collected not in [r for r, _, _ in roots]:
            failures.append(f"{name}: root {want_collected!r} not collected, got "
                            f"{[r for r, _, _ in roots]}")
        v = violations(roots, name, site_names)
        if not v:
            failures.append(f"{name}: expected a violation, got none")
            return
        # The label lives in the head, the reason after " -- ": a violation
        # raised for the wrong reason cannot satisfy this by accident.
        hit = [s for s in v
               if f": {want_root} [" in s.partition(" -- ")[0]
               and want_reason in s.partition(" -- ")[2]]
        if not hit:
            failures.append(f"{name}: no violation naming {want_root!r} for reason "
                            f"{want_reason!r}; got {v}")

    # PASS shape -- stdlib plain / dotted / from-import / __future__.
    expect_clean(
        "pass-stdlib",
        "from __future__ import annotations\nimport ast\nimport os.path\n"
        "from re import compile\n",
        [("__future__", 1), ("ast", 2), ("os", 3), ("re", 4)],
    )
    # FAIL shapes -- each names the offending module for the RIGHT reason.
    expect_violation("fail-import-third-party", "import requests\n",
                     "requests", "third-party")
    expect_violation("fail-from-third-party", "from pytest import fixture\n",
                     "pytest", "third-party")
    expect_violation("fail-dotted-third-party", "import numpy.linalg as la\n",
                     "numpy", "third-party")
    expect_violation("fail-local-sibling", "import complexity_index\n",
                     "complexity_index", "not stdlib and not installed")
    expect_violation("fail-relative", "from . import helpers\n",
                     ".", "relative import", want_collected="")
    expect_violation("fail-shadowed-stdlib", "import ast\n",
                     "ast", "shadowed", site_names=frozenset({"ast"}))

    # A source that does not parse must raise, never report "no imports".
    try:
        import_roots("import (\n")
        failures.append("parse-error: expected SyntaxError, got a clean parse")
    except SyntaxError:
        pass

    # Discovery must not raise on this interpreter (bare mode depends on it).
    # Emptiness is NOT asserted: a site-packages-free interpreter is legitimate
    # and does not make the allowlist permissive, only the wording less specific.
    try:
        site_package_names()
    except Exception as e:  # noqa: BLE001 - any failure here breaks bare mode
        failures.append(f"site_package_names() raised: {e!r}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK -- stdlib import/from/dotted shapes PASS; third-party, "
          "local-sibling, relative and shadowed-stdlib imports FAIL by name; "
          "an unparseable source raises.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
