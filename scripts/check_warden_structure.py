#!/usr/bin/env python3
"""Structural check for the warden skill scaffold (#464).

Invocation (from repo root):
    python3 scripts/check_warden_structure.py            # gate the real file
    python3 scripts/check_warden_structure.py --selftest # in-memory logic test

Asserts `skills/warden/SKILL.md` exists and carries the load-bearing structural
clauses: the `name: warden` frontmatter, a `description:` line, both canonical
link comments (dispatch + return conventions, per CLAUDE.md "link, never copy"),
a citation of the severity-verdict-contract, the reviewer-set section's
load-bearing clauses (the five-reviewer table, the disjunction-of-native-gates
statement, the sectioned-per-reviewer clause, the `reviewer-set` parameter, and
inquisitor's `unconditional` full-set coverage), and — as of Task 3 — the
Fix-behavior section's clauses: the per-leg residual commit primitive
(`git add -A && git commit`), the fully-empty clean-tree precondition
(`git status --porcelain` + "fully empty"/"no untracked"), the non-`fix:` subject
mandate (`chore(warden):` + a non-fix note), and the dirty-tree REFUSE clause
(`commit, stash, or clean untracked files`) — and, as of Task 4, the Ordering
(F1) / read-only freeze-guard clauses: the `SHA_pre_redteam` capture, the
terminating leg's `native report-only mode`, its `does not pass `--fix`` clause,
the delve-pinned-before-the-red-team-leg ordering, and the empty-range
benign-pass clause. Also asserts the ABSENCE of several cross-scale + fix-path
footguns: a cross-scale normalization construct (I-W1), `git commit -a` (R11),
`git stash` in COMMAND form (R12) — matched as the command (`git stash`, mutating
forms), NOT the bare word "stash" (warden's own REFUSE clause contains "stash")
and NOT the read-only `git stash create` temper snapshot — and `temper-reviewer`
in COMMAND/SKILL-REFERENCE form (R13, Task 4): the terminating freeze-guard is
plain delve, NOT a `temper-reviewer` re-run, so a `temper-reviewer.md` dispatch
trips it while a bare-word prose mention ("NOT a `temper-reviewer` re-run") does
not. Exits 0 when every clause is present and no
forbidden construct is found, 1 with a per-clause diff summary otherwise.
Task 6 adds the marker-ownership (I-W7) / Option-C no-emit / I-W8 / double-run
(M4) required clauses, plus two scoped command-form negatives: the no-emit guard
(an imperative `emit`/`ledger_append` call — matched over warden's emission
surface, SKILL.md PLUS `scripts/check_warden_*.py`, excluding `skills/warden/evals/`
by construction — while a descriptive `runs.jsonl`/emit prose token does NOT trip)
and the T-W13 siege-suppression guard (`skip_siege:`/`force_siege:`/`--skip-siege`
in param/flag form, not a bare substring).
Task 7 adds the Routing-boundary (S7) clauses — the phrase-ownership table header
and the "warden does **not** claim temper's phrases" statement (I-W3) — plus the
I-W3 DESCRIPTION-scoped negative: warden's frontmatter `description` must NOT
contain temper/quality-gate/delve owned trigger phrases ("is this ready to ship",
"red-team this", "find bugs in this diff", "instance-bug sweep"). That negative is
scoped to the `description:` value ONLY — those phrases legitimately appear in the
SKILL.md BODY (the phrase-ownership table lists them as other skills' triggers), so
a whole-file grep would false-trip; `_extract_description` isolates the value.
Task 17 adds the Minor-(b) M-c scope-gap disclosure check (`check_mc_scope_gap`)
— a dedicated PROXIMITY assertion (not a `REQUIRED_SUBSTRINGS`/`REQUIRED_ANY`
entry, since `outside` alone is too generic): the three anchors `inquisitor`,
`self-commit`, `outside` must CO-OCCUR within one `_MC_SCOPE_WINDOW`-char passage,
so warden discloses that the M-c non-`fix:` mandate binds only warden-owned commits
and that inquisitor/siege self-commit stays outside it (its own dedicated BAD
selftest case removes the `outside` anchor and confirms the check trips).
Stdlib only, no argparse.

Style mirrors `scripts/check_canonical_drift.py`: ROOT-from-`__file__`, error
accumulation, `sys.exit(main())`.

EXTENSION POINT (Phase-A tasks 4-8): add the substring a later task authors into
warden's SKILL.md to `REQUIRED_SUBSTRINGS` (label -> literal substring), or to
`REQUIRED_ANY` (label -> alternatives, at least one must appear) for an OR clause.
The frontmatter `name:`/`description:` guards live in `check_frontmatter()`; the
I-W1 normalization guard lives in `check_forbidden()`; the fix-path command
negatives (R11 `git commit -a`, R12 `git stash`, R13 `temper-reviewer`
reference-form) live in `check_negatives()`; the I-W3 owned-phrase negative
(description-scoped) lives in `check_description_negatives()`. The
`--selftest` GOOD/BAD samples are self-contained and must stay in sync — the
per-clause RED cases are generated automatically from `REQUIRED_SUBSTRINGS` and
`REQUIRED_ANY`, so a new required clause gets its own RED case for free; add a
dedicated BAD case for any new *negative*.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/warden/SKILL.md"
TEMPER_SKILL = ROOT / "skills/temper/SKILL.md"

# label -> literal substring that MUST appear somewhere in SKILL.md. Later
# Phase-A tasks EXTEND this dict; the selftest generates a RED case per entry.
REQUIRED_SUBSTRINGS: dict[str, str] = {
    "dispatch canonical link": "<!-- CANONICAL: shared/dispatch-convention.md -->",
    "return canonical link": "<!-- CANONICAL: shared/return-convention.md -->",
    "severity-verdict-contract citation": "severity-verdict-contract.md",
    # Task 2 — reviewer set (native scales, no normalization), design L94-123.
    "disjunction-of-native-gates statement": "disjunction of native gates",
    "sectioned-per-reviewer clause (I-W2)": "sectioned per reviewer",
    "reviewer table header": "| Reviewer |",
    "reviewer leg: temper": "temper",
    "reviewer leg: delve": "delve",
    "reviewer leg: red-team": "red-team",
    "reviewer leg: siege": "siege",
    "reviewer leg: inquisitor": "inquisitor",
    "reviewer-set parameter (full | standalone)": "reviewer-set: full | standalone",
    "inquisitor unconditional in full set": "unconditional",
    # Task (warden risk-tier) — standalone inquisitor risk-aware predicate, #466.
    # Each pin proves a predicate CLAUSE EXISTS in SKILL.md (structural teeth only;
    # the predicate is never executed in CI — see design AC3 / §Live-validation).
    "standalone inquisitor retained reach clause":
        ">1 changed file OR >1 top-level module",
    "standalone inquisitor interface escalator": "INTERFACE/API/SCHEMA glob set",
    "standalone inquisitor dependency escalator": "DEPENDENCY/lockfile glob set",
    "standalone inquisitor binary fail-safe": "binary or otherwise unparseable path",
    "standalone inquisitor pure-doc skip": "EVERY changed path is a PURE-DOC file",
    # Structural teeth for the previously-unpinned INV-P invariants block (design
    # L89-104): anchors that the invariants block EXISTS, not just the clause literals.
    # (Monotonicity/residual-risk paragraphs carry no pinned literal — inspection-only.)
    "standalone inquisitor predicate INV-P block": "INV-P8",
    # Task 3 — fix behavior (Universal per-leg residual commit + clean-tree
    # precondition), design L125-278.
    "per-leg residual commit primitive (M-c)": "git add -A && git commit",
    "clean-tree precondition command": "git status --porcelain",
    "non-`fix:` subject label (M-c)": "chore(warden):",
    "dirty-tree REFUSE clause": "commit, stash, or clean untracked files",
    # Task 4 — Ordering (F1) + read-only freeze-guard, design L280-422.
    "freeze-guard SHA capture (F1 step 3 / I-W6)": "SHA_pre_redteam",
    "terminating leg native report-only mode (F1 step 4 / I-W6)":
        "native report-only mode",
    "terminating leg does not pass --fix (F1 step 4 / I-W6)":
        "does not pass `--fix`",
    # Task 5 — Gate + enforcement (fail-closed escalation / dead-leg / M5),
    # design L424-449 + failure-modes L954-963.
    "fail-closed keyword (Gate)": "fail-closed",
    "BLOCKED verdict keyword (Gate)": "BLOCKED",
    "escalation folds into BLOCKED (Gate)": "an escalation folds into `BLOCKED`",
    "dead-leg fail-closed BLOCK (unrun gate is not a pass)":
        "an unrun gate is not a pass",
    "condition-skipped is a normal PASS input, not a failure (M5)":
        "normal PASS input, not a failure",
    # Task 6 — marker ownership (I-W7) + Option-C no-emit ledger (I-W8) +
    # double-run marker, design L511-598 + L687-702.
    "marker ownership: warden's own run-id (I-W7)": "warden's own run-id",
    "I-W8 no-calibration-emit clause": "no calibration",
    "M-5 degree-not-kind attribution disclosure": "degree, not kind",
    "double-run pre-run-base marker (M4)": "pre-run base",
    # Task 7 — Routing boundary (S7) + phrase-ownership / I-W3, design L638-671.
    "phrase-ownership table header (S7)": "| Phrase / intent | Owner | Why |",
    "warden does NOT claim temper's phrases (I-W3)": "does **not** claim temper's",
    # Task 8 — API surface + invariants list + test obligations, design L712-1097.
    # The `--effort` flag (M-o4) must be documented so it is not silently dropped;
    # warden has NO `--fix` flag (it fixes-then-certifies); a sub-skill dispatch
    # omitting `reviewer-set` fail-safe-defaults to `full` (I-W9). The I-Wx / T-Wx
    # literals are matched in COLON-list form (`I-W1:` / `T-W1:`) so each is a
    # precise assertion: bare `T-W1` is a substring of `T-W10`..`T-W14`, which would
    # make the individual check vacuous (any higher token would satisfy it) and its
    # auto-RED case mangle the whole list. `T-W1:` is NOT a substring of `T-W10:`,
    # so the colon disambiguates. T-W10 is RETIRED (design L913-916) — NOT required
    # (only its `retired` note is), so no RED case demands it back.
    "M-o4: --effort flag (API surface)": "--effort low|medium|high",
    "no `--fix` flag (API surface)": "no `--fix` flag",
    "reviewer-set fail-safe default → full (I-W9)": "defaults to `full`",
    "Invariants section header": "## Invariants",
    "T-W10 retirement note": "retired",
    "invariant I-W1": "I-W1:",
    "invariant I-W2": "I-W2:",
    "invariant I-W3": "I-W3:",
    "invariant I-W4": "I-W4:",
    "invariant I-W5": "I-W5:",
    "invariant I-W6": "I-W6:",
    "invariant I-W7": "I-W7:",
    "invariant I-W8": "I-W8:",
    "invariant I-W9": "I-W9:",
    "test obligation T-W1": "T-W1:",
    "test obligation T-W2": "T-W2:",
    "test obligation T-W3": "T-W3:",
    "test obligation T-W4": "T-W4:",
    "test obligation T-W5": "T-W5:",
    "test obligation T-W6": "T-W6:",
    "test obligation T-W7": "T-W7:",
    "test obligation T-W8": "T-W8:",
    "test obligation T-W9": "T-W9:",
    "test obligation T-W11": "T-W11:",
    "test obligation T-W12": "T-W12:",
    "test obligation T-W13": "T-W13:",
    "test obligation T-W14": "T-W14:",
}

# I-W3 — the owned trigger phrases warden's `description` must NOT carry. Each
# belongs to a single-reviewer skill (the discriminator is whole-set gate vs
# single reviewer); listing them in warden's description would recreate the exact
# routing collision the phrase-ownership table exists to prevent.
_OWNED_TRIGGER_PHRASES: tuple[str, ...] = (
    "is this ready to ship",   # temper (single fresh-eyes merge-verdict)
    "red-team this",           # quality-gate (red-team of a typed artifact)
    "find bugs in this diff",  # delve (report-only bug finder)
    "instance-bug sweep",      # delve
)

# I-W3 (temper side, Task 9) — the routing collision is resolved in BOTH
# descriptions: warden must not claim temper's phrases (above), AND temper cedes
# the push-gate phrasing that now routes to warden. So temper's `description`
# must NOT carry a push-gate cue ("before merging" / "before I push" / "before
# pushing") — those hand the utterance to warden — while it MUST keep its
# single-reviewer merge-verdict trigger ("is this ready to ship"). Checked on the
# lowercased `description:` value (via `_extract_description`), so casing in the
# real file doesn't matter.
_TEMPER_BANNED_PUSH_PHRASES: tuple[str, ...] = (
    "before merging", "before i push", "before pushing")
_TEMPER_REQUIRED_PHRASE = "is this ready to ship"

# label -> alternatives; at least ONE must appear (an OR clause). The dispatch
# frames these as disjunctions, so requiring both alternatives would be stricter
# than the spec. A RED case is auto-generated per label (removes every
# alternative, asserts the label is flagged).
REQUIRED_ANY: dict[str, tuple[str, ...]] = {
    # clean-tree precondition is "fully empty" (no tracked mods AND no untracked).
    "fully-empty clean-tree wording": ("fully empty", "no untracked"),
    # M-c non-`fix:` mandate note (backticked or bare).
    "non-fix subject note (M-c)": ("non-`fix:`", "non-fix"),
    # Task 4 — delve's `--fix` leg is pinned among the non-terminal fixers,
    # BEFORE the red-team leg (design L334-336). Either the design's literal
    # "before the red-team leg" phrasing or the shorthand satisfies it.
    "delve pinned before the red-team leg (F1 step 1)":
        ("before the red-team leg", "delve pinned before"),
    # Task 4 — the terminating freeze-guard reviews an EMPTY range benignly
    # (no "non-empty range" requirement — design L382-383). Each alternative
    # carries both the `empty` anchor AND the benign-pass wording.
    "empty-range benign-pass clause (F1 step 4 / I-W6)":
        ("empty range and benignly passes", 'no "non-empty range" requirement'),
}

# I-W1 negative guard. Matches a real cross-scale normalization construct — a
# prose "convert <X> to <Y> scale" mapping — within a single sentence
# (`[^.\n]*` never crosses a `.` or newline). Deliberately NOT a table-shaped
# arrow-map detector: that would false-positive on warden's own legitimate
# reviewer table (full of `Critical`/`High`/`Important` cells). Negation prose
# ("no cross-scale normalization", "conversion is forbidden", "converted into
# another's") does NOT trip it — `convert\w*` never matches "conversion"
# (7th char is `s`, not `t`) and `\bto\b` never matches inside "into".
_FORBIDDEN_NORMALIZATION = re.compile(
    r"convert\w*\b[^.\n]*\bto\b[^.\n]*\bscale\b", re.IGNORECASE)

# R12 negative guard — `git stash` in COMMAND form. THE CRUX (M-o2): warden's own
# required REFUSE clause literally contains the word "stash" ("commit, stash, or
# clean untracked files"), so a bare-word `stash` grep would self-contradict
# against warden's own required clause and could never go green. So match the
# COMMAND (the `git ` prefix), never the bare word. The negative lookahead
# excludes the ONE allowed mention: `git stash create` — the read-only snapshot
# temper uses that leaves HEAD/index/tree untouched (design L133-134, authored
# verbatim). Every mutating form (`git stash` bare / push / save / pop) trips it;
# `git stash create` and the REFUSE-clause bare "stash" do not.
_FORBIDDEN_GIT_STASH = re.compile(r"\bgit\s+stash\b(?!\s+create\b)")

# R13 negative guard — `temper-reviewer` in COMMAND/SKILL-REFERENCE form. The
# terminating freeze-guard (Ordering step 4) is deliberately **plain delve,
# report-only** — NOT a `temper-reviewer` re-run. But warden's own prose must be
# able to SAY that ("the freeze-guard is plain delve, NOT a `temper-reviewer`
# re-run") without tripping its own guard — the same bare-word/command-form split
# as R12 (M-o2). In THIS codebase `temper-reviewer` is only ever *dispatched* by
# its template-file path — `temper-reviewer.md` (temper/SKILL.md:212, finish/
# SKILL.md:60) or a `temper-reviewer/` dir — never by a `subagent_type` (it is a
# prompt template run through the harness adapter, not a registered agent). So the
# reference/dispatch form is exactly `temper-reviewer.md` / `temper-reviewer/`;
# match that, never the bare word. Backticked prose (`` `temper-reviewer` ``,
# followed by a backtick + " re-run", not `.md`) does NOT trip.
_FORBIDDEN_TEMPER_REVIEWER = re.compile(r"\btemper-reviewer(?:\.md\b|/)")

# S4 / Option-C no-emit guard (I-W8) — warden emits NOTHING to `runs.jsonl`. This
# matches an IMPERATIVE ledger emit *call* — an `emit`/`ledger_append` invocation
# with an opening paren — and NEVER a descriptive prose token. Same command-form
# split as the R12 `git stash` crux: match the call, not the bare word. A
# descriptive mention ("each leg self-emits to `runs.jsonl`; warden emits none")
# does NOT trip — "self-emits"/"emits none" have no `(` after "emit". Because the
# emission-surface scan (`check_emission_surface_files`) greps this checker's OWN
# source too, no docstring/error/sample below may contain a contiguous
# emit-then-paren token (the imperative selftest sample is built by concatenation
# for exactly this reason).
_FORBIDDEN_LEDGER_EMIT = re.compile(r"\b(?:emit|ledger_append)\s*\(")

# T-W13 no-siege-suppression guard — warden's QG-leg dispatch must NOT pass the
# real `quality-gate/SKILL.md:187-188` siege-suppression params, which would
# silently break the LOCKED double-siege decision (I-W4 / design L777-781). Match
# the token in dispatch-PARAM / FLAG form only — `skip_siege:` / `force_siege:` as
# a dispatch key, or `--skip-siege` as a flag — NOT a bare substring, so
# descriptive prose ("warden does NOT pass `skip_siege` to the QG leg", backtick
# form, no `:`) does not false-trip. Parity with the R12 command-form split.
_FORBIDDEN_SIEGE_SUPPRESS = re.compile(
    r"(?:\b(?:skip_siege|force_siege)\s*:|--skip-siege\b)")

# Minor (b) — M-c SCOPE-GAP disclosure. The M-c non-`fix:` mandate only binds
# warden-OWNED commits; inquisitor/siege self-commit under their own subjects
# (`inquisitor/SKILL.md:163` is `fix:`-style), which warden does not control, so
# that self-commit is OUTSIDE the mitigation and can still hit reconcile's
# `fix`/`hotfix` candidate-walk collision — disclosed and accepted. The check keys
# on the three anchors `inquisitor`, `self-commit`, `outside` CO-OCCURRING within
# one proximity window (a single coherent disclosure passage), not three scattered
# mentions: `outside` alone is too generic to require as a bare substring, and the
# file already carries all three anchors far apart (`:188` "outside the original
# push scope", `:208` "inquisitor/siege self-commit") — the ~1460-char gap between
# them is why the window is tight enough that only a deliberate co-located clause
# satisfies it. Anchored on the least-generic literal (`self-commit`).
_MC_SCOPE_ANCHORS: tuple[str, ...] = ("inquisitor", "self-commit", "outside")
_MC_SCOPE_WINDOW = 600


def check_frontmatter(text: str) -> list[str]:
    """The `name: warden` scalar and a `description:` line must be present in
    the leading `---`-fenced YAML block."""
    errs: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ["missing leading `---` frontmatter fence"]
    fm: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm.append(line)
    else:
        return ["frontmatter block is not closed by a `---` fence"]
    if not any(ln.strip() == "name: warden" for ln in fm):
        errs.append("missing frontmatter `name: warden`")
    if not any(ln.lstrip().startswith("description:") for ln in fm):
        errs.append("missing frontmatter `description:` line")
    return errs


def _extract_description(text: str) -> str:
    """Return the frontmatter `description:` value (lowercased), or '' if there
    is no frontmatter/description. warden's `description` is the last key in the
    block, so everything from after `description:` to the closing `---` fence is
    the value — this isolates it from the SKILL.md body, which legitimately
    contains the owned phrases in the phrase-ownership table."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    fm_end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return ""
    fm = "\n".join(lines[1:fm_end])
    idx = fm.find("description:")
    if idx == -1:
        return ""
    return fm[idx + len("description:"):].lower()


