#!/usr/bin/env python3
"""Tests for scripts/cairn.py — the Layer 3 Phase Entry Check + Reconciliation Pass.

Pure stdlib unittest, mirrors the repo convention (scripts/test_compass.py etc.).
Run: python3 scripts/test_cairn.py   (registered in scripts/run_tests.sh)
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO_ROOT)

from scripts import cairn  # noqa: E402

RUN_ID = "2026-09-18T12-00-00"
CP = f"cairn-{RUN_ID}.md"  # canonical cairn filename (Run 3 authority)


def mk_cairn(title=True, phase=("design", 2), invariants=None, obligations=None,
             ledger=None, run_id=RUN_ID, parent_skill="build"):
    lines = []
    if title:
        lines.append(f"# Cairn — {run_id}")
        lines.append("")
    lines.append("## PHASE")
    lines.append(f"phase: {phase[0]} / {phase[1]}")
    lines.append("started-at: 2026-09-18T12:00:00")
    lines.append(f"parent-skill: {parent_skill}")
    lines.append("")
    lines.append("## INVARIANTS")
    lines.extend(invariants if invariants is not None else ["I-01: auth token rotation [ref: 0123456789ab]"])
    lines.append("")
    lines.append("## OPEN_OBLIGATIONS")
    lines.extend(obligations if obligations is not None else [])
    lines.append("")
    lines.append("## LEDGER")
    if ledger is None:
        ledger = ["design/1 | dispatches=1 receipts=1 verdict=PASS | design gate passed"]
    lines.extend(ledger)
    return "\n".join(lines) + "\n", CP if title else "cairn-x.md"


def mk_ledger(*rows):
    return [
        {"dispatch_id": f"{i}-x", "phase": rows[i][0], "rcpt_sha256": rows[i][1], "verdict": rows[i][2]}
        for i in range(len(rows))
    ]


SHA1 = "0123456789ab" + "0" * 52  # 64 hex chars, 12-hex prefix 0123456789ab
SHA2 = "ffffffffffff" + "0" * 52


class ParseEntryCheckTest(unittest.TestCase):
    def test_valid_pass(self):
        txt, _ = mk_cairn()
        self.assertEqual(cairn.phase_entry_check(txt), [])

    def test_missing_section(self):
        txt, _ = mk_cairn()
        txt = txt.replace("## LEDGER\n", "")
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("missing section" in e for e in errs))

    def test_section_order(self):
        txt, _ = mk_cairn()
        txt = txt.replace("## INVARIANTS", "## @@@").replace("## OPEN_OBLIGATIONS", "## INVARIANTS").replace("## @@@", "## OPEN_OBLIGATIONS")
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("out of order" in e for e in errs))

    def test_prose_outside_sections(self):
        inv = ["I-01: valid fact", "this is stray prose"]
        txt, _ = mk_cairn(invariants=inv)
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("violates grammar" in e for e in errs))

    def test_preamble_prose_between_title_and_phase(self):
        txt, _ = mk_cairn()
        txt = txt.replace("# Cairn — " + RUN_ID + "\n", "# Cairn — " + RUN_ID + "\nSTRAY PROSE HERE\n")
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("prose between title" in e for e in errs))

    def test_phase_not_three_lines(self):
        txt, _ = mk_cairn()
        txt = txt.replace("started-at: 2026-09-18T12:00:00\n", "")
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("exactly 3" in e for e in errs))

    def test_phase_expect_mismatch(self):
        txt, _ = mk_cairn()
        errs = cairn.phase_entry_check(txt, expect_phase="plan / 1")
        self.assertTrue(any("expected next phase" in e for e in errs))

    def test_phase_malformed_value(self):
        txt, _ = mk_cairn()
        txt = txt.replace("phase: design / 2", "phase: design")
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("phase value malformed" in e for e in errs))

    def test_invariant_grammar(self):
        txt, _ = mk_cairn(invariants=["not an invariant line"])
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("INVARIANTS line violates grammar" in e for e in errs))

    def test_invariant_ordinal_gap(self):
        txt, _ = mk_cairn(invariants=["I-01: a", "I-03: c"])
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("ordinal out of order" in e for e in errs))

    def test_invariant_todo(self):
        txt, _ = mk_cairn(invariants=["I-01: TODO"])
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("TODO" in e for e in errs))

    def test_invariant_over_240(self):
        txt, _ = mk_cairn(invariants=["I-01: " + "x" * 245])
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("exceeds 240" in e for e in errs))

    def test_obligation_over_240(self):
        txt, _ = mk_cairn(obligations=["- [ ] " + "x" * 245])
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("OPEN_OBLIGATIONS line exceeds 240" in e for e in errs))

    def test_ledger_summary_over_80(self):
        txt, _ = mk_cairn(ledger=["design/1 | dispatches=1 receipts=1 verdict=PASS | " + "s" * 90])
        errs = cairn.phase_entry_check(txt)
        self.assertTrue(any("LEDGER summary exceeds 80" in e for e in errs))


class ReconciliationTest(unittest.TestCase):
    def test_pass(self):
        txt, cp = mk_cairn()
        ledger = mk_ledger(("build:design/1", SHA1, "PASS"))
        rep = cairn.reconciliation_pass(txt, ledger=ledger, cairn_path=cp)
        self.assertTrue(rep["ok"], rep["escalations"])

    def test_rule5_skipped_completion_lines(self):
        txt, cp = mk_cairn(phase=("execute", 4), ledger=["design/1 | dispatches=1 receipts=1 verdict=PASS | x"])
        rep = cairn.reconciliation_pass(txt, ledger=mk_ledger(("build:design/1", SHA1, "PASS")), cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule5" in e for e in rep["escalations"]))

    def test_rule5_phase_counter_lagged(self):
        # PHASE counter == LEDGER tail counter (PHASE not advanced) -> escalate
        txt, cp = mk_cairn(phase=("design", 1), ledger=["design/1 | dispatches=1 receipts=1 verdict=PASS | x"])
        rep = cairn.reconciliation_pass(txt, ledger=mk_ledger(("build:design/1", SHA1, "PASS")), cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule5" in e and "lagged" in e for e in rep["escalations"]))

    def test_rule5_empty_ledger_high_counter(self):
        txt, cp = mk_cairn(phase=("design", 2), ledger=[])
        rep = cairn.reconciliation_pass(txt, ledger=None, cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule5" in e for e in rep["escalations"]))

    def test_rule1_dispatch_count_mismatch(self):
        ledger_lines = [
            "design/1 | dispatches=1 receipts=1 verdict=PASS | design",
            "plan/2 | dispatches=1 receipts=1 verdict=PASS | plan",
        ]
        ld = mk_ledger(
            ("build:design/1", SHA1, "PASS"), ("build:design/1", SHA2, "PASS"),
            ("build:plan/2", SHA2, "PASS"),
        )
        txt, cp = mk_cairn(phase=("execute", 3), ledger=ledger_lines)
        rep = cairn.reconciliation_pass(txt, ledger=ld, cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule1" in e for e in rep["escalations"]))

    def test_rule1_tail_mismatch_escalates(self):
        # deficit on the sole (tail) line -> escalate fail-closed (narrow repair is
        # orchestrator judgment, never auto-certified)
        ld = mk_ledger(("build:design/1", SHA1, "PASS"))
        txt, cp = mk_cairn(ledger=["design/1 | dispatches=3 receipts=1 verdict=PASS | x"])
        rep = cairn.reconciliation_pass(txt, ledger=ld, cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule1" in e for e in rep["escalations"]))

    def test_rule1_ledger_path_provided_but_missing(self):
        txt, cp = mk_cairn()
        rep = cairn.reconciliation_pass(txt, ledger=None, cairn_path=cp, ledger_provided=True)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("ledger path provided but file missing" in e for e in rep["escalations"]))

    def test_rule1_dispatches_declared_without_ledger(self):
        txt, cp = mk_cairn(obligations=[], invariants=["I-01: plain fact"])
        rep = cairn.reconciliation_pass(txt, ledger=None, cairn_path=cp, ledger_provided=False)
        # LEDGER declares dispatches=1 but no ledger -> escalate (not receipt-less no-op)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("dispatches>0" in e for e in rep["escalations"]))

    def test_rule2_direct_close_pass(self):
        ob = ["- [x] fix deployed [closed-by: 0123456789ab]"]
        txt, cp = mk_cairn(obligations=ob)
        ledger = mk_ledger(("build:design/1", SHA1, "PASS"))
        rep = cairn.reconciliation_pass(txt, ledger=ledger, cairn_path=cp)
        self.assertTrue(rep["ok"], rep["escalations"])

    def test_rule2_unknown_closed_by_form(self):
        ob = ["- [x] fix deployed [closed-by: mystery]"]
        txt, cp = mk_cairn(obligations=ob)
        rep = cairn.reconciliation_pass(txt, ledger=mk_ledger(("build:design/1", SHA1, "PASS")), cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("unknown [closed-by" in e for e in rep["escalations"]))

    def test_rule2_superseded_by_non_hex_prefix(self):
        ob = ["- [x] fix [closed-by: SUPERSEDED_BY=nothexatall]"]
        txt, cp = mk_cairn(obligations=ob)
        rep = cairn.reconciliation_pass(txt, ledger=mk_ledger(("build:design/1", SHA1, "PASS")), cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("non-12-hex later-prefix" in e for e in rep["escalations"]))

    def test_rule4_ref_unresolved(self):
        inv = ["I-01: auth [ref: deadbeefdead]"]
        txt, cp = mk_cairn(invariants=inv)
        rep = cairn.reconciliation_pass(txt, ledger=mk_ledger(("build:design/1", SHA1, "PASS")), cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule4" in e and "no ledger entry" in e for e in rep["escalations"]))

    def test_rule3_runid_mismatch(self):
        txt, cp = mk_cairn()
        ledger = mk_ledger(("build:design/1", SHA1, "PASS"))
        active = "run-id: 1999-01-01T00-00-00\n"
        rep = cairn.reconciliation_pass(txt, ledger=ledger, active_run_text=active, cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("rule3" in e for e in rep["escalations"]))

    def test_rule3_runid_matches_filename(self):
        txt, cp = mk_cairn()
        ledger = mk_ledger(("build:design/1", SHA1, "PASS"))
        active = f"run-id: {RUN_ID}\n"
        rep = cairn.reconciliation_pass(txt, ledger=ledger, active_run_text=active, cairn_path=cp)
        self.assertTrue(any("run-id matches" in n for n in rep["notes"]))

    def test_phase_malformed_value_does_not_crash(self):
        txt, cp = mk_cairn()
        txt = txt.replace("phase: design / 2", "phase: design")
        rep = cairn.reconciliation_pass(txt, ledger=None, cairn_path=cp)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("phase value malformed" in e for e in rep["escalations"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)