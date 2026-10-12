#!/usr/bin/env python3
"""Check build pipeline scratch isolation and its consumers."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = {
    "build": ROOT / "skills/build/SKILL.md",
    "replay": ROOT / "skills/replay/SKILL.md",
    "advisor": ROOT / "hooks/build-routing-advisor.sh",
    "reconcile": ROOT / "hooks/tests/tools/build-routing-reconcile.sh",
    "guard": ROOT / "hooks/gate-ledger-guard.sh",
    "dispatch": ROOT / "skills/shared/dispatch-convention.md",
}
STEP_MINUS_ONE_REQUIRED = (
    "git rev-parse --show-toplevel",
    "builds/<worktree-key>/",
    "Store this build's recovery files under `<build-scratch>`:",
    "copy existing files into `<build-scratch>` and continue normal recovery",
    "preserve the originals in place",
    "Starting fresh leaves all legacy files untouched",
    "worktree_root",
)
BUILD_PATH_REQUIRED = (
    "<build-scratch>/build-mode.md",
    "<build-scratch>/handoff-1-to-2.md",
    "<build-scratch>/handoff-2-to-3.md",
    "<build-scratch>/handoff-3-to-4.md",
)


def check(sources: dict[str, str]) -> list[str]:
    build = sources["build"]
    start = build.find("### Step -1: Resume Detection and Pipeline-Active Marker")
    end = build.find("\n### Step 0:", start)
    section = build[start:end] if start >= 0 and end > start else ""
    required = STEP_MINUS_ONE_REQUIRED + BUILD_PATH_REQUIRED
    missing = [pin for pin in required if pin not in build]
    for pin in STEP_MINUS_ONE_REQUIRED:
        if pin not in section:
            missing.append(f"Step -1: {pin}")
    digest = "full hex digest output by `printf '%s' \"$(git rev-parse --show-toplevel)\" | sha256sum | cut -d' ' -f1`"
    if digest not in section:
        missing.append("full SHA-256 worktree key derivation")
    if "git rev-parse --show-toplevel" not in section:
        missing.append("Step -1 worktree root derivation")
    if "~/.claude/projects/<project-hash>/memory/{.pipeline-active,build-gate-ledger.md,pipeline-status.md}" not in section:
        missing.append("legacy singleton paths and explicit first-run choice")
    if "<build-scratch>/pipeline-status.md" not in build or "<build-scratch>/build-mode.md" not in build:
        missing.append("build compaction recovery uses namespaced files")
    for stale in ("/tmp/crucible-build-mode.md", "~/.claude/projects/<hash>/memory/pipeline-status.md"):
        if stale in sources["replay"]:
            missing.append(f"replay retains stale shared path: {stale}")
    pins = {
        "replay": ("<build-scratch>/pipeline-status.md", "<build-scratch>/build-mode.md", "<build-scratch>/handoff-N-to-M.md"),
        "advisor": ("builds/$WORKTREE_KEY/.pipeline-active", "MARKER_SKILL"),
        "reconcile": ("builds/*/build-gate-ledger.md", "LEDGER_PATHS"),
        "guard": ("*build-gate-ledger.md)", "memory/.*|\\1|p"),
        "dispatch": ("worktree_root",),
    }
    for name, required in pins.items():
        for pin in required:
            if pin not in sources[name]:
                missing.append(f"{name}: {pin}")
    return missing


def sample_sources(build: str) -> dict[str, str]:
    return {
        "build": build,
        "replay": "<build-scratch>/pipeline-status.md <build-scratch>/build-mode.md <build-scratch>/handoff-N-to-M.md",
        "advisor": "builds/$WORKTREE_KEY/.pipeline-active MARKER_SKILL",
        "reconcile": "builds/*/build-gate-ledger.md LEDGER_PATHS",
        "guard": "*build-gate-ledger.md) memory/.*|\\1|p",
        "dispatch": "worktree_root",
    }


def selftest() -> int:
    step = "### Step -1: Resume Detection and Pipeline-Active Marker\n"
    step += "\n".join(STEP_MINUS_ONE_REQUIRED)
    step += "\n" + "\n".join(BUILD_PATH_REQUIRED)
    step += "\n<build-scratch>/pipeline-status.md"
    step += '\nfull hex digest output by `printf \'%s\' "$(git rev-parse --show-toplevel)" | sha256sum | cut -d\' \' -f1`\n'
    step += "~/.claude/projects/<project-hash>/memory/{.pipeline-active,build-gate-ledger.md,pipeline-status.md}\n### Step 0:\n"
    good = sample_sources(step + "\n".join(BUILD_PATH_REQUIRED))
    assert not check(good), check(good)
    for pin in STEP_MINUS_ONE_REQUIRED + BUILD_PATH_REQUIRED:
        bad = good.copy()
        bad["build"] = bad["build"].replace(pin, "")
        assert check(bad), f"missing pin not detected: {pin}"
    for name in ("replay", "advisor", "reconcile", "guard", "dispatch"):
        bad = good.copy()
        bad[name] = ""
        assert check(bad), f"missing consumer not detected: {name}"
    for stale in ("/tmp/crucible-build-mode.md", "~/.claude/projects/<hash>/memory/pipeline-status.md"):
        bad = good.copy()
        bad["replay"] += " " + stale
        assert any(stale in item for item in check(bad)), f"stale replay path not detected: {stale}"
    bad = good.copy()
    bad["build"] = bad["build"].replace("full hex digest output", "truncated hash")
    assert "full SHA-256 worktree key derivation" in check(bad)
    print("selftest OK — namespace, migration, and consumers are required")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    sources = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
    missing = check(sources)
    if missing:
        print("BUILD SCRATCH ISOLATION CHECK FAILED:")
        for pin in missing:
            print(f"  - {pin}")
        return 1
    print("OK — build scratch isolation, migration, and consumers are documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
