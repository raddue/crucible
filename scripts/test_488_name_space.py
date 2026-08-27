#!/usr/bin/env python3
"""Acceptance tests for #488 criterion 1 — the receipt name space.

Ruling under test: docs/plans/2026-08-21-488-c1-name-space-reduced.md
("The receipt name space — what a receipt may legally name, and how it resolves").

Run from repo root:  python3 scripts/test_488_name_space.py

These are ACCEPTANCE tests, not unit tests: each one states an observable
behaviour of the ruling as seen from outside `scripts/rcpt_verify.py` — at the
parser boundary (`parse_artifacts` / `parse_trace` / `parse_claims`, which is
where the ruling sites its LEXICAL half) or at the CLI (`--tier2`, which is
where it sites its SEMANTIC half). They were written BEFORE the implementation.

SCOPE — only the criteria §8 marks schedulable today are covered here.
Deliberately NOT tested (each is gated by the design doc's own ordering gates):

  * AC-1 second half   — the `return-convention.md:104`/`:256` retraction is
                         gated on GH #530 (§3.1 clause 2, second ordering gate).
  * AC-3, AC-5         — moved to GH #530 with the census floor (tombstones).
  * AC-4               — the C walk's 42→14 / 96→2 reproduction. C is not built
                         and is #530-gated (OQ-7, §3.1 clause 2); the corpora it
                         is measured on are machine-local and not CI-gated (§6).
  * AC-6 T1, T1-neg,
    T3, T7 leg 1       — all describe C's bounded within-root walk (#530-gated).
  * AC-6 T7 leg 2      — the `resolved-by-walk` census field is held by the
                         FIFTH ordering constraint (§4, §8): the 12 full-literal
                         `TIER2-COVERAGE` assertions in test_rcpt_verify.py must
                         be rewritten in the same change first.
  * AC-6 T11           — scheduling is OQ-9, undecided in the document.
  * AC-8               — the fourteen prose sites are edited "in the same change
                         that lands the mechanism", i.e. with C (#530-gated).
  * AC-9               — explicitly "text only ... does not land in this
                         ticket's own implementing change".
  * AC-7               — corrections posted to GitHub issue #488. Not
                         automatable from the test suite; MANUAL verification.

Covered here: AC-1 first half (the tautology), AC-2 (the lexical grammar plus
I8/T10 across all three parsers) and AC-6's T2 and T6.
"""
import hashlib
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "rcpt_verify.py"
REPO = pathlib.Path(__file__).resolve().parent.parent
RULING = REPO / "docs/plans/2026-08-21-488-c1-name-space-reduced.md"

H64 = "a" * 64
NOTE_PREFIX = "PROVENANCE-ONLY:"


def _import_rv():
    spec = importlib.util.spec_from_file_location("rcpt_verify", SCRIPT)
    rv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rv)
    return rv


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def receipt(*, artifacts=(), trace=(), claims=("(none)",), verdict="PASS",
            witness="lint:all-claims-cited  expect-fail=exit!=0  ran=TRACE#1",
            skill="red-team/1-devils-advocate", nxt="(none)"):
    """A minimal well-formed RCPT v1 receipt.

    The default WITNESS is a `lint:` kind deliberately: §5's T10 hazard note
    records that a fixture whose WITNESS is a ranged `kind=grep` on a declared
    name (or whose CLAIMS cites one, or whose TRACE carries `EXEC out=` naming
    one) is rejected at Tier-1 by a SHIPPED membership rule
    (`rcpt_verify.py:903-908`, `:937-953`, `:911-916`) the moment `(none)` wipes
    ARTIFACTS — so such a fixture passes green against the very build the pin
    names as broken, for the wrong reason on the wrong rule.
    """
    lines = [f"RCPT v1 {skill}", f"VERDICT  {verdict}  conf=0.90", "ARTIFACTS"]
    lines += [f"  {n}  sha256:{h}  {s}" for n, h, s in artifacts] or ["  (none)"]
    lines.append("TRACE")
    lines += [f"  {i}  {t}" for i, t in enumerate(trace, 1)] or ["  (none)"]
    lines.append("CLAIMS")
    lines += [f"  {c}" for c in claims]
    lines += [f"WITNESS    {witness}", "SUSPICION  0.10", f"NEXT       {nxt}"]
    return "\n".join(lines) + "\n"


