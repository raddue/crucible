#!/usr/bin/env python3
"""#474 S13 — the plan's measured figures come from one committed script, not from prose.

Rounds 2, 3, 4→5 and 6 of the #474 plan's quality gate each corrected a figure that
had been stated without the denominator it was computed over, or carried from an
earlier round without re-derivation. Prose cannot go red. This script emits every
figure §0h / §0e / §4 / S12(1) of `docs/plans/2026-08-07-474-witness-match-fail-open.md`
quotes and is gated by `scripts/run_tests.sh` — so a figure that rots fails CI instead
of aging quietly inside a document.

**What is GATING and what is ADVISORY** (stated precisely, because it used to be
overstated — round-1 / MIN-2 and MIN-3). Gating = enters the exit code:

  * rows 1-3 and 5-6 in full, and row 4's calibration-pin PRESENCE check;
  * every one of those reads only committed files, so they return the same verdict on
    CI and on any checkout. That is what CLAUDE.md's "single source of truth … so
    local and CI never drift" requires of anything `run_tests.sh` invokes.

Advisory = printed with its expected value, never gating:

  * every one of row 4's five figures — literal / range-shaped / accepted (round-1 /
    MIN-3) and `max #L span` / the in-band token list (round-4 / S1). All five are a
    census of a high-churn test suite: any future `out=` token in it moves one of them
    for reasons unrelated to correctness. What carries meaning is strictly weaker than
    an exact census and is gated on its own — that RED test 15's `out=a.log#L1-L100`
    calibration pin still EXISTS. None of this is a leak detector: row 6 is where a
    calibration leak fires (round-2 / MIN-3).
  * row 7 in its entirety — it reads a gitignored, machine-local corpus under `$HOME`.
    Asserting there would make this same script return different verdicts on CI (where
    it SKIPs) and on the maintainer's machine (where the corpus exists).

Two disciplines this script exists to enforce, both from the gate:

  **Denominator discipline.** Every row prints the exact glob it was computed over and
  the exact tokenization rule that produced its counts. Two defensible tokenizations
  disagree on the literal/range-shaped columns, so the rule is printed beside the
  count rather than assumed.

  **Anchoring discipline (round 7 / SIG-1).** No assertion here keys on a line number.
  A line number is a denominator that rots: S7 of this same plan rewrites prose inside
  `return-convention.md`, shifting every anchor below it. Keys are the block's
  start-of-line `^RCPT v…` header — total and unique over `return-convention.md`'s
  eight blocks — or, for `red-team-prompt.md`'s two blocks (which share a header), the
  `<!-- worked-example: PASS/FAIL -->` markers `check_rt_receipt_contract.py` already
  gates on. Line numbers appear in output as convenience locators only, never in an
  assertion. That is what makes S7 provably inert for this script.

**Three figures moved from the plan's §0h text, all attributable to this PR's own
additions, none to drift** (each named at its row):

  * jsonl glob: 33 files / 38 `out=` tokens → **34 / 40** — S8 added
    `inject/shape-e-grep-witness-inline-body.jsonl` (0 tokens) and two EXEC-cited
    `tier2-fixtures` rows (`m`, `n`).
  * ranged `kind=grep` membership: 8 of 8 → **14 of 14** — S8's five fixture rows plus
    the inject row, all of which declare their witness artifact.
  * `test_rcpt_verify.py`: 0 in band, max `#L` span 39 → **1**, max span **99** — S1's
    RED test 15 pins EXEC's calibration with `out=a.log#L1-L100`, which is deliberately
    inside the band. An in-band token in the *test* file is the guard, not the exposure.
    (Its literal / range-shaped / accepted counts were 21/19/15 → 25/22/17 when this
    row still asserted them; they are advisory as of round-1 / MIN-3, and `max #L span`
    / the in-band list joined them as of round-4 / S1 — the pin's PRESENCE is the gate.)

Unmoved: `return-convention.md` 4/3, `red-team-prompt.md` 0/0, the 10-block LINT
partition 5 FAIL / 5 PASS, and every §0e corpus figure.

The §0e corpus row reads a machine-local, gitignored dispatch corpus. It is SKIPPED —
not failed — when absent, so CI stays green on any checkout; pass `--corpus DIR` to
point it elsewhere. Stdlib only.
"""
from __future__ import annotations

