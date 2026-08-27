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

  * AC-1 second half   — the `return-convention.md:105`/`:257` retraction is
                         gated on GH #530 (§3.1 clause 2, second ordering gate).
                         §4 of the design doc names those two rows `:104`/`:256`;
                         AC-2's own edit to `:68` shifted every anchor below it
                         down by one, so the LIVE lines are `:105`/`:257`.
  * AC-3, AC-5         — moved to GH #530 with the census floor (tombstones).
  * AC-4               — the C walk's 42→14 / 96→2 reproduction. C is not built
                         and is #530-gated (OQ-7, §3.1 clause 2); the corpora it
                         is measured on are machine-local and not CI-gated (§6).
  * AC-6 T1, T1-neg,
    T3, T7 leg 1       — all describe C's bounded within-root walk (#530-gated).
                         T7 **leg 2** is NOT among them and IS covered here.
  * AC-6 T11           — scheduling is OQ-9, undecided in the document.
  * AC-8               — the fourteen prose sites are edited "in the same change
                         that lands the mechanism", i.e. with C (#530-gated).
  * AC-9               — explicitly "text only ... does not land in this
                         ticket's own implementing change".
  * AC-7               — corrections posted to GitHub issue #488. Not
                         automatable from the test suite; MANUAL verification.

Covered here: AC-1 first half (the tautology), AC-2 (the lexical grammar plus
I8/T10 across all three parsers) and AC-6's T2, T6 and T7 leg 2.
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
WALK_PREFIX = "RESOLVED-BY-WALK:"


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


def walk_notes(stderr):
    """The RESOLVED-BY-WALK advisory lines on a run's stderr, in order."""
    return [l for l in stderr.splitlines()
            if l.strip().startswith(WALK_PREFIX)]


def census(stderr):
    """The single TIER2-COVERAGE: line, or '' when the run emitted none."""
    for l in stderr.splitlines():
        if l.strip().startswith("TIER2-COVERAGE:"):
            return l.strip()
    return ""


def _plant_git_dir(repo):
    """Plant a SHAPE-VALID `.git` directory, making `repo` a git toplevel.

    Mirrors `scripts/test_rcpt_verify.py`'s helper of the same name: SIEGE-C1
    made `_git_toplevel` reject any ancestor entry merely NAMED `.git`, so a
    bare `mkdir .git` is not a marker. These are the three entries `git init`
    always creates. No `git` binary is invoked, so the fixture is hermetic."""
    g = pathlib.Path(repo) / ".git"
    (g / "objects").mkdir(parents=True)
    (g / "refs").mkdir()
    (g / "HEAD").write_text("ref: refs/heads/main\n")
    return g


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
    SECOND half (the `return-convention.md:105`/`:257` retraction — §4's
    `:104`/`:256` rows, renumbered by AC-2's own `:68` edit) is #530-gated
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
        (`test_rcpt_verify.py:5982-6055`) structurally unreachable while leaving
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
    path-shaped raise (`rcpt_verify.py:1800-1809`) and lets the name degrade to
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
        suppressing a TRUE advisory (61 flat / 79 nested such suppressions
        across the three frozen corpora — the figures `_emit_provenance_notes`'s
        own docstring carries). The larger 66/89 reading counts a
        no-raise-and-abandon model; §3.4's truncation rule already keeps a TRACE
        entry matching an UNEVALUATED artifact silent, so those runs are not
        suppressions this key is answerable for. Silence is the failure direction
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
    `notes += tier2_artifacts(...)` (`:3983`), which never executes on a raise,
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


class TestTheEmitterCannotMaskAnInFlightRaise(_RootCase):
    """AC-6 T2, leg 6's other edge — the emitter runs from `tier2_artifacts`'s
    `finally:`, so ANY exception IT raises there REPLACES the in-flight one per
    Python's finally-block semantics: a genuine `--strict` `LintError` would be
    destroyed and reported as `'NoneType' object is not iterable`.

    Broken copy: `for entry in trace:` without the `or []` guard. That copy has
    SHIPPED once already — cleanup commit `270c656` deleted the guard and the
    whole suite stayed green, both before and after it was restored, so nothing
    but this test stands between the guard and a second removal. `trace` is
    public-API-supplied (~40 direct call sites, no type enforcement), which is
    why `None` is reachable by ordinary API misuse even though the sole
    production call site passes `parse_trace`'s list. Driven by a DIRECT call
    because the CLI cannot reach the hazard — that is the point of pinning it."""

    ART = {"docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"}}

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    def test_a_none_trace_does_not_mask_an_in_flight_lint_error(self):
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART, None, [self.root], True,
                                    None, None, [])
        # The message identifies the REAL failure, not a TypeError from the
        # finally: that took its place.
        self.assertIn("absent under all bases", str(caught.exception))

    def test_the_control_shows_the_same_call_really_reaches_the_emitter(self):
        """Non-vacuity: the identical call with a well-formed `trace` raises the
        SAME `LintError` and the emitter demonstrably ran (it appended its note
        from inside the `finally:`). So the leg above is about the guard, not
        about the emitter being skipped on this path."""
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                self.ART, [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                [self.root], True, None, None, notes_out)
        self.assertIn("absent under all bases", str(caught.exception))
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/x.md "
                          "(declared in TRACE, not verified)"])


