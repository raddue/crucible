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


# ══ #474 — the red-team-mandated `pattern=/…/  expect-fail=match` form ══════════════
# Until these landed, NO fixture paired kind=grep + expect-fail=match with a resolvable
# body, so the shape that carries every red-team verdict had zero fixture coverage while
# rcpt_verify.py:30 names --selftest "the permanent CI guard". All five are REDACTED
# SYNTHETICS: synthetic paths and bodies preserving the real shape (the SEVERITY-COUNTS
# line, the EXEC-vs-witness artifact split). They give #474's evidence a durable home —
# the recovered dispatch-dir corpus it was measured on is ephemeral and machine-local.
#
# Each declares its witness artifact in its OWN ARTIFACTS: D6's Tier-1 membership rule
# would otherwise reject the receipt before it reaches the path the fixture exists to
# cover — coverage that cannot fail is the defect class these rows exist to remove.

RT_HIT = "SEVERITY-COUNTS: fatal=1 significant=3 minor=2\n"
RT_CLEAN = "SEVERITY-COUNTS: fatal=0 significant=0 minor=3\n"
RT_PRED = "pattern=/significant=[1-9]|fatal=[1-9]/"

# ── (j) the mandated form FIRES: a declared PASS over a non-clean findings body ──
body = RT_HIT + "## Finding 1\nsignificant: the guard is inert\n"
h = write_file("j", "round-3-findings.md", body)
add("j-rt-mandated-witness-fires",
    receipt("red-team/3-devils-advocate",
            [f"  round-3-findings.md  sha256:{h}  {len(body.encode())}"],
            ["  1  READ   design.md  sha256:" + HEXZ,
             "  2  WROTE  round-3-findings.md  sha256:" + HEXZ],
            ["  severity-max=significant  from=round-3-findings.md#L1-L1"],
            f"grep:round-3-findings.md#L1-L1  {RT_PRED}  expect-fail=match  ran=TRACE#2"),
    "j", "fail", False,
    "THE #474 REPRODUCTION: mandated red-team witness on a PASS whose findings body "
    "declares nonzero counts. Pre-fix the clause was never read → returned clean.")

# ── (k) the mandated form does NOT fire on a genuinely clean round ──
body = RT_CLEAN + "## No findings\nall prior rounds closed\n"
h = write_file("k", "round-11-findings.md", body)
add("k-rt-mandated-clean-round",
    receipt("red-team/11-devils-advocate",
            [f"  round-11-findings.md  sha256:{h}  {len(body.encode())}"],
            ["  1  READ   design.md  sha256:" + HEXZ,
             "  2  WROTE  round-11-findings.md  sha256:" + HEXZ],
            ["  severity-max=none  from=round-11-findings.md#L1-L1"],
            f"grep:round-11-findings.md#L1-L1  {RT_PRED}  expect-fail=match  ran=TRACE#2"),
    "k", "pass", False,
    "The no-false-BLOCK counterpart: a clean round must still PASS. Without this row the "
    "fires-fixture is satisfiable by a guard that rejects every red-team receipt.")

# ── (l) WROTE-cited, narrow payload range: the whole-file false-positive class ──
#   Line 1 is clean; a LATER line quotes a PRIOR round's nonzero counts in prose. A
#   whole-file read matches that prose and false-BLOCKs the clean round; the payload's
#   own #L1-L1 (which return-convention mandates) does not.
body = RT_CLEAN + "## Note\nround-8-findings.md filed fatal=0 significant=2 at the time\n"
h = write_file("l", "round-12-findings.md", body)
add("l-rt-wrote-cited-narrow-range",
    receipt("red-team/12-devils-advocate",
            [f"  round-12-findings.md  sha256:{h}  {len(body.encode())}"],
            ["  1  READ   design.md  sha256:" + HEXZ,
             "  2  WROTE  round-12-findings.md  sha256:" + HEXZ],
            ["  severity-max=none  from=round-12-findings.md#L1-L1"],
            f"grep:round-12-findings.md#L1-L1  {RT_PRED}  expect-fail=match  ran=TRACE#2"),
    "l", "pass", False,
    "Prose quoting a prior round's counts sits OUTSIDE the cited #L1-L1. The narrowed "
    "read is what keeps this clean round clean — a whole-file read would false-BLOCK it.")