def check_description_negatives(text: str) -> list[str]:
    """I-W3: warden's frontmatter `description` must NOT contain a temper/
    quality-gate/delve owned trigger phrase — the routing discriminator is
    whole-set gate (warden) vs single reviewer (temper/quality-gate/delve).
    Scoped to the `description:` value ONLY (via `_extract_description`): the
    same phrases appear in the SKILL.md BODY (the phrase-ownership table names
    them as the other skills' triggers), so a whole-file grep would false-trip."""
    desc = _extract_description(text)
    errs: list[str] = []
    for phrase in _OWNED_TRIGGER_PHRASES:
        if phrase in desc:
            errs.append(f"forbidden owned trigger phrase in warden description "
                        f"(I-W3): {phrase!r} — that intent belongs to a single "
                        "reviewer (temper/quality-gate/delve), not warden's "
                        "whole-set gate")
    return errs


def check_temper_description(desc: str) -> list[str]:
    """I-W3 (temper side): temper's frontmatter `description` must NOT carry a
    push-gate cue (ceded to warden by this build — "before merging" / "before I
    push" / "before pushing") and MUST keep its single-reviewer merge-verdict
    trigger ("is this ready to ship"). `desc` is the lowercased `description:`
    value (via `_extract_description`). Pure, so `--selftest` can exercise it."""
    errs: list[str] = []
    for phrase in _TEMPER_BANNED_PUSH_PHRASES:
        if phrase in desc:
            errs.append(f"push-gate phrase still in temper description "
                        f"(I-W3): {phrase!r} — ceded to warden by #464; temper's "
                        "description keeps single-reviewer phrasing only")
    if _TEMPER_REQUIRED_PHRASE not in desc:
        errs.append(f"temper description dropped its single-reviewer trigger "
                    f"(I-W3): missing {_TEMPER_REQUIRED_PHRASE!r} — temper keeps "
                    "the fresh-eyes merge-verdict cue after ceding the push-gate")
    return errs


