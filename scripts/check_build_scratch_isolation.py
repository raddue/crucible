#!/usr/bin/env python3
"""Check build pipeline scratch state is isolated per worktree."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "skills/build/SKILL.md"
REQUIRED = (
    "git rev-parse --show-toplevel",
    "builds/<worktree-key>/",
    "Store this build's three recovery files only here",
    "copy existing files into `<build-scratch>` and continue normal recovery",
    "preserve the originals in place",
)


def check(text: str) -> list[str]:
    start = text.find("### Step -1: Resume Detection and Pipeline-Active Marker")
    end = text.find("\n### Step 0:", start)
    section = text[start:end] if start >= 0 and end > start else ""
    missing = [pin for pin in REQUIRED if pin not in section]
    if "full hex digest output by `printf '%s' \"$(git rev-parse --show-toplevel)\" | sha256sum | cut -d' ' -f1`" not in section:
        missing.append("full SHA-256 worktree key derivation")
    for pin in ("<build-scratch>/.pipeline-active", "<build-scratch>/build-gate-ledger.md",
                "<build-scratch>/pipeline-status.md"):
        if pin not in text:
            missing.append(pin)
    return missing


def selftest() -> int:
    good = "### Step -1: Resume Detection and Pipeline-Active Marker\n" + "\n".join(REQUIRED) + '\nfull hex digest output by `printf \'%s\' "$(git rev-parse --show-toplevel)" | sha256sum | cut -d\' \' -f1`\n' + "\n".join(("<build-scratch>/.pipeline-active", "<build-scratch>/build-gate-ledger.md", "<build-scratch>/pipeline-status.md")) + "\n### Step 0:\n"
    assert not check(good), check(good)
    for pin in REQUIRED:
        bad = good.replace(pin, "removed")
        assert pin in check(bad), f"missing pin not detected: {pin}"
    assert "full SHA-256 worktree key derivation" in check(good.replace("full hex digest output", "truncated hash"))
    print("selftest OK — every isolation and migration clause is required")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    missing = check(BUILD.read_text(encoding="utf-8"))
    if missing:
        print("BUILD SCRATCH ISOLATION CHECK FAILED:")
        for pin in missing:
            print(f"  - missing {pin}")
        return 1
    print("OK — build scratch isolation and legacy-state handling are documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
