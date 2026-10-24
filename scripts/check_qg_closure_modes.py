#!/usr/bin/env python3
"""Check quality-gate standard/full closure-mode contract.

Path-pinned, stdlib-only structural check. Use --selftest for mutation guards.
"""
from __future__ import annotations

from qg_source import read_runbook
from build_source import read_runbook as read_build_runbook

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = {
    "quality-gate": ROOT / "skills/quality-gate/SKILL.md",
    "build": ROOT / "skills/build/SKILL.md",
    "spec": ROOT / "skills/spec/SKILL.md",
    "migrate": ROOT / "skills/build/references/migration.md",
    "warden": ROOT / "skills/warden/SKILL.md",
    "ledger-append": ROOT / "skills/shared/ledger-append.md",
}


_HEDGE = re.compile(r"\b(may|might|can|could|should|optional|optionally|not|never)\b", re.I)
_GUARD_HEAD = "### Run-completeness guard (#755)"

_SIEGE_PHRASE = "demotes only a local PASS"
_SIEGE_SITES = (
    ("loop.md candidate-clean step 2", "2. If `SiegeVerdict != PASS`", True),
    ("artifact-preflight ordering (2)", "(2) if `SiegeVerdict != PASS`", True),
    ("artifact-preflight verdict mapping", "**Verdict mapping:**", False),
    ("verdict.md siege-blocked reason", "- `siege-blocked` —", False),
)

_LEDGER_SITES = (
    ("verdict.md emit scope", "**Ledger emit at verdict-emit.**", 3000, (
        "exactly once per run", "chunked early non-PASS exit", "before publishing a PASS marker or return summary",
        "for any non-PASS verdict, the marker is written first", "never emits and never requires a ledger row")),
    ("loop.md guard parenthetical", "ledger-emit obligation in `verdict.md`", 700, ("chunked early non-PASS exit",)),
    ("telemetry-invariants order", "**When written:** Once per gate run", 600, (
        "terminal PASS: ledger emit attempt, PASS marker, convergence log", "non-PASS: marker, ledger emit, convergence log")),
    ("recovery ledger-emitted", "`ledger-emitted` defaults to `false`", 700, (
        "run-terminal verdict", "The key is informational", "post-emit rewrite")),
)

def _flat(s: str) -> str:
    return " ".join(re.sub(r"<!--.*?-->", " ", s, flags=re.S).split())

def _operative(scope: str, needle: str) -> bool:
    """True iff every occurrence of needle in scope is un-hedged: the text between the
    previous sentence boundary and the needle must not contain may/can/not/never.
    Mirrors the _negates() polarity idea in check_qg_second_pass_score.py (#755 F2)."""
    scope, needle = _flat(scope), _flat(needle)
    hits = [m.start() for m in re.finditer(re.escape(needle), scope)]
    if not hits:
        return False
    for i in hits:
        prefix = re.split(r"(?<=[.;:!?])\s", scope[:i])[-1]
        if _HEDGE.search(prefix):
            return False
    return True

