#!/usr/bin/env python3
"""Provenance + GT-integrity check for the delve eval ground-truth fixtures (#373).

Invocation (from repo root):
    python3 scripts/check_delve_gt_provenance.py            # check the tree
    python3 scripts/check_delve_gt_provenance.py --selftest # built-in logic tests

Two machine-verifiable checks per fixture under `skills/delve/evals/fixtures/<repo>/`:

1. Blind boundary. Each fixture's primary oracle is `ground-truth-bugs.json`, whose
   `signature` tokens + per-bug `desc` strings ARE the answer key. The design requires
   that key be withheld from the blind author who wrote `ground-truth-bugs.provenance.md`
   (authoring from the answer key would bias the recorded run's grading). This check
   asserts the provenance file contains NONE of that fixture's GT `signature` tokens or
   `desc` strings — if any appears, the blind boundary leaked.

2. GT integrity. A malformed committed fixture corrupts recall silently (CI stays
   green while a bug can never match) or crashes `match()`/the scorer at score time.
   This check is a COMPLETE GT-schema validator — it asserts the full invariant set the
   matcher + scorer depend on, and is itself total (it returns a violations list for ANY
   input shape and never raises):
     - structure: `gt["bugs"]` is present and a `list`, and every element is a `dict`
       (a non-list `bugs` or a non-dict element would crash the per-bug loop / matcher);
     - per bug, every required field is present AND correctly typed: `bug_id` and `file`
       are non-empty `str`, `line_lo` and `line_hi` are `int` (and not `bool`, since
       `isinstance(True, int)` is True) — the matcher does `file.startswith(...)` and
       arithmetic/comparison on the lines, so a wrong type crashes `match()` (a str/None
       line → TypeError, an int file → AttributeError) and a float line silently matches;
     - relational: `line_lo <= line_hi` — an inverted/transposed range inverts the match
       window, so the bug can NEVER match and its recall is silently 0;
     - non-empty `signature` per bug — a `list` with ≥1 non-empty `str` token; the
       matcher gates every edge on `_signature_hits(bug, finding) > 0`, so a bug with no
       usable signature token can NEVER match (recall silently 0), while a `[""]`-only
       signature substring-matches EVERYTHING (recall silently inflated);
     - `off_axis`, when present, is a JSON bool — the scorer uses `b.get("off_axis")`
       truthiness, so a JSON string like `"false"` would (mis)count as off-axis;
     - unique `bug_id`s within `ground-truth-bugs.json` (the matcher keys everything by
       `bug_id`, so two rows sharing one collapse into a single matchable slot);
     - if a `manifest.json` exists, `manifest["n"] == len(bugs)` AND
       `set(manifest["bug_ids"])` equals the GT bug_id set (the manifest duplicates the
       answer key, so an undetected mismatch would mask a corrupt fixture).

"Trust the process" is what this repo's calibration ethos rejects, so both are gated.
Stdlib only. Exit 0 clean / 1 on any detected leak or integrity violation.
"""
from __future__ import annotations
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "skills/delve/evals/fixtures"


def withheld_strings(gt: dict) -> list:
    """Every signature token + desc string the provenance must NOT contain.

    Signature tokens are matched case-insensitively (the matcher lowercases them);
    desc strings are matched verbatim. Returned as (needle, kind, comparison_text)
    so the scan can be case-correct per kind.

    Robust by construction: a non-string `desc` or signature token is skipped (the
    `isinstance(..., str)` guards), so the comparison_text fed to `leaks()` is always a
    `str` and `cmp in haystack` can never raise — even if a malformed fixture bypassed
    `gt_integrity_violations()`. The validator names the violation; this guarantees no
    bare TypeError regardless."""
    out = []
    if not isinstance(gt, dict):
        return out
    bugs = gt.get("bugs")
    if not isinstance(bugs, list):
        return out
    for bug in bugs:
        if not isinstance(bug, dict):
            continue
        sig = bug.get("signature")
        for tok in sig if isinstance(sig, list) else []:
            if isinstance(tok, str) and tok:
                out.append((tok, "signature", tok.lower()))
        desc = bug.get("desc")
        if isinstance(desc, str) and desc:
            out.append((desc, "desc", desc))
    return out


