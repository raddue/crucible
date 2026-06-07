#!/usr/bin/env python3
"""Runtime receipt linter (Ledger Return Protocol). Tier-1 (v1 structural, ported
verbatim from eval/ledger-return-protocol/lint.py) + Tier-2 parts 1-2 (disk sha256 +
witness byte-range). stdlib-only, argparse-free. Exit 0=pass, 1=fail; bullets on stderr.

Usage:
  rcpt_verify.py [--tier1|--tier2] [--root DIR] [--strict] [FILE|-]
  rcpt_verify.py --selftest
  rcpt_verify.py --eval FILE.jsonl
"""
from __future__ import annotations
import json, re, sys, hashlib, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "eval/ledger-return-protocol"


class LintError(Exception):
    pass


# ── Tier-1 (v1 structural) — ported VERBATIM from eval/ledger-return-protocol/lint.py
#    (lint.py SECTIONS..lint_receipt, the eval-validated v1 layer). Do NOT re-derive:
#    the differential oracle gate (scripts/_oracle_gate.py) proves byte-equivalence.
SECTIONS = ["RCPT", "VERDICT", "ARTIFACTS", "TRACE", "CLAIMS", "WITNESS", "SUSPICION", "NEXT"]
UNRUNNABLE_VOCAB = {
    "sandbox-restricted", "tooling-absent", "platform-incompatible",
    "network-unreachable", "service-unavailable", "time-budget-exceeded",
    "requires-human-input",
}
LINT_RULES = {"all-claims-cited", "trace-consistent", "skip-declared"}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONF = re.compile(r"^(0\.\d{2}|1\.00)$")


def parse_receipt(text):
    """Parse receipt into {section: body_lines} dict. Body lines preserve
    their original content (including leading whitespace)."""
    lines = text.splitlines()
    if not lines:
        raise LintError("empty receipt")
    # First line must be RCPT v1 or v1.1
    header_m = re.match(r"^RCPT v(1(?:\.1)?) (.+)$", lines[0])
    if not header_m:
        raise LintError("first line must start with 'RCPT v1 ' or 'RCPT v1.1 '")
    sections = {"RCPT": [header_m.group(2)]}
    current = None
    for line in lines[1:]:
        stripped = line.lstrip()
        matched = None
        for name in SECTIONS[1:]:
            if line.startswith(name):
                matched = name
                break
        if matched:
            if matched in sections:
                raise LintError(f"section {matched} duplicated")
            rest = line[len(matched):].lstrip()
            sections[matched] = [rest] if rest else []
            current = matched
        else:
            if current is None:
                raise LintError(f"prose before first section header: {line!r}")
            sections[current].append(line)
    # Check order (unknown sections after NEXT ignored — but SECTIONS list is the strict v1 set)
    got_order = [s for s in SECTIONS if s in sections]
    if got_order != SECTIONS[:len(got_order)]:
        raise LintError(f"sections out of order: got {got_order}")
    missing = [s for s in SECTIONS if s not in sections]
    if missing:
        raise LintError(f"missing required sections: {missing}")
    return sections


def parse_artifacts(body):
    """Returns {name: {hash, size, meta}} from ARTIFACTS body lines."""
    out = {}
    # body is indented lines; skip blanks and "(none)"
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line == "(none)":
            return {}
        parts = line.split()
        if len(parts) < 3:
            raise LintError(f"ARTIFACTS malformed: {raw!r}")
        name, hash_field, size = parts[0], parts[1], parts[2]
        if not hash_field.startswith("sha256:") or not HEX64.match(hash_field[len("sha256:"):]):
            raise LintError(f"ARTIFACTS bad hash: {raw!r}")
        out[name] = {"hash": hash_field[len("sha256:"):], "size": size}
    return out


def parse_trace(body):
    """Returns list of {n, verb, args_str} entries."""
    out = []
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            raise LintError(f"TRACE malformed: {raw!r}")
        n_str, verb = parts[0], parts[1]
        args = parts[2] if len(parts) == 3 else ""
        if not n_str.isdigit():
            raise LintError(f"TRACE index not integer: {raw!r}")
        if verb not in {"READ", "EDIT", "WROTE", "EXEC", "DISPATCHED", "CONSULTED", "SKIPPED"}:
            raise LintError(f"TRACE unknown verb: {verb!r}")
        out.append({"n": int(n_str), "verb": verb, "args": args})
    for i, entry in enumerate(out, start=1):
        if entry["n"] != i:
            raise LintError(f"TRACE indices not 1-based contiguous: expected {i} got {entry['n']}")
    return out


