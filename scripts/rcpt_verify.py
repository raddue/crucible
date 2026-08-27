#!/usr/bin/env python3
"""Runtime receipt linter (Ledger Return Protocol). Tier-1 (v1 structural, a verbatim
port of the former eval-only eval/ledger-return-protocol/lint.py, removed in #369) +
Tier-2 parts 1-2 (disk sha256 + witness byte-range). stdlib-only, argparse-free.
Exit 0=pass, 1=fail, 2=usage. A supplied `--root` is NEVER degraded to cwd (that is a
silent fail-open), but the two ways it can be wrong part company: `--root ""` and a
`--root` naming an existing non-directory are argv errors (exit 2), while a root that
does not exist is a lint failure (exit 1) — Tier-1 still runs, Tier-2 does not. Two
different `--root` tokens naming ONE directory is likewise a lint failure. Bullets on
stderr.

Usage:
  rcpt_verify.py [--tier1|--tier2] [--root DIR]... [--strict] [--ledger PATH] [FILE|-]
  rcpt_verify.py --selftest
  rcpt_verify.py --eval FILE.jsonl

--ledger PATH (Tier-2 part-3): bind each DISPATCHED TRACE line to a receipt-ledger.jsonl
entry on (dispatch_id, rcpt_sha256, verdict); mismatch = FAIL. Without it, a receipt that
has DISPATCHED lines reports `UNVERIFIABLE: ledger binding (no --ledger)` (advisory).
"""
from __future__ import annotations
import contextlib, io, json, re, signal, sys, hashlib, pathlib, typing

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "eval/ledger-return-protocol"


class LintError(Exception):
    pass


# ── #474 / round-3 S5 — the CLI-only bound on witness-predicate evaluation.
#    DEFINED here, INSTALLED only by _verify_single. Defining a handler is inert;
#    installing one at import time would silently change SIGALRM behaviour for
#    _gen.py, sweep.py and test_rcpt_verify.py, which import this module and own
#    their own signal disposition. See _compile_guard for why the bound is here
#    and not around the re.search itself.
WITNESS_TIMEOUT_S = 5
# round-4 / M3 — the message names EVERYTHING inside the bound, not just the regex.
# The wrapped call is tier2_witness, which does resolve_base (stat + symlink walk), a
# whole-file read_text() on the rangeless grep path (_read_cited_range) and a
# read_bytes() for the #B cap BEFORE re.search runs, so "catastrophic backtracking"
# alone would blame the predicate for a slow or very large artifact read. The narrow
# wrap is still the right one (see _verify_single) — it is the string that was wrong.
WITNESS_TIMEOUT_MSG = (f"witness evaluation exceeded {WITNESS_TIMEOUT_S}s "
                       "(predicate backtracking or a slow/large artifact read)")


class WitnessTimeout(LintError):
    """#486 / Q8 — a WALL-CLOCK witness timeout, distinguishable from a lint failure.

    A SUBCLASS deliberately: every existing `except LintError` and
    `assertRaises(LintError)` still catches it, so #485's contract and its round-5
    teardown ordering are untouched and this is not a type widening at the CLI
    boundary. What the subclass buys is distinguishability at the sites that would
    otherwise SWALLOW it. The complete set of `except LintError` handlers wrapping a
    tier2_witness() call, and each one's disposition after this commit:
      * _selftest_run_fixture  -- FIXED here, (f). 'fail' is a PASSING fixture for
        every expect:fail row.
      * _selftest_crosscheck   -- FIXED here, (g). 'LINT-FAIL' AGREES with an inline
        LINT-FAIL, so it reports no problem.
      * tier2-fixtures/_gen.py:301 -- FIXED here, (h). Same shape as
        _selftest_run_fixture, one directory away.
      * scripts/measure_474_corpus.py:58 -- NOT FIXED. Bounded now (the arm is inside
        tier2_witness), but its `except rv.LintError` still renders a timeout as a
        BLOCKED disposition. Stated, not solved; #486 does not republish its figures.
      * any test that wants to assert the subclass may -- an affordance, not a swallow.
    ITIMER_REAL is wall-clock, so a loaded CI box qualifies, not only catastrophic
    backtracking; without the subclass D7 would introduce "coverage that cannot fail"
    across ~35 sites in this linter's only regression net.
    """


def _witness_alarm(signum, frame):
    """SIGALRM → WitnessTimeout, so a catastrophically-backtracking witness predicate
    lint-FAILs one receipt (exit 1, message on stderr) instead of hanging the process
    with no receipt and no verdict.

    #486 / D7 — the raise no longer lands in _verify_single's `except LintError` by
    construction: after the bound moved into tier2_witness it lands wherever THAT
    function's caller catches, which is why the exception is WitnessTimeout(LintError)
    rather than a bare LintError (Q8). Every existing handler still catches it; the
    three that would silently swallow it classify it instead."""
    raise WitnessTimeout(WITNESS_TIMEOUT_MSG)


@contextlib.contextmanager
def _witness_bound():
    """#486 / D7 — the CLI-only bound, re-sited so a direct tier2_witness() importer is
    bounded too. EXACTLY ONE ARM on the path through tier2_witness: _verify_single no
    longer arms, because nesting would make the inner arm capture the outer's REMAINING
    delay and restore it on exit, pushing the CLI deadline out by the inner's elapsed
    time (an effective bound of up to ~2x WITNESS_TIMEOUT_S, falsifying #485's measured
    5.09 s).

    The platform guard is #485's, carried VERBATIM, both conjuncts — round-4/M7 records
    why the second is not redundant: the attribute access itself raises AttributeError,
    which `except LintError` does not catch. PLUS a try/except ValueError around
    signal.signal, because tier2_witness has no main-thread guarantee the way
    _verify_single did (":1573-1575": "the CLI entry path and therefore main-thread by
    construction") and signal.signal raises ValueError off the main thread. Degradation
    is to UNBOUNDED evaluation — the pre-round-3 behaviour — never a raise.

    The `prev` capture is INSIDE the same guard as the arm: capturing outside it would
    restore a timer that was never replaced.

    Teardown order is round-5/MIN-3's, carried verbatim: disarm, restore the handler,
    re-arm. See _verify_single at 5d1fb15 for why merely swapping two statements is
    incomplete.
    """
    armed = False
    prev = prev_delay = prev_interval = None
    if hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM"):
        try:
            prev = signal.signal(signal.SIGALRM, _witness_alarm)
        except ValueError:
            pass                      # off the main thread — unbounded, never a raise
        else:
            prev_delay, prev_interval = signal.setitimer(
                signal.ITIMER_REAL, WITNESS_TIMEOUT_S)
            armed = True
    try:
        yield
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prev)
            if prev_delay:
                signal.setitimer(signal.ITIMER_REAL, prev_delay, prev_interval)


# ── Tier-1 (v1 structural) — ported VERBATIM from the former eval-only lint.py
#    (SECTIONS..lint_receipt, the eval-validated v1 layer; lint.py removed in #369).
#    Do NOT re-derive: the differential oracle gate proved byte-equivalence before
#    lint.py was deleted (the permanent CI guard is --selftest).
SECTIONS = ["RCPT", "VERDICT", "ARTIFACTS", "TRACE", "CLAIMS", "WITNESS", "SUSPICION", "NEXT"]
UNRUNNABLE_VOCAB = {
    "sandbox-restricted", "tooling-absent", "platform-incompatible",
    "network-unreachable", "service-unavailable", "time-budget-exceeded",
    "requires-human-input",
}
LINT_RULES = {"all-claims-cited", "trace-consistent", "skip-declared"}

# ── v1.1 Tier-1 extension (#369 fast-follow) — receipt-local subset of
#    return-convention.md §"Linter extension (Tier-1 additions for v1.1 receipts)".
#    Ported from eval/ledger-return-protocol/tripwire/sweep.py (which now delegates
#    its receipt-local checks here — single source). Manifest-relative SUPERSEDES
#    rules (uniqueness / no-double-supersede / the witness-evidence TRIGGER) are NOT
#    here: a single receipt has no manifest to resolve them against.
#
#    SIEGE-R2CH-2 — the witness-evidence rule's CONSEQUENT is receipt-local and IS here,
#    even though its trigger is not. See lint_v11_local for the fail-closed reading and
#    what it costs.
GLOB_ENTRIES_CAP = 8

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONF = re.compile(r"^(0\.\d{2}|1\.00)$")


def _receipt_int(digits: str, label: str) -> int:
    """SIEGE-R2BA-3 — int() on a RECEIPT-AUTHORED digit string, guarded. The same
    fault-isolation class as _trace_idx and _compile_guard, and the same remedy: a
    malformed field is a one-line lint bullet, never an escaping ValueError.

    CPython caps int() string conversion at sys.get_int_max_str_digits() (4300 by
    default), so a 5000-digit run of ASCII digits raises ValueError — which is NOT a
    LintError. Every anchor in this file admits it: `str.isdigit()` (parse_trace),
    `[0-9]+` (_TRACE_REF_RE), `\\d+` (_OUT_RANGE_RE, _WITNESS_RANGE_RE) and `-?\\d+`
    (the exit= clauses) all match arbitrarily long runs. Measured on this tree, both
    contracts this file states were falsified:
      * CLI — line 1 was the census, line 2 onward a Traceback: the precise shape the
        `except BaseException` arm and the F3 read guards exist to eliminate.
      * --eval — a good/poison/good batch printed NO stdout at all and exited 1,
        against run_eval's "ALWAYS exits 0 for a readable file (F1)" and _eval_text's
        "one corrupt line must not suppress the rest". The good record BEFORE the
        poison one was lost too.

    Raising the interpreter's digit limit would be treating the symptom: the receipt is
    untrusted input and an over-long index is malformed whatever the limit is.

    The guard is `except ValueError` and not a length pre-test, so it also covers the
    NON-length legs the anchors admit — `str.isdigit()` is true for e.g. superscripts
    ('\\xb2'), which int() then rejects, and `\\d` matches every Unicode decimal digit.
    The bullet shows a TRUNCATED value: interpolating 5000 digits into a message on a
    channel an orchestrator records verbatim just moves the problem."""
    try:
        return int(digits)
    except ValueError as e:
        shown = digits if len(digits) <= 40 else digits[:40] + "…"
        raise LintError(f"{label} is not a usable integer: {shown!r} ({e})")


def parse_receipt(text):
    """Parse receipt into {section: body_lines} dict. Body lines preserve
    their original content (including leading whitespace)."""
    lines = text.splitlines()
    if not lines:
        raise LintError("empty receipt")
    # First line must be RCPT v1 or v1.1
    header_m = re.match(r"^RCPT v(1(?:\.1)?) (.+)$", lines[0])
    if not header_m:
        raise LintError("first line must start with 'RCPT v1 ' or 'RCPT v1.1 '")
    sections = {"RCPT": [header_m.group(2)]}
    current = None
    for line in lines[1:]:
        stripped = line.lstrip()
        matched = None
        for name in SECTIONS[1:]:
            if line.startswith(name):
                matched = name
                break
        if matched:
            if matched in sections:
                raise LintError(f"section {matched} duplicated")
            rest = line[len(matched):].lstrip()
            sections[matched] = [rest] if rest else []
            current = matched
        else:
            if current is None:
                raise LintError(f"prose before first section header: {line!r}")
            sections[current].append(line)
    # Check order (unknown sections after NEXT ignored — but SECTIONS list is the strict v1 set)
    got_order = [s for s in SECTIONS if s in sections]
    if got_order != SECTIONS[:len(got_order)]:
        raise LintError(f"sections out of order: got {got_order}")
    missing = [s for s in SECTIONS if s not in sections]
    if missing:
        raise LintError(f"missing required sections: {missing}")
    return sections


def _none_sentinel(body, section):
    """#488 I8 / T10 — `(none)` is the empty-set sentinel and ONLY that.

    The shipped defect is identical in all three name-bearing parsers:
    `if line == "(none)": return ...` is an UNANCHORED `return` inside the entry loop,
    not a `continue`, so one `(none)` line anywhere in the body discards every entry —
    the ones after it (never reached) and the ones before it (the accumulator is thrown
    away) alike. Measured on dd06b80, both orderings:

        parse_artifacts(['a.md sha256:…', '(none)', 'b.md sha256:…'])  -> {}
        parse_artifacts(['(none)', 'a.md sha256:…'])                   -> {}

    and end-to-end, two receipts differing by one appended line: `artifacts 1/2 … partial
    EXIT=1` becomes `artifacts 0/0 … EXIT=0` (§3.4 channel 5).

    ONE helper rather than three copies of the same guard: three parsers already drifted
    into carrying the identical bug verbatim, which is what a duplicated guard invites.

    #488 inquisitor/D2 — this scan CONSUMES `body`. Every caller iterates `body` a
    SECOND time for its own entries, so a one-shot `body` (a generator, an `iter(...)`,
    a file object) is exhausted here and the caller's loop sees nothing — `{}`/`[]`
    returned silently at exit 0, which is the same fail-open shape this guard exists to
    close. `body` is public-API-supplied with no type enforcement, exactly as `trace`
    and `artifacts` are, and before fa108d2 each parser iterated it exactly once, so a
    one-shot body worked. Callers therefore materialise with `list(body)` first; the
    fix is theirs and not this helper's because they need the ORIGINAL unstripped `raw`
    line, which this helper does not return.

    Returns True when the body IS the legal one-line sentinel, False when it holds no
    sentinel at all, and raises when a `(none)` co-occurs with any entry."""
    entries = [l.strip() for l in body if l.strip()]
    if "(none)" not in entries:
        return False
    if len(entries) != 1:
        raise LintError(
            f"{section} (none) is the empty-set sentinel and must be the only entry")
    return True


def parse_artifacts(body):
    """Returns {name: {hash, size, meta}} from ARTIFACTS body lines."""
    out = {}
    # #488 inquisitor/D2 — materialise BEFORE the scan: `_none_sentinel` consumes
    # `body`, and the entry loop below iterates it again. See its docstring.
    body = list(body)
    if _none_sentinel(body, "ARTIFACTS"):
        return {}
    # body is indented lines; skip blanks
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            raise LintError(f"ARTIFACTS malformed: {raw!r}")
        name, hash_field, size = parts[0], parts[1], parts[2]
        # #488 AC-2 / §3 *Lexical grammar* — a legal ARTIFACTS <name> is a POSIX-relative
        # path. Only TWO of the four clauses land as a Tier-1 raise. `no whitespace` is
        # already unreachable (line.split() above), and `no ..` is producer-normative
        # ONLY: landing it would make siege S-3's monotonicity pin structurally
        # unreachable while leaving its exit code unmoved (1 -> 1), for a traversal
        # `_contained` already rejects by realpath. Whether `..` ever lands is OQ-10.
        #
        # The name is rendered through `_show_path` for the same SIEGE-R2BA-4 reason
        # every other receipt-supplied name on this channel is — required a fortiori for
        # the NUL clause, whose whole point is that the byte never reaches the channel.
        if name.startswith("/"):
            raise LintError(f"ARTIFACTS name is not relative: {_show_path(name)}")
        if "\x00" in name:
            raise LintError(f"ARTIFACTS name contains NUL: {_show_path(name)}")
        if not hash_field.startswith("sha256:") or not HEX64.match(hash_field[len("sha256:"):]):
            raise LintError(f"ARTIFACTS bad hash: {raw!r}")
        # #488 inquisitor/AV2 — the accumulator is a dict, so a name declared TWICE
        # silently collapsed to LAST-WINS: two receipts making the SAME two claims about
        # the SAME name in opposite line order produced OPPOSITE exit codes (measured:
        # bogus-then-honest EXIT=0, honest-then-bogus EXIT=1), and the census billed
        # `artifacts 1/1` either way — indistinguishable from a single-line receipt, so
        # an orchestrator could not tell that a hash it may itself have logged was never
        # checked. Rejected rather than reconciled: `parse_receipt` already rejects a
        # duplicated SECTION name with the same shape of message, so fail-loud on a
        # duplicated declaration is this file's established policy and not a new one, and
        # the alternatives (keep-first, or verify both) each pick a winner the receipt
        # grammar does not name. Tier-1, deliberately: this is a fact about the receipt's
        # TEXT and needs no disk, so it is refused before any root is probed.
        if name in out:
            raise LintError(f"ARTIFACTS name duplicated: {_show_path(name)}")
        out[name] = {"hash": hash_field[len("sha256:"):], "size": size}
    return out


def parse_trace(body):
    """Returns list of {n, verb, args_str} entries."""
    out = []
    # #488 inquisitor/D2 — materialise BEFORE the scan: `_none_sentinel` consumes
    # `body`, and the entry loop below iterates it again. See its docstring.
    body = list(body)
    if _none_sentinel(body, "TRACE"):
        return []  # #397: empty sentinel accepted uniformly (cf. ARTIFACTS/NEXT)
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            raise LintError(f"TRACE malformed: {raw!r}")
        n_str, verb = parts[0], parts[1]
        args = parts[2] if len(parts) == 3 else ""
        if not n_str.isdigit():
            raise LintError(f"TRACE index not integer: {raw!r}")
        if verb not in {"READ", "EDIT", "WROTE", "EXEC", "DISPATCHED", "CONSULTED", "SKIPPED"}:
            raise LintError(f"TRACE unknown verb: {verb!r}")
        # SIEGE-R2BA-3 — `str.isdigit()` above admits both a 5000-digit run (over
        # CPython's int() cap) and non-ASCII digit forms int() rejects.
        out.append({"n": _receipt_int(n_str, "TRACE index"), "verb": verb, "args": args})
    for i, entry in enumerate(out, start=1):
        if entry["n"] != i:
            raise LintError(f"TRACE indices not 1-based contiguous: expected {i} got {entry['n']}")
    return out


class OutRange(typing.NamedTuple):
    artifact: str
    kind: str   # "L" (line) | "B" (byte)
    start: int
    end: int


# #442 G6b: the ONE canonical out=<artifact>#<KIND><a>-<KIND><b> parser, accepting
# EXACTLY one well-formed range as a complete token. [^#\s]+ rejects '#' in the
# artifact; \2 back-ref rejects mixed kind (#L1-B5); (?!#[LB]\d) negative-lookahead
# rejects a trailing second #<range> (double-#range) WITHOUT over-rejecting other
# trailing chars (out=a#L1-L5 mode=x / out=a#L1-L5,x still parse). A None parse
# makes check_exec_range_bound LINT-FAIL at Tier-1 before any Tier-2 site, so all 5
# (formerly divergent: old greedy/last vs the non-greedy first-range readers) now
# agree. Replaces 5 divergent regexes.
_OUT_RANGE_RE = re.compile(r"out=([^#\s]+)#([LB])(\d+)-\2(\d+)(?!#[LB]\d)")


def parse_out_range(args_str):
    """Parse out=<artifact>#<KIND><a>-<KIND><b>. Returns OutRange or None."""
    m = _OUT_RANGE_RE.search(args_str)
    if not m:
        return None
    # SIEGE-R2BA-3 — `\d+` matches an arbitrarily long run; guarded like every other
    # receipt-authored integer in this file.
    return OutRange(m.group(1), m.group(2),
                    _receipt_int(m.group(3), "EXEC out= range start"),
                    _receipt_int(m.group(4), "EXEC out= range end"))


# The 4 KiB budget from return-convention.md § Cost model, ONE name (round-4 / M6).
# Both span sites — EXEC's out= bound and #474/D6's grep-witness bound — go through
# check_span_bound, and the Tier-2 cap message interpolates this same constant, so a
# second spelling of 4096 could only ever drift from the text it is supposed to match.
WITNESS_SPAN_CAP = 4096


def check_span_bound(kind, a, b, *, bytes_per_line, label, detail):
    """The span arithmetic shared by EXEC's out= bound and #474/D6's grep-witness
    bound. Tier-1 is disk-free, so a #L span can only be reasoned about from the
    receipt's own text; #B is the byte count to within one (ranges are 1-based
    INCLUSIVE, so b-a undercounts by one — inherited, and the Tier-2 cap closes it).

    `bytes_per_line` is the per-site CALIBRATION and is deliberately NOT shared:
    EXEC keeps its 80-B/line ESTIMATE (a gated Tier-1 rule — loosening it is
    fail-open), while the grep path uses the SOUND 1-B/line floor (a line is at
    minimum its newline). An estimate that guesses false-rejects provably in-spec
    receipts: (b-a)*80 rejects the committed, CI-gated `12-judge` witness, whose
    whole file is 3120 B. `label`/`detail` are required, not decoration — the two
    sites pin different message text byte-for-byte."""
    if b < a:
        raise LintError(f"{label} range negative: {detail}")
    span_bytes = (b - a) if kind == "B" else (b - a) * bytes_per_line
    if span_bytes > WITNESS_SPAN_CAP:
        raise LintError(f"{label} range exceeds 4 KiB: {detail}")


def check_exec_range_bound(args_str):
    """out=<artifact>#<range> — check range ≤ 4 KiB. The authoritative cap is
    enforced against the ACTUAL bytes read at Tier-2 (tier2_witness, #397 defect 4)."""
    r = parse_out_range(args_str)
    if not r:
        raise LintError(f"EXEC missing out= or bad range: {args_str}")
    check_span_bound(r.kind, r.start, r.end,
                     bytes_per_line=80, label="EXEC", detail=args_str)


def parse_claims(body):
    out = []
    # #488 inquisitor/D2 — materialise BEFORE the scan: `_none_sentinel` consumes
    # `body`, and the entry loop below iterates it again. See its docstring.
    body = list(body)
    if _none_sentinel(body, "CLAIMS"):
        return []  # #397: empty sentinel accepted uniformly (cf. ARTIFACTS/NEXT)
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        # pattern= may be quoted (containing spaces) or a /regex/ form or bare
        m = re.match(
            r'^([^\s=]+)=(\S+)\s+from=(\S+)(?:\s+pattern=("[^"]*"|/[^/]*/|\S+))?$',
            line,
        )
        if not m:
            raise LintError(f"CLAIM malformed: {raw!r}")
        out.append({"key": m.group(1), "value": m.group(2), "citation": m.group(3), "pattern": m.group(4)})
    return out


# #474 / S2(a)3 — the pattern= clause grammar. Reuses parse_claims:190's alternation
# rather than inventing a second one. The bare `\S+` alternative STAYS in the
# extraction regex: it is what stops an unquoted clause silently becoming part of the
# artifact name (which would move the ranged/rangeless split). A bare clause is
# rejected in VALIDATION, not in parsing.
_WITNESS_CLAUSE_RE = re.compile(r'\s+pattern=("[^"]*"|/[^/]*/|\S+)\s*$')

# #442 G6b sibling — the ONE reader of a WITNESS payload's <artifact>#<KIND><a>-<KIND><b>.
# Mirrors _OUT_RANGE_RE's three earned properties ([^#\s]+ rejects '#' in the artifact;
# the \2 back-ref rejects mixed kinds like #L1-B5; the (?!#[LB]\d) lookahead rejects a
# trailing second #range) because _OUT_RANGE_RE itself cannot be reused — it is anchored
# on the literal `out=`, which a witness payload never carries. Five sites need these
# fields; they read them, they do not re-parse (five divergent readers of this exact
# syntax already diverged once in this file — #442 G6b).
_WITNESS_RANGE_RE = re.compile(r"^([^#\s]+)#([LB])(\d+)-\2(\d+)(?!#[LB]\d)")


def _compile_guard(src, msg_prefix, shown):
    """re.compile a DERIVED regex source, re-raising every exception re.compile
    raises — re.error, OverflowError and RecursionError — as LintError, which is the
    COMPILE half of #440's fault-isolation class, and only that half. The clause and
    the expect-fail signature are freely-authored, attacker-influenced receipt text
    handed straight to re.search; an escaping compile exception aborts a whole --eval
    batch instead of lint-FAILing one record. Always the DERIVED source — for a quoted
    literal that is the re.escape'd text, so this guard is provably inert there.
    Compiling the RAW inner text instead would false-BLOCK the escape hatch D3
    prescribes (pattern="**Severity:** Fatal").

    round-6 / S1 — the caught set was re.error ALONE, and the two escapees are not
    exotic: `pattern=/a{4294967295}/` (13 characters, an ordinary repetition
    quantifier at 2**32-1) raises OverflowError, and a deeply-nested group raises
    RecursionError. Both reached __main__ as a traceback where the protocol specifies
    a one-line lint bullet, and both aborted an --eval batch mid-file against
    the contract _eval_text's malformed-JSON branch states in those words —
    "one corrupt line must not suppress the rest" (phrase-anchored, not line-anchored:
    round-3 / S4 retired the line cites in this file). Only the OverflowError leg is
    pinned by a test, and only at the clause site plus the /regex/ expect-fail
    signature site; the "literal" site stays inert. The RecursionError
    threshold moves with the interpreter's recursion limit AND with the stack depth
    already consumed at the call site (measured on this tree: 495 nested groups
    compile clean from a shallow frame and raise from a deeper one), so a test
    asserting on it would pin the interpreter, not this guard.

    THE SEARCH IS NOT BOUNDED HERE — it is bounded by the CALLER, and only one caller
    does it (round-1 / SIG-5, round-3 / S4+S5). A clause that compiles fine can still
    hang re.search catastrophically — measured on this tree, /(a+)+$/ against a 24-byte
    body takes 2.1 s and against a 40-byte body does not return in 120 s, and the Tier-2
    body cap is 4096 bytes. That outcome is worse than the exception this guard
    replaces: a LintError is recoverable and attributed to one record, a hang takes the
    process with no receipt and no verdict. The exposure is pre-existing (an
    `expect-fail=/(a+)+$/` signature has been fed to the same re.search since v1) and
    this branch widens the surface at the same seam by admitting a second
    freely-authored source.

    Where the bound lives, and why not here: tier2_witness wraps its whole body in
    _witness_bound(), which arms signal.setitimer(ITIMER_REAL, WITNESS_TIMEOUT_S) and
    converts SIGALRM into a WitnessTimeout — see _witness_alarm. #486 / D7 re-sited it
    there from _verify_single precisely so a DIRECT tier2_witness() importer is bounded
    too, not only the CLI; _verify_single now arms nothing. Where setitimer does not
    exist (non-Unix), or the call is off the main thread (signal.signal raises
    ValueError), that degrades to unbounded rather than aborting (round-4 / M7). This
    module is NOT imported by any hook (hooks/rcpt-verify-hook.sh runs it as a
    --tier1 SUBPROCESS, which never reaches this search at all), and installing a signal
    handler at import time on its importers' behalf would be the overreach — a handler is
    the owning process's business, and setitimer's handler does run on the main thread, so
    those callers can install one if they want it. --eval stays unbounded and is now the
    ONLY unbounded path: _eval_tier2 reaches verify_witness directly, without going
    through tier2_witness. --selftest DOES route through tier2_witness (twice) and is
    therefore bounded after D7. Carried on #488.

    The importers, and which of them are UNBOUNDED (round-5 / MIN-2 — this list had been
    wrong twice when that was written and was wrong a third time until #486/T20, so it
    names dispositions, not just names):
      * _gen.py, sweep.py, test_rcpt_verify.py — pre-existing, and now with three
        DIFFERENT dispositions. Re-derived at #486/T20: grepping every .py outside this
        file and its test module for tier2_witness|verify_witness|_eval_tier2 returns
        exactly THREE call sites (_gen.py, measure_474_corpus.py and
        measure_486_corpus.py), and inside this file verify_witness( has exactly two
        (tier2_witness and _eval_tier2) — which is what makes --eval the only remaining
        unbounded path.
          - sweep.py has NO hit: it reaches this guard through Tier-1 ONLY
            (lint_receipt / parse_witness), i.e. it compiles receipt-authored patterns
            and never runs one against a body — same disposition as
            measure_474_denominators.py below.
          - _gen.py calls tier2_witness (:413) and is therefore BOUNDED after D7, with
            its timeout swallow fixed in the same commit.
          - test_rcpt_verify.py is likewise BOUNDED at its tier2_witness( call sites, and
            carries criterion 8's ACCEPTED residual: at the overlap with its
            assertRaises(self.rv.LintError) blocks a wall-clock timeout is still a
            passing test. Narrowing those is a separate declared flip, not done here.
      * measure_474_denominators.py (CI-gated, run_tests.sh) — reaches this guard only
        through Tier-1 (lint_receipt / parse_witness / parse_out_range). It COMPILES
        receipt-authored patterns and never runs one against a body, so it is safe.
      * measure_474_corpus.py — calls rv.tier2_witness(...) DIRECTLY at :58, which is now
        where the arm lives, so it is BOUNDED after D7 (this is the "a direct importer is
        bounded too" property D7 is sold on). Its RESIDUAL is distinguishability, not
        liveness: :58's `except rv.LintError` still renders a timeout as a BLOCKED
        disposition. Stated, not solved — #486 does not republish its figures. It is not
        run by run_tests.sh.
      * measure_486_corpus.py — added by this branch (#486 task 18); calls
        rv.tier2_witness(...) DIRECTLY at :303, so it is BOUNDED after D7 for the same
        reason measure_474_corpus.py is. It does NOT carry that module's
        distinguishability residual: its `except rv.WitnessTimeout` arm is ordered
        BEFORE `except rv.LintError`, so a timeout surfaces as a skip rather than as a
        BLOCKED disposition. Not run by run_tests.sh directly; it is CI-gated through
        scripts/test_measure_486.py, which imports and drives it."""
    try:
        re.compile(src)
    except (re.error, OverflowError, RecursionError) as e:
        raise LintError(f"{msg_prefix}: {shown!r} ({e})")


# ── siege S-4 — the OTHER direction of the expect-fail shape guard.
#
# `parse_witness`'s existing guard is `len(pattern) < 4 or pattern in {".*", ".+"}`: a
# two-element blacklist aimed exclusively at the ALWAYS-FIRES direction (a predicate so
# broad it false-BLOCKs). Nothing rejected the mirror image — a predicate that PROVABLY
# CANNOT fire. `/(?!)/`, `/(?!x)x/` and `/[^\s\S]/` were accepted, billed `witness 1/1`
# ("a predicate ran against the bytes read from disk" — satisfied to the letter) and
# rendered a census BYTE-IDENTICAL to the honest run that exits 1. That is
# "coverage that cannot fail", which this codebase forbids by name elsewhere.
#
# A DECISION PROCEDURE for regex emptiness is not on offer here and this is not one: it
# is a shape blacklist, deliberately the same instrument and the same size as the
# always-fires blacklist one branch over, covering the three published constructions and
# their immediate twins. Measured cost: 0 of the 11 distinct expect-fail sources across
# the committed jsonl corpora, return-convention.md and red-team-prompt.md. A sound
# decision procedure would mean walking `re._parser`'s private AST, which pins the
# interpreter rather than this guard.
#
# C1-R2-S3 — WHAT THIS GUARD CLAIMS, CORRECTED. It claimed it "can only ever FALSE-ACCEPT
# …, never false-reject a satisfiable pattern". That claim was FALSE, and it was
# load-bearing: it is the entire safety argument for shipping a heuristic into a Tier-1
# gate that HARD-FAILS, and a hard Tier-1 FAIL is a structural BLOCK on the one linter
# build:14, siege:21, quality-gate:30 and return-convention.md run on EVERY receipt, whose
# only documented remedy is a re-dispatch loop. Three separate causes, all now closed:
#   (1) LOOKBEHIND ≠ LOOKAHEAD. `\(\?<?!…\)` admitted `(?<!X)X`, which is "an X not
#       preceded by X" — satisfiable for every X — and the emitted reason string then
#       MISDESCRIBED it as "the lookahead". `(?<!=)=fatal` was rejected while matching
#       'x=fatal'. A wrong rule, not a narrow one. The `<?` is gone.
#   (2) NO ALTERNATION AWARENESS. A source is empty only if EVERY alternative is;
#       `(?!)|significant=[1-9]` was rejected while matching 'significant=7'. A `|` at
#       top level now declines to judge at all — the fail-ACCEPT direction this blacklist
#       already declares it prefers.
#   (3) NO CONTEXT AWARENESS. `tok in src` / `.search()` are substring tests, so `[(?!)]`
#       (a class matching one of `(`, `?`, `!`, `)`) and `\[^\s\S]` (a literal `[`) both
#       tripped an arm, and `((?!a)a)?b` — where the empty element is quantified away —
#       would have too. Every arm now requires its match to start at a JUDGEABLE position
#       (see _regex_judgeable) and to carry no `?`/`*`/`{` quantifier of its own.
# The corrected claim, which each arm meets by construction rather than by heuristic: for
# a source with no top-level `|`, an UNQUANTIFIED top-level `(?!)` / `(?<!)` / `[^\C\c]` /
# `(?!TEXT)TEXT` makes the whole source empty for every input, because at depth 0 the
# source is a pure sequence and every element of it must match. Sources carrying
# alternation are not judged; nor is any construction nested inside a group, where a
# quantifier could make it optional. Both of those are refusals to judge, i.e. the
# false-ACCEPT direction, which is the only direction this guard is allowed to be wrong in.
_UNSAT_LOOKAROUND = ("(?!)", "(?<!)")
# A NEGATED class holding a category AND its complement (\s\S, \w\W, \d\D) is the empty
# set, so nothing can match one character of it.
_UNSAT_EMPTY_CLASS_RE = re.compile(r"\[\^\\([sSwWdD])\\([sSwWdD])\]")
# `(?!TEXT)TEXT` — a negative lookahead forbidding exactly the literal that follows it.
# The captured run is restricted to plain literal characters so a quantified or grouped
# body (where the two need not be the same language) is not claimed to be provable.
# NO `<?`: see cause (1) above.
_UNSAT_SELF_NEGATED_RE = re.compile(r"\(\?!([^()\[\]\\|?*+{}]+)\)")
# A quantifier that admits ZERO repetitions, which makes the element it applies to
# optional and therefore makes an empty element harmless. `+` is deliberately absent (it
# requires one repetition), but excluding it too would only cost accepts.
# A TUPLE, not a string: `src[end:end+1]` is `""` at end-of-source and `"" in "?*{"` is
# True, which would silently make every construction at the END of a source unjudgeable —
# i.e. the guard would accept the three published constructions themselves.
_UNSAT_ZERO_QUANTIFIERS = ("?", "*", "{")


def _regex_judgeable(src):
    """C1-R2-S3 — per-index flags: True where a top-level regex TOKEN starts, i.e. the
    index is outside every `[...]` character class, is not the operand of a `\\` escape,
    and is at group depth 0.

    This is what makes each arm of `_unsatisfiable_reason` a statement about the SOURCE
    rather than about an arbitrary substring of it. `[(?!)]` is a character class, not a
    lookahead; `\\[^\\s\\S]` is a literal `[`, not a negated class; and at depth > 0 an
    empty element can be quantified away by the group that holds it (`((?!a)a)?b` matches
    'b'). Every one of those was reported as "can never match".

    Deliberately NOT a parser: group depth counts unescaped top-level parens without
    distinguishing capturing, non-capturing or lookaround groups, and an unbalanced `)`
    drives the depth negative so that nothing after it is judgeable. Both errors are in
    the refuse-to-judge direction."""
    flags = [False] * len(src)
    i, n, depth, in_class = 0, len(src), 0, False
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2                       # the escape and its operand: never judgeable
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        flags[i] = depth == 0
        if c == "[":
            in_class = True
            # `]` as the FIRST member of a class is a literal `]`, not the terminator.
            j = i + 2 if src[i + 1:i + 2] == "^" else i + 1
            if src[j:j + 1] == "]":
                i = j + 1
                continue
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return flags


def _unsatisfiable_reason(src):
    """Return a one-clause reason when `src` is a PROVABLY empty regex source, else None.
    See _UNSAT_LOOKAROUND for the scope of "provably", why this is a blacklist, and — the
    part that is load-bearing — the exact sense in which it does not false-reject."""
    if src is None:
        return None
    judgeable = _regex_judgeable(src)

    def unquantified(end):
        return src[end:end + 1] not in _UNSAT_ZERO_QUANTIFIERS

    # Cause (2) — alternation at top level: every branch would have to be empty, and this
    # guard reasons about one. Refuse to judge rather than reject.
    if any(c == "|" and judgeable[i] for i, c in enumerate(src)):
        return None
    for tok in _UNSAT_LOOKAROUND:
        i = src.find(tok)
        while i != -1:
            if judgeable[i] and unquantified(i + len(tok)):
                return f"the empty negative lookaround {tok} can never match"
            i = src.find(tok, i + 1)
    for m in _UNSAT_EMPTY_CLASS_RE.finditer(src):
        if (judgeable[m.start()] and unquantified(m.end())
                and m.group(1) != m.group(2)
                and m.group(1).lower() == m.group(2).lower()):
            return f"the negated class {m.group(0)} excludes every character"
    for m in _UNSAT_SELF_NEGATED_RE.finditer(src):
        lit = m.group(1)
        if (judgeable[m.start()] and src[m.end():].startswith(lit)
                and unquantified(m.end() + len(lit))):
            return (f"the lookahead {m.group(0)} forbids the very text that follows it")
    return None


def _reject_unsatisfiable(src, msg_prefix, shown):
    reason = _unsatisfiable_reason(src)
    if reason is not None:
        raise LintError(f"{msg_prefix}: {shown!r} ({reason})")


