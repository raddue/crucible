"""R1+R2 grudge-guard journal invariants: C-a, C-h, C-j, C-l, C-n greps + INV-C8 4a/4b.

Grep-based fences over TRACKED production files (design §9 + §10 criterion 10),
each wired into scripts/run_tests.sh and each with a red-first violating fixture
in --selftest (round-3 finding S-5: a declared, unenforced grep drifted until
its restatements disagreed with each other).

- **C-a** — The journal is only ever opened for append; no code path rewrites,
  truncates, or deletes it — with exactly one named, bounded exception: `C-q`'s
  rename-to-quarantine-and-re-arm (`_journal_quarantine`). No other code path
  may do so.
- **C-h** — The hook never reads `outcomes.tsv`. No read, no test, no branch —
  the witness is write-only.
- **C-j** — No code path converts a per-member `ABSENT` or `UNMEASURABLE`
  journal read into a numeric contribution (never coerced to `0`).
- **C-l** — Every git shell-out in this subsystem (`grudge_append.py`'s
  `resolve_repo()`/`resolve_store_repo()`, `grudge_query.py`'s
  `_git_env()`-backed calls, `ledger_doctor.py`'s store-identity resolution,
  the hook's `_git()`) invokes git through the PATH/HOME-only allowlist, never
  the inherited process environment (#605).
- **C-n** — No journal write may lower `blocks(m)` for a member that was not
  itself *durably* demonstrated resolved this Stop: `CLEAR\t<m>` is written only
  for a member whose own resolution is durable this Stop; a by-files
  (working-tree) resolution clears the Stop but mints no `CLEAR`.
- **4a (C-c, INV-C8)** — `STOP_HOOK_ACTIVE` appears only as a conjunct that
  forbids a block — no bash `if`/`[[`/`&&` gate whose gate term is exclusively
  the flag.
- **4b (INV-C8 YAML-wording)** — machine-local (the contract YAML is in
  gitignored docs/plans): when the YAML is present, INV-C8's clause (2) must
  carry the amended forbidding-conjunct wording or the check FAILS LOUDLY
  (a stand-down NOTE does not satisfy criterion 4, design §6/§10). When the
  YAML is absent (CI / fresh clone) this half prints a NOTE and stands down —
  it cannot check a file that is not there.

Scope is the PRODUCTION sources the design names, not the test suite (a test
may legitimately drive a bad shape to prove it fails). `--selftest` drives the
same `_scan` against PASS and FAIL fixture trees, so each fence has a
red-fixture witness.

Pure stdlib. Style mirrors scripts/check_grudge_encoding_invariants.py.
"""
import glob
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, ".."))

HOOK = ("hooks/grudge-resolution-guard.sh",)
PY_PROD = ("scripts/grudge_query.py", "scripts/grudge_append.py",
           "scripts/ledger_doctor.py")
CONTRACT_YAML = "docs/plans/2026-08-28-558-559-crap-grudge-contract.yaml"


def _lineno(text, match):
    return text.count("\n", 0, match.start()) + 1


# C-a: the junction between the journal path and a write that is NOT append.
# Appends are `>> "$JOURNAL_FILE"` (O_APPEND) or a `printf` into it; a rewrite
# is a truncating `>`, or a `touch`/`mv`/`rm` targeting the journal path outside
# C-q's `corrupt.<epoch>` quarantine rename.
_C_A_BANNED = None  # implemented line-windowed in _truncate_sites

# C-h: the hook may never read the witness.
_C_H_READS = re.compile(r'\boutcomes\.tsv\b')

# C-j: assigning a numeric that folds ABSENT/UNMEASURABLE into the group fold.
# The forbidden shapes are `ABSENT`/`UNMEASURABLE` adjacent to a numeric
# assignment (`:-0`, `=0`, arithmetic) — the coercion a correct
# contributes-nothing join never performs. The token must be a READ VALUE (a
# bare `ABSENT`/`UNMEASURABLE` in a case branch or `read` result), not the name
# of the `JR_ABSENT`/`JR_UNMEASURABLE` FLAG variables.
_C_J_COERCE = re.compile(
    r'(?:(?<![A-Za-z_])(?:ABSENT|UNMEASURABLE)[^\n]*(?::-[0-9]|=0)|(?::-[0-9]|=0)[^\n]*(?<![A-Za-z_])(?:ABSENT|UNMEASURABLE))')

