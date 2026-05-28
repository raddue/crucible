"""Expectation checkers for build-evals.

Each expectation is a dict with a 'type' key plus type-specific fields. Pluggable
dispatch via _CHECKERS. New types can be added in v0.2 without touching call sites.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckContext:
    """Runtime context passed to every expectation checker."""
    workdir: Path                       # the staged project root (where source files live)
    manifest_path: Path | None          # build's manifest.jsonl on disk, if reachable
    gate_ledger_path: Path | None       # build's build-gate-ledger.md, if reachable
    git_repo: Path | None               # repo root for git diff operations (usually == workdir)
    baseline_sha_file: Path | None      # <workdir>/.eval-baseline-sha (written by stage)


@dataclass
class CheckResult:
    passed: bool
    detail: str


def check(expectation: dict, ctx: CheckContext) -> CheckResult:
    etype = expectation.get("type")
    if etype is None:
        return CheckResult(False, "expectation missing 'type' field")
    fn = _CHECKERS.get(etype)
    if fn is None:
        return CheckResult(False, f"unknown expectation type: {etype!r}")
    try:
        return fn(expectation, ctx)
    except Exception as e:  # noqa: BLE001 — defensive: an expectation crash should not bring down score()
        return CheckResult(False, f"expectation {etype!r} crashed: {e!r}")


# ---------------- individual checkers ----------------

def _file_exists(exp: dict, ctx: CheckContext) -> CheckResult:
    p = ctx.workdir / exp["path"]
    return CheckResult(p.exists(), f"{exp['path']} {'exists' if p.exists() else 'MISSING'}")


def _file_does_not_exist(exp: dict, ctx: CheckContext) -> CheckResult:
    p = ctx.workdir / exp["path"]
    return CheckResult(not p.exists(), f"{exp['path']} {'absent' if not p.exists() else 'UNEXPECTEDLY PRESENT'}")


def _file_contains(exp: dict, ctx: CheckContext) -> CheckResult:
    p = ctx.workdir / exp["path"]
    if not p.exists():
        return CheckResult(False, f"{exp['path']} missing (cannot check pattern)")
    body = p.read_text(errors="replace")
    found = exp["pattern"] in body
    return CheckResult(found, f"pattern {exp['pattern']!r} {'found' if found else 'NOT FOUND'} in {exp['path']}")


def _function_defined(exp: dict, ctx: CheckContext) -> CheckResult:
    """Match top-level FunctionDef, AsyncFunctionDef, ClassDef, or methods within any ClassDef.

    Python-only for v0.1. Non-Python files raise SyntaxError which is caught upstream.
    """
    p = ctx.workdir / exp["file"]
    if not p.exists():
        return CheckResult(False, f"{exp['file']} missing")
    src = p.read_text(errors="replace")
    try:
        tree = ast.parse(src, filename=str(p))
    except SyntaxError as e:
        return CheckResult(False, f"{exp['file']} did not parse: {e}")
    name = exp["name"]
    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            found = True
            break
    return CheckResult(found, f"name {name!r} {'defined' if found else 'NOT defined'} in {exp['file']}")


def _read_manifest(ctx: CheckContext) -> list[dict]:
    """Read manifest.jsonl, skipping malformed lines."""
    if ctx.manifest_path is None or not ctx.manifest_path.exists():
        return []
    out: list[dict] = []
    for line in ctx.manifest_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _dispatch_matches_skill(entry: dict, skill: str) -> bool:
    """Match a manifest entry against a skill identifier.

    Field naming in build's manifest.jsonl is not contractually fixed; check several
    plausible fields (template, skill, dispatch_template, type) and substring-match
    so 'plan-writer-prompt.md' satisfies 'plan-writer'.
    """
    for key in ("template", "skill", "dispatch_template", "type"):
        v = entry.get(key)
        if isinstance(v, str) and skill in v:
            return True
    return False


def _manifest_contains_dispatch(exp: dict, ctx: CheckContext) -> CheckResult:
    entries = _read_manifest(ctx)
    n = sum(1 for e in entries if _dispatch_matches_skill(e, exp["skill"]))
    cmin = int(exp.get("count_min", 1))
    cmax = int(exp.get("count_max", 1_000_000))
    ok = cmin <= n <= cmax
    return CheckResult(ok, f"dispatch {exp['skill']!r} count={n} expected={cmin}..{cmax}")


def _manifest_does_not_contain(exp: dict, ctx: CheckContext) -> CheckResult:
    entries = _read_manifest(ctx)
    n = sum(1 for e in entries if _dispatch_matches_skill(e, exp["skill"]))
    return CheckResult(n == 0, f"dispatch {exp['skill']!r} count={n} (expected 0)")


def _gate_ledger_phase_status(exp: dict, ctx: CheckContext) -> CheckResult:
    if ctx.gate_ledger_path is None or not ctx.gate_ledger_path.exists():
        return CheckResult(False, "gate ledger absent")
    body = ctx.gate_ledger_path.read_text()
    # Find the phase block, then look for a Status: line within it.
    phase_header = re.compile(rf"^## Phase {re.escape(str(exp['phase']))}:", re.MULTILINE)
    m = phase_header.search(body)
    if not m:
        return CheckResult(False, f"phase {exp['phase']} not found in ledger")
    # Scan from match to next "## " or EOF
    tail = body[m.end():]
    nxt = re.search(r"^## ", tail, re.MULTILINE)
    block = tail[: nxt.start()] if nxt else tail
    sm = re.search(r"^Status:\s*(\S+)", block, re.MULTILINE)
    if not sm:
        return CheckResult(False, f"phase {exp['phase']} has no Status: line")
    actual = sm.group(1).strip()
    expected = exp["status"]
    ok = actual == expected
    return CheckResult(ok, f"Phase {exp['phase']} Status={actual} expected={expected}")


def _resolve_baseline_sha(exp: dict, ctx: CheckContext) -> str | None:
    """Resolve 'BASELINE' placeholder to the SHA written by stage()."""
    sha = exp.get("baseline_sha")
    if sha and sha != "BASELINE":
        return sha
    if ctx.baseline_sha_file and ctx.baseline_sha_file.exists():
        return ctx.baseline_sha_file.read_text().strip() or None
    return None


def _working_tree_unchanged_from(exp: dict, ctx: CheckContext) -> CheckResult:
    sha = _resolve_baseline_sha(exp, ctx)
    if sha is None:
        return CheckResult(False, "no baseline SHA resolvable (placeholder unresolved)")
    if ctx.git_repo is None:
        return CheckResult(False, "no git_repo set on context")
    try:
        # Tracked content vs the baseline SHA. --quiet exits 0 when identical.
        diff = subprocess.run(
            ["git", "diff", "--quiet", sha, "--"],
            cwd=ctx.git_repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Untracked files are invisible to `git diff` — list them separately.
        # b4's halt signal is "no source modifications", and an over-eager build
        # leaking a brand-new file is the most likely failure shape, so an
        # untracked file must count as "changed". Eval-harness scaffolding that
        # legitimately lives inside the workdir (the isolated HOME and the
        # baseline-SHA marker stage() writes post-commit) is excluded so it does
        # not masquerade as a build-leaked file.
        untracked = subprocess.run(
            [
                "git", "ls-files", "--others", "--exclude-standard", "--",
                ":(exclude).home", ":(exclude).home/**",
                ":(exclude).eval-baseline-sha",
            ],
            cwd=ctx.git_repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return CheckResult(False, "git binary not found")
    except subprocess.TimeoutExpired:
        return CheckResult(False, "git diff timed out")
    untracked_files = [ln for ln in untracked.stdout.splitlines() if ln.strip()]
    tracked_unchanged = diff.returncode == 0
    unchanged = tracked_unchanged and not untracked_files
    if untracked_files:
        detail = f"untracked files present: {', '.join(untracked_files[:5])}"
    else:
        detail = f"git diff vs {sha[:12]} exit={diff.returncode}"
    return CheckResult(unchanged, detail)


_CHECKERS = {
    "file_exists": _file_exists,
    "file_does_not_exist": _file_does_not_exist,
    "file_contains": _file_contains,
    "function_defined": _function_defined,
    "manifest_contains_dispatch": _manifest_contains_dispatch,
    "manifest_does_not_contain": _manifest_does_not_contain,
    "gate_ledger_phase_status": _gate_ledger_phase_status,
    "working_tree_unchanged_from": _working_tree_unchanged_from,
}
