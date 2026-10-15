#!/usr/bin/env python3
"""Regenerate the CONFUSABLE_MAP block embedded in scripts/rcpt_verify.py from
Unicode's confusables.txt (UTS #39). This script's main()/--vendor are NOT run
by scripts/run_tests.sh or any CI path -- picking up a new Unicode release is
a manual, offline maintenance act. (Round-2 quality-gate Minor 7:
scripts/check_chain1_confusables_drift.py DOES import and execute this
module's top level on every CI run, via importlib, to call its parse()/
render() -- so it is not true that this FILE never runs under CI, only that
its main()/--vendor entry points don't.) Two separate steps, so a re-vendor
is an explicit, auditable act and every OTHER regeneration is fully offline
(no network in CI, ever -- scripts/check_chain1_confusables_drift.py replays
this file's own parse()/render() against the COMMITTED source snapshot,
never the network):

    # 1. Only when you want to pick up a new Unicode release:
    python3 scripts/gen_chain1_confusables.py --vendor
    #    Fetches confusables.txt and writes it VERBATIM to
    #    scripts/chain1_confusables_source.txt (commit the result).

    # 2. Every time -- including immediately after --vendor, and any time you
    #    touch TARGET_ALPHABET or this file's parse()/render() logic -- to
    #    re-splice scripts/rcpt_verify.py's generated block from the
    #    (committed) source snapshot:
    python3 scripts/gen_chain1_confusables.py

Step 2 with no fresh --vendor is the common case and needs no network at all.
scripts/check_chain1_confusables_drift.py asserts the committed block in
rcpt_verify.py never drifts from what step 2 would currently produce.
"""
from __future__ import annotations
import hashlib
import re
import sys
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_URL = "https://www.unicode.org/Public/security/latest/confusables.txt"
SOURCE_SNAPSHOT = ROOT / "scripts" / "chain1_confusables_source.txt"
RCPT_VERIFY = ROOT / "scripts" / "rcpt_verify.py"

BEGIN_MARKER = "# --- BEGIN GENERATED CONFUSABLE_MAP (scripts/gen_chain1_confusables.py) ---"
END_MARKER = "# --- END GENERATED CONFUSABLE_MAP ---"

# The only characters a well-formed `SUPERSEDES:`-claim line can legally
# contain: the keyword itself, the confirmed grammar's `none` sentinel, and
# a 12-hex receipt-hash prefix. Scoped deliberately narrow (not the full
# confusables set) -- see the design doc's "Decision A" for why. NOTE
# (round-1 quality-gate M3): the design doc's own inspection invariant names
# a broader alphabet string (`SUPERDTNXdiceonhx0123456789abcdef:`, including
# T/N/X/i/c/h/x, none of which appear in "SUPERSEDES:", "none", or a hex
# prefix). TARGET_ALPHABET here is correct as a statement about ITSELF --
# it is exactly the union of characters those three tokens can contain.
# ROUND-3 CORRECTION (quality-gate S3): an earlier version of this comment
# went on to claim the design doc's broader string was therefore "simply
# looser than it needs to be" about the generated table's VALUES too. That
# is backwards. TARGET_ALPHABET constrains which characters a MAPPING
# TARGET may be drawn from; it does not constrain the CASE the generated
# table actually stores that target in -- parse() below keeps Unicode's own
# documented case (round-2 quality-gate F3), so a value can be the
# opposite case of anything in this literal (e.g. small-capital S maps to
# lowercase "s", full-width A maps to uppercase "A"). Measured on the real
# generated table: the distinct VALUES are
# `23456789:ABCDEFNOPRSUabcdefnoprsu` -- ten characters
# (A B C F N O p r s u) that are not themselves in TARGET_ALPHABET's literal
# spelling above (round-6 quality-gate M1: corrected from nine -- N, from
# e.g. U+039D GREEK CAPITAL LETTER NU mapping to uppercase 'N', was
# omitted; TARGET_ALPHABET's own literal spelling only contains lowercase
# `n` from `none`). So the design doc's mirrored "every value is one of
# SUPERDTNXdiceonhx..." invariant is not merely loose, it actually FAILS on
# the real table, and it fails BECAUSE of the case-insensitive filter this
# round-2 fix introduced -- not because the design doc over-specified. The
# correct relationship: TARGET_ALPHABET bounds this generator's SOURCE-side
# filter; the VALUE set a reader should check against is
# `{c, c.upper(), c.lower() : c in TARGET_ALPHABET}`. Not reconciled in the
# design doc itself -- out of this plan's edit boundary (round-10
# quality-gate SIGNIFICANT 5: the specific sentence is
# docs/plans/2026-09-01-567-chain1-homoglyph-scanscope-design.md:478-481,
# "every *value* should be one of `SUPERDTNXdiceonhx0123456789abcdef:` or
# the equivalent").
# PR #714 review (High 2): the v1.1 Layer-2 keywords TRIPWIRE:/TRIPWIRE-CHILD:
# are matched through the SAME table (parse_v11_sections), so their letters
# must be in the alphabet too -- without T/I/W/H/L a homoglyph'd TRIPWIRE line
# skeletonized to a non-keyword. The hyphen is deliberately excluded: the
# skeleton drops ASCII punctuation, so a '-' target would add a char no
# keyword skeleton contains.
TARGET_ALPHABET = (set("SUPERSEDES:") | set("none") | set("0123456789abcdef")
                   | set("TRIPWIRECHILD"))

