# Writing a `scripts/check_*.py` checker

These checkers are the repo's structural CI gates over Markdown-as-code. Two
conventions keep them from taxing the work the repo does most. Both exist to
answer the same recurring authoring question: *how do I pin a contract without
breaking CI every time someone re-words prose, and without the checker matching
itself?*

## 1. Pin the contract, not the prose — use `CONTRACT` anchors (#399)

A wording edit with zero behavioral meaning must never break CI. The two hottest
files in the repo (`skills/quality-gate/SKILL.md`, the build reviewer family) are
edited constantly; a checker that pins a verbatim English sentence there turns
every benign re-word into a red build.

So: when an assertion means *"this rule / section is present here"*, pin a
structural HTML-comment anchor, not the sentence. The prose inside is then free.

- **Point anchor** — a rule that lives in a flowing paragraph or a list item:
  append an inline comment at the end of its line.

  ```
  … the original concern demonstrably no longer reproduces. <!-- CONTRACT:rt-fix-test-less-witness — check_rt_receipt_contract.py [C18] -->
  ```
  The checker asserts `"CONTRACT:rt-fix-test-less-witness" in text`.

- **Block anchor** — a delimited region whose *interior* must satisfy a real
  invariant (an enum value-set, a non-empty template): wrap it in START/END.

  ```
  <!-- CONTRACT:qg-dr-cause:START — the enum below is the contract; prose is free -->
  - `dr_cause`: … Value set: `"minor-accumulation" | "structural-saturation" | "consensus" | null`.
  <!-- CONTRACT:qg-dr-cause:END -->
  ```
  The checker extracts the interior and asserts it is non-empty **and** still
  carries the genuine contract tokens (here, the four enum values). The interior
  token set a block anchor enforces is chosen **per-checker** and is intentionally
  minimal — e.g. the `CONTRACT:preflight` block enforces only the single `MISSING`
  template token (plus non-empty + present-in-both), having deliberately dropped
  its former `deployed right now` / `dash bullets` / `Always emit` prose pins. Do
  not infer that every block anchor re-checks its full former pin set.

  Block and point anchors need not sit at column 0: the real `CONTRACT:preflight`
  block anchors in `skills/build/build-reviewer-prompt.md` are indented 4 spaces
  inside a dispatch-template. The checker regexes run on raw text with `re.DOTALL`
  and are indentation-agnostic, so the unindented examples above are illustrative,
  not a requirement.

Anchor names are `<checker-area>:<id>`, e.g. `rt-findings-writer-inversion`,
`qg-dr-cause`, `preflight`. Anchors render invisibly and have no reason to be
touched during a prose edit, so they are stable; the regression guard survives
while the churn tax disappears.

**What this trades away (and when that's fine).** An anchor guards against
*deletion of the rule's home*, not against someone gutting the prose while
leaving the comment. That is the right strength for a regression guard on
already-shipped behavior. It is the *wrong* tool — keep the verbatim pin —
when:

- the assertion is **required-ABSENT** (a stale claim that must not reappear):
  you cannot marker-wrap a string that isn't there;
- the token **IS** the contract and editing it is a real change: code-like
  tokens (`### Fatal Challenges`, `SEVERITY-COUNTS:`, `Category: Tenancy`,
  `TRIPWIRE: none`), enum value-sets, schema field names;
- the exact wording is a **cross-file doctrine** two files must paraphrase
  consistently (the reviewer-common ↔ build-reviewer lens/ceiling sentences):
  the wording is the drift contract, not incidental prose.

Pin the brittle pure-English present-pins; keep the rest verbatim.

**Known limitation — first-match decoy.** The block-anchor regex
(`...START.*?-->(.*?)...END`, a non-greedy `re.search`) latches the FIRST
`:START` in the file. A future edit that places a *same-named* `:START`/`:END`
example (e.g. an illustrative empty block) ABOVE the real block in the same
path-pinned file makes the checker bind the decoy and false-FAIL at fix-time
(loud, not silent). Mitigate by keeping at most one block per anchor name per
file, or scope the block search after a section heading if a file must also carry
an illustrative example.

## 2. Don't let a checker match itself

A checker that scans Markdown for its own pin strings can read *itself* and pass
spuriously (or read a doc that merely mentions the pin). Which discipline applies
is decided by **one** thing — does the checker glob, or read a fixed file list?

- **Path-pinned checkers are immune.** If a checker reads only an explicit,
  hard-coded set of target files (e.g. `check_rt_receipt_contract.py`,
  `check_qg_stagnation_minor.py`, `check_canonical_drift.py`) and never walks the
  tree, it cannot encounter its own source. It may pin literal strings —
  including `CONTRACT` anchor names — freely. This is the preferred shape: pin
  the file, pin the literal.

- **Globbing checkers must avoid self-match.** If a checker walks the tree
  (`rglob("*.md")`, `git ls-files "*.md"`), it WILL eventually read any new file
  containing the pin — including itself and incidental prose mentions. Use one of:
  - **column-0 anchoring** — match only at line start (`^dispatch: delve-engine`),
    so inline / backtick-wrapped / indented mentions elsewhere stay safe
    (`check_i2_marker.py`);
  - **fragment-splitting** — build the match string from concatenated pieces so
    the checker's own source never contains the whole literal
    (`check_i2_marker.py:` `r"^dispatch: " + "delve-engine"`);
  - **a distinct namespace** the checker resolves rather than greps
    (`check_crossref.py` resolves `crucible:<token>` against `skills/<token>/`;
    `check_model_pins.py` keys on the `MODEL-TIER` marker as a standalone line).

`CONTRACT` anchors are safe to sprinkle into any `.md`: they contain no
`crucible:` token, no line-start `model:`, and no `^dispatch:` line, so none of
the three globbing checkers above false-fire on them.

## 3. Other house rules

- **Stdlib only.** No third-party imports — these run in bare CI.
- **Exit 0 clean / 1 with a `- <error>` list.** One finding per line.
- **A `--selftest` is encouraged** for detection logic with edge cases
  (`check_model_pins.py`, `check_crossref.py`, `check_calibration_dispatch.py`),
  and is run as its own line in `scripts/run_tests.sh` ahead of the tree check.
- **Wire it into `scripts/run_tests.sh`** — the single source of truth that
  `.github/workflows/ci.yml` invokes. A checker not listed there does not run.