def check_temper_description_file() -> list[str]:
    """Read the real `skills/temper/SKILL.md` and run the I-W3 temper-side guard
    on its frontmatter `description` value. A filesystem check (like
    `check_emission_surface_files`), so it lives in `main()`, not `--selftest`."""
    if not TEMPER_SKILL.is_file():
        return [f"{TEMPER_SKILL.relative_to(ROOT)} does not exist"]
    desc = _extract_description(TEMPER_SKILL.read_text(encoding="utf-8"))
    return check_temper_description(desc)


def check_forbidden(text: str) -> list[str]:
    """I-W1: warden must carry NO cross-scale normalization construct. Returns
    an error if a 'convert <X> to <Y> scale' mapping is present; negation prose
    must NOT trip it (see `_FORBIDDEN_NORMALIZATION`)."""
    m = _FORBIDDEN_NORMALIZATION.search(text)
    if m:
        return [f"forbidden cross-scale normalization construct present (I-W1): "
                f"{m.group(0)!r}"]
    return []


def check_negatives(text: str) -> list[str]:
    """Fix-path command negatives (regression guards from the design's R11/R12
    fixes). R11: no `git commit -a` (would commit only tracked edits, dropping a
    leg's new/untracked files — the design mandates `git add -A && git commit`).
    R12: no `git stash` in COMMAND form (warden has no working-tree save/restore
    machinery; `git stash create`, temper's read-only snapshot, is exempt — see
    `_FORBIDDEN_GIT_STASH`). R13: no `temper-reviewer` in COMMAND/SKILL-REFERENCE
    form (`temper-reviewer.md` / `temper-reviewer/`) — the terminating
    freeze-guard is plain delve, not a `temper-reviewer` re-run; a bare prose
    mention of `temper-reviewer` saying exactly that must NOT trip it — see
    `_FORBIDDEN_TEMPER_REVIEWER`."""
    errs: list[str] = []
    if "git commit -a" in text:
        errs.append("forbidden `git commit -a` present (R11): warden must use "
                    "`git add -A && git commit` so a leg's new/untracked files "
                    "land in the frozen HEAD")
    m = _FORBIDDEN_GIT_STASH.search(text)
    if m:
        errs.append(f"forbidden `git stash` command present (R12): {m.group(0)!r} "
                    "— warden has no working-tree save/restore machinery")
    m = _FORBIDDEN_TEMPER_REVIEWER.search(text)
    if m:
        errs.append(f"forbidden `temper-reviewer` dispatch/reference present "
                    f"(R13): {m.group(0)!r} — the terminating freeze-guard is "
                    "plain delve report-only, not a temper-reviewer re-run")
    m = _FORBIDDEN_LEDGER_EMIT.search(text)
    if m:
        errs.append(f"forbidden imperative ledger emit present "
                    f"(no-emit / Option C / I-W8): {m.group(0)!r} — warden emits "
                    "NOTHING to runs.jsonl; each leg self-emits its own entry")
    m = _FORBIDDEN_SIEGE_SUPPRESS.search(text)
    if m:
        errs.append(f"forbidden siege-suppression param present (T-W13): "
                    f"{m.group(0)!r} — warden must not pass skip_siege/force_siege "
                    "to the QG red-team leg (breaks the LOCKED double-siege, I-W4)")
    return errs


