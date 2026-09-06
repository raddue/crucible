#!/usr/bin/env python3
"""Codified Step 12.3 contract-coverage sweep (#577, #566, #578).

Invocation (from repo root):
    python3 scripts/check_contract_tags.py            # gate the real repo
    python3 scripts/check_contract_tags.py --selftest # fixture-driven logic test

Until this script existed the sweep was a shell fence pasted out of
`docs/plans/2026-08-28-558-559-crap-grudge-implementation-plan.md` ("Step 12.3:
Contract coverage sweep"). It ran only when a human remembered to paste it, and
five of its assertions could not fail. Measured against the tree at the time of
writing, with the fence's `1 + checks` loop generalised in its favour so the
pre-existing multi-marker break did not mask anything:

  * delete a `check` call AND decrement its inline `checks=` marker  -> fence rc 0
  * rename a carrier file (grep contributes zero matches)            -> fence rc 0
  * add a `contract:foo:inv-t99` tag the contract never declared     -> fence rc 0
  * delete a `test_tag:` from the contract YAML                      -> fence rc 0
  * make `3193271` unresolvable (shallow clone)                      -> fence rc 0

Each of those is a mutant this script turns red. What it checks:

  1. **Carrier existence.** Every path in `COVERAGE_MAP` must exist as a regular
     file BEFORE anything is counted. The fence grepped a hardcoded list, so a
     renamed carrier contributed zero matches and the sweep stayed green.
  2. **Three-way tag-set identity.** The set of `test_tag:` values declared by
     the contract YAML, the set of tags actually carried by the carrier files,
     and the set of tags pinned in `COVERAGE_MAP` must be identical. Both
     directions of every difference are reported separately: *declared but never
     carried* (an invariant with no test) and *carried but never declared* (a
     typo that today silently counts toward coverage). The headline count is
     asserted against `len(COVERAGE_MAP)`, not printed as a comment.
     `docs/plans/` is gitignored, so the contract YAML is machine-local: where
     it is absent the map-vs-carriers half still runs in full and the stand-down
     of the upstream half is printed as a NOTE. See `declared_tags`.
  3. **Stray tags.** A `contract:*:inv-t*` tag anywhere under the code trees
     that is NOT in a declared carrier is an error — a tag moved to a file the
     sweep does not read is coverage that silently stopped being measured.
  4. **The `n_markers + sum(checks)` arithmetic** the fence encoded as
     `1 + checks`, generalised: `contract:hook:inv-t22` and `contract:hook:inv-t23`
     legitimately carry more than one annotated scenario, and the fence's literal
     one-marker loop mis-fires on them (verified: it reports
     `MISMATCH: contract:hook:inv-t22 expected 13 got 22` against a clean tree).
     Also preserved: the absence assertion — every distinct bash tag must carry a
     `checks=` annotation, so an unannotated scenario fails loudly instead of
     matching nothing.
  5. **The authoritative map (#566).** `checks=N` lives inline next to the checks
     it counts, so deleting a check and decrementing the annotation in the same
     edit passes. `COVERAGE_MAP` pins the expected count per tag OUTSIDE the file
     being counted; the inline annotations must sum to it and disagreement in
     either direction is an error. Lowering coverage now requires a deliberate
     edit to the map.
  6. **INV-C10** (#578) — see `check_no_merge_grudge_writer` and
     `check_merge_pr_untouched` below.

### Scope limit on "the test really pins its invariant" (read this)

Requirement 5 of this sweep is **assertion presence, not assertion efficacy**.
Task 12's mutation pass found four tagged invariants — INV-T1, INV-T6, INV-T7,
INV-C2 — whose tests survived mutation of the very behaviour they claimed to
pin. This script does NOT catch those and cannot: proving statically that an
assertion constrains a particular behaviour is the halting problem wearing a
hat. What it does check is the weaker, decidable property that a tag is backed
by at least one real assertion construct rather than by a comment and a
docstring token alone:

  * bash: at least one line whose command is `check` and which names the tag;
  * python: at least one `assert` statement or `self.assert*` call inside every
    test function whose docstring carries the tag.

Of the four, only three are even in scope: INV-C2 is declared
`check_method: code-inspection` with no `test_tag`, so it is not part of the tag
set at all and no tag-based sweep can reach it. The other three do carry real
assertions and pass this check. **Read a green run as "every declared invariant
has a tagged test that asserts something", never as "every declared invariant is
pinned".** Mutation testing is the instrument for the stronger claim.

Style mirrors `scripts/check_claude_settings.py` / `scripts/check_stdlib_only.py`:
ROOT-from-`__file__`, error accumulation, `sys.exit(main())`, stdlib only (the
contract YAML is parsed for the one construct this needs — `test_tag:` scalars —
rather than pulling in PyYAML), no argparse. Exit codes are `0` (ok) or `1` (any
failure, including unknown argv). Every checker takes an explicit `root` and an
explicit map, so `--selftest` drives the SAME code paths the bare run does
against throwaway fixture trees, covering the PASS and the FAIL shape of each.

No temp file is used for the tag counts: the fence's fixed `/tmp/qg-tagcounts.txt`
(a shared path a co-tenant can pre-create) is replaced by an in-process dict.
`--selftest` builds its fixture trees with `tempfile.mkdtemp()`.
"""

from __future__ import annotations

import ast
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONTRACT_YAML = "docs/plans/2026-08-28-558-559-crap-grudge-contract.yaml"

# The one Path-A-adjacent artifact INV-C10 names by path, plus the commit the
# merge-pr/SKILL.md Step 7.5 fence must be unchanged since.
MERGE_PR_SKILL = "skills/merge-pr/SKILL.md"
INV_C10_BASE_SHA = "3193271"

TAG_RE = re.compile(r"contract:[a-z]+:inv-t[0-9]+")
ANNOT_RE = re.compile(r"(contract:[a-z]+:inv-t[0-9]+)[ \t]+checks=([0-9]+)")
MARKER_RE = re.compile(r"^[ \t]*#[ \t]*(contract:[a-z]+:inv-t[0-9]+)\b")
TEST_TAG_RE = re.compile(r'^\s*test_tag:\s*"(contract:[a-z]+:inv-t[0-9]+)"\s*$')