def check_exec_range_bound(args_str):
    """out=<artifact>#<range> — check range ≤ 4 KiB."""
    m = re.search(r"out=\S+#([LB])(\d+)-\1(\d+)", args_str)
    if not m:
        raise LintError(f"EXEC missing out= or bad range: {args_str}")
    kind, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    if b < a:
        raise LintError(f"EXEC range negative: {args_str}")
    span_bytes = (b - a) if kind == "B" else (b - a) * 80  # 80 bytes/line conservative estimate
    if span_bytes > 4096:
        raise LintError(f"EXEC range exceeds 4 KiB: {args_str}")


def parse_claims(body):
    out = []
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        # pattern= may be quoted (containing spaces) or a /regex/ form or bare
        m = re.match(
            r'^([^\s=]+)=(\S+)\s+from=(\S+)(?:\s+pattern=("[^"]*"|/[^/]*/|\S+))?$',
            line,
        )
        if not m:
            raise LintError(f"CLAIM malformed: {raw!r}")
        out.append({"key": m.group(1), "value": m.group(2), "citation": m.group(3), "pattern": m.group(4)})
    return out


def parse_witness(body):
    if not body:
        raise LintError("WITNESS missing")
    line = body[0].strip()
    if line == "(n/a)":
        raise LintError("WITNESS is '(n/a)' — not permitted under any verdict")
    # form: <kind>:<payload>  expect-fail=<sig>  ran=<disp>
    # expect-fail sig may be /regex/ or "literal" which can contain spaces.
    # Anchor on `  ran=` (last occurrence) and split backwards.
    if "  ran=" not in line and " ran=" not in line:
        raise LintError(f"WITNESS missing ran= clause: {line!r}")
    head, _, ran = line.rpartition("ran=")
    head = head.rstrip()
    if not head.endswith(" "):
        # ran= must be preceded by whitespace
        pass
    # head now ends before " ran=". Find " expect-fail=" (first occurrence after payload).
    if "expect-fail=" not in head:
        raise LintError(f"WITNESS missing expect-fail= clause: {line!r}")
    kind_payload, _, expect_fail = head.rpartition("expect-fail=")
    kind_payload = kind_payload.rstrip()
    expect_fail = expect_fail.strip()
    if ":" not in kind_payload:
        raise LintError(f"WITNESS kind:payload malformed: {line!r}")
    kind, _, payload = kind_payload.partition(":")
    kind = kind.strip()
    payload = payload.strip()
    ran = ran.strip()
    if kind not in {"exec", "grep", "lint"}:
        raise LintError(f"WITNESS kind unknown: {kind!r}")
    if kind == "lint" and payload not in LINT_RULES:
        raise LintError(f"WITNESS lint rule unknown: {payload!r}")
    # expect-fail validation
    if not expect_fail:
        raise LintError("WITNESS expect-fail empty")
    if expect_fail.startswith("/") and expect_fail.endswith("/"):
        pattern = expect_fail[1:-1]
        if len(pattern) < 4 or pattern in {".*", ".+"}:
            raise LintError(f"WITNESS expect-fail wildcard/too-short: {expect_fail!r}")
    elif expect_fail.startswith('"') and expect_fail.endswith('"'):
        if len(expect_fail[1:-1]) < 4:
            raise LintError(f"WITNESS expect-fail literal too short: {expect_fail!r}")
    elif not re.match(r"^(exit!=0|exit=-?\d+|match)$", expect_fail):
        raise LintError(f"WITNESS expect-fail not a valid signature form: {expect_fail!r}")
    return {"kind": kind, "payload": payload.strip(), "expect_fail": expect_fail, "ran": ran.strip()}


