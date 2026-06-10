#!/usr/bin/env python3
"""Model-tier guardrail: no fable pin on security-marked files (#392).

Invocation (from repo root):
    python3 scripts/check_model_pins.py            # check the tracked tree
    python3 scripts/check_model_pins.py --selftest # run the built-in logic tests

Default-deny, marker-driven (mirrors check_crossref.py's `git ls-files "*.md"`
walk — tracked files only; an untracked/unstaged .md is invisible until staged,
so this is a PR-time gate, not an author-time one). Two rules:
  (a) FAIL any fable-family pin (`fable`, `Fable`, `claude-fable-5`, ...) on a
      file carrying the `<!-- MODEL-TIER: security-hard-out -->` marker;
  (b) FAIL any file in the security-surface set that LACKS the marker.

Security-surface set (evaluated on the repo-relative path):
  - dir allowlist: skills/siege/**, skills/dependency-audit/** — marker
    required for EVERY .md there, pin or no pin (everything in a known
    security skill dir matters);
  - explicit file: agents/crucible-red-team.md — not blocked *content* but the
    calibration-recall-critical static pin (a silent Fable->Opus fallback would
    make the recall-critical reviewer nondeterministic);
  - name-stem set (case-insensitive substring on the basename): siege,
    dependency-audit, security, vuln, cve, exploit, threat — applied ONLY to
    files that carry at least one model pin (match-then-check-for-pin: a
    pure-prose stem-matcher like skills/shared/security-signals.md cannot host
    a fable pin, so it is not forced to carry a marker);
  - carve-outs (never security-surface): skills/audit/**,
    skills/test-coverage/**, skills/stocktake/** — the general audit skill's
    lenses are ELIGIBLE-PENDING-VERIFICATION in the model-tier policy, so
    forcing a hard-out marker onto them would contradict the taxonomy.

Pin-surface forms (all case-insensitive — the tree has real casing drift,
e.g. `model: Sonnet` in skills/prospector/SKILL.md:335. Values may be bare
or single/double-quoted, indented (form 1 — nested config is a live
convention, see skills/consensus/SKILL.md), or bracket-suffixed
(`claude-fable-5[1m]`, this repo's own live pin convention). EVERY
id-shaped token in the value region is checked, not just the first — the
repo's live disjunction convention (`model: opus or sonnet — lead
decides`, see skills/build/build-reviewer-prompt.md) would otherwise hide
a second-position fable (gate round 3, S1). Value-region boundaries:
form 1 ends at the first `#` or end-of-line, so `model: opus  # never
fable` is a non-fable pin whose comment merely MENTIONS fable; forms 2-3
end at the FIRST closing paren (`[^)]*`) — prose after the id but inside
the parens is part of the region (accepted over-match, see below).
Accepted limitation: a nested parenthetical BEFORE `model:` inside a
tool form closes the region early and truncates the scan (the known
nested-paren Minor, accepted for v1)):
  1. line-anchored `model: <value>` (frontmatter or any indented line)
  2. inline `Task tool (... model: <value> ...)`
  3. inline `Agent tool (... model: <value> ...)`

Enforcement boundary (see skills/shared/model-tier-policy.md): static pins in
tracked *.md ONLY. This checker does NOT cover (a) `inherit`/session-model
roles (crucible-qg-fix, dependency-audit's inline-on-session path), (b)
consensus membership in untracked .claude/consensus-config.yaml (raw model
ids, a .yaml — structurally invisible here), (c) other untracked operator
config. Those are operator-convention residuals, documented, not enforced.

Fenced-example handling (gate round 3, S2): lines inside ```- or
~~~-fenced code blocks (fences close on the SAME character they opened
with, per CommonMark) are stripped before rule (a) scans for pins, so a
MARKED security doc may document the banned form (a fenced `model: fable`
counter-example) without tripping the gate. Fail-closed: an UNTERMINATED
fence strips nothing — a real pin cannot hide behind an unclosed one. A
single leading U+FEFF BOM is stripped before scanning (it would otherwise
defeat the line-anchored form-1 regex on the first line). Rule (b)'s
pin-presence gate reads the RAW (unstripped) text: a fenced example pin
can at worst DEMAND a marker on a security-named doc — an over-demand,
never a missed fable pin. has_marker also reads raw text (a fence-buried
marker still counts as a stamp; deliberate asymmetry — it subjects the
file to MORE scrutiny under rule (a), never less).

Known over-match (accepted): in NON-marked prose docs an unfenced
line-anchored `model:` example still registers as a pin. Harmless — the
marker is matched as a STANDALONE line (has_marker), so a prose doc that
merely *quotes* the marker string inline (the policy doc's "Marker
convention", the stocktake bullet) is NOT treated as marked; rule (a)
therefore cannot fire there, and rule (b) can at worst require a marker
on a security-named doc. On MARKED files one residual remains: an
UNFENCED prose mention of fable after `model:` but inside a tool-form
paren (e.g. `Task tool (..., model: opus — never fable)`) fires rule (a);
write such notes outside the parens, after a `#` (form 1), or in a fence.

Exits 0 if clean, 1 with a per-violation list otherwise. Stdlib only.
"""
from __future__ import annotations
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARKER = "<!-- MODEL-TIER: security-hard-out -->"

