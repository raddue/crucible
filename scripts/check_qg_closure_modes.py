#!/usr/bin/env python3
"""Check quality-gate standard/full closure-mode contract.

Path-pinned, stdlib-only structural check. Use --selftest for mutation guards.
"""
from __future__ import annotations

from qg_source import read_runbook
from build_source import read_runbook as read_build_runbook

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = {
    "quality-gate": ROOT / "skills/quality-gate/SKILL.md",
    "build": ROOT / "skills/build/SKILL.md",
    "spec": ROOT / "skills/spec/SKILL.md",
    "migrate": ROOT / "skills/build/references/migration.md",
    "warden": ROOT / "skills/warden/SKILL.md",
}


def check_qg(text: str) -> list[str]:
    required = {
        "mode argument": "| `mode` | enum: `standard` \\| `full` | `standard` |",
        "default standard": "Absent `mode` means",
        "standard default value": "`standard`; there is no environment switch",
        "immutable invocation": "`mode` is invocation-scoped and immutable",
        "actionable round": "`actionable-round`",
        "required reverify": "`required-reverify`",
        "standard zero Fatal": "reverify may close at `0 Fatal`",
        "standard significant actionable": "`0 Fatal / >0 Significant` round is actionable",
        "first-round significant fix": "first-round `0 Fatal / >0 Significant` result is actionable and MUST dispatch fix +",
        "invalid mode fail closed": "rejected before round 1",
        "standard residual disclosure": "Significant/Minor findings on that reverify are",
        "look-harder residual gate": "pre-fix look-harder receipt",
        "first-clean look-harder strict": "first truly clean", 
        "standard no empty fix": "No empty fix dispatch is invented",
        "full strict closure": "`0 Fatal AND\n  0 Significant` on the fresh review",
        "mode-aware look-harder": "active mode's clean predicate",
        "mode marker": "Mode: <standard | full>",
        "residual significant marker": "ResidualSignificant:",
        "residual identity source": "deduplicated by finding identity",
        "residual minor marker": "ResidualMinor:",
        "mode-aware PASS": "PASS`: gate exited cleanly under active mode",
        "mode convergence field": '"mode":"standard"',
        "mode convergence residual": '"residual_significant"',
        "return mode summary": "On gate termination (any verdict), the orchestrator emits structured summary lines",
        "return residual summary": "ResidualSignificant: <int>",
        "run-wide completeness": "Before any PASS, reconcile every completed round and chunk",
        "incomplete closure": "emit `Verdict: ESCALATED`, `Reason: incomplete-run`",
        "unknown completion blocks": "Missing completion evidence counts as incomplete",
        "no verifier substitution (eval 9)": "A fresh red-team review cannot substitute for the fix verifier",
        "judge suppression (eval 6)": "Suppression of escalation does not waive a triggered judge dispatch",
        "required receipt lint": "receipt-linter execution and acceptance for every receipt-bearing dispatch",
        "required cairn": "cairn reconciliation and tripwire processing",
        "ledger omission blocks": "Deliberately omitting the emit attempt is an incomplete run",
        "ledger failure exception": "An attempted emit that fails remains non-blocking",
        "ledger before PASS publication": "before publishing a PASS marker or return summary",
        "documented exemptions": "Documented conditional skips and fallbacks remain valid",
        "clean path completeness guard": "apply the Run-completeness guard before publishing PASS",
        "incomplete reason mapping": "`incomplete-run` — Verdict: ESCALATED",
        "PASS completeness semantics": "and satisfied the Run-completeness guard",
        "completeness precedes clean-pass": "Run completeness is a prerequisite to clean-pass",

    }
    return [f"QG: missing {label}" for label, needle in required.items() if needle not in text]


def check_parent(name: str, text: str) -> list[str]:
    if name == "build":
        required = {
            "mode-aware anti-rationalization": "mode-clean fresh reverify (`0 Fatal` in default `standard`",
            "first clean exception": "truly clean first round",
            "standard closure wording": "`0 Fatal` in default `standard`",
            "full closure wording": "`0 Fatal, 0 Significant` when the caller passes `mode: full`",
            "explicit standard propagation": "explicit `mode: standard` (unless caller explicitly requests `full`)",
            "mode persists recovery": "Persist selected QG mode in the phase handoff/cairn state and reuse it on retries, compaction recovery, and resume",
            "ledger mode field": "QualityGateMode: <standard | full>",
            "quality-gate dispatch remains": "Use crucible:quality-gate",
        }
    elif name in {"spec", "migrate"}:
        required = {
            "mode-aware gate requirement": "mode-clean fresh reverify (`0 Fatal` in default `standard`",
            "standard closure wording": "`0 Fatal` in default `standard`",
            "full closure wording": "`0 Fatal, 0 Significant` when the caller passes `mode: full`",
            "explicit mode propagation": "explicit `mode: standard` (or caller-requested `full`)",
        }
    else:
        required = {
            "strict native predicate": "quality-gate `mode: full` verdict ≠ PASS (Fatal>0 ∨ Significant>0)",
            "explicit full mode": "mode: full",
            "quality-gate leg": "quality-gate red-team leg",
        }
    return [f"{name}: missing {label}" for label, needle in required.items() if needle not in text]


def check_files(texts: dict[str, str]) -> list[str]:
    errors = check_qg(texts["quality-gate"])
    for name in ("build", "spec", "migrate", "warden"):
        errors.extend(check_parent(name, texts[name]))
    return errors


