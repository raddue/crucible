#!/usr/bin/env python3
"""Grudge privacy + cross-repo isolation.

Covers O-6 (default store under ~/.claude/crucible/grudge), O-6b (append refuses
to write into the current repo's tree), O-6c (committed fixture is synthetic-only),
O-7 (same-basename repos are isolated by repo_root).
"""
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import grudge_append as ga  # noqa: E402
import grudge_query as gq  # noqa: E402

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def test_default_dir_outside_repo():
    saved = os.environ.pop("CRUCIBLE_GRUDGE_DIR", None)
    try:
        d = ga.default_base_dir()
        expected = os.path.join(os.path.expanduser("~"), ".claude", "crucible", "grudge")
        _check("O-6 default store is ~/.claude/crucible/grudge", d == expected, f"d={d}")
        # and it is not inside this repo's tree
        _check("O-6 default store is not inside the crucible repo",
               not ga._is_inside(d, REPO_ROOT))
    finally:
        if saved is not None:
            os.environ["CRUCIBLE_GRUDGE_DIR"] = saved


def test_privacy_guard_refuses_in_repo():
    repo_root = os.path.realpath(tempfile.mkdtemp(prefix="grudge-repo-"))
    try:
        os.makedirs(os.path.join(repo_root, "src"))
        with open(os.path.join(repo_root, "src", "x.py"), "w") as fh:
            fh.write("x\n")
        # base_dir INSIDE the repo -> must refuse
        in_repo_base = os.path.join(repo_root, ".crucible", "grudge")
        path = ga.append(symptom="leaky", files_touched=["src/x.py"], repo="r",
                         repo_root=repo_root, base_dir=in_repo_base)
        _check("O-6b append refuses to write into the repo tree", path is None, f"path={path}")
        gdir = ga.grudges_dir("r", in_repo_base)
        wrote = os.path.isdir(gdir) and any(f.endswith(".md") for f in os.listdir(gdir))
        _check("O-6b nothing was written inside the repo", not wrote)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_fixture_is_synthetic():
    fdir = os.path.join(REPO_ROOT, ".crucible", "grudge", "grudges")
    files = [os.path.join(fdir, f) for f in os.listdir(fdir)] if os.path.isdir(fdir) else []
    _check("O-6c at least one committed fixture exists", len(files) >= 1)
    leaks = [r"/home/[a-z]", r"/Users/[A-Za-z]", r"AKIA[0-9A-Z]{16}",
             r"BEGIN [A-Z ]*PRIVATE KEY", r"password\s*=", r"secret\s*="]
    bad = []
    for fp in files:
        with open(fp, "r", encoding="utf-8") as fh:
            text = fh.read()
        for pat in leaks:
            if re.search(pat, text):
                bad.append((os.path.basename(fp), pat))
    _check("O-6c fixtures contain no real paths/secrets", not bad, f"leaks={bad}")


def test_same_basename_isolation():
    pa = tempfile.mkdtemp(prefix="grudge-pa-")
    pb = tempfile.mkdtemp(prefix="grudge-pb-")
    base = os.path.realpath(tempfile.mkdtemp(prefix="grudge-store-"))
    try:
        rootA = os.path.realpath(os.path.join(pa, "proj"))
        rootB = os.path.realpath(os.path.join(pb, "proj"))  # SAME basename "proj"
        for r in (rootA, rootB):
            os.makedirs(os.path.join(r, "src"))
            with open(os.path.join(r, "src", "x.py"), "w") as fh:
                fh.write("x\n")
        # grudge recorded under repo A only (cosmetic dir "proj" shared by both)
        ga.append(symptom="A-only bug", files_touched=["src/x.py"], repo="proj",
                  repo_root=rootA, base_dir=base)
        mA, _ = gq.query(["src/x.py"], "proj", rootA, base_dir=base)
        mB, _ = gq.query(["src/x.py"], "proj", rootB, base_dir=base)
        _check("O-7 repo A sees its own grudge", bool(mA))
        _check("O-7 same-basename repo B does NOT see repo A's grudge", not mB)
    finally:
        shutil.rmtree(pa, ignore_errors=True)
        shutil.rmtree(pb, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def main():
    test_default_dir_outside_repo()
    test_privacy_guard_refuses_in_repo()
    test_fixture_is_synthetic()
    test_same_basename_isolation()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
