"""Read the build runbook across its flat references/ files and SKILL.md for contract checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "skills/build"
PARTS = (
    "runtime-protocols.md", "gate-ledger.md", "pipeline-status.md",
    "phase-1-design.md", "phase-2-plan.md", "phase-3-execute.md",
)


def read_runbook() -> str:
    """Phase references first, SKILL.md last (migration mode excluded: separate subflow).

    gate-ledger.md's fenced ledger template reuses `## Phase 4: Completion`; SKILL.md last
    keeps LAST-match extractors on the real Phase 4 workflow section.
    """
    parts = [ROOT.joinpath("references", name).read_text(encoding="utf-8") for name in PARTS]
    parts.append(ROOT.joinpath("SKILL.md").read_text(encoding="utf-8"))
    return "\n".join(parts)
