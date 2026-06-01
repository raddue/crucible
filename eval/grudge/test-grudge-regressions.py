#!/usr/bin/env python3
"""Grudge implementation-gate regressions (#271 impl adversarial gate).

Three defects the impl gate found, each with a live regression test:
- O-9  FATAL: a real filename containing glob metachars (Next.js `pages/[id].js`)
       must surface + survive — not be misread as a glob (which finds nothing,
       so the grudge silently never matches AND --cull deletes it).
- O-10 SIGNIFICANT: a frontmatter VALUE (or body) containing `---` must not
       truncate the frontmatter and drop files_touched (silent false-negative).
- O-11 SIGNIFICANT (ReDoS): a catastrophic-backtracking signature must NOT hang
       the pre-flight — it returns under the wall-clock budget, degrading to a
       graceful no-hit (the pre-flight contract is NEVER-block).
"""
import os
import shutil
import sys
import tempfile
import time

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


def test_metachar_filename_surfaces_and_survives():
    """O-9: `pages/[id].js` is a real file (brackets legal + common); it must
    match itself and not be culled."""
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "pages/[id].js")
        ga.append(symptom="dynamic route 500s", files_touched=["pages/[id].js"],
                  repo="r", repo_root=repo_root, base_dir=base)
        m, _ = gq.query(["pages/[id].js"], "r", repo_root, base_dir=base)
        _check("O-9 literal metachar filename matches itself", bool(m),
               "grudge on pages/[id].js did not surface")
        # survival: must NOT be judged stale, and --cull must NOT delete it
        removed = gq.cull("r", repo_root, base_dir=base)
        d = ga.grudges_dir("r", base)
        remaining = len([x for x in os.listdir(d) if x.endswith(".md")])
        _check("O-9 metachar-filename grudge is NOT wrongly culled",
               not removed and remaining == 1,
               f"removed={removed} remaining={remaining}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_intentional_glob_still_works():
    """O-9b: a deliberate glob entry (`src/auth/*`) still matches + survives —
    the literal-first fix must not break the glob feature."""
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/auth/login.py")
        ga.append(symptom="auth-wide bug", files_touched=["src/auth/*"],
                  repo="r", repo_root=repo_root, base_dir=base)
        m, _ = gq.query(["src/auth/login.py"], "r", repo_root, base_dir=base)
        _check("O-9b intentional glob entry still matches a concrete scope file", bool(m))
        # delete the only matching file -> glob no longer survives -> culled
        os.remove(os.path.join(repo_root, "src/auth/login.py"))
        removed = gq.cull("r", repo_root, base_dir=base)
        _check("O-9b stale glob (no matching file left) IS culled", len(removed) == 1,
               f"removed={removed}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_dashes_in_frontmatter_value():
    """O-10: a `---` inside a frontmatter value must not truncate the block."""
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/parser.py")
        ga.append(symptom="parser chokes --- on rule lines",  # value contains ---
                  root_cause="split on --- anywhere",
                  files_touched=["src/parser.py"], repo="r",
                  repo_root=repo_root, base_dir=base)
        m, _ = gq.query(["src/parser.py"], "r", repo_root, base_dir=base)
        _check("O-10 grudge with '---' in a value still surfaces (files_touched intact)",
               bool(m), "frontmatter truncated -> files_touched dropped")
        if m:
            _check("O-10 symptom round-trips with its dashes",
                   "---" in m[0].get("symptom", ""), f"symptom={m[0].get('symptom')!r}")
        else:
            _check("O-10 symptom round-trips with its dashes", False, "no match")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_dashes_in_body():
    """O-10b: a `---` fence inside the repro/why body must not break parsing."""
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/x.py")
        ga.append(symptom="body fence bug", files_touched=["src/x.py"],
                  repro="see diff:\n---\n- old\n+ new\n---\n", repo="r",
                  repo_root=repo_root, base_dir=base)
        m, _ = gq.query(["src/x.py"], "r", repo_root, base_dir=base)
        _check("O-10b grudge with '---' fences in body still surfaces", bool(m))
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_pathological_signature_does_not_hang():
    """O-11 (ReDoS): a catastrophic-backtracking signature returns under budget
    and degrades to a graceful no-hit instead of hanging the pre-flight."""
    repo_root, base = _mk_repo()
    try:
        _write(repo_root, "src/keep.py")  # grudge's own file (survives staleness)
        # target file content that detonates the pathological pattern
        _write(repo_root, "src/target.py", "a" * 60 + "!\n")
        ga.append(symptom="redos", files_touched=["src/keep.py"],
                  anti_pattern_signature=r"(a+)+$", repo="r",
                  repo_root=repo_root, base_dir=base)
        t0 = time.time()
        m, _ = gq.query(["src/target.py"], "r", repo_root, base_dir=base,
                        with_signatures=True)
        elapsed = time.time() - t0
        # Unguarded this never returns; guarded it caps near SIG_MATCH_TIMEOUT_S.
        _check("O-11 pathological signature returns under wall-clock budget",
               elapsed < gq.SIG_MATCH_TIMEOUT_S + 8.0, f"elapsed={elapsed:.2f}s")
        _check("O-11 timed-out signature degrades to a graceful no-hit", not m,
               f"matched={m}")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def main():
    test_metachar_filename_surfaces_and_survives()
    test_intentional_glob_still_works()
    test_dashes_in_frontmatter_value()
    test_dashes_in_body()
    test_pathological_signature_does_not_hang()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
