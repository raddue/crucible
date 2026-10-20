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
PIPELINE_STATUS_DOC = ROOT / "skills/build/references/pipeline-status.md"

_FREEZE_NEEDLES = {
    "gated set enumerated at the freeze point": "at the `FinalArtifactHash` freeze point",
    "freeze-point tracked enumeration": "`git -C <root> diff --no-renames --no-relative --name-status -z <base>`",
    "freeze-point untracked enumeration": "`git -C <root> ls-files --others --exclude-standard -z`",
}

# #750: the enumerations and the committed-tree revalidation are module code, not prose only.
_HELPER_NEEDLES = {
    "caller expected_gated from persisted base": "`committed_paths(root, gated.base)`",
}

QG_REQUIRED = {
    **_FREEZE_NEEDLES,
    **_HELPER_NEEDLES,
    "freeze enumeration helper": "`freeze_gated(root, base, untracked_at_start=...)`",
    "QG committed-tree revalidation": "`gated_hash(..., committed=True)`",
    "inventory section": "## Model Assurance Inventory (#746)",
    "QG caller committed-range expected_gated command is rename-safe": "git -C <root> diff --no-renames --no-relative --name-only -z <base>..HEAD",
    "durable inventory path": "memory/quality-gate/model-assurance/<run-id>.json",
    "record before consumption": "before its result is consumed",
    "demotion stays consumed": "keeps the original dispatch's consumed record",
    "verdict-mode members and synthesis": "consensus members and their separate synthesis",
    "model_resolution separation": "`model_resolution` ledger field",
    "unobservable consensus cap": "at most `configured`/`unknown`",
    "PASS never suppressed": "never suppresses an artifact PASS",
    "wrapper cannot attest children": "never attests its children",
    "bridged response counted once": "counts once — never a second row",
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
    "marker ModelAssurance is marker_assurance output": "`ModelAssurance` is the output of `marker_assurance`",
    "row labels never feed verified": "a row's `assurance` label is never an input to `verified`",
    "kind required on every row": "a required non-empty `kind`",
    "consensus rows carry kind": "`kind: consensus-member` / `consensus-synthesis`",
}

PIPELINE_REQUIRED = {
    "manifest writer rule for opt-in line": "every handoff manifest carries the `**RequiredModelAssurance:** qg-verified` header line",
}

GATE_LEDGER_REQUIRED = {
    **_FREEZE_NEEDLES,
    **_HELPER_NEEDLES,
    "committed-tree revalidation": "`gated_hash(data, root, committed=True)`",
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
    "expected_gated binds the artifact": "`expected_gated` binds the tuple to the artifact being authorized",
    "expected_gated never re-read from ledger": "never re-read from this ledger",
    "expected_gated rename-safe NUL command": "git -C <root> diff --no-renames --no-relative --name-only -z <base>..HEAD",
    "authenticated evidence covers gated and roster": "`canonical_evidence` covers `gated` and `roster`",
    "3-4 transition re-checks Phase 2 tuple": "re-checks Phase 2's tuple",
    "reconstruction keys on manifest opt-in line": "`**RequiredModelAssurance:** qg-verified` header line",
    "inventory or tuple is not an opt-in signal": "is not an opt-in signal",
    "gated_hash failure never passed as None": "is never passed to the predicate as `None`",
    "warden-verified blocks only the opted-in action": "if it is found in persisted state it blocks only the opted-in action pending explicit user resolution",
    "warden-verified never treated as none": "and is never treated as `none`",
}

LEDGER_REQUIRED = {
    "shape section": "### `model_assurance` shape (#746, additive optional)",
    "schema stays 2": "`schema_version` stays 2",
    "proof of record": "the inventory file, not the ledger row, is the proof of record",
    "no transcripts or credentials": "Never archive raw provider transcripts or credentials",
}

def check_files(qg: str, ledger: str, gate_ledger: str, pipeline: str | None = None) -> list[str]:
    errors = [f"QG: missing {label}" for label, needle in QG_REQUIRED.items() if needle not in qg]
    errors += [f"gate-ledger: missing {label}" for label, needle in GATE_LEDGER_REQUIRED.items()
               if needle not in gate_ledger]
    errors += [f"ledger: missing {label}" for label, needle in LEDGER_REQUIRED.items() if needle not in ledger]
    if pipeline is not None:
        errors += [f"pipeline-status: missing {label}" for label, needle in PIPELINE_REQUIRED.items()
                   if needle not in pipeline]
    return errors

