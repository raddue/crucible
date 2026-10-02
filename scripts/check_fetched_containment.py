#!/usr/bin/env python3
"""Fetched-content containment + cat-8 propagation contract checker (#641).

Path-pinned structural gate over the shared rules the PR #638 merged diff
introduced, their consumers, and the spec/quality-gate dispatch paths that must
honour category 8. Pins *contract tokens* (enum values, CONTRACT anchors, grep
forms, exception sentences) — not prose — per scripts/CHECKER_CONVENTIONS.md.

Invocation (from repo root):
    python3 scripts/check_fetched_containment.py            # check the tracked tree
    python3 scripts/check_fetched_containment.py --selftest # built-in logic tests

Covers the #641 findings, triaged mechanical:
  - F1  category-8 single-match rule live on: action table + contract enum +
       status semantics (security-signals.md), siege activation heuristic, the
       spec validator + contract-schema + spec-writer-prompt `destination`
       value, and the quality-gate detection heuristic;
  - F2  ledger-monotonicity guard on siege's own self-commit path, run by the
       orchestrator against a round-start SHA the orchestrator records before
       dispatch, disclosed prose-only;
  - F3  "currently open" ledger grep anchored to id + disposition field (not
       fail-open to FE-1/FE-12 prefix or URL/host-field disposition tokens);
  - F4  host character class admits dotted real hostnames;
  - F6  fetched-content-containment declared as a column-0 CANONICAL link in
       both consumers so check_canonical_links.py resolves it.

F4 note: the host class `[A-Za-z0-9.-]+` does not admit `:` (ports fail closed)
and admits ASCII uppercase (case is accepted) — an upstream ERE property, not
separately documented in the contract doc. Stdlib only. Exit 0 / 1 + `- <error>`.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

FILES = {
    "fetched": "skills/shared/fetched-content-containment.md",
    "signals": "skills/shared/security-signals.md",
    "siege": "skills/siege/SKILL.md",
    "sdd": "skills/source-driven-development/SKILL.md",
    "spec_skill": "skills/spec/SKILL.md",
    "contract_schema": "skills/spec/contract-schema.md",
    "spec_writer": "skills/spec/spec-writer-prompt.md",
    "qg": "skills/quality-gate/SKILL.md",
}

CANONICAL_LINK = "<!-- CANONICAL: shared/fetched-content-containment.md -->"

# The two grep forms the ledger "currently open" set MUST use (POSIX ERE; <n>
# substituted with the concrete id). Anchored: id is delimited by ` \|` (so
# FE-1 does not prefix-match FE-12), disposition is the last field and ends
# the line (so a disposition token in the host/URL field cannot self-close).
OPEN_GREP = r"^- FETCHED-ENDPOINT FE-<n> \|.*\| UNAPPROVED$"
CLOSED_GREP = r"^- FETCHED-ENDPOINT FE-<n> \|.*\| (APPROVED|REJECTED)-[A-Za-z0-9]+-[0-9]{4}-[0-9]{2}-[0-9]{2}$"

# The authoritative field-exact ERE tail (fetched-content-containment.md:82)
# must stay present: URL + date + disposition are each a distinct field, so the
# `.*` convenience greps above cannot become the only reference.
AUTHORITATIVE_FIELD_EXACT = r"https?://[^ |]+ \| [0-9]{4}-[0-9]{2}-[0-9]{2} \| (UNAPPROVED"

# Required-absent: the unanchored forms that fail open. Each is a distinct
# historical bug, so each gets its own pin (CHECKER_CONVENTIONS §1 — a
# required-absent assertion cannot be marker-wrapped, so pin the literal).
OLD_OPEN = r"FE-<n>.*UNAPPROVED"
OLD_CLOSED_PAREN = r"FE-<n>.*(APPROVED-|REJECTED-)"
OLD_CLOSED_BARE = r"FE-<n>.*APPROVED|REJECTED"
OLD_APPROVED_LOOSE = r"FE-<n>.*APPROVED"

# Field-exact forms derived from the authoritative 6-field ERE (:82) with the id
# substituted for `FE-[0-9]+` — no `.*`, so an extra field cannot satisfy the
# disposition anchor. Used by the selftest to prove the fix above the doc's
# `.*` convenience forms (which still admit a 6-field line).
EXACT_FIELDS = r"\| [A-Za-z0-9.-]+ \| https?://[^ |]+ \| [0-9]{4}-[0-9]{2}-[0-9]{2} \| "
OPEN_EXACT = r"^- FETCHED-ENDPOINT FE-<n> " + EXACT_FIELDS + r"UNAPPROVED$"
CLOSED_EXACT = r"^- FETCHED-ENDPOINT FE-<n> " + EXACT_FIELDS + r"(APPROVED|REJECTED)-[A-Za-z0-9]+-[0-9]{4}-[0-9]{2}-[0-9]{2}$"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def has_column0_link(text: str) -> bool:
    """Dependency declared as a standalone column-0 CANONICAL line — the only
    form check_canonical_links.py's MATCH_RE resolves."""
    return any(line.strip() == CANONICAL_LINK for line in text.splitlines())