import argparse
import glob as globlib
import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The calibration band is `#L`-only BY CONSTRUCTION, not by luck: EXEC's bound computes
# (b-a) for #B and (b-a)*80 for #L, D6's grep bound (b-a) for #B and the 1-B/line floor
# for #L — identical on every #B range, so they can differ only on #L.
BAND_LO, BAND_HI = 52, 4096

# The one tokenization rule, printed beside every token count it produces.
TOKENIZATION = r'''re.findall(r"out=\S+") over raw file text, no dedupe'''
BAND_RULE = f"kind=#L and {BAND_LO} <= (b-a) <= {BAND_HI}  (#B can never differ)"

JSONL_GLOB = "eval/ledger-return-protocol/**/*.jsonl"
RETURN_CONV = "skills/shared/return-convention.md"
RT_PROMPT = "skills/red-team/red-team-prompt.md"
RCPT_TESTS = "scripts/test_rcpt_verify.py"
# round-5 / MIN-5 — the project slug is DERIVED from this checkout, not pinned to the
# maintainer's. Claude Code names a project directory after the absolute repo path with
# every `/` replaced by `-`, so the slug is a function of ROOT. With the slug hard-coded,
# row 7's SKIP meant "wrong checkout" on any differently-located clone even when an
# equivalent corpus was present — and `run_tests.sh` passes no `--corpus`, so there was
# no way to reach it. Derived, the SKIP means "no corpus". Row 7 stays advisory either
# way (it reads a gitignored, machine-local tree — see row_corpus).
DEFAULT_CORPUS = pathlib.Path.home() / ".claude/projects" / str(ROOT).replace("/", "-") / (
    "memory/quality-gate/evidence-474-tier2-resolution/corpus-2026-08-01"
)
CORPUS_GLOB = "rcpt-*-asreturned.txt"


def load_rcpt_verify():
    """The figures must come from the SHIPPED parser, not from a second implementation.
    A probe with its own regexes measures itself and reports the same answer whether the
    linter is fixed, broken or absent — the failure mode S10's docstring records."""
    spec = importlib.util.spec_from_file_location("rv_s13", ROOT / "scripts/rcpt_verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Block extraction — keyed on the ^RCPT v… header, never on a line number.
# ---------------------------------------------------------------------------

_HDR = re.compile(r"^(\s*)(RCPT v\S+\s+\S+.*)$")
_MARKER = re.compile(r"<!-- worked-example: (PASS|FAIL) -->")


def rcpt_blocks(text: str):
    """Every taught receipt in a Markdown file, as (identity, body).

    Anchored on the `RCPT v…` header line rather than on fence pairing: the fences in
    `red-team-prompt.md` are indented inside list items and an unindented fence earlier
    in that file swallows them under any regex that pairs ``` to ```. A block runs from
    its header to the first blank line, fence, or dedent.

    Identity is the header text; where a file's headers are not unique (both of
    `red-team-prompt.md`'s blocks are `red-team/N-devils-advocate`) the nearest
    preceding worked-example marker disambiguates. Both keys are stable under S7.
    """
    lines = text.splitlines()
    marks = [(m.start(), m.group(1)) for m in _MARKER.finditer(text)]
    # byte offset of the start of each line, for marker proximity only
    offsets, acc = [], 0
    for line in lines:
        offsets.append(acc)
        acc += len(line) + 1

    out, i = [], 0
    while i < len(lines):
        m = _HDR.match(lines[i])
        if not m:
            i += 1
            continue
        indent, header = m.group(1), m.group(2).strip()
        buf, j = [], i
        while j < len(lines):
            line = lines[j]
            if not line.strip() or line.strip().startswith("```") or not line.startswith(indent):
                break
            buf.append(line[len(indent):])
            j += 1
        preceding = [k for pos, k in marks if pos < offsets[i]]
        ident = header
        if _duplicate_header(text, header) and preceding:
            ident = f"{header} <worked-example: {preceding[-1]}>"
        out.append((ident, "\n".join(buf) + "\n", i + 1))
        i = max(j, i + 1)
    return out


def _duplicate_header(text: str, header: str) -> bool:
    return len(re.findall(r"^\s*" + re.escape(header) + r"\s*$", text, re.M)) > 1


def jsonl_receipts(path: pathlib.Path):
    """(identity, receipt-text) for every JSONL row carrying a `receipt` field.
    Identity is `<file basename>#<dispatch-id>`, never a line number."""
    import json
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("receipt"), str):
            ident = rec.get("dispatch-id") or rec.get("id") or rec.get("name") or f"row{n}"
            out.append((f"{path.name}#{ident}", rec["receipt"]))
    return out


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.errors: list[str] = []

    def check(self, label: str, got, want):
        mark = "ok " if got == want else "RED"
        print(f"       {mark} {label}: {got!r}" + ("" if got == want else f"  (expected {want!r})"))
        if got != want:
            self.errors.append(f"{label}: got {got!r}, expected {want!r}")

    def advise(self, label: str, got, want):
        """Print-and-compare WITHOUT gating (round-1 / MIN-2). For figures computed
        over a machine-local corpus: a mismatch is a signal to a human on the machine
        that has the corpus, never a CI verdict — a row that asserts here and SKIPs on
        CI makes the same gated script machine-dependent."""
        mark = "ok " if got == want else "DIFF"
        print(f"       {mark} {label}: {got!r}"
              + ("" if got == want else f"  (advisory — expected {want!r})"))