class TestANonStringArtifactsKeyCannotMaskAnInFlightRaise(_RootCase):
    """AC-6 T2, leg 6 again — the SECOND, independently reachable instance of the
    same finally-block masking hazard the class above pins.

    `_emit_provenance_notes`'s `trace or []` guard (and its `notes_out is None`
    early return) close the hazard only for what happens INSIDE the helper. The
    unevaluated-basenames set-comprehension is an ARGUMENT of that call, so Python
    evaluates it BEFORE the helper is entered and neither guard covers it: it runs
    naked inside `tier2_artifacts`'s `finally:`.

    Broken copy: `{n.rsplit("/", 1)[-1] for n in artifacts if n not in evaluated}`.
    Measured on `00bfd2e` (pre-fix), a non-string ARTIFACTS key replaced the
    in-flight `Tier-2 --strict: ... absent under all bases` LintError with
    `AttributeError: 'int' object has no attribute 'rsplit'` — for BOTH
    `notes_out=None` AND `notes_out=[]`, i.e. including the shape the sole
    production call site passes, which is why the helper-side guards were not
    enough. `artifacts` is public-API-supplied (~40 direct call sites, no type
    enforcement) exactly as `trace` is. Driven by a DIRECT call because the CLI
    cannot reach the hazard — that is the point of pinning it."""

    #  ORDER IS LOAD-BEARING: the path-shaped absent name must come FIRST so the
    #  --strict raise truncates the loop and leaves the bad key UNEVALUATED, which
    #  is the only branch of the comprehension that reaches `.rsplit`.
    ART = {"docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"},
           42: {"hash": H64, "size": "10"}}
    TRACE = [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}]

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    def test_it_does_not_mask_on_the_production_notes_requested_shape(self):
        """The leg the helper's own guards CANNOT cover: `notes_out` is a real
        list, so the helper runs — and the comprehension ran before it either way.
        Carries its own non-vacuity control: the emitter demonstrably executed
        from inside the `finally:` on this very call, so a green result here is
        about the argument expression, not about the emitter being skipped."""
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART, self.TRACE, [self.root], True,
                                    None, None, notes_out)
        self.assertIn("absent under all bases", str(caught.exception))
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/x.md "
                          "(declared in TRACE, not verified)"])

    def test_the_whole_finally_body_is_skipped_when_no_notes_were_asked_for(self):
        """Pins the `if notes_out is not None:` half directly. The `str()` half
        alone already makes the two legs above green, so without this leg the
        guard is an UNPINNED line — and the docstring of the class above records
        what happens to unpinned guards here (cleanup commit `270c656` deleted
        one and the whole suite stayed green).

        Stand-in for "the body ran": an emitter that RECORDS. It used to be one
        that RAISES, which #488 round-3/S1 retired: the call site is now itself
        wrapped in `except Exception: pass` (the outer half of the structural
        no-raise guarantee), so a raising stand-in is swallowed there and can no
        longer tell "skipped" from "called". A recorder is immune to that and
        detects the same mutation — delete the guard and the `notes_out=None` leg
        below records a call."""
        calls = []
        real = self.rv._emit_provenance_notes
        self.rv._emit_provenance_notes = lambda *a, **kw: calls.append(a)
        self.addCleanup(setattr, self.rv, "_emit_provenance_notes", real)

        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART, self.TRACE, [self.root], True,
                                    None, None, None)
        self.assertIn("absent under all bases", str(caught.exception))
        self.assertEqual(calls, [], "the emitter ran for a caller that asked "
                                    "for no notes")

        # Non-vacuity: the identical call that DOES ask for notes reaches the
        # patched emitter, so the leg above is about the guard, not about a
        # monkeypatch that never took.
        with self.assertRaises(self.rv.LintError):
            self.rv.tier2_artifacts(self.ART, self.TRACE, [self.root], True,
                                    None, None, [])
        self.assertEqual(len(calls), 1, "the monkeypatch never took")

    def test_it_does_not_mask_when_the_caller_wants_no_notes(self):
        """`notes_out=None` — the ~40 --eval/--selftest-shaped call sites. The
        real failure must reach them too, rather than an AttributeError raised by
        work whose only product they asked not to receive."""
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART, self.TRACE, [self.root], True,
                                    None, None, None)
        self.assertIn("absent under all bases", str(caught.exception))


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


# --------------------------------------------------------------------------
# ADVERSARIAL (Task 4) — five failure modes probed after the two masking
# hazards of rounds 1-2 were fixed. Written to BREAK the shipped build.
# --------------------------------------------------------------------------
class TestAMalformedTraceEntryCannotMaskAnInFlightRaise(_RootCase):
    """ADVERSARIAL 1 — the THIRD instance of the finally-block masking hazard.

    `_emit_provenance_notes`'s `trace or []` guard hardens the CONTAINER; the
    ELEMENTS are read naked (`entry["verb"]`, `entry["args"].split()`) and that
    read still happens inside `tier2_artifacts`'s `finally:`, where any exception
    REPLACES the in-flight one. A `trace` list holding an entry that is not a
    two-key `{"verb": str, "args": str}` dict therefore destroys a genuine
    `Tier-2 --strict: ... absent under all bases` LintError exactly as a `None`
    `trace` did before `00bfd2e`.

    The reachability argument is the one the two shipped guards make for
    themselves, verbatim: `trace` is public-API-supplied (~40 direct call sites,
    no type enforcement). If that argument licenses the `or []`, it licenses this
    leg too — a caller who can pass `None` can pass `[None]`."""

    ART = {"docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"}}

    #  Each shape is ordinary API misuse, not a contrived object: a hand-built
    #  entry missing a key, a raw TRACE line never run through `parse_trace`, and
    #  a `None` where an entry was expected.
    #
    #  The three `verb is ...` shapes are the FOURTH instance of this hazard
    #  (#488 round-3/S1) and they get in through the guard written for the first
    #  three: `entry.get("verb") not in _PROVENANCE_VERBS` HASHES the verb,
    #  because `_PROVENANCE_VERBS` is a frozenset. A `list` or a `dict` verb
    #  raises `TypeError: unhashable type` at the membership test itself, inside
    #  the caller's `finally:`. `set` is here as the control that shows the
    #  survivor was INCIDENTAL, not designed: CPython special-cases `set` on the
    #  left of `in` against a `frozenset` and silently converts it, so that one
    #  shape happened to be green while its two siblings were not — a distinction
    #  no reader of this code could have predicted, and the reason the fix is a
    #  structural guard rather than a fifth type-check.
    SHAPES = {
        "entry missing the args key": [{"n": 1, "verb": "READ"}],
        "entry missing the verb key": [{"n": 1, "args": "x.md"}],
        "entry is a raw unparsed line": ["1 READ x.md"],
        "args is None": [{"n": 1, "verb": "READ", "args": None}],
        "entry is None": [None],
        "verb is an unhashable list": [{"n": 1, "verb": [], "args": "x.md"}],
        "verb is an unhashable dict": [{"n": 1, "verb": {}, "args": "x.md"}],
        "verb is a set": [{"n": 1, "verb": set(), "args": "x.md"}],
    }

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    def test_no_malformed_entry_shape_replaces_the_real_lint_error(self):
        for label, trace in self.SHAPES.items():
            with self.subTest(shape=label):
                with self.assertRaises(self.rv.LintError) as caught:
                    self.rv.tier2_artifacts(self.ART, trace, [self.root], True,
                                            None, None, [])
                self.assertIn("absent under all bases", str(caught.exception))

    def test_the_control_shows_the_same_call_really_reaches_the_emitter(self):
        """Non-vacuity: a well-formed `trace` raises the SAME LintError and the
        emitter demonstrably ran from inside the `finally:`, so a red leg above
        is about the element reads and not about the emitter being skipped."""
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                self.ART, [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                [self.root], True, None, None, notes_out)
        self.assertIn("absent under all bases", str(caught.exception))
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/x.md "
                          "(declared in TRACE, not verified)"])


class TestANonStringArtifactsKeyCannotCrashTheVerifiedPath(_RootCase):
    """ADVERSARIAL 2 — `0b45be2` hardened ONE of the two `.rsplit` sites this
    change added.

    The `finally:` twin got `str(n).rsplit(...)`. Its sibling in the loop body,
    `verified_bases.add(name.rsplit("/", 1)[-1])`, did not — and that line is
    NOT gated on `notes_out`, so it runs on every caller including the
    `notes_out=None` `--eval`/`--selftest` shape that asked for no notes at all.

    `PurePosixPath` is the demonstration because it is `os.PathLike`: it survives
    `resolve_base`, the read and the sha256 comparison, and only then hits
    `.rsplit`. Measured against `2457fa9` (pre-change), the identical call
    verified CLEANLY and returned `[]`, so this is a regression the change
    introduced, on the same public-API-supplied hostile-key class whose sibling
    site the shipped code already concedes is reachable."""

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        self.body = "hello\n"
        (self.root / "a.txt").write_text(self.body)
        self.art = {pathlib.PurePosixPath("a.txt"): {
            "hash": hashlib.sha256(self.body.encode()).hexdigest(),
            "size": str(len(self.body))}}
        self.trace = [{"n": 1, "verb": "READ", "args": "a.txt"}]

    def test_a_pathlike_key_still_verifies_when_no_notes_were_asked_for(self):
        """`notes_out=None`. These callers opted out of the advisory entirely;
        the advisory's bookkeeping must not be able to fail their run."""
        self.assertEqual(
            self.rv.tier2_artifacts(self.art, self.trace, [self.root], True,
                                    None, None, None), [])

    def test_a_pathlike_key_still_verifies_when_notes_were_asked_for(self):
        notes_out = []
        self.assertEqual(
            self.rv.tier2_artifacts(self.art, self.trace, [self.root], True,
                                    None, None, notes_out), [])

    def test_the_control_shows_the_str_key_spelling_verifies(self):
        """Non-vacuity: the same fixture keyed by `str` verifies and is silent,
        so the legs above are about the key TYPE and not about the fixture."""
        art = {str(k): v for k, v in self.art.items()}
        notes_out = []
        self.assertEqual(
            self.rv.tier2_artifacts(art, self.trace, [self.root], True,
                                    None, None, notes_out), [])
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)], [])