def check_mc_scope_gap(text: str) -> list[str]:
    """Minor (b): warden must DISCLOSE that the M-c non-`fix:` mandate binds only
    warden-OWNED commits, and that inquisitor/siege `self-commit` is `outside`
    that mitigation (so it can still hit reconcile's `fix`/`hotfix` candidate-walk
    collision). The three anchors in `_MC_SCOPE_ANCHORS` must CO-OCCUR within one
    `_MC_SCOPE_WINDOW`-char passage — a single coherent clause, not three
    scattered mentions. Pure (takes the text) so `--selftest` can exercise it."""
    lowered = text.lower()
    start = 0
    while True:
        idx = lowered.find("self-commit", start)
        if idx == -1:
            break
        window = lowered[max(0, idx - _MC_SCOPE_WINDOW): idx + _MC_SCOPE_WINDOW]
        if all(anchor in window for anchor in _MC_SCOPE_ANCHORS):
            return []
        start = idx + len("self-commit")
    return ["missing M-c scope-gap disclosure (Minor b): warden must state that "
            "the non-`fix:` mandate binds only warden-owned commits and that "
            "`inquisitor`/siege `self-commit` is `outside` that mitigation — the "
            f"three anchors {list(_MC_SCOPE_ANCHORS)} must co-occur in one passage"]


