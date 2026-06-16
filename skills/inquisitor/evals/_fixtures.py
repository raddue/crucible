#!/usr/bin/env python3
"""Variant materialization for the Phase-1b seeded repos (#424).

Pure plumbing shared by the differential oracle (`_oracle.py`) and the
fixture-build invariant checker (`scripts/check_fixture_independence.py`). Given
a fixture repo dir, materialize the `base` / `all-fixed` / `all-fixed-minus-Bᵢ`
variant classes (design §3, §4) by copying the tree and applying the per-bug
`fixes/<bug_id>.patch` files.

Patches are authored against the committed base and touch disjoint files / base
line-ranges (the §3 HARD rule), so they compose order-independently and
zero-fuzz. We apply with `patch -p1 -F0` (fuzz disabled) and fail loud on any
reject — never apply with offset/fuzz, which would silently corrupt attribution.
`patch` (not `git apply`) so the temp copy needs no git repo.
"""
import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_MANIFEST_KEYS = ("repo_id", "pkg", "test_dir", "runner_cmd", "bug_ids", "n")


def load_manifest(repo_dir) -> dict:
    """Read + validate `<repo_dir>/manifest.json`."""
    repo_dir = Path(repo_dir)
    manifest = json.loads((repo_dir / "manifest.json").read_text())
    for key in _MANIFEST_KEYS:
        if key not in manifest:
            raise ValueError(f"manifest missing key: {key!r} ({repo_dir})")
    if len(manifest["bug_ids"]) != manifest["n"]:
        raise ValueError(
            f"manifest n={manifest['n']} != len(bug_ids)="
            f"{len(manifest['bug_ids'])} ({repo_dir})")
    return manifest


def materialize_variant(repo_dir, *, apply=None, exclude=None) -> str:
    """Copy `repo_dir` to a fresh temp dir and apply (set(apply) - set(exclude))
    of the per-bug patches, in deterministic manifest `bug_ids` order.

    Returns the temp dir path; the caller owns cleanup (or use `variant(...)`).
    Raises on an unknown bug_id (not in the manifest) or any patch reject.
    """
    repo_dir = Path(repo_dir)
    manifest = load_manifest(repo_dir)
    bug_ids = manifest["bug_ids"]

    surviving = set(apply or ()) - set(exclude or ())
    unknown = surviving - set(bug_ids)
    if unknown:
        raise ValueError(f"unknown bug_id(s): {sorted(unknown)} ({repo_dir})")
    # deterministic order = manifest bug_ids order
    ordered = [b for b in bug_ids if b in surviving]

    tmp = tempfile.mkdtemp(prefix=f"variant-{manifest['repo_id']}-")
    shutil.copytree(repo_dir, tmp, dirs_exist_ok=True)

    for bid in ordered:
        patch_path = repo_dir / "fixes" / f"{bid}.patch"
        if not patch_path.exists():
            raise FileNotFoundError(f"missing patch for {bid}: {patch_path}")
        proc = subprocess.run(
            ["patch", "-p1", "-F0", "-i", str(patch_path)],
            cwd=tmp, capture_output=True, text=True)
        if proc.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(
                f"patch {bid} failed (rc={proc.returncode}) in {repo_dir.name}:\n"
                f"{proc.stdout}\n{proc.stderr}")
    return tmp


def base(repo_dir) -> str:
    """Materialize the as-committed base (every seeded bug live)."""
    return materialize_variant(repo_dir, apply=[])


def all_fixed(repo_dir) -> str:
    """Materialize base + every patch (the fully-corrected repo)."""
    return materialize_variant(repo_dir, apply=load_manifest(repo_dir)["bug_ids"])


def all_fixed_minus(repo_dir, bug_id) -> str:
    """Materialize base + every patch EXCEPT bug_id's (only bug_id live)."""
    return materialize_variant(
        repo_dir, apply=load_manifest(repo_dir)["bug_ids"], exclude=[bug_id])


@contextlib.contextmanager
def variant(repo_dir, *, apply=None, exclude=None):
    """Context-manager form of materialize_variant: yields the dir, then removes it."""
    d = materialize_variant(repo_dir, apply=apply, exclude=exclude)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- Test runner against a materialized variant (shared by the oracle and the
#     fixture-independence checker) --------------------------------------------

def rc_to_verdict(rc: int) -> str:
    """Canonical pytest rc -> verdict mapping (design §4 / M2 truth table).

        0 -> GREEN   (all tests pass)
        1 -> RED     (a test failed = a bug was caught)
        2,3,4,5,* -> ERROR   (interrupted / internal / usage / NO TESTS COLLECTED)

    rc 5 (no tests collected — an empty/mis-named harvested file) is ERROR, NOT
    green: an empty test catches nothing, and counting it green would silently
    credit a WITHOUT failure mode. ERROR is distinct from both GREEN and RED.
    """
    if rc == 0:
        return "GREEN"
    if rc == 1:
        return "RED"
    return "ERROR"


def run_test_in_dir(variant_dir, test_file, manifest) -> str:
    """Run a single pytest `test_file` against an ALREADY-materialized variant.

    Copies the file into the variant's `test_dir` as a probe (the variant's
    conftest puts `src/` on sys.path), runs `runner_cmd --tb=no <probe>` with
    cwd=variant, and maps the rc via `rc_to_verdict`. The caller owns the
    variant lifecycle (materialize once, run many tests, clean up), so the
    oracle can re-use one `all-fixed` / `minus-Bᵢ` copy across many tests.
    """
    variant_dir = Path(variant_dir)
    test_dir = variant_dir / manifest["test_dir"]
    test_dir.mkdir(parents=True, exist_ok=True)
    # Unique probe name per run: reusing one name lets Python load a STALE .pyc
    # for the next probe (mtime-granularity collision), silently running the
    # previous test. Unique names + no-bytecode keep each run hermetic.
    fd, probe_path = tempfile.mkstemp(suffix=".py", prefix="test_probe_", dir=str(test_dir))
    os.close(fd)
    probe = Path(probe_path)
    shutil.copyfile(test_file, probe)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        runner = list(manifest["runner_cmd"])
        proc = subprocess.run(
            runner + ["--tb=no", str(probe)],
            cwd=str(variant_dir), capture_output=True, text=True, env=env)
        return rc_to_verdict(proc.returncode)
    finally:
        probe.unlink(missing_ok=True)
