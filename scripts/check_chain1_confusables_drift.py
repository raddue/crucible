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
CURRENTLY_UNCOVERED_VALUES = {"0", "1"}


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
    table. Runs in under half a second against the real 766-entry table.

    (MINOR 4, round-10 quality-gate: for a target that is one of the
    keyword's own letters, only that letter's FIRST position is exercised
    (`pos_list[0]` below) -- for target `S` this is position 0, never 5 or
    9; for `E`, position 3, never 6 or 8. ROUND-11 CORRECTION (quality-gate
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
    and Task 2's test is now the genuinely all-positions half.)"""
    rv = _load_rcpt_verify()
    keyword = "SUPERSEDES:"
    problems = []
    for src, target in mapping.items():
        pos_list = [i for i, c in enumerate(keyword) if c.upper() == target.upper()]
        if pos_list:
            pos = pos_list[0]
            line = keyword[:pos] + src + keyword[pos + 1:] + " 21a1b2c3d4e5"
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

    failures = []

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
          "a duplicated marker pair, and a missing composition-guard "
          "helper; tolerates a clean regeneration.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