def check_emission_surface_files() -> list[str]:
    """Option-C no-emit / I-W8 also greps warden's shipped SCRIPTS —
    `scripts/check_warden_*.py` — for an imperative ledger emit, on top of
    `skills/warden/SKILL.md` (already scanned by `check_negatives` via
    `check_text`). Together those two are warden's whole emission surface. It does
    NOT grep the entire `skills/warden/` tree: `skills/warden/evals/` (authored by
    Task 10) legitimately MENTIONS `runs.jsonl` in fixtures/docstrings when
    describing the per-leg self-emit, and is excluded by construction — this scan
    reads only SKILL.md (via `check_text`) + `scripts/check_warden_*.py` here."""
    errs: list[str] = []
    for path in sorted((ROOT / "scripts").glob("check_warden_*.py")):
        m = _FORBIDDEN_LEDGER_EMIT.search(path.read_text(encoding="utf-8"))
        if m:
            errs.append(f"forbidden imperative ledger emit in scripts/{path.name} "
                        f"(no-emit / Option C / I-W8): {m.group(0)!r}")
    return errs


def check_text(text: str) -> list[str]:
    """Run every structural assertion against SKILL.md content. Pure (takes the
    text) so `--selftest` can exercise it on in-memory samples."""
    errs = check_frontmatter(text)
    for label, sub in REQUIRED_SUBSTRINGS.items():
        if sub not in text:
            errs.append(f"missing {label}: `{sub}`")
    for label, alts in REQUIRED_ANY.items():
        if not any(alt in text for alt in alts):
            errs.append(f"missing {label}: none of {list(alts)} present")
    errs.extend(check_forbidden(text))
    errs.extend(check_negatives(text))
    errs.extend(check_description_negatives(text))
    errs.extend(check_mc_scope_gap(text))
    return errs


# --------------------------------------------------------------------------
# selftest — self-contained GOOD/BAD samples (do NOT read the real file)
# --------------------------------------------------------------------------
_GOOD_SAMPLE = """\
---
name: warden
description: Consolidated pre-push review gate — temper, delve, red-team, siege, inquisitor.
---

# Warden

<!-- CANONICAL: shared/dispatch-convention.md -->
<!-- CANONICAL: shared/return-convention.md -->

## Overview

warden runs each reviewer on its own severity scale — there is no cross-scale
normalization (see `severity-verdict-contract.md`).
The gate is a disjunction of native gates.
The combined report is sectioned per reviewer.
No leg's severity is converted into another's.

## Reviewer set (native scales, no normalization)

The "Runs" column is split by reviewer-set: full | standalone.

| Reviewer | Runs (`full`) | Runs (`standalone`) | Gate | Notes |
|---|---|---|---|---|
| temper | always | always | T non-empty | the merge-verdict loop |
| delve | always | always | any kept finding | report-only, warden owns the fix |
| red-team | always | always | quality-gate ≠ PASS | via quality-gate |
| siege | conditional | conditional | Critical>0 | six-agent security audit |
| inquisitor | always (unconditional) | conditional | any FAIL | stays unconditional in full |

## Standalone inquisitor-inclusion predicate

Evaluated on the entry diff, in order (escalators dominate; strictly additive):
1. any changed path matches the INTERFACE/API/SCHEMA glob set, or the
   DEPENDENCY/lockfile glob set, or the diff has a binary or otherwise unparseable path
   → run inquisitor (fail-safe: unknown → run).
2. else if EVERY changed path is a PURE-DOC file (`.md`/`.rst`/`.adoc` by extension,
   any depth; no `docs/**` catch-all) → skip inquisitor.
3. else if >1 changed file OR >1 top-level module touched → run inquisitor.
4. else → skip inquisitor.

Predicate invariants: INV-P1..INV-P10 (INV-P8 = pure-doc bounded; escalator
over-match disclosed in residual-risk).

## Fix behavior

temper edits the working tree but never commits. The `git stash create` temper
uses in that mode only snapshots the tree; it is not how the fix is applied. So
temper's edits sit in the working tree, uncommitted, for warden to commit.

Universal per-leg residual commit (I-W6): after each fixer leg, warden commits
that leg's residual with `git add -A && git commit -m '<subject>'` and a
non-`fix:` subject (`chore(warden): temper fixes <run-id>`, per M-c).

M-c scope gap: the non-`fix:` mandate binds only warden-owned commits. inquisitor
and siege self-commit under their own subjects, which warden does not control, so
an inquisitor self-commit stays **outside** this mitigation and can still hit
reconcile's fix/hotfix candidate walk — disclosed and accepted.

Working-tree-clean precondition: warden asserts `git status --porcelain` is
fully empty — no tracked modifications and no untracked files. Standalone warden
on a dirty tree REFUSES: commit, stash, or clean untracked files, then re-run.

## Ordering (F1)

1. Non-terminal fixers first, with the delve `--fix` leg pinned among them,
   before the red-team leg (step 3).
3. Capture `SHA_pre_redteam = HEAD`, run the red-team leg, commit its residual.
4. Read-only instance-bug freeze-guard: run plain delve in its
   native report-only mode over `SHA_pre_redteam..HEAD`. If the range is empty the
   terminating delve reviews an empty range and benignly passes — there is no
   "non-empty range" requirement. warden does not pass `--fix` on this leg, so
   it writes nothing into the frozen HEAD. This is plain delve, not a
   `temper-reviewer` re-run.

## Verdict marker ownership (F2)

warden invokes the quality-gate red-team leg with warden's own run-id as the
PipelineID, not build's, and writes the one build-PipelineID aggregate marker (I-W7).

## Calibration-ledger entries

warden emits no calibration row to `runs.jsonl`; each leg self-emits its native
entry (I-W8). The change from build is one of degree, not kind (M-5). warden does
not pass `skip_siege`/`force_siege` to the QG leg.

## Double-run avoidance

warden writes a coverage marker keyed by the pre-run base SHA + reviewer-set (M4);
build's finish-skip is the primary guard, the marker a backstop.

## Gate + enforcement

warden's verdict is `BLOCKED` if any run reviewer's native gate trips. Escalation
verdicts are fail-closed (BLOCKED, never PASS): an escalation folds into `BLOCKED`
and halts the pipeline. A reviewer sub-dispatch that dies is fail-closed too —
warden surfaces the failed leg and returns `BLOCKED` (an unrun gate is not a pass),
never silently drops it. A correctly condition-skipped leg is a
normal PASS input, not a failure (M5).

## Routing boundary

The discriminator is whole-set gate (warden) vs single reviewer.

| Phrase / intent | Owner | Why |
|---|---|---|
| "gate this before I push", "warden" | warden | whole reviewer set + one verdict |
| "is this ready to ship", "review my changes" (bare) | temper | single fresh-eyes merge-verdict |
| "red-team this" | quality-gate | red-team of a typed artifact |
| "find bugs in this diff", "instance-bug sweep" | delve | report-only bug finder |

warden deliberately does **not** claim temper's "is this ready to ship" phrases (I-W3).

## API Surface

`/warden [scope] [--effort low|medium|high]` — warden fixes-then-certifies, so there is no `--fix` flag. A sub-skill dispatch that omits `reviewer-set` defaults to `full`.

## Invariants

**Checkable by inspection:**
- I-W1: warden never converts one reviewer's severity into another's scale.
- I-W2: one section per run reviewer; no merged ranking.
- I-W3: description guard (see Routing boundary).
- I-W4: red-team via quality-gate; siege twice (see Calibration-ledger entries).
- I-W5: exactly one warden call site each in build/finish.
- I-W6: ordering + clean-tree inductive base (see Ordering).
- I-W7: single build-tagged marker (see Verdict marker ownership).
- I-W8: legs self-emit; warden emits no `code` row.
- I-W9: a sub-skill dispatch that omits `reviewer-set` defaults to `full`.

**Requires tests:**
- T-W1: one native gate trip → BLOCKED.
- T-W2: siege conditional on a security surface.
- T-W3: standalone inquisitor conditional on diff shape.
- T-W4: double-temper killed.
- T-W5: one build-tagged marker; leg marker not surfaced.
- T-W6: clean diff → PASS.
- T-W7: routing selection-eval.
- T-W8: full-set inquisitor unconditional.
- T-W9: ordering — residual commits + terminating re-check.
- T-W10: *retired.*
- T-W11: delve leg bounded convergence.
- T-W12: build recovery re-invokes warden.
- T-W13: siege twice per run (see Calibration-ledger entries).
- T-W14: temper-only fixer → frozen HEAD contains the fix.
"""