def notes(stderr):
    """The PROVENANCE-ONLY advisory lines on a run's stderr, in order."""
    return [l for l in stderr.splitlines() if l.strip().startswith(NOTE_PREFIX)]


class _RootCase(unittest.TestCase):
    """A dispatch root OUTSIDE the checkout — §6's requirement for every fixture
    root in this ruling, so no committed file can satisfy a name by accident."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = pathlib.Path(self.td.name)

    def plant(self, relname, body):
        p = self.root / relname
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        return hashlib.sha256(body.encode()).hexdigest(), str(len(body))

    def verify(self, text, *extra, name="rcpt.txt"):
        p = self.root / name
        p.write_text(text)
        return run("--tier2", *extra, "--root", str(self.root), str(p))


# --------------------------------------------------------------------------
# AC-1, first half — the ruling is RECORDED.
# --------------------------------------------------------------------------
class TestTheRulingIsRecorded(unittest.TestCase):
    """AC-1 first half. §8 calls this out as a tautology satisfied by the
    artifact's own existence and discounts its contribution to zero; it is
    pinned anyway so the recorded ruling cannot silently leave the repo. AC-1's
    SECOND half (the `return-convention.md:104`/`:256` retraction) is #530-gated
    and is NOT tested."""

    def test_the_name_space_ruling_document_is_in_the_repo(self):
        self.assertTrue(RULING.exists(), f"missing ruling: {RULING}")

    def test_the_ruling_states_a_lexical_grammar_and_a_resolution_rule(self):
        text = RULING.read_text()
        self.assertIn("Lexical grammar", text)
        self.assertIn("Resolution rule", text)


# --------------------------------------------------------------------------
# AC-2 — the LEXICAL half, enforced at Tier-1 in `parse_artifacts`.
# --------------------------------------------------------------------------
class TestALegalArtifactsNameIsAPosixRelativePath(_RootCase):
    """AC-2 / §3 *Lexical grammar*. A legal `ARTIFACTS` <name> is a POSIX-relative
    path. Of the four clauses only TWO land as a Tier-1 raise — *not absolute*
    and *no NUL*. *No whitespace* is already unreachable (the line grammar splits
    on it) and *no `..`* is ruled producer-normative ONLY."""

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    # --- clause: not absolute (LANDS at Tier-1)
    def test_an_absolute_artifacts_name_is_rejected_at_tier1(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  /etc/hostname  sha256:{H64}  10"])

    def test_an_absolute_artifacts_name_is_rejected_before_tier2_runs(self):
        """The grammar is a grammar, not a membership rule the resolver decides
        after the fact (§1.2): the reject reaches the exit code."""
        out = self.verify(receipt(
            artifacts=[(str(self.root / "planted.md"), H64, "10")],
            trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("tier1-reject", out.stderr)

    def test_the_tier1_absolute_rejection_escapes_the_name_too(self):
        """§3, `not absolute` clause: this leg renders the name through
        `_show_path` for the same SIEGE-R2BA-4 reason the NUL leg does — an ANSI
        escape sequence in a receipt-supplied name renders as terminal control in
        the durable stderr record. Without this pin the escaping could be dropped
        from THIS leg alone and every other test would stay green."""
        out = self.verify(receipt(artifacts=[("/tmp/\x1b[31mx.md", H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("\x1b", out.stderr)
        self.assertIn(r"ARTIFACTS name is not relative: /tmp/\x1b[31mx.md",
                      out.stderr.splitlines())

    # --- clause: no NUL (LANDS at Tier-1)
    def test_a_nul_in_an_artifacts_name_is_rejected_at_tier1(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  f\x00.txt  sha256:{H64}  10"])

    def test_the_tier1_nul_rejection_never_puts_a_raw_nul_on_the_channel(self):
        """§3, `no NUL` clause: the Tier-1 message MUST render the name through
        `_show_path`, so SIEGE-R2BA-4's escaping guarantee survives the move from
        the Tier-2 `UNVERIFIABLE` line rather than being deleted with it."""
        out = self.verify(receipt(artifacts=[("f\x00.txt", H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("\x00", out.stderr)

    # --- clause: no `..` — producer-normative ONLY, deliberately NOT enforced
    def test_a_dotdot_component_is_producer_normative_and_not_a_tier1_raise(self):
        """§3: landing `..` at Tier-1 would make siege S-3's monotonicity pin
        (`test_rcpt_verify.py:5964-6006`) structurally unreachable while leaving
        its exit code unmoved. `_contained`'s realpath test already rejects the
        traversal at Tier-2. Whether it ever lands is OQ-10, undecided — so this
        pin asserts the status quo the document ships, and an implementer who
        turns it red has over-implemented AC-2."""
        out = self.rv.parse_artifacts([f"  ../../credentials  sha256:{H64}  10"])
        self.assertIn("../../credentials", out)

    # --- shapes that MUST stay legal
    def test_a_root_relative_subpath_stays_legal(self):
        """§3.4 move 1's recommended remedy is exactly this shape; rejecting
        path-shaped names at Tier-1 would also make the Tier-2 `--strict`
        path-shaped raise — the branch T6 pins — unreachable."""
        out = self.rv.parse_artifacts(
            [f"  out-9/round-9-findings.md  sha256:{H64}  10"])
        self.assertIn("out-9/round-9-findings.md", out)

    def test_a_twelve_hex_receipt_hash_prefix_stays_legal(self):
        out = self.rv.parse_artifacts([f"  a1b2c3d4e5f6  sha256:{H64}  10"])
        self.assertIn("a1b2c3d4e5f6", out)

    def test_a_bare_basename_stays_legal(self):
        out = self.rv.parse_artifacts([f"  round-1-findings.md  sha256:{H64}  10"])
        self.assertIn("round-1-findings.md", out)


# --------------------------------------------------------------------------
# AC-2 / I8 / AC-6 T10 — `(none)` is the empty-set sentinel and ONLY that.
# --------------------------------------------------------------------------
class TestTheNoneSentinelIsAnchoredToASingleLineBody(unittest.TestCase):
    """AC-6 T10 (three legs) / I8. `(none)` co-occurring with any entry is a
    Tier-1 `LintError`; `(none)` ALONE remains the legal empty-set sentinel.

    Both orderings are pinned for each parser — leading and trailing — because
    the shipped defect is an unanchored `return` inside the loop, and a fix that
    only skips a TRAILING `(none)` leaves the leading case live (§5, T10)."""

    def setUp(self):
        self.rv = _import_rv()

    A = f"a.md  sha256:{H64}  10"
    B = f"b.md  sha256:{H64}  20"
    T1 = f"1  READ  a.txt  sha256:{H64}"
    T2 = f"2  WROTE  b.txt  sha256:{H64}"
    C1 = "fatal-fixed=2 from=x.md#L1-L5"
    C2 = "significant-fixed=6 from=x.md#L1-L5"

    # --- leg 1: ARTIFACTS / parse_artifacts (rcpt_verify.py:240-241)
    def test_artifacts_none_after_an_entry_is_a_lint_error(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  {self.A}", "  (none)", f"  {self.B}"])

    def test_artifacts_none_before_an_entry_is_a_lint_error(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts(["  (none)", f"  {self.A}"])

    def test_artifacts_none_alone_remains_the_empty_set_sentinel(self):
        self.assertEqual(self.rv.parse_artifacts(["  (none)"]), {})

    # --- leg 2: TRACE / parse_trace (:259-260)
    def test_trace_none_after_an_entry_is_a_lint_error(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_trace([f"  {self.T1}", f"  {self.T2}", "  (none)"])

    def test_trace_none_before_an_entry_is_a_lint_error(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_trace(["  (none)", f"  {self.T1}"])

    def test_trace_none_alone_remains_the_empty_set_sentinel(self):
        self.assertEqual(self.rv.parse_trace(["  (none)"]), [])

    # --- leg 3: CLAIMS / parse_claims (:352-353)
    def test_claims_none_after_an_entry_is_a_lint_error(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_claims([f"  {self.C1}", "  (none)"])

    def test_claims_none_before_an_entry_is_a_lint_error(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_claims(["  (none)", f"  {self.C1}"])

    def test_claims_none_alone_remains_the_empty_set_sentinel(self):
        self.assertEqual(self.rv.parse_claims(["  (none)"]), [])

    def test_two_claims_without_a_sentinel_are_both_kept(self):
        """The control for the two legs above: without `(none)` the parser keeps
        both entries, so a red leg above is the sentinel and not the grammar."""
        self.assertEqual(len(self.rv.parse_claims([f"  {self.C1}", f"  {self.C2}"])), 2)


class TestTheNoneSentinelCannotEmptyArtifactsAtTheCli(_RootCase):
    """AC-6 T10, CLI leg. §5's measured discrimination on `dd06b80`:

        honest        : artifacts 1/2 ... unreached 1 ... partial   EXIT=1
        + "  (none)"  : artifacts 0/0 ... unreached 0               EXIT=0

    One `(none)` line empties `ARTIFACTS` before the path-shaped name is probed,
    so a receipt that must hard-FAIL exits clean instead. The pin demands a
    Tier-1 `LintError` on the second receipt."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("round-1-findings.md", "# findings\nfatal=0\n")
        self.honest = receipt(
            artifacts=[("round-1-findings.md", h, s),
                       ("docs/plans/absent-path-shaped.md", "b" * 64, "10")],
            trace=[f"WROTE  {self.root}/round-1-findings.md  sha256:{h}"])

    def test_the_honest_receipt_hard_fails_on_the_path_shaped_name(self):
        out = self.verify(self.honest, "--strict", name="honest.txt")
        self.assertEqual(out.returncode, 1)
        self.assertIn("absent under all bases", out.stderr)

    def test_one_injected_none_line_cannot_turn_that_hard_fail_into_exit_zero(self):
        injected = self.honest.replace("TRACE\n", "  (none)\nTRACE\n")
        out = self.verify(injected, "--strict", name="injected.txt")
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn("artifacts 0/0", out.stderr)


