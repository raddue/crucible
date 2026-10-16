"""Read the quality-gate runbook across its flat reference files for contract checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "skills/quality-gate"
PARTS = (
    "receipt-consensus.md", "loop.md", "cost-fix.md", "stagnation.md",
    "artifact-preflight.md", "recovery.md", "verdict.md", "telemetry-invariants.md",
)


def read_runbook() -> str:
    body = ROOT.joinpath("SKILL.md").read_text(encoding="utf-8")
    for name in PARTS:
        reference = ROOT.joinpath(name).read_text(encoding="utf-8")
        body += reference.split("\n\n", 2)[2]  # Strip only the generated contents list.
    return body