# The negation prose above must NOT trip the I-W1 guard; a real
# convert-to-scale construct MUST. This sample carries one.
_FORBIDDEN_SAMPLE = (
    _GOOD_SAMPLE
    + "\nTo merge, convert temper's Critical to siege's CVSS scale first.\n"
)

# Only "scale"/"normaliz"/"convert" mentions here are negation prose — the
# I-W1 guard must stay quiet on this in isolation.
_NEGATION_ONLY_SAMPLE = """\
warden runs each reviewer on its own severity scale — there is no cross-scale
normalization. Cross-scale conversion is forbidden. No leg's severity is
converted into another's.
"""

# Frontmatter regression case (missing `name: warden`).
_BAD_FRONTMATTER_SAMPLE = _GOOD_SAMPLE.replace("name: warden", "name: notwarden")

# ---- Task 3 fix-path negative/allow samples (R11 / R12) -------------------
# (a) R11 — a real `git commit -a` (would drop a leg's untracked files) FAILS.
_GIT_COMMIT_A_SAMPLE = (
    _GOOD_SAMPLE + "\nBad: warden runs `git commit -a` to commit the leg.\n")

# (b) THE CRUX trap — a sample whose ONLY "stash" occurrence is inside the
# REFUSE clause must NOT trip the R12 git-stash negative (bare word, no `git `
# prefix). This is what a bare-word grep would self-contradict against.
_REFUSE_ONLY_SAMPLE = (
    "Standalone warden on a dirty tree REFUSES: commit, stash, or clean "
    "untracked files, then re-run /warden.\n")

# (c) R12 — an actual `git stash` command line (mutating form) FAILS.
_GIT_STASH_CMD_SAMPLE = (
    _GOOD_SAMPLE + "\nBad: warden runs `git stash pop` to restore the tree.\n")

# (d) The ONE allowed mention — `git stash create` (temper's read-only snapshot,
# design L133-134) must NOT trip R12; the negative lookahead exempts it.
_GIT_STASH_CREATE_SAMPLE = (
    "temper uses `git stash create` to snapshot the tree; it is read-only.\n")

# ---- Task 4 temper-reviewer negative/allow samples (R13) ------------------
# THE TASK-4 TRAP (parity with the R12 crux, M-o2): the terminating freeze-guard
# is plain delve, NOT a `temper-reviewer` re-run — and warden's own prose must be
# able to SAY that without tripping its own guard. So R13 matches only the
# COMMAND/SKILL-REFERENCE form (`temper-reviewer.md` / `temper-reviewer/`), never
# the bare word.
# (a) R13 — dispatching the terminating leg AS temper-reviewer (its template-file
#     reference form, how temper actually dispatches it) FAILS.
_TEMPER_REVIEWER_DISPATCH_SAMPLE = (
    _GOOD_SAMPLE + "\nBad: warden re-dispatches `temper-reviewer.md` over "
    "`SHA_pre_redteam..HEAD` as the terminating leg.\n")

# (b) THE CRUX allow-case: prose that merely NAMES `temper-reviewer` to say the
#     freeze-guard is plain delve, NOT a temper-reviewer re-run, must NOT trip
#     R13 (bare word, no `.md`/`/` reference suffix).
_TEMPER_REVIEWER_PROSE_SAMPLE = (
    "The terminating freeze-guard is plain delve report-only — it is "
    "deliberately NOT a `temper-reviewer` re-run and runs no temper "
    "enumeration at all.\n")

# ---- Task 5 gate/enforcement negative sample (dead-leg fail-open) ----------
# THE FAIL-OPEN FOOTGUN: a §Gate that DROPS the dead-leg fail-closed clause —
# a died sub-dispatch silently treated as a pass instead of BLOCKED — must be
# flagged. Removing the "an unrun gate is not a pass" clause trips its label.
_GATE_MISSING_UNRUN_SAMPLE = _GOOD_SAMPLE.replace(
    "an unrun gate is not a pass", "it is fine")

# ---- Task 6 Option-C no-emit / I-W8 + T-W13 siege-suppression samples ---------
# (a) THE OPTION-C ALLOW (parity with the R12 crux): an evals-style DESCRIPTIVE
#     mention of runs.jsonl/emit must NOT trip the no-emit negative — only an
#     imperative emit *call* does. "self-emits"/"emits none" have no `(`.
_DESCRIPTIVE_EMIT_SAMPLE = (
    "Each leg self-emits its native `code` entry to `runs.jsonl`; warden emits "
    "none. delve self-emits a Tier-B stub; the fixture asserts one runs.jsonl "
    "row per leg.\n")