class TestAVerifiedSiblingCannotSilenceADeclaredUnverifiedName(_RootCase):
    """ADVERSARIAL 3 — the basename key's accepted collision is not confined to
    "a genuinely different file". It also fires on a name the run itself
    DECLARED and itself reported UNVERIFIABLE in the same breath.

    `TestTheNoteIsKeyedOnVerifiedBasenames`'s leg 5 pins that a TRACE entry
    naming an unresolved ARTIFACTS entry emits the note. That guarantee is
    defeated by ONE extra ARTIFACTS line the receipt author chooses freely: any
    real file whose basename collides. The run then prints
    `UNVERIFIABLE: b/x.md (no file under root)` and, on the very same stderr,
    stays silent about the TRACE entry that cites `b/x.md`.

    That makes the advisory OPTIONAL for its author, which for a mechanism whose
    stated job is closing grudge e0f0a6b75692 ("silence is not permitted") is the
    failure direction, not a corner of it. It is also cheap: the silencer must
    hash-verify, but the author owns the dispatch root and picks the name."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("a/x.md", "alpha\n")
        self.out = self.verify(receipt(
            artifacts=[("a/x.md", h, s), ("b/x.md", "b" * 64, "9")],
            trace=["READ  b/x.md"]))

    def test_the_run_says_out_loud_that_the_cited_name_is_unverified(self):
        """Non-vacuity: the run KNOWS. This is not a case where the information
        was unavailable — it is printed two lines away."""
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        self.assertIn("UNVERIFIABLE: b/x.md", self.out.stderr)

    def test_the_trace_citation_of_that_same_name_still_emits_the_note(self):
        emitted = notes(self.out.stderr)
        self.assertTrue(any("b/x.md" in n for n in emitted), self.out.stderr)

    def test_the_control_without_the_colliding_sibling_emits_the_note(self):
        """Non-vacuity: delete the sibling and the note returns, so the leg above
        is about the collision and not about the fixture never qualifying."""
        out = self.verify(receipt(artifacts=[("b/x.md", "b" * 64, "9")],
                                  trace=["READ  b/x.md"]),
                          name="control.txt")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(any("b/x.md" in n for n in notes(out.stderr)),
                        out.stderr)


class TestATrailingSlashArtifactNameCannotSilenceUnrelatedNames(_RootCase):
    """ADVERSARIAL 4 — `rsplit("/", 1)[-1]` maps every name ending in `/` to the
    EMPTY basename, and the empty basename is stored and matched like any other.

    `_trace_basename`'s `if not name: continue` screens the empty NAME; nothing
    screens the empty BASE. So a single verified `ARTIFACTS` entry spelled with a
    trailing slash (`x/` — accepted by `parse_artifacts`, and resolved and
    hash-verified by `resolve_base`, which normalises the slash away) puts `""`
    into `verified_bases`, and from then on EVERY `TRACE` name ending in `/`
    matches it — including names that resolve nowhere and share nothing with the
    declared artifact.

    A degenerate key that swallows a whole family of unrelated names is the same
    silence the note exists to prevent, reachable from one legal spelling."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("x", "body\n")
        self.out = self.verify(receipt(
            artifacts=[("x/", h, s)],
            trace=["READ  /secret/elsewhere/"]))

    def test_the_slashed_artifact_really_did_verify(self):
        """Non-vacuity: `x/` resolved AND hash-verified, so `""` is in
        `verified_bases` by the VERIFIED route, not by the truncation route."""
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        self.assertIn("artifacts 1/1", self.out.stderr)

    def test_an_unrelated_trace_name_ending_in_a_slash_still_emits_the_note(self):
        emitted = notes(self.out.stderr)
        self.assertTrue(any("/secret/elsewhere/" in n for n in emitted),
                        self.out.stderr)

    def test_the_control_without_the_trailing_slash_emits_the_note(self):
        """Non-vacuity: declare the same file as `x` and the note returns, so the
        leg above is about the empty basename and not about the TRACE name."""
        h, s = self.plant("x", "body\n")
        out = self.verify(receipt(artifacts=[("x", h, s)],
                                  trace=["READ  /secret/elsewhere/"]),
                          name="control.txt")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(any("/secret/elsewhere/" in n for n in notes(out.stderr)),
                        out.stderr)


class TestTheTruncationPartitionHoldsAtScale(_RootCase):
    """ADVERSARIAL 5 — the evaluated/unevaluated partition under a mid-loop raise
    with a large `ARTIFACTS` block.

    §3.4's truncation rule is a statement about two sets that are BOTH built
    incrementally inside the loop (`verified_bases`, `evaluated`) and consumed
    once in the `finally:`. With 2000 entries and the raise at entry 4, all three
    dispositions must be simultaneously right on one run: VERIFIED-before-the-
    raise silent, EVALUATED-but-not-verified audible, NEVER-REACHED silent, and a
    name in neither set audible."""

    N = 2000

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        body = "ok\n"
        h = hashlib.sha256(body.encode()).hexdigest()
        art = {}
        for i in range(3):
            self.plant(f"pre/v{i}.md", body)
            art[f"pre/v{i}.md"] = {"hash": h, "size": "3"}
        self.plant("boom.md", body)                 # resolves, hash MISMATCHES
        art["boom.md"] = {"hash": "b" * 64, "size": "3"}
        for i in range(self.N):
            art[f"later/u{i}.md"] = {"hash": H64, "size": "3"}
        self.art = art
        self.trace = [
            {"n": 1, "verb": "READ", "args": "pre/v0.md"},     # verified
            {"n": 2, "verb": "READ", "args": "boom.md"},       # evaluated, not verified
            {"n": 3, "verb": "READ", "args": "later/u5.md"},   # never reached
            {"n": 4, "verb": "READ", "args": "never/heard.md"}]  # in neither set

    def test_all_four_dispositions_are_right_on_one_truncated_run(self):
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.art, self.trace, [self.root], False,
                                    None, None, notes_out)
        # Non-vacuity: the run really was truncated, at the entry it was meant to
        # be truncated at.
        self.assertIn("boom.md sha256 mismatch", str(caught.exception))
        self.assertEqual(
            [n for n in notes_out if n.startswith(NOTE_PREFIX)],
            [f"{NOTE_PREFIX} boom.md (declared in TRACE, not verified)",
             f"{NOTE_PREFIX} never/heard.md (declared in TRACE, not verified)"])