DIR_ALLOWLIST = ("skills/siege/", "skills/dependency-audit/")
EXPLICIT_FILES = {"agents/crucible-red-team.md"}
NAME_STEMS = ("siege", "dependency-audit", "security", "vuln", "cve",
              "exploit", "threat")
CARVE_OUTS = ("skills/audit/", "skills/test-coverage/", "skills/stocktake/")

# Each regex captures the VALUE REGION after `model:`, not a single token:
# form 1 to the first `#` or end-of-line, forms 2-3 to the closing paren.
FRONTMATTER_PIN_RE = re.compile(
    r"^[ \t]*model:([^\n#]*)", re.IGNORECASE | re.MULTILINE)
TASK_TOOL_PIN_RE = re.compile(
    r"Task tool\s*\([^)]*model:([^)]*)", re.IGNORECASE)
AGENT_TOOL_PIN_RE = re.compile(
    r"Agent tool\s*\([^)]*model:([^)]*)", re.IGNORECASE)
ID_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]+")


def pins_in(text: str) -> list[str]:
    """All id-shaped tokens across the value regions of the three static
    pin-surface forms.

    EVERY token in a value region is returned, not just the first — the
    repo's live disjunction convention (`model: opus or fable`) puts the
    pin of interest in the SECOND position (gate round 3, S1). Region
    boundaries: form 1 ends at `#` or end-of-line, so a trailing comment
    can MENTION fable without firing; forms 2-3 end at the FIRST closing
    paren (the accepted nested-paren limitation — see module docstring).
    Quotes, `[1m]` suffixes, and connectives like ` or ` are non-id chars
    the token scan skips over — they never void a match (gate rounds 1-2);
    connective words come back as tokens, which is harmless: is_fable
    filters them and rule (b) only needs truthiness."""
    regions = (FRONTMATTER_PIN_RE.findall(text)
               + TASK_TOOL_PIN_RE.findall(text)
               + AGENT_TOOL_PIN_RE.findall(text))
    return [tok for region in regions for tok in ID_TOKEN_RE.findall(region)]


def strip_fences(text: str) -> str:
    """Drop lines inside ```- or ~~~-fenced code blocks (fence lines
    included), so rule (a) does not accuse a marked security doc of the
    very pin its fenced counter-example warns against (gate round 3, S2;
    tilde fences: minor pass QF1). Per CommonMark a fence closes on the
    SAME character it opened with: a ``` block is closed only by ``` and
    a ~~~ block only by ~~~. Fail-closed: a fence with NO closing line
    strips nothing — everything after an unterminated opener is kept and
    scanned, so a real pin cannot hide there."""
    lines = text.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        head = lines[i].lstrip()
        fence = next((f for f in ("```", "~~~") if head.startswith(f)), None)
        if fence is not None:
            j = i + 1
            while j < n and not lines[j].lstrip().startswith(fence):
                j += 1
            if j < n:          # terminated block: drop it, fences included
                i = j + 1
                continue       # unterminated: fall through, keep the lines
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def has_marker(text: str) -> bool:
    """True iff the marker appears as its own line (a real stamp), NOT merely
    quoted inline in prose/backticks (a documentation mention). Task-2 stamps
    always place the marker on its own line, so genuine stamps still match;
    a doc that merely quotes the marker string (the policy doc, the stocktake
    bullet) is correctly NOT treated as marked."""
    return any(line.strip() == MARKER for line in text.splitlines())


