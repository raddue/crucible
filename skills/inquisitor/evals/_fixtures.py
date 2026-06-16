#!/usr/bin/env python3
"""Variant materialization for the Phase-1b seeded repos (#424).

Pure plumbing shared by the differential oracle (`_oracle.py`) and the
fixture-build invariant checker (`scripts/check_fixture_independence.py`). Given
a fixture repo dir, materialize the `base` / `all-fixed` / `all-fixed-minus-Bᵢ`
variant classes (design §3, §4) by copying the tree and applying the per-bug
`fixes/<bug_id>.patch` files.

Patches are authored against the committed base and touch disjoint files / base
line-ranges (the §3 HARD rule), so they compose order-independently and
zero-fuzz. We apply with `patch -p1 -F0` (fuzz disabled) and fail loud on any
reject — never apply with offset/fuzz, which would silently corrupt attribution.
`patch` (not `git apply`) so the temp copy needs no git repo.
"""
import ast
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import tokenize
from pathlib import Path

_MANIFEST_KEYS = ("repo_id", "pkg", "test_dir", "runner_cmd", "bug_ids", "n")

# S3: hard wall-clock bound on every subprocess that runs model-written test code
# (and on `patch`). A hung/runaway test (`while True:`, a blocking network call)
# would otherwise wedge `score` indefinitely after the expensive collect. A
# timeout maps to ERROR (non-eligible, never credited) — see run_test_in_dir.
_SUBPROCESS_TIMEOUT_S = 60

# F1 (Strategy B): the committed fixture `src/` annotates each seeded bug with its
# id AND a plain-language description of the defect+fix, in comments and docstrings
# (build scaffolding for the maintainer/oracle). NONE of that prose may reach a
# producer agent — an arm that reads the answer key (the bug, not just its numeric
# id) ceilings the WITH−WITHOUT delta toward null. Round-1 stripped only the id
# TOKEN, leaving the bug+fix description intact (the F-1 leak). The complete rule:
# `copy_repo_for_producer` strips ALL comments and ALL docstrings from every copied
# producer-visible `*.py` (both `src/` AND `tests/`). Comments and docstrings never affect these fixtures' runtime
# behavior (no code reads `__doc__`; verified in CI), so the producer copy stays
# behavior-identical to the oracle's pristine committed base — the oracle still
# materializes/scores from _FIXTURES_DIR, never from the producer copy.
#
# `_LEAK_RE` is retained ONLY for the adversarial blindness assertions (it is no
# longer the strip mechanism): the strip removes whole comment/docstring nodes, so
# any surviving id token in a producer copy is a strip bug worth flagging.
_LEAK_RE = re.compile(r"\b(?:BUG)\b|(?:nt|rb|pg)-b[0-9]", re.IGNORECASE)


def load_manifest(repo_dir) -> dict:
    """Read + validate `<repo_dir>/manifest.json`."""
    repo_dir = Path(repo_dir)
    manifest = json.loads((repo_dir / "manifest.json").read_text())
    for key in _MANIFEST_KEYS:
        if key not in manifest:
            raise ValueError(f"manifest missing key: {key!r} ({repo_dir})")
    if len(manifest["bug_ids"]) != manifest["n"]:
        raise ValueError(
            f"manifest n={manifest['n']} != len(bug_ids)="
            f"{len(manifest['bug_ids'])} ({repo_dir})")
    return manifest