# C-l: a python `subprocess.run([... "git" ...])` that does not pass the
# allowlist, and the hook invoking `git` other than through `_git()`.
_C_L_RUN = re.compile(r'subprocess\.run\(')


def _cl_python(text):
    """Find `subprocess.run([... "git" ...])` calls without an `env=` argument
    inside the same (balanced) call. Args can span lines, so a lookahead on the
    same line (or a `[^\]]` up to the first `]`) is not enough: `env=` may sit
    on the line after the closing bracket, exactly as every allowlist-backed
    call in the tree is formatted. Returns (lineno, git_argument_fragment)
    tuples."""
    out = []
    for m in _C_L_RUN.finditer(text):
        call = m.group(0)
        # Balance parens from the '(' to its close, honoring no strings — the
        # argument lists here never contain a literal ')' inside a string that
        # would unbalance them, and a false imbalance is a loud false-positive
        # (safe direction: it forces a look, never a silent pass).
        depth = 0
        end = m.end() - 1  # position of '('
        while end < len(text):
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
                if depth == 0:
                    break
            end += 1
        call += text[m.end():end + 1] if end < len(text) else text[m.end():]
        if "git" not in call:
            continue
        # The runtime env for git is handed either as `env=` (subprocess) or by
        # prefixing with env -i (bash). Python side must carry `env=` on the
        # call whose argv contains a git token.
        if "env=" not in call:
            out.append((_lineno(text, m), call[:80]))
    return out
_C_L_HOOK_GIT = re.compile(
    r'(?<![{\s])git[ \t]+(?!-C\s|rev-parse\s|cat-file\s)')
_HOOK_GIT_SAFE = re.compile(r'_git\(\)|env -i PATH')

# C-n: a CLEAR journal append that the surrounding word cannot be durable
# (skips.log / by-commit). A by-files/transient site must never mint CLEAR.
_C_N_TRANSIENT_CLEAR = re.compile(
    r'(?:by.files|--by-files|transient|GROUP_CLEARED[^D])[^\n]*'
    r'(\.journal_append_group[^\n]*CLEAR|CLEAR[^\n]*journal_append_group)')

def _cc_sole_gates(text):
    """4a (INV-C8 clause 2, C-c): `STOP_HOOK_ACTIVE` may never be the SOLE term
    of a bash `if`/`[[`/`&&`/`||` gate — it may appear only as a conjunct that
    forbids a block. The greppable proxy the design names (§6: "appears in no
    bash if/[[ whose *entire* condition is that one term"; necessary but not
    sufficient): a single-line gate condition that references the flag and
    carries no conjunct of its own (`&&`/`||`) and no other variable reference.
    A condition that pairs the flag with another term (`&& [ -n "$OTHER" ]`,
    `&& [ "$STOP_HOOK_ACTIVE" != "true" ]`) is a conjunct and is not flagged.
    Returns (lineno, gate_line)."""
    out = []
    for ln, line in enumerate(text.splitlines(), 1):
        if "STOP_HOOK_ACTIVE" not in line:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Is this a gate line at all? `if ... then`, `[[ ... ]]`, `[ ... ]`,
        # or a `&&`/`||` continuation.
        is_gate = (
            re.search(r'\b(?:if|elif|while|until)\b', stripped)
            or re.search(r'\[\[?\s*[^\n]*\]?\]?\s*(?:\)|&&|\|\|)', line)
        )
        if not is_gate:
            continue
        other_vars = re.findall(r'\$[A-Za-z_]\w*', line)
        other_vars = [v for v in other_vars if v != "$STOP_HOOK_ACTIVE"]
        if re.search(r'&&|\|\|', line):
            continue  # a conjunct: the flag is not the sole term
        if other_vars:
            continue  # another term present
        out.append((ln, stripped))
    return out