# --- The Contract Coverage Map (#566) --------------------------------------
# THE AUTHORITATIVE SIDE. `checks` is the expected total number of tagged
# `check` calls for a bash tag; `tests` is the expected number of tagged test
# functions for a python tag. Both live here, deliberately outside the file
# being counted, so that lowering coverage requires editing this map and not
# just nudging an inline annotation. Numbers were MEASURED against the tree,
# never copied out of the plan document.
COVERAGE_MAP: dict[str, dict] = {
    # --- python carriers (#558 complexity signal) ---
    "contract:cc:inv-t1": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:floor:inv-t2": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:qualname:inv-t3": {
        "kind": "python",
        "carriers": ["scripts/test_brier_advise.py", "scripts/test_complexity_index.py"],
        "tests": 2,
    },
    "contract:paths:inv-t4": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:order:inv-t5": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:nesting:inv-t6": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:diffscope:inv-t7": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:diffscope:inv-t8": {"kind": "python", "carriers": ["scripts/test_brier_advise.py"], "tests": 1},
    "contract:calibration:inv-t9": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 1},
    "contract:isolation:inv-t10": {"kind": "python", "carriers": ["scripts/test_complexity_index.py"], "tests": 2},
    "contract:cli:inv-t11": {"kind": "python", "carriers": ["scripts/test_brier_advise.py"], "tests": 1},
    # --- bash carrier (#559 Stop-hook seam suite) ---
    "contract:hook:inv-t12": {"kind": "bash", "carriers": [_G := "hooks/tests/test-grudge-resolution-guard.sh"], "checks": 16},
    "contract:hook:inv-t13": {"kind": "bash", "carriers": [_G], "checks": 6},
    "contract:hook:inv-t14": {"kind": "bash", "carriers": [_G], "checks": 26},
    "contract:match:inv-t15": {"kind": "bash", "carriers": [_G], "checks": 6},
    "contract:match:inv-t16": {"kind": "bash", "carriers": [_G], "checks": 13},
    "contract:match:inv-t17": {"kind": "bash", "carriers": [_G], "checks": 4},
    "contract:skip:inv-t18": {"kind": "bash", "carriers": [_G], "checks": 7},
    "contract:group:inv-t19": {"kind": "bash", "carriers": [_G], "checks": 51},
    "contract:group:inv-t20": {"kind": "bash", "carriers": [_G], "checks": 13},
    "contract:group:inv-t21": {"kind": "bash", "carriers": [_G], "checks": 45},
    "contract:hook:inv-t22": {"kind": "bash", "carriers": [_G], "checks": 19},
    "contract:hook:inv-t23": {"kind": "bash", "carriers": [_G], "checks": 93},
    "contract:hook:inv-t24": {"kind": "bash", "carriers": [_G], "checks": 22},
    "contract:worktree:inv-t25": {"kind": "bash", "carriers": [_G], "checks": 20},
    "contract:cli:inv-t26": {"kind": "bash", "carriers": [_G], "checks": 7},
    "contract:cli:inv-t27": {"kind": "bash", "carriers": [_G], "checks": 7},
}
del _G

# Code trees swept for stray tags. `docs/` is excluded on purpose: the plan and
# the contract quote these tags as prose. This file is excluded because its map
# IS the authority — it names every tag by construction.
STRAY_SCAN_DIRS = ("scripts", "hooks", "eval", "skills", "agents", "mcp-servers")
STRAY_SELF = "scripts/check_contract_tags.py"


def carrier_paths(coverage_map: dict) -> list[str]:
    """Every carrier named by the map, deduplicated, in stable order."""
    seen: list[str] = []
    for spec in coverage_map.values():
        for path in spec["carriers"]:
            if path not in seen:
                seen.append(path)
    return sorted(seen)


# --- 1. carrier existence ---------------------------------------------------


def check_carriers_exist(root: Path, coverage_map: dict, errors: list[str]) -> bool:
    """Every carrier must exist as a regular file before anything is counted.

    The fence grepped a hardcoded list; a renamed carrier made grep contribute
    zero matches to every downstream count and the sweep still passed.
    """
    ok = True
    for rel in carrier_paths(coverage_map):
        path = root / rel
        if not path.is_file():
            errors.append(
                f"carrier file missing or renamed: {rel} — the coverage map names it, "
                f"but no regular file exists at that path. Update COVERAGE_MAP's "
                f"'carriers' if the rename was deliberate."
            )
            ok = False
    return ok


# --- 2. the three tag sets --------------------------------------------------


def declared_tags(
    root: Path, contract_rel: str, errors: list[str], notes: list[str]
) -> tuple[set[str], bool]:
    """(`test_tag:` scalars declared by the contract YAML, whether it was present).

    Parsed with a line regex rather than a YAML library: `scripts/check_stdlib_only.py`
    gates parts of this tree to the stdlib and the construct needed here is a
    flat quoted scalar. A `test_tag:` line the regex cannot read is reported,
    so a reformat cannot silently shrink the declared set.

    `docs/plans/` is gitignored in this repo, so the contract YAML is a
    machine-local artifact: it is present where the plan was authored and absent
    in CI and in every fresh clone. Its absence is therefore REPORTED (a NOTE on
    stdout naming the path) and the upstream cross-check stands down — it is not
    an error, because the file is not supposed to be there. This does not
    reintroduce the vacuity #577 was filed for: `COVERAGE_MAP` is the committed
    projection of that YAML and the map-vs-carriers identity is enforced
    unconditionally, everywhere. What degrades without the YAML is only the
    redundant check that the committed projection still matches its upstream.
    A YAML that IS present but yields no `test_tag:` at all is an error, so a
    truncated or reformatted file cannot masquerade as a satisfied cross-check.
    """
    path = root / contract_rel
    if not path.is_file():
        notes.append(
            f"contract YAML not present ({contract_rel}) — `docs/plans/` is gitignored, so "
            f"the upstream test_tag cross-check did not run. COVERAGE_MAP vs carriers was "
            f"still enforced in full."
        )
        return set(), False
    tags: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "test_tag:" not in line:
            continue
        m = TEST_TAG_RE.match(line)
        if not m:
            errors.append(
                f"{contract_rel}:{lineno}: unparseable test_tag line — expected "
                f'`test_tag: "contract:<category>:<id>"`, got: {line.strip()}'
            )
            continue
        tags.add(m.group(1))
    if not tags:
        errors.append(
            f"{contract_rel}: exists but declares no parseable `test_tag:` at all — a present "
            f"contract must not read as a satisfied cross-check by being empty"
        )
    return tags, True


def carried_tags(root: Path, coverage_map: dict) -> dict[str, dict[str, int]]:
    """{tag: {carrier_rel: occurrence_count}} across the declared carriers."""
    found: dict[str, dict[str, int]] = {}
    for rel in carrier_paths(coverage_map):
        path = root / rel
        if not path.is_file():
            continue
        for tag in TAG_RE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(tag, {}).setdefault(rel, 0)
            found[tag][rel] += 1
    return found