def is_fable(value: str) -> bool:
    """fable-family: the alias and any raw claude-fable-* id."""
    return "fable" in value.lower()


def is_security_surface(rel: str, text: str) -> bool:
    """Membership in the machine-checkable security-surface set."""
    if rel.startswith(CARVE_OUTS):
        return False
    if rel.startswith(DIR_ALLOWLIST) or rel in EXPLICIT_FILES:
        return True
    base = pathlib.PurePosixPath(rel).name.lower()
    if any(stem in base for stem in NAME_STEMS):
        return bool(pins_in(text))  # match-then-check-for-pin
    return False


def check_file(rel: str, text: str) -> list[str]:
    """Return violation strings for one file (empty == OK)."""
    if text.startswith("\ufeff"):
        # A leading BOM would defeat the line-anchored form-1 regex on the
        # first line (minor pass QF2). Strip a single leading BOM here (not
        # in main()) so the no-filesystem selftest path is covered too.
        text = text[1:]
    fails = []
    marked = has_marker(text)          # raw text: fences never hide a stamp
    # rule (a) scans fence-stripped text (S2); rule (b)'s pin-presence gate
    # (is_security_surface below) stays on RAW text — over-demand, fail-closed.
    fable_pins = [v for v in pins_in(strip_fences(text)) if is_fable(v)]
    if marked and fable_pins:
        fails.append(f"{rel}: fable pin on security-marked file "
                     f"(model-tier hard-out): {fable_pins}")
    if is_security_surface(rel, text) and not marked:
        fails.append(f"{rel}: security-surface file lacks marker `{MARKER}`")
    return fails


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
        rel = path.relative_to(ROOT).as_posix()
        errs.extend(check_file(rel, text))
    if errs:
        print("MODEL-TIER GUARDRAIL VIOLATIONS:")
        for e in errs:
            print(f"  {e}")
        print("\nSee skills/shared/model-tier-policy.md — marker convention, "
              "security-surface set, and what this checker does NOT cover.")
        return 1
    print("OK — no fable pin on marked files; every security-surface file "
          "carries the MODEL-TIER marker.")
    return 0


