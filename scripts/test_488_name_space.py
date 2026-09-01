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


def _cache_for(rv, artifacts, trace, witness, verdict, root):
    cache = {}
    rv._build_identity_cache(artifacts, trace,
                             [witness] if witness is not None else [],
                             verdict, root, cache)
    return cache


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


def outside_notes(stderr):
    """The RESOLVED-OUTSIDE-ROOTS advisory lines on a run's stderr, in order
    (SIEGE-S5). Deliberately a SEPARATE reader from `walk_notes`: the two channels
    report different facts, and a single reader matching both would let one of them go
    silent without any assertion noticing."""
    return [l for l in stderr.splitlines()
            if l.strip().startswith("RESOLVED-OUTSIDE-ROOTS:")]


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


class _TwoRootCase(unittest.TestCase):
    """The MANDATED two-root production shape (`quality-gate/SKILL.md` › Receipt
    Linter: `--tier2 --strict --root <dispatch-root> --root <findings-root>`),
    both roots OUTSIDE the checkout per §6 and SIBLINGS rather than nested —
    layout pin (b) makes `<findings-root>` the run's scratch directory, not a
    subdirectory of the dispatch root."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.dispatch = base / "dispatch"
        self.findings = base / "scratch"
        self.dispatch.mkdir()
        self.findings.mkdir()

    def plant(self, root, relname, body):
        p = pathlib.Path(root) / relname
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        return hashlib.sha256(body.encode()).hexdigest(), str(len(body))

    def verify(self, text, name="rcpt.txt"):
        p = self.dispatch / name
        p.write_text(text)
        return run("--tier2", "--strict", "--root", str(self.dispatch),
                   "--root", str(self.findings), str(p))


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
            self.rv.tier2_artifacts(
                self.ART, None, [self.root], True, None, [],
                cache=_cache_for(self.rv, self.ART, None, None, "PASS",
                                 [self.root]), verified={})
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
                [self.root], True, None, notes_out,
                cache=_cache_for(
                    self.rv, self.ART,
                    [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                    None, "PASS", [self.root]), verified={})
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
            self.rv.tier2_artifacts(
                self.ART, self.TRACE, [self.root], True, None, notes_out,
                cache=_cache_for(self.rv, self.ART, self.TRACE, None, "PASS",
                                 [self.root]), verified={})
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
            self.rv.tier2_artifacts(
                self.ART, self.TRACE, [self.root], True, None, None,
                cache=_cache_for(self.rv, self.ART, self.TRACE, None, "PASS",
                                 [self.root]), verified={})
        self.assertIn("absent under all bases", str(caught.exception))
        self.assertEqual(calls, [], "the emitter ran for a caller that asked "
                                    "for no notes")

        # Non-vacuity: the identical call that DOES ask for notes reaches the
        # patched emitter, so the leg above is about the guard, not about a
        # monkeypatch that never took.
        with self.assertRaises(self.rv.LintError):
            self.rv.tier2_artifacts(
                self.ART, self.TRACE, [self.root], True, None, [],
                cache=_cache_for(self.rv, self.ART, self.TRACE, None, "PASS",
                                 [self.root]), verified={})
        self.assertEqual(len(calls), 1, "the monkeypatch never took")

    def test_it_does_not_mask_when_the_caller_wants_no_notes(self):
        """`notes_out=None` — the ~40 --eval/--selftest-shaped call sites. The
        real failure must reach them too, rather than an AttributeError raised by
        work whose only product they asked not to receive."""
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                self.ART, self.TRACE, [self.root], True, None, None,
                cache=_cache_for(self.rv, self.ART, self.TRACE, None, "PASS",
                                 [self.root]), verified={})
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
                    self.rv.tier2_artifacts(
                        self.ART, trace, [self.root], True, None, [],
                        cache=_cache_for(self.rv, self.ART, trace, None, "PASS",
                                         [self.root]), verified={})
                self.assertIn("absent under all bases", str(caught.exception))

    def test_the_control_shows_the_same_call_really_reaches_the_emitter(self):
        """Non-vacuity: a well-formed `trace` raises the SAME LintError and the
        emitter demonstrably ran from inside the `finally:`, so a red leg above
        is about the element reads and not about the emitter being skipped."""
        notes_out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                self.ART, [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                [self.root], True, None, notes_out,
                cache=_cache_for(
                    self.rv, self.ART,
                    [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                    None, "PASS", [self.root]), verified={})
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
            self.rv.tier2_artifacts(
                self.art, self.trace, [self.root], True, None, None,
                cache=_cache_for(self.rv, self.art, self.trace, None, "PASS",
                                 [self.root]), verified={}), [])

    def test_a_pathlike_key_still_verifies_when_notes_were_asked_for(self):
        notes_out = []
        self.assertEqual(
            self.rv.tier2_artifacts(
                self.art, self.trace, [self.root], True, None, notes_out,
                cache=_cache_for(self.rv, self.art, self.trace, None, "PASS",
                                 [self.root]), verified={}), [])

    def test_the_control_shows_the_str_key_spelling_verifies(self):
        """Non-vacuity: the same fixture keyed by `str` verifies and is silent,
        so the legs above are about the key TYPE and not about the fixture."""
        art = {str(k): v for k, v in self.art.items()}
        notes_out = []
        self.assertEqual(
            self.rv.tier2_artifacts(
                art, self.trace, [self.root], True, None, notes_out,
                cache=_cache_for(self.rv, art, self.trace, None, "PASS",
                                 [self.root]), verified={}), [])
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


class TestADegenerateVerifiedBasenameCannotSilenceUnrelatedNames(_RootCase):
    """TEMPER/LEG-1 — ADVERSARIAL 4's sibling, one character over.

    `rsplit("/", 1)[-1]` is a string split, not a basename function, and THREE
    legal `ARTIFACTS` spellings drive it to a value that names no file:
    `x/` -> `""`, `x/.` -> `"."`, `x/..` -> `".."`. F4 hardened only the `""`
    symptom, and it did so with a TRUTHINESS test — so `.` and `..` still keyed
    `verified_bases` / `unevaluated_bases`, and each silenced a whole family of
    unrelated `TRACE` names.

    `x/.` is legal under §3's lexical grammar (`.` is not a `..` component),
    `resolve_base` normalises the `/.` away, and it hash-verifies — so the
    receipt renders `artifacts 1/1` and EXIT=0 and looks immaculate. What one
    extra character in the author's OWN `ARTIFACTS` spelling then buys is silence
    on arbitrarily many undeclared reads. Silence a receipt author can buy is the
    direction grudge `e0f0a6b75692` forbids, and is the exact failure
    `_emit_provenance_notes`'s F3 paragraph says the exact-name override exists
    to prevent.

    The four arms below are ADVERSARIAL 4's table shifted onto the `.` key, with
    three non-vacuity controls so the silence can only be attributed to it."""

    def setUp(self):
        super().setUp()
        # `q` is REAL, DIFFERENT, and never declared — so its TRACE citation is a
        # genuinely unverified read the note exists to report.
        self.plant("q", "secret\n")
        self.h, self.s = self.plant("x", "body\n")

    def _run(self, art, cited, name):
        out = self.verify(receipt(artifacts=[(art, self.h, self.s)],
                                  trace=[f"READ  {cited}"]), name=name)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", out.stderr)   # non-vacuity: it verified
        return out

    def test_a_dot_suffixed_artifact_cannot_silence_an_undeclared_dot_read(self):
        """The defect itself: this arm was SILENT before the fix."""
        out = self._run("x/.", "q/.", "dot.txt")
        self.assertTrue(any("q/." in n for n in notes(out.stderr)), out.stderr)

    def test_a_dotdot_suffixed_artifact_cannot_silence_an_undeclared_read(self):
        """`..` reaches the OTHER keyed set, so the guard is needed at both sites.

        It never reaches `verified_bases` — `x/..` resolves to a DIRECTORY and so
        never hash-verifies — but §3.4's truncation rule puts every NEVER-REACHED
        declared name's basename into `unevaluated_bases`, which keys the same
        match. So the fixture declares `x/..` AFTER an absent path-shaped entry
        whose `--strict` raise truncates the loop before reaching it: `".."`
        lands in the unevaluated set, and the undeclared `TRACE READ q/..` was
        silenced by it. Measured pre-fix on this exact receipt: SILENT, with
        `artifacts 1/2 ... partial`."""
        out = self.verify(receipt(
            artifacts=[("x", self.h, self.s),
                       ("nope/absent.md", "d" * 64, "9"),
                       ("x/..", self.h, self.s)],
            trace=["READ  q/.."]), "--strict", name="dotdot.txt")
        # Non-vacuity: the run really was TRUNCATED, so `x/..` really is
        # unevaluated rather than merely unverified. `--strict` is what makes the
        # absent path-shaped entry RAISE rather than degrade to UNVERIFIABLE.
        self.assertNotEqual(out.returncode, 0, out.stderr)
        self.assertIn("partial", out.stderr)
        self.assertIn("artifacts 1/2", out.stderr)
        self.assertTrue(any("q/.." in n for n in notes(out.stderr)), out.stderr)

    def test_the_control_with_a_plain_artifact_name_emits(self):
        """Non-vacuity: the note fires on this TRACE name when the ARTIFACTS
        spelling is ordinary, so the silence above was about the `.` key."""
        out = self._run("x", "q/.", "ctl-art.txt")
        self.assertTrue(any("q/." in n for n in notes(out.stderr)), out.stderr)

    def test_the_control_with_a_plain_trace_name_emits(self):
        """Non-vacuity from the other side: the same degenerate ARTIFACTS
        spelling does not silence an ordinary TRACE name."""
        out = self._run("x/.", "q", "ctl-trace.txt")
        self.assertTrue(any(n.rstrip().endswith("q (declared in TRACE, not verified)")
                            for n in notes(out.stderr)), out.stderr)


class TestAVerifiedNameCitedVerbatimIsSilent(_RootCase):
    """TEMPER/LEG-1 — the VERIFIED set's exact-name leg, the third of three.

    `unevaluated_names` (round-3/Minor-3) and `unverified_names` (F3) each carry
    the full declared spellings that the basename key cannot represent. The
    VERIFIED set had no such leg — so a name whose basename is degenerate had
    nothing to fall back on, and a `TRACE` entry citing a name this run declared,
    resolved and HASH-VERIFIED still got a note saying it was "not verified".

    Measured before the fix: `ARTIFACTS x/` + `TRACE READ x/` rendered
    `artifacts 1/1` AND `PROVENANCE-ONLY: x/ (declared in TRACE, not verified)`
    on the SAME stderr, about the SAME name — the advisory channel stating the
    opposite of the census. Advisory-only, so no exit code moved; the cost is
    cry-wolf on the channel whose whole job is to be believed.

    This leg is also what keeps the degenerate-key fix above honest: once `.`
    stops keying `verified_bases`, an honest `ARTIFACTS x/.` + `TRACE READ x/.`
    receipt would start emitting a false note by exactly this mechanism."""

    def setUp(self):
        super().setUp()
        self.h, self.s = self.plant("x", "body\n")

    def _run(self, spelling, name):
        out = self.verify(receipt(artifacts=[(spelling, self.h, self.s)],
                                  trace=[f"READ  {spelling}"]), name=name)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", out.stderr)   # non-vacuity: it verified
        return out

    def test_a_slash_suffixed_verified_name_gets_no_note(self):
        self.assertEqual(notes(self._run("x/", "slash.txt").stderr), [])

    def test_a_dot_suffixed_verified_name_gets_no_note(self):
        """CONTROL — green in BOTH directions, deliberately, and the only test of
        this pair that is. Before the degenerate-key fix this name was silent by
        COINCIDENCE (`.` keyed `verified_bases`); after it, it is silent because
        `verified_names` says so. So it reddens no `dec31_sweep` row and pins no
        leg on its own — what it pins is the COUPLING: it is the test that goes
        red if the degenerate-key fix is ever landed without this exact-name leg,
        which would widen the false note from the `/` family to the `/.` family.
        Its slash-suffixed sibling above is the arm that actually fails pre-fix."""
        self.assertEqual(notes(self._run("x/.", "dot.txt").stderr), [])

    def test_the_plain_control_also_gets_no_note(self):
        """Non-vacuity twin: the plain spelling was already silent, so the two
        tests above are about the VERIFIED leg and not about the spelling."""
        self.assertEqual(notes(self._run("x", "plain.txt").stderr), [])

    def test_an_unverified_spelling_still_speaks(self):
        """The fix must not silence by SPELLING. Same degenerate `x/.` name, but
        the declared sha256 does not match, so the entry is evaluated and NOT
        verified — `unverified_names` must still win and the note must fire."""
        bad = "0" * 64
        out = self.verify(receipt(artifacts=[("x/.", bad, self.s)],
                                  trace=["READ  x/."]), name="mismatch.txt")
        self.assertNotEqual(out.returncode, 0, out.stderr)
        self.assertTrue(any("x/." in n for n in notes(out.stderr)), out.stderr)


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
            self.rv.tier2_artifacts(
                self.art, self.trace, [self.root], False, None, notes_out,
                cache=_cache_for(self.rv, self.art, self.trace, None, "PASS",
                                 [self.root]), verified={})
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
            self.rv.tier2_artifacts(
                self.ART if art is None else art, trace,
                [self.root], True, None,
                [] if notes_out is None else notes_out,
                cache=_cache_for(self.rv, self.ART if art is None else art,
                                 trace, None, "PASS", [self.root]),
                verified={})
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
        """Re-aimed (identity redesign). `str(k)` normalisation moved from this
        `finally:`'s set comprehension into `_build_identity_cache`'s gather, so a
        hostile key's `__str__` surfaces at cache-build time, not inside the
        `finally:`. What survives is the guard the relocation does not remove: the
        `finally:` still projects the unevaluated names through `str(n)`, and a key
        with a raising `__str__` must not replace the in-flight `--strict` LintError
        there. The cache is therefore built from the benign keys so the relocated
        gather never fires, and the hostile key reaches only the guarded projection.

        ORDER IS LOAD-BEARING: the absent path-shaped name first, so `--strict`
        truncates and leaves the hostile key in the UNEVALUATED comprehension."""
        class _RaisingStr:
            def __str__(self):
                raise RuntimeError("__str__ exploded")

        art = dict(self.ART)
        art[_RaisingStr()] = {"hash": H64, "size": "10"}
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                art, [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}],
                [self.root], True, None, [],
                cache=_cache_for(self.rv, self.ART,
                                 [{"n": 1, "verb": "READ",
                                   "args": "/elsewhere/x.md"}],
                                 None, "PASS", [self.root]),
                verified={})
        self.assertIn("absent under all bases", str(caught.exception))

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
    """ROUND-4/S1 — the FIFTH instance of the class the four classes above pin one
    shape at a time, stated at the FUNCTION level instead.

    ROUND-3/S1 corrects this class's original "(intended) LAST": a SIXTH arrived,
    at the RESOLVED-BY-WALK emission sites Task 5 added to both legs' clean paths.
    The correction is in the fixture, not the wording — the claim below was always
    the right claim, but the `ART` it was tested against held only names that never
    RESOLVE, so control never reached the new site and the FUNCTION-level statement
    was true of the docstring and not of the test. The resolving entry now sits
    first (see the comment on `WALK`), and
    `TestNoHostileNotesOutCanMaskTheWitnessLegsInFlightRaise` states the same
    property for `tier2_witness`, which had no hostile-`notes_out` pin at all.

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

    #  ORDER IS LOAD-BEARING, in TWO places. The RESOLVING below-top-level name
    #  first, so control reaches the RESOLVED-BY-WALK emission site — round-3/S1
    #  found that the fixture below stopped at names that never resolve, which
    #  left the FUNCTION-level claim in the docstring ("no hostile shape on ANY
    #  of the three parameters") untested against the one site Task 5 added, and
    #  that site was the sixth instance of the class. Then the bare basename, so
    #  it appends an UNVERIFIABLE note to the RETURN-value list before the
    #  path-shaped name raises — that note is what the mirror arm exists to
    #  mirror, so a `notes` list that is empty at the raise would make every leg
    #  here vacuous. The planted file is added in setUp (it needs a root).
    WALK = "out-9/round-9-findings.md"
    ART = {"bare-basename.md": {"hash": H64, "size": "10"},
           "docs/plans/absent-path-shaped.md": {"hash": H64, "size": "10"}}
    TRACE = [{"n": 1, "verb": "READ", "args": "/elsewhere/x.md"}]

    class _NoExtend:
        """Ordinary API misuse, not a contrived object: any caller who passed the
        wrong out-parameter (a `set`, a `_Coverage`, a namedtuple) lands here."""

    class _RaisingExtend:
        def extend(self, items):
            raise RuntimeError("notes_out.extend exploded")

    class _RaisingAppend:
        """ROUND-4-of-this-gate/M1 — the shape this class was blind to. Every
        hostile shape above is `.extend`-flavoured, and `_RaisingExtend` has no
        `.append` AT ALL, so at the walk-note emission site it degrades to the
        same `AttributeError` `_NoExtend` already produces. A narrowed guard at
        `_emit_walk_note` (`except AttributeError:` instead of `except
        Exception:`) was therefore caught only by the WITNESS leg's sibling pin
        — the same leg asymmetry round-1/S2 found and closed once already.
        Deliberately the identical shape
        `TestNoHostileNotesOutCanMaskTheWitnessLegsInFlightRaise._RaisingAppend`
        uses, so the two legs are tested against the same hostile object."""

        def append(self, item):
            raise RuntimeError("notes_out.append exploded")

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        h, s = self.plant(self.WALK, "# findings\nfatal=0\n")
        self.ART = {self.WALK: {"hash": h, "size": s}, **self.ART}

    def _run(self, notes_out, art=None, trace=None):
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                self.ART if art is None else art,
                self.TRACE if trace is None else trace,
                [self.root], True, None, notes_out,
                cache=_cache_for(self.rv, self.ART if art is None else art,
                                 self.TRACE if trace is None else trace,
                                 None, "PASS", [self.root]), verified={})
        self.assertIn("absent under all bases", str(caught.exception))

    def test_no_hostile_notes_out_shape_replaces_the_real_lint_error(self):
        for label, notes_out in (("tuple", ()), ("int", 0),
                                 ("object without .extend", self._NoExtend()),
                                 ("object whose .extend raises",
                                  self._RaisingExtend()),
                                 ("object whose .append raises",
                                  self._RaisingAppend())):
            with self.subTest(shape=label):
                self._run(notes_out)

    def test_all_three_caller_supplied_parameters_hostile_at_once(self):
        """The function-level statement. Each parameter's guard lives in a
        DIFFERENT block (`finally:` wrapper, per-entry guard, mirror arm), and
        the arms run in sequence on one raise — so a fix that closed one by
        breaking another's ordering would pass the single-parameter legs and
        fail here.

        Re-aimed (identity redesign): the ARTIFACTS key's `str(k)` normalisation
        moved into `_build_identity_cache`'s gather, so the cache is built from the
        benign keys — the hostile key reaches only the `finally:`'s guarded `str(n)`
        projection, and the hostile `trace`/`notes_out` still run their own guards."""
        class _RaisingStr:
            def __str__(self):
                raise RuntimeError("__str__ exploded")

        art = dict(self.ART)
        art[_RaisingStr()] = {"hash": H64, "size": "10"}
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                art, [None, 5], [self.root], True, None, (),
                cache=_cache_for(self.rv, self.ART, self.TRACE, None, "PASS",
                                 [self.root]), verified={})
        self.assertIn("absent under all bases", str(caught.exception))

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
                         [f"{WALK_PREFIX} {self.WALK} ({self.WALK})",
                          "UNVERIFIABLE: bare-basename.md (no file under root)",
                          f"{NOTE_PREFIX} /elsewhere/x.md (declared in TRACE, "
                          "not verified)"])

    def test_the_walk_note_site_is_actually_reached_by_this_fixture(self):
        """Non-vacuity for the widening itself — round-3/S1. Without this the
        fixture could silently drift back to names that never resolve (the
        state it was found in) and every hostile-shape leg above would go green
        while never executing the emission site it claims to cover. Asserted on
        the CENSUS rather than the note, because the counter is the half that
        survives a hostile out-parameter."""
        cov = self.rv._Coverage()
        with self.assertRaises(self.rv.LintError):
            self.rv.tier2_artifacts(
                self.ART, self.TRACE, [self.root], True, cov, [],
                cache=_cache_for(self.rv, self.ART, self.TRACE, None, "PASS",
                                 [self.root]), verified={})
        self.assertEqual(cov.counts.get("resolved-by-walk"), 1, cov.counts)


