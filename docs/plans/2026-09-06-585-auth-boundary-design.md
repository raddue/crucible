---
ticket: "#585"
title: "The orchestrator/subagent trust boundary on gate state"
date: "2026-09-06"
source: "design"
---

# #585 — the orchestrator/subagent trust boundary on gate state

**Status: design, pre-gate.** Deliverable is this document. No implementation is proposed for
immediate landing; §8 names five tiers (0-4) plus a cross-cutting liveness probe that is specified
and then withdrawn (§8.6), of which one tier
is already filed separately (#591) and one is blocked on a measurement (§10.1).

**Scope.** The two artifacts named in #585 — the quality-gate verdict marker
(`gate-verdict-<run-id>.md`) and the receipt-ledger dispatch binding
(`<dispatch-dir>/receipt-ledger.jsonl`) — and the general question the issue asks: is
convention-only protection an acceptable pattern, or does PR #583's accepted-risk rationale fail to
generalize?

**Out of scope.** The mechanical repair of `hooks/gate-ledger-guard.sh` (filed as **#591** — see
§4). The `SUPERSEDES` referential-integrity class (#586). Ledger lock liveness (#588).

**Citation anchor.** Every `hooks/gate-ledger-guard.sh` line number in this document is stated
against commit `ee471e6` (PR #594, merged 2026-09-06T19:40:44Z), which landed *after* both round-1
gate legs (red-team, siege) froze their review on `1888642` and repaired the dead payload shape this
document's Finding 2 identifies. Where a citation describes something #594 changed, this document
says so explicitly and dates it; where a defect this document relies on survives unchanged at
`ee471e6`, that is stated too (§4, §8.3(a)).

---

## 1. Answer, up front

Three findings — the first two verified on disk during this design run, the third an argument from
them:

1. **#585's central premise is stale, not settled either way.** The Claude Code harness *does*
   expose caller identity to hooks on 2.1.263. It may have been true when the issue was written —
   the repo's only evidence of absence is an April-2026 capture, ~4.7 months before #585 was filed on
   2026-09-04, and the landing version is unknown (§10.2). A mechanical discriminator exists today
   and does not require harness changes, a secret, or a signing scheme — but it is a **cost-raiser**
   on the tool-call writer population (§8), not an authentication mechanism, and it does not close
   the boundary: a subagent with `Bash` can issue the protected write from a second harness instance
   it spawns, whose payload carries no `agent_id` at all (§6/C6, §7.1, §8.3).
2. **The enforcement layer this issue assumes as its baseline was inert for ~4.8 months and was
   repaired mid-review.** The one hook that backs the convention was payload-broken, test-certified-
   broken, unregistered, and undistributable from `84b1f5c` (2026-04-13) until PR #594
   (`ee471e6`, 2026-09-06T19:40:44Z) repaired the payload shape and the test suite. The delta in
   #583's "hasn't gotten worse" was measured against a mechanism that did not exist at the time. Not
   every defect §4 documents was fixed by #594 — see §4 and §8.3(a) for what survives.
3. **#583's acceptance does not generalize.** Its stated premises are diff-scoped claims about one
   PR; its unstated premises are falsified by workflows Crucible ships today.

The recommendation is **not** "close #585 with a mechanism." It is: write the boundary down
honestly, then take a *scoped population reduction* that raises cost and claims only what it can
carry — never that it authenticates the caller. The reason is §6 — an `agent_id` check as naively
scoped relocates the vulnerability class rather than closing it, which is precisely the pattern #567
records this repo hitting twice already, and it has a one-command escape (§6/C6) that this document
does not paper over.

---

## 2. What the mechanisms actually are

### 2.1 The gate-verdict marker

`skills/quality-gate/SKILL.md:1153-1250` ("## Verdict Marker") writes
`~/.claude/projects/<project-hash>/memory/quality-gate/gate-verdict-<run-id>.md` on **all** exit
paths (`:1157`), using the Write tool. `skills/warden/SKILL.md:642` emits the single
build-`PipelineID`-tagged aggregate marker. Key fields: `Verdict`, `Phase`, `PipelineID`,
`ArtifactHash`, `RunID`.

Two readers turn a decision on it:

- `hooks/gate-ledger-guard.sh:230-262` (at `ee471e6`; `:226-258` at the pre-#594 `1888642` this
  design's review legs read) — a `PreToolUse` hook on Write/Edit. When a write would
  introduce a new `Status: PASS` into `build-gate-ledger.md`, it globs `gate-verdict-*.md` for a
  marker matching `(PipelineID, Verdict: PASS, Phase)` and `exit 2`s if none matches.
- `skills/build/SKILL.md:232-244` — build's own Verdict Marker Verification, in-context, before
  writing the phase PASS. **It then deletes the marker** (`:244`).

The phase gate at `skills/build/SKILL.md:222-228` blocks Phase N until Phase N-1 is
`PASS`/`COMPLETE`.

### 2.2 The receipt-ledger dispatch binding

`skills/shared/return-convention.md:129-131` (Parent-Child Receipt Binding): on accepting a child
receipt, the orchestrator records `{dispatch_id, phase, rcpt_sha256, verdict}` into
`<dispatch-dir>/receipt-ledger.jsonl` — canonical location per
`skills/shared/dispatch-convention.md:291-303`. `scripts/rcpt_verify.py::tier2_ledger` (`:5659-5712`)
then requires every `DISPATCHED … verdict=<V> rcpt-sha256:<H>` TRACE line to bind to a ledger row on
the triple `(dispatch_id, rcpt_sha256, verdict)`. Its stated purpose is rejecting a
**parent-fabricated child verdict**.

The binding is a **membership test with no hash recompute** (`:5673-5675` — the verifier never holds
the child receipt's text). A forged row is therefore sufficient; nothing re-derives it.

Beyond the linter, a ledger row is also the closure oracle for cairn obligations
(`skills/shared/cairn-convention.md:134`, Rule 2 — `[closed-by: <prefix-12>]` resolves against a
row's `rcpt_sha256` and requires `verdict=PASS`), and Rule 1 (`:129`) counts rows per phase.

### 2.3 What actually protects them today

Nothing enumerable. This design run searched `skills/`, `hooks/`, `scripts/` and `docs/` for a rule
forbidding a subagent from writing either file. **No such rule exists.** The closest statements are
descriptive, not prohibitive: `dispatch-convention.md:293` ("written by the orchestrator"),
`quality-gate/SKILL.md:1146` ("the build orchestrator is responsible for their lifecycle"), warden
I-W7 (`warden/SKILL.md:678`, motivated at `:469-476` by two *honest* writers colliding, not by
forgery).

This matters more than it looks. **A subagent that writes either file violates no written rule.**
The protection is not a convention a subagent could be said to break; it is an inference readers
draw from prose that never addresses the question.

Two exposure facts compound it:

- `PipelineID` is `date -u +build-%Y%m%d-%H%M%S` (`skills/build/SKILL.md:149`), stored `0644` in a
  well-known path and carried in the pipeline-active marker the subagent reads
  (`dispatch-convention.md:151`). There is no secret to protect.
- The marker directory and the calibration-ledger directory are ordinary `0755` user-owned
  directories. There is no permission boundary of any kind.

---

## 3. Finding 1 — the caller-identity signal exists

#585 states:

> `gate-ledger-guard.sh` also receives no caller-identity signal (top-level session vs.
> Task-dispatched subagent) to check against, regardless of what's stored where.

**This is false on Claude Code 2.1.263**, measured three independent ways during this design run:

**Live probe.** Two isolated headless `claude -p --settings <tmp>` runs (throwaway settings file in
scratch; no shared config touched) with a `PreToolUse` logger:

| `tool_name` | `agent_id` | `agent_type` |
|---|---|---|
| `Bash` (parent) | absent | absent |
| `Agent` (the dispatch call itself) | absent | absent |
| `Bash` (inside an `Explore` subagent) | `a08ae1f8cf6fe921e` | `Explore` |
| `Write` (depth-1 `general-purpose`) | `a5154d4958b92e1dd` | `general-purpose` |
| `Bash` (**depth-2** sub-subagent) | `a3cfad1ee2e291d5e` | `general-purpose` |

**Binary self-documentation.** The installed harness carries, in its hook-input schema strings:

> "Subagent identifier. Present only when the hook fires from within a subagent (e.g., a tool called
> by an AgentTool worker). Absent for the main thread, even in `--agent` sessions. **Use this field
> (not `agent_type`) to distinguish subagent calls from main-thread calls.**"

**Official docs** (`code.claude.com/docs/en/hooks`) state that hooks run inside subagents and that
`PreToolUse` fires there, and list `agent_id` / `agent_type` as the two additional fields.

Three consequences:

- **`PreToolUse` fires inside subagents.** The guard *does* see a subagent's Write. It simply has no
  check for it (and currently cannot fire at all — §4).
- **`agent_id` is a clean boolean discriminator for the call it is stamped on**, stable per
  subagent instance, at any nesting depth. It is stamped by the harness, not read from
  `tool_input`, so a subagent cannot *edit* it out of a call it issues. It can, however, avoid
  issuing the call at all (§6/C6, §7.1).
- **`session_id` and `transcript_path` are NOT discriminators** — a subagent's payload carries the
  *parent's* values, byte-identical. This is the grain of truth #585 reasoned from, and any design
  keying off those two fields would be wrong.

**In fairness to the issue:** `agent_id` is absent from the repo's own April-2026 capture
(`hooks/tests/fixtures/agent-pretooluse-sample.json`), and the upstream request for it was closed
not-planned. The premise was plausibly true when written. Treat it as **stale, not absurd** — and
note the design consequence: whatever is built on this field needs a version floor and must not
degrade silently below it (§8.3, §10.1).

**What survives from #585's reasoning, and should be preserved:** its claim that there is *nowhere
to keep a secret out of subagent reach* is still correct. Same uid, same filesystem, no privilege
gradient. The fix does not need a secret; it needs a **caller label on the tool-call path**, which
the harness supplies for that path only. This design replaces a **secrecy** argument with a
**cost** argument — not an authenticity one (§7.1, §8, §6/C6).

---

## 4. Finding 2 — the baseline enforcement has never run

Filed separately as **#591**; summarized here because it invalidates a premise of #585 itself.
**This finding is now historical** — PR #594 (`ee471e6`, merged 2026-09-06T19:40:44Z) repaired the
payload shape *after* both this design's review legs froze on `1888642`. The finding still stands
and is still this document's most important empirical result: it establishes there was no baseline
to measure #583's acceptance against (§5.2/P5), for ~4.8 months, on the merge target, up until four
hours before this design gate ran. What follows is stated in the past tense, with the terminus PR
#594 supplied.

- **Dead payload shape (2026-04-13 – 2026-09-06T19:40:44Z, repaired by #594).** At `1888642`,
  `hooks/gate-ledger-guard.sh:27` read `.tool`; `:41`/`:49`/`:50`/`:99` read `.input.*`. The live
  payload is `.tool_name` / `.tool_input.*` — per the repo's own committed capture
  (`hooks/tests/fixtures/README.md:36`: "Tool-name field `.tool_name` — **NOT** `.tool`") and the
  sibling hook `hooks/build-routing-advisor.sh:84`, which had the fallback the guard lacked. `TOOL`
  was always empty → `exit 0` on every real invocation for the whole interval. Reproduced directly at
  the time: the real shape allowed a forged PASS; only the test shape blocked. **At `ee471e6`**, line
  31 reads `TOOL="$(echo "$INPUT" | jq -r '.tool_name // .tool // empty' 2>/dev/null)"` — the
  canonical field with a legacy fallback — and the `.tool_input.*` reads sit at `:45`, `:53`, `:54`,
  `:101`. The dead `.tool`-only read is gone.
- **Tests encoded the bug, and were also repaired by #594.** At `1888642`,
  `hooks/tests/test-gate-ledger-guard.sh:83-95` built every fixture in the dead shape; all 22 cases
  passed against a hook that could not fire, and `run_tests.sh` was green throughout. **At
  `ee471e6`**, the same helper builds canonical `{"tool_name":…,"tool_input":{…}}` fixtures, a
  dedicated `make_legacy_json` helper and two new tests (21, 22) exercise the `.tool`/`.input`
  fallback explicitly, and three further tests (23–25, from PR #583's own warden gate: CHAIN-N1,
  R2BA-1, R2BA-3) cover an Edit-simulation matcher rewrite done in the same PR. 25 cases, still
  green — but now against a payload shape that matches production.
- **Registration and install path — unchanged by #594, still true.** `~/.claude/settings.json`'s
  `hooks` block holds only `Notification` and `SessionStart`; `settings.local.json` has no `hooks`
  key. `hooks/README.md:137`'s "Registered in user-global `~/.claude/settings.json`" is stale — and
  `skills/quality-gate/SKILL.md:1022` already contradicts it in-repo, dated 2026-08-14.
  `.claude-plugin/plugin.json` declares `"skills": "./skills/"` and **no `hooks` key**. The plugin
  ships zero hooks; registration is a manual per-machine settings edit. This is the mechanical cause
  of the inertness that ran for ~4.8 months: nothing installed the hook, and nothing noticed it
  wasn't installed. #591's items 1-2 (payload shape, live-fixture tests) are what #594 landed; item 3
  (install path) is still open — see §10.3.
- **Timeline.** Introduced `84b1f5c` 2026-04-13. Found by #583's siege leg as SIEGE-CA-1; a first fix
  landed in `a387f18`, which was **not an ancestor of `main`** (it existed only on the unmerged
  `fix/488-c1-receipt-name-space`) and never shipped. The payload shape was repaired for real in
  `ee471e6` (PR #594, 2026-09-06T19:40:44Z) — **~4.8 months inert, from `84b1f5c` to `ee471e6`**, on
  the branch this design's own review legs froze on.

**Two lessons this forces onto the present design:**

- **L1 — absence-of-block is not a success signal.** A no-op guard and a satisfied guard are
  byte-identical from the orchestrator's view: both are a silent `exit 0`. Any mechanism proposed
  here must carry a **positive liveness signal** — the pipeline must be able to assert *"the check
  ran and answered"*, not infer it from nothing having happened. (Compare the standing lesson in
  `verify-systematically-not-when-suspicious`: build self-asserting probes; do not rely on suspicion
  to trigger a re-check.)
- **L2 — tests that mirror the implementation's assumptions certify nothing.** Twenty-two green
  cases over a dead payload shape is the strongest argument in this repo's history for driving at
  least one test from a **live-captured** fixture.

---

## 5. Does #583's acceptance generalize? — No

The maintainer's rationale, verbatim:

> Accepting this as a known risk for PR #583 specifically: the underlying trust model hasn't gotten
> worse because of this PR, and the fix's own scope (F1/CHAIN-1/IT-1) doesn't touch this attack
> surface.

### 5.1 Decomposition

| # | Premise | Stated? | Property of |
|---|---|---|---|
| P1 | "the underlying trust model hasn't gotten worse because of this PR" | stated | **the PR's diff** |
| P2 | "the fix's own scope doesn't touch this attack surface" | stated | **the PR's diff** |
| P3 | a maintainer was supervising this run and read its output | implicit | **the run** |
| P4 | reviewers were Crucible's own pinned agent types over maintainer-authored artifacts | implicit | **the run** |
| P5 | convention **plus the guard hook** is the baseline the delta is measured against | implicit | **the mechanism** |

### 5.2 Why each fails to carry forward

**P1 and P2 are non-regression claims.** They are sound as a reason not to block one PR mid-gate.
They establish nothing about whether the surface is safe: a surface that was already open stays open
when a diff doesn't touch it. They are also not re-derivable by anyone but the person holding that
diff — so they can never become a standing property of the mechanism, only a per-run judgement.

**P2 fails whenever the reviewed artifact is untrusted input.** `/temper`, `/delve`,
`/code-review`, `/siege` and `/warden` all accept a PR id or `base..head` range
(`skills/warden/SKILL.md:614`) — including an outside contributor's PR or a vendored dependency. The
*fix's* scope is then irrelevant: the **artifact** is the attack surface, because the artifact is
what the subagent reads, and every Crucible agent def is full-tools (`agents/crucible-red-team.md`,
`crucible-qg-fix.md`, `crucible-qg-judge.md`, `crucible-qg-verifier.md` declare only
`name`/`description`/`model` — no `tools`, no `disallowedTools`).

**P3 fails on any unattended run.** `/spec` is the extreme case — explicitly the highest-volume gate
dispatcher, running potentially dozens of gates autonomously with no human between a gate verdict
and the next wave (`skills/spec/SKILL.md:509-511`, `:171`, `:316-336`). `/build` left running
overnight is the same shape.

**P4 fails on a documented degradation path.** `skills/quality-gate/SKILL.md:244` and `:535` specify
that if `crucible-red-team` / `crucible-qg-fix` fail to resolve, the dispatch **falls back to
`general-purpose` on the orchestrator's inherited model**, with a one-time warning. Reviewer identity
and model are not guaranteed by the mechanism.

**P1/P2 were arguably false for #583 itself.** #583's diff touched `hooks/gate-ledger-guard.sh` and
`scripts/rcpt_verify.py`. In this repo that is not an edge case — Crucible's *product* is the gate,
so the modal `/build` here has reviewer subagents holding write access to the very files that
certify the review. #583's own siege leg had to fix the enforcement hook mid-gate.

**P5 is simply false** (§4). The delta was measured against a baseline that did not exist. "Not
worse than nothing" is true, and not reassuring.

### 5.3 Verdict

The acceptance is a property of **PR #583**, not of the mechanism. #585 cannot be closed as
"accepted risk, documented" **on #583's rationale.**

It could, in principle, be closed by an explicit **per-run acceptance predicate** — a condition a
run can evaluate about *itself*, e.g. *"accepted only when the artifact under review is
repo-internal and maintainer-authored, a human reads the verdict before the next phase, agent-def
resolution did not degrade, and the guard is installed and demonstrably firing."* Note that under
today's state the last conjunct is **false everywhere**, and that today the gate can evaluate none
of the four. Until it can evaluate at least the last one, the acceptance is unrepeatable by
construction — and that condition cannot be met: a live enforcement signal is what would make it
evaluable, and §8.6 establishes that none can be safely specified without a consumer-side change this
document declines to design. **A repeatable per-run acceptance predicate is therefore not achievable
by anything this design ships; it is recorded as an open gap, alongside L1 (§9), not deleted and not
resolved.**

**#585 may instead be closed on an accurate documentation deliverable** — Tier 1 shipped alone, with
§8.2's points 3 and 5 amended to state that no mechanism exists; §13 AC 9 states the conditions. This
is a deliberate maintainer decision, not an oversight: #585 ships a document and no enforcement, and
this document's own standard — that it must not overstate what it delivers — applies to its own
close-out condition too.

---

## 6. The class

Per the standing lesson from #567 (redesign-doesn't-close-the-class, recorded twice) and the leg-3
stagnation handoff's "the fix has been happening at the wrong level", this design states the class
before the mechanism.

> **Class.** A party whose work the gate is judging can write — or disarm the reader of — the
> artifacts the gate reads to decide.

Members, in descending damage:

| # | Member | Status under this design |
|---|---|---|
| C1 | subagent → the guard script itself | **open** — §8.4/Tier 3 is blast-radius reduction, not a closure; false in the modal on-this-machine config (S585-1, §8.4) and open against a subagent that targets the install path deliberately; this is the sharpest one |
| C2 | subagent → `gate-verdict-*.md` via Write/Edit | closed by §8.3(a) **only if** the rule is evaluated on the *simulated post-write file state*, never the payload delta — copying the existing guard's delta-first Edit early-exit (still live at `ee471e6:59-61`) reproduces the bypass instead of closing it (F2/S585-4) — **and only if A1 holds** (§10.6): an un-canonicalized `file_path` lets a symlink or `..`/`//`-laundered write past the marker glob entirely, unmeasured |
| C3 | subagent → protected paths via `Bash` / `python -c` subprocess | **open** — no tier in §8 specifies a Bash/subprocess rule; only OS-level separation (§7.2) closes it. A command-text blocklist was considered and rejected as the recorded whack-a-mole shape (#567; #488 c1 leg-3) |
| C4 | subagent → `receipt-ledger.jsonl` row | **split.** *Fabricated-row half* — **open here; assigned to #586** (proposed mechanism: the orchestrator passes the expected predecessor identity on argv, so the verifier resolves nothing against the store — explicitly not re-derivation from the predecessor's own bytes, since the on-disk copy sits in the attacker-owned dispatch root and hashing it would recreate the class one level down). **#586 is OPEN and pre-gate as of 2026-09-06; this document does not verify that mechanism, and its status here is contingent on #586 landing and being gated.** Path-exposure (the ledger living inside the subagent-writable dispatch root) is **reduced, not closed**, by §8.5 (relocation = obscurity, not authentication) |
| C5 | orchestrator → everything | **not closable in-band** (§7.1) |
| C6 | subagent → nested harness instance (`claude -p`, `--settings`, `--dangerously-skip-permissions`) | **open, not reducible by any tier here** (F1). A subagent with `Bash` issues the protected write from a second harness instance it spawns; that instance's `PreToolUse` payload carries no `agent_id` at all, and `--settings` makes it load no hooks and no `permissions.deny` rules either — voiding §8.3, §7.4, and §8.4's deny-rule half in one move |
| C7 | subagent → `build-gate-ledger.md` via non-`PASS` gate-satisfying tokens (`COMPLETE`, `SKIPPED`+`Acknowledged: true`) | **open** — no tier in §8 applies any caller check to these tokens; `hooks/tests/test-gate-ledger-guard.sh`'s own Test 9 ("COMPLETE write to ledger, exit 0") certifies the gap stays open. **Scoped to non-`PASS` tokens only — the `PASS` token has its own, separately forgeable gap, C8, not covered by this row** |
| C8 | subagent → `build-gate-ledger.md`'s `Status: PASS` write, forged with zero verdict markers ever created (S585R2-1) | **open, Critical** — no tier in §8 applies any caller check to this write; the marker-driven guard (§2.1) is defeated in two ordinary `Write` calls against an empty marker directory: Write #1 strips `PipelineID:`, so the phase-delta scan (`gate-ledger-guard.sh:162-181` @`ee471e6`) finds nothing new and returns at `:187-189`, before the PipelineID-missing block (`:195-198`) is ever reached; Write #2 re-stamps a fresh attacker `PipelineID`, which `PIPELINE_CHANGED` (`:157`) misses because it requires `-n "$EXISTING_PID"`, emptied by Write #1. Tier 2 (§8.3) does not narrow this by one call — the attack never touches a marker |
| C9 | subagent → hook registration / `permissions.deny` store (`~/.claude/settings.json`) | **open, residue (S585-2)** — same-uid writable; `jq 'del(.hooks)'` yields valid JSON, a one-command disarm of the entire enforcement layer that leaves the guard script's content and its registered path untouched; §4 treats this as a distribution problem, never an adversary one |

**C1 is the finding that reshaped this design.** The guard is registered as a *command invocation of
an on-disk script* — `"command": "bash hooks/gate-ledger-guard.sh"` (`hooks/README.md:91`), a
**repo-relative** path. Registration is captured at session start; **the script body is re-read by
`bash` on every invocation.** An edit to the guard therefore takes effect on the very next tool call
*in the same session*, not the next run.

So a naive "protect the marker and the ledger" rule leaves the cheapest bypass untouched:

```
Write hooks/gate-ledger-guard.sh   →   (guard is now `exit 0`)   →   Write gate-verdict-*.md
```

This is a shipped workflow, not a hypothetical: `crucible-qg-fix` is a full-tools subagent whose job
is editing the artifact under review; CLAUDE.md mandates gating this repo with its own gate; and
#583's siege leg edited that exact file mid-gate.

Adding `hooks/**` to a deny set does **not** fix it — that wedges Crucible's own `/build` on itself.
The coherent answer is to stop enforcing from inside the repo under review (§8.4).

---

## 7. Options considered and rejected

### 7.1 Authenticate the orchestrator — impossible, and the framing must be split

The orchestrator is itself an LLM. Any token it can present, it can mint. Any file it must write
consistently, it can write consistently. Any hook that permits its writes permits its forged writes.
There is no in-band construction distinguishing *"the orchestrator concluded PASS honestly"* from
*"the orchestrator wrote PASS"*. This is not a gap to close; it is the shape of the problem.

**#585 conflates two edges with opposite answers, and the right response is to split them — but
neither edge gets clean authentication (§6/C6):**

- **Subagent → gate state, via the tool-call path:** `agent_id` is a real, harness-stamped signal a
  subagent cannot suppress *for that call*. **Corrected statement (F1):** the harness decides what
  `agent_id` says for calls issued by that harness instance; a subagent with `Bash` can issue the
  protected write from a *different* harness instance it spawns (`claude -p --settings /tmp/x.json
  '<write>'`), and that child's `PreToolUse` payload carries no `agent_id` at all — the binary's own
  schema says the field is absent for the main thread, and the child's main thread is what issues the
  call. `--settings` replaces the settings file wholesale, so the child also loads no hooks and no
  `permissions.deny` rules. So `agent_id` is a **cost-raiser** on the tool-call writer population, not
  a caller authenticator: it is not the harness alone that decides what the field says, because the
  subagent decides *which harness instance* issues the call.
- **Orchestrator → gate state:** authentication is the wrong frame. The only anchors are
  deterministic evidence recomputable by a non-LLM program, and the human maintainer reading the
  transcript. The `/warden` → maintainer-confirmation workflow *is* that anchor operating.

Corollary the docs should adopt: **the verdict marker is not a security token; it is a continuity
token between two phases of one LLM.** Its achievable job is preventing an honest bug — or a
post-compaction orchestrator that lost the gate result — from silently recording PASS.

### 7.2 Per-run token / shared secret / HMAC / signing — reject

#585's own reasoning is correct. An HMAC key must be readable by the hook, an external process at
the same uid, hence readable by the subagent's Bash. There is no privilege gradient to hide it
behind. A real asymmetric scheme needs either an unlocked agent (same access ⇒ same forgery) or a
per-gate passphrase prompt, which walks straight into **#484** (standalone `/quality-gate` blocking
prompts stalling for hours — filed, unfixed).

**The one sound variant, named so it is not silently omitted:** run reviewed subagents under a
different uid or in a container. Kernel-enforced separation genuinely closes both edges. It is
outside Crucible's control — Crucible is a skills library and does not launch the harness. Correct
disposition: an upstream harness feature request, recorded here as *the only sound closure, not
available to us*.

### 7.3 Multi-artifact re-derivation — cheapest subset only, advisory

Requiring the marker to be consistent with independently-written artifacts (`convergence-log.jsonl`,
`defer-ledger-<run-id>/` round count, `len(ScoreTrajectory) == Rounds`,
`Verdict: PASS ⟹ Reason: clean-pass`) defends an honest bug strongly and raises a shortcut's price.
It does **not** defend prompt injection — "write these five files" is the same instruction, only
longer — and every input is a file the same uid can write.

The decisive argument against the full version is cost shape: the checker must encode a slice of the
quality-gate spec, and *that spec churns* (`MarkerVersion: 2`, `MinorTrajectory` #362,
`FanOutRounds`/`FanOutCheckCount`/`FanOutErrorCount` #546, `LookHarderSkippedReason`,
`PersistentCheckCount`). A stale invariant wedges every phase transition, mid-pipeline, for the
maintainer to diagnose. Take only the cheapest, most stable predicates, **as a fail-loud advisory
warning, never a block.**

### 7.4 Agent tool restriction / path-scoped deny rules — not a closure

A uniform tool denial is structurally impossible: `crucible-red-team` must Write
`round-N-findings.md` into `<findings-root>`, the `TIER2-COVERAGE:` capture requires Bash
(`quality-gate/SKILL.md:1020`), and `crucible-qg-fix` must Write the artifact under review.

Path-scoped `permissions.deny` fails for a different reason: it is **not caller-scoped**. A rule like
`Edit(**/gate-verdict-*.md)` applies to the orchestrator too — the legitimate writer — so it breaks
the mechanism instead of protecting it. It becomes usable only *in combination with* §8.3's caller
discrimination, at which point §8.3 is already doing the work.

Tightening the three find-and-report-only agent defs to the tools they actually use remains
independently good hygiene, consistent with CLAUDE.md's "find-and-report-only skills don't edit
code". **File separately; it does not stand in for #585.**

### 7.5 Divergence-check against the central calibration ledger — defer

`~/.claude/crucible/ledger/runs.jsonl` sits outside the repo, the dispatch root, and project memory,
and is written by a deterministic CLI rather than by prose. A gate that never ran leaves an
*absence* there contradicting a PASS in the gate ledger.

Against it: #460 deliberately moved **every in-repo ledger reader** to `raddue/crucible-eval`;
adding one back re-imports the class just extracted. The file is same-uid writable and
`ledger_append.py` is a plain stdlib appender, so the absence is as fillable as the marker is
forgeable. And there is an unresolved seam — `ledger-append.md:172` maps marker `RunID` → ledger
`run_id` 1:1, while `:253` says forward-captured `run_id` is a UUIDv7 and
`quality-gate/SKILL.md:1016` makes the run-id a timestamp. **Resolve that seam independently; it may
be a latent defect. Revisit this option only if a reader returns to Crucible.**

---

## 8. Recommendation — honest boundary plus a cost-raiser, not a mechanism that closes it

**Dependency graph, stated once, correctly (fixes SP1's self-contradiction — the previous draft
called Tier 2 "independent" while separately making it depend on both Tier 0 and Tier 3):**

- **Tier 1 is independent of everything and ships alone, first.**
- **Tier 0 (#591) is a hard prerequisite for Tiers 2 and 3.** Items 1-2 (payload shape, live-fixture
  tests) already shipped — see §4 — via PR #594. Item 3 (install path) has not, and Tier 2 cannot
  claim even its cost-raising effect durably without it (next point).
- **Tier 2 MUST NOT land without Tier 3.** Per §6/C1, Tier 2 alone makes the guard script the new
  single point of failure while leaving it unprotected — one write, same session — which is the
  exact class-relocation #567 records this repo doing twice already. This is a hard ordering
  constraint, not sequencing advice (§13 adds an acceptance criterion for it).
- **Tier 4 is independent of Tiers 0/2/3**, but its ledger-writer enumeration depends on §10.1 (A2)
  the same way Tier 2 does — it can land whenever §10.1 is resolved.

**What no tier here does, stated up front so §8.3 is not read as more than it is:** no tier
authenticates the orchestrator (§7.1/C5), no tier closes the `Bash`/subprocess leg (§6/C3), no tier
touches the nested-harness escape (§6/C6) — a subagent that issues the protected write from a
`claude -p` child it spawns is not blocked by anything below, and no probe ships (§8.6), so nothing
reports on this path at all — and no tier here closes C4's fabricated-row half, which is assigned to
#586 and stays open until #586 lands and is gated, and no tier here applies any caller check to
`build-gate-ledger.md`'s non-`PASS` gate-satisfying tokens (§6/C7) — nor to the ledger's `Status:
PASS` write itself, which is forgeable in two `Write` calls with zero verdict markers ever created
(§6/C8). **Tier 2 is a cost-raiser on the
tool-call writer population. It is not an authentication mechanism, and this document does not call
it one anywhere in this document.**

### 8.1 Tier 0 — repair the enforcement that exists (#591 — items 1-2 shipped via PR #594, item 3 open)

Payload-shape fix, tests driven from the committed live fixture, an install path, a liveness signal.
This is not #585's design question; it is a shipped defect. It nonetheless **precedes** everything
below, because every mechanism here is a hook, and a hook that is broken and uninstalled is a
mechanism in name only. **Items 1-2 landed in PR #594 (`ee471e6`, 2026-09-06T19:40:44Z) — see §4 for
what changed.** Item 3, the install path, is unshipped and is also Tier 3's mechanism (§8.4, §10.3);
it is the largest remaining piece of this tier and is roughly ten lines for the mechanical part.

### 8.2 Tier 1 — write the boundary down (ship first, ships alone)

A trust-boundary section in `docs/architecture.md` (or a new `docs/trust-model.md`) stating, in
these words:

1. Crucible's gate integrity is anchored in the maintainer reading the transcript and in durable
   deterministic evidence — **not** in any in-band mechanism.
2. Every file-based check in the pipeline (verdict marker, receipt-ledger binding, convergence log)
   is **tamper-evidence and coordination**, not authentication.
3. **As published (Tier 1 alone), no cost-raiser exists on either edge.** If Tier 2 ships, the
   **subagent edge**, on the tool-call path only, would be *cost-raised* by a harness signal (§8.3) —
   raising the bar on the unwatched writer population, not closing the boundary — but even then it
   has a one-command escape (§6/C6): a subagent with `Bash` can spawn a second harness instance and
   issue the write from there, unstamped. The **orchestrator edge** is not closable in-band at all,
   with or without Tier 2 (§7.1).
4. The only sound closure for either edge is OS-level separation, which the harness must provide
   (§7.2).
5. Enforcement liveness is **not** established by any mechanism this design ships; the only candidate
   probe (§8.6) cannot be given a safe canary and is not recommended. Absence of a block is not
   evidence of enforcement (L1).

**This is the most durable deliverable in this document and it should be written first, not last.**
Cost is ~40 lines of prose; blast radius is zero; reversibility is total. It is also the thing that
would have stopped this issue's premise from going stale for 4.8 months, and it discharges the
standing obligation created by §2.3 — that the protection is currently an inference, not a rule.

A cost-raiser advertised as a boundary is worse than an honestly-labelled convention, because the
label invites reliance the mechanism cannot bear. That is the same failure #567 records twice.

### 8.3 Tier 2 — `agent_id` cost-raiser on the tool-call path, with two mandatory refinements

**This is a cost-raiser, not an authenticator (§6/C6, §7.1, §8's preamble).** It raises the bar on
the *tool-call* writer population — a subagent using `Write`/`Edit` directly — and does nothing
against a subagent that issues the same write from a nested `claude -p` instance it spawns, which
carries no `agent_id` at all. Extend the guard (after Tier 0) so that a **dispatched subagent using
Write/Edit** cannot write the verdict marker:

```
AGENT_ID="$(jq -r '.agent_id // empty')"     # present ⇔ subagent (this tool call), absent ⇔ main
                                              # thread OR a subagent that routed around this call
                                              # entirely (§6/C6) — the two are indistinguishable here
```

Two refinements are **required**, not optional; without either, this tier is a regression.

**(a) Gate on content, not path — and evaluate the content of the *resulting file*, never the
payload delta (F2/S585-4).** Block a subagent marker write only when the **post-write file state**
carries a `PipelineID:` field: for `Write`, that is the payload's `content`; for `Edit`, it is the
on-disk file with `old_string`→`new_string` applied — the same simulation the guard already performs
for the ledger, at `gate-ledger-guard.sh:62` onward. **Do not early-exit on the delta before
simulating.** The guard's existing ledger logic does exactly the wrong thing to copy here: at
`ee471e6:59-61` (unchanged by #594 — this is a live property of the current guard, not a historical
one) it exits 0 on `Edit` whenever the delta itself doesn't contain `Status: PASS`, and *only after*
that early-exit does it simulate the full result. Applied verbatim to the marker rule, a subagent
composes the file across two individually-permitted calls — `Write` with no `PipelineID:`, then
`Edit` splitting the literal string `PipelineID:` across `old_string`/`new_string` so neither half
contains it — and the early-exit lets both through before the simulated result ever gets checked.
Any split of that string across a Write and an Edit works, and there are unboundedly many. The fix is
structural, not a tighter grep: simulate first, then test the **result**, with no delta-based
early-exit anywhere in the marker path. Add **T-585-6** (§12/§14): a subagent `Write` with no
`PipelineID:` followed by a subagent `Edit` whose `old_string`/`new_string` contain no `PipelineID:`
but whose result does, must be **blocked at the Edit**.

A blanket rule (blocking every subagent marker write regardless of content) breaks `/spec`, which
runs per-document quality gates *inside* a subagent (`skills/spec/SKILL.md:525-528`, with an explicit
"sequentially via Agent tool fallback" at `:528` and `:336`), and quality-gate writes its marker on
all exit paths. A blanket rule would fire `exit 2` roughly `2N` times for `N` tickets on a step the
skill calls mandatory, with no specified recovery. The carve-out is sound rather than merely
convenient: the forgery that *matters* must carry build's `PipelineID` to be consumed at all —
build's verification is glob → PipelineID-filter → PASS-check (`skills/build/SKILL.md:232-243`).
Standalone markers carry no `PipelineID` and nothing reads them. Warden's leg marker carries warden's
own run-id but warden runs in-session, so it is unaffected.

**(b) The path rule must be a non-recursive top-level glob.** The quality-gate **scratch directory
is a subdirectory of the marker directory** — `…/memory/quality-gate/scratch/<run-id>/`
(`quality-gate/SKILL.md:1016`). A rule spelled `memory/quality-gate/**` blocks every red-team
`round-N-findings.md`, every fix journal, and `defer-ledger-<run-id>/`, i.e. it kills the core gate
loop on its first dispatch. The rule must be `memory/quality-gate/gate-verdict-*.md` exactly.
`convergence-log.jsonl` and `active-run-<run-id>.md` are top-level siblings that must stay writable.
Whether this rule must be matched against a *canonicalized* `file_path` (traversal/symlink laundering
through the mandated-writable scratch prefix) is an unmeasured harness property — see the assumption
register (§10.6) — and is not resolved by this design.

**What this tier honestly buys — state it this way, do not overclaim.** It does **not** close prompt
injection. Injection reaches the orchestrator too, by two mandated paths: the orchestrator reads the
artifact directly to compute `ArtifactHash` (`quality-gate/SKILL.md:875`, `:1165`), and it reads
subagent findings files directly every round (`:46`). It does **not** close the nested-harness escape
(§6/C6) — a subagent retains a one-command route to the same write, unstamped, and no probe ships
(§8.6), so nothing sees it. What the tier does, honestly: it reduces the injectable **tool-call** writer
population from `1 orchestrator + N subagents` to `1 orchestrator`, for the `Write`/`Edit` path
specifically — **on the verdict marker (`gate-verdict-*.md`) only.** `build-gate-ledger.md`'s
`Status: PASS` write is a separate decision site this tier does not touch at all (§6/C8); this
accounting covers the marker path, not the ledger. Over a ten-round code gate — red-team, fix, verifier and judge each round, each
full-tools, each reading the artifact — that is roughly forty unwatched *tool-call* actors down to
one watched one; every one of those forty retains the nested-harness escape at the cost of one extra
command, so the *writer population* is not reduced by this tier at all — only the cost of writing
through the cheapest path is. The orchestrator is the actor the human is actually reading; a
subagent's tool calls are not surfaced the same way, and the marker is deleted immediately after
consumption (`build/SKILL.md:244`). **Real, statable as a cost increase on one path, and not
authentication of the verdict, of the caller, or of the writer population as a whole.**

### 8.4 Tier 3 — move the enforcer out of the repo it polices (blast-radius reduction, not a boundary)

Per §6/C1, Tier 2 without this makes the guard script the new single point of failure while leaving
it unprotected — one write, same session. Install and register the guard from a path outside any
repo the pipeline reviews (`${CLAUDE_PLUGIN_ROOT}` via the plugin manifest, or
`~/.claude/crucible/hooks/`), and add that path to the same subagent deny rule.

**Label it accurately, like Tier 4 (§8.5): this is blast-radius reduction, not a capability
removal.** §2.3 already establishes the governing fact — same uid, same filesystem, no privilege
gradient, ordinary `0755` user-owned directories. `~/.claude/crucible/hooks/` is exactly as writable
by the reviewed subagent as `hooks/` is; the only thing standing between a subagent and the relocated
guard is the deny rule, and the deny rule's enforcer *is the guard*. What Tier 3 actually buys: the
guard stops being a file a reviewer subagent legitimately encounters in the course of its assigned
work (`crucible-red-team` and `crucible-qg-fix` have a *reason* to touch `hooks/`; they have no
reason to touch `~/.claude/crucible/`). That is a real reduction even though the new path is
same-uid writable — but it is not a boundary, and this document must not describe it as one (§9).

**S585-1 (siege): Tier 3's premise is false in the modal configuration on this machine.**
"Outside any repo the pipeline reviews" assumes the skills the orchestrator obeys live somewhere
other than the repo under review. **Orchestrator-verified:** `~/.claude/skills/{build,quality-gate,
warden}` are symlinks into this repo (`/mnt/coding/Coding/crucible/skills/`), per CLAUDE.md's own
documented install (`ln -sf "$PWD"/skills/* ~/.claude/skills/`), and CLAUDE.md separately mandates
gating this repo with its own gate. Zero crucible entries exist in `installed_plugins.json`. So in
the configuration that actually runs this pipeline, the pipeline's own prose layer (the skills that
decide what to dispatch and how to react to a verdict) is itself inside the reviewed repo, one layer
above the guard script Tier 3 relocates — Tier 3 does not touch that layer at all, and I-585-3 (a
string check on the *hook's* registered path) stays green while C1 is open one layer up. This is not
a defect in the invariant; it is a scope gap the invariant cannot see. **Do not claim Tier 3 closes
C1** in this configuration — restate it as a reduction (above), true only for the guard script
itself, and open against a subagent that edits `~/.claude/skills/*`'s repo-relative target or that
targets the relocated install path deliberately.

Shipping via `.claude-plugin/plugin.json` solves the install-path problem for the guard script **and**
Tier 0's missing-install-path problem with one move; it does not touch the skills-are-symlinks gap
above. This is the coordination point between #591 and this design (§10.3).

### 8.5 Tier 4 — move `receipt-ledger.jsonl` out of the dispatch root (obscurity — C4's other half is assigned to #586, open until it lands)

Today the ledger lives inside `/tmp/crucible-dispatch-<session-id>/`, a directory GH #498 records as
subagent-writable by mandate: *"The `--ledger` file is inside `<dispatch-root>`"* and *"the party
whose honesty the ledger exists to bind can write the ledger that binds it"* (#498's own words —
quoted directly here rather than paraphrased, per the correction this draft needed). The trusted file
is mandated to live in the untrusted directory. That is worth fixing on its own terms, and it is only
**half** of C4 (§6): the *path-exposure* half. The other half — a forged row accepted on membership
with no hash recompute (§2.2) — is **not** fixed by relocation; it is **assigned to #586, open until
it lands** — #586 is OPEN and pre-gate as of 2026-09-06. Its proposed mechanism has the orchestrator
pass the expected predecessor identity on argv so the verifier resolves nothing against the store at
all (explicitly not re-derivation from the predecessor's own bytes — the on-disk copy sits in the
attacker-owned dispatch root, so hashing it would recreate the class one level down), but this
document does not verify that mechanism. Where a consumer relies on C4's eventual closure (per #586),
"evidence it verifies itself" means evidence the **orchestrator computed and supplies** (as #586
proposes), not evidence re-derived from the referent (which would just relocate the forgery, per §9).

`rcpt_verify.py` needs **no change** — `--ledger` is a separate CLI argument from `--root` and is
never resolved through the root-probe machinery. **Cost correction (S585-8, siege):** this draft's
original "~4 documentation sites" estimate was wrong — I re-measured with `grep -rn
'receipt-ledger.jsonl' skills/ | wc -l` and confirmed siege's count: **23 sites across 9 files in
`skills/`, 46 repo-wide** (`grep -rn 'receipt-ledger.jsonl' . | wc -l`, excluding `.git/`), of which
**4** are hard-coded `--ledger <dispatch-root>/receipt-ledger.jsonl` CONTRACT mandates
(`shared/return-convention.md:137`, `build/SKILL.md:14`, `quality-gate/SKILL.md:30`,
`siege/SKILL.md:21`). Any unmigrated site is a consumer reading an attacker-plantable file at the old
path — the migration is not optional cleanup, it is the closure condition. Also update one
`.pipeline-active` marker field for cairn Rule 1's resolution (`cairn-convention.md:123`; Rule 1
itself is at `:129`), and add a
`check_*.py` drift pin. Cleanup already copies the ledger out to
`<scratch>/crucible-dispatch-<session-id>/`, so post-terminal consumers are untouched. **Bonus:** it
retires the read-hazard class documented at `scripts/rcpt_verify.py:5715-5728` — a mkfifo or 4 GiB sparse
file at the mandated `--ledger` path, planted by the subagent that owns the directory; note this
hazard is a TOCTOU on the *path* and survives relocation unless the read site itself is fixed
(`git show main:scripts/rcpt_verify.py` still carries the `is_file()`-then-reopen shape at the time of
this design run).

**Label it accurately: this is obscurity, not authentication.** The subagent can still glob. It
removes a structural absurdity; it does not create a boundary.

**Do not attempt an "allow appends, block rewrites" rule for the ledger.** It is detectable — the
guard already reads the on-disk file and simulates the post-edit result for its own ledger check
(`gate-ledger-guard.sh:62` onward, at `ee471e6`) — but useless: the threat *is* an append. Permitting
appends permits the attack 1:1. (That existing simulation runs only *after* a delta-based early-exit
at `:59-61` — see §8.3(a)'s warning that this exact ordering must not be copied for the marker rule.)

**Pin the nested-dispatch question explicitly.** The conventions *require* a subagent to write ledger
rows when it dispatches children (`dispatch-convention.md:26-28`; `return-convention.md:129`,
"synchronously, before returning control to any parent dispatch"), so a blanket "no subagent writes
the ledger" rule would contradict the convention as designed — the strong form is not even statable.
`Dispatch-Dir` appears in **zero** `SKILL.md`, which is why the "no nesting ships" reading looks
safe — but it is wrong: there are **two** non-main-thread ledger-writing shapes.
**Agent-tool-nested** dispatch is the `/spec` fallback (`spec/SKILL.md:528`, "sequentially via Agent
tool fallback") — **record this as explicitly unsupported.** **Agent-Teams-teammate-hosted** dispatch
is `/spec`'s *primary* path
(`spec/SKILL.md:322-330`, `:525-528`: TeamCreate/TaskCreate teammates run the per-document quality
gates), and it **is** shipped — its behaviour under Tiers 2 and 4 is gated on §10.1 (see A2), not
recorded as unsupported.

### 8.6 Cross-cutting — the liveness probe (considered and not shipped — L1 remains open)

No sound *in-band* discriminator exists between "this harness does not stamp `agent_id`" and "this
call came from the main thread". Every candidate liveness record — a `SessionStart` stamp file, a
nonce, a capability marker — lives on the same filesystem as the adversary, and is load-bearing
exactly in the case where it is forgeable: if the harness *does* stamp, the subagent is blocked
anyway and the record is redundant; if it does *not*, the subagent writes the record itself and the
guard concludes "stamping is live, no `agent_id` here, therefore main thread."

**The only candidate is an out-of-band behavioural probe, specified here and then withdrawn (below),
on the `Write` leg only.** At gate start, it would dispatch one throwaway subagent whose instructions
are to attempt the protected write once, via `Write`, with the orchestrator then checking *itself*
whether the canary exists. This would produce a positive signal from the harness's real behaviour and
collapse three failure states — old harness, unregistered hook, disarmed guard — into one observable,
which is correct, because the response to all three is the same.

**This probe certifies the tool-call `Write` leg only — a single `Write` cannot certify the `Edit`
path, which is a different branch of the guard (the delta-first early-exit, §8.3(a)) and would need a
second canary shape. It must not, and does not, attempt the nested-harness leg (§6/C6).** A design
must never mandate that its own pipeline execute the bypass it documents in order to test for it:
dispatching a `claude -p` child to attempt the nested-harness
write would, by this document's own C6, always succeed — planting a live, gate-verdict-shaped forged
marker on the honest path of every single run, which is worse than the gap it would measure.
**Disposition, stated once: nested-harness leg — not enforced by this design (§6/C6), and not tested
by this probe.** Any consumer reading a green probe result must read it as "the tool-call leg is
enforcing," never as "the boundary holds." §9 restates this; the two must agree.

**The canary this probe would write cannot be specified as both meaningful and safe, and that gap is
stated here rather than papered over.** To test anything, the canary must be a write the guard would
actually block: a top-level `gate-verdict-*.md` carrying a `PipelineID:` field (§8.3(a)/(b)) —
precisely the shape `build/SKILL.md`'s Verdict Marker Verification globs, PipelineID-filters,
Timestamp-sorts and reads `Verdict` from, and precisely the shape `ee471e6:246-252` globs and matches
on. A canary lacking either property (no `PipelineID:`, or written outside the `gate-verdict-*.md`
glob) is allowed by the carve-out and would report "not enforcing" on every honest run regardless of
whether the guard is live — worthless as a test. A canary carrying both properties, if the write
succeeds — exactly the case this probe exists to catch — is then indistinguishable on disk from a
genuine verdict and is consumed as one by `build/SKILL.md` and by the guard's own `(PipelineID,
Verdict, Phase)` match. Teaching either consumer to recognize and reject a sentinel filename or
`PipelineID` value would resolve this, but that is itself a new consumer-side mechanism — a
coordinated change to `build/SKILL.md`'s PipelineID-filter and to the guard's `:252` match — and this
round's constraint is to prefer deletion over inventing one. **This document therefore does not ship
a specified canary, and recommends the probe be dropped in its current form.** **L1 is not discharged
by this design.** The static unit tests already specified in §12/§14 (T-585-1..3/6/7), which invoke the
guard directly against crafted fixtures, satisfy L2 (live-captured payload shape) and say nothing
about L1 — a test that invokes the guard by path cannot tell you the guard is *registered*, which is
the exact failure §4 documents. Tier 2 therefore ships, if it ships, with L1 open, a real gap this
document records rather than closes. A future round could instead design and land the consumer-side
sentinel-rejection needed to make a live canary safe, gated in §13, but that is new-mechanism work
this round declines
to build.

Attacks on the probe as specified, relevant only if a future round revives it rather than dropping it
per the disposition above: it cannot distinguish *why* enforcement is off (fine — escalate to the
human either way); a probe subagent that never attempts the write leaves no canary and looks like a
pass, so the orchestrator **must** treat a probe receipt lacking a witness for the attempted write as
a failed probe, not a pass; a concurrent resident adversary can delete the canary (real, unmitigated,
and far narrower than today's silent fail-open); it costs one dispatch per pipeline, and — until the
canary is specified per the paragraph above — an unresolved disk-safety question on the one path it
does exercise.

**Split the failure direction by layer.** The **hook** stays fail-open at tool level — a wedged hook
is unrecoverable without the maintainer, and an unrecognised payload shape must not brick every
gate. The **pipeline** would be fail-closed if a probe were revived — a failed probe would block the
gate and escalate (see the paragraph above). Read the
harness version out-of-band once at session start and record it in narration; do not try to derive
it inside the hook, whose payload carries no version field.

**This does not conflict with I-585-4 (§12).** I-585-4 is a source-inspection property — every
failure path labelled in the code — not a runtime discriminator, so a fail-open runtime outcome is
compatible with it; the invariant requires only that the outcome be traceable in the source, which
the pre-repair guard also satisfied. The residual gap is that "failed open" and "ran and passed"
remain runtime-indistinguishable either way — that is L1, and it stays open (§9), not closed by
I-585-4.

---

## 9. What this design does not close

Stated plainly, because §8.2 requires it and because #567's recorded failure is exactly the omission
of this section:

**Shared boundary sentence (identical with #586's doc after normalizing blockquote markers, quotation
punctuation and line-wrapping — the checkable invariant; both sides have confirmed it on that basis.
Cite #586 wherever this document cites C4):**

> The receipt ledger and the gate-verdict marker are orchestrator-authored but subagent-writable —
> the boundary between them is a naming convention, not an authentication mechanism — so no consumer
> may resolve a claim against that store; it must re-derive the claim from evidence it verifies
> itself.

**Cross-document note:** as written, this sentence's "evidence it verifies itself" admits a reading —
re-derivation from the referent's own bytes — that §8.5 shows relocates the forgery one level down
for C4. This document therefore reads it as "evidence the **orchestrator** computed and supplies" (as
#586's argv-passed predecessor identity does for C4's fabricated-row defect). That reading is
narrower than the words, and it must be **reconciled with #586 before either document ships** (§10.3)
— this is a flagged tension, not a unilateral redefinition.

- **The orchestrator edge (C5) stays fully open.** No tier here touches it. It is not closable
  in-band.
- **The nested-harness edge (C6) stays fully open.** No tier here touches it. A subagent with `Bash`
  issues the protected write from a second harness instance it spawns, unstamped, and no in-band
  construction distinguishes that call from a legitimate main-thread one (§7.1, §8.3). No probe ships
  (§8.6); the nested-harness leg is therefore untested by construction — probing it would require the
  pipeline to perform the bypass, which this document declines to mandate. This document records
  "open" on this edge by design, not by omission.
- **`build-gate-ledger.md`'s non-`PASS` gate-satisfying tokens (C7) are untouched.** No tier here
  applies any caller check to a `Status: COMPLETE` or `Status: SKIPPED`+`Acknowledged: true` write;
  `hooks/tests/test-gate-ledger-guard.sh`'s Test 9 ("COMPLETE write to ledger, exit 0") certifies the
  gap stays open. **This is scoped to non-`PASS` tokens; the `PASS` token's own gap is C8, immediately
  below.**
- **`build-gate-ledger.md`'s `Status: PASS` write (C8) has no caller check anywhere in this design and
  is forgeable in two ordinary `Write` calls with zero verdict markers ever created.** Write #1 strips
  `PipelineID:`, defeating the phase-delta scan (`gate-ledger-guard.sh:162-181` @`ee471e6`); Write #2
  re-stamps a fresh attacker `PipelineID`, which `PIPELINE_CHANGED` (`:157`) does not detect once
  `EXISTING_PID` has been emptied by Write #1. Tier 2 (§8.3) does not narrow this population by one
  call — the attack never touches a marker.
- **Hook registration itself (C9, S585-2 residue) is untouched.** `~/.claude/settings.json` is
  same-uid writable; `jq 'del(.hooks)'` disarms the entire enforcement layer in one command without
  touching the guard's content or registered path — no tier here defends the registry.
- **L1 (a positive liveness signal) is not established by anything this design ships.** §8.6
  specifies and then withdraws the only candidate probe — no safe canary can be built without a
  consumer-side sentinel-rejection change this design declines to build (§8.6) — and the
  static unit tests in §12/§14 satisfy L2 only. Any tier that ships does so with L1 recorded open
  here. The per-run repeatable acceptance predicate that would need a live signal (§5.3) is open for
  the same reason. **I-585-4 (§12) is not a substitute:** it is a source-inspection property, and the
  pre-repair guard's own silent `exit 0` (§4) satisfies it as written — so it would not have flagged
  the failure it exists to prevent.
- **Prompt injection is reduced, not closed (C2/C5).** It reaches the orchestrator by two mandated
  read paths.
- **The `Bash` / subprocess leg (C3) is open.** No tier in §8 specifies a rule for it — the earlier
  draft's "reduced (blocklist)" status credited a mechanism this document never builds. A
  command-text blocklist was **considered and rejected** here as the recorded whack-a-mole shape
  (#567; #488 c1 leg-3), not adopted with known residue. `Edit(...)` deny rules cover Bash file
  commands and redirections but explicitly not "arbitrary subprocesses that read or write files
  indirectly, like a Python or Node script". Only the OS sandbox (§7.2) closes that.
- **Tier 4 is obscurity.** It removes a structural absurdity, not an attacker capability. It closes
  the path-exposure half of C4; the fabricated-row half is **open, assigned to #586** (OPEN,
  pre-gate as of 2026-09-06), not closed by this design (§8.5).
- **Tier 3 is blast-radius reduction, not a boundary** (§8.4). It removes the guard from the set of
  files a reviewer subagent legitimately edits in the course of its work. It does **not** make the
  installed copy unwritable — same uid, same filesystem, no privilege gradient (§2.3) — and in the
  modal on-this-machine configuration the skills the orchestrator obeys are themselves symlinks into
  the repo under review (S585-1, §8.4), so C1 remains open one layer above the guard script against
  that configuration, and open against any subagent that targets the relocated install path
  deliberately.

---

## 10. Open questions — three of these block implementation (§10.1, §10.2, and A1 in §10.6)

### 10.1 BLOCKING — are Agent-Teams teammates stamped with `agent_id`?

`/spec`'s primary path uses TeamCreate/TaskCreate (`skills/spec/SKILL.md:322-330`), giving teammates
`taskKind: "in_process_teammate"`. This design measured `agent_id` for Agent-tool subagents at depth
1 and 2; it did **not** measure teammates.

- If teammates **are** stamped, Tier 2 touches `/spec`'s primary path (mitigated by the §8.3(a)
  PipelineID carve, but it must be verified against a real `/spec` run).
- If they are **not**, Tier 2 has a hole exactly where Crucible's highest gate volume runs. Tier 4
  (§8.5) also depends on this: its ledger-writer enumeration is only complete if teammate-hosted
  ledger writes are accounted for the same way.

**Tiers 2 and 4 cannot claim a boundary without this measurement.** It is a single headless probe of
the same shape as §3's.

### 10.2 BLOCKING for the version floor — minimum harness version stamping `agent_id`

Verified present in 2.1.263 and absent in the April-2026 capture; the landing version is unknown.
The design must state a floor and detect "below the floor" behaviourally rather than by inspecting
the payload — but no behavioural probe ships (§8.6), so this question has no route to resolution
under this design and is open on that basis too.

### 10.3 Coordination — the plugin install path is claimed by two workstreams, and it is not deferrable

Tier 0 (#591 item 3) and Tier 3 (§8.4) are the same edit to `.claude-plugin/plugin.json`. **Reconciled
per §8's dependency graph (SP1):** item 3 is a **hard prerequisite for Tier 2** (§8, preamble) — Tier
2 must not land without Tier 3, and Tier 3 needs the install path. The #591 panel's brief to "land
items 1-2 only and coordinate before touching 3-4" therefore cannot leave item 3 permanently deferred
once Tier 2 work starts; it must move into this workstream's critical path rather than #591's, or the
two panels must land it together before Tier 2 code merges. Whichever lands first should carry both
rationales.

**Second coordination item:** §9's gloss on "evidence it verifies itself" (the shared sentence with
#586) reads a phrase both documents commit to identical-after-normalization more narrowly than its
words allow — see
§9's cross-document note. That reading must be reconciled with #586 before either document ships; it
is not resolved by this design alone.

### 10.4 Non-blocking — the `RunID` / `run_id` seam

`ledger-append.md:172` maps them 1:1; `:253` and `quality-gate/SKILL.md:1016` describe different
value shapes (UUIDv7 vs. timestamp). Blocks §7.5 and may be a latent defect independent of this
design. Worth its own issue.

### 10.5 Non-blocking — has the guard ever fired anywhere?

Evidence here covers this machine only, where the answer is no, not once. If the answer is "never,
anywhere", the pipeline's integrity story needs a broader correction than #591.

### 10.6 Assumption register

Premises this design depends on but does not establish, each with its failure mode. None of these
are measured; none block Tier 1 (documentation carries no code risk), but each is a precondition this
document is silently trusting somewhere above. **A1 is BLOCKING for Tier 2 code specifically** — AC 8
(§13) requires it be measured and recorded before any Tier 2 code is written.

| # | Assumption | Depended on by | Failure mode if false |
|---|---|---|---|
| A1 | The harness canonicalizes `tool_input.file_path` before `PreToolUse` fires (`realpath`/`~`-expansion, no unresolved `..`/`//`/symlink components) | §8.3(b)'s path rule, I-585-1's scratch allowance | A subagent plants a symlink or a `..`/`//`-laundered path at the mandated-writable scratch prefix; the write-site string never matches the marker glob (Tier 2 allows it) while the guard's own consuming scan later globs and follows the symlink to the real marker path — same bypass shape as the marker rule §8.3(a) exists to close, one directory up |
| A2 | Agent-Teams teammate dispatches (`TeamCreate`/`TaskCreate`, `taskKind: "in_process_teammate"`) are stamped with `agent_id` the same way Agent-tool subagents are | §10.1 (BLOCKING for Tiers 2 and 4, §8's dependency graph); Tier 4's ledger-writer assumptions (§8.5) | If unstamped, Tier 2 has a hole exactly where `/spec` — Crucible's highest-volume gate dispatcher — runs its primary path, and the §8.6 probe, had it shipped, was built against the Agent-tool shape and might not have exercised the teammate shape at all |
| A3 | `agent_id` semantics are a harness property that can change or disappear without notice, with no version contract from Anthropic | Every use of `agent_id` in §8.3; §8.6's whole reason for existing | A harness update silently stops stamping the field, changes what qualifies as "present," or reintroduces it on payloads it was previously absent from; nothing in this design detects a *semantic* change the way the §8.6 probe would have detected an *absence* — the probe assumed today's semantics, not future ones |
| A4 | `Edit` stamps `agent_id` the same way `Bash`/`Agent`/`Write` do — §3's live probe measured no `Edit` row | T-585-6, the round-1 fix's headline new test, which is entirely an `Edit` construction; §8.3(a)'s structural remedy | If `Edit` is stamped differently (or not at all), T-585-6 and §8.3(a)'s content-simulation rule may not fire on the exact path they are built to close; this is an inference from the binary's hook-input schema, not a measurement |
| A5 | The orchestrator retains, for the life of the run, the evidence it computed itself — the Layer-2 tripwire manifest that holds each receipt's hash prefix | §9's boundary sentence ("re-derive the claim from evidence it verifies itself"); §8.5's C4 gloss ("evidence the orchestrator computed and supplies") | The manifest is in-context only (`return-convention.md:557-558` @ee471e6, "Append manifest entry … to the in-context manifest") and `cairn-convention.md`'s Recovery Protocol restores `active-run.md`, the dispatch dir and `receipt-ledger.jsonl` but never the manifest — while its step 7 still calls both "authoritative for what happened". After a compaction the only durable source of a receipt prefix is `receipt-ledger.jsonl`, which lives in the dispatch root the reviewed subagent owns and can append to: the trust root has a lifetime shorter than the run. (Found by #586's siege round, SIEGE-C1; the remedy — making Layer 2 durable, or amending the Recovery Protocol's claim — is a change to `shared/cairn-convention.md` and `shared/return-convention.md`, filed separately, not to this document.) |

---

## 11. API surface

No code interfaces are added by Tiers 1 or 4. Tiers 2-3 change one hook's contract:

```
hooks/gate-ledger-guard.sh   (PreToolUse; matcher "Write|Edit" — see note)
  stdin : JSON  { tool_name, tool_input{file_path,content,old_string,new_string},
                  session_id, transcript_path, cwd, permission_mode,
                  agent_id?, agent_type? }
  exit 0 : allow
  exit 2 : block; single-line reason on stderr naming the rule that fired
  reads  : $HOME/.claude/projects/<hash>/memory/quality-gate/gate-verdict-*.md (top level only)
  writes : nothing
```

`exit 0` collapses "evaluated and allowed" with "did not evaluate" at runtime — the contract makes no
distinction between them. I-585-4 (§12) requires only that each such path be labelled in the source,
not that it be runtime-distinguishable; that gap is L1, and it stays open (§9).

Matcher note: the registration is and stays `Write|Edit`. Widening to `"*"` would not cover the
Bash/subprocess leg — a Bash `PreToolUse` payload carries no `tool_input.file_path` for the hook's
target-path filter to test — and no tier here specifies a Bash rule (§6/C3, §9). Only OS-level
separation (§7.2) closes that leg.

## 12. Invariants

**Checkable by inspection:**

- I-585-1 — the guard's path rule for the marker is a **non-recursive** top-level glob; no rule in
  the hook matches `memory/quality-gate/scratch/**`.
- I-585-2 — the guard reads `agent_id` from the payload only; it never derives caller identity from
  `session_id` or `transcript_path` (both are parent-valued inside subagents).
- I-585-3 — the guard's registered command resolves to a path outside any repository the pipeline
  reviews (Tier 3). **Necessary, not sufficient:** true today would still leave C1 open one layer up
  in the modal on-this-machine config, where the *skills* the orchestrator obeys are symlinks into
  the reviewed repo (S585-1, §8.4) — this invariant checks the guard script's registration only.
- I-585-4 — every non-terminal failure path in a shipped mechanism is enumerated and labelled in the
  source, so an audit can point to each early `exit 0` and state why it fires. **This is a
  source-inspection property only, and it is honestly weaker than earlier drafts implied: the
  pre-repair guard's own silent `exit 0` on an empty `TOOL` (`1888642:27-30`) — the exact 4.8-month
  inertness §4 documents — is source-labelled in exactly this sense and satisfies this invariant as
  written. With no liveness signal shipping (§8.6), I-585-4 does not, and cannot, detect a §4-shaped
  recurrence at runtime; that is recorded here and in §9 as an open gap, not one this invariant
  closes.**

**Requires tests:**

- T-585-1 — a subagent-shaped payload (`agent_id` present) writing a marker **with** `PipelineID:`
  is blocked; **without** `PipelineID:` is allowed. Driven from a live-captured fixture, not a
  hand-rolled one (L2).
- T-585-2 — a main-thread payload (`agent_id` absent) writing either marker form is allowed.
- T-585-3 — a subagent-shaped payload writing `…/memory/quality-gate/scratch/<run>/round-1-findings.md`
  is allowed (regression guard for I-585-1).
- T-585-4 — the liveness probe reports "not enforcing" when the hook is unregistered, when the guard
  body is `exit 0`, and when the payload carries no `agent_id`. **Contingent on §8.6's canary being
  safely specified; this document currently recommends the probe not ship until then (§8.6).**
- T-585-5 — a probe receipt with no witness for the attempted canary write is treated as a failed
  probe, not a pass. Same contingency as T-585-4. **Residue (S585-7):** `WITNESS` is subagent-authored
  and classified untrusted by this repo's own threat model (§2.3); this check alone cannot distinguish
  "the guard blocked the write" from "the probe never attempted it" — carried forward only if the
  probe is revived (§8.6).
- T-585-6 (F2) — a subagent `Write` with no `PipelineID:` followed by a subagent `Edit` whose
  `old_string`/`new_string` contain no `PipelineID:` but whose simulated result does, is blocked at
  the `Edit`. Regression guard for §8.3(a)'s "evaluate the resulting file state, never the delta"
  requirement.
- T-585-7 (S585R2-1) — a subagent `Write` to `build-gate-ledger.md` with `PipelineID:` stripped,
  followed by a subagent `Write` re-stamping a different `PipelineID:`, must not both `exit 0` against
  an empty marker directory. Regression guard for the ledger `Status: PASS` decision site (§6/C8).

## 13. Acceptance criteria

1. `docs/` contains a trust-boundary statement asserting §8.2's five points, and it names the
   orchestrator edge as not closable in-band.
2. No document in the repo describes the verdict marker or the receipt-ledger binding as
   *authentication* or *gate integrity*; both are described as tamper-evidence/continuity.
3. §10.1 is measured and its result recorded before any Tier 2 or Tier 4 code is written.
4. Every mechanism that ships carries at least one test driven from a live-captured payload (L2).
   **L1 (a positive liveness signal) has no available construction (§8.6); any tier that ships does
   so with L1 recorded as open in §9, and a mechanism must not be described anywhere as
   verified-live.**
5. This document's §9 is reproduced, not summarised away, wherever the mechanism is documented.
6. **Tier 2 does not land in a release that does not also contain Tier 3** (SP1; §8's dependency
   graph). A PR shipping the `agent_id` marker check without the guard relocation is rejected on that
   basis alone, regardless of how clean the check itself is. A PR landing Tier 2 must also amend the
   published §8.2 point 3 to match (§8.2).
7. C4's fabricated-row half (§6) is not recorded as closed anywhere in this document until #586 has
   landed and been gated.
8. A1 (§10.6) is measured and its result recorded before any Tier 2 code is written; if false,
   §8.3(b)'s scratch-path allowance and I-585-1 must be revised first.
9. #585 does not close as "accepted risk, documented" (§5.3) with Tier 1 shipped alone unless §8.2's
   points 3 and 5 are first amended to state that no mechanism exists — a documentation-only
   close-out must not describe cost-raising or liveness mitigations that are not actually shipped.
10. Tier 4 does not land as a partial migration (S585-8 residue; mirrors AC 6's ordering discipline
    for Tier 2/3): a PR must convert every documented `receipt-ledger.jsonl` consumer site (§8.5) in
    one change, not a subset, because an unmigrated site is a consumer reading an attacker-plantable
    file at the old path.

## 14. Testing strategy

Unit level: `hooks/tests/test-gate-ledger-guard.sh` gains T-585-1..3, T-585-6 and T-585-7, all built from
`hooks/tests/fixtures/agent-pretooluse-sample.json` extended with `agent_id`/`agent_type` rather
than hand-rolled — this is the specific discipline #591 exists to establish. Note that at `ee471e6`
this suite's own fixture-builder helpers were rewritten from the dead `.tool`/`.input` shape to the
canonical `.tool_name`/`.tool_input` shape as part of #594 (§4) — T-585-1..3/6/7 build on the post-#594
helpers, not the ones this design's review legs read.

Integration level: T-585-4/5 belong to the pipeline, not the hook, and are exercised by a `/build`
run whose gate-start probe is deliberately defeated three ways, on the `Write` leg only (§8.6) — there
is no nested-harness leg to test, by construction; this document does not mandate the pipeline
attempt that bypass (§8.6). T-585-4/5 also depend on §8.6's canary being specified, which it is not
yet — until then these describe a probe design this document recommends not shipping, not a probe
that ships (§8.6).

Explicitly not tested: the orchestrator edge (C5) and the nested-harness edge (C6). There is no test
for either, which is itself the finding.