def _check_clause_shape(clause):
    """The D3 (a)-(d) ladder for a WITNESS `pattern=` clause: delimited → derive →
    non-empty → floor → compiles. Raises LintError; returns nothing.

    Extracted (round-1 / SIG-2) so it can run on EVERY clause-carrying witness rather
    than only under `expect-fail=match`, which is where it used to live.

    S2(a)3 — the ordered enumeration, and the order is part of the spec:
    (a) delimited → (b) derive → (c) non-empty, then the floor → (d) compile.
    (a) must precede (d) because a bare clause COMPILES (re.compile("significant=[1-9]")
    succeeds) yet derives None, which verify_witness reads as clean — #474 verbatim.
    (c) must precede (d) for the same reason one delimiter over: re.compile("")
    succeeds and '' is FALSY, so `if pattern and re.search(...)` short-circuits clean.

    Derivation is via _expect_fail_pattern("match", clause) — the clause branch of the
    one shared helper — so the shape accepted here and the source evaluated at Tier-2
    cannot drift, whatever the receipt's own expect-fail signature says."""
    if not ((clause.startswith("/") and clause.endswith("/")) or
            (clause.startswith('"') and clause.endswith('"'))):
        raise LintError(
            f'WITNESS pattern= clause must be /regex/ or "literal": {clause!r}')
    src = _expect_fail_pattern("match", clause)
    if src == "":
        raise LintError(f"WITNESS pattern= clause derives an empty regex source: {clause!r}")
    if len(src) < 4:
        # A style bound inherited from the signature forms, declared for what it is:
        # under `match` a SHORTER pattern is BROADER and therefore stricter, so this
        # can only ever false-reject. It is NOT what closes the fail-open — the
        # non-empty rule above is. Kept because dropping it would be an undeclared
        # relaxation of the accepted subset (measured cost: 0 of 7 real clauses).
        #
        # round-4 / M1 — DELIBERATELY not the same string the expect-fail literal
        # floor measures, and NOT to be "unified" with it. This floor counts the
        # DERIVED source; parse_witness's `"literal"` floor counts the RAW inner text.
        # So pattern="a.b" is accepted (derives `a\.b`, 4 chars) where
        # expect-fail="a.b" is rejected — an inconsistency in the accepted subset, in
        # the fail-closed direction, and both are documented as written. Unifying on
        # the raw text would LOWER this floor for every escaping literal, which is a
        # relaxation of a clause rule and needs its own argument, not a tidy-up.
        raise LintError(f"WITNESS pattern= clause too short: {clause!r}")
    _compile_guard(src, "WITNESS pattern= clause is not a valid regex", clause)
    # siege S-4 — the clause is the `expect-fail=match` predicate, so it is the SAME
    # "cannot fire" hazard the signature site carries and takes the same guard.
    _reject_unsatisfiable(src, "WITNESS pattern= clause can never match", clause)


def parse_witness(body):
    if not body:
        raise LintError("WITNESS missing")
    line = body[0].strip()
    if line == "(n/a)":
        raise LintError("WITNESS is '(n/a)' — not permitted under any verdict")
    # form: <kind>:<payload>  expect-fail=<sig>  ran=<disp>
    # expect-fail sig may be /regex/ or "literal" which can contain spaces.
    # Anchor on `  ran=` (last occurrence) and split backwards.
    if "  ran=" not in line and " ran=" not in line:
        raise LintError(f"WITNESS missing ran= clause: {line!r}")
    head, _, ran = line.rpartition("ran=")
    head = head.rstrip()
    if not head.endswith(" "):
        # ran= must be preceded by whitespace
        pass
    # head now ends before " ran=". Find " expect-fail=" (first occurrence after payload).
    if "expect-fail=" not in head:
        raise LintError(f"WITNESS missing expect-fail= clause: {line!r}")
    kind_payload, _, expect_fail = head.rpartition("expect-fail=")
    kind_payload = kind_payload.rstrip()
    expect_fail = expect_fail.strip()
    if ":" not in kind_payload:
        raise LintError(f"WITNESS kind:payload malformed: {line!r}")
    kind, _, payload = kind_payload.partition(":")
    kind = kind.strip()
    payload = payload.strip()
    ran = ran.strip()
    if kind not in {"exec", "grep", "lint"}:
        raise LintError(f"WITNESS kind unknown: {kind!r}")
    if kind == "lint" and payload not in LINT_RULES:
        raise LintError(f"WITNESS lint rule unknown: {payload!r}")
    # #474 / S2(a)2-3 — strip the trailing pattern= clause off the payload. `payload_raw`
    # keeps it and is the ONLY clause-carrying string: it is what the ran=SKIPPED: check
    # binds verbatim (D1), so dropping the predicate there would silently loosen the
    # deferred path. Scoped to kind == "grep" — the clause is only ever READ on the grep
    # path, and stripping it elsewhere could only mutate payload for no gain (measured
    # null: 0 non-grep WITNESS lines carry a pattern= token).
    payload_raw = payload
    clause = None
    if kind == "grep":
        cm = _WITNESS_CLAUSE_RE.search(payload_raw)
        if cm:
            clause = cm.group(1)
            payload = payload_raw[:cm.start()].rstrip()
            # #474 round-2 / SIG-1 — the regex is `\s*$`-anchored, so on a payload
            # carrying TWO clauses it binds the LAST and leaves the first inert inside
            # `payload`: only the last is shape-checked below and only the last is
            # evaluated at Tier-2. Appending one token to the mandated witness therefore
            # restored #474 verbatim, and the winning clause is the trailing one — the
            # one an appender controls. Rejected rather than resolved by position, for
            # the reason rule (2) below already gives for two predicates across FIELDS
            # and return-convention.md ships as normative text: the receipt declares two
            # predicates and the linter cannot know which the author meant. Re-running
            # the same regex on the STRIPPED payload makes the rule "more than one",
            # not "exactly two" — the remainder's own last clause is now trailing.
            # Scoped to `if cm`, so a payload no clause was extracted FROM is untouched:
            # a rangeless grep whose search text merely contains a non-trailing
            # `pattern=` token keeps today's behaviour (test 28). Measured cost: 0 sites
            # carry two clauses across the committed jsonl corpus, return-convention.md,
            # red-team-prompt.md and the live as-returned corpus.
            if _WITNESS_CLAUSE_RE.search(payload):
                raise LintError(
                    f"WITNESS carries more than one pattern= clause: {payload_raw!r}")
    # expect-fail validation
    if not expect_fail:
        raise LintError("WITNESS expect-fail empty")
    if expect_fail.startswith("/") and expect_fail.endswith("/"):
        pattern = expect_fail[1:-1]
        if len(pattern) < 4 or pattern in {".*", ".+"}:
            raise LintError(f"WITNESS expect-fail wildcard/too-short: {expect_fail!r}")
        _compile_guard(_expect_fail_pattern(expect_fail),
                       "WITNESS expect-fail is not a valid regex", expect_fail)
        # siege S-4 — the mirror of the wildcard test above. That one blocks a predicate
        # that always fires; this one blocks a predicate that can never fire, which is
        # the direction that buys a clean exit 0 with a census identical to the honest
        # run's. A `"literal"` signature needs no such guard: re.escape's output always
        # matches its own source text.
        _reject_unsatisfiable(_expect_fail_pattern(expect_fail),
                              "WITNESS expect-fail can never match", expect_fail)
    elif expect_fail.startswith('"') and expect_fail.endswith('"'):
        if len(expect_fail[1:-1]) < 4:
            raise LintError(f"WITNESS expect-fail literal too short: {expect_fail!r}")
        # Declared widening (round 9 / SIG-2): provably inert here — re.escape output
        # always compiles — but applied for uniformity at the same site.
        _compile_guard(_expect_fail_pattern(expect_fail),
                       "WITNESS expect-fail is not a valid regex", expect_fail)
    elif not re.match(r"^(exit!=0|exit=-?\d+|match)$", expect_fail):
        raise LintError(f"WITNESS expect-fail not a valid signature form: {expect_fail!r}")
    # #474 round-1 / SIG-2 — the clause rules run on EVERY clause-carrying witness,
    # not only under `expect-fail=match`. The strip above is unconditional for
    # kind=grep, so before this a clause standing beside a /regex/ or "literal"
    # signature was removed from the payload, validated by NOTHING, and then discarded
    # at Tier-2 (_expect_fail_pattern returns the SIGNATURE source whenever expect_fail
    # is not "match"). `pattern=//` and `pattern=/[unclosed/` — the exact two shapes
    # (c) and (d) below exist to reject — passed clean one branch over, and the
    # reviewer's stated predicate was silently replaced by a possibly-stale signature.
    # Two rules, in this order so the more specific diagnostic wins:
    #   (1) a clause must be well-formed WHEREVER it appears; then
    #   (2) a clause beside a non-`match` signature is REJECTED, not silently resolved
    #       one way — the receipt declares two predicates and the linter cannot know
    #       which the author meant. `return-convention.md`'s Kinds bullet presents
    #       `pattern=` as THE grep predicate, so preferring expect-fail reads as
    #       "verified something other than what the author declared" — #474's class.
    # Measured cost: 0 sites pair a clause with a non-`match` signature across the
    # committed jsonl corpus, return-convention.md, red-team-prompt.md and the
    # 17-receipt live as-returned corpus. `clause` is None for every non-grep kind
    # (the strip is grep-scoped), so rule (2) can only ever fire on kind=grep.
    if clause is not None:
        _check_clause_shape(clause)
        if expect_fail != "match":
            raise LintError(
                f"WITNESS pattern= clause is only meaningful with expect-fail=match "
                f"(got expect-fail={expect_fail!r}); the clause would be silently ignored")
    if expect_fail == "match":
        # #474 / D3. Bare `match` carried no predicate at all, so Tier-2 read it as
        # clean — the P0. These are Tier-1, text-only, and therefore live in every
        # configuration (unlike the Tier-2 half, which cannot fire under the mandated
        # --root until artifact resolution lands).
        if kind != "grep":
            # return-convention.md § "witness structural check" ("fail if
            # expect-fail=match and kind is not grep") already said so; the divergence
            # was inert only
            # while bare `match` carried no predicate. Post-D3 an exec:/lint: witness
            # would newly run the reviewer's regex against the EXEC out= body.
            raise LintError(
                f"WITNESS expect-fail=match is only valid for kind=grep (got kind={kind})")
        if clause is None:
            raise LintError(f"WITNESS expect-fail=match requires a pattern= clause: {line!r}")
    # #474 / S2(b) — the payload range is parsed ONCE, here, from the clause-STRIPPED
    # payload (never payload_raw: a string still carrying `pattern=/x#L1-L2/` would
    # select the CLAUSE's range, or fail to match and silently take the rangeless
    # branch, disabling both new Tier-1 guards on the exact shape this repairs).
    art = range_kind = range_a = range_b = None
    if kind == "grep":
        rm = _WITNESS_RANGE_RE.match(payload)
        if rm:
            art, range_kind = rm.group(1), rm.group(2)
            # SIEGE-R2BA-3 — the payload range bounds are receipt-authored.
            range_a = _receipt_int(rm.group(3), "WITNESS payload range start")
            range_b = _receipt_int(rm.group(4), "WITNESS payload range end")
            # D6 span bound, SOUND calibration (see check_span_bound); the message names
            # the clause-stripped payload, not the predicate beside it.
            check_span_bound(range_kind, range_a, range_b,
                             bytes_per_line=1, label="witness", detail=payload)
    # #474 round-1 / SIG-1 — `expect-fail=match` REQUIRES a ranged payload. Every guard
    # this issue adds is scoped to `range_kind is not None`: D6's ARTIFACTS membership,
    # D6's span bound, D4's payload-sourced artifact, D6's empty-body rejection. A
    # RANGELESS `match` payload therefore turned all four off and had its predicate
    # evaluated against whatever derive_art_name returns for the cited TRACE entry —
    # a file the witness does not name. That is #474's exact consequence, after the
    # fix, reachable by deleting six characters, and it fails OPEN and SILENT (a clean
    # PASS, no UNVERIFIABLE note) where every other rule on this branch fails closed.
    #
    # This is not a widening of the guards to all rangeless payloads — that would
    # break the committed `grep:boom  expect-fail=/boom/` shapes RED test 13 pins,
    # which are `expect-fail=/…/` and stay exempt. It is ONE precondition on the one
    # signature whose grammar already requires the range: return-convention.md's Kinds
    # bullet defines the kind as `grep:<artifact>#<range>  pattern=<regex>`, so the
    # rangeless-`match` shape was never in the spec the linter enforces. Sited here
    # rather than in the `match` block above because that block runs BEFORE the range
    # parse. Measured cost: 0 of 14 `expect-fail=match` sites across the committed
    # jsonl corpus, return-convention.md, red-team-prompt.md and the live corpus.
    if expect_fail == "match" and range_kind is None:
        raise LintError(
            f"WITNESS expect-fail=match requires a ranged grep payload "
            f"(grep:<artifact>#<range>): {payload!r}")
    return {"kind": kind, "payload": payload.strip(), "payload_raw": payload_raw.strip(),
            "pattern": clause, "art": art, "range_kind": range_kind,
            "range_a": range_a, "range_b": range_b,
            "expect_fail": expect_fail, "ran": ran.strip()}


_TRACE_REF_RE = re.compile(r"^TRACE#([0-9]+)$")


def _trace_idx(ref: str) -> int:
    """Parse N from a `TRACE#N` reference. Raises LintError (NOT a raw ValueError
    traceback) on a non-numeric / empty / trailing-junk suffix. Receipt text is
    attacker-influenced, so a malformed citation must lint-FAIL cleanly — and an
    uncaught ValueError here used to abort the whole `--eval` batch (#440).
    Anchored on ASCII digits only (`str.isdigit()` would admit e.g. superscripts
    that `int()` then rejects)."""
    m = _TRACE_REF_RE.match(ref)
    if not m:
        raise LintError(f"malformed TRACE# reference: {ref!r}")
    # SIEGE-R2BA-3 — the ASCII-digit anchor closed the NON-NUMERIC leg this docstring
    # describes; it does not close the OVER-LONG one, which raises the same uncaught
    # ValueError from the same call and aborts the same --eval batch.
    return _receipt_int(m.group(1), "TRACE# reference")


def lint_receipt(text):
    sections = parse_receipt(text)
    # VERDICT
    verdict_body = sections["VERDICT"]
    if not verdict_body:
        raise LintError("VERDICT empty")
    vm = re.match(r"^(PASS|FAIL|BLOCKED)\s+conf=(\S+)\s*$", verdict_body[0])
    if not vm:
        raise LintError(f"VERDICT malformed: {verdict_body[0]!r}")
    verdict = vm.group(1)
    if not CONF.match(vm.group(2)):
        raise LintError(f"VERDICT conf malformed: {vm.group(2)!r}")
    artifacts = parse_artifacts(sections["ARTIFACTS"])
    trace = parse_trace(sections["TRACE"])
    claims = parse_claims(sections["CLAIMS"])
    witness = parse_witness(sections["WITNESS"])
    # #474 / D6 — a RANGED kind=grep witness payload must name an artifact the receipt
    # itself declares. Not a new contract: return-convention.md § "Citation resolution"
    # already says a
    # <artifact>#<range> citation is valid iff <artifact> appears in ARTIFACTS, and the
    # structurally identical EXEC out= rule is a few lines below. Sited here, not in
    # parse_witness, which never sees ARTIFACTS (its signature stays one-argument: an
    # `artifacts=None` default would make this rule silently inert at all 21 call sites).
    # Text-only, so LIVE on merge — it is what constrains D4's reviewer-chosen body to a
    # declared name. The sha256 BINDING that would make the declaration unforgeable stays
    # latent: tier2_artifacts recomputes only for a name that RESOLVES, and under the
    # mandated --root <dispatch-root> nothing does. Scoped to ranged payloads (rangeless
    # grep keeps today's whole-file behaviour) and verdict-independent, unlike D4's
    # payload rule: this validates a DECLARATION, so it belongs where no read happens.
    if witness["kind"] == "grep" and witness["range_kind"] is not None:
        if witness["art"] not in artifacts:
            # SIEGE-R2BA-4 — a Tier-1 bullet lands on the same parsed channel as a Tier-2
            # one, and this is a bare NAME (not an args string), so it takes the renderer.
            raise LintError(
                f"WITNESS grep artifact not in ARTIFACTS: {_show_path(witness['art'])}")
    # EXEC out= artifact must exist; range bound
    for entry in trace:
        if entry["verb"] == "EXEC":
            check_exec_range_bound(entry["args"])
            r = parse_out_range(entry["args"])
            if r and r.artifact not in artifacts:
                raise LintError(
                    f"EXEC out= artifact not in ARTIFACTS: {_show_path(r.artifact)}")
        elif entry["verb"] in {"EDIT", "WROTE"}:
            m = re.search(r"sha256:([0-9a-f]{64})", entry["args"])
            if not m:
                raise LintError(f"{entry['verb']} missing sha256: {entry['args']}")
            if m.group(1) not in {a["hash"] for a in artifacts.values()}:
                # DELIBERATE NON-GATE (#412 / BS1), NOT a TODO: the EDIT/WROTE hash is
                # provenance, not a verified claim. It is intentionally NOT required to
                # appear in ARTIFACTS — 0000…0 placeholders are the norm, and the dominant
                # legitimate pattern (EDIT src/foo.ts while only patch.diff is declared) is
                # structurally identical to a fabricated one, so gating here would flip
                # committed clean-pass fixtures and the canonical example. Effects are
                # verified via declared ARTIFACTS (disk-verified under --strict), the
                # WITNESS, and the receipt-ledger — never via this hash. See
                # return-convention.md "for each EDIT / WROTE in TRACE".
                path_m = re.match(r"^(\S+)", entry["args"])
                if path_m and path_m.group(1) not in artifacts:
                    pass  # accept — deliberate non-gate per the note above (#412)
        elif entry["verb"] == "DISPATCHED":
            if not re.search(r"rcpt-sha256:[0-9a-f]{64}", entry["args"]):
                raise LintError(f"DISPATCHED missing rcpt-sha256: {entry['args']}")
    # CLAIM citations must resolve
    for c in claims:
        cit = c["citation"]
        if cit.startswith("TRACE#"):
            idx = _trace_idx(cit)
            if not 1 <= idx <= len(trace):
                raise LintError(f"CLAIM citation TRACE#{idx} does not resolve")
        else:
            art_name = cit.split("#", 1)[0]
            # Receipt-hash prefix citations (used by SUPERSEDES justification)
            # are valid without appearing in ARTIFACTS. Layer 2 verifies the
            # hash resolves in the manifest.
            if re.match(r"^[0-9a-f]{12}$", art_name):
                continue
            if art_name not in artifacts:
                raise LintError(
                    f"CLAIM citation artifact not listed: {_show_path(art_name)}")
    # WITNESS ran resolution + rules
    ran = witness["ran"]
    if verdict == "PASS":
        if ran.startswith("UNRUNNABLE"):
            raise LintError("WITNESS ran=UNRUNNABLE not permitted on PASS")
    if ran.startswith("TRACE#"):
        idx = _trace_idx(ran)
        if not 1 <= idx <= len(trace):
            raise LintError(f"WITNESS ran=TRACE#{idx} does not resolve")
        verb = trace[idx - 1]["verb"]
        if witness["kind"] == "exec" and verb != "EXEC":
            raise LintError(f"WITNESS kind=exec requires ran= to point to EXEC (got {verb})")
        if witness["kind"] == "grep" and verb not in {"EXEC", "READ", "WROTE"}:
            raise LintError(f"WITNESS kind=grep requires ran= to point to EXEC/READ/WROTE (got {verb})")
    elif ran.startswith("SKIPPED:"):
        next_body = " ".join(sections["NEXT"])
        # #474 / D1: payload_RAW — the clause-carrying string. This check is what makes a
        # deferred witness runnable from the Cairn OPEN_OBLIGATIONS tail, so binding the
        # stripped payload would silently loosen the deferred path (the one nobody
        # watches) and name a string the check never used.
        if witness["payload_raw"] not in next_body:
            raise LintError(
                f"WITNESS ran=SKIPPED requires NEXT to contain witness payload verbatim; "
                f"payload={witness['payload_raw']!r}  NEXT={next_body!r}"
            )
    elif ran.startswith("UNRUNNABLE:"):
        reason = ran[len("UNRUNNABLE:"):]
        if reason not in UNRUNNABLE_VOCAB:
            raise LintError(f"UNRUNNABLE reason not in closed vocabulary: {reason!r}")
    else:
        raise LintError(f"WITNESS ran= form unknown: {ran!r}")
    # mandatory-work: tests run OR tests-related CLAIM must be backed by EXEC/SKIPPED
    claim_keys = {c["key"] for c in claims}
    if {"tests-ran", "tests-pass"} & claim_keys:
        has_exec = any(e["verb"] == "EXEC" for e in trace)
        has_skipped = any(e["verb"] == "SKIPPED" and "tests" in e["args"].lower() for e in trace)
        if not (has_exec or has_skipped):
            raise LintError("tests-ran/tests-pass claim but no EXEC and no SKIPPED tests entry")
        # Check claim points at an EXEC and success-claim is consistent with exit code
        if not has_skipped:
            for c in claims:
                if c["key"] in {"tests-ran", "tests-pass"} and c["citation"].startswith("TRACE#"):
                    idx = _trace_idx(c["citation"])
                    cited = trace[idx - 1]
                    if cited["verb"] != "EXEC":
                        raise LintError(f"CLAIM {c['key']} cites TRACE#{idx} which is {cited['verb']}, not EXEC")
                    # Consistency: tests-pass=true must not cite a non-zero-exit EXEC
                    if c["key"] == "tests-pass" and c["value"] == "true":
                        em = re.search(r"exit=(-?\d+)", cited["args"])
                        # SIEGE-R2BA-3 — the cited EXEC's own `exit=` is receipt text.
                        if em and _receipt_int(em.group(1), "TRACE exit=") != 0:
                            raise LintError(
                                f"CLAIM tests-pass=true cites TRACE#{idx} with exit={em.group(1)} "
                                f"(structural contradiction)"
                            )
    # v1.1 Tier-1 extension — version-dispatched; v1 receipts skip it entirely.
    # Folded into lint_receipt so EVERY caller (_verify_single, _eval_record,
    # run_selftest, the --tier1 hook) inherits v1.1 enforcement.
    parsed_v11 = parse_v11_sections(text)
    if parsed_v11 is not None:
        lint_v11_local(parsed_v11)
    return verdict


def parse_predicates(body):
    """Parse a TRIPWIRE/TRIPWIRE-CHILD body (`|`-separated predicates) into a list,
    enforcing the closed predicate vocabulary. `none` → []. Receipt-local."""
    if body == "none":
        return []
    out = []
    for p in (p.strip() for p in body.split("|")):
        m = re.match(
            r"^(suspicion>=[\d.]+|claims-touch\(.+?\)|wrote\(.+?\)|read\(.+?\)|"
            r"exec-exit!=0|peer-dispatch-disagrees\((?:verdict|same-file|severity|count)\)|verdict=FAIL|always)$",
            p,
        )
        if not m:
            raise LintError(f"v1.1 TRIPWIRE unknown predicate: {p!r}")
        out.append(p)
    return out


def expand_glob_entries(glob):
    """Count alternation entries in a glob predicate body (comma-shortcut or {a,b,c}).
    Counting only — never imports fnmatch (matching is sweep-only)."""
    inside = re.search(r"\((.*)\)", glob)
    if not inside:
        return 1
    body = inside.group(1)
    # Sum alternation across the WHOLE body: split on TOP-LEVEL commas (commas not
    # inside {…}); a {…} segment contributes its comma-count, a plain segment 1.
    total = 0
    depth = 0
    seg = ""
    segments = []
    for ch in body:
        if ch == "{":
            depth += 1
            seg += ch
        elif ch == "}":
            depth -= 1
            seg += ch
        elif ch == "," and depth == 0:
            segments.append(seg)
            seg = ""
        else:
            seg += ch
    segments.append(seg)
    for s in segments:
        brace = re.search(r"\{([^{}]*)\}", s)
        total += len(brace.group(1).split(",")) if brace else 1
    return total


def parse_v11_sections(text):
    """Recover the v1.1 Layer-2 sections (TRIPWIRE / SUPERSEDES / TRIPWIRE-CHILD)
    from the raw text tail after NEXT (parse_receipt's SECTIONS end at NEXT, so it
    swallows them — the tail scan recovers them as their own post-NEXT lines).
    Returns None for an RCPT v1 header (version-dispatch: v1 skips the extension).
    Enforces presence of TRIPWIRE + SUPERSEDES and the TRIPWIRE-CHILD-required-when-
    DISPATCHED rule; value checks live in lint_v11_local."""
    if not re.match(r"^RCPT v1\.1 ", text.splitlines()[0] if text.splitlines() else ""):
        return None
    sections = parse_receipt(text)
    tail = text.split("\nNEXT", 1)[1] if "\nNEXT" in text else ""
    tripwire = supersedes = trip_child = None
    for line in (l for l in tail.splitlines()[1:] if l.strip()):
        if line.startswith("TRIPWIRE-CHILD:"):
            if trip_child is not None:
                raise LintError("v1.1 section TRIPWIRE-CHILD duplicated")
            trip_child = line[len("TRIPWIRE-CHILD:"):].strip()
        elif line.startswith("TRIPWIRE:"):
            if tripwire is not None:
                raise LintError("v1.1 section TRIPWIRE duplicated")
            tripwire = line[len("TRIPWIRE:"):].strip()
        elif line.startswith("SUPERSEDES:"):
            if supersedes is not None:
                raise LintError("v1.1 section SUPERSEDES duplicated")
            supersedes = line[len("SUPERSEDES:"):].strip()
    if tripwire is None:
        raise LintError("v1.1 receipt missing TRIPWIRE: line (own line after NEXT)")
    if supersedes is None:
        raise LintError("v1.1 receipt missing SUPERSEDES: line (own line after NEXT)")
    # Empty-after-strip body is malformed (distinct from an absent line): the grammar
    # is `<predicate>[ | …]*` OR `none`/`<prefix>`/`none` — bare `TRIPWIRE:` matches
    # NEITHER, and "" would slip past both the `== "none"` two-leg gate and the
    # `if not body` predicate-loop skip in lint_v11_local (false-PASS). TRIPWIRE-CHILD
    # only when the line is PRESENT (absence stays `none` per return-convention.md
    # § "Recursive dispatch — TRIPWIRE-CHILD": "omitted — absence is treated as none").
    if tripwire == "":
        raise LintError("v1.1 TRIPWIRE: line has empty body (use a predicate or `none`)")
    if supersedes == "":
        raise LintError("v1.1 SUPERSEDES: line has empty body (use a prefix or `none`)")
    if trip_child is not None and trip_child == "":
        raise LintError("v1.1 TRIPWIRE-CHILD: line has empty body (use a predicate or `none`)")
    if any(t["verb"] == "DISPATCHED" for t in parse_trace(sections["TRACE"])) and trip_child is None:
        raise LintError(
            "v1.1 receipt with DISPATCHED in TRACE must emit TRIPWIRE-CHILD: "
            "(return-convention.md § 'Linter extension (Tier-1 additions for v1.1 "
            "receipts)'; the § 'Recursive dispatch' 'absence is treated as none' "
            "parenthetical is scoped to the no-DISPATCHED case — tension tracked in #387)"
        )
    return {"sections": sections, "tripwire": tripwire,
            "supersedes": supersedes, "trip_child": trip_child}


def lint_v11_local(parsed):
    """Receipt-local v1.1 value checks: TRIPWIRE: none two-leg rule; predicate
    vocabulary + glob-subset cap (TRIPWIRE and TRIPWIRE-CHILD); SUPERSEDES
    justification-by-CLAIMS and SUPERSEDES witness-evidence. No manifest access.

    SIEGE-R2CH-2 — the witness-evidence rule, and why it is here despite its trigger
    being manifest-relative.

    return-convention.md § "The Sweep" step 3 tells the orchestrator that "Tier-1 has
    already verified: uniqueness, CLAIMS justification, no-already-superseded,
    witness-evidence (if applicable)" and to mark SUPERSEDED_BY with NO check of its own.
    Of those four, this linter implemented exactly ONE (the CLAIMS `from=<prefix>#…`
    substring test below). Uniqueness and no-already-superseded are genuinely
    manifest-relative and are correctly out of scope — the v1.1 header comment above says
    so, and that is honest. The witness-evidence rule is different: its CONSEQUENT —
    "`N`'s WITNESS MUST have `kind ∈ {exec, grep}` (not `lint`) AND `ran=TRACE#N` (not
    `SKIPPED:` / `UNRUNNABLE:`)" (§ SUPERSEDES, and the Linter-extension pseudocode says
    the same) — reads only this receipt. Unenforced, a receipt with
    `SUPERSEDES: <prefix>` whose witness is `lint:… ran=SKIPPED:` exited 0, i.e. a fix
    agent retired a red-team's FAIL finding, its tripwires and its cairn invariant with a
    receipt that demonstrably ran nothing.

    FAIL-CLOSED OVER-APPROXIMATION, declared as one. The convention conditions the rule
    on the PREDECESSOR ("if any cited predecessor had VERDICT=FAIL OR SUSPICION ≥ 0.30"),
    which a single receipt cannot evaluate — the predecessor is a manifest row. The
    choice is therefore between enforcing nothing and enforcing the consequent on EVERY
    non-`none` SUPERSEDES, and the second is the fail-closed one. What it costs: a
    receipt superseding a PASS, low-suspicion predecessor with a `lint:` witness or a
    deferred `ran=` is convention-legal and is now rejected. Measured cost: 0 sites —
    across every committed corpus (`eval/ledger-return-protocol/**/*.jsonl`, the v1.1
    corpus, the v11-inject shapes, the tier2 fixtures) there are exactly four receipts
    with a non-`none` SUPERSEDES, and the only one this rule newly rejects is
    `tripwire/scenario-supersession-negative.jsonl`, which already declares
    `expect-lint-fail` with `reason_contains: "WITNESS kind in {exec, grep}"` — so the
    message below keeps that substring verbatim. return-convention.md's own worked
    example (:556-575), `scenario-supersession.jsonl` and
    `v11-inject/shape-supersedes-justification.jsonl` all satisfy it already, and both
    consuming skills mandate the strict form unconditionally in their own words
    (quality-gate/SKILL.md:70, siege/SKILL.md:52 — "`exec`/`grep` witness with
    `ran=TRACE#N`", no predecessor condition).

    The precedent for taking the fail-closed reading of a conditionally-worded convention
    clause here, rather than deferring it, is parse_v11_sections' DISPATCHED ⇒
    TRIPWIRE-CHILD rule, whose own tension with the "absence is treated as none"
    parenthetical is recorded on #387. This one belongs in the same place: the linter is
    STRICTER than the convention's letter, in the fail-closed direction, and the gap is
    the maintainer's to close by making the convention unconditional or by giving the
    linter the manifest.

    sweep.py keeps its manifest-GATED copy of the same two checks (:124-136). It is now
    unreachable through `lint_v11` — this runs first and is strictly broader — but it is
    pre-existing and is left in place; it is the only site that can ever narrow the rule
    back to the convention's exact trigger, because it is the only one with a manifest."""
    sections = parsed["sections"]
    susp_body = sections["SUSPICION"]
    susp_tok = susp_body[0].split() if susp_body else []
    if not susp_tok:
        raise LintError("SUSPICION body empty")
    suspicion = susp_tok[0]
    verdict_body = sections["VERDICT"]
    verdict_tok = verdict_body[0].split() if verdict_body else []
    if not verdict_tok:
        raise LintError("VERDICT body empty")
    verdict = verdict_tok[0]
    if parsed["tripwire"] == "none":
        if verdict != "PASS" or suspicion != "0.00":
            raise LintError(
                f"TRIPWIRE: none requires VERDICT=PASS and SUSPICION=0.00 "
                f"(got {verdict}+{suspicion})"
            )
    for body in (parsed["tripwire"], parsed["trip_child"]):
        if not body or body == "none":
            continue
        for p in parse_predicates(body):
            if p.startswith(("claims-touch(", "wrote(", "read(")) and \
               expand_glob_entries(p) > GLOB_ENTRIES_CAP:
                raise LintError(f"v1.1 glob entries exceed cap ({GLOB_ENTRIES_CAP}): {p}")
    if parsed["supersedes"] != "none":
        # siege S-7(b) — the test was `f"from={prefix}#" not in "\n".join(CLAIMS)`, a RAW
        # SUBSTRING scan over the section text. `pattern=` is free, unvalidated receipt
        # text on the same lines, so `verified=true from=TRACE#1 pattern="from=<prefix>#"`
        # satisfied the justification rule with no justifying citation present at all —
        # the rule was vacuously satisfiable by the party it constrains. The PARSED
        # citation field is the thing the rule is about: parse_claims already splits
        # `from=<citation>` out of each line and is already run over this same section by
        # lint_receipt, so this reads the receipt's structure instead of its bytes.
        #
        # NOT a tightening of the rule's TRIGGER (that is #500's subject and is left
        # exactly as it was): the same predecessors are required to be justified by the
        # same citation form. What moves is only that the citation now has to BE one.
        citations = [c["citation"] for c in parse_claims(sections["CLAIMS"])]
        for prefix in (s.strip() for s in parsed["supersedes"].split(",")):
            if not any(cit.startswith(f"{prefix}#") for cit in citations):
                raise LintError(
                    f"SUPERSEDES prefix {prefix} lacks CLAIMS justification "
                    f"(expected a from={prefix}#… citation)"
                )
        # SIEGE-R2CH-2 — the witness-evidence consequent. Sited AFTER the justification
        # loop so that rule's diagnostic keeps winning where both apply (it is the
        # pre-existing one and v11-inject/shape-supersedes-justification pins it).
        # parse_witness cannot raise anything new here: every caller reaches
        # lint_v11_local through a path that has already parsed the same section.
        w = parse_witness(sections["WITNESS"])
        if w["kind"] == "lint":
            raise LintError(
                "SUPERSEDES requires WITNESS kind in {exec, grep}, got lint "
                "(witness-evidence requirement: supersession must demonstrate the "
                "original concern no longer reproduces)")
        if w["ran"].startswith(("SKIPPED:", "UNRUNNABLE:")):
            raise LintError(
                # SIEGE-R2BA-4 — `ran` after `SKIPPED:`/`UNRUNNABLE:` is free receipt
                # text, so it takes a renderer. NOT because the channel is uniformly
                # rendered — it is not: several Tier-1 diagnostics still interpolate
                # receipt-controlled text raw, and closing those is a separate sweep — but
                # because this value is unbounded free text on the one diagnostic a
                # SUPERSEDES receipt controls. `!r` and not _show_path, matching
                # parse_witness's
                # `WITNESS ran= form unknown: {ran!r}`: _show_path is deliberately not
                # applied to whole payload/args strings (a backslash is ordinary there),
                # and `!r` additionally quotes the value so it cannot render as a line of
                # its own on the channel quality-gate captures verbatim.
                f"SUPERSEDES requires witness ran=TRACE#N, got ran={w['ran']!r} "
                f"(witness-evidence requirement: a deferred witness demonstrates "
                f"nothing about the predecessor it retires)")


# ── Tier-2 shared base resolution ───────────────────────────────────────────
def _as_roots(root) -> list:
    """#486 / D1 — normalise the `root` parameter to a de-duplicated list of roots.

    Accepts a bare str/Path (which is what every one of the ~50 existing call sites
    passes, positionally) or a sequence of them, so NO existing caller moves. This is
    the parameter-side half of D8.2's "no direct caller moves" promise.

    De-duplication is D2's and is by Path.resolve(), not by set(): `/tmp/x`, `/tmp/x/`
    and a symlinked equivalent are three tokens for one directory. Order is DECLARATION
    order (D3), so the de-duplication preserves position rather than going through a set.

    SIEGE-C14 — what this de-duplication does NOT do, corrected because the original
    claim here was false and a maintainer acting on it would look for a bug in the wrong
    place: it is NOT what stops two spellings of one root from being reported as an
    ambiguity. Deleting the `seen`/`continue` block leaves the whole suite and
    `--selftest` green, and `--root $D --root $D/` produces byte-identical output either
    way. The real de-duplicator of the AMBIGUITY signal is `resolve_base`'s
    `hit not in found`, which admits each distinct realpath once however many roots'
    probes land on it. This block is kept because it is cheap, because it keeps
    `_allowed_bases` free of duplicate entries, and because it stops one directory being
    probed twice — not because removing it would BLOCK every receipt of such a run.

    #486 fixer / F2 — the RESOLVED path is what is kept, i.e. the same value the
    de-duplication keys on. The original justification for keeping the unresolved token
    ("resolve_base already resolves it for the containment set") was wrong, because
    _git_toplevel is NOT on the containment-set path: _allowed_bases and
    _resolve_base_one both call `_git_toplevel(p)` on whatever this function returns, and
    `pathlib.Path(".").parents` is EMPTY — so a relative root's ancestor walk stopped at
    the cwd and that root's SECOND probed base silently vanished. Two spellings of one
    directory then behaved differently, and because de-duplication keys on the resolved
    path while keeping the unresolved one, WHICH spelling survived depended on
    declaration order — so `--root . --root <abs>` and `--root <abs> --root .` could
    disagree, falsifying criterion 6's "de-duplication is a no-op" (the
    `two-root-dedup-noop` fixture) and quality-gate/SKILL.md:30's "probed bases being
    each supplied root plus that root's git toplevel".
    """
    if isinstance(root, (str, pathlib.Path)):
        root = [root]
    out, seen = [], set()
    for r in root:
        key = pathlib.Path(r).resolve()
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _allowed_bases(roots, refused=None) -> list:
    """#486 / D2 — the #397/C1 containment set: the UNION of every de-duplicated root
    and that root's git toplevel.

    Design :211-213 and :290-295 pin the union DELIBERATELY, so a `..`-traversal from
    root A may legitimately land under root B. Computed ONCE here rather than per root,
    because a per-root set makes resolution depend on which root's probe produced the
    candidate — the implicitness O5 was rejected for — and silently narrows `found`,
    which is D2's ambiguity detector.

    SIEGE-C14 — this used to claim it was "byte-identical to what :839-840 computed at
    5d1fb15" for ONE root. That is FALSE, and falsely reassuring: 5d1fb15 computed
    `repo = _git_toplevel(root)` on the RAW root the caller passed, while this computes it
    on the RESOLVED root `_as_roots` now returns. For an absolute root the two agree; for
    a RELATIVE one they do not, and the difference is exactly the F2 bug the `_as_roots`
    docstring above describes (`pathlib.Path(".").parents` is empty, so the ancestor walk
    stopped at the cwd and the root's second probed base silently vanished). The resolved
    input is the CORRECT one; what is wrong is the equivalence claim. TestRootContainment
    is unflipped because its roots are absolute tempdir paths, for which the two forms do
    coincide — not because the computation did not move.
    """
    allowed = []
    for r in roots:
        p = pathlib.Path(r)
        allowed.append(p.resolve())
        # SIEGE-C1 — refusals are recorded HERE, and here only, because this is the site
        # that reaches BOTH cited-name shapes. A refused toplevel is missing from the
        # containment union, and containment is tested for EVERY candidate: a relative
        # name loses `repo / name` as a candidate, and an absolute name inside that repo
        # keeps its candidate but fails `_contained` against a union the repo is no longer
        # in. Recording only from _resolve_base_one's relative branch was tried and is
        # WRONG — it left the absolute shape hard-FAILing with exactly the silent "absent
        # under all bases" the clause exists to replace.
        repo = _git_toplevel(p, refused)
        if repo:
            allowed.append(repo.resolve())
    return allowed


