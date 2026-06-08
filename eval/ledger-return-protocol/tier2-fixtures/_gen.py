#!/usr/bin/env python3
"""Generator + self-verifier for the committed Tier-2 disk-fixture corpus (#369).

Each fixture is a {receipt, root, expect, strict, note} record realizing one design
acceptance-4 disposition against REAL on-disk files. This generator writes the files
under tier2-fixtures/<root>/, computes their real sha256, embeds the hashes into the
receipt text, writes manifest.jsonl, and self-verifies every fixture by running it
through rcpt_verify's Tier-2 functions. Re-run from repo root after any fixture edit:

    python3 eval/ledger-return-protocol/tier2-fixtures/_gen.py

Committed output (manifest.jsonl + the <root>/ files) is what --selftest consumes; this
generator is provenance/regeneration only. Deterministic — no RNG, no timestamps.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
rv_spec = importlib.util.spec_from_file_location("rcpt_verify", REPO / "scripts/rcpt_verify.py")
rv = importlib.util.module_from_spec(rv_spec)
rv_spec.loader.exec_module(rv)

HEXZ = "0" * 64  # placeholder hash for EDIT/WROTE args (path-not-in-ARTIFACTS → allowed)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_file(root: str, rel: str, content: str) -> str:
    p = HERE / root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content.encode())
    return sha(content.encode())


def receipt(skill, artifacts, trace, claims, witness, verdict="PASS", susp="0.00", nxt="(none)"):
    """artifacts: list of '  name  sha256:HASH  SIZE' lines (caller pre-fills HASH)."""
    lines = [f"RCPT v1 {skill}"]
    lines.append(f"VERDICT  {verdict}  conf=0.90")
    lines.append("ARTIFACTS")
    lines.extend(artifacts)
    lines.append("TRACE")
    lines.extend(trace)
    lines.append("CLAIMS")
    lines.extend(claims)
    lines.append(f"WITNESS    {witness}")
    lines.append(f"SUSPICION  {susp}")
    lines.append(f"NEXT       {nxt}")
    return "\n".join(lines) + "\n"


fixtures = []


def add(id_, text, root, expect, strict, note):
    fixtures.append({"id": id_, "receipt": text, "root": root,
                     "expect": expect, "strict": strict, "note": note})


# ── (a) clean PASS: on-disk cited range does NOT match expect-fail → pass ──
h = write_file("a", "test-output.log", "all green\n220 pass\n")
add("a-clean-pass",
    receipt("build/a", [f"  test-output.log  sha256:{h}  18"],
            ["  1  EDIT  src/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L2"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    "a", "pass", True,
    "on-disk L1-L2 has no '<n> fail' → witness would NOT have fired → clean PASS")

# ── (b) PASS whose on-disk range DOES match expect-fail → FAIL (silent-skip) ──
h = write_file("b", "test-output.log", "starting\nerror: boom\n")
add("b-pass-range-match",
    receipt("build/b", [f"  test-output.log  sha256:{h}  20"],
            ["  1  EDIT  src/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L2"],
            ["  patch-applied=true  from=TRACE#1"],
            "exec:`run`  expect-fail=/error:/  ran=TRACE#2"),
    "b", "fail", False,
    "cited range matches /error:/ → witness WOULD have fired → PASS rejected")

# ── (c) tampered-hash ARTIFACT → FAIL ──
h = write_file("c", "test-output.log", "real content\n")
wrong = "f" * 64
add("c-tampered-hash",
    receipt("build/c", [f"  test-output.log  sha256:{wrong}  13"],
            ["  1  EDIT  src/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    "c", "fail", False,
    "receipt ARTIFACTS hash != on-disk sha256 → Tier-2 part-1 FAIL")

# ── (e1) UNVERIFIABLE absent bare-basename artifact: non-fatal even --strict → pass ──
h = write_file("e1", "test-output.log", "ok\n")
add("e-absent-basename-unverifiable",
    receipt("build/e", [f"  test-output.log  sha256:{h}  3",
                        "  scratch.tmp  sha256:" + "a" * 64 + "  99"],
            ["  1  EDIT  src/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    "e1", "pass", True,
    "scratch.tmp is a bare basename absent on disk → UNVERIFIABLE (never FAIL, even --strict)")

# ── (e2) path-shaped artifact absent under --strict → FAIL ──
h = write_file("e2", "test-output.log", "ok\n")
add("e-pathshaped-absent-strict-fail",
    receipt("build/e", [f"  test-output.log  sha256:{h}  3",
                        "  build/gone.out  sha256:" + "a" * 64 + "  99"],
            ["  1  EDIT  src/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    "e2", "fail", True,
    "build/gone.out is path-shaped + absent + --strict → Tier-2 part-1 FAIL")

# ── (f) multi-root: resolvable path-shaped EDIT + absent bare WROTE → PASSES --strict ──
# NOTE: the resolvable path-shaped artifact lives under lib/ (NOT src/) because the
# repo-wide `src/` .gitignore rule would silently drop a committed src/ fixture file.
hfoo = write_file("f", "lib/foo.ts", "export const x = 1\n")
hlog = write_file("f", "test-output.log", "all green\n")
add("f-multi-root-strict-pass",
    receipt("build/f", [f"  lib/foo.ts  sha256:{hfoo}  19",
                        "  findings.md  sha256:" + "b" * 64 + "  44",
                        f"  test-output.log  sha256:{hlog}  10"],
            ["  1  EDIT  lib/foo.ts  sha256:" + HEXZ,
             "  2  WROTE  findings.md  sha256:" + HEXZ,
             "  3  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#3"),
    "f", "pass", True,
    "lib/foo.ts (path-shaped) resolves+hashes; findings.md (bare) absent→UNVERIFIABLE; "
    "the absent bare basename does NOT FAIL --strict")

# ── (g) range-extraction: expect-fail pattern OUTSIDE the cited range → PASS ──
glines = "".join(f"line {i}\n" for i in range(1, 50))
glines = glines.replace("line 45\n", "BOOM here\n")
h = write_file("g", "test-output.log", glines)
add("g-range-extraction-outside",
    receipt("build/g", [f"  test-output.log  sha256:{h}  {len(glines)}"],
            ["  1  EDIT  src/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L40"],
            ["  patch-applied=true  from=TRACE#1"],
            "exec:`run`  expect-fail=/BOOM/  ran=TRACE#2"),
    "g", "pass", False,
    "BOOM is on line 45, OUTSIDE the cited #L1-L40 → range-only read → no match → PASS")

# ── (i) byte-range (#B) inclusivity: cited inclusive byte range matches expect-fail → FAIL ──
#   #B2-B5 reads bytes 2..5 INCLUSIVE = read_bytes()[1:5] = "BOOM" (1-based inclusive,
#   parallel to #L). The 'M' at byte 5 is the inclusive endpoint: a half-open [2:5] read
#   would yield "OOM" and miss /BOOM/, so this fixture is load-bearing for the endpoint.
ibody = "xBOOMy\n"
h = write_file("i", "test-output.log", ibody)
add("i-byte-range-inclusive-match",
    receipt("build/i", [f"  test-output.log  sha256:{h}  {len(ibody.encode())}"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#B2-B5"],
            ["  patch-applied=true  from=TRACE#1"],
            "exec:`run`  expect-fail=/BOOM/  ran=TRACE#2"),
    "i", "fail", False,
    "#B2-B5 is 1-based inclusive (bytes 2..5 = 'BOOM'); /BOOM/ matches the cited range → "
    "witness WOULD have fired → PASS rejected. Endpoint byte 'M' is inside the inclusive range.")


# ── (h) synthetic path-shaped witness target absent under --strict → FAIL ──
#   grep-kind witness on a READ of a path-shaped file absent on disk (NOT in ARTIFACTS,
#   so Tier-2 part-1 stays clean — this isolates the part-2 witness-file disposition).
h = write_file("h", "test-output.log", "ok\n")
add("h-synthetic-witness-absent-strict-fail",
    receipt("build/h", [f"  test-output.log  sha256:{h}  3"],
            ["  1  READ  logs/ephemeral.log  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=test-output.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#2"],
            "grep:boom  expect-fail=/boom/  ran=TRACE#1"),
    "h", "fail", True,
    "HAND-CONSTRUCTED: grep witness cites READ logs/ephemeral.log (path-shaped, absent, "
    "not an ARTIFACT) → Tier-2 part-2 --strict FAIL. No natural corpus row produces it.")


def verify_fixture(fx):
    """Run the committed fixture through rcpt_verify's Tier-2 exactly as --selftest will."""
    text = fx["receipt"]
    root = HERE / fx["root"]
    strict = fx["strict"]
    raised = None
    try:
        verdict = rv.lint_receipt(text)
        sections = rv.parse_receipt(text)
        artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        trace = rv.parse_trace(sections["TRACE"])
        witness = rv.parse_witness(sections["WITNESS"])
        rv.tier2_artifacts(artifacts, trace, root, strict)
        if verdict in {"PASS", "FAIL"}:
            rv.tier2_witness(witness, trace, root, strict, verdict)
    except rv.LintError as e:
        raised = str(e)
    got = "fail" if raised else "pass"
    ok = got == fx["expect"]
    return ok, got, raised


def main():
    manifest = HERE / "manifest.jsonl"
    with manifest.open("w") as f:
        for fx in fixtures:
            f.write(json.dumps(fx) + "\n")
    print(f"wrote {manifest} ({len(fixtures)} fixtures)")
    all_ok = True
    for fx in fixtures:
        ok, got, raised = verify_fixture(fx)
        mark = "OK " if ok else "XX "
        all_ok = all_ok and ok
        print(f"  {mark}{fx['id']:40s} expect={fx['expect']:4s} got={got:4s}  {raised or ''}")
    if not all_ok:
        raise SystemExit("FIXTURE SELF-VERIFY FAILED — fix the generator before committing")
    print("all fixtures self-verify OK")


if __name__ == "__main__":
    main()