# --------------------------------------------------------------------------
# ROUND-3 STRUCTURAL — the masking hazard as a CLASS, not as four instances.
# --------------------------------------------------------------------------
class TestTheEmitterCannotRaiseOutOfTheFinallyOnAnyShape(_RootCase):
    """ROUND-3/S1 + Minor-2 — `_emit_provenance_notes` is called from
    `tier2_artifacts`'s `finally:`, so its no-raise property is a CONTRACT, not a
    property that happens to hold for the shapes anyone has enumerated so far.
    Four point-patches had been spent on one shape each (`None` container,
    non-string ARTIFACTS key, malformed entry, unhashable verb) before the
    contract was made structural. These legs pin the contract itself: the shapes
    below are chosen because NO existing type-check anticipates them.

    `ART`'s single path-shaped absent name under `--strict` is the in-flight
    exception every leg must see survive."""

    ART = {"docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"}}

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    def _run(self, trace, notes_out=None, art=None):
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART if art is None else art, trace,
                                    [self.root], True, None, None,
                                    [] if notes_out is None else notes_out)
        self.assertIn("absent under all bases", str(caught.exception))

    def test_a_truthy_non_iterable_trace_does_not_replace_the_lint_error(self):
        """MINOR-2 — `trace or []` hardens the FALSY container only. `5` is
        truthy, so it walks straight through the `or` and the `for` statement's
        own `iter()` raises `TypeError: 'int' object is not iterable` inside the
        `finally:`. No per-entry guard can reach this: there is no entry yet."""
        for label, trace in (("int", 5), ("object", object()),
                             ("float", 1.5)):
            with self.subTest(shape=label):
                self._run(trace)

    def test_a_generator_that_raises_mid_iteration_loses_only_the_rest(self):
        """The other half of Minor-2: iteration can fail at ANY `next()`, not
        only at the first. The notes already collected must survive, and so must
        the in-flight LintError."""
        def _gen():
            yield {"n": 1, "verb": "READ", "args": "/elsewhere/one.md"}
            raise RuntimeError("iterator exploded mid-TRACE")

        notes_out = []
        self._run(_gen(), notes_out)
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/one.md "
                          "(declared in TRACE, not verified)"])

    def test_one_malformed_entry_does_not_cost_the_other_entries_their_notes(self):
        """The granularity claim. A whole-function wrapper would satisfy the
        no-raise contract and silently drop every note after the first bad
        element — silence bought by one malformed entry, which is the direction
        grudge e0f0a6b75692 forbids. Per-entry is why both guards exist."""
        notes_out = []
        self._run([{"n": 1, "verb": "READ", "args": "/elsewhere/one.md"},
                   {"n": 2, "verb": [], "args": "/elsewhere/boom.md"},
                   {"n": 3, "verb": "READ", "args": "/elsewhere/two.md"}],
                  notes_out)
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/one.md "
                          "(declared in TRACE, not verified)",
                          f"{NOTE_PREFIX} /elsewhere/two.md "
                          "(declared in TRACE, not verified)"])

    def test_a_hostile_entry_object_cannot_raise_out_of_the_emitter(self):
        """The shape no type-check anticipates: `isinstance(entry, dict)` is
        TRUE for a dict subclass, and `.get` is overridable. This is the leg that
        distinguishes a structural guard from a fifth point-patch — it is green
        only because nothing is enumerated."""
        class _Hostile(dict):
            def get(self, *a, **kw):
                raise RuntimeError("entry.get exploded")

        notes_out = []
        self._run([_Hostile(verb="READ", args="x.md"),
                   {"n": 2, "verb": "READ", "args": "/elsewhere/after.md"}],
                  notes_out)
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/after.md "
                          "(declared in TRACE, not verified)"])

    def test_the_emitter_itself_swallows_a_non_iterable_trace(self):
        """Pins the emitter's OWN whole-loop guard, called DIRECTLY rather than
        through `tier2_artifacts`. Necessary because the call site now carries a
        wrapper of its own, which would keep every leg above green even with the
        emitter's guard deleted — i.e. the emitter's guard would be an UNPINNED
        line, and this file's `270c656` precedent records what happens to those.
        The contract is the module-level function's, not the call site's."""
        notes_out = []
        self.assertIsNone(self.rv._emit_provenance_notes(
            5, set(), set(), set(), set(), notes_out))
        self.assertEqual(notes_out, [])
        # Non-vacuity: the same direct call on a well-formed trace does emit.
        self.rv._emit_provenance_notes(
            [{"n": 1, "verb": "READ", "args": "q.md"}],
            set(), set(), set(), set(), notes_out)
        self.assertEqual(notes_out,
                         [f"{NOTE_PREFIX} q.md (declared in TRACE, not "
                          "verified)"])

    def test_an_artifacts_key_whose_str_raises_cannot_mask_the_lint_error(self):
        """Pins the CALL-SITE wrapper specifically. A call's ARGUMENTS are
        evaluated before the callee is entered, so the two set comprehensions in
        the `finally:` run OUTSIDE the emitter's own guarantee — no guard inside
        the emitter can ever cover them. This is the same structure as the
        already-pinned non-string-key leg, one level further out: `str()` fixed
        `.rsplit` on an `int`, and nothing fixed `str()` itself.

        ORDER IS LOAD-BEARING: the absent path-shaped name first, so `--strict`
        truncates and leaves the hostile key in the UNEVALUATED comprehension."""
        class _RaisingStr:
            def __str__(self):
                raise RuntimeError("__str__ exploded")

        art = dict(self.ART)
        art[_RaisingStr()] = {"hash": H64, "size": "10"}
        self._run([{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}], art=art)

    def test_the_control_shows_a_well_formed_trace_still_emits(self):
        """Non-vacuity for every leg above: the guards did not turn the emitter
        into a no-op."""
        notes_out = []
        self._run([{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                  notes_out)
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} /elsewhere/x.md "
                          "(declared in TRACE, not verified)"])


