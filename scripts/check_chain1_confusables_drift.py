#!/usr/bin/env python3
"""Drift check for the CONFUSABLE_MAP block scripts/gen_chain1_confusables.py
splices into scripts/rcpt_verify.py (#567 round-1 quality-gate F1).

Invocation (from repo root):
    python3 scripts/check_chain1_confusables_drift.py            # check the tree
    python3 scripts/check_chain1_confusables_drift.py --selftest # built-in logic tests

Fully offline: replays gen_chain1_confusables.py's own parse()/render()
against the COMMITTED scripts/chain1_confusables_source.txt snapshot (never
the network) and asserts the result is byte-identical to the block currently
committed between rcpt_verify.py's BEGIN/END markers. Mirrors this repo's
existing generated/duplicated-content checkers
(check_delve_helper_drift.py, check_ledger_append_doc_drift.py,
check_canonical_drift.py) -- reuses the generator's own logic rather than
re-implementing it, so the two can never independently drift from each
other; what this catches is the COMMITTED block drifting from what the
generator would currently produce (a hand-edit, a missed re-splice after
editing TARGET_ALPHABET, or a stale snapshot).

Exits 0 if the committed block matches a fresh regeneration, 1 with a diff
otherwise. Stdlib only.
"""
from __future__ import annotations
import difflib
import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RCPT_VERIFY = ROOT / "scripts" / "rcpt_verify.py"
SOURCE_SNAPSHOT = ROOT / "scripts" / "chain1_confusables_source.txt"
GEN = ROOT / "scripts" / "gen_chain1_confusables.py"


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_chain1_confusables", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_rcpt_verify():
    """round-9 quality-gate SIGNIFICANT 1: imports the live
    scripts/rcpt_verify.py -- this checker's own splice target -- so
    sanity_check_reachability below can call its real
    `_legacy_supersedes_claim`, rather than re-implementing any part of
    that logic here (the same reason `check()` above reuses the
    generator's own `parse()`/`render()` instead of re-parsing
    confusables.txt by hand)."""
    spec = importlib.util.spec_from_file_location("rcpt_verify", RCPT_VERIFY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_block(rcpt_text, begin_marker, end_marker):
    pattern = re.compile(re.escape(begin_marker) + r".*?" + re.escape(end_marker), re.DOTALL)
    matches = pattern.findall(rcpt_text)
    if len(matches) != 1:
        return None, len(matches)
    return matches[0], 1


def check(rcpt_text, source_text, gen) -> list:
    problems = []
    actual, n = extract_block(rcpt_text, gen.BEGIN_MARKER, gen.END_MARKER)
    if n != 1:
        problems.append(
            f"expected exactly one {gen.BEGIN_MARKER!r}...{gen.END_MARKER!r} "
            f"block, found {n}")
        return problems
    mapping = gen.parse(source_text)
    version_line, date_line = gen.source_header(source_text)
    expected = gen.render(mapping, version_line, date_line, source_text).rstrip("\n")
    if actual != expected:
        diff = "\n".join(difflib.unified_diff(
            expected.splitlines(), actual.splitlines(),
            fromfile="expected (regenerated)", tofile="actual (committed)",
            lineterm=""))
        problems.append(
            "CONFUSABLE_MAP block in rcpt_verify.py has drifted from what "
            "regenerating from the committed source snapshot produces:\n" + diff)
    # round-9 quality-gate SP1: a misreading of Step 0/Task 3 Step 3's marker
    # placement could put the composition-guard helper BETWEEN the markers
    # instead of below them -- `extract_block`'s DOTALL regex would then
    # delete it wholesale on the next regeneration, silently, since the
    # regenerated block still matches (nothing above checks the helper is
    # even present). A plain substring check on the security-critical
    # helper's own `def` line is a cheap, direct guard against exactly that.
    #
    # round-10 quality-gate MINOR 3: check every one of the four new
    # module-level names Task 3 Step 3 places below the END marker, not
    # just this one helper's own `def` line -- the stated hazard (a
    # regeneration wiping the region) removes all four at once, so one grep
    # already caught it, but the message read as a general "the security
    # helpers are present" assertion when it checked only one of them.
    for name in ("_SUPERSEDES_KEYWORD", "_SUPERSEDES_VALUE_RE",
                 "def _classify_supersedes_value(",
                 "def _keyword_reachable_by_dropping_optionals("):
        if name not in rcpt_text:
            problems.append(
                f"{name} is missing from rcpt_verify.py -- if a "
                f"regeneration just ran, check that Task 3's composition-"
                f"guard helpers live BELOW the CONFUSABLE_MAP END marker, "
                f"not between the markers (see Task 1 Step 0)")
    return problems


# round-3 quality-gate S2: promoted from a one-off `python3 -c "..."` manual
# sanity check (formerly Task 1 Step 2's "Sanity-check a handful of entries
# by hand" block) into a check this file itself runs against the REAL
# vendored snapshot every time -- unlike selftest() above (deliberately
# synthetic-input, so it works with no real snapshot present), this one only
# runs from main() below, where SOURCE_SNAPSHOT is guaranteed to exist. A
# hand-run shell one-liner is never re-run once its author moves on; this is.
KNOWN_MAPPINGS = {
    0x0405: "S",     # CYRILLIC CAPITAL LETTER DZE
    0x0415: "E",     # CYRILLIC CAPITAL LETTER IE
    0x0395: "E",     # GREEK CAPITAL LETTER EPSILON
    0xFF1A: ":",     # FULLWIDTH COLON
    0x1D412: "S",    # MATHEMATICAL BOLD CAPITAL S
    0xFF41: "a",     # FULLWIDTH LATIN SMALL LETTER A -- Task 2 depends on this
    0x043E: "o",     # CYRILLIC SMALL LETTER O -- Task 2 depends on this
    0x01A6: "R",     # LATIN LETTER YR -- Task 2's positive R-coverage test
    0xA731: "s",     # LATIN LETTER SMALL CAPITAL S -- round-2 F3
    0x1D1C: "u",     # LATIN LETTER SMALL CAPITAL U -- round-2 F3
}

# round-3 quality-gate F2, NARROWED round-4 quality-gate F1: the vendored
# table's TRUE table-level residue -- see the Task 3 docstring's "Known
# residue" paragraph for the full accounting. Every one of these is a
# Unicode-documented confusables.txt TARGET (a "prototype", not a source)
# whose own `str.lower()` is a no-op, so parse()'s `tgt_char.lower() not in
# TARGET_ALPHABET_LOWER` filter drops every entry that maps TO it, regardless
# of how visually convincing the source glyph is.
#
# ROUND-4 NARROWING (quality-gate F1): the round-3 version of this dict also
# carried D, E, P, R (in-keyword letters) and the PUA codepoint 0xE000. All
# five are DROPPED here -- not because the table now maps them (it still
# doesn't), but because they are no longer SECURITY residue: Task 3's
# composition guard (`_keyword_reachable_by_dropping_optionals`'s bounded
# wildcard extension) now catches a substitution at any of these positions
# and resolves it to `"malformed"`, not a silent miss. What remains here is
# scoped to where an unmapped table entry still changes user-visible
# behavior at all -- the VALUE grammar, which the wildcard guard does not
# reach: A/B (hex digits) and N (opens the `none` sentinel).
#
# ROUND-7 RE-CHECK (quality-gate SECOND PASS 1): this narrowing's premise --
# "the composition guard ... now catches a substitution at any of these
# positions" -- is conditional on the guard actually RUNNING, which
# round-7's own FATAL 1 showed it did not whenever the line also carried a
# literal `SUPERSEDES:` match (the round-6 `found_on_line` gate suppressed
# the guard for the WHOLE LINE, not just the literal match's own span).
# Re-verified after round-7's fix (which makes the guard run on every line,
# masking only the literal match's own token span, not the whole line): a
# keyword-letter substitution at any of D/E/P/R/PUA is caught regardless of
# whether an unrelated literal `SUPERSEDES:` claim also appears elsewhere on
# the same line -- confirmed by direct execution
# (`test_same_line_literal_and_fragmented_supersedes_both_detected`, Task 2).
# This narrowing's premise holds; no further change needed here.
KNOWN_RESIDUE = {
    0x1D00: "A",  # LATIN LETTER SMALL CAPITAL A
    0x0299: "B",  # LATIN LETTER SMALL CAPITAL B
    0x0274: "N",  # LATIN LETTER SMALL CAPITAL N
}

# ROUND-5 quality-gate S2: KNOWN_RESIDUE above only pins codepoints that HAVE
# a source-side entry to watch for newly mapping -- but two claim-alphabet
# characters have NO table coverage at all, from ANY codepoint: the digits
# `0` and `1`. Unicode routes their visual lookalikes to the LETTERS `O`/`l`
# instead (outside TARGET_ALPHABET), never to the digits themselves, so
# there is no source codepoint for KNOWN_RESIDUE to hang an entry off.
# sanity_check_alphabet_coverage() below is a positive-coverage check
# instead: it does not need a source codepoint, only confirmation that these
# two values remain absent from what the table can ever produce.
# PR #714: capital "I" joins them -- UTS #39 routes every I-lookalike
# (U+0406, U+0399, ...) to lowercase 'l', which _v11_keyword_end accepts for I.
CURRENTLY_UNCOVERED_VALUES = {"0", "1", "I"}


def sanity_check_known_mappings(mapping) -> list:
    """Asserts every KNOWN_MAPPINGS entry resolves as expected and every
    KNOWN_RESIDUE entry is (still) absent. Returns a list of problem
    strings, empty if clean. A future Unicode release changing one of the
    KNOWN_MAPPINGS entries, or newly covering one of the KNOWN_RESIDUE
    entries, is exactly the kind of change this check exists to surface as
    an explicit, readable failure rather than a silent behavior change."""
    problems = []
    for cp, expected in KNOWN_MAPPINGS.items():
        actual = mapping.get(chr(cp))
        if actual != expected:
            problems.append(
                f"KNOWN_MAPPINGS: U+{cp:04X} expected {expected!r}, got {actual!r}")
    for cp, expected_target in KNOWN_RESIDUE.items():
        if chr(cp) in mapping:
            problems.append(
                f"KNOWN_RESIDUE: U+{cp:04X} was expected to remain UNMAPPED "
                f"(documented residue for letter {expected_target!r}) but "
                f"now maps to {mapping[chr(cp)]!r} -- if this is a "
                f"deliberate closure, update the Task 3 docstring's Known "
                f"residue paragraph and this list together")
    return problems


def sanity_check_no_ascii_sources(mapping) -> list:
    """round-4 quality-gate S2: every SOURCE character must be non-ASCII --
    parse() excludes ASCII sources by construction (see its own comment),
    but a future change there could silently reintroduce one. An ASCII key
    would otherwise be shielded from firing only by loop ordering in
    _legacy_supersedes_claim's skeleton step, not by anything this table
    itself guarantees."""
    return [f"ASCII source U+{ord(src):04X} ({src!r}) in CONFUSABLE_MAP -- "
            f"see parse()'s ASCII-source exclusion"
            for src in mapping if ord(src) < 128]


def sanity_check_ascii_targets(mapping) -> list:
    """round-5 quality-gate M3: mirrors sanity_check_no_ascii_sources above,
    but for the TARGET side -- every CONFUSABLE_MAP value must itself be
    ASCII. parse()'s filter (`tgt_char.lower() in TARGET_ALPHABET_LOWER`)
    does not itself require tgt_char to be ASCII; it is ASCII today only
    because TARGET_ALPHABET is. _legacy_supersedes_claim's own
    `skeleton_upper = skeleton.upper()` comment ("length-preserving on this
    pure-ASCII skeleton") depends on every mapped value staying ASCII --
    a future change to TARGET_ALPHABET or parse()'s filter could silently
    violate that with no other check to catch it."""
    return [f"non-ASCII target {tgt!r} (U+{ord(tgt):04X}) in CONFUSABLE_MAP "
            f"-- see parse()'s TARGET_ALPHABET filter"
            for tgt in mapping.values() if ord(tgt) >= 128]


def sanity_check_alphabet_coverage(mapping, target_alphabet) -> list:
    """round-5 quality-gate S2: KNOWN_RESIDUE pins the specific codepoints
    excluded by the case-insensitive filter even though the VALUE they'd
    otherwise stand in for is covered by OTHER confusables.txt entries --
    but `0` and `1` have no table coverage at all, from any codepoint (see
    CURRENTLY_UNCOVERED_VALUES above), so there is no source codepoint for
    KNOWN_RESIDUE to track. This is a positive check instead: every
    character in the claim alphabet below is expected to be a
    CONFUSABLE_MAP value UNLESS it's in CURRENTLY_UNCOVERED_VALUES. Catches
    both directions: a NEW uncovered character (a real table regression) and
    a future Unicode release starting to cover `0`/`1` (worth a deliberate
    docstring update, not a silent widening).

    ROUND-7 CORRECTION (quality-gate MINOR 3): the alphabet checked used to
    be a hand-written literal (`"SUPERDsuperd:none0123456789abcdef"`) -- a
    THIRD independent spelling of TARGET_ALPHABET, alongside the generator's
    own `TARGET_ALPHABET` and the design doc's (already-flagged-wrong,
    round-1 M3 + round-3 S3 + round-6 M1) `SUPERDTNXdiceonhx...` -- reopening
    the identical drift risk this file just finished diagnosing twice.
    Derived from `TARGET_ALPHABET` instead: both cases, since a table VALUE
    can legitimately be either case (parse()'s filter keeps Unicode's own
    documented case, round-2 F3) while this check's OWN alphabet must cover
    both to have any chance of matching. Confirmed by direct execution
    against the real 766-entry table that this derivation checks a
    STRICT SUPERSET of the literal it replaces (adds uppercase A/B/C/F/N/O,
    which round-6 M1's own measurement already showed the table legitimately
    produces) and reports zero new problems. `target_alphabet` is passed in
    (the generator module's own `TARGET_ALPHABET`, via `main()`'s `gen`
    reference below) rather than imported directly -- this file only ever
    reaches the generator's module object through `_load_gen()`."""
    values = set(mapping.values())
    problems = []
    alphabet = ({c.upper() for c in target_alphabet}
                | {c.lower() for c in target_alphabet})
    for c in alphabet:
        if c not in values and c not in CURRENTLY_UNCOVERED_VALUES:
            problems.append(
                f"{c!r} has no CONFUSABLE_MAP value coverage at all and is "
                f"not in CURRENTLY_UNCOVERED_VALUES -- new table gap, or "
                f"CURRENTLY_UNCOVERED_VALUES needs updating")
    for c in CURRENTLY_UNCOVERED_VALUES:
        if c in values:
            problems.append(
                f"{c!r} is now covered by CONFUSABLE_MAP -- a future "
                f"Unicode release must have started mapping something to "
                f"it; update CURRENTLY_UNCOVERED_VALUES and the Task 3 "
                f"docstring's residue paragraph together")
    return problems


def sanity_check_reachability(mapping) -> list:
    """round-9 quality-gate SIGNIFICANT 1: every sanity check above is a
    property of `mapping` in isolation -- none of them exercises
    `_legacy_supersedes_claim`, the CONSUMING pipeline. A vendored entry the
    consuming code cannot reach at all is indistinguishable, to every check
    above, from one that works (measured: U+FE30, live in the real table,
    passed every one of them while being structurally inert -- see round-9
    FATAL 2). For each mapping entry, substitute the source at the position
    of its own mapped letter -- in "SUPERSEDES:" if the target is one of its
    letters, in a well-formed value (a 12-hex run, or "none") otherwise --
    and assert the resulting claim is not `None`, i.e. the substitution is
    DETECTED by the actual running mechanism, not merely present in the
    table. Runs against the committed confusables table.

    The target-coverage loop exercises every matching position in both
    `SUPERSEDES:` and `TRIPWIRE-CHILD:` so repeated letters and punctuation
    do not escape reachability coverage. ROUND-11 CORRECTION (quality-gate
    SIGNIFICANT 2): round-10's own claim that Task 2's
    `test_every_documented_confusable_for_a_keyword_letter_is_reachable`
    already covers the OTHER positions was false as written -- that test's
    candidate pool filtered on NFKD-all-ASCII, which excludes a
    CONFUSABLE_MAP-resolved entry whose NFKD does not itself decompose to
    ASCII (66 of 485 (entry, position) pairs, including Cyrillic Ѕ at
    positions 5 and 9, were covered by neither sweep). That test's
    candidate pool is now widened to the union of NFKD-all-ASCII and
    `CONFUSABLE_MAP.keys()`, so the claim now genuinely holds: this
    function is still the all-entries, first-position half of the pair,
    and Task 2's test is now the genuinely all-positions half.)

    WARDEN-GATE FINDING 3 (GH #567 round 1) -- everything above is a
    per-entry loop: an EMPTY (or drastically shrunken) `mapping` makes the
    loop run zero (or too few) times and this function returns `[]`, a
    vacuous pass indistinguishable from "every entry checked out". Guarded
    below by a genuine floor: `mapping`'s size must match the live,
    imported `CONFUSABLE_MAP` this checker's own splice target actually
    runs with (`rv`, already loaded above for the per-entry loop) -- reusing
    that existing wiring rather than inventing a second way to reach
    rcpt_verify.py's table."""
    rv = _load_rcpt_verify()
    keyword = "SUPERSEDES:"
    problems = []
    if len(mapping) != len(rv.CONFUSABLE_MAP):
        problems.append(
            f"mapping has {len(mapping)} entries but the live "
            f"rcpt_verify.py CONFUSABLE_MAP has {len(rv.CONFUSABLE_MAP)} -- "
            f"an empty or drastically shrunken mapping would otherwise pass "
            f"this function's per-entry loop vacuously (nothing to iterate "
            f"is nothing to fail)")
        return problems
    for src, target in mapping.items():
        v11_keyword = "TRIPWIRE-CHILD:"
        needle = "I" if target.lower() == "l" else target.upper()
        v11_positions = [i for i, c in enumerate(v11_keyword) if c == needle]
        for pos in v11_positions:
            if rv._v11_keyword_end(v11_keyword[:pos] + src + v11_keyword[pos + 1:] + " none", v11_keyword) is None:
                problems.append(
                    f"U+{ord(src):04X} ({src!r} -> {target!r}) is in "
                    f"CONFUSABLE_MAP but UNREACHABLE through _v11_keyword_end "
                    f"at position {pos}")
        pos_list = [i for i, c in enumerate(keyword) if c.upper() == target.upper()]
        if pos_list:
            for pos in pos_list:
                line = keyword[:pos] + src + keyword[pos + 1:] + " 21a1b2c3d4e5"
                text = f"RCPT v1 skill=x\nTRACE\nNEXT\n{line}\n"
                if rv._legacy_supersedes_claim(text) is None:
                    problems.append(
                        f"U+{ord(src):04X} ({src!r} -> {target!r}) is in "
                        f"CONFUSABLE_MAP but UNREACHABLE through "
                        f"_legacy_supersedes_claim at position {pos}")
            continue
        elif target.lower() in "0123456789abcdef":
            # round-10 quality-gate SIGNIFICANT 2: substitute src (the
            # actual vendored confusable), not target (plain ASCII) -- the
            # earlier version of this branch (and the two below) built a
            # line out of `target`, so the assertion held regardless of
            # whether `src` was reachable, or even present in the table.
            # Confirmed zero-churn: all 465 previously-unexercised entries
            # (the three branches below plus this one) pass once correctly
            # substituted.
            line = keyword + " " + src + "1a1b2c3d4e5"
        elif target.lower() == "n":
            line = keyword + " " + src + "one"
        elif target.lower() == "o":
            line = keyword + " n" + src + "ne"
        elif target.lower() in "tripwire-child":
            continue
        elif target == "-" or target == ":":
            # Also pin the punctuation at each position in TRIPWIRE-CHILD:.
            continue
        else:
            problems.append(
                f"U+{ord(src):04X} ({src!r} -> {target!r}) maps to a target "
                f"outside SUPERSEDES:/none/hex -- sanity_check_reachability "
                f"does not know how to place it; extend this function's "
                f"placement rules rather than silently skipping it")
            continue
        text = f"RCPT v1 skill=x\nTRACE\nNEXT\n{line}\n"
        if rv._legacy_supersedes_claim(text) is None:
            problems.append(
                f"U+{ord(src):04X} ({src!r} -> {target!r}) is in "
                f"CONFUSABLE_MAP but UNREACHABLE through "
                f"_legacy_supersedes_claim -- vendored, but structurally "
                f"inert")
    return problems


# WARDEN-GATE FINDING 3, part 2 (GH #567 round 1): the codepoint whose own
# round-9 "Known residue" measurement (rcpt_verify.py's Task 3 docstring,
# "SOURCE-LEVEL fallback" paragraph) documents it as reachable ONLY through
# the token-building loop's source-level fallback branch (its own NFKD
# pieces resolve to nothing kept/mapped, so only a lookup on the SOURCE
# codepoint itself, `if not produced_any and ch in CONFUSABLE_MAP`, finds
# it) -- deleting that branch does not un-detect this codepoint, because a
# dropped codepoint at the keyword's trailing-colon position is STILL
# wildcard-reachable (this file's own `sanity_check_reachability` above
# cannot tell "reached via the mapped ':'" from "reached via a WILDCARD
# standing in for it" -- both return non-`None`). What differs is the
# RESOLVED VALUE: the mapped ':' lands in `skeleton_chars`, so the LITERAL
# rescan loop finds "SUPERSEDES:" and reads the real hex value that follows
# it; a WILDCARD never enters `skeleton_chars` at all, so the literal loop
# can't see it, and only the composition guard's `_keyword_reachable_by_
# dropping_optionals` fires, which always resolves "malformed" (never the
# actual value) once reachable. This is the targeted, mechanism-level
# regression check `sanity_check_reachability` cannot provide.
_SOURCE_LEVEL_FALLBACK_ONLY_CODEPOINT = 0xFE30  # PRESENTATION FORM FOR
# VERTICAL TWO DOT LEADER -- the documented case; see rcpt_verify.py's
# Task 3 docstring for why its NFKD pieces (two ASCII periods) resolve to
# nothing kept or mapped.


def sanity_check_source_level_fallback(mapping) -> list:
    """Pins that U+FE30 -- reachable only via the round-9 source-level
    fallback branch -- resolves to its EXACT mapped ':' in the running
    skeleton, not merely to SOME detection. Placed at the keyword's own
    trailing colon, followed by a real hex value: if the fallback branch
    resolves it, the literal rescan loop finds "SUPERSEDES:" and returns
    the hex value verbatim; if that branch is deleted (the round-9
    regression this check exists to catch), U+FE30 falls through to a bare
    WILDCARD, the literal loop never sees a colon at all, and only the
    composition guard fires -- which resolves "malformed" unconditionally,
    regardless of the real value that follows. Confirmed by execution
    against a scratch copy of rcpt_verify.py with the fallback branch
    (`if not produced_any and ch in CONFUSABLE_MAP:`) removed: the exact
    value this check demands changes from the real hex value to
    "malformed" -- a claim is still detected either way (which is why
    sanity_check_reachability above, and all 36 pre-existing
    TestChain1HomoglyphAndScanScope567 tests, pass regardless of whether
    the fallback branch is present), but the EXACT resolved value is not,
    which is what this check demands instead."""
    rv = _load_rcpt_verify()
    src = chr(_SOURCE_LEVEL_FALLBACK_ONLY_CODEPOINT)
    if src not in mapping:
        return [
            f"U+{_SOURCE_LEVEL_FALLBACK_ONLY_CODEPOINT:04X} is no longer a "
            f"CONFUSABLE_MAP source -- this check's documented "
            f"source-level-fallback-only case (see rcpt_verify.py's Task 3 "
            f"docstring) needs a different codepoint; find one whose NFKD "
            f"pieces are all outside [A-Za-z0-9:] and not themselves table "
            f"keys, update _SOURCE_LEVEL_FALLBACK_ONLY_CODEPOINT, and check "
            f"the docstring's own example is still accurate"]
    text = f"RCPT v1 skill=x\nTRACE\nNEXT\nSUPERSEDES{src} 21a1b2c3d4e5\n"
    result = rv._legacy_supersedes_claim(text)
    if result != "21a1b2c3d4e5":
        return [
            f"U+{_SOURCE_LEVEL_FALLBACK_ONLY_CODEPOINT:04X} reaches "
            f"_legacy_supersedes_claim as {result!r}, not the exact hex "
            f"value '21a1b2c3d4e5' -- it is reachable ONLY through the "
            f"round-9 source-level fallback branch (its own NFKD pieces "
            f"resolve to nothing kept or mapped), so this means that "
            f"branch is gone or broken: the codepoint is falling through "
            f"to a bare WILDCARD, which the composition guard still "
            f"detects (as 'malformed', never the real value) but "
            f"sanity_check_reachability above cannot distinguish from a "
            f"genuine mapped-':' detection"]
    return []


def main() -> int:
    gen = _load_gen()
    # round-4 quality-gate M4: an explicit, actionable message on a partial
    # checkout -- gen.main() already raises one; this checker, wired into
    # scripts/run_tests.sh, previously let a bare FileNotFoundError escape
    # into the gating suite instead.
    if not SOURCE_SNAPSHOT.exists():
        print(f"{SOURCE_SNAPSHOT} not found -- run "
              f"'python3 scripts/gen_chain1_confusables.py --vendor' first.")
        return 1
    rcpt_text = RCPT_VERIFY.read_text(encoding="utf-8")
    source_text = SOURCE_SNAPSHOT.read_text(encoding="utf-8")
    mapping = gen.parse(source_text)
    problems = check(rcpt_text, source_text, gen)
    problems += sanity_check_known_mappings(mapping)
    problems += sanity_check_no_ascii_sources(mapping)
    problems += sanity_check_ascii_targets(mapping)
    problems += sanity_check_alphabet_coverage(mapping, gen.TARGET_ALPHABET)
    problems += sanity_check_reachability(mapping)
    problems += sanity_check_source_level_fallback(mapping)
    if problems:
        print("CHAIN1 CONFUSABLES DRIFT:")
        for p in problems:
            print(p)
        print("\nRe-run `python3 scripts/gen_chain1_confusables.py` to "
              "re-splice, or update this check if the divergence is "
              "intentional.")
        return 1
    print("OK -- the CONFUSABLE_MAP block in rcpt_verify.py matches a fresh "
          "regeneration from the committed source snapshot.")
    return 0


def selftest() -> int:
    """Synthetic-input logic tests (do not depend on the real, large
    vendored snapshot being present/current): a positive leg (fresh
    regeneration matches itself) and four negative legs -- a flipped
    mapped value, missing markers, duplicated markers, and (round-9
    quality-gate SP1) a missing composition-guard helper -- each of which
    must be caught."""
    gen = _load_gen()
    fake_source = (
        "# confusables.txt\n"
        "# Date: 2025-07-22, 05:49:37 GMT\n"
        "# Version: 17.0.0\n"
        "\n"
        "0405 ; 0053 ; MA  # ( S -> S )\n"
        "0415 ; 0045 ; MA  # ( E -> E )\n"
    )
    mapping = gen.parse(fake_source)
    version_line, date_line = gen.source_header(fake_source)
    good_block = gen.render(mapping, version_line, date_line, fake_source).rstrip("\n")
    rcpt_clean = (
        "X = 1\n\n" + good_block + "\n\n"
        # round-9 quality-gate SP1, WIDENED round-10 quality-gate MINOR 3:
        # all four of Task 3 Step 3's new module-level names must be
        # present for the positive leg to stay clean now that check() greps
        # for all of them -- bare stubs are enough, this checker never
        # executes any of this, only greps for the signatures.
        "_SUPERSEDES_KEYWORD = 'SUPERSEDES:'\n"
        "_SUPERSEDES_VALUE_RE = None\n"
        "def _classify_supersedes_value(a, b, c):\n    return None\n\n\n"
        "def _keyword_reachable_by_dropping_optionals(tokens):\n    return False\n\n\n"
        "def _legacy_supersedes_claim(text):\n    return None\n"
    )

    # The reachability sweep must exercise every matching keyword position;
    # pin the old first-position-only mutant so this cannot regress silently.
    position_probe = {"X": "S"}
    class Probe:
        CONFUSABLE_MAP = position_probe
        @staticmethod
        def _v11_keyword_end(line, keyword): return 1
        @staticmethod
        def _legacy_supersedes_claim(text):
            return None if text.splitlines()[3][5] == "X" else "ok"
    real_loader = globals()["_load_rcpt_verify"]
    globals()["_load_rcpt_verify"] = lambda: Probe
    try:
        position_errors = sanity_check_reachability(position_probe)
    finally:
        globals()["_load_rcpt_verify"] = real_loader
    failures = []
    if not any("position 5" in error for error in position_errors):
        failures.append("case-E: non-first repeated-keyword position not exercised")

    problems = check(rcpt_clean, fake_source, gen)
    if problems:
        failures.append(f"positive: clean pair unexpectedly flagged: {problems}")

    mutated = rcpt_clean.replace("'S',  # U+0405", "'Z',  # U+0405")
    if mutated == rcpt_clean:
        failures.append("case-A: mutation anchor not found (test is vacuous)")
    problems = check(mutated, fake_source, gen)
    if not problems:
        failures.append("case-A: flipped mapped value NOT caught")

    no_markers = rcpt_clean.replace(gen.BEGIN_MARKER, "").replace(gen.END_MARKER, "")
    problems = check(no_markers, fake_source, gen)
    if not problems:
        failures.append("case-B: missing markers NOT caught")

    duplicated = rcpt_clean + "\n" + good_block + "\n"
    problems = check(duplicated, fake_source, gen)
    if not problems:
        failures.append("case-C: duplicated marker pair NOT caught")

    no_helper = rcpt_clean.replace(
        "def _keyword_reachable_by_dropping_optionals(tokens):\n    return False\n\n\n",
        "")
    if no_helper == rcpt_clean:
        failures.append("case-D: helper-removal anchor not found (test is vacuous)")
    problems = check(no_helper, fake_source, gen)
    if not problems:
        failures.append("case-D: missing composition-guard helper NOT caught")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(" ", f)
        return 1
    print("SELFTEST OK -- catches a flipped mapped value, missing markers, "
          "a duplicated marker pair, a missing composition-guard helper, "
          "and first-position-only reachability; tolerates a clean regeneration.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