_GOOD = {
    "quality-gate": """
| `mode` | enum: `standard` \\| `full` | `standard` |
Absent `mode` means `standard`; there is no environment switch.
`mode` is invocation-scoped and immutable for the run.
Define `actionable-round` and `required-reverify`.
In standard, a `0 Fatal / >0 Significant` round is actionable; first-round `0 Fatal / >0 Significant` result is actionable and MUST dispatch fix + verifier; only its required fresh reverify may close at `0 Fatal`; Significant/Minor findings on that reverify are disclosed residuals.
Any value other than `standard` or `full` is rejected before round 1.
No empty fix dispatch is invented.
On gate termination (any verdict), the orchestrator emits structured summary lines.
ResidualSignificant: <int>
In full, candidate-clean requires `0 Fatal AND
  0 Significant` on the fresh review.
Look-harder's active mode's clean predicate.
In standard, a pre-fix look-harder receipt with `0 Fatal / >0 Significant` is actionable.
A first truly clean `0 Fatal / 0 Significant` round may close only when look-harder itself also has `0 Significant`.
Mode: <standard | full>
ResidualSignificant: <count>
ResidualMinor: <count>
deduplicated by finding identity
`PASS`: gate exited cleanly under active mode
{"mode":"standard","residual_significant":0}
Before any PASS, reconcile every completed round and chunk.
Missing completion evidence counts as incomplete; emit `Verdict: ESCALATED`, `Reason: incomplete-run`.
A fresh red-team review cannot substitute for the fix verifier.
Suppression of escalation does not waive a triggered judge dispatch.
Require receipt-linter execution and acceptance for every receipt-bearing dispatch,
cairn reconciliation and tripwire processing.
Deliberately omitting the emit attempt is an incomplete run.
An attempted emit that fails remains non-blocking.
Attempt emit before publishing a PASS marker or return summary.
Documented conditional skips and fallbacks remain valid.
apply the Run-completeness guard before publishing PASS.
`incomplete-run` — Verdict: ESCALATED.
PASS also means: and satisfied the Run-completeness guard.
Run completeness is a prerequisite to clean-pass.
""",
    "build": """
The gate is only complete after a mode-clean fresh reverify (`0 Fatal` in default `standard`; `0 Fatal, 0 Significant` when the caller passes `mode: full`).
truly clean first round
explicit `mode: standard` (unless caller explicitly requests `full`).
Persist selected QG mode in the phase handoff/cairn state and reuse it on retries, compaction recovery, and resume.
QualityGateMode: <standard | full>
Use crucible:quality-gate
""",
    "spec": """
Quality Gate Requirement: mode-clean fresh reverify (`0 Fatal` in default `standard`; `0 Fatal, 0 Significant` when the caller passes `mode: full`).
explicit `mode: standard` (or caller-requested `full`).
""",
    "migrate": """
Quality gate requires a mode-clean fresh reverify (`0 Fatal` in default `standard`; `0 Fatal, 0 Significant` when the caller passes `mode: full`).
explicit `mode: standard` (or caller-requested `full`).
""",
    "warden": """
quality-gate `mode: full` verdict ≠ PASS (Fatal>0 ∨ Significant>0)
quality-gate red-team leg uses mode: full
""",
}


def selftest() -> int:
    errors: list[str] = []
    errors.extend(check_files(_GOOD))
    mutations = [
        ("mode row", "| `mode` | enum: `standard` \\| `full` | `standard` |", "quality-gate"),
        ("standard predicate", "reverify may close at `0 Fatal`", "quality-gate"),
        ("full predicate", "`0 Fatal AND\n  0 Significant` on the fresh review", "quality-gate"),
        ("residual marker", "ResidualSignificant:", "quality-gate"),
        ("mode marker", "Mode: <standard | full>", "quality-gate"),
        ("invalid mode", "Any value other than `standard` or `full` is rejected before round 1.", "quality-gate"),
        ("look-harder residual gate", "pre-fix look-harder receipt", "quality-gate"),
        ("warden explicit full", "mode: full", "warden"),
        ("eval 6 judge skip", "Suppression of escalation does not waive a triggered judge dispatch", "quality-gate"),
        ("eval 9 verifier substitution", "A fresh red-team review cannot substitute for the fix verifier", "quality-gate"),
        ("receipt-linter omission", "receipt-linter execution and acceptance for every receipt-bearing dispatch", "quality-gate"),
        ("ledger omission", "Deliberately omitting the emit attempt is an incomplete run", "quality-gate"),
        ("ledger failure compatibility", "An attempted emit that fails remains non-blocking", "quality-gate"),
        ("missing completion evidence", "Missing completion evidence counts as incomplete", "quality-gate"),
        ("incomplete exit", "emit `Verdict: ESCALATED`, `Reason: incomplete-run`", "quality-gate"),
        ("clean-path bypass", "apply the Run-completeness guard before publishing PASS", "quality-gate"),
        ("conditional skip compatibility", "Documented conditional skips and fallbacks remain valid", "quality-gate"),
    ]
    for label, needle, target in mutations:
        broken = dict(_GOOD)
        broken[target] = broken[target].replace(needle, "")
        if not check_files(broken):
            errors.append(f"selftest: removing {label!r} did not fail")
    if errors:
        print("SELFTEST FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — selftest: closure-mode pins and mutation guards pass.")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    texts: dict[str, str] = {}
    errors: list[str] = []
    for name, path in TARGETS.items():
        try:
            texts[name] = (read_runbook() if name == "quality-gate" else read_build_runbook()
                           if name == "build" else path.read_text(encoding="utf-8"))
        except OSError as exc:
            errors.append(f"{name}: unreadable {path}: {exc}")
    if not errors:
        errors = check_files(texts)
    if errors:
        print("QG CLOSURE-MODE DRIFT DETECTED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — quality-gate standard/full closure-mode contract aligned.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
