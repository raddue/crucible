#!/usr/bin/env python3
"""Blind-boundary provenance check for the Phase-1b seeded-repo ground truth (#424, §3/§9).

Invocation (from repo root):
    python3 scripts/check_fixture_gt_provenance.py            # check the fixtures
    python3 scripts/check_fixture_gt_provenance.py --selftest # built-in logic tests

This is a NEW checker, distinct from scripts/check_ground_truth_provenance.py: the
Phase-1 check hardcodes evals.json and asserts no-evals.json-prose, which is
irrelevant to the Phase-1b seeded repos (they have no relationship to evals.json).
The Phase-1b blind boundary is "blind to the **dimension taxonomy**" — a different
leak set entirely. For each fixtures/<repo>/ this asserts:

  (a) the provenance file leaks NONE of the lensed dimension titles or the four
      arm/treatment names (the blind boundary held);
  (b) every GT bug_id has a matching fixes/<id>.patch and exemplars/<id>.py, GT
      fix_patch points at that patch, and GT bug_ids == manifest bug_ids;
  (c) the off_axis tagging is recorded as a POST-BLIND pass by a DISJOINT role.

Leak set (matched case-sensitively — these are the exact taxonomy/treatment
spellings; ordinary lowercase prose like "with"/"integration" is NOT a leak):
  dimension titles: Wiring / Integration / Edge Cases / State & Lifecycle / Regression
  arm names:        WITH / POOL / MID / WITHOUT

Stdlib only. Exit 0 clean / 1 on any violation.
"""
from __future__ import annotations
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skills.inquisitor.evals import _fixtures  # noqa: E402

FIXTURES_DIR = ROOT / "skills/inquisitor/evals/fixtures"

_DIM_TITLES = ("Wiring", "Integration", "Edge Cases", "State & Lifecycle", "Regression")
_ARM_RE = re.compile(r"\b(WITH|WITHOUT|POOL|MID)\b")
# (c): markers that record the post-blind, disjoint-role off_axis pass
_POSTBLIND_MARKERS = ("off_axis", "post-blind", "disjoint")


def leak_tokens(text: str) -> list:
    """Return the dimension-taxonomy / arm-treatment tokens that leaked."""
    found = [t for t in _DIM_TITLES if t in text]
    found += sorted(set(_ARM_RE.findall(text)))
    return found


def check_provenance_text(text: str) -> list:
    """(a) leak scan + (c) post-blind off_axis recording, over provenance text."""
    violations = []
    leaked = leak_tokens(text)
    if leaked:
        violations.append("blind boundary leaked taxonomy/treatment tokens: "
                          + ", ".join(repr(t) for t in leaked))
    missing = [m for m in _POSTBLIND_MARKERS if m not in text]
    if missing:
        violations.append("off_axis pass not recorded as post-blind/disjoint "
                          f"(missing markers: {missing})")
    return violations


def check_correspondence(repo_dir) -> list:
    """(b) GT bug_id <-> patch <-> exemplar <-> manifest correspondence."""
    repo_dir = pathlib.Path(repo_dir)
    violations = []
    try:
        manifest = _fixtures.load_manifest(repo_dir)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        return [f"manifest invalid: {e}"]
    gt = json.loads((repo_dir / "ground-truth-bugs.json").read_text())
    gt_ids = [b["bug_id"] for b in gt["bugs"]]
    if gt_ids != manifest["bug_ids"]:
        violations.append(f"GT bug_ids {gt_ids} != manifest bug_ids "
                          f"{manifest['bug_ids']}")
    for b in gt["bugs"]:
        bid = b["bug_id"]
        if not (repo_dir / "fixes" / f"{bid}.patch").exists():
            violations.append(f"{bid}: missing fixes/{bid}.patch")
        if not (repo_dir / "exemplars" / f"{bid}.py").exists():
            violations.append(f"{bid}: missing exemplars/{bid}.py")
        if b.get("fix_patch") != f"fixes/{bid}.patch":
            violations.append(f"{bid}: GT fix_patch={b.get('fix_patch')!r} "
                              f"!= 'fixes/{bid}.patch'")
    return violations


def check_repo(repo_dir) -> list:
    repo_dir = pathlib.Path(repo_dir)
    prov = repo_dir / "ground-truth-bugs.provenance.md"
    gt = repo_dir / "ground-truth-bugs.json"
    if not prov.exists():
        return [f"missing {prov.name}"]
    if not gt.exists():
        return [f"missing {gt.name}"]
    return check_provenance_text(prov.read_text()) + check_correspondence(repo_dir)


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
            print(f"PASS — {repo.name} (blind boundary held; GT correspondence OK)")
    return 1 if any_fail else 0


def selftest() -> int:
    import tempfile
    failures = []

    clean_prov = (
        "Authored blind to the lensed dimension taxonomy and arm/treatment names.\n"
        "off_axis flags applied in a post-blind pass by a disjoint role.\n")
    if check_provenance_text(clean_prov):
        failures.append(f"clean provenance should pass, got {check_provenance_text(clean_prov)}")

    # leak: an arm token (uppercase, word-boundary)
    if not leak_tokens(clean_prov + "the WITHOUT arm is the baseline\n"):
        failures.append("WITHOUT leak not caught")
    # leak: a dimension title (Title-case)
    if "Wiring" not in leak_tokens(clean_prov + "this is a Wiring defect\n"):
        failures.append("Wiring leak not caught")
    # ordinary lowercase prose is NOT a leak
    if leak_tokens("a job sent without a channel; integration of two modules\n"):
        failures.append("lowercase prose falsely flagged as leak")
    # (c): missing post-blind markers fails
    if not check_provenance_text("authored from source only\n"):
        failures.append("missing post-blind markers should fail")

    # (b): synthetic repo correspondence
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp) / "r"
        (repo / "fixes").mkdir(parents=True)
        (repo / "exemplars").mkdir(parents=True)
        (repo / "fixes" / "x1.patch").write_text("")
        (repo / "exemplars" / "x1.py").write_text("")
        (repo / "manifest.json").write_text(json.dumps(
            {"repo_id": "r", "pkg": "r", "test_dir": "tests",
             "runner_cmd": ["python3", "-m", "pytest", "-q"],
             "bug_ids": ["x1"], "n": 1}))
        (repo / "ground-truth-bugs.json").write_text(json.dumps(
            {"_provenance": "x", "bugs": [
                {"bug_id": "x1", "desc": "d", "off_axis": False,
                 "fix_patch": "fixes/x1.patch"}], "interacting_sets": []}))
        if check_correspondence(repo):
            failures.append(f"matching repo should pass (b), got {check_correspondence(repo)}")
        # break correspondence: GT references a missing patch/exemplar
        (repo / "ground-truth-bugs.json").write_text(json.dumps(
            {"_provenance": "x", "bugs": [
                {"bug_id": "x2", "desc": "d", "off_axis": False,
                 "fix_patch": "fixes/x2.patch"}], "interacting_sets": []}))
        if not check_correspondence(repo):
            failures.append("mismatched bug_id should fail (b)")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST OK — leak scan catches arm/dimension tokens (not lowercase "
          "prose), post-blind markers required, GT correspondence enforced.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