def lint_receipt(text):
    sections = parse_receipt(text)
    # VERDICT
    verdict_body = sections["VERDICT"]
    if not verdict_body:
        raise LintError("VERDICT empty")
    vm = re.match(r"^(PASS|FAIL|BLOCKED)\s+conf=(\S+)\s*$", verdict_body[0])
    if not vm:
        raise LintError(f"VERDICT malformed: {verdict_body[0]!r}")
    verdict = vm.group(1)
    if not CONF.match(vm.group(2)):
        raise LintError(f"VERDICT conf malformed: {vm.group(2)!r}")
    artifacts = parse_artifacts(sections["ARTIFACTS"])
    trace = parse_trace(sections["TRACE"])
    claims = parse_claims(sections["CLAIMS"])
    witness = parse_witness(sections["WITNESS"])
    # EXEC out= artifact must exist; range bound
    for entry in trace:
        if entry["verb"] == "EXEC":
            check_exec_range_bound(entry["args"])
            m = re.search(r"out=(\S+?)#", entry["args"])
            if m and m.group(1) not in artifacts:
                raise LintError(f"EXEC out= artifact not in ARTIFACTS: {m.group(1)}")
        elif entry["verb"] in {"EDIT", "WROTE"}:
            m = re.search(r"sha256:([0-9a-f]{64})", entry["args"])
            if not m:
                raise LintError(f"{entry['verb']} missing sha256: {entry['args']}")
            if m.group(1) not in {a["hash"] for a in artifacts.values()}:
                # artifact may be an on-disk path not re-declared; for lint purposes accept
                # only if the entry's path itself is in ARTIFACTS as key
                path_m = re.match(r"^(\S+)", entry["args"])
                if path_m and path_m.group(1) not in artifacts:
                    # Allow it — file may not be re-emitted as an ARTIFACT; a tightening
                    # is left as future work. For pilot, we don't hard-fail here.
                    pass
        elif entry["verb"] == "DISPATCHED":
            if not re.search(r"rcpt-sha256:[0-9a-f]{64}", entry["args"]):
                raise LintError(f"DISPATCHED missing rcpt-sha256: {entry['args']}")
    # CLAIM citations must resolve
    for c in claims:
        cit = c["citation"]
        if cit.startswith("TRACE#"):
            idx = int(cit[len("TRACE#"):])
            if not 1 <= idx <= len(trace):
                raise LintError(f"CLAIM citation TRACE#{idx} does not resolve")
        else:
            art_name = cit.split("#", 1)[0]
            # Receipt-hash prefix citations (used by SUPERSEDES justification)
            # are valid without appearing in ARTIFACTS. Layer 2 verifies the
            # hash resolves in the manifest.
            if re.match(r"^[0-9a-f]{12}$", art_name):
                continue
            if art_name not in artifacts:
                raise LintError(f"CLAIM citation artifact not listed: {art_name}")
    # WITNESS ran resolution + rules
    ran = witness["ran"]
    if verdict == "PASS":
        if ran.startswith("UNRUNNABLE"):
            raise LintError("WITNESS ran=UNRUNNABLE not permitted on PASS")
    if ran.startswith("TRACE#"):
        idx = int(ran[len("TRACE#"):])
        if not 1 <= idx <= len(trace):
            raise LintError(f"WITNESS ran=TRACE#{idx} does not resolve")
        verb = trace[idx - 1]["verb"]
        if witness["kind"] == "exec" and verb != "EXEC":
            raise LintError(f"WITNESS kind=exec requires ran= to point to EXEC (got {verb})")
        if witness["kind"] == "grep" and verb not in {"EXEC", "READ", "WROTE"}:
            raise LintError(f"WITNESS kind=grep requires ran= to point to EXEC/READ/WROTE (got {verb})")
    elif ran.startswith("SKIPPED:"):
        next_body = " ".join(sections["NEXT"])
        if witness["payload"] not in next_body:
            raise LintError(
                f"WITNESS ran=SKIPPED requires NEXT to contain witness payload verbatim; "
                f"payload={witness['payload']!r}  NEXT={next_body!r}"
            )
    elif ran.startswith("UNRUNNABLE:"):
        reason = ran[len("UNRUNNABLE:"):]
        if reason not in UNRUNNABLE_VOCAB:
            raise LintError(f"UNRUNNABLE reason not in closed vocabulary: {reason!r}")
    else:
        raise LintError(f"WITNESS ran= form unknown: {ran!r}")
    # mandatory-work: tests run OR tests-related CLAIM must be backed by EXEC/SKIPPED
    claim_keys = {c["key"] for c in claims}
    if {"tests-ran", "tests-pass"} & claim_keys:
        has_exec = any(e["verb"] == "EXEC" for e in trace)
        has_skipped = any(e["verb"] == "SKIPPED" and "tests" in e["args"].lower() for e in trace)
        if not (has_exec or has_skipped):
            raise LintError("tests-ran/tests-pass claim but no EXEC and no SKIPPED tests entry")
        # Check claim points at an EXEC and success-claim is consistent with exit code
        if not has_skipped:
            for c in claims:
                if c["key"] in {"tests-ran", "tests-pass"} and c["citation"].startswith("TRACE#"):
                    idx = int(c["citation"][len("TRACE#"):])
                    cited = trace[idx - 1]
                    if cited["verb"] != "EXEC":
                        raise LintError(f"CLAIM {c['key']} cites TRACE#{idx} which is {cited['verb']}, not EXEC")
                    # Consistency: tests-pass=true must not cite a non-zero-exit EXEC
                    if c["key"] == "tests-pass" and c["value"] == "true":
                        em = re.search(r"exit=(-?\d+)", cited["args"])
                        if em and int(em.group(1)) != 0:
                            raise LintError(
                                f"CLAIM tests-pass=true cites TRACE#{idx} with exit={em.group(1)} "
                                f"(structural contradiction)"
                            )
    return verdict


def _usage_exit():
    sys.stderr.write(__doc__)
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage_exit()
    # dispatch stub — filled in later tasks
    return _usage_exit()


if __name__ == "__main__":
    sys.exit(main())