class TestNoHostileNotesOutCanMaskTheWitnessLegsInFlightRaise(_RootCase):
    """ROUND-3/S1 — the SIXTH instance of the class, witness-leg half.

    The class above states the property for `tier2_artifacts`. Task 5 added a
    SECOND RESOLVED-BY-WALK emission site, in `tier2_witness`, with the same
    unguarded `notes_out.append(...)` and the same siting: BEFORE the
    `if len(found) > 1:` ambiguity block, which RAISES under `--strict` — the
    MANDATED invocation (`quality-gate/SKILL.md:30`). Until this class existed
    the witness leg had no hostile-`notes_out` pin at all, so the artifacts
    leg's pin could be widened and passed while this leg stayed open — exactly
    the leg asymmetry round-1/S2 found and closed once already.

    Measured on `8a5a1f9` (pre-fix), this fixture: `()`, `0`, an object without
    `.append`, and an object whose `.append` raises each replaced the genuine
    `Tier-2 --strict: witness artifact ... is ambiguous across roots` LintError
    — the first three with `AttributeError: '<t>' object has no attribute
    'append'`, the fourth with the object's own RuntimeError. Measured on
    `b6990c7` (pre-Task-5, same fixture): all four left the LintError intact,
    so this leg's hole ON THIS PATH is a Task-5 regression too. The witness
    leg's THREE `notes_out.extend(...)` sites (C1-R3-S2, on the paths BEYOND
    the ambiguity raise) are older and are NOT in this change's scope; they are
    reported, unfixed, in the round-3 receipt.

    Driven by a DIRECT call because the CLI cannot supply a hostile
    out-parameter; that is the point of pinning it."""

    WALK = "out-9/round-9-findings.md"

    class _NoAppend:
        """Ordinary API misuse: a caller who passed a `set`, a `_Coverage`, or a
        namedtuple as the out-parameter lands here."""

    class _RaisingAppend:
        def append(self, item):
            raise RuntimeError("notes_out.append exploded")

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        body = "# findings\nfatal=0\n"
        self.h, _ = self.plant(self.WALK, body)
        self.other = pathlib.Path(self.td.name) / "second-root"
        (self.other / "out-9").mkdir(parents=True)
        (self.other / self.WALK).write_text(body)
        self.trace = self.rv.parse_trace(
            [f"  1  WROTE  {self.WALK}  sha256:{self.h}"])
        self.witness = self.rv.parse_witness(
            ["lint:all-claims-cited  expect-fail=exit!=0  ran=TRACE#1"])

    def _run(self, notes_out, cov=None):
        cache = _cache_for(self.rv, {}, self.trace, self.witness, "PASS",
                           [self.root, self.other])
        return self.rv.tier2_witness(
            self.witness, self.trace, [self.root, self.other], True, "PASS",
            cov, None, notes_out, cache=cache, verified={})

    def test_no_hostile_notes_out_shape_replaces_the_real_lint_error(self):
        for label, notes_out in (("tuple", ()), ("int", 0),
                                 ("object without .append", self._NoAppend()),
                                 ("object whose .append raises",
                                  self._RaisingAppend())):
            with self.subTest(shape=label):
                with self.assertRaises(self.rv.LintError) as caught:
                    self._run(notes_out)
                self.assertIn("is ambiguous across roots", str(caught.exception))

    def test_a_real_list_still_receives_the_note(self):
        """Non-vacuity, and the mutation this fix could otherwise introduce: an
        envelope that swallowed the WORK as well as the exceptions would make
        the leg above green while silently discarding the note — the fail-open
        direction grudge `e0f0a6b75692` forbids."""
        notes_out = []
        with self.assertRaises(self.rv.LintError):
            self._run(notes_out)
        self.assertEqual(notes_out,
                         [f"{WALK_PREFIX} {self.WALK} ({self.WALK})"])

    def test_the_counter_and_the_note_cannot_disagree(self):
        """ROUND-3/S1 second-order half. With the emission ahead of the bump, a
        hostile out-parameter lost the note AND skipped the counter, so the
        census denied a resolution the ruling says happened. The counter is the
        half that must survive, on every shape."""
        for label, notes_out in (("real list", []), ("tuple", ()),
                                 ("object whose .append raises",
                                  self._RaisingAppend())):
            with self.subTest(shape=label):
                cov = self.rv._Coverage()
                with self.assertRaises(self.rv.LintError):
                    self._run(notes_out, cov)
                self.assertEqual(cov.counts.get("resolved-by-walk"), 1,
                                 cov.counts)


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
            self.rv.tier2_artifacts(
                self.ART if art is None else art, trace,
                [self.root], True, None, notes_out,
                cache=_cache_for(self.rv, self.ART if art is None else art,
                                 trace, None, "PASS", [self.root]),
                verified={})
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
            self.rv.tier2_artifacts(
                art, [{"n": 1, "verb": "READ", "args": "x/"}],
                [self.root], True, None, notes_out,
                cache=_cache_for(
                    self.rv, art, [{"n": 1, "verb": "READ", "args": "x/"}],
                    None, "PASS", [self.root]), verified={})
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
                [self.root], False, None, notes_out,
                cache=_cache_for(
                    self.rv, art, [{"n": 1, "verb": "READ", "args": "a.txt"}],
                    None, "PASS", [self.root]), verified={})
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
                [self.root], False, None, notes_out,
                cache=_cache_for(
                    self.rv, art, [{"n": 1, "verb": "READ", "args": "a.txt"}],
                    None, "PASS", [self.root]), verified={}), [])
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