def materialize_variant(repo_dir, *, apply=None, exclude=None) -> str:
    """Copy `repo_dir` to a fresh temp dir and apply (set(apply) - set(exclude))
    of the per-bug patches, in deterministic manifest `bug_ids` order.

    Returns the temp dir path; the caller owns cleanup (or use `variant(...)`).
    Raises on an unknown bug_id (not in the manifest) or any patch reject.
    """
    # M-6: resolve to absolute so the per-bug patch_path (repo_dir/"fixes"/…) is
    # well-defined; a relative repo_dir would resolve the patch against the variant
    # `cwd=tmp` and crash with a confusing "can't open patch file".
    repo_dir = Path(repo_dir).resolve()
    manifest = load_manifest(repo_dir)
    bug_ids = manifest["bug_ids"]

    surviving = set(apply or ()) - set(exclude or ())
    unknown = surviving - set(bug_ids)
    if unknown:
        raise ValueError(f"unknown bug_id(s): {sorted(unknown)} ({repo_dir})")
    # deterministic order = manifest bug_ids order
    ordered = [b for b in bug_ids if b in surviving]

    tmp = tempfile.mkdtemp(prefix=f"variant-{manifest['repo_id']}-")
    shutil.copytree(repo_dir, tmp, dirs_exist_ok=True)

    for bid in ordered:
        patch_path = repo_dir / "fixes" / f"{bid}.patch"
        if not patch_path.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            raise FileNotFoundError(f"missing patch for {bid}: {patch_path}")
        try:
            proc = subprocess.run(
                ["patch", "-p1", "-F0", "-i", str(patch_path)],
                cwd=tmp, capture_output=True, text=True,
                timeout=_SUBPROCESS_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(
                f"patch {bid} timed out after {_SUBPROCESS_TIMEOUT_S}s in "
                f"{repo_dir.name}")
        if proc.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(
                f"patch {bid} failed (rc={proc.returncode}) in {repo_dir.name}:\n"
                f"{proc.stdout}\n{proc.stderr}")
    return tmp


def base(repo_dir) -> str:
    """Materialize the as-committed base (every seeded bug live)."""
    return materialize_variant(repo_dir, apply=[])


def all_fixed(repo_dir) -> str:
    """Materialize base + every patch (the fully-corrected repo)."""
    return materialize_variant(repo_dir, apply=load_manifest(repo_dir)["bug_ids"])


def all_fixed_minus(repo_dir, bug_id) -> str:
    """Materialize base + every patch EXCEPT bug_id's (only bug_id live)."""
    return materialize_variant(
        repo_dir, apply=load_manifest(repo_dir)["bug_ids"], exclude=[bug_id])


@contextlib.contextmanager
def variant(repo_dir, *, apply=None, exclude=None):
    """Context-manager form of materialize_variant: yields the dir, then removes it."""
    d = materialize_variant(repo_dir, apply=apply, exclude=exclude)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- Test runner against a materialized variant (shared by the oracle and the
#     fixture-independence checker) --------------------------------------------

def rc_to_verdict(rc: int) -> str:
    """Canonical pytest rc -> verdict mapping (design §4 / M2 truth table).

        0 -> GREEN   (all tests pass)
        1 -> RED     (a test failed = a bug was caught)
        2,3,4,5,* -> ERROR   (interrupted / internal / usage / NO TESTS COLLECTED)

    rc 5 (no tests collected — an empty/mis-named harvested file) is ERROR, NOT
    green: an empty test catches nothing, and counting it green would silently
    credit a WITHOUT failure mode. ERROR is distinct from both GREEN and RED.
    """
    if rc == 0:
        return "GREEN"
    if rc == 1:
        return "RED"
    return "ERROR"


def run_test_in_dir(variant_dir, test_file, manifest) -> str:
    """Run a single pytest `test_file` against an ALREADY-materialized variant.

    Copies the file into the variant's `test_dir` as a probe (the variant's
    conftest puts `src/` on sys.path), runs `runner_cmd --tb=no <probe>` with
    cwd=variant, and maps the rc via `rc_to_verdict`. The caller owns the
    variant lifecycle (materialize once, run many tests, clean up), so the
    oracle can re-use one `all-fixed` / `minus-Bᵢ` copy across many tests.
    """
    variant_dir = Path(variant_dir)
    test_dir = variant_dir / manifest["test_dir"]
    test_dir.mkdir(parents=True, exist_ok=True)
    # Unique probe name per run: reusing one name lets Python load a STALE .pyc
    # for the next probe (mtime-granularity collision), silently running the
    # previous test. Unique names + no-bytecode keep each run hermetic.
    fd, probe_path = tempfile.mkstemp(suffix=".py", prefix="test_probe_", dir=str(test_dir))
    os.close(fd)
    probe = Path(probe_path)
    shutil.copyfile(test_file, probe)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        runner = list(manifest["runner_cmd"])
        try:
            proc = subprocess.run(
                runner + ["--tb=no", str(probe)],
                cwd=str(variant_dir), capture_output=True, text=True, env=env,
                timeout=_SUBPROCESS_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # A hung/runaway model-written test never collects: ERROR is
            # non-eligible (GREEN on all-fixed is required), so a timeout is
            # never credited and the score cannot wedge.
            return "ERROR"
        return rc_to_verdict(proc.returncode)
    finally:
        probe.unlink(missing_ok=True)


# --- F1/F2: build the blind producer-visible repo copy ----------------------

# Only these subtrees/files are producer-visible. Everything else in the fixture
# dir is the ANSWER KEY (exemplars = passing tests per bug, fixes = the exact
# patches, ground-truth-bugs* = the blind bug list, manifest.json = bug_ids) and
# must never reach the measured agent's writable sandbox (F2).
_PRODUCER_VISIBLE = ("src", "tests")


def _docstring_spans(py_source: str) -> set:
    """Return the set of full ((start_row, start_col), (end_row, end_col)) spans of
    every docstring STRING node — module, class, and function — in `py_source`.

    A docstring is the first statement of a module/class/function body when that
    statement is a bare string-constant expression (`ast.get_docstring`'s rule).
    Only these STRING nodes are eligible for removal; every other STRING is a
    runtime literal and is left untouched (M-3: the strip must never alter a
    non-docstring string, which is runtime data).

    S-2: the span covers the WHOLE Constant node (start..end), not just its first
    token. An implicitly-concatenated docstring (`"part one" "part two"` — one
    logical string in Python) emits MULTIPLE STRING tokens but the AST records one
    Constant; matching only the start position left the 2nd+ parts in the copy. The
    end position (`end_lineno`/`end_col_offset`, py3.8+) lets `_in_docstring_span`
    catch every concatenated part.
    """
    spans = set()
    tree = ast.parse(py_source)

    def record(node):
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            v = first.value
            spans.add(((v.lineno, v.col_offset), (v.end_lineno, v.end_col_offset)))

    record(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            record(node)
    return spans


def _in_docstring_span(tok_start, spans) -> bool:
    """True if a STRING token starting at `tok_start` (row, col) falls within any
    docstring span in `spans` (the ((start),(end)) tuples from `_docstring_spans`).

    Covers every part of an implicitly-concatenated docstring: each concatenated
    STRING token starts at-or-after the node start and before the node end (S-2)."""
    for (s_start, s_end) in spans:
        if s_start <= tok_start < s_end:
            return True
    return False


def _strip_comments_and_docstrings(py_source: str) -> str:
    """Remove ALL comments and ALL docstrings from a .py source, keeping executable
    code behavior-identical (F1, the complete blindness rule).

    The seeded `src/` annotates each bug with a plain-language description of the
    defect AND its fix, in comments and docstrings. Redacting only the id token
    (round-1) left that prose answer-key intact. This strips the whole comment and
    the whole docstring node instead, so no bug-describing prose can reach the
    producer. Comments and docstrings carry no runtime semantics for these fixtures
    (no code reads `__doc__`; CI-verified), so the copy stays behavior-identical to
    the oracle's pristine base.

    Token-aware + AST-scoped: COMMENT tokens are removed; STRING tokens are removed
    ONLY when they are a docstring node (per `_docstring_spans`) — a non-docstring
    string literal (runtime data) is never touched (M-3).
    """
    docstring_spans = _docstring_spans(py_source)
    out_lines = []
    last_lineno = 0
    last_col = 0
    comment_rows = set()
    for tok in tokenize.generate_tokens(io.StringIO(py_source).readline):
        ttype = tok.type
        s_row, s_col = tok.start
        e_row, e_col = tok.end
        # Preserve inter-token whitespace/newlines exactly by emitting the gap
        # between tokens; then emit (or drop) the token text.
        if ttype == tokenize.COMMENT:
            text = ""
            comment_rows.add(s_row)
        elif (ttype == tokenize.STRING
              and _in_docstring_span((s_row, s_col), docstring_spans)):
            # Drop the docstring's text but keep its line/column footprint as a
            # placeholder so the statement (`"""…"""`) stays syntactically present
            # and line numbers don't shift unexpectedly — emit an empty string lit.
            text = '""'
        else:
            text = tok.string
        out_lines.append(((s_row, s_col), (e_row, e_col), text))

    # Reconstruct from the raw source so all original spacing is preserved, only
    # replacing the spans we chose to rewrite (comments -> "", docstrings -> '""').
    line_start = [0]
    for line in py_source.splitlines(keepends=True):
        line_start.append(line_start[-1] + len(line))

    def off(row, col):
        return line_start[row - 1] + col

    edits = []
    for (s_row, s_col), (e_row, e_col), text in out_lines:
        # Only record an edit where the emitted text differs from the original
        # token text (comments and docstrings).
        orig = py_source[off(s_row, s_col):off(e_row, e_col)]
        if text != orig:
            edits.append((off(s_row, s_col), off(e_row, e_col), text))
    result = py_source
    for s, e, text in sorted(edits, reverse=True):
        result = result[:s] + text + result[e:]

    # Removing a trailing comment leaves the preceding inter-token gap behind
    # (e.g. `    return x  \n`). Trim trailing whitespace only on lines a comment
    # was removed from — cosmetic, behavior-irrelevant; never reflow code.
    if comment_rows:
        out = result.splitlines(keepends=True)
        for row in comment_rows:
            if 1 <= row <= len(out):
                line = out[row - 1]
                nl = line[len(line.rstrip("\r\n")):]
                out[row - 1] = line.rstrip() + nl
        result = "".join(out)
    return result


def copy_repo_for_producer(repo_dir, dst) -> None:
    """Materialize the BLIND producer-visible copy of a fixture repo at `dst`.

    Copies ONLY the producer-visible subset (`src/` + `tests/`) — never
    `exemplars/`, `fixes/`, `ground-truth-bugs*`, or `manifest.json` (F2) — and
    strips ALL comments and docstrings from every copied producer-visible `*.py`
    (every `_PRODUCER_VISIBLE` subtree: `src/` AND `tests/`) (F1), so no
    bug-describing prose (id OR plain-language description+fix) reaches the agent.
    The committed fixture and the oracle's _FIXTURES_DIR scoring path are
    untouched; only the agent's sandbox is narrowed + de-annotated.
    """
    repo_dir = Path(repo_dir)
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for name in _PRODUCER_VISIBLE:
        src = repo_dir / name
        if not src.exists():
            continue
        shutil.copytree(src, dst / name)
    # Strip every producer-visible subtree, not just src/: tests/ is equally
    # producer-visible (`_PRODUCER_VISIBLE`), so an annotated test file would
    # otherwise carry the answer key into the sandbox verbatim (S-1).
    for sub in _PRODUCER_VISIBLE:
        for py in (dst / sub).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            stripped = _strip_comments_and_docstrings(text)
            if stripped != text:
                py.write_text(stripped, encoding="utf-8")


def _assert_no_leak(repo_copy) -> None:
    """Raise if a producer repo_copy still carries the answer key — a leak token
    in any producer-visible `*.py` (every `_PRODUCER_VISIBLE` subtree: `src/` AND
    `tests/`), or any forbidden answer-key path. Used as a stage-time assertion and
    by the CI guard / unit tests (F1+F2).

    Scanning every producer-visible subtree (not just `src/`) closes the S-1
    `tests/`-scope hole: `tests/` reaches the agent verbatim too, so a leak token
    in a `tests/test_*.py` file would otherwise hand every arm the answer key.

    This is the path+token guard; the bug-DESCRIPTION-prose guard is the separate
    adversarial `assert_no_description_leak` (it cannot live here — `repo_copy` by
    construction excludes `ground-truth-bugs.json`, so the GT descriptions must be
    passed in from the source repo)."""
    repo_copy = Path(repo_copy)
    for forbidden in ("exemplars", "fixes", "manifest.json",
                      "ground-truth-bugs.json", "ground-truth-bugs.provenance.md"):
        if (repo_copy / forbidden).exists():
            raise AssertionError(
                f"producer repo_copy leaks answer-key path {forbidden!r}: {repo_copy}")
    for sub in _PRODUCER_VISIBLE:
        for py in (repo_copy / sub).rglob("*.py"):
            m = _LEAK_RE.search(py.read_text(encoding="utf-8"))
            if m:
                raise AssertionError(
                    f"producer repo_copy leaks bug-identity token {m.group(0)!r} in "
                    f"{py.relative_to(repo_copy)}: {repo_copy}")
    # Belt-and-suspenders: pin the documented `tests/` invariant ("empty dir +
    # conftest.py; arms/oracle write test files here") as a machine-checked fact.
    # The token/prose guards above already cover any annotated tests/ file; this
    # additionally flags the convention being broken at all, so a future fixture
    # that drops a substantive file into tests/ is surfaced even if it carries no
    # leak token (S-1).
    tests_copy = repo_copy / "tests"
    if tests_copy.exists():
        unexpected = sorted(
            str(p.relative_to(repo_copy)) for p in tests_copy.rglob("*")
            if p.is_file() and p.name != "conftest.py")
        if unexpected:
            raise AssertionError(
                f"producer repo_copy tests/ holds non-conftest file(s) {unexpected} "
                f"(the fixture convention is tests/ = empty dir + conftest.py): "
                f"{repo_copy}")


# Minimum contiguous word-run from a GT `desc` that, if it survives verbatim in a
# producer copy, is treated as a description leak. 5 words is long enough that an
# incidental overlap with ordinary code identifiers is implausible, short enough
# that any real sentence fragment from the answer key trips it.
_DESC_LEAK_MIN_WORDS = 5
_WORD_RE = re.compile(r"[A-Za-z0-9_']+")


def assert_no_description_leak(repo_copy, gt_descs) -> None:
    """Adversarial blindness guard (S-1): assert that NONE of the bug DESCRIPTIONS
    survive in the producer copy — independent of the strip mechanism.

    `gt_descs` is the list of `desc` strings from the source repo's
    `ground-truth-bugs.json`. For each desc, every contiguous `_DESC_LEAK_MIN_WORDS`-
    word window must be absent from the (whitespace-normalized) text of every copied
    producer-visible `*.py` (every `_PRODUCER_VISIBLE` subtree: `src/` AND `tests/`);
    the literal phrase `"The fix"` (the round-1 leak's fix-description marker) must
    also be absent. Scanning `tests/` too closes the S-1 hole — a GT-desc paraphrase
    in a `tests/` file is just as much an answer-key leak as one in `src/`. This does
    NOT re-use `_LEAK_RE`, so it catches any prose channel the strip might miss — it
    FAILS on the round-1 prose leak if the comment/docstring strip were reverted."""
    repo_copy = Path(repo_copy)
    # whitespace-normalized concatenation of every copied producer-visible file
    blobs = {}
    for sub in _PRODUCER_VISIBLE:
        for py in (repo_copy / sub).rglob("*.py"):
            blobs[py] = " ".join(py.read_text(encoding="utf-8").split())
    for py, blob in blobs.items():
        if "The fix" in blob:
            raise AssertionError(
                f"producer repo_copy leaks fix-description phrase 'The fix' in "
                f"{py.relative_to(repo_copy)}: {repo_copy}")
    for desc in gt_descs:
        words = _WORD_RE.findall(desc)
        # M-5: a desc SHORTER than _DESC_LEAK_MIN_WORDS would otherwise yield zero
        # windows and lose its prose backstop entirely (only the "The fix" literal
        # would guard it). Fall back to the whole desc as a single window so a terse
        # desc still gets a prose backstop.
        n = min(_DESC_LEAK_MIN_WORDS, len(words)) or 1
        windows = {" ".join(words[i:i + n]) for i in range(0, max(0, len(words) - n + 1))}
        for py, blob in blobs.items():
            norm = " ".join(_WORD_RE.findall(blob))
            for w in windows:
                if w and w in norm:
                    raise AssertionError(
                        f"producer repo_copy leaks GT bug-description prose "
                        f"{w!r} (from desc {desc!r}) in "
                        f"{py.relative_to(repo_copy)}: {repo_copy}")
