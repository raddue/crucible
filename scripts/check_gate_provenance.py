#!/usr/bin/env python3
"""Validate Pi gate verdicts against disk-mediated dispatch evidence.

Usage: check_gate_provenance.py <dispatch-dir> [--marker <gate-verdict.md>]
       check_gate_provenance.py --selftest
Stdlib only. Exit 0 when provenance is complete, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def check(dispatch_dir: pathlib.Path, marker: pathlib.Path | None = None) -> list[str]:
    violations = []
    manifest_path = dispatch_dir / "manifest.jsonl"
    if not manifest_path.is_file():
        return ["BLOCKED: DISPATCH-UNAVAILABLE", "missing manifest.jsonl"]
    try:
        rows = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        return [f"invalid manifest: {exc}"]
    if not rows:
        return ["BLOCKED: DISPATCH-UNAVAILABLE", "empty manifest.jsonl"]
    if marker is not None:
        try:
            marker_text = marker.read_text()
        except OSError as exc:
            return [f"cannot read marker: {exc}"]
        if re.search(r"^Harness:\s*pi\s*$", marker_text, re.M) is None:
            return []  # This Pi-first checker does not enforce Claude Code markers.
        if re.search(r"^Verdict:\s*PASS\b", marker_text, re.M) is None:
            return []
        required = re.search(r"^Required-Legs:\s*(.+)$", marker_text, re.M)
        mappings = dict(re.findall(r"^Mapped-Model:\s*(\S+)=(\S+)\s*$", marker_text, re.M))
        if required is None:
            return ["GATE-NOT-RUN:required-legs"]
        roles = [role.strip() for role in required.group(1).split(",") if role.strip()]
        if any(role not in mappings for role in roles):
            return [f"DISPATCH-UNMAPPED:{role}" for role in roles if role not in mappings]
    else:
        roles = sorted({r.get("role") for r in rows if r.get("status") != "skipped" and r.get("role")})
    if not roles:
        return ["BLOCKED: DISPATCH-UNAVAILABLE", "no required dispatch legs"]
    ledger_path = dispatch_dir / "receipt-ledger.jsonl"
    try:
        ledger = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
        if not ledger or any(
            not isinstance(entry, dict)
            or not isinstance(entry.get("dispatch_id"), str)
            or not isinstance(entry.get("phase"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry.get("rcpt_sha256", ""))
            or entry.get("verdict") not in {"PASS", "FAIL", "BLOCKED"}
            for entry in ledger
        ):
            raise ValueError("empty or invalid receipt-ledger row")
    except (OSError, ValueError, TypeError) as exc:
        return [f"GATE-NOT-RUN:receipt-ledger ({exc})"]
    for role in roles:
        matches = [r for r in rows if r.get("role") == role and r.get("status") == "completed"]
        if not matches:
            violations.append(f"GATE-NOT-RUN:{role}")
            continue
        row = matches[-1]
        if row.get("harness") != "pi":
            violations.append(f"GATE-NOT-RUN:{role} (harness is not pi)")
        if not row.get("dispatch_ref"):
            violations.append(f"GATE-NOT-RUN:{role} (missing dispatch_ref)")
        if not row.get("actual_model"):
            violations.append(f"GATE-NOT-RUN:{role} (missing actual_model)")
        mapped = mappings.get(role)
        if mapped and row.get("actual_model") != mapped:
            violations.append(f"GATE-NOT-RUN:{role} (actual_model differs from mapped model)")
        filename = row.get("file")
        if not isinstance(filename, str):
            violations.append(f"GATE-NOT-RUN:{role} (invalid manifest file: expected string)")
            continue
        dispatch_id = pathlib.Path(filename).stem
        receipts = sorted(p for p in dispatch_dir.iterdir() if p.is_file()
                          and p.name != row.get("file")
                          and (p.name.startswith(dispatch_id + "-") or p.name.startswith(dispatch_id + ".")))
        if not receipts:
            violations.append(f"GATE-NOT-RUN:{role} (receipt unavailable for {dispatch_id})")
            continue
        errors = []
        for receipt in receipts:
            try:
                text = receipt.read_text()
            except (OSError, UnicodeError) as exc:
                errors.append(f"cannot read receipt: {exc}")
                continue
            normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).rstrip("\n") + "\n"
            digest = hashlib.sha256(normalized.encode()).hexdigest()
            if not any(entry["dispatch_id"] == dispatch_id and entry["rcpt_sha256"] == digest
                       and entry["verdict"] == "PASS" for entry in ledger):
                errors.append(f"receipt not bound to PASS ledger row: {receipt.name}")
                continue
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/rcpt_verify.py"), "--tier2", "--strict",
                     "--root", str(dispatch_dir), "--ledger", str(ledger_path), str(receipt)],
                    capture_output=True, text=True)
            except OSError as exc:
                errors.append(f"receipt verifier unavailable: {exc}")
                continue
            coverage = re.search(r"^TIER2-COVERAGE: artifacts (\d+)/(\d+)\b.*$",
                                 result.stderr, re.M)
            if result.returncode or coverage is None:
                errors.append(f"receipt verification failed: {result.stderr.strip()}")
                continue
            verified_artifacts, declared_artifacts = map(int, coverage.groups())
            if not re.match(rf"^RCPT v1(?:\.1)? \S+/{re.escape(dispatch_id)}\s*$", text.split("\n", 1)[0]):
                errors.append(f"receipt dispatch ID mismatch: {receipt.name}")
                continue
            if verified_artifacts < 1:
                errors.append(f"receipt has no resolved artifact evidence: {verified_artifacts}/{declared_artifacts}")
                continue
            break
        else:
            violations.append(f"GATE-NOT-RUN:{role} ({'; '.join(errors)})")
    return violations


def selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        result = check(d)
        assert result[0] == "BLOCKED: DISPATCH-UNAVAILABLE", "missing manifest must block"
        (d / "manifest.jsonl").write_text(json.dumps({"seq": 1, "role": "crucible-red-team", "status": "completed", "file": "1-red-team.md", "dispatch_ref": "run-1", "actual_model": "provider/model", "harness": "pi"}) + "\n")
        artifact = "finding.md"
        artifact_bytes = b"finding\n"
        (d / artifact).write_bytes(artifact_bytes)
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        receipt = (
            "RCPT v1.1 quality-gate/1-red-team\nVERDICT  PASS  conf=0.90\n"
            "ARTIFACTS\n  finding.md sha256:" + artifact_hash + " 8\n"
            "TRACE\n  1  SKIPPED  no-artifacts\nCLAIMS\n  (none)\n"
            "WITNESS    lint:trace-consistent  expect-fail=/inconsistent/  ran=TRACE#1\n"
            "SUSPICION  0.00\nNEXT       (none)\nTRIPWIRE: none\nSUPERSEDES: none\n"
            "TRIPWIRE-CHILD: none\n"
        )
        (d / "1-red-team-receipt.md").write_text(receipt)
        (d / "receipt-ledger.jsonl").write_text(json.dumps({"dispatch_id": "1-red-team", "phase": "quality-gate:round/1", "rcpt_sha256": hashlib.sha256(receipt.encode()).hexdigest(), "verdict": "PASS"}) + "\n")
        marker = d / "gate-verdict.md"
        marker.write_text("Harness: pi\nVerdict: PASS\nRequired-Legs: crucible-red-team\nMapped-Model: crucible-red-team=provider/model\n")
        assert not check(d, marker), f"full Pi leg set must pass: {check(d, marker)}"
        row = json.loads((d / "manifest.jsonl").read_text())
        row.pop("dispatch_ref")
        (d / "manifest.jsonl").write_text(json.dumps(row) + "\n")
        assert any("missing dispatch_ref" in v for v in check(d, marker)), "missing dispatch_ref must fail"
        row["dispatch_ref"] = "run-1"
        row["actual_model"] = "provider/other"
        (d / "manifest.jsonl").write_text(json.dumps(row) + "\n")
        assert any("differs from mapped model" in v for v in check(d, marker)), "model mismatch must fail"
    print("SELFTEST OK — valid Pi provenance passes; self-review, missing dispatch_ref, and model mismatch fail.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dispatch_dir", nargs="?", type=pathlib.Path)
    parser.add_argument("--marker", type=pathlib.Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.dispatch_dir is None:
        parser.error("dispatch_dir is required unless --selftest is used")
    errors = check(args.dispatch_dir, args.marker)
    if errors:
        for error in errors:
            print(error if error.startswith("BLOCKED: ") else f"- {error}")
        return 1
    print("PASS — gate dispatch provenance valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