def leaks(provenance_text: str, strings) -> list:
    """Return the (needle, kind) entries that leaked into the provenance text.
    Signature tokens compare case-insensitively; desc strings compare verbatim."""
    lower_text = provenance_text.lower()
    found = []
    for needle, kind, cmp in strings:
        haystack = lower_text if kind == "signature" else provenance_text
        if cmp in haystack:
            found.append((needle, kind))
    return found


# Required fields and the exact type each must carry. `line_lo`/`line_hi` use `int`
# but bool is excluded explicitly below (isinstance(True, int) is True in Python).
_REQUIRED_FIELDS = ("bug_id", "file", "line_lo", "line_hi")
_STR_FIELDS = ("bug_id", "file")
_INT_FIELDS = ("line_lo", "line_hi")


def _is_int(v) -> bool:
    """True iff v is a real int — bool excluded (isinstance(True, int) is True)."""
    return isinstance(v, int) and not isinstance(v, bool)


def gt_integrity_violations(gt, manifest) -> list:
    """Return human-readable integrity violations for one fixture's GT (+manifest).

    COMPLETE GT-schema validator, and TOTAL: it returns a violations list for ANY input
    shape and never raises. Guards the container/elements FIRST, so a malformed
    `bugs` value or a non-dict element produces a violation instead of an exception.

    Per fixture, flags a violation for any of:
      - structure: `gt` is not a dict, or `gt["bugs"]` is missing / not a list, or any
        element of `bugs` is not a dict;
      - per bug: a required field (`bug_id`, `file`, `line_lo`, `line_hi`) missing or of
        the wrong type — `bug_id`/`file` must be non-empty `str`, `line_lo`/`line_hi`
        must be `int` (not `bool`);
      - relational: when both line bounds are valid ints, `line_lo <= line_hi`;
      - `signature` present, a `list`, with EVERY token a non-empty `str` (a missing
        key, non-list, empty list, or any non-str / empty / blank token → violation;
        the matcher does `str(tok).lower()`, so a non-str token would latently
        overmatch);
      - `desc`, when present, is a `str` (the blind-boundary leak scan uses it as a
        withheld needle in `cmp in haystack`, so a non-str would crash the scan);
      - `off_axis`, when present, is a Python `bool`;
      - bug_id uniqueness within `ground-truth-bugs.json`;
      - if `manifest` is not None, `manifest["n"] == len(bugs)` and
        `set(manifest["bug_ids"])` equals the GT bug_id set.
    Empty list ⇒ clean. Pure (no filesystem)."""
    violations = []
    # --- Structure guards (run FIRST so the per-bug loop never raises). ---
    if not isinstance(gt, dict):
        return [f"ground-truth-bugs.json is {type(gt).__name__}, not a dict (object)"]
    if "bugs" not in gt:
        violations.append("ground-truth-bugs.json is missing required key 'bugs'")
        bugs = []
    elif not isinstance(gt["bugs"], list):
        violations.append(
            f"ground-truth-bugs.json 'bugs' is {type(gt['bugs']).__name__}, not a list")
        bugs = []
    else:
        bugs = gt["bugs"]

    # bug_id set is computed only from dict elements (others are reported below).
    bug_ids = [b.get("bug_id") for b in bugs if isinstance(b, dict)]
    dups = sorted({bid for bid in bug_ids
                   if isinstance(bid, str) and bug_ids.count(bid) > 1})
    if dups:
        violations.append(f"duplicate bug_id(s) in ground-truth-bugs.json: {dups}")

    for i, b in enumerate(bugs):
        if not isinstance(b, dict):
            violations.append(
                f"bug at index {i} is {type(b).__name__}, not a dict (object)")
            continue
        # Name the bug by bug_id when it is a usable string, else by index.
        bid = b.get("bug_id")
        who = repr(bid) if isinstance(bid, str) and bid else f"index {i}"
        for field in _REQUIRED_FIELDS:
            if field not in b:
                violations.append(f"bug {who} is missing required field {field!r}")
        for field in _STR_FIELDS:
            if field in b:
                v = b[field]
                if not isinstance(v, str) or not v:
                    violations.append(
                        f"bug {who} field {field!r} is "
                        f"{type(v).__name__ if not isinstance(v, str) else 'empty'}, "
                        f"not a non-empty str")
        for field in _INT_FIELDS:
            if field in b and not _is_int(b[field]):
                violations.append(
                    f"bug {who} field {field!r} is {type(b[field]).__name__}, "
                    f"not an int")
        # Relational: only when both bounds are valid ints (else type errors above).
        if (_is_int(b.get("line_lo")) and _is_int(b.get("line_hi"))
                and b["line_lo"] > b["line_hi"]):
            violations.append(
                f"bug {who} has inverted range line_lo={b['line_lo']} > "
                f"line_hi={b['line_hi']} (bug could never match)")
        sig = b.get("signature")
        if not isinstance(sig, list):
            if "signature" not in b:
                shape = "absent (key missing)"
            elif sig is None:
                shape = "null"
            else:
                shape = type(sig).__name__
            violations.append(f"bug {who} signature is {shape}, not a list")
        elif not any(isinstance(tok, str) and tok.strip() for tok in sig):
            violations.append(
                f"bug {who} signature has no usable non-empty str token")
        else:
            # Every token must be a non-empty str: the matcher does str(tok).lower(),
            # so 123 -> "123" / None -> "none" is a latent substring overmatch even
            # when one good token satisfies the "≥1 usable" rule above.
            for j, tok in enumerate(sig):
                if not isinstance(tok, str):
                    violations.append(
                        f"bug {who} signature token at index {j} is "
                        f"{type(tok).__name__}, not a str")
                elif not tok.strip():
                    violations.append(
                        f"bug {who} signature token at index {j} is empty/blank")
        if "desc" in b and not isinstance(b["desc"], str):
            violations.append(
                f"bug {who} field 'desc' is {type(b['desc']).__name__}, not a str")
        if "off_axis" in b and not isinstance(b["off_axis"], bool):
            violations.append(
                f"bug {who} off_axis is {type(b['off_axis']).__name__}, not a bool")

    if manifest is not None:
        gt_set = set(bug_ids)
        man_n = manifest.get("n") if isinstance(manifest, dict) else None
        if man_n != len(bugs):
            violations.append(f"manifest n={man_n} != len(bugs)={len(bugs)}")
        man_ids = manifest.get("bug_ids", []) if isinstance(manifest, dict) else []
        man_set = set(man_ids) if isinstance(man_ids, list) else set()
        if man_set != gt_set:
            violations.append(
                f"manifest bug_ids {sorted(man_set, key=str)} != "
                f"GT bug_ids {sorted(gt_set, key=str)}")
    return violations


