#!/usr/bin/env python3
"""Producer-blindness CI guard for the Phase-1b seeded repos (#424, F1+F2).

Invocation (from repo root):
    python3 scripts/check_fixture_producer_blind.py            # check real fixtures
    python3 scripts/check_fixture_producer_blind.py --selftest # built-in logic tests

The score the live decision run produces is only meaningful if every producer arm
is BLIND to the seeded-bug identities. Two leaks (both Fatal, both passing the
GT-author provenance checker) would otherwise hand every arm the answer key and
ceiling the WITH−WITHOUT delta:

  F1 — the committed fixture `src/` annotates each bug with its id + a
       plain-language description of the defect AND its fix (`# BUG nt-b8: …`,
       `(nt-b1)`, `# … The fix coerces None to 0 …`); the prompts tell the agent
       to read `src/`. Hiding only the id TOKEN (round-1) still handed every arm
       the bug+fix in prose — the deeper, ceiling-inducing leak.
  F2 — the old `copy_for` copytree'd the WHOLE fixture dir into the agent's
       sandbox: `exemplars/` (passing tests per bug), `fixes/*.patch` (the exact
       fixes), `ground-truth-bugs.json` (the blind bug list), `manifest.json`.

`_fixtures.copy_repo_for_producer` is the fix: it copies only `src/` + `tests/`
and strips ALL comments and docstrings from every copied producer-visible `*.py`
(both subtrees, not `src/` alone — the complete F1 rule). This guard materializes a
real producer copy for every seeded repo and asserts:
  - (`_fixtures._assert_no_leak`) no answer-key path (`exemplars/`, `fixes/`,
    `manifest.json`, `ground-truth-*`) survives, no bug-identity leak TOKEN survives
    in any copied producer-visible `*.py` (`src/` AND `tests/`), and the copied
    `tests/` holds nothing but `conftest.py` (the documented invariant); AND
  - (`_fixtures.assert_no_description_leak`, ADVERSARIAL) no bug-DESCRIPTION prose
    survives — loaded from each repo's `ground-truth-bugs.json`, it asserts no
    >=N-word window of any bug `desc`, and no literal `"The fix"`, appears in any
    copied producer-visible source (`src/` AND `tests/`). This check does NOT re-use
    the strip's own regex (the round-1 circularity, S-1), so it independently FAILS
    on the prose leak if the strip were reverted.
It ALSO asserts the strip is behavior-preserving: every stripped `src/**/*.py`
still imports/compiles (so de-annotation never changed code).

This is the producer-side complement to check_fixture_gt_provenance.py (which only
checks the GT *author*'s blindness). Stdlib only. Exit 0 clean / 1 on violation.
"""
from __future__ import annotations
import ast
import compileall
import io
import json
import pathlib
import sys
import tempfile
import tokenize

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skills.inquisitor.evals import _fixtures  # noqa: E402

FIXTURES_DIR = ROOT / "skills/inquisitor/evals/fixtures"


def _gt_descs(repo_dir) -> list:
    gt_path = pathlib.Path(repo_dir) / "ground-truth-bugs.json"
    if not gt_path.exists():
        return []
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    return [b["desc"] for b in gt.get("bugs", []) if b.get("desc")]


