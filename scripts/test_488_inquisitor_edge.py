#!/usr/bin/env python3
"""#488 c1 — inquisitor / Edge Cases dimension.

Cross-component boundary tests over the ASSEMBLED c1 feature (Tasks 1-8 plus
warden leg-1's temper fixes), not over any single task's diff. Each class below
attacks a boundary that only exists because two of the new components meet:

  * the exact-name override legs (`unevaluated_names` / `unverified_names` /
    `verified_names`, T2 + adversarial/F3 + temper/leg-1) meeting §3.2's
    MANDATED absolute `TRACE` spelling;
  * the Tier-1 lexical grammar (AC-2) meeting `parse_artifacts`'s dict
    accumulator, i.e. one name declared twice;
  * the `_read_capped` cumulative read ceiling — the ONE truncating raise site
    the committed truncation-partition tests do not exercise — meeting §3.4's
    truncation rule and T7's walk note;
  * `_PROVENANCE_VERBS` meeting the closed `TRACE` verb set `parse_trace`
    actually admits.

Run from repo root:  python3 scripts/test_488_inquisitor_edge.py

Deliberately a SEPARATE file from `scripts/test_488_name_space.py`:
`scripts/dec31_sweep.py` pins that suite's exact test count (`TOTAL_TESTS`) and
every mutant row's expected failure set, so appending here keeps the DEC-31
harness discriminating instead of reddening it on a count change.
"""
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "rcpt_verify.py"
WALK_PREFIX = "RESOLVED-BY-WALK:"


def _import_rv():
    spec = importlib.util.spec_from_file_location("rcpt_verify", SCRIPT)
    rv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rv)
    return rv


def walk_notes(stderr):
    return [l.strip() for l in stderr.splitlines()
            if l.strip().startswith(WALK_PREFIX)]


# --------------------------------------------------------------------------
# ATTACK VECTOR 3 — the cumulative read ceiling as a truncation site.
#
# `tier2_artifacts` has five raise sites that truncate the entry loop, and
# §3.4's truncation rule has to hold at every one of them. The committed suite
# exercises the hash-mismatch site and the --strict path-shaped/ambiguity
# sites; the `_read_capped` CUMULATIVE budget site (SIEGE-R2BA-2, a boundary
# nothing in the c1 diff touched) is the one that is never reached, because
# reaching it at the CLI costs 64 MiB of disk. It is also the only truncating
# raise whose trigger is a MAXIMUM VALUE rather than a content mismatch, which
# is why it belongs to this dimension.
# --------------------------------------------------------------------------
class TestTheTruncationPartitionHoldsAtTheReadBudgetCeiling(unittest.TestCase):

    def setUp(self):
        self.rv = _import_rv()
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = pathlib.Path(self.td.name)
        (self.root / "deep" / "sub").mkdir(parents=True)
        self.small = b"s\n"
        (self.root / "deep" / "sub" / "a.md").write_bytes(self.small)
        self.big = b"B" * 100
        (self.root / "big.md").write_bytes(self.big)
        (self.root / "later.md").write_bytes(b"L\n")
        # The ceiling is a module constant named in the bullet it produces;
        # lowering it is how the boundary becomes reachable in a unit test.
        self.rv.ARTIFACT_READ_CAP = 10

        def _sha(b):
            return hashlib.sha256(b).hexdigest()

        self.artifacts = {
            "deep/sub/a.md": {"hash": _sha(self.small), "size": "2"},
            "big.md": {"hash": _sha(self.big), "size": "100"},
            "later.md": {"hash": _sha(b"L\n"), "size": "2"},
        }
        self.trace = [{"n": 1, "verb": "READ", "args": "deep/sub/a.md"},
                      {"n": 2, "verb": "READ", "args": "big.md"},
                      {"n": 3, "verb": "READ", "args": "later.md"}]
        self.notes_out = []
        self.cov = self.rv._Coverage()
        with self.assertRaises(self.rv.LintError) as ctx:
            self.rv.tier2_artifacts(self.artifacts, self.trace, self.root,
                                    True, self.cov, None, self.notes_out)
        self.err = str(ctx.exception)

    def test_the_budget_ceiling_is_what_truncated_the_run(self):
        self.assertIn("exceeds the Tier-2 read budget", self.err)
        self.assertTrue(self.cov.partial, "a truncated leg must report partial")

    def test_the_entry_the_ceiling_stopped_on_is_audible(self):
        # `big.md` was EVALUATED (reached, resolution done, read refused) and
        # not verified, so §3.4 says its TRACE citation still speaks.
        self.assertTrue(
            any("big.md" in n for n in self.notes_out),
            f"the raising entry lost its note: {self.notes_out}")

    def test_the_entry_the_ceiling_never_reached_stays_silent(self):
        # `later.md` might still have verified; §3.4 forbids crying wolf on it.
        self.assertFalse(
            any("later.md" in n for n in self.notes_out),
            f"an unreached entry was reported: {self.notes_out}")

    def test_the_verified_entrys_walk_note_survives_the_ceiling(self):
        # T7's note is emitted at resolution time, before the read that raises,
        # so a later entry's budget refusal must not silence it.
        self.assertEqual(len(walk_notes("\n".join(self.notes_out))), 1,
                         f"walk note lost or duplicated: {self.notes_out}")
        self.assertEqual(self.cov.counts.get("resolved-by-walk"), 1,
                         f"counter disagrees with the note: {self.cov.counts}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