# 4b: the amended INV-C8 clause (2) wording that must appear in the contract
# YAML when it is present.
_C8_AMENDED_WORDING = ("may never be the sole term of an allow/block gate, and "
                       "may never permit a block; it may appear only as a "
                       "conjunct that forbids one")


def _scan(files):
    """files: {rel_path: text}. Returns list of defect strings ([] == clean)."""
    errors = []

    for rel, text in files.items():
        if rel in HOOK:
            errors += _scan_hook(text, rel)
        if rel in PY_PROD:
            for ln, frag in _cl_python(text):
                errors.append(
                    f"[C-l] {rel}:{ln}: git shell-out without the "
                    f"PATH/HOME allowlist ({frag!r})")

    return errors


_BARE_GIT = re.compile(r'(?<!\w)git[ \t]+')
# A `git` invocation is safe iff it is inside the `_git()` allowlist wrapper
# (the wrapper's OWN line defines it) or a comment/string the hook never runs.
_GIT_WRAPPER_OPEN = re.compile(r'^_git\(\)[ \t]*\{')
_CLEAR_APPEND = re.compile(r'journal_append_group[ \t]+CLEAR|\bCLEAR[ \t]+t[^\n]*journal_append')
_BYFILES = re.compile(r'--by-files|by\.files|GROUP_CLEARED\b|transient|TRANSIENT')
# `>` (single, not `>>`) then spaces then the journal path = truncate; likewise
# `rm`/`touch` naming a journal path.
_TRNCATE = re.compile(
    r'(?<!>)>[ \t]+"?\$"?\{?JOURNAL(?:[^>]|$)'
    r'|\b(?:rm|touch)\b[ \t]+(?:-[a-zA-Z]+\s+)*"?\$"?\{?JOURNAL')


def _quarantine_body(text):
    """Line range (1-based, inclusive) of the `_journal_quarantine()` function
    body — the ONE named exception where the journal may be renamed
    (`corrupt.<epoch>`) and re-armed (`: >`) fresh. Returns (start, end) or None.
    Braces are counted from the function header to its matching close, so a
    comment containing `{`/`}` does not unbalance it."""
    lines = text.splitlines()
    start = None
    depth = 0
    for i, line in enumerate(lines):
        if re.search(r'^_journal_quarantine\(\)', line):
            start = i
            depth = line.count("{") - line.count("}")
            continue
        if start is None:
            continue
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            return (start + 1, i + 1)
    return None


def _truncate_sites(text):
    """C-a: `>` / `touch` / `mv` / `rm` against the journal path, OUTSIDE C-q's
    quarantine body (the rename to `.corrupt.<epoch>` and the re-arm `: >` that
    starts the fresh journal are the design's single named exception to
    append-only, §3.2/§9 C-q). Returns (lineno, match)."""
    out = []
    qstart, qend = _quarantine_body(text) or (0, 0)
    for ln, line in enumerate(text.splitlines(), 1):
        if qstart <= ln <= qend:
            continue  # C-q quarantine is the allowed one-time rename/re-arm
        if "JOURNAL" not in line:
            continue
        if re.search(r'>>\s*"?\$"?\{?JOURNAL', line):
            continue  # append — the only legal write form
        for m in _TRNCATE.finditer(line):
            if "JOURNAL" in line:
                out.append((ln, m.group(0)))
    return out


def _cl_hook(text):
    """C-l: every git invocation in the hook happens through `_git()`. The
    wrapper's own line (`env -i PATH… git …`) and its definition are allowed;
    any other bare `git` in a non-comment position is inherited-environment. `#`
    comments and single/double-quoted strings are not run and are skipped;
    `command -v git` is a PATH probe, not an invocation."""
    out = []
    for ln, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if _GIT_WRAPPER_OPEN.search(line):
            continue
        if re.search(r'command[ \t]+-v[ \t]+git\b', line):
            continue
        if re.search(r'[#\'"`]', line.split("git", 1)[0]):
            continue  # preceded by comment/quote opener on this line — runny gray
        for m in _BARE_GIT.finditer(line):
            out.append((ln, m.group(0)))
    return out


