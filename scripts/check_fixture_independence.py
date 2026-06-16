#!/usr/bin/env python3
"""Fixture behavioral-independence + patch-composition checker (#424 Phase 1b, §3/§9).

Invocation (from repo root):
    python3 scripts/check_fixture_independence.py            # check the real fixtures
    python3 scripts/check_fixture_independence.py --selftest # built-in logic tests (toy repos)

The load-bearing fixture invariant (design §3, S-A): for every seeded repo, every
bug Bᵢ's exemplar test is

    GREEN on all-fixed,  RED on the full-buggy base,
    RED on its own all-fixed-minus-Bᵢ,  and
    GREEN on every *other* all-fixed-minus-Bⱼ (j≠i)   [no co-violable pairs]

plus the patch-composition invariants (M4): each fixes/<bug_id>.patch applies
cleanly to base, all-fixed composes, every all-fixed-minus-Bᵢ applies cleanly, and
each patch touches only its own bug's base lines (pairwise-disjoint hunk ranges).

A genuinely co-violable pair that fixture construction could not avoid MUST be
registered as an `interacting_set` in ground-truth; registered set-mates are
exempted from the green-on-other-minus rule (only among themselves).

Stdlib only. Exit 0 clean / 1 on any violation.
"""
from __future__ import annotations
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skills.inquisitor.evals import _fixtures  # noqa: E402

FIXTURES_DIR = ROOT / "skills/inquisitor/evals/fixtures"

_HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+")


def patch_touched_lines(patch_text: str) -> dict:
    """Map each file -> set of base (old-side) line numbers the patch's hunks touch.

    Presupposes patches are authored against the committed base (A3 HARD rule), so
    the raw `@@ -s,l @@` ranges are directly comparable across patches (M4).
    """
    touched: dict = {}
    cur = None
    for line in patch_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip().split("\t")[0]
            if path[:2] in ("a/", "b/"):
                path = path[2:]
            cur = path
            touched.setdefault(cur, set())
        elif line.startswith("@@") and cur is not None:
            m = _HUNK_RE.search(line)
            if m:
                start = int(m.group(1))
                length = int(m.group(2)) if m.group(2) else 1
                touched[cur].update(range(start, start + length))
    return touched


def _mates(interacting_sets) -> dict:
    """bug_id -> set of co-registered interacting-set mates."""
    mate: dict = {}
    for s in interacting_sets or ():
        for b in s:
            mate.setdefault(b, set()).update(x for x in s if x != b)
    return mate


def _run_matrix(repo_dir, manifest, exemplar) -> dict:
    """Materialize each variant once, run every exemplar in it.

    Returns {(variant_label, bug_id): verdict}; variant_label in
    {"all-fixed", "base", "minus:<bid>"}. Raises on a patch-application failure
    (surfaced as a violation by the caller).
    """
    bug_ids = manifest["bug_ids"]
    verdicts: dict = {}
    with _fixtures.variant(repo_dir, apply=bug_ids) as d:
        for b in bug_ids:
            verdicts[("all-fixed", b)] = _fixtures.run_test_in_dir(d, exemplar[b], manifest)
    with _fixtures.variant(repo_dir, apply=[]) as d:
        for b in bug_ids:
            verdicts[("base", b)] = _fixtures.run_test_in_dir(d, exemplar[b], manifest)
    for k in bug_ids:
        with _fixtures.variant(repo_dir, apply=bug_ids, exclude=[k]) as d:
            for b in bug_ids:
                verdicts[(f"minus:{k}", b)] = _fixtures.run_test_in_dir(d, exemplar[b], manifest)
    return verdicts


