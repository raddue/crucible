#!/usr/bin/env python3
"""#488 c1 — inquisitor, **Regression** dimension.

"Did we break anything that used to work?" over the WHOLE #488 c1 build
(`fa108d2..HEAD`), not over any one task's diff.

The **linter's observable verdicts**: four parser changes (T3/T10's `(none)`
anchoring, AC-2's ARTIFACTS lexical grammar), two Tier-2 legs gaining
emission sites (T2's `PROVENANCE-ONLY:`, T7's `RESOLVED-BY-WALK:`) and a new
census field (`resolved-by-walk`) all land on one CLI. The question a
per-task tester cannot ask is whether the COMBINATION moves any receipt's
exit code, any `--eval` byte, or any census field name relative to the
pre-#488 linter. These tests replay the shipped corpora through BOTH builds
and compare.

(Two earlier vectors here — the gate-coupling findings, `dec31_sweep.py`
reddening the whole suite on an appended test, and a stale-anchor abort
silently dropping mutation rows — were fixed and their regression tests
promoted to `scripts/test_dec31_sweep_harness.py`, which IS gated.)

Run from repo root: `python3 scripts/test_488_regression_inquisitor.py`.
Wired into `scripts/run_tests.sh`.
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent

# The merge-base of `fix/488-c1-receipt-name-space` with `main` — the last commit
# BEFORE any of this build's eight tasks. Every differential below is against the
# `scripts/rcpt_verify.py` blob at this ref, read out of git rather than kept as a
# committed copy so it cannot drift from what the branch actually forked from.
BASE_REF = "fa108d2"

_CENSUS_RE = re.compile(r"^TIER2-COVERAGE: (.*)$", re.M)


def _git(*args):
    """`git <args>` from the repo root, or None when git/this ref is unavailable."""
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args],
                           capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def _run(script, args, stdin=None, cwd=None, timeout=900):
    p = subprocess.run([sys.executable, str(script), *args], input=stdin,
                       capture_output=True, text=True, cwd=cwd, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _census_fields(stderr):
    """The census line's counter NAMES, in printed order. The parenthetical reason
    codes are stripped, so a run that records a code and one that does not compare
    equal — this is the FIELD LIST, which is the parsed contract
    (`skills/shared/return-convention.md`, `TIER2-COVERAGE:`), not the values."""
    m = _CENSUS_RE.search(stderr)
    if not m:
        return None
    body = re.sub(r"\([^)]*\)", "", m.group(1))
    return re.findall(r"(?:^| )([a-z][a-z-]*) \d+", body)


class _BaselineLinter:
    """The pre-#488 `scripts/rcpt_verify.py`, materialised from git once."""

    _path = None
    _tried = False

    @classmethod
    def path(cls):
        if not cls._tried:
            cls._tried = True
            blob = _git("show", f"{BASE_REF}:scripts/rcpt_verify.py")
            if blob:
                d = pathlib.Path(tempfile.mkdtemp(prefix="rcpt-base-"))
                p = d / "rcpt_verify_base.py"
                p.write_bytes(blob)
                cls._path = p
        return cls._path


def _need_baseline(case):
    p = _BaselineLinter.path()
    if p is None:
        case.skipTest(f"pre-#488 linter unavailable (no git, or ref {BASE_REF} absent)")
    return p


def _head_tree(case):
    """An isolated checkout of HEAD. HEAD, not the working tree, so a concurrent
    editor cannot make these two tests non-deterministic."""
    blob = _git("archive", "HEAD")
    if blob is None:
        case.skipTest("git archive HEAD unavailable")
    d = pathlib.Path(tempfile.mkdtemp(prefix="rcpt-head-"))
    tar = subprocess.run(["tar", "-x", "-C", str(d)], input=blob, capture_output=True)
    if tar.returncode != 0:
        case.skipTest("could not extract git archive HEAD")
    if not (d / "scripts/dec31_sweep.py").is_file():
        case.skipTest("scripts/dec31_sweep.py absent at HEAD")
    return d