def _cn_sites(text):
    """C-n: every `journal_append_group CLEAR` call, plus a verdict whether its
    surrounding window smells of the transient/by-files path. The durable CLEAR
    site lives in the durable-clearance branch only. A call site whose preceding
    lines reach a `--by-files`/`GROUP_CLEARED`/`transient` marker is the
    forbidden shape (row-3 finding F-1: durable reset on a transient clear).
    Returns (lineno, match, flag)."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        m = _CLEAR_APPEND.search(line)
        if not m:
            continue
        window = "\n".join(lines[max(0, i - 6):i])
        out.append((i, m.group(0), bool(_BYFILES.search(window))))
    return out


def _scan_hook(text, rel):
    errors = []
    for ln, bad in _truncate_sites(text):
        errors.append(
            f"[C-a] {rel}:{ln}: journal rewrite/delete ({bad!r}) — only C-q's "
            f"quarantine rename may touch the journal; append-only otherwise")
    for ln, bad in _cl_hook(text):
        errors.append(
            f"[C-l] {rel}:{ln}: bare `git` invocation ({bad!r}) outside the "
            f"`_git()` PATH/HOME allowlist wrapper")
    for ln, bad, transient in _cn_sites(text):
        if transient:
            errors.append(
                f"[C-n] {rel}:{ln}: CLEAR write ({bad!r}) on a transient/"
                f"by-files window — durable resolution only (C-n)")
    for m in _C_H_READS.finditer(text):
        errors.append(
            f"[C-h] {rel}:{_lineno(text, m)}: the hook reads/named "
            f"outcomes.tsv — the witness is write-only")
    for m in _C_J_COERCE.finditer(text):
        errors.append(
            f"[C-j] {rel}:{_lineno(text, m)}: ABSENT/UNMEASURABLE coerced to a "
            f"numeric ({m.group(0)!r}) — a member that cannot be measured "
            f"contributes nothing")
    if _cc_sole_gates(text):
        errors.append(
            f"[C-c/4a] {rel}: STOP_HOOK_ACTIVE as the sole term of a gate — it "
            f"may only be a conjunct that forbids a block")
    return errors


def _4b_yaml(root):
    """INV-C8 4b: contract-YAML wording check. Returns (errors, notes).
    Machine-local: absent YAML stands down with a NOTE (it cannot be checked
    where it is not present), but a PRESENT unamended YAML fails loudly."""
    path = os.path.join(root, CONTRACT_YAML)
    if not os.path.isfile(path):
        return [], [f"contract YAML not present ({CONTRACT_YAML}) — 4b stood "
                     "down; criterion 4 (INV-C8 wording) is checked only on the "
                     "machine that holds the YAML"]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return [f"[4b] {CONTRACT_YAML}: unreadable ({exc}) — must fail loudly "
                 "when present but unamended"], []
    # Find the INV-C8 entry's description line; the amended clause (2) wording
    # must be present somewhere within it.
    if _C8_AMENDED_WORDING not in text:
        return [f"[4b] {CONTRACT_YAML}: INV-C8 clause (2) does not carry the "
                 "amended forbidding-conjunct wording — a present-but-unamended "
                 "contract must FAIL LOUDLY, a stand-down NOTE does not satisfy "
                 "criterion 4"], []
    return [], []


def _skills_md():
    return sorted(p for p in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))
                  if os.path.isfile(p))


def main(argv):
    real = {}
    for rel in HOOK + PY_PROD:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                real[rel] = fh.read()

    errors = _scan(real)
    if argv[0:1] == ["--selftest"]:
        selftest_rc = _selftest()
        if selftest_rc:
            errors.append("--selftest fixture failures")
    notes = []
    if argv[0:1] != ["--selftest"]:
        yerr, ynotes = _4b_yaml(ROOT)
        errors.extend(yerr)
        notes.extend(ynotes)
    for note in notes:
        print(f"NOTE: {note}")
    for e in errors:
        print(e)
    if errors:
        print(f"grudge-guard journal invariants: {len(errors)} defect(s)")
        return 1
    print("OK — C-a, C-h, C-j, C-l, C-n journal invariants + 4a/4b hold "
          f"across {len(real)} production file(s)")
    return 0


# --------------------------------------------------------------------------- #
# --selftest: each fence gets a PASS fixture and a FAIL fixture.               #
# --------------------------------------------------------------------------- #
_PASS = {
    "hooks/grudge-resolution-guard.sh": (
        "_journal_quarantine() {\n"
        "  mv -f \"$JOURNAL_FILE\" \"$JOURNAL_FILE.corrupt.$epoch\" 2>/dev/null\n"
        "  : > \"$JOURNAL_FILE\" 2>/dev/null || :\n"
        "}\n"
        "_journal_append_group() {\n"
        "  printf '%s\\n' \"$epoch\\tBLOCK\\t$m\\t$nonce\" >> \"$JOURNAL_FILE\"\n"
        "  printf '%s\\n' \"$epoch\\tCLEAR\\t$m\" >> \"$JOURNAL_FILE\"\n"
        "}\n"
        "_journal_read_group() {\n"
        "  case \"$r\" in\n"
        "    ABSENT) : ;;        # contributes nothing — C-j\n"
        "    UNMEASURABLE) : ;;  # contributes nothing — C-j\n"
        "  esac\n"
        "}\n"
        "_git() { env -i PATH=\"$PATH\" HOME=\"$HOME\" git -C \"$1\" \"${@:2}\"; }\n"
        "if [ \"$STOP_HOOK_ACTIVE\" = \"true\" ] && [ -n \"$OTHER\" ]; then :; fi\n"
    ),
    "scripts/grudge_query.py": (
        "proc = subprocess.run([\"git\", \"-C\", root, \"rev-parse\"],\n"
        "                      capture_output=True, env=_git_env(), timeout=30)\n"
    ),
    "scripts/grudge_append.py": (
        "proc = subprocess.run(\n"
        "    [\"git\", \"-C\", base, \"rev-parse\", \"--git-common-dir\"],\n"
        "    capture_output=True, text=True, timeout=5, env=_git_env())\n"
    ),
    "scripts/ledger_doctor.py": (
        "from scripts.grudge_append import resolve_repo\n"
    ),
}

_FAIL_EXPECT = [
    # (label, file, expected-prefix, failing text)
    ("C-a rm journal", HOOK[0], "[C-a]", "rm -f \"$JOURNAL_FILE\"  # never\n"),
    ("C-a truncate journal", HOOK[0], "[C-a]",
     "printf '' > \"$JOURNAL_FILE\"  # rewrite\n"),
    ("C-h read outcomes", HOOK[0], "[C-h]",
     "grep -c resolved outcomes.tsv \"$WITNESS\" 2>/dev/null\n"),
    ("C-j coerce ABSENT to 0", HOOK[0], "[C-j]",
     "case \"$r\" in ABSENT) n=0 ;; esac\n"),
    ("C-l no-env python", "scripts/grudge_append.py", "[C-l]",
     'proc = subprocess.run(["git", "-C", base, "rev-parse"])\n'),
    ("C-l bare hook git", HOOK[0], "[C-l]",
     'git -C "$SESSION_ROOT" log --format=%H HEAD\n'),
    ("C-n transient CLEAR", HOOK[0], "[C-n]",
     'if [ -n "${GROUP_CLEARED[$g]}" ]; then\n'
     '  _journal_append_group CLEAR "" "$m"   # transient-by-files site\n'
     'fi\n'),
    ("C-c sole stop_hook_active gate", HOOK[0], "[C-c/4a]",
     'if [[ -n "${STOP_HOOK_ACTIVE}" ]]; then exit 0; fi\n'),
]


def _fail_fixture(label, rel, bad_text):
    files = dict(_PASS)
    files[rel] = files.get(rel, "") + bad_text
    return files


def _selftest():
    failures = 0
    if _scan(_PASS):
        print("SELFTEST FAIL: clean PASS fixture produced defects")
        failures += 1
    for label, rel, prefix, bad in _FAIL_EXPECT:
        errors = _scan(_fail_fixture(label, rel, bad))
        hits = [e for e in errors if e.startswith(prefix)]
        if not hits:
            print(f"SELFTEST FAIL: {label} — expected a {prefix} defect, got none")
            failures += 1
    if failures == 0:
        print("selftest OK")
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))