def selftest() -> int:
    """Built-in regression cases for the detection logic (no filesystem)."""
    m = MARKER
    pin = "Task tool (general-purpose, model: opus):"
    cases = [
        # (relpath, text, expect_fail, reason)
        ("skills/siege/SKILL.md",
         f"---\nname: siege\n---\n{m}\n{pin}\n",
         False, "stamped siege file with an opus pin is clean"),
        ("skills/siege/new-attacker-prompt.md", "prose only, no pin\n",
         True, "dir-allowlist file needs the marker even with no pin"),
        ("skills/payloads/injection-vuln-prompt.md", f"{pin}\n",
         True, "newly-added unmarked security-named file WITH a pin is "
               "caught (the enumeration-bypass case)"),
        ("skills/payloads/injection-vuln-notes.md", "prose, no pin\n",
         False, "stem-match without a pin is spared (match-then-check)"),
        ("skills/shared/security-signals.md", "shared signals prose\n",
         False, "the real no-pin stem-matcher is NOT flagged"),
        ("agents/crucible-red-team.md", f"---\nmodel: fable\n---\n{m}\nbody\n",
         True, "fable flip of red-team IS caught (calibration-critical "
               "explicit entry)"),
        ("agents/crucible-red-team.md", f"---\nmodel: opus\n---\n{m}\nbody\n",
         False, "red-team stamped with its opus pin is clean"),
        ("agents/crucible-red-team.md", f"---\nmodel: opus\n---\nbody\n",
         True, "red-team WITHOUT the marker is caught (explicit entry)"),
        ("skills/audit/audit-robustness-prompt.md", f"{pin}\n",
         False, "carve-out: audit's security-pattern lenses are NOT forced "
                "to carry a marker (eligible-pending, process-gated)"),
        ("skills/test-coverage/SKILL.md", f"{pin}\n",
         False, "carve-out: test-coverage is NOT flagged"),
        ("skills/stocktake/SKILL.md", f"{pin}\n",
         False, "carve-out: stocktake is NOT flagged"),
        ("skills/siege/SKILL.md",
         f"{m}\nTask tool (general-purpose, model: Fable):\n",
         True, "case-insensitive: `model: Fable` on a marked file is caught"),
        ("skills/siege/SKILL.md",
         f"{m}\nAgent tool (subagent_type: general-purpose, model: fable)\n",
         True, "the Agent-tool pin form is covered"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: claude-fable-5\n---\n{m}\n",
         True, "raw id `claude-fable-5` is fable-family"),
        ("docs/notes.md", "model: fable\n",
         False, "fable pin on a non-surface unmarked file is allowed by "
                "this checker (the pilot path — eval-gated by policy, "
                "not by CI)"),
        ("skills/shared/model-tier-policy.md",
         f"Marker convention: a hard-out file carries the `{m}` marker.\n"
         f"Example of a banned pin: `Task tool (general-purpose, "
         f"model: fable)`.\n",
         False, "policy doc that QUOTES the marker inline (not a standalone "
                 "line) is NOT treated as marked, so its quoted `model: fable` "
                 "example does not trip rule (a) — the doc cannot accuse "
                 "itself; non-surface path, so rule (b) needs no marker"),
        ("skills/shared/model-tier-policy.md",
         f"---\nname: model-tier-policy\n---\n{m}\nmodel: fable\n",
         True, "a GENUINELY stamped file (marker on its own line) with a "
               "fable pin IS still flagged — has_marker matches the real "
               "stamp"),
        ("agents/crucible-red-team.md",
         f"---\nmodel: fable  # pilot\n---\n{m}\nbody\n",
         True, "trailing `# comment` after a frontmatter fable value on a "
               "stamped file is still caught (the value capture stops at "
               "the comment boundary)"),
        ("agents/crucible-red-team.md",
         f"---\nmodel: opus  # keep\n---\n{m}\nbody\n",
         False, "trailing `# comment` after a non-fable frontmatter value is "
                "captured-then-tolerated: `opus` still parses, rule (a) does "
                "not fire"),
        ("skills/siege/SKILL.md",
         f"---\nname: siege\nmodel: Fable\n---\n{m}\n",
         True, "case-insensitive frontmatter `model: Fable` on a marked file "
               "is caught (capitalized frontmatter form)"),
        ("skills/siege/SKILL.md",
         f"{m}\nAgent tool (subagent_type: general-purpose, model: Fable)\n",
         True, "case-insensitive Agent-tool `model: Fable` on a marked file "
               "is caught (capitalized Agent-tool form)"),
        ("skills/audit/audit-cve-prompt.md", f"{pin}\n",
         False, "carve-out dir beats cve stem"),
        ("skills/siege/SKILL.md",
         f"{m}\nproviders:\n  - name: anthropic\n    model: claude-fable-5\n",
         True, "indented fable pin in a nested config block on a marked file "
               "is caught (gate round 1, S1: column-0-anchor bypass)"),
        ("skills/siege/SKILL.md",
         f"{m}\nproviders:\n  - name: anthropic\n"
         "    model: claude-sonnet-4-20250514\n",
         False, "indented NON-fable pin on a marked file stays clean (indent "
                "tolerance does not over-fire)"),
        ("skills/siege/SKILL.md", f'{m}\nmodel: "fable"\n',
         True, "double-quoted fable value on a marked file is caught "
               "(gate round 1, S2: quoted-value bypass)"),
        ("skills/siege/SKILL.md", f"{m}\nmodel: 'fable'\n",
         True, "single-quoted fable value on a marked file is caught "
               "(gate round 1, S2)"),
        ("skills/siege/SKILL.md",
         f'{m}\nTask tool (general-purpose, model: "fable"):\n',
         True, "quoted fable value in the Task-tool form is caught "
               "(gate round 1, S2)"),
        ("skills/siege/SKILL.md",
         f"{m}\nAgent tool (subagent_type: general-purpose, model: 'fable')\n",
         True, "quoted fable value in the Agent-tool form is caught "
               "(gate round 1, S2)"),
        ("skills/siege/SKILL.md", f'{m}\nmodel: "opus"\n',
         False, "quoted NON-fable value on a marked file stays clean (quote "
                "tolerance does not over-fire)"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: claude-fable-5[1m]\n---\n{m}\n",
         True, "bracket-suffixed fable id `claude-fable-5[1m]` on a marked "
               "file is caught (gate round 2, S1: the rejecting boundary "
               "lookahead voided suffixed values)"),
        ("skills/siege/SKILL.md", f'{m}\nmodel: "claude-fable-5[1m]"\n',
         True, "quoted bracket-suffixed fable id on a marked file is caught "
               "(gate round 2, S1)"),
        ("agents/crucible-red-team.md",
         f"---\nmodel: claude-opus-4-8[1m]\n---\n{m}\nbody\n",
         False, "bracket-suffixed NON-fable id on a marked file stays clean "
                "(suffix tolerance does not over-fire)"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: sonnet or fable\n---\n{m}\n",
         True, "disjunction `model: sonnet or fable` on a marked file is "
               "caught — every value-region token is scanned, not just the "
               "first (gate round 3, S1)"),
        ("skills/siege/SKILL.md",
         f"{m}\nTask tool (general-purpose, model: opus or fable):\n",
         True, "disjunction in the Task-tool form is caught "
               "(gate round 3, S1)"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: opus or sonnet\n---\n{m}\n",
         False, "the live build-prompt disjunction `model: opus or sonnet` "
                "does not over-fire on a marked file"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: opus  # never fable\n---\n{m}\n",
         False, "a `#` comment MENTIONING fable after a non-fable "
                "frontmatter value does not fire — the value region stops "
                "at the comment boundary (gate round 3, S1 over-fire guard)"),
        ("skills/siege/SKILL.md",
         f"{m}\nNever write this:\n```\nmodel: fable\n```\n",
         False, "fenced `model: fable` counter-example on a MARKED file no "
                "longer trips rule (a) — fences are stripped "
                "(gate round 3, S2)"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: fable\n---\n{m}\n```\nmodel: fable\n```\n",
         True, "a real unfenced fable pin is still caught when a fenced "
               "example is also present — stripping fences does not hide "
               "real pins (gate round 3, S2)"),
        ("skills/siege/SKILL.md",
         f"{m}\n```\nmodel: fable\n",
         True, "UNTERMINATED fence does not hide a pin — fail-closed, the "
               "unclosed block is still scanned (gate round 3, S2)"),
        ("skills/payloads/injection-vuln-prompt.md",
         f"```\n{pin}\n```\n",
         True, "rule (b)'s pin-presence gate reads the RAW text: a fenced "
               "pin on an unmarked security-named file still demands a "
               "marker (over-demand accepted, M2(r2)-shaped)"),
        ("skills/siege/SKILL.md",
         f"{m}\nNever write this:\n~~~\nmodel: fable\n~~~\n",
         False, "tilde-fenced `model: fable` counter-example on a MARKED "
                "file does not trip rule (a) — ~~~ fences are stripped too "
                "(minor pass QF1)"),
        ("skills/siege/SKILL.md",
         f"---\nmodel: fable\n---\n{m}\n~~~\nmodel: fable\n~~~\n",
         True, "a real unfenced fable pin is still caught when a "
               "tilde-fenced example is also present — stripping ~~~ "
               "fences does not hide real pins (minor pass QF1)"),
        ("skills/siege/SKILL.md",
         f"\ufeffmodel: fable\n{m}\n",
         True, "a leading BOM does not defeat the line-anchored form-1 "
               "regex on the first line — the BOM is stripped before "
               "scanning (minor pass QF2)"),
        ("skills/siege/SKILL.md",
         "<!--MODEL-TIER: security-hard-out-->\nprose\n",
         True, "whitespace-variant marker is NOT a stamp — has_marker is "
               "an exact byte-for-byte line match (line.strip() == MARKER), "
               "so the dir-allowlist file counts as un-stamped and rule (b) "
               "fires (minor pass QF4 regression pin, no behavior change)"),
    ]
    failures = []
    for rel, text, expect_fail, reason in cases:
        got = check_file(rel, text)
        if bool(got) != expect_fail:
            failures.append(f"  {rel}: expected fail={expect_fail} "
                            f"({reason}), got {got!r}")
    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — marker, surface-set, carve-out, and pin-form "
          "detection behave as specified.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