class TestNoCallerSuppliedParameterCanMaskAnInFlightRaise(_RootCase):
    """ROUND-4/S1 — the FIFTH and (intended) LAST instance of the class the four
    classes above pin one shape at a time, stated at the FUNCTION level instead.

    `tier2_artifacts` takes THREE caller-controlled parameters with no type
    enforcement — `trace`, `artifacts` and `notes_out` (~40 direct call sites,
    all positional). The first two were hardened one instance at a time; the
    THIRD was never tested at all, and it is read while an exception is IN
    FLIGHT: the `except BaseException:` mirror arm does `notes_out.extend(notes)`
    before re-raising, so a `notes_out` that is not a list REPLACES the real
    verdict exactly as a `None` `trace` did in the `finally:`. Measured on
    `3749606` (pre-fix): `()`, `0`, an object without `.extend`, and an object
    whose `.extend` raises all destroyed the genuine `Tier-2 --strict: ... absent
    under all bases` LintError, reporting the shape error in its place.

    The property under test is therefore not "this call site is guarded" but
    "NO hostile shape on ANY of the three parameters, alone or together, can
    replace the exception that ended the run" — which is why the third leg
    drives all three at once. Driven by DIRECT calls because the CLI cannot
    reach the hazard; that is the point of pinning it."""

    #  ORDER IS LOAD-BEARING: the bare basename first, so it appends an
    #  UNVERIFIABLE note to the RETURN-value list before the path-shaped name
    #  raises — that note is what the mirror arm exists to mirror, so a `notes`
    #  list that is empty at the raise would make every leg here vacuous.
    ART = {"bare-basename.md": {"hash": H64, "size": "10"},
           "docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"}}
    TRACE = [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}]

    class _NoExtend:
        """Ordinary API misuse, not a contrived object: any caller who passed the
        wrong out-parameter (a `set`, a `_Coverage`, a namedtuple) lands here."""

    class _RaisingExtend:
        def extend(self, items):
            raise RuntimeError("notes_out.extend exploded")

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()

    def _run(self, notes_out, art=None, trace=None):
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART if art is None else art,
                                    self.TRACE if trace is None else trace,
                                    [self.root], True, None, None, notes_out)
        self.assertIn("absent under all bases", str(caught.exception))

    def test_no_hostile_notes_out_shape_replaces_the_real_lint_error(self):
        for label, notes_out in (("tuple", ()), ("int", 0),
                                 ("object without .extend", self._NoExtend()),
                                 ("object whose .extend raises",
                                  self._RaisingExtend())):
            with self.subTest(shape=label):
                self._run(notes_out)

    def test_all_three_caller_supplied_parameters_hostile_at_once(self):
        """The function-level statement. Each parameter's guard lives in a
        DIFFERENT block (`finally:` wrapper, per-entry guard, mirror arm), and
        the arms run in sequence on one raise — so a fix that closed one by
        breaking another's ordering would pass the single-parameter legs and
        fail here."""
        class _RaisingStr:
            def __str__(self):
                raise RuntimeError("__str__ exploded")

        art = dict(self.ART)
        art[_RaisingStr()] = {"hash": H64, "size": "10"}
        self._run((), art=art, trace=[None, 5])

    def test_the_mirror_arm_still_delivers_the_notes_it_exists_for(self):
        """Non-vacuity for every leg above, and the mutation this fix could
        otherwise have introduced: an envelope that swallowed the arm's WORK as
        well as its exceptions would make all three legs green while silently
        discarding the notes the arm was added to save — the fail-open direction
        grudge `e0f0a6b75692` forbids. A real list still receives both this
        leg's own UNVERIFIABLE note (via the mirror arm) and the
        PROVENANCE-ONLY note (via the `finally:`)."""
        notes_out = []
        self._run(notes_out)
        self.assertEqual(notes_out,
                         ["UNVERIFIABLE: bare-basename.md (no file under root)",
                          f"{NOTE_PREFIX} /elsewhere/x.md (declared in TRACE, "
                          "not verified)"])


class TestTheTruncationRuleHoldsForSlashSuffixedNames(_RootCase):
    """ROUND-3/Minor-3 — F4's read-site guard (`base` must be TRUTHY to match)
    and §3.4's truncation rule collided on one legal spelling.

    Every name ending in `/` has an EMPTY basename, and F4 made an empty basename
    match nothing — which is right for `verified_bases` (that was F4's whole
    point) and WRONG for `unevaluated_bases`, because there the empty basename was
    the only carrier of the truncation rule for that spelling. A `/`-suffixed
    ARTIFACTS entry the truncated loop NEVER REACHED could therefore not be
    excluded, and the TRACE entry citing it verbatim emitted `PROVENANCE-ONLY` on
    a run that had not yet had the CHANCE to verify it — the docstring's stated
    invariant ("emits NOTHING; its match may yet have arrived") violated silently.

    Fixed the way F3 already fixes the mirror-image case: carry the FULL NAMES.

    ORDER IS LOAD-BEARING — the path-shaped absent name comes FIRST so `--strict`
    truncates the loop and leaves `x/` unevaluated."""

    ART = {"docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"},
           "x/": {"hash": H64, "size": "5"}}

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        self.plant("x", "body\n")

    def _run(self, trace, art=None):
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(self.ART if art is None else art, trace,
                                    [self.root], True, None, None, notes_out)
        # Non-vacuity: the run really was truncated, at the entry it was meant
        # to be truncated at, so `x/` really is UNEVALUATED.
        self.assertIn("absent under all bases", str(caught.exception))
        return [n for n in notes_out if n.startswith(NOTE_PREFIX)]

    def test_a_never_reached_slash_suffixed_name_stays_silent(self):
        self.assertEqual(
            self._run([{"n": 1, "verb": "READ", "args": "x/"}]), [])

    def test_an_undeclared_slash_suffixed_name_still_speaks(self):
        """Non-vacuity: the silence above is about THIS declared unevaluated
        name, not about `/`-suffixed TRACE names as a family — F4's finding was
        precisely that swallowing the whole family is the failure mode."""
        self.assertEqual(
            self._run([{"n": 1, "verb": "READ", "args": "/secret/elsewhere/"}]),
            [f"{NOTE_PREFIX} /secret/elsewhere/ "
             "(declared in TRACE, not verified)"])

    def test_the_same_name_speaks_once_the_loop_actually_reaches_it(self):
        """Non-vacuity in the other direction: `x/` is silent because it was
        NEVER EVALUATED, not because `/`-suffixed names can never emit. Put it
        first and it is evaluated, hash-mismatches, and gets its note."""
        art = {"x/": {"hash": H64, "size": "5"},
               "docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"}}
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(art, [{"n": 1, "verb": "READ", "args": "x/"}],
                                    [self.root], True, None, None, notes_out)
        self.assertIn("sha256 mismatch", str(caught.exception))
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} x/ (declared in TRACE, not verified)"])


class TestTwoArtifactsKeysWithTheSameSpellingDoNotMerge(_RootCase):
    """ROUND-3/Minor-4 — the exact-name override was computed as
    `{str(n) for n in evaluated} - {str(n) for n in verified}`, i.e. as a
    difference of SPELLINGS. Two DISTINCT `ARTIFACTS` dict keys can share a
    spelling (`PurePosixPath("a.txt")` and `"a.txt"` are different keys, equal
    strings), so ONE of them verifying deleted the override for the OTHER, which
    had not — and the basename key then silenced it too. Silence bought by a
    spelling coincidence is the direction grudge e0f0a6b75692 forbids.

    Fixed by subtracting the raw KEYS (always hashable — they are dict keys) and
    applying `str()` once, afterwards, to what survives.

    Not receipt-author-reachable (`parse_artifacts` only ever produces `str`
    keys); reachable through the ~40 direct API call sites, exactly as every
    other leg in this section is."""

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        body = "hello\n"
        (self.root / "a.txt").write_text(body)
        self.good = hashlib.sha256(body.encode()).hexdigest()
        self.size = str(len(body))

    def test_the_unverified_twin_keeps_its_note(self):
        art = {pathlib.PurePosixPath("a.txt"): {"hash": self.good,
                                                "size": self.size},
               "a.txt": {"hash": "b" * 64, "size": self.size}}
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                art, [{"n": 1, "verb": "READ", "args": "a.txt"}],
                [self.root], False, None, None, notes_out)
        # Non-vacuity: the second key really was evaluated and really did fail.
        self.assertIn("sha256 mismatch", str(caught.exception))
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)],
                         [f"{NOTE_PREFIX} a.txt (declared in TRACE, not "
                          "verified)"])

    def test_the_control_shows_the_verified_twin_alone_is_silent(self):
        """Non-vacuity: with only the verifying key declared, the same TRACE
        citation is correctly silent — the leg above is about the collision, not
        about the fixture always emitting."""
        art = {pathlib.PurePosixPath("a.txt"): {"hash": self.good,
                                                "size": self.size}}
        notes_out = []
        self.assertEqual(
            self.rv.tier2_artifacts(
                art, [{"n": 1, "verb": "READ", "args": "a.txt"}],
                [self.root], False, None, None, notes_out), [])
        self.assertEqual([n for n in notes_out if n.startswith(NOTE_PREFIX)], [])


