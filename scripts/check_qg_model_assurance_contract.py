#!/usr/bin/env python3
"""Check the quality-gate model-assurance contract (#746).

Path-pinned, stdlib-only structural check over the QG runbook and the shared
ledger doc, plus behavioral rejection fixtures (chunk-milestone selection,
missing mandatory consensus, no-adapter verified, cross-chunk receipt lint). Every
rejection fixture starts from a configuration that is allowed/verified and flips exactly one field.
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
GATE_LEDGER_DOC = ROOT / "skills/build/references/gate-ledger.md"

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
    "provisional vs terminal schema": "Provisional vs terminal schema",
    "attestation pinned by inventory digest": "the inventory digest therefore pins the evidence",
    "provisional recovery read": "resume with the provisional read",
    "sole FinalArtifactHash computation": "computed only by `gated_hash`",
    "gated_hash failure downgrades": "write `FinalArtifactHash: unknown` and `ModelAssurance: unknown`",
}

GATE_LEDGER_REQUIRED = {
    "absent finality reads as final": "an absent `MarkerFinality`",
    "only explicit chunk-milestone rejected": "only an explicit `chunk-milestone` is rejected",
    "no assurance data at marker selection": "no inventory, roster, or assurance field is read here",
    "roster check belongs to opt-in": "belong to this opt-in predicate only",
    "evidence comes from host adapter": "host adapter supplies from its own protected store",
    "no adapter means False": "with no host adapter the predicate returns False",
    "warden handoff tuple source": "`QGLegProofTuple`",
    "tuple rebuilds the marker": "rebuild the marker dict for `caller_allowed` from the ledger",
    "unknown never withholds PASS": "never a reason to withhold or fail PASS",
    "changed paths within gated set": "is in the inventory's `gated.paths`",
    "reconstruction keys on manifest opt-in line": "`**RequiredModelAssurance:** qg-verified` header line",
    "inventory or tuple is not an opt-in signal": "is not an opt-in signal",
}

LEDGER_REQUIRED = {
    "shape section": "### `model_assurance` shape (#746, additive optional)",
    "schema stays 2": "`schema_version` stays 2",
    "proof of record": "the inventory file, not the ledger row, is the proof of record",
    "no transcripts or credentials": "Never archive raw provider transcripts or credentials",
}

def check_files(qg: str, ledger: str, gate_ledger: str) -> list[str]:
    errors = [f"QG: missing {label}" for label, needle in QG_REQUIRED.items() if needle not in qg]
    errors += [f"gate-ledger: missing {label}" for label, needle in GATE_LEDGER_REQUIRED.items()
               if needle not in gate_ledger]
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
    "**Provisional vs terminal schema.**",
    "the inventory digest therefore pins the evidence",
    "resume with the provisional read",
    "computed only by `gated_hash`",
    "write `FinalArtifactHash: unknown` and `ModelAssurance: unknown`",
])

_GOOD_GATE_LEDGER = "\n".join([
    "an absent `MarkerFinality` reads as final",
    "only an explicit `chunk-milestone` is rejected",
    "no inventory, roster, or assurance field is read here",
    "belong to this opt-in predicate only",
    "that the host adapter supplies from its own protected store",
    "with no host adapter the predicate returns False",
    "`QGLegProofTuple`",
    "rebuild the marker dict for `caller_allowed` from the ledger",
    "never a reason to withhold or fail PASS",
    "is in the inventory's `gated.paths`",
    "takes the requirement from the manifests' `**RequiredModelAssurance:** qg-verified` header line",
    "A retained inventory or a `QGProofTuple` is not an opt-in signal",
])

_GOOD_LEDGER = "\n".join([
    "### `model_assurance` shape (#746, additive optional)",
    "`schema_version` stays 2",
    "the inventory file, not the ledger row, is the proof of record",
    "Never archive raw provider transcripts or credentials",
])

def _behavior_fixtures() -> list[str]:
    import unittest
    from unittest import mock
    import qg_model_assurance as qma
    import test_qg_model_assurance as fx
    errors: list[str] = []

    class _Case(fx.EvidenceFixture, unittest.TestCase):
        def runTest(self):
            pass

    case = _Case()
    case.setUp()
    try:
        path = pathlib.Path(case.tmp.name, "inv.json")
        digest = qma.write_inventory(path, case.data, terminal=True)
        marker = {"Verdict": "PASS", "MarkerFinality": "final-integration", "RunID": "run-1",
                  "ArtifactHash": "a" * 64, "FinalArtifactHash": "b" * 64, "ModelAssurance": "verified",
                  "ModelAssuranceInventory": f"{path} sha256:{digest}", "Gated-Files": json.dumps(["a.txt"])}
        trusted = {"evidence": case.evidence, "allowlist": case.allowlist, "policy": case.POLICY,
                   "host_adapter": case.adapter}

        def allowed(m=marker, **over):
            return qma.caller_allowed("qg-verified", m, path, digest, "b" * 64, **{**trusted, **over})

        # Baseline: the unflipped configuration is allowed and verified, or every flip below is vacuous.
        if not allowed():
            errors.append("fixture: baseline verified configuration was not allowed")
        if case.reconcile() != "verified":
            errors.append("fixture: baseline evidence did not reconcile to verified")
        flips = {
            "chunk-milestone marker satisfied qg-verified": dict(m={**marker, "MarkerFinality": "chunk-milestone"}),
            "marker naming another inventory digest was accepted": dict(
                m={**marker, "ModelAssuranceInventory": f"{path} sha256:{'e' * 64}"}),
            "evidence without a host adapter produced verified": dict(host_adapter=None),
            "empty allowlist produced verified": dict(allowlist={}),
            "marker Gated-Files differing from the inventory gated set was accepted": dict(
                m={**marker, "Gated-Files": json.dumps(["a.txt", "extra.txt"])}),
        }
        for label, over in flips.items():
            if allowed(**over):
                errors.append(f"fixture: {label}")
        # Rejection: same-uid evidence (the reviewer's own uid owns it) never verifies.
        with mock.patch.object(qma.os, "getuid", return_value=case.real_uid):
            if case.reconcile() != "unknown":
                errors.append("fixture: reviewer-uid-owned evidence produced a verified state")
        # Rejection: a mandatory consensus member recorded unused is refused, not downgraded silently.
        gapped = json.loads(json.dumps(case.data))
        gapped["roster"]["consensus"] = ["synthesis"]
        gapped["invocations"][1]["disposition"] = "unused"
        try:
            qma.write_inventory(pathlib.Path(case.tmp.name, "gap.json"), gapped, terminal=True)
            errors.append("fixture: inventory with an unused mandatory consensus member was accepted")
        except ValueError:
            pass
        # Rejection: evidence whose bytes the inventory does not pin never verifies.
        case.data["invocations"][0]["attestation"]["digest"] = "e" * 64
        if case.reconcile(evidence=case.signed()) != "unknown":
            errors.append("fixture: evidence not anchored to the inventory produced a verified state")
    finally:
        case.doCleanups()
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
    errors = check_files(_GOOD_QG, _GOOD_LEDGER, _GOOD_GATE_LEDGER)
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
        ("provisional vs terminal schema", "QG", "**Provisional vs terminal schema.**"),
        ("sole FinalArtifactHash computation", "QG", "computed only by `gated_hash`"),
        ("absent finality reads as final", "gate", "an absent `MarkerFinality`"),
        ("no assurance data at marker selection", "gate", "no inventory, roster, or assurance field is read here"),
        ("roster check belongs to opt-in", "gate", "belong to this opt-in predicate only"),
        ("no adapter means False", "gate", "with no host adapter the predicate returns False"),
        ("warden handoff tuple source", "gate", "`QGLegProofTuple`"),
        ("tuple rebuilds the marker", "gate", "rebuild the marker dict for `caller_allowed` from the ledger"),
        ("unknown never withholds PASS", "gate", "never a reason to withhold or fail PASS"),
        ("changed paths within gated set", "gate", "is in the inventory's `gated.paths`"),
        ("reconstruction keys on manifest opt-in line", "gate", "`**RequiredModelAssurance:** qg-verified` header line"),
        ("inventory or tuple is not an opt-in signal", "gate", "is not an opt-in signal"),
        ("gated_hash failure downgrades", "QG", "write `FinalArtifactHash: unknown` and `ModelAssurance: unknown`"),
    ]
    for label, target, needle in mutations:
        qg = _GOOD_QG.replace(needle, "") if target == "QG" else _GOOD_QG
        ledger = _GOOD_LEDGER.replace(needle, "") if target == "ledger" else _GOOD_LEDGER
        gate = _GOOD_GATE_LEDGER.replace(needle, "") if target == "gate" else _GOOD_GATE_LEDGER
        if not check_files(qg, ledger, gate):
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
        gate_ledger = GATE_LEDGER_DOC.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"QG MODEL-ASSURANCE CONTRACT: unreadable source: {exc}")
        return 1
    errors = check_files(qg, ledger, gate_ledger)
    if errors:
        print("QG MODEL-ASSURANCE CONTRACT DRIFT DETECTED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — quality-gate model-assurance contract aligned.")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