def out_tokens(text: str) -> list[str]:
    return re.findall(r"out=\S+", text)


def classify(rv, tokens):
    """(literal, range_shaped, accepted, in_band) where in_band is [(token, span)]."""
    range_shaped = [t for t in tokens if re.search(r"#[LB]\d+-", t)]
    accepted, in_band, max_l_span = [], [], 0
    for t in tokens:
        r = rv.parse_out_range(t)
        if not r:
            continue
        accepted.append(t)
        if r.kind == "L":
            span = r.end - r.start
            max_l_span = max(max_l_span, span)
            if BAND_LO <= span <= BAND_HI:
                in_band.append((t, span))
    return len(tokens), len(range_shaped), len(accepted), in_band, max_l_span


def row_exec_jsonl(rv, rep: Report):
    files = sorted(globlib.glob(str(ROOT / JSONL_GLOB), recursive=True))
    tokens = []
    for f in files:
        tokens += out_tokens(pathlib.Path(f).read_text())
    lit, rng, acc, band, max_span = classify(rv, tokens)
    print(f"\n── ROW 1  EXEC out= ranges — the calibration band's fail-open exposure")
    print(f"   glob        : {JSONL_GLOB}")
    print(f"   tokenization: {TOKENIZATION}")
    print(f"   band        : {BAND_RULE}")
    print(f"   figures     : files={len(files)} literal={lit} range-shaped={rng} "
          f"accepted={acc} in-band={len(band)} max#Lspan={max_span}")
    print(f"   note        : 33/38 in the plan's §0h; S8 added the inject row (0 tokens) "
          f"and two EXEC-cited tier2-fixtures rows")
    # round-5 / MIN-1 — the SAME rot property row 4's columns were demoted for
    # (round-1/MIN-3, round-4/S1), applied here. `jsonl files` and `jsonl out= tokens`
    # are an exact census over a directory whose PURPOSE is to grow: this branch alone
    # moved the file count 33 → 34 by adding one fixture, and dropping any unrelated
    # JSONL row into tier2-fixtures/ turns run_tests.sh red with `jsonl files: got 35,
    # expected 34` while every load-bearing figure is intact. Demoted to advisory.
    #
    # What stays GATING is the pair that carries the meaning, in a form that does not
    # rot:
    #   * in-band == []  — the actual fail-open exposure. It does not move when the
    #     corpus grows; it moves when a token lands in the calibration band, which is
    #     exactly the event it exists to catch.
    #   * accepted == literal — every out= token in the corpus is parsed by
    #     parse_out_range. This is `accepted` still gating, as a RELATION rather than as
    #     the count 40. The count would have rotted in lockstep with `jsonl out= tokens`,
    #     making that demotion cosmetic; the relation is what makes `in-band == []`
    #     trustworthy, because a token that escapes classification is a token the band
    #     measurement never saw.
    rep.advise("jsonl files", len(files), 34)
    rep.advise("jsonl out= tokens", lit, 40)
    rep.check("jsonl every out= token is accepted (accepted == literal)", acc, lit)
    rep.check("jsonl in-band", [t for t, _ in band], [])


