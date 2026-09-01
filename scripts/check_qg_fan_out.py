#!/usr/bin/env python3
"""Structural check: Fix-Generated Defect Tracking / fan-out telemetry (#546).

Invocation (from repo root):
    python3 scripts/check_qg_fan_out.py
    python3 scripts/check_qg_fan_out.py --selftest

Path-pinned to exactly three target files — the quality-gate SKILL.md, the
fix-generated-defect checker prompt, and (as of round 8, F1) the persistence
checker prompt. This checker NEVER rglobs; the path pinning is what prevents a
self-match, so the pinned phrases need NOT be obfuscated/split.

Asserts against `skills/quality-gate/SKILL.md`:
  (a) `SUSTAINED_FAN_OUT` is NOT shipped as a verdict this round — the closed
      `Verdict:`/`Reason:` marker enum lines (each asserted to appear exactly
      once, round-2 M3) do NOT contain `SUSTAINED_FAN_OUT` / `sustained-fan-out`
      (F2's telemetry-only decision is load-bearing: a future editor re-adding
      the verdict must deliberately update this checker, not slip it back in
      via one enum edit);
  (b) `FanOutRounds`/`FanOutCheckCount`/`FanOutErrorCount` marker fields are
      present, with BOTH the `len(FanOutRounds) ≤ FanOutCheckCount` and
      `FanOutErrorCount ≤ FanOutCheckCount` invariants stated (the second
      added round-5 M2 — INV-546-6 claimed plural "invariants" pinned but
      only the first was actually asserted);
  (c) the convergence-log `fan_out_rounds`/`fan_out_check_count`/
      `fan_out_error_count`/`fan_out_oversized_count`/`fan_out_ambiguous_count`/
      `fan_out_diff_bytes_max`/`fan_out_diff_bytes_total` keys are documented
      (the middle two added round-5 S1/S3, the last two round-8 S2 — giving
      `fix-generated-diff-bytes`, round-7 S4's per-round size channel, a
      durable sink so its size-distribution interpretability survives scratch
      cleanup), and the retired `sustained_fan_out` key is NOT (M1 — the field
      was dropped as redundant with `verdict` once no verdict derives from it);
  (d) the `persistence_status` value-set enum is present inside the
      `<!-- CONTRACT:qg-fix-generated-persistence-status:START -->` … `:END -->`
      block, carrying all five quoted enum values, including `verifier-error`
      (round-2 S4 — a round-N verifier failure is NOT the same as "persistence
      genuinely didn't fire" and must fail open, not infer zero exclusions);
  (e) the checker's dispatch is documented as running strictly AFTER the
      persistence checker resolves (F4 ordering fix), AND the orchestrator's
      own fail-open interception (round-5 S4 — the orchestrator writes
      `status: error` itself on `verifier-error`/`error`/`absent` rather than
      dispatching and trusting subagent compliance) is present inside
      `<!-- CONTRACT:qg-fan-out-orchestrator-fail-open:START -->` … `:END -->`;
  (f) [removed, round-5 M1 — see inline comment at its former call site];
  (g) the completeness audit compares against the orchestrator's OWN
      independently-computed Fatal+Significant count, not the checker's
      self-declared count (round-2 S5 — a self-referential audit catches
      arithmetic slips but not a checker that silently drops findings), AND
      states that count is deliberately NOT the #366 Score-source count
      (round-5 F3 — decoupling the two counts is what keeps the widened
      population arithmetically self-consistent) — point-anchored (round-4
      S1) inside `<!-- CONTRACT:qg-fan-out-completeness-audit:START -->` …
      `:END -->`, not a file-wide substring search: an index-table/Red-Flags
      restatement of the same phrase must NOT satisfy this check;
  (h) the fan-out streak note is documented as a free-text `round-N-score.md`
      field, NOT a Minor observation (round-2 S6 — every "Minor" channel in
      this document is hash-pinned, telemetry-sourced from a different
      meaning of "Minor," or fix-dispatched, so borrowing the vocabulary does
      concrete damage) — point-anchored (round-4 S1) inside
      `<!-- CONTRACT:qg-fan-out-streak-note-field:START -->` … `:END -->`;
  (i) the streak note's "never escalates" guarantee is present (round-2 M2,
      mirroring `check_qg_minor_advisory.py`'s INV-T17 never-changes-verdict /
      never-blocks pin — the enum-name pin alone does not guard the
      substantive behavior INV-546-2 promises);
  (m) the checker's in-scope population covers every Fatal/Significant-severity
      finding regardless of section, explicitly including `### Second Pass
      Findings` (round-3 F1 originally heading-scoped this population to
      exclude that section; round-5 F3 widened it back — the excluded section
      is exactly where #488 c1's late-round relocating Fatals would surface,
      and round 3's own fix had already demoted the completeness audit to
      non-voiding, so the arithmetic no longer needs to close against the
      #366 count) — point-anchored (round-4 S1) inside
      `<!-- CONTRACT:qg-fan-out-population-scope:START -->` … `:END -->`;
  (n) a completeness mismatch does NOT set `status: error` (round-3 F1 — the
      residual mismatch is demoted to a narration-log flag, not a
      round-voiding failure);
  (o) `FanOutErrorCount`/`fan_out_error_count` is present in both the marker
      field list and the convergence-log field docs, with the corrected
      base-rate estimator subtracting it from the denominator (round-3 F2 —
      `fan_out_check_count` alone counts error dispatches that `fan_out_rounds`
      can never contain, biasing any naive rate estimate low). Round-5
      extensions: (o2) the Round History `fix-generated-count` field uses a
      three-value-plus-`n/a` encoding so an error dispatch (`error`) is
      distinguishable from a clean-zero dispatch (`0`) after a compaction,
      Compaction Recovery 6e's trigger carries the `code`-artifact-type
      qualifier inside `<!-- CONTRACT:qg-fan-out-recovery-trigger:START -->`
      … `:END -->` (F1), and 6e states the `FanOutCheckCount`/
      `FanOutErrorCount` reconstruction rule (F2); (o3) the oversized-diff
      fail-open is contradiction-free (`cap it and fail open` MUST NOT appear)
      and `fan_out_oversized_count` is documented (S1); (o4) the durable
      `fix-generated-ambiguous-count` (Round History) and `fan_out_ambiguous_count`
      (convergence log) channels for the checker's `ambiguous_count` band are
      documented (S3);
  (p) the fix-generated-defect checker's code-artifact exclusion is documented
      (`fix-generated-count: n/a`, round-3 S1 — code artifacts circulate a
      prepared/lossy snapshot, not a raw diff, so no reliable fix-diff exists)
      — point-anchored (round-4 S1) inside
      `<!-- CONTRACT:qg-fan-out-code-exclusion:START -->` … `:END -->`;
  (q) the `fired-clean` exclusion rule carries the `in-scope` qualifier and a
      Minor-finding carve-out (round-4 F1 — automatically population-matched
      again once round-5 F3 widened the population to all sections by
      severity alone), plus an explicit `medium`-confidence-correspondence
      instruction (round-5 M8 — previously unaddressed, entering the judged
      population unmarked) — point-anchored inside
      `<!-- CONTRACT:qg-fan-out-exclusion-scope:START -->` … `:END -->`;
  (s) round-6 F1/S3 — every fail-open object carries a structured
      `error_cause` (not just free-text `error_reason`): the orchestrator-side
      persistence interception writes `error_cause: "persistence-unknown"`
      (inside `qg-fan-out-orchestrator-fail-open`), the orchestrator-side
      oversized-diff interception writes `error_cause: "oversized-diff"`, and
      `round-N-score.md` gains a `fix-generated-error-cause` field carrying
      all four enum values (`oversized-diff`/`persistence-unknown`/
      `transport`/`n/a`) — the durable per-round channel `fan_out_oversized_count`
      (check (c)) is sourced from, closing the gap where that counter had no
      writer and always read `0` (F1's Fatal);
  (u) round-6 S1 — the Compaction Recovery 6e recovery-trigger CONTRACT span
      (`qg-fan-out-recovery-trigger`) also requires `persistence_status` to
      resolve to `fired-clean` or `not-triggered`, so recovery cannot
      re-dispatch the checker on exactly the three paths the orchestrator-side
      fail-open (check (e2)) forbids outside recovery;
  (v) round-6 S4 — two of round-5's new pins (the `fix-generated-count`
      `error`-encoding clause and the `fix-generated-ambiguous-count`
      value-encoding) are point-anchored inside
      `<!-- CONTRACT:qg-fan-out-score-field-encoding-count:START -->` … `:END -->`
      and `...-ambiguous:START -->` … `:END -->` respectively, not a file-wide
      substring search — mutation-verified maskable by restatements at
      INV-546-8 and the fan_out_ambiguous_count field doc, the exact
      round-4 S1 defect shape reproduced at these two new sites;
  (w) round-6 S2 — `fix-generated-ambiguous-count` carries the three-value-
      plus-`n/a` encoding (mirroring `fix-generated-count` exactly, not merely
      styled after it — round 5's version had no defined value on an error
      round), and `fan_out_ambiguous_count`'s doc states it sums only over
      integer-valued rounds, excluding (not zero-folding) `error`/`n/a` rounds;
  (x) round-6 S5 — the completeness-audit CONTRACT span
      (`qg-fan-out-completeness-audit`) states the mechanical counting rule
      both counts use (`**Severity:** Fatal` / `**Severity:** Significant`
      lines across the whole file), so the audit's comparand is not an
      unspecified judgment call over a free-form report;
  (z1) round-7 S1 — the section states its N/N+1 round-numbering convention
      once, and the fan-out-streak-note's emitted text is consistent with it
      ("rounds N and N+1", not the prior off-by-one "rounds N-1 and N");
  (z2) round-7 S2 — `FanOutErrorCount`/`fan_out_error_count`/INV-546-9 all
      carry round-6 M1's "orchestrator interception rounds count too" clause
      (previously only `FanOutCheckCount`/`fan_out_check_count` did, leaving
      the sibling counter's denominator under-inflated by the interception
      paths' contribution);
  (z3) round-7 S3 — the Anti-Rationalization Table's dispatch-trigger row
      carries the `persistence_status` fail-open exception (previously only
      Compaction Recovery 6e's restatement did, round-6 S1), and INV-546-1
      states the precondition once with 6e/Anti-Rat noted as inheriting it;
  (z4) round-7 S4 — `fix-generated-diff-bytes` gives `fan_out_oversized_count`
      a calibratable size channel, and a stated interception order
      (oversized-diff first, persistence-unknown residual) makes a
      both-conditions round's `error_cause` deterministic;
  (z5) round-7 S5 — the `qg-fan-out-finding-identity` CONTRACT span states a
      mechanical finding-identity rule (ordinal position among
      `**Severity:** Fatal`/`**Severity:** Significant` lines, mirroring
      round-6 S5's counting rule) so the join against the persistence
      checker's free-form `round_n_plus_1_finding_id` values is not two
      independently-rendered titles happening to match;
  (z6) round-7 S6 — `fix-generated-exclusion-basis` and
      `fan_out_not_triggered_count` let the base rate be stratified by
      whether persistence exclusions were available (a `not-triggered`
      round runs with zero exclusions, an upward bias with no counter
      before this round).

Asserts against `skills/quality-gate/fix-generated-defect-prompt.md`:
  (j) the JSON output schema's field names are present as quoted keys,
      including `ambiguous_count` (round-2 S7);
  (k) the judgment value set includes `ambiguous` (round-2 S7 — the checker
      claims the persistence checker's `high`/`medium`/`none` asymmetry but
      shipped without the `medium` analogue; a binary judgment silently folds
      ambiguous cases into `pre-existing`);
  (l) the `persistence_status` enum tokens are present, all backtick-quoted
      (round-2 M6 — normalizes the prior bare/backticked mix), including
      `verifier-error`;
  (r) the `fired-clean` bullet's exclusion rule mirrors SKILL.md's `in-scope`
      qualifier, Minor carve-out, and `medium`-confidence instruction
      (round-4 F1 mirror; round-5 M8 mirror); the population-scope input #1
      description mirrors SKILL.md's all-sections widening (round-5 F3
      mirror) and its round-6 S5 mechanical counting rule; and the
      anti-anchoring self-description no longer understates what input #2
      supplies (round-5 M4 — it previously claimed no findings beyond
      `round-(N+1)-persistence.md`'s summary, contradicted by input #2
      supplying the full round-N fix-journal entry);
  (y) round-6 F1/S3 — the Fail-open JSON schema carries a structured
      `error_cause` key with all three quoted enum values
      (`"oversized-diff"`/`"persistence-unknown"`/`"transport"`), and the
      `verifier-error`/`error`/`absent` bullets under input #3 each state the
      matching `error_cause: "persistence-unknown"` the orchestrator writes;
  (z5-mirror) round-7 S5 — the mechanical finding-identity rule and the
      `round_n_plus_1_finding_id` schema comment both state the ordinal-
      position rule, mirroring SKILL.md's `qg-fan-out-finding-identity` span.

Asserts against `skills/quality-gate/persistence-checker-prompt.md` (round 8, F1):
  (F1) the `round_n_plus_1_finding_id` schema comment and the Rules section's
      `qg-fan-out-persistence-finding-id-rule` CONTRACT span both state the
      identical mechanical ordinal-position rule SKILL.md's
      `qg-fan-out-finding-identity` span claims this file uses — round 7 S5's
      fix-generated-defect-checker span asserted this file assigns
      `round_n_plus_1_finding_id` "the same mechanical way ... ordinarily
      assigned," which was FALSE until this round: this file previously
      defined the field as a free-form `<id or short title>` string. Pinning
      this file too (not just asserting about it from SKILL.md) is what makes
      the claim actually checked, not just written down.

Note (round 8, S1 full audit): several bare `if "<needle>" not in text`
checks below are DELIBERATELY left unanchored — see the inline comment at
each such check for the specific reason (negative/retired-string checks,
count-threshold checks robust to single-site deletion by design, checks
already redundant with an existing anchored block, or vocabulary distributed
by design across multiple independently-justified sites with no single
canonical site to anchor). This is a judgment call, not an oversight; see
round-8 fix-journal `Pin audit record` for the full enumeration.

Round-9 changes (S1-S7 fixes, S5 pin-shape pass — see fix-journal for the
full round-9 entry):
  - (z2) reshaped: the `count >= 5` sibling-clause threshold (self-
    contradicting INV-546-1's own consolidation principle) is replaced by
    four independently-anchored per-site checks (the two Round History
    value-encoding spans, the FanOutErrorCount marker-field doc, and the
    fan_out_error_count convergence-log doc).
  - (x)/(n)/(z1)/(z3)/INV-546-1 reshaped: several bare or anchored
    full-English-sentence pins are converted to shorter contract tokens
    (`**Severity:** Fatal`/`**Severity:** Significant`/`#366`; "narration-log
    signal"; "generic template name"/"is the **current** round's"; the
    Anti-Rat row's two exception tokens; "inherits it by reference") per
    `CHECKER_CONVENTIONS.md` §1 — a partial pass over the flagged sites, not
    an exhaustive re-audit of every pin in this checker (round-9 S5).
  - (z4) reshaped: the interception-order check no longer pins the
    explanatory sentence; it asserts `oversized-diff` precedes
    `persistence-unknown` inside the (now widened) anchor.
  - (w) retargeted: asserts the denominator-correction sentence and a
    negative check against the vacuous "would bias this sum low" rationale,
    instead of the vacuous sourcing clause (round-9 S6).
  - New checks: the exclusion-basis field's exhaustive `n/a` clause, the
    `fan_out_not_triggered_count` gloss/invariant (round-9 S1); the
    recovery-trigger's oversized-diff condition (round-9 S2); the
    convergence-log `fan_out_rounds_not_triggered` key (round-9 S4).

Exits 0 when aligned, 1 with a `- <error>` list otherwise. Stdlib only.
See scripts/CHECKER_CONVENTIONS.md.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/quality-gate/SKILL.md"
PROMPT = ROOT / "skills/quality-gate/fix-generated-defect-prompt.md"
PERSISTENCE = ROOT / "skills/quality-gate/persistence-checker-prompt.md"


def _anchored(text: str, anchor: str) -> str | None:
    """Return the content inside a `<!-- CONTRACT:<anchor>:START -->` … `:END -->`
    point-anchor, or None if the anchor is absent. Point-anchoring (round-3 M4,
    extended round-4 S1) is what lets a check assert a phrase lives at its
    OPERATIVE site rather than being satisfied by an index-table/Red-Flags
    restatement of the same phrase elsewhere in the file.
    """
    m = re.search(
        rf"<!-- CONTRACT:{re.escape(anchor)}:START.*?-->(.*?)"
        rf"<!-- CONTRACT:{re.escape(anchor)}:END",
        text, re.DOTALL,
    )
    return m.group(1) if m else None


def check_skill(text: str) -> list[str]:
    errs: list[str] = []

    # (a) SUSTAINED_FAN_OUT / sustained-fan-out must NOT appear in the closed
    # marker enum lines — extract the exact `Verdict:`/`Reason:` lines. Uses
    # findall + an exactly-one-match assertion (round-2 M3) rather than the
    # first-match-wins re.search this checker shipped with in round 1: a
    # future edit adding an earlier line-anchored `Verdict: `/`Reason: ` line
    # (e.g. an example marker block) would otherwise make re.search silently
    # inspect the wrong line.
    verdict_lines = re.findall(r"^Verdict: .*$", text, re.MULTILINE)
    if len(verdict_lines) != 1:
        errs.append(
            f"SKILL: expected exactly one 'Verdict:' marker enum line, found {len(verdict_lines)} "
            "— if this is a deliberate second line (e.g. an illustrative example), pin the "
            "canonical enum line with an adjacent CONTRACT anchor and update this guard to "
            "search inside it, rather than relying on global uniqueness (round-2 M3)"
        )
    elif "SUSTAINED_FAN_OUT" in verdict_lines[0]:
        errs.append(
            "SKILL: 'Verdict:' marker enum line carries SUSTAINED_FAN_OUT — "
            "telemetry-only decision (F2) requires this NOT ship as a verdict "
            "this round without a deliberate, coordinated cross-reference sweep"
        )
    reason_lines = re.findall(r"^Reason: .*$", text, re.MULTILINE)
    if len(reason_lines) != 1:
        errs.append(
            f"SKILL: expected exactly one 'Reason:' marker enum line, found {len(reason_lines)} "
            "— if this is a deliberate second line (e.g. an illustrative example), pin the "
            "canonical enum line with an adjacent CONTRACT anchor and update this guard to "
            "search inside it, rather than relying on global uniqueness (round-2 M3)"
        )
    elif "sustained-fan-out" in reason_lines[0]:
        errs.append(
            "SKILL: 'Reason:' marker enum line carries sustained-fan-out — "
            "telemetry-only decision (F2) requires this NOT ship as a Reason "
            "this round without a deliberate, coordinated cross-reference sweep"
        )

    # (b) FanOutRounds / FanOutCheckCount / FanOutErrorCount marker fields +
    # both invariants + the estimator, point-anchored (round-8 S1 audit —
    # this was a bare file-wide check; the real document restates
    # 'len(FanOutRounds) ≤ FanOutCheckCount' and 'FanOutErrorCount ≤
    # FanOutCheckCount' at INV-546-5, and the estimator at INV-546-9, so
    # deleting the operative marker-template lines alone would have left
    # this check green, the same defect shape as round-4 S1/round-6 S4).
    block_b = _anchored(text, "qg-fan-out-marker-fields")
    if block_b is None:
        errs.append(
            "SKILL: fan-out marker-fields CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-marker-fields:START --> … :END -->, round-8 S1)"
        )
    else:
        if "FanOutRounds:" not in block_b:
            errs.append("SKILL: missing 'FanOutRounds:' marker field inside its point-anchored CONTRACT span (round-8 S1)")
        if "FanOutCheckCount:" not in block_b:
            errs.append("SKILL: missing 'FanOutCheckCount:' marker field inside its point-anchored CONTRACT span (round-8 S1)")
        if "FanOutErrorCount:" not in block_b:
            errs.append("SKILL: missing 'FanOutErrorCount:' marker field inside its point-anchored CONTRACT span (round-3 F2 / round-8 S1)")
        if "len(FanOutRounds) ≤ FanOutCheckCount" not in block_b:
            errs.append(
                "SKILL: missing 'len(FanOutRounds) ≤ FanOutCheckCount' invariant inside its "
                "point-anchored CONTRACT span (round-8 S1)"
            )
        if "FanOutErrorCount ≤ FanOutCheckCount" not in block_b:
            errs.append(
                "SKILL: missing 'FanOutErrorCount ≤ FanOutCheckCount' invariant inside its "
                "point-anchored CONTRACT span (round-5 M2 — INV-546-6 claims plural 'invariants' "
                "pinned; both must actually be asserted; round-8 S1)"
            )
        if "FanOutCheckCount - FanOutErrorCount" not in block_b:
            errs.append(
                "SKILL: missing the corrected base-rate estimator "
                "'len(FanOutRounds) / (FanOutCheckCount - FanOutErrorCount)' inside its "
                "point-anchored CONTRACT span (round-3 F2 / round-8 S1)"
            )

    # (c) convergence-log keys present; retired sustained_fan_out key absent —
    # scoped to the fan-out convergence-field CONTRACT block (round-3 M1: a
    # file-global absence check would forbid a future editor from documenting
    # the retired key in this repo's normal "Retired" prose elsewhere).
    block_c = _anchored(text, "qg-fan-out-convergence-fields")
    if block_c is None:
        errs.append(
            "SKILL: fan-out convergence-field CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-convergence-fields:START --> … :END -->)"
        )
    else:
        if '"fan_out_rounds"' not in block_c and "`fan_out_rounds`" not in block_c:
            errs.append("SKILL: missing convergence-log 'fan_out_rounds' key")
        if '"fan_out_check_count"' not in block_c and "`fan_out_check_count`" not in block_c:
            errs.append("SKILL: missing convergence-log 'fan_out_check_count' key")
        if '"fan_out_error_count"' not in block_c and "`fan_out_error_count`" not in block_c:
            errs.append("SKILL: missing convergence-log 'fan_out_error_count' key (round-3 F2)")
        if '"fan_out_oversized_count"' not in block_c and "`fan_out_oversized_count`" not in block_c:
            errs.append(
                "SKILL: missing convergence-log 'fan_out_oversized_count' key (round-5 S1 — "
                "the oversized-diff error cause is not missing-at-random, so it needs its own "
                "distinguishing subset count)"
            )
        if '"fan_out_ambiguous_count"' not in block_c and "`fan_out_ambiguous_count`" not in block_c:
            errs.append(
                "SKILL: missing convergence-log 'fan_out_ambiguous_count' key (round-5 S3 — "
                "the ambiguous_count band otherwise has no durable channel and is lost at "
                "scratch cleanup)"
            )
        if '"fan_out_diff_bytes_max"' not in block_c and "`fan_out_diff_bytes_max`" not in block_c:
            errs.append(
                "SKILL: missing convergence-log 'fan_out_diff_bytes_max' key (round-8 S2 — "
                "fix-generated-diff-bytes (round-7 S4) otherwise has no durable sink, destroying "
                "the size-distribution interpretability round-7 S4 promised at scratch cleanup)"
            )
        if '"fan_out_diff_bytes_total"' not in block_c and "`fan_out_diff_bytes_total`" not in block_c:
            errs.append(
                "SKILL: missing convergence-log 'fan_out_diff_bytes_total' key (round-8 S2)"
            )
        if '"fan_out_rounds_not_triggered"' not in block_c and "`fan_out_rounds_not_triggered`" not in block_c:
            errs.append(
                "SKILL: missing convergence-log 'fan_out_rounds_not_triggered' key (round-9 S4 "
                "— fan_out_not_triggered_count is a denominator-only sink; without this list, "
                "the per-round fix-generated-exclusion-basis tag it counts is not recoverable "
                "from the durable record after scratch cleanup)"
            )
        if "sustained_fan_out" in block_c:
            errs.append(
                "SKILL: retired convergence-log key 'sustained_fan_out' reappeared "
                "(M1 — redundant with 'verdict' once no verdict derives from it)"
            )

    # (d) persistence_status CONTRACT block, all five enum values.
    block_d = _anchored(text, "qg-fix-generated-persistence-status")
    if block_d is None:
        errs.append(
            "SKILL: persistence_status CONTRACT block not found "
            "(<!-- CONTRACT:qg-fix-generated-persistence-status:START --> … :END -->)"
        )
    else:
        for quoted in ('"fired-clean"', '"not-triggered"', '"verifier-error"', '"error"', '"absent"'):
            if quoted not in block_d:
                errs.append(
                    f"SKILL: persistence_status CONTRACT block missing quoted enum value {quoted}"
                )

    # (e) dispatch ordering documented — point-anchored to the operative
    # sentence specifically (round-3 M4): a plain global substring search
    # would still pass if only the operative sentence were deleted while the
    # INV-546-1 table restatement (same phrase) survives.
    block_e = _anchored(text, "qg-fan-out-dispatch-ordering")
    if block_e is None or "strictly AFTER the persistence checker" not in block_e:
        errs.append(
            "SKILL: missing the fix-generated-defect checker's dispatch-ordering "
            "statement ('strictly AFTER the persistence checker') inside its point-anchored "
            "CONTRACT span (round-3 M4 — a table restatement elsewhere does not satisfy this)"
        )

    # (e2) round-5 S4 — orchestrator intercepts verifier-error/error/absent BEFORE
    # dispatch rather than trusting the subagent's own fail-open compliance.
    block_e2 = _anchored(text, "qg-fan-out-orchestrator-fail-open")
    if block_e2 is None or "does **not** dispatch the fix-generated-defect checker" not in block_e2:
        errs.append(
            "SKILL: missing the orchestrator-side fail-open statement ('does NOT dispatch the "
            "fix-generated-defect checker') inside its point-anchored CONTRACT span (round-5 S4 "
            "— the orchestrator already knows persistence_status before dispatch and must not "
            "delegate the forbidden-outcome guard to subagent compliance alone)"
        )

    # (f) [removed, round-5 M1] — this check tested `"Fatal/Significant finding" not
    # in text`, file-wide. Verified vacuous against the real file: the needle occurs
    # in 7 pieces of pre-existing #366 prose this change does not own (Anti-Rat
    # table, `round-N-ledger.md` v0.1, fix-journal formats, DR messaging), so the
    # check could never fire in production — the underlying round-2 F1 property
    # (severity-scoping) is fully covered by check (q)'s point-anchored needle.
    # Deleted rather than point-anchored because (q) already owns this property.

    # (g) round-2 S5 — completeness audit uses the orchestrator's own count,
    # point-anchored (round-4 S1): the phrase also lives verbatim in the
    # INV-546-7 table restatement, so a file-wide substring check stays green
    # after the operative sentence (the completeness-audit paragraph) is
    # deleted — verified by mutation in the round-4 finding.
    block_g = _anchored(text, "qg-fan-out-completeness-audit")
    if block_g is None:
        errs.append(
            "SKILL: completeness-audit CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-completeness-audit:START --> … :END -->, round-4 S1)"
        )
    else:
        if "independently-computed Fatal+Significant count" not in block_g:
            errs.append(
                "SKILL: missing the completeness audit's 'independently-computed "
                "Fatal+Significant count' comparand inside its point-anchored CONTRACT "
                "span (round-2 S5 / round-4 S1)"
            )
        if "reviewer-declared cross-check only" not in block_g:
            errs.append(
                "SKILL: missing the 'reviewer-declared cross-check only' downgrade of the "
                "checker's self-declared round_n_plus_1_finding_count inside its point-anchored "
                "CONTRACT span (round-2 S5 / round-4 S1)"
            )
        if "deliberately NOT the same as the #366 Score-source count" not in block_g:
            errs.append(
                "SKILL: missing the completeness audit's explicit decoupling from the #366 "
                "Score-source count inside its point-anchored CONTRACT span (round-5 F3 — the "
                "audit's comparand is now an all-sections count of its own, not #366's "
                "heading-scoped count, which is what keeps the widened population arithmetically "
                "self-consistent without reopening round 3's F1 concern)"
            )

    # (h) round-2 S6 — fan-out streak note is a free-text score-file field, not
    # Minor, point-anchored (round-4 S1): the field name also lives verbatim in
    # four restatement sites (Anti-Rat table, Round History, Red Flags, INV
    # table), so a file-wide substring check stays green after the operative
    # streak-tracking sentence is deleted.
    block_h = _anchored(text, "qg-fan-out-streak-note-field")
    if block_h is None or "fan-out-streak-note:" not in block_h:
        errs.append(
            "SKILL: missing the 'fan-out-streak-note:' field name inside its point-anchored "
            "CONTRACT span (round-2 S6 / round-4 S1 — the streak note must NOT be routed "
            "through any Minor-observation channel, and a table/Red-Flags restatement of the "
            "field name does not satisfy this)"
        )

    # (i) round-2 M2 — never-escalates guarantee (mirrors INV-T17's never-changes-verdict
    # pin), point-anchored (round-3 M4) so an INV-546-2 table restatement of the same
    # phrase does not mask deletion of the operative sentence.
    block_i = _anchored(text, "qg-fan-out-never-escalates")
    if block_i is None or "never escalates" not in block_i:
        errs.append(
            "SKILL: missing the fan-out streak note's 'never escalates' guarantee inside its "
            "point-anchored CONTRACT span (round-2 M2 / round-3 M4)"
        )

    # (m) round-3 F1 — checker's in-scope population is heading-scoped, Second
    # Pass Findings excluded — point-anchored (round-4 S1): verified by
    # mutation that the un-anchored, file-wide form of this check stays green
    # after the operative sentence (SKILL.md input #1) is deleted, because
    # '### Fatal Challenges'/'### Significant Challenges' also appear
    # unconditionally in pre-existing #366 prose this change does not own,
    # plus Red Flags and INV-546-7 restatements.
    block_m = _anchored(text, "qg-fan-out-population-scope")
    if block_m is None:
        errs.append(
            "SKILL: fan-out population-scope CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-population-scope:START --> … :END -->, round-4 S1)"
        )
    else:
        if "regardless of which section it appears under" not in block_m:
            errs.append(
                "SKILL: missing the all-sections population-scope phrase ('regardless of which "
                "section it appears under') inside the population-scope CONTRACT span (round-5, "
                "F3 — widened from round-3 F1's heading-scoped population, which made the "
                "checker permanently blind to second-pass-surfaced defects)"
            )
        if "Second Pass Findings" not in block_m:
            errs.append(
                "SKILL: missing the explicit 'Second Pass Findings' in-scope carve-out "
                "inside the population-scope CONTRACT span (round-3 F1 / round-5 F3)"
            )

    # (n) round-3 F1, reshaped round-9 S5 — a completeness mismatch does NOT
    # set status: error; it is a narration-log flag instead. Point-anchored
    # round-8 S1 inside the same qg-fan-out-completeness-audit CONTRACT span
    # as check (g)/(x). Was a bare full-clause pin ("does NOT void the
    # round"); "narration-log signal" is the shorter, equally load-bearing
    # token distinguishing this outcome from status: error.
    block_n = _anchored(text, "qg-fan-out-completeness-audit")
    if block_n is None or "narration-log signal" not in block_n:
        errs.append(
            "SKILL: missing the completeness audit's 'narration-log signal' demotion "
            "(a mismatch is flagged there, not escalated to status: error) inside its "
            "point-anchored CONTRACT span (round-3 F1 / round-8 S1 / round-9 S5)"
        )

    # (o) round-3 F2 — FanOutErrorCount marker field + estimator corrected.
    # Now checked inside check (b)'s qg-fan-out-marker-fields CONTRACT span
    # (round-8 S1); the convergence-log 'fan_out_error_count' key is pinned
    # by check (c), scoped to the fan-out convergence-field CONTRACT block.

    # (o2) round-5 F2 — the `round-N-score.md` `fix-generated-count` field must
    # distinguish an error dispatch (`error`) from a clean-zero dispatch (`0`),
    # and the Compaction Recovery 6e reconstruction rule must read that
    # distinction, or FanOutErrorCount is silently unrecoverable after a
    # compaction (re-inflating the base-rate denominator with error dispatches
    # counted as confirmed negatives). Point-anchored round-8 S1: the
    # 'three-value-plus-`n/a` encoding' phrase is asserted separately for
    # EACH of the two fields that carry it (fix-generated-count and
    # fix-generated-ambiguous-count each state their own copy) so a single
    # deleted copy cannot hide behind the other field's independent copy.
    block_count_field = _anchored(text, "qg-fan-out-count-field-value-note")
    if block_count_field is None:
        errs.append(
            "SKILL: fan-out Round History fix-generated-count field CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-count-field-value-note:START --> … :END -->, round-8 S1)"
        )
    else:
        if "three-value-plus-`n/a` encoding" not in block_count_field:
            errs.append(
                "SKILL: missing the three-value `fix-generated-count` encoding note inside its "
                "point-anchored CONTRACT span (round-5 F2 / round-8 S1 — a two-value "
                "0-collapses-error encoding makes FanOutErrorCount unrecoverable after a "
                "compaction)"
            )
    block_ambiguous_field = _anchored(text, "qg-fan-out-ambiguous-count-field")
    if block_ambiguous_field is None:
        errs.append(
            "SKILL: fan-out Round History fix-generated-ambiguous-count field CONTRACT block "
            "not found (<!-- CONTRACT:qg-fan-out-ambiguous-count-field:START --> … :END -->, "
            "round-8 S1)"
        )
    else:
        if "fix-generated-ambiguous-count" not in block_ambiguous_field:
            errs.append(
                "SKILL: missing the 'fix-generated-ambiguous-count' field name inside its "
                "point-anchored CONTRACT span (round-5 S3 / round-8 S1 — the field name was "
                "previously a bare file-wide check, maskable by the Telemetry-only-paragraph "
                "and INV-546-8 restatements surviving deletion of the operative Round History "
                "bullet)"
            )
        if "three-value-plus-`n/a` encoding" not in block_ambiguous_field:
            errs.append(
                "SKILL: missing the three-value `fix-generated-ambiguous-count` encoding note "
                "inside its point-anchored CONTRACT span (round-6 S2 / round-8 S1)"
            )
    if "`fix-generated-count: error`" not in text:
        errs.append(
            "SKILL: missing the '`fix-generated-count: error`' token (round-5 F2 — recorded "
            "in round-N-score.md on a checker-error round, distinct from `0`). NOT point-"
            "anchored (round-8 S1 audit): this token is deliberately restated across ≥5 "
            "independently-justified sites (Failure modes, Compaction Recovery 6e, the "
            "fix-generated-error-cause/fix-generated-exclusion-basis Round History field docs, "
            "the INV-546-8 table row) rather than defined once — there is no single 'operative' "
            "site whose deletion should trip this check while the others stay silent, so a bare "
            "presence-anywhere check is the correct shape here, not a masking gap."
        )
    block_recovery = _anchored(text, "qg-fan-out-recovery-trigger")
    if block_recovery is None or "AND the artifact type is not `code`" not in block_recovery:
        errs.append(
            "SKILL: missing the `code`-artifact-type qualifier inside the Compaction Recovery "
            "6e trigger-conditions CONTRACT span (round-5 F1 — the code exclusion was "
            "previously stated once and left unqualified at this action site, so recovery "
            "would re-dispatch a checker the exclusion forbids on every `code` gate)"
        )
    if "is the count of score files" not in text or "FanOutErrorCount` is the count whose value is `error`" not in text:
        errs.append(
            "SKILL: missing the 6e reconstruction rule for FanOutCheckCount/FanOutErrorCount "
            "from the three-value `fix-generated-count` encoding (round-5 F2)"
        )

    # (o3) round-5 S1 — oversized-diff cause resolved to a single fail-open
    # action (no capping) and given its own distinguishing counter.
    # "cap it and fail open" is a NEGATIVE (retired-string-absence) check —
    # round-8 S1 audit: deliberately left unanchored. There is no "operative
    # site" to point-anchor for an absence check; the masking direction is
    # the opposite of round-4 S1's shape (a restatement elsewhere cannot hide
    # this phrase's reappearance — reappearing ANYWHERE trips it).
    if "cap it and fail open" in text:
        errs.append(
            "SKILL: the self-contradictory 'cap it and fail open' instruction for an "
            "oversized diff reappeared (round-5 S1 — pick one action: emit status: error, "
            "do not cap-and-process a truncated diff)"
        )
    # "fan_out_oversized_count" bare check — round-8 S1 audit: deliberately
    # left unanchored. This key's canonical definition already lives inside
    # check (c)'s point-anchored qg-fan-out-convergence-fields block (that
    # block's own '`fan_out_oversized_count`' assertion is what actually
    # guards this); this bare, file-wide copy is redundant with (c)'s
    # coverage, not an independent masking surface — deleting the operative
    # site inside block (c) already trips check (c) regardless of this line.
    if "fan_out_oversized_count" not in text:
        errs.append(
            "SKILL: missing 'fan_out_oversized_count' (round-5 S1 — a distinguishing subset "
            "of FanOutErrorCount so the corpus can be audited for size-censoring, which is not "
            "missing-at-random)"
        )

    # (o4) round-5 S3 — ambiguous_count durable channel. The Round History
    # field-name check moved into check (o2)'s qg-fan-out-ambiguous-count-field
    # block above (round-8 S1). "fan_out_ambiguous_count" here is left bare —
    # round-8 S1 audit: redundant with check (c)'s point-anchored coverage of
    # the same key inside qg-fan-out-convergence-fields, same reasoning as
    # fan_out_oversized_count above.
    if "fan_out_ambiguous_count" not in text:
        errs.append(
            "SKILL: missing 'fan_out_ambiguous_count' in the convergence-log field docs "
            "(round-5 S3)"
        )

    # (p) round-3 S1 — code-artifact exclusion, fix-generated-count: n/a,
    # point-anchored (round-4 S1): the phrase also lives verbatim in the Red
    # Flags and INV-546-10 restatements, so a file-wide substring check stays
    # green after the operative Artifact-class-scope sentence is deleted.
    block_p = _anchored(text, "qg-fan-out-code-exclusion")
    if block_p is None or "fix-generated-count: n/a" not in block_p:
        errs.append(
            "SKILL: missing the code-artifact 'fix-generated-count: n/a' exclusion inside its "
            "point-anchored CONTRACT span (round-3 S1 / round-4 S1)"
        )

    # (q) round-4 F1 — the fired-clean exclusion rule is scoped to the SAME
    # heading-scoped population as the completeness count, not merely
    # severity-scoped. Point-anchored because this is a brand-new operative
    # sentence with no restatement yet to be fooled by, but anchoring it now
    # (rather than after a future round discovers the same gap) keeps the
    # convention uniform across every #546 pin.
    block_q = _anchored(text, "qg-fan-out-exclusion-scope")
    if block_q is None:
        errs.append(
            "SKILL: fan-out exclusion-scope CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-exclusion-scope:START --> … :END -->, round-4 F1)"
        )
    else:
        if "in-scope** round-(N+1) Fatal/Significant finding" not in block_q:
            errs.append(
                "SKILL: missing the 'in-scope' qualifier on the fired-clean exclusion rule "
                "inside its point-anchored CONTRACT span (round-4 F1)"
            )
        if "outside this checker's scope entirely" not in block_q:
            errs.append(
                "SKILL: missing the Minor-finding carve-out ('outside this checker's scope "
                "entirely') on the fired-clean exclusion rule inside its point-anchored "
                "CONTRACT span (round-4 F1 / round-5 F3)"
            )
        if "`medium`-confidence correspondence" not in block_q or "is NOT excluded either" not in block_q:
            errs.append(
                "SKILL: missing the `medium`-confidence-correspondence instruction on the "
                "fired-clean exclusion rule inside its point-anchored CONTRACT span (round-5, "
                "M8 — a medium match previously had no explicit instruction and entered the "
                "judged population unmarked)"
            )

    # (s) round-6 F1/S3 — structured error_cause on every fail-open object,
    # plus the durable round-N-score.md field it is sourced from.
    block_s = _anchored(text, "qg-fan-out-orchestrator-fail-open")
    if block_s is None or 'error_cause: "persistence-unknown"' not in block_s:
        errs.append(
            "SKILL: missing 'error_cause: \"persistence-unknown\"' inside the orchestrator-side "
            "fail-open CONTRACT span (round-6 F1/S3 — every fail-open object must carry a "
            "structured cause, not just free-text error_reason)"
        )
    # Point-anchored round-8 S1: 'error_cause: "oversized-diff"' was a bare
    # file-wide check — the real document restates it at the INV-546-12
    # table row, so deleting the operative Input #2 interception clause
    # alone would have left this check green.
    block_ovc = _anchored(text, "qg-fan-out-oversized-diff-error-cause")
    if block_ovc is None or 'error_cause: "oversized-diff"' not in block_ovc:
        errs.append(
            "SKILL: missing 'error_cause: \"oversized-diff\"' inside its point-anchored CONTRACT "
            "span (round-6 F1 / round-8 S1 — the orchestrator-side oversized-diff interception "
            "at input #2 must write the matching structured cause)"
        )
    # Point-anchored round-8 S1: the field-name + its own enum-value list are
    # now checked inside the Round History bullet's CONTRACT span, mirroring
    # how check (d) already scopes persistence_status's enum to its own
    # block — previously a bare file-wide check, maskable by the
    # Telemetry-only-paragraph and Failure-modes restatements of the same
    # field name and tokens.
    block_ec_field = _anchored(text, "qg-fan-out-error-cause-field")
    if block_ec_field is None or "`fix-generated-error-cause`" not in block_ec_field:
        errs.append(
            "SKILL: missing the 'fix-generated-error-cause' field inside its point-anchored "
            "CONTRACT span (round-6 F1 / round-8 S1 — the durable per-round channel "
            "fan_out_oversized_count is sourced from; without it that counter has no writer "
            "and always reads 0)"
        )
    else:
        for tok in ("`oversized-diff`", "`persistence-unknown`", "`transport`", "`n/a`"):
            if tok not in block_ec_field:
                errs.append(
                    f"SKILL: fix-generated-error-cause enum missing value {tok} inside its "
                    "point-anchored CONTRACT span (round-6 F1 / round-8 S1)"
                )

    # (u) round-6 S1 — Compaction Recovery 6e's recovery-trigger also
    # requires persistence_status to be fired-clean/not-triggered, so
    # recovery cannot re-dispatch on the three paths the orchestrator-side
    # fail-open (check e2) forbids outside recovery.
    block_u = _anchored(text, "qg-fan-out-recovery-trigger")
    if block_u is None or "persistence_status`" not in block_u or "`fired-clean` or `not-triggered`" not in block_u:
        errs.append(
            "SKILL: missing the 'persistence_status ... fired-clean or not-triggered' condition "
            "inside the Compaction Recovery 6e recovery-trigger CONTRACT span (round-6 S1 — "
            "without it, recovery can re-dispatch the checker on exactly the three paths the "
            "orchestrator-side fail-open forbids outside recovery)"
        )
    # (u2) round-9 S2 — the recovery-trigger must also require the round-N
    # diff to be non-oversized, so recovery cannot re-dispatch on exactly the
    # oversized-diff path the non-recovery orchestrator-side fail-open (input
    # #2's oversized-diff interception) forbids outside recovery.
    if block_u is None or "the round-N diff is not oversized" not in block_u:
        errs.append(
            "SKILL: missing the 'the round-N diff is not oversized' condition inside the "
            "Compaction Recovery 6e recovery-trigger CONTRACT span (round-9 S2 — without it, "
            "recovery can re-dispatch the checker on exactly the oversized-diff path the "
            "non-recovery orchestrator-side fail-open forbids, with no discard rule to catch a "
            "well-formed ok response built from a truncated diff)"
        )

    # (v) round-6 S4 — two of round-5's own new pins were un-anchored,
    # file-wide substring checks at sites that already carry restatements
    # (INV-546-8, the fan_out_ambiguous_count doc) — mutation-verified
    # maskable, the exact round-4 S1 defect shape reproduced at new sites.
    block_v1 = _anchored(text, "qg-fan-out-score-field-encoding-count")
    if (
        block_v1 is None
        or "a `status: error` object exists for the round" not in block_v1
        or "no `round-(N+1)-fix-generated.md` object exists at all" not in block_v1
    ):
        errs.append(
            "SKILL: missing the fix-generated-count 'a status: error object exists for the "
            "round ... whether the checker returned it or the orchestrator wrote it in the "
            "checker's place' / 'no round-(N+1)-fix-generated.md object exists at all' clauses "
            "inside its point-anchored CONTRACT span (round-7 F1 — corrects the round-6 S4 "
            "phrasing, which contradicted Failure modes/Compaction Recovery 6e by defining "
            "n/a as 'the checker does not fire at all', a description of the orchestrator-side "
            "interception paths those sections mandate be recorded as error, not n/a)"
        )
    block_v2 = _anchored(text, "qg-fan-out-score-field-encoding-ambiguous")
    if block_v2 is None or "integer, or `0`, or `error`, or `n/a`" not in block_v2:
        errs.append(
            "SKILL: missing the fix-generated-ambiguous-count three-value-plus-n/a encoding "
            "inside its point-anchored CONTRACT span (round-6 S4 — un-anchored, this definition "
            "was maskable by restatements at INV-546-8 and the fan_out_ambiguous_count doc)"
        )
    block_v3 = _anchored(text, "qg-fan-out-score-field-encoding-ambiguous-detail")
    if (
        block_v3 is None
        or "a `status: error` object exists for the round" not in block_v3
        or "no `round-(N+1)-fix-generated.md` object exists at all" not in block_v3
    ):
        errs.append(
            "SKILL: missing the fix-generated-ambiguous-count detailed error/n/a clauses "
            "('a status: error object exists for the round' / 'no round-(N+1)-fix-generated.md "
            "object exists at all') inside its point-anchored CONTRACT span (round-7 F1 — "
            "mirrors fix-generated-count's corrected phrasing, which this field's detailed "
            "clauses previously did not carry at all)"
        )

    # (w) round-6 S2, retargeted round-9 S6 — fan_out_ambiguous_count and
    # fan_out_diff_bytes_max/_total both source their sum/max only over
    # integer-valued rounds (a descriptive fact, kept). The substantive check
    # is retargeted: round-9 S6 found the OLD rationale — "folding it into 0
    # would bias this sum low" — arithmetically vacuous (excluding a value
    # from a sum and folding it in as 0 are the identical operation), so
    # pinning it taught a false lesson and trapped a future editor who
    # correctly removed it. The real correction is a denominator statement,
    # which must appear once per field (ambiguous_count and diff_bytes).
    if "only over rounds whose value there is an integer" not in text:
        errs.append(
            "SKILL: missing the descriptive 'sums/maxes only over rounds whose value there is "
            "an integer' clause on fan_out_ambiguous_count's/fan_out_diff_bytes_max/_total's "
            "sourcing sentences (round-6 S2 / round-8 S2)"
        )
    if "would bias this sum low" in text:
        errs.append(
            "SKILL: the vacuous 'folding it into 0 would bias this sum low' rationale "
            "reappeared (round-9 S6 — excluding a value from a sum and folding it in as 0 are "
            "arithmetically identical; the true correction is a denominator statement, not a "
            "sum-bias claim)"
        )
    if text.count("not against `fan_out_check_count`") < 2:
        errs.append(
            "SKILL: missing the denominator-correction sentence ('read this ... against "
            "`fan_out_check_count - fan_out_error_count`, not against `fan_out_check_count`') "
            "on BOTH fan_out_ambiguous_count's and fan_out_diff_bytes_max/_total's sourcing "
            "docs (round-9 S6)"
        )

    # (x) round-6 S5, reshaped round-9 S5 — the completeness audit's comparand
    # is a mechanical counting rule over the steel-man protocol's own severity
    # markers, not an unspecified judgment call over a free-form report. Was a
    # bare-inside-anchor full-sentence pin; the genuine contract tokens are the
    # two severity markers the rule counts plus the #366 count it deliberately
    # is NOT, so assert those rather than the English clause describing them.
    block_x = _anchored(text, "qg-fan-out-completeness-audit")
    if block_x is None:
        errs.append(
            "SKILL: completeness-audit CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-completeness-audit:START --> … :END -->, round-4 S1)"
        )
    else:
        for tok in ("**Severity:** Fatal", "**Severity:** Significant", "#366"):
            if tok not in block_x:
                errs.append(
                    f"SKILL: completeness-audit CONTRACT span missing token '{tok}' (round-6 S5 "
                    "/ round-9 S5 — the mechanical counting rule and its deliberate #366 "
                    "decoupling both depend on these markers being named, not just described)"
                )

    # (z1) round-7 S1, reshaped round-9 S5 — the section's N/N+1 round-
    # numbering convention is stated once, and the streak note's emitted text
    # is consistent with it ("rounds N and N+1", not the old off-by-one
    # "rounds N-1 and N"). Was a bare full-sentence pin; shortened to two
    # shorter, still-distinctive tokens from the same sentence.
    if "generic template name" not in text or "is the **current** round's" not in text:
        errs.append(
            "SKILL: missing the Fix-Generated Defect Tracking round-numbering convention "
            "tokens ('generic template name' / 'is the **current** round's') (round-7 S1 / "
            "round-9 S5 — without them, 'round-N-score.md' inside this section is ambiguous "
            "between the fix round and the surfacing round)"
        )
    if "rounds N and N+1 each surfaced" not in text:
        errs.append(
            "SKILL: fan-out-streak-note's emitted text missing 'rounds N and N+1 each "
            "surfaced' (round-7 S1 — the prior 'rounds N-1 and N' text was off-by-one "
            "relative to the section's own N=fix-round/N+1=current-round convention)"
        )
    if "rounds N-1 and N each surfaced" in text:
        errs.append(
            "SKILL: fan-out-streak-note's emitted text still carries the old, inconsistent "
            "'rounds N-1 and N each surfaced' phrasing (round-7 S1)"
        )

    # (z2) round-7 S2, reshaped round-9 S5 — FanOutErrorCount/
    # fan_out_error_count's docs (plus the two Round History value-encoding
    # spans) carry round-6 M1's "orchestrator interception counts too" clause,
    # not just their sibling FanOutCheckCount/fan_out_check_count. Was a
    # file-wide `count >= 5` threshold check — round-9 S5 found this
    # self-contradicting with INV-546-1's own consolidation principle (a
    # maintainer who merges a redundant restatement, exactly what that
    # principle instructs, could drop the count below 5 and turn the build
    # red for doing the instructed thing). Replaced with a per-site assertion
    # inside each of the four independently-justified sites round-8 S1's
    # audit already identified: the two Round History value-encoding spans
    # (block_v1/block_v3), the FanOutErrorCount marker-field doc (inside
    # block_b), and the fan_out_error_count convergence-log doc (inside
    # block_c) — consolidating a redundant restatement elsewhere no longer
    # trips this check; deleting one of these four operative copies still does.
    sibling_clause = "the checker returned it or the orchestrator wrote it in the checker's place"
    _sibling_sites = (
        ("fix-generated-count's qg-fan-out-score-field-encoding-count span", block_v1),
        ("fix-generated-ambiguous-count's qg-fan-out-score-field-encoding-ambiguous-detail span", block_v3),
        ("FanOutErrorCount's marker-field doc (qg-fan-out-marker-fields span)", block_b),
        ("fan_out_error_count's convergence-log doc (qg-fan-out-convergence-fields span)", block_c),
    )
    for site_name, site_block in _sibling_sites:
        if site_block is not None and sibling_clause not in site_block:
            errs.append(
                f"SKILL: {site_name} missing the '{sibling_clause}' clause (round-7 S2 / "
                "round-9 S5)"
            )

    # (z3) round-7 S3, reshaped round-9 S5/S2 — the Anti-Rationalization
    # Table's trigger restatement carries the persistence_status AND
    # oversized-diff fail-open exceptions (previously only Compaction
    # Recovery 6e did, round-6 S1; oversized-diff added to this row round-9
    # S2), and INV-546-1 states the precondition once with 6e/Anti-Rat noted
    # as inheriting it. Was a ~150-char full-sentence file-wide pin; shortened
    # to the two shorter tokens that actually distinguish this row's content.
    if "resolves to `verifier-error`/`error`/`absent`" not in text or "does not dispatch" not in text:
        errs.append(
            "SKILL: Anti-Rationalization Table's fix-generated-defect dispatch-trigger row "
            "missing the persistence_status fail-open exception tokens (round-7 S3 — round-6 "
            "S1 swept this precondition into Compaction Recovery 6e's restatement but not "
            "into the Anti-Rat table's, the restatement an orchestrator under pressure "
            "actually consults)"
        )
    if "or the round-N diff is oversized (round 9, S2)" not in text:
        errs.append(
            "SKILL: Anti-Rationalization Table's fix-generated-defect dispatch-trigger row "
            "missing the oversized-diff fail-open exception (round-9 S2 — the row previously "
            "named only the persistence_status exception, so an orchestrator consulting this "
            "row under pressure would dispatch the checker on exactly the oversized-diff path "
            "input #2's pre-dispatch interception forbids)"
        )
    if "inherits it by reference" not in text:
        errs.append(
            "SKILL: INV-546-1 missing the 'inherits it by reference' consolidation of the "
            "persistence_status/oversized-diff precondition (round-7 S3; round-9 S2)"
        )

    # (z4) round-7 S4 — the oversized-diff counter is calibratable (a
    # recorded diff-size channel) and the two pre-dispatch interception
    # conditions have a stated, deterministic order. Both point-anchored
    # round-8 S1: these were the first two of round-8's three cited bare,
    # mutation-verified-maskable checks — the real document restates
    # 'fix-generated-diff-bytes' at the Telemetry-only paragraph and
    # INV-546-12, and the interception-order sentence at INV-546-12, so
    # deleting either operative site alone left these checks green.
    block_diff_bytes = _anchored(text, "qg-fan-out-diff-bytes-field")
    if block_diff_bytes is None or "fix-generated-diff-bytes" not in block_diff_bytes:
        errs.append(
            "SKILL: missing the 'fix-generated-diff-bytes' field inside its point-anchored "
            "CONTRACT span (round-7 S4 / round-8 S1 — without a recorded diff size, "
            "fan_out_oversized_count's 'too large' trigger has no threshold and the counter is "
            "uncalibrated across runs, reinstating round-6 F1's no-writer symptom through a "
            "different mechanism)"
        )
    # Reshaped round-9 S5: was a bare-inside-anchor full-sentence pin ("the size
    # measurement is orchestrator-local and always available, so it is checked
    # first"), which breaks CI on any benign re-word of that clause per
    # CHECKER_CONVENTIONS.md #1. The genuine contract is an ORDER between two
    # tokens, not the sentence explaining why — so assert both tokens are
    # present and `oversized-diff` precedes `persistence-unknown` (the anchor
    # was widened round-9 S5 to include both tokens, previously outside it).
    block_order = _anchored(text, "qg-fan-out-interception-order")
    if block_order is None:
        errs.append(
            "SKILL: fan-out interception-order CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-interception-order:START --> … :END -->, round-7 S4)"
        )
    else:
        idx_ov = block_order.find("oversized-diff")
        idx_pu = block_order.find("persistence-unknown")
        if idx_ov == -1 or idx_pu == -1:
            errs.append(
                "SKILL: interception-order CONTRACT span missing 'oversized-diff' and/or "
                "'persistence-unknown' tokens (round-7 S4 / round-9 S5 — reshaped from a "
                "full-sentence pin to a token-order assertion)"
            )
        elif idx_ov > idx_pu:
            errs.append(
                "SKILL: interception-order CONTRACT span has 'persistence-unknown' before "
                "'oversized-diff' — the deterministic order (oversized-diff checked first, "
                "persistence-unknown the residual, round-7 S4) is reversed or ambiguous"
            )

    # (z5) round-7 S5 — the fan-out checker's finding-identity rule is
    # mechanical (ordinal position), matching round-6 S5's counting rule,
    # so the join against persistence-checker-prompt.md's free-form
    # round_n_plus_1_finding_id values does not depend on two independently
    # rendered titles happening to match.
    block_z5 = _anchored(text, "qg-fan-out-finding-identity")
    if (
        block_z5 is None
        or "1-based ordinal of the finding's `**Severity:** Fatal`/`**Severity:** Significant` line"
        not in block_z5
    ):
        errs.append(
            "SKILL: missing the mechanical finding-identity rule ('1-based ordinal of the "
            "finding's **Severity:** Fatal/Significant line ... in file order') inside its "
            "point-anchored CONTRACT span (round-7 S5 — without a mechanical rule, a missed "
            "join between the two checkers' free-form finding identifiers is undetectable by "
            "the completeness invariant and silently promotes a persistent finding into "
            "fix-generated)"
        )

    # (z6) round-7 S6 — a not-triggered round runs the fan-out checker with
    # zero persistence-exclusions; that basis is now recorded per-round and
    # summed in the convergence log so the base rate can be stratified.
    # Point-anchored round-8 S1: this was the third of round-8's three cited
    # bare, mutation-verified-maskable checks — the real document restates
    # 'fix-generated-exclusion-basis' at the Telemetry-only paragraph, so
    # deleting the operative Round History bullet alone left this check
    # green.
    block_excl_basis = _anchored(text, "qg-fan-out-exclusion-basis-field")
    if block_excl_basis is None or "fix-generated-exclusion-basis" not in block_excl_basis:
        errs.append(
            "SKILL: missing the 'fix-generated-exclusion-basis' field inside its point-anchored "
            "CONTRACT span (round-7 S6 / round-8 S1 — a not-triggered round's zero-exclusion "
            "judgment population was otherwise untagged, so its upward bias could not be "
            "distinguished from a fired-clean round's measurement)"
        )
    block_c6 = _anchored(text, "qg-fan-out-convergence-fields")
    if block_c6 is None or '`fan_out_not_triggered_count`' not in block_c6:
        errs.append(
            "SKILL: missing the convergence-log 'fan_out_not_triggered_count' key inside the "
            "fan-out convergence-field CONTRACT block (round-7 S6)"
        )

    # (z7) round-9 S1 — the exclusion-basis `n/a` clause must be exhaustive
    # over every checker-error round, not just the orchestrator-side
    # interception rounds; a dispatched-and-returned status: error round was
    # previously undefined, which can drive the derived fired-clean stratum
    # size negative. The convergence-log gloss and its invariant must agree.
    if block_excl_basis is None or "or on any round recording `fix-generated-count: error`" not in block_excl_basis:
        errs.append(
            "SKILL: fix-generated-exclusion-basis's `n/a` clause is not exhaustive over "
            "checker-error rounds inside its point-anchored CONTRACT span (round-9 S1 — the "
            "prior 'fired only via an orchestrator-side error interception' wording left a "
            "dispatched-and-returned status: error round undefined)"
        )
    if block_c6 is None or 'rounds carrying a well-formed `status: "ok"` judgment' not in block_c6:
        errs.append(
            "SKILL: fan_out_not_triggered_count's gloss still reads (or lacks) 'rounds "
            "carrying a well-formed status: \"ok\" judgment' inside the fan-out "
            "convergence-field CONTRACT block (round-9 S1 — the old 'rounds where the checker "
            "ran' gloss double-counts a dispatched status:error round into both "
            "fan_out_error_count and fan_out_not_triggered_count)"
        )
    if block_c6 is None or "fan_out_not_triggered_count ≤ fan_out_check_count" not in block_c6:
        errs.append(
            "SKILL: missing the 'fan_out_not_triggered_count ≤ fan_out_check_count - "
            "fan_out_error_count' invariant inside the fan-out convergence-field CONTRACT "
            "block (round-9 S1 — without it, a negative derived fired-clean stratum size is "
            "not structurally ruled out)"
        )

    return errs


def check_prompt(text: str) -> list[str]:
    errs: list[str] = []

    # (j) JSON output schema field names.
    for key in (
        '"status"', '"round_n_plus_1_finding_count"', '"excluded_as_persistent"',
        '"judgments"', '"round_n_plus_1_finding_id"', '"judgment"',
        '"rationale_one_line"', '"fix_generated_count"', '"ambiguous_count"',
        '"error_reason"', '"error_cause"',
    ):
        if key not in text:
            errs.append(f"PROMPT: missing JSON schema key {key}")

    # (y) round-6 F1/S3 — error_cause enum values, and the interception
    # bullets under input #3 stating the matching cause the orchestrator
    # writes.
    for tok in ('"oversized-diff"', '"persistence-unknown"', '"transport"'):
        if tok not in text:
            errs.append(f"PROMPT: missing error_cause value {tok} (round-6 F1/S3)")
    if 'error_cause: "persistence-unknown"' not in text:
        errs.append(
            "PROMPT: missing 'error_cause: \"persistence-unknown\"' on the verifier-error/"
            "error/absent bullets (round-6 F1/S3 — the orchestrator writes this cause when it "
            "intercepts these tokens before dispatch)"
        )

    # (k) round-2 S7 — judgment value set includes 'ambiguous'.
    if '"ambiguous"' not in text:
        errs.append(
            "PROMPT: missing the 'ambiguous' judgment value (round-2 S7 — the direct "
            "analogue of the persistence checker's 'medium' band)"
        )

    # (l) persistence_status enum tokens, all backtick-quoted (round-2 M6).
    for tok in ("`fired-clean`", "`not-triggered`", "`verifier-error`", "`error`", "`absent`"):
        if tok not in text:
            errs.append(f"PROMPT: missing persistence_status token '{tok}'")

    # round-5 F3 — all-sections population scope (widened from round-3 F1's
    # heading-scoped population). Point-anchored round-8 S1 audit: the real
    # prompt file restates 'Second Pass Findings' in its own Rules bullet
    # (input #1 population re-cited under `judgments`), so a bare check for
    # this operative Task-step-1 definition alone was maskable.
    block_pop = _anchored(text, "qg-fan-out-prompt-population-scope")
    if block_pop is None:
        errs.append(
            "PROMPT: in-scope population-scope CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-prompt-population-scope:START --> … :END -->, round-8 S1)"
        )
    block_pop_text = block_pop or ""
    if "regardless of which section it appears under" not in block_pop_text:
        errs.append(
            "PROMPT: missing the all-sections population-scope phrase ('regardless of which "
            "section it appears under') inside its point-anchored CONTRACT span (round-5 F3 / "
            "round-8 S1 — widened from round-3 F1's heading-scoped population)"
        )
    if "Second Pass Findings" not in block_pop_text:
        errs.append(
            "PROMPT: missing the explicit 'Second Pass Findings' in-scope carve-out inside its "
            "point-anchored CONTRACT span (round-3 F1 / round-5 F3 / round-8 S1)"
        )
    if "counting `**Severity:** Fatal` and `**Severity:** Significant` lines" not in block_pop_text:
        errs.append(
            "PROMPT: missing the mechanical 'counting **Severity:** Fatal and **Severity:** "
            "Significant lines' counting rule inside its point-anchored CONTRACT span "
            "(round-6 S5 mirror / round-8 S1 — "
            "must match SKILL.md's completeness-audit counting rule so both readers segment "
            "the file identically)"
        )

    # (r) round-4 F1 mirror — the fired-clean bullet's exclusion rule carries
    # the same qualifier SKILL.md's does.
    if "in-scope** round-(N+1) Fatal/Significant finding" not in text:
        errs.append(
            "PROMPT: fired-clean bullet missing the 'in-scope' qualifier on its exclusion rule "
            "(round-4 F1 mirror)"
        )
    if "Minors are outside this checker's scope entirely" not in text:
        errs.append(
            "PROMPT: fired-clean bullet missing the Minor-finding carve-out ('Minors are "
            "outside this checker's scope entirely') (round-4 F1 / round-5 F3 mirror)"
        )
    if "medium`-confidence match is NOT excluded" not in text:
        errs.append(
            "PROMPT: fired-clean bullet missing the `medium`-confidence-match instruction "
            "(round-5 M8 mirror)"
        )

    # round-5 M4 — anti-anchoring self-description must not understate input #2.
    if "You do NOT receive prior rounds' findings beyond what `round-(N+1)-persistence.md` already summarizes" in text:
        errs.append(
            "PROMPT: the anti-anchoring self-description still claims it does not receive "
            "prior-round findings beyond persistence.md's summary — false, since input #2 "
            "supplies the full round-N fix-journal entry including Findings-addressed and "
            "Verifier-Assessment (round-5 M4)"
        )
    if "including its `Findings addressed`" not in text:
        errs.append(
            "PROMPT: missing the corrected anti-anchoring self-description acknowledging input "
            "#2's full fix-journal entry (round-5 M4)"
        )

    # round-7 S5 — mechanical finding-identity rule, mirroring SKILL.md's
    # qg-fan-out-finding-identity CONTRACT span, so the join against
    # persistence-checker-prompt.md's round_n_plus_1_finding_id values does
    # not depend on two independently-rendered free-form titles matching.
    if "1-based ordinal of the finding's `**Severity:** Fatal`/`**Severity:** Significant` line" not in text:
        errs.append(
            "PROMPT: missing the mechanical finding-identity rule ('1-based ordinal of the "
            "finding's **Severity:** Fatal/Significant line ... in file order') (round-7 S5 "
            "mirror of SKILL.md's qg-fan-out-finding-identity span)"
        )
    if "the finding's 1-based ordinal among **Severity:** Fatal/Significant lines" not in text:
        errs.append(
            "PROMPT: JSON schema's round_n_plus_1_finding_id comment still describes a "
            "free-form '<id or short title>' rather than the mechanical ordinal rule "
            "(round-7 S5)"
        )

    return errs


def check_persistence(text: str) -> list[str]:
    """Round-8, F1: `persistence-checker-prompt.md`'s `round_n_plus_1_finding_id`
    must actually carry the same mechanical ordinal rule SKILL.md's
    `qg-fan-out-finding-identity` span claims this file uses. Prior to round 8
    this file defined the field as a free-form `<id or short title>` string —
    the claim in SKILL.md was FALSE. Point-anchored inside
    `qg-fan-out-persistence-finding-id-rule`.
    """
    errs: list[str] = []
    block = _anchored(text, "qg-fan-out-persistence-finding-id-rule")
    if block is None:
        errs.append(
            "PERSISTENCE: finding-identity-rule CONTRACT block not found "
            "(<!-- CONTRACT:qg-fan-out-persistence-finding-id-rule:START --> … :END -->, round-8 F1)"
        )
    else:
        if (
            "1-based ordinal among `**Severity:** Fatal`/`**Severity:** Significant` line"
            not in block
        ):
            errs.append(
                "PERSISTENCE: missing the mechanical ordinal-position rule inside its "
                "point-anchored CONTRACT span (round-8 F1 — 'the finding's 1-based ordinal "
                "among **Severity:** Fatal/**Severity:** Significant lines in "
                "round-(N+1)-findings.md, in file order')"
            )
        if "Minor/Nit" not in block or "title-only id" not in block:
            errs.append(
                "PERSISTENCE: missing the Minor/Nit title-only-id carve-out inside its "
                "point-anchored CONTRACT span (round-8 F1 — this checker's own population is "
                "all severities, so the ordinal rule, scoped to the Fatal/Significant subset "
                "only, needs an explicit fallback for Minor/Nit findings)"
            )
    if "1-based ordinal among" not in text:
        errs.append(
            "PERSISTENCE: the round_n_plus_1_finding_id JSON schema comment still describes a "
            "free-form '<id or short title>' rather than the mechanical ordinal rule (round-8 F1)"
        )
    return errs


def _read(path: pathlib.Path, errs: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError) as err:
        errs.append(f"{path} missing or unreadable: {err}")
        return None


# Minimal fixtures carrying every pinned phrase — positive controls for --selftest.
# Each point-anchored phrase also has a "table restatement" copy elsewhere in the
# fixture, deliberately, so the round-4-S1-shaped positive controls below (gut the
# anchor, leave the restatement) exercise the exact failure mode they fix.
_GOOD_SKILL_FIXTURE = """
Verdict: PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION
Reason: clean-pass | siege-blocked | sustained-regression | no-op-fix
Round-numbering convention: round-N-score.md is a generic template name; the score file this section actually reads and writes is the **current** round's, i.e. round-(N+1)-score.md.
<!-- CONTRACT:qg-fan-out-marker-fields:START -->
FanOutRounds: <list>
FanOutCheckCount: <int>
FanOutErrorCount: <int — count of rounds whose round-(N+1)-fix-generated.md carries status: error — whether the checker returned it or the orchestrator wrote it in the checker's place>
invariant: len(FanOutRounds) ≤ FanOutCheckCount
invariant: FanOutErrorCount ≤ FanOutCheckCount
estimator: len(FanOutRounds) / (FanOutCheckCount - FanOutErrorCount)
<!-- CONTRACT:qg-fan-out-marker-fields:END -->
INV-546-5 table restatement: invariants len(FanOutRounds) ≤ FanOutCheckCount and FanOutErrorCount ≤ FanOutCheckCount.
<!-- CONTRACT:qg-fan-out-convergence-fields:START -->
- `fan_out_rounds`: JSON list.
- `fan_out_check_count`: integer count.
- `fan_out_error_count`: integer count — rounds whose round-(N+1)-fix-generated.md carries status: error, whether the checker returned it or the orchestrator wrote it in the checker's place.
- `fan_out_oversized_count`: integer count.
- `fan_out_ambiguous_count`: integer count. Sourcing: sums only over rounds whose value there is an integer; read this count against `fan_out_check_count - fan_out_error_count`, not against `fan_out_check_count`.
- `fan_out_not_triggered_count`: integer count of rounds carrying a well-formed `status: "ok"` judgment. Invariant: fan_out_not_triggered_count ≤ fan_out_check_count - fan_out_error_count.
- `fan_out_rounds_not_triggered`: JSON list.
- `fan_out_diff_bytes_max`: integer max.
- `fan_out_diff_bytes_total`: integer sum. Read these against `fan_out_check_count - fan_out_error_count`, not against `fan_out_check_count`.
<!-- CONTRACT:qg-fan-out-convergence-fields:END -->
<!-- CONTRACT:qg-fix-generated-persistence-status:START -->
Value set: "fired-clean" | "not-triggered" | "verifier-error" | "error" | "absent"
<!-- CONTRACT:qg-fix-generated-persistence-status:END -->
**Dispatch ordering.** <!-- CONTRACT:qg-fan-out-dispatch-ordering:START -->Dispatched strictly AFTER the persistence checker resolves.<!-- CONTRACT:qg-fan-out-dispatch-ordering:END -->
INV-546-1 table restatement: dispatched strictly AFTER the persistence checker resolves for round N+1, never in parallel. This precondition is stated once, and every restatement inherits it by reference rather than restating it independently.
<!-- CONTRACT:qg-fan-out-orchestrator-fail-open:START -->The orchestrator does **not** dispatch the fix-generated-defect checker on verifier-error/error/absent, writing error_cause: "persistence-unknown".<!-- CONTRACT:qg-fan-out-orchestrator-fail-open:END -->
Input #2 oversized-diff interception writes <!-- CONTRACT:qg-fan-out-oversized-diff-error-cause:START -->error_cause: "oversized-diff"<!-- CONTRACT:qg-fan-out-oversized-diff-error-cause:END -->.
INV-546-12 table restatement: error_cause: "oversized-diff" on the orchestrator-side interception.
<!-- CONTRACT:qg-fan-out-error-cause-field:START -->`fix-generated-error-cause`: `oversized-diff` | `persistence-unknown` | `transport` | `n/a`.<!-- CONTRACT:qg-fan-out-error-cause-field:END -->
<!-- CONTRACT:qg-fan-out-diff-bytes-field:START -->`fix-generated-diff-bytes`: integer, orchestrator-estimated not byte-exact, recorded on every round the trigger fires.<!-- CONTRACT:qg-fan-out-diff-bytes-field:END -->
Telemetry-only-paragraph restatement: fix-generated-diff-bytes is recorded every round.
<!-- CONTRACT:qg-fan-out-interception-order:START -->error_cause is oversized-diff — the size measurement is orchestrator-local and always available, so it is checked first — and persistence-unknown is the residual cause.<!-- CONTRACT:qg-fan-out-interception-order:END -->
INV-546-12 table restatement: the size measurement is orchestrator-local and always available, so it is checked first.
<!-- CONTRACT:qg-fan-out-population-scope:START -->Population is every Fatal/Significant-severity finding entry, regardless of which section it appears under — including any `### Second Pass Findings` section.<!-- CONTRACT:qg-fan-out-population-scope:END -->
INV-546-7 table restatement: population is every Fatal/Significant-severity finding entry, regardless of which section it appears under — including any `### Second Pass Findings` section.
<!-- CONTRACT:qg-fan-out-exclusion-scope:START -->On fired-clean, exclude any **in-scope** round-(N+1) Fatal/Significant finding; a match on a Minor finding is NOT excluded — Minors are outside this checker's scope entirely. A `medium`-confidence correspondence is NOT excluded either.<!-- CONTRACT:qg-fan-out-exclusion-scope:END -->
<!-- CONTRACT:qg-fan-out-finding-identity:START -->the 1-based ordinal of the finding's `**Severity:** Fatal`/`**Severity:** Significant` line within round-(N+1)-findings.md, in file order<!-- CONTRACT:qg-fan-out-finding-identity:END -->
<!-- CONTRACT:qg-fan-out-completeness-audit:START -->The orchestrator audits the checker's output against its own independently-computed Fatal+Significant count for `round-(N+1)-findings.md`, computed by counting `**Severity:** Fatal` and `**Severity:** Significant` lines across the whole file. This count is deliberately NOT the same as the #366 Score-source count. The checker's own declared round_n_plus_1_finding_count is a reviewer-declared cross-check only. On a mismatch the orchestrator does NOT void the round — this completeness audit is a narration-log signal, not a precondition for trusting fix_generated_count.<!-- CONTRACT:qg-fan-out-completeness-audit:END -->
INV-546-7 table restatement: independently-computed Fatal+Significant count; reviewer-declared cross-check only.
When the streak reaches 2, <!-- CONTRACT:qg-fan-out-streak-note-field:START -->record the following as a free-text `fan-out-streak-note:` line in `round-(N+1)-score.md`<!-- CONTRACT:qg-fan-out-streak-note-field:END -->: "Fix-generated-defect streak: rounds N and N+1 each surfaced ...". <!-- CONTRACT:qg-fan-out-never-escalates:START -->This note never escalates, never changes the verdict or precedence.<!-- CONTRACT:qg-fan-out-never-escalates:END -->
INV-546-2 table restatement: fan-out-streak-note: never escalates, never changes the verdict or precedence.
<!-- CONTRACT:qg-fan-out-code-exclusion:START -->On a `code` gate, record fix-generated-count: n/a and do not increment FanOutCheckCount.<!-- CONTRACT:qg-fan-out-code-exclusion:END -->
INV-546-10 table restatement: fix-generated-count: n/a on code gates.
<!-- CONTRACT:qg-fan-out-recovery-trigger:START -->AND the artifact type is not `code` AND `persistence_status` resolves to `fired-clean` or `not-triggered` AND the round-N diff is not oversized<!-- CONTRACT:qg-fan-out-recovery-trigger:END -->
Anti-Rationalization Table restatement: Dispatch the fix-generated-defect checker on every non-clean non-`code` round following a fix, regardless of the fix verifier's Resolved/Unresolved outcome — except when `persistence_status` resolves to `verifier-error`/`error`/`absent`, or the round-N diff is oversized (round 9, S2), where the orchestrator writes the `status: error` object itself and does not dispatch.
<!-- CONTRACT:qg-fan-out-count-field-value-note:START -->`fix-generated-count`: integer, or `0`, or <!-- CONTRACT:qg-fan-out-score-field-encoding-count:START -->`error` on rounds where a `status: error` object exists for the round in round-(N+1)-fix-generated.md — whether the checker returned it or the orchestrator wrote it in the checker's place — ; `n/a` only on rounds where no `round-(N+1)-fix-generated.md` object exists at all<!-- CONTRACT:qg-fan-out-score-field-encoding-count:END -->, or `n/a` (three-value-plus-`n/a` encoding).<!-- CONTRACT:qg-fan-out-count-field-value-note:END -->
INV-546-8 table restatement: fix-generated-count `error` on rounds where a status: error object exists for the round.
File EXISTS with `status: error` → `fix-generated-count: error` is recorded.
`FanOutCheckCount` is the count of score files whose fix-generated-count is not n/a; `FanOutErrorCount` is the count whose value is `error`.
<!-- CONTRACT:qg-fan-out-ambiguous-count-field:START -->`fix-generated-ambiguous-count`: <!-- CONTRACT:qg-fan-out-score-field-encoding-ambiguous:START -->integer, or `0`, or `error`, or `n/a`<!-- CONTRACT:qg-fan-out-score-field-encoding-ambiguous:END --> (three-value-plus-`n/a` encoding).
<!-- CONTRACT:qg-fan-out-score-field-encoding-ambiguous-detail:START -->`error` on rounds where a `status: error` object exists for the round — whether the checker returned it or the orchestrator wrote it in the checker's place; `n/a` only on rounds where no `round-(N+1)-fix-generated.md` object exists at all<!-- CONTRACT:qg-fan-out-score-field-encoding-ambiguous-detail:END --><!-- CONTRACT:qg-fan-out-ambiguous-count-field:END -->
INV-546-8 table restatement: fix-generated-ambiguous-count integer, or `0`, or `error`, or `n/a`.
Telemetry-only-paragraph restatement: fix-generated-ambiguous-count is recorded every round.
<!-- CONTRACT:qg-fan-out-exclusion-basis-field:START -->`fix-generated-exclusion-basis`: `fired-clean` | `not-triggered` | `n/a` — n/a when the checker did not fire or on any round recording `fix-generated-count: error`.<!-- CONTRACT:qg-fan-out-exclusion-basis-field:END -->
Telemetry-only-paragraph restatement: fix-generated-exclusion-basis is recorded every round.
"""

_GOOD_PROMPT_FIXTURE = """
{
  "status": "ok",
  "round_n_plus_1_finding_count": 1,
  "excluded_as_persistent": 0,
  "judgments": [
    {"round_n_plus_1_finding_id": "x", "judgment": "fix-generated" | "ambiguous" | "pre-existing", "rationale_one_line": "y"}
  ],
  "fix_generated_count": 1,
  "ambiguous_count": 0,
  "error_cause": "oversized-diff" | "persistence-unknown" | "transport",
  "error_reason": "n/a"
}
persistence_status token: `fired-clean` | `not-triggered` | `verifier-error` | `error` | `absent`
verifier-error/error/absent bullets: the orchestrator writes error_cause: "persistence-unknown".
<!-- CONTRACT:qg-fan-out-prompt-population-scope:START -->In-scope population: every Fatal/Significant-severity finding entry, regardless of which section it appears under — including any `### Second Pass Findings` section, computed by counting `**Severity:** Fatal` and `**Severity:** Significant` lines.<!-- CONTRACT:qg-fan-out-prompt-population-scope:END -->
Rules-section restatement: judgments includes Second Pass Findings entries.
fired-clean bullet: exclude any **in-scope** round-(N+1) Fatal/Significant finding; a match on a Minor finding is not excluded — Minors are outside this checker's scope entirely. A `medium`-confidence match is NOT excluded — judge it ambiguous.
Finding identity: the finding's 1-based ordinal among **Severity:** Fatal/Significant lines in round-(N+1)-findings.md, in file order — the 1-based ordinal of the finding's `**Severity:** Fatal`/`**Severity:** Significant` line within round-(N+1)-findings.md.
Anti-anchoring: you receive the full round-N fix-journal entry per input #2, including its `Findings addressed` and any Verifier Assessment.
"""

_GOOD_PERSISTENCE_FIXTURE = """
{
  "round_n_plus_1_finding_id": "<Fatal/Significant: the finding's 1-based ordinal among **Severity:** Fatal/**Severity:** Significant lines in round-(N+1)-findings.md, in file order, optionally suffixed with a short title; Minor/Nit: a title-only id>"
}
<!-- CONTRACT:qg-fan-out-persistence-finding-id-rule:START -->Finding-identity rule: round_n_plus_1_finding_id is the finding's 1-based ordinal among `**Severity:** Fatal`/`**Severity:** Significant` lines in round-(N+1)-findings.md, in file order, optionally suffixed with a short title. A Minor/Nit-severity finding keeps a title-only id.<!-- CONTRACT:qg-fan-out-persistence-finding-id-rule:END -->
"""


def selftest() -> int:
    """Negative-control self-test: assert the checker is not a no-op."""
    errs: list[str] = []
    good_skill = check_skill(_GOOD_SKILL_FIXTURE)
    if good_skill:
        errs.append(f"selftest: GOOD skill fixture unexpectedly reported errors: {good_skill}")
    good_prompt = check_prompt(_GOOD_PROMPT_FIXTURE)
    if good_prompt:
        errs.append(f"selftest: GOOD prompt fixture unexpectedly reported errors: {good_prompt}")
    good_persistence = check_persistence(_GOOD_PERSISTENCE_FIXTURE)
    if good_persistence:
        errs.append(f"selftest: GOOD persistence fixture unexpectedly reported errors: {good_persistence}")

    # Positive-control regression: reintroducing SUSTAINED_FAN_OUT into the
    # closed marker enum must trip the checker.
    bad_verdict = _GOOD_SKILL_FIXTURE.replace(
        "Verdict: PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION",
        "Verdict: PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION | SUSTAINED_FAN_OUT",
    )
    if not check_skill(bad_verdict):
        errs.append("selftest: reintroducing SUSTAINED_FAN_OUT into Verdict: did NOT trip the checker")

    bad_reason = _GOOD_SKILL_FIXTURE.replace(
        "Reason: clean-pass | siege-blocked | sustained-regression | no-op-fix",
        "Reason: clean-pass | siege-blocked | sustained-regression | sustained-fan-out | no-op-fix",
    )
    if not check_skill(bad_reason):
        errs.append("selftest: reintroducing sustained-fan-out into Reason: did NOT trip the checker")

    # Positive-control regression (round-5 S1): reintroducing the
    # self-contradictory "cap it and fail open" instruction must trip the
    # checker.
    bad_oversized = _GOOD_SKILL_FIXTURE + "\nIf the diff is too large, cap it and fail open.\n"
    if not check_skill(bad_oversized):
        errs.append("selftest: reintroducing 'cap it and fail open' did NOT trip the checker (round-5 S1)")

    # Positive-control regression (round-9 S5): the interception-order check
    # was reshaped from a full-sentence pin to a token-order assertion —
    # reversing which token comes first inside the anchor must still trip it.
    reversed_order = _GOOD_SKILL_FIXTURE.replace(
        "<!-- CONTRACT:qg-fan-out-interception-order:START -->error_cause is oversized-diff — "
        "the size measurement is orchestrator-local and always available, so it is checked "
        "first — and persistence-unknown is the residual cause."
        "<!-- CONTRACT:qg-fan-out-interception-order:END -->",
        "<!-- CONTRACT:qg-fan-out-interception-order:START -->error_cause is persistence-unknown — "
        "the size measurement is orchestrator-local and always available, so it is checked "
        "first — and oversized-diff is the residual cause."
        "<!-- CONTRACT:qg-fan-out-interception-order:END -->",
    )
    assert reversed_order != _GOOD_SKILL_FIXTURE, "selftest fixture setup: reversed_order replace found no match"
    if not check_skill(reversed_order):
        errs.append(
            "selftest: reversing the interception-order tokens (persistence-unknown before "
            "oversized-diff) did NOT trip the checker (round-9 S5)"
        )

    # Positive-control regression (round-9 S6): reintroducing the vacuous
    # "would bias this sum low" rationale must trip the checker.
    bad_vacuous_rationale = _GOOD_SKILL_FIXTURE + "\nFolding it into 0 would bias this sum low.\n"
    if not check_skill(bad_vacuous_rationale):
        errs.append(
            "selftest: reintroducing 'would bias this sum low' did NOT trip the checker "
            "(round-9 S6)"
        )

    # round-3 M1: the absence check is scoped to the fan-out convergence-field
    # CONTRACT block — reintroducing the retired key INSIDE that block must
    # still trip the checker...
    reintroduced_field = _GOOD_SKILL_FIXTURE.replace(
        "<!-- CONTRACT:qg-fan-out-convergence-fields:END -->",
        "- `sustained_fan_out`: boolean.\n<!-- CONTRACT:qg-fan-out-convergence-fields:END -->",
    )
    if not check_skill(reintroduced_field):
        errs.append("selftest: reintroducing 'sustained_fan_out' convergence-log key did NOT trip the checker (M1)")

    # ...but documenting the retired key OUTSIDE the block (e.g. a future
    # "Retired" prose entry) must NOT trip the checker — that permission is
    # the entire point of round-3 M1's fix.
    documented_retired_key_outside_block = _GOOD_SKILL_FIXTURE + "\nRetired: `sustained_fan_out` must not be reintroduced.\n"
    outside_errs = check_skill(documented_retired_key_outside_block)
    if any("sustained_fan_out" in e for e in outside_errs):
        errs.append(
            "selftest: documenting the retired 'sustained_fan_out' key OUTSIDE the "
            "convergence-field CONTRACT block incorrectly tripped the checker (round-3 M1 "
            "— this must be permitted, that's the fix)"
        )

    # Positive-control regression (round-2 M3): a second line-anchored
    # 'Verdict: '/'Reason: ' line must trip the new exactly-one-match guard.
    duplicated_verdict = _GOOD_SKILL_FIXTURE + "\nVerdict: PASS\n"
    if not check_skill(duplicated_verdict):
        errs.append("selftest: a second 'Verdict:' line did NOT trip the exactly-one-match guard (round-2 M3)")

    duplicated_reason = _GOOD_SKILL_FIXTURE + "\nReason: clean-pass\n"
    if not check_skill(duplicated_reason):
        errs.append("selftest: a second 'Reason:' line did NOT trip the exactly-one-match guard (round-2 M3)")

    # Positive-control regression (round-3 M4, extended round-4 S1): deleting
    # ONLY the point-anchored operative content, while an identical-phrase
    # table restatement survives elsewhere in the fixture, must still trip
    # the checker — this is the exact failure mode M4/round-4-S1 reported (a
    # plain global substring search would pass).
    def _gut(anchor: str, fixture: str) -> str:
        return re.sub(
            rf"<!-- CONTRACT:{re.escape(anchor)}:START -->.*?"
            rf"<!-- CONTRACT:{re.escape(anchor)}:END -->",
            f"<!-- CONTRACT:{anchor}:START --><!-- CONTRACT:{anchor}:END -->",
            fixture, flags=re.DOTALL,
        )

    for anchor, label in (
        ("qg-fan-out-dispatch-ordering", "dispatch-ordering (round-3 M4)"),
        ("qg-fan-out-never-escalates", "never-escalates (round-3 M4)"),
        ("qg-fan-out-population-scope", "population-scope (round-4 S1)"),
        ("qg-fan-out-code-exclusion", "code-exclusion (round-4 S1)"),
        ("qg-fan-out-completeness-audit", "completeness-audit (round-4 S1)"),
        ("qg-fan-out-streak-note-field", "streak-note-field (round-4 S1)"),
        ("qg-fan-out-exclusion-scope", "exclusion-scope (round-4 F1)"),
        ("qg-fan-out-orchestrator-fail-open", "orchestrator-fail-open (round-5 S4)"),
        ("qg-fan-out-recovery-trigger", "recovery-trigger (round-5 F1)"),
        ("qg-fan-out-score-field-encoding-count", "score-field-encoding-count (round-6 S4)"),
        ("qg-fan-out-score-field-encoding-ambiguous", "score-field-encoding-ambiguous (round-6 S4)"),
        ("qg-fan-out-score-field-encoding-ambiguous-detail", "score-field-encoding-ambiguous-detail (round-7 F1)"),
        ("qg-fan-out-finding-identity", "finding-identity (round-7 S5)"),
        ("qg-fan-out-marker-fields", "marker-fields (round-8 S1)"),
        ("qg-fan-out-count-field-value-note", "count-field-value-note (round-8 S1)"),
        ("qg-fan-out-ambiguous-count-field", "ambiguous-count-field (round-8 S1)"),
        ("qg-fan-out-diff-bytes-field", "diff-bytes-field (round-8 S1)"),
        ("qg-fan-out-exclusion-basis-field", "exclusion-basis-field (round-8 S1)"),
        ("qg-fan-out-error-cause-field", "error-cause-field (round-8 S1)"),
        ("qg-fan-out-oversized-diff-error-cause", "oversized-diff-error-cause (round-8 S1)"),
        ("qg-fan-out-interception-order", "interception-order (round-8 S1)"),
    ):
        gutted = _gut(anchor, _GOOD_SKILL_FIXTURE)
        if not check_skill(gutted):
            errs.append(
                f"selftest: deleting the anchored {label} span, with any table restatement "
                f"left intact, did NOT trip the checker"
            )

    # round-8 S1 — same gut-test shape, applied to the new PROMPT and
    # PERSISTENCE anchors.
    for anchor, label in (
        ("qg-fan-out-prompt-population-scope", "prompt population-scope (round-8 S1)"),
    ):
        gutted = _gut(anchor, _GOOD_PROMPT_FIXTURE)
        if not check_prompt(gutted):
            errs.append(
                f"selftest: deleting the anchored {label} span, with any restatement left "
                f"intact, did NOT trip the PROMPT checker"
            )

    for anchor, label in (
        ("qg-fan-out-persistence-finding-id-rule", "persistence finding-id-rule (round-8 F1)"),
    ):
        gutted = _gut(anchor, _GOOD_PERSISTENCE_FIXTURE)
        if not check_persistence(gutted):
            errs.append(
                f"selftest: deleting the anchored {label} span did NOT trip the PERSISTENCE checker"
            )

    skill_mutations = {
        "FanOutRounds field": "FanOutRounds:",
        "FanOutCheckCount field": "FanOutCheckCount:",
        "invariant": "len(FanOutRounds) ≤ FanOutCheckCount",
        "FanOutErrorCount invariant (round-5 M2)": "FanOutErrorCount ≤ FanOutCheckCount",
        "fan_out_rounds key": "`fan_out_rounds`",
        "fan_out_check_count key": "`fan_out_check_count`",
        "fan_out_oversized_count key (round-5 S1)": "`fan_out_oversized_count`",
        "fan_out_ambiguous_count key (round-5 S3)": "`fan_out_ambiguous_count`",
        "fan_out_diff_bytes_max key (round-8 S2)": "`fan_out_diff_bytes_max`",
        "fan_out_diff_bytes_total key (round-8 S2)": "`fan_out_diff_bytes_total`",
        "CONTRACT block": "<!-- CONTRACT:qg-fix-generated-persistence-status:END -->",
        "quoted 'fired-clean'": '"fired-clean"',
        "quoted 'not-triggered'": '"not-triggered"',
        "quoted 'verifier-error'": '"verifier-error"',
        "quoted 'error'": '"error"',
        "quoted 'absent'": '"absent"',
        "dispatch ordering": "strictly AFTER the persistence checker",
        "completeness-audit narration-log signal (round-9 S5)": "narration-log signal",
        "FanOutErrorCount field (round-3 F2)": "FanOutErrorCount:",
        "fan_out_error_count key (round-3 F2)": "`fan_out_error_count`",
        "corrected base-rate estimator (round-3 F2)": "FanOutCheckCount - FanOutErrorCount",
        "fan-out convergence-fields CONTRACT block (round-3 M1)": "<!-- CONTRACT:qg-fan-out-convergence-fields:END -->",
        "dispatch-ordering CONTRACT anchor (round-3 M4)": "<!-- CONTRACT:qg-fan-out-dispatch-ordering:END -->",
        "never-escalates CONTRACT anchor (round-3 M4)": "<!-- CONTRACT:qg-fan-out-never-escalates:END -->",
        "population-scope CONTRACT anchor (round-4 S1)": "<!-- CONTRACT:qg-fan-out-population-scope:END -->",
        "code-exclusion CONTRACT anchor (round-4 S1)": "<!-- CONTRACT:qg-fan-out-code-exclusion:END -->",
        "completeness-audit CONTRACT anchor (round-4 S1)": "<!-- CONTRACT:qg-fan-out-completeness-audit:END -->",
        "streak-note-field CONTRACT anchor (round-4 S1)": "<!-- CONTRACT:qg-fan-out-streak-note-field:END -->",
        "exclusion-scope CONTRACT anchor (round-4 F1)": "<!-- CONTRACT:qg-fan-out-exclusion-scope:END -->",
        "in-scope qualifier inside exclusion-scope anchor (round-4 F1)": "in-scope** round-(N+1) Fatal/Significant finding",
        "Minor carve-out inside exclusion-scope anchor (round-4 F1 / round-5 F3)": "outside this checker's scope entirely",
        "medium-confidence clause inside exclusion-scope anchor (round-5 M8)": "`medium`-confidence correspondence",
        "all-sections population-scope phrase (round-5 F3)": "regardless of which section it appears under",
        "completeness-audit #366-decoupling phrase (round-5 F3)": "deliberately NOT the same as the #366 Score-source count",
        "orchestrator-fail-open CONTRACT anchor (round-5 S4)": "<!-- CONTRACT:qg-fan-out-orchestrator-fail-open:END -->",
        "orchestrator-fail-open text (round-5 S4)": "does **not** dispatch the fix-generated-defect checker",
        "recovery-trigger CONTRACT anchor (round-5 F1)": "<!-- CONTRACT:qg-fan-out-recovery-trigger:END -->",
        "recovery-trigger code qualifier (round-5 F1)": "AND the artifact type is not `code`",
        "three-value fix-generated-count encoding note (round-5 F2)": "three-value-plus-`n/a` encoding",
        "fix-generated-count: error token (round-5 F2)": "`fix-generated-count: error`",
        "6e FanOutCheckCount reconstruction rule (round-5 F2)": "is the count of score files",
        "6e FanOutErrorCount reconstruction rule (round-5 F2)": "FanOutErrorCount` is the count whose value is `error`",
        "fix-generated-ambiguous-count field (round-5 S3)": "fix-generated-ambiguous-count",
        "orchestrator-side persistence-unknown error_cause (round-6 F1/S3)": 'error_cause: "persistence-unknown"',
        "orchestrator-side oversized-diff error_cause (round-6 F1)": 'error_cause: "oversized-diff"',
        "fix-generated-error-cause field (round-6 F1)": "`fix-generated-error-cause`",
        "persistence_status recovery-trigger condition (round-6 S1)": "resolves to `fired-clean` or `not-triggered`",
        "fan_out_ambiguous_count integer-only sourcing (round-6 S2)": "only over rounds whose value there is an integer",
        "completeness-audit mechanical counting rule (round-6 S5)": "counting `**Severity:** Fatal` and `**Severity:** Significant` lines",
        "round-numbering convention sentence (round-7 S1)": "the score file this section actually reads and writes is the **current** round's",
        "streak note 'rounds N and N+1' text (round-7 S1)": "rounds N and N+1 each surfaced",
        "checker-returned-or-orchestrator-wrote sibling clause (round-7 S2)": "the checker returned it or the orchestrator wrote it in the checker's place",
        "FanOutErrorCount marker field's 'rounds whose ... carries status: error' framing (round-7 S2)": "FanOutErrorCount: <int — count of rounds whose round-(N+1)-fix-generated.md carries status: error",
        "Anti-Rat persistence_status fail-open exception tokens (round-7 S3)": "resolves to `verifier-error`/`error`/`absent`",
        "Anti-Rat oversized-diff fail-open exception (round-9 S2)": "or the round-N diff is oversized (round 9, S2)",
        "INV-546-1 precondition-inheritance consolidation (round-7 S3)": "inherits it by reference rather than restating it independently",
        "fix-generated-diff-bytes field (round-7 S4)": "`fix-generated-diff-bytes`",
        "fix-generated-exclusion-basis field (round-7 S6)": "fix-generated-exclusion-basis",
        "fan_out_not_triggered_count key (round-7 S6)": "`fan_out_not_triggered_count`",
        "recovery-trigger oversized-diff condition (round-9 S2)": "the round-N diff is not oversized",
        "exclusion-basis exhaustive n/a clause (round-9 S1)": "or on any round recording `fix-generated-count: error`",
        "fan_out_not_triggered_count well-formed-ok gloss (round-9 S1)": 'rounds carrying a well-formed `status: "ok"` judgment',
        "fan_out_not_triggered_count invariant (round-9 S1)": "fan_out_not_triggered_count ≤ fan_out_check_count",
        "fan_out_rounds_not_triggered key (round-9 S4)": "`fan_out_rounds_not_triggered`",
        "denominator-correction sentence (round-9 S6)": "not against `fan_out_check_count`",
    }
    for label, needle in skill_mutations.items():
        broken = _GOOD_SKILL_FIXTURE.replace(needle, "")
        if not check_skill(broken):
            errs.append(f"selftest: removing '{label}' did NOT trip the SKILL checker (no-op grep)")

    prompt_mutations = {
        '"status" key': '"status"',
        '"fix_generated_count" key': '"fix_generated_count"',
        '"ambiguous_count" key': '"ambiguous_count"',
        '"judgment" key': '"judgment"',
        "'ambiguous' judgment value (S7)": '"ambiguous"',
        "`fired-clean` token": "`fired-clean`",
        "`not-triggered` token": "`not-triggered`",
        "`verifier-error` token": "`verifier-error`",
        "`error` token": "`error`",
        "`absent` token": "`absent`",
        "all-sections population-scope phrase (round-5 F3)": "regardless of which section it appears under",
        "Second Pass Findings carve-out (round-3 F1 / round-5 F3)": "Second Pass Findings",
        "in-scope qualifier on fired-clean bullet (round-4 F1)": "in-scope** round-(N+1) Fatal/Significant finding",
        "Minor carve-out on fired-clean bullet (round-4 F1 / round-5 F3)": "Minors are outside this checker's scope entirely",
        "medium-confidence clause on fired-clean bullet (round-5 M8)": "medium`-confidence match is NOT excluded",
        "corrected anti-anchoring self-description (round-5 M4)": "including its `Findings addressed`",
        '"error_cause" key (round-6 F1/S3)': '"error_cause"',
        "error_cause 'oversized-diff' value (round-6 F1)": '"oversized-diff"',
        "error_cause 'persistence-unknown' value (round-6 S3)": '"persistence-unknown"',
        "error_cause 'transport' value (round-6 F1)": '"transport"',
        "persistence-unknown error_cause mirror on interception bullets (round-6 F1/S3)": 'error_cause: "persistence-unknown"',
        "completeness-audit counting-rule mirror (round-6 S5)": "counting `**Severity:** Fatal` and `**Severity:** Significant` lines",
        "mechanical finding-identity rule (round-7 S5)": "1-based ordinal of the finding's `**Severity:** Fatal`/`**Severity:** Significant` line",
        "mechanical round_n_plus_1_finding_id schema comment (round-7 S5)": "the finding's 1-based ordinal among **Severity:** Fatal/Significant lines",
    }
    for label, needle in prompt_mutations.items():
        broken = _GOOD_PROMPT_FIXTURE.replace(needle, "")
        if not check_prompt(broken):
            errs.append(f"selftest: removing '{label}' did NOT trip the PROMPT checker (no-op grep)")

    # Positive-control regression (round-5 M4): reintroducing the inaccurate
    # anti-anchoring claim must trip the checker.
    bad_anti_anchoring = _GOOD_PROMPT_FIXTURE + (
        "\nYou do NOT receive prior rounds' findings beyond what "
        "`round-(N+1)-persistence.md` already summarizes.\n"
    )
    if not check_prompt(bad_anti_anchoring):
        errs.append(
            "selftest: reintroducing the inaccurate anti-anchoring self-description did NOT "
            "trip the PROMPT checker (round-5 M4)"
        )

    if errs:
        print("SELFTEST FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — selftest: good fixtures clean; all pinned-phrase deletions and the SUSTAINED_FAN_OUT/sustained_fan_out reintroductions detected.")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    errs: list[str] = []
    skill_text = _read(SKILL, errs)
    if skill_text is not None:
        errs += check_skill(skill_text)
    prompt_text = _read(PROMPT, errs)
    if prompt_text is not None:
        errs += check_prompt(prompt_text)
    persistence_text = _read(PERSISTENCE, errs)
    if persistence_text is not None:
        errs += check_persistence(persistence_text)
    if errs:
        print("QG FAN-OUT TELEMETRY DRIFT DETECTED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(
        "OK — fix-generated-defect tracking (#546): SUSTAINED_FAN_OUT absent from the "
        "closed marker enum, FanOutRounds/FanOutCheckCount/FanOutErrorCount + both "
        "invariants present, persistence_status CONTRACT block complete (incl. "
        "verifier-error), excluded_as_persistent all-sections-and-severity-scoped and "
        "decoupled from the #366 count, completeness audit uses the orchestrator's own "
        "count, fan-out-streak-note is not a Minor channel, dispatch-ordering documented "
        "with orchestrator-side fail-open, the code exclusion holds at its recovery-trigger "
        "restatement, the three-value fix-generated-count encoding survives compaction, "
        "oversized-diff handling is contradiction-free with its own counter, ambiguous_count "
        "has a durable channel, the fix-generated-defect-prompt.md JSON schema (incl. "
        "ambiguous/ambiguous_count) is aligned, every fail-open object carries a structured "
        "error_cause with a durable fix-generated-error-cause channel, recovery cannot "
        "re-dispatch on a persistence-unknown round, the fix-generated-count/"
        "fix-generated-ambiguous-count encodings are point-anchored, fan_out_ambiguous_count "
        "sums only over integer rounds, and the completeness audit's comparand is a stated "
        "mechanical counting rule. Round 7: the n/a/error value domains are object-existence "
        "based (not 'does the checker fire'), FanOutErrorCount/fan_out_error_count/INV-546-9 "
        "count interception rounds like their FanOutCheckCount sibling, the Anti-Rat trigger "
        "row and INV-546-1 carry/consolidate the persistence_status precondition, "
        "fan_out_oversized_count is interpretable against a recorded diff-size channel with a "
        "deterministic interception order, finding identity between the two checkers is "
        "mechanical (ordinal position), and fix-generated-exclusion-basis/"
        "fan_out_not_triggered_count let the base rate be stratified by exclusion availability. "
        "Round 8: persistence-checker-prompt.md is now a third path-pinned target and actually "
        "carries the mechanical ordinal-position finding-identity rule SKILL.md claims it uses "
        "(F1), fix-generated-diff-bytes now has a durable fan_out_diff_bytes_max/_total "
        "convergence-log sink (S2), and the S1 full pin audit re-anchored every bare, "
        "mutation-verified-maskable check found this round (marker fields/invariants/estimator, "
        "the completeness-audit round-status clause, the fix-generated-count/-ambiguous-count/"
        "-diff-bytes/-exclusion-basis/-error-cause Round History field bullets, the "
        "oversized-diff error_cause clause, the interception-order sentence, and the prompt's "
        "population-scope sentence). Round 9: fix-generated-diff-bytes/fan_out_diff_bytes_max/"
        "_total are typed as orchestrator-estimated (S0); fix-generated-exclusion-basis's n/a "
        "clause is exhaustive over checker-error rounds and fan_out_not_triggered_count's gloss "
        "and invariant guard against a negative derived fired-clean stratum (S1); the recovery-"
        "trigger and Anti-Rat row both carry the oversized-diff interception alongside "
        "persistence_status (S2); INV-546-6 names the third path-pinned file and the five "
        "convergence keys it had gone stale for, and INV-546-13 records the persistence-"
        "checker's ordinal-identity rule (S3); fan_out_rounds_not_triggered makes the "
        "not-triggered stratum's numerator recoverable after cleanup (S4); several full-"
        "sentence pins are reshaped to contract tokens per CHECKER_CONVENTIONS.md, and (z2)'s "
        "count>=5 threshold is replaced by four per-site anchored checks (S5); the "
        "fan_out_ambiguous_count/fan_out_diff_bytes sourcing docs assert the substantive "
        "denominator claim instead of the vacuous sum-bias rationale (S6); and the Write-"
        "ordering paragraph now names all three round-(N+1)-score.md write times (S7)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