# --------------------------------------------------------------------------
# AC-6 T7 leg 2 — a BELOW-TOP-LEVEL clause-1 resolution is counted.
#
# §3.1 clause 2 keys `RESOLVED-BY-WALK:` and its `resolved-by-walk` census
# sub-count on resolution DEPTH, not on which clause resolved. Leg 1 (a name
# only C's walk finds) is #530-gated and is NOT tested here. Leg 2 is: §3.4
# move 1's own recommended remedy — a root-relative citation one directory
# down, `out-N/round-N-findings.md` — resolves by clause 1's literal join and
# MUST emit the identical note and bump the identical counter, with no walk
# involved. The broken copy §5 names for this leg is a build that fires the
# note on walk resolutions only, which lets move 1's recommended citation
# resolve clean and silent — the fail-open §3.4 channel 2 exists to prevent.
# --------------------------------------------------------------------------
class TestABelowTopLevelResolutionIsCounted(_RootCase):
    """AC-6 T7 leg 2. Fixture is move 1's own recommended citation form."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("out-9/round-9-findings.md", "# findings\nfatal=0\n")
        self.out = self.verify(receipt(
            artifacts=[("out-9/round-9-findings.md", h, s)],
            trace=[f"WROTE  {self.root}/out-9/round-9-findings.md  sha256:{h}"]))

    def test_the_run_completes(self):
        # Non-vacuity: the note is an advisory, not a failure.
        self.assertEqual(self.out.returncode, 0, self.out.stderr)

    def test_a_below_top_level_clause_one_resolution_emits_the_note(self):
        """One note per LEG that resolved the name, each naming the form THAT
        leg was given — the ARTIFACTS entry's bare relative path, and the
        witness leg's absolute cited form. §3.2 mandates the two forms differ
        by design, so a build emitting one note here has gone silent on a leg."""
        self.assertEqual(
            walk_notes(self.out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)",
             f"RESOLVED-BY-WALK: {self.root}/out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"],
            self.out.stderr)

    def test_the_census_carries_a_resolved_by_walk_sub_count(self):
        """PER-LEG, like every other _COV_COUNTERS member: `ambiguous`,
        `unreached` and `not-reachable` are all bumped from both
        `tier2_artifacts` and `tier2_witness` for the same file, because the
        census's unit is a CITED NAME ON A LEG (which is why `artifacts <v>/<a>`
        and `witness <v>/<a>` are separate) and not a file. This fixture cites
        the one file on both legs, so the count is 2."""
        self.assertIn("resolved-by-walk 2", census(self.out.stderr),
                      self.out.stderr)

    def test_the_sub_count_is_reported_beside_the_floor_and_not_summed_into_it(self):
        # §3.1 clause 2: reported, NOT summed into `unreached`/`not-reachable`.
        # Whether it is ever summed is OQ-7, on #530.
        c = census(self.out.stderr)
        self.assertIn("unreached 0", c, c)
        self.assertIn("not-reachable 0", c, c)
        self.assertIn("artifacts 1/1", c, c)


class TestTheWalkNoteSurvivesATruncatedRun(_RootCase):
    """AC-6 T7 leg 2, truncation leg — the mirror of T2's leg 6, and the pin
    that round 2's build failed.

    What this test pins is the PROPERTY — on a run truncated by a later
    entry's raise, the earlier name's note is still on stderr and the census
    agrees with it — not the CHANNEL that provides it. On the shipped build
    the property has two independent providers: the direct `notes_out` routing
    at the emission site, and round-4-of-this-gate's S1 `except BaseException:`
    arm (`tier2_artifacts`), which mirrors the leg's own `notes` onto
    `notes_out` on ANY raise. So a build that appends the walk note to
    `tier2_artifacts`'s RETURN VALUE instead of `notes_out` is NOT
    distinguishable here: the rescue arm carries it to stderr anyway and this
    test — and both suites — stay green. Task 7's DEC-31 row 12 discriminates
    that channel only because its mutant copy ALSO removes the rescue arm,
    reproducing the pre-S1 shape; against that copy this test is ONE OF FIVE
    that go red — one of the TWO the channel change itself accounts for.
    Measured on the two mutants separately, both suites, on this commit: the
    arm removal ALONE (channel intact) reddens three, none of them about this
    note — `TestNoCallerSuppliedParameterCanMaskAnInFlightRaise`'s mirror-arm
    pin and both of `TestTheNoteSurvivesATruncatedRun`'s. The channel change
    ALONE (arm intact) reddens NONE, which is the paragraph above restated as a
    measurement. Only the two together reach this test and
    `TestTheArtifactsLegsWalkNoteSurvivesTheStrictAmbiguityRaise`'s
    `test_the_strict_raise_does_not_silence_them`. `test_rcpt_verify.py` stays
    green on all three mutants."""

    def test_a_later_hash_mismatch_does_not_silence_the_earlier_walk_note(self):
        h, s = self.plant("out-9/round-9-findings.md", "# findings\nfatal=0\n")
        body = "disk content\n"
        self.plant("mismatch.md", body)
        out = self.verify(receipt(
            artifacts=[("out-9/round-9-findings.md", h, s),
                       ("mismatch.md", "d" * 64, str(len(body)))],
            trace=[f"WROTE  {self.root}/out-9/round-9-findings.md  sha256:{h}"]),
            name="walk-trunc.txt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("sha256 mismatch", out.stderr)
        # The FIRST entry resolved below top level and hash-matched before the
        # SECOND truncated the loop; its note must still be on the channel, and
        # the census must agree with it rather than contradict it.
        self.assertEqual(
            walk_notes(out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"],
            out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)


class TestTheWitnessLegsWalkNoteSurvivesTheStrictAmbiguityRaise(_RootCase):
    """AC-6 T7 leg 2, witness-leg truncation leg — round 3's S1.

    `--strict` is the MANDATED invocation (`quality-gate/SKILL.md:30`), and the
    witness leg's ambiguity check RAISES under it. §3.1 clause 2 binds on
    RESOLUTION, not on survival: the name DID resolve below top level, so the
    note and the counter are owed on that run too.

    Broken copy (DEC-31 row 13): a build siting the witness-leg emission AFTER
    the ambiguity block — round 3's own placement. Measured on it, same fixture,
    one flag apart: without `--strict`, `resolved-by-walk 1` plus the note; with
    `--strict`, `resolved-by-walk 0 ... partial` and NO note. That is the
    silent-on-a-truncated-run shape §3.4 channel 2 exists to arrest, reached
    through the flag every real run sets.

    The fixture is witness-leg-only by construction: `ARTIFACTS` is `(none)`, so
    the artifacts leg cannot raise first and the two legs' notes cannot be
    confused for one another."""

    def setUp(self):
        super().setUp()
        self.other = pathlib.Path(self.td.name) / "second-root"
        (self.other / "out-9").mkdir(parents=True)
        body = "# findings\nfatal=0\n"
        self.plant("out-9/round-9-findings.md", body)
        (self.other / "out-9/round-9-findings.md").write_text(body)
        self.h = hashlib.sha256(body.encode()).hexdigest()
        self.rcpt = receipt(
            trace=[f"WROTE  out-9/round-9-findings.md  sha256:{self.h}"])

    def _run(self, *extra):
        return self.verify(self.rcpt, *extra, "--root", str(self.other))

    def test_without_strict_the_note_and_the_counter_both_fire(self):
        """Non-vacuity: the ambiguity is real and the name resolves anyway."""
        out = self._run()
        self.assertIn("ambiguous 1", census(out.stderr), out.stderr)
        self.assertEqual(
            walk_notes(out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"], out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)

    def test_the_strict_raise_does_not_silence_them(self):
        out = self._run("--strict")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("is ambiguous across roots", out.stderr)
        self.assertEqual(
            walk_notes(out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"], out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)


class TestTheArtifactsLegsWalkNoteSurvivesTheStrictAmbiguityRaise(_RootCase):
    """AC-6 T7 leg 2, artifacts-leg ambiguity-truncation leg — round-1-of-this-
    gate S2, the exact mirror of the witness-leg class above.

    The artifacts leg has the SAME siting obligation as the witness leg: its
    emission is placed BEFORE the `if len(found) > 1:` ambiguity block, which
    RAISES under `--strict` — the MANDATED invocation
    (`quality-gate/SKILL.md:30`). §3.1 clause 2 binds on RESOLUTION, not on
    survival: the name DID resolve below top level, so the note and the counter
    are owed on that run too. Until this class existed the obligation was
    unpinned on this leg: a build emitting after the raise (or routing the note
    through the return value on this ordering) left both suites green.

    The fixture is artifacts-leg-only by construction: the ARTIFACTS name is
    the ambiguous below-top-level one, while TRACE names a DIFFERENT file at
    the root's own top level, planted under one root only — so the witness leg
    contributes neither a walk note nor an ambiguity, and the two legs' notes
    cannot be confused for one another."""

    def setUp(self):
        super().setUp()
        self.other = pathlib.Path(self.td.name) / "second-root"
        (self.other / "out-9").mkdir(parents=True)
        body = "# findings\nfatal=0\n"
        self.h, self.size = self.plant("out-9/round-9-findings.md", body)
        (self.other / "out-9/round-9-findings.md").write_text(body)
        th, _ = self.plant("top.md", "top\n")
        self.rcpt = receipt(
            artifacts=[("out-9/round-9-findings.md", self.h, self.size)],
            trace=[f"WROTE  {self.root}/top.md  sha256:{th}"])

    def _run(self, *extra):
        return self.verify(self.rcpt, *extra, "--root", str(self.other))

    def test_without_strict_the_note_and_the_counter_both_fire(self):
        """Non-vacuity: the ambiguity is real and the name resolves anyway."""
        out = self._run()
        self.assertIn("ambiguous 1", census(out.stderr), out.stderr)
        self.assertEqual(
            walk_notes(out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"], out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)

    def test_the_strict_raise_does_not_silence_them(self):
        out = self._run("--strict")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("is ambiguous across roots", out.stderr)
        self.assertEqual(
            walk_notes(out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"], out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)


class TestATopLevelResolutionIsNotCounted(_RootCase):
    """The discriminator for the depth key. A name resolving AT a probed root's
    top level is not a below-top-level resolution and must stay silent and
    uncounted; a build that fires on every resolution is as blind as one that
    fires on none."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("round-9-findings.md", "# findings\nfatal=0\n")
        self.out = self.verify(receipt(
            artifacts=[("round-9-findings.md", h, s)],
            trace=[f"WROTE  {self.root}/round-9-findings.md  sha256:{h}"]))

    def test_the_run_completes(self):
        self.assertEqual(self.out.returncode, 0, self.out.stderr)

    def test_no_note_is_emitted(self):
        self.assertEqual(walk_notes(self.out.stderr), [], self.out.stderr)

    def test_the_sub_count_stays_zero(self):
        self.assertIn("resolved-by-walk 0", census(self.out.stderr),
                      self.out.stderr)


