#!/usr/bin/env python3
"""INV-C1 check: `scripts/complexity_index.py` imports stdlib modules only (#558).

Invocation (from repo root):
    python3 scripts/check_stdlib_only.py            # check the real complexity_index.py
    python3 scripts/check_stdlib_only.py --selftest # built-in logic tests (synthetic)

Exactly those two argv shapes are accepted; anything else is a usage failure
(exit 1, message on stderr) rather than a silent fall-through to the bare check
-- a typo'd `--self-test` in a CI wiring line must not look like a passing run.

The rule is an ALLOWLIST, not a third-party blocklist: `ast.parse` the target,
collect the root of every `import X` / `import X.Y` / `from X.Y import Z`, and
accept a root ONLY if it is in `sys.stdlib_module_names` AND is not shadowed by a
module sitting beside the target. Three ways to fail:

  - root not in `sys.stdlib_module_names`, and a site-packages name -> third-party
    (`import requests`);
  - root not in `sys.stdlib_module_names`, and NOT a site-packages name -> local
    sibling / unknown module (`import complexity_index`) -- an allowlist rejects
    this too, so it can never pass silently just because it isn't pip-installed;
  - root IS a stdlib name but a module of that name sits NEXT TO the target
    (`scripts/argparse.py`) -> the import does not actually resolve to the stdlib.

The shadow arm looks at the target's own directory, not at site-packages,
because that is where shadowing can actually happen: running `scripts/x.py` puts
`scripts/` at `sys.path[0]`, above the stdlib, while site-packages sits BELOW the
stdlib and therefore cannot shadow it. (Checking site-packages instead produced a
false INV-C1 failure on a correct file whenever the `argparse` PyPI backport
happened to be installed.)

Relative imports (`from . import x`) have no root and are rejected as non-stdlib.
A target that fails to parse, is missing, or contains zero imports is a FAIL, not
a silent pass -- each of those would otherwise turn this check permanently green.

Documented limitation: the check reads `import` / `from ... import` STATEMENTS.
`importlib.import_module("requests")`, `__import__("requests")` and `exec` of an
import string are invisible to it, by design -- the threat model is accidental
dependency drift in a file this team writes, not adversarial evasion. Dynamic
import detection is deliberately not attempted. The "no imports found" guard is
what stops a target whose imports are *only* dynamic from passing as clean.

Stdlib only (it would be absurd otherwise). Exit 0 clean / 1 on any violation.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import pathlib
import site
import subprocess
import sys
import sysconfig
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = "scripts/complexity_index.py"
USAGE = "usage: check_stdlib_only.py [--selftest]"

# Set in child processes spawned by the selftest's CLI battery, so a child does
# not spawn its own battery (and so a mutant that routes bare mode into the
# selftest cannot fork-bomb instead of failing).
_CHILD_ENV = "CHECK_STDLIB_ONLY_SELFTEST_CHILD"


def site_package_names() -> frozenset[str]:
    """Top-level importable names present in this interpreter's site-packages.

    Used only to word the reason for a non-stdlib root ("third-party" vs "local
    sibling or unknown module"); it is NOT the shadow test -- see the module
    docstring for why site-packages cannot shadow the stdlib.
    """
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


def sibling_module_names(directory) -> frozenset[str]:
    """Top-level module names importable from `directory` itself.

    Running `directory/target.py` puts `directory` at `sys.path[0]` -- the
    highest-precedence entry -- so `directory/argparse.py` genuinely shadows
    stdlib `argparse` for that target. An unreadable directory yields the empty
    set; the caller has already established that the target itself is readable.
    """
    try:
        entries = os.listdir(directory)
    except OSError:  # pragma: no cover - target is readable by the time we get here
        return frozenset()
    names: set[str] = set()
    for entry in entries:
        path = os.path.join(directory, entry)
        if entry.endswith(".py") and os.path.isfile(path):
            names.add(entry[:-3])
        elif os.path.isdir(path) and os.path.isfile(os.path.join(path, "__init__.py")):
            names.add(entry)
    return frozenset(n for n in names if n and not n.startswith("_"))


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


def violations(roots, label: str, site_names, sibling_names) -> list[str]:
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
        elif root in sibling_names:
            shown = root
            reason = ("stdlib name shadowed by a module of the same name beside "
                      "the target")
        else:
            continue
        out.append(f"{label}:{lineno}: {shown} [{form}] -- {reason}")
    return out


def check_path(target, label: str) -> int:
    """Check one file end-to-end; 0 clean / 1 violation-or-unusable-target.

    `label` is what the messages name (the repo-relative path for the real run).
    Internal seam only -- the CLI stays `[--selftest]`; this exists so the
    selftest can drive the whole enforcement path against synthetic targets.
    """
    if not target.exists():
        print(f"FAIL -- {label} does not exist (nothing was checked).")
        return 1
    try:
        source = target.read_text(encoding="utf-8")
    except OSError as e:
        print(f"FAIL -- cannot read {label}: {e}")
        return 1
    try:
        roots = import_roots(source)
    except SyntaxError as e:
        print(f"FAIL -- {label} does not parse (line {e.lineno}): {e.msg}")
        return 1
    if not roots:
        print(f"FAIL -- no imports found in {label}; the target imports several "
              "modules, so zero means this check is broken, not that it passed.")
        return 1

    bad = violations(roots, label, site_package_names(),
                     sibling_module_names(target.parent))
    if bad:
        print(f"INV-C1 VIOLATION -- {label} imports outside the standard library:")
        for v in bad:
            print(f"  - {v}")
        print("  Fix: drop the dependency; complexity_index.py is stdlib-only by contract.")
        return 1
    print(f"OK -- {label}: {len(roots)} import(s), every root stdlib "
          f"({', '.join(sorted({r for r, _, _ in roots}))}).")
    return 0


def main() -> int:
    return check_path(ROOT / TARGET, TARGET)


# --------------------------------------------------------------------------- #
# selftest -- synthetic sources, fixed site-name sets (no real environment)     #
# --------------------------------------------------------------------------- #

_FAKE_SITE = frozenset({"requests", "pytest", "numpy"})


def selftest() -> int:
    failures: list[str] = []

    def expect_clean(name, src, want_roots, site_names=_FAKE_SITE,
                     sibling_names=frozenset()):
        try:
            roots = import_roots(src)
        except SyntaxError as e:
            failures.append(f"{name}: source did not parse: {e}")
            return
        got = [(r, ln) for r, ln, _ in roots]
        if got != want_roots:
            failures.append(f"{name}: roots {got} != expected {want_roots}")
        v = violations(roots, name, site_names, sibling_names)
        if v:
            failures.append(f"{name}: expected clean, got {v}")

    def expect_violation(name, src, want_root, want_reason, site_names=_FAKE_SITE,
                         want_collected=None, sibling_names=frozenset()):
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
        v = violations(roots, name, site_names, sibling_names)
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

    def expect_check(name, files, want_rc, want_out=(), target_name="target.py"):
        """Drive check_path() end-to-end over a synthetic tree.

        `files` maps a name to its content; a None content makes a DIRECTORY of
        that name (used for the unreadable-target case).
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            for fname, content in files.items():
                if content is None:
                    (base / fname).mkdir()
                else:
                    (base / fname).write_text(content, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check_path(base / target_name, target_name)
            out = buf.getvalue()
        if rc != want_rc:
            failures.append(f"{name}: check_path exit {rc}, expected {want_rc} "
                            f"(output: {out.strip()!r})")
            return
        for token in want_out:
            if token not in out:
                failures.append(f"{name}: output missing {token!r}; got {out.strip()!r}")

    def expect_cli(name, args, want_rc, want_stdout=(), want_stderr=()):
        """Run this script as a subprocess -- the only way to pin mode dispatch."""
        proc = subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).resolve()), *args],
            capture_output=True, text=True, cwd=str(ROOT),
            env={**os.environ, _CHILD_ENV: "1"})
        if proc.returncode != want_rc:
            failures.append(f"{name}: argv {args} exit {proc.returncode}, expected "
                            f"{want_rc} (stdout {proc.stdout.strip()!r}, "
                            f"stderr {proc.stderr.strip()!r})")
            return
        for token in want_stdout:
            if token not in proc.stdout:
                failures.append(f"{name}: stdout missing {token!r}; got "
                                f"{proc.stdout.strip()!r}")
        for token in want_stderr:
            if token not in proc.stderr:
                failures.append(f"{name}: stderr missing {token!r}; got "
                                f"{proc.stderr.strip()!r}")

    # -- import_roots / violations: PASS shapes ------------------------------ #
    # stdlib plain / dotted / from-import / dotted-from / __future__.
    expect_clean(
        "pass-stdlib",
        "from __future__ import annotations\nimport ast\nimport os.path\n"
        "from re import compile\nfrom os.path import join\n",
        [("__future__", 1), ("ast", 2), ("os", 3), ("re", 4), ("os", 5)],
    )
    # A site-packages distribution named after a stdlib module does NOT shadow
    # it (site-packages sits below the stdlib on sys.path): `pip install
    # argparse` must not redden a correct file.
    expect_clean("pass-stdlib-name-also-in-site-packages", "import argparse\n",
                 [("argparse", 1)], site_names=frozenset({"argparse"}))

    # -- import_roots / violations: FAIL shapes ------------------------------ #
    # Each names the offending module for the RIGHT reason.
    expect_violation("fail-import-third-party", "import requests\n",
                     "requests", "third-party")
    expect_violation("fail-from-third-party", "from pytest import fixture\n",
                     "pytest", "third-party")
    expect_violation("fail-dotted-third-party", "import numpy.linalg as la\n",
                     "numpy", "third-party")
    # Dotted `from`: the root is the FIRST segment, else the reason degrades.
    expect_violation("fail-dotted-from-third-party",
                     "from requests.adapters import HTTPAdapter\n",
                     "requests", "third-party")
    # Multi-alias: every alias in the statement is collected, not just the first.
    expect_violation("fail-multi-alias", "import os, requests\n",
                     "requests", "third-party")
    # Non-top-level imports: the walk must reach into function bodies and blocks.
    expect_violation("fail-nested-in-function",
                     "import os\ndef f():\n    import requests\n",
                     "requests", "third-party")
    expect_violation("fail-guarded-by-try",
                     "try:\n    import numpy\nexcept ImportError:\n    numpy = None\n",
                     "numpy", "third-party")
    expect_violation("fail-local-sibling", "import complexity_index\n",
                     "complexity_index", "not stdlib and not installed")
    expect_violation("fail-relative", "from . import helpers\n",
                     ".", "relative import", want_collected="")
    # A NAMED relative import must collect the empty root, not the bare name --
    # otherwise `from .os import path` launders into a clean stdlib pass.
    expect_violation("fail-relative-named", "from .os import path\n",
                     ".", "relative import", want_collected="")
    expect_violation("fail-shadowed-stdlib", "import ast\n",
                     "ast", "shadowed", sibling_names=frozenset({"ast"}))

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

    # -- check_path: the enforcement path, end to end ------------------------ #
    expect_check("check-clean", {"target.py": "import os\nfrom re import compile\n"},
                 0, ("OK -- target.py", "os, re"))
    expect_check("check-violation", {"target.py": "import os\nimport requests\n"},
                 1, ("INV-C1 VIOLATION", "requests"))
    expect_check("check-missing-target", {}, 1, ("does not exist",))
    expect_check("check-unparseable-target", {"target.py": "import (\n"},
                 1, ("does not parse",))
    expect_check("check-zero-imports", {"target.py": "x = 1\n"},
                 1, ("no imports found",))
    expect_check("check-unreadable-target", {"target.py": None},
                 1, ("cannot read",))
    # A real sibling module shadowing a stdlib name reddens; an unimported one
    # does not (the arm must fire on shadowed IMPORTS, not on mere presence).
    expect_check("check-sibling-shadow",
                 {"target.py": "import argparse\n", "argparse.py": "raise SystemExit\n"},
                 1, ("INV-C1 VIOLATION", "shadowed"))
    expect_check("check-sibling-unimported",
                 {"target.py": "import os\n", "argparse.py": "raise SystemExit\n"},
                 0, ("OK -- target.py",))

    # -- CLI: mode dispatch and argument rejection --------------------------- #
    # Skipped inside a child spawned by this battery (no recursion).
    if os.environ.get(_CHILD_ENV):
        print("(child process: CLI battery skipped)")
    else:
        # Bare mode must run the REAL check against the REAL target: this pins
        # both the target identity and that main() is actually invoked.
        expect_cli("cli-bare", [], 0, want_stdout=("OK -- scripts/complexity_index.py",))
        expect_cli("cli-selftest", ["--selftest"], 0, want_stdout=("SELFTEST OK",))
        for bad_argv in (["--self-test"], ["--selftest=1"], ["--selftest", "extra"],
                         ["--bogus"], ["--help"], ["-h"], ["foo"]):
            expect_cli(f"cli-reject-{'_'.join(bad_argv)}", bad_argv, 1,
                       want_stderr=("usage:",))

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK -- stdlib import/from/dotted/nested shapes PASS; third-party, "
          "local-sibling, relative and sibling-shadowed imports FAIL by name; an "
          "unparseable source raises; check_path fails closed on missing/unreadable/"
          "unparseable/import-free targets; the CLI rejects unknown arguments.")
    return 0


if __name__ == "__main__":
    _args = sys.argv[1:]
    if _args == ["--selftest"]:
        sys.exit(selftest())
    if _args:
        print(f"FAIL -- unrecognised argument(s) {_args}; {USAGE}", file=sys.stderr)
        sys.exit(1)
    sys.exit(main())