def check_tag_sets(
    declared: set[str], declared_available: bool, carried: set[str],
    coverage_map: dict, errors: list[str],
) -> None:
    """Declared, carried and mapped tag sets must be identical.

    Both directions are reported separately and both must be empty. Counting
    occurrences (what the fence did) cannot see either failure.

    map-vs-carriers runs always. The two comparisons that need the contract YAML
    run only when it is present — see `declared_tags` for why that is a reported
    stand-down and not a silent skip.
    """
    mapped = set(coverage_map)
    for tag in sorted(mapped - carried):
        errors.append(
            f"tag-set mismatch: {tag} is pinned in COVERAGE_MAP but no carrier file "
            f"carries it — removing coverage is a deliberate edit to the map (#566)"
        )
    for tag in sorted(carried - mapped):
        errors.append(
            f"tag-set mismatch: {tag} appears in the carrier files but COVERAGE_MAP does "
            f"not pin it — an unpinned tag counts toward coverage while asserting nothing "
            f"anyone declared (usually a typo)"
        )
    if not declared_available:
        return
    for label, missing_from, extra in (
        ("contract YAML", "no test carries it", sorted(declared - carried)),
        ("carrier files", "the contract YAML does not declare it", sorted(carried - declared)),
    ):
        for tag in extra:
            errors.append(f"tag-set mismatch: {tag} appears in the {label} but {missing_from}")
    for tag in sorted(declared - mapped):
        errors.append(
            f"coverage-map gap: {tag} is declared by the contract YAML but is not pinned "
            f"in COVERAGE_MAP — add it (adding coverage must be as deliberate as removing it)"
        )
    for tag in sorted(mapped - declared):
        errors.append(
            f"coverage-map stale: {tag} is pinned in COVERAGE_MAP but the contract YAML "
            f"no longer declares it"
        )


def check_carrier_placement(
    carried: dict[str, dict[str, int]], coverage_map: dict, errors: list[str]
) -> None:
    """Each tag must appear in exactly the carriers its map entry names."""
    for tag, spec in sorted(coverage_map.items()):
        want = set(spec["carriers"])
        got = set(carried.get(tag, {}))
        for rel in sorted(want - got):
            errors.append(f"{tag}: COVERAGE_MAP names carrier {rel}, but the tag does not appear there")
        for rel in sorted(got - want):
            errors.append(f"{tag}: appears in {rel}, which COVERAGE_MAP does not name as a carrier")


# --- 3. stray tags outside the declared carriers ----------------------------


def check_no_stray_tags(root: Path, coverage_map: dict, errors: list[str]) -> None:
    """A contract tag in a code file that is not a declared carrier is an error."""
    carriers = set(carrier_paths(coverage_map))
    for top in STRAY_SCAN_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for name in sorted(filenames):
                path = Path(dirpath) / name
                rel = path.relative_to(root).as_posix()
                if rel in carriers or rel == STRAY_SELF:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                strays = sorted(set(TAG_RE.findall(text)))
                if strays:
                    errors.append(
                        f"{rel}: carries contract tag(s) {', '.join(strays)} but is not a "
                        f"declared carrier — coverage measured there is invisible to this sweep"
                    )


# --- 4/5. bash arithmetic, the absence assertion, and the authoritative map --


