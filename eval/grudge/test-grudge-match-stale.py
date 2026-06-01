#!/usr/bin/env python3
"""Grudge signature matching + staleness.

Covers O-2 (regex signature match), O-2b (invalid regex degrades to literal,
no crash), O-5 (per-path staleness: survives on partial survival, skipped +
culled when all files gone).
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
    base = os.path.realpath(tempfile.mkdtemp(prefix="grudge-store-"))
    return repo_root, base


def _write(repo_root, rel, content="x\n"):
    p = os.path.join(repo_root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(content)


def test_signature_match():
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/other.py")  # grudge's own file (survives)
        _write(repo_root, "src/new.py", "x = FORBIDDEN_CALL(1)\n")
        ga.append(symptom="forbidden call reintroduced", files_touched=["src/other.py"],
                  anti_pattern_signature=r"FORBIDDEN_CALL\(", repo="r",
                  repo_root=repo_root, base_dir=base)
        # path does NOT match (new.py vs other.py); signature does, with the flag
        m_off, _ = gq.query(["src/new.py"], "r", repo_root, base_dir=base, with_signatures=False)
        _check("O-2 signature NOT checked without flag", not m_off)
        m_on, _ = gq.query(["src/new.py"], "r", repo_root, base_dir=base, with_signatures=True)
        _check("O-2 regex signature matches file contents", bool(m_on))
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_invalid_regex_degrades():
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/other.py")
        _write(repo_root, "src/code.py", "value = foo(bar + 1\n")  # contains literal 'foo(bar'
        ga.append(symptom="bad pattern", files_touched=["src/other.py"],
                  anti_pattern_signature="foo(bar", repo="r",  # invalid regex (unbalanced paren)
                  repo_root=repo_root, base_dir=base)
        try:
            m, _ = gq.query(["src/code.py"], "r", repo_root, base_dir=base, with_signatures=True)
            crashed = False
        except Exception as e:  # noqa: BLE001
            crashed = True
            m = []
            print(f"   (crashed: {e})")
        _check("O-2b invalid regex does not crash", not crashed)
        _check("O-2b invalid regex degrades to literal substring match", bool(m))
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_staleness_per_path_and_cull():
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/a.py")
        _write(repo_root, "src/b.py")
        ga.append(symptom="two-file bug", files_touched=["src/a.py", "src/b.py"],
                  repo="r", repo_root=repo_root, base_dir=base)
        # both exist: matches a
        m1, _ = gq.query(["src/a.py"], "r", repo_root, base_dir=base)
        _check("O-5 both files present -> match", bool(m1))
        # delete a: still survives via b
        os.remove(os.path.join(repo_root, "src/a.py"))
        m2, _ = gq.query(["src/b.py"], "r", repo_root, base_dir=base)
        _check("O-5 partial survival -> still match on survivor", bool(m2))
        # querying the deleted file must NOT match (it's gone)
        m_dead, _ = gq.query(["src/a.py"], "r", repo_root, base_dir=base)
        _check("O-5 deleted file no longer matches", not m_dead)
        # delete b too: no survivors -> skipped on read
        os.remove(os.path.join(repo_root, "src/b.py"))
        m3, stats = gq.query(["src/b.py"], "r", repo_root, base_dir=base)
        _check("O-5 all files gone -> skipped on read", not m3 and stats["skipped_stale"] == 1,
               f"stats={stats}")
        # cull removes it
        removed = gq.cull("r", repo_root, base_dir=base)
        d = ga.grudges_dir("r", base)
        remaining = len([x for x in os.listdir(d) if x.endswith(".md")])
        _check("O-5 cull removes settled grudge", len(removed) == 1 and remaining == 0,
               f"removed={removed} remaining={remaining}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def main():
    test_signature_match()
    test_invalid_regex_degrades()
    test_staleness_per_path_and_cull()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