def row_exec_file(rv, rep: Report, relpath, n, want, note="", assert_counts=True,
                  pin_token=None):
    text = (ROOT / relpath).read_text()
    lit, rng, acc, band, max_span = classify(rv, out_tokens(text))
    blocks = rcpt_blocks(text) if relpath.endswith(".md") else []
    # attribute each in-band token to the block that contains it — block identity, not line
    attributed = []
    for tok, span in band:
        owner = next((ident for ident, body, _ in blocks if tok in body), tok)
        attributed.append((owner, span))
    print(f"\n── ROW {n}  EXEC out= ranges")
    print(f"   glob        : {relpath}")
    print(f"   tokenization: {TOKENIZATION}")
    print(f"   band        : {BAND_RULE}")
    print(f"   figures     : literal={lit} range-shaped={rng} accepted={acc} "
          f"in-band={len(band)} max#Lspan={max_span}")
    if note:
        print(f"   note        : {note}")
    for owner, span in attributed:
        print(f"   in-band     : {owner}  (span {span})")
    if assert_counts:
        rep.check(f"{relpath} literal", lit, want["literal"])
        rep.check(f"{relpath} range-shaped", rng, want["range_shaped"])
        rep.check(f"{relpath} accepted", acc, want["accepted"])
    else:
        # round-1 / MIN-3 — the three token-count columns are DELIBERATELY advisory for
        # this file. They are a census of a high-churn test suite: any future
        # rcpt_verify test that happens to carry an `out=` token moves them and turns
        # CI red for a reason unrelated to correctness. What is load-bearing here is
        # ONE property, gated below since round-4 / S1: RED test 15's
        # `out=a.log#L1-L100` calibration pin still exists in the file. Not even that
        # detects a calibration leak — classify() does its own arithmetic against
        # script-local BAND_LO/BAND_HI and never calls check_span_bound, so row 4
        # returns identical figures under any calibration (round-2 / MIN-3). A LEAK
        # fires at row 6 (lint_receipt → check_exec_range_bound), and test_9c/test_15b
        # cover the reverse direction. Counts are printed so a reviewer can still see
        # the denominator.
        print(f"   advisory    : literal/range-shaped/accepted are printed, NOT asserted "
              f"(high-churn file; the calibration pin below is the gate)")
    key = "in_band_blocks" if relpath.endswith(".md") else "in_band_tokens"
    got = sorted(attributed) if relpath.endswith(".md") else sorted(band)
    if pin_token is None:
        rep.check(f"{relpath} max #L span", max_span, want["max_l_span"])
        rep.check(f"{relpath} {key}", got, sorted(want[key]))
    else:
        # round-4 / S1 — the SAME rot property the three token columns were demoted for
        # (round-1 / MIN-3) applies to these two figures, because they are computed from
        # the same tokens over the same high-churn file. `max #L span` and the exact
        # in-band LIST both go red when an unrelated future test carries any out= token
        # with a span over 99, or any span in [52, 4096] — measured: injecting one
        # `out=b.log#L1-L300` line produced 2 gated failures while leaving the thing they
        # were protecting fully intact. What is load-bearing is strictly weaker and is
        # what the rationale above actually describes: RED test 15's calibration pin is
        # still PRESENT. That is gated below; the two figures stay printed and compared
        # as advisories. A calibration LEAK was never caught here — it fires at row 6
        # (lint_receipt → check_exec_range_bound), verified by simulation.
        rep.advise(f"{relpath} max #L span", max_span, want["max_l_span"])
        rep.advise(f"{relpath} {key}", got, sorted(want[key]))
        # The trailing `"` is part of the token BY CONSTRUCTION: TOKENIZATION is
        # `out=\S+` over raw file text, and the pin lives inside a double-quoted Python
        # string in the test. Rewriting test 15's quoting is therefore a real edit to the
        # pin and is meant to be visible here.
        rep.check(f"{relpath} calibration pin present",
                  any(t == pin_token for t, _ in band), True)


