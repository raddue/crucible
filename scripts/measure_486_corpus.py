#!/usr/bin/env python3
"""#486 Task 18 — the corpus measurement that discharges criteria 1, 12 and 13.

Runs the three enumerated frozen corpora through the SHIPPED `rcpt_verify` functions —
`resolve_base`, `parse_receipt`, `parse_artifacts`, `parse_trace`, `parse_witness`,
`witness_art_name`, `tier2_artifacts`, `tier2_witness` and the `_Coverage` collector —
and publishes the four census counters per leg, the criterion-1 name census and
criterion 13's entry-level resolution ratio.

A SIBLING of `scripts/measure_474_corpus.py`, not an extension (#486 plan, round-2/S6).
That script's output shape is per-RECEIPT disposition *flips* between a baseline linter
and this tree; this one's is per-ENTRY dispositions and counters over a probe set, per
leg. Folding them together would mean a second output mode and a second corpus
definition inside a script whose whole contract is one comparison. What IS reused is its
discipline, deliberately: an enumerated corpus (never a bare glob), the size asserted,
each receipt measured twice (as-returned + PASS-leg synthetic), shipped functions only.

**Why a script and not the CLI's stderr** (D8.2 sub-decision 6). A Tier-2 `LintError`
truncates the walk on exactly the receipts with the most to hide, so summing CLI census
lines understates the residual in the direction that makes the floor look shippable.
Every leg here runs independently, and the ARTIFACTS leg is driven ONE ENTRY AT A TIME
through `tier2_artifacts` with a fresh `_Coverage` per entry — `tier2_artifacts` raises
on the first mismatching entry and abandons the rest of that receipt's entries mid-loop,
and 8/29 `live29` and 5/22 `codegate22` receipts carry such a mismatch.

**Every ARTIFACTS-leg bucket is sourced from the shipped function.** `is_path_shaped`,
the 12-hex `receipt-hash-prefix` branch, the `art_verified` numerator rule and the
ambiguity bump are NOT re-derived here: a hand-written mirror is a drift surface with
nothing checking it, in the script that exists to corroborate the instrument.

**A `WitnessTimeout` is a named skip with a stop, never a disposition** (round-4/SIG-3).
It is a `LintError` SUBCLASS since Task 9, so `except rv.WitnessTimeout` must precede
every `except rv.LintError` — copied verbatim from `measure_474_corpus.py:60`, a bare
`except rv.LintError` converts a timeout into a disposition indistinguishable from a
real lint failure, inside the sole discharge for criteria 1, 12 and 13.

⚠ REACHABILITY, STATED HONESTLY (round-1/C3-R1-S4). The watchdog is armed at exactly
ONE place in the linter — `_witness_bound()`, called only from `tier2_witness` — so
`WitnessTimeout` is reachable HERE only from the `tier2_witness` arm, and only that arm
is pinned by `test_measure_486.py`. The arms on `lint_receipt`, on the section parses,
on `tier2_artifacts` and in `witness_name` are uniform-by-policy, NOT load-bearing
today: `_compile_guard`/`_reject_unsatisfiable` are static analyses, and the ARTIFACTS
leg is documented in `rcpt_verify.py` as running OUTSIDE `_witness_bound()` with no
timeout of any kind. They are kept because the moment a bound IS armed on the ARTIFACTS
leg they become live, and a missing arm there would swallow a timeout into a
disposition. Do not read a `# MUST precede` comment as "a test covers this site".

NOT a CI gate, and NOTHING ELSE IN #486 GATES THESE FIGURES EITHER. The corpora are
machine-local and gitignored, so this script SKIPs or stops on any machine that does not
hold them; its true #474 analogue is `measure_474_corpus.py`, which is machine-local and
ungated for the same reason. #474 also ships a SECOND, gated half —
`scripts/measure_474_denominators.py`, on `run_tests.sh:56` — which re-derives from
COMMITTED files every figure its plan quotes, "so a figure that rots fails CI instead of
aging quietly inside a document". **#486 ships no such whole-figure checker**: the
published corpus figures (`0/14 → 12/14`, `0/89 → 88/89`, `ambiguous == 0`,
`tier1-rejects 1`, `5/89 in 5/22`, `88/88`) are reproducible on demand by running this
script, but they are NOT CI-pinned. What IS gated by `scripts/run_tests.sh` is
`scripts/test_measure_486.py` — this script's behaviour on a corpus that has gone wrong
(synthetic corpora in a tempdir), plus the committed-file half that CAN be gated: the
six `two-root-*` fixture rows and `_MULTI_ROOT_FIXTURE_IDS`
(`TestCommittedFiguresAreGated` there). Read a corpus figure quoted in prose as
reproducible, never as CI-defended.

Usage:
  measure_486_corpus.py --corpus {corpus17,live29,codegate22} --expect-size N
                        [--no-strict] [--keep-flat]

Exit: 0 clean · 1 stop-and-declare (corpus drift, a witness timeout, a broken
reconstruction) · 2 usage.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home()
MEM = HOME / ".claude/projects/-mnt-coding-Coding-crucible/memory/quality-gate"
EV486 = MEM / "evidence-486-tier2-resolution"
EV474 = MEM / "evidence-474-tier2-resolution"
FROZEN = EV486 / "frozen-corpora"

# ── The three corpora, ENUMERATED (rule 1). A bare glob is what lets a corpus grow or
#    shrink under a figure; these lists are the corpus definition, and the on-disk glob
#    is compared against them below rather than trusted.
CORPUS17_NAMES = [
    "rcpt-2-asreturned.txt", "rcpt-3-asreturned.txt", "rcpt-4-asreturned.txt",
    "rcpt-5-asreturned.txt", "rcpt-6-asreturned.txt", "rcpt-7-asreturned.txt",
    "rcpt-8-asreturned.txt", "rcpt-9-asreturned.txt", "rcpt-10-asreturned.txt",
    "rcpt-11-asreturned.txt", "rcpt-12-asreturned.txt", "rcpt-13-asreturned.txt",
    "rcpt-16-asreturned.txt", "rcpt-17-asreturned.txt", "rcpt-18-asreturned.txt",
    "rcpt-19-asreturned.txt", "rcpt-25-asreturned.txt",
]
LIVE29_NAMES = [f"rcpt-{i}-asreturned.txt" for i in range(1, 30)]
CODEGATE22_NAMES = [
    "r1/rcpt-1-asreturned.txt", "r1/rcpt-2-asreturned.txt", "r1/rcpt-3-asreturned.txt",
    "r2/rcpt-4-asreturned.txt", "r2/rcpt-5-asreturned.txt", "r2/rcpt-6-asreturned.txt",
    "r3/rcpt-7-asreturned.txt", "r3/rcpt-8-asreturned.txt", "r3/rcpt-9-asreturned.txt",
    "r3/probe/fakecorpus/rcpt-99-asreturned.txt",
    "r4/rcpt-10-asreturned.txt", "r4/rcpt-11-asreturned.txt", "r4/rcpt-12-asreturned.txt",
    "r5/rcpt-13-asreturned.txt", "r5/rcpt-14-asreturned.txt", "r5/rcpt-15-asreturned.txt",
    "r5/rcpt-16-asreturned.txt", "r5/rcpt-17-asreturned.txt",
    "r6/rcpt-18-asreturned.txt", "r6/rcpt-19-asreturned.txt", "r6/rcpt-20-asreturned.txt",
    "r7/rcpt-21-asreturned.txt",
]

RECEIPT_GLOB = "rcpt-*-asreturned.txt"


class Corpus:
    """One enumerated corpus plus the two root sets it is measured under.

    `roots` is built lazily because `codegate22`'s post-fix root set is a RECONSTRUCTION
    (a flat temp tree), not a directory that exists on disk.
    """

    def __init__(self, label, directory, names, definition, build_roots, recursive=False):
        self.label = label
        self.dir = directory
        self.names = names
        self.definition = definition
        self.build_roots = build_roots
        self.recursive = recursive
        # round-1/C3-R1-F1 — the count the figures BELOW the current point were actually
        # computed over. `n=` is the enumeration and is a constant; this one moves when a
        # receipt is skipped, and `fig` stamps BOTH so a figure lifted into prose cannot
        # silently carry a denominator it was not computed over.
        self.computed_over = None


def _corpus17_roots():
    """Criterion 1's two roots, stated in full by the plan so they are not inferred.

    Root 1 is the corpus's OWN dispatch directory — the original path, not the frozen
    integrity copy (Task 4 Step 2b: "Task 18 keeps measuring the original path").
    Root 2 is the paired quality-gate SCRATCH directory, i.e. the run's findings root;
    the frozen copy is the only surviving instance of it, because the live scratch dir
    is long past quality-gate/SKILL.md:911's 2-hour stale cleanup.
    """
    r1 = EV474 / "corpus-2026-08-01"
    r2 = FROZEN / "scratch-2026-08-01T21-18-18"
    return [r1, r2], [r1], []


def _live29_roots():
    da = FROZEN / "crucible-dispatch-1786146169"
    sa = FROZEN / "scratch-2026-08-07T23-42-25"
    return [da, sa], [da], []


def _codegate22_roots():
    """Criterion 13's configuration: the PINNED FLAT SINGLE-HOME layout, two roots.

    The frozen corpus is NOT in that layout (receipts nest in `r*/`), so the layout is
    reconstructed here exactly as `gate-evidence/fix-3-measure.py` PART 2 built it —
    transcribed into the plan so it does not depend on that file surviving:

      1. copy every top-level file of the frozen dispatch root into a fresh temp dir;
      2. flatten `r1`..`r7` in sorted order, SKIPPING any basename already present
         (6 skips, all `r{2..7}/artifact-under-review.diff` — the collisions a real flat
         layout renames; dropping rather than renaming is what produces the 5th hash
         mismatch, and modelling it any other way is a DIFFERENT configuration);
      3. apply D1.1 clause 2 — delete every basename that also sits at the top level of
         the findings root (5 deletions). This step is what `ambiguous == 0` measures;
      4. measure with roots = [flat temp root, findings root]. The CORPUS is unchanged —
         still the 22 receipts read from the ORIGINAL frozen dispatch root.
    """
    db = FROZEN / "crucible-dispatch-1786228538"
    sb = FROZEN / "scratch-2026-08-08T22-34-51"
    flat = pathlib.Path(tempfile.mkdtemp(prefix="measure486-flat-"))
    notes = []
    for p in sorted(db.iterdir()):
        if p.is_file():
            shutil.copy2(p, flat / p.name)
    rounds = sorted(p for p in db.glob("r[0-9]") if p.is_dir())
    skipped = []
    for d in rounds:
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            if (flat / p.name).exists():
                skipped.append(f"{d.name}/{p.name}")
                continue
            shutil.copy2(p, flat / p.name)
    findings_top = {p.name for p in sb.iterdir() if p.is_file()}
    removed = []
    for p in sorted(flat.iterdir()):
        if p.is_file() and p.name in findings_top:
            removed.append(p.name)
            p.unlink()
    n_files = len(list(flat.iterdir()))
    notes.append(f"run-C reconstruction: round subdirs {len(rounds)} (expect 7); "
                 f"flat root {n_files + len(removed)} files before clause 2 (expect 143)")
    notes.append(f"  step 2 collisions skipped: {len(skipped)} (expect 6) {sorted(skipped)}")
    notes.append(f"  step 3 clause-2 deletions: {len(removed)} (expect 5) {sorted(removed)}")
    notes.append(f"  flat root as measured: {n_files} files")
    ok = (len(rounds) == 7 and n_files + len(removed) == 143
          and len(skipped) == 6 and len(removed) == 5)
    if not ok:
        notes.append("  STOP: the run-C reconstruction does not match the pinned shape — "
                     "a figure from it is a DIFFERENT configuration, not a disagreement")
    return [flat, sb], [db], notes if ok else notes + ["__STOP__"]


CORPORA = {
    "corpus17": Corpus(
        "corpus17", EV474 / "corpus-2026-08-01", CORPUS17_NAMES,
        "17 enumerated as-returned receipts of the #474 corpus dispatch dir "
        "(evidence-474-tier2-resolution/corpus-2026-08-01)",
        _corpus17_roots),
    "live29": Corpus(
        "live29", FROZEN / "crucible-dispatch-1786146169", LIVE29_NAMES,
        "29 top-level as-returned receipts of the plan gate's frozen dispatch root",
        _live29_roots),
    "codegate22": Corpus(
        "codegate22", FROZEN / "crucible-dispatch-1786228538", CODEGATE22_NAMES,
        "22 as-returned receipts read recursively from the code gate's frozen dispatch "
        "root (incl. r3/probe/fakecorpus/rcpt-99)",
        _codegate22_roots, recursive=True),
}


def load_rcpt_verify():
    spec = importlib.util.spec_from_file_location("rv_measure486", HERE / "rcpt_verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pass_leg_synthetic(text):
    """Only the VERDICT token flipped — body, WITNESS, pattern, ARTIFACTS and TRACE stay
    real. None when the receipt is already PASS. (`measure_474_corpus.py:82-88`.)"""
    m = re.search(r"^VERDICT  (FAIL|BLOCKED)  ", text, re.M)
    if not m:
        return None
    return text[:m.start(1)] + "PASS" + text[m.end(1):]


class Skip(Exception):
    """A named skip: the receipt could not be measured. Carries its reason."""

    def __init__(self, reason, stop=False):
        super().__init__(reason)
        self.reason = reason
        self.stop = stop


class ReceiptResult:
    def __init__(self):
        self.tier1_reject = False
        self.tier1_msg = ""
        self.entries = []        # [(name, resolved, mismatch, blocked_msg)]
        self.art_covs = []       # one _Coverage per ARTIFACTS entry
        self.wit_cov = None
        self.wit_disposition = "not-entered"
        self.partial = False


def _cache_for(rv, artifacts, trace, witness, verdict, root):
    cache = {}
    rv._build_identity_cache(artifacts, trace,
                             [witness] if witness is not None else [],
                             verdict, root, cache)
    return cache


def measure_receipt(rv, text, roots, strict):
    """One receipt, one pass, both legs, run INDEPENDENTLY — never stopping at the first
    LintError. Raises Skip (never a traceback) on anything that makes the receipt
    unmeasurable."""
    res = ReceiptResult()
    # ORDER IS LOAD-BEARING — `lint_receipt` FIRST, exactly as `_verify_single:2028`
    # runs it. Several Tier-1 rules live inside `parse_witness`/`parse_artifacts`, so a
    # script that parses the sections first attributes a TIER-1 REJECTION to
    # "unparseable" and drops the receipt: on `codegate22` that silently converts the
    # pinned `tier1-rejects 1` into 0 and criterion 13's `88/89` into `88/88` — the
    # rcpt-99 confusion the plan's round-3/SIG-4 note exists to keep out of the figures.
    #
    # Tier-1 is a RECEIPT-level fact: a rejected receipt contributes to NO census
    # counter (D8.2 sub-decision 6 — reported as unmeasured, never as a zero). Its
    # ARTIFACTS entries still enter the corpus-side entry enumeration criterion 13's
    # ratio is stated over; those are two different units, and the plan says so.
    try:
        verdict = rv.lint_receipt(text)
    except rv.WitnessTimeout as e:                # MUST precede `except rv.LintError`
        # UNREACHABLE TODAY, uniform by policy — `lint_receipt` reaches only the static
        # analyses, never `_witness_bound()`. See the module docstring's reachability
        # paragraph; the pinned arm is the `tier2_witness` one below (C3-R1-S4).
        raise Skip(f"witness-timeout: {e}", stop=True)
    except rv.LintError as e:
        res.tier1_reject = True
        res.tier1_msg = str(e)
        verdict = None
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise Skip(f"{type(e).__name__}: {e}")

    try:
        sections = rv.parse_receipt(text)
        artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        trace = rv.parse_trace(sections["TRACE"])
    except rv.WitnessTimeout as e:                # MUST precede `except rv.LintError`
        # UNREACHABLE TODAY, uniform by policy — the section parses are static.
        raise Skip(f"witness-timeout: {e}", stop=True)
    except rv.LintError as e:
        # Reachable only on a Tier-1-rejected receipt whose ARTIFACTS/TRACE are
        # themselves unreadable; nothing about it is measurable, so it is a named skip.
        raise Skip(f"unparseable: {e}")
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise Skip(f"{type(e).__name__}: {e}")
    witness = None
    if verdict is not None:
        witness = rv.parse_witness(sections["WITNESS"])

    # ── ARTIFACTS leg, ONE ENTRY AT A TIME (rule 8). A per-receipt call would abandon
    #    every later entry of a receipt whose first entry mismatches — silently, and in
    #    the direction that makes the residual look smaller.
    #    FATAL-8-1(c) — ONE cache per receipt, built from the receipt's FULL artifacts
    #    dict BEFORE the per-entry loop, and ONE verified dict shared across every
    #    tier2_artifacts call and the subsequent tier2_witness call.
    cache = _cache_for(rv, artifacts, trace, witness, verdict, roots)
    verified = {}
    for name, meta in artifacts.items():
        cov = rv._Coverage()
        cov.tier1_ok()
        blocked = ""
        try:
            rv.tier2_artifacts({name: meta}, trace, roots, strict, cov,
                               cache=cache, verified=verified)
        except rv.WitnessTimeout as e:            # MUST precede `except rv.LintError`
            # UNREACHABLE TODAY, uniform by policy — the ARTIFACTS leg runs OUTSIDE
            # `_witness_bound()` and has no timeout of any kind. THIS is the arm that
            # goes live the moment a bound is armed there, and it is the reason the
            # policy is uniform rather than pinned-only (C3-R1-S4).
            raise Skip(f"witness-timeout: {e}", stop=True)
        except rv.LintError as e:
            blocked = str(e)
        res.art_covs.append(cov)
        res.partial = res.partial or cov.partial
        res.entries.append((name, cov.art_verified == 1,
                            "sha256 mismatch" in blocked, blocked))
    # SIG-13-3 — finalize probe (2)'s degenerate-collision disambiguation ONCE, after the
    # per-entry loop completes; never per entry, never inside the loop.
    rv._finalize_identity_degenerate(cache, verified)

    # ── witness leg, verdict-gated exactly as `_verify_single` gates it.
    if verdict in {"PASS", "FAIL"}:
        cov = rv._Coverage()
        cov.tier1_ok()
        try:
            notes = rv.tier2_witness(witness, trace, roots, strict, verdict, cov,
                                     cache=cache, verified=verified)
            res.wit_disposition = ("unverifiable"
                                   if any(n.startswith("UNVERIFIABLE") for n in notes)
                                   else "clean")
        except rv.WitnessTimeout as e:            # MUST precede `except rv.LintError`
            # THE ONE REACHABLE ARM, and the one `test_measure_486.py` pins: the watchdog
            # is armed inside `tier2_witness` only (C3-R1-S4).
            raise Skip(f"witness-timeout: {e}", stop=True)
        except rv.LintError as e:
            res.wit_disposition = f"raise: {e}"
        res.wit_cov = cov
        res.partial = res.partial or cov.partial
    elif verdict is not None:
        res.wit_disposition = "not-entered (verdict not PASS/FAIL)"
    return res


def witness_name(rv, text):
    """The witness artifact NAME via the shipped `witness_art_name` — criterion 1's name
    corpus. Returns (name|None, note); never raises."""
    try:
        verdict = rv.lint_receipt(text)
    except rv.WitnessTimeout as e:
        return None, f"ERR witness-timeout: {e}"
    except rv.LintError as e:
        return None, f"ERR {e}"
    try:
        sections = rv.parse_receipt(text)
        trace = rv.parse_trace(sections["TRACE"])
        witness = rv.parse_witness(sections["WITNESS"])
        if not witness["ran"].startswith("TRACE#"):
            return None, "no-art (ran= is not a TRACE citation)"
        idx = rv._trace_idx(witness["ran"])
        if not 1 <= idx <= len(trace):
            return None, "no-art (ran= does not resolve)"
        art, _from_payload = rv.witness_art_name(witness, trace[idx - 1], verdict)
        if art is None:
            return None, f"no-art (verdict={verdict})"
        return art, ""
    except rv.WitnessTimeout as e:            # MUST precede `except rv.LintError`
        # round-1/C3-R1-S4 — this arm was MISSING while the first try-block of the same
        # function ordered the two correctly, so a timeout here would be swallowed into
        # the generic `ERR` note: the name silently drops out of criterion 1's `names`
        # denominator and `12/14` becomes `12/13` with no stop and exit 0. Unreachable
        # today for the same reason the other uniform arms are (see the module
        # docstring's reachability paragraph); it is here so the leg that computes the
        # denominator is not the one place the rule is not applied.
        return None, f"ERR witness-timeout: {e}"
    except rv.LintError as e:
        return None, f"ERR {e}"


class Census:
    """Aggregated counters for one pass. Four counters PER LEG and summed (rule 6)."""

    def __init__(self, rv):
        self.rv = rv
        self.art = {k: 0 for k in rv._COV_COUNTERS}
        self.wit = {k: 0 for k in rv._COV_COUNTERS}
        self.art_codes = {k: set() for k in rv._COV_COUNTERS}
        self.wit_codes = {k: set() for k in rv._COV_COUNTERS}
        self.art_verified = self.art_applicable = 0
        self.wit_verified = self.wit_applicable = 0
        self.partial_runs = 0
        self.tier1_rejects = 0

    def add(self, res):
        """Counters take only Tier-1-clean receipts (D8.2 sub-decision 6)."""
        if res.partial:
            self.partial_runs += 1
        if res.tier1_reject:
            self.tier1_rejects += 1
            return
        for cov in res.art_covs:
            for k in self.art:
                self.art[k] += cov.counts[k]
                self.art_codes[k] |= cov.codes[k]
            self.art_verified += cov.art_verified
            self.art_applicable += cov.art_applicable
        if res.wit_cov is not None:
            for k in self.wit:
                self.wit[k] += res.wit_cov.counts[k]
                self.wit_codes[k] |= res.wit_cov.codes[k]
            self.wit_verified += res.wit_cov.wit_verified
            self.wit_applicable += res.wit_cov.wit_applicable


def run_pass(rv, corpus, files, roots, strict, label):
    """Measure every receipt of one pass. Returns (census, results, skips)."""
    census = Census(rv)
    results, skips = [], []
    for rel, path in files:
        try:
            text = path.read_text()
            body = text if label == "as-returned" else pass_leg_synthetic(text)
            if body is None:                     # already PASS — rule 3 has no 2nd leg
                continue
            res = measure_receipt(rv, body, roots, strict)
        except Skip as s:
            skips.append((rel, s.reason, s.stop))
            continue
        except (OSError, UnicodeDecodeError, ValueError) as e:
            skips.append((rel, f"{type(e).__name__}: {e}", False))
            continue
        results.append((rel, res))
        census.add(res)
    return census, results, skips


def fig(corpus, pass_, label, value, leg=None, roots=None, note="", over=None):
    """Rule (2): the corpus size and definition token, the pass and the leg travel with
    EVERY figure. A figure without a pass label is not comparable to the plan's table.

    round-1/C3-R1-F1 — `n=` alone is NOT enough, because it is the ENUMERATION and is a
    hard-coded constant: a run that lost six receipts to skips still stamped `n=29` on
    every row. `computed-over=` is the number of corpus members this figure's pass
    actually measured, so the two disagree loudly exactly when the denominator moved.
    `over=` overrides it for a figure computed over a different pass than the block it
    is printed in (criterion 13's one-root baseline)."""
    n_over = corpus.computed_over if over is None else over
    bits = [f"corpus={corpus.label}", f"n={len(corpus.names)}",
            f"computed-over={'?' if n_over is None else n_over}", f"pass={pass_}"]
    if leg:
        bits.append(f"leg={leg}")
    if roots is not None:
        bits.append(f"roots={roots}")
    print(f"  {label:<46s} {value:<28s} [{' '.join(bits)}]" + (f"  {note}" if note else ""))


def print_counters(corpus, pass_, census, roots_n):
    for k in census.rv._COV_COUNTERS:
        a, w = census.art[k], census.wit[k]
        codes = sorted(census.art_codes[k] | census.wit_codes[k])
        note = f"codes: {','.join(codes)}" if codes else ""
        fig(corpus, pass_, k, f"artifacts-leg {a}  witness-leg {w}  total {a + w}",
            leg="both", roots=roots_n, note=note)


def probe_set(rv, roots):
    """Rule (5): print the measured PROBE SET, not just the root set. `ambiguous == 0` is
    a property of {root, git-toplevel(root)} per root, so a figure reported without the
    toplevels does not say which environment it was measured in. A non-`None` toplevel
    where the design's tables recorded `None` means two different candidate spaces are
    being compared — stop and declare it."""
    rows = []
    for r in roots:
        top = rv._git_toplevel(pathlib.Path(r))
        rows.append((str(r), str(top) if top else "None"))
    return rows


def main(argv):
    args = {"corpus": None, "expect-size": None}
    strict, keep_flat = True, False
    it = iter(argv)
    for a in it:
        if a == "--no-strict":
            strict = False
        elif a == "--keep-flat":
            keep_flat = True
        elif a.startswith("--") and a[2:] in args:
            args[a[2:]] = next(it, None)
        else:
            sys.stderr.write(f"unknown argument {a!r}\n{__doc__}")
            return 2
    if not args["corpus"] or args["expect-size"] is None:
        sys.stderr.write(__doc__)
        return 2
    if args["corpus"] not in CORPORA:
        sys.stderr.write(f"unknown corpus {args['corpus']!r}; "
                         f"known: {', '.join(sorted(CORPORA))}\n")
        return 2
    corpus = CORPORA[args["corpus"]]
    try:
        expect = int(args["expect-size"])
    except (TypeError, ValueError):
        sys.stderr.write(f"--expect-size must be an integer, got {args['expect-size']!r}\n")
        return 2

    rv = load_rcpt_verify()
    stop = False

    print(f"### measure_486_corpus — corpus {corpus.label}, strict={strict}")
    print(f"    definition : {corpus.definition}")
    print(f"    enumerated : {len(corpus.names)} receipts (rule 1 — an enumerated list, "
          f"never a bare glob)")
    print(f"    directory  : {corpus.dir}")

    # ── rule (4): fail loudly rather than report against a silently-changed denominator.
    if len(corpus.names) != expect:
        print(f"    STOP: enumeration is {len(corpus.names)}, --expect-size {expect} — "
              f"the corpus definition and the pinned expectation disagree")
        return 1
    if not corpus.dir.is_dir():
        # The denominator identity `measured + skipped == receipts` holds HERE too: the
        # corpus is still its enumeration, every entry of it is skipped. Reporting
        # `receipts=0` instead would state the absent corpus as an empty one, which is
        # the silent-denominator-shrink this script's rule (4) exists to refuse.
        print(f"    SKIP: corpus directory absent (machine-local, gitignored) — "
              f"receipts={len(corpus.names)} measured=0 skipped={len(corpus.names)}")
        return 1
    on_disk = sorted(str(p.relative_to(corpus.dir)) for p in (
        corpus.dir.rglob(RECEIPT_GLOB) if corpus.recursive else corpus.dir.glob(RECEIPT_GLOB)))
    extra = sorted(set(on_disk) - set(corpus.names))
    if extra:
        print(f"    STOP: {len(extra)} receipt(s) on disk are outside the enumeration — "
              f"the corpus moved: {extra}")
        return 1
    # round-1/C3-R1-F1 — the SHRINK direction, which `--expect-size` structurally cannot
    # see: it compares `len(corpus.names)` against a CLI integer, i.e. one hard-coded
    # constant against another, and never touches the disk. Without this, a member that
    # has vanished falls through to `path.read_text()`, becomes an ordinary skip, and the
    # run publishes a full set of figures at `### done` / exit 0 — the paradigm case of
    # the "silently-changed denominator" rule (4) exists to refuse, and the ONLY drift
    # class the absent-DIRECTORY guard above (which is loud, and exit 1) does not cover.
    # `corpus17` in particular has no integrity manifest at all: it deliberately measures
    # the original unfrozen path, which `SHA256SUMS-frozen.txt` does not cover.
    missing = sorted(set(corpus.names) - set(on_disk))
    if missing:
        print(f"    STOP: {len(missing)} enumerated receipt(s) are absent from disk — "
              f"the corpus shrank: {missing}")
        return 1

    roots, roots_one, notes = corpus.build_roots()
    for n in notes:
        if n == "__STOP__":
            stop = True
        else:
            print(f"    {n}")
    if stop:
        return 1

    print(f"    PROBE SET (rule 5 — root, and _git_toplevel(root), `None` printed as None):")
    for r, top in probe_set(rv, roots):
        print(f"      root     {r}\n        toplevel {top}")
    print(f"    one-root reference set (the mandated single `--root`, today's code):")
    for r, top in probe_set(rv, roots_one):
        print(f"      root     {r}\n        toplevel {top}")

    files = [(rel, corpus.dir / rel) for rel in corpus.names]

    # ══ pass 1: as-returned — the pass EVERY counter row is stated over.
    print(f"\n── pass=as-returned  ({len(roots)} roots)")
    cen, results, skips = run_pass(rv, corpus, files, roots, strict, "as-returned")
    measured = len(results)
    corpus.computed_over = measured        # C3-R1-F1 — every fig below this line
    for rel, reason, is_stop in skips:
        print(f"  SKIPPED  {rel}: {reason}")
        stop = stop or is_stop
    fig(corpus, "as-returned", "denominator",
        f"receipts={len(corpus.names)} measured={measured} skipped={len(skips)}",
        roots=len(roots),
        note=("(of which tier1-rejected {}) OK".format(cen.tier1_rejects)
              if measured + len(skips) == len(corpus.names) else "ACCOUNTING BROKEN"))
    fig(corpus, "as-returned", "artifacts verified/applicable",
        f"{cen.art_verified}/{cen.art_applicable}", leg="artifacts", roots=len(roots))
    fig(corpus, "as-returned", "witness verified/applicable",
        f"{cen.wit_verified}/{cen.wit_applicable}", leg="witness", roots=len(roots))
    print_counters(corpus, "as-returned", cen, len(roots))
    fig(corpus, "as-returned", "partial-runs", str(cen.partial_runs), roots=len(roots))
    fig(corpus, "as-returned", "tier1-rejects", str(cen.tier1_rejects), roots=len(roots),
        note="contributes to NO counter — unmeasured, never a zero (D8.2 sub-decision 6)")
    for rel, res in results:
        if res.tier1_reject:
            print(f"    tier1-reject  {rel}: {res.tier1_msg}")
            # RECONCILIATION, printed rather than folded in (D8.2 sub-decision 6 + the
            # plan's rcpt-99 note). A Tier-1-rejected receipt is rejected before EITHER
            # leg, so its entries contribute to no counter — but a design-time script
            # that measured resolution per entry WITHOUT the Tier-1 gate did bucket
            # them, which is where design :1316's `NOT-REACHABLE 1` on `codegate22`
            # comes from against a shipped-instrument reading of 0. Both are correct on
            # their own unit; printing the entries is what makes the difference
            # diagnosable instead of a manufactured criterion-2 event.
            for name, resolved, _mis, _msg in res.entries:
                if resolved:
                    continue
                bucket = ("unreached" if rv.is_path_shaped(name)
                          else "not-reachable (unresolvable-basename)")
                print(f"      unmeasured entry  {name}  -> would bucket {bucket} "
                      f"(NOT counted above)")

    # ── the ADVISORY/EXACT rule, printed where it is read (round-5/FATAL-1).
    a_sum = cen.art["unreached"] + cen.art["not-reachable"] + cen.art["not-applicable"]
    fig(corpus, "as-returned", "unreached+not-reachable+not-applicable",
        str(a_sum), leg="artifacts", roots=len(roots),
        note="the SUM is exact; the unreached/not-reachable SPLIT is advisory "
             "(syntactic instrument vs the design's tree-walk one)")
    # GH #501 — `discarded` joins the witness sum. Without it this figure would have
    # silently DROPPED by the size of the fail-leg population the fix re-bucketed
    # (8 receipts over the three enumerated corpora, re-derived by reverting the
    # withholding on a copy of the tree): those items moved out of `unreached` and
    # into `discarded`, and they are non-verifications either way, so leaving them out
    # would report the corpus as having got better by exactly the number of receipts
    # whose disposition was only re-described. `not-applicable` is still omitted here —
    # that is GH #507's subject and is deliberately not changed under this fix.
    w_sum = cen.wit["unreached"] + cen.wit["not-reachable"] + cen.wit["discarded"]
    fig(corpus, "as-returned", "unresolved across BOTH legs",
        f"{a_sum} + {w_sum} = {a_sum + w_sum}",
        leg="both", roots=len(roots),
        note="artifacts-leg unresolved (incl. not-applicable) + witness-leg "
             "(unreached+not-reachable+discarded). SUMS ONLY — no per-counter total is "
             "pinned, because the two legs' design-side references are different "
             "instruments")

    # ── witness-leg dispositions, the shape the design publishes.
    disp = {}
    for _rel, res in results:
        key = res.wit_disposition.split(":")[0]
        disp[key] = disp.get(key, 0) + 1
    fig(corpus, "as-returned", "witness dispositions",
        "  ".join(f"{k}={v}" for k, v in sorted(disp.items())),
        leg="witness", roots=len(roots))
    for rel, res in results:
        if res.wit_disposition.startswith(("raise", "unverifiable")):
            print(f"    witness  {rel}: {res.wit_disposition}")

    # ── criterion 13's ENTRY-LEVEL ratio, both readings (round-3/SIG-4).
    ent_all = [(rel, e) for rel, res in results for e in res.entries]
    ent_t1 = [(rel, e) for rel, res in results if res.tier1_reject for e in res.entries]
    resolved_all = sum(1 for _r, e in ent_all if e[1])
    resolved_ex = sum(1 for _r, e in ent_all if e[1]) - sum(1 for _r, e in ent_t1 if e[1])
    mis_all = [(r, e) for r, e in ent_all if e[2]]
    mis_ex = [(r, e) for r, e in mis_all if r not in {x for x, _ in ent_t1}]
    rc_all = len({r for r, e in mis_all})
    rc_ex = len({r for r, e in mis_ex})
    fig(corpus, "as-returned", "entry resolution (tier1-rejects INCLUDED)",
        f"{resolved_all}/{len(ent_all)}", leg="artifacts", roots=len(roots),
        note="the side §6.0's rule states criterion 13 on")
    fig(corpus, "as-returned", "entry resolution (tier1-rejects EXCLUDED)",
        f"{resolved_ex}/{len(ent_all) - len(ent_t1)}", leg="artifacts", roots=len(roots),
        note="the same measurement stated on the other side — NOT a criterion-2 event")
    fig(corpus, "as-returned", "hash mismatch (included / excluded)",
        f"{len(mis_all)}/{len(ent_all)} in {rc_all}/{measured}  ==  "
        f"{len(mis_ex)}/{len(ent_all) - len(ent_t1)} in {rc_ex}/{measured - cen.tier1_rejects}",
        leg="artifacts", roots=len(roots))
    # ── criterion 13 is stated as a DELTA (`0/89 → 88/89`), and until round-1/C3-R1-S2
    #    this script emitted only the right-hand side: `roots_one` was computed on every
    #    path but used for criterion 1's name leg ONLY, so the sole designated discharge
    #    for criterion 13 reproduced the `88` and not the `0`. Criterion 1 prints both
    #    root-count legs on adjacent lines; this is the same shape for the ARTIFACTS leg.
    #    The two halves ARE measured under different layouts on codegate22 — that is a
    #    material property of the published delta, and rule (5)'s reason for printing
    #    both probe sets is exactly that a figure must say which environment produced it.
    _cen1, res1, sk1 = run_pass(rv, corpus, files, roots_one, strict, "as-returned")
    for rel, reason, is_stop in sk1:
        print(f"  SKIPPED (one-root baseline)  {rel}: {reason}")
        stop = stop or is_stop
    ent_one = [e for _rel, res in res1 for e in res.entries]
    fig(corpus, "as-returned", "entry resolution, ONE root (baseline)",
        f"{sum(1 for e in ent_one if e[1])}/{len(ent_one)}", leg="artifacts",
        roots=len(roots_one), over=len(res1),
        note="the left-hand side of criterion 13's delta, measured by THIS instrument. "
             "The mandated single `--root`; for codegate22 that is the NESTED frozen "
             "dispatch root, a DIFFERENT LAYOUT from the flat reconstruction the "
             "two-root rows above are measured under — the delta spans both changes")
    for rel, e in mis_all:
        print(f"    mismatch  {rel}  {e[0]}: {e[3]}")
    for rel, e in ent_all:
        if not e[1] and not e[2]:
            print(f"    unresolved  {rel}  {e[0]}")

    # ══ pass 2: PASS-leg synthetic — reported SEPARATELY, never added into the rows
    #    above. It exists so `witness_art_name`'s payload-sourced names enter criterion
    #    1's name corpus (rule 3's own stated reason).
    print(f"\n── pass=PASS-synthetic  (reported separately; NEVER summed into as-returned)")
    cen2, results2, skips2 = run_pass(rv, corpus, files, roots, strict, "PASS-synthetic")
    corpus.computed_over = len(results2)    # C3-R1-F1 — this pass's own denominator
    for rel, reason, is_stop in skips2:
        print(f"  SKIPPED  {rel}: {reason}")
        stop = stop or is_stop
    fig(corpus, "PASS-synthetic", "denominator",
        f"legs={len(results2) + len(skips2)} measured={len(results2)} skipped={len(skips2)}",
        roots=len(roots),
        note="receipts already PASS have no second leg (measure_474_corpus.py:83-88)")
    fig(corpus, "PASS-synthetic", "artifacts verified/applicable",
        f"{cen2.art_verified}/{cen2.art_applicable}", leg="artifacts", roots=len(roots))
    fig(corpus, "PASS-synthetic", "witness verified/applicable",
        f"{cen2.wit_verified}/{cen2.wit_applicable}", leg="witness", roots=len(roots))
    print_counters(corpus, "PASS-synthetic", cen2, len(roots))
    fig(corpus, "PASS-synthetic", "partial-runs", str(cen2.partial_runs), roots=len(roots))
    fig(corpus, "PASS-synthetic", "tier1-rejects", str(cen2.tier1_rejects), roots=len(roots))

    # ══ criterion 1 — the unique WITNESS artifact-name corpus, over the UNION of both
    #    passes. That union is what DEFINES this corpus (design :1484).
    print(f"\n── pass=union  (criterion 1: the unique witness artifact-name corpus)")
    names, per_pass = [], {}
    unread = set()
    for leg in ("as-returned", "PASS-synthetic"):
        rows = []
        for rel, path in files:
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError, ValueError) as e:
                rows.append((rel, None, f"unreadable: {type(e).__name__}"))
                unread.add(rel)
                continue
            body = text if leg == "as-returned" else pass_leg_synthetic(text)
            if body is None:
                continue
            nm, note = witness_name(rv, body)
            rows.append((rel, nm, note))
            if nm is not None and nm not in names:
                names.append(nm)
        per_pass[leg] = rows
    for leg, rows in per_pass.items():
        for rel, nm, note in rows:
            print(f"    {leg:15s} {rel:36s} {nm or note}")
    # C3-R1-F1 — the union leg's own denominator: corpus members whose bytes were read.
    corpus.computed_over = len(corpus.names) - len(unread)
    res_two = [n for n in names if rv.resolve_base(n, roots) is not None]
    res_one = [n for n in names if rv.resolve_base(n, roots_one) is not None]
    fig(corpus, "union", "unique witness names resolved, ONE root",
        f"{len(res_one)}/{len(names)}", roots=len(roots_one),
        note="the mandated single `--root`")
    fig(corpus, "union", "unique witness names resolved, TWO roots",
        f"{len(res_two)}/{len(names)}", roots=len(roots),
        note="criterion 1's configuration")
    residual = [n for n in names if n not in res_two]
    print(f"    residual ({len(residual)}): {sorted(residual)}")

    if keep_flat:
        print(f"\n    --keep-flat: reconstruction left at {roots[0]}")
    elif corpus.label == "codegate22":
        shutil.rmtree(roots[0], ignore_errors=True)

    if stop:
        print("\n### STOP-AND-DECLARE: a witness timeout was hit. The figures above are "
              "NOT publishable with a timed-out receipt in the corpus "
              "(§7 measurement discipline rule 4).")
        return 1
    print("\n### done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
