#!/usr/bin/env python3
"""Validate Pi gate verdicts against disk-mediated dispatch evidence.

Usage: check_gate_provenance.py <dispatch-dir> [--marker <gate-verdict.md>]
       check_gate_provenance.py --selftest
Stdlib only. Exit 0 when provenance is complete, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def check(dispatch_dir: pathlib.Path, marker: pathlib.Path | None = None) -> list[str]:
    violations = []
    manifest_path = dispatch_dir / "manifest.jsonl"
    if not manifest_path.is_file():
        return ["GATE-NOT-RUN:manifest"]
    try:
        rows = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        return [f"invalid manifest: {exc}"]
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
    ledger_path = dispatch_dir / "receipt-ledger.jsonl"
    ledger_ids = set()
    try:
        for line in ledger_path.read_text().splitlines():
            if line.strip():
                ledger_ids.add(json.loads(line).get("dispatch_id"))
    except (OSError, ValueError):
        pass
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
        dispatch_id = pathlib.Path(row.get("file", "")).stem
        if dispatch_id not in ledger_ids:
            violations.append(f"GATE-NOT-RUN:{role} (receipt not bound)")
    if not ledger_path.is_file():
        violations.append("GATE-NOT-RUN:receipt-ledger")
    return violations


def selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        result = check(d)
        assert result, "missing manifest (self-review) must fail"
        (d / "manifest.jsonl").write_text(json.dumps({"seq": 1, "role": "crucible-red-team", "status": "completed", "file": "1-red-team.md", "dispatch_ref": "run-1", "actual_model": "provider/model", "harness": "pi"}) + "\n")
        (d / "receipt-ledger.jsonl").write_text('{"dispatch_id":"1-red-team","phase":"quality-gate:round/1","rcpt_sha256":"' + "0" * 64 + '","verdict":"PASS"}\n')
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
            print(f"- {error}")
        return 1
    print("PASS — gate dispatch provenance valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