def _marker_lines(text: str) -> list[tuple[int, str, int | None]]:
    """(lineno, tag, checks_or_None) for every `# contract:...` comment marker."""
    out: list[tuple[int, str, int | None]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = MARKER_RE.match(line)
        if not m:
            continue
        annot = ANNOT_RE.search(line)
        out.append((lineno, m.group(1), int(annot.group(2)) if annot else None))
    return out


def _bash_check_lines(text: str) -> list[tuple[int, str, list[str]]]:
    """(lineno, line, tags) for every line whose command word is `check`."""
    out: list[tuple[int, str, list[str]]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.match(r"^[ \t]*check[ \t]", line):
            out.append((lineno, line, TAG_RE.findall(line)))
    return out


def check_bash_carrier(root: Path, rel: str, coverage_map: dict, errors: list[str]) -> None:
    """Preserve the fence's arithmetic, then pin it against COVERAGE_MAP.

    * occurrences == markers + tagged `check` calls, per tag (the fence's
      `1 + checks`, generalised to the multi-marker tags it mis-fires on);
    * every distinct bash tag carries at least one `checks=` annotation and
      EVERY marker for it does (the fence's absence assertion);
    * the inline annotations sum to COVERAGE_MAP's pinned count (#566) — the
      half the fence structurally cannot have, since its expectation sat in the
      file it was measuring;
    * at least one tagged `check` call exists (assertion presence — see the
      module docstring's scope limit).
    """
    text = (root / rel).read_text(encoding="utf-8")
    bash_tags = {t for t, s in coverage_map.items() if s["kind"] == "bash" and rel in s["carriers"]}

    markers = _marker_lines(text)
    checks = _bash_check_lines(text)

    occurrences: dict[str, int] = {}
    for tag in TAG_RE.findall(text):
        occurrences[tag] = occurrences.get(tag, 0) + 1

    for tag in sorted(bash_tags):
        tag_markers = [m for m in markers if m[1] == tag]
        tag_checks = [c for c in checks if tag in c[2]]
        annotated = [m for m in tag_markers if m[2] is not None]

        if not tag_markers:
            errors.append(f"{rel}: {tag} has no `# {tag} checks=N` comment marker")
            continue
        # The absence assertion: an unannotated scenario must fail loudly rather
        # than match nothing and pass.
        for lineno, _tag, ann in tag_markers:
            if ann is None:
                errors.append(
                    f"{rel}:{lineno}: marker for {tag} has no `checks=` annotation — "
                    f"an unannotated scenario contributes nothing to the arithmetic"
                )
        if not annotated:
            continue

        if not tag_checks:
            errors.append(
                f"{rel}: {tag} is tagged but no `check` call names it — a comment marker "
                f"alone asserts nothing"
            )

        want_total = len(tag_markers) + sum(m[2] for m in annotated) + sum(
            0 for m in tag_markers if m[2] is None
        )
        got_total = occurrences.get(tag, 0)
        if got_total != want_total:
            errors.append(
                f"{rel}: {tag} occurrence arithmetic — expected "
                f"{len(tag_markers)} marker(s) + {sum(m[2] for m in annotated)} annotated check(s) "
                f"= {want_total}, measured {got_total}. Either a `check` call lost or gained the "
                f"tag, or the tag is named outside a `check` call."
            )

        inline_sum = sum(m[2] for m in annotated)
        if len(tag_checks) != inline_sum:
            errors.append(
                f"{rel}: {tag} — inline annotations sum to {inline_sum} but "
                f"{len(tag_checks)} `check` call(s) name the tag"
            )

        pinned = coverage_map[tag]["checks"]
        if inline_sum != pinned:
            errors.append(
                f"{rel}: {tag} — COVERAGE_MAP pins checks={pinned} but the inline "
                f"annotation(s) sum to {inline_sum}. Lowering coverage is a deliberate "
                f"edit to COVERAGE_MAP, not an inline tweak (#566)."
            )

    # Any bash tag in the file the map does not know about (caught set-wise too,
    # but reported here with its file for a usable message).
    for tag in sorted(set(occurrences) - bash_tags):
        if coverage_map.get(tag, {}).get("kind") != "python":
            errors.append(f"{rel}: carries {tag}, which COVERAGE_MAP does not pin as a bash tag here")


# --- python carriers: tagged tests must contain a real assertion ------------


def _has_assertion(node: ast.AST) -> bool:
    """True iff the function body contains an `assert` or a `self.assert*` call."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            return True
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                return True
            if isinstance(func, ast.Name) and func.id.startswith("assert"):
                return True
    return False


def check_python_carrier(root: Path, rel: str, coverage_map: dict, errors: list[str]) -> None:
    """Arithmetic + assertion presence for a python carrier.

    Python has no `checks=` annotation; its shape is a `# tag` comment marker
    directly above a test whose docstring repeats the tag. So:
    occurrences == markers + tagged test functions, the tagged-test count is
    pinned by COVERAGE_MAP's `tests`, and every tagged test must contain at
    least one assertion construct (see the docstring's scope limit).
    """
    path = root / rel
    text = path.read_text(encoding="utf-8")
    py_tags = {t for t, s in coverage_map.items() if s["kind"] == "python" and rel in s["carriers"]}

    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        errors.append(f"{rel}: does not parse as python ({exc})")
        return

    docstring_carriers: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        for tag in set(TAG_RE.findall(doc)):
            docstring_carriers.setdefault(tag, []).append(node)

    markers = _marker_lines(text)
    occurrences: dict[str, int] = {}
    for tag in TAG_RE.findall(text):
        occurrences[tag] = occurrences.get(tag, 0) + 1

    for tag in sorted(py_tags):
        tag_markers = [m for m in markers if m[1] == tag]
        tests = docstring_carriers.get(tag, [])

        if not tests:
            errors.append(
                f"{rel}: {tag} has no test function whose docstring carries it — a comment "
                f"marker alone is not a carrier"
            )
            continue

        want_total = len(tag_markers) + len(tests)
        got_total = occurrences.get(tag, 0)
        if got_total != want_total:
            errors.append(
                f"{rel}: {tag} occurrence arithmetic — expected {len(tag_markers)} marker(s) "
                f"+ {len(tests)} tagged test(s) = {want_total}, measured {got_total}"
            )

        for node in tests:
            if not _has_assertion(node):
                errors.append(
                    f"{rel}:{node.lineno}: {tag} is carried by {node.name}, which contains no "
                    f"assert / self.assert* — a docstring token is not an assertion"
                )

    # Tagged-test totals are pinned across all carriers, so compare once, in the
    # first carrier the map lists for the tag.
    for tag in sorted(py_tags):
        spec = coverage_map[tag]
        if spec["carriers"][0] != rel:
            continue
        total = 0
        for other in spec["carriers"]:
            other_path = root / other
            if not other_path.is_file():
                continue
            try:
                other_tree = ast.parse(other_path.read_text(encoding="utf-8"), filename=other)
            except SyntaxError:
                continue
            for node in ast.walk(other_tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and TAG_RE.findall(
                    ast.get_docstring(node) or ""
                ).count(tag):
                    total += 1
        if total != spec["tests"]:
            errors.append(
                f"{tag}: COVERAGE_MAP pins tests={spec['tests']} but {total} tagged test "
                f"function(s) carry it. Lowering coverage is a deliberate edit to COVERAGE_MAP (#566)."
            )


# --- 6. INV-C10 (#578) ------------------------------------------------------
#
# INV-C10: "Path A stays cut: no hooks/grudge-merge-writer.sh exists;
# merge-pr/SKILL.md Step 7.5 remains exactly its existing templated bash fence
# (plugin_root=... + placeholder-valued grudge_append.py), untouched and not
# further automated."
#
# The fence checked this with `test ! -e hooks/grudge-merge-writer.sh` (one
# filename, not the content it stands for) plus a `git diff … | grep` pipeline
# whose exit status is grep's and whose output nothing reads.

# The Step 7.5 fence, pinned verbatim. Clone-independent: this half of the
# INV-C10 check runs in a shallow clone, a tarball, anywhere.
EXPECTED_STEP_75_FENCE = '''# only for fix(*) PRs
plugin_root="$(realpath "<this-skill-base-dir>/../..")"
python3 "$plugin_root/scripts/grudge_append.py" \\
  --symptom "<PR title minus the fix() prefix>" \\
  --root-cause "<from PR body, if stated>" \\
  --files "<comma-separated files the PR changed>" \\
  --commit "<squash/merge SHA>" \\
  --why "<from PR body, if stated>"'''

# The only change INV-C10 permits since INV_C10_BASE_SHA: the one added
# paragraph (plus the blank line separating it). Measured from the real diff.
EXPECTED_ADDED_LINES = [
    "If this step is skipped or fails, Path B's Stop hook "
    "(`grudge-resolution-guard.sh`) will block the session's next Stop event "
    "until a grudge is recorded or explicitly skipped — see `hooks/README.md`.",
    "",
]

# Command words that may precede the real command word in a simple command.
_BASH_PREFIXES = {
    "if", "then", "else", "elif", "do", "while", "until", "!", "exec", "eval",
    "command", "sudo", "env", "time", "nohup",
}
_PY_RUNNERS = {"python", "python3", "python3.12", "uv", "poetry"}


def _executes_grudge_append(text: str) -> list[str]:
    """Lines of a shell script that EXECUTE the grudge writer, if any.

    INV-C10 is about Path A staying cut, not about one filename, so the
    predicate is content-based: does any hook script *run* `grudge_append.py`?
    Deliberately not "does any hook mention it" — `hooks/grudge-resolution-guard.sh`
    legitimately names the script twice (an `APPEND_SCRIPT=` assignment and a
    `printf` that prints a copy-pasteable command for the human), and a
    mention-based predicate would fail on the Path B hook INV-C10 exists to
    protect, and on any unrelated future hook that merely documents the path.

    Detection: backslash continuations are joined first (so the `printf … \\`
    + `"$APPEND_SCRIPT" args` pair reads as the one `printf` command it is),
    comment lines are dropped, variables assigned a grudge_append path become
    aliases, and a hit requires the script (or an alias) in COMMAND position —
    the first word of a simple command, optionally behind a python runner.
    """
    joined = re.sub(r"\\\n[ \t]*", " ", text)
    lines = [ln for ln in joined.splitlines() if not ln.lstrip().startswith("#")]

    aliases = set()
    for line in lines:
        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)=[^\s;]*grudge_append", line):
            aliases.add(m.group(1))

    def _is_writer(token: str) -> bool:
        bare = token.strip("\"'")
        if bare.endswith("grudge_append.py") or bare.endswith("grudge_append"):
            return True
        m = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", bare)
        return bool(m and m.group(1) in aliases)

    hits: list[str] = []
    for line in lines:
        for segment in re.split(r"(?:\|\||&&|[;|&()]|\bthen\b|\bdo\b|\belse\b)", line):
            words = segment.split()
            # `VAR=…` prefixes and bare assignments are not commands: the Path B
            # hook's own `APPEND_SCRIPT="…/grudge_append.py"` must not count.
            while words and (words[0] in _BASH_PREFIXES or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
                words.pop(0)
            if not words:
                continue
            if words[0].strip("\"'") in _PY_RUNNERS:
                words.pop(0)
                while words and words and words[0].startswith("-"):
                    words.pop(0)
            if words and _is_writer(words[0]):
                hits.append(line.strip())
                break
    return hits


def check_no_merge_grudge_writer(root: Path, errors: list[str]) -> None:
    """No hook writes grudges — whatever it is named, wherever it sits (INV-C10, #578).

    Scope, stated exactly, because this docstring used to claim more than the
    code did: every regular file under `hooks/` — any name, any suffix, any
    depth — except those under `hooks/tests/`, is read as shell text and run
    through `_executes_grudge_append`. `hooks/tests/` is excluded on purpose: a
    test is not a hook and may legitimately drive the writer to seed a fixture.
    Files that are not valid UTF-8 are skipped (nothing this predicate can read).

    The limit, also stated exactly: the predicate is SHELL-command-shaped — it
    finds an invocation whose command word is the writer script or a shell
    variable aliased to it, which is the shape of every hook in this repo. A
    hook written in another language that reaches the writer through a language
    API (Python `subprocess.run([...])`, node `execFile`) is NOT detected. That
    is a real gap, deliberately left open rather than papered over: the honest
    reading of a green run is "no shell hook executes the grudge writer".
    """
    legacy = root / "hooks" / "grudge-merge-writer.sh"
    if legacy.exists():
        errors.append("INV-C10: hooks/grudge-merge-writer.sh exists — Path A was uncut")

    hooks_dir = root / "hooks"
    if not hooks_dir.is_dir():
        return
    tests_dir = hooks_dir / "tests"
    for path in sorted(hooks_dir.rglob("*")):
        if not path.is_file() or tests_dir in path.parents:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = _executes_grudge_append(text)
        if hits:
            errors.append(
                f"INV-C10: {rel} executes the grudge writer ({hits[0]!r}) — Path A is "
                f"'a hook records the grudge', and it stays cut regardless of the hook's "
                f"name, suffix or location under hooks/"
            )


def check_merge_pr_untouched(root: Path, base_sha: str, errors: list[str]) -> None:
    """merge-pr/SKILL.md Step 7.5 is unchanged since `base_sha` (INV-C10, #578).

    Two independent halves, because each covers the other's blind spot:

    * a clone-independent content pin of the Step 7.5 fence in the working tree
      (works in a shallow clone, a tarball, an export);
    * the `base_sha`-to-WORKING-TREE diff, asserted rather than printed — and guarded, so an
      unresolvable `base_sha` is a LOUD failure instead of the silent no-op the
      original pipeline degraded to. CI clones shallow by default
      (`actions/checkout@v4` without `fetch-depth`), which is exactly why the
      original check was vacuous there; `.github/workflows/ci.yml` now sets
      `fetch-depth: 0` so this assertion is real in CI too.

    Both halves end at the same state — the working tree — on purpose: with the
    diff half ending at HEAD instead, an uncommitted edit outside the fence
    passed both halves, which is the state this suite normally runs in.
    """
    skill = root / MERGE_PR_SKILL
    if not skill.is_file():
        errors.append(f"INV-C10: {MERGE_PR_SKILL} is missing")
        return

    text = skill.read_text(encoding="utf-8")
    m = re.search(r"^### Step 7\.5:.*?^```bash\n(.*?)^```", text, re.S | re.M)
    if not m:
        errors.append(
            f"INV-C10: could not locate the Step 7.5 ```bash fence in {MERGE_PR_SKILL} — "
            f"the step was renamed, reformatted, or removed"
        )
    elif m.group(1).rstrip("\n") != EXPECTED_STEP_75_FENCE:
        errors.append(
            f"INV-C10: {MERGE_PR_SKILL} Step 7.5's bash fence differs from the pinned "
            f"templated form. INV-C10 requires it untouched and not further automated.\n"
            f"    measured: {m.group(1).rstrip()!r}"
        )

    git_dir = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-dir"],
        capture_output=True, text=True,
    )
    if git_dir.returncode != 0:
        errors.append(
            f"INV-C10: {root} is not a git checkout, so the Step 7.5 history assertion "
            f"cannot run. This is a failure, not a skip — the check that voids quietly is "
            f"the defect #578 was filed for."
        )
        return

    present = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{base_sha}^{{commit}}"],
        capture_output=True, text=True,
    )
    if present.returncode != 0:
        errors.append(
            f"INV-C10: base commit {base_sha} is not present in this clone, so the "
            f"Step 7.5 history assertion cannot run. This is a LOUD failure, not a skip "
            f"(#578): a shallow clone previously made it a silent no-op. "
            f"Fix with `git fetch --unshallow` (CI sets fetch-depth: 0)."
        )
        return

    # `<base> --` (no `..HEAD`): the diff ends at the WORKING TREE, the same
    # state the fence pin above reads. With `..HEAD` the two halves read two
    # different states and an UNCOMMITTED edit outside the fence passed both —
    # pre-commit being exactly when this suite is normally run.
    # `--no-color --no-ext-diff`: a `color.ui = always` / `diff.external` in the
    # developer's global config would otherwise leave no line starting with `+`,
    # and the gating suite would fail with a bogus INV-C10 error.
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--no-color", "--no-ext-diff", base_sha,
         "--", MERGE_PR_SKILL],
        capture_output=True, text=True,
    )
    if diff.returncode != 0:
        errors.append(f"INV-C10: `git diff {base_sha} -- {MERGE_PR_SKILL}` failed: {diff.stderr.strip()}")
        return

    # Hunk-anchored, NOT prefix-filtered: a removed line whose own text starts
    # with `--` renders as `---…`, so dropping every line that starts with `---`
    # discarded exactly the removals this file is full of (its `---` frontmatter
    # fences). Header lines are skipped by position instead — everything before
    # the first `@@` of a file's hunks.
    added, removed = [], []
    in_hunk = False
    for line in diff.stdout.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])

    if removed:
        errors.append(
            f"INV-C10: {MERGE_PR_SKILL} has {len(removed)} REMOVED line(s) since {base_sha}; "
            f"INV-C10 permits none. First: {removed[0]!r}"
        )
    if added != EXPECTED_ADDED_LINES:
        errors.append(
            f"INV-C10: {MERGE_PR_SKILL} added lines since {base_sha} are not the one "
            f"permitted paragraph.\n    expected: {EXPECTED_ADDED_LINES!r}\n"
            f"    measured: {added!r}"
        )


# --- orchestration ----------------------------------------------------------


def run_checks(root: Path, coverage_map: dict = COVERAGE_MAP, contract_rel: str = CONTRACT_YAML,
               base_sha: str = INV_C10_BASE_SHA, git_checks: bool = True,
               notes: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    if notes is None:
        notes = []

    if not check_carriers_exist(root, coverage_map, errors):
        # Counting against a tree with a missing carrier produces a cascade of
        # meaningless arithmetic errors; the missing path IS the finding.
        return errors

    declared, declared_available = declared_tags(root, contract_rel, errors, notes)
    carried = carried_tags(root, coverage_map)
    check_tag_sets(declared, declared_available, set(carried), coverage_map, errors)
    check_carrier_placement(carried, coverage_map, errors)
    check_no_stray_tags(root, coverage_map, errors)

    for rel in carrier_paths(coverage_map):
        kinds = {s["kind"] for t, s in coverage_map.items() if rel in s["carriers"]}
        if "bash" in kinds:
            check_bash_carrier(root, rel, coverage_map, errors)
        if "python" in kinds:
            check_python_carrier(root, rel, coverage_map, errors)

    check_no_merge_grudge_writer(root, errors)
    if git_checks:
        check_merge_pr_untouched(root, base_sha, errors)
    return errors


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--selftest":
        return selftest()
    if len(argv) > 1:
        print(f"usage: {Path(argv[0]).name} [--selftest]", file=sys.stderr)
        return 1

    notes: list[str] = []
    errors = run_checks(ROOT, notes=notes)
    for note in notes:
        print(f"NOTE: {note}")
    if errors:
        print(f"FAIL — {len(errors)} contract-coverage problem(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK — contract coverage: {len(COVERAGE_MAP)} tags, all carried and pinned")
    return 0


# --- selftest ---------------------------------------------------------------
#
# Fixture-driven. Every assertion above gets both a PASS and a FAIL fixture, so
# no enforcement branch can be mutated into a no-op without a failure here. The
# fixtures are the mutants from #577/#566/#578, frozen.

_FIX_YAML = """\
  testable:
    - id: "INV-T1"
      description: "d"
      test_tag: "contract:aa:inv-t1"
    - id: "INV-T2"
      description: "d"
      test_tag: "contract:bb:inv-t2"
"""

_FIX_BASH = """\
#!/usr/bin/env bash
check() { :; }

# contract:aa:inv-t1 checks=2
check 1 "one — contract:aa:inv-t1" a a
check 2 "two — contract:aa:inv-t1" b b
"""

_FIX_PY = '''\
import unittest


class T(unittest.TestCase):
    # contract:bb:inv-t2
    def test_two(self):
        """contract:bb:inv-t2 — a real assertion lives here."""
        self.assertEqual(1, 1)
'''

_FIX_MAP = {
    "contract:aa:inv-t1": {"kind": "bash", "carriers": ["t.sh"], "checks": 2},
    "contract:bb:inv-t2": {"kind": "python", "carriers": ["t.py"], "tests": 1},
}


def _make_fixture(tmp: Path, yaml_text: str = _FIX_YAML, bash_text: str = _FIX_BASH,
                  py_text: str = _FIX_PY) -> Path:
    root = Path(tempfile.mkdtemp(dir=tmp))
    (root / "docs" / "plans").mkdir(parents=True)
    (root / "docs" / "plans" / "c.yaml").write_text(yaml_text, encoding="utf-8")
    (root / "t.sh").write_text(bash_text, encoding="utf-8")
    (root / "t.py").write_text(py_text, encoding="utf-8")
    return root


def _fixture_errors(root: Path, coverage_map: dict = None) -> list[str]:
    return run_checks(root, coverage_map or _FIX_MAP, "docs/plans/c.yaml", git_checks=False)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git against a fixture repo with the machine's own config neutralised.

    `check=True`, so ANY ambient global/system setting that makes a fixture
    command fail is an unhandled traceback and a spurious RED unrelated to a
    regression — `commit.gpgsign = true` was the reported one, but the class is
    the whole config file (`core.hooksPath`, templates, `commit.template`, …).
    Neutralising both config layers closes the class rather than one member;
    `hooks/tests/test-grudge-resolution-guard.sh` does the narrower
    `git config commit.gpgsign false` per fixture repo.
    """
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True, env=env)


def _make_git_fixture(tmp: Path) -> tuple[Path, str]:
    """A repo whose merge-pr/SKILL.md gained exactly the permitted paragraph."""
    root = Path(tempfile.mkdtemp(dir=tmp))
    (root / "skills" / "merge-pr").mkdir(parents=True)
    skill = root / MERGE_PR_SKILL
    # The `---` frontmatter fences are load-bearing fixture, not decoration: a
    # REMOVED line whose own text starts with `--` renders as `---…` in a diff,
    # which a header filter anchored on a bare `---` prefix silently eats.
    head = ("---\nname: merge-pr\n---\n\n"
            "### Step 7.5: Record a grudge if this was a fix\n\n```bash\n"
            + EXPECTED_STEP_75_FENCE + "\n```\n")
    skill.write_text(head + "\nNon-`fix(*)` PRs record nothing.\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    skill.write_text(
        head + "\n" + EXPECTED_ADDED_LINES[0] + "\n\nNon-`fix(*)` PRs record nothing.\n",
        encoding="utf-8",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "add paragraph")
    return root, base


def selftest() -> int:
    failures: list[str] = []

    def expect_clean(label: str, errs: list[str]) -> None:
        if errs:
            failures.append(f"{label}: expected no errors, got {errs}")

    def expect_error(label: str, errs: list[str], needle: str) -> None:
        if not any(needle in e for e in errs):
            failures.append(f"{label}: expected an error containing {needle!r}, got {errs}")

    tmp = Path(tempfile.mkdtemp())
    try:
        # --- baseline: a clean fixture tree is green -----------------------
        expect_clean("clean fixture", _fixture_errors(_make_fixture(tmp)))

        # --- MUTANT: delete a `check` call, leave the annotation -----------
        root = _make_fixture(tmp, bash_text=_FIX_BASH.replace(
            'check 2 "two — contract:aa:inv-t1" b b\n', ""))
        expect_error("check deleted, annotation kept", _fixture_errors(root), "occurrence arithmetic")

        # --- MUTANT: delete a `check` AND decrement the annotation (#566) --
        root = _make_fixture(tmp, bash_text=_FIX_BASH
                             .replace('check 2 "two — contract:aa:inv-t1" b b\n', "")
                             .replace("checks=2", "checks=1"))
        errs = _fixture_errors(root)
        expect_error("check deleted + annotation decremented", errs, "COVERAGE_MAP pins checks=2")
        if any("occurrence arithmetic" in e for e in errs):
            failures.append("check deleted + annotation decremented: arithmetic should be self-consistent "
                            "— only the map should catch this")

        # --- MUTANT: raise the annotation without adding checks ------------
        root = _make_fixture(tmp, bash_text=_FIX_BASH.replace("checks=2", "checks=3"))
        expect_error("annotation raised", _fixture_errors(root), "COVERAGE_MAP pins checks=2")

        # --- MUTANT: the absence assertion (marker with no checks=) --------
        root = _make_fixture(tmp, bash_text=_FIX_BASH.replace(
            "# contract:aa:inv-t1 checks=2", "# contract:aa:inv-t1"))
        expect_error("unannotated marker", _fixture_errors(root), "has no `checks=` annotation")

        # --- MUTANT: rename a carrier --------------------------------------
        root = _make_fixture(tmp)
        (root / "t.sh").rename(root / "t-renamed.sh")
        expect_error("carrier renamed", _fixture_errors(root), "carrier file missing or renamed")

        # --- MUTANT: a tag the contract never declared ---------------------
        root = _make_fixture(tmp, bash_text=_FIX_BASH + (
            "\n# contract:foo:inv-t99 checks=1\ncheck 3 \"x — contract:foo:inv-t99\" a a\n"))
        errs = _fixture_errors(root)
        expect_error("undeclared tag", errs, "contract:foo:inv-t99")
        expect_error("undeclared tag", errs, "the contract YAML does not declare it")

        # --- MUTANT: test_tag removed from the contract while tests remain -
        root = _make_fixture(tmp, yaml_text=_FIX_YAML.replace(
            '      test_tag: "contract:aa:inv-t1"\n', ""))
        errs = _fixture_errors(root)
        expect_error("test_tag removed", errs, "the contract YAML does not declare it")
        expect_error("test_tag removed", errs, "COVERAGE_MAP but the contract YAML")

        # --- MUTANT: declared but never carried ----------------------------
        root = _make_fixture(tmp, bash_text=_FIX_BASH.replace("contract:aa:inv-t1", "contract:aa:inv-t7"))
        expect_error("declared but uncarried", _fixture_errors(root),
                     "contract:aa:inv-t1 appears in the contract YAML but no test carries it")

        # --- MUTANT: a python tag whose test has no assertion --------------
        root = _make_fixture(tmp, py_text=_FIX_PY.replace("self.assertEqual(1, 1)", "pass"))
        expect_error("assertionless python test", _fixture_errors(root),
                     "contains no assert / self.assert*")

        # --- MUTANT: a python tag carried by a comment marker only ---------
        root = _make_fixture(tmp, py_text=_FIX_PY.replace(
            '"""contract:bb:inv-t2 — a real assertion lives here."""', '"""nothing."""'))
        expect_error("python docstring token removed", _fixture_errors(root),
                     "has no test function whose docstring carries it")

        # --- MUTANT: a stray tag in a non-carrier code file ----------------
        root = _make_fixture(tmp)
        (root / "scripts").mkdir()
        (root / "scripts" / "stray.py").write_text("# contract:aa:inv-t1\n", encoding="utf-8")
        expect_error("stray tag", _fixture_errors(root), "is not a declared carrier")

        # --- contract YAML absent (the CI / fresh-clone shape) -------------
        # The upstream cross-check stands down with a NOTE, and the map-vs-carriers
        # half must still be enforced in full — otherwise a gitignored contract
        # would have reintroduced exactly the vacuity #577 was filed for.
        root = _make_fixture(tmp)
        (root / "docs" / "plans" / "c.yaml").unlink()
        notes: list[str] = []
        errs = run_checks(root, _FIX_MAP, "docs/plans/c.yaml", git_checks=False, notes=notes)
        expect_clean("contract YAML absent", errs)
        if not any("upstream test_tag cross-check did not run" in n for n in notes):
            failures.append(f"contract YAML absent: expected a stand-down NOTE, got {notes}")

        root = _make_fixture(tmp, bash_text=_FIX_BASH.replace("contract:aa:inv-t1", "contract:aa:inv-t7"))
        (root / "docs" / "plans" / "c.yaml").unlink()
        expect_error("contract YAML absent + carrier drift", _fixture_errors(root),
                     "contract:aa:inv-t1 is pinned in COVERAGE_MAP but no carrier file carries it")

        # --- MUTANT: contract YAML present but empty -----------------------
        root = _make_fixture(tmp, yaml_text="  testable: []\n")
        expect_error("empty contract YAML", _fixture_errors(root),
                     "declares no parseable `test_tag:` at all")

        # --- MUTANT: an unparseable test_tag line --------------------------
        root = _make_fixture(tmp, yaml_text=_FIX_YAML.replace(
            '      test_tag: "contract:aa:inv-t1"', "      test_tag: contract:aa:inv-t1"))
        expect_error("unparseable test_tag", _fixture_errors(root), "unparseable test_tag line")

        # --- INV-C10: the merge-writer predicate ---------------------------
        prints_only = (
            'APPEND_SCRIPT="$ROOT/scripts/grudge_append.py"\n'
            "_prefill() {\n"
            '  printf \'    python3 "%s" --symptom "<x>"\\n\' \\\n'
            '    "$APPEND_SCRIPT" >&2\n'
            "}\n"
        )
        if _executes_grudge_append(prints_only):
            failures.append("merge-writer predicate: fired on a hook that only PRINTS the writer")
        executes_direct = 'python3 "$ROOT/scripts/grudge_append.py" --symptom "x"\n'
        if not _executes_grudge_append(executes_direct):
            failures.append("merge-writer predicate: missed a direct `python3 …/grudge_append.py` call")
        executes_alias = (
            'W="$ROOT/scripts/grudge_append.py"\n'
            'if [ -n "$SHA" ]; then "$W" --symptom "x"; fi\n'
        )
        if not _executes_grudge_append(executes_alias):
            failures.append("merge-writer predicate: missed a variable-indirected invocation")

        root = _make_fixture(tmp)
        (root / "hooks").mkdir()
        errs: list[str] = []
        check_no_merge_grudge_writer(root, errs)
        expect_clean("no-merge-writer, clean", errs)
        (root / "hooks" / "grudge-merge-writer.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        errs = []
        check_no_merge_grudge_writer(root, errs)
        expect_error("legacy path present", errs, "hooks/grudge-merge-writer.sh exists")
        (root / "hooks" / "grudge-merge-writer.sh").unlink()
        (root / "hooks" / "totally-innocent-name.sh").write_text(
            "#!/bin/sh\n" + executes_direct, encoding="utf-8")
        errs = []
        check_no_merge_grudge_writer(root, errs)
        expect_error("renamed merge writer", errs, "executes the grudge writer")
        (root / "hooks" / "totally-innocent-name.sh").unlink()

        # --- MUTANT: the writer moved below hooks/, or lost its extension ----
        # A `hooks/*.sh` glob reads exactly one directory level and one
        # extension. INV-C10 is about Path A staying cut, not about a filename
        # OR a location OR a suffix.
        (root / "hooks" / "lib").mkdir()
        (root / "hooks" / "lib" / "writer.sh").write_text(
            "#!/bin/sh\n" + executes_direct, encoding="utf-8")
        errs = []
        check_no_merge_grudge_writer(root, errs)
        expect_error("writer in a subdirectory", errs, "hooks/lib/writer.sh")
        (root / "hooks" / "lib" / "writer.sh").unlink()

        (root / "hooks" / "post-merge").write_text(
            "#!/bin/sh\n" + executes_direct, encoding="utf-8")
        errs = []
        check_no_merge_grudge_writer(root, errs)
        expect_error("writer without a .sh suffix", errs, "hooks/post-merge")
        (root / "hooks" / "post-merge").unlink()

        # --- hooks/tests/ is NOT a hook --------------------------------------
        # A test may legitimately drive the writer to seed a fixture store; the
        # exclusion is deliberate, so it gets a fixture of its own.
        (root / "hooks" / "tests").mkdir()
        (root / "hooks" / "tests" / "test-writer.sh").write_text(
            "#!/bin/sh\n" + executes_direct, encoding="utf-8")
        errs = []
        check_no_merge_grudge_writer(root, errs)
        expect_clean("hooks/tests/ is excluded", errs)

        # --- a non-text file under hooks/ is skipped, not a crash ------------
        (root / "hooks" / "blob.bin").write_bytes(b"\xff\xfe\x00binary")
        errs = []
        check_no_merge_grudge_writer(root, errs)
        expect_clean("binary file under hooks/", errs)

        # --- INV-C10: the Step 7.5 history assertion -----------------------
        root, base = _make_git_fixture(tmp)
        errs = []
        check_merge_pr_untouched(root, base, errs)
        expect_clean("merge-pr untouched", errs)

        errs = []
        check_merge_pr_untouched(root, "0" * 40, errs)
        expect_error("shallow clone / missing base", errs, "is not present in this clone")
        expect_error("shallow clone / missing base", errs, "LOUD failure")

        skill = root / MERGE_PR_SKILL
        original = skill.read_text(encoding="utf-8")
        skill.write_text(original + "\nAn extra automation paragraph.\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "extra")
        errs = []
        check_merge_pr_untouched(root, base, errs)
        expect_error("merge-pr gained a line", errs, "are not the one permitted paragraph")

        skill.write_text(original.replace('  --why "<from PR body, if stated>"\n', ""), encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "drop a fence line")
        errs = []
        check_merge_pr_untouched(root, base, errs)
        expect_error("fence line removed", errs, "REMOVED line(s)")
        expect_error("fence line removed", errs, "differs from the pinned templated form")

        # --- MUTANT: a removed line whose own text starts with `--` ---------
        # `-` + `---` renders as `----`; a header filter that anchors on the
        # bare prefix `---` discards it, and "INV-C10 permits no removed lines"
        # silently stops seeing the one edit shape the real file is full of.
        root, base = _make_git_fixture(tmp)
        skill = root / MERGE_PR_SKILL
        # Exactly ONE removed line, and its own text is `---`.
        skill.write_text(skill.read_text(encoding="utf-8").replace("\n---\n\n###", "\n\n###", 1),
                         encoding="utf-8")
        _git(root, "commit", "-aqm", "drop the closing --- frontmatter fence")
        errs = []
        check_merge_pr_untouched(root, base, errs)
        expect_error("removed line beginning with --", errs, "REMOVED line(s)")

        # --- MUTANT: an UNCOMMITTED edit outside the fence -------------------
        # Both halves must read ONE state. The fence pin reads the working tree,
        # so an added-lines assertion reading `base..HEAD` lets an uncommitted
        # automation paragraph through — precisely when this suite normally runs.
        root, base = _make_git_fixture(tmp)
        skill = root / MERGE_PR_SKILL
        skill.write_text(skill.read_text(encoding="utf-8") + "\nAn uncommitted automation paragraph.\n",
                         encoding="utf-8")
        errs = []
        check_merge_pr_untouched(root, base, errs)
        expect_error("uncommitted edit outside the fence", errs, "are not the one permitted paragraph")

        # --- hostile ambient git config (color / external diff) --------------
        # `color.ui = always` prefixes every diff line with ANSI, so nothing
        # starts with `+`; a `diff.external` replaces the diff wholesale. Either
        # turns this assertion into a bogus INV-C10 failure in the gating suite.
        root, base = _make_git_fixture(tmp)
        hostile = root.parent / "hostile.gitconfig"
        hostile.write_text("[color]\n\tui = always\n[diff]\n\texternal = /bin/echo\n", encoding="utf-8")
        saved = os.environ.get("GIT_CONFIG_GLOBAL")
        os.environ["GIT_CONFIG_GLOBAL"] = str(hostile)
        try:
            errs = []
            check_merge_pr_untouched(root, base, errs)
            expect_clean("hostile ambient git config", errs)
        finally:
            if saved is None:
                os.environ.pop("GIT_CONFIG_GLOBAL", None)
            else:
                os.environ["GIT_CONFIG_GLOBAL"] = saved

        # --- main()'s own argv dispatch ------------------------------------
        # stderr is swallowed so the usage line does not read as a failure in
        # the suite log; the exit code is what is being asserted.
        with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
            rc = main([__file__, "--nonsense"])
        if rc != 1:
            failures.append("main: unknown argv should exit 1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"selftest FAILED — {len(failures)} case(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