# --------------------------------------------------------------------------
# AC-6 T6 — regression pin (shipped behaviour; MUST stay green).
# --------------------------------------------------------------------------
class TestAnUnresolvablePathShapedArtifactStillFailsUnderStrict(_RootCase):
    """AC-6 T6. Broken copy (DEC-31): a build that drops the `--strict`
    path-shaped raise (`rcpt_verify.py:1710-1719`) and lets the name degrade to
    `UNVERIFIABLE` at exit 0.

    Built the way §5 mandates — the fixture carries the MANDATED ranged-grep
    witness on its resolving artifact (`red-team-prompt.md:193`'s shape), so the
    shipped #474/D6 rule (`:903-908`) raises at Tier-1 on the `(none)` variant
    before the `--strict` raise is reached. Without that, T6 pins the raise
    against one way of removing it and not against the cheaper way (§5's ⚠)."""

    PATTERN = "/significant=[1-9]|fatal=[1-9]/"

    def setUp(self):
        super().setUp()
        h, s = self.plant("round-1-findings.md",
                          "# Round 1 findings\n\nfatal=0\nsignificant=2\nminor=1\n")
        self.text = receipt(
            artifacts=[("round-1-findings.md", h, s),
                       ("docs/plans/absent-path-shaped.md", "b" * 64, "10")],
            trace=[f"WROTE  round-1-findings.md  sha256:{h}"],
            witness=(f"grep:round-1-findings.md#L1-L5  pattern={self.PATTERN}  "
                     "expect-fail=match  ran=TRACE#1"))

    def test_the_strict_run_hard_fails_and_says_which_name_and_why(self):
        out = self.verify(self.text, "--strict", name="t6.txt")
        self.assertEqual(out.returncode, 1)
        self.assertIn("path-shaped artifact docs/plans/absent-path-shaped.md",
                      out.stderr)
        self.assertIn("absent under all bases", out.stderr)

    def test_the_pin_is_not_defeated_by_an_injected_none_line(self):
        injected = self.text.replace("TRACE\n", "  (none)\nTRACE\n")
        out = self.verify(injected, "--strict", name="t6-none.txt")
        self.assertNotEqual(out.returncode, 0)