# round-2 quality-gate F3: TARGET_ALPHABET above is case-mixed (uppercase
# SUPERDT..., lowercase none/hex), so a case-SENSITIVE `in` test against it
# drops any confusables.txt entry whose Unicode-documented prototype is the
# OTHER case of one of these letters -- e.g. U+A731 LATIN LETTER SMALL
# CAPITAL S is documented as confusable with lowercase "s", which is not
# itself in TARGET_ALPHABET, so a naive filter silently discards it even
# though Task 3's own keyword/value search is what actually needs to be
# case-tolerant, not this table. Filtering (and, in Task 3, searching) on
# the LOWERED form closes that gap without discarding case information --
# see parse() below and Task 3 Step 3's `skeleton.upper().find(...)`.
TARGET_ALPHABET_LOWER = {c.lower() for c in TARGET_ALPHABET}


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def vendor():
    """Fetch confusables.txt and write it VERBATIM to SOURCE_SNAPSHOT -- the
    committed, offline input every other run of this script (and
    check_chain1_confusables_drift.py) replays against. Run this only when
    you deliberately want to pick up a new Unicode release; commit the
    resulting snapshot together with the re-spliced rcpt_verify.py block."""
    text = fetch(SOURCE_URL)
    # round-3 quality-gate M5: explicit newline="\n" on every write_text()
    # call in this file -- the default (newline=None) translates "\n" to
    # os.linesep, so on Windows --vendor would write a CRLF snapshot and,
    # worse, main()'s splice() below would rewrite ALL of rcpt_verify.py
    # with CRLF line endings.
    SOURCE_SNAPSHOT.write_text(text, encoding="utf-8", newline="\n")
    # round-2 quality-gate Minor 1: len(text) on a decoded str is a
    # CHARACTER count, not a byte count -- label it accurately so the
    # "stop and investigate" discipline below doesn't fire on a correct run.
    print(f"wrote {SOURCE_SNAPSHOT} ({len(text)} characters)", file=sys.stderr)


def source_header(text):
    """Pull Unicode's own `# Version:` / `# Date:` header lines out of a
    confusables.txt-shaped text (round-1 quality-gate S7 -- provenance lives
    in the vendored file itself, not a hand-typed sentence in this plan).
    Falls back to a literal 'unknown' rather than raising, so a hand-edited
    or older-format snapshot still regenerates -- with an honestly
    incomplete header -- instead of hard-failing the offline regen path."""
    version = next((l.strip().lstrip("#").strip() for l in text.splitlines()
                     if l.startswith("# Version:")), "Version: unknown")
    date = next((l.strip().lstrip("#").strip() for l in text.splitlines()
                 if l.startswith("# Date:")), "Date: unknown")
    return version, date


def resolved_source_url(version_line):
    """A versioned, non-`latest` URL derived from Unicode's own `# Version:`
    line (round-1 quality-gate S7 -- `.../security/latest/...` points at a
    moving target and does not reproduce what was actually vendored). NOTE
    (round-2 quality-gate S3): Unicode does not always publish a directory
    for a version the moment it appears under `latest/` -- this URL can 404
    for a time after a fresh vendor. render() below therefore emits this ONLY
    as a labeled, best-effort archival pointer, never as the sole provenance
    record; the URL actually fetched (SOURCE_URL) plus the Version/Date
    lines are what a future maintainer can rely on."""
    m = re.search(r"(\d+\.\d+\.\d+)", version_line)
    if not m:
        return SOURCE_URL
    return f"https://www.unicode.org/Public/security/{m.group(1)}/confusables.txt"