def row_grep_membership(rv, rep: Report):
    """§0h finding 3 — every ranged `kind=grep` witness names an artifact its own
    ARTIFACTS declares, so D6's membership rule is free on every committed site."""
    sites = []
    for f in sorted(globlib.glob(str(ROOT / JSONL_GLOB), recursive=True)):
        sites += [(pathlib.Path(f).name, i, t) for i, t in jsonl_receipts(pathlib.Path(f))]
    for relpath in (RETURN_CONV, RT_PROMPT):
        text = (ROOT / relpath).read_text()
        sites += [(relpath, ident, body) for ident, body, _ in rcpt_blocks(text)]

    total, ok, misses = 0, 0, []
    for where, ident, text in sites:
        try:
            sections = rv.parse_receipt(text)
            witness = rv.parse_witness(sections["WITNESS"])
            artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        # round-2 / MIN-2 — LintError and NOTHING WIDER. This row exists to measure the
        # SHIPPED parser, so a genuine crash inside it must not be reattributed to
        # fixture drift: under a bare `except Exception` the row would silently drop out
        # of the denominator and surface only as `ranged grep sites: got 13, expected
        # 14`. Safe to narrow because parse_receipt raises LintError (not KeyError) on a
        # missing section, so the sections[...] subscripts above cannot fire on a
        # non-receipt block, and both corpus iterators yield str.
        except rv.LintError:
            continue            # non-receipt or deliberately malformed; other rows cover those
        if witness["kind"] != "grep" or witness["range_kind"] is None:
            continue
        total += 1
        if witness["art"] in artifacts:
            ok += 1
        else:
            misses.append(f"{where} › {ident} → {witness['art']}")
    print(f"\n── ROW 5  ranged kind=grep witnesses — ARTIFACTS membership (D6)")
    print(f"   glob        : {JSONL_GLOB} + {RETURN_CONV} + {RT_PROMPT}")
    print(f"   predicate   : parse_witness kind==grep and payload declares a #L/#B range")
    print(f"   figures     : sites={total} membership-ok={ok}")
    print(f"   note        : 8 of 8 in the plan's §0h; S8 added five tier2-fixtures rows "
          f"and one inject row, all declaring their witness artifact")
    for m in misses:
        print(f"   MISS        : {m}")
    rep.check("ranged grep sites", total, 14)
    rep.check("membership ok", ok, 14)


def row_taught_lint(rv, rep: Report):
    """S12(1)'s baseline partition, keyed on block identity. The two `red-team-prompt.md`
    blocks are LINT-PASS and nothing else in the suite reads them — no selftest path, no
    `--eval` golden, and `check_rt_receipt_contract.py` pins the taught line's *text*,
    never its lint classification. If a Tier-1 rule flips them, this row is the only
    place it shows."""
    partition, detail = {}, {}
    for relpath in (RETURN_CONV, RT_PROMPT):
        for ident, body, _ in rcpt_blocks((ROOT / relpath).read_text()):
            key = f"{relpath} › {ident}"
            try:
                partition[key] = f"LINT-PASS ({rv.lint_receipt(body)})"
            except rv.LintError as e:
                partition[key] = "LINT-FAIL"
                detail[key] = str(e)
    fails = sorted(k for k, v in partition.items() if v == "LINT-FAIL")
    passes = sorted(k for k, v in partition.items() if v != "LINT-FAIL")
    print(f"\n── ROW 6  taught RCPT blocks — Tier-1 classification (S12(1) baseline)")
    print(f"   glob        : {RETURN_CONV} + {RT_PROMPT}")
    print(f"   key         : ^RCPT v… header; worked-example marker where headers repeat")
    print(f"   figures     : blocks={len(partition)} LINT-FAIL={len(fails)} "
          f"LINT-PASS={len(passes)}")
    for k in fails:
        print(f"   LINT-FAIL   : {k} → {detail[k]}")
    for k in passes:
        print(f"   LINT-PASS   : {k} → {partition[k]}")
    rep.check("taught blocks", len(partition), 10)
    rep.check("taught LINT-FAIL identities", fails, sorted([
        f"{RETURN_CONV} › RCPT v1 <skill>/<dispatch-id>",
        f"{RETURN_CONV} › RCPT v1 build/7-implementer",
        f"{RETURN_CONV} › RCPT v1 build/8-implementer",
        f"{RETURN_CONV} › RCPT v1 build/9-implementer",
        f"{RETURN_CONV} › RCPT v1.1 build/42-implementer",
    ]))
    rep.check("taught LINT-PASS count", len(passes), 5)


