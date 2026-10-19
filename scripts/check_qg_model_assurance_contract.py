#!/usr/bin/env python3
"""Check the quality-gate model-assurance contract (#746).

Path-pinned, stdlib-only structural check over the QG runbook and the shared
ledger doc, plus behavioral rejection fixtures (chunk-milestone selection,
missing mandatory consensus, wrapper-only verified, cross-chunk receipt lint).
Use --selftest for mutation guards.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

from qg_source import read_runbook

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER_DOC = ROOT / "skills/shared/ledger-append.md"

QG_REQUIRED = {
    "inventory section": "## Model Assurance Inventory (#746)",
    "durable inventory path": "memory/quality-gate/model-assurance/<run-id>.json",
    "record before consumption": "before its result is consumed",
    "demotion stays consumed": "keeps the original dispatch's consumed record",
    "verdict-mode members and synthesis": "consensus members and their separate synthesis",
    "model_resolution separation": "`model_resolution` ledger field",
    "unobservable consensus cap": "at most `configured`/`unknown`",
    "PASS never suppressed": "never suppresses an artifact PASS",
    "wrapper cannot attest children": "never attests its children",
    "bridged response counted once": "counts once",
    "inventory survives scratch deletion": "surviving compaction and scratch deletion",
    "roster membership set": "consensus membership set",
    "marker finality values": "MarkerFinality: chunk-milestone | final-integration",
    "final-integration preconditions": "all mandatory cross-chunk consensus membership is consumed",
    "no timestamp selection": "never select latest PASS by timestamp",
    "chunk milestone non-qualifying": "never be selected or displayed as whole-gate high assurance",
    "final hash freeze point": "frozen **after** all fixes including the post-PASS Minor",
    "no duplicate RunID": "never write a duplicate RunID field",
    "inventory binding field": "ModelAssuranceInventory:",
    "high-assurance display gate": "HIGH-ASSURANCE QG PASS",
    "ledger emit advisory only": "skipped, deduplicated, or fail without changing the durable inventory",
    "cross-chunk layout pin": "Cross-chunk layout (pinned, #746)",
    "cross-chunk second root": "second `--root`",
    "recovery never assumes empty": "never an assumed-empty invocation set",
    "external response inventory": "stable response ID",
    "judge dispatch inventory": "silent-seed included",
}

LEDGER_REQUIRED = {
    "shape section": "### `model_assurance` shape (#746, additive optional)",
    "schema stays 2": "`schema_version` stays 2",
    "proof of record": "the inventory file, not the ledger row, is the proof of record",
    "no transcripts or credentials": "Never archive raw provider transcripts or credentials",
}

def check_files(qg: str, ledger: str) -> list[str]:
    errors = [f"QG: missing {label}" for label, needle in QG_REQUIRED.items() if needle not in qg]
    errors += [f"ledger: missing {label}" for label, needle in LEDGER_REQUIRED.items() if needle not in ledger]
    return errors

_GOOD_QG = "\n".join([
    "## Model Assurance Inventory (#746)",
    "memory/quality-gate/model-assurance/<run-id>.json",
    "before its result is consumed",
    "keeps the original dispatch's consumed record",
    "consensus members and their separate synthesis",
    "separate from the terminal-round `model_resolution` ledger field",
    "QG assurance is at most `configured`/`unknown`",
    "never suppresses an artifact PASS",
    "A wrapper receipt (siege's included) never attests its children",
    "counts once",
    "surviving compaction and scratch deletion",
    "mandatory consensus membership set",
    "MarkerFinality: chunk-milestone | final-integration",
    "every manifest-listed chunk has terminal status and all mandatory cross-chunk consensus membership is consumed",
    "never select latest PASS by timestamp",
    "must never be selected or displayed as whole-gate high assurance",
    "frozen **after** all fixes including the post-PASS Minor quick-fix",
    "never write a duplicate RunID field",
    "ModelAssuranceInventory: <inventory-path> sha256:<inventory-digest>",
    "HIGH-ASSURANCE QG PASS",
    "skipped, deduplicated, or fail without changing the durable inventory or the verdict",
    "**Cross-chunk layout (pinned, #746).**",
    "passed as the second `--root`",
    "never an assumed-empty invocation set",
    "one inventory row under its stable response ID",
    "silent-seed included",
])

_GOOD_LEDGER = "\n".join([
    "### `model_assurance` shape (#746, additive optional)",
    "`schema_version` stays 2",
    "the inventory file, not the ledger row, is the proof of record",
    "Never archive raw provider transcripts or credentials",
])

def _behavior_fixtures() -> list[str]:
    import qg_model_assurance as qma
    errors: list[str] = []
    data = {
        "version": 1, "run_id": "run-1", "artifact_hash": "a" * 64, "final_artifact_hash": "b" * 64,
        "roster": {"kind": "chunked", "chunks": ["c1", "cross-chunk"], "terminal": ["c1", "cross-chunk"],
                   "consensus": ["synthesis"]},
        "invocations": [
            {"id": "review", "parent": "run-1", "scope": "c1", "disposition": "consumed", "assurance": "verified"},
            {"id": "synthesis", "parent": "run-1", "scope": "cross-chunk", "disposition": "consumed", "assurance": "verified"},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp, "inv.json")
        digest = qma.write_inventory(path, data)
        marker = {"Verdict": "PASS", "MarkerFinality": "final-integration", "RunID": "run-1",
                  "ArtifactHash": "a" * 64, "FinalArtifactHash": "b" * 64, "ModelAssurance": "verified",
                  "ModelAssuranceInventory": f"{path} sha256:{digest}"}
        # Rejection: a chunk milestone must never satisfy qg-verified or read as whole-gate assurance.
        if qma.action_allowed("qg-verified", {**marker, "MarkerFinality": "chunk-milestone"},
                              path, digest, "b" * 64):
            errors.append("fixture: chunk-milestone marker satisfied qg-verified")
        # Rejection: an inventory omitting a mandatory consensus member is refused, not downgraded silently.
        gapped = json.loads(json.dumps(data))
        gapped["invocations"] = [row for row in gapped["invocations"] if row["id"] != "synthesis"]
        try:
            qma.write_inventory(pathlib.Path(tmp, "gap.json"), gapped)
            errors.append("fixture: inventory omitting a mandatory consensus member was accepted")
        except ValueError:
            pass
        # Rejection: a wrapper result with no host evidence never verifies the whole run.
        if qma.reconcile_evidence(data, {}, {}, {}) != "unknown":
            errors.append("fixture: wrapper-only evidence produced a verified state")
    # Fixture: the chunked gate's cross-chunk integration round completes receipt lint with its
    # findings and journal resolvable under the explicitly passed cross-chunk findings root.
    with tempfile.TemporaryDirectory() as tmp:
        dispatch = pathlib.Path(tmp, "dispatch")
        dispatch.mkdir()
        cross = pathlib.Path(tmp, "scratch", "cross-chunk")
        cross.mkdir(parents=True)
        (cross / "round-1-findings.md").write_text("finding\n")
        (cross / "fix-journal.md").write_text("journal\n")
        (cross / "round-1-coverage.md").write_text("")
        receipt = (
            "RCPT v1.1 quality-gate/1-crucible-red-team\nVERDICT  PASS  conf=0.90\n"
            "ARTIFACTS\n"
            f"  round-1-findings.md sha256:{hashlib.sha256(b'finding' + b'\n').hexdigest()} 8\n"
            f"  fix-journal.md sha256:{hashlib.sha256(b'journal' + b'\n').hexdigest()} 8\n"
            "TRACE\n  1  SKIPPED  no-artifacts\nCLAIMS\n  (none)\n"
            "WITNESS    lint:trace-consistent  expect-fail=/inconsistent/  ran=TRACE#1\n"
            "SUSPICION  0.00\nNEXT       (none)\nTRIPWIRE: none\nSUPERSEDES: none\n"
            "TRIPWIRE-CHILD: none\n"
        )
        rpath = dispatch / "1-crucible-red-team-receipt.md"
        rpath.write_text(receipt)
        ledger = dispatch / "receipt-ledger.jsonl"
        ledger.write_text(json.dumps({"dispatch_id": "1-crucible-red-team", "phase": "quality-gate:round/1",
                                      "rcpt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
                                      "verdict": "PASS"}) + "\n")
        base = [sys.executable, str(ROOT / "scripts/rcpt_verify.py"), "--tier2",
                "--root", str(dispatch), "--ledger", str(ledger), str(rpath)]
        pinned = subprocess.run(base[:5] + ["--root", str(cross)] + base[5:], capture_output=True, text=True)
        if pinned.returncode != 0 or "UNVERIFIABLE" in pinned.stdout + pinned.stderr:
            errors.append(f"fixture: cross-chunk lint failed under the pinned root "
                          f"(exit {pinned.returncode}): {(pinned.stdout + pinned.stderr).strip()[:300]}")
        unpinned = subprocess.run(base, capture_output=True, text=True)
        if "UNVERIFIABLE" not in unpinned.stdout + unpinned.stderr:
            errors.append("fixture: bare-basename citation resolved without the explicit cross-chunk root")
    return errors

def selftest() -> int:
    errors = check_files(_GOOD_QG, _GOOD_LEDGER)
    mutations = [
        ("chunk milestone non-qualifying", "QG", "must never be selected or displayed as whole-gate high assurance"),
        ("timestamp selection ban", "QG", "never select latest PASS by timestamp"),
        ("wrapper attestation ban", "QG", "never attests its children"),
        ("PASS suppression ban", "QG", "never suppresses an artifact PASS"),
        ("verdict-mode synthesis inventory", "QG", "consensus members and their separate synthesis"),
        ("model_resolution separation", "QG", "`model_resolution` ledger field"),
        ("marker finality", "QG", "MarkerFinality: chunk-milestone | final-integration"),
        ("final hash freeze point", "QG", "frozen **after** all fixes including the post-PASS Minor"),
        ("cross-chunk layout pin", "QG", "Cross-chunk layout (pinned, #746)"),
        ("ledger shape section", "ledger", "### `model_assurance` shape (#746, additive optional)"),
    ]
    for label, target, needle in mutations:
        qg = _GOOD_QG.replace(needle, "") if target == "QG" else _GOOD_QG
        ledger = _GOOD_LEDGER.replace(needle, "") if target == "ledger" else _GOOD_LEDGER
        if not check_files(qg, ledger):
            errors.append(f"selftest: removing {label!r} did not fail")
    errors.extend(f"selftest: {error}" for error in _behavior_fixtures())
    if errors:
        print("SELFTEST FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — selftest: model-assurance contract pins, mutation guards, and rejection fixtures pass.")
    return 0

def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    errors: list[str] = []
    try:
        qg = read_runbook()
        ledger = LEDGER_DOC.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"QG MODEL-ASSURANCE CONTRACT: unreadable source: {exc}")
        return 1
    errors = check_files(qg, ledger)
    if errors:
        print("QG MODEL-ASSURANCE CONTRACT DRIFT DETECTED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — quality-gate model-assurance contract aligned.")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
