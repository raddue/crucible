#!/usr/bin/env python3
"""
Reference implementation of the Layer 2 Tripwire Manifest sweep.

Input: a JSONL scenario file. Each line is one of:
  - {"type": "receipt", "receipt": "<full v1.1 receipt text>"}
  - {"type": "expect-fire", "predicates": ["..."]}     — assert the last receipt's
      sweep fired exactly these predicates (on prior entries)
  - {"type": "expect-lint-fail", "reason_contains": "..."} — assert the last
      receipt's Tier-1 lint failed
  - {"type": "expect-lint-pass"}                        — assert clean lint

Runs the Tier-1 linter (from ../../../scripts/rcpt_verify.py) extended for v1.1, then the sweep.

Usage: python3 sweep.py <scenario.jsonl>
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

# Tier-1 linter now lives at scripts/rcpt_verify.py (the verbatim port of the former
# eval-only reference linter, #369). Load it by path so sweep.py's lint_receipt /
# parse_* / UNRUNNABLE_VOCAB / LintError references resolve against the single port.
# parents[3] = repo root (eval/ledger-return-protocol/tripwire/sweep.py → ../../../).
_RV_PATH = Path(__file__).resolve().parents[3] / "scripts/rcpt_verify.py"
_rv_spec = importlib.util.spec_from_file_location("rcpt_verify", _RV_PATH)
layer1 = importlib.util.module_from_spec(_rv_spec)
_rv_spec.loader.exec_module(layer1)


PREDICATE_VOCAB = {
    "suspicion>=", "claims-touch", "wrote", "read", "exec-exit!=0",
    "peer-dispatch-disagrees", "verdict=FAIL", "always",
}
GLOB_ENTRIES_CAP = 8
UNRUNNABLE_VOCAB = layer1.UNRUNNABLE_VOCAB


class LintError(layer1.LintError):
    pass


def parse_receipt_v11(text):
    """Parse v1.1 receipt: Layer 1 sections + TRIPWIRE + SUPERSEDES [+ TRIPWIRE-CHILD]."""
    version_m = re.match(r"^RCPT v(1|1\.1) ", text)
    if not version_m:
        raise LintError("header missing or bad version")
    version = version_m.group(1)
    sections = layer1.parse_receipt(text)
    # Look for Layer 2 sections after NEXT
    tail = text.split("\nNEXT", 1)[1] if "\nNEXT" in text else ""
    tail_lines = [l for l in tail.splitlines()[1:] if l.strip()]
    tripwire = supersedes = trip_child = None
    for line in tail_lines:
        if line.startswith("TRIPWIRE-CHILD:"):
            trip_child = line[len("TRIPWIRE-CHILD:"):].strip()
        elif line.startswith("TRIPWIRE:"):
            tripwire = line[len("TRIPWIRE:"):].strip()
        elif line.startswith("SUPERSEDES:"):
            supersedes = line[len("SUPERSEDES:"):].strip()
    if version == "1.1":
        if tripwire is None:
            raise LintError("v1.1 receipt missing TRIPWIRE:")
        if supersedes is None:
            raise LintError("v1.1 receipt missing SUPERSEDES:")
        # TRIPWIRE-CHILD required when TRACE contains any DISPATCHED verb
        trace_entries = layer1.parse_trace(sections["TRACE"])
        has_dispatched = any(t["verb"] == "DISPATCHED" for t in trace_entries)
        if has_dispatched and trip_child is None:
            raise LintError("v1.1 receipt with DISPATCHED in TRACE must emit TRIPWIRE-CHILD:")
    return {
        "version": version,
        "sections": sections,
        "tripwire": tripwire,
        "supersedes": supersedes,
        "trip_child": trip_child,
    }


def parse_predicates(body):
    if body == "none":
        return []
    preds = [p.strip() for p in body.split("|")]
    out = []
    for p in preds:
        # match predicate head
        m = re.match(r"^(suspicion>=[\d.]+|claims-touch\(.+?\)|wrote\(.+?\)|read\(.+?\)|exec-exit!=0|peer-dispatch-disagrees\(\w+\)|verdict=FAIL|always)$", p)
        if not m:
            raise LintError(f"unknown predicate: {p!r}")
        out.append(p)
    return out


def expand_glob_entries(glob):
    """Count the number of alternation entries in {a,b,c}; expand comma shortcut."""
    # glob may have comma shortcut: claims-touch(auth,payments)
    # Expand to {auth,payments}/**
    inside = re.search(r"\((.*)\)", glob)
    if not inside:
        return 1
    body = inside.group(1)
    # If body has commas and no braces, it's the shortcut form
    if "," in body and "{" not in body:
        return len(body.split(","))
    # Count entries in {a,b,c}
    brace = re.search(r"\{([^{}]*)\}", body)
    if brace:
        return len(brace.group(1).split(","))
    return 1


def compute_hash_prefix(receipt_text):
    import hashlib
    # normalize per Layer 1 binding rules
    lines = receipt_text.splitlines()
    norm = "\n".join(l.rstrip() for l in lines).rstrip() + "\n"
    return hashlib.sha256(norm.encode()).hexdigest()[:12]


def lint_v11(parsed, manifest):
    """Tier-1 v1.1 extensions beyond Layer 1."""
    if parsed["version"] != "1.1":
        return  # v1 receipts not required to carry Layer 2 sections
    trip = parsed["tripwire"]
    if trip is None:
        raise LintError("TRIPWIRE line missing")
    # TRIPWIRE=none requires PASS + suspicion=0.00
    verdict_line = parsed["sections"]["VERDICT"][0]
    verdict = verdict_line.split()[0]
    susp_line = parsed["sections"]["SUSPICION"][0]
    susp_val = susp_line.split()[0]
    if trip == "none":
        if verdict != "PASS" or susp_val != "0.00":
            raise LintError(f"TRIPWIRE: none requires PASS+0.00, got {verdict}+{susp_val}")
    else:
        predicates = parse_predicates(trip)
        for p in predicates:
            # glob cap
            if p.startswith(("claims-touch(", "wrote(", "read(")):
                if expand_glob_entries(p) > GLOB_ENTRIES_CAP:
                    raise LintError(f"glob entries exceed cap ({GLOB_ENTRIES_CAP}): {p}")
    # SUPERSEDES
    sup = parsed["supersedes"]
    if sup is None:
        raise LintError("SUPERSEDES line missing")
    if sup != "none":
        prefixes = [s.strip() for s in sup.split(",")]
        claims_body = "\n".join(parsed["sections"]["CLAIMS"])
        for prefix in prefixes:
            # must resolve uniquely in manifest
            matches = [m for m in manifest if m["hash_prefix"] == prefix]
            if len(matches) == 0:
                raise LintError(f"SUPERSEDES cites unknown prefix: {prefix}")
            if len(matches) > 1:
                raise LintError(f"SUPERSEDES prefix ambiguous: {prefix}")
            pred = matches[0]
            if pred.get("superseded_by"):
                raise LintError(f"SUPERSEDES cites already-superseded receipt: {prefix}")
            # justification: prefix must appear in CLAIMS from=<prefix>
            if f"from={prefix}#" not in claims_body:
                raise LintError(f"SUPERSEDES prefix {prefix} has no CLAIMS justification (expected from={prefix}#…)")
            # witness-evidence requirement
            if pred["verdict"] == "FAIL" or pred["suspicion"] >= 0.30:
                witness_line = parsed["sections"]["WITNESS"][0]
                w = layer1.parse_witness([witness_line])
                if w["kind"] == "lint":
                    raise LintError(
                        f"SUPERSEDES of FAIL/high-suspicion predecessor requires "
                        f"WITNESS kind in {{exec, grep}}, got lint"
                    )
                if w["ran"].startswith(("SKIPPED:", "UNRUNNABLE:")):
                    raise LintError(
                        f"SUPERSEDES of FAIL/high-suspicion predecessor requires "
                        f"witness ran=TRACE#N, got ran={w['ran']}"
                    )


def extract_discriminators(parsed):
    """Extract keys= and files= for manifest."""
    sections = parsed["sections"]
    skill = sections["RCPT"][0].split("/", 1)[0].strip()
    # keys: severity-max and *-count from CLAIMS
    claims = layer1.parse_claims(sections["CLAIMS"])
    keys = []
    for c in claims:
        if c["key"] == "severity-max" or re.match(r"^[a-z][a-z0-9-]*-count$", c["key"]):
            keys.append(f"{skill}:{c['key']}:{c['value']}")
    # files: EDIT/WROTE paths with first 6 hex of hash
    files = []
    trace = layer1.parse_trace(sections["TRACE"])
    for t in trace:
        if t["verb"] in {"EDIT", "WROTE"}:
            path_m = re.match(r"^(\S+)\s+sha256:([0-9a-f]{6})", t["args"])
            if path_m:
                files.append(f"{path_m.group(1)}:{path_m.group(2)}")
    return keys[:GLOB_ENTRIES_CAP], files[:GLOB_ENTRIES_CAP]


def match_glob(glob_body, paths):
    """Match shell-subset glob against a list of paths. Comma shortcut expanded."""
    # Extract body from claims-touch(...) / wrote(...) / read(...)
    m = re.match(r"[\w-]+\(([^)]*)\)", glob_body)
    if not m:
        return False
    body = m.group(1)
    # Comma shortcut: auth,payments → {auth,payments}/**
    if "," in body and "{" not in body:
        alternatives = body.split(",")
        patterns = [f"{a}/**" for a in alternatives]
    else:
        patterns = [body]
    import fnmatch
    for pattern in patterns:
        # Expand ** → *; fnmatch doesn't understand **, but we approximate:
        # a/**/b matches a/anything/b and a/b
        # Simple approximation: convert ** to * at each level
        fn_pattern = pattern.replace("**", "*")
        for path in paths:
            # Also check if path begins with a directory-shortcut match
            if fnmatch.fnmatch(path, fn_pattern):
                return True
            # Additional: try matching against any path-suffix
            parts = path.split("/")
            for i in range(len(parts)):
                candidate = "/".join(parts[i:])
                if fnmatch.fnmatch(candidate, fn_pattern):
                    return True
    return False


def predicate_fires_on_new(pred, new_parsed):
    """Does predicate fire on the new receipt?"""
    new_claims = layer1.parse_claims(new_parsed["sections"]["CLAIMS"])
    new_trace = layer1.parse_trace(new_parsed["sections"]["TRACE"])
    new_susp = float(new_parsed["sections"]["SUSPICION"][0].split()[0])
    claim_paths = []
    for c in new_claims:
        cit = c["citation"]
        if not cit.startswith("TRACE#") and "#" in cit:
            claim_paths.append(cit.split("#", 1)[0])
    write_paths = [re.match(r"^(\S+)", t["args"]).group(1) for t in new_trace if t["verb"] in {"EDIT", "WROTE"}]
    read_paths = [re.match(r"^(\S+)", t["args"]).group(1) for t in new_trace if t["verb"] == "READ"]
    if pred.startswith("claims-touch"):
        return match_glob(pred, claim_paths + write_paths + read_paths)
    if pred.startswith("wrote"):
        return match_glob(pred, write_paths)
    if pred.startswith("read"):
        return match_glob(pred, read_paths)
    if pred.startswith("suspicion>="):
        threshold = float(pred[len("suspicion>="):])
        return new_susp >= threshold
    if pred == "always":
        return True
    if pred.startswith("peer-dispatch-disagrees"):
        # Requires access to manifest; handled at sweep level
        return False  # placeholder
    return False


def sweep(manifest, new_parsed):
    """Run the sweep. Returns list of firing {manifest_prefix, predicate} dicts."""
    firings = []
    # Process SUPERSEDES first
    if new_parsed["supersedes"] and new_parsed["supersedes"] != "none":
        for prefix in [p.strip() for p in new_parsed["supersedes"].split(",")]:
            for m in manifest:
                if m["hash_prefix"] == prefix and not m.get("superseded_by"):
                    m["superseded_by"] = new_parsed["hash_prefix"]
    # Forward-checks on active manifest entries
    new_skill = new_parsed["sections"]["RCPT"][0].split("/", 1)[0].strip()
    for m in manifest:
        if m.get("superseded_by"):
            continue
        predicates = []
        if m["tripwire"] and m["tripwire"] != "none":
            predicates += parse_predicates(m["tripwire"])
        if m.get("trip_child") and m["trip_child"] != "none":
            predicates += parse_predicates(m["trip_child"])
        for p in predicates:
            if p.startswith("peer-dispatch-disagrees"):
                # Same-skill, discriminator mismatch
                if m["skill"] != new_skill:
                    continue
                dim_m = re.match(r"peer-dispatch-disagrees\((\w+)\)", p)
                if not dim_m:
                    continue
                dim = dim_m.group(1)
                new_keys, new_files = extract_discriminators(new_parsed)
                if dim == "same-file":
                    # files= collision with different hash
                    for nf in new_files:
                        n_path, n_h6 = nf.rsplit(":", 1)
                        for mf in m.get("files", []):
                            m_path, m_h6 = mf.rsplit(":", 1)
                            if n_path == m_path and n_h6 != m_h6:
                                firings.append({"manifest_prefix": m["hash_prefix"], "predicate": p})
                                break
                elif dim in {"severity", "count", "verdict"}:
                    # Check keys for collision with different value
                    for nk in new_keys:
                        parts = nk.split(":", 2)
                        if len(parts) != 3: continue
                        for mk in m.get("keys", []):
                            mparts = mk.split(":", 2)
                            if len(mparts) != 3: continue
                            # same skill + same key + different value
                            if parts[0] == mparts[0] and parts[1] == mparts[1] and parts[2] != mparts[2]:
                                firings.append({"manifest_prefix": m["hash_prefix"], "predicate": p})
                                break
            else:
                if predicate_fires_on_new(p, new_parsed):
                    # self-exclusion: don't fire on the receipt itself (here, the just-appended)
                    firings.append({"manifest_prefix": m["hash_prefix"], "predicate": p})
    return firings


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    scenario_path = Path(sys.argv[1])
    manifest = []
    last_parsed = None
    last_firings = []
    last_lint_error = None
    results = []
    for line in scenario_path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec["type"] == "receipt":
            text = rec["receipt"]
            # Resolve {{rcpt-prefix-N}} placeholders against manifest[N]
            for i, entry in enumerate(manifest):
                text = text.replace(f"{{{{rcpt-prefix-{i}}}}}", entry["hash_prefix"])
            try:
                parsed = parse_receipt_v11(text)
                # Layer 1 lint first
                layer1.lint_receipt(text)
                lint_v11(parsed, manifest)
                last_lint_error = None
                # Append to manifest
                keys, files = extract_discriminators(parsed)
                prefix = compute_hash_prefix(text)
                skill = parsed["sections"]["RCPT"][0].split("/", 1)[0].strip()
                verdict = parsed["sections"]["VERDICT"][0].split()[0]
                susp = float(parsed["sections"]["SUSPICION"][0].split()[0])
                entry = {
                    "hash_prefix": prefix,
                    "skill": skill,
                    "verdict": verdict,
                    "suspicion": susp,
                    "tripwire": parsed["tripwire"],
                    "trip_child": parsed["trip_child"],
                    "keys": keys,
                    "files": files,
                }
                # Set this on parsed for sweep
                parsed["hash_prefix"] = prefix
                last_firings = sweep(manifest, parsed)
                manifest.append(entry)
                last_parsed = parsed
            except layer1.LintError as e:
                # Catch the BASE layer1.LintError (raised by lint_receipt / parse_*),
                # which also catches the local LintError subclass (raised by lint_v11).
                # `except LintError` (the subclass) would NOT catch a base-class instance,
                # so a Tier-1 grammar failure routed through the sweep would escape as an
                # uncaught traceback instead of a graceful lint-fail classification.
                last_lint_error = str(e)
                last_firings = []
        elif rec["type"] == "expect-fire":
            expected = set(rec["predicates"])
            actual = set(f["predicate"] for f in last_firings)
            if expected != actual:
                results.append(("FAIL", f"expect-fire: expected {expected}, got {actual}"))
            else:
                results.append(("PASS", f"expect-fire {expected}"))
        elif rec["type"] == "expect-no-fire":
            if last_firings:
                results.append(("FAIL", f"expect-no-fire: got {last_firings}"))
            else:
                results.append(("PASS", "expect-no-fire"))
        elif rec["type"] == "expect-lint-fail":
            if last_lint_error is None:
                results.append(("FAIL", f"expect-lint-fail but lint passed"))
            elif rec.get("reason_contains", "") not in last_lint_error:
                results.append(("FAIL", f"expect-lint-fail reason mismatch: got {last_lint_error!r}"))
            else:
                results.append(("PASS", f"expect-lint-fail: {last_lint_error[:80]}"))
        elif rec["type"] == "expect-lint-pass":
            if last_lint_error is not None:
                results.append(("FAIL", f"expect-lint-pass but lint failed: {last_lint_error}"))
            else:
                results.append(("PASS", "expect-lint-pass"))
    # Report
    passed = sum(1 for r in results if r[0] == "PASS")
    for status, msg in results:
        print(f"  {status}  {msg}")
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
