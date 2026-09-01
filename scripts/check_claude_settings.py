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
     hook for exactly one working copy and for nobody else,
  8. the script the registration NAMES actually exists as a regular file under
     the root — a registration pointing at a deleted or renamed script is the
     same declared-but-not-wired failure this check exists to eliminate,

and, as self-guards, 9. `main`'s own argv dispatch still routes the bare,
`--selftest` and unknown-argv paths correctly (see `check_dispatch`), and
10. the `__main__` block still consumes the verdict each mode computes (see
`check_entrypoint`) — replacing either `sys.exit(...)` line with a constant
does not make an assertion vacuous, it stops the interpreter from reaching
one, which is why that guard is made of source text.

Style mirrors `scripts/check_handoff_stop_contract.py` /
`scripts/check_calibration_dispatch.py`: ROOT-from-`__file__`, error
accumulation, `sys.exit(main())`, stdlib only, no argparse. Exit codes are
`0` (ok) or `1` (any failure, including unknown argv), per the #558/#559
contract's `returns: exit code 0|1`.

Every checker takes an explicit `root`, so `--selftest` exercises the SAME code
path the bare run does against throwaway fixtures (real `git init`ed trees, not
argued equivalents) and covers the PASS **and** FAIL shape of all eight repo
assertions plus `main`'s own argv dispatch. A checker whose enforcement branch
has no fixture is a checker that can be mutated into a no-op without its suite
noticing, so the self-verifying layers get fixtures too:
`_selftest_dispatch` drives `_probe_dispatch` against deliberately broken
`main`s (one defect per routing rule), and `_selftest_children` runs THIS FILE
as a subprocess — the only vantage point from which `sys.exit(main())` and the
"is the guard still wired into the gating path" questions are observable at
all. Selftest failures are raised, never returned, so a mutated `sys.exit(0)`
cannot swallow them; and they are raised through `_require`, not `assert`, so
`python3 -O` cannot strip them.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

SCRIPT_REL = "scripts/check_claude_settings.py"
SETTINGS_REL = ".claude/settings.json"
GITIGNORE_REL = ".gitignore"

# Substring, not equality: the committed registration is
# `bash "$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh"`, and a plain
# relative `bash hooks/grudge-resolution-guard.sh` is equally valid.
HOOK_COMMAND_SUBSTRING = "hooks/grudge-resolution-guard.sh"

GITIGNORE_REQUIRED_LINES = (".claude/*", "!.claude/settings.json")
GITIGNORE_FORBIDDEN_LINE = ".claude/"

USAGE = "usage: check_claude_settings.py [--selftest]"

# Assertion 10's subject. `sys.exit(selftest())` -> `sys.exit(0)` silences the
# whole suite and leaves BARE working, so the bare gating run is the vantage
# point that catches it; `sys.exit(main())` -> `sys.exit(0)` silences bare and
# leaves `--selftest` working, so the subprocess battery catches that one.
# Each of the two entry lines is pinned by the mode the other mutant spares.
_ENTRY_MARKER = 'if __name__ == "__main__":'
_ENTRY_REQUIRED = ("sys.exit(selftest())", "sys.exit(main())")

# Set on children this file spawns from `--selftest`, so a child does not
# re-run the subprocess battery and fork-bomb the suite.
_CHILD_ENV = "CHECK_CLAUDE_SETTINGS_SELFTEST_CHILD"


def _require(condition: object, message: str) -> None:
    """An `assert` that `python3 -O` cannot strip.

    The selftest is an enforcement surface: an interpreter flag must not be
    able to turn it into a green no-op, which is exactly what bare `assert`
    allows (`python3 -O` / `PYTHONOPTIMIZE=1` removes every one of them).
    """
    if not condition:
        raise AssertionError(message)


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


def check_hook_script(root: pathlib.Path) -> list[str]:
    """Assertion 8 — the script the registration NAMES is really there.

    Assertion 3 only proves the settings file *mentions* the hook. Deleting or
    renaming `hooks/grudge-resolution-guard.sh` is the single most likely
    future regression, and without this the check keeps affirming a
    registration whose command can only ever exit 127.

    The executable bit is deliberately NOT required: the registered command is
    `bash "<path>"`, which runs a mode-644 file fine, and every hook in this
    repo is committed 100644.
    """
    path = root / HOOK_COMMAND_SUBSTRING
    if not path.is_file():
        return [
            f"{SETTINGS_REL} registers `{HOOK_COMMAND_SUBSTRING}` but that file does "
            f"not exist under {root} — the registered command can only exit 127"
        ]
    return []