def check_repo(repo_dir) -> list:
    """Return a list of human-readable violation strings ([] == clean)."""
    repo_dir = pathlib.Path(repo_dir)
    violations: list = []
    try:
        manifest = _fixtures.load_manifest(repo_dir)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        return [f"manifest invalid: {e}"]
    bug_ids = manifest["bug_ids"]

    gt_path = repo_dir / "ground-truth-bugs.json"
    gt = json.loads(gt_path.read_text()) if gt_path.exists() else {}
    mate = _mates(gt.get("interacting_sets", []))

    # exemplar + patch presence
    exemplar = {}
    for b in bug_ids:
        ex = repo_dir / "exemplars" / f"{b}.py"
        patch = repo_dir / "fixes" / f"{b}.patch"
        if not ex.exists():
            violations.append(f"missing exemplar: exemplars/{b}.py")
        if not patch.exists():
            violations.append(f"missing patch: fixes/{b}.patch")
        exemplar[b] = ex
    if violations:
        return violations

    # M4: each patch touches only its own bug's base lines (pairwise disjoint)
    touched = {b: patch_touched_lines((repo_dir / "fixes" / f"{b}.patch").read_text())
               for b in bug_ids}
    for i in range(len(bug_ids)):
        for j in range(i + 1, len(bug_ids)):
            bi, bj = bug_ids[i], bug_ids[j]
            for f in set(touched[bi]) & set(touched[bj]):
                overlap = touched[bi][f] & touched[bj][f]
                if overlap:
                    violations.append(
                        f"patch line overlap: {bi} and {bj} both touch "
                        f"{f} lines {sorted(overlap)} (cross-bug coupling)")

    # patch-composition: each patch applies to base; all-fixed + every minus compose
    try:
        for b in bug_ids:
            d = _fixtures.materialize_variant(repo_dir, apply=[b]); _rm(d)
        d = _fixtures.materialize_variant(repo_dir, apply=bug_ids); _rm(d)
        for k in bug_ids:
            d = _fixtures.materialize_variant(repo_dir, apply=bug_ids, exclude=[k]); _rm(d)
    except (RuntimeError, FileNotFoundError) as e:
        return violations + [f"patch composition failed: {e}"]

    # behavioral matrix
    try:
        verdicts = _run_matrix(repo_dir, manifest, exemplar)
    except (RuntimeError, FileNotFoundError) as e:
        return violations + [f"variant materialization failed during matrix: {e}"]

    for bi in bug_ids:
        if verdicts[("all-fixed", bi)] != "GREEN":
            violations.append(f"{bi}: exemplar not GREEN on all-fixed "
                              f"(got {verdicts[('all-fixed', bi)]})")
        if verdicts[("base", bi)] != "RED":
            violations.append(f"{bi}: exemplar not RED on full-buggy base "
                              f"(got {verdicts[('base', bi)]})")
        if verdicts[(f"minus:{bi}", bi)] != "RED":
            violations.append(f"{bi}: exemplar not RED on its own all-fixed-minus "
                              f"(got {verdicts[(f'minus:{bi}', bi)]})")
        for bj in bug_ids:
            if bj == bi:
                continue
            if bj in mate.get(bi, set()):
                continue  # registered interacting set-mate: exempt
            if verdicts[(f"minus:{bj}", bi)] != "GREEN":
                violations.append(
                    f"co-violable pair ({bi}, {bj}): {bi}'s exemplar is "
                    f"{verdicts[(f'minus:{bj}', bi)]} on all-fixed-minus-{bj} "
                    f"(expected GREEN; register as an interacting_set if unavoidable)")
    return violations


def _rm(d):
    shutil.rmtree(d, ignore_errors=True)


def _arg(flag):
    args = sys.argv[1:]
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return None


def main() -> int:
    only = _arg("--repo")
    if only is not None:
        repo = pathlib.Path(only)
        if not (repo / "manifest.json").exists():
            repo = FIXTURES_DIR / only
        repos = [repo] if (repo / "manifest.json").exists() else []
        if not repos:
            print(f"FAIL — no manifest.json under {only!r}")
            return 1
    else:
        repos = sorted(p for p in FIXTURES_DIR.glob("*")
                       if (p / "manifest.json").exists()) if FIXTURES_DIR.exists() else []
    if not repos:
        print(f"OK — no seeded fixtures under {FIXTURES_DIR.relative_to(ROOT)} yet.")
        return 0
    any_fail = False
    for repo in repos:
        violations = check_repo(repo)
        if violations:
            any_fail = True
            print(f"FAIL — {repo.name}:")
            for v in violations:
                print(f"  - {v}")
        else:
            print(f"PASS — {repo.name} ({_fixtures.load_manifest(repo)['n']} "
                  "independent bugs)")
    return 1 if any_fail else 0


# --------------------------------------------------------------------------- #
# selftest — toy repos built inline (no real fixture)                          #
# --------------------------------------------------------------------------- #

_CONFTEST = (
    "import pathlib, sys\n"
    "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))\n"
)