def _resolve_base_one(name: str, root: pathlib.Path, allowed):
    """Probe {root, repo-root-of-root, absolute-as-is} in fixed order; return the
    FIRST base where the file exists, else None. repo-root = git toplevel of `root`
    (NOT this script's checkout). Used by part-1 hash, part-2 witness read, and --strict.

    #397 containment: a candidate is read ONLY if its realpath (symlinks + `..`
    resolved) is contained under `root` or the repo toplevel. A `..`-traversal,
    an absolute-outside-root name, or an in-tree symlink whose TARGET escapes the
    tree resolves to None — never an out-of-tree disk read while linting an
    attacker-influenced receipt. (None then becomes UNVERIFIABLE, or path-shaped +
    --strict FAIL, in the callers — the same shape as a genuinely-absent file.)"""
    repo = _git_toplevel(root)   # still needed: it is a CANDIDATE base (:847-848).
    # Refusals are NOT recorded from here — _allowed_bases owns that, because it is the
    # site that reaches both name shapes (see its comment). Recording here as well would
    # only duplicate; recording here INSTEAD misses the absolute shape entirely.
    # `allowed` is now the caller's UNION over ALL roots (#486 / D2, design :290).
    cands = []
    p = pathlib.Path(name)
    if p.is_absolute():
        cands.append(p)
    else:
        cands.append(root / name)
        if repo:
            cands.append(repo / name)
    for c in cands:
        try:
            real = c.resolve()  # normalizes `..` and follows symlinks
        except (ValueError, OSError):
            # #486 fixer / F3 — the cited NAME is receipt-controlled, i.e. attacker-
            # controlled, and a receipt is an untrusted subagent return. Path.is_file()
            # swallows OSError/ValueError; Path.resolve() does NOT, so an embedded NUL
            # ("ValueError: embedded null character") or an ELOOP/ENAMETOOLONG name
            # escaped the CLI as a traceback printed AFTER the TIER2-COVERAGE: line, on
            # the stream orchestrators parse. A malformed name is simply a candidate that
            # does not exist: skip it, so it degrades to UNVERIFIABLE like any absent
            # file rather than crashing the lint.
            continue
        if not any(_contained(real, base) for base in allowed):
            continue  # containment violation — never read
        if real.is_file():
            return real
    return None


def _below_top_level(resolved, root):
    """#488 T7 — the relpath of `resolved` from the first SUPPLIED ROOT, in
    declaration order, that holds it BELOW its own top level; None when no supplied
    root does.

    Keyed on resolution DEPTH, never on which clause resolved (§3.1 clause 2): a
    clause-1 literal join of a multi-segment name that lands below a root's top level
    is this case exactly as a clause-2 walk hit would be, and one counter serves both
    so the two producer remedies stay comparable at quality-gate/SKILL.md:36.

    The quantifier is §3.1 clause 2's own: "below A ROOT's top level" — existential
    over the roots THE RUN WAS GIVEN, and over nothing else. Two things follow, and
    both are fixes for a measured bug rather than preferences.

    (1) GIT TOPLEVELS ARE NOT IN THE DEPTH KEY. They are probed BASES (`_resolve_base_one`)
    and they are in the containment union (`_allowed_bases`), but neither makes one a
    root the run was given. Admitting them lets a root that did not resolve the name
    decide how deep it is: with `--root <repo>/dispatch --root <repo>/findings` and a
    bare `round-9-findings.md` living at `<repo>/findings`'s OWN top level, `dispatch`'s
    git toplevel is `<repo>`, which sees that file two components down — so a build
    consulting derived bases fires on the one citation form this counter exists to
    distinguish §3.4 move 1's remedy FROM. A resolution that lands under NO supplied
    root (the `<git-toplevel>/name` candidate winning) has no relpath from a root at
    all, and is therefore not this clause's case; it is silent here by construction,
    which is the design's own placeholder `(<relpath-from-root>)` read literally.

    (2) NO MINIMUM, MAXIMUM OR OTHER COMPARISON ACROSS ROOTS. The first supplied root
    that sees the name below its top level answers, in DECLARATION order — the same
    order `resolve_base` already resolves in (D3). Taking a global minimum instead lets
    a second, NESTED --root zero both the note and the counter for a name that still
    resolves two components under the first root, silently, which is the failure
    direction §3.4 channel 2 exists to arrest. A root that does not CONTAIN the resolved
    path cannot change the answer either way, so no unrelated root ever participates.

    KEYED ON `resolved`, NOT ON THE CITATION — stated because it is a deliberate,
    disclosed reading and not an oversight (round-1-of-this-gate S1). `resolve_base`
    returns `c.resolve()`, i.e. symlinks followed, so a BARE BASENAME sitting at a
    root's own top level whose on-disk target is itself a symlink into a subdirectory
    DOES fire this note and bump the counter — the realpath genuinely sits below the
    root's top level, and §3.1 clause 2's "resolves to a path below a root's top
    level" is satisfied literally by that realpath. The cost: the census cannot
    tell that case apart from a genuine root-relative citation. Kept, not re-keyed.
    """
    for r in _as_roots(root):
        try:
            rel = resolved.relative_to(r)
        except ValueError:      # not under this root — PurePath op, never OSError
            continue
        if len(rel.parts) > 1:
            return rel
    return None


def _walk_note(name, rel):
    # SIEGE-R2BA-4 — BOTH the receipt-supplied name and the rendered relpath take the
    # escaper, on the same grounds as every other name on this channel (§3.1 clause 2
    # says so explicitly for this note).
    return (f"RESOLVED-BY-WALK: {_show_path(name)} "
            f"({_show_path(str(rel))})")


def _emit_walk_note(notes_out, name, rel):
    """Append the RESOLVED-BY-WALK note to `notes_out`, and NEVER raise doing it.

    #488 round-3/S1 — the SIXTH instance of the hazard class the `except
    BaseException:` arm's comment in tier2_artifacts enumerates (see there for the
    first five). Task 5 added two `notes_out.append(...)` emission sites, one per leg,
    and both are sited BEFORE the `if len(found) > 1:` ambiguity block that RAISES
    under `--strict` — the MANDATED invocation. `notes_out` is a caller-controlled
    parameter with no type enforcement (~40 call sites, all positional), so `()`, `0`,
    an object without `.append`, and an object whose `.append` raises are all ordinary
    API misuse. Measured on `8a5a1f9`, on BOTH legs, all four shapes replaced a genuine
    `Tier-2 --strict: ... absent under all bases` (artifacts) / `... is ambiguous across
    roots` (witness) LintError — the first three with `AttributeError: '<t>' object has
    no attribute 'append'`, the fourth with the object's own RuntimeError. Measured on
    `b6990c7` (pre-Task-5), same two fixtures: all four left the LintError intact on
    both legs, so this is a regression Task 5 introduced, not a pre-existing hole.

    The note is RENDERED INSIDE the envelope, not passed in already-rendered: a call's
    ARGUMENTS are evaluated BEFORE the callee is entered, and `_walk_note` runs
    `_show_path(name)` -> `str(name)` on a public-API-supplied ARTIFACTS key, which is
    the same raising-`__str__` shape the `finally:` block's own wrapper exists for. A
    helper taking a finished string would leave that half outside the guarantee.

    `Exception`, not `BaseException`: KeyboardInterrupt/SystemExit propagate. Swallowing
    is right here for the reason it is right at the two sibling wrappers — this note is
    an advisory side channel and must never preempt the verdict."""
    try:
        if notes_out is not None:
            notes_out.append(_walk_note(name, rel))
    except Exception:
        pass


def resolve_base(name: str, root, found=None, refused=None):
    """Resolve `name` against one or more roots; return the FIRST hit, else None.

    #486 / D1 — `root` is a single root (as today) or a sequence probed in DECLARATION
    ORDER. The first hit is the file that is READ (D3); this is NOT an early exit,
    because D2 needs the distinct realpaths from EVERY de-duplicated root.

    #486 / D2 — when a caller passes a mutable `found` list it is filled with the
    DISTINCT realpaths the per-root probes returned, in probe order. The RETURN TYPE
    does not move: `Path | None`, exactly as before. That is deliberate and is what
    keeps all nine direct call sites in scripts/test_rcpt_verify.py unflipped
    (a (first_hit, [realpaths]) tuple would break every assertIsNone). The callers —
    tier2_artifacts and tier2_witness — own the LintError-vs-AMBIGUOUS-note
    disposition, because `notes` is theirs to build.

    #486 / Q7 — WITHIN one root the existing root-then-repo precedence is UNTOUCHED and
    silently first-hit-wins (test_resolve_base_binds_root_first still holds), so that
    probe contributes at most one realpath. ACROSS roots the repo bases participate for
    free: root A's probe may return repoA/name and root B's B/name, and those are two
    distinct realpaths.

    Containment (#397 / C1) is the UNION of all roots and their git toplevels, not a
    per-root test — see D2 and _allowed_bases. The reachable FILE set is identical
    either way; what grows is the set of name forms that reach a given file. Per-root
    containment was rejected because it would make resolution depend on which root's
    probe produced the candidate, which is the implicitness O5 was rejected for.
    """
    roots = _as_roots(root)
    allowed = _allowed_bases(roots, refused)
    first = None
    for r in roots:
        hit = _resolve_base_one(name, r, allowed)
        if hit is None:
            continue
        if first is None:
            first = hit
        if found is not None and hit not in found:
            found.append(hit)
    return first


def _contained(child: pathlib.Path, base: pathlib.Path) -> bool:
    """True iff resolved `child` is `base` itself or lies beneath it. Both paths
    must already be realpath-resolved by the caller (resolve_base does so)."""
    return child == base or base in child.parents


def _is_git_marker(g: pathlib.Path) -> bool:
    """SIEGE-C1 — is `g` a REAL `.git` marker, or an entry that merely bears the name?

    The predicate here used to be a bare `.exists()`. That was DELIBERATE and its
    rationale is retained in full: a git WORKTREE (and a submodule) has `.git` as a
    *FILE* — a gitlink — not a directory, so `.is_dir()` would break those and is still
    the wrong tightening. What `.exists()` also accepted was ANY entry named `.git`,
    including a zero-byte file, and `_git_toplevel` walks EVERY ancestor of every
    supplied root: `: > /tmp/.git` (mode 1777, the parent of every live
    `<dispatch-root>`) therefore made `/tmp` both a probed base AND a member of the
    `_allowed_bases` containment union for every root, so a decoy planted there was
    hashed, predicate-checked and rendered `artifacts 1/1`, exit 0.

    Validating the SHAPE costs one read and closes the accidental/zero-byte plant in
    both forms: a `.git` DIRECTORY must hold the three entries every git dir has
    (`HEAD`, `objects/`, `refs/` — `git init` creates all three, and so does every
    worktree's real gitdir), and a `.git` FILE has the fixed gitlink form
    `gitdir: <path>`. Symlinks are followed, as before.
    """
    try:
        if g.is_dir():
            return ((g / "HEAD").is_file() and (g / "objects").is_dir()
                    and (g / "refs").is_dir())
        if g.is_file():
            with g.open("rb") as fh:
                return fh.read(8) == b"gitdir: "
    except OSError:
        return False              # unreadable is not a marker — fail closed
    return False


def _git_toplevel(start: pathlib.Path, refused=None):
    d = start if start.is_dir() else start.parent
    for cur in [d, *d.parents]:
        # SIEGE-C1 — shape-valid AND not world-writable. The shape check alone does not
        # close the /tmp plant: `mkdir -p /tmp/.git/{objects,refs} && : > /tmp/.git/HEAD`
        # is as cheap for any local uid as the zero-byte file was. What closes it is
        # refusing a toplevel ANY uid can plant into; the cost is that a repository
        # checked out into a world-writable directory stops contributing its toplevel as
        # a probed base — a shape that is itself insecure and absent from this repo and
        # from CI (both 0755). STATE THAT COST HONESTLY: it degrades to UNVERIFIABLE only
        # for a bare basename, or with --strict off. For a repo-relative PATH-SHAPED name
        # under the MANDATED --strict it is a hard FAIL, i.e. a structural BLOCK on every
        # receipt of the run — fail-closed and correct, but it must be diagnosable, which
        # is what `refused` and _refused_clause are for. Skipped rather than aborted, so
        # a legitimate repo further up still
        # wins (siege S-3: it no longer does — see the refusal arm below).
        #
        # It does NOT close a same-uid plant such as `~/.git` (mode 0700), and the
        # reason this comment used to give for tolerating it was FALSE — corrected here
        # rather than left for the next maintainer to act on: "a subagent that can write
        # there can equally write the decoy into a root it already owns, so that plant
        # buys an attacker nothing this linter can withhold". It buys two things. An
        # in-root SYMLINK to an out-of-tree target is refused by `_contained`; the plant
        # is not, because it WIDENS the containment union itself, so a decoy under $HOME
        # that neither supplied root holds becomes verifiable as the cited artifact. And
        # the widened union reaches other runs' scratch directories, i.e. sibling
        # dispatches this subagent is not party to. RESIDUAL, stated and not closed: the
        # remedy is a rule about WHICH ancestors may contribute a toplevel at all, which
        # is a design change to the probe set (quality-gate/SKILL.md:30 defines it as
        # "each supplied root plus that root's git toplevel") and not a linter-local fix.
        if _is_git_marker(cur / ".git"):
            if not _is_world_writable(cur):
                return cur
            # `refused` is an optional out-param (the same idiom as found/cov/probe/
            # meter/bodies): the refusal must be REPORTABLE, not merely silent. Dropping
            # this base is what makes a repo-relative name resolve nowhere, and under the
            # MANDATED --strict a path-shaped name that resolves nowhere is a hard FAIL —
            # so in a world-writable checkout the refusal blocks every receipt of the run
            # while stderr says only "absent under all bases", of a file that is present
            # and readable. The disposition appends the real reason instead.
            if refused is not None and cur not in refused:
                refused.append(cur)
            # siege S-3 — and STOP. This used to KEEP WALKING, on the reasoning that "a
            # legitimate repo further up still wins". Measured, that reasoning INVERTED
            # the containment guarantee: the ancestor toplevel a continued walk finds is
            # strictly BROADER than the refused one, so the same receipt against the same
            # roots resolved a `../../credentials` traversal at `artifacts 1/1 witness 1/1`
            # exit 0 with the checkout at 0777, and hard-FAILed at exit 1 with it at 0755.
            # Making a directory LESS secure made the linter reach MORE files, which is
            # the opposite of what SIEGE-C1 was written to do — and SIEGE-C1's own
            # docstring claimed the cost was "stops contributing its toplevel" when the
            # measured cost was "contributes its GRANDPARENT's".
            #
            # Refusing terminally is monotone: a refusal can now only ever SHRINK the
            # probe set and the containment union, never grow it. The cost is the one
            # SIEGE-C1 already declared and priced (a checkout under a world-writable
            # directory stops contributing a toplevel) — no longer silently swapped for a
            # wider one. `refused` still records what was dropped, so the disposition and
            # the standalone REFUSED: note can name it.
            return None
    return None   # stdlib-only: walk for .git rather than shelling out to git


def _is_world_writable(d: pathlib.Path) -> bool:
    """SIEGE-C1 — writable by someone other than its owner, on the directory that HOLDS
    the `.git` marker, i.e. "a uid that is not this one could have created this marker".
    Raw mode bits rather than an `import stat` for two bits; the sticky bit is irrelevant
    here (it restrains deletion, not creation). An unstattable directory is treated as
    writable — fail closed.

    siege S-3 — the mask was `0o002` (other) ALONE while this function's callers, and
    `quality-gate/SKILL.md` § "Dispatch-root and findings-root layout (#486)" pin (b)
    ("Single home"), both claim the property "any local uid could have planted a marker
    there". (C1-R2-S8 — cited by SECTION, not by line: this branch's own edits moved the
    line these comments named, and a stale number points at unrelated prose.) 0775 and 0770 are exactly that claim's case and were ACCEPTED. The
    mask is now `0o022`, so group-writable is refused too and the name matches what is
    tested. Group membership is narrower than "any local uid", which is why this is
    fail-CLOSED rather than an equivalence.

    NOT covered, stated so the next reader does not assume it is: POSIX ACLs and
    filesystem-specific permission models. `stat().st_mode` cannot see them, the stdlib
    has no portable reader, and this module is stdlib-only — so an ACL-writable directory
    with owner-only mode bits still contributes its toplevel."""
    try:
        return bool(d.stat().st_mode & 0o022)
    except OSError:
        return True


