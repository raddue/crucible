import json
import subprocess
from pathlib import Path

import pytest

from skills.build.evals.expectations import CheckContext, check


def _ctx(workdir: Path, *, manifest: Path | None = None, ledger: Path | None = None,
         baseline_file: Path | None = None) -> CheckContext:
    return CheckContext(
        workdir=workdir,
        manifest_path=manifest,
        gate_ledger_path=ledger,
        git_repo=workdir if (workdir / ".git").exists() else None,
        baseline_sha_file=baseline_file,
    )


# ---- file_exists / file_does_not_exist ----

def test_file_exists_pass(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")
    assert check({"type": "file_exists", "path": "a.py"}, _ctx(tmp_path)).passed


def test_file_exists_fail(tmp_path: Path) -> None:
    assert not check({"type": "file_exists", "path": "missing.py"}, _ctx(tmp_path)).passed


def test_file_does_not_exist_pass(tmp_path: Path) -> None:
    assert check({"type": "file_does_not_exist", "path": "nope.py"}, _ctx(tmp_path)).passed


def test_file_does_not_exist_fail(tmp_path: Path) -> None:
    (tmp_path / "here.py").write_text("x")
    assert not check({"type": "file_does_not_exist", "path": "here.py"}, _ctx(tmp_path)).passed


# ---- file_contains ----

def test_file_contains_pass(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello world")
    assert check({"type": "file_contains", "path": "a.py", "pattern": "world"}, _ctx(tmp_path)).passed


def test_file_contains_missing_file_fails(tmp_path: Path) -> None:
    assert not check({"type": "file_contains", "path": "x", "pattern": "y"}, _ctx(tmp_path)).passed


# ---- function_defined ----

def test_function_defined_top_level(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def get_email(uid):\n    return ''\n")
    assert check({"type": "function_defined", "file": "m.py", "name": "get_email"}, _ctx(tmp_path)).passed


def test_function_defined_async(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("async def fetch():\n    return None\n")
    assert check({"type": "function_defined", "file": "m.py", "name": "fetch"}, _ctx(tmp_path)).passed


def test_function_defined_matches_class(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("class UserService:\n    pass\n")
    assert check({"type": "function_defined", "file": "m.py", "name": "UserService"}, _ctx(tmp_path)).passed


def test_function_defined_matches_method(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("class C:\n    def do_thing(self): pass\n")
    assert check({"type": "function_defined", "file": "m.py", "name": "do_thing"}, _ctx(tmp_path)).passed


def test_function_defined_no_match(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("x = 1\n")
    assert not check({"type": "function_defined", "file": "m.py", "name": "missing"}, _ctx(tmp_path)).passed


def test_function_defined_syntax_error(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def broken(:\n")
    r = check({"type": "function_defined", "file": "m.py", "name": "x"}, _ctx(tmp_path))
    assert not r.passed and "did not parse" in r.detail


# ---- manifest_contains_dispatch / does_not_contain ----

def _write_manifest(p: Path, entries: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_manifest_contains_dispatch_pass(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.jsonl"
    _write_manifest(mf, [{"template": "plan-writer-prompt.md"}, {"template": "implementer-prompt.md"}])
    exp = {"type": "manifest_contains_dispatch", "skill": "plan-writer", "count_min": 1, "count_max": 1}
    assert check(exp, _ctx(tmp_path, manifest=mf)).passed


def test_manifest_contains_dispatch_count_violation(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.jsonl"
    _write_manifest(mf, [{"template": "implementer.md"}, {"template": "implementer.md"}, {"template": "implementer.md"}])
    exp = {"type": "manifest_contains_dispatch", "skill": "implementer", "count_min": 1, "count_max": 2}
    assert not check(exp, _ctx(tmp_path, manifest=mf)).passed


def test_manifest_does_not_contain_pass(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.jsonl"
    _write_manifest(mf, [{"template": "plan-writer"}])
    assert check({"type": "manifest_does_not_contain", "skill": "design"}, _ctx(tmp_path, manifest=mf)).passed


def test_manifest_does_not_contain_fail(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.jsonl"
    _write_manifest(mf, [{"template": "design-prompt.md"}])
    assert not check({"type": "manifest_does_not_contain", "skill": "design"}, _ctx(tmp_path, manifest=mf)).passed


def test_manifest_skips_malformed_lines(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.jsonl"
    mf.write_text('{"template":"plan-writer"}\nNOT JSON\n{"template":"plan-writer"}\n')
    exp = {"type": "manifest_contains_dispatch", "skill": "plan-writer", "count_min": 2, "count_max": 2}
    assert check(exp, _ctx(tmp_path, manifest=mf)).passed


# ---- gate_ledger_phase_status ----

def test_gate_ledger_phase_status_pass(tmp_path: Path) -> None:
    led = tmp_path / "ledger.md"
    led.write_text(
        "# Ledger\n## Phase 1: Design\nStatus: PASS\n\n## Phase 2: Plan\nStatus: NOT_STARTED\n"
    )
    exp = {"type": "gate_ledger_phase_status", "phase": "1", "status": "PASS"}
    assert check(exp, _ctx(tmp_path, ledger=led)).passed


def test_gate_ledger_phase_status_mismatch(tmp_path: Path) -> None:
    led = tmp_path / "ledger.md"
    led.write_text("## Phase 4: Completion\nStatus: NOT_STARTED\n")
    exp = {"type": "gate_ledger_phase_status", "phase": "4", "status": "PASS"}
    assert not check(exp, _ctx(tmp_path, ledger=led)).passed


def test_gate_ledger_missing_phase(tmp_path: Path) -> None:
    led = tmp_path / "ledger.md"
    led.write_text("## Phase 1: Design\nStatus: PASS\n")
    exp = {"type": "gate_ledger_phase_status", "phase": "2", "status": "PASS"}
    assert not check(exp, _ctx(tmp_path, ledger=led)).passed


# ---- working_tree_unchanged_from ----

def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_working_tree_unchanged_pass(tmp_path: Path) -> None:
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "t@x", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("hi")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "seed", cwd=tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / ".eval-baseline-sha").write_text(sha)
    # Eval-harness scaffolding inside the workdir must not read as a build leak.
    home = tmp_path / ".home" / ".claude"
    home.mkdir(parents=True)
    (home / "pipeline-status.md").write_text("build process artifact")
    ctx = _ctx(tmp_path, baseline_file=tmp_path / ".eval-baseline-sha")
    assert check({"type": "working_tree_unchanged_from", "baseline_sha": "BASELINE"}, ctx).passed


def test_working_tree_unchanged_detects_diff(tmp_path: Path) -> None:
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "t@x", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("hi")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "seed", cwd=tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / ".eval-baseline-sha").write_text(sha)
    (tmp_path / "a.txt").write_text("MODIFIED")
    ctx = _ctx(tmp_path, baseline_file=tmp_path / ".eval-baseline-sha")
    assert not check({"type": "working_tree_unchanged_from", "baseline_sha": "BASELINE"}, ctx).passed


def test_working_tree_unchanged_detects_untracked_file(tmp_path: Path) -> None:
    # An untracked new file is the most likely b4-halt failure shape (build leaks
    # a file it created). `git diff` is blind to it, so the check must catch it.
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.email", "t@x", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("hi")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "seed", cwd=tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / ".eval-baseline-sha").write_text(sha)
    (tmp_path / "leaked.py").write_text("# build should not have created this")
    ctx = _ctx(tmp_path, baseline_file=tmp_path / ".eval-baseline-sha")
    r = check({"type": "working_tree_unchanged_from", "baseline_sha": "BASELINE"}, ctx)
    assert not r.passed and "untracked" in r.detail


# ---- error paths ----

def test_unknown_expectation_type(tmp_path: Path) -> None:
    r = check({"type": "nonsense"}, _ctx(tmp_path))
    assert not r.passed and "unknown expectation type" in r.detail


def test_missing_type_field(tmp_path: Path) -> None:
    r = check({}, _ctx(tmp_path))
    assert not r.passed and "missing 'type'" in r.detail
