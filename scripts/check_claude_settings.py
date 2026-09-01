#!/usr/bin/env python3
"""Structural check: the grudge Stop hook is really registered (#559, INV-C9).

Invocation (from repo root):
    python3 scripts/check_claude_settings.py            # gate the real repo
    python3 scripts/check_claude_settings.py --selftest # fixture-driven logic test

`hooks/grudge-resolution-guard.sh` only ever runs if Claude Code is told about
it. Before this check the only thing standing between "the hook exists" and
"the hook fires" was prose in `hooks/README.md`, so a registration that was
never made — or silently un-made by a `.gitignore` that swallows
`.claude/settings.json` again — would leave every part of #559 inert while the
tree looked perfectly correct. This asserts, mechanically:

  1. `.claude/settings.json` exists,
  2. it parses as JSON,
  3. some `hooks.Stop[].hooks[].command` names
     `hooks/grudge-resolution-guard.sh` (substring, so the
     `$CLAUDE_PROJECT_DIR`-prefixed form counts),
  4. `.gitignore` carries the literal line `.claude/*`,
  5. `.gitignore` carries the literal line `!.claude/settings.json`,
  6. `.gitignore` carries NO bare `.claude/` line (which would re-ignore the
     settings file and undo 4+5),
  7. `.claude/settings.json` is git-tracked
     (`git ls-files --error-unmatch` exits 0) — an untracked file registers the
     hook for exactly one working copy and for nobody else.

and, as a self-guard, 8. `main`'s own argv dispatch still routes the bare,
`--selftest` and unknown-argv paths correctly — see `check_dispatch`.

Style mirrors `scripts/check_handoff_stop_contract.py` /
`scripts/check_calibration_dispatch.py`: ROOT-from-`__file__`, error
accumulation, `sys.exit(main())`, stdlib only, no argparse.

Every checker takes an explicit `root`, so `--selftest` exercises the SAME code
path the bare run does against throwaway fixtures (real `git init`ed trees, not
argued equivalents) and covers the PASS **and** FAIL shape of all seven
assertions plus `main`'s own argv dispatch. A checker whose enforcement branch
has no fixture is a checker that can be mutated into a no-op without its suite
noticing; see `_selftest_dispatch` for the dispatch mutants specifically.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

SETTINGS_REL = ".claude/settings.json"
GITIGNORE_REL = ".gitignore"

# Substring, not equality: the committed registration is
# `bash "$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh"`, and a plain
# relative `bash hooks/grudge-resolution-guard.sh` is equally valid.
HOOK_COMMAND_SUBSTRING = "hooks/grudge-resolution-guard.sh"

GITIGNORE_REQUIRED_LINES = (".claude/*", "!.claude/settings.json")
GITIGNORE_FORBIDDEN_LINE = ".claude/"

USAGE = "usage: check_claude_settings.py [--selftest]"


# --------------------------------------------------------------------------
# assertions (each takes an explicit root so fixtures use the real code path)
# --------------------------------------------------------------------------
def stop_hook_commands(doc: object) -> list[str]:
    """Every `hooks.Stop[].hooks[].command` string in `doc`.

    Defensive at every level on purpose: a flat `{"command": ...}` Stop entry
    with no nested `hooks` array parses as JSON but Claude Code silently
    ignores it (see hooks/README.md), so it must yield NO commands here and
    fail assertion 3 rather than pass on a technicality.
    """
    commands: list[str] = []
    if not isinstance(doc, dict):
        return commands
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    stop = hooks.get("Stop")
    if not isinstance(stop, list):
        return commands
    for entry in stop:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("hooks")
        if not isinstance(inner, list):
            continue
        for hook in inner:
            if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                commands.append(hook["command"])
    return commands


def check_settings(root: pathlib.Path) -> list[str]:
    """Assertions 1-3. Later assertions presuppose earlier ones, so this
    returns the first blocking failure rather than a cascade of noise."""
    path = root / SETTINGS_REL
    if not path.is_file():
        return [f"{SETTINGS_REL} does not exist — the Stop hook is not registered"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return [f"{SETTINGS_REL} is not valid JSON: {exc}"]
    commands = stop_hook_commands(doc)
    if not any(HOOK_COMMAND_SUBSTRING in cmd for cmd in commands):
        found = ", ".join(repr(c) for c in commands) if commands else "no Stop commands at all"
        return [
            f"no hooks.Stop[].hooks[].command in {SETTINGS_REL} names "
            f"`{HOOK_COMMAND_SUBSTRING}` (found: {found})"
        ]
    return []


def check_gitignore(root: pathlib.Path) -> list[str]:
    """Assertions 4-6. All three are reported together: they are independent
    edits to the same file and a maintainer wants the whole list at once."""
    path = root / GITIGNORE_REL
    if not path.is_file():
        return [f"{GITIGNORE_REL} does not exist"]
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    errs: list[str] = []
    for required in GITIGNORE_REQUIRED_LINES:
        if required not in lines:
            errs.append(f"{GITIGNORE_REL} is missing the literal line `{required}`")
    if GITIGNORE_FORBIDDEN_LINE in lines:
        errs.append(
            f"{GITIGNORE_REL} still carries a bare `{GITIGNORE_FORBIDDEN_LINE}` line — "
            f"it re-ignores {SETTINGS_REL} and undoes the re-include"
        )
    return errs


def check_tracked(root: pathlib.Path) -> list[str]:
    """Assertion 7 — the real `git ls-files --error-unmatch`, not a proxy."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", SETTINGS_REL],
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:  # git absent / not executable
        return [f"could not run git to check that {SETTINGS_REL} is tracked: {exc}"]
    if proc.returncode != 0:
        return [
            f"{SETTINGS_REL} is not git-tracked "
            f"(`git ls-files --error-unmatch {SETTINGS_REL}` exit {proc.returncode}) — "
            f"stage it with `git add {SETTINGS_REL}`"
        ]
    return []