class TestTheWalkNoteEscapesTheNameHalfToo(_RootCase):
    """AC-6 T7 leg 2, SIEGE-R2BA-4 leg — the `RESOLVED-BY-WALK:` twin of
    `TestTheNoteEscapesTheLeastConstrainedNameInTheGrammar`.

    `_walk_note` runs `_show_path` over BOTH halves it renders, per its own
    `SIEGE-R2BA-4` comment. The RELPATH half is pinned by construction —
    dropping its `_show_path` reddens three tests in `test_rcpt_verify.py`.
    The NAME half was not: round-4-of-this-gate/S1 measured a mutant that
    leaves the name raw and escapes only the relpath, and BOTH suites stayed
    100% green. AC-2's Tier-1 raise bans only a leading `/` and NUL in an
    ARTIFACTS name, so an ANSI escape and a backslash are both LEGAL there,
    and this note is captured verbatim into the durable `round-N-coverage.md`
    a human reads (`quality-gate/SKILL.md`'s coverage-line capture rule) —
    which is the same threat SIEGE-R2BA-4 names for every other name on this
    channel.

    Artifacts-leg-only by construction, like
    `TestABareBasenameResolvedThroughASymlinkStillFires`: TRACE names an
    absolute path outside every root, so the ONE note on the channel is
    unambiguously the ARTIFACTS leg's and its name half is the hostile key."""

    HOSTILE = "out-9/ho\x1b[31mst\\ile.md"

    def setUp(self):
        super().setUp()
        h, s = self.plant(self.HOSTILE, "# findings\nfatal=0\n")
        self.out = self.verify(receipt(
            artifacts=[(self.HOSTILE, h, s)],
            trace=["READ  /elsewhere/round-0-notes.md"]))

    def test_both_halves_of_the_note_render_escaped(self):
        self.assertEqual(
            walk_notes(self.out.stderr),
            [r"RESOLVED-BY-WALK: out-9/ho\x1b[31mst\\ile.md "
             r"(out-9/ho\x1b[31mst\\ile.md)"],
            self.out.stderr)

    def test_the_ansi_escape_never_reaches_the_channel_raw(self):
        # Asserted together with the note's PRESENCE, for the same reason the
        # PROVENANCE-ONLY twin states it: a build that emits nothing at all
        # would otherwise pass this leg by staying silent, which is the
        # fail-open direction grudge e0f0a6b75692 names.
        self.assertTrue(walk_notes(self.out.stderr), self.out.stderr)
        self.assertNotIn("\x1b", self.out.stderr)


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
    ALONE (arm intact) reddens NONE *in the suite as it stood when this class
    was written*. The adversarial pass at the foot of this file changes that
    number, and the paragraph above with it: measured on this commit, the
    channel change alone now reddens `TestTheWalkNoteAndTheProvenanceNoteCoFire`
    (the two channels' stderr ORDER flips, because the return value is merged
    only after the `finally:` block has already appended) and
    `TestTheEmitterGuardsLayerCorrectlyOnTheCleanPath`, with
    `test_rcpt_verify.py` still green — so the routing IS discriminated now,
    without the paired arm removal, just not by this class.
    Only the two together reach this test and
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
    through the return value on this ordering) left both suites green. The
    return-value routing is no longer green anywhere — see the correction in
    `TestTheWalkNoteSurvivesATruncatedRun`'s docstring.

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