# ── (m) EXEC-cited MISMATCH: the witness payload names a DIFFERENT file than out= ──
#   The facet-(b) case no single-file fixture can see: pre-fix the body came from the
#   EXEC out= log (which never matches), so the witness was inert on a real contradiction.
body = RT_HIT + "## Finding 1\nfatal: still broken\n"
log = "# cmd: grep -nE 'significant' round-4-findings.md\nno hits\n"
h = write_file("m", "round-4-findings.md", body)
hlog = write_file("m", "witness-grep.log", log)
add("m-rt-exec-cited-artifact-mismatch",
    receipt("red-team/4-devils-advocate",
            [f"  round-4-findings.md  sha256:{h}  {len(body.encode())}",
             f"  witness-grep.log  sha256:{hlog}  {len(log.encode())}"],
            ["  1  WROTE  round-4-findings.md  sha256:" + HEXZ,
             "  2  EXEC   `grep -nE significant round-4-findings.md`  exit=0  dur=0.1s  "
             "out=witness-grep.log#L1-L2"],
            ["  severity-max=fatal  from=round-4-findings.md#L1-L1"],
            f"grep:round-4-findings.md#L1-L1  {RT_PRED}  expect-fail=match  ran=TRACE#2"),
    "m", "fail", False,
    "Witness payload names round-4-findings.md; the cited EXEC's out= names witness-grep.log. "
    "The verified body must come from the PAYLOAD's file (return-convention.md kind=grep "
    "rule) — from the log it would never fire, a fail-open inside the fix.")

# ── (n) the same EXEC-cited-mismatch shape on a clean round → PASS ──
body = RT_CLEAN + "## No findings\n"
log = "# cmd: grep -nE 'significant' round-13-findings.md\nno hits\n"
h = write_file("n", "round-13-findings.md", body)
hlog = write_file("n", "witness-grep.log", log)
add("n-rt-exec-cited-mismatch-clean",
    receipt("red-team/13-devils-advocate",
            [f"  round-13-findings.md  sha256:{h}  {len(body.encode())}",
             f"  witness-grep.log  sha256:{hlog}  {len(log.encode())}"],
            ["  1  WROTE  round-13-findings.md  sha256:" + HEXZ,
             "  2  EXEC   `grep -nE significant round-13-findings.md`  exit=0  dur=0.1s  "
             "out=witness-grep.log#L1-L2"],
            ["  severity-max=none  from=round-13-findings.md#L1-L1"],
            f"grep:round-13-findings.md#L1-L1  {RT_PRED}  expect-fail=match  ran=TRACE#2"),
    "n", "pass", False,
    "Mismatch shape, clean body — pins that re-pointing the body at the payload artifact "
    "does not itself reject; only a contradicting body does.")


# ── #486 two-root rows: D1/D2/D3 and criterion 6 ──────────────────────────────
# The token is "two-root", NOT "multi-root": f-multi-root-strict-pass above already
# means root + git toplevel — the pre-existing two-candidate probe within ONE --root.
# Reusing that token would make the fixture whose subject is the within-root precedence
# D2 PRESERVES indistinguishable from the fixtures about the across-root rule D2 ADDS.
#
# What is NOT here and cannot be: _selftest_run_fixture returns 'pass'|'fail'|'error'
# and never captures stderr, so criterion 6's BYTE-IDENTITY half and criterion 5's
# non-strict `AMBIGUOUS:` note half live in the subprocess tests in
# scripts/test_rcpt_verify.py (TestRepeatableRootFlag, TestCrossRootAmbiguity).
_SPLIT_NOTE = ("stderr-shape half lives in test_rcpt_verify.py's subprocess tests — "
               "--selftest compares only pass/fail")

# p1 exists as a probed root that does NOT hold the row-1 basename; the decoy keeps the
# directory committed (git does not track empty dirs) and makes "absent from root 1" a
# real, stable fact rather than an artefact of a missing directory.
write_file("p1", "decoy.txt", "not referenced by any receipt\n")