def compile_grep(grep_form: str, n: int) -> re.Pattern:
    # The ERE dialect used here (`\|` = literal pipe, `[0-9]{4}` repeats) is
    # valid Python `re` too.
    return re.compile(grep_form.replace("<n>", str(n)))


def check(texts: dict[str, str]) -> list[str]:
    errs: list[str] = []

    f = texts["fetched"]
    # F3 — anchored open + closing forms present; unanchored old forms absent.
    if OPEN_GREP not in f:
        errs.append("- fetched: anchored open-set grep missing")
    if CLOSED_GREP not in f:
        errs.append("- fetched: anchored closing-line grep missing")
    if AUTHORITATIVE_FIELD_EXACT not in f:
        errs.append("- fetched: authoritative field-exact ERE (URL|date|disposition) missing")
    for label, old in [("FE-<n>.*UNAPPROVED", OLD_OPEN),
                       ("FE-<n>.*(APPROVED-|REJECTED-)", OLD_CLOSED_PAREN),
                       ("FE-<n>.*APPROVED|REJECTED", OLD_CLOSED_BARE),
                       ("FE-<n>.*APPROVED", OLD_APPROVED_LOOSE)]:
        if old in f:
            errs.append(f"- fetched: fail-open grep form reappeared: {label}")
    # F4 — host token admits dotted real hostnames.
    if "[A-Za-z0-9.-]+" not in f:
        errs.append("- fetched: ERE host token lacks the dot ('[A-Za-z0-9.-]+')")

    s = texts["signals"]
    # F1 — eight categories; enum; action-table + status-row anchors + prose.
    if "Eight categories" not in s:
        errs.append("- signals: intro still says 'Seven categories'")
    if "`dependencies`, `destination`" not in s:
        errs.append("- signals: contract enum missing the 'destination' category-8 value")
    if "CONTRACT:signals-cat8-action-table" not in s:
        errs.append("- signals: action-table category-8 exception anchor missing")
    if "CONTRACT:signals-cat8-status-row" not in s:
        errs.append("- signals: status-row category-8 anchor missing")
    if "a single Category-8 match is `required`" not in s:
        errs.append("- signals: action-table category-8 exception sentence missing")

    g = texts["siege"]
    # F1 — activation heuristic carries the category-8 single-match exception.
    if "CONTRACT:siege-activation-cat8-exception" not in g:
        errs.append("- siege: activation heuristic missing category-8 single-match exception")
    if "8-category" not in g:
        errs.append("- siege: activation heuristic still says '7-category'")
    if "dispatching siege regardless of the 2-of-7 threshold" not in g:
        errs.append("- siege: activation exception sentence missing")
    # F2 — orchestrator records round-start SHAs before dispatch; fix agent no
    # longer writes expected-head.md.
    if "CONTRACT:siege-ledger-monotonicity" not in g:
        errs.append("- siege: Phase 4 self-commit path missing ledger-monotonicity guard")
    if "records the round-start SHA" not in g:
        errs.append("- siege: orchestrator-owned round-start SHA recording missing")
    if "fix agent writes `expected-head.md`" in g:
        errs.append("- siege: fix-agent-writes-expected-head rule reappeared")
    if "Prose-only" not in g:
        errs.append("- siege: ledger guard not disclosed prose-only")
    # F1 — no dead build Step 5.5 reference (routed through warden).
    if "Phase 4 Step 5.5" in g:
        errs.append("- siege: dead 'build Phase 4 Step 5.5' reference reappeared")
    # F6 — column-0 dependency link.
    if not has_column0_link(g):
        errs.append("- siege: missing column-0 CANONICAL fetched-content-containment link")

    if not has_column0_link(texts["sdd"]):
        errs.append("- sdd: missing column-0 CANONICAL fetched-content-containment link")

    # F1 propagation to the dispatching consumers.
    if "`dependencies`, `destination`" not in texts["spec_skill"]:
        errs.append("- spec: validator enum missing 'destination'")
    if "dependencies | destination" not in texts["contract_schema"]:
        errs.append("- contract-schema: comment enum missing 'destination'")
    if "single Category-8 match" not in texts["contract_schema"]:
        errs.append("- contract-schema: status comment missing category-8 exception")
    if "8 signal categories" not in texts["spec_writer"]:
        errs.append("- spec-writer: still says '7 signal categories'")
    if "pii_data, dependencies, destination" not in texts["spec_writer"]:
        errs.append("- spec-writer: enum comment missing 'destination' (or the pii_data/dependencies tail)")
    if "single bounded destination-bearing match fires alone, never `recommended`" not in texts["spec_writer"]:
        errs.append("- spec-writer: single Category-8 `status: required` rule missing")
    if "Destination-bearing construct (category 8" not in texts["qg"]:
        errs.append("- quality-gate: detection heuristic missing category-8 trigger")
    if "Category 8 is the sole exception" not in texts["qg"]:
        errs.append("- quality-gate: confidence-threshold category-8 exception sentence missing")
    if "git diff <base>..HEAD" not in texts["qg"]:
        errs.append("- quality-gate: category-8 arm missing raw-diff base / fail-closed rule")

    return errs


