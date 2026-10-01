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
    skills/test-coverage/**, skills/stocktake/** — general-purpose review
    lenses, not security-only roles, so a hard-out marker is not demanded.

Pin-surface forms (all case-insensitive — the tree has real casing drift,
e.g. historical `model: Sonnet` pins (all removed by #651 / ADR-0003). Values may be bare
or single/double-quoted, indented (form 1 — nested config is a live
convention, see skills/consensus/SKILL.md), or bracket-suffixed
(`claude-fable-5[1m]`, this repo's own live pin convention). EVERY
id-shaped token in the value region is checked, not just the first — the
repo's former disjunction convention (`model: opus or sonnet — lead
decides`, pre-#651) would otherwise hide
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

<!-- CANONICAL: shared/model-tier-policy.md -->
Enforcement boundary (see skills/shared/model-tier-policy.md, Security marker): static pins in
tracked *.md ONLY. This checker does NOT cover (a) `inherit`/session-model
roles (dependency-audit's inline-on-session path; crucible-qg-fix left this
residual when #537 pinned it to sonnet; the standalone-or-finish-driven /red-team
fix-mechanism dispatch is a member by the same "no static pin to catch" test
— see #538), (b) consensus membership in
untracked .claude/consensus-config.yaml (raw model ids, a .yaml —
structurally invisible here), (c) other untracked operator
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
import collections, pathlib, re, subprocess, sys

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
ROLE_CLASSES = {"recall-critical-review", "generative-checked", "mechanical-predicate"}
RUNGS = ("R0", "R1", "R2")
RUNG_ORDER = {r: i for i, r in enumerate(RUNGS)}
ON_UNKNOWN_VALUES = {"refuse", "degrade-with-disclosure", "proceed"}
EGRESS_LEVELS = ("none", "first-party", "third-party")
BRAND_RUNG = {"opus": "R2", "sonnet": "R1", "haiku": "R0"}
MIN_RUNG_FOR_ROLE_CLASS = {
    "recall-critical-review": "R2",
    "generative-checked": "R1",
    "mechanical-predicate": "R0",
}
# The four agent defs design §12/§11 names as MODEL-REQ carriers. Each must
# carry exactly one complete standalone declaration (S1) — a malformed,
# duplicated, or missing wrapper is an authoring error, not an absent
# requirement the checker silently ignores.
BINDING_AGENT_DEFS = {
    "agents/crucible-red-team.md",
    "agents/crucible-qg-fix.md",
    "agents/crucible-qg-judge.md",
    "agents/crucible-qg-verifier.md",
}
# design §12 (S3, round 11; S7, round 12): `<citation>` is EITHER a file:line OR a
# role name naming the downstream check. Both alternatives are honored, and the file
# alternative does NOT require punctuation in the filename — design §12 says
# `file:line`, and `Makefile:1` is as valid a citation as
# `model-tier-policy.md:51`. A bare file, a bare line, a zero/negative line, or any
# nonempty junk still fails: only the SHAPE is checked here (existence is a Task 6
# semantic assertion).
BOUNDED_BY_RE = re.compile(
    r"[a-z][a-z0-9-]*"                # role name, e.g. red-team, crucible-qg-fix
    r"|[^\s:]+:[1-9]\d*"              # file:line, e.g. model-tier-policy.md:51, Makefile:1
)
# Indent-tolerant (S7 — mirrors has_marker()'s standalone-line pattern, which
# accepts leading whitespace via line.strip()): a MODEL-REQ line one column
# off zero must still be checked, never silently skipped.
MODEL_REQ_LINE_RE = re.compile(r"^[ \t]*<!-- MODEL-REQ:(.+?)-->[ \t]*$", re.MULTILINE)

def binding_decl_placement_ok(text: str) -> bool:
    """True iff the file's leading YAML frontmatter block is followed
    (blank lines skipped — **unlimited blank lines are permitted** (M2, round 11):
    "adjacent" means no *content* intervenes, not zero blank lines — and the existing
    adjacent MODEL-TIER marker
    tolerated) by the standalone MODEL-REQ declaration within a small
    window — design §5's "standalone comment immediately after
    frontmatter" placement (SP3, round 3). A declaration embedded deep in
    body prose therefore fails, which the exactly-one presence rule alone
    could not detect. A binding path with NO leading frontmatter block is
    not an agent-def layout and is not placement-checked here (every real
    binding agent def does carry frontmatter)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False
    # Skip blank lines, tolerate AT MOST the single adjacent MODEL-TIER
    # marker, then require the very next non-blank line to be the complete
    # MODEL-REQ declaration (S6, round 4). A fixed non-blank window was too
    # permissive: a body heading (e.g. "# Instructions") immediately after
    # frontmatter would have been skipped and a body declaration certified
    # as "adjacent".
    after = lines[end + 1:]
    i = 0
    while i < len(after) and not after[i].strip():
        i += 1
    if i < len(after) and after[i].strip().startswith("<!-- MODEL-TIER"):
        i += 1
        while i < len(after) and not after[i].strip():
            i += 1
    if i >= len(after):
        return False
    return bool(MODEL_REQ_LINE_RE.match(after[i]))

def model_req_lines(text: str) -> list[str]:
    """Standalone MODEL-REQ declaration line bodies. Caller decides whether to
    scan raw or fence-stripped text (mirrors has_marker/pins_in split)."""
    return [m.group(1).strip() for m in MODEL_REQ_LINE_RE.finditer(text)]

def parse_model_req(body: str) -> dict:
    """Tokenize one MODEL-REQ line body against design §12's grammar
    (`<role-class> <rung> [flags] ...`, no leading vocabulary-version token).
    Raises ValueError with a human-readable reason on any malformed token —
    callers turn that into a hard-fail line."""
    tokens = body.split()
    if not tokens:
        raise ValueError("empty MODEL-REQ body")
    selector = tokens[0]
    if selector not in ROLE_CLASSES and selector != "unclassified":
        raise ValueError(f"unknown role-class {selector!r} (expected one of "
                         f"{sorted(ROLE_CLASSES)} or 'unclassified')")
    fields: dict = {"selector": selector, "flags": set()}
    rest = tokens[1:]
    if not rest or rest[0] not in RUNGS:
        raise ValueError(f"{selector!r} requires a mandatory rung (R0/R1/R2)")
    fields["rung"] = rest[0]
    # design §12 (S1, round 12): the grammar is POSITIONAL —
    # `[<flag>…] [ctx>=N] egress= on-unknown= [bounded-by=]`. Order is enforced
    # below, not merely displayed: accepting permutations would be a *different*
    # grammar from the one this plan claims to implement verbatim.
    SLOT_RANK = {"flag": 0, "ctx": 1, "egress": 2, "on_unknown": 3, "bounded_by": 4}
    last_slot = -1
    for tok in rest[1:]:
        kind = ("flag" if tok in ("accepts-offensive-security", "no-retention",
                                  "no-training")
                else "ctx" if tok.startswith("ctx>=")
                else "egress" if tok.startswith("egress=")
                else "on_unknown" if tok.startswith("on-unknown=")
                else "bounded_by" if tok.startswith("bounded-by=")
                else None)
        if kind is not None:
            if SLOT_RANK[kind] < last_slot:
                raise ValueError(
                    f"{tok!r} is out of design §12's declared token order "
                    f"(`<role-class> <rung> [<flag>…] [ctx>=N] egress=<class> "
                    f"on-unknown=<policy> [bounded-by=<citation>]`) — the grammar "
                    f"is positional and is enforced (S1, round 12)")
            last_slot = SLOT_RANK[kind]
        # Singleton tokens and flags are closed-vocabulary: a repeated token is
        # an authoring error, NOT a last-wins override (S1, round 2). A second
        # `egress=` must not silently relax a declared trust ceiling, and a
        # second `on-unknown=` must not silently replace an earlier obligation.
        if tok == "accepts-offensive-security":
            if tok in fields["flags"]:
                raise ValueError("duplicate accepts-offensive-security flag")
            fields["flags"].add(tok)
        elif tok in ("no-retention", "no-training"):
            if tok in fields["flags"]:
                raise ValueError(f"duplicate {tok} flag")
            fields["flags"].add(tok)
        elif tok.startswith("ctx>="):
            if "ctx" in fields:
                raise ValueError("duplicate ctx>= token")
            n = tok[len("ctx>="):]
            if not re.fullmatch(r"\d+[kKmM]?", n):
                raise ValueError(f"ctx>= must be a number optionally "
                                 f"suffixed k/m, got {n!r}")
            fields["ctx"] = n
        elif tok.startswith("egress="):
            if "egress" in fields:
                raise ValueError("duplicate egress= token — a second trust "
                                 "token cannot override the first")
            level = tok[len("egress="):]
            if level not in EGRESS_LEVELS:
                raise ValueError(f"egress= must be one of {EGRESS_LEVELS}, "
                                 f"got {level!r}")
            fields["egress"] = level
        elif tok.startswith("on-unknown="):
            if "on_unknown" in fields:
                raise ValueError("duplicate on-unknown= token")
            fields["on_unknown"] = tok[len("on-unknown="):]
        elif tok.startswith("bounded-by="):
            if "bounded_by" in fields:
                raise ValueError("duplicate bounded-by= token")
            fields["bounded_by"] = tok[len("bounded-by="):]
        else:
            raise ValueError(f"unrecognized MODEL-REQ token {tok!r}")
    return fields

def leading_frontmatter(text: str):
    """Return the body of the file's LEADING closed YAML frontmatter block, or
    None when the file does not open with `---` ... `---` (S2, round 5)."""
    s = text.lstrip()
    if not s.startswith("---"):
        return None
    end = s.find("\n---", 3)
    return None if end == -1 else s[3:end]

# design §12 (S1, round 12): the published grammar is POSITIONAL —
# `<role-class> <rung> [<flag>…] [ctx>=N] egress=<class> on-unknown=<policy>
# [bounded-by=<citation>]`. Token order is ENFORCED in `parse_model_req` below, so
# the checker accepts exactly §12's language. Earlier rounds parsed the tokens
# order-insensitively and documented that latitude as deliberate; that parse accepted
# a *superset* — a different grammar from the one this plan claims to implement
# verbatim — so the round-8 fixtures that pinned a permuted declaration as clean are
# now hard-fail cases.
def check_model_req_hardfail(rel: str, text: str) -> list[str]:
    """T2 (well-formedness/closed egress+ctx vocab), T18 (bounded-by mandatory
    iff, and only if, degrade-with-disclosure, and `<file>:<line>` shaped), T16
    (role-class <-> on-unknown legality), plus S1 (exactly one complete
    standalone declaration on each binding agent-def path; malformed or
    duplicate declarations hard-fail). Scans FENCE-STRIPPED text: an
    illustrative MODEL-REQ example inside a fenced block (model-tier-
    policy.md's worked examples) is documentation, not a live declaration —
    same convention as the fable-pin rule."""
    fails = []
    stripped = strip_fences(text)
    bodies = []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        s = line.strip()
        # A declaration candidate is a line that opens an HTML comment and
        # mentions MODEL-REQ. Inline prose backtick mentions and fenced
        # examples are not candidates (S1/S7).
        if not s.startswith("<!--") or "MODEL-REQ" not in s:
            continue
        m = MODEL_REQ_LINE_RE.match(line)
        if not m:
            fails.append(f"{rel}:{lineno}: malformed MODEL-REQ declaration — "
                         f"not a complete standalone `<!-- MODEL-REQ: ... -->` "
                         f"line (missing terminator or trailing text): `{s}`")
            continue
        bodies.append((lineno, m.group(1).strip()))
    if len(bodies) > 1:
        fails.append(f"{rel}: {len(bodies)} MODEL-REQ declarations present — "
                     f"exactly one is allowed per file (duplicates hard-fail, "
                     f"S1)")
    if rel in BINDING_AGENT_DEFS and len(bodies) != 1:
        fails.append(f"{rel}: binding agent-def path must carry exactly one "
                     f"MODEL-REQ declaration, found {len(bodies)} (S1)")
    if rel in BINDING_AGENT_DEFS:
        # S2 (round 5) required a binding agent-def to carry exactly one
        # frontmatter `model:` pin. #651 / ADR-0003 removed repo-side model
        # selection entirely — the host harness and operator choose — so the
        # pin-presence half of that rule is gone with it. What still binds is
        # the frontmatter block's presence (the declaration's placement anchor,
        # design §12) and the declaration's position (SP3, round 3).
        fm = leading_frontmatter(stripped)
        if fm is None:
            fails.append(f"{rel}: binding agent-def path must open with a "
                         f"closed YAML frontmatter block — without it the "
                         f"MODEL-REQ declaration has no frontmatter to sit "
                         f"adjacent to, whatever it says (S2, round 5)")
        else:
            if (len(bodies) == 1
                    and not binding_decl_placement_ok(stripped)):
                fails.append(f"{rel}: the MODEL-REQ declaration must sit "
                             f"immediately after the closing YAML frontmatter "
                             f"(optionally after the adjacent MODEL-TIER "
                             f"marker), not embedded in body prose (SP3, "
                             f"round 3)")
    # S1 (round 14): placement binds the DECLARATION, not the path. design §12 requires a
    # standalone MODEL-REQ to be adjacent to the frontmatter, and §2.3 lets an author declare
    # `unclassified` on a role this repo does not otherwise declare — so a frontmatter-carrying
    # non-binding file that buries its declaration in body prose must hard-fail too. A file with
    # no leading frontmatter block cannot satisfy §12's adjacency rule at all; that case stays
    # governed by the exactly-one rule (unchanged, S1 round 14).
    if (rel not in BINDING_AGENT_DEFS and len(bodies) == 1
            and leading_frontmatter(stripped) is not None
            and not binding_decl_placement_ok(stripped)):
        fails.append(f"{rel}: the standalone MODEL-REQ declaration must sit immediately "
                     f"after the closing YAML frontmatter (optionally after the adjacent "
                     f"MODEL-TIER marker), not embedded in body prose (S1, round 14)")
    # S3 (round 19): a file with NO leading frontmatter cannot satisfy design section 12 adjacency
    # at all, so a real (unfenced, standalone) declaration there is a hard fail - otherwise an
    # author gets green validation for an inert, unplaced declaration.
    if (rel not in BINDING_AGENT_DEFS and len(bodies) == 1
            and leading_frontmatter(stripped) is None):
        fails.append(f"{rel}: a standalone MODEL-REQ declaration requires a leading YAML "
                     f"frontmatter block to be adjacent to (design section 12) (S3, round 19)")
    for lineno, raw in bodies:
        try:
            f = parse_model_req(raw)
        except ValueError as e:
            fails.append(f"{rel}:{lineno}: malformed MODEL-REQ ({e}): `{raw}`")
            continue
        selector = f["selector"]
        # design §12 (S5, round 12): `unclassified` is a LEGAL role-class — `<rung>` is
        # mandatory and `on-unknown=refuse` is its only legal policy. Rejecting the
        # declaration outright made the checker recognise a NARROWER language than the
        # approved grammar, and that hard-fail was unconditional, so no maintainer
        # approval could have lifted it. The unresolved item is the rung's MEANING, not
        # the syntax: the rung is not interpreted on an `unclassified` line, and
        # authoring one still waits on Task 1's approval checkpoint. The declaration
        # therefore falls through to the ordinary checks below (mandatory `egress=`,
        # forced `on-unknown=refuse`, `bounded-by=` illegal).
        if not f.get("egress"):
            fails.append(f"{rel}:{lineno}: MODEL-REQ missing mandatory "
                         f"egress=<level>: `{raw}`")
        on_unknown = f.get("on_unknown")
        if on_unknown is None:
            fails.append(f"{rel}:{lineno}: MODEL-REQ missing mandatory "
                         f"on-unknown=: `{raw}`")
            continue
        if on_unknown not in ON_UNKNOWN_VALUES:
            fails.append(f"{rel}:{lineno}: unknown on-unknown value "
                         f"{on_unknown!r}: `{raw}`")
            continue
        # Design §4.1: EVERY security-surface role must refuse on an unknown
        # resolution — not only the roles whose selector/flag happens to force
        # it (S1, round 3). The four in-scope declarations mask this gap because
        # red-team is simultaneously recall-critical and offensive-flagged; the
        # first declared siege/dependency-audit path would otherwise be
        # certified while violating the approved security policy, so consult
        # is_security_surface() directly rather than inferring from the token.
        forces_refuse = (selector in ("recall-critical-review", "unclassified")
                          or "accepts-offensive-security" in f["flags"]
                          or is_security_surface(rel, text))
        if forces_refuse and on_unknown != "refuse":
            fails.append(f"{rel}:{lineno}: {selector!r} (or "
                         f"accepts-offensive-security, or a security-surface "
                         f"file) requires on-unknown=refuse, got "
                         f"{on_unknown!r}: `{raw}`")
        if on_unknown == "degrade-with-disclosure":
            if selector != "generative-checked":
                fails.append(f"{rel}:{lineno}: on-unknown=degrade-with-"
                             f"disclosure is only legal for generative-checked, "
                             f"got {selector!r}: `{raw}`")
            bound = f.get("bounded_by")
            if not bound:
                fails.append(f"{rel}:{lineno}: on-unknown=degrade-with-"
                             f"disclosure requires mandatory "
                             f"bounded-by=<citation>: `{raw}`")
            elif not BOUNDED_BY_RE.fullmatch(bound):
                fails.append(f"{rel}:{lineno}: bounded-by= must be a "
                             f"file:line citation or a role name (got "
                             f"{bound!r}), not an arbitrary nonempty token — "
                             f"the named check's existence is asserted at "
                             f"Task 6, not checked here (S3, round 11): `{raw}`")
        if on_unknown == "proceed" and selector != "mechanical-predicate":
            fails.append(f"{rel}:{lineno}: on-unknown=proceed is only legal "
                         f"for mechanical-predicate, got {selector!r}: `{raw}`")
        if on_unknown != "degrade-with-disclosure" and "bounded_by" in f:
            fails.append(f"{rel}:{lineno}: bounded-by= is only legal with "
                         f"on-unknown=degrade-with-disclosure, got "
                         f"on-unknown={on_unknown!r} (illegal and meaningless "
                         f"otherwise, T18): `{raw}`")
    return fails


# S1 (round 15): the executor is driven by the PUBLISHED map, not by a second hardcoded
# alternative list. A brand added to BRAND_RUNG (the documented single-line update procedure)
# must resolve through this same map, so the two cannot silently drift apart.
# repo's live raw-id convention is `claude-<brand>-<digit...>` with an optional bracketed
# suffix. The id part MUST start with a digit so lookalike prefixes (`claude-opus-proxy`) do
    # not resolve; the brand is matched against BRAND_RUNG's own keys (S5, round 17),
    # so the raw-id path and the published-table path agree on which brands exist.
WHOLE_CLAUDE_ID_RE = re.compile(
    r"^claude-(?P<brand>[a-z][a-z0-9.\-]*?)-\d[\w.\-]*(?:\[[^\]]*\])?$")

def resolve_rung(model_pin_value: str) -> str | None:
    """Brand -> rung per model-tier-policy.md's brand->rung table, driven by the published
    `BRAND_RUNG` map itself (S1, round 15: a second, hardcoded alternative list would let a
    newly published brand pass the table assertion while resolving to `None` here). v1
    resolves ONLY a whole, single value (S2, round 3): a bare brand alias present in the map,
    or a whole raw dated Claude id (digit-initial, optional bracketed suffix, e.g.
    `claude-opus-4-8[1m]`) whose brand is looked up in the same map. It never scans tokens
    and picks out the recognized ones - doing that guessed a rung for
    `opus or some-custom-model-v2` and for the lookalike `claude-opus-proxy`. ANY additional
    token, unrecognized alternative, or multi-brand disjunction resolves to None
    (indeterminate), so T5 can never report agreement for a pin whose other possible
    resolution is unknown."""
    v = model_pin_value.strip().strip("\"'").lower()
    if v in BRAND_RUNG:
        return BRAND_RUNG[v]
    if not WHOLE_CLAUDE_ID_RE.match(v):
        return None
    # S5 (round 17): the brand is matched against the published table's OWN keys, longest
    # first, so a digit-bearing brand (`claude-gpt-5-2026` once `gpt-5` is published)
    # resolves exactly as its table form does. A wider capture alphabet would not do this:
    # a lazy capture still yields `gpt`, and a greedy one turns the documented
    # `claude-opus-4-8[1m]` into `opus-4`. The digit-initial id guard below is unchanged, so
    # the lookalike `claude-opus-proxy` still resolves to None (indeterminate).
    rest = v[len("claude-"):]
    if "[" in rest:
        rest = rest[:rest.index("[")]
    for _b in sorted(BRAND_RUNG, key=len, reverse=True):
        tail = rest[len(_b):]
        if rest.startswith(_b) and tail[:1] == "-" and tail[1:2].isdigit():
            return BRAND_RUNG[_b]
    return None

# S1 (round 15): the map -> executor coupling is asserted, not assumed. Task 12's `--selftest`
# gate runs this same check, so a brand published in BRAND_RUNG without a resolver path fails
# immediately instead of resolving to `indeterminate` in production.
assert BRAND_RUNG, "the published brand->rung table is empty"
for _brand, _rung in BRAND_RUNG.items():
    assert resolve_rung(_brand) == _rung, (
        "brand %r is published as %s but the executor resolves it to %r - the published "
        "table and the resolver have drifted apart" % (_brand, _rung, resolve_rung(_brand)))
assert resolve_rung("some-unknown-brand") is None, (
    "an unpublished brand resolved to a rung")

def frontmatter_model_pins(text: str) -> list[str]:
    """Live `model:` pin values from the file's LEADING YAML frontmatter
    block ONLY (SP1, round 3). The fable-ban scan intentionally reads the
    whole document (inline examples included), but T5 asks "what binds",
    and Claude Code binds only the frontmatter `model:`. A body-line
    `model:` with no frontmatter pin must therefore resolve to
    indeterminate, not be mistaken for a live binding (FRONTMATTER_PIN_RE
    itself is unchanged and still used by the fable-pin scan)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "\n".join(lines[1:i])
            return [v.strip() for v in FRONTMATTER_PIN_RE.findall(fm)]
    return []

def check_model_req_report_only(rel: str, text: str) -> list[str]:
    """T3 (accepts-offensive-security resolves indeterminate, never attested,
    in v1 — always fires, disclosed by design), the design's other two named
    unsatisfiable capability×trust pairs ({R2, egress=none}, {R2,
    no-retention} — design §3.3/§12, F3), T5 (requirement<->resolution
    agreement against the file's own model: pin), T17 (role-class's own
    declared rung vs. its floor). Advisory only — never changes exit code.
    Also reports (S6) when a MODEL-REQ-bearing file's own model: pin
    resolves to no rung at all — T5 cannot run against it, and that skip is
    now visible rather than silent."""
    reports = []
    stripped = strip_fences(text)
    pin_values = frontmatter_model_pins(stripped)
    file_rung = resolve_rung(pin_values[0]) if pin_values else None
    lines = model_req_lines(stripped)
    # SP1 (round 3) reported a MODEL-REQ-bearing file with no frontmatter pin.
    # Under #651 / ADR-0003 no repo file carries a pin at all — that state is
    # the designed one, not a disclosure — so the advisory is gone and T5
    # simply does not run. S6 still fires for a pin that resolves to no rung.
    if lines and pin_values and file_rung is None:
        reports.append(
            f"{rel}: file's own frontmatter model: pin {pin_values[0]!r} "
            f"resolves to no rung (indeterminate) — the MODEL-REQ "
            f"requirement/resolution agreement check (T5) cannot run "
            f"against it, made visible here rather than silently skipped "
            f"(S6)")
    for raw in lines:
        try:
            f = parse_model_req(raw)
        except ValueError:
            continue  # already hard-failed by check_model_req_hardfail
        selector, rung = f["selector"], f.get("rung")
        if "accepts-offensive-security" in f["flags"]:
            reports.append(
                f"{rel}: accepts-offensive-security capability resolves "
                f"`indeterminate` (the #392 boundary-verification probe has "
                f"never been run), never `attested` (fixture-based "
                f"attestation is design #493 §2.4, out of scope for v1) — "
                f"disclosed, not a defect: `{raw}`")
        # Design §8 caps security-surface roles at egress=first-party. Runtime
        # egress enforcement is out of v1 scope, but the DECLARED token pair in
        # a tracked security-surface file is an authoring-time consistency
        # check the checker can already make (it reads is_security_surface()
        # for the on-unknown rule) — a future siege/dependency-audit
        # declaration must not be certified with a third-party ceiling
        # (S5, round 5). Report-Only; no exit-code change.
        if (is_security_surface(rel, text) and f.get("egress")
                and f["egress"] in EGRESS_LEVELS and EGRESS_LEVELS.index(f["egress"]) >
                EGRESS_LEVELS.index("first-party")):
            reports.append(
                f"{rel}: security-surface role declares egress="
                f"{f['egress']} — design §8 caps security-surface roles at "
                f"egress=first-party or stricter (report-only in v1; runtime egress "
                f"enforcement is out of scope, S5, round 5): `{raw}`")
        floor = MIN_RUNG_FOR_ROLE_CLASS.get(selector)
        if rung and floor and RUNG_ORDER[rung] < RUNG_ORDER[floor]:
            reports.append(
                f"{rel}: role-class {selector} declares rung {rung}, below "
                f"its own floor {floor}: `{raw}`")
        # S1 (round 18): the deferred `unclassified` rung must not drive pair reports either.
        # Task 1 leaves that rung meaning unapproved, so reporting {R2, egress=none} or
        # {R2, no-retention} for such a role asserts a policy the plan has not adopted, even
        # report-only: the reviewer executed the parser and saw the advisory appear for a
        # declaration whose rung semantics are explicitly deferred.
        if selector != "unclassified" and rung == "R2" and f.get("egress") == "none":
            reports.append(
                f"{rel}: unsatisfiable capability×trust pair "
                f"{{R2, egress=none}} (design §3.3/§12): `{raw}`")
        if selector != "unclassified" and rung == "R2" and "no-retention" in f["flags"]:
            reports.append(
                f"{rel}: unsatisfiable capability×trust pair "
                f"{{R2, no-retention}} (design §3.3/§12): `{raw}`")
        # S3 (round 17): the rung of an `unclassified` declaration is explicitly deferred
        # (Task 1), so this comparison must not interpret it - reporting an unmet rung for a
        # role whose rung meaning is unresolved asserts a policy the plan has not adopted.
        if (rung and file_rung and selector != "unclassified"
                and RUNG_ORDER[file_rung] < RUNG_ORDER[rung]):
            reports.append(
                f"{rel}: MODEL-REQ requires rung {rung} but the file's own "
                f"model: pin resolves (asserted, brand-table) to "
                f"{file_rung} — requirement/resolution disagreement: `{raw}`")
    return reports
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
    fails.extend(check_model_req_hardfail(rel, text))
    return fails


def tracked_md() -> list[pathlib.Path]:
    res = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT,
        capture_output=True, text=True, check=True)
    return [ROOT / p for p in res.stdout.splitlines() if p]


def main() -> int:
    errs: list[str] = []
    reports: list[str] = []
    for path in tracked_md():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        file_errs = check_file(rel, text)
        errs.extend(file_errs)
        # SP1 (round 15): never run the advisory interpreter over a file that already
        # hard-failed. A malformed declaration (e.g. `egress=banana`) must produce the
        # authored-token failure list, not an uncaught ValueError from the advisory pass.
        if not file_errs:
            reports.extend(check_model_req_report_only(rel, text))
    if reports:
        print("MODEL-REQ REPORT-ONLY (advisory — does not fail the gate):")
        for r in reports:
            print(f"  {r}")
    if errs:
        print("MODEL-TIER GUARDRAIL VIOLATIONS:")
        for e in errs:
            print(f"  {e}")
        print("\nSee skills/shared/model-tier-policy.md (Security marker) and "
              "this checker's docstring — security-surface set, and what this "
              "checker does NOT cover.")
        return 1
    print("OK — no fable pin on marked files; every security-surface file "
          "carries the MODEL-TIER marker.")
    return 0


def report_rule_id(msg: str) -> str:
    """Stable category id for a Report-Only message (S5, round 4). A
    per-file COUNT alone accepted a one-for-one REPLACEMENT of a known
    finding (e.g. qg-judge's pin flipped to `inherit` swaps its T5
    disagreement for an S6/SP1 indeterminate-pin notice — same file, same
    count, wholly different disclosure). Rule ids pin the CATEGORY, never
    the full message prose, so diagnostic wording can still change freely."""
    for needle, rid in (
        ("accepts-offensive-security capability resolves",
         "T3-offensive-indeterminate"),
        ("unsatisfiable capability×trust pair {R2, egress=none}",
         "T3-pair-r2-egress-none"),
        ("unsatisfiable capability×trust pair {R2, no-retention}",
         "T3-pair-r2-no-retention"),
        ("declares rung", "T17-floor"),
        ("MODEL-REQ requires rung", "T5-disagreement"),
        ("resolves to no rung", "S6-indeterminate-pin"),
    ):
        if needle in msg:
            return rid
    return "unclassified"

def _day_one_pairs_ok(got_pairs) -> bool:
    """Pure comparison of live `(path, rule-id)` pairs against the known
    day-one set, so the one-for-one replacement case is unit-testable
    without touching the tracked tree (S5, round 4). Uses COUNTS rather than a
    set (S3, round 10): set semantics collapse two findings of the SAME rule
    on the SAME file into one pair, so an extra advisory warning on an
    already-flagged path would leave this green while the docstring below
    claims exactly one finding per file. Counter equality pins multiplicity too."""
    want = collections.Counter({
        ("agents/crucible-red-team.md", "T3-offensive-indeterminate"): 1,
        # The former second member — crucible-qg-judge's T5 rung/pin
        # disagreement, disclosed as maintainer-pending — is gone by design:
        # #651 / ADR-0003 removed every `model:` pin, so T5 has nothing to
        # disagree with. That is the sanctioned disappearance the old
        # docstring anticipated, not a regression.
    })
    return collections.Counter(got_pairs) == want

def _known_day_one_disclosures() -> int:
    """S11 (round-2 fix: S3 replaced a file-SET comparison over 4 hardcoded
    paths — which could not see a second finding on an already-flagged file,
    or any finding outside those 4 paths — with a per-file finding COUNT (S5, round 4: replaced by stable `(path, rule-id)` PAIRS in `_day_one_pairs_ok`)
    derived from the whole tracked tree via tracked_md()). The live
    Report-Only set must be exactly ONE finding on crucible-red-team.md
    (accepts-offensive-security) and ZERO on every other tracked file. Any
    other pair set means a real, previously-unseen disagreement has
    appeared — the whole point of pinning this is to turn that from silent
    folded-CI-log drift into a red selftest the moment it happens.

    The former second member (crucible-qg-judge's T5 rung-vs-pin
    disagreement, maintainer-pending) disappeared by design when #651 /
    ADR-0003 removed every `model:` pin; see _day_one_pairs_ok."""
    # S3 (round 10) negative control: multiplicity matters. The SAME pair twice must
    # fail — which the previous frozenset comparison could not detect, since both
    # spellings of two identical findings collapse to one element.
    assert not _day_one_pairs_ok([
        ("agents/crucible-red-team.md", "T3-offensive-indeterminate"),
        ("agents/crucible-red-team.md", "T3-offensive-indeterminate"),
        ("agents/crucible-qg-judge.md", "T5-disagreement"),
    ]), "duplicate advisory category on a flagged file must fail the day-one gate"
    # A list, not a set: duplicates must be countable.
    # (Add `import collections` at the top of check_model_pins.py if not already imported.)
    got_pairs = []
    for path in tracked_md():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for msg in check_model_req_report_only(rel, text):
            got_pairs.append((rel, report_rule_id(msg)))
    if not _day_one_pairs_ok(got_pairs):
        print(f"REPORT-ONLY SELFTEST FAILED: live (path, rule-id) pairs "
              f"{sorted(got_pairs)} != known day-one pairs (see "
              f"_day_one_pairs_ok) — a live agent-def "
              f"Report-Only finding appeared, disappeared, or was "
              f"REPLACED by a different rule on the same file; "
              f"investigate before continuing")
        return 1
    return 0

REPORT_ONLY_CASES = [
    # (relpath, text, expect_nonempty, reason)
    ("agents/crucible-red-team.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "accepts-offensive-security egress=first-party on-unknown=refuse -->\n",
     True, "accepts-offensive-security always resolves indeterminate, never "
           "attested, in v1 (T3) — always Report-Only-flagged by design"),
    ("agents/crucible-qg-judge.md",
     "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "egress=first-party on-unknown=refuse -->\n",
     True, "declared rung R2 vs. the file's own sonnet pin (asserted R1) "
           "is a requirement/resolution disagreement (T5)"),
    ("agents/crucible-qg-fix.md",
     "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
     "egress=first-party on-unknown=degrade-with-disclosure "
     "bounded-by=model-tier-policy.md:51 -->\n",
     False, "declared rung R1 matches the file's own sonnet pin (asserted "
            "R1) — no T5 disagreement"),
    ("agents/x.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: generative-checked R0 "
     "egress=first-party on-unknown=degrade-with-disclosure "
     "bounded-by=x.md:1 -->\n",
     True, "a generative-checked declaration with rung R0 is below its own "
           "floor R1 (T17), independent of the file's actual pin"),
    ("agents/x.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: mechanical-predicate R0 "
     "egress=first-party on-unknown=proceed -->\n",
     False, "mechanical-predicate at its own floor R0, opus pin resolves "
            "R2 >= R0 — clean on both T5 and T17"),
    # --- F3: the design's other two named unsatisfiable pairs (§3.3/§12) ---
    ("agents/x.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "egress=none on-unknown=refuse -->\n",
     True, "{R2, egress=none} is the design's flagship unsatisfiable pair "
           "(T3, §3.3/§12) — Report-Only, independent of accepts-"
           "offensive-security"),
    ("agents/x.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "no-retention egress=first-party on-unknown=refuse -->\n",
     True, "{R2, no-retention} is the design's second named unsatisfiable "
           "pair (T3, §3.3/§12)"),
    ("agents/x.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "egress=first-party on-unknown=refuse -->\n",
     False, "R2 + egress=first-party is satisfiable — the two new "
            "unsatisfiable-pair rules must not over-fire on it (this is "
            "the shape Task 6's real declarations use)"),
    # --- S6: resolve_rung must match id-shaped tokens, not brand prefixes,
    # and must never first-wins-guess a multi-brand region ---
    ("agents/x.md",
     "---\nmodel: claude-opus-4-8[1m]\n---\n<!-- MODEL-REQ: "
     "recall-critical-review R2 egress=first-party on-unknown=refuse "
     "-->\n",
     False, "a bracket-suffixed raw dated opus id resolves correctly to R2 "
            "via id-shaped matching, matching the declared R2 requirement "
            "— clean, not falsely indeterminate (S6)"),
    ("agents/x.md",
     "---\nmodel: opus or sonnet\n---\n<!-- MODEL-REQ: generative-checked "
     "R1 egress=first-party on-unknown=degrade-with-disclosure "
     "bounded-by=x.md:1 -->\n",
     True, "a disjunctive pin resolves to indeterminate, never "
           "first-wins-guessed (S6); MODEL-REQ's presence on an "
           "indeterminate-resolution file is now visibly reported rather "
           "than silently unchecked"),
    ("agents/x.md",
     "---\nmodel: some-custom-model-v2\n---\n<!-- MODEL-REQ: "
     "mechanical-predicate R0 egress=first-party on-unknown=proceed -->\n",
     True, "an unrecognized model id resolves to indeterminate — visible "
           "(S6), not silently skipped"),
    # --- S2 (round 3): whole-value resolution only ---
    ("agents/x.md",
     "---\nmodel: opus or some-custom-model-v2\n---\n<!-- MODEL-REQ: "
     "mechanical-predicate R0 egress=first-party on-unknown=proceed -->\n",
     True, "a known brand disjoined with an UNKNOWN alternative resolves to "
           "indeterminate, never R2 — whole-value resolution, not "
           "token-picking (S2, round 3)"),
    ("agents/x.md",
     "---\nmodel: claude-opus-proxy\n---\n<!-- MODEL-REQ: "
     "mechanical-predicate R0 egress=first-party on-unknown=proceed -->\n",
     True, "a lookalike `claude-opus-proxy` (non-digit id part) does NOT "
           "resolve to opus/R2 — indeterminate (S2, round 3)"),
    # --- SP1 (round 3): only the leading frontmatter `model:` binds ---
    ("agents/x.md",
     "No frontmatter block at all.\n\nmodel: opus\n<!-- MODEL-REQ: "
     "mechanical-predicate R0 egress=first-party on-unknown=proceed -->\n",
     False, "a body-only `model:` is not a live binding, and #651 / ADR-0003 "
            "removed repo-side pins altogether — so the former SP1 "
            "no-frontmatter-pin advisory no longer fires; T5 simply does "
            "not run on an unpinned file"),
    # --- S5 (round 5): security-surface trust ceiling is an authoring check ---
    ("skills/siege/SKILL.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "egress=third-party on-unknown=refuse -->\n",
     True, "a security-surface declaration with egress=third-party breaks "
           "design §8's first-party ceiling — Report-Only, since runtime "
           "egress enforcement is out of v1 scope (S5, round 5)"),
    ("skills/siege/SKILL.md",
     "---\nmodel: opus\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
     "egress=first-party on-unknown=refuse -->\n",
     False, "the same security-surface shape at egress=first-party is within "
            "the ceiling — the new rule must not over-fire (S5, round 5)"),
         ("skills/siege/SKILL.md",
          "---\nmodel: haiku\n---\n<!-- MODEL-REQ: mechanical-predicate R0 "
          "egress=none on-unknown=refuse -->\n",
          False, "a security-surface declaration egress=none is stricter than the "
          "first-party ceiling, not a violation — §8 is an at-most ceiling, so "
          "egress=none must not be reported (S1, round 8; R0 avoids the separate "
          "{R2, egress=none} unsatisfiable-pair rule so only the ceiling is under "
          "test)"),
]


def selftest_report_only() -> int:
    """T3/T5/T17 are advisory — verify they fire/don't-fire on their own
    channel, never touching check_file's hard-fail return."""
    failures = []
    for rel, text, expect_nonempty, reason in REPORT_ONLY_CASES:
        got = check_model_req_report_only(rel, text)
        if bool(got) != expect_nonempty:
            failures.append(f"  {rel}: expected nonempty={expect_nonempty} "
                            f"({reason}), got {got!r}")
    if failures:
        print("REPORT-ONLY SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    if _known_day_one_disclosures():
        return 1
    # S5 (round 4): pin the one-for-one REPLACEMENT case directly — same
    # file, same count, different rule id must fail; the exact known pair
    # set must pass.
    assert not _day_one_pairs_ok({
        ("agents/crucible-qg-judge.md", "S6-indeterminate-pin"),
    }), "a one-for-one disclosure replacement must fail the day-one pin"
    assert _day_one_pairs_ok({
        ("agents/crucible-red-team.md", "T3-offensive-indeterminate"),
    }), "the exact known day-one pair set must pass"
    print("REPORT-ONLY SELFTEST OK.")
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
        ("agents/crucible-red-team.md", f"---\nmodel: opus\n---\n{m}\n<!-- MODEL-REQ: recall-critical-review R2 accepts-offensive-security egress=first-party on-unknown=refuse -->\nbody\n",
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
         f"---\nmodel: opus  # keep\n---\n{m}\n<!-- MODEL-REQ: recall-critical-review R2 accepts-offensive-security egress=first-party on-unknown=refuse -->\nbody\n",
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
         f"---\nmodel: claude-opus-4-8[1m]\n---\n{m}\n<!-- MODEL-REQ: recall-critical-review R2 accepts-offensive-security egress=first-party on-unknown=refuse -->\nbody\n",
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
        # --- #493 MODEL-REQ hard-fail rules (T2/T16/T18, S1/S2/S3) ---
        # S1 (round 12): design §12's token order is ENFORCED — the first case is a
        # clean canonical declaration, the second a permuted one that must now FAIL,
        # so a future order-insensitive parser cannot land without turning red.
        ("agents/x.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "ctx>=200k egress=first-party on-unknown=degrade-with-disclosure "
         "bounded-by=model-tier-policy.md:51 -->\n",
         False, "canonical (design §12 display) token order is clean"),
        ("agents/x.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "egress=first-party on-unknown=degrade-with-disclosure "
         "bounded-by=Makefile:1 -->\n",
         False, "a dotless filename is a valid file:line citation (S7, round 12)"),
        ("agents/x.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "egress=first-party on-unknown=degrade-with-disclosure "
         "bounded-by=red-team -->\n",
         False, "a role name is a valid citation per design §12 (S3, round 11)"),
        ("agents/x.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "bounded-by=model-tier-policy.md:51 egress=first-party "
         "on-unknown=degrade-with-disclosure ctx>=200k -->\n",
         True, "a permuted token order is a HARD FAIL (S1, round 12): design §12's "
         "grammar is positional and the checker now enforces it — a permuted "
         "declaration is outside the approved language"),
        ("agents/x.md",
         "---\nname: x\n---\n<!-- MODEL-REQ: generative-checked R1 ctx>=200k egress=first-party "
         "on-unknown=degrade-with-disclosure "
         "bounded-by=model-tier-policy.md:51 -->\n",
         False, "a well-formed generative-checked declaration with its "
                "mandatory bounded-by= is clean"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure -->\n",
         True, "degrade-with-disclosure without bounded-by= is a hard fail (T18)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure "
         "bounded-by=model-tier-policy.md -->\n",
         True, "bounded-by= must carry the `<file>:<positive line>` shape — a "
               "bare file with no line is a hard fail, not accepted as a "
               "nonempty token (S2)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure "
         "bounded-by=model-tier-policy.md:0 -->\n",
         True, "bounded-by= line must be a positive integer — :0 is malformed "
               "(S2)"),
        ("agents/x.md",
         "---\nname: x\n---\n<!-- MODEL-REQ: recall-critical-review R2 egress=first-party "
         "on-unknown=refuse -->\n",
         False, "recall-critical-review paired with on-unknown=refuse is clean"),
        ("agents/crucible-qg-judge.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: recall-critical-review R2 egress=first-party "
         "on-unknown=proceed -->\n",
         True, "recall-critical-review MUST use on-unknown=refuse (T16)"),
        ("agents/x.md",
         "---\nname: x\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure "
         "bounded-by=quality-gate/SKILL.md:289 -->\n",
         False, "generative-checked paired with on-unknown=degrade-with-"
                "disclosure and a shape-valid downstream-check citation (citation SHAPE only — that the cited check is real is Task 6's semantic assertion, not this parser's; S3 residual, round-11 verifier) is clean — "
                "qg-verifier is generative-checked (design §2.3's round-3 "
                "reclassification), and its disclosure is bounded by the next "
                "round's fresh red-team re-review, cited at "
                "`quality-gate/SKILL.md:289` (S2 — the earlier draft cited "
                "`model-tier-policy.md:50`, a taxonomy row that names no "
                "downstream check at all)"),
        ("agents/crucible-qg-verifier.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=proceed -->\n",
         True, "on-unknown=proceed is illegal outside mechanical-predicate "
               "(T16)"),
        ("agents/x.md",
         "<!-- MODEL-REQ: mechanical-predicate R0 egress=first-party "
         "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         True, "on-unknown=degrade-with-disclosure is illegal outside "
               "generative-checked (T16)"),
        ("agents/crucible-red-team.md",
         f"---\nmodel: opus\n---\n{m}\n<!-- MODEL-REQ: recall-critical-review R2 "
         "accepts-offensive-security egress=first-party on-unknown=refuse "
         "-->\n",
         False, "with the file's own required MODEL-TIER marker present "
                "(crucible-red-team.md is a hard-out EXPLICIT_FILES member — "
                "rule (b) fires independent of MODEL-REQ), "
                "accepts-offensive-security combined with the mandatory "
                "refuse is clean (T16)"),
        ("agents/crucible-red-team.md",
         f"---\nmodel: opus\n---\n{m}\n<!-- MODEL-REQ: recall-critical-review R2 "
         "accepts-offensive-security egress=first-party on-unknown=proceed "
         "-->\n",
         True, "with the marker present (isolating the T16 violation from "
               "rule (b)'s own marker requirement), accepts-offensive-security "
               "MUST use on-unknown=refuse (T16)"),
        ("agents/x.md", "<!-- MODEL-REQ: bogus-role R1 egress=first-party "
         "on-unknown=refuse -->\n",
         True, "unknown role-class is a hard fail (T2)"),
        ("agents/x.md", "<!-- MODEL-REQ: unclassified egress=first-party "
         "on-unknown=refuse -->\n",
         True, "unclassified with no rung is a hard fail — design §12 makes "
               "<rung> mandatory, and unclassified's rung semantics are an "
               "unresolved maintainer decision (S3)"),
        ("agents/x.md", "---\nname: x\n---\n<!-- MODEL-REQ: unclassified R0 egress=first-party "
         "on-unknown=refuse -->\n",
         False, "even WITH a rung token, an `unclassified` declaration is now "
               "ACCEPTED syntactically (S5, round 12): its rung is simply not "
               "interpreted, and authoring one still waits on the approval "
               "checkpoint (S3, round 11; S5, round 12)"),
        ("agents/x.md", "<!-- MODEL-REQ: generative-checked -->\n",
         True, "role-class missing its mandatory rung is a hard fail (T2)"),
        ("agents/x.md", "<!-- MODEL-REQ: generative-checked R1 -->\n",
         True, "missing mandatory egress= is a hard fail (S2/T2 — egress is "
               "unbracketed, i.e. mandatory, in design §12's grammar)"),
        ("agents/x.md", "<!-- MODEL-REQ: generative-checked R1 egress=banana "
         "on-unknown=refuse -->\n",
         True, "egress= must be a closed-ladder value "
               "(none/first-party/third-party) — an out-of-ladder value is "
               "a hard fail, not silently accepted (S3)"),
        ("agents/x.md", "<!-- MODEL-REQ: generative-checked R1 "
         "ctx>=lots egress=first-party on-unknown=degrade-with-disclosure "
         "bounded-by=x.md:1 -->\n",
         True, "ctx>= must be a number optionally suffixed k/m — a "
               "non-numeric payload is a hard fail, not silently accepted "
               "(S3)"),
        ("agents/x.md", "<!-- MODEL-REQ: generative-checked R1 "
         "egress=first-party on-unknown=refuse bounded-by=x.md:1 -->\n",
         True, "bounded-by= is illegal (and meaningless) on any line not "
               "carrying on-unknown=degrade-with-disclosure — accepting it "
               "silently was the other half of T18 the checker did not "
               "enforce (S3)"),
        ("skills/shared/model-tier-policy.md",
         "Example:\n```\n<!-- MODEL-REQ: generative-checked R1 "
         "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n```\n",
         False, "a FENCED illustrative MODEL-REQ example (the policy doc's "
                "own worked example) is not a live declaration and does not "
                "trip T2/T16/T18 — same fence-immunity convention as the "
                "fable-pin rule"),
        ("agents/x.md",
         " <!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=proceed -->\n",
         True, "an INDENTED MODEL-REQ declaration is still matched and "
               "hard-failed, not silently skipped — has_marker-style indent "
               "tolerance (S7); on-unknown=proceed is illegal for "
               "generative-checked (T16)"),
        ("agents/x.md",
         "See the grammar: `<!-- MODEL-REQ: generative-checked R1 "
         "on-unknown=proceed -->` for details.\n",
         False, "a MODEL-REQ mentioned INLINE in a prose sentence is not a "
                "standalone line and must NOT fire, even though its content "
                "would otherwise hard-fail (S7)"),
        # --- S1: malformed / duplicate / missing declaration presence ---
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse -- >\n",
         True, "a malformed terminator (`-- >`) is a missing-close authoring "
               "error — it must hard-fail, not read as an absent declaration "
               "(S1)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse --> trailing text\n",
         True, "trailing text after the terminator means the declaration is "
               "not standalone — a hard fail (S1)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse -->\n"
         "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse -->\n",
         True, "two declarations in one file is a duplicate hard fail (S1)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\nno declaration here\n",
         True, "a binding agent-def path with ZERO declarations is a hard "
               "fail — exactly one standalone declaration is required (S1)"),
        ("agents/x.md",
         "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse -->\n",
         True, "a non-binding path with NO frontmatter cannot satisfy design "
               "section 12 adjacency, so a standalone declaration there is a hard fail (S3, round 19)"),
        ("agents/x.md",
         "---\nname: x\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse -->\n",
         False, "a single well-formed declaration on a non-binding path WITH frontmatter "
                "is clean — the exactly-one rule binds only the four binding agent defs (S1)"),
        ("agents/x.md",
         "---\nmodel: sonnet\n---\n\n" + ("filler instructional line\n" * 40)
         + "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
           "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         True, "S1 (round 14): placement binds the DECLARATION, not the path — a "
               "non-binding frontmatter-carrying file that buries its declaration in "
               "body prose hard-fails exactly like a binding agent def (design §12)"),
        ("agents/x.md",
         "<!-- MODEL-REQ: recall-critical-review R2 egress=none "
         "egress=first-party on-unknown=refuse -->\n",
         True, "a repeated egress= token is a hard fail, NOT a last-wins "
               "override — a second trust ceiling cannot silently relax the "
               "first (S1, round 2)"),
        ("agents/x.md",
         "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=refuse on-unknown=degrade-with-disclosure "
         "bounded-by=skills/shared/model-tier-policy.md:51 -->\n",
         True, "a repeated on-unknown= token is a hard fail — a later token "
               "cannot replace an earlier obligation (S1, round 2)"),
        ("agents/x.md",
         "<!-- MODEL-REQ: mechanical-predicate R0 egress=first-party "
         "on-unknown=proceed no-training no-training -->\n",
         True, "a repeated flag is a hard fail (S1, round 2)"),
        # --- S1 (round 3): security-surface files must refuse regardless of selector ---
        ("skills/siege/SKILL.md",
         "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         True, "a security-surface file declaring generative-checked degrade "
               "is a hard fail — design §4.1 requires on-unknown=refuse for "
               "EVERY security-surface role, not only recall-critical/offensive "
               "(S1, round 3)"),
        ("agents/x.md",
         "---\nname: x\n---\n<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         False, "the non-security generative control stays clean — the "
                "security-surface refusal rule does not over-fire (S1, round 3)"),
        # --- SP3 (round 3): a binding declaration must be adjacent to frontmatter ---
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n\n" + ("filler instructional line\n" * 40)
         + "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
           "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         True, "a binding agent-def MODEL-REQ buried in body prose fails the "
               "frontmatter-adjacency rule (SP3, round 3)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n# Instructions\nDo something else\n"
         "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         True, "a body heading immediately after frontmatter does NOT make a "
               "following declaration 'adjacent' — only blank lines and the "
               "single MODEL-TIER marker may precede it (S6, round 4)"),
        # --- S2 (round 5): a binding path must KEEP its frontmatter model: pin ---
        ("agents/crucible-red-team.md",
         f"{m}\n<!-- MODEL-REQ: recall-critical-review R2 "
         "accepts-offensive-security egress=first-party on-unknown=refuse "
         "-->\n",
         True, "a binding agent-def that LOST its leading YAML frontmatter "
               "(no `model: opus` pin) is a hard fail — the old "
               "`startswith(\"---\")` guard let it skip the placement check "
               "and exit 0 while the role bound nothing (S2, round 5)"),
        ("agents/crucible-qg-fix.md",
         "---\n# frontmatter present, but no model: pin\n---\n"
         "<!-- MODEL-REQ: generative-checked R1 egress=first-party "
         "on-unknown=degrade-with-disclosure bounded-by=x.md:1 -->\n",
         False, "a binding agent-def with frontmatter but no `model:` pin is "
                "the designed state since #651 / ADR-0003 removed repo-side "
                "model selection — the S2 (round 5) pin-presence hard fail "
                "is gone; only a MISSING frontmatter block still hard-fails"),
    ]
    # Bound-specific diagnostic (S3, round 7): both T18 rules emit a reason
    # containing the literal `bounded-by`; assert on the reason text so a
    # deleted bound rule cannot keep these fixtures green via another rule.
    for _rel, _text, _label in (
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "egress=first-party on-unknown=degrade-with-disclosure -->\n",
         "missing mandatory bounded-by="),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "egress=first-party on-unknown=degrade-with-disclosure "
         "bounded-by=model-tier-policy.md -->\n",
         "malformed bounded-by= (bare file, no line)"),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: generative-checked R1 "
         "egress=first-party on-unknown=degrade-with-disclosure "
         "bounded-by=model-tier-policy.md:0 -->\n",
         "malformed bounded-by="),
        ("agents/crucible-qg-fix.md",
         "---\nmodel: sonnet\n---\n<!-- MODEL-REQ: recall-critical-review R2 "
         "egress=first-party on-unknown=refuse bounded-by= -->\n",
         "bounded-by= present but EMPTY on a non-degradation line"),
    ):
        got = check_model_req_hardfail(_rel, _text)
        assert any("bounded-by" in f for f in got), (
            f"{_label}: expected a bound-specific diagnostic, got {got!r}")
    # SP2 (round 8): the published brand->rung table is the policy SOURCE and
    # BRAND_RUNG is its EXECUTOR; without a tie an approved table revision can
    # leave the checker stale with a green suite. Parse the canonical table and
    # assert equality — a one-line policy edit with no checker edit turns red. The
# comparison is over the FULL parsed mapping and must NOT filter by the checker's
# current keys (SP1, round 9): filtering would let a newly published brand row drift
# silently, leaving the checker resolving that brand as indeterminate while this guard
# stayed green. A fourth policy row without executor support therefore FAILS here.
    def _published_brand_rung(path: str) -> dict:
        text = pathlib.Path(path).read_text(encoding="utf-8")
        # M2 (round 10): bound the parse to the named brand->rung section. Scanning the
        # whole document would let any later illustrative two-column table trip the guard.
        head = re.search(r"^#{1,6}[^\n]*[Bb]rand[^\n]*[Rr]ung[^\n]*$", text, re.M)
        if head is None:
            raise AssertionError("brand->rung table section heading not found")
        body = text[head.end():]
        nxt = re.search(r"^#{1,6} ", body, re.M)
        if nxt is not None:
            body = body[:nxt.start()]
        rows = {}
        seen_sep = False
        for _line in body.splitlines():
            if not _line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in _line.strip().strip("|").split("|")]
            if not seen_sep:
                # rows above the header separator are the header itself
                if all(c and set(c) <= set("-: ") for c in cells):
                    seen_sep = True
                continue
            # S4 (round 14): parse EVERY data row and REJECT what does not parse.
            # Matching only `[a-z]+` silently ignored a published brand carrying a digit
            # or hyphen (e.g. `gpt-5`), leaving this guard green while the checker
            # resolved that brand as indeterminate.
            m = re.fullmatch(r"`([a-z][a-z0-9.-]*)`", cells[0])
            if m is None:
                raise AssertionError(
                    "unparseable brand row in the published table: %r" % _line)
            if not re.fullmatch(r"R[0-9]", cells[1]):
                raise AssertionError(
                    "unparseable rung cell in the published table row: %r" % _line)
            if m.group(1) in rows:
                raise AssertionError(
                    "duplicate brand row in the published table: %r" % _line)
            rows[m.group(1)] = cells[1]
        return rows

    assert _published_brand_rung(
        "skills/shared/model-tier-policy.md") == BRAND_RUNG, (
        "published brand->rung table drifted from the checker's BRAND_RUNG")
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
        # `|`, not `or` — both selftests must run even if the first is
        # nonzero, so a hard-fail regression never hides a Report-Only one
        # in the same run (M7).
        sys.exit(selftest() | selftest_report_only())
    sys.exit(main())