def _runtime_string_leak_tokens(repo_dir) -> list:
    """M-3 guard: a leak token (`_LEAK_RE`) inside a NON-docstring STRING literal in
    the committed `src/` is a hazard — the strip deliberately does NOT rewrite
    runtime strings (they are data), so such a token would survive into the copy
    AND the strip would have no safe way to scrub it without changing behavior.
    Today there are none (the leak prose lives only in comments/docstrings); this
    fails loud if a future fixture introduces one. Returns a list of violations."""
    violations = []
    for py in sorted((pathlib.Path(repo_dir) / "src").rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        docstring_spans = _fixtures._docstring_spans(text)
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if (tok.type == tokenize.STRING
                    and not _fixtures._in_docstring_span(tok.start, docstring_spans)
                    and _fixtures._LEAK_RE.search(tok.string)):
                violations.append(
                    f"leak token in a NON-docstring string literal {tok.string!r} "
                    f"in {py.relative_to(repo_dir)} (the strip won't scrub it — M-3)")
    return violations


def check_repo(repo_dir) -> list:
    repo_dir = pathlib.Path(repo_dir)
    violations: list = _runtime_string_leak_tokens(repo_dir)
    with tempfile.TemporaryDirectory() as tmp:
        copy = pathlib.Path(tmp) / "repo_copy"
        _fixtures.copy_repo_for_producer(repo_dir, copy)
        try:
            _fixtures._assert_no_leak(copy)
        except AssertionError as e:
            violations.append(str(e))
        # ADVERSARIAL (S-1): the bug DESCRIPTIONS — not just the id token — must be
        # absent. Loaded from the source repo's GT (the copy excludes it), checked
        # WITHOUT _LEAK_RE so the guard is independent of the strip mechanism.
        try:
            _fixtures.assert_no_description_leak(copy, _gt_descs(repo_dir))
        except AssertionError as e:
            violations.append(str(e))
        # behavior-preserving: every stripped source file still compiles
        if not compileall.compile_dir(str(copy / "src"), quiet=1, force=True):
            violations.append(f"stripped src/ no longer compiles: {repo_dir.name}")
    return violations


def main() -> int:
    repos = sorted(p for p in FIXTURES_DIR.glob("*")
                   if (p / "manifest.json").exists()) if FIXTURES_DIR.exists() else []
    if not repos:
        print(f"OK — no seeded fixtures under {FIXTURES_DIR.relative_to(ROOT)} yet.")
        return 0
    any_fail = False
    for repo in repos:
        v = check_repo(repo)
        if v:
            any_fail = True
            print(f"FAIL — {repo.name}:")
            for s in v:
                print(f"  - {s}")
        else:
            print(f"PASS — {repo.name} (producer copy blind: no answer-key path, "
                  f"no leak token, no GT-description prose, src/ still compiles)")
    return 1 if any_fail else 0


# A GT description whose prose is embedded verbatim in the src comment (the F-1
# leak shape: the comment paraphrases the answer key). The id token is also
# present, so a token-only strip would still leak this prose.
_SELFTEST_DESC = "a None or negative delay is passed straight through to the job"


def selftest() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp) / "r"
        (repo / "src" / "pkg").mkdir(parents=True)
        (repo / "src" / "pkg" / "__init__.py").write_text("")
        # leak prose lives in a comment + docstring (as in real fixtures): both the
        # id token AND a verbatim GT-desc window AND a "The fix" sentence.
        (repo / "src" / "pkg" / "m.py").write_text(
            '"""seam exercised here (nt-b1)."""\n'
            'X = 1  # BUG nt-b3: ' + _SELFTEST_DESC + '. The fix clamps it.\n'
            'LABEL = "delay"  # a runtime string literal that must stay intact\n'
            'def f():\n    """' + _SELFTEST_DESC + '"""\n    return X\n')
        # S-2: an IMPLICITLY-CONCATENATED docstring (one logical string, multiple
        # STRING tokens). The id token (`nt-b1`/`BUG`) lives in the 2nd part and the
        # GT-desc prose is SPLIT across the concatenation boundary so no single part
        # holds a 5-word window. A start-position-only strip would leave parts 2+
        # verbatim — both the token guard AND the description guard must still catch
        # it. (`_SELFTEST_DESC` = "a None or negative delay is passed straight
        # through to the job"; split after "negative".)
        (repo / "src" / "pkg" / "concat.py").write_text(
            'def g():\n'
            '    ("a None or negative "\n'
            '     "delay is passed straight through to the job "\n'
            '     "BUG nt-b1 leaked in part two")\n'
            '    return 1\n')
        (repo / "tests").mkdir()
        (repo / "tests" / "conftest.py").write_text("")
        (repo / "exemplars").mkdir()
        (repo / "exemplars" / "nt-b1.py").write_text("# answer key\n")
        (repo / "fixes").mkdir()
        (repo / "fixes" / "nt-b1.patch").write_text("--- a\n+++ b\n")
        (repo / "manifest.json").write_text("{}")
        (repo / "ground-truth-bugs.json").write_text(json.dumps(
            {"bugs": [{"bug_id": "nt-b3", "desc": _SELFTEST_DESC}]}))

        copy = pathlib.Path(tmp) / "copy"
        _fixtures.copy_repo_for_producer(repo, copy)

        m_txt = (copy / "src" / "pkg" / "m.py").read_text()
        if "nt-b" in m_txt or "BUG" in m_txt:
            failures.append(f"strip left a leak token: {m_txt!r}")
        # the bug-describing PROSE (comment + docstring) is gone (F-1)
        if _SELFTEST_DESC in m_txt or "The fix" in m_txt:
            failures.append(f"strip left bug-description prose: {m_txt!r}")
        # code preserved: assignment + function body intact
        if "X = 1" not in m_txt or "return X" not in m_txt:
            failures.append(f"strip changed code: {m_txt!r}")
        # M-3: a NON-docstring string literal (`"delay"`) is NOT touched — it is
        # runtime data, not a comment/docstring. (The strip only removes COMMENT
        # tokens + docstring nodes; it never rewrites a runtime STRING.)
        if 'LABEL = "delay"' not in m_txt:
            failures.append(f"strip altered a non-docstring string literal: {m_txt!r}")
        # S-2: the implicitly-concatenated docstring is removed in FULL — no
        # concatenated part (id token OR split prose) survives, and the function
        # body (`return 1`) is preserved.
        c_txt = (copy / "src" / "pkg" / "concat.py").read_text()
        if "nt-b" in c_txt or "BUG" in c_txt:
            failures.append(f"strip left a concat-docstring leak token: {c_txt!r}")
        if "passed straight through" in c_txt or "negative" in c_txt:
            failures.append(f"strip left concat-docstring prose: {c_txt!r}")
        if "return 1" not in c_txt:
            failures.append(f"strip changed concat-docstring fn code: {c_txt!r}")
        for forbidden in ("exemplars", "fixes", "manifest.json",
                          "ground-truth-bugs.json"):
            if (copy / forbidden).exists():
                failures.append(f"answer-key path {forbidden} leaked into copy")
        # _assert_no_leak passes on the clean copy
        try:
            _fixtures._assert_no_leak(copy)
        except AssertionError as e:
            failures.append(f"_assert_no_leak false-positive on clean copy: {e}")
        # ADVERSARIAL: assert_no_description_leak passes on the clean copy ...
        try:
            _fixtures.assert_no_description_leak(copy, [_SELFTEST_DESC])
        except AssertionError as e:
            failures.append(f"description guard false-positive on clean copy: {e}")
        # ... and FAILS if the bug-description prose is re-introduced (this is the
        # check that, had it existed, would have caught the round-1 F-1 leak —
        # independent of _LEAK_RE, so it is not circular with the strip).
        (copy / "src" / "pkg" / "prose.py").write_text(
            "Y = 2\n# " + _SELFTEST_DESC + "\n")
        try:
            _fixtures.assert_no_description_leak(copy, [_SELFTEST_DESC])
            failures.append("description guard missed re-introduced bug-desc prose")
        except AssertionError:
            pass
        # ... and FAILS on a re-introduced "The fix" phrase
        (copy / "src" / "pkg" / "prose.py").write_text("Y = 2\n# The fix does X\n")
        try:
            _fixtures.assert_no_description_leak(copy, [])
            failures.append("description guard missed re-introduced 'The fix' phrase")
        except AssertionError:
            pass
        (copy / "src" / "pkg" / "prose.py").unlink()
        # _assert_no_leak FAILS when a leak token is re-introduced
        (copy / "src" / "pkg" / "leak.py").write_text("# BUG nt-b9: x\n")
        try:
            _fixtures._assert_no_leak(copy)
            failures.append("_assert_no_leak missed a re-introduced leak token")
        except AssertionError:
            pass
        (copy / "src" / "pkg" / "leak.py").unlink()

        # S-1: the producer-visible tests/ subtree is in scope of BOTH guards. Drop
        # an ANNOTATED test file (leak token + a GT-desc prose window SPLIT across a
        # comment boundary so no single line holds it via the strip + "The fix"
        # marker) into the copy's tests/ and assert both guards now catch it (proving
        # the tests/-scope hole is closed and a strip/guard regression to src/-only
        # would re-open it). The materialized copy strips tests/ too (real path), so
        # we write POST-strip directly into the copy to exercise the guard scope.
        (copy / "tests" / "test_seam.py").write_text(
            "# BUG nt-b3: leak token in a producer-visible test file\n"
            "# " + _SELFTEST_DESC + "\n"
            "# The fix clamps it.\n"
            "def test_x():\n    assert True\n")
        try:
            _fixtures._assert_no_leak(copy)
            failures.append(
                "_assert_no_leak missed a leak token in a tests/ file (S-1 scope hole)")
        except AssertionError as e:
            if "leaks bug-identity token" not in str(e):
                failures.append(
                    f"_assert_no_leak caught tests/ file but NOT via the token guard "
                    f"(scope-widening unproven): {e}")
        try:
            _fixtures.assert_no_description_leak(copy, [_SELFTEST_DESC])
            failures.append(
                "assert_no_description_leak missed GT-desc prose in a tests/ file "
                "(S-1 scope hole)")
        except AssertionError:
            pass
        (copy / "tests" / "test_seam.py").unlink()

        # S-1 belt-and-suspenders: the documented "tests/ = empty dir + conftest.py"
        # invariant is machine-checked — a substantive (non-conftest) tests/ file is
        # flagged by _assert_no_leak even when it carries NO leak token.
        (copy / "tests" / "test_clean.py").write_text(
            "def test_clean():\n    assert 1 + 1 == 2\n")
        try:
            _fixtures._assert_no_leak(copy)
            failures.append(
                "_assert_no_leak missed a non-conftest tests/ file "
                "(tests/-empty-except-conftest invariant unenforced)")
        except AssertionError as e:
            if "non-conftest file" not in str(e):
                failures.append(
                    f"_assert_no_leak flagged a clean tests/ file but not via the "
                    f"tests/-invariant check: {e}")
        (copy / "tests" / "test_clean.py").unlink()
        # ... and a copy whose tests/ holds only conftest.py still passes the guard.
        try:
            _fixtures._assert_no_leak(copy)
        except AssertionError as e:
            failures.append(
                f"_assert_no_leak false-positive on tests/ = conftest.py only: {e}")

    # isolated forbidden-path check
    with tempfile.TemporaryDirectory() as tmp:
        c = pathlib.Path(tmp) / "c"
        (c / "src").mkdir(parents=True)
        (c / "fixes").mkdir()
        try:
            _fixtures._assert_no_leak(c)
            failures.append("_assert_no_leak missed a forbidden fixes/ path")
        except AssertionError:
            pass

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK — copy strips comments+docstrings (code + non-docstring "
          "strings preserved), excludes answer-key paths, and both the token guard "
          "(_assert_no_leak) and the adversarial description guard "
          "(assert_no_description_leak) catch re-introduced leaks in EVERY "
          "producer-visible subtree (src/ AND tests/), with the "
          "tests/-empty-except-conftest invariant machine-checked.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