def _entrypoint_errors(text: str) -> list[str]:
    """Assertion 10, as a pure function over source text so it can have real
    PASS and FAIL fixtures instead of being asserted only about itself."""
    _head, sep, tail = text.rpartition(_ENTRY_MARKER)
    if not sep:
        return [f"{SCRIPT_REL} has no `{_ENTRY_MARKER}` block — nothing runs at all"]
    return [
        f"{SCRIPT_REL}'s `{_ENTRY_MARKER}` block no longer carries `{needed}` — "
        f"the mode it dispatches computes a verdict that nothing consumes"
        for needed in _ENTRY_REQUIRED
        if needed not in tail
    ]


def check_entrypoint() -> list[str]:
    """Assertion 10 — the outermost lines, which no in-process check can see.

    A mutant that replaces an entry line with a constant does not merely make
    an assertion vacuous; it stops the interpreter from ever reaching one. The
    guard therefore has to be made of source text, read back from disk, and it
    has to run on the gating path so it survives the mutant that kills the
    selftest.
    """
    try:
        text = pathlib.Path(__file__).resolve().read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"could not read {SCRIPT_REL} to check its entry point: {exc}"]
    return _entrypoint_errors(text)


def collect_errors(root: pathlib.Path) -> list[str]:
    return (
        check_settings(root)
        + check_gitignore(root)
        + check_tracked(root)
        + check_hook_script(root)
        + check_dispatch()
        + check_entrypoint()
    )


def run(root: pathlib.Path) -> int:
    errs = collect_errors(root)
    if errs:
        print("CLAUDE SETTINGS CHECK FAILED:")
        for err in errs:
            print(f"  - {err}")
        return 1
    print(
        "OK — .claude/settings.json is tracked, valid JSON, registers "
        "hooks/grudge-resolution-guard.sh on Stop, that script exists, "
        "and .gitignore re-includes it."
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
    hook: bool = True,
) -> pathlib.Path:
    """Build a throwaway repo-shaped tree. `settings_text=None` omits the file;
    `track=False` leaves it unstaged so assertion 7 has a real RED case;
    `hook=False` omits the registered hook script so assertion 8 does too."""
    root = parent / name
    (root / ".claude").mkdir(parents=True)
    if settings_text is not None:
        (root / SETTINGS_REL).write_text(settings_text, encoding="utf-8")
    if gitignore_text is not None:
        (root / GITIGNORE_REL).write_text(gitignore_text, encoding="utf-8")
    if hook:
        hook_path = root / HOOK_COMMAND_SUBSTRING
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
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