# --------------------------------------------------------------------------
# AC-6 T2 — silence is not permitted (grudge e0f0a6b75692).
# --------------------------------------------------------------------------
class TestATraceNameAbsentFromArtifactsIsNotSilent(_RootCase):
    """AC-6 T2, legs 1-3. §3.4: a `TRACE` entry of ANY verb — `READ`, `EDIT` or
    `WROTE` — whose name is absent from `ARTIFACTS` MUST emit
    `PROVENANCE-ONLY: <name> (declared in TRACE, not verified)`.

    Broken copy (DEC-31): a build with the note keyed on the verb (the
    `EDIT`/`WROTE`-only scoping §3.4 corrects)."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("round-1-findings.md", "# findings\nfatal=0\n")
        self.out = self.verify(receipt(
            artifacts=[("round-1-findings.md", h, s)],
            trace=[f"WROTE  {self.root}/round-1-findings.md  sha256:{h}",
                   "READ  /elsewhere/notes-read.md",
                   f"EDIT  /elsewhere/notes-edit.md  sha256:{'f' * 64}",
                   f"WROTE  /elsewhere/notes-wrote.md  sha256:{'f' * 64}"]))

    def test_the_run_completes(self):
        self.assertEqual(self.out.returncode, 0, self.out.stderr)

    def test_a_read_only_name_emits_the_note(self):
        self.assertTrue(any("notes-read.md" in n for n in notes(self.out.stderr)),
                        self.out.stderr)

    def test_an_edit_only_name_emits_the_note(self):
        self.assertTrue(any("notes-edit.md" in n for n in notes(self.out.stderr)),
                        self.out.stderr)

    def test_a_wrote_only_name_emits_the_note(self):
        self.assertTrue(any("notes-wrote.md" in n for n in notes(self.out.stderr)),
                        self.out.stderr)

    def test_the_note_carries_the_ruled_wording(self):
        emitted = notes(self.out.stderr)
        self.assertTrue(emitted, self.out.stderr)  # never vacuous on silence
        for n in emitted:
            self.assertIn("(declared in TRACE, not verified)", n)


class TestTheNoteIsKeyedOnVerifiedBasenames(_RootCase):
    """AC-6 T2, legs 4 and 5 — the match key. §3.4: *absent from `ARTIFACTS`* is
    evaluated on the BASENAME of the `TRACE` name against the basenames of the
    `ARTIFACTS` names Tier-2 RESOLVED AND HASH-VERIFIED.

    Without both legs the pin cannot separate the three candidate keys, and
    separating them is the entire subject of §3.4's match-key clause."""

    def test_a_trace_absolute_path_of_a_verified_artifact_emits_nothing(self):
        """Leg 4. Broken copy (DEC-31): a build keyed on the literal `parts[0]`
        string, which mislabels 13 verified entries across the three corpora —
        §3.2 mandates different name forms by design (absolute in `TRACE`, bare
        in `ARTIFACTS`), so an exact-match key fires on correct receipts."""
        h, s = self.plant("round-1-findings.md", "# findings\nfatal=0\n")
        out = self.verify(receipt(
            artifacts=[("round-1-findings.md", h, s)],
            trace=[f"WROTE  {self.root}/round-1-findings.md  sha256:{h}"]))
        self.assertEqual(out.returncode, 0, out.stderr)
        # Non-vacuity: the artifact really did resolve AND hash-verify, so this
        # is silence on a VERIFIED match and not silence on a run where nothing
        # was verified at all.
        self.assertIn("artifacts 1/1", out.stderr)
        self.assertEqual(notes(out.stderr), [])

    def test_a_trace_name_matching_an_unresolved_artifact_still_emits_the_note(self):
        """Leg 5, the leg the whole match-key clause turns on. Broken copy
        (DEC-31): the verified-blind basename key, which stays SILENT here —
        suppressing a TRUE advisory (66 flat / 89 nested such suppressions
        across the three frozen corpora). Silence is the failure direction
        grudge e0f0a6b75692 names."""
        h, s = self.plant("round-1-findings.md", "# findings\nfatal=0\n")
        out = self.verify(receipt(
            artifacts=[("round-1-findings.md", h, s),
                       ("absent-bare.md", "b" * 64, "10")],
            trace=[f"WROTE  {self.root}/round-1-findings.md  sha256:{h}",
                   "READ  /elsewhere/absent-bare.md"]))
        self.assertEqual(out.returncode, 0, out.stderr)
        emitted = notes(out.stderr)
        self.assertEqual(len(emitted), 1, out.stderr)
        self.assertIn("absent-bare.md", emitted[0])