def _fixture_dirs() -> list:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(d for d in FIXTURES_DIR.iterdir()
                  if d.is_dir() and (d / "ground-truth-bugs.json").exists())


def main() -> int:
    dirs = _fixture_dirs()
    if not dirs:
        print(f"[fatal] no delve eval fixtures with ground-truth-bugs.json under "
              f"{FIXTURES_DIR.relative_to(ROOT)}", file=sys.stderr)
        return 1
    any_leak = False
    total = 0
    for d in dirs:
        gt = json.loads((d / "ground-truth-bugs.json").read_text(encoding="utf-8"))

        manifest_path = d / "manifest.json"
        manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest_path.exists() else None)
        integrity = gt_integrity_violations(gt, manifest)
        if integrity:
            any_leak = True
            print(f"GROUND-TRUTH INTEGRITY VIOLATION in {d.relative_to(ROOT)}:")
            for v in integrity:
                print(f"  {v}")

        prov_path = d / "ground-truth-bugs.provenance.md"
        if not prov_path.exists():
            print(f"[fatal] {d.relative_to(ROOT)} has ground-truth-bugs.json but no "
                  f"ground-truth-bugs.provenance.md (the blind input is unverifiable)",
                  file=sys.stderr)
            any_leak = True
            continue
        strings = withheld_strings(gt)
        total += len(strings)
        text = prov_path.read_text(encoding="utf-8")
        found = leaks(text, strings)
        if found:
            any_leak = True
            print(f"GROUND-TRUTH BLIND BOUNDARY LEAKED in "
                  f"{prov_path.relative_to(ROOT)}:")
            for needle, kind in found:
                print(f"  withheld {kind} present: {needle[:80]!r}")
    if any_leak:
        print("\nThe provenance artifact must contain only the feature description + "
              "factual codebase context fed to the blind author — none of the "
              "ground-truth-bugs.json signature tokens or desc strings. And each "
              "fixture's GT must satisfy the COMPLETE schema: bugs is a list of dicts; "
              "every bug has its required fields present and correctly typed "
              "(bug_id/file non-empty str, line_lo/line_hi int with line_lo<=line_hi), a "
              "non-empty string signature, and a bool off_axis where present; bug_ids "
              "are unique and consistent with the manifest n/bug_ids. A violation means "
              "the recorded run may be scored against a biased or corrupt oracle "
              "(design #373).")
        return 1
    print(f"OK — {len(dirs)} fixture(s); provenance contains none of the {total} "
          "withheld signature/desc strings; the blind boundary held; every GT is a "
          "list of dict bugs with unique bug_ids consistent with each manifest, every "
          "required field present and correctly typed (bug_id/file non-empty str, "
          "line_lo<=line_hi ints), a non-empty string signature, and a bool off_axis "
          "where present.")
    return 0