# (1) D1 — bare basename absent from root 1, present at root 2's top level
h = write_file("p2", "second-root.log", "all green\n")
add("two-root-second-root-resolves",
    receipt("build/two-root", [f"  second-root.log  sha256:{h}  10"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=second-root.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    ["p1", "p2"], "pass", True,
    "D1 — absent under root 1, resolves at root 2's top level and its sha256 is "
    "checked; witness reads the same file and does not fire. " + _SPLIT_NOTE)

# (2) D3 — same basename in both roots, receipt declares ROOT 2's hash; root 1 is read
h1 = write_file("p1", "dup.log", "root one bytes\n")
h2 = write_file("p2", "dup.log", "root two bytes\n")
add("two-root-declaration-order-first-hit",
    receipt("build/two-root", [f"  dup.log  sha256:{h2}  16"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=dup.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    ["p1", "p2"], "fail", False,
    "D3 — declaration order means root 1 is the file READ, so root 2's declared hash "
    "mismatches. LIMITATION: --selftest compares only pass/fail, so this row cannot say "
    "WHICH LintError fired — the intended mismatch, or an ambiguity raise misfiring "
    "(which under strict=false would itself be a bug). The discriminating assertion for "
    "declaration order is test_first_hit_is_declaration_order, which asserts the "
    "resolved path itself. " + _SPLIT_NOTE)

# (3) D2 — two distinct realpaths under --strict → LintError before any read
add("two-root-ambiguous-strict-fail",
    receipt("build/two-root", [f"  dup.log  sha256:{h1}  15"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=dup.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    ["p1", "p2"], "fail", True,
    "D2 — dup.log exists under both roots as two distinct realpaths → --strict "
    "LintError, raised BEFORE any read (the declared hash here is root 1's and would "
    "have matched). " + _SPLIT_NOTE)

# (4) Q7 — byte-IDENTICAL copies are still ambiguous
same = "identical bytes\n"
hs = write_file("p1", "same.log", same)
write_file("p3", "same.log", same)
add("two-root-ambiguous-identical-bytes-strict-fail",
    receipt("build/two-root", [f"  same.log  sha256:{hs}  16"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=same.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    ["p1", "p3"], "fail", True,
    "Q7 — two distinct realpaths are ambiguous regardless of content; collapsing "
    "same-content copies would make the disposition depend on a file the receipt may "
    "control. " + _SPLIT_NOTE)

# (5) criterion 6's DISPOSITION half — the same root twice de-duplicates to a no-op
h = write_file("p1", "solo.log", "all green\n")
add("two-root-dedup-noop",
    receipt("build/two-root", [f"  solo.log  sha256:{h}  10"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=solo.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    ["p1", "p1"], "pass", True,
    "criterion 6 — the same root declared twice de-duplicates by resolved path, so it "
    "is NOT ambiguous and the run stays clean. " + _SPLIT_NOTE)


# (6) criterion 3 — the ARTIFACTS sha256 is demonstrably RECOMPUTED, proved through the
# SECOND root, which is the path #486 creates. c-tampered-hash already models the shape
# under one root. ⚠ The control must RESOLVE: a perturbed artifact planted where nothing
# resolves passes at exit 0 — that is #486's own defect wearing a test's clothes. For a
# bare basename, "resolves" means the top level of a probed base.
h = write_file("p2", "tampered.log", "real content\n")
# Exactly one hex digit differs, and it is the FIRST one deliberately: the mismatch
# bullet prints only hash[:12], so perturbing the last digit produces
# "disk=b951fe82cd99 receipt=b951fe82cd99" — a real FAIL whose own message shows two
# identical prefixes and reads like a linter bug to the next person who sees it.
_perturbed = ("0" if h[0] != "0" else "1") + h[1:]
add("two-root-tampered-hash-second-root",
    receipt("build/two-root", [f"  tampered.log  sha256:{_perturbed}  13"],
            ["  1  EDIT  lib/x.ts  sha256:" + HEXZ,
             "  2  EXEC  `run`  exit=0  dur=1s  out=tampered.log#L1-L1"],
            ["  patch-applied=true  from=TRACE#1"],
            r"exec:`run`  expect-fail=/\d+ fail/  ran=TRACE#2"),
    ["p1", "p2"], "fail", True,
    "criterion 3 — tampered.log resolves at root 2's top level (reachability condition "
    "met) and its declared hash differs from disk by one hex digit, so the FAIL proves "
    "the sha256 was recomputed through the second root rather than assumed. "
    + _SPLIT_NOTE)


def verify_fixture(fx):
    """Run the committed fixture through rcpt_verify's Tier-2 exactly as --selftest will."""
    text = fx["receipt"]
    root = rv._fx_roots(HERE, fx["root"])    # #486 — string OR list of roots
    strict = fx["strict"]
    raised = None
    got = None
    try:
        verdict = rv.lint_receipt(text)
        sections = rv.parse_receipt(text)
        artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        trace = rv.parse_trace(sections["TRACE"])
        witness = rv.parse_witness(sections["WITNESS"])
        rv.tier2_artifacts(artifacts, trace, root, strict)
        if verdict in {"PASS", "FAIL"}:
            rv.tier2_witness(witness, trace, root, strict, verdict)
    except rv.WitnessTimeout as e:
        # #486/Q8 — a wall-clock timeout is NOT a passing expect:"fail" fixture. Same
        # swallow shape rcpt_verify._selftest_run_fixture fixes, one directory away.
        raised = f"TIMEOUT: {e}"
        got = "error"        # never compares equal to expect ('pass'|'fail' only)
    except rv.LintError as e:
        raised = str(e)
    # `got` may already be set by the timeout handler above — do not overwrite it, or
    # the swallow is reinstated while looking fixed.
    got = got or ("fail" if raised else "pass")
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