def main() -> int:
    texts = {k: read(v) for k, v in FILES.items()}
    errs = check(texts)
    if errs:
        print("\n".join(errs))
        return 1
    print("OK — fetched-content containment contract holds.")
    return 0


def _good_fixture() -> dict[str, str]:
    return {
        "fetched": OPEN_GREP + "\n" + CLOSED_GREP + "\n[A-Za-z0-9.-]+\n" + AUTHORITATIVE_FIELD_EXACT + "\n",
        "signals": "Eight categories\n`dependencies`, `destination`\n"
                   "CONTRACT:signals-cat8-action-table\nCONTRACT:signals-cat8-status-row\n"
                   "a single Category-8 match is `required`\n",
        "siege": CANONICAL_LINK + "\nCONTRACT:siege-activation-cat8-exception\n8-category\n"
                 "dispatching siege regardless of the 2-of-7 threshold\n"
                 "CONTRACT:siege-ledger-monotonicity\nrecords the round-start SHA\nProse-only\n",
        "sdd": CANONICAL_LINK + "\n",
        "spec_skill": "`dependencies`, `destination`\n",
        "contract_schema": "dependencies | destination\nsingle Category-8 match\n",
        "spec_writer": "8 signal categories\npii_data, dependencies, destination\n"
                       "single bounded destination-bearing match fires alone, never `recommended`\n",
        "qg": "Destination-bearing construct (category 8\nCategory 8 is the sole exception\n"
             "git diff <base>..HEAD\n",
    }