def check_guard(text: str) -> list[str]:
    """Behavioral pins for #755: operative guard clauses (polarity + section scoped),
    Exit Precedence slot, pre-threshold list, terminal-only ledger, second PASS site."""
    flat = _flat(text)
    errs: list[str] = []
    i = flat.find(_flat(_GUARD_HEAD))
    section = flat[i:flat.find("**Artifact-type-aware", i) if "**Artifact-type-aware" in flat[i:] else None] if i >= 0 else ""
    if not section:
        return ["QG: missing Run-completeness guard section"]
    for label, needle in {
        "emit incomplete-run": "emit `Verdict: ESCALATED`, `Reason: incomplete-run`",
        "no PASS publication": "Do not publish PASS in the marker, ledger, or summary.",
        "remediate before closing": "complete it and any dependent reverify before closing",
        "no verifier substitution": "A fresh red-team review cannot substitute for the fix verifier",
        "applies to chunk milestones": "applies to chunk-milestone PASSes as well as the final integration",
        "run-terminal ledger": "run-terminal verdict only",
        "co-fire recorded": "recording `incomplete-run` under `CoFiredExits`",
    }.items():
        if not _operative(section, needle):
            errs.append(f"QG: guard clause not operative (missing/hedged/negated/out of section): {label}")
    pre = re.search(r"The only pre-threshold exits are:(.{0,1800})", flat)
    if not pre or "`incomplete-run`" not in pre.group(1):
        errs.append("QG: pre-threshold exit list omits incomplete-run (#755 F1)")
    prec = re.search(r"### Exit Precedence(.*?)## Red Flags", flat)
    prec_t = prec.group(1) if prec else ""
    if not re.search(r"\b10\. \*\*Incomplete-run ESCALATED", prec_t) or "reason `incomplete-run`" not in prec_t:
        errs.append("QG: Exit Precedence lacks incomplete-run slot #10 (#755 F1)")
    if "Run-completeness guard is satisfied" not in prec_t or "slot #1 does not match" not in prec_t:
        errs.append("QG: Exit Precedence slot #1 not reconciled with Run-completeness guard (#755 F6)")
    if "the Run-completeness guard is not one" not in prec_t:
        errs.append("QG: siege-demotion 'ONLY post-precedence modification' not reconciled (#755 F6)")
    pf = re.search(r"\(4\) apply the Run-completeness guard.{0,200}", flat)
    if not pf or "only if satisfied write `Verdict: PASS, Reason: clean-pass`" not in pf.group(0):
        errs.append("QG: artifact-preflight clean-round PASS write not gated by Run-completeness guard (#755 F5)")
    # S1: siege-blocked demotes only a local PASS; incomplete-run (slot #10) stands over it.
    for label, anchor, need_incomplete in _SIEGE_SITES:
        j = flat.find(anchor)
        win = flat[j:j + 700] if j >= 0 else ""
        if _SIEGE_PHRASE not in win or (need_incomplete and "incomplete-run" not in win):
            errs.append(f"QG: siege-blocked/incomplete-run precedence diverges at {label} (S1)")
    if re.search(r"write (?:the |a )?(?:verdict marker )?(?:with )?`Verdict: ESCALATED, Reason: siege-blocked`", flat):
        errs.append("QG: early unconditional siege-blocked Reason before Exit Precedence (S1)")
    if "`ledger-emitted` defaults to `false`" not in flat:
        errs.append("QG: recovery.md ledger-emitted default contradicts terminal-only emit (M3)")
    # #755 round-2 S1/S2: one emit per run-terminal verdict (incl. chunked early non-PASS exits),
    # QG terminal PASS emits pre-marker, others marker-first. ponytail: substring pins in anchored windows;
    # upgrade to a parsed contract if wording churns.
    for label, anchor, size, needles in _LEDGER_SITES:
        j = flat.find(anchor)
        win = flat[j:j + size] if j >= 0 else ""
        for n in needles:
            if n not in win:
                errs.append(f"QG: ledger contract pin missing at {label}: {n!r} (S1/S2)")
    return errs

def check_ledger_doc(text: str) -> list[str]:
    """shared/ledger-append.md must carry the QG-scoped PASS pre-marker carve-out (S1)."""
    flat = _flat(text)
    j = flat.find("## When to emit")
    win = flat[j:j + 1200] if j >= 0 else ""
    need = ("quality-gate only", "terminal PASS", "before publishing the PASS marker", "marker-first")
    return [f"ledger-append.md: When-to-emit lacks {n!r} (S1)" for n in need if n not in win]

def check_qg(text: str, guard: bool = True) -> list[str]:
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
    return [f"QG: missing {label}" for label, needle in required.items() if needle not in text] + (check_guard(text) if guard else [])


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