# (b) an IMPERATIVE ledger emit call in the SKILL.md must FAIL. Built by
#     concatenation so THIS checker's own source never carries a contiguous
#     emit-then-paren token — the emission-surface scan greps check_warden_*.py
#     (incl. this file), so a literal call here would self-trip.
_IMPERATIVE_EMIT_SAMPLE = (
    _GOOD_SAMPLE + "\nAt gate end warden runs " + "emit" + "(warden_code_row) "
    "to append its own aggregate verdict.\n")

# (c) T-W13 — a warden QG-dispatch that passes `skip_siege: true` (param form)
#     must FAIL: it would silently suppress warden's second siege (I-W4).
_SKIP_SIEGE_DISPATCH_SAMPLE = (
    _GOOD_SAMPLE + "\nDispatch the QG red-team leg with:\n  reviewer-set: full\n"
    "  skip_siege: true\n")

# (d) THE CRUX allow-case: descriptive prose that NAMES `skip_siege` to state the
#     guard must NOT trip T-W13 (backtick form, no `:` key / `--` flag).
_SKIP_SIEGE_PROSE_SAMPLE = (
    "warden deliberately does NOT pass `skip_siege` or `force_siege` to the QG "
    "red-team leg — it never suppresses the second siege.\n")

# ---- Task 7 I-W3 description-negative sample --------------------------------
# An owned trigger phrase in the frontmatter `description` FAILS (I-W3): warden
# must not claim a single-reviewer intent. The allow-case is the GOOD sample
# itself — its BODY carries all four owned phrases in the phrase-ownership table,
# yet passes, proving the negative is scoped to the `description:` value only.
_DESC_OWNED_PHRASE_SAMPLE = _GOOD_SAMPLE.replace(
    "description: Consolidated pre-push review gate — temper, delve, red-team, "
    "siege, inquisitor.",
    "description: Full gate — use when you want to know is this ready to ship.")


# ---- Task 9 I-W3 temper-side description samples ---------------------------
# temper's ceded `description` (lowercased, as `_extract_description` returns it):
# single-reviewer phrasing only, keeps the merge-verdict trigger, carries NO
# push-gate cue.
_TEMPER_DESC_GOOD = (
    'iteratively review code changes for production readiness through fresh-eyes '
    'review loops. use when completing tasks, implementing major features, or '
    'reviewing a change for production readiness — including when the user says '
    '"review this pr", "review my changes", "code review", "check the diff", or '
    '"is this ready to ship". works on prs from any forge or on raw git sha ranges.')
# A re-added push-gate cue must FAIL (I-W3): reintroduce "before merging".
_TEMPER_DESC_BANNED = _TEMPER_DESC_GOOD.replace(
    "reviewing a change for production readiness", "before merging")
# Dropping the single-reviewer trigger must FAIL (I-W3).
_TEMPER_DESC_MISSING_TRIGGER = _TEMPER_DESC_GOOD.replace(
    "is this ready to ship", "does it look ok")


# ---- Minor (b) M-c scope-gap sample -----------------------------------------
# The GOOD sample carries the M-c scope-gap disclosure (all three anchors
# co-located). Removing the `outside` anchor — the clause's scope word — breaks
# the trio's co-occurrence, so the M-c scope-gap check must FAIL. "outside"
# appears NOWHERE else in `_GOOD_SAMPLE`, so this transform is a clean removal.
_MC_SCOPE_MISSING_SAMPLE = _GOOD_SAMPLE.replace("outside", "within")