class TestASecondNestedRootDoesNotSilenceTheCounter(_RootCase):
    """AC-6 T7 leg 2, PER-ROOT depth key (round-5 F2).

    §3.1 clause 2 fires when a cited name resolves below *A ROOT's* top level —
    existential over the supplied roots. The broken copy (DEC-31 row 14) keys
    the depth check on the shallowest relpath across ALL supplied roots and
    their git toplevels at once, so a second, NESTED `--root` silently zeroes
    both the note and the counter for a name that still resolves below the
    first root's top level. Same receipt, one extra flag apart."""

    def setUp(self):
        super().setUp()
        h, s = self.plant("out-9/round-9-findings.md", "# findings\nfatal=0\n")
        self.rcpt = receipt(
            artifacts=[("out-9/round-9-findings.md", h, s)],
            trace=[f"WROTE  {self.root}/out-9/round-9-findings.md  sha256:{h}"])
        self.nested = self.verify(self.rcpt, "--root", str(self.root / "out-9"))

    def test_the_run_completes(self):
        self.assertEqual(self.nested.returncode, 0, self.nested.stderr)

    def test_the_nested_root_does_not_silence_the_note(self):
        self.assertEqual(
            walk_notes(self.nested.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)",
             f"RESOLVED-BY-WALK: {self.root}/out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"],
            self.nested.stderr)

    def test_the_nested_root_does_not_zero_the_counter(self):
        self.assertIn("resolved-by-walk 2", census(self.nested.stderr),
                      self.nested.stderr)

    def test_the_verdict_does_not_depend_on_root_ORDER(self):
        """Declaration order is load-bearing elsewhere (`resolve_base` is
        first-hit-wins, and the note's relpath is the one from the FIRST
        supplied root that holds the name below its own top level), so the
        existential is asserted under both orderings — mirroring
        `TestAnotherRootsGitToplevelDoesNotFlagATopLevelName`'s own ORDER
        test on the over-fire side. setUp's run is NESTED-first; this one is
        OUTER-first, which is why it calls `run` rather than `verify` (that
        helper always appends the outer root LAST)."""
        p = self.root / "rcpt.txt"
        p.write_text(self.rcpt)
        out = run("--tier2", "--root", str(self.root),
                  "--root", str(self.root / "out-9"), str(p))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(
            walk_notes(out.stderr),
            ["RESOLVED-BY-WALK: out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)",
             f"RESOLVED-BY-WALK: {self.root}/out-9/round-9-findings.md "
             "(out-9/round-9-findings.md)"],
            out.stderr)
        self.assertIn("resolved-by-walk 2", census(out.stderr), out.stderr)