def _selftest_assertions(tmp: pathlib.Path) -> int:
    """PASS and FAIL shape for assertions 1-8. Returns the number of fixtures
    it actually exercised, so `selftest` can pin that this ran at all."""
    exercised = 0

    # ---- PASS shape: every assertion satisfied -> no errors, run() == 0 -----
    good = _make_fixture(tmp, "good")
    _require(collect_errors(good) == [],
             f"GOOD fixture should pass, got: {collect_errors(good)}")
    rc, out = _quiet_run(good)
    _require(rc == 0, f"run() on the GOOD fixture must exit 0, got {rc}")
    _require("OK —" in out, f"GOOD run should print an OK line, got: {out!r}")
    exercised += 1

    # A plain relative command form must also pass (substring tolerance).
    rel = _make_fixture(
        tmp, "relative",
        settings_text=_GOOD_SETTINGS_TEXT.replace(
            'bash \\"$CLAUDE_PROJECT_DIR/hooks/grudge-resolution-guard.sh\\"',
            "bash hooks/grudge-resolution-guard.sh"),
    )
    _require(collect_errors(rel) == [],
             f"a plain `bash hooks/...` command must satisfy assertion 3, got: {collect_errors(rel)}")
    exercised += 1

    # Trailing whitespace on a `.gitignore` line is insignificant to git, so it
    # must be insignificant here too (pins the `.strip()`, which is tolerance,
    # not enforcement).
    padded = _make_fixture(
        tmp, "padded-gitignore",
        gitignore_text=_GOOD_GITIGNORE_TEXT.replace(".claude/*\n", ".claude/*   \n"))
    _require(collect_errors(padded) == [],
             f"trailing whitespace must not break assertion 4, got: {collect_errors(padded)}")
    exercised += 1

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
        # 8. registered, but the script it names was deleted/renamed
        ("hook script exists", _make_fixture(tmp, "no-hook-script", hook=False),
         "but that file does not exist"),
    ]
    for label, fixture, needle in cases:
        errs = collect_errors(fixture)
        _require(any(needle in e for e in errs),
                 f"the {label!r} FAIL fixture should flag {needle!r}, got: {errs}")
        rc, out = _quiet_run(fixture)
        _require(rc == 1, f"run() on the {label!r} FAIL fixture must exit 1, got {rc}")
        _require("CHECK FAILED" in out and needle in out,
                 f"the {label!r} failure must be PRINTED, not just counted; got: {out!r}")
        exercised += 1

    # A `.gitignore` that is missing entirely is its own distinct failure.
    none_gi = _make_fixture(tmp, "no-gitignore", gitignore_text=None)
    _require(any("does not exist" in e for e in check_gitignore(none_gi)),
             f"an absent .gitignore should be reported, got: {check_gitignore(none_gi)}")
    exercised += 1

    # A comment mentioning the pattern is not the pattern (line-literal, not
    # substring): `# .claude/*` must NOT satisfy assertion 4.
    commented = _make_fixture(
        tmp, "commented",
        gitignore_text=_GOOD_GITIGNORE_TEXT.replace(".claude/*\n", "# .claude/*\n"))
    _require(any("`.claude/*`" in e for e in check_gitignore(commented)),
             "a commented-out `.claude/*` must not satisfy assertion 4")
    exercised += 1

    # ---- assertion 10: PASS and FAIL shape over real source text ---------
    entry_src = pathlib.Path(__file__).resolve().read_text(encoding="utf-8")
    _require(_entrypoint_errors(entry_src) == [],
             f"the real entry point must pass assertion 10, got: {_entrypoint_errors(entry_src)}")
    exercised += 1
    for dead in _ENTRY_REQUIRED:
        maimed = entry_src.replace(dead, "sys.exit(0)")
        _require(maimed != entry_src, f"assertion-10 fixture for {dead!r} changed nothing")
        _require(any(dead in e for e in _entrypoint_errors(maimed)),
                 f"a `__main__` block missing `{dead}` must be flagged, "
                 f"got: {_entrypoint_errors(maimed)}")
        exercised += 1
    _require(_entrypoint_errors("x = 1\n") != [],
             "a source file with no `__main__` block at all must be flagged")
    exercised += 1

    return exercised


# --------------------------------------------------------------------------
# assertion 9: main()'s argv dispatch, and the fixtures that make it go red
# --------------------------------------------------------------------------
def _probe_dispatch(main_fn) -> list[str]:
    """Every way `main_fn` violates the argv-dispatch contract, one per entry.

    Returns error strings rather than raising, so the caller decides whether a
    violation is an exit-1 gate failure (the bare run) or a selftest fixture
    expectation. Stubs `run`/`selftest` through `globals()`, so no real repo is
    touched, and restores them in a `finally`.
    """
    real_run, real_selftest = run, selftest
    seen: list[pathlib.Path] = []
    errs: list[str] = []
    # The unknown-argv branch prints usage on stderr by design; capture it here
    # so the probe stays quiet in CI without weakening what it asserts.
    err = io.StringIO()
    try:
        globals()["run"] = lambda root: (seen.append(root), 0)[1]
        globals()["selftest"] = lambda: 77

        with contextlib.redirect_stderr(err):
            rc_bare = main_fn([])
            if rc_bare != 0:
                errs.append(f"bare argv must return run()'s code, got {rc_bare}")
            if seen != [ROOT]:
                errs.append(f"bare argv must run the check exactly once on ROOT, got {seen}")
            after_bare = list(seen)

            rc_self = main_fn(["--selftest"])
            if rc_self != 77:
                errs.append(f"--selftest must dispatch to selftest(), got {rc_self}")
            if seen != after_bare:
                errs.append("--selftest must NOT also run the repo check")
            after_self = list(seen)

            for bad_argv in (["--bogus"], ["--self-test"], ["--selftest", "extra"],
                             ["selftest"], ["--Selftest"], ["-h"], ["--help"], ["foo"]):
                rc_bad = main_fn(bad_argv)
                if rc_bad != 1:
                    errs.append(f"unknown argv {bad_argv} must exit 1, got {rc_bad}")
                if seen != after_self:
                    errs.append(
                        f"unknown argv {bad_argv} must NOT silently run the check; calls={seen}")
    finally:
        globals()["run"] = real_run
        globals()["selftest"] = real_selftest
    if "usage:" not in err.getvalue():
        errs.append("the unknown-argv branch must print usage on stderr")
    return errs