def selftest() -> int:
    """Built-in logic tests (in-memory) for the substring leak scan."""
    gt = {"bugs": [
        {"signature": ["off-by-one", "Slice"], "desc": "drops the final element"},
    ]}
    strings = withheld_strings(gt)
    clean = ("## Feature under review\nA helper returning recent items.\n"
             "## Task\nReview for defects.\n")
    leaky_sig = clean + "There is an off-by-one here.\n"
    leaky_sig_case = clean + "A SLICE bug lurks.\n"   # case-insensitive signature
    leaky_desc = clean + "It drops the final element.\n"
    cases = [
        (clean, False, "feature/context only → no leak"),
        (leaky_sig, True, "a signature token in the provenance is caught"),
        (leaky_sig_case, True, "signature match is case-insensitive"),
        (leaky_desc, True, "a desc string in the provenance is caught"),
    ]
    failures = []
    for text, expect_fail, reason in cases:
        got = bool(leaks(text, strings))
        if got != expect_fail:
            failures.append(f"  expected leak={expect_fail} ({reason}), got={got}")
    # GT-integrity legs (in-memory; no real broken fixture added to the tree).
    # A fully clean bug carries every required field, a non-empty signature, and a
    # bool off_axis — the broadened check must pass it untouched.
    def _bug(**over):
        base = {"bug_id": "x1", "file": "a.py", "line_lo": 5, "line_hi": 5,
                "signature": ["a"], "desc": "d1", "off_axis": False}
        base.update(over)
        return base
    clean_gt = {"bugs": [_bug(), _bug(bug_id="x2", signature=["b"], desc="d2")]}
    clean_manifest = {"n": 2, "bug_ids": ["x1", "x2"]}
    dup_gt = {"bugs": [_bug(), _bug(signature=["b"], desc="d2")]}
    mismatch_manifest_n = {"n": 3, "bug_ids": ["x1", "x2"]}
    mismatch_manifest_ids = {"n": 2, "bug_ids": ["x1", "x9"]}
    # Each seeds exactly one malformation the complete-schema check must name.
    empty_sig_gt = {"bugs": [_bug(signature=[])]}
    missing_sig_gt = {"bugs": [{k: v for k, v in _bug().items() if k != "signature"}]}
    blank_sig_gt = {"bugs": [_bug(signature=[""])]}        # [""] substring-matches all
    missing_field_gt = {"bugs": [{k: v for k, v in _bug().items() if k != "line_lo"}]}
    str_off_axis_gt = {"bugs": [_bug(off_axis="false")]}
    inverted_range_gt = {"bugs": [_bug(line_lo=60, line_hi=40)]}
    str_line_gt = {"bugs": [_bug(line_lo="10")]}           # matcher would TypeError
    none_line_gt = {"bugs": [_bug(line_lo=None)]}          # matcher would TypeError
    float_line_gt = {"bugs": [_bug(line_lo=10.0)]}         # latent: passed AND matched
    int_file_gt = {"bugs": [_bug(file=123)]}               # matcher would AttributeError
    empty_file_gt = {"bugs": [_bug(file="")]}
    nonlist_bugs_gt = {"bugs": "not-a-list"}               # would crash the per-bug loop
    nondict_bug_gt = {"bugs": ["not-a-dict", _bug()]}      # would crash .get on element
    missing_bugs_gt = {}                                   # no 'bugs' key
    # R5-S1: non-string desc — validator names it AND the leak scan must not raise.
    list_desc_gt = {"bugs": [_bug(desc=["a", "b"])]}       # leaks() crashed on this
    num_desc_gt = {"bugs": [_bug(desc=123)]}
    # R5-M3: a non-str signature token passes the "≥1 usable" rule yet overmatches.
    nonstr_sig_tok_gt = {"bugs": [_bug(signature=["ok", 123])]}
    integrity_cases = [
        # (gt, manifest, expect_violation, anchor_substr, reason)
        (clean_gt, clean_manifest, False, None,
         "fully clean bug (typed fields, line_lo<=line_hi, str sig, bool off_axis) → clean"),
        (clean_gt, None, False, None,
         "no manifest → per-bug + uniqueness checks still pass"),
        (dup_gt, clean_manifest, True, "duplicate bug_id",
         "a duplicate bug_id is caught"),
        (clean_gt, mismatch_manifest_n, True, "!= len(bugs)",
         "a manifest n mismatch is caught"),
        (clean_gt, mismatch_manifest_ids, True, "!= GT bug_ids",
         "a manifest bug_ids mismatch is caught"),
        (empty_sig_gt, None, True, "signature",
         "an empty signature is caught (bug could never match)"),
        (missing_sig_gt, None, True, "signature",
         "a missing signature key is caught"),
        (blank_sig_gt, None, True, "signature",
         "a [''] blank-only signature is caught (would substring-match everything)"),
        (missing_field_gt, None, True, "line_lo",
         "a missing required field (line_lo) is caught"),
        (str_off_axis_gt, None, True, "off_axis",
         "a string off_axis (not bool) is caught"),
        # R4-S1: inverted/transposed range — the Significant.
        (inverted_range_gt, None, True, "inverted range",
         "an inverted range line_lo>line_hi is caught (R4-S1)"),
        # R4-M1: wrong-type fields the presence-only check missed.
        (str_line_gt, None, True, "line_lo",
         "a str line_lo (matcher TypeError) is caught as a type violation"),
        (none_line_gt, None, True, "line_lo",
         "a None line_lo (matcher TypeError) is caught as a type violation"),
        (float_line_gt, None, True, "line_lo",
         "a float line_lo (latent laxness — passed AND matched) is caught"),
        (int_file_gt, None, True, "file",
         "an int file (matcher AttributeError) is caught as a type violation"),
        (empty_file_gt, None, True, "file",
         "an empty-string file is caught"),
        # R4-M1: the validator itself must be total — never raise on a bad container.
        (nonlist_bugs_gt, None, True, "not a list",
         "a non-list 'bugs' is caught (validator does not raise)"),
        (nondict_bug_gt, None, True, "not a dict",
         "a non-dict bug element is caught (validator does not raise)"),
        (missing_bugs_gt, None, True, "missing required key 'bugs'",
         "a GT with no 'bugs' key is caught"),
        # R5-S1: a non-string desc — validator names it (totality guard + the leak-scan
        # no-raise assertion below cover the runtime path).
        (list_desc_gt, None, True, "desc",
         "a list desc is caught (R5-S1; leaks() would otherwise TypeError)"),
        (num_desc_gt, None, True, "desc",
         "a numeric desc is caught (R5-S1)"),
        # R5-M3: a non-str signature token (latent str()-coerce overmatch).
        (nonstr_sig_tok_gt, None, True, "signature token",
         "a non-str signature token is caught (R5-M3; latent str()-coerce overmatch)"),
    ]
    for gt_c, man_c, expect_violation, anchor, reason in integrity_cases:
        try:
            viols = gt_integrity_violations(gt_c, man_c)
        except Exception as e:  # the validator must be total — a raise is a failure.
            failures.append(
                f"  gt_integrity_violations RAISED {type(e).__name__}: {e} ({reason})")
            continue
        if bool(viols) != expect_violation:
            failures.append(
                f"  expected violation={expect_violation} ({reason}), got={viols}")
        elif anchor is not None and not any(anchor in v for v in viols):
            # Non-vacuous: the mutation we seeded must produce a violation naming it.
            failures.append(
                f"  violation present but anchor {anchor!r} missing ({reason}): {viols}")

    # R5-S1 runtime path: even bypassing the validator, withheld_strings()/leaks() on a
    # non-string desc must NOT raise (belt-and-suspenders for the provenance scan).
    for gt_c, reason in [(list_desc_gt, "list desc"), (num_desc_gt, "numeric desc"),
                         (nonstr_sig_tok_gt, "non-str signature token")]:
        try:
            leaks("some provenance text", withheld_strings(gt_c))
        except Exception as e:
            failures.append(
                f"  withheld_strings/leaks RAISED {type(e).__name__}: {e} "
                f"({reason} — R5-S1 robustness)")
    # And a clean bug with a valid string desc + all-string signature actually leaks
    # those very strings when the provenance contains them (the scan still works).
    valid_desc_gt = {"bugs": [_bug(desc="a unique sentinel desc",
                                   signature=["uniquesig"])]}
    try:
        hit = leaks("text mentions uniquesig and a unique sentinel desc here",
                    withheld_strings(valid_desc_gt))
        kinds = {k for _, k in hit}
        if kinds != {"signature", "desc"}:
            failures.append(
                f"  valid string desc/sig leak scan caught {kinds}, expected "
                f"{{'signature', 'desc'}}")
    except Exception as e:
        failures.append(
            f"  valid-desc leak scan RAISED {type(e).__name__}: {e}")

    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — the leak scan fires on a seeded signature token "
          "(case-insensitively) and a desc string, passes a "
          "feature-plus-context-only provenance, and the GT-integrity check is a total, "
          "complete-schema validator: it catches a duplicate bug_id, manifest n/bug_ids "
          "mismatch, missing/empty/blank/non-list signature, missing required field, "
          "wrong-typed fields (str/None/float line, int/empty file), an inverted range "
          "(R4-S1), a non-string desc (R5-S1) and a non-str signature token (R5-M3), a "
          "string off_axis, and a non-list 'bugs' / non-dict element / missing 'bugs' "
          "key — all WITHOUT raising — while the provenance leak scan itself never "
          "raises on a non-string desc/sig token yet still leaks valid string "
          "desc/sig needles; a fully clean fixture passes untouched.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