def _sweep(tree):
    return _run(tree / "scripts/dec31_sweep.py", [], cwd=str(tree))


class TestNoShippedReceiptChangesItsVerdictAgainstThePre488Linter(unittest.TestCase):
    """ATTACK VECTOR 3 — the build's headline regression question, asked across
    every task at once. Four parser changes and two Tier-2 legs moved; the shipped
    corpora are what the pre-#488 linter's behaviour was DEFINED by
    (`--selftest` is built from `tier2-fixtures/`, and `eval/` is the frozen
    measurement corpus). If any of them changes exit code or stdout verdict under
    the combined build, some receipt that used to lint one way now lints another.

    Deliberately NOT an assertion about stderr: T2 and T7 add `PROVENANCE-ONLY:`
    and `RESOLVED-BY-WALK:` advisory lines and the census gained a field, all of
    which are intended additive changes to that stream. What must not move is the
    DECIDED part — the exit code an orchestrator branches on and the per-record
    verdict `--eval` prints.

    Runs both legs under `--strict` as well, because `--strict` is the mandated
    invocation (`skills/quality-gate/SKILL.md:30`) and it is the mode in which the
    new emission sites sit ahead of a raise."""

    def _tier1_receipts(self):
        out = []
        for f in sorted((REPO / "eval/ledger-return-protocol").rglob("*.jsonl")):
            for i, line in enumerate(f.read_text().splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                r = rec.get("receipt")
                if isinstance(r, str) and "RCPT v1" in r:
                    out.append((f"{f.relative_to(REPO)}:{i}", r))
        return out

    def test_tier1_exit_codes_and_verdicts_are_unchanged(self):
        base = _need_baseline(self)
        receipts = self._tier1_receipts()
        self.assertGreater(len(receipts), 20, "corpus scan found almost nothing")
        moved = []
        for label, r in receipts:
            o = _run(base, ["--tier1", "-"], r)
            n = _run(REPO / "scripts/rcpt_verify.py", ["--tier1", "-"], r)
            if (o[0], o[1]) != (n[0], n[1]):
                moved.append(f"{label}: old rc={o[0]} {o[1]!r} -> new rc={n[0]} {n[1]!r}")
        self.assertEqual(moved, [], "\n".join(moved))

    def test_tier2_fixture_exit_codes_are_unchanged(self):
        base = _need_baseline(self)
        fx = REPO / "eval/ledger-return-protocol/tier2-fixtures"
        if not (fx / "manifest.jsonl").is_file():
            self.skipTest("tier2 fixture manifest absent")
        moved, seen = [], 0
        for line in (fx / "manifest.jsonl").read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            roots = rec.get("roots") or rec.get("root")
            roots = [roots] if isinstance(roots, str) else list(roots or [])
            for strict in (False, True):
                args = ["--tier2"] + (["--strict"] if strict else [])
                for r in roots:
                    args += ["--root", str(fx / r)]
                args.append("-")
                seen += 1
                o = _run(base, args, rec["receipt"])
                n = _run(REPO / "scripts/rcpt_verify.py", args, rec["receipt"])
                if (o[0], o[1]) != (n[0], n[1]):
                    moved.append(f"{rec['id']}{' --strict' if strict else ''}: "
                                 f"old rc={o[0]} {o[1]!r} -> new rc={n[0]} {n[1]!r}")
        self.assertGreater(seen, 10, "fixture manifest scan found almost nothing")
        self.assertEqual(moved, [], "\n".join(moved))


class TestTheEvalPathIsByteIdenticalToThePre488Linter(unittest.TestCase):
    """ATTACK VECTOR 4 — `--eval`'s byte-diff contract, which this build names as
    load-bearing in three separate places (`verify_witness`'s docstring, the
    census's "NEVER appears in `_eval_text`" comment, `tier2_artifacts`'s
    "callers that pass None get no notes, which is why --eval and --selftest are
    unaffected"). Every one of those is a claim that a note routed through the new
    `notes_out` out-parameter, or the new census field, cannot reach the `--eval`
    stream.

    Three independent code paths have to hold for that at once — T2's `finally:`
    provenance pass, T5/T7's two `_emit_walk_note` sites, and D8's census — and
    each was added by a different task. The contract is BYTE equality, so this
    test asserts byte equality of stdout, stderr and exit code rather than
    verdict equality: an extra blank line would break a downstream `diff` just as
    surely as a changed verdict."""

    def test_every_shipped_eval_corpus_is_byte_identical(self):
        base = _need_baseline(self)
        corpora = sorted(p for p in (REPO / "eval/ledger-return-protocol").rglob("*.jsonl")
                         if "manifest" not in p.name)
        self.assertGreater(len(corpora), 3, "no eval corpora found")
        moved = []
        for c in corpora:
            o = _run(base, ["--eval", str(c)])
            n = _run(REPO / "scripts/rcpt_verify.py", ["--eval", str(c)])
            if o != n:
                moved.append(f"{c.relative_to(REPO)}: rc {o[0]}->{n[0]}, "
                             f"stdout {'same' if o[1] == n[1] else 'DIFFERS'}, "
                             f"stderr {'same' if o[2] == n[2] else 'DIFFERS'}")
        self.assertEqual(moved, [], "\n".join(moved))


class TestTheCensusFieldListIsAppendOnly(unittest.TestCase):
    """ATTACK VECTOR 5 — the `TIER2-COVERAGE:` line is a PARSED channel with a
    named consumer (`skills/quality-gate/SKILL.md:36` branches on it, and
    `:296` captures it verbatim into a durable `round-N-coverage.md`). T7 added a
    counter to `_COV_COUNTERS`, and `render()` emits every member of that tuple in
    order — so the one change that must NOT have ridden along is a rename,
    a reorder, or a drop of any counter that was already there. Any of the three
    breaks a stored capture and every reader written against the old field list,
    silently, because the line still parses.

    Asserted at CLI level on the field NAMES the two builds actually print (reason
    codes stripped), not by importing `_COV_COUNTERS` — the tuple is an
    implementation detail, the rendered line is the contract. Old order must
    survive as a subsequence, and exactly one name may be new."""

    def _census(self, script, fx_dir, rec):
        roots = rec.get("roots") or rec.get("root")
        roots = [roots] if isinstance(roots, str) else list(roots or [])
        args = ["--tier2", "--strict"]
        for r in roots:
            args += ["--root", str(fx_dir / r)]
        args.append("-")
        return _census_fields(_run(script, args, rec["receipt"])[2])

    def test_no_counter_was_renamed_reordered_or_dropped(self):
        base = _need_baseline(self)
        fx = REPO / "eval/ledger-return-protocol/tier2-fixtures"
        if not (fx / "manifest.jsonl").is_file():
            self.skipTest("tier2 fixture manifest absent")
        checked = 0
        for line in (fx / "manifest.jsonl").read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            old = self._census(base, fx, rec)
            new = self._census(REPO / "scripts/rcpt_verify.py", fx, rec)
            if old is None or new is None:
                continue    # a `not-reached (...)` render carries no field list
            checked += 1
            # Old order survives as a subsequence of the new order.
            it = iter(new)
            self.assertTrue(all(name in it for name in old),
                            f"{rec['id']}: a counter was renamed, reordered or "
                            f"dropped.\n  old: {old}\n  new: {new}")
            added = [n for n in new if n not in old]
            self.assertEqual(added, ["resolved-by-walk"],
                             f"{rec['id']}: unexpected census field change\n"
                             f"  old: {old}\n  new: {new}")
        self.assertGreater(checked, 5, "no fixture rendered a full census line")


if __name__ == "__main__":
    unittest.main(verbosity=1)
