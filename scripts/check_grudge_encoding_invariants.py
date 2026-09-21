#!/usr/bin/env python3
"""R4 encoding invariants: C-m, C-d, C-o, T-s (#574, #568, DEC-5).

Grep-based fences over TRACKED production files only (design §9 + §10
criterion 10): nothing a path can contain may travel through a
character-delimited channel or a two-token argv construction, at any of the
subsystem's boundaries.

- **C-d** — No `split(",")` / comma-join on any path-valued expression in
  `grudge_query.py`, `grudge_append.py`, the hook, or any `skills/*/SKILL.md`
  bash fence that invokes either script (including via `IFS=,` or a
  comma-joined `--files`/`--by-files` value). SIEGE-R2-H10/CHAIN-1.
- **C-m** — Every construction of `--files=` / `--by-files=` is the single
  joined token `--flag=path`, never a two-token space-separated argv element
  (`["--files", path]` in a subprocess arg list, or `--files "$path"` in bash).
  Siege S-7.
- **C-o** — Every `declare -a "F_$sha"` in the hook is preceded by the
  hex-only `_sha_key_ok` guard — on BOTH the fresh-scan and the `.files` load
  branch (SIEGE-R2-H6). The mechanical form asserted here is the guard line
  immediately above the declare in the one funnel helper.
- **T-s** — No comment claims the comma-separated `--by-files`/`--files`
  encoding is "carried deliberately" (the pre-R4 contract decision was
  reversed; the stale claim must not silently drift back, SP-3).

Scope is deliberately the PRODUCTION sources the design names — the files a
future regression would land in — not the test suite (a test may legitimately
drive a bad shape to prove it fails). `--selftest` drives the same `_scan`
against PASS and FAIL fixture trees, so each fence has a red-fixture witness.

Pure stdlib. Follows scripts/check_contract_tags.py's style: errors accumulate,
`main()` exits 0 iff none.
"""
import glob
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, ".."))

# Production files the design's invariants range over (C-d/C-m scope) —
# grudge_query.py, grudge_append.py, the hook, every skills/*/SKILL.md.
PY_PROD = ("scripts/grudge_query.py", "scripts/grudge_append.py")
HOOK = ("hooks/grudge-resolution-guard.sh",)
SELF = os.path.basename(__file__)

_SPLIT_JOIN_COMMA = re.compile(r"\b(?:split|join)\(\s*[\"']\s*,\s*[\"']\s*\)")
_IFS_COMMA = re.compile(r"IFS=,")
_TWO_TOKEN_LIST = re.compile(r'\[[^\]]*?["\']--(?:files|by-files)["\']\s*,')
# space-form = `--files "…"` / `--by-files "$x"`: a space followed by a quoted
# or $-dollar value. A bare English-word mention (`--by-files under …` in a
# prose comment) is not a construction and must not flag.
_SPACE_FORM = re.compile(r"--(?:files|by-files)[ \t]+[\"']")
# comma inside a --files/--by-files VALUE: the `=` or whitespace before the
# opening quote excludes an argparse definition line (`--files", required=…`).
_COMMA_IN_VALUE = re.compile(r'--(?:files|by-files)(?:=|[ \t])["\'][^" \t]*,[^"\']*["\']')
_CARRIED_DELIBERATELY = re.compile(r"carried deliberately")
_SHA_KEY_OK_DEF = re.compile(r"^_sha_key_ok\(\)[ \t]*\{", re.M)
_SPLIT_CSV_DEF = re.compile(r"^_split_csv\(\)[ \t]*\{", re.M)
_GUARDED_DECLARE = re.compile(
    r"_sha_key_ok \"\$sha\" \|\| return 1\n(?:[ \t]*#[^\n]*\n)*[ \t]*declare(?: -g)? -a \"F_\$sha\"")
_DECLARE_F = re.compile(r"declare(?: -g)? -a \"F_\$[a-zA-Z_][a-zA-Z0-9_]*\"")


def _lineno(text, match):
    return text.count("\n", 0, match.start()) + 1