class TestSiegeS4ASymlinkInsideAnOwnedRootCannotZeroTheWalkNote(_TwoRootCase):
    """SIEGE-S4 — `_below_top_level` keyed its depth check on `resolved`, the
    POST-symlink path, and a symlink can only ever SHORTEN a path. A subagent owns
    its `--root` dispatch directory, so it runs `ln -s ../top.md sub/in2.md` and
    cites `sub/in2.md`: the two-component citation resolves to the root's OWN top
    level, `len(rel.parts) == 1`, and both the `RESOLVED-BY-WALK:` note and the
    `resolved-by-walk` counter vanish — a per-citation mute switch on the one
    instrument that discloses unusual resolution, needing no deployment-specific
    condition, only write access to a root the subagent already has.

    Measured on `ba482e2` under the mandated two-root command line: `resolved-by-walk
    0` and no note for the symlink, against `resolved-by-walk 2` and two notes for the
    non-symlink `sub/y.md` control. The old docstring disclosed only the FALSE-POSITIVE
    direction (a bare basename whose target is a symlink into a subdirectory DOES
    fire); this attacker-favourable inverse was stated nowhere.

    The control is the non-vacuity half: an ordinary deep citation must keep firing on
    exactly the resolution key it always used, so the fix cannot be "always fire"."""

    def _run(self, cited, target_rel):
        h, size = self.plant(self.dispatch, target_rel, "t\n")
        text = receipt(artifacts=[(cited, h, size)], trace=[f"READ  {cited}"])
        return self.verify(text)

    def test_the_symlink_shortened_citation_still_discloses(self):
        (self.dispatch / "sub").mkdir(parents=True, exist_ok=True)
        (self.dispatch / "sub" / "in2.md").symlink_to("../top.md")
        out = self._run("sub/in2.md", "top.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 2", census(out.stderr), out.stderr)
        # The rendered relpath is the POST-resolution one, and the two spellings
        # DIFFERING is the disclosure: the citation is two deep, the resolution is not.
        self.assertEqual(walk_notes(out.stderr),
                         ["RESOLVED-BY-WALK: sub/in2.md (top.md)"] * 2, out.stderr)

    def test_an_ordinary_deep_citation_is_unchanged(self):
        """NON-VACUITY — no symlink, same depth. This fired before the fix and must
        fire identically after it, with the identical relpath: the resolution key is
        additive-only, never replaced."""
        out = self._run("sub/y.md", "sub/y.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 2", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr),
                         ["RESOLVED-BY-WALK: sub/y.md (sub/y.md)"] * 2, out.stderr)

    def test_a_top_level_citation_stays_silent(self):
        """The other non-vacuity bound: a genuine bare-basename citation at the root's
        own top level is NOT this clause's case and must stay silent, or the counter
        stops distinguishing anything at all."""
        out = self._run("top.md", "top.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)


class TestSiegeR11TheAbsoluteSpellingOfTheShortenedCitationAlsoDiscloses(_TwoRootCase):
    """SIEGE-R1-1 — SIEGE-S4's own fix, bypassed by re-spelling the identical attack.

    `_cited_below_top_level` returned False for EVERY absolute name, on the claim that an
    absolute citation's depth "is already answered by `rel`". `rel` is computed from
    `resolved`, the POST-symlink path — which is the very thing SIEGE-S4 showed a
    root-owned symlink shortens — and §3.2 MANDATES the absolute spelling for a tracked
    file, so the arm that answered False was the PRIMARY spelling, not an edge case.

    Measured on `8d26620`, same plant as SIEGE-S4's own fixture, varying ONLY how TRACE
    spells the citation: `sub/top.md` → `resolved-by-walk 1` plus the note;
    `<root>/sub/top.md` → `resolved-by-walk 0` and silence.

    THE THREE ABSOLUTE SPELLINGS ARE ASSERTED TOGETHER because one lexical form is
    exactly what round 1 shipped and round 2 walked around: the plain absolute, the
    doubled-slash `//` form (which `PurePosixPath` and `normpath` both preserve as a
    distinct root component while `Path.resolve()` collapses it), and a citation written
    through a SYMLINK-valued `--root` token (`_as_roots` hands the depth check only
    RESOLVED roots, so no lexical prefix of the raw token survives to compare against).

    The relative control is the parity half — the two spellings of one citation must read
    the same — and the top-level controls are the non-vacuity half: an ordinary absolute
    tracked-file citation must stay silent, or the counter stops distinguishing anything."""

    def _plant(self):
        h, size = self.plant(self.dispatch, "top.md", "t\n")
        (self.dispatch / "sub").mkdir(parents=True, exist_ok=True)
        (self.dispatch / "sub" / "top.md").symlink_to("../top.md")
        return h, size

    def _run(self, cited):
        h, size = self._plant()
        return self.verify(receipt(artifacts=[("top.md", h, size)],
                                   trace=[f"READ  {cited}"]))

    def _assert_discloses(self, cited):
        out = self._run(cited)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr),
                         [f"RESOLVED-BY-WALK: {cited} (top.md)"], out.stderr)

    def test_the_relative_spelling_discloses(self):
        """The parity baseline — this is what SIEGE-S4's fix already got right."""
        self._assert_discloses("sub/top.md")

    def test_the_absolute_spelling_discloses(self):
        self._assert_discloses(f"{self.dispatch}/sub/top.md")

    def test_the_doubled_slash_absolute_spelling_discloses(self):
        self._assert_discloses(f"{self.dispatch}//sub/top.md")

    def test_a_symlink_valued_root_token_does_not_silence_it(self):
        """The prefix-symlink family: the citation names the root through a symlink, so
        NO spelling of the resolved root `_as_roots` supplies is a lexical prefix of it.
        Only resolving the citation's own PARENT (never its basename, which is what the
        attack symlinks) sees the depth."""
        link = self.dispatch.parent / "link"
        link.symlink_to(self.dispatch.name)
        h, size = self._plant()
        cited = f"{link}/sub/top.md"
        p = self.dispatch / "rcpt.txt"
        p.write_text(receipt(artifacts=[("top.md", h, size)],
                             trace=[f"READ  {cited}"]))
        out = run("--tier2", "--strict", "--root", str(link),
                  "--root", str(self.findings), str(p))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr),
                         [f"RESOLVED-BY-WALK: {cited} (top.md)"], out.stderr)

    def test_an_absolute_top_level_citation_stays_silent(self):
        """NON-VACUITY — §3.2's mandated spelling for an ORDINARY tracked file. Counting
        the absolute path's own components (rather than its depth below a supplied root)
        would fire on every one of these in the corpus."""
        out = self._run(f"{self.dispatch}/top.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)

    def test_a_doubled_slash_top_level_citation_stays_silent(self):
        """The same bound for the `//` spelling — the collapse must not manufacture a
        component that makes an ordinary citation read as deep."""
        out = self._run(f"{self.dispatch}//top.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)


class TestSiegeR2Ba1TheCitationDepthIsWalkedNotGuessed(_TwoRootCase):
    """SIEGE-R2BA-1 — the third respelling of SIEGE-S4, and the reason the absolute
    arm stopped enumerating candidate spellings altogether.

    Rounds 1 and 2 both answered "is this absolute citation deeper than one component
    below a root?" by building lexically-transformed candidate strings and asking
    `relative_to`. Round 2's own review then found the arrangement no candidate family
    reaches: `ln -s . <root>/sub` (a self-referential directory link inside a root the
    subagent owns) plus `ln -s <root> <outside>/L` (a prefix link ANYWHERE outside every
    supplied root), cited as `<outside>/L/sub/top.md`. No root is a string prefix of that
    name, so every lexical pairing raises `ValueError`; and `p.parent.resolve()`
    collapses BOTH links in one call and lands on the root itself, so the
    resolved-parent family reads depth 1. Measured on `588a7e9`: `resolved-by-walk 0`
    and silence, against `resolved-by-walk 1` plus the note for the byte-identical
    `<root>/sub/top.md`.

    The depth is now WALKED — one written component at a time, taking the deepest
    reading at any prefix that lands inside a supplied root — so a symlink is a STEP in
    the measurement rather than a spelling the measurement has to anticipate. These
    pins are therefore not "three more spellings": each is a distinct symlink
    ARRANGEMENT (outside-prefix, chained outside-prefix, in-root bounce), and the
    controls below are the bound that keeps the counter meaning something."""

    def _plant(self):
        h, size = self.plant(self.dispatch, "top.md", "t\n")
        (self.dispatch / "sub").symlink_to(".")
        return h, size

    def _run(self, cited, roots=None):
        h, size = self._plant()
        p = self.dispatch / "rcpt.txt"
        p.write_text(receipt(artifacts=[("top.md", h, size)],
                             trace=[f"READ  {cited}"]))
        roots = roots or [self.dispatch, self.findings]
        args = []
        for r in roots:
            args += ["--root", str(r)]
        return run("--tier2", "--strict", *args, str(p))

    def _assert_discloses(self, out, cited):
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 1", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr),
                         [f"RESOLVED-BY-WALK: {cited} (top.md)"], out.stderr)

    def test_a_prefix_symlink_outside_every_root_does_not_silence_it(self):
        """The round-2 repro verbatim. `L` lives outside every supplied root, so no
        root spelling is a lexical prefix of the citation; `sub -> .` is what makes the
        resolved parent collapse onto the root itself."""
        outside = self.dispatch.parent / "outside"
        outside.mkdir()
        (outside / "L").symlink_to(str(self.dispatch))
        cited = f"{outside}/L/sub/top.md"
        self._assert_discloses(self._run(cited), cited)

    def test_a_chain_of_outside_prefix_symlinks_does_not_silence_it(self):
        """One link deeper than the reported shape — `L2 -> L1 -> <root>`. A candidate
        family keyed on a single `.resolve()` cannot tell the two apart; a walk does not
        care how long the chain is, because it only ever asks where each prefix landed."""
        outside = self.dispatch.parent / "outside"
        outside.mkdir()
        (outside / "L1").symlink_to(str(self.dispatch))
        (outside / "L2").symlink_to(str(outside / "L1"))
        cited = f"{outside}/L2/sub/top.md"
        self._assert_discloses(self._run(cited), cited)

    def test_a_symlink_valued_root_token_plus_a_self_link_does_not_silence_it(self):
        """The second spelling the finding names: `--root` is itself a symlink (the
        findings root is created by the reviewed subagent per quality-gate/SKILL.md),
        and `sub -> .` defeats the R1-1 pin, which uses a REAL `sub/` directory."""
        link = self.dispatch.parent / "link"
        link.symlink_to("dispatch")
        cited = f"{link}/sub/top.md"
        self._assert_discloses(self._run(cited, roots=[link, self.findings]), cited)

    def test_a_top_level_citation_through_an_outside_symlink_stays_silent(self):
        """NON-VACUITY, and the bound the walk has to respect: naming the root through
        an outside link is not itself the disclosure — the citation still spells exactly
        one component below the root, so there is nothing to report. A measurement that
        counted the citation's own components, or that fired on "a symlink was
        followed", would fire here and stop distinguishing anything."""
        outside = self.dispatch.parent / "outside"
        outside.mkdir()
        (outside / "L").symlink_to(str(self.dispatch.parent))
        out = self._run(f"{outside}/L/dispatch/top.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)

    def test_an_absolute_top_level_citation_stays_silent_with_the_self_link_planted(self):
        """The other non-vacuity bound, with the attack's own fixture on disk: the
        `sub -> .` link EXISTS, and an ordinary tracked-file citation that does not go
        through it is still silent."""
        out = self._run(f"{self.dispatch}/top.md")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)


class TestSiegeR3Ba1TheWalkNeitherEatsTheAlarmNorAmplifiesItsOwnCost(unittest.TestCase):
    """SIEGE-R3BA-1 — the two halves of one defect the round-3 walk introduced.

    (a) THE SWALLOW. `_cited_below_top_level`'s absolute arm ends in `except Exception:
    return True`, written so a receipt-controlled name and a hostile filesystem can
    never crash a verdict. `WitnessTimeout` subclasses `LintError` subclasses
    `Exception`, so that arm also ate the SIGALRM this linter's only wall-clock guard
    raises — and `_witness_bound` arms `setitimer` ONE-SHOT with interval 0, so nothing
    re-arms it and the rest of the leg, including `re.search` over a receipt-authored
    `expect-fail` regex, then ran with no bound at all. Measured on `1943055`: the
    byte-identical shallow spelling exited 1 at 5.0 s with `witness evaluation exceeded
    5s`; the 250-component spelling was still running when killed at 60 s.

    (b) THE AMPLIFICATION that made (a) reachable at will. The round-3 walk calls
    `.resolve()` fresh per component with no memo, so a chain whose last link lands the
    walk back where it started (`k0 -> k1 -> … -> k25000 -> .`) is re-walked once per
    written component. Measured on `1943055` over a 254-component citation:
    `resolve_base` 0.039 s, the pre-round-3 `p.parent.resolve()` 0.040 s, the walk
    9.76 s — a 244x amplification, i.e. the receipt tuning the walk across the 5 s
    boundary on demand.

    Both are pinned because either alone leaves the other live: a propagating timeout
    over a walk still tunable to a large multiple of ordinary cost is a receipt that can
    still spend the whole budget, and a cheap walk that eats the alarm still disarms
    every LATER predicate on the leg."""

    def setUp(self):
        self.rv = _import_rv()
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.root = base / "dispatch"
        self.root.mkdir()
        self.outside = base / "outside"
        self.outside.mkdir()
        # The chain's last link lands back on `outside`, so every written `k0`
        # component asks for the SAME resolution — the shape the memo collapses.
        chain = 400
        for i in range(chain):
            (self.outside / f"k{i}").symlink_to(f"k{i + 1}")
        (self.outside / f"k{chain}").symlink_to(".")
        (self.root / "evidence.log").write_text("a" * 16)
        (self.outside / "evidence.log").symlink_to(str(self.root / "evidence.log"))
        self.deep = (str(self.outside) + "/" + "/".join(["k0"] * 250)
                     + "/evidence.log")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_witness_timeout_raised_mid_walk_is_not_swallowed(self):
        """(a). Fault injection rather than a real 5 s alarm, so the pin states the
        PROPERTY ("a LintError raised anywhere in the walk leaves the walk") instead of
        racing a wall clock on a loaded CI box. The alarm's own exception is exactly
        this class arriving at exactly this kind of site."""
        real = pathlib.Path.resolve
        seen = {"n": 0}

        def boom(self_, *a, **k):
            seen["n"] += 1
            if seen["n"] == 2:
                raise self.rv.WitnessTimeout(self.rv.WITNESS_TIMEOUT_MSG)
            return real(self_, *a, **k)

        pathlib.Path.resolve = boom
        try:
            with self.assertRaises(self.rv.WitnessTimeout):
                self.rv._cited_below_top_level(self.deep, [self.root])
        finally:
            pathlib.Path.resolve = real

    def test_the_walk_is_not_the_only_helper_that_must_not_eat_it(self):
        """(a), stated over the CLASS rather than over the reported site. The witness
        leg runs several MUST-NOT-RAISE helpers inside `_witness_bound()`, and the alarm
        arrives wherever the process happens to be — so a rule that fixed only the walk
        would leave the same swallow one function over. Each of these must let a
        LintError through its own catch-all. (`_carry_spellings` was retired by the
        identity redesign; the two disclosure-note emitters remain.)"""
        boom = self.rv.LintError("planted")

        class HostileList(list):
            def append(self, item):
                raise boom

        with self.assertRaises(self.rv.LintError):
            self.rv._emit_walk_note(HostileList(), "f.md", "a/f.md")
        with self.assertRaises(self.rv.LintError):
            self.rv._emit_outside_note(HostileList(), "f.md", self.root / "f.md")

    def test_an_ordinary_input_still_never_raises_out_of_the_walk(self):
        """The BOUND on (a). Narrowing the catch-all is only correct if it still
        tolerates everything it was written for: a malformed component, a NUL byte, a
        resolution loop, a non-path root. None of these may escape."""
        loop = self.root / "loop"
        loop.symlink_to("loop")
        for name in (f"{self.root}/loop/x.md", f"{self.root}/a\x00b/x.md",
                     "//" + str(self.root).lstrip("/") + "/x.md",
                     f"{self.root}/" + "x" * 4096 + "/y.md"):
            with self.subTest(name=name):
                self.assertIsInstance(
                    self.rv._cited_below_top_level(name, [self.root, 0, None]), bool)

    def test_the_walk_does_not_amplify_its_own_cost(self):
        """(b), counted rather than timed — a wall-clock assertion is a flake on a
        loaded box, and the defect is not "slow" but "one resolution charged 250 times".
        Every written component of this citation asks for the same prefix, so a memoised
        walk resolves ONCE. The pre-fix build issues one `resolve()` per component."""
        real = pathlib.Path.resolve
        seen = {"n": 0}

        def counted(self_, *a, **k):
            seen["n"] += 1
            return real(self_, *a, **k)

        pathlib.Path.resolve = counted
        try:
            self.rv._cited_below_top_level(self.deep, [self.root])
        finally:
            pathlib.Path.resolve = real
        # 250 written `k0` components; a walk with no memo issues one resolve each.
        self.assertLess(seen["n"], 10, f"{seen['n']} resolve() calls for one prefix")

    def test_the_memo_does_not_change_what_the_walk_answers(self):
        """The BOUND on (b). A memo that changed a reading would be a silencer wearing
        an optimisation's name, so the three round-2/round-3 arrangements and both
        SILENCE controls are re-asserted through the memoised walk directly."""
        (self.root / "sub").symlink_to(".")
        (self.root / "top.md").write_text("t\n")
        (self.outside / "L").symlink_to(str(self.root))
        (self.outside / "L2").symlink_to(str(self.outside / "L"))
        (self.outside / "P").symlink_to(str(self.root.parent))
        for cited, expected in (
                (f"{self.outside}/L/sub/top.md", True),
                (f"{self.outside}/L2/sub/top.md", True),
                (f"{self.root}/sub/top.md", True),
                (f"{self.outside}/P/dispatch/top.md", False),
                (f"{self.root}/top.md", False)):
            with self.subTest(cited=cited):
                self.assertIs(
                    self.rv._cited_below_top_level(cited, [self.root]), expected)


class TestALaterDisjointRootAnswersTheDepthKey(_RootCase):
    """AC-6 T7 leg 2, the DECLARATION-ORDER existential (round-4-of-this-gate/S2).

    `_below_top_level`'s `except ValueError: continue` IS the existential: it is
    what lets the loop walk PAST a supplied root that does not contain the
    resolution, on to a LATER root that does. No fixture reached that arm's
    load-bearing case — `TestASecondNestedRootDoesNotSilenceTheCounter` NESTS
    its two roots (the first already contains the file),
    `TestNoHostileNotesOutCanMaskTheWitnessLegsInFlightRaise` plants the file
    under BOTH — so a mutant returning `None` from that arm instead of
    continuing left both suites 100% green while silently zeroing the note and
    the counter on the mainline shape.

    That shape is the EVERYDAY one, not an edge case: the mandated gate
    invocation is `--root <dispatch-root> --root <findings-root>`
    (`quality-gate/SKILL.md:30`), those two roots are disjoint in the ordinary
    case, and a cited findings file lives under exactly one of them.

    Artifacts-leg-only by construction (TRACE names an absolute path outside
    every root), so the count below is the one cited-name-on-a-leg that
    resolved. Driven through `run` rather than `verify`, because that helper
    always appends `self.root` — which CONTAINS both roots here — as a third,
    containing root, which would destroy the shape under test."""

    NAME = "out-9/round-9-findings.md"

    def setUp(self):
        super().setUp()
        self.first = self.root / "dispatch-root"
        self.second = self.root / "findings-root"
        self.first.mkdir()
        body = "# findings\nfatal=0\n"
        planted = self.second / self.NAME
        planted.parent.mkdir(parents=True)
        planted.write_text(body)
        rcpt = self.root / "rcpt.txt"
        rcpt.write_text(receipt(
            artifacts=[(self.NAME,
                        hashlib.sha256(body.encode()).hexdigest(),
                        str(len(body)))],
            trace=["READ  /elsewhere/round-0-notes.md"]))
        self.out = run("--tier2", "--root", str(self.first),
                       "--root", str(self.second), str(rcpt))

    def test_the_two_roots_are_genuinely_disjoint(self):
        """Non-vacuity for the fixture itself. If either root contained the
        other, or the file existed under the first, the `continue` arm would
        never be the thing that answers and every leg below would go green
        against the mutant."""
        self.assertNotIn(self.first, self.second.parents)
        self.assertNotIn(self.second, self.first.parents)
        self.assertFalse((self.first / self.NAME).exists())
        self.assertTrue((self.second / self.NAME).is_file())

    def test_the_run_completes(self):
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        self.assertIn("artifacts 1/1", census(self.out.stderr), self.out.stderr)

    def test_the_note_carries_the_relpath_from_the_second_root(self):
        self.assertEqual(walk_notes(self.out.stderr),
                         [f"RESOLVED-BY-WALK: {self.NAME} ({self.NAME})"],
                         self.out.stderr)

    def test_the_non_containing_first_root_does_not_zero_the_counter(self):
        self.assertIn("resolved-by-walk 1", census(self.out.stderr),
                      self.out.stderr)


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

    ⚠ THE CLASS NAME IS NOW HALF TRUE, and SIEGE-S5 is the other half. This fixture
    is silent on `resolved-by-walk` — correctly, and that is still what the two
    original assertions pin. It is NOT silent overall: the same resolution now earns
    the `resolved-outside-roots` counter and its own note, which is the whole subject
    of `test_siege_s5_*` below. The class is kept under its old name because the
    ruling it pins (a git toplevel is a probed base, never a root the run was given)
    is unchanged and still load-bearing.

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

    def test_siege_s5_the_resolution_is_not_silent_overall(self):
        """SIEGE-S5 — `resolved-by-walk` staying 0 here is correct, and the convention
        used to rule the resulting TOTAL silence intentional and normative. That
        ruling is retracted: this is a resolution that left every root the
        orchestrator declared, which is the case most needing disclosure, and the run
        rendered `artifacts 1/1 … resolved-by-walk 0` with `PROVENANCE-ONLY:`
        suppressed as well (`verified_bases` gained the basename). An operator reading
        the durably-captured `TIER2-COVERAGE:` line could not tell.

        The two assertions above are the non-vacuity half of this one: they prove the
        fix did NOT close the gap by widening `resolved-by-walk` to fire here, which
        would have destroyed that counter's own meaning."""
        out = self._run()
        # 2, not 1: per CITED NAME ON A LEG, exactly as `resolved-by-walk` counts.
        # This fixture's name is cited on both the ARTIFACTS and the witness leg.
        self.assertIn("resolved-outside-roots 2", census(out.stderr), out.stderr)
        notes = outside_notes(out.stderr)
        self.assertEqual(len(notes), 2, out.stderr)
        # The realpath is named on every note: WHERE it landed is the disclosure.
        target = str(self.repo / "sub/round-9-findings.md")
        for n in notes:
            self.assertIn(target, n)


class TestSiegeS5AnOutOfRootResolutionIsDisclosedOnBothLegs(unittest.TestCase):
    """SIEGE-S5, the report's own chain fixture, on the MANDATED two-root command line
    and with the witness leg live so both emission sites are exercised.

    A `git init`-ed tree holds `<repo>/docs/clean.md`; the two supplied roots are
    `<repo>/scratch/dispatch` and `<repo>/scratch/findings`, and neither holds it.
    `_resolve_base_one` reaches it through `_git_toplevel(root)`, `_allowed_bases`
    folds that same toplevel into the containment union so `_contained` passes, and
    the cross-root ambiguity de-dup collapses to the single out-of-root location.
    Measured on `ba482e2`: `artifacts 1/1 witness 1/1 … resolved-by-walk 0`, exit 0,
    not one word about having left the declared scope — while the SUPERSEDES
    consequent gated on a predicate run against those very bytes.

    The VERDICT is deliberately not asserted to have changed. This finding is
    Hardening: the fix makes the fact audible, it does not newly refuse the receipt,
    and a pin demanding exit 1 here would be pinning a behaviour change nobody
    ordered."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.repo = pathlib.Path(self.td.name) / "repo"
        (self.repo / "scratch/dispatch").mkdir(parents=True)
        (self.repo / "scratch/findings").mkdir(parents=True)
        (self.repo / "docs").mkdir()
        _plant_git_dir(self.repo)
        body = "clean\n"
        (self.repo / "docs/clean.md").write_text(body)
        h = hashlib.sha256(body.encode()).hexdigest()
        self.rcpt = self.repo / "scratch/dispatch/r.rcpt"
        self.rcpt.write_text(receipt(
            artifacts=[("docs/clean.md", h, str(len(body)))],
            trace=["READ  docs/clean.md"],
            witness="grep:docs/clean.md#L1-L1  expect-fail=/zzz-absent/  ran=TRACE#1"))

    def _run(self):
        return run("--tier2", "--strict",
                   "--root", str(self.repo / "scratch/dispatch"),
                   "--root", str(self.repo / "scratch/findings"), str(self.rcpt))

    def test_both_legs_disclose_the_out_of_root_resolution(self):
        out = self._run()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-outside-roots 2", census(out.stderr), out.stderr)
        self.assertEqual(len(outside_notes(out.stderr)), 2, out.stderr)

    def test_the_walk_counter_is_not_repurposed_for_it(self):
        """NON-VACUITY — the fix must not close the gap by widening
        `resolved-by-walk`, whose own subject (depth below a SUPPLIED root's top
        level) this resolution does not satisfy under any reading."""
        out = self._run()
        self.assertIn("resolved-by-walk 0", census(out.stderr), out.stderr)
        self.assertEqual(walk_notes(out.stderr), [], out.stderr)

    def test_an_in_root_control_discloses_nothing(self):
        """The other non-vacuity bound: the SAME receipt with the file inside a
        supplied root must leave the new counter at 0, or it stops distinguishing
        anything."""
        body = "clean\n"
        (self.repo / "scratch/dispatch/docs").mkdir(parents=True)
        (self.repo / "scratch/dispatch/docs/clean.md").write_text(body)
        (self.repo / "docs/clean.md").unlink()
        out = self._run()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("resolved-outside-roots 0", census(out.stderr), out.stderr)
        self.assertEqual(outside_notes(out.stderr), [], out.stderr)


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


# --------------------------------------------------------------------------
# AC-6 T7 leg 2 — ADVERSARIAL PASS (Task 5, attack tests 1-5). Five angles the
# five prior review rounds left unreached, chosen to be disjoint from the
# fixtures above: MULTIPLICITY within one run (every fixture above cites at
# most one below-top-level name per leg), a truncating raise sited DOWNSTREAM
# of the emission ON THE SAME ENTRY (every truncation fixture above raises at
# the ambiguity block or on a different entry), CO-FIRING with Task 4's
# PROVENANCE-ONLY channel (never exercised together), hostile content confined
# to the RELPATH half alone (every escaping fixture above puts it in the name,
# where name == relpath), and the emitter's guard LAYERING on the CLEAN path
# (every hostile-`notes_out` fixture above drives the ambiguity raise).
# --------------------------------------------------------------------------
class TestEveryBelowTopLevelEntryInOneRunIsCountedAndNoted(_RootCase):
    """ATTACK 1 — MULTIPLICITY, and the deep-relpath rendering.

    Every fixture above cites exactly ONE below-top-level name per leg, so the
    counter is never observed above 1 from a single leg (`resolved-by-walk 2`
    in `TestABelowTopLevelResolutionIsCounted` is 1 + 1 across the two legs).
    That leaves the PER-ENTRY loop unpinned in both directions: a build that
    emits and counts only the FIRST below-top-level entry of a multi-entry
    ARTIFACTS block, and a build that counts the entries but renders one
    entry's relpath for another, both stay green on every class above.

    The fixture also carries the depth question the note's `(<relpath-from-root>)`
    placeholder raises: one entry resolves 31 components below the root, so a
    truncating or eliding renderer is visible here and nowhere else. It renders
    in full — the note is a single stderr line of ~200 characters, which is the
    measured cost of the design's literal reading and is recorded here rather
    than capped.

    Artifacts-leg-only by construction (TRACE names an absolute path outside
    every root), so the count below is exactly the artifacts leg's."""

    DEEP = "/".join(f"d{i}" for i in range(30)) + "/deep.md"

    def setUp(self):
        super().setUp()
        body = "# findings\nfatal=0\n"
        h1, s1 = self.plant("out-1/a.md", body)
        h2, s2 = self.plant(self.DEEP, body)
        h3, s3 = self.plant("top.md", body)
        self.out = self.verify(receipt(
            artifacts=[("out-1/a.md", h1, s1),
                       (self.DEEP, h2, s2),
                       ("top.md", h3, s3)],
            trace=["READ  /elsewhere/round-0-notes.md"]))

    def test_the_run_completes_and_every_entry_verified(self):
        # Non-vacuity: all three names resolve and hash-verify, so the only
        # thing under test is which of them the counter and the notes see.
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        self.assertIn("artifacts 3/3", census(self.out.stderr), self.out.stderr)

    def test_each_below_top_level_entry_gets_its_own_note_in_declaration_order(self):
        """Two notes, not one: the second below-top-level entry is the half a
        first-entry-only build drops. ARTIFACTS is an insertion-ordered dict,
        so declaration order is the order under test."""
        self.assertEqual(
            walk_notes(self.out.stderr),
            [f"{WALK_PREFIX} out-1/a.md (out-1/a.md)",
             f"{WALK_PREFIX} {self.DEEP} ({self.DEEP})"],
            self.out.stderr)

    def test_the_counter_accumulates_across_entries(self):
        self.assertIn("resolved-by-walk 2", census(self.out.stderr),
                      self.out.stderr)

    def test_the_top_level_sibling_stays_silent_in_the_same_run(self):
        """The discriminator, INSIDE one run rather than across two fixtures: a
        build that fires on every resolution renders three notes here."""
        self.assertNotIn("top.md (", self.out.stderr)

    def test_the_thirty_one_component_relpath_renders_untruncated(self):
        """No elision, no `...`, no cap. Asserted on the RELPATH half by
        component count, so a renderer that truncated only the tail is caught
        even if the prefix still matches."""
        note = walk_notes(self.out.stderr)[1]
        rel = note.rsplit("(", 1)[1].rstrip(")")
        self.assertEqual(rel, self.DEEP)
        self.assertEqual(len(rel.split("/")), 31, rel)


class TestTheWalkNoteSurvivesAMismatchRaiseOnItsOwnEntry(_RootCase):
    """ATTACK 2 — a truncating raise sited DOWNSTREAM of the emission, on the
    SAME entry, at a raise site no fixture above uses.

    `TestTheWalkNoteSurvivesATruncatedRun` truncates on a LATER entry, and both
    `...WalkNoteSurvivesTheStrictAmbiguityRaise` classes truncate at the
    `if len(found) > 1:` block, which is the one raise site the emission is
    deliberately sited ABOVE. Neither reaches the shape where the entry that
    earned the note is the entry that then raises — the sha256-mismatch raise
    at `rcpt_verify.py:2338`, which sits between the emission and the loop's
    next iteration, needs no second root, and fires WITHOUT `--strict`.

    Two things are pinned here that nothing above pins. First, survival across
    that raise. Second, NON-DUPLICATION: the `except BaseException:` arm mirrors
    the leg's own `notes` onto `notes_out` on any raise, so a build that also
    appended the walk note to `notes` would render it TWICE on exactly this
    run — a silent double-count against the census, which counts once."""

    def setUp(self):
        super().setUp()
        body = "# findings\nfatal=0\n"
        _, size = self.plant("out-9/bad.md", body)
        h2, s2 = self.plant("out-9/later.md", body)
        self.out = self.verify(receipt(
            artifacts=[("out-9/bad.md", "b" * 64, size),
                       ("out-9/later.md", h2, s2)],
            trace=["READ  /elsewhere/round-0-notes.md"]))

    def test_the_mismatch_is_the_verdict(self):
        # Non-vacuity: the advisory must not preempt or replace the real FAIL.
        self.assertEqual(self.out.returncode, 1, self.out.stderr)
        self.assertIn("ARTIFACTS out-9/bad.md sha256 mismatch", self.out.stderr)

    def test_the_note_for_the_raising_entry_survives_exactly_once(self):
        self.assertEqual(self.out.stderr.count(f"{WALK_PREFIX} out-9/bad.md"), 1,
                         self.out.stderr)

    def test_the_unreached_entry_contributes_no_note_and_no_count(self):
        """The census's honesty half. The second entry never resolved, so a
        build that pre-counted the block would claim a resolution that did not
        happen on this run; `partial` is what says the rest is uncounted."""
        self.assertEqual(walk_notes(self.out.stderr),
                         [f"{WALK_PREFIX} out-9/bad.md (out-9/bad.md)"],
                         self.out.stderr)
        c = census(self.out.stderr)
        self.assertIn("resolved-by-walk 1", c, c)
        self.assertIn("partial", c, c)


class TestTheWalkNoteAndTheProvenanceNoteCoFire(_RootCase):
    """ATTACK 3 — Task 4's `PROVENANCE-ONLY:` and Task 5's `RESOLVED-BY-WALK:`
    on ONE run, which no fixture in either task's suite arranges.

    The two notes share the `notes_out` channel but are produced from different
    places: the walk notes inline on each leg's clean path, the provenance notes
    from `tier2_artifacts`'s `finally:` block. Nothing pinned that they coexist,
    so a build that had one channel consume, reorder or overwrite the other's
    entries — or that emitted the provenance notes into a fresh list — stayed
    green on both suites.

    The ORDER is asserted, not just the membership, because the order is what
    tells a human reading the durable coverage file which leg produced which
    note: artifacts-leg walk note, then that leg's `finally:` provenance note,
    then the witness leg's walk note."""

    def setUp(self):
        super().setUp()
        body = "# findings\nfatal=0\n"
        h, s = self.plant("out-9/f.md", body)
        self.plant("out-9/g.md", body)
        self.out = self.verify(receipt(
            artifacts=[("out-9/f.md", h, s)],
            trace=[f"WROTE  {self.root}/out-9/f.md  sha256:{h}",
                   "READ  out-9/g.md"]))

    def test_the_run_completes(self):
        self.assertEqual(self.out.returncode, 0, self.out.stderr)

    def test_both_channels_fire_and_neither_suppresses_the_other(self):
        self.assertEqual(
            walk_notes(self.out.stderr),
            [f"{WALK_PREFIX} out-9/f.md (out-9/f.md)",
             f"{WALK_PREFIX} {self.root}/out-9/f.md (out-9/f.md)"],
            self.out.stderr)
        self.assertEqual(
            notes(self.out.stderr),
            [f"{NOTE_PREFIX} out-9/g.md (declared in TRACE, not verified)"],
            self.out.stderr)

    def test_the_two_channels_interleave_in_production_order(self):
        emitted = [l for l in self.out.stderr.splitlines()
                   if l.startswith((WALK_PREFIX, NOTE_PREFIX))]
        self.assertEqual(
            [l.split(":", 1)[0] for l in emitted],
            ["RESOLVED-BY-WALK", "PROVENANCE-ONLY", "RESOLVED-BY-WALK"],
            self.out.stderr)

    def test_the_census_counts_only_the_walk_channel(self):
        """`PROVENANCE-ONLY` has no counter (§3.4), so a build that bumped
        `resolved-by-walk` from the provenance emitter would read 3 here."""
        self.assertIn("resolved-by-walk 2", census(self.out.stderr),
                      self.out.stderr)


class TestTheRelpathHalfAloneCannotForgeTheChannel(_RootCase):
    """ATTACK 4 — hostile content in the RELPATH half ONLY.

    `TestTheWalkNoteEscapesTheNameHalfToo` puts its hostile bytes in a
    path-shaped ARTIFACTS name, where the name and the relpath are the SAME
    string — so one escaper call covers both halves and a build that escaped
    only one of them can still pass it (that class exists because the reverse
    mutant, escaping the relpath alone, was green). This fixture separates
    them: the cited name is a clean bare basename that the Tier-1 grammar would
    accept anywhere, and every hostile byte lives in an ON-DISK directory name
    reached through a symlink, i.e. in a string the RECEIPT never spells and
    only `resolve()` produces.

    Three separate primitives are packed into that directory name, because all
    three ride the same half and none is otherwise reachable there: a NEWLINE
    (forges a whole extra advisory line on the channel orchestrators parse), a
    literal census TOKEN (forges the `TIER2-COVERAGE:` substring `_show_path`
    neuters), and an ANSI escape (renders as terminal control in the durable
    coverage file). A directory name cannot contain `/`, which is why the
    forged census payload below is slash-free rather than a full census line."""

    EVIL = "sub\nTIER2-COVERAGE: forged\x1b[31m"

    def setUp(self):
        super().setUp()
        body = "# findings\nfatal=0\n"
        h, s = self.plant(f"{self.EVIL}/real.md", body)
        (self.root / "top.md").symlink_to(
            pathlib.Path(self.EVIL) / "real.md")
        self.out = self.verify(receipt(
            artifacts=[("top.md", h, s)],
            trace=["READ  /elsewhere/round-0-notes.md"]))

    def test_the_run_completes_and_the_note_fires(self):
        """Non-vacuity in the fail-open direction grudge `e0f0a6b75692` names:
        a build that emitted nothing would pass every assertion below."""
        self.assertEqual(self.out.returncode, 0, self.out.stderr)
        self.assertEqual(len(walk_notes(self.out.stderr)), 1, self.out.stderr)

    def test_the_hostile_relpath_renders_fully_escaped(self):
        self.assertEqual(
            walk_notes(self.out.stderr),
            [r"RESOLVED-BY-WALK: top.md "
             r"(sub\nTIER2\x2dCOVERAGE: forged\x1b[31m/real.md)"],
            self.out.stderr)

    def test_no_forged_line_or_token_reaches_the_channel(self):
        self.assertNotIn("\x1b", self.out.stderr)
        self.assertEqual(
            len([l for l in self.out.stderr.splitlines()
                 if "TIER2-COVERAGE:" in l]), 1, self.out.stderr)


class TestTheEmitterGuardsLayerCorrectlyOnTheCleanPath(_RootCase):
    """ATTACK 5 — `_emit_walk_note`'s envelope where NO exception is in flight,
    and the `BaseException` boundary underneath the two layered guards.

    Both hostile-`notes_out` classes above (`TestNoCallerSuppliedParameterCan...`
    and `TestNoHostileNotesOutCanMaskTheWitnessLegsInFlightRaise`) drive the
    `--strict` ambiguity RAISE, so what they pin is that the envelope does not
    MASK a verdict. The complementary obligation — that on a run with no
    verdict to mask the envelope does not MANUFACTURE one, and does not swallow
    the WORK either — was unpinned, and so was the `None` shape (the `--eval`
    and `--selftest` callers' shape, the one where the counter is the only
    surviving record of the resolution).

    The `BaseException` leg answers the layering question directly: the
    emission site's envelope (`except Exception`) sits above the leg's
    `except BaseException:` mirror arm, whose body carries its OWN
    `except Exception: pass`. Two independent swallowing guards on one path is
    exactly the shape in which an interrupt goes missing. It does not: a
    `KeyboardInterrupt` raised by `notes_out.append` propagates out of
    `tier2_artifacts` unconverted, and the counter — bumped before the emission
    by round-3/S1's ordering — is already recorded when it does.

    Driven by a DIRECT call, because the CLI cannot supply an out-parameter."""

    WALK = "out-9/round-9-findings.md"

    class _RaisingAppend(list):
        def append(self, item):
            raise RuntimeError("notes_out.append exploded")

    class _InterruptingAppend(list):
        def append(self, item):
            raise KeyboardInterrupt("interrupted mid-append")

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        self.h, size = self.plant(self.WALK, "# findings\nfatal=0\n")
        self.artifacts = self.rv.parse_artifacts(
            [f"  {self.WALK}  sha256:{self.h}  {size}"])
        # TRACE names the SAME file the ARTIFACTS entry verifies, so its
        # basename is in `verified_bases` and the `finally:` block's
        # `_emit_provenance_notes` appends NOTHING. That is load-bearing for
        # the interrupt leg below: a provenance note would give the run a
        # SECOND unguarded `notes_out.append`, and the interrupt would reach
        # the caller from there whatever `_emit_walk_note`'s envelope caught —
        # measured, a `BaseException` envelope survives the leg without it.
        self.trace = self.rv.parse_trace(
            [f"  1  WROTE  {self.root}/{self.WALK}  sha256:{self.h}"])

    def _run(self, notes_out, cov):
        return self.rv.tier2_artifacts(
            self.artifacts, self.trace, self.root, True, cov, notes_out,
            cache=_cache_for(self.rv, self.artifacts, self.trace, None, "PASS",
                             self.root), verified={})

    def test_a_real_list_receives_the_note_and_the_run_is_clean(self):
        # Non-vacuity for the two shapes below: this is the same call with a
        # cooperating out-parameter, and it must NOT raise.
        cov, notes_out = self.rv._Coverage(), []
        self._run(notes_out, cov)
        self.assertEqual(notes_out,
                         [f"{WALK_PREFIX} {self.WALK} ({self.WALK})"])
        self.assertEqual(cov.counts.get("resolved-by-walk"), 1)

    def test_a_none_out_parameter_still_counts_and_never_raises(self):
        cov = self.rv._Coverage()
        self._run(None, cov)
        self.assertEqual(cov.counts.get("resolved-by-walk"), 1, cov.counts)

    def test_a_raising_append_manufactures_no_verdict_on_the_clean_path(self):
        """The envelope must swallow the emission failure WITHOUT inventing a
        LintError and without skipping the rest of the leg."""
        cov = self.rv._Coverage()
        self._run(self._RaisingAppend(), cov)
        self.assertEqual(cov.counts.get("resolved-by-walk"), 1, cov.counts)
        self.assertEqual(cov.art_verified, 1)

    def test_an_interrupt_is_not_swallowed_by_either_layer(self):
        """`Exception`, not `BaseException` — asserted on the ONE run where the
        walk-note append is the only append the leg makes, so the envelope's
        WIDTH is what decides the outcome and nothing downstream re-raises for
        it. The counter, bumped ahead of the emission by round-3/S1's ordering,
        is already recorded when the interrupt leaves."""
        cov = self.rv._Coverage()
        with self.assertRaises(KeyboardInterrupt):
            self._run(self._InterruptingAppend(), cov)
        self.assertEqual(cov.counts.get("resolved-by-walk"), 1, cov.counts)

    def test_the_fixture_produces_no_provenance_note(self):
        """Non-vacuity for the leg above: if this ever stops holding, the
        interrupt leg silently stops discriminating."""
        notes_out = []
        self._run(notes_out, self.rv._Coverage())
        self.assertEqual(notes_out,
                         [f"{WALK_PREFIX} {self.WALK} ({self.WALK})"])


# --------------------------------------------------------------------------
# INQUISITOR/D1 — the unevaluated/unverified SPELLING collision.
# --------------------------------------------------------------------------
class TestAnUnreachedTwinCannotSilenceAnEvaluatedUnverifiedName(_RootCase):
    """INQUISITOR/D1 — the fourth and last leg of the exact-name ordering.

    `tier2_artifacts` accumulates `evaluated` and `verified_keys` as RAW
    `ARTIFACTS` dict keys (round-3/Minor-4 made that deliberate) and then hands
    `_emit_provenance_notes` four SPELLING sets built with `str()`. The two are
    not the same partition: Minor-4 established that two DISTINCT dict keys can
    share one `str()` spelling (`PurePosixPath("a.txt")` and `"a.txt"`), so one
    spelling can sit in `unevaluated_names` and `unverified_names` at once.

    Minor-4 ruled such a tie must go to the FAIL-NOISY set, and nested
    `verified_names` inside the `unverified_names` override for exactly that
    reason. `unevaluated_names` was left OUTSIDE it, tested first, so the
    fail-SILENT set won: an `ARTIFACTS` key this run never reached bought
    silence for a DIFFERENT key the same run evaluated and reported unverified.
    Silence a receipt author can buy by adding one `ARTIFACTS` line is the
    direction grudge `e0f0a6b75692` forbids.

    Not receipt-author-reachable (`parse_artifacts` only ever produces `str`
    keys) — reachable through the ~40 direct API call sites, the same
    reachability every sibling leg in this file already accepts."""

    def setUp(self):
        super().setUp()
        self.rv = _import_rv()
        self.good, self.size = self.plant("a.txt", "hello\n")
        self.trace = [{"n": 1, "verb": "READ", "args": "a.txt"}]

    def _run(self, artifacts):
        out = []
        with self.assertRaises(self.rv.LintError) as caught:
            self.rv.tier2_artifacts(
                artifacts, self.trace, [self.root], False, None, out,
                cache=_cache_for(self.rv, artifacts, self.trace, None, "PASS",
                                 [self.root]), verified={})
        # Non-vacuity: the declared key really was evaluated and really failed,
        # so it really is in the unverified set.
        self.assertIn("sha256 mismatch", str(caught.exception))
        return [n for n in out if n.startswith(NOTE_PREFIX)]

    def test_the_evaluated_unverified_name_keeps_its_note(self):
        """The defect: SILENT before the fix. `"a.txt"` is evaluated and
        hash-mismatches (-> `unverified_names`); the `PurePosixPath` twin is
        never reached (-> `unevaluated_names`). One spelling, both sets."""
        self.assertEqual(
            self._run({"a.txt": {"hash": "b" * 64, "size": self.size},
                       pathlib.PurePosixPath("a.txt"): {"hash": self.good,
                                                        "size": self.size}}),
            [f"{NOTE_PREFIX} a.txt (declared in TRACE, not verified)"])

    def test_the_control_without_the_unreached_twin_emits(self):
        """Non-vacuity: with only the mismatching key declared, the identical
        TRACE citation DOES get its note — so the silence above was caused by
        the unreached twin's spelling and by nothing else."""
        self.assertEqual(
            self._run({"a.txt": {"hash": "b" * 64, "size": self.size}}),
            [f"{NOTE_PREFIX} a.txt (declared in TRACE, not verified)"])


# --------------------------------------------------------------------------
# INQUISITOR/D2 — `_none_sentinel` must not drain a one-shot section body.
# --------------------------------------------------------------------------
class TestAOneShotSectionBodyIsNotDrainedByTheSentinel(unittest.TestCase):
    """INQUISITOR/D2 — the I8/T10 guard must not itself return the empty set.

    `_none_sentinel` scans `body` for the sentinel, and each parser then
    iterates `body` again for its own entries. On a one-shot `body` — a
    generator, an `iter(...)`, a file object — the scan EXHAUSTS it and the
    entry loop sees nothing, so a body holding legal entries yields `{}`/`[]`
    silently at exit 0. That is the same fail-open shape I8/T10 exists to close,
    re-entering through the clause written to close it, and it is a REGRESSION:
    before `fa108d2` each parser iterated `body` exactly once.

    The section bodies are public-API-supplied with no type enforcement, the
    identical reachability argument this suite already makes for `trace` and the
    `ARTIFACTS` keys."""

    def setUp(self):
        self.rv = _import_rv()

    def test_a_one_shot_artifacts_body_still_yields_its_entries(self):
        body = [f"  a.md  sha256:{H64}  1", f"  b.md  sha256:{H64}  2"]
        self.assertEqual(sorted(self.rv.parse_artifacts(iter(body))),
                         ["a.md", "b.md"])

    def test_a_one_shot_trace_and_claims_body_still_yield_their_entries(self):
        for parse, body in (
                (self.rv.parse_trace, ["  1  READ  a.md", "  2  READ  b.md"]),
                (self.rv.parse_claims, ["  c1=true  from=TRACE#1"])):
            with self.subTest(parser=parse.__name__):
                self.assertEqual(len(parse(iter(body))), len(body))

    def test_a_one_shot_body_holding_the_sentinel_is_still_the_empty_set(self):
        """Non-vacuity from the other side: materialising the body must not
        cost the sentinel its meaning, on the one-shot shape either."""
        self.assertEqual(self.rv.parse_artifacts(iter(["  (none)"])), {})
        self.assertEqual(self.rv.parse_trace(iter(["  (none)"])), [])

    def test_a_one_shot_body_mixing_the_sentinel_with_an_entry_still_raises(self):
        """And the co-occurrence raise still fires — the scan sees BOTH lines,
        which on the pre-fix drain it also did, so this arm is the control that
        keeps the two above honest rather than a second reproduction."""
        with self.assertRaises(self.rv.LintError):
            self.rv.parse_artifacts(iter(["  (none)", f"  a.md  sha256:{H64}  1"]))


# --------------------------------------------------------------------------
# #488 inquisitor / Integration AV1 — the verdict dispatch that decides whether
# the WITNESS LEG runs must not also decide whether the SUPERSEDES
# witness-evidence consequent is ENFORCED. Promoted from the Integration
# dimension: this is a permanent pin, not dimension scratch.
# --------------------------------------------------------------------------
class TestABlockedVerdictCannotDisarmTheSupersessionWitnessGate(_TwoRootCase):
    """siege S-7(a)'s Tier-2 half, on the ONE verdict class it was never wired for.

    The consequent used to sit NESTED inside `_verify_single`'s
    `if verdict in {"PASS", "FAIL"}:` arm, so a BLOCKED receipt took the `else:`,
    bumped `not-applicable (verdict-not-pass-fail)` and never reached it. Tier-1's
    half of the same rule (`lint_v11_local`: `kind in {exec, grep}` AND
    `ran=TRACE#N`) is verdict-INDEPENDENT and still fired, so a BLOCKED receipt had
    to carry a shape-conformant witness — and then nothing checked whether that
    witness resolved to anything at all.

    The three receipts below are byte-identical apart from the VERDICT token, which
    the reviewed subagent writes itself. Measured pre-fix: PASS → exit 1, FAIL →
    exit 1, BLOCKED → exit 0 with the supersession intact. That is DEC-29's
    forbidden key verbatim — the guard narrowed by SHAPE, the narrowing restoring a
    fail-open — and it is the same shape `_verify_single`'s own ⚠ note records
    being closed for the PASS/FAIL pair.

    Not a paper hole: `return-convention.md` § The Sweep step 3 tells the
    orchestrator to process SUPERSEDES with NO check of its own ("Tier-1 has
    already verified: ... witness-evidence (if applicable)") and does not condition
    that step on the new receipt's verdict, and `quality-gate/SKILL.md` lints
    BLOCKED receipts like any other. So a fix agent that cannot finish its work
    could retire a red-team's FAIL finding, its tripwires and its cairn invariant
    by returning BLOCKED with a witness naming a file that does not exist, at
    exit 0, with the census's only trace being a `not-applicable 1
    (verdict-not-pass-fail)` that reads as ordinary for every BLOCKED receipt."""

    def _receipt(self, verdict):
        # The witness names a DECLARED artifact absent from BOTH roots. A bare
        # basename, so the artifacts leg's own disposition is a non-fatal
        # UNVERIFIABLE and the run reaches the consequent under --strict rather
        # than hard-FAILing before it.
        return "\n".join([
            "RCPT v1.1 quality-gate/9-fix",
            f"VERDICT  {verdict}  conf=0.90",
            "ARTIFACTS",
            f"  round-3-findings.md  sha256:{H64}  120",
            "TRACE",
            f"  1  WROTE  round-3-findings.md  sha256:{H64}",
            "CLAIMS",
            '  fix-verified=true  from=21a1b2c3d4e5#L1-L10  pattern="token rotation"',
            "WITNESS    grep:round-3-findings.md#L1-L2  "
            "expect-fail=/Fatal: [1-9]/  ran=TRACE#1",
            "SUSPICION  0.10",
            "NEXT       (none)",
            "TRIPWIRE:  claims-touch(auth/**)",
            "SUPERSEDES: 21a1b2c3d4e5",
        ]) + "\n"

    def test_the_pass_twin_is_refused_the_supersession(self):
        # Non-vacuity control 1: the consequent IS armed and this fixture reaches
        # it. Without it the BLOCKED assertion could pass on a build where the rule
        # fires nowhere at all.
        out = self.verify(self._receipt("PASS"), name="pass.rcpt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("EVALUATED at Tier-2", out.stderr)
        # #488 warden-r2/F-C — the GENERIC half of the message, pinned here so the
        # BLOCKED assertion below is a distinctness claim and not just "some string
        # containing `EVALUATED at Tier-2`".
        self.assertIn("the witness resolved to no evaluated predicate", out.stderr)

    def test_the_fail_twin_is_refused_the_supersession(self):
        # Non-vacuity control 2: GH #501 armed this leg too, so the hole was
        # specific to the third verdict rather than general to "not PASS".
        out = self.verify(self._receipt("FAIL"), name="fail.rcpt")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("EVALUATED at Tier-2", out.stderr)

    def test_the_blocked_twin_is_refused_the_same_supersession(self):
        """The defect. One receipt-authored token turned a hard structural BLOCK
        into exit 0 with the supersession intact."""
        out = self.verify(self._receipt("BLOCKED"), name="blocked.rcpt")
        line = census(out.stderr)
        self.assertIn("EVALUATED at Tier-2", out.stderr,
                      f"BLOCKED receipt retired a predecessor with a witness "
                      f"that resolved nowhere; census: {line}")
        # #488 warden-r2/F-C — the substring above occurs in BOTH message branches,
        # so on its own it does not pin warden-r2/F1's fix at all. F1's whole subject
        # is the WORDING: on BLOCKED the witness leg is verdict-gated OFF (D8.2
        # sub-decision 5), so the generic "the witness resolved to no evaluated
        # predicate" names a resolution that never happened and sends the author
        # hunting a citation that is not the problem. Pin the BLOCKED-specific
        # sentence, and pin that the generic one is NOT what this verdict gets.
        self.assertIn("this receipt is BLOCKED, so the witness leg never ran",
                      out.stderr,
                      f"BLOCKED refusal lost its verdict-specific wording; "
                      f"census: {line}")
        self.assertNotIn("the witness resolved to no evaluated predicate",
                         out.stderr,
                         "BLOCKED refusal regressed to the generic PASS/FAIL "
                         "sentence, which is factually wrong on this path")
        self.assertEqual(out.returncode, 1, out.stderr)

    def test_the_witness_leg_itself_is_still_verdict_gated(self):
        """The half that must NOT move. Lifting the consequent out of the arm
        leaves D8.2 sub-decision 5 exactly where it was: a BLOCKED receipt still
        does not enter the witness leg, and the census still says so with the
        literal code rather than a bare `witness 0/0`."""
        out = self.verify(self._receipt("BLOCKED"), name="blocked2.rcpt")
        self.assertIn("not-applicable 1 (verdict-not-pass-fail)",
                      census(out.stderr), census(out.stderr))
        self.assertIn("witness 0/0", census(out.stderr), census(out.stderr))


# --------------------------------------------------------------------------
# #488 inquisitor / State AV1 — the hashed-body carry across the
# artifacts → witness boundary, with BOTH of the failure modes its two keys
# each close ALONE put on ONE run.
# --------------------------------------------------------------------------
class TestTheHashedBodyCarrySurvivesASpellingDifferenceAndAResolutionChange(
        _RootCase):
    """`bodies` is state one leg BUILDS and another CONSUMES, stored under TWO
    keys precisely because either alone misses a known failure mode: the NAME key
    misses when the two legs SPELL the file differently (`f.md` vs `./f.md`), the
    REALPATH key misses when the name RESOLVES differently between the legs (a
    mid-lint symlink swap). The write site's conclusion — "a hit under either
    binds the predicate to the bytes this leg hashed AND matched" — holds for
    EITHER mode alone and NOT for both together, and both halves are
    receipt-controlled and free: no Tier-1 rule ties the TRACE spelling to the
    ARTIFACTS spelling (the membership rule binds only RANGED kind=grep payloads).

    Measured pre-fix: both keys missed, the carry degraded SILENTLY to a fresh
    disk read of the swapped-in sanitised file, the predicate passed and the
    receipt was accepted — while the single-spelling twin of the same receipt was
    correctly rejected."""

    def _run_legs(self, trace_spelling, key_type=str, swap=True, prep=None):
        """_verify_single's own two-leg sequence, with a mid-run swap between them.

        Returns the LintError message the witness leg raised, or None if it passed
        the receipt clean. Each call gets its OWN root: the swap mutates the tree,
        so a shared one would make the second call depend on the first.

        `key_type` re-spells the DECLARED ARTIFACTS key in the mapping handed to
        `tier2_artifacts` — `str` for the CLI's own key space, `PurePosixPath` for
        the direct-API one this file already treats as in scope (see the write
        site's `str(name)` note). The carry must bind under BOTH.

        `trace_spelling` may be a callable taking the root, for the ABSOLUTE spelling
        §3.2 mandates (SIEGE-S2) — the root is a fresh tempdir per call, so an
        absolute citation cannot be written as a literal. `swap=False` runs the same
        receipt with the tree left ALONE, which is the non-vacuity control: the
        witness must then reach its ordinary predicate rather than this detector."""
        rv = _import_rv()
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = pathlib.Path(td.name)
        secret = "line one\nSECRET token\n"
        h, size = self.plant("f.md", secret)
        self.plant("clean.md", "line one\nharmless\n")
        # SIEGE-R1-2 — `prep` plants whatever the spelling under test needs to EXIST
        # (a symlinked directory component, say) after the two artifacts and before
        # the receipt is written, so the citation is a live path on the pre-swap tree.
        if prep is not None:
            prep(self.root)
        if callable(trace_spelling):
            trace_spelling = trace_spelling(self.root)
        text = receipt(
            artifacts=[("f.md", h, size)],
            trace=[f"READ {trace_spelling}"],
            witness="exec:probe  expect-fail=/SECRET/  ran=TRACE#1")

        sections = rv.parse_receipt(text)
        artifacts = rv.parse_artifacts(sections["ARTIFACTS"])
        artifacts = {key_type(k): v for k, v in artifacts.items()}
        trace = rv.parse_trace(sections["TRACE"])
        witness = rv.parse_witness(sections["WITNESS"])

        cache = _cache_for(rv, artifacts, trace, witness, "PASS", self.root)
        verified = {}
        cov = rv._Coverage()
        rv.tier2_artifacts(artifacts, trace, self.root, True, cov, [],
                           cache=cache, verified=verified)

        # The swap the carry exists to defeat: the hashed regular file is replaced
        # by a symlink to a sanitised sibling AFTER it was hashed.
        if swap:
            (self.root / "f.md").unlink()
            (self.root / "f.md").symlink_to(self.root / "clean.md")

        try:
            rv.tier2_witness(witness, trace, self.root, True, "PASS",
                             cov, {}, [], cache=cache, verified=verified)
        except rv.LintError as e:
            return str(e)
        return None

    def test_siege_s2_the_swap_detector_is_spelling_invariant(self):
        """SIEGE-S2 — the detector compared `PurePosixPath` values RAW-lexically, so it
        could only ever fire on a citation spelled the same way as the §3.1-relative
        ARTIFACTS declaration. §3.2 MANDATES the ABSOLUTE spelling for a tracked file,
        and an absolute path never lexically equals a relative one: every subagent
        following the convention lost the swap protection the relative form kept.

        Measured on `ba482e2` with this same harness: `./f.md` RAISED, while
        `/<root>/f.md` (mandated) and `f.md/../f.md` (second bypass spelling —
        `PurePosixPath` does not collapse `..`) both passed CLEAN with the predicate run
        against the swapped-in sanitised bytes. The old code SAID SO, in a scope
        paragraph that called leaving it open deliberate.

        Each spelling gets its OWN no-swap control, and the controls are what make this
        non-vacuous: without them the detector could be narrowed to an unconditional
        raise and every attack arm would still pass. A control must reach the ORDINARY
        expect-fail predicate — that is the detector staying silent on a tree that never
        moved."""
        spellings = {
            "relative": "./f.md",                       # already detected pre-fix
            "absolute-mandated": lambda r: str(r / "f.md"),
            "uncollapsed-dotdot": "f.md/../f.md",
        }
        for label, spelling in spellings.items():
            with self.subTest(spelling=label):
                attacked = self._run_legs(spelling)
                self.assertIsNotNone(
                    attacked,
                    f"the {label} spelling let a mid-lint symlink swap through: both "
                    f"carry keys missed and the double-miss detector was silent, so "
                    f"the predicate ran against bytes NO leg hashed")
                self.assertIn("identity CHANGED between the legs", attacked)

                control = self._run_legs(spelling, swap=False)
                self.assertIsNotNone(
                    control,
                    f"control precondition broken for {label}: the unswapped tree "
                    f"did not reach the expect-fail predicate at all")
                self.assertIn("expect-fail regex", control)

    def test_siege_r1_2_the_detector_sees_the_cited_names_own_resolution(self):
        """SIEGE-R1-2 — SIEGE-S2's own fix, bypassed by re-spelling the identical
        attack. `_carry_spellings` was purely LEXICAL: it resolved the ROOTS and then
        did `cand.relative_to(base)`, so the only absolute citations it could collapse
        onto the declared name were those whose prefix a string comparison already
        matched. The cited NAME was never resolved, so any spelling whose prefix
        `relative_to` cannot collapse produced no candidate that intersects the
        declaration and the detector went silent again:

          * a symlinked DIRECTORY component the subagent plants in a root it owns
            (`ln -s . link`, then cite through `link/`), absolute or relative;
          * a DOUBLED LEADING SLASH — `PurePosixPath` and `posixpath.normpath` both
            preserve `//` as a distinct root component (POSIX reserves it), while
            `Path.resolve()` collapses it, so `//<root>/f.md` is a free spelling of
            the mandated absolute one.

        Measured on `20c7b7b`: `_carry_spellings('<root>/link/f.md', roots)` returned
        `{'<root>/link/f.md', 'link/f.md'}` — no `f.md` — and each of these spellings
        passed the swap CLEAN with the predicate run against the sanitised bytes.

        Same control discipline as the SIEGE-S2 arm above, and for its reason: without
        the no-swap control an unconditional raise would satisfy every attack arm."""
        def link_prep(root):
            (root / "link").symlink_to(".")

        spellings = {
            "symlinked-dir-absolute": (lambda r: str(r / "link" / "f.md"), link_prep),
            "symlinked-dir-relative": ("link/f.md", link_prep),
            "doubled-leading-slash": (lambda r: "/" + str(r / "f.md"), None),
        }
        for label, (spelling, prep) in spellings.items():
            with self.subTest(spelling=label):
                attacked = self._run_legs(spelling, prep=prep)
                self.assertIsNotNone(
                    attacked,
                    f"the {label} spelling let a mid-lint symlink swap through: both "
                    f"carry keys missed and the double-miss detector was silent, so "
                    f"the predicate ran against bytes NO leg hashed")
                self.assertIn("identity CHANGED between the legs", attacked)

                control = self._run_legs(spelling, swap=False, prep=prep)
                self.assertIsNotNone(
                    control,
                    f"control precondition broken for {label}: the unswapped tree "
                    f"did not reach the expect-fail predicate at all")
                self.assertIn("expect-fail regex", control)

    def test_an_undeclared_witness_name_still_takes_the_independent_read(self):
        """Re-aimed onto the empty-payload shape FATAL-12-1/FATAL-13-1 prescribes:
        a rangeless `grep:` witness whose non-empty payload names an undeclared file
        now hard-FAILs at the Tier-1-style membership rule before `bound` is
        computed, so the independent-read disposition (`unhashed-body`) is reached
        only via the empty payload (`stated == ""`). The cited TRACE entry still
        names the same undeclared file, so the read, and therefore the note, is
        unchanged."""
        h, s = self.plant("declared.md", "declared and verified\n")
        self.plant("round-3-findings.md", "# Round 3 findings\nFatal: 0\n")
        out = self.verify(receipt(
            artifacts=[("declared.md", h, s)],
            trace=["READ declared.md",
                   f"WROTE round-3-findings.md  sha256:{H64}"],
            witness="grep:  expect-fail=/Fatal: [1-9]/  ran=TRACE#2"))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("unhashed-body", census(out.stderr), census(out.stderr))


# --------------------------------------------------------------------------
# #488 inquisitor / Edge AV1 — the exact-name override vs §3.2's MANDATED
# absolute TRACE spelling.
# --------------------------------------------------------------------------
class TestTheExactNameOverrideSurvivesTheMandatedAbsoluteSpelling(_RootCase):
    """A DECLARED name this run evaluated and reported UNVERIFIED must keep its
    PROVENANCE-ONLY note however §3.2 spells it in TRACE.

    The two halves were built in different tasks: the override is keyed on the
    DECLARED ARTIFACTS name (a bare relative, §3.1) while §3.2 MANDATES that a
    tracked repo file's TRACE home carry its ABSOLUTE path — so nobody ever ran
    the override against the spelling the ruling requires on the other leg. The
    design doc prices the basename collision as STRUCTURAL rather than
    hypothetical (`quality-gate/SKILL.md`'s per-chunk `round-N-findings.md` /
    `fix-journal.md` guarantee sibling chunks share a basename).

    The receipt is otherwise immaculate: `a/x.md` is real and hash-verifies,
    `b/x.md` is declared and absent. Both arms print
    `UNVERIFIABLE: b/x.md (no file under root)`; the only difference is which of
    the two MANDATED name forms the TRACE entry uses."""

    def setUp(self):
        super().setUp()
        h, size = self.plant("a/x.md", "the verified sibling\n")
        self.arts = [("a/x.md", h, size), ("b/x.md", H64, "1")]

    def _run(self, cited):
        r = self.verify(receipt(artifacts=self.arts, trace=[f"READ {cited}"]),
                        name="r.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("UNVERIFIABLE: b/x.md", r.stderr,
                      "fixture vacuous: b/x.md was not reported unverified")
        return r

    def test_the_bare_declared_spelling_keeps_its_note(self):
        # CONTROL — proves the override exists and the fixture reaches it.
        r = self._run("b/x.md")
        self.assertTrue(any("b/x.md" in n for n in notes(r.stderr)),
                        f"no note for the bare spelling: {notes(r.stderr)}")

    def test_the_mandated_absolute_spelling_keeps_its_note_too(self):
        # THE ATTACK. Spelled the way §3.2 mandates, `name` missed all three
        # exact-name sets (which held declared RELATIVE names) and fell through to
        # the basename key, where the UNRELATED verified `a/x.md` had already put
        # `x.md` into `verified_bases`. The run then said `UNVERIFIABLE: b/x.md`
        # and stayed silent about the TRACE entry citing that same file, on the
        # same stderr — silence a receipt author buys with one extra ARTIFACTS
        # line, grudge e0f0a6b75692's direction.
        r = self._run(str(self.root / "b/x.md"))
        self.assertTrue(any("b/x.md" in n for n in notes(r.stderr)),
                        f"no note for the mandated absolute spelling: "
                        f"{notes(r.stderr)}")

    def test_a_verified_name_cited_absolutely_is_still_silent(self):
        """The symmetric half, and the one that keeps the fix from being pure
        noise: §3.2 makes the two legs spell one file differently BY DESIGN, so
        the absolute citation of a name that DID hash-verify must stay silent.
        The suppressors gained the same spelling the override did, so this holds
        for the exact-name reason now and not only via the basename key."""
        h, size = self.plant("only.md", "verified and cited absolutely\n")
        r = self.verify(receipt(artifacts=[("only.md", h, size)],
                                trace=[f"READ {self.root / 'only.md'}"]),
                        name="v.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("artifacts 1/1", census(r.stderr), census(r.stderr))
        self.assertEqual([], notes(r.stderr),
                         f"a verified name was called unverified: {notes(r.stderr)}")


# --------------------------------------------------------------------------
# #488 warden-r2 / F3 — the exact-name override vs a SYMLINKED --root.
# --------------------------------------------------------------------------
class TestTheExactNameOverrideSurvivesASymlinkedRoot(unittest.TestCase):
    """WARDEN-R2/F3 — the same headline case as AV1 above, reached by a second
    door: the AS-SUPPLIED root spelling.

    `_as_roots` resolves symlinks unconditionally, so when the `--root` argument
    is ITSELF a symlink the lexical root-join produced only the REALPATH spelling
    — while a real receipt's §3.2 TRACE citation carries the path the dispatch was
    handed, i.e. the as-supplied one. The exact-name override therefore missed,
    the citation fell through to the basename key, and the unrelated verified
    `a/x.md` had already put `x.md` into `verified_bases`: silence, at exit 0, on
    the very shape AV1 was filed to make audible.

    Not exotic. Any `/tmp`-rooted dispatch on macOS (`/var`→`/private/var`), and
    many CI runners' symlinked workdirs, supply a symlinked root by default."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.real = base / "real"
        (self.real / "a").mkdir(parents=True)
        self.link = base / "link"
        self.link.symlink_to(self.real)
        body = "the verified sibling\n"
        (self.real / "a" / "x.md").write_text(body)
        self.arts = [("a/x.md", hashlib.sha256(body.encode()).hexdigest(),
                      str(len(body))),
                     ("b/x.md", H64, "1")]

    def _run(self, root, cited, name):
        p = self.real / name
        p.write_text(receipt(artifacts=self.arts, trace=[f"READ {cited}"]))
        out = run("--tier2", "--root", str(root), str(p))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("UNVERIFIABLE: b/x.md", out.stderr,
                      "fixture vacuous: b/x.md was not reported unverified")
        return out

    def test_the_realpath_spelling_keeps_its_note(self):
        """CONTROL — the spelling the resolved root-join always produced. Green
        before and after; it is here so the attack arm cannot be read as the
        override being broken generally."""
        out = self._run(self.link, str(self.real / "b/x.md"), "ctl.txt")
        self.assertTrue(any("b/x.md" in n for n in notes(out.stderr)),
                        f"no note for the realpath spelling: {notes(out.stderr)}")

    def test_the_as_supplied_symlinked_spelling_keeps_its_note_too(self):
        """THE ATTACK. Byte-identical to the control except that the TRACE entry
        spells the root the way the invocation did. Pre-fix this stderr carried
        `UNVERIFIABLE: b/x.md` and NOTHING about the TRACE entry citing that same
        file — the grudge e0f0a6b75692 direction, bought by a symlink nobody in
        the receipt chose."""
        out = self._run(self.link, str(self.link / "b/x.md"), "atk.txt")
        self.assertTrue(any("b/x.md" in n for n in notes(out.stderr)),
                        f"a symlinked --root silenced the override for the "
                        f"as-supplied spelling: {notes(out.stderr)}")


# --------------------------------------------------------------------------
# #488 warden-r2 / F4 — the root-join must not widen a DEGENERATE basename.
# --------------------------------------------------------------------------
class TestTheRootJoinDoesNotWidenADegenerateDeclaration(_TwoRootCase):
    """WARDEN-R2/F4 — leg-1's silence-via-degenerate-declaration hole, reopened
    through the EXACT-NAME leg instead of the basename leg it was closed on.

    The lexical root-join widens all THREE exact-name sets uniformly, and two of
    them (`unevaluated_names`, `verified_names`) are fail-SILENT suppressors. For
    a non-degenerate declared name that is inert — the basename leg already covers
    it. For a DEGENERATE-basename one (`x/`, the `_DEGENERATE_BASES` family leg-1
    added a basename-leg screen for), the join MANUFACTURES an absolute spelling
    under every supplied root, so one hash-verified `x/` under the dispatch root
    silently bought silence for `<findings-root>/x/` — a different, unverified,
    cross-root citation sharing nothing with it but a degenerate basename.

    Nothing in the suite covered this, which is why it stayed green through
    `4a11bcf`. Measured pre-fix on the MANDATED two-root invocation: exit 0, zero
    notes. The basename leg cannot catch it either — `_DEGENERATE_BASES` keeps
    `""` out of `verified_bases`, which is exactly what leaves the exact-name leg
    as the only suppressor in play."""

    def setUp(self):
        super().setUp()
        body = "body\n"
        self.h = hashlib.sha256(body.encode()).hexdigest()
        self.size = str(len(body))
        (self.dispatch / "x").write_text(body)

    def _run(self, cited, name):
        # TRACE#1 is the witness's own citation and is deliberately the DECLARED
        # spelling: the cross-root citation under test sits at #2, so the witness
        # leg cannot hard-FAIL on it and bury the advisory channel's answer.
        out = self.verify(receipt(artifacts=[("x/", self.h, self.size)],
                                  trace=["READ  x/", f"READ  {cited}"]),
                          name=name)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("artifacts 1/1", out.stderr)   # non-vacuity: `x/` verified
        return out

    def test_a_cross_root_degenerate_citation_is_not_silenced(self):
        """THE ATTACK. `<findings>/x/` is not the verified `<dispatch>/x/` and no
        file answers it, yet the unscreened join put it in `verified_names`."""
        out = self._run(str(self.findings / "x") + "/", "atk.txt")
        self.assertTrue(
            any(str(self.findings) in n for n in notes(out.stderr)),
            f"a verified degenerate declaration bought silence for an unrelated "
            f"cross-root citation: {notes(out.stderr)}")

    def test_an_ordinary_cross_root_citation_still_speaks(self):
        """Non-vacuity control: the emitter is live on this fixture for a
        non-degenerate name too, so the arm above is about the degenerate join
        and not about the two-root shape."""
        out = self._run(str(self.findings / "q.md"), "ctl.txt")
        self.assertTrue(any("q.md" in n for n in notes(out.stderr)),
                        f"no note for an ordinary cross-root citation: "
                        f"{notes(out.stderr)}")


# --------------------------------------------------------------------------
# #488 inquisitor / Edge AV2 — one ARTIFACTS name declared twice.
# --------------------------------------------------------------------------
class TestOneNameDeclaredTwiceIsNotSilentlyCollapsed(_RootCase):
    """Two ARTIFACTS lines naming one file with CONTRADICTORY hashes must not
    verify clean and silent.

    AC-2 landed a LEXICAL GRAMMAR in `parse_artifacts` ("a legal ARTIFACTS <name>
    is a POSIX-relative path"), but the accumulator behind it is a dict, so the
    grammar admitted the same name twice and the LAST line silently won. Task 2
    owned the grammar, Task 4 owned the verified/unverified bookkeeping the census
    reports, and neither owned the accumulator between them. `parse_receipt`
    already rejects a duplicated SECTION by name, so duplicate-rejection was an
    established policy in this file that the new name grammar did not inherit."""

    def setUp(self):
        super().setUp()
        self.h, self.size = self.plant("x.md", "real content\n")

    def _run(self, arts, name):
        return self.verify(receipt(artifacts=arts, trace=["READ x.md"]), name=name)

    def test_the_outcome_does_not_depend_on_which_line_came_last(self):
        # The two receipts declare the SAME two facts about the SAME name, in
        # opposite order. A verifier whose verdict flips on line order is
        # reporting position, not content. Measured pre-fix: 0 vs 1.
        honest = ("x.md", self.h, self.size)
        bogus = ("x.md", H64, self.size)
        first = self._run([bogus, honest], "dup-honest-last.txt")
        second = self._run([honest, bogus], "dup-honest-first.txt")
        self.assertEqual(
            first.returncode, second.returncode,
            "the verdict flips on ARTIFACTS line ORDER alone:\n"
            f"  bogus-then-honest EXIT={first.returncode}\n"
            f"  honest-then-bogus EXIT={second.returncode}")

    def test_the_dropped_declaration_is_reported_on_some_channel(self):
        # The receipt makes TWO declarations; the run checked ONE and said so
        # nowhere. `artifacts 1/1` is indistinguishable from a single-line
        # receipt, so an orchestrator recording the census could not tell that a
        # hash it may itself have logged was never verified.
        r = self._run([("x.md", H64, self.size), ("x.md", self.h, self.size)],
                      "dup.txt")
        silent = (r.returncode == 0
                  and "duplicat" not in r.stderr.lower()
                  and "artifacts 1/1" in census(r.stderr))
        self.assertFalse(
            silent,
            "a contradictory duplicate declaration verified clean and silent:\n"
            f"  EXIT={r.returncode}\n  {census(r.stderr)}")

    def test_two_distinct_names_are_untouched(self):
        """Non-vacuity: the rejection is keyed on the name repeating, not on the
        entry count. A receipt declaring two DIFFERENT names still verifies."""
        o, osize = self.plant("y.md", "other content\n")
        r = self._run([("x.md", self.h, self.size), ("y.md", o, osize)], "two.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("artifacts 2/2", census(r.stderr), census(r.stderr))


# --------------------------------------------------------------------------
# #488 inquisitor / Edge AV4 — the advisory's verb set vs the verb set the
# Tier-1 grammar admits. RECORDED AS AN ACCEPTED LIMITATION, not closed.
# --------------------------------------------------------------------------
class TestTheAdvisoryScopeIsDeliberatelyNarrowerThanTheTraceVerbSet(_RootCase):
    """§3.4's advisory covers READ/EDIT/WROTE and NOT the other four verbs
    `parse_trace` admits — `CONSULTED` most consequentially, since
    `return-convention.md:84` defines it as covering "web/doc/prior-artifact
    lookup" and a cited PRIOR ARTIFACT is exactly the population the silence rule
    ranges over. So a `CONSULTED` citation of an undeclared, unverified file gets
    no advisory at all.

    THIS TEST PINS THE CURRENT, NARROWER BEHAVIOUR AS INTENTIONAL. It is not a
    statement that the coverage hole is harmless — it is a real gap and it is
    recorded as one at `_PROVENANCE_VERBS`. It is a statement about WHO may close
    it: the frozen design doc scopes §3.4 to READ/EDIT/WROTE explicitly
    throughout, so adding `CONSULTED` to the emitter would make the code diverge
    from its own ruling, and it would move the advisory's note volume (which the
    doc costs elsewhere) on receipts naming no file at all, because `CONSULTED`
    references are frequently URLs. Widening the verb set is a RULING AMENDMENT.
    If this test goes red, the question to ask is whether the ruling was amended —
    not how to make it green."""

    def setUp(self):
        super().setUp()
        self.h, self.size = self.plant("x.md", "declared and verified\n")
        # A REAL file the receipt never declares and the run never verifies.
        self.plant("q.md", "undeclared\n")

    def _notes(self, verb):
        r = self.verify(
            receipt(artifacts=[("x.md", self.h, self.size)],
                    trace=["READ x.md", f"{verb} q.md"]),
            name=f"{verb.lower()}.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        return notes(r.stderr)

    def test_a_read_citation_of_an_undeclared_file_speaks(self):
        # CONTROL — the same undeclared name under a covered verb. Without it the
        # assertion below would pass on a build where the advisory fires nowhere.
        self.assertTrue(any("q.md" in n for n in self._notes("READ")),
                        "fixture vacuous: even READ was silent")

    def test_a_consulted_citation_of_an_undeclared_file_is_deliberately_silent(self):
        # THE ACCEPTED GAP, pinned so a later change cannot close it by accident
        # without amending the ruling first.
        self.assertFalse(
            any("q.md" in n for n in self._notes("CONSULTED")),
            "a CONSULTED citation now emits a PROVENANCE-ONLY note. The design "
            "doc scopes §3.4 to READ/EDIT/WROTE; if the ruling was amended, "
            "update this pin and _PROVENANCE_VERBS's note together — if it was "
            "not, the emitter has silently outgrown its own ruling")

    def test_the_narrow_scope_is_recorded_where_the_verb_set_is_defined(self):
        """The limitation has to be READABLE at the site a future maintainer
        edits, or "deliberate" is only true in this test file."""
        text = SCRIPT.read_text()
        head = text.split("_PROVENANCE_VERBS = frozenset")[0]
        self.assertIn("CONSULTED", head[-3000:],
                      "_PROVENANCE_VERBS carries no record of the accepted "
                      "CONSULTED gap")



if __name__ == "__main__":
    unittest.main(verbosity=1)
