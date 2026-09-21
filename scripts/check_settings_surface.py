#!/usr/bin/env python3
"""Structural check: no tracked app-config may register executable hooks (#604).

Invocation (from repo root):
    python3 scripts/check_settings_surface.py            # gate the real repo
    python3 scripts/check_settings_surface.py --selftest # fixture-driven logic test

GH-604 (siege S-1): a committed `.claude/settings.json` that registers a hook by
path turns every PR checkout into an arbitrary-code execution surface on the
reviewer's machine. `.claude/settings.json:6` was force-added past `.gitignore`
(#559), registering a blocking Stop hook whose body (`hooks/grudge-resolution-guard.sh`)
and helper (`scripts/grudge_query.py`) live in the SAME tracked tree — so a
contributor touching any of those files runs their code with the maintainer's
full privileges the moment the maintainer runs `gh pr checkout N` and ends a
turn. Claude Code's directory-trust prompt does not help: it is per-directory,
so checking out a branch inside an already-`/trust`ed repo does not re-prompt.
Verified: a contributor-modified helper created a marker file in `$HOME` from the
hook's argv on an ordinary Stop. The `/.claude/` git-ignore being blanket means
the ONLY legal settings registration points for a repo-owned hook are per-machine
and untracked: `.claude/settings.local.json` or user-global `~/.claude/settings.json`
(the `build-routing-advisor` convention). A plugin manifest may separately
declare hooks (see `.claude-plugin/plugin.json`, #591), which fire on explicit
per-machine plugin enable — not a checkout side-effect. This check pins the
settings surface closed:

  1. `.claude/settings.json` (and any other tracked file under `.claude/`) is
     NOT git-tracked — `git ls-files` must list nothing under `.claude/`.
  2. `.gitignore` carries the blanket `.claude/` ignore and no `!`-negation that
     re-includes any part of `.claude/` (the #559 prologue added exactly such a
     negation to re-track the settings file; both must be absent).
  3. `hooks/README.md` carries the "Hook Registration Surface" contract — the
     two per-machine registration points, the prohibition on registering
     executable hooks in committed config, and the hooks/scripts diff review
     rule.

Style mirrors `scripts/check_handoff_stop_contract.py`: ROOT-from-`__file__`,
error accumulation, `sys.exit(main())`, stdlib only, no argparse. The selftest
drives the SAME check functions against throwaway fixtures (real `git init`ed
trees for the tracking assertions) covering the PASS and FAIL shape of every
assertion — including the git-unavailable fail-closed branch — so an enforcement
branch cannot be mutated into a no-op without the suite noticing. Selftest
failures raise; they are never returned.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETTINGS_REL = ".claude/settings.json"

# Contract the Hook Registration Surface section of hooks/README.md must carry.
README_CONTRACT: dict[str, str] = {
    "machine-local registration point": "settings.local.json",
    "user-global registration point": "~/.claude/settings.json",
    "committed-config prohibition": "never in a committed `.claude/settings.json`",
    "hooks/scripts diff review rule": "a `hooks/` or `scripts/` diff",
}

_SECTION_RE = re.compile(
    r"^## Hook Registration Surface\b.*?(?=^## |\Z)",
    re.DOTALL | re.MULTILINE,
)


def extract_surface_section(text: str) -> str:
    matches = _SECTION_RE.findall(text)
    return matches[-1] if matches else ""


def tracked_under_claude(root: pathlib.Path) -> list[str] | None:
    """Tracked paths under `.claude/` at any depth (or None if unverifiable)."""
    # Two pathspecs: root `.claude/` and any-depth `**/.claude/**` — the blanket
    # gitignore rule matches at every depth, so the tracking assertion must too.
    pathspecs = [".claude/", ":(glob)**/.claude/**"]
    tracked: set[str] = set()
    for ps in pathspecs:
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--", ps],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        if out.returncode != 0:
            return None
        tracked.update(p.strip() for p in out.stdout.splitlines() if p.strip())
    return sorted(tracked)


def check_tracking(root: pathlib.Path) -> list[str]:
    tracked = tracked_under_claude(root)
    if tracked is None:
        return [
            "could not verify git tracking of `.claude/` (git ls-files failed) — "
            "gate cannot confirm no tracked app-config; treat as FAILED"
        ]
    if not tracked:
        return []
    critical = [p for p in tracked if p == SETTINGS_REL]
    lines = []
    if critical:
        lines.append(
            f"execution surface: `{SETTINGS_REL}` is git-TRACKED; a committed "
            "app-config registering hooks runs contributor code on the reviewer's "
            "machine at Stop (GH-604). Register hooks in untracked "
            "settings.local.json / ~/.claude/settings.json, and git rm this file."
        )
    rest = [p for p in tracked if p != SETTINGS_REL]
    if rest:
        lines.append(
            "tracked file(s) under `.claude/` (machine-local session state, "
            "public repo): " + ", ".join(f"`{p}`" for p in rest)
        )
    return lines


def check_gitignore(root: pathlib.Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.is_file():
        return ["`.gitignore` missing"]
    lines = gi.read_text(encoding="utf-8").splitlines()
    errors = []
    if not any(l.strip() == ".claude/" for l in lines):
        errors.append("`.gitignore` lacks the blanket `.claude/` ignore line")
    for l in lines:
        s = l.strip()
        body = s[1:] if s.startswith("!") else ""
        body = body.lstrip("/")
        if body == ".claude" or body.startswith(".claude/") or body.startswith("**/.claude"):
            errors.append(
                f"`.gitignore` carries a `!`-negation re-including `.claude/` "
                f"(`{l}`) — that is how #559 re-tracked the settings file; remove it"
            )
    return errors


def check_readme_contract(root: pathlib.Path) -> list[str]:
    readme = root / "hooks/README.md"
    if not readme.is_file():
        return ["`hooks/README.md` missing"]
    section = extract_surface_section(readme.read_text(encoding="utf-8"))
    if not section:
        return ["no `## Hook Registration Surface` section in hooks/README.md"]
    return [
        f"missing {label} in Hook Registration Surface section: `{sub}`"
        for label, sub in README_CONTRACT.items()
        if sub not in section
    ]


# --------------------------------------------------------------------------
# selftest — throwaway fixtures, never the real repo
# --------------------------------------------------------------------------
def _git_init(path: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "selftest@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "selftest"],
        check=True,
    )


def _write_gitignore(path: pathlib.Path, content: str) -> None:
    (path / ".gitignore").write_text(content, encoding="utf-8")


def selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)

        # -- tracking assertions (real git trees) -------------------------
        good = tmp / "good"
        good.mkdir()
        _git_init(good)
        _write_gitignore(good, ".claude/\nnode_modules/\n")
        (good / "x.txt").write_text("hi", encoding="utf-8")
        subprocess.run(["git", "-C", str(good), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(good), "commit", "-qm", "init"], check=True
        )
        assert check_tracking(good) == [], f"clean tree should pass, got: {check_tracking(good)}"

        evil = tmp / "evil"
        evil.mkdir()
        _git_init(evil)
        _write_gitignore(evil, ".claude/\n")
        settings = evil / SETTINGS_REL
        settings.parent.mkdir()
        settings.write_text(
            '{"hooks":{"Stop":[{"hooks":[{"type":"command",'
            '"command":"bash $CLAUDE_PROJECT_DIR/hooks/x.sh"}]}]}}',
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(evil), "add", "-f", SETTINGS_REL], check=True)
        subprocess.run(
            ["git", "-C", str(evil), "commit", "-qm", "tracked settings"], check=True
        )
        errs = check_tracking(evil)
        assert any(SETTINGS_REL in e for e in errs), (
            f"tracked settings.json must be flagged, got: {errs}")

        nested = tmp / "nested"
        nested.mkdir()
        _git_init(nested)
        _write_gitignore(nested, ".claude/\n")
        (nested / ".claude").mkdir()
        (nested / ".claude/scratch.log").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(nested), "add", "-f", ".claude/scratch.log"], check=True)
        subprocess.run(
            ["git", "-C", str(nested), "commit", "-qm", "nested"], check=True
        )
        errs = check_tracking(nested)
        assert any("scratch.log" in e for e in errs), (
            f"tracked non-settings .claude file must be flagged, got: {errs}")

        deep = tmp / "deep"
        deep.mkdir()
        _git_init(deep)
        _write_gitignore(deep, ".claude/\n")
        deep_settings = deep / "skills/foo/.claude/settings.json"
        deep_settings.parent.mkdir(parents=True)
        deep_settings.write_text('{"hooks":{}}', encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(deep), "add", "-f", "skills/foo/.claude/settings.json"],
            check=True)
        subprocess.run(
            ["git", "-C", str(deep), "commit", "-qm", "deep"], check=True
        )
        errs = check_tracking(deep)
        assert any("settings.json" in e for e in errs), (
            f"any-depth tracked .claude/settings.json must be flagged, got: {errs}")

        nogit = tmp / "nogit"
        nogit.mkdir()
        (nogit / ".claude").mkdir(parents=True)
        (nogit / SETTINGS_REL).write_text('{"hooks":{}}', encoding="utf-8")
        errs = check_tracking(nogit)
        assert any("could not verify" in e for e in errs), (
            f"git-unavailable tree must fail closed, got: {errs}")

        # -- gitignore assertions -----------------------------------------
        assert check_gitignore(good) == [], f"good gitignore should pass, got: {check_gitignore(good)}"
        no_ignore = tmp / "no_ignore"
        no_ignore.mkdir()
        (no_ignore / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        errs = check_gitignore(no_ignore)
        assert any(".claude/" in e for e in errs), f"missing .claude/ ignore must flag, got: {errs}"

        reinclude = tmp / "reinclude"
        reinclude.mkdir()
        (reinclude / ".gitignore").write_text(
            ".claude/*\n!.claude/settings.json\n", encoding="utf-8"
        )
        errs = check_gitignore(reinclude)
        assert any("!" in e for e in errs), f"re-inclusion negation must flag, got: {errs}"

        # -- README contract assertions -----------------------------------
        good_readme = (
            "## Hook Registration Surface\n\n"
            "Repo hooks register in per-machine config, never in a committed "
            "`.claude/settings.json`: `.claude/settings.local.json` "
            "(untracked) or user-global `~/.claude/settings.json`. Every PR "
            "touching a `hooks/` or `scripts/` diff gets full review.\n\n"
            "## Other\n"
        )
        # exercise against a fake hooks/README.md file
        fake_root = tmp / "fake"
        fake_root.mkdir()
        (fake_root / "hooks").mkdir(parents=True)
        (fake_root / "hooks/README.md").write_text(good_readme, encoding="utf-8")
        assert check_readme_contract(fake_root) == [], (
            f"contract-complete README should pass, got: {check_readme_contract(fake_root)}")

        for label, sub in README_CONTRACT.items():
            bad = good_readme.replace(sub, "‹removed›")
            (fake_root / "hooks/README.md").write_text(bad, encoding="utf-8")
            errs = check_readme_contract(fake_root)
            assert any(label in e for e in errs), (
                f"removing {label!r} (`{sub}`) should flag it, got: {errs}")
            (fake_root / "hooks/README.md").write_text(good_readme, encoding="utf-8")

        missing_section = "# Only One Heading\n\nno surface section\n"
        (fake_root / "hooks/README.md").write_text(missing_section, encoding="utf-8")
        errs = check_readme_contract(fake_root)
        assert any("section" in e for e in errs), (
            f"missing section heading should flag it, got: {errs}")

    print("selftest OK — tracking (root + any-depth tracked `.claude/` incl. settings.json, "
          "nested `.claude/` file, git-unavailable fail-closed), gitignore (missing ignore, "
          "re-inclusion negation), and README contract (per-token RED + section-missing) all "
          "covered with PASS and FAIL fixtures.")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    errs: list[str] = []
    errs += ["[tracking] " + e for e in check_tracking(ROOT)]
    errs += ["[gitignore] " + e for e in check_gitignore(ROOT)]
    errs += ["[readme] " + e for e in check_readme_contract(ROOT)]

    if errs:
        print("SETTINGS EXECUTION SURFACE CHECK FAILED (#604):")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — no tracked `.claude/` app-config; .gitignore and hooks/README carry "
          "the per-machine registration contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())