class TestTheNoteSurvivesATruncatedRun(_RootCase):
    """AC-6 T2, leg 6 — BOTH halves in one fixture, or the pin cannot tell
    "correct" from "notes discarded wholesale".

    §3.4: on a run truncated by any raise that abandons the rest of the entry
    loop, a `TRACE` entry whose basename matches an `ARTIFACTS` entry that was
    NOT EVALUATED emits nothing; one matching an entry that WAS evaluated
    (verified or not) before the raise still gets its note.

    Broken copy (DEC-31): a build accumulating the notes into
    `tier2_artifacts`'s own RETURN VALUE instead of a caller-supplied
    out-parameter — the sole production call site is
    `notes += tier2_artifacts(...)` (`:3793`), which never executes on a raise,
    so every note is discarded. It goes green on the un-evaluated half by
    coincidence and wrong on the evaluated half.

    §5 requires the fixture be built TWICE — once truncating on a hash mismatch,
    once on the `--strict` path-shaped raise — because a build that records
    evaluation status only in the mismatch arm passes the first and fails the
    second."""

    TRACE = ["READ  /elsewhere/evaluated-unverified.md",
             "READ  /elsewhere/unreached.md"]

    def _assert_halves(self, out):
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("partial", out.stderr)
        emitted = notes(out.stderr)
        self.assertEqual(len(emitted), 1, out.stderr)
        self.assertIn("evaluated-unverified.md", emitted[0])
        self.assertFalse([n for n in emitted if "unreached.md" in n], out.stderr)

    def test_truncation_by_hash_mismatch_keeps_the_evaluated_half_audible(self):
        body = "disk content\n"
        self.plant("mismatch.md", body)
        out = self.verify(receipt(
            artifacts=[("evaluated-unverified.md", "c" * 64, "10"),
                       ("mismatch.md", "d" * 64, str(len(body))),
                       ("unreached.md", "e" * 64, "10")],
            trace=self.TRACE), name="mismatch-run.txt")
        self.assertIn("sha256 mismatch", out.stderr)
        self._assert_halves(out)

    def test_truncation_by_the_strict_path_shaped_raise_behaves_identically(self):
        out = self.verify(receipt(
            artifacts=[("evaluated-unverified.md", "c" * 64, "10"),
                       ("docs/plans/absent-path-shaped.md", "d" * 64, "10"),
                       ("unreached.md", "e" * 64, "10")],
            trace=self.TRACE), "--strict", name="strict-run.txt")
        self.assertIn("absent under all bases", out.stderr)
        self._assert_halves(out)