def _diff(path, before_text, after_text):
    """Generate a fuzz-0-applicable unified diff (real `diff -u`, a/ b/ headers)."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        a = pathlib.Path(d) / "a"
        b = pathlib.Path(d) / "b"
        a.write_text(before_text)
        b.write_text(after_text)
        out = subprocess.run(["diff", "-u", str(a), str(b)],
                             capture_output=True, text=True).stdout
    lines = out.splitlines()
    return "\n".join([f"--- a/{path}", f"+++ b/{path}"] + lines[2:]) + "\n"


def _build_repo(root: pathlib.Path, files: dict, fixes: dict, exemplars: dict,
                manifest: dict, gt: dict):
    (root / "src").mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "conftest.py").write_text(_CONFTEST)
    (root / "fixes").mkdir(exist_ok=True)
    for bid, patch in fixes.items():
        (root / "fixes" / f"{bid}.patch").write_text(patch)
    (root / "exemplars").mkdir(exist_ok=True)
    for bid, ex in exemplars.items():
        (root / "exemplars" / f"{bid}.py").write_text(ex)
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "ground-truth-bugs.json").write_text(json.dumps(gt))


def selftest() -> int:
    import tempfile
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)

        # --- GOOD repo: 2 independent bugs in disjoint files ---
        good = tmp / "good"
        _build_repo(
            good,
            files={
                "src/toy/__init__.py": "",
                "src/toy/m1.py": "def f():\n    return 1\n",
                "src/toy/m2.py": "def g():\n    return 2\n",
            },
            fixes={
                "b1": _diff("src/toy/m1.py", "def f():\n    return 1\n",
                            "def f():\n    return 10\n"),
                "b2": _diff("src/toy/m2.py", "def g():\n    return 2\n",
                            "def g():\n    return 20\n"),
            },
            exemplars={
                "b1": "from toy.m1 import f\n\ndef test_f():\n    assert f() == 10\n",
                "b2": "from toy.m2 import g\n\ndef test_g():\n    assert g() == 20\n",
            },
            manifest={"repo_id": "good", "pkg": "toy", "test_dir": "tests",
                      "runner_cmd": ["python3", "-m", "pytest", "-q"],
                      "bug_ids": ["b1", "b2"], "n": 2},
            gt={"bugs": [], "interacting_sets": []},
        )
        v = check_repo(good)
        if v:
            failures.append(f"GOOD repo should PASS, got violations: {v}")

        # --- BAD repo: co-violable pair (one assertion fails if either unfixed).
        #     base_a / base_b are deliberately well-SEPARATED so their patch hunks
        #     are line-disjoint (M4 clean) — the only fault is behavioral. ---
        _PAD = "_p1 = 0\n_p2 = 0\n_p3 = 0\n_p4 = 0\n_p5 = 0\n_p6 = 0\n"
        combo_base = ("def base_a():\n    return 1\n\n" + _PAD +
                      "\ndef base_b():\n    return 2\n\n"
                      "def total():\n    return base_a() + base_b()\n")
        combo_a = combo_base.replace("    return 1\n", "    return 10\n", 1)
        combo_b = combo_base.replace("    return 2\n", "    return 20\n", 1)
        bad_files = {"src/toy/__init__.py": "", "src/toy/combo.py": combo_base}
        bad_fixes = {
            "b3a": _diff("src/toy/combo.py", combo_base, combo_a),
            "b3b": _diff("src/toy/combo.py", combo_base, combo_b),
        }
        coviolable_ex = {
            "b3a": "from toy.combo import total\n\ndef test_a():\n    assert total() == 30\n",
            "b3b": "from toy.combo import total\n\ndef test_b():\n    assert total() == 30\n",
        }
        bad = tmp / "bad"
        _build_repo(bad, bad_files, bad_fixes, coviolable_ex,
                    {"repo_id": "bad", "pkg": "toy", "test_dir": "tests",
                     "runner_cmd": ["python3", "-m", "pytest", "-q"],
                     "bug_ids": ["b3a", "b3b"], "n": 2},
                    {"bugs": [], "interacting_sets": []})
        v = check_repo(bad)
        named = any("b3a" in s and "b3b" in s for s in v)
        if not v or not named:
            failures.append(f"BAD repo should FAIL naming (b3a,b3b), got: {v}")

        # --- BAD repo, but pair REGISTERED as interacting_set -> PASS ---
        reg = tmp / "reg"
        _build_repo(reg, bad_files, bad_fixes, coviolable_ex,
                    {"repo_id": "reg", "pkg": "toy", "test_dir": "tests",
                     "runner_cmd": ["python3", "-m", "pytest", "-q"],
                     "bug_ids": ["b3a", "b3b"], "n": 2},
                    {"bugs": [], "interacting_sets": [["b3a", "b3b"]]})
        v = check_repo(reg)
        if v:
            failures.append(f"REGISTERED interacting pair should PASS, got: {v}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK — independent pair PASSES, co-violable pair FAILS (named), "
          "registered interacting_set is exempted.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
