#!/usr/bin/env python3
"""Cross-reference invariant: every live `crucible:<token>` resolves to a skill.

Invocation (from repo root):
    python3 scripts/check_crossref.py            # check the tracked tree
    python3 scripts/check_crossref.py --selftest # run the built-in logic tests

Scans every git-tracked `*.md` file for `crucible:<token>` references and
asserts each one resolves to a real `skills/<token>/` directory. Exits 0 if all
references resolve, 1 with a `file:line  crucible:<token>` list otherwise.
Stdlib only. The invariant covers TRACKED references only — a brand-new
untracked/not-yet-staged `.md` is invisible to `git ls-files` and is checked
once it is staged or committed.

Why: `cartographer-skill/SKILL.md` referenced `crucible:cartographer` (no such
skill) in its own feed-forward instructions, self-misrouting (#365 / A40). This
checker covers the `crucible:<token>` reference *form* (the namespaced-invocation
syntax). It does NOT cover the `skills/<token>/` path form or
`<!-- CANONICAL: shared/x.md -->` links — those are out of its scope.

Scope decisions:
- **git-tracked only.** Resolution runs over `git ls-files`, which lists tracked
  files only, so gitignored docs are naturally excluded. `docs/plans/`,
  `docs/prds/`, and `docs/handoffs/` are all gitignored (e.g. `docs/plans/`
  carries historical pre-rename names like `crucible:writing-plans`), so NEW
  files added under those paths are NOT scanned. Tracked surfaces ARE scanned:
  `skills/**`, top-level `docs/*.md`, `docs/research/` (not gitignored),
  `docs/ledger/`, etc. (Edge case: `docs/handoffs/` has one grandfathered
  tracked file committed before the ignore rule existed, which is still scanned.)
- **One blanket-exempt pattern + one resolved pattern** (real references, not
  skill directories):
  - documented template PLACEHOLDERS (`skill-name`, `old-name`, `new-name`) —
    literal fill-ins in authoring templates; blanket-exempt (forward-looking;
    only `skill-name` is currently used in a scanned file).
  - `crucible:crucible-*` — plugin-namespaced *agent types* (e.g.
    `crucible:crucible-red-team`). NOT blanket-exempt: each is RESOLVED against
    `agents/<token>.md` so a typo'd agent ref is still caught.
"""
from __future__ import annotations
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
REF_RE = re.compile(r"(?<![\w-])crucible:([a-z][a-z0-9-]*)")

# Documented template placeholders — fill-ins, not references to real skills.
PLACEHOLDERS = {"skill-name", "old-name", "new-name"}


def is_exempt(name: str) -> bool:
    """True only for documented template placeholders — literal fill-ins that
    are not references to real skills. Agent types are NOT exempt here; they are
    resolved against `agents/<token>.md` in resolves()."""
    return name in PLACEHOLDERS


def resolves(name: str) -> bool:
    if name.startswith("crucible-"):
        # Plugin-namespaced agent type: resolve against agents/<token>.md so a
        # typo'd agent ref is caught instead of blanket-exempted.
        return (ROOT / "agents" / f"{name}.md").is_file()
    return (SKILLS / name).is_dir()


def unresolved_in(text: str) -> list[tuple[int, str]]:
    """Return (lineno, token) for each non-exempt, non-resolving reference."""
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in REF_RE.finditer(line):
            name = m.group(1)
            if is_exempt(name) or resolves(name):
                continue
            out.append((i, name))
    return out


def tracked_md() -> list[pathlib.Path]:
    res = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT,
        capture_output=True, text=True, check=True)
    return [ROOT / p for p in res.stdout.splitlines() if p]


def main() -> int:
    errs: list[str] = []
    for path in tracked_md():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT)
        for lineno, name in unresolved_in(text):
            errs.append(f"  {rel}:{lineno}  crucible:{name}")
    if errs:
        print("BROKEN CROSS-REFERENCES (no matching skills/<token>/ dir):")
        print("\n".join(errs))
        print("\nIf the token is an agent type or template placeholder, add it "
              "to the exemptions in scripts/check_crossref.py.")
        return 1
    print("OK — every live crucible:<token> resolves to a skill directory.")
    return 0


def selftest() -> int:
    """Built-in regression cases for the resolution logic (no filesystem)."""
    cases = [
        # (token, exempt-or-resolves-expected, reason)
        ("cartographer", False, "the #365 bug: no skills/cartographer/ dir"),
        ("crucible-red-team", True, "agent type resolves via agents/<token>.md"),
        ("crucible-red-tea", False, "typo'd agent ref: no agents/<token>.md"),
        ("skill-name", True, "documented template placeholder"),
    ]
    failures = []
    for name, expect_ok, reason in cases:
        ok = is_exempt(name) or resolves(name)
        if ok != expect_ok:
            failures.append(f"  crucible:{name}: expected ok={expect_ok} "
                            f"({reason}), got {ok}")
    # A known-good skill must resolve (guards against a broken SKILLS path).
    if not resolves("quality-gate"):
        failures.append("  crucible:quality-gate should resolve but did not")
    # The bug must be *detected* by unresolved_in on synthetic text.
    sample = "2. `crucible:cartographer` consult\n`crucible:crucible-red-team` ok"
    found = unresolved_in(sample)
    if found != [(1, "cartographer")]:
        failures.append(f"  unresolved_in mismatch: {found!r}")
    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — exemptions and detection behave as specified.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
