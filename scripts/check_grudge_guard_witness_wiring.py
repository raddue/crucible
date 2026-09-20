"""R5 outcome-witness wiring fence (design §9 T-x, §10 criterion 8).

The outcome witness (§5b) is write-only from the hook and is surfaced by an
explicit `ledger_doctor --grudge-guard` invocation that `/handoff` and
`/finish` call — or it does not ship (criterion 8). This check forbids the
round-2 shape T-x replaced: a wired-nothing pair satisfiable by a flag that
argparse accepts but nothing runs. Three assertions:

  1. **Wiring clauses** — `ledger_doctor --grudge-guard` appears inside the
     `## Process` section of `skills/handoff/SKILL.md` and inside the
     `### Step 5.5` section of `skills/finish/SKILL.md` (clause-presence
     within a NAMED executable step section, NOT a whole-file substring and
     NOT a fenced example or comment — the check_handoff_stop_contract.py
     technique, round-3 finding S-4).
  2. **Executability** — `scripts/ledger_doctor.py --grudge-guard` exits 0 and
     emits its report header when run against a synthetic fixture directory
     via `--witness-dir` (T-o shape), not merely that argparse accepts the
     flag (SIEGE-R2-M9/CHAIN-4).
  3. **--selftest RED arms** — one per required clause, auto-generated off the
     same pins the real check uses.

Pure stdlib. Reads only tracked files + runs the tracked script, so it works
in CI / a shallow clone.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER_DOCTOR = ROOT / "scripts" / "ledger_doctor.py"
HANDOFF = ROOT / "skills" / "handoff" / "SKILL.md"
FINISH = ROOT / "skills" / "finish" / "SKILL.md"

INVOCATION = "ledger_doctor --grudge-guard"
# The fences may name the script with or without its `.py` suffix.
_INVOCATION_RE = re.compile(r"ledger_doctor(?:\.py)? --grudge-guard")

# Named executable-step section per skill; the invocation must appear inside
# the section BODY, after fenced blocks are removed.
SECTIONS = {
    "skills/handoff/SKILL.md": re.compile(r"^## Process\b.*?(?=^## |\Z)",
                                          re.DOTALL | re.MULTILINE),
    "skills/finish/SKILL.md": re.compile(r"^### Step 5\.5\b.*?(?=^###|\Z)",
                                         re.DOTALL | re.MULTILINE),
}

_FENCE_TICK = re.compile(r"^```[^\n]*\n.*?^```", re.DOTALL | re.MULTILINE)
_COMMENT_RE = re.compile(r"^[ \t]*(?:#|<!--).*$", re.MULTILINE)


def extract_section(text: str, rel: str) -> str:
    rx = SECTIONS[rel]
    matches = rx.findall(text)
    body = matches[-1] if matches else ""
    # Strip fenced examples and comment lines so the clause must be in real,
    # executable prose — not pasted as a non-running example (T-x, S-4).
    body = _FENCE_TICK.sub("", body)
    body = _COMMENT_RE.sub("", body)
    return body


def check_wiring(text: str, rel: str) -> list[str]:
    body = extract_section(text, rel)
    if not body:
        return [f"{rel}: named executable-step section not found"]
    if not _INVOCATION_RE.search(body):
        return [f"{rel}: `{INVOCATION}` missing from its named executable-step "
                f"section (Process / Step 5.5)"]
    return []


# Synthetic witnesses for the EXECUTABILITY arm: clean (nothing to report) and
# stale (a possibly-stuck session the reader MUST flag with a non-zero exit).
_PIN_REPO = "witness-tx"
_GOOD_ROWS = (
    "1735000000\tok-sess\twitness-tx\tBLOCK\tabcdef0123456789\n"
    "1735000001\tok-sess\twitness-tx\tCLEARED\t-\n"
)
_STALE_ROWS = (
    "1735000000\tstuck-sess\twitness-tx\tBLOCK\tabcdef0123456789\n"
)


def build_fixture(rows: str) -> str:
    d = tempfile.mkdtemp(prefix="grudge-guard-witness-")
    pathlib.Path(d, "outcomes.tsv").write_text(rows, encoding="utf-8")
    return d


def run_reader(fixture_dir: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(LEDGER_DOCTOR), "--grudge-guard",
         "--witness-dir", fixture_dir, f"--repo={_PIN_REPO}",
         "--witness-age-hours", "1"],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout


def check_reader() -> list[str]:
    """The reader must exit 0 + emit its header on the clean fixture, and exit
    non-zero on a stale fixture (a possible stuck guard must hard-fail)."""
    out: list[str] = []
    good = build_fixture(_GOOD_ROWS)
    stale = build_fixture(_STALE_ROWS)
    try:
        rc, stdout = run_reader(good)
        if rc != 0:
            out.append(f"ledger_doctor --grudge-guard exited {rc} on a clean "
                       f"fixture (expect 0)")
        if "=== grudge-guard witness ===" not in stdout:
            out.append("ledger_doctor --grudge-guard did not emit its report "
                       "header (=== grudge-guard witness ===)")
        rc3, stdout3 = run_reader(stale)
        if rc3 == 0:
            out.append("ledger_doctor --grudge-guard exited 0 on a STALE "
                       "fixture — a possibly-stuck stop hook must fail loudly")
        if "stuck-sess" not in stdout3:
            out.append("stale fixture did not name the stuck session in output")
    finally:
        for d in (good, stale):
            pathlib.Path(d, "outcomes.tsv").unlink(missing_ok=True)
            pathlib.Path(d).rmdir()
    return out


def selftest() -> int:
    errs: list[str] = []
    # 1. GOOD wiring samples per skill pass; per-clause RED when the
    #    invocation is removed from the named section.
    good_docs = {
        "skills/handoff/SKILL.md": "## Process\n\n- run `ledger_doctor "
        "--grudge-guard` here.\n--\n## Next\n",
        "skills/finish/SKILL.md": "### Step 5.5: Pre-Push Validation\n\nrun "
        "`ledger_doctor --grudge-guard`.\n\n### Step 6\n",
    }
    for rel, text in good_docs.items():
        e = check_wiring(text, rel)
        if e:
            errs.append(f"GOOD wiring sample failed: {rel}: {e}")
    for rel, text in good_docs.items():
        bad = text.replace(INVOCATION, "surfaced elsewhere")
        e = check_wiring(bad, rel)
        if not e:
            errs.append(f"RED wiring sample passed (invocation removed): {rel}")
    # 2. Fenced example must NOT satisfy the clause (S-4): invocation only
    #    inside ``` fences.
    fenced = ("## Process\n\n```bash\nledger_doctor --grudge-guard\n```\n"
              "--\n")
    if not check_wiring(fenced, "skills/handoff/SKILL.md"):
        errs.append("fenced-only invocation satisfied the wiring clause")
    # 3. Reader executability RED arm: analytic shape — since run_reader
    #    executes the tracked script, iterate the same checks over an
    #    obviously-broken fixture (malformed rows must still not mask the
    #    header). End-to-end cleanliness is covered by the real check.
    bad_dir = build_fixture("GARBAGE\tNOT\tTSV\n" + _STALE_ROWS)
    try:
        rc, stdout = run_reader(bad_dir)
        if "=== grudge-guard witness ===" not in stdout:
            errs.append("malformed+stale fixture lost the report header")
    finally:
        pathlib.Path(bad_dir, "outcomes.tsv").unlink(missing_ok=True)
        pathlib.Path(bad_dir).rmdir()

    if errs:
        print("SELFTEST FAIL:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("selftest OK — per-clause wiring RED arms fire; fenced examples do "
          "not satisfy the clause; reader executability is exercised.")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    errors: list[str] = []
    for rel in ("skills/handoff/SKILL.md", "skills/finish/SKILL.md"):
        p = ROOT / rel
        if not p.is_file():
            errors.append(f"{rel} is missing")
            continue
        errors += check_wiring(p.read_text(encoding="utf-8"), rel)
    errors += check_reader()

    if errors:
        print("GRUDGE-GUARD WITNESS WIRING FAILED (criterion 8):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK — `{INVOCATION}` is wired into handoff's Process and finish's "
          "Step 5.5, and the reader executes clean/stale fixtures correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())