def row_corpus(rv, rep: Report, corpus: pathlib.Path | None):
    """§0e — the 17-receipt as-returned corpus. Machine-local and gitignored.

    ADVISORY, NOT GATING (round-1 / MIN-2). Its figures are printed with the expected
    value beside them and compared, but a mismatch does NOT enter rep.errors and does
    not change the exit code. The reason is CLAUDE.md's rule that `scripts/run_tests.sh`
    is one source of truth "so local and CI never drift": these ten checks read a
    gitignored corpus under $HOME, so they SKIP on CI and used to ASSERT on the
    maintainer's machine — the same gated script returning different verdicts on two
    machines. A figure over a corpus that only one machine can see is evidence for the
    plan, not a regression gate; the gate is rows 1-6 plus the fixtures, all of which
    run identically everywhere."""
    print(f"\n── ROW 7  §0e as-returned corpus (machine-local)")
    print(f"   glob        : {corpus}/{CORPUS_GLOB}" if corpus else "   glob        : (none)")
    if corpus is None or not corpus.is_dir():
        print("   SKIP        : corpus absent (gitignored, machine-local) — not a failure")
        return
    files = sorted(globlib.glob(str(corpus / CORPUS_GLOB)))
    if not files:
        print("   SKIP        : no rcpt-*-asreturned.txt under the corpus dir")
        return
    grep = ranged = memb = mandated = sig_form = sig_on_pass = 0
    rt_ns, rt_findings, rt_wrong_form = 0, 0, 0
    skipped = []
    for f in files:
        # round-3 / S2 — LintError and NOTHING WIDER, for the same reason
        # row_grep_membership narrows: this row measures the SHIPPED parser, so a
        # genuine crash inside it must not be reattributed to corpus drift. The
        # narrowing is sound here on its own terms: parse_receipt raises LintError
        # (not KeyError) on a missing section, so the sections[...] subscripts cannot
        # fire on a malformed file, and read_text() yields str. The corpus is written
        # by live agents, so it will contain receipts that PRE-DATE this branch's new
        # Tier-1 rules (rangeless expect-fail=match, duplicate/misplaced clauses) —
        # those must SKIP, not abort a CI-gated script, or the same run_tests.sh goes
        # red on the maintainer's machine and green on CI (where this row SKIPs
        # wholesale). Every skip is named below, so a rejected receipt is visible
        # rather than silently leaving the denominator.
        #
        # round-4 / M5 — the READ IS INSIDE THE TRY, and the guard is (LintError, OSError,
        # UnicodeDecodeError). It is not only a malformed *receipt* that can reach this
        # loop: `--corpus DIR` is documented and glob-driven, so a non-UTF-8 byte
        # (UnicodeDecodeError, a ValueError — not an OSError), an unreadable file, or a
        # directory named `rcpt-*-asreturned.txt` (IsADirectoryError) all arrive here.
        # With the read one line above the try, each of those aborted a run_tests.sh-gated
        # script with a traceback — red on the maintainer's machine, green on CI, which is
        # the exact machine-divergence this row was demoted to advisory to prevent. The
        # narrowing argument is unchanged: still no bare `except Exception`, so a genuine
        # crash inside the SHIPPED parser is not reattributed to corpus drift.
        try:
            text = pathlib.Path(f).read_text()
            sections = rv.parse_receipt(text)
            witness = rv.parse_witness(sections["WITNESS"])
            artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        except (rv.LintError, OSError, UnicodeDecodeError) as e:
            skipped.append(f"{pathlib.Path(f).name}: {e}")
            continue
        # Same treatment for the two header regexes — but DEFENCE IN DEPTH, not a
        # reachable bug today: `\s+` spans newlines, so on a receipt whose VERDICT line
        # carries no value the match runs on and captures the NEXT line's first token
        # rather than returning None. The guards exist so that narrowing either regex
        # to `[ \t]+` later, or pointing --corpus at a truncated file, degrades to a
        # counted skip instead of `AttributeError: 'NoneType' has no attribute group`,
        # which is the same un-attributable hard abort the LintError guard above fixes.
        m_verdict = re.search(r"^VERDICT\s+(\S+)", text, re.M)
        m_ns = re.search(r"^RCPT v\S+\s+(\S+)", text, re.M)
        if m_verdict is None or m_ns is None:
            missing = "VERDICT line" if m_verdict is None else "RCPT header namespace"
            skipped.append(f"{pathlib.Path(f).name}: no {missing}")
            continue
        verdict = m_verdict.group(1)
        namespace = m_ns.group(1)
        is_rt = namespace.startswith("red-team/")
        rt_ns += is_rt
        if witness["kind"] != "grep":
            continue
        grep += 1
        if witness["range_kind"] is not None:
            ranged += 1
            memb += witness["art"] in artifacts
        if is_rt and (witness["art"] or "").endswith("findings.md"):
            rt_findings += 1
            if witness["expect_fail"] != "match":
                rt_wrong_form += 1
        if witness["expect_fail"] == "match" and witness.get("pattern"):
            mandated += 1
        elif witness["expect_fail"].startswith("/") and witness["expect_fail"].endswith("/"):
            sig_form += 1
            sig_on_pass += verdict == "PASS"
    print(f"   figures     : receipts={len(files)} measured={len(files) - len(skipped)} "
          f"skipped={len(skipped)} kind=grep={grep} ranged={ranged} "
          f"membership-ok={memb}")
    print(f"                 mandated pattern=+match={mandated}  expect-fail=/re/={sig_form} "
          f"(of which on a PASS: {sig_on_pass})")
    print(f"                 red-team/ namespace={rt_ns}, witness targets a findings file="
          f"{rt_findings}, of those in the WRONG form={rt_wrong_form}")
    for s in skipped:
        print(f"   SKIPPED     : {s}")
    rep.advise("corpus receipts", len(files), 17)
    rep.advise("corpus kind=grep", grep, 13)
    rep.advise("corpus ranged", ranged, 13)
    rep.advise("corpus membership-ok", memb, 12)
    rep.advise("corpus mandated pattern=+match", mandated, 5)
    rep.advise("corpus expect-fail=/re/", sig_form, 8)
    rep.advise("corpus expect-fail=/re/ on a PASS", sig_on_pass, 6)
    rep.advise("corpus red-team/ receipts", rt_ns, 4)
    rep.advise("corpus red-team/ witnesses on a findings file", rt_findings, 2)
    rep.advise("corpus red-team/ witnesses in the wrong form", rt_wrong_form, 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default=None,
                    help="§0e as-returned corpus dir (default: the machine-local path; "
                         "skipped when absent)")
    args = ap.parse_args(argv)
    corpus = pathlib.Path(args.corpus) if args.corpus else DEFAULT_CORPUS

    rv = load_rcpt_verify()
    rep = Report()
    print("#474 S13 — measured denominators, emitted and asserted from the shipped parser.")
    print("Every assertion keys on block identity or token text; none keys on a line number.")

    row_exec_jsonl(rv, rep)
    row_exec_file(rv, rep, RETURN_CONV, 2, dict(
        literal=12, range_shaped=4, accepted=4, max_l_span=219,
        in_band_blocks=[("RCPT v1 build/7-implementer", 219),
                        ("RCPT v1 build/8-implementer", 179),
                        ("RCPT v1.1 build/42-implementer", 60)]),
        note="a leak of grep's 1-B/line floor into EXEC turns build/7-implementer and "
             "build/8-implementer from committed LINT-FAIL to LINT-PASS")
    row_exec_file(rv, rep, RT_PROMPT, 3, dict(
        literal=1, range_shaped=0, accepted=0, max_l_span=0, in_band_blocks=[]))
    row_exec_file(rv, rep, RCPT_TESTS, 4, dict(
        literal=None, range_shaped=None, accepted=None, max_l_span=99,
        in_band_tokens=[('out=a.log#L1-L100"', 99)]),
        note="21/19/15 and max span 39 in the plan's §0h; S1's RED test 15 added "
             "out=a.log#L1-L100 — an in-band token HERE is the guard, not exposure. "
             "Every column is advisory for this file (round-1/MIN-3, round-4/S1); the "
             "GATE is that test 15's pin is still present.",
        assert_counts=False, pin_token='out=a.log#L1-L100"')
    row_grep_membership(rv, rep)
    row_taught_lint(rv, rep)
    row_corpus(rv, rep, corpus)

    print()
    if rep.errors:
        print(f"FAIL — {len(rep.errors)} figure(s) rotted:")
        for e in rep.errors:
            print(f"  - {e}")
        print("\nA rotted figure is not a test bug by default: re-derive it, then update "
              "BOTH this script and the plan/PR text that quotes it, naming the cause.")
        return 1
    print("measure_474_denominators: all figures reproduce.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