def _scan(files):
    """files: {rel_path: text}. Returns list of defect strings ([] == clean).

    A fixture mode takes synthetic text and the SAME code paths a real-tree run
    takes, so the PASS and FAIL shapes beneath cover every check below.
    """
    errors = []

    for rel, text in files.items():
        for m in _SPLIT_JOIN_COMMA.finditer(text):
            errors.append(
                f"[C-d] {rel}:{_lineno(text, m)}: comma split/join "
                f"({m.group(0)!r}) on a path-valued expression"
            )
        if _IFS_COMMA.search(text):
            errors.append(
                f"[C-d] {rel}: IFS=, — a comma-delimited bash split cannot "
                f"carry a path byte"
            )
        for m in _TWO_TOKEN_LIST.finditer(text):
            errors.append(
                f"[C-m] {rel}:{_lineno(text, m)}: two-token argv construction "
                f"({m.group(0)!r}) — every --files/--by-files must be the "
                f"single joined token --flag=path"
            )
        for m in _SPACE_FORM.finditer(text):
            errors.append(
                f"[C-m] {rel}:{_lineno(text, m)}: space-form --files/--by-files "
                f"({m.group(0)!r} + value) — a value beginning with '-' would "
                f"be consumed as the next flag; use --flag=path"
            )
        for m in _COMMA_IN_VALUE.finditer(text):
            errors.append(
                f"[C-d] {rel}:{_lineno(text, m)}: comma-joined --files/"
                f"--by-files value ({m.group(0)!r}) — a comma is a legal path byte"
            )
        if _CARRIED_DELIBERATELY.search(text):
            errors.append(
                f"[T-s] {rel}: a comment claims the comma-separated --by-files/"
                f"--files encoding was 'carried deliberately' — that decision "
                f"was reversed (DEC-5) and the stale claim must not return"
            )

        if rel in HOOK:
            if not _SHA_KEY_OK_DEF.search(text):
                errors.append(
                    f"[C-o] {rel}: _sha_key_ok() is not defined — no hex-"
                    f"and-length gate exists before any F_$sha identifier"
                )
            if _SPLIT_CSV_DEF.search(text):
                errors.append(
                    f"[C-d] {rel}: _split_csv is still defined — the comma "
                    f"splitter was deleted, not reused (DEC-5)"
                )
            if not _GUARDED_DECLARE.search(text):
                errors.append(
                    f"[C-o] {rel}: no `_sha_key_ok \"$sha\" || return 1` line "
                    f"immediately above `declare -a \"F_$sha\"` — a bash "
                    f"identifier must never be built from an unvalidated sha"
                )
            for m in _DECLARE_F.finditer(text):
                if "F_$sha" in m.group(0):
                    continue
                errors.append(
                    f"[C-o] {rel}:{_lineno(text, m)}: declare -a on "
                    f"{m.group(0)!r} outside the guarded funnel — every per-sha "
                    f"identifier must pass _sha_key_ok first"
                )
    return errors


def _skills_md():
    return sorted(p for p in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))
                  if os.path.isfile(p))


def main(argv):
    real = {}
    for rel in PY_PROD + HOOK:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                real[rel] = fh.read()
    for p in _skills_md():
        rel = os.path.relpath(p, ROOT)
        real[rel] = open(p, "r", encoding="utf-8", errors="replace").read()

    errors = _scan(real)
    if argv[0:1] == ["--selftest"]:
        selftest_rc = _selftest()
        if selftest_rc:
            errors.append("--selftest fixture failures")
    for e in errors:
        print(e)
    if errors:
        print(f"R4 encoding invariants: {len(errors)} defect(s)")
        return 1
    print("OK — C-m, C-d, C-o, T-s R4 encoding invariants hold "
          f"across {len(real)} production file(s)")
    return 0


# --------------------------------------------------------------------------- #
# --selftest: each fence gets a PASS fixture and a FAIL fixture.               #
# --------------------------------------------------------------------------- #
_PASS = {
    "scripts/grudge_query.py": (
        'ap.add_argument("--by-files", action="append", metavar="PATH")\n'
        "hit = find_by_files(args.by_files or [], ...)\n"
    ),
    "scripts/grudge_append.py": (
        'ap.add_argument("--files", action="append")\n'
        'ap.add_argument("--files-from", metavar="PATH")\n'
        'files = ["--files=%s" % f for f in parts]\n'
    ),
    "hooks/grudge-resolution-guard.sh": (
        "_sha_key_ok() {\n"
        "  case \"$1\" in ''|*[!0-9a-fA-F]*) return 1 ;; esac\n"
        "}\n"
        "_sha_array_set() {\n"
        "  local sha=\"$1\"; shift\n"
        '  _sha_key_ok "$sha" || return 1\n'
        '  declare -a "F_$sha"\n'
        "}\n"
        '_write_state_files() { :; }\n'
    ),
    "skills/merge-pr/SKILL.md": (
        '  --files="<changed file 1>" --files="<changed file 2>" \\\n'
    ),
    "skills/debugging/SKILL.md": '  --files="<path 1>" --files="<path 2>"\n',
    "skills/grudge/SKILL.md": "  --files=src/a.py --files=src/b.py\n",
}

_FAIL_EXPECT = [
    # (label, file, expected-error-prefix, failing text)
    ("C-d py split", "scripts/grudge_query.py", "[C-d]",
     "files = args.by_files.split(',')\n"),
    ("C-d hook IFS=,", "hooks/grudge-resolution-guard.sh", "[C-d]",
     "IFS=, read -r -a AA <<< \"$1\"\n"),
    ("C-m list form", "scripts/grudge_append.py", "[C-m]",
     'subprocess.run(["python3", "--files", "a.py"])\n'),
    ("C-m space form", "hooks/grudge-resolution-guard.sh", "[C-m]",
     'python3 "$AP" --by-files "$csv"  # two tokens\n'),
    ("C-d comma value", "skills/grudge/SKILL.md", "[C-d]",
     '  --files "src/a.py,src/b.py" \\\n'),
    ("C-o unguarded declare", "hooks/grudge-resolution-guard.sh", "[C-o]",
     "declare -a \"F_$badsha\"\n"),
    ("T-s carried deliberately", "scripts/grudge_query.py", "[T-s]",
     "# comma encoding carried deliberately\n"),
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
        elif any(h.startswith(prefix) for h in hits):
            continue
    if failures == 0:
        print("selftest OK")
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))