_GOOD_QG = "\n".join([
    "## Model Assurance Inventory (#746)",
    "git -C <root> diff --no-renames --no-relative --name-only -z <base>..HEAD",
    "memory/quality-gate/model-assurance/<run-id>.json",
    "before its result is consumed",
    "keeps the original dispatch's consumed record",
    "consensus members and their separate synthesis",
    "separate from the terminal-round `model_resolution` ledger field",
    "QG assurance is at most `configured`/`unknown`",
    "never suppresses an artifact PASS",
    "A wrapper receipt (siege's included) never attests its children",
    "counts once — never a second row",
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
    "`ModelAssurance` is the output of `marker_assurance`",
    "a row's `assurance` label is never an input to `verified`",
    "a required non-empty `kind`",
    "written with `kind: consensus-member` / `consensus-synthesis`",
    *_FREEZE_NEEDLES.values(),
    *_HELPER_NEEDLES.values(),
    "`freeze_gated(root, base, untracked_at_start=...)`",
    "`gated_hash(..., committed=True)`",
])

_GOOD_PIPELINE = "every handoff manifest carries the `**RequiredModelAssurance:** qg-verified` header line"

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
    "`expected_gated` binds the tuple to the artifact being authorized",
    "never re-read from this ledger",
    "git -C <root> diff --no-renames --no-relative --name-only -z <base>..HEAD",
    "`canonical_evidence` covers `gated` and `roster`",
    "re-checks Phase 2's tuple",
    "takes the requirement from the manifests' `**RequiredModelAssurance:** qg-verified` header line",
    "A retained inventory or a `QGProofTuple` is not an opt-in signal",
    "is never passed to the predicate as `None`",
    "if it is found in persisted state it blocks only the opted-in action pending explicit user resolution",
    "and is never treated as `none`",
    *_FREEZE_NEEDLES.values(),
    *_HELPER_NEEDLES.values(),
    "`gated_hash(data, root, committed=True)`",
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
            return qma.caller_allowed("qg-verified", m, path, digest, "b" * 64,
                                      **{"expected_gated": ["a.txt"], **trusted, **over})

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
            "tuple for another artifact authorized this phase artifact (expected_gated not bound)": dict(
                expected_gated=["new.md"]),
            "missing expected_gated was accepted": dict(expected_gated=None),
            "marker Gated-Files differing from the inventory gated set was accepted": dict(
                m={**marker, "Gated-Files": json.dumps(["a.txt", "extra.txt"])}),
        }
        for label, over in flips.items():
            if allowed(**over):
                errors.append(f"fixture: {label}")
        # Rejection: a None binding (gated_hash failure, absent marker FinalArtifactHash, no digest) never authorizes.
        bare = {k: v for k, v in marker.items() if k != "FinalArtifactHash"}
        if qma.caller_allowed("qg-verified", bare, path, digest, None, expected_gated=["a.txt"], **trusted):
            errors.append("fixture: absent marker FinalArtifactHash with a None current hash was accepted")
        if qma.caller_allowed("qg-verified", marker, path, None, "b" * 64, expected_gated=["a.txt"], **trusted):
            errors.append("fixture: a None digest was accepted")
        if not qma.caller_allowed("none", {"Verdict": "PASS"}, None, None, None):
            errors.append("fixture: ordinary PASS was blocked by a None binding")
        # Rejection: an unapproved request (equal to every turn) or an empty policy is never verified.
        cheap = {"model": "provider/cheap-haiku", "effort": "low", "route": "fixed"}
        saved = [dict(r.get("request") or {}) for r in case.data["invocations"][:2]]
        for row in case.data["invocations"][:2]:
            row["request"] = dict(cheap)
        for name, res in (("review", "1" * 64), ("synthesis", "2" * 64)):
            case.put_record(name, {"id": name, "result_digest": res, "turns": [cheap]})
        if case.reconcile(evidence=case.signed()) != "unknown" or case.reconcile(evidence=case.signed(), policy={}) != "unknown":
            errors.append("fixture: an unapproved request produced a verified state")
        for row, old_req in zip(case.data["invocations"][:2], saved):
            row["request"] = old_req
        for name, res in (("review", "1" * 64), ("synthesis", "2" * 64)):
            case.put_record(name, {"id": name, "result_digest": res, "turns": [case.TURN]})
        if case.reconcile(evidence=case.signed()) != "verified":
            errors.append("fixture: restored approved request did not reconcile to verified")
        # Rejection: a verified inventory whose roster records a non-PASS chunk cannot authorize a PASS marker.
        case.data["roster"]["terminal"]["c2"] = "ESCALATED"
        esc_path = pathlib.Path(case.tmp.name, "esc.json")
        esc_digest = qma.write_inventory(esc_path, case.data, terminal=True)
        esc_marker = {**marker, "ModelAssuranceInventory": f"{esc_path} sha256:{esc_digest}"}
        if qma.caller_allowed("qg-verified", esc_marker, esc_path, esc_digest, "b" * 64,
                              expected_gated=["a.txt"], **trusted):
            errors.append("fixture: ESCALATED roster chunk authorized a PASS marker")
        case.data["roster"]["terminal"]["c2"] = "PASS"
        # Rejection: self-labelled verified rows with no host adapter never yield a verified marker.
        if qma.marker_assurance(case.data, case.POLICY) == "verified":
            errors.append("fixture: marker_assurance trusted row labels without a host adapter")
        # Rejection: a terminal row with no `kind` is refused (consensus cap keys on it).
        kindless = json.loads(json.dumps(case.data))
        del kindless["invocations"][0]["kind"]
        try:
            qma.write_inventory(pathlib.Path(case.tmp.name, "kindless.json"), kindless, terminal=True)
            errors.append("fixture: terminal inventory row without kind was accepted")
        except ValueError:
            pass
        # Rejection: same-uid evidence (the reviewer's own uid owns it) never verifies.
        with mock.patch.object(qma.os, "getuid", return_value=case.real_uid):
            if case.reconcile() != "unknown":
                errors.append("fixture: reviewer-uid-owned evidence produced a verified state")
        # Rejection: a reviewer not provably unprivileged (uid 0, any capability, NoNewPrivs 0, unreadable
        # status) can rewrite adapter-owned files, so ownership cannot certify them.
        for name in ("getuid", "geteuid"):
            with mock.patch.object(qma.os, name, return_value=0):
                if case.reconcile() != "unknown":
                    errors.append(f"fixture: uid-0 reviewer ({name}) produced a verified state")
        status = pathlib.Path(case.tmp.name, "status")
        for label, text in (("non-DAC capability", fx.STATUS_OK.replace("CapEff:\t0000000000000000", "CapEff:\t0000000000000001")),
                            ("NoNewPrivs 0", fx.STATUS_OK.replace("NoNewPrivs:\t1", "NoNewPrivs:\t0")),
                            ("CapPrm", fx.STATUS_OK.replace("CapPrm:\t0000000000000000", "CapPrm:\t0000000000000004"))):
            status.write_text(text)
            if case.reconcile() != "unknown":
                errors.append(f"fixture: {label} reviewer produced a verified state")
        status.write_text(fx.STATUS_OK)
        # Rejection: turns that contradict the row's request (or mix models) are never verified.
        wide = {**case.POLICY, "provider/b": {"effort": "xhigh", "route": "r2"}}
        case.put_record("review", {"id": "review", "result_digest": "1" * 64,
                                   "turns": [{"model": "provider/b", "effort": "xhigh", "route": "r2"}]})
        if case.reconcile(evidence=case.signed(), policy=wide) != "unknown":
            errors.append("fixture: turns contradicting the row request produced a verified state")
        case.put_record("review", {"id": "review", "result_digest": "1" * 64, "turns": [case.TURN]})
        if case.reconcile(evidence=case.signed()) != "verified":
            errors.append("fixture: restored evidence did not reconcile to verified")
        # Property: every top-level canonical field and each record digest is under the signature.
        base = qma.canonical_evidence(case.data, case.journal, case.records)
        for key, val in (("run_id", "run-2"), ("artifact_hash", "f" * 64), ("final_artifact_hash", "f" * 64),
                         ("gated", {**case.data["gated"], "paths": ["other.md"]}),
                         ("roster", {**case.data["roster"], "terminal": {}})):
            if qma.canonical_evidence({**case.data, key: val}, case.journal, case.records) == base:
                errors.append(f"fixture: canonical evidence does not cover {key}")
        if qma.canonical_evidence(case.data, case.journal[:-1], case.records) == base:
            errors.append("fixture: canonical evidence does not cover the journal")
        for name in case.records:
            changed = {**case.records, name: {**case.records[name], "digest": "f" * 64}}
            if qma.canonical_evidence(case.data, case.journal, changed) == base:
                errors.append(f"fixture: canonical evidence does not cover the {name} record digest")
        # Rejection: malformed request/policy shapes read unknown and never raise.
        shaped = json.loads(json.dumps(case.data))
        shaped["invocations"][0]["request"] = "provider/model"
        try:
            if qma.marker_assurance(shaped, ["bad-policy"]) != "unknown":
                errors.append("fixture: malformed request/policy did not read unknown")
        except Exception as exc:  # noqa: BLE001 - the property is that nothing escapes
            errors.append(f"fixture: marker_assurance raised on malformed request/policy: {exc!r}")
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
        nl = b"\n"
        receipt = (
            "RCPT v1.1 quality-gate/1-crucible-red-team\nVERDICT  PASS  conf=0.90\n"
            "ARTIFACTS\n"
            f"  round-1-findings.md sha256:{hashlib.sha256(b'finding' + nl).hexdigest()} 8\n"
            f"  fix-journal.md sha256:{hashlib.sha256(b'journal' + nl).hexdigest()} 8\n"
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

_MUTANTS = {
    "completeness reconciliation removed": ("if consumed != expected or set(records) != consumed:",
                                            "if set(records) != consumed:"),
    "journal/inventory id-set equality removed": ("if seen != {row['id'] for row in data['invocations']}:", "if False:"),
    "journal dropped from signed bytes": ("'journal': journal, 'records': records}", "'records': records}"),
    "record digests dropped from signed bytes": (
        "    return json.dumps({'run_id': data['run_id'], 'artifact_hash': data['artifact_hash'],",
        "    records = {k: {'path': v['path']} for k, v in records.items()}\n"
        "    return json.dumps({'run_id': data['run_id'], 'artifact_hash': data['artifact_hash'],"),
    "gated dropped from signed bytes": ("                       'gated': data['gated'],\n", ""),
    "roster dropped from signed bytes": ("                       'roster': data['roster'],\n", ""),
    "row kinds dropped from signed bytes": (
        "                       'kinds': {row['id']: row.get('kind') for row in data['invocations']},\n", ""),
    "unprivileged reviewer check removed": (" or not _unprivileged_reviewer():", ":"),
    "turn equals request check removed": ("any(not isinstance(turn, dict) or any(turn.get(key) != request[key]",
                                          "any(not isinstance(turn, dict) or any(False"),
    "evidence file size cap removed": ("if len(raw) > MAX_INVENTORY_BYTES:\n        raise ValueError('evidence file",
                                       "if False:\n        raise ValueError('evidence file"),
    "request policy approval removed": (
        "or not record['turns'] or configured_assurance(request, policy) != 'configured'",
        "or not record['turns']"),
    "None final hash binding removed": (
        "if not (_hex64(current_final_hash) and _hex64(digest) and _hex64(marker.get('FinalArtifactHash'))):",
        "if False:"),
    "expected_gated artifact binding removed": ("if not set(expected_gated) <= set(data['gated']['paths']):",
                                                "if False:"),
    "expected_gated requirement removed": ("if (not isinstance(expected_gated, (list, tuple, set, frozenset))\n            or any(not isinstance(item, str) for item in expected_gated)):",
                                           "if False:"),
    "expected_gated non-empty requirement removed": ("    if not expected_gated:\n        return False",
                                                     "    if False:\n        return False"),
    "committed-tree revalidation removed": ("    if committed and gated['mode'] == 'manifest' and _git(",
                                            "    if False and _git("),
    "clean-tree exemption dropped from freeze": (
        "for code, name in zip(status[0::2], status[1::2]) if name not in CLEAN_TREE_EXEMPT]",
        "for code, name in zip(status[0::2], status[1::2])]"),
    "gate-start untracked snapshot ignored": ("    skip = CLEAN_TREE_EXEMPT | set(untracked_at_start)",
                                              "    skip = CLEAN_TREE_EXEMPT"),
    "committed_paths base check removed": ("    if not _commit_id(base):\n        raise ValueError('base must",
                                           "    if False:\n        raise ValueError('base must"),
    "roster PASS check removed": ("if any(value != 'PASS' for value in data['roster']['terminal'].values()):",
                                  "if False:"),
}


def _mutation_guards() -> list[str]:
    """Apply each mutant to a temp copy of the module (never the real one); the module tests must fail."""
    errors: list[str] = []
    scripts = pathlib.Path(__file__).resolve().parent
    source = (scripts / "qg_model_assurance.py").read_text(encoding="utf-8")
    for label, (old, new) in _MUTANTS.items():
        if source.count(old) != 1:
            errors.append(f"mutant anchor not found: {label}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("test_qg_model_assurance.py", "qg_source.py"):
                (pathlib.Path(tmp) / name).write_text((scripts / name).read_text(encoding="utf-8"), encoding="utf-8")
            (pathlib.Path(tmp) / "qg_model_assurance.py").write_text(source.replace(old, new), encoding="utf-8")
            run = subprocess.run([sys.executable, "test_qg_model_assurance.py"], cwd=tmp,
                                 capture_output=True, text=True)
            if run.returncode == 0:
                errors.append(f"mutant survived the module tests: {label}")
    return errors


def selftest() -> int:
    errors = check_files(_GOOD_QG, _GOOD_LEDGER, _GOOD_GATE_LEDGER, _GOOD_PIPELINE)
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
        ("expected_gated binds the artifact", "gate", "`expected_gated` binds the tuple to the artifact being authorized"),
        ("expected_gated never re-read from ledger", "gate", "never re-read from this ledger"),
        ("expected_gated rename-safe NUL command", "gate", "git -C <root> diff --no-renames --no-relative --name-only -z <base>..HEAD"),
        ("authenticated evidence covers gated and roster", "gate", "`canonical_evidence` covers `gated` and `roster`"),
        ("3-4 transition re-checks Phase 2 tuple", "gate", "re-checks Phase 2's tuple"),
        ("gated set enumerated at the freeze point", "QG", "at the `FinalArtifactHash` freeze point"),
        ("gated set enumerated at the freeze point (gate)", "gate", "at the `FinalArtifactHash` freeze point"),
        ("freeze-point tracked enumeration", "QG", "`git -C <root> diff --no-renames --no-relative --name-status -z <base>`"),
        ("freeze-point tracked enumeration (gate)", "gate", "`git -C <root> diff --no-renames --no-relative --name-status -z <base>`"),
        ("freeze-point untracked enumeration", "QG", "`git -C <root> ls-files --others --exclude-standard -z`"),
        ("freeze-point untracked enumeration (gate)", "gate", "`git -C <root> ls-files --others --exclude-standard -z`"),
        ("QG caller committed-range expected_gated command is rename-safe", "QG", "git -C <root> diff --no-renames --no-relative --name-only -z <base>..HEAD"),
        ("reconstruction keys on manifest opt-in line", "gate", "`**RequiredModelAssurance:** qg-verified` header line"),
        ("inventory or tuple is not an opt-in signal", "gate", "is not an opt-in signal"),
        ("gated_hash failure never passed as None", "gate", "is never passed to the predicate as `None`"),
        ("warden-verified blocks only the opted-in action", "gate", "if it is found in persisted state it blocks only the opted-in action pending explicit user resolution"),
        ("warden-verified never treated as none", "gate", "and is never treated as `none`"),
        ("gated_hash failure downgrades", "QG", "write `FinalArtifactHash: unknown` and `ModelAssurance: unknown`"),
        ("marker ModelAssurance is marker_assurance output", "QG", "`ModelAssurance` is the output of `marker_assurance`"),
        ("row labels never feed verified", "QG", "a row's `assurance` label is never an input to `verified`"),
        ("kind required on every row", "QG", "a required non-empty `kind`"),
        ("consensus rows carry kind", "QG", "`kind: consensus-member` / `consensus-synthesis`"),
        ("caller expected_gated from persisted base", "QG", "`committed_paths(root, gated.base)`"),
        ("caller expected_gated from persisted base (gate)", "gate", "`committed_paths(root, gated.base)`"),
        ("freeze enumeration helper", "QG", "`freeze_gated(root, base, untracked_at_start=...)`"),
        ("QG committed-tree revalidation", "QG", "`gated_hash(..., committed=True)`"),
        ("committed-tree revalidation", "gate", "`gated_hash(data, root, committed=True)`"),
        ("manifest writer rule for opt-in line", "pipeline", "every handoff manifest carries the `**RequiredModelAssurance:** qg-verified` header line"),
    ]
    for label, target, needle in mutations:
        qg = _GOOD_QG.replace(needle, "") if target == "QG" else _GOOD_QG
        ledger = _GOOD_LEDGER.replace(needle, "") if target == "ledger" else _GOOD_LEDGER
        gate = _GOOD_GATE_LEDGER.replace(needle, "") if target == "gate" else _GOOD_GATE_LEDGER
        pipe = _GOOD_PIPELINE.replace(needle, "") if target == "pipeline" else _GOOD_PIPELINE
        if not check_files(qg, ledger, gate, pipe):
            errors.append(f"selftest: removing {label!r} did not fail")
    errors.extend(f"selftest: {error}" for error in _behavior_fixtures())
    errors.extend(f"selftest: {error}" for error in _mutation_guards())
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
        pipeline = PIPELINE_STATUS_DOC.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"QG MODEL-ASSURANCE CONTRACT: unreadable source: {exc}")
        return 1
    errors = check_files(qg, ledger, gate_ledger, pipeline)
    if errors:
        print("QG MODEL-ASSURANCE CONTRACT DRIFT DETECTED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK — quality-gate model-assurance contract aligned.")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