def parse(text):
    """{confusable_char: target_char} for every confusables.txt entry whose
    SOURCE is a single codepoint and whose TARGET is a single codepoint that
    lands in TARGET_ALPHABET, case-insensitively (round-2 quality-gate F3 --
    the target is kept in Unicode's own documented case, e.g. small-capital
    S maps to lowercase 's', not forced to uppercase; Task 3's keyword/value
    search is what's made case-tolerant, not this table). Multi-codepoint
    targets are excluded by construction (see design doc "Known residue"
    point 2). This does lose SOME table entries: measured against the
    committed 6565-parseable-entry snapshot (round-11 quality-gate
    SIGNIFICANT 3), 41 entries have a multi-codepoint target drawn
    entirely from this alphabet (case-insensitively) -- e.g. U+00E6 `æ`
    -> `ae`, U+0153 `œ` -> `oe`, U+2116 `№` -> `No`, U+A733 `ꜳ` -> `aa`,
    plus 13 mathematical small-m variants -> `rn`. None of the 41 targets
    is a single keyword letter, and losing them loses no detection, only
    resolution: an excluded SOURCE codepoint either NFKD-reduces to
    something the skeleton loop's first branch already keeps (kept
    anyway), or drops to a WILDCARD token the composition guard's
    reachability check still catches (see Task 3's docstring).

    ROUND-3 CORRECTION (quality-gate F2): `tgt_char.lower() not in
    TARGET_ALPHABET_LOWER` does NOT close every case-variant gap the round-2
    F3 fix set out to close -- it only helps when Python's own `.lower()`
    maps the target to an ASCII letter. Seven Unicode-documented prototype
    codepoints relevant to this alphabet are themselves "LATIN LETTER SMALL
    CAPITAL <X>" characters for X in {A, B, D, E, N, P, R} (U+1D00, U+0299,
    U+1D05, U+1D07, U+0274, U+1D18, U+0280) -- Python's `str.lower()` is a
    no-op on each of them (`chr(0x1D18).lower() == chr(0x1D18)`, not `'p'`),
    so this filter silently drops every entry whose confusables.txt TARGET
    is one of these seven, even though NFKD does not decompose them either
    (they are prototypes, not compatibility variants of anything). See the
    Task 3 docstring's "Known residue" paragraph for the full, measured
    accounting of this class.

    ROUND-4 ADDITION (quality-gate S2): every SOURCE character is required
    to be non-ASCII, excluded by construction rather than relying on
    `_legacy_supersedes_claim`'s own skeleton loop happening to test
    `[A-Za-z0-9:]` before the `CONFUSABLE_MAP` lookup runs. Measured: the
    table already contained exactly one ASCII key before this exclusion
    (`'0' -> 'O'`, U+0030 -> U+004F) — inert only because of that loop
    ordering, not because of anything this function guaranteed. An ASCII
    key would silently change how a plain-ASCII receipt skeletonizes if a
    future re-vendor ever depended on loop order instead of this filter."""
    mapping = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split(";")
        if len(fields) < 2:
            continue
        src_hex = fields[0].strip()
        tgt_tokens = fields[1].strip().split()
        if not re.fullmatch(r"[0-9A-Fa-f]+", src_hex) or len(tgt_tokens) != 1:
            continue
        try:
            src_char = chr(int(src_hex, 16))
            tgt_char = chr(int(tgt_tokens[0], 16))
        except ValueError:
            continue
        # round-4 quality-gate S2: every ASCII character in [A-Za-z0-9:] is
        # kept verbatim by the skeleton step BEFORE the CONFUSABLE_MAP lookup
        # runs, and no ASCII character may be rewritten into the alphabet --
        # an ASCII key would silently change how a plain-ASCII receipt
        # skeletonizes. Excluded by construction, not by loop ordering.
        if ord(src_char) < 128:
            continue
        if tgt_char.lower() not in TARGET_ALPHABET_LOWER or src_char == tgt_char:
            continue
        mapping[src_char] = tgt_char
    return mapping