def selftest() -> int:
    # 1. GOOD sample passes every assertion.
    good_errs = check_text(_GOOD_SAMPLE)
    assert good_errs == [], f"GOOD sample should pass, got: {good_errs}"

    # 2. Per-clause RED: removing any single required substring flags exactly
    #    that clause. Auto-generated so every new entry gets its own RED case.
    for label, sub in REQUIRED_SUBSTRINGS.items():
        bad = _GOOD_SAMPLE.replace(sub, "‹removed›")
        errs = check_text(bad)
        # Exact-match, not loose `label in e`: labels nest (e.g. "…T-W1" ⊂
        # "…T-W11"), so a loose check could let one pin's RED pass on another
        # pin's error. Match the precise error string check_text builds at :487.
        assert any(e == f"missing {label}: `{sub}`" for e in errs), (
            f"removing {label!r} (`{sub}`) should flag it, got: {errs}")

    # 2b. Per-clause RED for the OR clauses: removing EVERY alternative flags the
    #     label. Auto-generated, so a new REQUIRED_ANY entry gets its RED case.
    for label, alts in REQUIRED_ANY.items():
        bad = _GOOD_SAMPLE
        for alt in alts:
            bad = bad.replace(alt, "‹removed›")
        errs = check_text(bad)
        # Exact-match against the OR-clause error string built at :490 — same
        # nesting-safety rationale as the REQUIRED_SUBSTRINGS loop above.
        assert any(
            e == f"missing {label}: none of {list(alts)} present" for e in errs), (
            f"removing all of {list(alts)} for {label!r} should flag it, "
            f"got: {errs}")

    # 3. I-W1 negative RED path: a real convert-to-scale construct is flagged.
    fb_errs = check_forbidden(_FORBIDDEN_SAMPLE)
    assert any("I-W1" in e for e in fb_errs), (
        f"convert-to-scale construct should trip I-W1, got: {fb_errs}")
    assert any("I-W1" in e for e in check_text(_FORBIDDEN_SAMPLE)), (
        "I-W1 trip should also surface through check_text")

    # 4. Negation prose in isolation must NOT trip I-W1.
    assert check_forbidden(_NEGATION_ONLY_SAMPLE) == [], (
        "negation prose must not trip I-W1, got: "
        f"{check_forbidden(_NEGATION_ONLY_SAMPLE)}")

    # 5. Frontmatter guard still catches a broken `name:`.
    fm_errs = check_text(_BAD_FRONTMATTER_SAMPLE)
    assert any("name: warden" in e for e in fm_errs), (
        f"missing `name: warden` should be flagged, got: {fm_errs}")

    # 6. Fix-path negatives (R11 / R12) — the three required cases + the crux allow.
    # (a) a real `git commit -a` FAILS (R11).
    a_errs = check_negatives(_GIT_COMMIT_A_SAMPLE)
    assert any("R11" in e for e in a_errs), (
        f"`git commit -a` should trip R11, got: {a_errs}")
    # (b) THE CRUX: a sample whose only "stash" is the REFUSE clause must NOT
    #     trip R12 (bare word, no `git ` prefix) — verify it passes clean.
    b_errs = check_negatives(_REFUSE_ONLY_SAMPLE)
    assert b_errs == [], (
        f"REFUSE-clause 'stash' must NOT trip the git-stash negative, got: {b_errs}")
    # (c) an actual `git stash` command line FAILS (R12).
    c_errs = check_negatives(_GIT_STASH_CMD_SAMPLE)
    assert any("R12" in e for e in c_errs), (
        f"`git stash pop` command should trip R12, got: {c_errs}")
    # (d) the allowed `git stash create` snapshot must NOT trip R12.
    d_errs = check_negatives(_GIT_STASH_CREATE_SAMPLE)
    assert d_errs == [], (
        f"`git stash create` (read-only snapshot) must NOT trip R12, got: {d_errs}")

    # 7. Task-4 temper-reviewer negative (R13) — both required cases.
    # (a) a `temper-reviewer.md` dispatch/reference FAILS (R13).
    ta_errs = check_negatives(_TEMPER_REVIEWER_DISPATCH_SAMPLE)
    assert any("R13" in e for e in ta_errs), (
        f"`temper-reviewer.md` dispatch should trip R13, got: {ta_errs}")
    # (b) THE CRUX: prose naming `temper-reviewer` to say the freeze-guard is
    #     NOT a temper-reviewer re-run must NOT trip R13 (bare word).
    tb_errs = check_negatives(_TEMPER_REVIEWER_PROSE_SAMPLE)
    assert tb_errs == [], (
        f"bare-word `temper-reviewer` prose must NOT trip R13, got: {tb_errs}")

    # 8. Task-5 gate negative — dropping the dead-leg fail-closed clause (a
    #    fail-open footgun: a died sub-dispatch treated as pass) is flagged.
    g_errs = check_text(_GATE_MISSING_UNRUN_SAMPLE)
    assert any("unrun gate is not a pass" in e for e in g_errs), (
        f"dropping the dead-leg fail-closed clause should be flagged, got: {g_errs}")

    # 9. Task-6 Option-C no-emit negative (I-W8) — descriptive allow + imperative
    #    FAIL (the scoped no-emit case-pair).
    de_errs = check_negatives(_DESCRIPTIVE_EMIT_SAMPLE)
    assert all("no-emit" not in e for e in de_errs), (
        f"descriptive runs.jsonl/emit mention must NOT trip no-emit, got: {de_errs}")
    ie_errs = check_negatives(_IMPERATIVE_EMIT_SAMPLE)
    assert any("no-emit" in e for e in ie_errs), (
        f"imperative ledger emit call should trip no-emit, got: {ie_errs}")

    # 10. Task-6 T-W13 siege-suppression negative — param FAIL + prose allow (the
    #     scoped no-siege-suppression case-pair).
    ss_errs = check_negatives(_SKIP_SIEGE_DISPATCH_SAMPLE)
    assert any("T-W13" in e for e in ss_errs), (
        f"`skip_siege: true` param should trip T-W13, got: {ss_errs}")
    sp_errs = check_negatives(_SKIP_SIEGE_PROSE_SAMPLE)
    assert all("T-W13" not in e for e in sp_errs), (
        f"descriptive `skip_siege` prose must NOT trip T-W13, got: {sp_errs}")

    # 11. Task-7 I-W3 description-negative — an owned phrase in the `description`
    #     FAILS; the allow-case is the GOOD sample (owned phrases in its BODY
    #     table pass, proving the negative is description-scoped, not whole-file).
    dn_errs = check_description_negatives(_DESC_OWNED_PHRASE_SAMPLE)
    assert any("I-W3" in e for e in dn_errs), (
        f"an owned phrase in the `description` should trip I-W3, got: {dn_errs}")
    assert check_description_negatives(_GOOD_SAMPLE) == [], (
        "owned phrases in the BODY (phrase-ownership table) must NOT trip the "
        "description-scoped I-W3 negative, got: "
        f"{check_description_negatives(_GOOD_SAMPLE)}")
    # 12. Task-9 I-W3 temper-side description guard — GOOD (ceded) passes; a
    #     re-added push-gate cue FAILS; dropping the merge-verdict trigger FAILS.
    assert check_temper_description(_TEMPER_DESC_GOOD) == [], (
        "ceded temper description should pass, got: "
        f"{check_temper_description(_TEMPER_DESC_GOOD)}")
    tban_errs = check_temper_description(_TEMPER_DESC_BANNED)
    assert any("before merging" in e for e in tban_errs), (
        f"a push-gate cue in temper's description should FAIL (I-W3), got: {tban_errs}")
    tmiss_errs = check_temper_description(_TEMPER_DESC_MISSING_TRIGGER)
    assert any("is this ready to ship" in e for e in tmiss_errs), (
        f"dropping temper's merge-verdict trigger should FAIL (I-W3), got: {tmiss_errs}")

    # 13. Minor (b) M-c scope-gap disclosure — GOOD (all three anchors
    #     co-located) passes; removing the `outside` scope anchor breaks the
    #     trio's proximity, so the check FAILS.
    assert check_mc_scope_gap(_GOOD_SAMPLE) == [], (
        "GOOD sample's M-c scope-gap disclosure should pass, got: "
        f"{check_mc_scope_gap(_GOOD_SAMPLE)}")
    mc_errs = check_mc_scope_gap(_MC_SCOPE_MISSING_SAMPLE)
    assert any("Minor b" in e for e in mc_errs), (
        "removing the `outside` scope anchor should trip the M-c scope-gap "
        f"disclosure check, got: {mc_errs}")

    # (The emission-surface scan over the shipped scripts and the temper-side
    # description read are filesystem checks, so they stay in `main()` — not here
    # — keeping `--selftest` purely in-memory.)

    print("selftest OK — GOOD passes; each required clause (incl. OR clauses), "
          "the I-W1 normalization negative, the R11 `git commit -a` and R12 "
          "`git stash`-command negatives (with the REFUSE-clause bare-word and "
          "`git stash create` allow-cases), the R13 `temper-reviewer` "
          "reference-form negative (a: `temper-reviewer.md` dispatch FAILS; "
          "b: bare-word prose 'NOT a temper-reviewer re-run' does NOT trip), the "
          "Task-6 Option-C no-emit negative (descriptive runs.jsonl/emit mention "
          "does NOT trip; an imperative emit-call FAILS) and its emission-surface "
          "scan over check_warden_*.py, the T-W13 siege-suppression negative "
          "(`skip_siege: true` param FAILS; descriptive `skip_siege` prose does "
          "NOT trip), the Task-7 I-W3 description-scoped owned-phrase negative "
          "(an owned phrase in the `description` FAILS; the same phrases in the "
          "BODY phrase-ownership table do NOT trip), and the frontmatter guard "
          "each have an exercised path.")
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    if not SKILL.is_file():
        print("WARDEN STRUCTURE CHECK FAILED:")
        print(f"  - {SKILL.relative_to(ROOT)} does not exist")
        return 1

    errs = check_text(SKILL.read_text(encoding="utf-8"))
    errs.extend(check_emission_surface_files())
    errs.extend(check_temper_description_file())
    if errs:
        print("WARDEN STRUCTURE CHECK FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — warden SKILL.md carries every required structural clause.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