# SIEGE-C2 — the ONE renderer for a filesystem path interpolated into stderr.
# stderr is a PARSED channel (return-convention.md § "TIER2-COVERAGE:"; the documented
# consumer greps it line-wise, and `grep -m1` takes the FIRST match), and unlike an
# ARTIFACTS/witness name — which is whitespace-split out of the receipt and therefore
# cannot hold a newline — a RESOLVED path can hold one: the reviewed subagent creates
# directories under a root it owns, so `mkdir "$ROOT/$(printf 'ev\nTIER2-COVERAGE: …')"`
# plus a cited symlink put a forged census line on the channel ahead of the real one.
# Escaping is line-integrity only: `\` and every escaped control character become a
# literal two-character escape, so an ordinary path renders BYTE-IDENTICALLY to what it
# did before and only a hostile one changes. Deliberately NOT applied to the census line
# itself, which carries no paths at all — that machine-independence is pinned by
# return-convention.md:271.
#
# SIEGE-R2BA-4 — the class was `[\\\x00-\x1f\x7f]`, which is the class for a `grep`
# consumer and NOT the class for the consumers this channel actually has:
# quality-gate/SKILL.md § "Coverage-line capture (#486)" (under How It Works step 6)
# records "the `TIER2-COVERAGE:` line verbatim" into a durable
# file read by an LLM, and every Python consumer splits with str.splitlines(). THAT
# splits on more separators than \n/\r — \x0b \x0c \x1c \x1d \x1e \x85 U+2028 U+2029 —
# and the last three were OUTSIDE the class, so a directory tree whose components spell a
# census line and which is bracketed by U+2028 (the `/` in `artifacts 9/9` supplied by
# real path separators) put a byte-identical forged census line on the channel AHEAD of
# the real one, reachable with one `mkdir` plus a cited symlink to a non-UTF-8 file. The
# class is now every str.splitlines() separator plus the whole C1 range (\x80-\x9f, which
# contains \x85 and whose neighbours are terminal control introducers in their own right).
#
# C1-R1-S2 \u2014 escaping the separators is line-integrity only, and line integrity is NOT
# the property the DOCUMENTED consumer keys on. The consumer this channel is specified
# against is `grep -m1 'TIER2-COVERAGE:'` (the comment above says so in those words), and
# `grep` matches a SUBSTRING, not a line: a forged census sitting INSIDE an earlier
# bullet is taken as the first match while every separator in the path is faithfully
# escaped. Path components may hold spaces (a receipt-supplied NAME may not \u2014 it is
# whitespace-split \u2014 but a RESOLVED path reached through a cited symlink may) and the
# `/` of `artifacts 1/1` is supplied by real path separators, so one `mkdir` plus a cited
# symlink put a byte-identical forged census AHEAD of the real one at exit 0.
# Neutralising the TOKEN (rather than escaping the space, which would change how every
# ordinary path with a space in it renders) makes the forged text unreachable by
# substring while leaving every path that does not spell the census marker byte-identical.
# The replacement is in the SAME escape vocabulary the renderer already uses, so a reader
# still sees what the path said.
_CENSUS_TOKEN = "TIER2-COVERAGE:"
_CENSUS_TOKEN_NEUTERED = "TIER2\\x2dCOVERAGE:"
_PATH_ESCAPES = {"\\": r"\\", "\n": r"\n", "\r": r"\r", "\t": r"\t"}
_PATH_UNSAFE_RE = re.compile("[\\\\\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _show_path(p) -> str:
    """Render `p` for the stderr channel with line-breaking and non-printable characters
    escaped. See _PATH_ESCAPES above for why.

    SIEGE-R2BA-4 — `p` is a resolved PATH or a receipt-supplied NAME. The name half was
    left out at 5a215f7 on the reasoning that a name is whitespace-split out of the
    receipt and so cannot break a line. That reasoning is sound FOR LINE-BREAKING —
    str.split()'s whitespace class covers every str.splitlines() separator — and it is
    the wrong bound for the threat: a name can still carry a NUL (`UNVERIFIABLE:
    f\\x00.txt (no file under root)` put a raw NUL on the channel) and an ANSI escape
    sequence (`\\x1b[…` renders as terminal control in the durable file a human reads).
    Applied to interpolated NAMES, i.e. bare artifact/witness names. Deliberately NOT
    applied to whole `args`/payload/predicate strings (`{entry['args']}`,
    `{args_str}`, a `pattern=` source): a backslash is ORDINARY there, so doubling it
    would change the rendering of in-spec receipts, which is the one thing this renderer
    promises not to do. Those are a distinct escaping problem, not this one.

    Ordinals above U+00FF render `\\uXXXX`, not `\\xXX` — `"\\x%02x" % 0x2028` is `\\x2028`,
    which reads as `\\x20` followed by `28` and would be a second forgery primitive.

    C1-R1-S2 — the census TOKEN is neutered AFTER the escape pass (never before: escaping
    the replacement's own backslash would undo it). See _CENSUS_TOKEN for why the
    substring, and not only the line, is the thing that has to be unforgeable."""
    return (_PATH_UNSAFE_RE.sub(_escape_unsafe, str(p))
            .replace(_CENSUS_TOKEN, _CENSUS_TOKEN_NEUTERED))


def _escape_unsafe(m) -> str:
    ch = m.group(0)
    if ch in _PATH_ESCAPES:
        return _PATH_ESCAPES[ch]
    o = ord(ch)
    return "\\x%02x" % o if o < 0x100 else "\\u%04x" % o


def _show_diag(text) -> str:
    """C1-R2-S2 — neuter the census token on the DIAGNOSTIC channel (LintError bullets and
    UNVERIFIABLE/REFUSED notes), which is the OTHER half of the substring contract
    `TestTheCensusTokenCannotBeForgedBySubstring` asserts by name.

    C1-R1-S2 closed the forgery inside a rendered PATH. `_show_path` is deliberately not
    applied to whole `args`/payload/predicate strings (a backslash is ordinary there), and
    several Tier-1 diagnostics interpolate receipt-authored text RAW — `f"{entry['verb']}
    missing sha256: {entry['args']}"`, the DISPATCHED sibling, check_exec_range_bound,
    check_span_bound. A TRACE line's `args` is unrestricted single-line receipt text, which
    is all a substring consumer needs: a receipt rejected at Tier-1, having verified
    NOTHING, handed `grep -m1 'TIER2-COVERAGE:'` a fully attacker-authored
    `artifacts 9/9 witness 9/9` with all six sub-counts at zero, ahead of the real
    `not-reached (tier1-reject)` line. The verdict was safe (exit 1 ⇒ structurally
    BLOCKED); the RECORD was not, and quality-gate/SKILL.md captures this line verbatim
    into a durable per-dispatch file that #486's own headline figure is measured from.

    Applied at the WRITE SITES rather than to 40 f-strings: this covers every current and
    future raw interpolation into a bullet or a note at one place. It cannot change the
    rendering of any in-spec run — no legitimate diagnostic contains the census token, and
    a token that arrived via `_show_path` is already neutered, so this is a no-op on it.
    Deliberately NOT applied to the census line itself, nor to the usage banner."""
    return str(text).replace(_CENSUS_TOKEN, _CENSUS_TOKEN_NEUTERED)


def is_path_shaped(name: str) -> bool:
    """True if name carries a path separator or is absolute (a 'concrete path');
    False for a bare basename. The --strict FAIL-vs-UNVERIFIABLE discriminator.
    Intentionally POSIX-`/`-only (committed-corpus shape space)."""
    return ("/" in name) or pathlib.Path(name).is_absolute()


def _unresolved_disposition(name, strict, cov, witness_leg=False, refused=None):
    """#486 fixer / F4 — the ONE disposition for a cited name that `resolve_base`
    returned None for. Returns the note to append; raises LintError on the --strict
    path-shaped FAIL.

    resolve_base deliberately returns `Path | None` and hands the disposition to its two
    consumers "because `notes` is theirs to build" — and owning it twice is exactly what
    produced the divergence this helper closes: tier2_artifacts had the D8.3 arm ruling a
    bare 12-hex receipt-hash prefix "not a file", tier2_witness had none, so ONE name in
    ONE run was billed `not-applicable (receipt-hash-prefix)` by the artifacts leg and
    `not-reachable (unresolvable-basename)` by the witness leg, with two contradictory
    stderr notes. It is reachable in practice: a RANGELESS grep payload carries no
    ARTIFACTS-membership rule, so the witness leg's art_name comes from the cited TRACE
    entry, and a `READ <12-hex>` of a superseded receipt is the SUPERSEDES justification
    form the convention describes. It matters because `not-reachable` is the bucket an
    operator reads as "a root is mis-pointed" and the counter #488's proposed --strict
    floor consumes — inflated by a name the linter itself has ruled is not a file.

    D8.3's ORDERING RULING is preserved by the call sites, not by this helper: both call
    it only AFTER resolve_base returned None, never as a pre-resolution shortcut (a
    pre-resolution `continue` would skip the sha256 recomputation for a 12-hex entry that
    DOES resolve, turning a shipped hard FAIL on mismatch into exit 0 plus an advisory
    note saying the opposite of the truth).

    Applicability bookkeeping lives HERE so the two legs cannot drift again: a 12-hex
    prefix is kept OUT of the applicable set on BOTH legs (the artifacts leg never
    increments art_applicable for it; the witness leg clears the wit_applicable it
    optimistically set before resolution), and every other unresolved name IS applicable
    on both. The unreached/not-reachable split is D8.3's SYNTACTIC approximation — no new
    disk surface; the split is ADVISORY and conservative, the SUM is exact, and any future
    rule reading the two SEPARATELY breaks that invariance.
    """
    # SIEGE-R2BA-4 — the NAME is receipt-supplied and lands on the parsed channel, so it
    # takes the same renderer a resolved path does. Only the RENDERING is escaped: every
    # predicate below (the 12-hex test, is_path_shaped) still reads the raw name.
    label = f"witness {_show_path(name)}" if witness_leg else _show_path(name)
    if re.fullmatch(r"[0-9a-f]{12}", name):
        if cov is not None:
            if witness_leg:
                cov.wit_applicable = 0
            cov.bump("not-applicable", "receipt-hash-prefix")
        # #486 / S6 — NOT SILENT. D8.3 pins the census BUCKET; it does not pin silence,
        # and a declared entry that is neither verified nor mentioned anywhere on stderr
        # is the fail-open shape, on a predicate the RECEIPT controls.
        return f"NOT-APPLICABLE: {label} (12-hex receipt-hash prefix, not a file)"
    if cov is not None:
        if not witness_leg:
            cov.art_applicable += 1
        if is_path_shaped(name):
            cov.bump("unreached")
        else:
            cov.bump("not-reachable", "unresolvable-basename")
    if strict and is_path_shaped(name):
        if cov is not None:
            cov.partial = True     # remaining entries + the other leg uncounted
        # The two messages differ verbatim ("path-shaped artifact …" vs "witness artifact
        # …") because they already did, and message fidelity is load-bearing for the
        # --eval byte-diff.
        noun = "witness artifact" if witness_leg else "path-shaped artifact"
        raise LintError(
            f"Tier-2 --strict: {noun} {_show_path(name)} absent under all bases"
            f"{_refused_clause(refused)}")
    return f"UNVERIFIABLE: {label} (no file under root){_refused_clause(refused)}"


def _refused_clause(refused):
    """SIEGE-C1 — the suffix naming a probe base that was DROPPED rather than absent.

    A world-writable git toplevel is refused as a probe base, so a repo-relative name
    resolves nowhere and (path-shaped, under the mandated --strict) hard-FAILs. Without
    this the operator is told the artifact is "absent under all bases" for a file that is
    present and readable, with nothing on stderr mentioning permissions — so a checkout in
    a 0777 directory (routine for WSL drvfs mounts, `chmod -R 777` devcontainers, and
    umask-000 container clones) blocks every receipt citing such a name, with a false
    diagnosis. Blocks, precisely: a PATH-SHAPED name hard-FAILs under --strict; a bare
    basename stays UNVERIFIABLE at exit 0. The clause is appended on both dispositions,
    since the operator needs the reason either way.

    It reaches BOTH cited-name shapes because the refusal is recorded in `_allowed_bases`:
    a relative name loses `repo / name` as a candidate, and an absolute name inside the
    refused repo keeps its candidate but fails `_contained` against a union the repo is no
    longer in. Recording from `_resolve_base_one`'s relative branch alone left the
    absolute shape silent.

    A SUFFIX, and empty when nothing was refused: the existing message prefixes are
    byte-identical on every run that refuses no base, which is what keeps --eval's
    byte-diff and the message-fidelity contract above intact.

    The refusal itself is NOT relaxed and the exit code does NOT move. Degrading these to
    UNVERIFIABLE instead would let anyone able to chmod a checkout's parent silently
    disable path-shaped verification — strictly worse than a loud, diagnosable block.
    What was wrong was the silence, not the refusal."""
    if not refused:
        return ""
    homes = ", ".join(sorted(_show_path(d) for d in refused))
    return (f" [refused as probe base: world-writable git toplevel {homes} — "
            f"any local uid can plant a marker there; make it non-world-writable]")


# SIEGE-R2BA-2 — the ceiling on how many bytes ONE Tier-2 leg will materialise from
# receipt-NAMED files. Chosen deliberately, and the two halves of the choice are separate:
#
# WHY A CEILING AT ALL. Every read on this path is of a file whose name the receipt
# supplies and whose contents live under a root the reviewed subagent owns, and the
# ARTIFACTS leg runs OUTSIDE _witness_bound() — it has no timeout of any kind. A 4 GiB
# SPARSE file (`truncate -s 4G`, zero bytes on disk, instant to create) drove
# `Maximum resident set size` to 4,225,380 kB in 2.32 s through the old bare
# `resolved.read_bytes()`; a 12 GiB one completed in 1.87 s, so even the WITNESS leg's
# 5 s bound admits tens of GiB. Under `ulimit -v` the resulting MemoryError is NOT an
# OSError, escaped the `except OSError` guard, and printed a Traceback AFTER the
# TIER2-COVERAGE: line — the exact shape the F3 read guards exist to eliminate. The
# declared `<size>` field is parsed and explicitly NOT validated, so it is no defence.
# Denying the linter is a security outcome and not merely a robustness one: the skills'
# only documented remedy for a linter that does not work is the in-context pseudocode
# fallback, which performs ZERO disk verification.
#
# WHY 64 MiB. It must not false-reject a legitimate artifact — findings files, build
# logs, diffs. Measured on this corpus: the largest artifact under
# eval/ledger-return-protocol/ is 24 KB (_gen.py) and the largest file tracked anywhere
# in this repo is 223 KB (scripts/test_rcpt_verify.py), so 64 MiB is ~290x the biggest
# file this repo contains and ~2,800x the biggest thing the receipt corpus ever cites.
# Reading and hashing 64 MiB costs ~0.2 s and 64 MiB of transient RSS, which is a bound
# a linter can afford; 4 GiB is not. An over-cap artifact fails CLOSED with a classified
# bullet (never a silent skip) — see tier2_artifacts.
#
# The budget is CUMULATIVE across the ARTIFACTS leg, not per entry: the number of
# declared entries is receipt-controlled and unbounded, so a per-entry cap still admits
# N x 64 MiB of unbounded-time reads on the leg that has no timeout. It is also what
# bounds the SIEGE-R2BA-1 carry (`bodies`), whose peak is this same budget however many
# entries the receipt declares.
ARTIFACT_READ_CAP = 64 * 1024 * 1024


def _strerror(e: BaseException) -> str:
    """SIEGE-R2BA-2 — the human half of a failed read, for OSError AND its new
    non-OSError sibling. `e.strerror or e` was fine while the caught set was OSError
    alone; a bare `MemoryError()` has no `strerror` (AttributeError) and stringifies to
    the EMPTY string, which would render the bullet as `unreadable ()` — a diagnostic
    that names nothing on the one channel an orchestrator records verbatim."""
    return getattr(e, "strerror", None) or str(e) or type(e).__name__


def _read_capped(path: pathlib.Path, budget: int, label: str) -> bytes:
    """SIEGE-R2BA-2 — read `path` whole, with a HARD ceiling, race-free.

    Reads at most `budget`+1 bytes and raises when it got them all, so the ceiling holds
    however the file GROWS between the check and the read. An `st_size` pre-test — the
    obvious primitive — does not: the file lives in a directory the reviewed subagent
    owns, so stat-then-read is a window it can drive, and this way there is no window at
    all. `budget` is what REMAINS of ARTIFACT_READ_CAP, so the message names both.

    OSError propagates unchanged: every caller already classifies it (and MemoryError
    beside it), and their bullets differ verbatim."""
    with path.open("rb") as fh:
        raw = fh.read(budget + 1)
    if len(raw) > budget:
        raise LintError(
            f"Tier-2: {label} exceeds the Tier-2 read budget "
            f"({budget} B remaining of {ARTIFACT_READ_CAP} B; not read)")
    return raw


# #488 inquisitor/AV4 (edge) — a KNOWN, DELIBERATELY OUT-OF-SCOPE GAP, recorded here so
# it is not "fixed" by accident. `parse_trace` admits SEVEN verbs; this set holds three.
# `return-convention.md:84` defines `CONSULTED <reference>` as covering "web/doc/
# prior-artifact lookup", and a cited PRIOR ARTIFACT is exactly the population §3.4's
# silence rule ranges over — so a `CONSULTED` citation of an undeclared, unverified file
# gets no PROVENANCE-ONLY advisory at all, on an ORDINARY receipt and not only under
# attack. That is a real hole in the advisory's coverage and it is left OPEN.
#
# NOT a code bug: the frozen design doc scopes §3.4 to READ/EDIT/WROTE explicitly
# throughout, so the code matches its own ruling and the gap is in the RULING's scope.
# Adding `CONSULTED` here would make the code diverge from the design doc it implements,
# and it would do so at a measurable price the doc costs elsewhere — `CONSULTED`
# references are frequently URLs and other non-file strings, so the advisory's note
# volume (the thing §3.4 trades against silence) would move on receipts that name no
# file at all. Widening the verb set is a RULING AMENDMENT, not a fix; until one is made,
# `TestTheAdvisoryScopeIsDeliberatelyNarrowerThanTheTraceVerbSet` in
# scripts/test_488_name_space.py pins the CURRENT narrower behaviour as intentional.
_PROVENANCE_VERBS = frozenset({"READ", "EDIT", "WROTE"})

# #488 temper/leg-1 — the basenames that are NOT a usable key for the PROVENANCE-ONLY
# basename match. `rsplit("/", 1)[-1]` is not a basename function: it is a string split,
# and three legal ARTIFACTS spellings drive it to a value that names no file —
# `x/` -> "", `x/.` -> ".", `x/..` -> "..". F4 hardened only the "" symptom, with a
# TRUTHINESS test. `.` and `..` are truthy, so they still key `verified_bases` /
# `unevaluated_bases`, and each silences a whole family of unrelated TRACE names.
#
# Measured on 5e1b6df, four arms, one harness (`q` is a REAL file the receipt never
# declares and the run never verifies; ARTIFACTS holds a genuinely hash-verified entry):
#
#   ARTIFACTS `x`    TRACE READ `q`     -> PROVENANCE-ONLY: q      artifacts 1/1  EXIT=0
#   ARTIFACTS `x/.`  TRACE READ `q/.`   -> (SILENT)                artifacts 1/1  EXIT=0
#   ARTIFACTS `x/.`  TRACE READ `q`     -> PROVENANCE-ONLY: q      artifacts 1/1  EXIT=0
#   ARTIFACTS `x`    TRACE READ `q/.`   -> PROVENANCE-ONLY: q/.    artifacts 1/1  EXIT=0
#
# Rows 1/3/4 are the non-vacuity controls: row 2's silence is caused by the `.` key and
# by nothing else. `x/.` is legal under §3's lexical grammar (`.` is not `..`), resolves,
# and hash-verifies, so the receipt looks immaculate — and one extra character in the
# author's OWN ARTIFACTS spelling buys silence on arbitrarily many undeclared reads.
# That is silence a receipt author can buy, which is the direction grudge e0f0a6b75692
# forbids and which _emit_provenance_notes's own F3 paragraph names as the failure the
# exact-name override exists to prevent.
#
# `..` is reachable through `unevaluated_bases` even though it is not through
# `verified_bases`: a declared `x/..` resolves to a DIRECTORY and so never hash-verifies,
# but a run truncated before reaching it puts `".."` into the unevaluated set, which keys
# the same match.
#
# ACCEPTED COST, stated because this widening BUYS it and nothing else records it. The
# degenerate key was also, coincidentally, the only thing bridging §3.2's two spellings
# for a `/.`-suffixed name: `ARTIFACTS x/.` (verified) cited in TRACE by the absolute form
# §3.2 mandates was SILENT before, because both sides split to `.`. It now emits a note
# for an artifact that genuinely verified. That is cry-wolf on an advisory channel — the
# FAIL-NOISY direction — and it is the side of the trade this emitter's docstring already
# rules for: the alternative is silence a receipt author buys by spelling their own
# ARTIFACTS entry with a `/.` suffix, which is grudge e0f0a6b75692's direction. It needs
# a degenerate spelling in the author's OWN declaration to arise at all; the ordinary
# `ARTIFACTS x` + absolute-form TRACE control is untouched. It is the same trade F4 made
# for `x/`, extended to the two spellings F4's truthiness test missed. Not closed by a
# more specific key: the docstring's first bullet measures 13 verified entries mislabelled
# when the key is narrowed past basename, which is a strictly worse exchange.
_DEGENERATE_BASES = frozenset({"", ".", ".."})


def _trace_basename(entry):
    """The name a TRACE entry cites, and its basename. The name is the FIRST token of
    the entry's `args` — the field is receipt-authored and unconstrained (§3: `TRACE`
    may name anything, and AC-2's Tier-1 grammar binds `ARTIFACTS` only), so nothing
    here may assume path shape. `rsplit("/")` rather than `pathlib`: this is a string
    operation on the LEAST-constrained receipt-controlled string in the grammar, and it
    must not acquire path semantics (or an exception) on a hostile name.

    #488 adversarial/F1 — a MALFORMED entry returns `("", "")` rather than raising.
    This is the THIRD instance of the `finally:`-block masking hazard the `trace or []`
    and `str(n)` guards already close: this helper runs from tier2_artifacts's
    `finally:`, so `entry["args"]` on an entry that is not a `{"verb": ..., "args":
    str}` dict raises KeyError/TypeError/AttributeError right there and REPLACES the
    in-flight exception — a genuine `Tier-2 --strict: ... absent under all bases`
    LintError would be destroyed and reported as the shape error instead. The
    reachability argument is the one those two guards make verbatim: `trace` is
    public-API-supplied (~40 direct call sites, no type enforcement), and a caller who
    can pass `None` can pass `[None]`. `("", "")` routes a malformed entry into the
    caller's existing `if not name: continue` arm — "not a match", never a crash — which
    is the same disposition an empty `args` already takes. That ordering is the point:
    these notes are an advisory side channel and must never preempt the verdict."""
    args = entry.get("args") if isinstance(entry, dict) else None
    if not isinstance(args, str):
        return "", ""
    tokens = args.split()
    name = tokens[0] if tokens else ""
    return name, name.rsplit("/", 1)[-1]


def _declared_spellings(names, roots, resolutions):
    """#488 inquisitor/AV1 (edge) — every spelling of a DECLARED ARTIFACTS name that a
    conformant TRACE entry may cite it by, for the three exact-name sets
    _emit_provenance_notes tests.

    The three sets used to hold the BARE DECLARED name only, and §3.2 makes that the
    wrong key on its own: a tracked repo file's TRACE citation is MANDATED to carry its
    ABSOLUTE path, while §3.1 mandates the ARTIFACTS declaration be POSIX-RELATIVE. The
    two legs therefore spell one real file differently BY RULING, and an override keyed
    on one spelling simply never fires for the other. Measured on the honest shape (a
    declared, evaluated, UNVERIFIED `b/x.md` cited in TRACE by the ruling's own absolute
    form, beside an unrelated verified `a/x.md`): the run printed
    `UNVERIFIABLE: b/x.md (no file under root)` and stayed SILENT about the TRACE entry
    citing that same file, because `x.md` was already in `verified_bases` — silence a
    receipt author buys with one extra ARTIFACTS line, grudge e0f0a6b75692's direction
    and the exact failure the override exists to close.

    THREE spellings per name, and the first two are not interchangeable:
      * the DECLARED name verbatim — the §3.1 form, and the only one available for a
        name that never resolved;
      * `<root>/<name>` for each supplied root, derived LEXICALLY (string concatenation,
        no disk), and SCREENED by `_DEGENERATE_BASES` (see the join). Lexical is
        load-bearing rather than lazy: the population this closes is dominated by names
        that do NOT resolve — `b/x.md` above is absent from every root, so there is no
        realpath to project, and the resolved-path spelling alone would leave the
        measured case exactly as it was. `roots` carries BOTH the resolved root tokens
        and the as-supplied ones (#488 warden-r2/F3 widens them at the call site), so
        the join covers the §3.2 spelling a receipt written against a SYMLINKED root
        actually uses — the resolved one alone did not;
      * the RESOLVED realpath, when this run recorded one. This is the spelling the
        lexical join CANNOT produce: a name that resolved through a git toplevel rather
        than a root, or through a symlink BELOW the root, lands somewhere no root-join
        names. (A symlinked ROOT is not an instance of that — `_as_roots` resolves it
        before the join, so the join already produces the realpath spelling there and it
        was the AS-SUPPLIED one that was missing, which is the direction F3 corrects.)

    ADDITIVE ONLY, which is what makes it safe in the fail-noisy direction the emitter
    rules for: every set keeps its bare spelling, so no note that was emitted before
    stops being emitted, and no suppression that was correct before is lost. What moves
    is that a citation using the OTHER mandated spelling now reaches the same
    exact-name test its bare twin already reached.

    Residual, stated rather than left to be found: a name whose declared spelling ends
    in `/` (or `/.`) contributes NO joined spelling at all, so the two spellings of THAT
    family meet only at the bare key. That is true BECAUSE THE JOIN IS SCREENED, not
    because the join structurally could not produce the absolute form — it can, and
    unscreened it did, which is the #488 warden-r2/F4 hole: the manufactured spelling let
    a hash-verified degenerate declaration suppress an unrelated cross-root citation
    through the fail-silent sets. These are the same degenerate spellings
    `_DEGENERATE_BASES` exists for, and the screen leaves them exactly the bare-name leg
    `_DEGENERATE_BASES` was added to give them.

    MUST NOT RAISE (#488 round-3/S1): its result feeds tier2_artifacts's `finally:`,
    where any exception REPLACES the in-flight one. `str()` on an arbitrary ARTIFACTS
    key can raise, so each name is projected under its own guard and a name that cannot
    be rendered simply contributes no spellings — never a crash, and never a note the
    real verdict is replaced by."""
    out = set()
    for n in names:
        try:
            s = str(n)
            out.add(s)
            resolved = resolutions.get(n)
            if resolved is not None:
                out.add(str(resolved))
            # #488 warden-r2/F4 — the join is SCREENED by `_DEGENERATE_BASES`. It widens
            # all three sets uniformly, two of which (`unevaluated_names`,
            # `verified_names`) are fail-SILENT suppressors. For a non-degenerate name
            # that is inert — the basename leg already covers it — but for a DEGENERATE
            # one (`x/`, `x/.`) the join manufactured an absolute spelling that let one
            # hash-verified degenerate declaration buy silence for a completely different,
            # unverified cross-root citation: leg-1's silence-via-degenerate-declaration
            # hole, reopened through the exact-name leg instead of the basename leg it was
            # closed on. Screening by degeneracy is preferred over restricting the
            # widening to `unverified_names` alone, because the join is already inert for
            # non-degenerate names in the silent sets — so this is the smaller change and
            # it does not touch the override's own coverage at all.
            #
            # ACCEPTED RESIDUAL: this restores leg-1's cry-wolf for the narrow case of a
            # verified degenerate name cited by its OWN root's absolute form (`ARTIFACTS
            # x/` verified under `/dispatch`, `TRACE READ /dispatch/x/` → a false
            # PROVENANCE-ONLY note again, matching pre-4a11bcf behaviour). That is the
            # fail-noisy side of the trade `_emit_provenance_notes` already rules on
            # ("fail-noisy on a spelling tie"), and it is cheaper to accept than the code
            # needed to avoid it.
            if (not s.startswith("/")
                    and s.rsplit("/", 1)[-1] not in _DEGENERATE_BASES):
                for base in roots:
                    out.add(f"{base}/{s}")
        except Exception:
            continue
    return out


def _emit_provenance_notes(trace, verified_bases, unevaluated_bases,
                           unevaluated_names, unverified_names, notes_out,
                           verified_names=frozenset()):
    """§3.4 / T2 — silence is not permitted (grudge e0f0a6b75692).

    One note per READ/EDIT/WROTE entry whose BASENAME matches no ARTIFACTS basename
    that Tier-2 RESOLVED AND HASH-VERIFIED. All three verbs, because scoping to
    EDIT/WROTE exempts the one declaration §1.1 quotes as the filed contradiction and
    turns two measured hard-FAILs (corpus17/rcpt-18, live29/rcpt-22, both READ-only)
    into silence. The four OTHER verbs `parse_trace` admits are OUT OF SCOPE
    DELIBERATELY and not by oversight — `CONSULTED` most consequentially, because its
    own definition names prior-artifact lookup; see `_PROVENANCE_VERBS` for why that gap
    is a ruling amendment rather than a fix.

    The key is the VERIFIED basename set. Both obvious alternatives are wrong in
    opposite directions, and the basename key itself has a THIRD, opposite cost that is
    the reason those two are not the whole tradeoff (round-1-of-this-gate S2):
      * the literal `parts[0]` string mislabels 13 verified entries across the three
        frozen corpora, because §3.2 mandates DIFFERENT name forms by design (absolute
        in TRACE, bare in ARTIFACTS);
      * the verified-BLIND basename key suppresses 61 (flat) / 79 (nested) TRUE
        advisories, which is the grudge re-entering through the clause written to
        close it;
      * the basename key ITSELF is silent on a SAME-BASENAME DIFFERENT-FILE collision: a
        TRACE entry naming a genuinely different file whose basename happens to match a
        verified ARTIFACTS basename emits nothing, exactly as if the two names had
        named the same file. `quality-gate/SKILL.md` makes such collisions structural
        rather than hypothetical — per-chunk `chunk-N/round-N-findings.md` and
        per-chunk `fix-journal.md` both guarantee sibling chunks share a basename — so
        this is not a corner case invented for this docstring. It is accepted, not
        fixed, because keying on anything more specific than basename re-opens the
        first bullet's mislabeling (§3.2's two legs spell one real file DIFFERENTLY
        by design, so a more specific key would call verified files unverified); its
        rate on live corpora is not measured, unlike the first two bullets' figures,
        so it should be read as unknown rather than as small.

    `unverified_names` is the EXACT-NAME OVERRIDE on that third bullet (#488
    adversarial/F3), and it closes the one slice of the collision that is CHOSEN rather
    than coincidental. Held as declared FULL NAMES (not basenames): every ARTIFACTS name
    this run EVALUATED and did not hash-verify. A TRACE entry citing such a name
    verbatim gets its note regardless of any OTHER entry's colliding basename. Without
    it, one extra ARTIFACTS line the receipt author picks freely — any real file whose
    basename collides — makes the advisory optional for its own author: the run prints
    `UNVERIFIABLE: b/x.md (no file under root)` and, on the very same stderr, stays
    silent about the TRACE entry citing `b/x.md`, because the UNRELATED verified `a/x.md`
    put `x.md` in `verified_bases`. Silence a receipt author can buy is the grudge
    re-entering through the clause written to close it.

    The override does NOT close the third bullet's general limitation, and is not meant
    to: a TRACE entry naming a genuinely different file that this run never evaluated at
    all — the chunked `chunk-N/round-N-findings.md` shape — matches no declared name, so
    it still falls through to the basename key and still emits nothing. That case stays
    accepted for the reason the bullet gives (a more specific key re-opens §3.2's
    by-design mislabeling of verified files). The override only refuses to extend that
    acceptance to a name the SAME run declared, evaluated, and reported unverified.

    `unevaluated_bases` carries §3.4's truncation rule: on a run truncated by any of
    tier2_artifacts's five raise sites, a TRACE entry matching an ARTIFACTS entry the
    loop never reached emits NOTHING (its match may yet have arrived), while one
    matching an entry EVALUATED — verified or not — before the raise still gets its
    note. The census's existing `partial` flag records that the set is incomplete.

    `unevaluated_names` is that same rule's EXACT-NAME leg, mirroring what
    `unverified_names` does for the verified set, and it exists because the basename
    key alone cannot carry the rule for one legal spelling (#488 round-3/Minor-3). F4's
    read-site guard requires a TRUTHY `base` to match anything, and every name ending in
    `/` has an empty basename — so a `/`-suffixed ARTIFACTS entry the truncated loop
    NEVER REACHED could not be excluded via `unevaluated_bases`, and the TRACE entry
    citing it verbatim emitted a note on a run that had not yet had the chance to verify
    it. That is the truncation rule inverted for exactly the spelling F4 hardened, so
    the fix is the same one F3 already uses: carry the FULL NAMES too, and test them
    before the basename key.

    #488 inquisitor/D1 — the declared-name sets are disjoint as RAW KEYS
    (`unverified_names` is `evaluated`-derived, `unevaluated_names` its complement) and
    NOT as SPELLINGS, which is what this function actually receives: tier2_artifacts's
    `finally:` projects both through `str(n)`, and round-3/Minor-4 established that two
    DISTINCT `artifacts` dict keys can share one `str()` spelling
    (`PurePosixPath("a/x.md")` and `"a/x.md"`). So the two exact-name tests CAN name one
    spelling at once, and what settles that tie is the ORDERING below, not any
    disjointness. All three suppressors sit INSIDE the `unverified_names` override, so
    the fail-NOISY set wins — the same resolution Minor-4 already ruled for the
    verified/unverified pair. An earlier version of this paragraph asserted the
    disjointness and put the `unevaluated_names` test ABOVE the override, where the
    fail-SILENT set won: one ARTIFACTS key the run never reached bought silence for a
    DIFFERENT key the same run evaluated and reported unverified or hash-mismatched.
    That is silence a receipt author can buy with one extra ARTIFACTS line — the
    direction grudge e0f0a6b75692 forbids and the one the override exists to close.

    `_show_path` is required a fortiori (SIEGE-R2BA-4): `name` here comes out of the
    `args` field, which is exactly the shape `_show_path`'s own docstring says the
    surrounding code interpolates raw, so "the surrounding code already does it" is not
    available as a defence at this site.

    THIS FUNCTION MAY NOT RAISE, ON ANY INPUT (#488 round-3/S1). It is called from
    tier2_artifacts's `finally:`, where ANY exception it raises REPLACES the in-flight
    one — a genuine `Tier-2 --strict: ... absent under all bases` LintError reported
    instead as whatever the advisory's own bookkeeping tripped over. Four separate
    point-patches had already been spent on one instance each of that class (`trace or
    []` for a `None` container, `str(n)` for a non-string ARTIFACTS key, F1's isinstance
    for a malformed entry, and the fourth: `entry.get("verb") not in _PROVENANCE_VERBS`
    HASHES the verb, so an unhashable `verb` — a `list` or a `dict` — raises `TypeError:
    unhashable type` at the membership test itself). A fifth type-check would have been
    the fifth instance, so the guarantee is made STRUCTURAL instead: the two `try`s
    below make it hold for every input, including ones nobody has thought of.

    The guards are at TWO granularities and neither subsumes the other:
      * PER-ENTRY (`continue`) — one malformed entry loses only its OWN note; the rest
        of a long TRACE still gets its advisories. A whole-function wrapper would drop
        them all on the first bad element.
      * WHOLE-LOOP (`return`) — the `for` statement itself can raise, and no per-entry
        guard can catch that: a truthy NON-ITERABLE `trace` (`trace=5`, which `trace or
        []` passes straight through) raises at the `iter()`, and a generator `trace` can
        raise on any `next()` (#488 round-3/Minor-2).
    The four point-patches are KEPT alongside them rather than collapsed into them:
    F2's `str()` coercion is a CORRECTNESS fix (it decides which basename gets
    recorded, not merely whether a crash happens), and on exception-safety-critical
    code belt-and-suspenders is the cheaper error. `Exception`, not `BaseException`, so
    KeyboardInterrupt/SystemExit still propagate."""
    if notes_out is None:
        return
    # WHOLE-LOOP guard — see the docstring's structural-invariant paragraph. Covers
    # everything the per-entry guard structurally cannot: the `iter()` the `for`
    # statement performs (a truthy non-iterable `trace` such as `5` walks straight
    # through `trace or []`), and every `next()` after it (a generator `trace` may
    # raise mid-iteration). `return`, not `continue`: once iteration itself has
    # failed there is no next element to move on to.
    try:
        # `or []` is NOT the redundant guard the surrounding file's bare iterations are:
        # this helper runs from tier2_artifacts's `finally:`, so a `None` trace here
        # raises TypeError INSIDE the finally, which REPLACES any in-flight exception —
        # a genuine Tier-2 --strict LintError would be destroyed and reported as
        # "'NoneType' object is not iterable". `trace` is public-API-supplied (~40 call
        # sites, no type enforcement), so the masking hazard is not hypothetical even
        # though the sole production call site passes parse_trace's `[]`. Kept although
        # the enclosing `try` would now catch that TypeError too: `None` is the ONE
        # shape with a right answer better than "abandon the advisory" — an absent
        # trace has no entries, so it should emit nothing and let the loop finish.
        for entry in trace or []:
            # PER-ENTRY guard — a malformed entry loses its OWN note and nothing else.
            # This is the arm that catches the fourth masking instance: the membership
            # test below HASHES `entry.get("verb")`, so an unhashable verb (`list`,
            # `dict`) raises `TypeError: unhashable type` inside the caller's
            # `finally:`. `set` survived it only because CPython special-cases `set`
            # in `x in frozenset(...)` — incidental, not a design guarantee, which is
            # exactly why the guard is structural rather than a fifth type-check.
            try:
                # #488 adversarial/F1 — `.get` behind an isinstance, for the reason
                # _trace_basename's docstring gives: a naked `entry["verb"]` on a
                # malformed element raises inside the caller's `finally:` and REPLACES
                # the in-flight exception. Malformed is "not a match", never a crash.
                if (not isinstance(entry, dict)
                        or entry.get("verb") not in _PROVENANCE_VERBS):
                    continue
                name, base = _trace_basename(entry)
                if not name:
                    continue
                # #488 adversarial/F3 — the exact-name override is tested BEFORE every
                # suppressor, so a colliding sibling cannot silence a name this run
                # itself evaluated and reported unverified. See the docstring for why
                # it does not (and must not) close the general collision.
                if name not in unverified_names:
                    # #488 round-3/Minor-3 — §3.4's truncation rule, exact-name leg.
                    # First of the three suppressors, because it is the rule the other
                    # two are exceptions to: an ARTIFACTS entry this run never reached
                    # may yet have matched, so the citation stays silent. Carries the
                    # `/`-suffixed spelling that the empty basename cannot.
                    #
                    # #488 inquisitor/D1 — NESTED inside the override, not a sibling
                    # ABOVE it, for the same reason `verified_names` below is: the four
                    # sets are disjoint as raw keys but collide as SPELLINGS, and on a
                    # collision the fail-noisy set must win (Minor-4). Sited above it,
                    # this `continue` let an UNREACHED key's spelling silence a
                    # DIFFERENT key the same run evaluated and reported unverified.
                    # Behaviour-preserving off the collision: an unevaluated name is by
                    # construction not in `unverified_names`, so it still `continue`s.
                    if name in unevaluated_names:
                        continue
                    # #488 temper/leg-1 — the VERIFIED set's exact-name leg, the third
                    # of three and the one that was missing. `unevaluated_names` (above)
                    # and `unverified_names` (this test) already carry the spellings the
                    # basename key cannot; the verified set had no such leg, so a name
                    # whose basename is degenerate had nothing to fall back on and got a
                    # note asserting the opposite of the census. Measured on 5e1b6df:
                    # ARTIFACTS `x/` + TRACE `READ x/` renders `artifacts 1/1` AND
                    # `PROVENANCE-ONLY: x/ (declared in TRACE, not verified)` on the same
                    # stderr, about the same name.
                    #
                    # NESTED INSIDE the `unverified_names` test, deliberately, as every
                    # suppressor here now is (#488 inquisitor/D1): round-3/Minor-4
                    # established that two DISTINCT ARTIFACTS dict keys can share one
                    # SPELLING, so a spelling can sit in `verified_names` and
                    # `unverified_names` at once. Nesting makes UNVERIFIED win that tie —
                    # the fail-noisy direction, which is the one Minor-4 already ruled for.
                    if name in verified_names:
                        continue
                    # #488 adversarial/F4, widened by #488 temper/leg-1 — `base` must be
                    # a NON-DEGENERATE key to match. `rsplit("/", 1)[-1]` maps every name
                    # ending in `/` to `""`, in `/.` to `"."`, and in `/..` to `".."`, and
                    # `if not name: continue` above screens an empty NAME, not a degenerate
                    # BASE. One legally-spelled verified `ARTIFACTS` entry (`x/` or `x/.`,
                    # both of which resolve_base normalises and hash-verifies) would
                    # otherwise put that degenerate key into `verified_bases` and from then
                    # on silence EVERY TRACE name with the same degenerate basename, however
                    # unrelated — a key that swallows a whole family of names. F4 tested
                    # truthiness, which caught `""` and missed `.`/`..`; see
                    # _DEGENERATE_BASES for the four-arm measurement. Guarded here as well
                    # as at the `.add` site, so a degenerate base cannot match
                    # `unevaluated_bases` either; `unevaluated_names` above and
                    # `verified_names` just above carry those sets' own members instead.
                    if base not in _DEGENERATE_BASES and (
                            base in verified_bases
                            or base in unevaluated_bases):
                        continue
                notes_out.append(
                    f"PROVENANCE-ONLY: {_show_path(name)} "
                    f"(declared in TRACE, not verified)")
            except Exception:
                continue
    except Exception:
        return


def tier2_artifacts(artifacts, trace, root, strict, cov=None, bodies=None,
                    notes_out=None):
    """Part 1. For each ARTIFACTS <name>: resolve_base; if found, recompute sha256
    and compare (mismatch -> FAIL). If absent: path-shaped + strict -> FAIL;
    else UNVERIFIABLE (non-fatal). Returns list of UNVERIFIABLE notes; raises LintError on FAIL.

    #486 / D8 — `cov` is an optional _Coverage collector. OPTIONAL WITH A DEFAULT is
    deliberate: the ~50 direct call sites pass positionally, so a required parameter
    would change arity everywhere and falsify D8.2's "no existing caller moves".

    SIEGE-R2BA-1 — `bodies` is an optional out-parameter (a dict, same idiom and same
    reason as `cov`/`found`/`probe`/`meter`). When passed, each entry whose sha256
    MATCHED is recorded under BOTH keys — `{declared-name: raw}` AND
    `{resolved-realpath: raw}` — and tier2_witness evaluates ITS predicate against that
    buffer instead of re-resolving the name and re-reading the file. Two keys because
    each covers a miss the other does not; see the write site. Only
    matched entries are carried, because the whole point of the carry is that the
    verified hash is a statement about the bytes the predicate ran against.

    #488 / T2 — `notes_out` is an optional out-parameter list for the PROVENANCE-ONLY
    notes, the same idiom tier2_witness already uses for wit_notes/notes_out and the
    same OPTIONAL-WITH-A-DEFAULT reason as cov/bodies: the ~40 call sites pass
    positionally, so a required parameter would change arity everywhere. The notes MUST
    NOT ride the return value: this function raises on five sites that truncate the
    entry loop, and the sole production call site is `notes += tier2_artifacts(...)`,
    whose `+=` never executes on a raise — a return-by-value note list is discarded
    WHOLE, not partially, on every truncated run. Callers that pass None get no notes,
    which is why --eval and --selftest are unaffected.

    #488 / T7 — the RESOLVED-BY-WALK: notes this function also emits go through the
    SAME out-parameter, for the same reason. Do not route them through `notes`.

    #488 inquisitor/M2 — an ACCEPTED, and until now unrecorded, cost of that split: the
    ORDER the three note classes reach stderr in is not stable across runs. The
    PROVENANCE-ONLY:/RESOLVED-BY-WALK: notes go into `notes_out` as the loop runs, while
    this leg's own UNVERIFIABLE:/REFUSED:/AMBIGUOUS: notes ride the RETURN value and are
    appended by the caller's `+=` afterwards — except on a raise, where the
    `except BaseException:` arm mirrors them into `notes_out` mid-band. Measured: a
    clean run renders [WALK, PROVENANCE, UNVERIFIABLE, UNVERIFIABLE] and a truncated one
    [WALK, WALK, UNVERIFIABLE, PROVENANCE]. Nothing normative pins it —
    return-convention.md pins the `TIER2-COVERAGE:` line's own position and content, and
    the walk note's emission BEFORE the ambiguity raise, but says nothing about the
    bullets' order relative to each other — and all three classes are advisory, bumping
    no counter and moving no exit code. Do NOT "fix" it by reordering: putting these
    notes back on the return value re-opens the discard-on-raise fail-open the
    out-parameter exists to close. Do not read the clean-run order as a contract."""
    notes = []
    # SIEGE-R2BA-2 — what is LEFT of ARTIFACT_READ_CAP for this leg. Cumulative, because
    # the entry count is receipt-controlled; see the constant for why.
    budget = ARTIFACT_READ_CAP
    # #488 / T2 — the two facts the PROVENANCE-ONLY key needs, accumulated AS the loop
    # runs so a raise leaves them PARTIAL rather than absent (§3.4's truncation rule).
    verified_bases = set()
    evaluated = set()
    # #488 adversarial/F3 — the DECLARED ARTIFACTS KEYS that hash-verified, accumulated
    # the same incremental way, so `evaluated - verified_keys` in the `finally:` is
    # exactly "declared, evaluated on this run, and NOT verified" however the run ended.
    # That set is the exact-name override; see _emit_provenance_notes's docstring.
    #
    # #488 round-3/Minor-4 — the RAW KEYS, not `str(name)`. Subtracting a set of
    # SPELLINGS re-merged two DISTINCT ARTIFACTS keys whose `str()` collides (a
    # `PurePosixPath("a/x.md")` and an `"a/x.md"` are different dict keys but the same
    # string), so one key verifying deleted the override for the OTHER key that did
    # not — silence bought by a spelling coincidence, which is the direction grudge
    # e0f0a6b75692 forbids. Keys are `artifacts` dict keys and therefore hashable by
    # construction, so a raw-key set is always available; the `str()` is applied once,
    # at the `finally:`, to the entries that survive the subtraction.
    verified_keys = set()
    # #488 inquisitor/AV1 (edge) — where each DECLARED name actually resolved on this
    # run, accumulated the same incremental way as the sets above. Read only by the
    # `finally:`, to project the three exact-name sets through §3.2's OTHER mandated
    # spelling; see _declared_spellings.
    resolutions = {}
    # The EFFECTIVE roots, once. Needed in the `finally:` (where an unresolvable name
    # still has an absolute spelling, derived lexically), and computed here rather than
    # there because a `finally:` may not acquire a new failure mode — `_as_roots` already
    # runs inside every resolve_base call below, so this adds none.
    all_roots = _as_roots(root)
    # #488 warden-r2/F3 — widened, FOR SPELLING PURPOSES ONLY, with the AS-SUPPLIED
    # root token(s) beside the resolved ones. `_as_roots` resolves symlinks
    # unconditionally and ~50 call sites depend on that resolved-only contract, so it is
    # not the thing to change; but a `--root` that is ITSELF a symlink (`/tmp` on macOS,
    # `/var`→`/private/var`, many CI runners' workdirs) then makes the lexical join emit
    # ONLY the realpath spelling — while a real receipt's §3.2 TRACE citation carries the
    # path the dispatch was given, i.e. the as-supplied one. That left the exact-name
    # override fail-SILENT for precisely the spelling production uses, reopening AV1's
    # headline case through a second door. `all_roots` feeds nothing but the three
    # `_declared_spellings` calls in the `finally:` (verified above), so widening it here
    # cannot move resolution, containment or ambiguity. Computed before the `try:` so the
    # `finally:` acquires no new failure mode. `.rstrip("/")` because the join is
    # `f"{base}/{s}"` and a trailing-slash-supplied root would otherwise double it.
    _supplied = [root] if isinstance(root, (str, pathlib.Path)) else list(root)
    all_roots = list(dict.fromkeys(
        [str(x) for x in all_roots] + [str(x).rstrip("/") for x in _supplied]))
    try:
        for name, meta in artifacts.items():
            evaluated.add(name)     # tried, whatever this iteration goes on to do
            found = []
            refused = []
            resolved = resolve_base(name, root, found, refused)
            if resolved is None:
                # D8.3's arm, and the --strict/UNVERIFIABLE arms, now live in the shared
                # _unresolved_disposition so the witness leg cannot classify the same name
                # differently (F4). Decided AFTER resolution — that ordering ruling
                # (round-2/S2) is the call site's to keep, and it is kept here.
                #
                # `resolved is None` implies `found == []` (resolve_base returns the first
                # hit, so a non-empty `found` always yields a `resolved`), which is why this
                # branch may sit above the `len(found) > 1` test without hiding an ambiguity:
                # a 12-hex name present under two roots is a real file in two homes and takes
                # the ambiguity branch exactly as any other name does.
                notes.append(_unresolved_disposition(name, strict, cov,
                                                     refused=refused))
                continue
            resolutions[name] = resolved
            if refused:
                # siege S-3(b) — `_refused_clause` was consumed ONLY by
                # _unresolved_disposition, so a refusal that the FALLBACK then papered over
                # was never printed at all: the operator saw a clean run and no mention that
                # the probe set had been narrowed under them. The refusal is a property of
                # the RUN, not of the failure, so it is reported whenever it happens.
                notes.append(f"REFUSED: probe base dropped while resolving "
                             f"{_show_path(name)}{_refused_clause(refused)}")
            if cov is not None:
                cov.art_applicable += 1
            # #488 / T7 — a below-top-level resolution is REPORTED and COUNTED, never
            # summed into the floor buckets (whether it ever is, is OQ-7 on #530).
            #
            # SITED BEFORE the `if len(found) > 1:` ambiguity block, not after it: that
            # block RAISES under --strict, and --strict is the MANDATED invocation. The
            # name DID resolve, so an emission below the raise goes silent on exactly
            # the run the raise truncates — the same reason the `ambiguous` bump inside
            # that block is itself sited before its own raise.
            #
            # ROUTED THROUGH `notes_out`, NOT through `notes`: this function's own
            # docstring says why — the return value is discarded WHOLE on every one of
            # the five truncating raise sites, so an append to `notes` here would leave
            # the counter and the note contradicting each other on exactly the truncated
            # runs. That is the reason for the routing, but it is NOT what the acceptance
            # suite measures: round-4-of-this-gate's S1 arm (`except BaseException:`
            # below) mirrors `notes` onto `notes_out` on ANY raise, so a build that
            # appends here to `notes` still reaches stderr and leaves
            # `TestTheWalkNoteSurvivesATruncatedRun` — and both suites — green. The
            # direct routing is what makes this note's survival independent of that arm;
            # Task 7's DEC-31 row 12 discriminates the channel only because its mutant
            # copy removes the arm as well.
            _rel = _below_top_level(resolved, root)
            if _rel is not None:
                # COUNTER FIRST, note second — round-3/S1. With the emission ahead of
                # the bump, a `notes_out` that cannot take the note lost the note AND
                # skipped the counter, so the census denied an event the ruling says
                # happened. This order cannot produce that contradiction: the bump is
                # unconditional on resolution, and the note is the only half a hostile
                # out-parameter can suppress.
                #
                # #488 inquisitor/M1 — that suppression is not always all-or-nothing.
                # An out-parameter that refuses EVERY append leaves no note of this
                # class on stderr at all, so nothing remains to disagree with the
                # census; one that refuses only the Nth delivers some notes and leaves
                # the count ABOVE them (measured: census 2, notes 1). The order still
                # stands — it is the census's COUNTS, not the advisory bullets, that
                # are the machine channel (return-convention.md pins the
                # `TIER2-COVERAGE:` line, not the bullets), and the production
                # out-param is a plain list — but the claim it supports is "the census
                # never denies an event", not "the two halves can never differ".
                #
                # REDUNDANT while `_emit_walk_note`'s envelope holds, and deliberately
                # so: measured on this commit, reverting THIS order alone leaves both
                # suites green, because a guarded emission cannot raise past the bump.
                # It is the second layer — if a later change ever narrows that envelope,
                # this order degrades the failure to "counter right, note missing"
                # instead of "counter wrong, note missing, and the verdict replaced".
                # Only the two mutations TOGETHER redden
                # `test_the_counter_and_the_note_cannot_disagree`.
                if cov is not None:
                    cov.bump("resolved-by-walk")
                _emit_walk_note(notes_out, name, _rel)
            if len(found) > 1:
                # #486 / D2 — two or more DISTINCT realpaths. Fail closed under --strict:
                # first-hit-wins here would verify against a plausible but WRONG file, a
                # silent-wrong-answer class strictly worse than the loud UNVERIFIABLE it
                # replaces. Byte-identical copies count too (Q7): collapsing them would make
                # the disposition depend on the content of a file the receipt may control.
                # The parenthetical lists EVERY distinct realpath, sorted lexicographically;
                # with N roots the candidate space is up to 2N, so it is not a two-item bound.
                if cov is not None:
                    # Bumped BEFORE the --strict raise, so the item is recorded on exactly
                    # the run the raise truncates.
                    cov.bump("ambiguous")
                # SIEGE-C2 — _show_path, not str(): `found` holds RESOLVED paths under roots
                # the reviewed subagent owns, and an unescaped newline in one forges a second
                # TIER2-COVERAGE: line on the channel callers parse.
                homes = ", ".join(sorted(_show_path(p) for p in found))
                # SIEGE-R2BA-4 — the NAME too, not only the homes.
                msg = f"artifact {_show_path(name)} is ambiguous across roots ({homes})"
                if strict:
                    if cov is not None:
                        cov.partial = True     # remaining entries + witness leg uncounted
                    raise LintError(f"Tier-2 --strict: {msg}")   # BEFORE any read
                notes.append(f"AMBIGUOUS: {msg}")
            try:
                # SIEGE-R2BA-2 — bounded, so an attacker-named 4 GiB sparse file is refused
                # instead of materialised. The raise is a LintError and lands on the arm
                # below it, which sets `partial` exactly as the unreadable arm does.
                raw = _read_capped(resolved, budget, f"ARTIFACTS {_show_path(name)}")
            except LintError:
                # Over-cap: bytes NOT read, hash NOT recomputed, remaining entries and the
                # witness leg uncounted. Fails CLOSED — never a silent skip.
                if cov is not None:
                    cov.partial = True
                raise
            except (OSError, MemoryError) as e:
                # SIEGE-R2BA-2 — MemoryError beside OSError. It is NOT an OSError, so under
                # `ulimit -v` it escaped this guard and printed a Traceback AFTER the census.
                # `strerror` via getattr because only the OSError leg has one.
                #
                # #486 fixer / F3 — a name that RESOLVES but cannot be READ. #486's whole
                # purpose is to make these names resolve, under a second, orchestrator-
                # supplied findings root whose contents this process does not own, so a
                # mode-000 / EISDIR / ENOENT-since-probe file is now ordinary. _verify_single
                # catches only LintError and the module guard only _PathReadError, so the
                # bare read_bytes() escaped as a traceback printed AFTER the
                # TIER2-COVERAGE: line. A clean classified bullet instead; partial because
                # the remaining entries and the witness leg go uncounted.
                if cov is not None:
                    cov.partial = True
                raise LintError(
                    f"Tier-2: ARTIFACTS {_show_path(name)} unreadable "
                    f"({_strerror(e)})")
            budget -= len(raw)
            actual = hashlib.sha256(raw).hexdigest()
            if cov is not None:
                # ⚠ PLACEMENT IS LOAD-BEARING (round-5/SIG-3): bytes read + hash
                # evaluated == VERIFIED, including the entry that then mismatches, so
                # the increment sits between the recomputation and the comparison —
                # never after it. The natural placement ("count it once we know it's
                # good") renders `artifacts 0/N` on exactly the mismatch runs the
                # census exists to explain.
                cov.art_verified += 1
            if actual != meta["hash"]:
                if cov is not None:
                    cov.partial = True     # remaining entries + witness leg uncounted
                raise LintError(f"Tier-2: ARTIFACTS {_show_path(name)} sha256 mismatch (disk={actual[:12]} receipt={meta['hash'][:12]})")
            if bodies is not None:
                # SIEGE-R2BA-1 — carried AFTER the comparison, so the buffer the witness leg
                # evaluates is exactly the buffer this leg hashed AND matched.
                #
                # Carried under BOTH keys — the declared NAME and the RESOLVED realpath — and
                # both are load-bearing in opposite directions. Keying on only one loses a
                # case the other covers, which is why this is not a single-key choice:
                #   * NAME alone (the original) missed whenever the two legs SPELLED the same
                #     file differently. The witness leg's `art_name` for a rangeless grep
                #     payload is the first token of the cited TRACE entry's args verbatim,
                #     written independently of the ARTIFACTS line, so a `./f.md` in TRACE
                #     against an `f.md` in ARTIFACTS silently reinstated the second
                #     independent read this carry exists to remove — on a name that HAD been
                #     hashed. Realpath closes `./`, `a/../f.md` and absolute-vs-relative.
                #   * REALPATH alone missed whenever the same declared name RESOLVES
                #     differently between the legs — precisely the mid-lint symlink swap this
                #     carry was written against. Replacing the hashed regular file with a
                #     symlink to a sanitised sibling moves the realpath, so a realpath-only
                #     lookup misses and the predicate runs on the sanitised bytes: a receipt
                #     the carry used to REJECT would be accepted. That is a fail-open, so
                #     realpath is an ADDITION here, never a replacement.
                # Two keys for one buffer, so a hit under either binds the predicate to the
                # bytes this leg hashed AND matched. `name` is a str and `resolved` a Path, so
                # the two key spaces cannot collide.
                #
                # #488 warden-r2/F2 — `str(name)`, matching the `finally:` block's twin below
                # and for the identical hazard. `name` is only str-typed for the CLI path;
                # the ~40 direct-API call sites this file already treats as in scope can hand
                # in an `os.PathLike` (e.g. `PurePosixPath`) declared key. Stored raw, such a
                # key made BOTH halves of the carry fail open: the ordinary single-spelling
                # NAME lookup missed (the witness leg's `art_name` is always a str, and
                # `PurePosixPath("f.md") != "f.md"`), and `_carry_should_have_bound`'s
                # `isinstance(k, str)` filter then skipped it, so the mid-run-swap detector
                # was silent too. Normalising here fixes both at once and makes that filter's
                # stated contract — "the string keys ARE the declared names" — true rather
                # than aspirational, instead of widening the filter to a key space the
                # lookup still cannot hit.
                bodies[str(name)] = raw
                bodies[resolved] = raw
            # #488 / T2 — recorded only AFTER the sha256 comparison above, so "verified"
            # means resolved AND hash-matched, never merely resolved.
            #
            # #488 adversarial/F2 — `str(name)`, matching the `finally:` block's twin.
            # This site was left naked when that one was hardened, and unlike that one it
            # is NOT gated on `notes_out`, so it runs for EVERY caller including the
            # `notes_out=None` --eval/--selftest shape that asked for no notes at all: an
            # `os.PathLike` ARTIFACTS key that survives resolve_base AND the hash
            # comparison reached `.rsplit` and raised `AttributeError` on an otherwise
            # SUCCESSFUL run — a new exception, not merely a masking hazard, on input the
            # pre-#488 code returned `[]` for. The advisory's own bookkeeping must never
            # be able to fail a verification that passed.
            #
            # #488 adversarial/F4, widened by #488 temper/leg-1 — a DEGENERATE basename
            # is never stored. A legally-spelled `x/` or `x/.` resolves and hash-verifies,
            # and `""` / `"."` in `verified_bases` would then match every TRACE name
            # ending in `/` / `/.`; see _DEGENERATE_BASES and _emit_provenance_notes. F4
            # stored anything TRUTHY, which excluded `""` and admitted `.`.
            vbase = str(name).rsplit("/", 1)[-1]
            if vbase not in _DEGENERATE_BASES:
                verified_bases.add(vbase)
            verified_keys.add(name)
            # <size> is parsed-but-not-validated, matching lint.py
    except BaseException:
        # round-4-of-this-gate S1 — siege S-3(b) parity with tier2_witness's C1-R3-S2
        # mirror: this leg's OWN UNVERIFIABLE:/REFUSED:/AMBIGUOUS: notes, accumulated
        # into `notes` above, ride the RETURN value, whose `+=` at the sole production
        # call site never executes on a raise. Without this arm they are silently
        # discarded WHOLE on every one of the five truncating raises — the exact
        # fail-open shape grudge e0f0a6b75692 exists to prevent, and the one the new
        # PROVENANCE-ONLY:/RESOLVED-BY-WALK: notes do NOT share, because Task 4/5 route
        # them through `notes_out` directly.
        #
        # #488 round-4/S1 — the ENTIRE arm body is inside the no-raise envelope, not
        # just the `.extend` call, and that scope is the point. This is the FIFTH
        # instance of one hazard class: an expression evaluated while an exception is
        # IN FLIGHT, which — by Python's `except`/`finally` semantics — REPLACES the
        # real verdict with its own failure. The four before it were point-patched one
        # shape at a time (`trace or []`, `str(n)`, the per-entry guard, the call-site
        # wrapper) and each patch's own new code carried the next instance in. Here
        # `notes_out` is the THIRD caller-controlled parameter with no type enforcement
        # (~40 call sites, positional), so `()`, `0`, an object without `.extend`, and
        # an object whose `.extend` raises are all ordinary API misuse — and all four
        # were measured destroying a genuine `Tier-2 --strict: ... absent under all
        # bases` LintError. Wrapping the BODY rather than the CALL is what stops a
        # sixth INSIDE THIS ARM: any line a later change adds here is inside the
        # envelope by construction, exactly as the `finally:` block's twin wrapper
        # already is. #488 round-3/S1 records the bound that claim actually has —
        # the sixth instance arrived, and it arrived OUTSIDE this arm, at the two
        # RESOLVED-BY-WALK emission sites Task 5 added to the two legs' clean paths.
        # A per-block envelope closes a block, not a parameter; each new site that
        # touches `notes_out` still has to carry its own (see `_emit_walk_note`).
        # `Exception`, not `BaseException`: KeyboardInterrupt/SystemExit propagate.
        # Swallowing is right HERE for the same reason it is right there — these notes
        # are an advisory side channel and must never preempt the verdict.
        try:
            if notes_out is not None:
                notes_out.extend(notes)
        except Exception:
            pass
        raise
    finally:
        # In a `finally:` so the notes survive all five truncating raise sites, which is
        # the whole reason the out-parameter exists (§3.4, T2 leg 6).
        #
        # BOTH defences below exist because this body runs from a `finally:`, where
        # ANY exception it raises REPLACES the in-flight one — the hazard
        # _emit_provenance_notes's own `trace or []` guard names. Neither of the
        # helper's guards can cover this site, because a call's ARGUMENTS are
        # evaluated BEFORE the callee is entered:
        #   * `if notes_out is not None` — the helper's own `if notes_out is None:
        #     return` is reached only after the set-comprehensions below have already
        #     run. Hoisting the same test to the call site makes the whole body a
        #     no-op for the callers that want no notes (--eval, --selftest). The
        #     helper KEEPS its own check (#488 round-3/Minor-5 corrects an earlier
        #     comment here that called it retired): it is a public-module-level
        #     function, and its no-raise contract has to hold for a caller that did
        #     not hoist the test.
        #   * `str(n)` — a non-string ARTIFACTS key made `n.rsplit(...)` raise
        #     `AttributeError: 'int' object has no attribute 'rsplit'` right here,
        #     destroying a genuine `Tier-2 --strict: ... absent under all bases`
        #     LintError and reporting the AttributeError in its place. `artifacts` is
        #     public-API-supplied (~40 direct call sites, no type enforcement) exactly
        #     as `trace` is, so the reachability argument is the same one. `str()` is
        #     identity on the str keys parse_artifacts produces, so production
        #     behaviour does not move; on a bad key the basename simply matches no
        #     TRACE basename and the REAL verdict survives. That ordering is the
        #     point: these notes are an advisory side channel and must never preempt
        #     the verdict, so coercing beats raising here — fail-loud belongs on the
        #     verification path, not inside its `finally:`.
        if notes_out is not None:
            # #488 round-3/S1 — the OUTER half of the structural no-raise guarantee.
            # _emit_provenance_notes now guarantees it never raises, but a call's
            # ARGUMENTS are evaluated BEFORE the callee is entered, so the two set
            # comprehensions below run OUTSIDE that guarantee, right here in the
            # `finally:` — `str(n)` on an ARTIFACTS key with a raising `__str__` would
            # still replace the in-flight LintError. One wrapper closes the whole class
            # at this site permanently instead of type-checking `artifacts` keys.
            # `Exception`, not `BaseException`: KeyboardInterrupt/SystemExit propagate.
            try:
                unevaluated = [n for n in artifacts if n not in evaluated]
                # #488 inquisitor/AV1 (edge) — the three EXACT-NAME sets are projected
                # through _declared_spellings, so each carries §3.2's absolute form
                # beside §3.1's declared one. The BASENAME set is NOT: it is already
                # spelling-independent by construction (that is what a basename key is
                # for), and adding absolute spellings to a set matched by basename would
                # be a category error.
                _emit_provenance_notes(
                    trace, verified_bases,
                    {str(n).rsplit("/", 1)[-1] for n in unevaluated},
                    _declared_spellings(unevaluated, all_roots, resolutions),
                    _declared_spellings(
                        [n for n in evaluated if n not in verified_keys],
                        all_roots, resolutions),
                    notes_out,
                    # #488 temper/leg-1 — the verified set's exact-name leg. Built from
                    # `verified_keys`, which already exists (it is what the line above
                    # subtracts), so this adds a comprehension and no new bookkeeping.
                    # Inside the same `try` as its siblings, so it keeps the round-3/S1
                    # no-raise envelope: a raising `__str__` here would otherwise replace
                    # the in-flight LintError.
                    #
                    # #488 inquisitor/AV1 (edge) — projected like its two siblings.
                    # _declared_spellings keeps the same envelope (it is guarded per
                    # name and cannot raise) and carries the `str()` this used to do.
                    _declared_spellings(verified_keys, all_roots, resolutions))
            except Exception:
                pass
    return notes


def derive_art_name(cited, verdict):
    """Derive the body-lookup artifact name from the cited TRACE entry, EXACTLY as
    lint.py's tier2_verify (PASS: EXEC out= OR READ/WROTE cited path) and
    tier2_verify_fail (FAIL: EXEC out= only) do. Returns None when no body lookup
    applies (→ clean). Shared by verify_witness (message/control) and the --eval
    caller (body fetch) so the two Tier-2 paths cannot diverge on art_name."""
    r = parse_out_range(cited["args"]) if cited["verb"] == "EXEC" else None
    if verdict == "FAIL":
        # tier2_verify_fail — EXEC-only (lint.py:370-373)
        if not r:
            return None
        return r.artifact
    # verdict == PASS — tier2_verify (lint.py:315-326)
    if not r and cited["verb"] in {"READ", "WROTE"}:
        path_m = re.match(r"^(\S+)", cited["args"])
        return path_m.group(1) if path_m else None
    if r:
        return r.artifact
    return None


def _expect_fail_pattern(expect_fail, pattern_clause=None):
    """Regex source for a WITNESS expect-fail sig: /regex/ verbatim, "literal"
    escaped, else None (e.g. an exit= clause). #442 G6c — one source for the
    two byte-identical derivation blocks in verify_witness.

    #474 / D2: for `expect_fail == "match"` the source comes from the WITNESS line's
    separate `pattern=` clause instead (expect_fail keeps its verbatim "match", so no
    message text and no consumer comparing == "match" moves). PRECONDITION: callers
    must pass a DELIMITED clause whose derived source is NON-EMPTY — Tier-1
    (parse_witness) rejects the rest. This helper is deliberately not self-defending:
    it keeps returning None for a bare/undelimited clause and '' for an empty one, and
    verify_witness reads both as clean. Adding a 'treat a bare token as a regex' branch
    here would be the fail-OPEN direction on the very form Tier-1 exists to close."""
    src = pattern_clause if expect_fail == "match" else expect_fail
    if src is None:
        return None
    if src.startswith("/") and src.endswith("/"):
        return src[1:-1]
    if src.startswith('"') and src.endswith('"'):
        return re.escape(src[1:-1])
    return None


def witness_art_name(witness, cited, verdict):
    """#474 / D4 — which artifact the Tier-2 witness body comes from, and whether it
    came from the WITNESS payload. Returns (art_name, from_payload).

    return-convention.md § "kind=grep artifact/range resolution" already settles this:
    "For kind=grep, the cited artifact
    AND range are those named on the grep:<artifact>#<range> payload's own #<range>
    (the witness line itself), NOT an out= field." derive_art_name is non-conformant
    for kind=grep — it returns the EXEC out= artifact or the READ/WROTE cited path.

    The pair is returned together on purpose: taking the RANGE from the payload while
    leaving the ARTIFACT from derive_art_name pairs a range with the wrong file (lines
    112-155 of a 6-line log = the empty string, which re.search never matches — a new
    categorical fail-open inside a fail-open fix). Callers pass `witness if from_payload
    else None` to _read_cited_range, so artifact and range are always sourced together.

    GH #501 — BOTH LEGS, which is what the convention said all along. The rule quoted
    above is not scoped to a verdict, so the PASS-only conjunct that used to stand here
    was a non-conformance, not lint.py parity. Its cost was total: on the FAIL leg
    derive_art_name is EXEC-only, every red-team receipt cites a WROTE (that is what
    TRACE looks like when the work product is a findings file), so art_name came back
    None and tier2_witness returned before resolve_base was EVER called. #486's whole
    resolution machinery was unreachable on the verdict of every gate round that finds
    anything. Measured with `scripts/measure_486_corpus.py` over the three ENUMERATED
    frozen corpora (`corpus17` + `live29` + `codegate22` = 68 receipts): 18 of 68 carry
    this shape — every one of the 19 `FAIL` receipts except the single one citing an
    `EXEC` with an `out=` range, which `derive_art_name` could still name.

    ⚠ The conjunct could NOT be dropped on its own, and the reason is the half that
    makes this a convention change rather than a one-liner. verify_witness's FAIL branch
    computes `content_match` and then discards it unless `exit_success`, and a
    WROTE-cited entry carries no `exit=` — so sourcing alone makes the predicate run,
    resolve, read real bytes and still be structurally unable to reject, while
    `_bill_witness_evaluation` bills it `witness 1/1`. Measured by reverting ONLY the
    `probe["result_discarded"]` assignment on a copy of this tree and re-running
    `measure_486_corpus.py`: the conjunct drop ALONE takes the witness ratio from the
    shipped `9/15 + 18/29 + 15/21 = 42/65` to `11/15 + 18/29 + 21/21 = 50/65`, i.e. it
    moves 8 of the 68 enumerated frozen-corpus receipts from an honest `witness 0/1
    unreached 1 (fail-leg-payload-not-sourced)` to `witness 1/1` with every sub-count at
    0 — trading a false `not-applicable` for a false `verified`, which is strictly
    worse. (Both figures are reproducible on demand, never CI-defended — see
    `measure_486_corpus.py`'s docstring.) The companion withholding
    (`probe["result_discarded"]` → the `discarded` sub-count) is what makes this safe,
    and the two must never be separated.

    WIDENING, stated plainly: ran=TRACE#N no longer determines which file is read (it is
    still Tier-1-checked to point at an EXEC/READ/WROTE) — the reviewer gains control of
    WHICH FILE, not merely which lines. D6's ARTIFACTS-membership rule buys back the
    DECLARATION half (the name must be one the receipt declares) and, since #486, the
    payload artifact resolves under the supplied roots like any other, so the widening
    now lands inside artifact resolution instead of ahead of it."""
    if (witness.get("kind") == "grep"
            and witness.get("range_kind") is not None):
        return witness["art"], True
    return derive_art_name(cited, verdict), False


def verify_witness(body_text, witness, verdict, cited, probe=None) -> bool:
    """Pure expect-fail decision core — the ONE shared, deliberately-non-verbatim
    factor of lint.py's tier2_verify (verdict=PASS) and tier2_verify_fail (verdict=FAIL).
    Returns True if the witness is clean; RAISES LintError with the BYTE-IDENTICAL
    message string of the source function on the branch that would FAIL (message
    fidelity is load-bearing for the --eval byte-diff). `cited` = the WHOLE parsed
    cited TRACE entry; `body_text` = the resolved body for derive_art_name(cited, verdict)
    (None ⇒ no body ⇒ clean, reproducing lint.py's `art_name not in artifact_bodies: return`).
    Shared by the disk reader (cited #L/#B range) and the --eval inline-body path.

    ASYMMETRY — WHAT #501 CLOSED AND WHAT IT DID NOT. lint.py's FAIL-leg body lookup is
    EXEC-only, so the SAME grep:READ/WROTE witness whose body matches expect-fail raised
    under PASS and returned clean under FAIL. #474 sharpened that into a
    NON-CONFORMANCE rather than parity: return-convention.md § "kind=grep artifact/range
    resolution" scopes the grep artifact/range rule to BOTH branches. #501 reversed it —
    witness_art_name now sources a ranged payload on either verdict, so the body IS read
    here on FAIL and derive_art_name no longer keys the lookup on the verdict.

    What survives is NOT a lookup asymmetry but an EVIDENTIAL one, visible a few lines
    down: this leg raises only under `exit_success and not content_match`, so on a cited
    entry carrying no `exit=` the predicate runs and its result is discarded. That is
    reported (`probe["result_discarded"]` → the `discarded` sub-count, never
    `witness 1/1`) rather than closed, because closing it means deciding what a witness
    on a SHELL-LESS dispatch can prove at all — a convention question no --root
    configuration answers, and the honest successor to #501 rather than a deferral of it.

    DISK vs --eval DIVERGENCE 1 — SLICING (deliberate, #474/D4): the disk reader slices
    the body to the witness/cited range, while _eval_tier2 passes the WHOLE inline
    artifact_bodies entry. Slicing the inline path would mean re-deriving line offsets
    against a body that never had them — there is no file. Selftest step (iv) checks
    the paths do not drift on kind=exec; for kind=grep they diverge BY DESIGN.

    DISK vs --eval DIVERGENCE 2 — DISPOSITION on an unsupplied body (named here after
    round-1/SIG-3 found it undocumented). D4 changed WHICH artifact the PASS leg reads
    for a ranged kind=grep witness: the payload's artifact, not derive_art_name's
    out=/cited path. The two modes then answer differently when those names differ:
      * disk (tier2_witness) resolves the PAYLOAD artifact under --root. Present ⇒ it
        is read and the predicate runs, so a contradicting body RAISES.
      * --eval (_eval_tier2) can only see the bodies the record hands it. If the
        record is keyed on the CITED artifact — which every pre-existing inline row
        is — `bodies.get(payload_artifact)` misses, body_text is None, and this
        function returns clean at the lint.py-parity guard below.
    The same receipt is therefore LINT-FAIL on disk and LINT-PASS under --eval. This
    is an INFORMATION asymmetry, not a rule disagreement, and it is deliberately NOT
    closed by making --eval raise: disk reports an unavailable artifact as a non-fatal
    UNVERIFIABLE note, --eval has no UNVERIFIABLE channel, so clean IS the parity
    disposition (`art_name not in artifact_bodies: return`). Failing closed on the
    inline leg would CREATE a disposition divergence rather than remove one. What is
    guarded instead: selftest step (iv) now rejects any artifact_bodies row whose
    ranged grep witness verifies an artifact the row does not supply — the
    "coverage that cannot fail" shape — so the fixture corpus cannot drift into it.
    Pinned by test_23* in scripts/test_rcpt_verify.py.

    SIEGE-C3 — `probe` is an optional out-parameter (a dict; optional-with-a-default for
    the same reason `cov` is, so none of the ~50 existing call sites moves). When passed,
    it records under "no_predicate" the reason NO predicate was evaluated against `body`
    on this call — the census consumes it and must NOT bill such a call as a verification.
    Write-only: nothing this function DECIDES depends on it, so no exit code moves.
    The ONE shape that reaches here and consults zero disk bytes is an expect-fail from
    which no body pattern derives — i.e. `_expect_fail_pattern(...) is None`. That is the
    single test, and `kind` only selects which reason code names it:
      * kind=lint — there is no `lint:` branch below AT ALL. return-convention.md's
        `ran=` bullet says Tier-2 "re-applies the named rule"; it does not, and
        `LINT_RULES` is used only for NAME validation in parse_witness. Implementing the
        rules is a feature and is NOT done here; what is corrected is the census's false
        assertion that a verification happened.
        NOT a kind-wide exemption, deliberately: a lint witness carrying a /regex/ or
        "literal" expect-fail falls through to the shared regex tail below and IS
        evaluated against the disk body (and can raise from it) — the body is read and
        discarded only when the expect-fail is an exit clause. Billing such a call
        `no_predicate` made the census contradict its own run's stderr, and it is the
        form the one lint witness in the committed corpus uses.
      * an exit-clause expect-fail (`exit!=0` / `exit=<N>`) — the PASS-leg kind=exec
        branch compares the RECEIPT's own expect-fail against the RECEIPT's own
        `TRACE exit=`, and for any other kind `_expect_fail_pattern` returns None so
        `if pattern and re.search(...)` short-circuits clean. Either way the bytes on
        disk are never consulted. `_expect_fail_pattern(...) is None` is the exact test
        — it is None for the exit forms and for nothing else Tier-1 admits — so the two
        legs cannot drift from the derivation they actually use.

    siege S-7 — `probe["evaluated"]` is the POSITIVE twin of `no_predicate`, and it is a
    deliberately DIFFERENT question from `cov.wit_verified`. `wit_verified` asserts "bytes
    off DISK + a predicate evaluated", which is false for a kind=exec exit-clause witness —
    the shape return-convention.md's own worked example and every mandated fix-agent
    receipt use — even though a comparison really did run. The SUPERSEDES witness-evidence
    rule consults this instead; keying it on `wit_verified` would have made that exec
    exit-clause shape unsupersedable on the PASS leg, where the comparison is the whole
    check. **The two legs ask it differently, and QG-r2/S2 is why.** On the PASS leg the
    question is "did a predicate evaluate to a result AT ALL", and both PASS sites set the
    flag where a comparison really runs. On the FAIL leg that question is too weak — that
    leg raises at exactly one site, so the flag is set only when the result could REACH it
    (`pattern and exit_success`), which withholds it from the exec exit-clause shape there.
    Write-only here, exactly like `no_predicate`: nothing this function decides reads it.

    DEFERRED (#474 §3): a witness carrying ran=SKIPPED: is Tier-1-legal on a PASS and
    Tier-2 never evaluates it, so a reviewer can still obtain a PASS whose witness was
    never tested. That is a designed Cairn-routed deferral, not a fall-through; rejecting
    it is a receipt-shape contract change. Carried on GH #510 — split out of "the
    resolution issue" when #501 closed, because it is a DIFFERENT subject and leaving it
    pointed at a closing issue would have been the third repetition of the deferral chain
    that produced #501's own defect."""
    if not witness["ran"].startswith("TRACE#"):
        return True
    art_name, _ = witness_art_name(witness, cited, verdict)
    if art_name is None:
        return True
    if body_text is None:
        return True  # reproduces lint.py `if art_name not in artifact_bodies: return`
    kind = witness["kind"]
    expect_fail = witness["expect_fail"]
    body = body_text
    if probe is not None:      # SIEGE-C3 — see the docstring. Write-only.
        # The DERIVATION is the discriminator; `kind` only picks the reason code. An
        # `if kind == "lint" … elif <derivation>` shape (the original) short-circuits the
        # derivation for EVERY lint witness, including one carrying a /regex/ or
        # "literal" expect-fail — which falls through to the shared body predicate below
        # and really does run against the disk bytes. That mis-billed the only lint
        # witness in the committed corpus.
        if _expect_fail_pattern(expect_fail, witness.get("pattern")) is None:
            probe["no_predicate"] = ("lint-kind-unimplemented" if kind == "lint"
                                     else "exit-clause-not-a-body-predicate")
    if verdict == "FAIL":
        # tier2_verify_fail (lint.py:377-390)
        exit_m = re.search(r"exit=(-?\d+)", cited["args"])
        # SIEGE-R2BA-3 — receipt-authored exit code.
        exit_success = exit_m and _receipt_int(exit_m.group(1), "TRACE exit=") == 0
        # #474 / S4: the FAIL site too — a behaviour change, not a no-op. Today
        # expect_fail == "match" ⇒ pattern is None ⇒ content_match always False, so a
        # grep + EXEC-cited + match FAIL receipt with exit=0 is rejected by "no evidence
        # of failure"; after this the predicate runs and that rejection stops firing.
        # The new behaviour is the conformant one; blast radius measured zero.
        pattern = _expect_fail_pattern(expect_fail, witness.get("pattern"))
        content_match = bool(pattern and re.search(pattern, body))
        if probe is not None and pattern and exit_success:
            # GH #501 / QG-r2/S2 — siege S-7's `evaluated`, keyed on the ONE question
            # DEC-29 admits: could this witness's result affect this leg's outcome. The
            # FAIL leg raises at exactly one site, `exit_success and not content_match`,
            # so the result can reach the outcome only when a body predicate was derived
            # (`pattern`) AND the cited entry's exit is 0. Everything else evaluated
            # nothing this leg could act on. Fail-CLOSED direction: a withheld
            # `evaluated` can only ever over-BLOCK.
            #
            # ⚠ DEC-29, twice over. The first form was `exit_m or pattern`; the second was
            # `exit_m`, the PRESENCE of an `exit=` token — a SHAPE, the forbidden key,
            # and nothing on this leg COMPARES it (`exit_success` is read only by the
            # raise below). The `exit_m` form closed only the arms where a pattern
            # exists: an exit-clause `expect-fail` (`exit!=0` / `exit=<N>`) derives no
            # pattern from `_expect_fail_pattern` at all, so `result_discarded` — which
            # is keyed on `pattern` — never fired for it either, and the SUPERSEDES
            # consequent that consumes this flag opened for a witness the census bills
            # `not-applicable (exit-clause-not-a-body-predicate)` on the same stderr
            # line: siege S-7(a), one `expect-fail` token over. The whole suite passed
            # with and without that hole, which is what an unpinned arm buys.
            # Pinned by test_501_fail_leg_exit_clause_expect_fail_cannot_retire on BOTH
            # kind=exec and ranged kind=grep (the key is the derivation, never the kind);
            # reverting this line to `exit_m` turns it RED.
            #
            # Scope: this branch is FAIL-leg-only. The PASS leg sets `evaluated` at its
            # own two sites, where a comparison really runs, so no PASS receipt's exit
            # code can move — the false-BLOCK risk this re-key was weighed against.
            probe["evaluated"] = True
        if probe is not None and pattern and not exit_success:
            # GH #501 — the companion withholding witness_art_name's docstring names.
            # The predicate ran against real bytes and its RESULT WAS THROWN AWAY, so no
            # verification happened however healthy the read was. Keyed on whether the
            # result could affect the outcome — NOT on the verdict and NOT on the witness
            # kind (DEC-29: both of those are shapes, and narrowing a guard by shape is
            # what reopened this class three times this session). Two ways to reach one
            # counter, so the counter name is not the whole reason and the code carries
            # the rest — the same idiom `empty-range` uses for past-eof/empty-file.
            probe["result_discarded"] = ("fail-leg-exit-nonzero" if exit_m
                                         else "fail-leg-no-exit-evidence")
        if exit_success and not content_match:
            raise LintError(
                f"Tier-2 FAIL: no evidence of failure — exit=0 AND body does not match "
                f"expect-fail {expect_fail} (weak positive-evidence check)"
            )
        return True
    # verdict == PASS — tier2_verify (lint.py:330-355)
    if kind == "exec":
        em = re.match(r"exit(!?=)(-?\d+)", expect_fail)
        if em:
            # SIEGE-R2BA-3 — both the receipt's expect-fail operand and the cited
            # entry's own exit= are receipt-authored integers.
            op, n = em.group(1), _receipt_int(em.group(2), "WITNESS expect-fail exit")
            exit_m = re.search(r"exit=(-?\d+)", cited["args"])
            if exit_m:
                if probe is not None:
                    probe["evaluated"] = True   # siege S-7 — a comparison really ran
                actual = _receipt_int(exit_m.group(1), "TRACE exit=")
                failed = (actual != 0) if op == "!=" else (actual == n)
                if failed:
                    raise LintError(
                        f"Tier-2: WITNESS expect-fail exit-clause matches actual exit={actual} "
                        f"(witness would have fired → PASS rejected)"
                    )
            return True
    # regex / literal expect-fail
    pattern = _expect_fail_pattern(expect_fail, witness.get("pattern"))
    if probe is not None and pattern:
        probe["evaluated"] = True          # siege S-7 — see the `evaluated` note above
    if pattern and re.search(pattern, body):
        raise LintError(
            # SIEGE-R2BA-4 — the NAME is escaped; the PATTERN deliberately is not (a
            # backslash is ordinary in a regex source, so escaping it would change how
            # in-spec receipts render — see _show_path).
            f"Tier-2: WITNESS expect-fail regex /{pattern}/ matches body of "
            f"{_show_path(art_name)} (witness would have fired → PASS rejected)"
        )
    return True


def _read_cited_range(path: pathlib.Path, cited, witness=None, meter=None, raw=None):
    """Read ONLY the cited #L<a>-L<b> (line) / #B<a>-B<b> (byte) range from disk.
    Deliberate (M2): lint.py's inline tier2_verify reads the WHOLE body, but the disk
    reader reads only the cited range (fixture-4(g)-guarded). READ/WROTE entries carry
    no #range → read whole file (the grep-on-READ/WROTE path; not in natural corpus).

    #474 / D4: `witness` is optional-with-default so the four existing two-argument call
    sites keep today's cited-only behaviour verbatim. It is passed ONLY when
    witness_art_name sourced the artifact from the payload (`witness if from_payload
    else None`), which is what keeps artifact and range inseparable.

    SIEGE-R2BA-2: `meter` is an optional out-parameter (a dict — the `found`/`cov`/`probe`
    idiom, optional-with-a-default so none of the existing call sites moves). On the #B
    branch it records `raw_bytes`, the length of the RAW slice actually read, which is
    what tier2_witness's 4 KiB cap must measure. Before this, that caller re-derived the
    number with its OWN `resolved.read_bytes()[a-1:b]` — a THIRD independent read of an
    attacker-named file, materialising whole what the seek below never materialises.

    SIEGE-R2BA-1: `raw` is the ARTIFACTS leg's already-hashed buffer for this same name,
    or None. When it is present, `path` is used only for MESSAGES — every branch below
    slices the CARRIED bytes, so the predicate runs against exactly what was hashed
    rather than against whatever the name resolves to on a second, later read."""
    if witness is not None and witness.get("range_kind") is not None:
        kind, a, b = witness["range_kind"], witness["range_a"], witness["range_b"]
        return _slice(path, kind, a, b, meter, raw)
    r = parse_out_range(cited["args"])
    if not r:
        return _read_text_lossless(path, raw)
    return _slice(path, r.kind, r.start, r.end, meter, raw)


def _read_text_lossless(path: pathlib.Path, raw=None) -> str:
    """#486 fixer / F3 — THE text reader for a cited artifact body, guarded.

    Both text-decoding sites (this module's rangeless whole-file read and _slice's #L
    branch) go through here, so the guard cannot be added to one call site and missed at
    the other. One non-UTF-8 byte in a cited artifact — ordinary mojibake in a build log
    or a findings file — raised UnicodeDecodeError straight through tier2_witness (whose
    only handler is `except WitnessTimeout`) and out of the CLI as a traceback.

    The decode stays LOSSLESS on purpose: `errors="replace"` here would silently break
    the 4 KiB cap's byte-count equality, which explicitly depends on this read having no
    `errors=` ("so there is NO U+FFFD inflation on this path"). The #B sibling keeps its
    errors="replace" because its cap measures the RAW bytes, not the decoded string.

    SIEGE-R2BA-2 — bounded. `Path.read_text()` is exactly `self.open(mode="r")` followed
    by an UNBOUNDED `.read()`, so a 4 GiB cited artifact was materialised whole on this
    leg too. `fh.read(n)` on the SAME handle keeps the decoding and the universal-newline
    translation byte-identical for every file at or under the ceiling — which is the
    property that matters, because the #L slice and the 4 KiB cap's byte count are both
    computed from this string. Counted in DECODED CHARACTERS here and in bytes on the
    ARTIFACTS leg: both are ceilings on materialised data, not an accounting identity.

    SIEGE-R2BA-1 — when `raw` is the ARTIFACTS leg's carried buffer, it is decoded HERE
    instead of the file being read again. `io.TextIOWrapper(io.BytesIO(raw))` and not
    `raw.decode()`: `Path.open("r")` applies the locale encoding AND universal-newline
    translation, so a plain decode would silently change the #L slice (and therefore the
    4 KiB cap's byte count) for every CRLF artifact. The wrapper is the same object
    `open()` returns, over bytes instead of a file descriptor. Already inside the
    ceiling — the buffer was read through _read_capped — so no second cap test."""
    try:
        if raw is not None:
            return io.TextIOWrapper(io.BytesIO(raw)).read()
        with path.open("r") as fh:
            text = fh.read(ARTIFACT_READ_CAP + 1)
    except UnicodeDecodeError:
        raise LintError(
            # SIEGE-C2 — `path` is a RESOLVED path under a root the reviewed subagent
            # owns, and this bullet is the one an attacker can reach with a cited
            # symlink to a non-UTF-8 file: escaped, so it cannot forge a census line.
            f"Tier-2: cited artifact {_show_path(path)} is not valid UTF-8 "
            f"(the #L range reader decodes losslessly; range not read)")
    except (OSError, MemoryError) as e:
        # SIEGE-R2BA-2 — this reader had NO read guard at all: tier2_witness catches only
        # LintError, so an unreadable/vanished cited artifact escaped the CLI as a
        # Traceback printed after the census, the same shape F3 closed one leg over.
        # Ordered AFTER UnicodeDecodeError, which is a ValueError and not caught here —
        # the ordering is documentation, not disambiguation.
        raise LintError(
            f"Tier-2: cited artifact {_show_path(path)} unreadable ({_strerror(e)})")
    if len(text) > ARTIFACT_READ_CAP:
        raise LintError(
            f"Tier-2: cited artifact {_show_path(path)} exceeds the Tier-2 read budget "
            f"({ARTIFACT_READ_CAP} B; range not read)")
    return text


def _slice(path: pathlib.Path, kind, a, b, meter=None, raw=None):
    """The 1-based-inclusive range read shared by the cited-range and witness-payload
    sourcings (#474/D4) — one reader, so the two cannot drift.

    SIEGE-R2BA-1: `raw`, when present, is the ARTIFACTS leg's already-hashed buffer and
    is sliced INSTEAD of opening `path`."""
    # Ranges are 1-based; a<1 is malformed, clamp to 1 so `[a-1:b]` never slices from
    # the END (a=0 → [-1:b], an empty/wrong body that silently bypasses the witness).
    if a < 1:
        a = 1
    # Both #L (line) and #B (byte) ranges are 1-based INCLUSIVE: #L1-L5 = 5 lines,
    # #B1-B5 = bytes 1..5 = 5 bytes (parallel symmetric forms per return-convention).
    if kind == "L":
        lines = _read_text_lossless(path, raw).splitlines(keepends=True)
        return "".join(lines[a - 1:b])  # 1-based inclusive
    # SIEGE-R2BA-2 — SEEK, do not slurp. `path.read_bytes()[a-1:b]` materialised the
    # WHOLE attacker-named file to hand back at most a few KiB of it; the seek reads
    # exactly the range. Bytes returned are byte-identical to the old slice for every
    # file (including a past-EOF start, which yields b"" either way).
    #
    # The read length is bounded a SECOND time, at WITNESS_SPAN_CAP + 1, so this reader
    # is safe on its own terms rather than only because Tier-1 happens to have bounded
    # `b - a` already (check_span_bound, both span sites). The +1 is what keeps the
    # AUTHORITATIVE cap in tier2_witness able to see an over-budget range and reject it:
    # it compares `> WITNESS_SPAN_CAP`, so it must be able to observe CAP+1.
    if raw is not None:
        # SIEGE-R2BA-1 — slice the carried, already-hashed buffer. Truncated at the same
        # CAP+1 as the seek below so the two branches hand tier2_witness's authoritative
        # cap the same number for the same range.
        sliced = raw[a - 1:b][:WITNESS_SPAN_CAP + 1]
    else:
        with path.open("rb") as fh:
            fh.seek(a - 1)
            sliced = fh.read(max(0, min(b - a + 1, WITNESS_SPAN_CAP + 1)))
    if meter is not None:
        meter["raw_bytes"] = len(sliced)
    return sliced.decode("utf-8", errors="replace")  # 1-based inclusive


def _bill_witness_evaluation(cov, probe, body_text, ambiguous):
    """SIEGE-C3 — the ONE place `wit_verified` is set, so states (a) and (b) cannot
    disagree about what "verified" means. Returns the WITHHOLDING REASON — `"empty"` for
    DEC-26's zero-bytes case, `"discarded"` for GH #501's thrown-away FAIL-leg result —
    which is the caller's signal to bucket the item (DEC-28); None on every other path,
    including the `no_predicate` arm, which buckets its own. It became a reason rather
    than a bool when #501 added the second way to reach "read fine, verified nothing":
    the two land in DIFFERENT sub-counts, so a bare True could no longer say which.

    `wit_verified = 1` asserts that a predicate ran against the bytes read from disk —
    design :1188-1190's ARTIFACTS-leg analogue, "bytes off disk + predicate evaluated TO A
    RESULT", which INCLUDES the run whose result is a FAIL. A call that reached a clean
    return without evaluating anything (verify_witness's `probe` says which shape) is not
    that: before this, `lint:<rule> expect-fail=exit!=0 ran=TRACE#1` over a body an
    equivalent grep witness correctly rejects rendered `artifacts 1/1 witness 1/1 …`,
    BYTE-IDENTICAL to a genuine verification.

    The item leaves the applicable set and is billed `not-applicable` with a literal code
    — the same idiom as D8.2 sub-decision 5's `verdict-not-pass-fail` (`witness 0/0` plus
    a code), rather than `witness 0/1`, which would read as "a check that could have run
    and did not" when the truth is that this linter implements no such check.

    TELEMETRY ONLY, deliberately: the EXIT CODE for these receipts does not move. Making
    an unimplemented `lint:` rule a hard FAIL is a new gate — it would flip committed
    fixtures and the mandated red-team witness shapes — and is a separate decision.

    DEC-26 — a cited range that delivered NO BYTES withholds the claim for the OTHER way a
    call reaches here having consulted zero disk bytes: a predicate that exists and ran,
    against nothing. A cited range PAST EOF resolves to no bytes, `re.search` over `""`
    cannot match, and the run rendered `artifacts 1/1 witness 1/1 … wrong-name 1
    (rangeless-grep-payload)`, exit 0 — while the byte-identical receipt citing an
    IN-RANGE span of the same file fires the predicate and exits 1. Same file, same
    predicate, opposite census. `_reject_empty_grep_body` does not cover it (that guard is
    keyed on a RANGED payload, and its rangeless blind spot PRE-DATES this branch —
    corrected D5, GH #495). Closing the guard would move the exit code; this moves only
    the claim.

    DEC-28 half 2, CORRECTED — C1-R2-S1. THE BUCKET KEYS ON THE RESOLUTION; THE RATIO
    DOES NOT. `a2968a0` read the ruling as also moving the RATIO and made the guard
    `ranged and body_text == ""`, so a RANGELESS citation over a genuinely 0-byte file was
    billed `wit_verified = 1` — the argument being that the whole file WAS delivered and
    the predicate examined exactly the bytes the citation named. That argument is about
    CITATION FIDELITY. `wit_verified`'s contract, three paragraphs above, is "bytes off
    disk + predicate evaluated TO A RESULT": zero bytes came off disk, `re.search(p, "")`
    cannot match for ANY p, so the witness structurally could not fire and the census
    asserted a verification that did not happen. Measured: the rangeless-payload receipt
    over an EMPTY findings file and the same receipt over a 900-line one rendered a
    BYTE-IDENTICAL census, and `6b234b5` — six commits earlier — read `witness 0/1` for
    the first. That is `43e5a50`'s subject verbatim ("a witness that consults zero disk
    bytes is no longer billed `witness 1/1`") and the #474 grudge class by name: a
    predicate that could not fire, reported clean. So the guard is `body_text == ""`,
    ranged or not — and this function is not GIVEN `ranged`, so the ratio cannot start
    reading it again without the caller being changed too.

    What DEC-28 half 2's argument does buy is kept, and kept where it belongs — in the
    BUCKET rather than the ratio. `_bill_witness_billing` bumps `empty-range` with a
    reason code: `past-eof` for a ranged citation (a range that addressed no bytes lies
    beyond the file's content — a 0-byte file has no line 1 either) and `empty-file` for a
    rangeless one. A genuinely-empty file is therefore no longer described as a citation
    defect, while the census still says no verification happened. (`return-convention.md`'s
    one-line gloss of `empty-range` reads "a range past EOF" and wants widening to "a
    citation that delivered no bytes" — a chunk-2 edit, flagged not made.)

    NOT keyed on the witness KIND, and that is still the whole point. Narrowing by SHAPE
    (e.g. "only a rangeless grep payload") was tried and REVERTED: it silently restored
    `witness 1/1` for a RANGED kind=exec citation past EOF — the shape the build pipeline's
    own mandated witness uses — which is the exact fail-open DEC-26 closed. Zero delivered
    bytes is a property of the READ, so kind=exec, kind=lint, a ranged grep and a rangeless
    read are all withheld alike.

    DEC-28 half 1 — WHERE A WITHHELD ITEM IS REPORTED. A withheld item stays in the
    applicable denominator and renders `witness 0/1`; before DEC-28, for every shape except
    the rangeless grep payload it landed in NONE of the disjoint sub-counts, because none
    described "resolved, applicable, predicate ran against zero delivered bytes" — the
    shape tier2_witness's docstring below declares forbidden. The maintainer ruling adds the
    sixth sub-count `empty-range` for exactly that state, bumped by `_bill_witness_billing`
    (not here) so it can be ordered behind the sub-counts an item may ALSO earn: `wrong-name`
    for the rangeless grep payload, `ambiguous` for a cross-root name. This function returns
    the withheld flag rather than bumping, which is what keeps the sub-counts disjoint.

    The affected population GREW when verify_witness's probe stopped billing every
    kind=lint witness `no_predicate`: a lint witness carrying a body regex over an empty
    body used to land in `not-applicable` and now lands in `empty-range`. That is the
    correct trade (the old billing asserted no predicate ran on runs where one did).

    UNLIKE the `no_predicate` arm this one stays IN the applicable set, rendering
    `witness 0/1`: a check DOES structurally exist here, so 0/1's reading — "a check that
    could have run and did not" — is the true one, and design :1239-1240 already pins
    `0/1` as the normal shape for a leg that determined applicability and did not verify.
    The item keeps whatever disjoint sub-count its shape earns (`wrong-name` for the
    rangeless payload above), which is where it is reported — and for THAT shape the
    partition now holds on both exits, because `_bill_witness_billing` runs both bumps
    together on the clean-return AND the raise path. Calling this function alone, or
    bumping `wrong-name` after a `raise`, re-opens it. Every OTHER withheld shape earns
    `empty-range` there, so the partition holds for all of them. `partial` is not set by
    this decision: a withheld claim is not a truncated walk (the raise path's caller sets
    it where it belongs).

    `== ""` and not falsiness: `body_text is None` means "no body was supplied at all",
    which verify_witness returns clean on as documented lint.py parity, and that
    disposition is not this decision's to change (it is billed VERIFIED here, as before —
    `None == ""` is False, so the withholding arm cannot swallow it). It is unreachable
    from tier2_witness, whose reader always returns a str.
    """
    code = probe.get("no_predicate")
    if code is None:
        if body_text == "":
            return "empty"       # DEC-28 — withheld; _bill_witness_billing buckets it
        if probe.get("result_discarded"):
            # GH #501 — the OTHER way a call reaches here having verified nothing: bytes
            # came off disk and a predicate ran, but the FAIL leg discarded the result
            # (see verify_witness). Ordered AFTER the zero-bytes test on DEC-28's
            # tie-break — when two descriptions fit, count the EARLIER and more
            # recoverable fact, and a citation that delivered no bytes is both.
            return "discarded"
        cov.wit_verified = 1
        return None
    if ambiguous:
        # C1-R1-S1 — THE SAME GUARD `empty-range` ALREADY HAS, carried to the sibling arm
        # the author who wrote it did not reach. `ambiguous` is bumped at RESOLUTION time,
        # before applicability is finally known; this arm then cleared `wit_applicable`
        # and bumped `not-applicable`, so ONE item landed in two of the sub-counts
        # `return-convention.md:271` ships as normative disjoint ("An item that already
        # earns `ambiguous` or `wrong-name` is reported only there") — on a line whose
        # `witness 0/0` says the item is not in the applicable set at all, while
        # `ambiguous` is defined as a sub-count OF that denominator.
        #
        # The resolution is design :1178-1180's tie-break, the same one `wrong-name` and
        # `empty-range` already take: when two descriptions fit, count the EARLIER and
        # more recoverable fact. So the item stays applicable and renders
        # `witness 0/1 … ambiguous 1` — `0/1` reads "a check that could have run and did
        # not", which is true here, and the reason it did not is on its own stderr note.
        # Under --strict the ambiguity raises before any of this, so this arm is live
        # only on the non-strict diagnostic path — which is the path the handoff
        # prescribes for READING the census.
        return None
    cov.wit_applicable = 0
    cov.bump("not-applicable", code)
    return None


def _bill_witness_billing(cov, probe, body_text, rangeless_grep, ranged, ambiguous,
                          derived_name=False, bound=True):
    """The witness leg's WHOLE census contribution for one evaluated item, so states (a)
    and (b) — clean return and LintError raise — cannot bill differently.

    The two bumps are ORDER-DEPENDENT and must stay together: `_bill_witness_evaluation`
    decides applicability, and the `wrong-name` bump is legal only for an item that is
    still IN the applicable set. Splitting them is what produced both halves of the
    disjointness break this pair closes:
      * The `wrong-name` bump used to run unguarded, so an item _bill_witness_evaluation
        had just REMOVED from the applicable set (rangeless grep + an exit-clause
        expect-fail, which derives no body predicate) landed in `not-applicable` AND
        `wrong-name` — two of the sub-counts design :1175 declares disjoint, on a line
        whose `witness 0/0` says the item is not in the applicable set at all. Design
        :1212: a NOT-APPLICABLE item is reported ONLY in `not-applicable`.
      * The `wrong-name` bump used to sit AFTER the try/except, so the `raise` in state
        (b) skipped it. A rangeless grep witness over 0 bytes whose predicate RAISED was
        billed with every sub-count at 0 — the shape tier2_witness's docstring declares
        forbidden, on a run where the predicate provably ran. Recording it on the raise
        path is the same rule the `ambiguous` bump already follows ("bumped BEFORE the
        --strict raise, so the item is recorded on exactly the run the raise truncates").
        C1-R2-S1: a rangeless citation delivering zero bytes is withheld like every other
        zero-byte read, so that shape reads `witness 0/1` and earns `wrong-name` here.
        The raise-path bump is what this bullet is about and it is unchanged.

    DEC-28 half 1 — the `empty-range` bump is the THIRD member of the same ordered
    sequence, and its position is what keeps :1175's sub-counts disjoint. A withheld item
    can ALSO be a rangeless grep payload (a rangeless payload citing an EXEC `out=` range
    past EOF is exactly DEC-26's own repro) or cross-root `ambiguous` (bumped at
    resolution, before the read). Both of those already describe the item, and design
    :1178-1180's rule — when two descriptions fit, count the earlier and more recoverable
    fact — makes them win: `empty-range` is the bucket for a withheld item that earns NO
    other sub-count, which before DEC-28 was every shape but the rangeless payload. Hence
    `elif`, and hence the explicit `ambiguous` argument: `rangeless_grep` already folds in
    `not notes_ambiguous`, so without a second signal an ambiguous past-EOF item would be
    double-bumped.

    C1-R2-S1 — `ranged` reaches THIS function and no longer reaches the ratio one function
    down, because it is a fact about the CITATION while the ratio is a fact about the READ.
    It survives here as the `empty-range` REASON CODE, which is where DEC-28 half 2's
    argument belongs: `past-eof` when the citation named a range that addressed no bytes,
    `empty-file` when the whole file was delivered and the whole file is 0 bytes. Two ways
    to reach one counter, so — unlike `ambiguous` — the counter name is not the whole
    reason and the code carries the rest.
    """
    withheld = _bill_witness_evaluation(cov, probe, body_text, ambiguous)
    # `and not notes_ambiguous` is folded into `rangeless_grep` by the caller — design
    # :1178-1180: under non-strict an item can satisfy both descriptions, and the ruling
    # is that it counts `ambiguous` and not `wrong-name` (the ambiguity is the earlier and
    # the recoverable fact). Under --strict the ambiguity raises before this point, so the
    # guard is live only on the non-strict path — where, without it, :1175's disjointness
    # fails on exactly one shape.
    # D8.3 — the rangeless payload is NOT "no check exists": the predicate really ran,
    # against the CITED TRACE entry rather than the payload token, i.e. against a file the
    # witness never names. VERIFIED and counted wrong-name, so the one class where a
    # predicate provably runs against an undeclared file is not filed under "not
    # applicable" and erased from every counter a floor can act on. (Retired in commit 2
    # if corrected D5 lands — S3.)
    if rangeless_grep and cov.wit_applicable:
        # siege S-2 — `derived_name` is the SAME class one kind over, and it was billed
        # `witness 1/1` with all six sub-counts at 0. The `wrong-name` bump was gated on
        # `kind == "grep"`, but `kind=lint` is the kind under NO membership rule at all:
        # `ran=` verb binding constrains only exec/grep (lint_receipt), the D6
        # ARTIFACTS-membership rule is scoped to a ranged grep payload, and
        # `_reject_empty_grep_body` is grep-only. So swapping `grep:` for `lint:` moved a
        # predicate onto an undeclared, never-hashed file AND produced a CLEANER census
        # than the honest grep run it replaced. The counter's meaning — "the predicate
        # ran against a file the witness never names" — was always kind-independent; only
        # the gate was not.
        cov.bump("wrong-name", "rangeless-grep-payload")
        if not bound:
            # siege S-5 — the counter used to fire on SHAPE alone: it read `1` identically
            # whether the read was bound to the artifacts leg's hashed-AND-MATCHED buffer
            # or not, so a floor built on it (#488's proposal) would fire on clean
            # receipts and pass dirty ones. `unhashed-body` is the DISAGREEMENT half, and
            # it is a code rather than a second increment because it describes the same
            # item — splitting it into its own counter would re-open the disjointness
            # this pair exists to keep. A note on stderr carries the same fact for a
            # reader (tier2_witness), because a census with no consumer (#499) is not a
            # channel on its own.
            cov.note_code("wrong-name", "unhashed-body")
    elif derived_name and cov.wit_applicable:
        # siege S-2 — the same counter for the same fact, one kind over. The caller folds
        # `not bound` into `derived_name`, so reaching here means the predicate really did
        # run against a file no ARTIFACTS line hashed. Its own code, because the SHAPE
        # differs (a lint rule name where a grep payload would be) and an operator reading
        # the census has to be able to tell which one they are looking at.
        cov.bump("wrong-name", "unbound-trace-name")
    elif withheld == "empty" and not ambiguous:
        cov.bump("empty-range", "past-eof" if ranged else "empty-file")
    elif withheld == "discarded" and not ambiguous:
        # GH #501 — the SEVENTH sub-count, and the last member of the same ordered
        # sequence for the same reason the sixth was: an item that already earns
        # `wrong-name`, `ambiguous` or `empty-range` is reported only there (design
        # :1178-1180's tie-break), so this is the bucket for a withheld item that earns
        # no earlier one. Without it the 8 frozen-corpus receipts measured at
        # witness_art_name land in NONE of the disjoint sub-counts on a `witness 0/1`
        # line — the state tier2_witness's docstring declares forbidden, which is exactly
        # the C01 break DEC-28 closed one counter earlier.
        cov.bump("discarded", probe["result_discarded"])


def _carry_should_have_bound(art_name, bodies):
    """#488 inquisitor/AV1 (state) — True when the witness's cited name is a SPELLING of
    a name the artifacts leg hash-verified, so a `bodies` miss on BOTH keys is proof the
    resolution changed mid-run rather than evidence that nothing was hashed.

    PURELY LEXICAL, and that is the whole point: the event being detected is that the
    FILESYSTEM moved between the two legs, so any test that goes back to disk is testing
    the post-swap tree and cannot see it. `PurePosixPath` is the normaliser rather than
    `os.path.normpath` because it collapses `./`, `//` and a trailing `/` — the forms
    that name the same file under any tree — while leaving `..` alone: collapsing `..`
    lexically is unsound across a symlinked parent and would make this fire on two names
    that genuinely resolve differently.

    Only the STRING keys of `bodies` are considered; those are the DECLARED ARTIFACTS
    names, and only hash-MATCHED entries are ever carried (see the write site). The Path
    keys are the realpaths, which the caller has already consulted directly.

    Scope, stated because it bounds what the caller's raise can claim: an ABSOLUTE cited
    name (§3.2's mandated form) never lexically equals a §3.1-relative declaration, so a
    swap against a name cited in THAT form is not detected here and still degrades to the
    independent read the census bills `unhashed-body`. Closing that half needs the cited
    name relativised against the roots, which reintroduces a cross-root collision this
    detector has no way to adjudicate; it is left open deliberately rather than guessed.

    MUST NOT RAISE on any input: `art_name` is receipt-controlled and `bodies` is a
    caller-supplied out-param, and a False here costs the old behaviour while an
    exception costs the verdict."""
    try:
        want = pathlib.PurePosixPath(art_name)
    except Exception:
        return False
    for k in bodies:
        if not isinstance(k, str):
            continue
        try:
            if pathlib.PurePosixPath(k) == want:
                return True
        except Exception:
            continue
    return False


def tier2_witness(witness, trace, root, strict, verdict, cov=None, bodies=None,
                  probe_out=None, notes_out=None):
    """Part 2. Resolve the cited TRACE artifact via resolve_base, read ONLY the cited
    #L/#B range from disk, then call the shared verify_witness. Absent witness file:
    path-shaped + --strict -> FAIL; else UNVERIFIABLE (non-fatal). Returns UNVERIFIABLE
    notes; raises LintError on FAIL (incl. verify_witness's byte-identical messages).

    #486 / D8 — `cov` is an optional _Coverage collector, optional with a default for
    the same reason tier2_artifacts' is. Round-2/S1: four of the counters (`unreached`,
    `not-reachable`, `ambiguous`, `not-applicable`) are BOTH-LEGS counters, so this leg
    wires all four and not only the two it alone can bump (`wrong-name`, and DEC-28's
    `empty-range`) — a `witness 0/1` line with every sub-count at 0 puts an item in the
    applicable set that belongs to none of design :1175's disjoint sub-counts, and this is
    the leg #486's headline figure (0 of 14 witness resolutions) is about.

    SIEGE-R2BA-1 — `bodies` is tier2_artifacts' carry: the buffers that leg HASHED AND
    MATCHED, keyed under BOTH the declared NAME and the RESOLVED REALPATH. When the cited
    artifact matches either key, the predicate below is evaluated against that buffer and
    the file is NOT read again. Both keys are load-bearing and neither is redundant: the
    two legs derive their names from different receipt lines (ARTIFACTS vs. the cited
    TRACE entry's args), so a NAME-only key missed on `./f.md` vs `f.md`; and a
    REALPATH-only key missed whenever the same declared name RESOLVES differently between
    the legs — the mid-lint symlink swap this carry was written against, where missing is
    a fail-open. See the write site.

    Why that is a security fix and not a micro-optimisation: this leg used to do its OWN
    resolve_base and its OWN read of the same name, and the #B cap check did a third, so
    nothing tied the sha256 that was verified to the body the expect-fail predicate ran
    against. Measured on this tree with a background process alternating a symlink
    between the real findings file and a sanitised copy, 60 of 300 runs of the MANDATED
    `--tier2 --strict --root <dispatch-root>` line returned exit 0 with
    `TIER2-COVERAGE: artifacts 1/1 witness 1/1 …` — a census byte-identical to a genuine
    verification — on a receipt whose real findings file fires the predicate. The
    reviewed subagent owns the dispatch root and can leave such a process behind; an
    inotify-triggered flipper raises the 20% to near-certainty.

    WHAT IS NOT CLOSED, precisely:
      * The RANGELESS grep path has no ARTIFACTS-membership rule (its name comes from
        the cited READ/WROTE entry, which #412 deliberately does not gate), so such a
        name need never have been declared at all. It is bound whenever it RESOLVES to a
        file the artifacts leg hashed and matched (the realpath key above is what makes
        that work regardless of how the two lines spell it), and unbound — keeping its
        single independent read — when it resolves anywhere else. Every RANGED read is of
        a declared name: Tier-1 requires both the payload artifact and the EXEC out=
        artifact to be in ARTIFACTS.
        So the carry covers every read of a name that RESOLVED AND MATCHED on the
        artifacts leg — NOT "every read a sha256 was ever claimed about". A declared name
        the artifacts leg could not resolve is recorded in no carry (the write sits after
        the comparison, and the unresolved arm `continue`s before it), so if that name
        starts resolving here it gets an independent, never-hashed read.
      * RESOLUTION is still independent. This leg re-runs resolve_base, so the census
        classification (resolved / unresolved / ambiguous) and the path rendered into
        messages still come from a second stat walk and may disagree with the artifacts
        leg's. That residual is FAIL-CLOSED IN THE STOPS-RESOLVING DIRECTION ONLY: a name
        that stops resolving between the legs becomes UNVERIFIABLE (or, for a path-shaped
        name under --strict, a FAIL), never a silent pass. The converse is NOT closed —
        a name that resolves HERE but not on the artifacts leg is read independently and
        still billed `witness 1/1`, visible only as that leg's `artifacts N-1/N` plus its
        `unreached`/`not-reachable` sub-count. Refusing to read such a name would move the
        exit code on a receipt-controlled predicate; that is a new gate and a separate
        decision (the natural companion to #488's proposed --strict floor).
        What can no longer diverge is the BYTES, for the names the carry holds.
      * A caller that does not pass `bodies` — every direct in-process importer
        (_gen.py, the measure_*_corpus.py scripts, the direct-call tests) — is unbound
        exactly as before. _verify_single and --selftest wire it.

    siege S-7 — `probe_out` is verify_witness's `probe` dict, surfaced to the caller (the
    same optional out-param idiom as cov/bodies/found/meter, so no existing call site
    moves). `_verify_single` reads `evaluated` from it to enforce the SUPERSEDES
    witness-evidence rule's Tier-2 half — "Tier-2 then verifies the witness normally"
    (return-convention.md § SUPERSEDES), which was the half nothing checked."""
    with _witness_bound():
        try:
            if not witness["ran"].startswith("TRACE#"):
                if cov is not None:
                    cov.bump("not-applicable", "ran-not-trace")
                return []
            idx = _trace_idx(witness["ran"])
            if not 1 <= idx <= len(trace):
                # D8.2 — deliberately NO census code. Unreachable from the CLI: lint_receipt
                # raises "WITNESS ran=TRACE#N does not resolve" first, landing on the
                # not-reached (tier1-reject) shape. The census is complete AS SCOPED TO THE
                # CLI PATH and is not complete for a direct in-process call that skips
                # lint_receipt — a caller shape no criterion covers today, named so a future
                # consumer does not inherit the gap silently.
                return []
            cited = trace[idx - 1]
            art_name, from_payload = witness_art_name(witness, cited, verdict)
            if art_name is None:
                # C1-R3-S1 (freeze-guard revision 2) — "the linter sourced nothing AND the
                # receipt has no way to make it source something". Both halves are needed,
                # and the second is why this is not simply `art_name is None`:
                #
                #   * On the FAIL leg derive_art_name is EXEC-only (see its docstring), so
                #     a witness citing a READ or a WROTE can never yield a name however it
                #     is written. The only "remedy" is to cite an EXEC, which the
                #     research/judge dispatches this shape is the DEFAULT for cannot
                #     produce — they have no shell. Genuinely unsatisfiable ⇒ exempt.
                #   * On the PASS leg the same None means the receipt cited something that
                #     yields no name (e.g. a DISPATCHED entry) while READ, WROTE and an
                #     EXEC with out= all DO yield one. That is an ordinary in-receipt
                #     remedy, so the consequent must stay armed. Revision 1 set the flag
                #     unconditionally and silently exempted this case, which was gated
                #     before the whole C1-R3-S1 change.
                #
                # ⚠ The `verdict` test here is NOT the verdict standing in for a shape —
                # that is the mistake revision 1 was reverted for, and DEC-29 forbids it in
                # a GUARD. This is an EXEMPTION, and narrowing an exemption can only ever
                # produce a false BLOCK, never a fail-open. It reads derive_art_name's own
                # documented PASS/FAIL asymmetry, which is the thing that decides whether a
                # remedy exists. Do not widen it back to bare `art_name is None`.
                # GH #501 NARROWED THIS, and the narrowing is the point: the FAIL leg now
                # SOURCES a ranged grep payload, so the shape that used to dominate this
                # branch (the mandated red-team witness) no longer reaches it at all. What
                # is left on the FAIL leg is a witness with no range for the leg to source
                # AND no EXEC out= to fall back to — still genuinely unsatisfiable, still
                # exempt. Widening it back to bare `art_name is None` re-exempts the PASS
                # leg's remediable case; narrowing it further would over-BLOCK only.
                #
                # SIEGE-S1 — #501 retired MORE of this exemption than the paragraph above
                # claimed. A `kind=grep` payload carries an `#<range>` SLOT, and since
                # #501 `witness_art_name` sources that slot on EITHER leg — so a
                # rangeless grep reaches here because the author OMITTED the range, not
                # because the leg cannot source one. That is an ordinary in-receipt
                # remedy (write `grep:<artifact>#L<a>-L<b>`), and the exemption's own
                # stated antecedent — "the receipt has no way to make it source
                # something" — is false for it. Measured on `ba482e2`: two receipts
                # differing only in the VERDICT token, witness `grep:evidence.log
                # expect-fail=/zzz-absent/ ran=TRACE#1`, cited file ABSENT from disk,
                # exited 1 (PASS) / 0 (FAIL) — the FAIL leg retiring its predecessor on a
                # witness naming a file that does not exist.
                #
                # ⚠ This narrows by `kind`, which DEC-29 forbids in a GUARD — and this is
                # not one. It is the EXEMPTION, where the direction reverses: narrowing
                # can only ever produce a false BLOCK (the paragraph above says so), and
                # the key is not the kind standing in for something else — it is the
                # literal availability of the remedy, since `kind=grep` is the ONE kind
                # whose payload has a range slot `witness_art_name` reads.
                #
                # WHAT IS LEFT EXEMPT, stated as measured rather than claimed to be a
                # live residue: through the CLI, on a receipt that actually carries a
                # SUPERSEDES, NOTHING. Tier-1 admits only `kind in {exec, grep}` for a
                # non-`none` SUPERSEDES (lint_v11_local), forces a `kind=exec` witness's
                # `ran=` to point at an EXEC, and forces EVERY EXEC entry to carry a
                # parseable `out=<artifact>#<range>` (check_exec_range_bound at :974) --
                # so `derive_art_name` names something on every FAIL-leg exec witness,
                # and the grep half is what this line closes. The branch STAYS because it
                # still guards two live shapes: a DIRECT in-process `tier2_witness` call,
                # which skips Tier-1 (the unit tests' own shape), and any future witness
                # kind whose payload has no range slot. Keeping it is fail-CLOSED;
                # deleting it moves the fail-open one layer down, onto whoever adds that
                # kind.
                _rangeable = witness.get("kind") == "grep"
                if probe_out is not None and verdict == "FAIL" and not _rangeable:
                    probe_out["unsourced"] = True
                # D8.5 — D4's single "NOT-EVALUATED" string folds onto TWO codes, because
                # this branch has two arms: the FAIL leg with no EXEC out= range, and a PASS
                # leg whose cited entry yields no name at all. Mapping both onto
                # fail-leg-no-range would mislabel the PASS-leg cases.
                if cov is not None:
                    # GH #501 RETIRED the `unreached (fail-leg-payload-not-sourced)` arm
                    # that used to stand here. C1-R3-F1 added it to stop the census
                    # calling a Tier-1-MANDATED check `not-applicable` while the FAIL leg
                    # declined to source it; now the leg sources it, so the shape the arm
                    # described cannot arrive — witness_art_name returns a name for every
                    # ranged grep payload on either verdict, and this branch is not
                    # entered. The honest rendering of the same receipts moved with the
                    # behaviour: they now report whatever their payload artifact really
                    # does (`not-reachable` when the bare basename resolves nowhere,
                    # `discarded` when it resolves and the FAIL leg throws the predicate
                    # result away). Measured pre/post with `measure_486_corpus.py` over
                    # the three enumerated frozen corpora, that is 10 and 8 receipts
                    # respectively — the 18 this arm held, redistributed with nothing
                    # left over (witness-leg `unreached` drops by exactly 18 and the
                    # code-less `unreached` population is byte-identical either side) —
                    # and no exit code moved.
                    #
                    # D8.5 — D4's single "NOT-EVALUATED" string still folds onto TWO
                    # codes: a FAIL leg with no range AND no EXEC out= range, and a PASS
                    # leg whose cited entry yields no name at all.
                    cov.bump("not-applicable",
                             "fail-leg-no-range" if verdict == "FAIL" else "no-art-name")
                return []
            if cov is not None:
                # S2 — applicability is a MEASURED fact from here on, so d becomes 1 only now.
                cov.wit_applicable = 1
            found = []
            refused = []
            resolved = resolve_base(art_name, root, found, refused)
            # #488 / T7 — same depth key, same counter, on the witness leg (§4). SITED
            # HERE, immediately after resolve_base and BEFORE the ambiguity block, for
            # the same reason that block's own `ambiguous` bump sits before its raise:
            # `--strict` raises out of it, and `--strict` is the MANDATED invocation
            # (quality-gate/SKILL.md:30). The name DID resolve, so §3.1 clause 2's "MUST
            # fire whenever a cited name resolves to a path below a root's top level"
            # binds on that run too. This mirrors the artifacts leg's placement exactly.
            #
            # Through `notes_out` ALONE, never `notes_refused` or the return value:
            # _verify_single DISCARDS this leg's return value (see the call site), and
            # every raise between here and the clean-path return drops it in this frame.
            _rel = (_below_top_level(resolved, root)
                    if resolved is not None else None)
            if _rel is not None:
                # Round-3/S1 — the artifacts leg's order and the artifacts leg's
                # no-raise envelope, for the artifacts leg's reasons. Both legs move
                # together deliberately: guarding one and not the other recreates the
                # leg asymmetry round-1/S2 already found and closed once.
                if cov is not None:
                    cov.bump("resolved-by-walk")
                _emit_walk_note(notes_out, art_name, _rel)
            if len(found) > 1:
                # #486 / D2 — same rule as the artifacts leg, its OWN wording. The two messages
                # differ because :893 and :1127 already differ ("path-shaped artifact …" vs
                # "witness artifact …") and message fidelity is load-bearing for the --eval
                # byte-diff (see verify_witness's docstring).
                if cov is not None:
                    # Round-2/S1 — the SAME counter and entry semantics as the ARTIFACTS
                    # leg's bump. Bumped BEFORE the --strict raise, so the item is recorded
                    # on exactly the run the raise truncates.
                    cov.bump("ambiguous")
                # SIEGE-C2 — _show_path, as on the artifacts leg and for the same reason.
                homes = ", ".join(sorted(_show_path(p) for p in found))
                # SIEGE-R2BA-4 — the NAME too, as on the artifacts leg.
                msg = (f"witness artifact {_show_path(art_name)} is ambiguous "
                       f"across roots ({homes})")
                if strict:
                    if cov is not None:
                        cov.partial = True
                    raise LintError(f"Tier-2 --strict: {msg}")
                notes_ambiguous = [f"AMBIGUOUS: {msg}"]
            else:
                notes_ambiguous = []
            if resolved is None:
                # #486 fixer / F4 — the SHARED disposition, not this leg's own. This is
                # the branch #486's headline figure is about (a witness artifact that
                # resolves under NO root; before this, such a run rendered `witness 0/1`
                # with every sub-count at 0) — and it is also where this leg used to
                # miss the artifacts leg's D8.3 12-hex arm, so one name got two
                # contradictory dispositions in one run. `notes_ambiguous` is always []
                # on this path (len(found) > 1 implies a resolved first hit); it is kept
                # in the expression for parity with the reached path.
                early = notes_ambiguous + [
                    _unresolved_disposition(art_name, strict, cov, witness_leg=True,
                                            refused=refused)]
                # C1-R3-S2 — mirrored here too, so `notes_out` is a COMPLETE record of
                # this leg's notes on every exit. _verify_single reads only the
                # out-param, so a site that returns without mirroring would go silent.
                if notes_out is not None:
                    notes_out.extend(early)
                return early
            # siege S-3(b) — reported whenever a probe base was dropped, not only when the
            # drop made the name unresolvable. Same reason as the artifacts leg's: a
            # refusal the fallback papers over was invisible on every channel. Its OWN
            # list, never appended to `notes_ambiguous`: that list is also read as the
            # BOOLEAN `ambiguous` by the billing below, so growing it would mis-bill.
            notes_refused = [
                f"REFUSED: probe base dropped while resolving witness "
                f"{_show_path(art_name)}{_refused_clause(refused)}"] if refused else []
            # C1-R3-S2 (freeze-guard revision) — mirrored into `notes_out` AT THE MOMENT
            # IT IS PRODUCED, because the only place the lists below are returned is the
            # clean path: every `raise` between here and that return drops them inside
            # this frame, so _verify_single's handler drain never saw them. That is
            # precisely the failing run siege S-3(b) says the refusal must survive ("a
            # property of the RUN, not of the failure"), and REFUSED has no census
            # counter, so stderr is its only channel.
            if notes_out is not None:
                notes_out.extend(notes_ambiguous)
                notes_out.extend(notes_refused)
            meter = {}     # SIEGE-R2BA-2 — filled on the #B branch, read by the cap below
            # SIEGE-R2BA-1 — the artifacts leg's hashed-AND-matched buffer for THIS FILE,
            # or None when there is none (no carry supplied; the name never resolved on
            # that leg; or a rangeless grep name that is not an ARTIFACTS entry at all).
            # NAME first, then realpath — the order matters. The name key is authoritative
            # for identity across a mid-lint resolution change (a symlink swap moves the
            # realpath but not the declared name), and the realpath key catches the two
            # legs spelling the same file differently. Consulting both is what makes the
            # carry hit in either failure mode; see the write site for why neither key
            # alone is sufficient.
            carried = None
            if bodies:
                carried = bodies.get(art_name)
                if carried is None:
                    carried = bodies.get(resolved)
                if carried is None and _carry_should_have_bound(art_name, bodies):
                    # #488 inquisitor/AV1 (state) — the DOUBLE MISS, which the write
                    # site's own conclusion ("a hit under either binds the predicate to
                    # the bytes this leg hashed AND matched") does not cover. Each key
                    # closes a different failure mode ALONE; put both failure modes on
                    # ONE run and both keys miss:
                    #   * a TRACE spelling difference (`./f.md` for a declared `f.md`)
                    #     defeats the NAME key — the witness's `art_name` for a rangeless
                    #     payload is the cited entry's first token verbatim, written
                    #     independently of the ARTIFACTS line, and no Tier-1 rule ties
                    #     the two spellings together;
                    #   * a mid-lint symlink swap moves the REALPATH after the hash, which
                    #     is the very attack the realpath key was added for.
                    # Both halves are receipt-controlled and free. Measured: a declared,
                    # hash-verified `f.md` containing the token the witness must NOT
                    # match, replaced between the legs by a symlink to a sanitised
                    # sibling and cited in TRACE one `./` apart — the carry silently
                    # degraded to a FRESH READ of the sanitised file, the predicate
                    # passed, and the run exited 0 still billing `witness 1/1`. The
                    # single-spelling twin of the same receipt was correctly REJECTED.
                    #
                    # The defect is the silent degradation, not the missing key, so the
                    # fix is fail-CLOSED and not a third key. A third normalised-name key
                    # would widen the same chain that has now failed twice: it would bind
                    # the predicate on one more spelling and go on silently re-reading
                    # disk for the next one. What is DETECTABLE here — with no disk
                    # access, and therefore immune to the swap itself — is that the cited
                    # name is a spelling of a name THIS RUN HASHED, while neither key
                    # bound it. That can only mean the resolution moved between the legs,
                    # which is exactly the event the carry exists to refuse.
                    #
                    # A name the artifacts leg never verified is untouched: it has no
                    # `bodies` entry under any spelling, so this never fires for it and
                    # the honest independent-read disposition below still applies (the
                    # `(none)`-ARTIFACTS and undeclared-payload shapes both keep their
                    # `unhashed-body` census code and their `independent read` note).
                    #
                    # `partial`, and raised before the read: bytes were never decoded and
                    # the predicate provably never ran, which is the same state the
                    # `_read_cited_range` LintError arm just below records.
                    if cov is not None:
                        cov.partial = True
                    raise LintError(
                        f"Tier-2: witness {_show_path(art_name)} names an artifact this "
                        f"run hash-verified, but its resolution CHANGED between the "
                        f"legs (neither the declared name nor the resolved realpath "
                        f"carries the hashed body); the predicate would have run "
                        f"against bytes no leg hashed")
            try:
                body_text = _read_cited_range(resolved, cited,
                                              witness if from_payload else None, meter,
                                              carried)
            except LintError:
                # #486 fixer / F3 — state (c)'s sibling: the body was never decoded, so
                # the predicate provably never ran and this leg did not finish. Without
                # this arm a guarded read failure renders `witness 0/1` with every
                # sub-count at 0 and no `partial` — byte-for-byte the shape this
                # function's own docstring above declares forbidden.
                if cov is not None:
                    cov.partial = True
                raise
            # #397 defect 4 — authoritative 4 KiB cap on the cited range (Tier-1's 80-bytes/line
            # estimate under-counts long lines). The cap measures EXACTLY what the reader read:
            #  - #L: len(body_text.encode("utf-8")) — the reader's own slice. read_text() decodes
            #    losslessly (no errors=), so there is NO U+FFFD inflation on this path; this also
            #    makes the cap byte-count equal the reader's str.splitlines() slice exactly (vs.
            #    bytes.splitlines(), which diverges on exotic separators U+2028/NEL/VT/FF).
            #  - #B: len(raw[a-1:b]) on the RAW on-disk bytes — matches the reader's read_bytes()
            #    slice. NOT body_text: a #B range over invalid UTF-8 decodes each bad byte to
            #    U+FFFD (3 bytes), which would inflate an in-budget range past the cap and
            #    false-FAIL.
            # Scoped to ranged citations (the #L/#B read budget per return-convention.md
            # § "Cost model": one Read of a byte-range <= 4 KiB per verified verdict);
            # rangeless READ/WROTE grep reads carry no #range and keep their whole-file behavior.
            # #474 / S6: when the body came from the WITNESS payload, the cap keys on THAT range
            # — the one actually read — not on parse_out_range(cited), which the grep path never
            # had. Tier-1's grep bound is only the sound 1-B/line floor, so this is where a
            # reviewer-declared range is measured against its real bytes.
            if from_payload:
                cap = (witness["range_kind"], witness["range_a"], witness["range_b"])
            else:
                r = parse_out_range(cited["args"])
                cap = (r.kind, r.start, r.end) if r else None
            if cap:
                kind, a, b = cap
                if a < 1:  # 1-based; clamp matches _read_cited_range
                    a = 1
                if kind == "L":
                    span = len(body_text.encode("utf-8"))
                else:
                    # SIEGE-R2BA-2 — the METER, not a third read. `resolved.read_bytes()`
                    # here re-materialised the whole attacker-named file to re-derive a
                    # number the reader already knew, and it re-derived it from a fresh
                    # read of a path that may no longer hold the bytes the slice came
                    # from. `raw_bytes` is the length of the slice actually returned, so
                    # the cap measures EXACTLY what the reader read — which is what this
                    # block's own comment above has always claimed it does.
                    span = meter["raw_bytes"]
                if span > WITNESS_SPAN_CAP:
                    if cov is not None:
                        cov.partial = True   # bytes read, predicate never ran — leg unfinished
                    raise LintError(
                        f"Tier-2: cited witness range exceeds 4 KiB actual bytes "
                        f"({span} > {WITNESS_SPAN_CAP}; Tier-1's line estimate under-counted)"
                    )
            try:
                _reject_empty_grep_body(body_text, witness, verdict, art_name)
            except LintError:
                # State (c): bytes read, predicate never ran. This arm needs NO WitnessTimeout
                # arm and that is deliberate — a timeout landing here is caught by this broad
                # `except LintError` (WitnessTimeout is a subclass), which sets partial and
                # re-raises: the same treatment state (d) gets, and it sets no wit_verified.
                # The subclass-ordering hazard only bites where an arm would ASSERT something
                # a timeout falsifies, which is the verify_witness wrapper below.
                if cov is not None:
                    cov.partial = True
                raise
            # SIEGE-C3 — filled by verify_witness, read below. siege S-7 — and handed
            # back to the caller when it asked for it, so the SUPERSEDES rule can read
            # `evaluated` without a second evaluation.
            probe = probe_out if probe_out is not None else {}
            # The shape whose item earns the `wrong-name` sub-count in
            # _bill_witness_billing. Hoisted above the try because BOTH the except and the
            # else arm need it. It does NOT scope DEC-26's zero-bytes withholding:
            # narrowing that guard by witness SHAPE was tried and REVERTED, because it
            # silently restores `witness 1/1` for a ranged kind=exec citation past EOF —
            # see _bill_witness_evaluation's DEC-28 note before reaching for it again.
            rangeless_grep = bool(witness.get("kind") == "grep"
                                  and witness.get("range_kind") is None
                                  and not notes_ambiguous)
            # siege S-2 — the same "the predicate ran against a file the witness never
            # names" shape for the kinds `rangeless_grep` does not cover. `cap is None`
            # with `from_payload` false means the body came from derive_art_name's
            # READ/WROTE branch, i.e. the cited TRACE entry's first token, which #412
            # deliberately does not gate — no ARTIFACTS membership, no hash binding.
            # kind=exec cannot reach it (Tier-1 forces its ran= onto an EXEC and every
            # EXEC carries an out= range, so `cap` is never None), so in practice this is
            # the `kind=lint` escape and only that.
            #
            # `and not bound` is what keeps this a DISAGREEMENT test rather than a shape
            # test: when the body came from the ARTIFACTS leg's hashed-AND-MATCHED buffer
            # the name IS a declared artifact and there is nothing wrong about it, however
            # it was spelled. Only the never-hashed read earns the counter.
            # siege S-5 — did the predicate run against the bytes the ARTIFACTS leg
            # hashed AND matched, or against an independent read? This is the DISAGREEMENT
            # the `wrong-name` counter was supposed to report and did not.
            bound = carried is not None
            derived_name = bool(witness.get("kind") != "grep" and not from_payload
                                and cap is None and not notes_ambiguous and not bound)
            notes_unbound = []
            if (rangeless_grep or derived_name) and not bound:
                notes_unbound = [
                    f"UNVERIFIABLE: witness {_show_path(art_name)} (predicate evaluated "
                    f"against an independent read — the name is not a hash-matched "
                    f"ARTIFACTS entry)"]
                # C1-R3-S2 — mirrored as produced; the predicate below raises on a
                # matching expect-fail and this note would be dropped with the frame.
                if notes_out is not None:
                    notes_out.extend(notes_unbound)
            # DEC-28 half 2 — the BUCKET's reason code, keyed on the RESOLUTION. `cap` is
            # the range the read was actually made against (payload range when
            # from_payload, else the cited entry's out= range; None ⇒ the whole file was
            # delivered), so this is "the citation named a range" and nothing about kind.
            # C1-R2-S1 — it reaches _bill_witness_billing and stops there: the RATIO is a
            # fact about the bytes that reached the predicate, and `a2968a0` billing a
            # rangeless 0-byte read `witness 1/1` on the strength of this flag re-opened
            # the zero-disk-bytes shape `43e5a50` closed.
            ranged = cap is not None
            try:
                verify_witness(body_text, witness, verdict, cited, probe)  # raises on FAIL
            except WitnessTimeout:
                # State (d). WitnessTimeout IS a LintError subclass, so this arm MUST precede
                # the broader one below — deleting it as a "pointless re-raise" would silently
                # route a timeout into the arm that sets wit_verified = 1, which is
                # round-4/SIG-2 exactly: `witness 1/1 ... partial`, a verification that
                # provably did not happen. The predicate was ENTERED and never finished, so it
                # is NOT verified. `partial` is set by the wrapper below; nothing to do here.
                raise
            except LintError:
                # State (b). Design :1188-1190's ARTIFACTS-leg analogue: bytes off disk +
                # predicate evaluated TO A RESULT == VERIFIED, including the run where that
                # result is a FAIL. SIEGE-C3 — routed through _bill_witness_evaluation,
                # which withholds the claim when `probe` says no predicate ran at all.
                if cov is not None:
                    _bill_witness_billing(cov, probe, body_text, rangeless_grep,
                                          ranged, bool(notes_ambiguous),
                                          derived_name, bound)
                raise
            else:
                # State (a). Same definition, clean result.
                if cov is not None:
                    _bill_witness_billing(cov, probe, body_text, rangeless_grep,
                                          ranged, bool(notes_ambiguous),
                                          derived_name, bound)
            return notes_ambiguous + notes_refused + notes_unbound
        except WitnessTimeout:
            if cov is not None:
                cov.partial = True
            raise


def _reject_empty_grep_body(body_text, witness, verdict, art_name):
    """#474 / D6 — an EMPTY resolved body on a ranged kind=grep witness is a LintError.
    An empty body can never fire and is indistinguishable from a skipped check — the
    fail-open shape this whole issue is about — and it backstops D4 if a range is ever
    paired with the wrong file again.

    Keyed on kind=grep + a ranged payload, NOT on expect-fail=match: a kind=grep +
    expect-fail=/…/ witness whose range lands past EOF yields "" just as easily, and
    that form is the majority of the real corpus.

    Gated on verdict == PASS, explicitly: this function's callers are verdict-agnostic,
    and a FAIL + grep + EXEC-cited witness does read a body (the UN-narrowed out= range),
    so an unscoped guard would newly raise where today it returns clean.

    An empty STRING from a successful read — never `body_text is None`, which
    verify_witness returns clean on as documented lint.py parity (`art_name not in
    artifact_bodies`). A guard written against a falsy body would swallow None too."""
    if (verdict == "PASS" and witness.get("kind") == "grep"
            and witness.get("range_kind") is not None and body_text == ""):
        raise LintError(
            f"Tier-2: WITNESS grep body empty for {_show_path(art_name)} "
            f"(declared range resolves to no bytes — witness could not fire)")


def _eval_tier2(witness, trace, bodies, verdict):
    """Reproduce lint.py:411-418's Tier-2 dispatch for the --eval inline-body path,
    routed through the shared verify_witness (PASS→tier2_verify, FAIL→tier2_verify_fail).
    Raises LintError (byte-identical message) on FAIL; the caller prints it as LINT-FAIL."""
    if not witness["ran"].startswith("TRACE#"):
        return
    idx = _trace_idx(witness["ran"])
    if not 1 <= idx <= len(trace):
        return
    cited = trace[idx - 1]
    art_name, _ = witness_art_name(witness, cited, verdict)
    body_text = bodies.get(art_name) if art_name else None
    # #474 / D6 MIN-4: bodies.get returns "" just as easily as the disk reader does, ""
    # survives the None-parity guard, and re.search(pattern, "") never matches — the same
    # fail-open on the --eval path, closed with the same rejection and the same PASS gate.
    _reject_empty_grep_body(body_text, witness, verdict, art_name)
    verify_witness(body_text, witness, verdict, cited)


def _eval_record(rec):
    """Classify one --eval record exactly as lint.py's main() loop does (Tier-1 then,
    if inline artifact_bodies + verdict in {PASS,FAIL}, the Tier-2 dispatch via the shared
    verify_witness). Returns ('LINT-PASS', verdict) or ('LINT-FAIL', error_string)."""
    receipt_text = rec.get("receipt")
    try:
        verdict = lint_receipt(receipt_text)
        bodies = rec.get("artifact_bodies", {})
        if bodies and verdict in {"PASS", "FAIL"}:
            sections = parse_receipt(receipt_text)
            trace = parse_trace(sections["TRACE"])
            witness = parse_witness(sections["WITNESS"])
            _eval_tier2(witness, trace, bodies, verdict)
        return ("LINT-PASS", verdict)
    except LintError as e:
        return ("LINT-FAIL", str(e))


def _eval_text(path) -> str:
    """The full --eval stdout (per-line columns + leading-`\\n` summary), byte-exact.
    Shared by run_eval (prints it) and run_selftest's golden-string assertion, so the
    printed format and the CI-pinned format can never drift."""
    out = []
    total = 0
    passed = 0
    for line in _read_path_arg(path).splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:  # json.JSONDecodeError is a ValueError subclass
            # Per-record fault isolation (#440): a malformed line is surfaced as a
            # LINT-FAIL row, never an aborted batch. The contract is "classify each
            # record, always exit 0"; one corrupt line must not suppress the rest.
            total += 1
            out.append(f"{'?':30s}  LINT-FAIL  malformed JSON line")
            continue
        if not rec.get("receipt"):
            continue
        total += 1
        disp, info = _eval_record(rec)
        did = rec.get("dispatch-id", "?")
        if disp == "LINT-PASS":
            out.append(f"{did:30s}  LINT-PASS  ({info})")
            passed += 1
        else:
            out.append(f"{did:30s}  LINT-FAIL  {info}")
    out.append(f"\nsummary: {passed}/{total} receipts passed lint")
    return "\n".join(out) + "\n"


def run_eval(path) -> int:
    """Port of lint.py main(): per-line LINT-PASS/LINT-FAIL on stdout + trailing summary.
    ALWAYS exits 0 for a readable file (F1) — per-record verdicts are stdout-only, never
    the process exit code, so run-eval.sh's pipefail greps over all-FAIL inject shapes."""
    sys.stdout.write(_eval_text(path))
    return 0


def tier2_ledger(trace, ledger_path):
    """Tier-2 part-3 — receipt-ledger binding (#369). For each DISPATCHED TRACE entry,
    verify a matching row exists in the orchestrator-supplied `receipt-ledger.jsonl`
    (`--ledger PATH`). The ledger row is the 4-key snake_case schema #383 pinned —
    `{dispatch_id, phase, rcpt_sha256, verdict}` — and the binding match is the TRIPLE
    `(dispatch_id, rcpt_sha256, verdict)`; **`phase` is NOT matched** (it is recorded for
    cairn reconciliation, not binding — see `return-convention.md` "Parent-Child Receipt
    Binding"). **Phase-exclusion holds by construction, not by a runtime branch:** the
    DISPATCHED TRACE grammar carries no phase token (it is `<skill>/<dispatch-id>
    verdict=… rcpt-sha256:…`), so there is nothing for the binding to match a ledger
    `phase` against — the property is structural, and consequently no corpus row can
    exercise a phase-mismatch (a phase-differs fixture would be vacuous). The DISPATCHED
    token is `<skill>/<dispatch-id>`; the ledger `dispatch_id` is the phase-less
    `<dispatch-id>` basename, so the `<skill>/` prefix is stripped before comparison. The
    DISPATCHED line carries the child's `rcpt-sha256:<H>` literal, which is string-compared
    to the ledger's `rcpt_sha256` — there is NO hash recompute (the verifier never holds
    the child receipt's text; the orchestrator recorded the hash at dispatch). Raises
    LintError on any DISPATCHED line with no full-triple match (hard FAIL, independent of
    --strict — a declared dispatch that is not bound is a structural break). The ledger
    read is guarded for both an absent/unreadable file (OSError) AND a malformed-JSONL or
    non-object-row ledger (ValueError, incl. json.JSONDecodeError) → a clean LintError
    bullet, never a traceback; non-dict rows are dropped (a non-object is not a valid
    ledger entry, so a DISPATCHED line backed only by junk rows FAILs to bind). Returns []."""
    dispatched = [t for t in trace if t["verb"] == "DISPATCHED"]
    if not dispatched:
        return []
    try:
        ledger = [e for e in _read_jsonl(ledger_path) if isinstance(e, dict)]
    except (OSError, ValueError, MemoryError, RecursionError) as ex:
        # siege S-1 — MemoryError and RecursionError are NEITHER OSError nor ValueError,
        # so a sparse ledger under `ulimit -v` and a deeply-nested JSON row each escaped
        # this guard and printed a Traceback AFTER the census, on the parsed channel.
        # `_read_jsonl`'s own ceiling makes the first unreachable from a plausible plant
        # and the recursion limit still owns the second; both are caught here regardless,
        # because "the ledger could not be read" is one disposition however it failed.
        # SIEGE-C2 — argv-supplied rather than subagent-supplied, but it lands on the
        # same parsed channel, so it takes the same renderer.
        raise LintError(
            f"Tier-2 --ledger: cannot parse receipt-ledger {_show_path(ledger_path)}: {ex}")
    for t in dispatched:
        token = t["args"].split()[0] if t["args"].split() else ""
        vm = re.search(r"verdict=(\S+)", t["args"])
        hm = re.search(r"rcpt-sha256:([0-9a-f]{64})", t["args"])
        if not token or not vm or not hm:
            raise LintError(f"Tier-2 --ledger: DISPATCHED args lack token/verdict=/rcpt-sha256: {t['args']!r}")
        verdict, h = vm.group(1), hm.group(1)
        did = token.split("/", 1)[1] if "/" in token else token  # strip <skill>/ prefix
        if not any(e.get("dispatch_id") == did and e.get("rcpt_sha256") == h
                   and e.get("verdict") == verdict for e in ledger):
            raise LintError(
                f"Tier-2 --ledger: DISPATCHED {token} (verdict={verdict}, "
                f"rcpt-sha256:{h[:12]}…) has no matching receipt-ledger entry "
                f"(dispatch_id={did}; phase is not part of the match)")
    return []


def _read_jsonl(path):
    """siege S-1 — the ONE Tier-2 read the SIEGE-R2BA-2 bounding sweep missed.

    This was a bare `pathlib.Path(path).read_text()`: no regular-file gate, no ceiling,
    and outside `_witness_bound()`. `quality-gate/SKILL.md:30` mandates
    `--ledger <dispatch-root>/receipt-ledger.jsonl`, i.e. a path INSIDE the directory the
    reviewed subagent owns, and the receipt itself decides whether the read happens at all
    (a `DISPATCHED` TRACE line is the only trigger). Measured on the mandated command
    line: `mkfifo` at that path hung to EXIT=124 with ZERO bytes on stdout AND stderr —
    no bullet, no `TIER2-COVERAGE:` line, nothing an orchestrator can classify — and the
    only documented remedy for a linter that does not work is the in-context pseudocode
    fallback, which performs zero disk verification. A 4 GiB sparse ledger drove 8.4 GB
    RSS on the same path.

    `is_file()` FIRST and it is what closes the hang: it stats, it does not open, so a
    FIFO/device/directory is classified without blocking. Then `_read_capped` — the same
    race-free ceiling every other reader on this leg already took, and for the same
    reason (the file lives where the reviewed party can grow it between the check and the
    read). A LintError, so `tier2_ledger`'s caller renders one bullet plus the census and
    exits 1.

    The corpus callers in `run_selftest` read committed, in-repo files well under the
    ceiling, so they are unaffected — but they are covered by the same guard rather than
    routed around it, because a second reader is how this one got missed."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise LintError(
            f"Tier-2: {_show_path(p)} is not a regular file (not read)")
    raw = _read_capped(p, ARTIFACT_READ_CAP, f"JSONL {_show_path(p)}")
    try:
        text = raw.decode()
    except UnicodeDecodeError as e:
        raise LintError(f"Tier-2: {_show_path(p)} is not valid UTF-8 ({e})")
    return [json.loads(l) for l in text.splitlines() if l.strip()]


# SIEGE-C12 — the six multi-root rows of tier2-fixtures/manifest.jsonl by id. They are
# the corpus-level coverage of criteria 5 and 6 (cross-root ambiguity, and de-duplication
# being a no-op), i.e. the two safety properties multi-root introduces; a prune that left
# the 14 legacy rows in place would otherwise still print `selftest OK`.
_MULTI_ROOT_FIXTURE_IDS = frozenset({
    "two-root-second-root-resolves",
    "two-root-declaration-order-first-hit",
    "two-root-ambiguous-strict-fail",
    "two-root-ambiguous-identical-bytes-strict-fail",
    "two-root-dedup-noop",
    "two-root-tampered-hash-second-root",
})


def run_selftest() -> int:
    """CI gate: (i) v1 corpus classification via the --eval Tier-2 dispatch; (iii) Tier-2
    disk fixtures; (iv) inline-vs-disk cross-check; (v) --eval stdout golden-string.
    Exit 0 iff all pass; non-zero (never silent) on any failure or absent corpus."""
    if not CORPUS_DIR.is_dir():
        sys.stderr.write(f"corpus not found at {CORPUS_DIR}\n")
        return 1
    problems = []

    # (i) v1 corpus — 5 samples lint-pass; 7 injections LINT-FAIL via the --eval Tier-2
    #     dispatch (the 2 Tier-2-only rows 102/105 raise in verify_witness, NOT lint_receipt).
    for rec in _read_jsonl(CORPUS_DIR / "sample-corpus/receipts.jsonl"):
        disp, info = _eval_record(rec)
        if disp != "LINT-PASS":
            problems.append(f"sample {rec.get('dispatch-id','?')} expected LINT-PASS, got LINT-FAIL: {info}")
    inject_shapes = sorted((CORPUS_DIR / "inject").glob("shape-*.jsonl"))
    if not inject_shapes:
        problems.append("no inject/shape-*.jsonl found")
    for shape in inject_shapes:
        for rec in _read_jsonl(shape):
            if not rec.get("receipt"):
                continue
            disp, info = _eval_record(rec)
            if disp != "LINT-FAIL":
                problems.append(f"inject {shape.name}/{rec.get('dispatch-id','?')} "
                                f"expected LINT-FAIL, got {disp} ({info})")

    # (ii) v1.1 Tier-1 extension — conformant v1.1 row lint-passes; one FAIL injection
    #      per distinct receipt-local rule lint-fails. Globbed so a new rule's shape is
    #      auto-covered; absent corpus is a HARD problem (a no-op port can't pass by
    #      silently skipping a missing v1.1 corpus).
    v11_corpus = CORPUS_DIR / "v11-corpus/receipts.jsonl"
    v11_inject = CORPUS_DIR / "v11-inject"
    if not v11_corpus.is_file():
        problems.append(f"v1.1 corpus not found at {v11_corpus}")
    else:
        for rec in _read_jsonl(v11_corpus):
            disp, info = _eval_record(rec)
            if disp != "LINT-PASS":
                problems.append(f"v11-corpus {rec.get('dispatch-id','?')} expected LINT-PASS, got LINT-FAIL: {info}")
    v11_shapes = sorted(v11_inject.glob("shape-*.jsonl"))
    if not v11_shapes:
        problems.append(f"no v11-inject/shape-*.jsonl found under {v11_inject}")
    for shape in v11_shapes:
        for rec in _read_jsonl(shape):
            if not rec.get("receipt"):
                continue
            disp, info = _eval_record(rec)
            if disp != "LINT-FAIL":
                problems.append(f"v11-inject {shape.name}/{rec.get('dispatch-id','?')} "
                                f"expected LINT-FAIL, got {disp} ({info})")

    # (iii) Tier-2 disk fixtures — each fixture's expect realized against REAL files.
    #       SIEGE-C12: this was the ONE corpus leg with no presence guard. Truncating
    #       manifest.jsonl to zero bytes deleted EVERY Tier-2 disk fixture — including
    #       all six multi-root rows, which are the corpus-level coverage of the two
    #       safety properties multi-root introduces — and --selftest still printed
    #       `selftest OK` and returned 0. Legs (i), (ii) and (vi) all append a hard
    #       problem when their corpus is missing; this one now does too, plus an
    #       id-presence assertion so a silent PRUNE of exactly those rows shows up
    #       (the `LEGACY_EXPECT` idiom in scripts/test_rcpt_verify.py, kept
    #       proportionate: only the subset a bare presence guard cannot cover, never
    #       the whole corpus re-stated here).
    fx_dir = CORPUS_DIR / "tier2-fixtures"
    fx_manifest = fx_dir / "manifest.jsonl"
    fx_rows = _read_jsonl(fx_manifest) if fx_manifest.is_file() else []
    if not fx_rows:
        problems.append(f"tier2 fixture manifest missing or empty at {fx_manifest}")
    pruned = _MULTI_ROOT_FIXTURE_IDS - {fx.get("id") for fx in fx_rows}
    if pruned:
        problems.append("tier2 fixture manifest is missing multi-root rows: "
                        f"{sorted(pruned)}")
    for fx in fx_rows:
        got = _selftest_run_fixture(fx, _fx_roots(fx_dir, fx["root"]))
        if got != fx["expect"]:
            problems.append(f"fixture {fx['id']} expected {fx['expect']}, got {got}")

    # (iv) cross-check: inline --eval verdict == disk tier2_witness verdict for the inject
    #      rows carrying artifact_bodies (102/105). Also asserts the silent corpus invariant
    #      that the inline body equals its cited #L/#B range (disk reads only the range).
    for shape in inject_shapes:
        for rec in _read_jsonl(shape):
            bodies = rec.get("artifact_bodies")
            if not bodies:
                continue
            problems.extend(_selftest_crosscheck(rec, bodies))

    # (v) --eval stdout golden-string — pins the run-eval.sh-grepped byte format in CI.
    golden = (fx_dir / "eval-golden.txt").read_text()
    captured = _eval_text(CORPUS_DIR / "sample-corpus/receipts.jsonl")
    if captured != golden:
        problems.append("--eval stdout does NOT match committed eval-golden.txt (byte-format drift)")

    # (vi) Tier-2 part-3 receipt-ledger binding — each ledger-manifest row's expect
    #      realized by running tier2_ledger against a materialized ledger (absent
    #      manifest is a HARD problem so a no-op port can't skip the binding silently).
    ledger_manifest = fx_dir / "ledger-manifest.jsonl"
    if not ledger_manifest.is_file():
        problems.append(f"ledger-manifest not found at {ledger_manifest}")
    else:
        for fx in _read_jsonl(ledger_manifest):
            got = _selftest_run_ledger_fixture(fx)
            if got != fx["expect"]:
                problems.append(f"ledger fixture {fx['id']} expected {fx['expect']}, got {got}")

    if problems:
        for p in problems:
            sys.stderr.write(f"selftest FAIL: {p}\n")
        return 1
    print("selftest OK: v1 corpus + v1.1 extension + Tier-2 fixtures + ledger binding + cross-check + golden-string")
    return 0


def _fx_roots(fx_dir, spec):
    """#486 — manifest `root` accepts a string OR a list of strings; a bare string
    normalises to a one-element list, so all 14 committed rows keep their meaning
    verbatim (criterion 10(c)). The corpus needs this because run_selftest is the
    design's own named anti-drift instrument (D8.4 rejects a built-in canary on the
    grounds that CI already runs these fixtures through the REAL functions), and
    criteria 5 and 6 are the two safety properties multi-root introduces — left as
    test_rcpt_verify.py-only they would sit outside that corpus."""
    if isinstance(spec, str):
        spec = [spec]
    return [fx_dir / s for s in spec]


def _selftest_run_fixture(fx, root) -> str:
    """Run one committed Tier-2 fixture through Tier-1 + Tier-2; return 'pass'|'fail'.

    `root` is a LIST of roots (see _fx_roots); it forwards to tier2_artifacts /
    tier2_witness, which normalise via _as_roots, so the parameter itself is unchanged."""
    try:
        text = fx["receipt"]
        verdict = lint_receipt(text)
        sections = parse_receipt(text)
        artifacts = parse_artifacts(sections["ARTIFACTS"])
        trace = parse_trace(sections["TRACE"])
        witness = parse_witness(sections["WITNESS"])
        # SIEGE-R2BA-1 — the fixture leg wires the carry too, so the committed corpus is
        # exercised through the BOUND path the CLI takes, not a second unbound one.
        bodies = {}
        tier2_artifacts(artifacts, trace, root, fx["strict"], None, bodies)
        if verdict in {"PASS", "FAIL"}:
            tier2_witness(witness, trace, root, fx["strict"], verdict, None, bodies)
        return "pass"
    except WitnessTimeout:
        return "error"        # #486/Q8 — a timeout is NOT a passing expect:fail fixture
    except LintError:
        return "fail"


def _selftest_run_ledger_fixture(fx) -> str:
    """Run one committed ledger-manifest row: materialize its ledger to a tmp
    receipt-ledger.jsonl, parse the receipt's TRACE, run tier2_ledger. 'pass'|'fail'.
    A row with a `"ledger_raw"` string field writes THAT verbatim (exercises the
    malformed-JSONL / non-dict-row guard); else its `"ledger"` list is json.dumps-ed
    line-per-entry. Any non-LintError Exception → 'error' so a guard regression shows
    as a clean `expected fail, got error` selftest problem, not a crash."""
    import tempfile
    try:
        sections = parse_receipt(fx["receipt"])
        trace = parse_trace(sections["TRACE"])
        with tempfile.TemporaryDirectory() as td:
            led = pathlib.Path(td) / "receipt-ledger.jsonl"
            if "ledger_raw" in fx:
                led.write_text(fx["ledger_raw"])
            else:
                led.write_text("".join(json.dumps(e) + "\n" for e in fx["ledger"]))
            tier2_ledger(trace, led)
        return "pass"
    except LintError:
        return "fail"
    except Exception:
        return "error"


def _selftest_crosscheck(rec, bodies):
    """Materialize an artifact_bodies inject's body to disk, run the disk tier2_witness
    path, and assert it agrees with the inline --eval path. Returns a list of problems."""
    import tempfile
    problems = []
    text = rec["receipt"]
    did = rec.get("dispatch-id", "?")
    verdict = lint_receipt(text)
    sections = parse_receipt(text)
    trace = parse_trace(sections["TRACE"])
    witness = parse_witness(sections["WITNESS"])
    idx = _trace_idx(witness["ran"])
    cited = trace[idx - 1]
    # #474 / S8(2): witness_art_name, not derive_art_name — a READ/WROTE-cited grep row
    # carries no out=, so the old derivation landed at the wrong path and its range
    # assertion was vacuous: coverage that could not fail.
    art, from_payload = witness_art_name(witness, cited, verdict)
    # #474 round-1 / SIG-3 — a row whose ranged grep witness verifies an artifact the
    # row does not SUPPLY is coverage that cannot fail: `bodies.get` misses, body_text
    # is None, and verify_witness returns clean under the lint.py parity rule no matter
    # what the body would have said. That inline/disk disposition divergence is
    # documented (verify_witness) and deliberate; what must not happen is a fixture
    # silently drifting into the shape and reporting green. This is the check that
    # keeps the one committed kind=grep artifact_bodies row honest.
    #
    # NO LONGER SCOPED TO THE PASS LEG — GH #501 widened it, and did so by fixing the
    # thing the old scoping was a symptom of rather than by touching this line. The gate
    # is `from_payload`, which witness_art_name used to set only for verdict == "PASS",
    # so a FAIL + ranged kind=grep + artifact_bodies row would have reintroduced the
    # round-1/SIG-3 vacuity uncaught (round-5 / MIN-4 named the gap; it was never live —
    # measured over eval/ledger-return-protocol/inject/*.jsonl, the one ranged kind=grep
    # row (shape-e) is a PASS and no FAIL row is ranged kind=grep). Sourcing the payload
    # on both legs means `art` is now the PAYLOAD artifact on either verdict, so the
    # check means the same thing on both and the shape it could not cover is covered.
    # The corpus still holds no FAIL row of that shape, so this widening is latent
    # coverage, not a behaviour change anything today can observe.
    if witness["kind"] == "grep" and from_payload and art not in bodies:
        problems.append(f"crosscheck {did}: artifact_bodies does not supply {art}, the "
                        f"artifact this ranged grep witness verifies — the --eval leg "
                        f"cannot fire (coverage that cannot fail)")
    inline_disp = _eval_record(rec)[0]
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = bodies.get(art)
        if body is not None:
            (root / art).parent.mkdir(parents=True, exist_ok=True)
            (root / art).write_text(body)
            if witness["kind"] == "grep":
                # For kind=grep the two paths diverge BY DESIGN (#474/D4): the disk
                # reader slices to the witness payload's range while --eval passes the
                # WHOLE inline body — there are no line offsets to slice an inline body
                # against. So assert what must still hold: the slice is non-empty and is
                # drawn from that same body. A slice taken from the wrong file, or an
                # empty one, fails here.
                sliced = _read_cited_range(root / art, cited,
                                           witness if from_payload else None)
                if not sliced or sliced not in body:
                    problems.append(f"crosscheck {did}: grep slice is empty or not drawn "
                                    f"from the inline body (wrong artifact or dead range)")
            else:
                # corpus invariant: inline body == cited range (disk reads only the range)
                cited_range = _read_cited_range(root / art, cited)
                if cited_range != body:
                    problems.append(f"crosscheck {did}: inline body != cited range "
                                    f"(disk path reads only the range — fixture invariant broken)")
        try:
            tier2_witness(witness, trace, root, False, verdict)
            disk_disp = "LINT-PASS"
        except WitnessTimeout as e:
            # #486/Q8 — recording "LINT-FAIL" here AGREES with an inline LINT-FAIL and
            # so reports no problem: the swallow this crosscheck exists to prevent.
            disk_disp = "TIMEOUT"
            problems.append(f"crosscheck {did}: witness evaluation timed out ({e})")
        except LintError:
            disk_disp = "LINT-FAIL"
    if disk_disp != inline_disp:
        problems.append(f"crosscheck {did}: inline={inline_disp} != disk={disk_disp}")
    return problems


def _usage_exit(argv=None, code=None):
    """SIEGE-R2BA-5 — `argv`/`code` are optional so the two callers that CANNOT be a
    `--tier2` run (an empty argv; `--eval` at the wrong arity) keep today's behaviour
    verbatim. Every caller inside main's flag loop passes both: those are the exit-2
    terminal states the mandated `--tier2` command line can actually land on."""
    sys.stderr.write(__doc__)
    if code is not None:
        _state_not_reached(code, argv)
    return 2


def _read_path_arg(path):
    """Read the top-level path argument, returning its text. Raises _PathReadError
    (clean one-line stderr + usage exit 2) on a missing/unreadable file — instead of
    leaking a FileNotFoundError/OSError traceback. Only guards the path read itself;
    malformed JSON *content* inside a readable file is out of scope (left to json.loads).

    siege S-1 — the receipt path is the OTHER unguarded `read_text()`, and the mandated
    invocation names a file under the dispatch root the reviewed subagent owns, so it is
    the same FIFO/huge-file surface `_read_jsonl` was: `is_file()` (stat, never open) is
    what stops the hang, and the ceiling is `ARTIFACT_READ_CAP`. Both failures map onto
    the EXISTING `_PathReadError` disposition — one clean stderr line plus the
    `not-reached (receipt-unreadable)` census and exit 2 — rather than a new terminal
    state: "this path did not yield a receipt" is one outcome however it failed.

    C1-R2-S4 — `encoding`/`errors` are NOT decoration. `p.open("r")` decodes with the
    LOCALE codec and `UnicodeDecodeError` is a `ValueError`, not an `OSError`: it escaped
    this guard, escaped `main`, and escaped the module guard (`except _PathReadError`),
    so a `--tier2` run terminated with a raw traceback and NEITHER a bullet NOR a census —
    the eighth terminal state, on a channel `SIEGE-R2BA-5` swept for exactly this ("every
    exit-2 terminal state is a state in which verification did not happen", applied
    "uniformly, through ONE formatter"). `siege S-1` added `UnicodeDecodeError` arms to
    `_read_jsonl` and `_read_text_lossless` in the same commit series and did not reach the
    reader that reads the RECEIPT. Reachability is not theoretical: under `LC_ALL=C`, which
    is routine in CI containers and cron, *any* non-ASCII byte took that branch — an
    em-dash or a `→`, both of which appear in the receipts this repo ships.

    `errors="replace"` rather than a `UnicodeDecodeError` arm, deliberately: a receipt is
    TEXT, and a mojibake byte should reach Tier-1 and earn a real grammar bullet, not be
    reported as a failure to READ the path. Pinning `encoding="utf-8"` removes the locale
    dependence at the same time. Note the asymmetry with `_read_text_lossless`, which must
    stay lossless because its byte count feeds the 4 KiB witness cap; nothing here does."""
    p = pathlib.Path(path)
    try:
        if not p.is_file():
            raise _PathReadError(path)
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(ARTIFACT_READ_CAP + 1)
    except OSError:
        raise _PathReadError(path)
    if len(text) > ARTIFACT_READ_CAP:
        raise _PathReadError(path)
    return text


def _read_stdin_arg():
    """C1-R2-S4, the sibling branch. `sys.stdin.read()` decodes with the locale codec too,
    and `hooks/rcpt-verify-hook.sh:76` pipes a receipt block into it — so the same
    non-UTF-8 (or merely non-ASCII-under-`LC_ALL=C`) byte produced the same traceback with
    no bullet and no census. Same disposition as the path branch: replace the byte, let
    Tier-1 speak.

    Guarded rather than assumed: `reconfigure` exists only on `io.TextIOWrapper`, and
    `sys.stdin` is a `StringIO` under the in-process tests and can be detached or already
    partly consumed, all of which raise instead of failing to decode. A stream that cannot
    be reconfigured is read exactly as it was before this fix."""
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    return sys.stdin.read()


class _PathReadError(Exception):
    def __init__(self, path):
        super().__init__(path)
        self.path = path


# ── #486 / D8 — the coverage census ──────────────────────────────────────────
# Counts and reason codes ONLY: no paths, no roots, no timings, so goldens stay
# machine-independent. The line NEVER appears in _eval_text (:2259) — that path routes
# through _eval_tier2, which takes inline bodies and no root, so `unreached` has no
# meaning there — and never alters run_selftest's fixture comparison.
# DEC-28 — `empty-range` is the SIXTH sub-count, and it is witness-leg-only (the artifacts
# leg reads no cited range and evaluates no predicate). It sits before `not-applicable`
# because every counter ahead of it describes an item that is still IN the applicable set,
# and `not-applicable` — the one bucket for items that left it — reads last.
# #488 T7 — `resolved-by-walk` takes a position in that run WITHOUT inheriting that
# justification, and the exception is deliberate: it is a fact about HOW a name resolved,
# not about whether the item is in the applicable set, so it MAY co-occur with
# `not-applicable` on the same witness-leg item — a name that resolved below a root's top
# level and was then billed not-applicable is both, and is counted in both positions. That
# is not a partition violation: the disjointness rule this ordering argument comes from is
# the floor buckets', and `resolved-by-walk` stands outside them (return-convention.md's
# `resolved-by-walk` blockquote says so).
_COV_COUNTERS = ("unreached", "not-reachable", "ambiguous", "wrong-name", "empty-range",
                 "discarded", "resolved-by-walk", "not-applicable")

# SIEGE-C4 — the census state for a --tier2 exit that happens BEFORE _verify_single is
# entered, where no _Coverage exists and the finally: documented to "survive every
# LintError path" never runs. Same `not-reached (<code>)` idiom as tier1-reject, and for
# the same reason: "verification did not happen" must be STATED on the channel. Without
# it, a reviewed subagent that deletes the findings root it owns makes the mandated
# invocation exit 2 in silence — no orchestrator in skills/ has a rule for exit 2, and
# the mandating paragraphs' only remedy for a non-working tool is the in-context
# pseudocode fallback, which does zero disk verification. Carries no path: the offending
# root is named on its OWN bullet, because this line's "no paths, no roots"
# machine-independence is pinned by return-convention.md:271.
#
# SIEGE-R2BA-5 — C4 established the rule and applied it to ONE exit-2 path. FIVE others
# stayed silent, one of them (`two-positionals`) CREATED by SIEGE-C15 one commit after
# the rule was written, whose own rationale is that a mis-expanded shell substitution
# "lands exactly on this branch". The rule is not per-branch: every exit-2 terminal state
# is a state in which verification did not happen, and every one of them is reachable
# from the mandated four-substitution command line. Now applied uniformly, through ONE
# formatter so the idiom cannot acquire a second spelling. The `_COV_ROOT_INVALID`
# constant this replaces is gone rather than left orphaned; the STRING it held is
# unchanged, and is what the tests pin.
#
# The codes, and the shell slip each one names:
#   root-invalid          — a root that is empty / not a directory (C4)
#   root-missing-value    — `--root` as the final token (a substitution expanded to
#                           nothing and ate the root)
#   ledger-missing-value  — `--ledger` as the final token, same shape
#   two-positionals       — a second receipt path (C15's branch)
#   unknown-flag          — an unrecognised `--flag`
#   receipt-unreadable    — the receipt path itself could not be read (_PathReadError)
def _cov_not_reached(code) -> str:
    return f"TIER2-COVERAGE: not-reached ({code})"


def _state_not_reached(code, argv) -> None:
    """SIEGE-R2BA-5 — write the `not-reached (<code>)` census for a terminal exit that
    happens before (or instead of) _verify_single.

    Gated on `--tier2` being anywhere in argv rather than on `mode`, which is C4's
    precedent and is required for the same reason: `mode` is not final part-way through
    main's flag loop (`--root X --tier2` is a legal ordering). `--tier1` therefore emits
    nothing in any configuration (D8.2 sub-decision 4), and neither does `--eval`, whose
    argv cannot contain `--tier2` at the arity its own guard admits and which is
    documented never to carry this line at all."""
    if "--tier2" in argv:
        sys.stderr.write(_cov_not_reached(code) + "\n")


class _Coverage:
    """One receipt's Tier-2 coverage, rendered as exactly one TIER2-COVERAGE: line.

    Initialised in the `tier1-reject` state (D8.2 sub-decision 3): an all-zeros line
    would be byte-indistinguishable from a legitimate no-op census over a receipt with
    no artifacts and a not-applicable witness. tier1_ok() leaves that state once
    lint_receipt has returned.
    """

    def __init__(self):
        self.tier1_reject = True
        # C1-R1-S3 — which `not-reached` state this is. `tier1-reject` is the default and
        # the only one _verify_single could reach before; a supplied-but-absent `--root`
        # now lands here too, AFTER Tier-1 has actually run, so the code has to be able
        # to say which of the two it was.
        self.not_reached_code = "tier1-reject"
        self.partial = False
        self.art_verified = 0
        self.art_applicable = 0
        self.wit_verified = 0
        self.wit_applicable = 0
        self.counts = {k: 0 for k in _COV_COUNTERS}
        self.codes = {k: set() for k in _COV_COUNTERS}

    def tier1_ok(self):
        self.tier1_reject = False

    def bump(self, counter, code=None):
        self.counts[counter] += 1
        if code is not None:
            self.codes[counter].add(code)

    def note_code(self, counter, code):
        """Attach a reason code to a counter WITHOUT incrementing it — for a second fact
        about an item that is already counted. Splitting such a fact into its own counter
        would put one item in two sub-counts, which is exactly the disjointness break
        C1-R1-S1 closes one function over."""
        self.codes[counter].add(code)

    def render(self) -> str:
        if self.tier1_reject:
            # SIEGE-R2BA-5 — one formatter. C1-R1-S3 — one formatter, several codes.
            return _cov_not_reached(self.not_reached_code)
        parts = [f"artifacts {self.art_verified}/{self.art_applicable}",
                 f"witness {self.wit_verified}/{self.wit_applicable}"]
        for k in _COV_COUNTERS:
            # D8.3 — the parenthetical is attached to EACH counter whose code set is
            # non-empty, in that counter's printed position; sorted lexicographically
            # and de-duplicated, with NO parenthetical at all when the set is empty.
            codes = self.codes[k]
            suffix = f" ({','.join(sorted(codes))})" if codes else ""
            parts.append(f"{k} {self.counts[k]}{suffix}")
        if self.partial:
            parts.append("partial")
        return "TIER2-COVERAGE: " + " ".join(parts)


def _drain(notes):
    """C1-R3-S2 — the ONE note-drain. _verify_single has three exits (clean, LintError,
    unclassified escape) and every one of them must emit what the completed legs already
    diagnosed; three hand-copied loops is how the third one came to emit nothing."""
    for n in notes:
        sys.stderr.write(_show_diag(n) + "\n")


def _verify_single(text, mode, root, strict, ledger=None, root_error=None) -> int:
    """Single-receipt mode: Tier-1 (always) + Tier-2 (if --tier2). Exit 0 on pass,
    1 on any LintError (bullet on stderr). UNVERIFIABLE notes are advisory (stderr, non-fatal).

    #486 / D8 — emits exactly one TIER2-COVERAGE: line per --tier2 run, from a finally:
    so it survives every LintError path, AFTER the bullet and after the notes. It is
    NOT emitted from a notes drain: the census is a fact about the whole run, while a
    note is a fact one leg learned, and the failing run is exactly where the census
    earns its keep — tier2_artifacts raises on the FIRST failing entry and the bullet
    then tells you about one name and nothing about the rest.

    C1-R3-S2 — the notes reach stderr on ALL THREE exits, via `_drain`: the clean path,
    the LintError handler, and the unclassified-escape handler. They did not before —
    a single drain sat at the end of the try and every LintError (lint_receipt,
    tier2_artifacts, tier2_witness, tier2_ledger) jumped past it, discarding what the
    completed legs had learned on exactly the runs the notes exist to diagnose. Stderr
    ordering is therefore notes, then the bullet, then the census. tier2_witness's own
    notes arrive through its `notes_out` out-param rather than its return value,
    because its return is reached only on ITS clean path.

    `partial` is set at the raise sites, never inferred here: this handler cannot tell
    WHICH leg truncated, and guessing is how a silently-wrong number gets into the one
    instrument built to expose silently-wrong numbers. That stays true for CLASSIFIED
    failures — every LintError raise site still owns its own `partial`.

    #486 fixer / F3 — an UNCLASSIFIED unwind is the exception, and the honest fallback is
    the opposite default. A non-LintError escape (an unguarded OSError/ValueError, a
    SystemExit, a KeyboardInterrupt) sets nothing at any raise site, so the finally: below
    rendered a complete-looking census for a run that aborted mid-leg — e.g.
    `witness 0/1` with every sub-count at 0 and no `partial`, the shape tier2_witness's
    own docstring declares forbidden. `partial` claims only "this run did not finish",
    which is exactly what an unclassified escape proves, and it does not guess WHICH leg.
    """
    cov = _Coverage()
    # C1-R3-S2 — bound HERE, not at the v11 dispatch below, because the LintError handler
    # now drains it and lint_receipt / parse_receipt / parse_{artifacts,trace,witness} all
    # raise BEFORE the tier2 branch would assign it. An empty drain is the correct output
    # on those paths: nothing had been learned yet.
    notes = []
    # C1-R3-S2 (freeze-guard revision) — tier2_witness returns its notes ONLY on its clean
    # path, so a raise inside it drops them in that frame. This is the out-param it mirrors
    # them into as they are produced, and it is the SOLE channel for that leg here: the
    # call site discards the return value, because holding the notes in both lists printed
    # them twice whenever the witness leg succeeded and a later leg raised. Every drain
    # site therefore emits `notes + wit_notes`.
    wit_notes = []
    try:
        try:
            verdict = lint_receipt(text)
            if root_error is not None:
                # C1-R1-S3 — a DEFERRED lint failure, and the deferral is the whole
                # point. F1 was right that a supplied root which is not a directory must
                # never silently degrade to cwd, and wrong about the disposition: it
                # returned 2 from main's flag loop, BEFORE `_verify_single`, so the
                # receipt was never parsed at all. `<findings-root>` is
                # `<scratch-dir>/chunk-N`, which the REVIEWED SUBAGENT creates by writing
                # its findings file — so "absent" is the NORMAL pre-write state, and it is
                # also what a crash, a timeout or a wrong output path produces. On every
                # one of those the mandated command line ran zero verification, including
                # the Tier-1 checks that are what stop a fabricated `BLOCKED` receipt
                # with a malformed WITNESS or a `SUPERSEDES:` retiring a prior FAIL. Exit
                # 2 plus a usage banner is also the canonical shape of "you invoked this
                # tool wrong / the tool is unavailable", and the ONE documented remedy for
                # an unavailable linter is the in-context pseudocode fallback, which does
                # zero disk verification — so the guard opened a new way to DENY the
                # linter, in a file that argues elsewhere that denying the linter is a
                # security outcome.
                #
                # Tier-1 has therefore already run above and owns its own bullet and its
                # own `tier1-reject` census. Only then is the root failure raised, as an
                # ordinary LintError: exit 1, one bullet, one census line stating which
                # `not-reached` state this is. Every consumer already maps a non-zero,
                # non-2 exit to structurally BLOCKED. Tier-2 never runs — the probe set is
                # not silently narrowed, which is the property F1 was defending.
                #
                # `--root ""`, a `--root` naming a FILE, and an unknown flag stay exit 2
                # in main: those are genuine argv errors, not a normal transient.
                cov.not_reached_code = root_error[0]
                raise LintError(root_error[1])
            cov.tier1_ok()
            if mode == "tier2":
                # C1-R1-S4(b) — the EFFECTIVE root set, on a channel. `--root` is
                # validated as a directory and then silently replaced by
                # `Path.resolve()`, and neither the resolved set nor a collapse of two
                # declared roots into one appeared anywhere: the notes carry names and
                # the census is pinned "no paths, no roots". An operator debugging a
                # surprising `ambiguous 0` had literally nothing to read. Its OWN line,
                # deliberately not the census line, whose machine-independence is pinned
                # by return-convention.md:271.
                sys.stderr.write(
                    "ROOTS: " + ", ".join(_show_path(r) for r in _as_roots(root)) + "\n")
                sections = parse_receipt(text)
                artifacts = parse_artifacts(sections["ARTIFACTS"])
                trace = parse_trace(sections["TRACE"])
                witness = parse_witness(sections["WITNESS"])
                # SIEGE-R2BA-1 — the ONE buffer the two legs share, so the sha256 this
                # run verifies is a statement about the bytes its witness predicate is
                # evaluated against. See tier2_witness for the measured attack and for
                # what the carry does NOT close.
                bodies = {}
                # siege S-6 — an `RCPT v1` first line version-dispatches the ENTIRE v1.1
                # rule set off (TRIPWIRE-`none`, the SUPERSEDES justification rule, the
                # witness-evidence consequent), and nothing said so on any channel.
                # `return-convention.md:565` makes mixed-version runs legal, so this is
                # NOT a rejection and there is no `--require-v11` flag to invent here —
                # what was missing is that the gate could not tell "the v1.1 rules passed"
                # from "the v1.1 rules never ran", while quality-gate/SKILL.md:34,58 state
                # that every QG subagent emits v1.1 and treat Layer 2 as enforced.
                # Advisory, on the notes channel, exit code unmoved.
                v11 = parse_v11_sections(text)
                notes += ([] if v11 is not None else
                          ["UNVERIFIABLE: v1.1 Layer-2 rules not evaluated "
                           "(receipt declares RCPT v1)"])
                # #488 / T2 — `notes` is passed AS the out-param, not collected into a
                # second list: every drain site emits `notes + wit_notes`, so mirroring
                # into `notes` directly is what makes the PROVENANCE-ONLY lines reach
                # stderr on the LintError exits too.
                notes += tier2_artifacts(artifacts, trace, root, strict, cov, bodies,
                                         notes)
                wit_probe = {}
                if verdict in {"PASS", "FAIL"}:
                    # #486 / D7 — the bound now lives in tier2_witness, so a direct
                    # importer is bounded too and there is exactly ONE arm on this path.
                    # C1-R3-S2 — the RETURN VALUE IS DELIBERATELY DISCARDED. `wit_notes`
                    # is the single channel for this leg's notes: mirroring into it AND
                    # adding the return would print every witness note twice on any run
                    # where tier2_witness succeeds and a LATER leg raises (the handler
                    # drains `notes + wit_notes`, and both would hold them). Measured on
                    # exactly that shape — clean witness, then a --ledger mismatch — before
                    # this line stopped accumulating. tier2_witness mirrors at every one of
                    # its exits, so nothing is lost by ignoring the return here; other
                    # callers (--selftest, the direct-call tests) still use it.
                    tier2_witness(witness, trace, root, strict, verdict, cov,
                                  bodies, wit_probe, wit_notes)
                else:
                    # D8.2 sub-decision 5 — a BLOCKED receipt never enters the witness
                    # leg, so the collector would hear nothing from it and the line would
                    # read a bare `witness 0/0`. Every receipt carries a mandatory WITNESS
                    # line (return-convention.md:122), so a witness check ALWAYS exists
                    # and an unannotated 0/0 says one did not — indistinguishable from a
                    # PASS receipt with a structurally-absent witness.
                    cov.bump("not-applicable", "verdict-not-pass-fail")
                # #488 inquisitor/AV1 — LIFTED OUT of the `verdict in {PASS, FAIL}` arm,
                # which is where it used to sit. The witness LEG stays verdict-gated (D8.2
                # sub-decision 5 above, unchanged); the CONSEQUENT does not, because the
                # rule it enforces is not about the witness leg running — it is about
                # whether a supersession is backed by evidence. Nested in that arm, a
                # BLOCKED receipt took the `else:`, bumped `not-applicable
                # (verdict-not-pass-fail)` and never reached this test at all: three
                # byte-identical receipts differing ONLY in the VERDICT token exited
                # 1 / 1 / 0, the third retiring its predecessor with a witness naming a
                # file that does not exist. That is DEC-29's forbidden key verbatim — the
                # guard narrowed by SHAPE (the verdict), and the narrowing restoring a
                # fail-open — and it is the same shape the ⚠ note below already records
                # being closed for the PASS/FAIL pair; it was simply never closed for the
                # third verdict class. Tier-1's half of the rule (`lint_v11_local`:
                # `kind in {exec, grep}` AND `ran=TRACE#N`) is already verdict-independent,
                # so a BLOCKED receipt has to carry a shape-conformant witness and nothing
                # checked whether it resolved to anything; `return-convention.md` § The
                # Sweep step 3 tells the orchestrator to process SUPERSEDES with no check
                # of its own and does not condition that on the new receipt's verdict.
                #
                # On the BLOCKED path `wit_probe` is EMPTY by construction (tier2_witness
                # never ran), so `unsourced` is unset and `evaluated` is falsy and the
                # raise fires: a receipt that could not finish its work cannot retire a
                # peer's finding. That is the intended disposition, not a side effect —
                # the remedy is in the author's hands (return the SUPERSEDES as `none`,
                # or finish the work and return PASS/FAIL with a witness that resolves).
                if v11 is not None and v11["supersedes"] != "none" \
                        and not wit_probe.get("unsourced") \
                        and (not wit_probe.get("evaluated")
                             or wit_probe.get("result_discarded")):
                    # C1-R3-S1 — the exemption is keyed on `unsourced`: tier2_witness
                    # sourced NO artifact, so resolve_base never ran, verify_witness was
                    # never called, and `evaluated` cannot be set by any witness this
                    # receipt could have written. On the FAIL leg that is every kind=grep
                    # witness, because witness_art_name's payload sourcing is PASS-only —
                    # not a narrow range, not a well-chosen one. That is a hard structural
                    # BLOCK with no in-receipt remedy, on the shape return-convention.md
                    # makes the DEFAULT for research/judge dispatches with no shell — and
                    # the bullet below would blame "resolved to no evaluated predicate"
                    # when the witness resolved to nothing at all. lint_v11_local's
                    # declared over-approximation does not cover it: that one is about the
                    # TRIGGER, and its 0-site measurement is silent here because no
                    # committed corpus holds a FAIL + non-`none` SUPERSEDES row.
                    #
                    # ⚠ The first attempt keyed on `verdict == "PASS"` and the freeze-guard
                    # caught it: that exempts the WHOLE FAIL leg, including a witness that
                    # WAS sourced and merely resolved nowhere — a case whose remedy is
                    # ordinary (name a file that exists). Measured: such a FAIL receipt
                    # exited 0 while its byte-identical PASS twin exited 1, reopening
                    # siege S-7(a) for a whole verdict class. This is DEC-29 exactly:
                    # narrowing by SHAPE (verdict, or witness kind) silently restores a
                    # fail-open; the only safe key is whether the cited range addressed
                    # bytes. Do not re-narrow this on `verdict` or on `kind`.
                    #
                    # GH #501 LANDED, and it retired the exemption for the shape this
                    # note was about: the FAIL leg now sources a ranged payload, so
                    # `unsourced` is no longer set for the MANDATED form and the gate is
                    # armed on both legs again. What still reaches here is the residue —
                    # a FAIL witness with no range to source AND no EXEC `out=` to fall
                    # back to, which remains genuinely unsatisfiable.
                    #
                    # ⚠ Arming it is only real because `evaluated` is keyed on whether
                    # this leg's outcome can depend on the witness at all (verify_witness):
                    # `pattern and exit_success`, the exact antecedent of the leg's one
                    # raise. THREE forms of this key have now been wrong, all in the same
                    # direction — `exit_m or pattern` (QG-r1/S1: no exit clause at all,
                    # so the branch is inert), `exit_m` (QG-r2/S2: the PRESENCE of a
                    # token, DEC-29's forbidden key) — and this consequent consumes the
                    # flag, so each let a supersession survive on a witness that proved
                    # nothing.
                    #
                    # ⚠ QG-r2/S2 — what the `exit_m` form left open, and why the
                    # `or result_discarded` conjunct did NOT cover it: an exit-clause
                    # `expect-fail` (`exit!=0` / `exit=<N>`) derives no pattern from
                    # `_expect_fail_pattern`, and `result_discarded` is keyed on
                    # `pattern`, so NEITHER flag fired for it. A FAIL receipt retired a
                    # peer's finding on the same stderr line that billed its witness
                    # `witness 0/0 … not-applicable 1 (exit-clause-not-a-body-predicate)`
                    # — one `expect-fail` token from the shape QG-r1/S1 closed. The whole
                    # 436-test suite passed with and without the hole, because that arm
                    # had no pin at all.
                    #
                    # WHAT PINS WHAT (each verified by reverting the half on a copy of the
                    # tree, never by watching a pin go green — DEC-31):
                    #   * key → `exit_m`: test_501_fail_leg_exit_clause_expect_fail_cannot_
                    #     retire goes RED on BOTH kind=exec and ranged kind=grep, and
                    #     NOTHING else does — test_501_13 included.
                    #   * key → `exit_m or pattern`: that test AND test_501_13 (which pins
                    #     the `pattern` half at verify_witness's own level).
                    #   * the `or result_discarded` conjunct removed: NOTHING goes red —
                    #     437/437 still pass. Stated rather than left to be discovered,
                    #     because "the pin is green" is not evidence the guard is live.
                    #     The conjunct is REDUNDANT given the key above: `result_discarded`
                    #     is `pattern and not exit_success`, whose every case `not
                    #     evaluated` already covers. It is kept as defence in depth against
                    #     the two flags drifting apart — NOT as the arming mechanism, and
                    #     test_501_fail_leg_witness_with_a_DISCARDED_result_cannot_retire
                    #     now pins the KEY's behaviour on that shape, not the conjunct.
                    #
                    # Net on this leg: a predecessor is retired only when a body predicate
                    # was derived AND the cited entry's exit is 0 — and since
                    # `exit_success and not content_match` raises separately, only when
                    # that body also MATCHED (test_501_5's shape). The `unsourced`
                    # exemption above is the one remaining way past this consequent.
                    #
                    # ⚠ THE CORPUS FIGURE BOUNDS THE `PASS` POPULATION ONLY (QG-r2/S3).
                    # 21 of the 68 receipts in the three enumerated frozen corpora carry a
                    # non-`none` SUPERSEDES and ALL 21 are `PASS` — re-derived as
                    # {'n': 68, 'sup': 21, 'supfail': 0, 'fail': 19} — and running all 68
                    # through the CLI with and without this key gives byte-identical exit
                    # codes. As evidence ABOUT THIS CONSEQUENT that is VACUOUS: the corpora
                    # hold ZERO `FAIL` receipts carrying a non-`none` SUPERSEDES of any
                    # shape, so "0 exit codes move" cannot distinguish "the arming blocks
                    # nothing" from "the corpus contains none of the targeted shape". What
                    # it does bound is the `PASS` population, and that bound is real for a
                    # structural reason rather than a measured one: this key sits inside
                    # `if verdict == "FAIL"`, and the PASS leg sets `evaluated` at its own
                    # two sites, so no `PASS` receipt's exit code can move.
                    #
                    # siege S-7(a) — the Tier-2 half of the witness-evidence rule.
                    # Tier-1 checks the witness's SHAPE (`kind ∈ {exec, grep}`,
                    # `ran=TRACE#N`) and stopped there, so a shape-conformant witness
                    # whose Tier-2 disposition is `not-applicable` — no artifact name,
                    # a name that resolves nowhere, an unimplemented kind — retired a
                    # peer's FAIL finding, its tripwires and its cairn invariant at
                    # exit 0, having demonstrably evaluated nothing. The convention is
                    # explicit that the shape check is not the whole rule: "Tier-2
                    # then verifies the witness normally — supersession only survives
                    # if the witness demonstrably does NOT match expect-fail".
                    #
                    # This does NOT touch the rule's TRIGGER, which is #500's subject:
                    # the fail-closed over-approximation over EVERY non-`none`
                    # SUPERSEDES is left exactly as `lint_v11_local` states it.
                    # #488 warden-r2/F1 — the MESSAGE branches, the raise condition does
                    # NOT. Re-keying the condition on `verdict` is DEC-29's forbidden key
                    # (see the ⚠ note above; caught twice already in this file's history).
                    # But the single PASS/FAIL-shaped sentence was factually WRONG on the
                    # BLOCKED path: there the witness leg is verdict-gated OFF (D8.2
                    # sub-decision 5), so no predicate was ever evaluated because none was
                    # ever ATTEMPTED — "the witness resolved to no evaluated predicate"
                    # names a resolution that never happened and sends the author looking
                    # for a broken citation that is not the problem. The remedy differs
                    # too: on PASS/FAIL, cite a witness that resolves; on BLOCKED, there
                    # is no witness that can satisfy this consequent at all, so the only
                    # in-receipt move is `SUPERSEDES: none`.
                    raise LintError(
                        "SUPERSEDES requires witness ran=TRACE#N whose predicate was "
                        "EVALUATED at Tier-2 (witness-evidence requirement: this "
                        "receipt is BLOCKED, so the witness leg never ran and no "
                        "predicate was evaluated — a receipt that could not finish "
                        "its own work cannot retire a peer's finding, and no witness "
                        "satisfies this on a BLOCKED verdict; return "
                        "`SUPERSEDES: none`, or finish the work and return PASS/FAIL "
                        "with a witness that resolves)"
                        if verdict == "BLOCKED" else
                        "SUPERSEDES requires witness ran=TRACE#N whose predicate was "
                        "EVALUATED at Tier-2 (witness-evidence requirement: the "
                        "witness resolved to no evaluated predicate, so it "
                        "demonstrates nothing about the predecessor it retires)")
                # Part-3 receipt-ledger binding: only with an orchestrator-supplied
                # --ledger (no default-path synthesis). A mismatch is a hard FAIL
                # (strict-independent); absent --ledger is advisory UNVERIFIABLE, and
                # only when there IS a DISPATCHED line.
                if ledger is not None:
                    tier2_ledger(trace, ledger)
                elif any(t["verb"] == "DISPATCHED" for t in trace):
                    # C1-R3-S2 — appended to `wit_notes`, NOT to `notes`, purely to keep
                    # stderr in PRODUCTION order. Every drain emits `notes + wit_notes`,
                    # so anything added to `notes` after the witness call would sort ABOVE
                    # the witness-leg notes even though it was produced after them. This
                    # leg genuinely runs last, so it belongs at the end of the note band.
                    wit_notes.append("UNVERIFIABLE: ledger binding (no --ledger)")
                _drain(notes + wit_notes)
            elif ledger is not None:
                sys.stderr.write("UNVERIFIABLE: --ledger ignored under --tier1 "
                                 "(binding is a Tier-2 check; re-run with --tier2)\n")
        except LintError as e:
            # C1-R3-S2 — drain whatever the completed legs already learned BEFORE the
            # bullet. The notes loop lives at the end of the try, so every LintError jumped
            # past it and discarded the lot — on exactly the failing runs the notes were
            # added to make diagnosable. Each of the four note classes this branch added was
            # justified in writing by that argument: siege S-3(b) ("the refusal is a
            # property of the RUN, not of the failure, so it is reported whenever it
            # happens"), _refused_clause's docstring, siege S-6's v1.1-not-evaluated note,
            # and #486/S6's "a declared entry that is neither verified nor mentioned
            # anywhere on stderr is the fail-open shape". `REFUSED` is the sharp case: it
            # has NO census counter, so stderr is its only channel, and a refusal SHRINKS
            # what the linter can reach — the run it hid behind is precisely a run where an
            # artifact went unverified.
            #
            # Order is preserved (notes above the bullet, census last from the finally:),
            # so no existing reader moves; `notes` is bound above the outer try (see there)
            # so this cannot NameError on the paths that raise before the tier2 branch.
            _drain(notes + wit_notes)
            # C1-R2-S2 — the bullet channel is where receipt-authored text reaches stderr
            # un-escaped, and it is live on exactly the runs the census was built for
            # ("the failing run is exactly where the census earns its keep"). See
            # _show_diag.
            sys.stderr.write(_show_diag(e) + "\n")
            return 1
        except BaseException:
            # C1-R3-S2 (freeze-guard revision) — the third exit drains too. An
            # unclassified escape truncates the run just as thoroughly as a LintError, and
            # dropping what the completed legs had already diagnosed is the same
            # fail-open shape this fix exists to close. Drained BEFORE `cov.partial` so
            # the notes survive even if the re-raise is not caught anywhere above.
            _drain(notes + wit_notes)
            # #486 fixer / F3 — see the docstring. BaseException, not Exception: a
            # SystemExit or a KeyboardInterrupt truncates the run just as thoroughly as
            # an OSError, and the census must not claim otherwise. Nothing is swallowed
            # — the escape is re-raised unchanged, so the module guard and the caller
            # see exactly what they saw before.
            cov.partial = True
            raise
        return 0
    finally:
        # sub-decision 4 — NOTHING on --tier1. _verify_single serves both modes and main
        # defaults to tier1, so an unguarded finally would print an all-zeros line on the
        # default mode: exactly the shape sub-decision 3 forbids, on the path
        # hooks/rcpt-verify-hook.sh:76 runs.
        if mode == "tier2":
            sys.stderr.write(cov.render() + "\n")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage_exit()
    if argv[0] == "--selftest":
        return run_selftest()
    if argv[0] == "--eval":
        if len(argv) != 2:
            return _usage_exit()
        return run_eval(argv[1])
    # single-receipt mode — hand-parse flags (mirror check_*.py simplicity)
    mode = "tier1"
    roots = []            # #486 / D1 — --root is REPEATABLE; declaration order is D3's
    root_tokens = []      # C1-R1-S4 — the RAW spellings, for the collapse test below
    root_error = None     # C1-R1-S3/S4 — (census-code, bullet) deferred to _verify_single
    strict = False
    ledger = None
    path = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tier1":
            mode = "tier1"
        elif a == "--tier2":
            mode = "tier2"
        elif a == "--strict":
            strict = True
        elif a == "--root":
            i += 1
            if i >= len(argv):
                # SIEGE-R2BA-5 — `--root` as the FINAL token: a substitution that expanded
                # to nothing ate the root and this exit was silent.
                return _usage_exit(argv, "root-missing-value")
            # #486 fixer / F1 — an EXPLICITLY SUPPLIED root must be a real directory.
            # Unvalidated, `--root ""` becomes Path(".") -> the linter's cwd, and since
            # quality-gate/SKILL.md mandates a TWO-substitution command line run from
            # Bash (cwd = the repo), one swallowed shell substitution silently grew both
            # the probe set and the #397/C1 containment union to the whole checkout: a
            # receipt could declare a repo top-level file it never touched and come back
            # `artifacts 1/1`, exit 0 — byte-identical to the #486 fail-open this change
            # exists to close. A FILE passed as `--root` (the `<findings-root>` vs
            # `[FINDINGS_OUTPUT_PATH]` one-token slip) was a silent no-op for the same
            # reason. Both now exit 2 and NAME the offending root on stderr.
            #
            # The diagnostic deliberately does NOT go on the TIER2-COVERAGE: line — that
            # line's "no paths, no roots" machine-independence is pinned by
            # return-convention.md:271 — and the empty-string test is on the RAW token,
            # because Path("") is already Path(".") and would pass is_dir().
            #
            # Scoped to roots the caller actually passed: the no-`--root` default below
            # is untouched, verbatim.
            #
            # C1-R1-S3 — the ARGV-ERROR half and the TRANSIENT half are split, because
            # they are not the same failure. `--root ""` (a swallowed shell substitution)
            # and a `--root` naming an existing NON-directory (the `<findings-root>` vs
            # `[FINDINGS_OUTPUT_PATH]` one-token slip) are genuine invocation errors and
            # keep exit 2 verbatim. A root that simply does not EXIST is the normal
            # pre-write state of `<scratch-dir>/chunk-N`, which the reviewed subagent
            # creates — see _verify_single for why that must not skip Tier-1.
            tok = argv[i]
            root_p = pathlib.Path(tok)
            if tok == "" or (root_p.exists() and not root_p.is_dir()):
                # Quoted, because the empty-string case is the whole point and an
                # unquoted "" renders as nothing at all.
                sys.stderr.write(f"rcpt_verify: --root {argv[i]!r} is not a directory\n")
                # SIEGE-C4 — and SAY that verification did not happen, on the parsed
                # channel, in the `not-reached (<code>)` idiom. Gated on `--tier2` being
                # anywhere in argv rather than on `mode`, which is not final at this
                # point in the loop (`--root X --tier2` is a legal ordering); --tier1
                # emits no census line in any configuration (sub-decision 4).
                # SIEGE-R2BA-5 — that gate is now _state_not_reached's, shared with the
                # five sibling exit-2 paths. The emitted string is unchanged.
                _state_not_reached("root-invalid", argv)
                return 2
            if not root_p.is_dir() and root_error is None:
                # Deferred: Tier-1 runs first, then this raises. Never degraded to cwd —
                # the root is still appended, so the no-`--root` default cannot kick in.
                root_error = ("root-absent",
                              f"--root {tok!r} is not a directory (supplied root absent; "
                              f"Tier-1 ran, Tier-2 did not)")
            roots.append(root_p)
            root_tokens.append(tok)
        elif a == "--ledger":
            i += 1
            if i >= len(argv):
                # SIEGE-R2BA-5 — same shape as `--root` with no value.
                return _usage_exit(argv, "ledger-missing-value")
            ledger = pathlib.Path(argv[i])
        elif a == "-" or not a.startswith("--"):
            # SIEGE-C15 — a SECOND positional used to overwrite the first with no
            # diagnostic at all, so `… <receipt-A> <receipt-B>` linted B and silently
            # ignored A: the same argv set produced OPPOSITE verdicts depending on which
            # receipt came last. The mandated command line now carries four shell
            # substitutions into this loop, and one that expands to an extra token (or to
            # nothing, shifting a later token here) lands exactly on this branch. Rejected
            # rather than resolved by position, for the same reason parse_witness rejects
            # a second `pattern=` clause: two receipts are declared and the linter cannot
            # know which the caller meant.
            #
            # SIEGE-R2BA-5 — and this branch, which C15 ADDED one commit after C4
            # established the state-it-on-the-channel rule, is exactly the branch C15's
            # own rationale says a mis-expanded substitution lands on. It said nothing.
            if path is not None:
                return _usage_exit(argv, "two-positionals")
            path = a
        else:
            # SIEGE-R2BA-5 — an unrecognised `--flag` is the other way a mangled
            # substitution terminates the run.
            return _usage_exit(argv, "unknown-flag")
        i += 1
    if not roots:
        # Preserved VERBATIM as a one-element list: an invocation with no --root behaves
        # exactly as today (main:1683-1684 at 5d1fb15 did `root = pathlib.Path.cwd()`).
        roots = [pathlib.Path.cwd()]
    if root_error is None and len(root_tokens) > 1:
        # C1-R1-S4 — TWO DIFFERENT `--root` TOKENS THAT NAME ONE DIRECTORY.
        #
        # `--root` is validated with `is_dir()`, which FOLLOWS SYMLINKS, and `_as_roots`
        # then stores `Path.resolve()`. So the directory actually probed could differ from
        # the one the orchestrator named, and two declared roots could silently become
        # one, on no channel at all. Combined with the verified fact that
        # `<scratch-dir>/chunk-N` is created by the REVIEWED SUBAGENT's own write, that
        # handed the reviewed party control of the trust anchor: one `ln -s <dispatch-root>
        # <scratch>/chunk-1` turned the `--strict` cross-root ambiguity FAIL — one of the
        # two safety properties #486 introduces — into a clean exit 0 whose census is
        # byte-identical to a genuine two-root verification. It also achieves, from the
        # other side, exactly what quality-gate/SKILL.md:30 spends a paragraph forbidding
        # the orchestrator from doing (passing `<scratch-dir>` itself as a root).
        #
        # Scoped to DISTINCT SPELLINGS, which is what keeps criterion 6 intact where the
        # corpus pins it: the committed `two-root-dedup-noop` fixture declares the SAME
        # token twice, and repeating one token is still a byte-for-byte no-op. Two
        # different tokens resolving to one directory is not a no-op — under a mandated
        # two-root line it is a configuration error, and the honest thing is to say so
        # rather than to probe half of what was asked for and report nothing. Deferred
        # like the absent root, so Tier-1 still runs and the disposition is exit 1.
        seen = {}
        for tok in root_tokens:
            key = pathlib.Path(tok).resolve()
            if key in seen and seen[key] != tok:
                root_error = ("root-collapse",
                              f"--root {tok!r} and --root {seen[key]!r} name the same "
                              f"directory ({_show_path(key)}) — two declared roots "
                              f"collapsed to one, so the cross-root checks cannot fire")
                break
            seen.setdefault(key, tok)
    text = _read_stdin_arg() if path in (None, "-") else _read_path_arg(path)
    return _verify_single(text, mode, roots, strict, ledger, root_error)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except _PathReadError as e:
        sys.stderr.write(f"rcpt_verify: cannot read {_show_path(e.path)}\n")  # SIEGE-C2
        # SIEGE-R2BA-5 — the sixth exit-2 terminal state, and the one that does NOT go
        # through _usage_exit: _read_path_arg raises out of main entirely. The census is
        # emitted HERE rather than at the raise site because this is the only frame that
        # is guaranteed to be the CLI — main(argv=…) is called in-process by the tests,
        # where a raised _PathReadError is the caller's to handle and printing a census
        # line on its behalf would be this module writing to a channel it does not own.
        # sys.argv[1:] is the real process argv, which is what the gate must read (a
        # script path is not a flag). Ordered AFTER the diagnostic, as on the
        # `root-invalid` path. `--eval FILE` reaches the same raise and correctly emits
        # nothing: its argv cannot contain `--tier2`.
        _state_not_reached("receipt-unreadable", sys.argv[1:])
        sys.exit(2)