def render(mapping, version_line, date_line, source_text):
    """Render the block to splice between BEGIN/END markers in
    rcpt_verify.py -- a plain module-level dict literal, no import, no
    logic. version_line/date_line are Unicode's own header lines (S7): a
    stale re-vendor is then a legible diff (URL/version bump), not a silent
    drift with no audit trail.

    round-2 quality-gate S3: the primary provenance line is `# Fetched-from:`
    -- SOURCE_URL, the URL this run ACTUALLY fetched -- never a synthesised
    URL that may not exist; resolved_source_url()'s versioned form is kept
    only as a separate, explicitly-labeled archival pointer.

    round-2 quality-gate F1: each key uses `!a` (`ascii()`), not `!r`
    (`repr()`), for the dict-literal source-side render. `repr()` of a
    non-ASCII character decides whether to escape it via
    `str.isprintable()`, which is answered from the UNICODE DATABASE BUNDLED
    WITH THE RUNNING INTERPRETER -- so two Python versions with different
    bundled UCDs (e.g. CI's pinned 3.12 vs. a contributor's local 3.13/3.14)
    can render the identical `mapping` to different bytes, and
    check_chain1_confusables_drift.py would then report a "drift" that is
    really just an interpreter mismatch, with a misleading remediation
    message. `ascii()` always escapes every non-ASCII codepoint regardless
    of the running interpreter's UCD, so the rendered block -- and therefore
    the drift check -- is interpreter-independent. Do not "simplify" this
    back to `!r`: it looks equivalent on any single interpreter and is not.

    round-3 quality-gate S2: `source_text` (the COMMITTED snapshot's own
    content, not a re-fetch) is hashed into `# Source-sha256:` below, and
    `len(mapping)` into `# Entries:`. Both are then covered by the SAME
    byte-identical drift comparison check_chain1_confusables_drift.py
    already does -- a hand-edited or truncated snapshot (e.g. one missing
    line deleted out of ~10,000) becomes a one-line hash diff instead of an
    invisible change nothing else in this pattern would catch (the drift
    checker's ground truth is otherwise this generator's OWN parse()/
    render(), which cannot independently notice a change to their shared
    input -- see check_chain1_confusables_drift.py's module docstring)."""
    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    lines = [
        BEGIN_MARKER,
        "# Vendored Unicode confusables (UTS #39), restricted to the alphabet a",
        "# `_legacy_supersedes_claim`-shaped claim can legally contain.",
        "# This is a derivative extract of Unicode's confusables.txt, which",
        "# carries its own copyright/terms-of-use -- see the header of the",
        "# committed scripts/chain1_confusables_source.txt for the notice.",
        f"# Fetched-from: {SOURCE_URL}",
        f"# {version_line}",
        f"# {date_line}",
        f"# Source-sha256: {source_sha256}",
        f"# Entries: {len(mapping)}",
        "# Archival-copy (may not exist until Unicode publishes this",  # round-6 M4: no placeholder, no `f` needed
        f"# version's own directory): {resolved_source_url(version_line)}",
        "# Regenerate: python3 scripts/gen_chain1_confusables.py (reads the",
        "# committed scripts/chain1_confusables_source.txt -- run",
        "# '... --vendor' first only to pick up a newer Unicode release).",
        "# DO NOT HAND-EDIT this block.",
        "CONFUSABLE_MAP = {",
    ]
    for src in sorted(mapping, key=lambda c: ord(c)):
        tgt = mapping[src]
        lines.append(f"    {src!a}: {tgt!r},  # U+{ord(src):04X} -> {tgt!r}")
    lines.append("}")
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def splice(rcpt_text, block):
    """Replace the text between BEGIN_MARKER and END_MARKER (inclusive) in
    rcpt_verify.py's source with `block`. Raises if the markers aren't found
    exactly once -- a missing/duplicated marker pair is a hand-edit error,
    not something to silently paper over."""
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)
    matches = pattern.findall(rcpt_text)
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one {BEGIN_MARKER!r}...{END_MARKER!r} block "
            f"in {RCPT_VERIFY}, found {len(matches)}")
    return pattern.sub(lambda _m: block.rstrip("\n"), rcpt_text)


def main():
    if "--vendor" in sys.argv[1:]:
        vendor()
        return
    if not SOURCE_SNAPSHOT.exists():
        raise SystemExit(
            f"{SOURCE_SNAPSHOT} not found -- run with --vendor first to "
            f"fetch and commit an initial snapshot.")
    text = SOURCE_SNAPSHOT.read_text(encoding="utf-8")
    mapping = parse(text)
    version_line, date_line = source_header(text)
    block = render(mapping, version_line, date_line, text)
    rcpt_text = RCPT_VERIFY.read_text(encoding="utf-8")
    # round-3 quality-gate M5: newline="\n" -- see vendor()'s identical note;
    # this write is the more consequential one, since it rewrites the WHOLE
    # of rcpt_verify.py, not just the standalone snapshot.
    RCPT_VERIFY.write_text(splice(rcpt_text, block), encoding="utf-8", newline="\n")
    # round-3 quality-gate M4: "N entries", not a hardcoded count -- see the
    # generated block's own "# Entries:" line for what this run produced;
    # this print is a progress message, not a provenance record.
    print(f"spliced {len(mapping)} entries into {RCPT_VERIFY}", file=sys.stderr)


if __name__ == "__main__":
    main()
