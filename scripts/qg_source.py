"""Read the quality-gate runbook across its flat reference files for contract checks."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "skills/quality-gate"
PARTS = (
    "receipt-consensus.md", "loop.md", "cost-fix.md", "stagnation.md",
    "artifact-preflight.md", "recovery.md", "verdict.md", "telemetry-invariants.md",
)


def read_runbook() -> str:
    try:
        body = ROOT.joinpath("SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"Read these flat references in order.*?\n(.*?)(?=\n\n)", body, re.S)
        documented = tuple(re.findall(r"`([^`]+\.md)`", match.group(1))) if match else ()
        if documented != PARTS:
            raise ValueError(f"Contents references differ from qg_source.PARTS: {documented!r}")
        for name in PARTS:
            reference = ROOT.joinpath(name).read_text(encoding="utf-8")
            body += reference.split("\n\n", 2)[2]  # Strip only the generated contents list.
        return body
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        print(f"- quality-gate source drift: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
