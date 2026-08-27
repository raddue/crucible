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
    (`rcpt_verify.py:932-937`, `:966-982`, `:940-945`) the moment `(none)` wipes
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
# ADVERSARIAL (Task 2) — five attacks on the two new Tier-1 raises.
# --------------------------------------------------------------------------
class TestTheNameBanIsByteExactAndAHomoglyphGainsNothing(_RootCase):
    """ATTACK 1 — the ban is `name.startswith("/")`, a BYTE test. A fullwidth
    solidus U+FF0F (`\uff0f`) renders indistinguishably from `/` in most fonts, so
    `／etc/passwd` reads as absolute to a human reviewing the receipt while
    sailing past the check.

    The attack only MATTERS if the homoglyph buys a capability the ASCII form
    would have had, so this pins both halves: the name stays legal at Tier-1
    (over-implementing the ban to cover look-alikes would flip the first leg and
    is not what AC-2 rules), and it resolves NOWHERE — the byte U+FF0F is not a
    POSIX separator, so `root / name` is one literal component that cannot reach
    the planted file the ASCII twin names."""

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        self.outside = tempfile.TemporaryDirectory()
        self.addCleanup(self.outside.cleanup)
        secret = pathlib.Path(self.outside.name) / "secret.md"
        secret.write_text("outside-the-root\n")
        self.abs_name = str(secret)                       # /tmp/.../secret.md
        self.homo_name = "／" + self.abs_name[1:]     # ／ tmp/.../secret.md

    def test_the_ascii_twin_is_the_one_the_ban_catches(self):
        """Non-vacuity anchor: the two names differ in exactly one codepoint."""
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  {self.abs_name}  sha256:{H64}  10"])

    def test_a_fullwidth_solidus_name_stays_legal_at_tier1(self):
        out = self.rv.parse_artifacts([f"  {self.homo_name}  sha256:{H64}  10"])
        self.assertIn(self.homo_name, out)

    def test_the_homoglyph_name_resolves_nowhere_so_it_buys_no_read(self):
        # Control first — resolve_base really does find a file under this root,
        # so a None below is the homoglyph failing and not a dead resolver.
        self.plant("planted.md", "in-the-root\n")
        self.assertIsNotNone(self.rv.resolve_base("planted.md", self.root))
        self.assertIsNone(self.rv.resolve_base(self.homo_name, self.root))

    def test_the_homoglyph_name_is_never_billed_as_verified_at_the_cli(self):
        out = self.verify(receipt(artifacts=[(self.homo_name, H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertNotIn("ARTIFACTS name is not relative", out.stderr)
        self.assertIn("artifacts 0/1", out.stderr)


class TestTheBanReachesTheArtifactsHeaderLineItself(_RootCase):
    """ATTACK 2 — `parse_receipt` puts any text trailing the section header into
    the body: `sections[matched] = [rest] if rest else []`. So
    `ARTIFACTS  /etc/hostname  sha256:...  10` is a one-entry ARTIFACTS body that
    never appears as an INDENTED line, which is the shape every fixture in this
    file (and the `receipt()` helper) exercises. A check bolted onto the indented
    path only would be blind here."""

    def _inline(self, name):
        text = receipt(artifacts=[(name, H64, "10")],
                       trace=["READ  /elsewhere/x.md"])
        return text.replace(f"ARTIFACTS\n  {name}  ", f"ARTIFACTS  {name}  ")

    def test_the_inline_form_really_is_a_one_entry_body(self):
        """Non-vacuity: a LEGAL inline name parses to a one-entry ARTIFACTS."""
        out = self.verify(self._inline("round-1-findings.md"), name="ok.txt")
        self.assertIn("artifacts 0/1", out.stderr)

    def test_an_absolute_name_on_the_header_line_is_rejected_at_tier1(self):
        out = self.verify(self._inline("/etc/hostname"), name="abs.txt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("ARTIFACTS name is not relative: /etc/hostname",
                      out.stderr.splitlines())

    def test_a_nul_name_on_the_header_line_is_rejected_at_tier1(self):
        out = self.verify(self._inline("f\x00.txt"), name="nul.txt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertNotIn("\x00", out.stderr)
        self.assertIn(r"ARTIFACTS name contains NUL: f\x00.txt",
                      out.stderr.splitlines())


class TestEveryNulPositionIsRejectedAndNoneReachesTheChannel(_RootCase):
    """ATTACK 3 — `"\x00" in name` is position-blind by construction, but the
    RENDERING is not: `_show_path` substitutes per match, so a multi-NUL name is
    the case where a `str.replace`-style or first-match-only escaper would leak a
    raw byte after escaping the first one. The shipped test covers exactly one
    NUL, in the middle, at the API boundary.

    Also pins the PRECEDENCE between the two new raises on a name that is both
    absolute and NUL-bearing: the absolute leg is first, and its message must
    still escape the NUL — the escaping cannot live on the NUL leg alone."""

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    def test_a_leading_nul_is_rejected(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  \x00f.txt  sha256:{H64}  10"])

    def test_a_trailing_nul_is_rejected(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  f.txt\x00  sha256:{H64}  10"])

    def test_a_name_that_is_only_nuls_is_rejected(self):
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts([f"  \x00\x00\x00  sha256:{H64}  10"])

    def test_every_nul_of_a_multi_nul_name_is_escaped_on_the_channel(self):
        out = self.verify(receipt(artifacts=[("a\x00b\x00c.md", H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertNotIn("\x00", out.stderr)
        self.assertIn(r"ARTIFACTS name contains NUL: a\x00b\x00c.md",
                      out.stderr.splitlines())

    def test_an_absolute_nul_bearing_name_takes_the_absolute_leg_still_escaped(self):
        out = self.verify(receipt(artifacts=[("/tmp/f\x00.txt", H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertNotIn("\x00", out.stderr)
        self.assertIn(r"ARTIFACTS name is not relative: /tmp/f\x00.txt",
                      out.stderr.splitlines())


class TestTheNewTier1RaisesCannotForgeACensusLine(_RootCase):
    """ATTACK 4 — C1-R2-S2's substring forgery, aimed at the TWO NEW write sites.
    Both raises print BEFORE `TIER2-COVERAGE: not-reached (tier1-reject)`, and the
    documented consumer is `grep -m1 'TIER2-COVERAGE:'` — so a name spelling the
    census token hands that consumer an attacker-authored first match from a
    receipt that verified NOTHING. A name may hold no whitespace, but the token
    itself has none, and `grep` matches a SUBSTRING."""

    FORGED = "TIER2-COVERAGE:artifacts=9/9"

    def _first_census(self, stderr):
        for line in stderr.splitlines():
            if "TIER2-COVERAGE:" in line:
                return line
        return None

    def test_the_absolute_leg_cannot_put_a_live_token_ahead_of_the_census(self):
        out = self.verify(receipt(artifacts=[("/" + self.FORGED, H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("ARTIFACTS name is not relative", out.stderr)
        self.assertEqual(self._first_census(out.stderr),
                         "TIER2-COVERAGE: not-reached (tier1-reject)")

    def test_the_nul_leg_cannot_put_a_live_token_ahead_of_the_census(self):
        out = self.verify(receipt(artifacts=[(self.FORGED + "\x00", H64, "10")],
                                  trace=["READ  /elsewhere/x.md"]))
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("ARTIFACTS name contains NUL", out.stderr)
        self.assertEqual(self._first_census(out.stderr),
                         "TIER2-COVERAGE: not-reached (tier1-reject)")


class TestTheBanAlsoRejectsTheShapeThatUsedToVerifyCleanly(_RootCase):
    """ATTACK 5 — collateral damage, the failure direction a ban can only have.
    Before this change an ABSOLUTE ARTIFACTS name pointing at a real file INSIDE
    the root took `_resolve_base_one`'s `p.is_absolute()` branch, passed
    `_contained`, hash-verified, and billed `artifacts 1/1` at exit 0. That branch
    is now unreachable from ARTIFACTS, so this shape flips 0 -> 1.

    The flip is INTENDED; what must not come with it is a crash or a lost census.
    The relative twin is asserted in the same fixture, from the same planted file
    and the same digest, so a green run cannot mean "both directions broke"."""

    def setUp(self):
        super().setUp()
        self.body = "# findings\nfatal=0\n"
        self.h, self.s = self.plant("planted.md", self.body)

    def test_the_relative_twin_still_verifies_and_exits_zero(self):
        out = self.verify(receipt(artifacts=[("planted.md", self.h, self.s)],
                                  trace=["READ  /elsewhere/x.md"]),
                          name="rel.txt")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", out.stderr)

    def test_the_absolute_twin_hard_fails_with_a_census_and_no_traceback(self):
        name = str(self.root / "planted.md")
        out = self.verify(receipt(artifacts=[(name, self.h, self.s)],
                                  trace=["READ  /elsewhere/x.md"]),
                          name="abs.txt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertNotIn("artifacts 1/1", out.stderr)
        self.assertIn(f"ARTIFACTS name is not relative: {name}",
                      out.stderr.splitlines())
        self.assertIn("TIER2-COVERAGE: not-reached (tier1-reject)",
                      out.stderr.splitlines())


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

    # --- leg 1: ARTIFACTS / parse_artifacts (rcpt_verify.py:232-258, called at :264)
    def test_artifacts_none_after_an_entry_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_artifacts([f"  {self.A}", "  (none)", f"  {self.B}"])

    def test_artifacts_none_before_an_entry_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_artifacts(["  (none)", f"  {self.A}"])

    def test_artifacts_none_alone_remains_the_empty_set_sentinel(self):
        self.assertEqual(self.rv.parse_artifacts(["  (none)"]), {})

    def test_two_artifacts_nones_are_a_lint_error(self):
        """A body that is nothing BUT sentinels is not a one-line body either:
        `(none)` co-occurring with `(none)` is the same violation."""
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_artifacts(["  (none)", "  (none)"])

    def test_the_sentinel_raise_precedes_the_name_legality_raise(self):
        """Precedence pin. `_none_sentinel` runs BEFORE the per-entry
        absolute/NUL checks, so a body that is BOTH co-occurring and
        name-illegal reports the sentinel violation. Deliberate: the body is
        rejected as a whole before any entry in it is read."""
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_artifacts(["  (none)", f"  /etc/passwd  sha256:{H64}  10"])

    # --- leg 2: TRACE / parse_trace (`_none_sentinel` called at :298)
    def test_trace_none_after_an_entry_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_trace([f"  {self.T1}", f"  {self.T2}", "  (none)"])

    def test_trace_none_before_an_entry_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_trace(["  (none)", f"  {self.T1}"])

    def test_trace_none_between_two_entries_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_trace([f"  {self.T1}", "  (none)", f"  {self.T2}"])

    def test_trace_none_alone_remains_the_empty_set_sentinel(self):
        self.assertEqual(self.rv.parse_trace(["  (none)"]), [])

    def test_two_trace_nones_are_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_trace(["  (none)", "  (none)"])

    # --- leg 3: CLAIMS / parse_claims (`_none_sentinel` called at :391)
    def test_claims_none_after_an_entry_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_claims([f"  {self.C1}", "  (none)"])

    def test_claims_none_before_an_entry_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_claims(["  (none)", f"  {self.C1}"])

    def test_claims_none_between_two_entries_is_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_claims([f"  {self.C1}", "  (none)", f"  {self.C2}"])

    def test_claims_none_alone_remains_the_empty_set_sentinel(self):
        self.assertEqual(self.rv.parse_claims(["  (none)"]), [])

    def test_two_claims_nones_are_a_lint_error(self):
        with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
            self.rv.parse_claims(["  (none)", "  (none)"])

    def test_two_claims_without_a_sentinel_are_both_kept(self):
        """The control for the CLAIMS legs above: without `(none)` the parser
        keeps both entries, so a red leg above is the sentinel and not the
        grammar."""
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
        self.assertIn("empty-set sentinel", out.stderr)
        self.assertNotIn("artifacts 0/0", out.stderr)


# --------------------------------------------------------------------------
# AC-6 T6 — regression pin (shipped behaviour; MUST stay green).
# --------------------------------------------------------------------------
class TestAnUnresolvablePathShapedArtifactStillFailsUnderStrict(_RootCase):
    """AC-6 T6. Broken copy (DEC-31): a build that drops the `--strict`
    path-shaped raise (`rcpt_verify.py:1739-1748`) and lets the name degrade to
    `UNVERIFIABLE` at exit 0.

    Built the way §5 mandates — the fixture carries the MANDATED ranged-grep
    witness on its resolving artifact (`red-team-prompt.md:193`'s shape), so the
    shipped #474/D6 rule (`:932-937`) raises at Tier-1 on the `(none)` variant
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

    def test_a_trace_name_matching_a_hash_mismatched_artifact_still_emits_the_note(self):
        """Legs 4 and 5, the half that fixes the meaning of VERIFIED. §3.4 says
        RESOLVED *AND* HASH-VERIFIED, so `verified_bases.add(...)` sits AFTER the
        sha256 comparison, never before it.

        Broken copy (DEC-31): recording the basename as soon as the name RESOLVES.
        The two legs above cannot see the difference — both of their artifacts
        either hash-match or never resolve at all — so that build stays green on
        the whole suite while a MISMATCHED artifact counts as verified and
        silences the advisory for the `TRACE` entry citing it. Silence on the
        entry whose declared file failed its hash is the worst direction of the
        failure grudge e0f0a6b75692 names."""
        body = "disk content\n"
        self.plant("mismatch.md", body)
        out = self.verify(receipt(
            artifacts=[("mismatch.md", "d" * 64, str(len(body)))],
            trace=[f"READ  {self.root}/mismatch.md"]))
        # Non-vacuity: the name RESOLVED and was read and hashed — it failed only
        # the COMPARISON, which is exactly the state the two candidate placements
        # of the `.add()` disagree about.
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("sha256 mismatch", out.stderr)
        emitted = notes(out.stderr)
        self.assertEqual(len(emitted), 1, out.stderr)
        self.assertIn("mismatch.md", emitted[0])


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
    `notes += tier2_artifacts(...)` (`:3836`), which never executes on a raise,
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
        # Leg 6, THIRD half — the `except BaseException` mirror arm. This leg's OWN
        # UNVERIFIABLE:/REFUSED:/AMBIGUOUS: notes ride the RETURN value, and the sole
        # production call site's `notes += tier2_artifacts(...)` never executes on a
        # raise; the mirror arm is the only thing that puts them on stderr here.
        # Deleting its `notes_out.extend(notes)` leaves the two assertions above
        # green (the PROVENANCE-ONLY notes go through `notes_out` directly), so
        # without this line the arm is entirely unpinned.
        self.assertIn("UNVERIFIABLE: evaluated-unverified.md", out.stderr)

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



# --------------------------------------------------------------------------
# ADVERSARIAL (Task 3) — five attacks on `_none_sentinel` and its call sites.
#
# The unit legs above pin the helper's contract. These five attack the SEAM
# between the helper and everything that reaches it: the two sections whose
# CLI leg was never pinned (only ARTIFACTS was), the look-alike sentinels that
# `.strip()` does and does not normalise, the inline-header body shape, and the
# entry modes that could route around the raise.
# --------------------------------------------------------------------------
class TestATrailingNoneInClaimsCannotLaunderAnUncitedClaim(_RootCase):
    """ATTACK A-1. The `TestTheNoneSentinelCannotEmptyArtifactsAtTheCli` pin
    covers ARTIFACTS only. CLAIMS is the sharper channel: `lint_receipt` walks
    every parsed claim and raises when its citation names an artifact the
    receipt does not declare, so a `(none)` that empties the list deletes the
    check along with the evidence. Measured on `157fd54` (pre-fix):

        honest        : CLAIM citation artifact not listed: ghost.md   EXIT=1
        + "  (none)"  : (clean)                                        EXIT=0

    One appended line turned a hard reject into a clean pass."""

    def setUp(self):
        super().setUp()
        self.honest = receipt(
            claims=["fatal-fixed=2 from=ghost.md#L1-L5"],
            trace=[f"READ  a.txt  sha256:{H64}"])

    def test_the_honest_receipt_hard_fails_on_the_undeclared_citation(self):
        out = self.verify(self.honest, name="honest.txt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("CLAIM citation artifact not listed", out.stderr)

    def test_one_injected_none_line_cannot_turn_that_hard_fail_into_exit_zero(self):
        injected = self.honest.replace("\nWITNESS", "\n  (none)\nWITNESS", 1)
        out = self.verify(injected, name="injected.txt")
        self.assertNotEqual(out.returncode, 0, out.stderr)
        self.assertIn("CLAIMS (none) is the empty-set sentinel", out.stderr)

    def test_the_laundered_run_never_reports_reaching_tier2(self):
        """The reject must be a Tier-1 one. A build that raised somewhere later
        would still exit 1 while having already billed coverage it never had."""
        injected = self.honest.replace("\nWITNESS", "\n  (none)\nWITNESS", 1)
        out = self.verify(injected, name="injected.txt")
        census = [l for l in out.stderr.splitlines() if "TIER2-COVERAGE:" in l]
        self.assertEqual(census, ["TIER2-COVERAGE: not-reached (tier1-reject)"],
                         out.stderr)


class TestATrailingNoneInTraceCannotDeleteTheExecOutCheck(_RootCase):
    """ATTACK A-2, the TRACE half of the same unpinned seam. `lint_receipt`
    derives four membership rules from TRACE entries (`EXEC out=`, EDIT/WROTE
    `sha256:`, DISPATCHED `rcpt-sha256:`, and every `ran=TRACE#n` resolution).
    An emptied TRACE deletes all four at once. The witness is `ran=SKIPPED:` on
    purpose: a `ran=TRACE#1` witness would fail to resolve against the emptied
    list and mask the fail-open behind an unrelated raise. Measured on
    `157fd54` (pre-fix):

        honest        : EXEC out= artifact not in ARTIFACTS: ghost.md   EXIT=1
        + "  (none)"  : (clean)                                         EXIT=0
    """

    WITNESS = "lint:all-claims-cited  expect-fail=exit!=0  ran=SKIPPED:deferred"

    def setUp(self):
        super().setUp()
        self.honest = receipt(trace=["EXEC  pytest out=ghost.md#L1-L5"],
                              witness=self.WITNESS, nxt="lint:all-claims-cited")

    def test_the_honest_receipt_hard_fails_on_the_undeclared_exec_output(self):
        out = self.verify(self.honest, name="honest.txt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("EXEC out= artifact not in ARTIFACTS", out.stderr)

    def test_one_injected_none_line_cannot_turn_that_hard_fail_into_exit_zero(self):
        injected = self.honest.replace("CLAIMS\n", "  (none)\nCLAIMS\n", 1)
        out = self.verify(injected, name="injected.txt")
        self.assertNotEqual(out.returncode, 0, out.stderr)
        self.assertIn("TRACE (none) is the empty-set sentinel", out.stderr)


class TestOnlyTheExactSentinelIsEverTreatedAsOne(unittest.TestCase):
    """ATTACK A-3 — sentinel look-alikes. `_none_sentinel` normalises with
    `str.strip()`, which strips the whole Unicode whitespace class (`\xa0` NBSP
    included) but NOT the zero-width characters that merely LOOK like padding.
    Two opposite hazards fall out and both must land fail-CLOSED:

      * a look-alike that `.strip()` does NOT normalise (`(None)`, `(NONE)`,
        `\u200b(none)`, `( none )`) must never reach the entry loop as a
        silently-skipped line — the loop no longer has a `(none)` branch, so it
        must reject the line as malformed rather than ignore it;
      * a look-alike that `.strip()` DOES normalise (`\xa0(none)\xa0`) is a real
        sentinel and must therefore obey the co-occurrence rule, not slip past
        the membership test on its raw spelling."""

    def setUp(self):
        self.rv = _import_rv()

    ENTRY = {"parse_artifacts": f"a.md  sha256:{H64}  10",
             "parse_trace": f"1  READ  a.txt  sha256:{H64}",
             "parse_claims": "fatal-fixed=2 from=x.md#L1-L5"}
    LOOKALIKE = ["(None)", "(NONE)", "\u200b(none)", "(none)\u200b", "( none )",
                 "(none )", "((none))"]

    def test_no_lookalike_is_ever_silently_skipped_by_any_parser(self):
        for fn, entry in self.ENTRY.items():
            for fake in self.LOOKALIKE:
                with self.subTest(parser=fn, lookalike=fake):
                    with self.assertRaises(self.rv.LintError):
                        getattr(self.rv, fn)([f"  {fake}", f"  {entry}"])

    def test_no_lookalike_alone_is_accepted_as_an_empty_set(self):
        for fn, _ in self.ENTRY.items():
            for fake in self.LOOKALIKE:
                with self.subTest(parser=fn, lookalike=fake):
                    with self.assertRaises(self.rv.LintError):
                        getattr(self.rv, fn)([f"  {fake}"])

    def test_a_nbsp_cloaked_sentinel_is_still_bound_by_the_co_occurrence_rule(self):
        """`\xa0(none)\xa0` strips to the sentinel, so it wipes exactly as
        `(none)` does — and must therefore be caught exactly as `(none)` is.
        A membership test written against the RAW line would miss it."""
        for fn, entry in self.ENTRY.items():
            with self.subTest(parser=fn):
                with self.assertRaisesRegex(self.rv.LintError, "empty-set sentinel"):
                    getattr(self.rv, fn)(["  \xa0(none)\xa0", f"  {entry}"])


class TestTheSentinelRuleReachesTheInlineHeaderBodyShape(_RootCase):
    """ATTACK A-4. `parse_receipt` puts a section header's own remainder into
    the body as `body[0]` UNINDENTED, so `ARTIFACTS  (none)` and `  (none)`
    produce different strings in the same list. A guard that keyed off the
    indented spelling — or that started scanning at `body[1]` — would leave the
    header line as a laundering slot. Both orders are attacked for all three
    sections: sentinel-on-the-header + indented entry, and entry-on-the-header
    + indented sentinel."""

    ENTRY = {"ARTIFACTS": f"a.md  sha256:{H64}  10",
             "TRACE": f"1  READ  a.txt  sha256:{H64}",
             # a 12-hex receipt-hash citation, NOT a name: `lint_receipt`
             # requires a named artifact to appear in ARTIFACTS, and ARTIFACTS
             # is `(none)` in every cell where CLAIMS is the section under test.
             "CLAIMS": "fatal-fixed=2 from=aaaaaaaaaaaa#L1-L5"}
    OTHER = {"ARTIFACTS": ["  (none)"], "TRACE": ["  (none)"], "CLAIMS": ["  (none)"]}

    def _receipt(self, section, first, rest):
        """A v1 receipt whose `section` body is `first` inline on the header
        line and `rest` indented under it; every other section is `(none)`."""
        out = ["RCPT v1 red-team/1-devils-advocate", "VERDICT  PASS  conf=0.90"]
        for name in ("ARTIFACTS", "TRACE", "CLAIMS"):
            if name == section:
                out.append(f"{name}  {first}")
                out += [f"  {l}" for l in rest]
            else:
                out += [name] + self.OTHER[name]
        out += ["WITNESS    lint:all-claims-cited  expect-fail=exit!=0  "
                "ran=SKIPPED:deferred", "SUSPICION  0.10",
                "NEXT       lint:all-claims-cited"]
        return "\n".join(out) + "\n"

    def test_a_sentinel_on_the_header_line_still_binds_the_indented_entry(self):
        for section, entry in self.ENTRY.items():
            with self.subTest(section=section, order="sentinel-first"):
                out = self.verify(self._receipt(section, "(none)", [entry]),
                                  name=f"{section}-a.txt")
                self.assertNotEqual(out.returncode, 0, out.stderr)
                self.assertIn(f"{section} (none) is the empty-set sentinel",
                              out.stderr)

    def test_an_entry_on_the_header_line_still_binds_the_indented_sentinel(self):
        for section, entry in self.ENTRY.items():
            with self.subTest(section=section, order="entry-first"):
                out = self.verify(self._receipt(section, entry, ["(none)"]),
                                  name=f"{section}-b.txt")
                self.assertNotEqual(out.returncode, 0, out.stderr)
                self.assertIn(f"{section} (none) is the empty-set sentinel",
                              out.stderr)

    def test_the_control_inline_receipt_without_a_sentinel_is_accepted(self):
        """The control for the six legs above: the same inline-header shape
        with no co-occurring `(none)` must NOT raise, so a red leg is the
        sentinel rule and not the inline shape itself."""
        out = self.verify(self._receipt("CLAIMS", self.ENTRY["CLAIMS"], []),
                          name="control.txt")
        self.assertEqual(out.returncode, 0, out.stderr)


class TestNoEntryModeRoutesAroundTheSentinelRaise(_RootCase):
    """ATTACK A-5. The raise is only worth what the narrowest entry path
    enforces. `rcpt_verify.py` has three verification modes (`--tier1`,
    `--tier2`, and the default) and two schema versions (`RCPT v1`, `RCPT v1.1`,
    the latter carrying a second local lint pass in `lint_v11_local`). A guard
    sited on one branch of that 3x2 grid — or a v1.1 path that re-parsed the
    body through its own loop — would leave the rest live. All six cells must
    reject the same co-occurring TRACE `(none)`."""

    def _receipt(self, version):
        body = [f"RCPT v{version} red-team/1-devils-advocate",
                "VERDICT  PASS  conf=0.90", "ARTIFACTS", "  (none)", "TRACE",
                f"  1  READ  a.txt  sha256:{H64}", "  (none)", "CLAIMS",
                "  (none)",
                "WITNESS    lint:all-claims-cited  expect-fail=exit!=0  ran=TRACE#1",
                # SUSPICION 0.00, not 0.10: `TRIPWIRE: none` is legal only on a
                # PASS at suspicion zero (`lint_v11_local`), and the v1.1 cells
                # of the grid must reach the sentinel rule, not that one.
                "SUSPICION  0.00", "NEXT       (none)"]
        if version == "1.1":
            body += ["TRIPWIRE: none", "SUPERSEDES: none"]
        return "\n".join(body) + "\n"

    def test_every_mode_and_schema_version_rejects_the_co_occurring_sentinel(self):
        for version in ("1", "1.1"):
            for mode in ("--tier1", "--tier2", None):
                with self.subTest(version=version, mode=mode or "default"):
                    p = self.root / f"r-{version}-{mode}.txt"
                    p.write_text(self._receipt(version))
                    args = [a for a in (mode, "--root", str(self.root), str(p)) if a]
                    out = run(*args)
                    self.assertEqual(out.returncode, 1, out.stderr)
                    self.assertIn("TRACE (none) is the empty-set sentinel",
                                  out.stderr)

    def test_the_control_receipt_without_the_injected_line_is_accepted(self):
        """Control: the same six cells with the `(none)` line removed must all
        exit 0, so a red leg above is the sentinel and not the fixture."""
        for version in ("1", "1.1"):
            for mode in ("--tier1", "--tier2", None):
                with self.subTest(version=version, mode=mode or "default"):
                    p = self.root / f"c-{version}-{mode}.txt"
                    p.write_text(self._receipt(version).replace(
                        f"  1  READ  a.txt  sha256:{H64}\n  (none)\n",
                        f"  1  READ  a.txt  sha256:{H64}\n", 1))
                    args = [a for a in (mode, "--root", str(self.root), str(p)) if a]
                    out = run(*args)
                    self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