def check_files(texts: dict[str, str], guard: bool = True) -> list[str]:
    errors = check_qg(texts["quality-gate"], guard)
    if guard:
        errors.extend(check_ledger_doc(texts["ledger-append"]))
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
    errors.extend(check_files(_GOOD, guard=False))
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
        if not check_files(broken, guard=False):
            errors.append(f"selftest: removing {label!r} did not fail")
    # Behavioral guard (#755 F2): mutate the REAL runbook; each semantic inversion,
    # hidden-in-comment, or contract-removal must trip check_guard.
    real = read_runbook()
    if check_guard(real):
        errors.append(f"selftest: real runbook fails check_guard: {check_guard(real)}")
    guard_mutations = [
        ("MAY emit incomplete-run", "emit `Verdict: ESCALATED`, `Reason: incomplete-run`; name", "MAY emit `Verdict: ESCALATED`, `Reason: incomplete-run`; name"),
        ("PASS publication allowed", "Do not publish PASS in the marker, ledger, or summary.", "It may publish PASS in the marker, ledger, or summary."),
        ("verifier substitution allowed", "A fresh red-team review cannot substitute for the fix verifier.", "A fresh red-team review can substitute for the fix verifier."),
        ("chunk milestones exempt", "applies to chunk-milestone PASSes as well as the final integration", "does not apply to chunk-milestone PASSes as well as the final integration"),
        ("milestone ledger emit", "run-terminal verdict only", "every marker"),
        ("early chunked exit dropped (loop)", "or a chunked early non-PASS exit that ends the run before integration", "or nothing"),
        ("early chunked exit dropped (verdict)", "or a chunked early non-PASS exit (", "or nothing ("),
        ("emit once", "Attempt this emit exactly once per run", "Attempt this emit"),
        ("non-PASS marker-first dropped", "for any non-PASS verdict, the marker is written first", "for any non-PASS verdict, nothing"),
        ("milestone requires row", "never emits and never requires a ledger row", "emits and requires a ledger row"),
        ("convergence PASS order", "terminal PASS: ledger emit attempt, PASS marker, convergence log", "marker, convergence log"),
        ("convergence non-PASS order", "non-PASS: marker, ledger emit, convergence log", "non-PASS: marker, convergence log"),
        ("ledger-emitted informational", "The key is informational", "gates recovery"),
        ("ledger-emitted post-emit rewrite", "post-emit rewrite", "pre-emit write"),
        ("co-fire record dropped", "recording `incomplete-run` under `CoFiredExits`", "recording nothing"),
        ("pre-threshold list", "run-completeness closure (`incomplete-run`", "run-completeness closure (`x`"),
        ("exit precedence slot", "10. **Incomplete-run ESCALATED", "10. **Other ESCALATED"),
        ("slot #1 reconcile", "AND the Run-completeness guard is satisfied", "AND nothing else"),
        ("siege-demotion sentence", "the Run-completeness guard is not one", "nothing else is one"),
        ("loop siege early Reason", "skip look-harder + Minor Issue Handling, surface siege findings in", "skip look-harder + Minor Issue Handling, write verdict marker `Verdict: ESCALATED, Reason: siege-blocked`, surface siege findings in"),
        ("preflight siege early Reason", "resolve the local verdict by Exit Precedence; `siege-blocked` demotes only a local PASS", "write `Verdict: ESCALATED, Reason: siege-blocked`; `siege-blocked` demotes only a local PASS"),
        ("preflight mapping unqualified", "cannot be `PASS`: `siege-blocked` demotes only a local PASS", "cannot be `PASS`: `siege-blocked` demotes every verdict"),
        ("verdict.md reason unqualified", "ESCALATED; demotes only a local PASS", "ESCALATED; demotes every verdict"),
        ("ledger default true", "`ledger-emitted` defaults to `false`", "`ledger-emitted` defaults to `true`"),
        ("preflight PASS ungated", "only if satisfied write `Verdict: PASS, Reason: clean-pass`", "write `Verdict: PASS, Reason: clean-pass`"),
    ]
    for label, old, new in guard_mutations:
        if old not in real:
            errors.append(f"selftest: mutation anchor missing in real runbook: {label!r}")
        elif not check_guard(real.replace(old, new)):
            errors.append(f"selftest: guard mutation {label!r} not caught")
    ledger_real = TARGETS["ledger-append"].read_text(encoding="utf-8")
    if check_ledger_doc(ledger_real):
        errors.append(f"selftest: real ledger-append.md fails: {check_ledger_doc(ledger_real)}")
    for label, old, new in (
        ("ledger-append QG carve-out dropped", "quality-gate only", "all skills"),
        ("ledger-append PASS pre-marker dropped", "before publishing the PASS marker", "after the PASS marker"),
        ("ledger-append marker-first dropped", "marker-first", "nothing-first"),
    ):
        if old not in ledger_real:
            errors.append(f"selftest: ledger anchor missing: {label!r}")
        elif not check_ledger_doc(ledger_real.replace(old, new)):
            errors.append(f"selftest: ledger mutation {label!r} not caught")
    head = "### Run-completeness guard (#755)"
    if head in real:
        i = real.index(head); j = real.index("**Artifact-type-aware", i)
        if not check_guard(real[:i] + "<!--\n" + real[i:j] + "\n-->\n" + real[j:]):
            errors.append("selftest: HTML-commented guard section not caught")
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