# --------------------------------------------------------------------------
# AC-6 T7 leg 2 — the OVER-fire direction (round-6 F1). The mirror of
# TestASecondNestedRootDoesNotSilenceTheCounter: that class pins that a second
# root must not SILENCE a below-top-level resolution; this one pins that a
# second root must not FLAG a resolution that happened AT a root's own top
# level. Both roots here live inside one git checkout, so the FIRST root's git
# toplevel sees the file two components down while the file itself sits at the
# top level of the root that actually resolved it, and under no supplied
# root's top level otherwise. §3.1 clause 2 quantifies over "a ROOT's top
# level"; a build that lets a DERIVED base (some other root's git toplevel)
# decide the depth fires here, on exactly the bare-basename citation form the
# counter exists to distinguish §3.4 move 1's remedy FROM.
# --------------------------------------------------------------------------
class TestAnotherRootsGitToplevelDoesNotFlagATopLevelName(unittest.TestCase):
    """AC-6 T7 leg 2, over-fire direction. Fixture is the citation form the
    counter must stay silent on: a bare basename resolving at a root's own top
    level, with a sibling root inside the same checkout."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.repo = base / "repo"
        (self.repo / "dispatch").mkdir(parents=True)
        (self.repo / "findings").mkdir()
        _plant_git_dir(self.repo)
        body = "# findings\nfatal=0\n"
        f = self.repo / "findings/round-9-findings.md"
        f.write_text(body)
        h = hashlib.sha256(body.encode()).hexdigest()
        self.rcpt = base / "rcpt.txt"
        self.rcpt.write_text(receipt(
            artifacts=[("round-9-findings.md", h, str(len(body)))],
            trace=[f"WROTE  {f}  sha256:{h}"]))

    def _run(self, *roots):
        args = []
        for r in roots:
            args += ["--root", str(self.repo / r)]
        return run("--tier2", "--strict", *args, str(self.rcpt))

    def test_the_run_completes(self):
        """Non-vacuity: the name DOES resolve and DOES hash-verify, so the
        only thing under test is whether the note and the counter fire."""
        out = self._run("dispatch", "findings")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", census(out.stderr), out.stderr)

    def test_no_note_is_emitted(self):
        out = self._run("dispatch", "findings")
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)

    def test_the_sub_count_stays_zero(self):
        out = self._run("dispatch", "findings")
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)

    def test_the_verdict_does_not_depend_on_root_ORDER(self):
        """Declaration order is load-bearing elsewhere (`resolve_base` is
        first-hit-wins), so the silence is asserted under both orderings."""
        out = self._run("findings", "dispatch")
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)

    def test_the_single_root_control_is_silent_too(self):
        """The discriminator: with only the resolving root supplied there is
        no second root to leak a base, and every build agrees the answer is
        silence. A copy that goes red HERE has broken the base case, not the
        cross-root case."""
        out = self._run("findings")
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)


class TestAGitToplevelDeepResolutionIsSilent(unittest.TestCase):
    """AC-6 T7 leg 2, `_below_top_level` clause (1), DEEP direction.

    `TestAnotherRootsGitToplevelDoesNotFlagATopLevelName` above pins the SHALLOW
    case — the resolved file sits at a SUPPLIED root's own top level and another
    root's git toplevel sees it one component down. It leaves the other half of
    clause (1) unpinned: a resolution that lands under NO supplied root at all,
    reached through the git-toplevel candidate, which the docstring rules
    "silent here by construction" because there is no relpath from a root to
    print in the note's `(<relpath-from-root>)` placeholder.

    Fixture: the ONLY supplied root is `<repo>/dispatch`, and the cited file
    lives at `<repo>/sub/round-9-findings.md` — under `dispatch`'s git toplevel
    (`<repo>`, a probed BASE and a member of the containment union) but under no
    supplied root. Measured on a build that adds a git-toplevel fallback to
    `_below_top_level` — consult each root's toplevel only when no supplied
    root CONTAINS the resolution — `test_no_note_is_emitted` and
    `test_the_sub_count_stays_zero` below are the only two tests in either
    suite that go red; the shallow class above stays green, because its
    resolution IS contained by a supplied root and that fallback never runs
    there. (Gate the same fallback on "no supplied root FIRED" instead and the
    shallow class reddens too — which is why the containment form is the one
    that isolates this half of the clause.)"""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.repo = base / "repo"
        (self.repo / "dispatch").mkdir(parents=True)
        (self.repo / "sub").mkdir()
        _plant_git_dir(self.repo)
        body = "# findings\nfatal=0\n"
        f = self.repo / "sub/round-9-findings.md"
        f.write_text(body)
        h = hashlib.sha256(body.encode()).hexdigest()
        self.rcpt = base / "rcpt.txt"
        self.rcpt.write_text(receipt(
            artifacts=[("sub/round-9-findings.md", h, str(len(body)))],
            trace=[f"WROTE  {f}  sha256:{h}"]))

    def _run(self):
        return run("--tier2", "--strict", "--root", str(self.repo / "dispatch"),
                   str(self.rcpt))

    def test_the_run_still_succeeds(self):
        """Non-vacuity: the git-toplevel candidate DOES resolve the name and it
        DOES hash-verify, so the only thing under test is the counter."""
        out = self._run()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", census(out.stderr), out.stderr)

    def test_no_note_is_emitted(self):
        out = self._run()
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)

    def test_the_sub_count_stays_zero(self):
        out = self._run()
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)


class TestABareBasenameResolvedThroughASymlinkStillFires(_RootCase):
    """AC-6 T7 leg 2, the "KEYED ON `resolved`, NOT ON THE CITATION" clause.

    `_below_top_level`'s docstring rules this shape IN, explicitly and as a
    disclosed cost: `resolve_base` returns `c.resolve()`, so a BARE BASENAME at
    a root's own top level whose on-disk target is a symlink into a
    subdirectory has a realpath genuinely below that top level, and §3.1 clause
    2's "resolves to a path below a root's top level" is satisfied literally.
    Until this class existed the ruling was prose only: every fixture that
    fires the counter cites a path-shaped name, so a build gating the emission
    on `is_path_shaped(name)` — i.e. re-keying the predicate on the CITATION,
    the reading the docstring refuses — left both suites green. Measured on
    exactly that mutant, both assertions below go red and nothing else moves.

    The note's `(<relpath-from-root>)` is the RESOLVED relpath (`sub/real.md`),
    not the cited name, which is the same disclosure stated as an assertion.

    The fixture is artifacts-leg-only by construction: TRACE names an absolute
    path outside every root, so the witness leg resolves nothing and the ONE
    note on the channel is unambiguously the ARTIFACTS leg's."""

    def test_the_note_and_the_counter_both_fire(self):
        h, s = self.plant("sub/real.md", "# findings\nfatal=0\n")
        (self.root / "top.md").symlink_to(pathlib.Path("sub/real.md"))
        out = self.verify(receipt(
            artifacts=[("top.md", h, s)],
            trace=["READ  /elsewhere/round-0-notes.md"]))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr),
                         ["RESOLVED-BY-WALK: top.md (sub/real.md)"], out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)


class TestTheBasenameKeyIsSilentOnASameBasenameCollision(_RootCase):
    """Documented cost of §3.4's basename key (round-4-of-this-gate S3), PINNED
    so the silence is a recorded decision rather than an unmeasured property.
    A TRACE entry naming a DIFFERENT file whose basename matches a verified
    ARTIFACTS basename emits nothing. Change this test only by changing the
    ruled key.

    Fixture is the chunked-gate collision Task 4's docstring names: two
    same-basename files in two different chunks, one verified, one not."""

    def test_the_collision_is_silent(self):
        h, s = self.plant("chunk-A/fix-journal.md", "# fix journal\n")
        out = self.verify(receipt(
            artifacts=[("chunk-A/fix-journal.md", h, s)],
            trace=[f"WROTE  {self.root}/chunk-A/fix-journal.md  sha256:{h}",
                   "READ  /elsewhere/chunk-B/fix-journal.md"]))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(notes(out.stderr), [], out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