def collect_errors(root: pathlib.Path) -> list[str]:
    return check_settings(root) + check_gitignore(root) + check_tracked(root) + check_dispatch()


def run(root: pathlib.Path) -> int:
    errs = collect_errors(root)
    if errs:
        print("CLAUDE SETTINGS CHECK FAILED:")
        for err in errs:
            print(f"  - {err}")
        return 1
    print(
        "OK — .claude/settings.json is tracked, valid JSON, registers "
        "hooks/grudge-resolution-guard.sh on Stop, and .gitignore re-includes it."
    )
    return 0


# --------------------------------------------------------------------------
# selftest fixtures
# --------------------------------------------------------------------------
_GOOD_SETTINGS_TEXT = json.dumps(
    {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'bash "$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh"',
                            "timeout": 500,
                        }
                    ]
                }
            ]
        }
    },
    indent=2,
)

_GOOD_GITIGNORE_TEXT = "node_modules/\n.claude/*\n!.claude/settings.json\n.envrc\n"


def _make_fixture(
    parent: pathlib.Path,
    name: str,
    settings_text: str | None = _GOOD_SETTINGS_TEXT,
    gitignore_text: str | None = _GOOD_GITIGNORE_TEXT,
    track: bool = True,
) -> pathlib.Path:
    """Build a throwaway repo-shaped tree. `settings_text=None` omits the file;
    `track=False` leaves it unstaged so assertion 7 has a real RED case."""
    root = parent / name
    (root / ".claude").mkdir(parents=True)
    if settings_text is not None:
        (root / SETTINGS_REL).write_text(settings_text, encoding="utf-8")
    if gitignore_text is not None:
        (root / GITIGNORE_REL).write_text(gitignore_text, encoding="utf-8")
    subprocess.run(
        ["git", "init", "-q"], cwd=str(root),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )
    if track and settings_text is not None:
        subprocess.run(
            ["git", "add", "-f", SETTINGS_REL], cwd=str(root),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
    return root


def _quiet_run(root: pathlib.Path) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run(root)
    return rc, buf.getvalue()


def _selftest_assertions(tmp: pathlib.Path) -> None:
    # ---- PASS shape: every assertion satisfied -> no errors, run() == 0 -----
    good = _make_fixture(tmp, "good")
    assert collect_errors(good) == [], f"GOOD fixture should pass, got: {collect_errors(good)}"
    rc, out = _quiet_run(good)
    assert rc == 0, f"run() on the GOOD fixture must exit 0, got {rc}"
    assert "OK —" in out, f"GOOD run should print an OK line, got: {out!r}"

    # A plain relative command form must also pass (substring tolerance).
    rel = _make_fixture(
        tmp, "relative",
        settings_text=_GOOD_SETTINGS_TEXT.replace(
            'bash \\"$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh\\"',
            "bash hooks/grudge-resolution-guard.sh"),
    )
    assert collect_errors(rel) == [], (
        f"a plain `bash hooks/...` command must satisfy assertion 3, got: {collect_errors(rel)}")

    # ---- FAIL shape: one fixture per assertion -----------------------------
    # (label, fixture, substring the message must carry)
    cases: list[tuple[str, pathlib.Path, str]] = [
        # 1. file absent
        ("exists", _make_fixture(tmp, "no-settings", settings_text=None), "does not exist"),
        # 2. present but unparseable
        ("valid JSON", _make_fixture(tmp, "bad-json", settings_text="{not json,"), "not valid JSON"),
        # 3a. Stop hook names some OTHER script
        ("hook named", _make_fixture(
            tmp, "wrong-hook",
            settings_text=_GOOD_SETTINGS_TEXT.replace(
                "grudge-resolution-guard.sh", "gate-ledger-guard.sh")),
         "names `hooks/grudge-resolution-guard.sh`"),
        # 3b. right script, but on the WRONG event (PreToolUse, not Stop)
        ("hook named", _make_fixture(
            tmp, "wrong-event",
            settings_text=_GOOD_SETTINGS_TEXT.replace('"Stop"', '"PreToolUse"')),
         "no Stop commands at all"),
        # 3c. flat `{command: ...}` entry — parses, but Claude Code ignores it
        ("hook named", _make_fixture(
            tmp, "flat-entry",
            settings_text=json.dumps({"hooks": {"Stop": [
                {"type": "command",
                 "command": 'bash "$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh"'}]}})),
         "no Stop commands at all"),
        # 4. `.claude/*` missing
        ("gitignore .claude/*", _make_fixture(
            tmp, "no-star",
            gitignore_text=_GOOD_GITIGNORE_TEXT.replace(".claude/*\n", "")),
         "missing the literal line `.claude/*`"),
        # 5. `!.claude/settings.json` re-include missing
        ("gitignore re-include", _make_fixture(
            tmp, "no-reinclude",
            gitignore_text=_GOOD_GITIGNORE_TEXT.replace("!.claude/settings.json\n", "")),
         "missing the literal line `!.claude/settings.json`"),
        # 6. bare `.claude/` line still present
        ("gitignore bare line", _make_fixture(
            tmp, "bare-claude",
            gitignore_text=_GOOD_GITIGNORE_TEXT + ".claude/\n"),
         "still carries a bare `.claude/` line"),
        # 7. present and correct, but never staged
        ("git-tracked", _make_fixture(tmp, "untracked", track=False), "is not git-tracked"),
    ]
    for label, fixture, needle in cases:
        errs = collect_errors(fixture)
        assert any(needle in e for e in errs), (
            f"the {label!r} FAIL fixture should flag {needle!r}, got: {errs}")
        rc, out = _quiet_run(fixture)
        assert rc == 1, f"run() on the {label!r} FAIL fixture must exit 1, got {rc}"
        assert "CHECK FAILED" in out and needle in out, (
            f"the {label!r} failure must be PRINTED, not just counted; got: {out!r}")

    # A `.gitignore` that is missing entirely is its own distinct failure.
    none_gi = _make_fixture(tmp, "no-gitignore", gitignore_text=None)
    assert any("does not exist" in e for e in check_gitignore(none_gi)), (
        f"an absent .gitignore should be reported, got: {check_gitignore(none_gi)}")

    # A comment mentioning the pattern is not the pattern (line-literal, not
    # substring): `# .claude/*` must NOT satisfy assertion 4.
    commented = _make_fixture(
        tmp, "commented",
        gitignore_text=_GOOD_GITIGNORE_TEXT.replace(".claude/*\n", "# .claude/*\n"))
    assert any("`.claude/*`" in e for e in check_gitignore(commented)), (
        "a commented-out `.claude/*` must not satisfy assertion 4")


def _probe_dispatch() -> None:
    """argv dispatch is itself an enforcement surface — mutate it and the check
    silently stops running. Probed with stubs so no real repo is touched.
    Raises AssertionError on the first broken routing rule."""
    real_run, real_selftest = run, selftest
    seen: list[pathlib.Path] = []
    # The unknown-argv branch prints usage on stderr by design; swallow it here
    # so the probe stays quiet in CI without weakening what it asserts.
    err = io.StringIO()
    try:
        globals()["run"] = lambda root: (seen.append(root), 0)[1]
        globals()["selftest"] = lambda: 77

        rc_bare = main([])
        assert rc_bare == 0, f"bare argv should return run()'s code, got {rc_bare}"
        assert seen == [ROOT], f"bare argv must run the check exactly once on ROOT, got {seen}"

        rc_self = main(["--selftest"])
        assert rc_self == 77, f"--selftest must dispatch to selftest(), got {rc_self}"
        assert seen == [ROOT], "--selftest must NOT also run the repo check"

        for bad_argv in (["--bogus"], ["--selftest", "extra"], ["selftest"], ["--Selftest"]):
            with contextlib.redirect_stderr(err):
                rc_bad = main(bad_argv)
            assert rc_bad == 2, f"unknown argv {bad_argv} must exit 2, got {rc_bad}"
            assert seen == [ROOT], (
                f"unknown argv {bad_argv} must NOT silently run the check; calls={seen}")
    finally:
        globals()["run"] = real_run
        globals()["selftest"] = real_selftest
    assert "usage:" in err.getvalue(), "the unknown-argv branch must print usage on stderr"


def check_dispatch() -> list[str]:
    """Assertion 8 — a self-guard the BARE run carries, not only the selftest.

    Assertions 1-7 are only enforced if `main` still routes an argv to them, and
    a suite that is reached ONLY through `--selftest` structurally cannot notice
    that `--selftest` stopped running it: disable that branch and the suite goes
    quiet instead of red. So the routing contract is asserted from the gating
    path too, where a broken dispatch surfaces as an ordinary exit-1 failure.
    Costs microseconds — the probe stubs `run`/`selftest` and touches no repo.
    """
    try:
        _probe_dispatch()
    except AssertionError as exc:
        return [f"main()'s argv dispatch no longer routes correctly: {exc}"]
    return []


def selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        _selftest_assertions(pathlib.Path(td))
    dispatch_errs = check_dispatch()
    assert dispatch_errs == [], f"dispatch contract broken: {dispatch_errs}"
    print(
        "selftest OK — 7 repo assertions (settings exists / valid JSON / Stop command "
        "names the hook / .gitignore has `.claude/*` / has `!.claude/settings.json` / "
        "has no bare `.claude/` / file is git-tracked) each verified in their PASS "
        "and FAIL shape against real git fixtures, run() exits 1 and PRINTS every "
        "failure, and the 8th (main()'s argv dispatch: bare, --selftest and "
        "unknown-argv routing) is asserted here AND by the bare gating run."
    )
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--selftest"]:
        return selftest()
    if args:
        print(f"unknown argument(s): {' '.join(args)}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    return run(ROOT)


if __name__ == "__main__":
    sys.exit(main())