def _broken_main(defect: str):
    """A `main`-shaped callable carrying exactly ONE routing defect.

    These are the FAIL fixtures for assertion 9: without them `_probe_dispatch`
    has a PASS shape and no FAIL shape, and any single check inside it can be
    deleted without the suite noticing. `defect="none"` is the PASS shape and
    proves the harness is not vacuously red.
    """
    def broken(argv: list[str] | None = None) -> int:
        args = list(sys.argv[1:] if argv is None else argv)
        if args == ["--selftest"] and defect != "selftest-not-routed":
            if defect == "selftest-also-runs-check":
                run(ROOT)
            return selftest()
        if args:
            if defect == "unknown-argv-runs-check":
                return run(ROOT)
            if defect != "unknown-argv-no-usage":
                print(f"unknown argument(s): {' '.join(args)}", file=sys.stderr)
                print(USAGE, file=sys.stderr)
            return 0 if defect == "unknown-argv-exit-0" else 1
        if defect == "bare-skips-check":
            return 0
        if defect == "bare-wrong-code":
            run(ROOT)
            return 9
        return run(ROOT)
    return broken


def _selftest_dispatch() -> int:
    """FAIL shape for every rule `_probe_dispatch` enforces, plus its PASS
    shape. Returns the number of cases exercised."""
    # PASS shape — a correct main, and the real one, must both probe clean.
    _require(_probe_dispatch(_broken_main("none")) == [],
             f"an undefected main must probe clean, got: {_probe_dispatch(_broken_main('none'))}")
    cases = [
        ("bare-wrong-code", "bare argv must return run()'s code"),
        ("bare-skips-check", "exactly once on ROOT"),
        ("selftest-not-routed", "--selftest must dispatch to selftest()"),
        ("selftest-also-runs-check", "must NOT also run the repo check"),
        ("unknown-argv-exit-0", "must exit 1"),
        ("unknown-argv-runs-check", "must NOT silently run the check"),
        ("unknown-argv-no-usage", "must print usage on stderr"),
    ]
    for defect, needle in cases:
        errs = _probe_dispatch(_broken_main(defect))
        _require(any(needle in e for e in errs),
                 f"the {defect!r} broken main should flag {needle!r}, got: {errs}")
    return len(cases)


def check_dispatch() -> list[str]:
    """Assertion 9 — a self-guard the BARE run carries, not only the selftest.

    Assertions 1-8 are only enforced if `main` still routes an argv to them, and
    a suite that is reached ONLY through `--selftest` structurally cannot notice
    that `--selftest` stopped running it: disable that branch and the suite goes
    quiet instead of red. So the routing contract is asserted from the gating
    path too, where a broken dispatch surfaces as an ordinary exit-1 failure.
    Costs microseconds — the probe stubs `run`/`selftest` and touches no repo.
    """
    return [
        f"main()'s argv dispatch no longer routes correctly: {e}"
        for e in _probe_dispatch(main)
    ]


