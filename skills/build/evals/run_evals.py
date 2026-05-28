"""build-evals harness entry point.

Stage / score / CLI for the build skill eval gate. The harness is split into:

    stage(fixture_id, work_root)  -> StageResult   prepares a tmpdir + env for /build
    score(fixture, workdir)       -> FixtureResult evaluates expectations after /build ran

The harness does NOT drive /build itself — build runs in a separate shell. This keeps
the harness pure and avoids modeling the Crucible orchestrator runtime in Python.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .expectations import CheckContext, check
from .fixture_loader import load_fixture


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


@dataclass
class StageResult:
    fixture_id: str
    workdir: Path
    baseline_sha: str
    env: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "workdir": str(self.workdir),
            "baseline_sha": self.baseline_sha,
            "env": self.env,
        }


@dataclass
class FixtureResult:
    fixture_id: str
    passed: bool
    expectations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "passed": self.passed,
            "expectations": self.expectations,
        }


# ---------------- stage ----------------

def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def stage(fixture_id: str, work_root: Path, fixtures_root: Path | None = None) -> StageResult:
    """Prepare a workdir for a fixture run.

    Steps:
        1. Resolve fixture directory under fixtures_root
        2. Create tmpdir under work_root, copy seed/ in as the project root
        3. git init + add + commit, capture baseline SHA
        4. Write <workdir>/.eval-baseline-sha
        5. Compose env dict (deps on fixture.no_mock and fixture.mode)
    """
    fixtures_root = Path(fixtures_root or FIXTURES_ROOT)
    fixture_dir = fixtures_root / fixture_id
    fixture = load_fixture(fixture_dir)

    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    workdir = work_root / f"{fixture_id}-{uuid.uuid4().hex[:8]}"
    workdir.mkdir()
    # copy seed contents directly into workdir
    _copytree_into(fixture.seed_dir, workdir)
    # set up isolated HOME
    home = workdir / ".home"
    home.mkdir()

    # git init + initial commit
    _git("init", "-q", "-b", "main", cwd=workdir)
    _git("config", "user.email", "build-evals@example.invalid", cwd=workdir)
    _git("config", "user.name", "build-evals", cwd=workdir)
    _git("add", "-A", cwd=workdir)
    _git("commit", "-q", "-m", "seed", cwd=workdir)
    sha = _git("rev-parse", "HEAD", cwd=workdir).stdout.strip()
    (workdir / ".eval-baseline-sha").write_text(sha)

    env: dict[str, str] = {"HOME": str(home)}
    if not fixture.no_mock:
        env["CRUCIBLE_BUILD_EVAL_MOCK_DIR"] = str(fixture.mock_dispatch_dir)
        if fixture.mode is not None:
            env["CRUCIBLE_BUILD_EVAL_MODE"] = fixture.mode
        if fixture.mock_user_input_dir is not None:
            # Present even when empty (b4's dir holds only .gitkeep): build's
            # AskUserQuestion finds no turn-N reply and halts cleanly.
            env["CRUCIBLE_BUILD_EVAL_USER_INPUT_DIR"] = str(fixture.mock_user_input_dir)

    return StageResult(fixture_id=fixture_id, workdir=workdir, baseline_sha=sha, env=env)


def _copytree_into(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


# ---------------- score ----------------

def score(fixture_id: str, build_output_dir: Path, fixtures_root: Path | None = None) -> FixtureResult:
    """Evaluate a fixture's expectations against the on-disk artifacts left by /build."""
    fixtures_root = Path(fixtures_root or FIXTURES_ROOT)
    fixture = load_fixture(fixtures_root / fixture_id)
    workdir = Path(build_output_dir)

    # discover manifest + gate ledger if present
    manifest_path = _find_first(workdir, ["manifest.jsonl"])
    gate_ledger_path = _find_first(workdir, ["build-gate-ledger.md", ".claude/build-gate-ledger.md"])
    baseline_sha_file = workdir / ".eval-baseline-sha"

    ctx = CheckContext(
        workdir=workdir,
        manifest_path=manifest_path,
        gate_ledger_path=gate_ledger_path,
        git_repo=workdir if (workdir / ".git").exists() else None,
        baseline_sha_file=baseline_sha_file if baseline_sha_file.exists() else None,
    )

    expectation_results: list[dict] = []
    overall = True
    for exp in fixture.expectations:
        r = check(exp, ctx)
        expectation_results.append(
            {"type": exp.get("type"), "passed": r.passed, "detail": r.detail, "expectation": exp}
        )
        if not r.passed:
            overall = False
    return FixtureResult(fixture_id=fixture_id, passed=overall, expectations=expectation_results)


def _find_first(root: Path, rel_candidates: list[str]) -> Path | None:
    """Try several relative paths under root; return the first that exists."""
    for rel in rel_candidates:
        p = root / rel
        if p.exists():
            return p
    # also try a recursive find for manifest.jsonl which build writes under a dispatch dir.
    # Sort for deterministic selection when a multi-phase pipeline leaves several.
    if rel_candidates and rel_candidates[0] == "manifest.jsonl":
        hits = sorted(root.rglob("manifest.jsonl"))
        if hits:
            return hits[0]
    return None


# ---------------- CLI ----------------

def _cmd_stage(args: argparse.Namespace) -> int:
    result = stage(args.fixture, Path(args.work_root))
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    result = score(args.fixture, Path(args.build_output))
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.passed else 1


def _cmd_run_all(args: argparse.Namespace) -> int:
    print(
        "run-all is not yet implemented as an in-process orchestration loop.\n"
        "v0.1 design: invoke /build externally per fixture, run `score` for each.\n"
        "See skills/build/evals/README.md for the manual k=3 procedure."
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    print(
        "run is not yet implemented as an in-process orchestration loop.\n"
        "Use `stage` to set up, invoke /build externally, then use `score`."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_evals", description="build skill eval-gate harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("stage", help="prepare workdir + env for a fixture")
    sp.add_argument("--fixture", required=True)
    sp.add_argument("--work-root", default="/tmp/build-evals-work")
    sp.set_defaults(func=_cmd_stage)

    sc = sub.add_parser("score", help="evaluate expectations against a build output dir")
    sc.add_argument("--fixture", required=True)
    sc.add_argument("--build-output", required=True)
    sc.set_defaults(func=_cmd_score)

    sub.add_parser("run-all", help="(stub) explains the manual k=3 procedure").set_defaults(func=_cmd_run_all)
    rn = sub.add_parser("run", help="(stub) explains the per-fixture procedure")
    rn.add_argument("--fixture", required=True)
    rn.set_defaults(func=_cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