class TestTheNoteEscapesTheLeastConstrainedNameInTheGrammar(_RootCase):
    """AC-6 T2, leg 7. SIEGE-R2BA-4's escaping guarantee, extended to `TRACE`
    names — required *a fortiori* (§3.4), because a `TRACE` name is the LEAST
    constrained receipt-controlled string in the grammar: §3 lets `TRACE` name
    anything, and AC-2's Tier-1 raise binds `ARTIFACTS` only.

    Broken copy (DEC-31): a build interpolating the raw `args` token — the shape
    `_show_path`'s own docstring says the surrounding code deliberately uses for
    whole `args` strings, so "the surrounding code already does it" is NOT
    available as a defence at this site."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("round-1-findings.md", "# findings\nfatal=0\n")
        self.out = self.verify(receipt(
            artifacts=[("round-1-findings.md", h, s)],
            trace=[f"WROTE  {self.root}/round-1-findings.md  sha256:{h}",
                   "READ  /elsewhere/ho\x00st\x1b[31mile.md"]))

    def test_the_hostile_trace_name_is_still_reported(self):
        self.assertTrue(any("ile.md" in n for n in notes(self.out.stderr)),
                        self.out.stderr)

    def test_neither_the_nul_nor_the_ansi_escape_reaches_the_channel_raw(self):
        # Asserted together with the note's presence: a build that emits NOTHING
        # would otherwise pass this leg by staying silent, which is the exact
        # fail-open direction grudge e0f0a6b75692 names.
        self.assertTrue(notes(self.out.stderr), self.out.stderr)
        self.assertNotIn("\x00", self.out.stderr)
        self.assertNotIn("\x1b", self.out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
