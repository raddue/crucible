#!/usr/bin/env python3
"""Grudge core: live write->read hit-rate, normalization, no-false-positive, dedupe.

Covers O-1 (live path hit-rate >=3/5), O-1b (path normalization), O-3 (no false
positive + glob-no-cross-slash), O-4 (idempotent append, commit not in key),
O-4b (empty-discriminator falls back to symptom).
"""
import os
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


def _mk_repo():
    repo_root = os.path.realpath(tempfile.mkdtemp(prefix="grudge-repo-"))
    base = os.path.realpath(tempfile.mkdtemp(prefix="grudge-store-"))  # outside repo
    return repo_root, base


def _touch(repo_root, rel):
    p = os.path.join(repo_root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write("x\n")


def test_live_hitrate():
    repo_root, base = _mk_repo()
    try:
        files = [f"src/mod{i}.py" for i in range(5)]
        for i, f in enumerate(files):
            _touch(repo_root, f)
            ga.append(symptom=f"bug {i}", files_touched=[f], repo="myrepo",
                      repo_root=repo_root, base_dir=base, fixed_in_commit=f"c{i}")
        catches = 0
        for f in files:
            matched, _ = gq.query([f], "myrepo", repo_root, base_dir=base)
            if matched:
                catches += 1
        _check("O-1 live write->read hit-rate >=3/5", catches >= 3, f"catches={catches}")
        _check("O-1 all 5 caught", catches == 5, f"catches={catches}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_normalization():
    repo_root, base = _mk_repo()
    try:
        _touch(repo_root, "src/auth/token.py")
        ga.append(symptom="null session", files_touched=["src/auth/token.py"],
                  repo="r", repo_root=repo_root, base_dir=base)
        forms = [
            os.path.join(repo_root, "src/auth/token.py"),  # absolute
            "./src/auth/token.py",                          # ./-prefixed
            "src/auth/token.py",                            # repo-relative
        ]
        for form in forms:
            matched, _ = gq.query([form], "r", repo_root, base_dir=base)
            _check(f"O-1b normalized match: {form[:24]!r}", bool(matched))
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_no_false_positive_and_glob():
    repo_root, base = _mk_repo()
    try:
        _touch(repo_root, "src/auth/token.py")
        _touch(repo_root, "src/db/conn.py")
        _touch(repo_root, "src/deep/sub/x.py")
        # exact grudge on token.py
        ga.append(symptom="bug", files_touched=["src/auth/token.py"],
                  repo="r", repo_root=repo_root, base_dir=base)
        m, _ = gq.query(["src/db/conn.py"], "r", repo_root, base_dir=base)
        _check("O-3 unrelated file -> no match", not m)

        # glob grudge: src/deep/* must NOT cross / into src/deep/sub/x.py
        ga.append(symptom="glob bug", files_touched=["src/deep/*"],
                  repo="r", repo_root=repo_root, base_dir=base)
        _touch(repo_root, "src/deep/y.py")
        m_deep, _ = gq.query(["src/deep/sub/x.py"], "r", repo_root, base_dir=base)
        _check("O-3 glob * does not cross /", not m_deep)
        m_shallow, _ = gq.query(["src/deep/y.py"], "r", repo_root, base_dir=base)
        _check("O-3 glob matches same-depth", bool(m_shallow))
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_idempotent_commit_not_in_key():
    repo_root, base = _mk_repo()
    try:
        _touch(repo_root, "src/mod.py")
        ga.append(symptom="same bug", files_touched=["src/mod.py"], repo="r",
                  repo_root=repo_root, base_dir=base, fixed_in_commit="aaaaaaa")
        ga.append(symptom="same bug", files_touched=["src/mod.py"], repo="r",
                  repo_root=repo_root, base_dir=base, fixed_in_commit="bbbbbbb")
        d = ga.grudges_dir("r", base)
        n = len([x for x in os.listdir(d) if x.endswith(".md")])
        _check("O-4 same bug, two commits -> one file", n == 1, f"n={n}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_empty_discriminator_falls_back_to_symptom():
    repo_root, base = _mk_repo()
    try:
        _touch(repo_root, "src/mod.py")
        ga.append(symptom="bug A", files_touched=["src/mod.py"], repo="r",
                  repo_root=repo_root, base_dir=base, fixed_in_commit="aaaaaaa")
        ga.append(symptom="bug B", files_touched=["src/mod.py"], repo="r",
                  repo_root=repo_root, base_dir=base, fixed_in_commit="aaaaaaa")
        d = ga.grudges_dir("r", base)
        n = len([x for x in os.listdir(d) if x.endswith(".md")])
        _check("O-4b two bugs/one commit/no sig -> two files (symptom keys)", n == 2, f"n={n}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def main():
    test_live_hitrate()
    test_normalization()
    test_no_false_positive_and_glob()
    test_idempotent_commit_not_in_key()
    test_empty_discriminator_falls_back_to_symptom()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