def selftest() -> int:
    failures: list[str] = []

    def expect(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    def closes(form: str, ledger_line: str) -> bool:
        return compile_grep(form, 1).search(ledger_line) is not None

    def opens(form: str, ledger_line: str) -> bool:
        return compile_grep(form, 1).search(ledger_line) is not None

    # F3 adversarial cases (reproduce the warden bypasses). CLOSED must match a
    # genuine closing line and nothing else in this list; OPEN must match only
    # UNAPPROVED lines.
    closing_ok = "- FETCHED-ENDPOINT FE-1 | api.sentry.io | https://doc | 2026-01-01 | APPROVED-rr-2026-01-02"
    rejected_ok = "- FETCHED-ENDPOINT FE-1 | api.sentry.io | https://doc | 2026-01-01 | REJECTED-rr-2026-01-02"
    unapproved = "- FETCHED-ENDPOINT FE-1 | api.sentry.io | https://doc | 2026-01-01 | UNAPPROVED"
    expect(closes(CLOSED_GREP, closing_ok), "genuine APPROVED-… closing line closes")
    expect(closes(CLOSED_GREP, rejected_ok), "genuine REJECTED-… closing line closes")
    expect(not closes(CLOSED_GREP, unapproved), "UNAPPROVED line is not closed")

    # FE-1 vs FE-12 prefix collision: FE-12's closing line must not close FE-1.
    fe12 = "- FETCHED-ENDPOINT FE-12 | x | https://d | 2026-01-01 | APPROVED-rr-2026-01-02"
    expect(not closes(CLOSED_GREP, fe12), "FE-12 APPROVED does not close FE-1")
    fe12_open = "- FETCHED-ENDPOINT FE-12 | x | https://d | 2026-01-01 | UNAPPROVED"
    expect(not opens(OPEN_GREP, fe12_open), "FE-12 UNAPPROVED is not FE-1 open")

    # URL-field disposition self-close: must not close.
    url_decoy = "- FETCHED-ENDPOINT FE-1 | x | https://evil/FE-1/APPROVED-x | 2026-01-01 | UNAPPROVED"
    expect(not closes(CLOSED_GREP, url_decoy), "URL-field APPROVED-x does not self-close")
    url_decoy2 = "- FETCHED-ENDPOINT FE-1 | x | https://ok.io/?s=FE-8,REJECTED-1 | 2026-01-01 | UNAPPROVED"
    expect(not closes(CLOSED_GREP, url_decoy2), "URL-field REJECTED-1 does not self-close")

    # Host-field disposition self-close: must not close.
    host_decoy = "- FETCHED-ENDPOINT FE-1 | APPROVED-ab | https://d | 2026-01-01 | UNAPPROVED"
    expect(not closes(CLOSED_GREP, host_decoy), "host-field APPROVED-ab does not self-close")

    # Malformed disposition (no date) must not close.
    malformed = "- FETCHED-ENDPOINT FE-1 | x | https://d | 2026-01-01 | APPROVED-x"
    expect(not closes(CLOSED_GREP, malformed), "malformed APPROVED-x does not close")

    # The open line still registers as open.
    expect(opens(OPEN_GREP, unapproved), "UNAPPROVED line registers open")

    # Field-exact 6-field decoy: an agent-written extra field between the date
    # and the disposition must not close under the authoritative field-exact
    # ERE (the doc's `.*` convenience form spans fields and would close it).
    six_field = "- FETCHED-ENDPOINT FE-1 | api.sentry.io | https://doc | 2026-01-01 | UNAPPROVED | APPROVED-ab-2026-01-02"
    expect(not closes(CLOSED_EXACT, six_field), "6-field line does not close (field-exact)")
    expect(not opens(OPEN_EXACT, six_field), "6-field line is not a pure UNAPPROVED open (field-exact)")

    # Required-absent detection: each old form trips exactly its own pin.
    good = _good_fixture()
    for label, old in [("FE-<n>.*UNAPPROVED", OLD_OPEN),
                       ("FE-<n>.*(APPROVED-|REJECTED-)", OLD_CLOSED_PAREN),
                       ("FE-<n>.*APPROVED|REJECTED", OLD_CLOSED_BARE),
                       ("FE-<n>.*APPROVED", OLD_APPROVED_LOOSE)]:
        mutated = dict(good)
        mutated["fetched"] = old + "\n" + good["fetched"]
        bad = check(mutated)
        hit = any("reappeared" in e for e in bad)
        expect(hit, f"old fail-open form {label!r} rejected when present")

    # A clean fixture passes.
    expect(check(good) == [], "clean fixture passes")

    # Column-0 detection: a backtick/mid-sentence placement is NOT a declaration.
    inline = dict(good)
    inline["sdd"] = "governed by `" + CANONICAL_LINK + "` — see note.\n"
    expect(any("column-0" in e for e in check(inline)), "inline link not a column-0 declaration")

    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())