# --------------------------------------------------------------------------
# the subprocess layer: the only vantage point outside this process
# --------------------------------------------------------------------------
def _install_copy(root: pathlib.Path, text: str) -> pathlib.Path:
    """Drop `text` into `<root>/scripts/<this file's name>` so the copy's
    ROOT-from-`__file__` resolves to `root`."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    path = scripts / pathlib.Path(__file__).name
    path.write_text(text, encoding="utf-8")
    return path


def _run_child(script: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable]
    # Keep the child in the same -O regime as the parent, so the `-O` column of
    # a mutation battery measures the child too, not just this process.
    if sys.flags.optimize == 1:
        cmd.append("-O")
    elif sys.flags.optimize >= 2:
        cmd.append("-OO")
    cmd += [str(script), *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(script.parent.parent),
        env={**os.environ, _CHILD_ENV: "1"}, check=False,
    )


def _mutate_source(text: str, old: str, new: str, label: str) -> str:
    """Textual mutation with a fixture-integrity guard: a replacement that
    matched zero (or several) times would silently produce a NON-mutant and the
    case below would pass for the wrong reason."""
    _require(text.count(old) == 1,
             f"{label}: expected exactly one occurrence of {old!r}, found {text.count(old)}")
    return text.replace(old, new, 1)


def _selftest_children(tmp: pathlib.Path) -> int:
    """Run THIS FILE as a subprocess and assert the CHILD's exit code.

    Nothing inside the process can observe `sys.exit(main())`: mutate it to
    `sys.exit(0)` and every in-process assertion still passes while the gate
    reports green. Nothing inside the process can observe that `check_dispatch`
    is still wired into `collect_errors` either — `selftest` calls it a second
    time on its own, which masks the removal. Both become visible here.

    Selftest failures are RAISED (`_require`), never returned, so a mutated
    `sys.exit(0)` cannot swallow this battery's own verdict.
    """
    cases = 0
    source = pathlib.Path(__file__).resolve().read_text(encoding="utf-8")

    def expect(name: str, script: pathlib.Path, args: list[str], want_rc: int,
               want_out: str = "", want_err: str = "") -> None:
        nonlocal cases
        proc = _run_child(script, args)
        _require(proc.returncode == want_rc,
                 f"{name}: child argv {args} exited {proc.returncode}, expected {want_rc} "
                 f"(stdout {proc.stdout.strip()!r}, stderr {proc.stderr.strip()!r})")
        _require(want_out in proc.stdout,
                 f"{name}: child stdout missing {want_out!r}; got {proc.stdout.strip()!r}")
        _require(want_err in proc.stderr,
                 f"{name}: child stderr missing {want_err!r}; got {proc.stderr.strip()!r}")
        cases += 1

    # -- the real script, unmutated ----------------------------------------- #
    good = _make_fixture(tmp, "child-good")
    good_script = _install_copy(good, source)
    expect("child-bare-pass", good_script, [], 0, want_out="OK —")
    expect("child-selftest", good_script, ["--selftest"], 0, want_out="selftest OK")

    bad = _make_fixture(tmp, "child-bad", settings_text=None)
    bad_script = _install_copy(bad, source)
    # A RED bare child: the only in-repo place where a non-zero exit code of
    # THIS script is actually observed.
    expect("child-bare-fail", bad_script, [], 1, want_out="does not exist")

    for bad_argv in (["--bogus"], ["--self-test"], ["-h"], ["--help"], ["foo"],
                     ["--selftest", "extra"]):
        expect(f"child-reject-{'_'.join(bad_argv)}", good_script, bad_argv, 1,
               want_err="usage:")

    # -- a copy whose `--selftest` routing is broken ------------------------- #
    # Its BARE run must go red: that is the whole reason `check_dispatch()` sits
    # in `collect_errors`. Drop it from there (or empty out `check_dispatch`, or
    # delete the `--selftest`-routing rule from `_probe_dispatch`) and this
    # child returns 0.
    typo = _make_fixture(tmp, "child-selftest-typo")
    typo_script = _install_copy(typo, _mutate_source(
        source,
        '    if args == ["--selftest"]:\n        return selftest()\n',
        '    if args == ["--selftest-DISABLED"]:\n        return selftest()\n',
        "selftest-route mutant"))
    expect("child-broken-selftest-route-bare", typo_script, [], 1,
           want_out="argv dispatch no longer routes correctly")

    # -- a copy whose BARE routing is broken --------------------------------- #
    # Its `--selftest` must go red: that is the reason `selftest()` re-asserts
    # `check_dispatch()`. Drop that assertion and this child returns 0.
    noop = _make_fixture(tmp, "child-bare-noop")
    noop_script = _install_copy(noop, _mutate_source(
        source, "\n    return run(ROOT)\n", "\n    return 0  # bare check disabled\n",
        "bare-route mutant"))
    expect("child-broken-bare-route-selftest", noop_script, ["--selftest"], 1)

    # -- a copy whose ENTRY POINT no longer runs the selftest ---------------- #
    # `sys.exit(selftest())` -> `sys.exit(0)` makes `--selftest` a silent green
    # that no assertion inside it can see, because none of them run. Its BARE
    # run is untouched, and assertion 10 is what makes it red.
    dead_entry = _make_fixture(tmp, "child-dead-entry")
    dead_script = _install_copy(dead_entry, _mutate_source(
        source, "\n        sys.exit(selftest())\n", "\n        sys.exit(0)\n",
        "dead-selftest-entry mutant"))
    expect("child-dead-selftest-entry-bare", dead_script, [], 1,
           want_out="no longer carries")

    # -- a copy with a REPO assertion neutered ------------------------------- #
    # Pins from outside that the fixture battery still runs: skip it (and fake
    # its count) and this child stops going red.
    dead_check = _make_fixture(tmp, "child-dead-check")
    check_script = _install_copy(dead_check, _mutate_source(
        source, "\n    path = root / SETTINGS_REL\n",
        "\n    return []\n    path = root / SETTINGS_REL\n",
        "assertion-1-3 mutant"))
    expect("child-dead-settings-check-selftest", check_script, ["--selftest"], 1)

    # -- a copy with one _probe_dispatch rule neutered ----------------------- #
    # Pins from outside that the dispatch battery still runs: only
    # `_selftest_dispatch`'s "bare-skips-check" fixture notices this.
    weak = _make_fixture(tmp, "child-weak-probe")
    weak_script = _install_copy(weak, _mutate_source(
        source, "\n            if seen != [ROOT]:\n",
        "\n            if False:  # bare-ran-once rule removed\n",
        "probe-weakening mutant"))
    expect("child-weakened-probe-selftest", weak_script, ["--selftest"], 1)

    return cases


def selftest() -> int:
    # `_require` is the mechanism every check below runs through, so the guard
    # chain terminates here: prove the helper still bites, with a raw `raise`
    # that does not itself go through `_require`. Neuter `_require` and every
    # battery below would otherwise pass vacuously.
    try:
        _require(False, "sentinel")
    except AssertionError:
        pass
    else:
        raise AssertionError("_require no longer raises — every check below is vacuous")
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        exercised = _selftest_assertions(tmp)
        _require(exercised == 19,
                 f"the fixture battery must exercise 19 fixtures, ran {exercised} — "
                 f"a skipped battery is a silent green")
        dispatch_cases = _selftest_dispatch()
        _require(dispatch_cases == 7,
                 f"the dispatch battery must exercise 7 broken mains, ran {dispatch_cases}")
        if os.environ.get(_CHILD_ENV):
            child_cases = -1
            print("(child process: subprocess battery skipped)")
        else:
            child_cases = _selftest_children(tmp)
            _require(child_cases == 14,
                     f"the subprocess battery must exercise 14 children, ran {child_cases}")
    dispatch_errs = check_dispatch()
    _require(dispatch_errs == [], f"dispatch contract broken: {dispatch_errs}")
    print(
        "selftest OK — 8 repo assertions (settings exists / valid JSON / Stop command "
        "names the hook / .gitignore has `.claude/*` / has `!.claude/settings.json` / "
        "has no bare `.claude/` / file is git-tracked / the named hook script exists) "
        "each verified in their PASS and FAIL shape against real git fixtures, run() "
        "exits 1 and PRINTS every failure; the 9th (main()'s argv dispatch) has a FAIL "
        "fixture per routing rule and is re-asserted by the bare gating run; the 10th "
        "(the `__main__` block still consuming each mode's verdict) has PASS and FAIL "
        f"fixtures over real source text; and {child_cases} subprocess runs of this "
        "file pin the child's exit code per mode, five of them mutated copies that must "
        "go red. Raised, not returned, and via _require, so neither `sys.exit(0)` nor "
        "`python3 -O` can silence it."
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
        return 1
    return run(ROOT)


if __name__ == "__main__":
    # `--selftest` is dispatched HERE rather than through `main()`'s return
    # value, mirroring `scripts/check_stdlib_only.py`. `sys.exit(main())` ->
    # `sys.exit(0)` deletes the call to `main` outright: nothing inside this
    # process runs, so no in-process assertion could ever observe it. Routing
    # the assertion-carrying mode past that line is what makes the mutant
    # visible — `--selftest` still runs, and its subprocess battery sees the
    # now-dead bare mode. `main` still routes `--selftest` itself and
    # `check_dispatch` pins that, so the two cannot drift apart; and assertion
    # 10 pins that BOTH of these two lines are still here.
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main())
