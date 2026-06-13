#!/usr/bin/env python3
"""Central-store foundation fix — INV-5..INV-9 (#270).

The calibration ledger must capture real cross-repo usage: emit from any cwd,
aggregate to one machine-local store, slice by repo, stay backward-compatible
with the v1 corpus, and degrade gracefully.

Covers (design §Invariants / contract):
  INV-1 default_ledger_dir() returns a ~-rooted path (never inside a git repo)
        when CRUCIBLE_LEDGER_DIR is unset.
  INV-5 `emit` succeeds from a cwd != the script's repo (the core bug).
  INV-6 `emit -` writes to the central default; CRUCIBLE_LEDGER_DIR overrides.
  INV-7 repo auto-populates to the git-toplevel basename inside a git repo;
        cwd basename when not in a git repo; never raises.
  INV-8 mixed v1 (no `repo`, schema_version 1) + v2 rows read/dedup/render
        without error; v1 rows bucket as repo:unknown.
  INV-9 graceful skip: kill-switch and duplicate `emit` both no-op with exit 0.

Plain python3 — no pytest. Builds entries into temp dirs; never touches the
real ~/.claude or the in-repo .crucible/ledger/runs.jsonl.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

SCRIPT = os.path.join(REPO_ROOT, "scripts", "ledger_append.py")

from scripts.ledger_append import (  # noqa: E402
    append,
    caller_dedup,
    default_ledger_dir,
    default_ledger_path,
    default_repo,
)

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def _emit(ledger_arg, entry, *, cwd, extra_env=None):
    """Invoke the `emit` CLI by ABSOLUTE script path from `cwd`. Returns
    CompletedProcess. The absolute-path invocation is the whole point of INV-5:
    no PYTHONPATH, no cwd dependency."""
    env = dict(os.environ)
    env.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
    env.pop("CRUCIBLE_LEDGER_DIR", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, SCRIPT, "emit", ledger_arg, json.dumps(entry)],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _v2(run_id, skill, repo=None):
    e = {
        "schema_version": 2, "run_id": run_id, "skill": skill, "tier": "A",
        "artifact_type": "code", "verdict": "PASS", "confidence": 0.5,
        "would_have_shipped_without_gate": False, "rounds": 1,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
    }
    if repo is not None:
        e["repo"] = repo
    return e


def _v1(run_id, skill):
    """A legacy v1 row: schema_version 1, NO repo key at all."""
    return {
        "schema_version": 1, "run_id": run_id, "skill": skill, "tier": "A",
        "artifact_type": "code", "verdict": "PASS", "confidence": 0.5,
        "would_have_shipped_without_gate": False, "rounds": 1,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
    }


# --------------------------------------------------------------------------- #
# INV-1 — central default is ~-rooted, never inside a git repo
# --------------------------------------------------------------------------- #
def test_default_dir_is_home_rooted():
    saved = os.environ.pop("CRUCIBLE_LEDGER_DIR", None)
    try:
        d = default_ledger_dir()
        home = os.path.expanduser("~")
        _check("INV-1 default_ledger_dir under ~", d.startswith(home), d)
        _check("INV-1 default_ledger_path ends runs.jsonl",
               default_ledger_path().endswith(os.path.join("runs.jsonl")),
               default_ledger_path())
        _check("INV-1 default dir not the cwd tree",
               not d.startswith(os.getcwd()), d)
    finally:
        if saved is not None:
            os.environ["CRUCIBLE_LEDGER_DIR"] = saved


# --------------------------------------------------------------------------- #
# INV-5 / INV-6 — emit from a foreign cwd, central default + env override
# --------------------------------------------------------------------------- #
def test_emit_cwd_independent_and_central():
    with tempfile.TemporaryDirectory(prefix="cs-foreign-") as foreign, \
         tempfile.TemporaryDirectory(prefix="cs-central-") as central:
        central_dir = os.path.join(central, "ledger")
        proc = _emit("-", _v2("uuid-1", "siege", repo="x"),
                     cwd=foreign,
                     extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
        _check("INV-5 emit exits 0 from foreign cwd", proc.returncode == 0,
               f"rc={proc.returncode} stderr={proc.stderr}")
        rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
        _check("INV-6 line landed in CRUCIBLE_LEDGER_DIR central store",
               len(rows) == 1 and rows[0].get("run_id") == "uuid-1",
               f"rows={rows}")


# --------------------------------------------------------------------------- #
# INV-7 — repo auto-population (git basename / cwd fallback / never raises)
# --------------------------------------------------------------------------- #
def test_repo_population_git_and_fallback():
    # never raises, anywhere
    try:
        default_repo("/nonexistent/path/should/not/exist")
        _check("INV-7 default_repo never raises", True)
    except Exception as exc:  # noqa: BLE001
        _check("INV-7 default_repo never raises", False, repr(exc))

    # non-git temp dir -> cwd basename
    with tempfile.TemporaryDirectory(prefix="cs-nogit-") as nogit:
        sub = os.path.join(nogit, "myproj")
        os.makedirs(sub)
        _check("INV-7 non-git -> cwd basename",
               default_repo(sub) == "myproj", default_repo(sub))

    # git repo -> toplevel basename, even from a subdir
    with tempfile.TemporaryDirectory(prefix="cs-git-") as gitparent:
        repo_dir = os.path.join(gitparent, "repo-alpha")
        os.makedirs(os.path.join(repo_dir, "src"))
        try:
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True,
                           capture_output=True)
            got = default_repo(os.path.join(repo_dir, "src"))
            _check("INV-7 git repo -> toplevel basename from subdir",
                   got == "repo-alpha", got)
        except (FileNotFoundError, subprocess.CalledProcessError):
            _check("INV-7 git repo -> toplevel basename (SKIPPED: no git)", True)

    # The emit CLI auto-stamps repo when the entry omits it. Emit from a SUBDIR
    # of the git repo so the git-toplevel basename ("repo-beta") genuinely
    # differs from the cwd basename ("sub") — this exercises which branch fires.
    with tempfile.TemporaryDirectory(prefix="cs-emit-git-") as gp:
        repo_dir = os.path.join(gp, "repo-beta")
        sub_dir = os.path.join(repo_dir, "sub")
        os.makedirs(sub_dir)
        central_dir = os.path.join(gp, "central")
        try:
            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True,
                           capture_output=True)
            ok_git = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            ok_git = False
        proc = _emit("-", _v2("uuid-2", "audit"),  # no repo key
                     cwd=sub_dir,
                     extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
        rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
        # git present -> toplevel basename "repo-beta"; absent -> cwd basename "sub"
        expected = "repo-beta" if ok_git else "sub"
        _check("INV-7 emit auto-stamps repo (git toplevel, not cwd subdir)",
               proc.returncode == 0 and len(rows) == 1
               and rows[0].get("repo") == expected,
               f"ok_git={ok_git} rc={proc.returncode} rows={rows}")

    # And an explicit repo:null in the entry must STILL be auto-filled (the
    # Significant finding: setdefault would have left it null).
    with tempfile.TemporaryDirectory(prefix="cs-emit-null-") as gp:
        central_dir = os.path.join(gp, "central")
        entry = _v2("uuid-3", "siege")
        entry["repo"] = None
        proc = _emit("-", entry, cwd=gp,
                     extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
        rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
        _check("INV-7 explicit repo:null is overwritten, not preserved",
               proc.returncode == 0 and len(rows) == 1
               and rows[0].get("repo") not in (None, ""),
               f"rows={rows}")


# --------------------------------------------------------------------------- #
# INV-8 — mixed v1/v2 read + dedup + render
# --------------------------------------------------------------------------- #
def test_mixed_v1_v2_read_dedup_render():
    with tempfile.TemporaryDirectory(prefix="cs-mixed-") as tmp:
        ledger = os.path.join(tmp, "runs.jsonl")
        ov = os.path.join(tmp, "overflow")
        _check("INV-8 v1 append ok",
               append(ledger, _v1("v1-a", "quality-gate"), overflow_dir=ov))
        _check("INV-8 v2 append ok",
               append(ledger, _v2("v2-a", "siege", repo="repo-alpha"),
                      overflow_dir=ov))
        # caller_dedup tolerates mixed rows
        _check("INV-8 dedup sees v1 row",
               caller_dedup(ledger, "v1-a", "quality-gate") is True)
        _check("INV-8 dedup distinguishes new",
               caller_dedup(ledger, "nope", "siege") is False)

        # renderer reads mixed rows without crashing; v1 buckets as unknown
        from scripts.render_ledger import load_runs, week_summary  # noqa: E402
        try:
            entries = load_runs(ledger)
            summary = week_summary(entries)
            repos = summary.get("per_repo", {})
            ok = (len(entries) == 2
                  and "unknown" in repos
                  and "repo-alpha" in repos)
            _check("INV-8 per_repo buckets v1->unknown, v2->repo", ok,
                   f"per_repo={repos}")
        except Exception as exc:  # noqa: BLE001
            _check("INV-8 mixed render does not crash", False, repr(exc))


# --------------------------------------------------------------------------- #
# INV-9 — graceful skip: kill-switch and duplicate both exit 0, no write
# --------------------------------------------------------------------------- #
def test_graceful_skips():
    with tempfile.TemporaryDirectory(prefix="cs-skip-") as tmp:
        central_dir = os.path.join(tmp, "ledger")
        # kill-switch -> no-op, exit 0, no file
        proc = _emit("-", _v2("ks-1", "siege", repo="x"), cwd=tmp,
                     extra_env={"CRUCIBLE_LEDGER_DIR": central_dir,
                                "CRUCIBLE_CALIBRATION_DISABLED": "1"})
        rows = _read_lines(os.path.join(central_dir, "runs.jsonl"))
        _check("INV-9 kill-switch exits 0", proc.returncode == 0,
               f"rc={proc.returncode}")
        _check("INV-9 kill-switch wrote nothing", rows == [], f"rows={rows}")

        # first real emit, then duplicate -> second skips, exit 0, one row
        _emit("-", _v2("dup-1", "siege", repo="x"), cwd=tmp,
              extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
        proc2 = _emit("-", _v2("dup-1", "siege", repo="x"), cwd=tmp,
                      extra_env={"CRUCIBLE_LEDGER_DIR": central_dir})
        rows2 = _read_lines(os.path.join(central_dir, "runs.jsonl"))
        _check("INV-9 duplicate emit exits 0", proc2.returncode == 0,
               f"rc={proc2.returncode} stderr={proc2.stderr}")
        _check("INV-9 duplicate not appended (1 row)", len(rows2) == 1,
               f"rows={rows2}")


def main():
    test_default_dir_is_home_rooted()
    test_emit_cwd_independent_and_central()
    test_repo_population_git_and_fallback()
    test_mixed_v1_v2_read_dedup_render()
    test_graceful_skips()
    total = len(_results)
    passed = sum(_results)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
