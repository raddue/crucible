# Contents

- Artifact Preparation · Small artifacts (design docs, plans, hypotheses) · Code artifacts · Chunked Gate Counter Semantics
- Hypothesis artifacts · Minor Issue Handling · Clean-Pass Minor Advisory (#362) · Pre-Flight Dependency Audit
- Security Surface Detection and Siege Dispatch · Detection Heuristic · Decision and Dispatch · Result Integration
- Standalone Siege Invocations · Anti-Anchoring Rules

## Artifact Preparation

**Round-0 baseline snapshot (#546).** Before the first red-team dispatch, on `design | plan | hypothesis` artifacts (round 4, M1 — scoped to match Fix-Generated Defect Tracking › Artifact-class scope; `code` gates never consult this file, so writing it there would have no reader), write the artifact content **as prepared for that dispatch** — the same representation subsequently used for every `artifact-N.md` (see Round History) — to `artifact-0.md`, written into `<findings-root>`, which the create-before-lint rule (Receipt Linter) has already created (round 4, M2). This is the "before" side of round 1's fix diff — the input the Fix-Generated Defect Tracking checker needs for round N=1 (see Fix-Generated Defect Tracking › Artifact-class scope), matching every N>1's `artifact-(N-1).md` baseline uniformly. Without it, round 1's fix would edit the artifact in place with the pre-fix bytes preserved nowhere on disk. **On a chunked gate this is written per chunk (round 3, S2)** — `chunk-K/artifact-0.md`, immediately before that chunk's first red-team dispatch, containing that chunk's own content. The cross-chunk integration round's own `artifact-0.md` is subject to the same unpinned-home known gap this document already declares for that round's other files (round 4, M3 — see Write/lint ordering on `fix-journal.md` › "Known gap — the cross-chunk integration round"), not a resolved location.

### Small artifacts (design docs, plans, hypotheses)

Pass the full artifact content to the red-team subagent. No preparation needed.

### Code artifacts

Code artifacts vary in size. The orchestrator prepares the artifact based on scope:

- **Small implementations (<500 lines diff):** Pass the full diff + any new files in full.
- **Medium implementations (500-2000 lines):** Pass full source of high-risk files (new files, files with complex logic changes) + summaries of routine changes (imports, wiring, boilerplate). Include a change manifest listing all files with 1-line descriptions.
- **Large implementations (>2000 lines):** Split into logical chunks (by subsystem, module, or feature boundary). Run a quality gate on each chunk, then a final cross-chunk round reviewing the integration points. Present the chunking plan to the user before proceeding. See Chunked Gate Counter Semantics below for how round numbering, consensus cadence, and the suppression threshold apply across chunks. **Chunked compaction recovery:** Use a parent run-id for the entire chunked gate. Write `chunk-manifest.md` (lists all chunks with gated/pending status) to the parent scratch directory. Per-chunk round files go in `chunk-N/` subdirectories. Only delete the parent scratch directory after the final cross-chunk round completes. The `active-run.md` marker references the parent run-id throughout.

**Grudge pre-flight (regression-oracle, #271).** On round 1, query the **Book of Grudges** for the gated files and include any matches in the red-team dispatch context as known prior regressions to check against — a reviewer should weight a past grudge on a touched file heavily. Resolve the helper by absolute path from the plugin root — `plugin_root="$(realpath "<this-skill-base-dir>/../..")"` — and run `python3 "$plugin_root/scripts/grudge_query.py" <gated files…> --with-signatures`. Best-effort: if unresolved, emit a one-line stderr warning and continue — a missing pre-flight must NEVER block the gate. See `skills/debugging/SKILL.md` for the grudge regression-oracle mechanics.

### Chunked Gate Counter Semantics

A chunked gate has two independent round counters: a **local** counter per chunk (resets to 1 at each chunk start) and a **global** counter (monotonic across all chunks). These counters drive different mechanisms; the spec made them collide before this section was added.

| Mechanism | Counter | Rationale |
|---|---|---|
| `suppression_threshold` | **local** (per chunk) | Each chunk is conceptually its own artifact converging from scratch; the convergence economics that justify a 10-round trust window apply per chunk, not globally. |
| Consensus cadence (every `max(1, suppression_threshold // 3)` rounds, starting at 1) | **local** (per chunk) | Each chunk's round 1 deserves multi-model review; otherwise chunks 2+ never get consensus coverage. |
| Stagnation judge dispatch | **local** (per chunk) | The judge's "consecutive-round comparison" semantics are about within-chunk convergence, not cross-chunk drift. |
| Fix journal / fix memory (`fix-journal.md`) | **local** (per chunk) | The journal's **file location** is forced: it is a cited artifact whose declared sha256 a receipt pins, and the **bare basename** it is cited by is probed only at a root's top level — resolution is a literal join, with **no search** — while nothing above a root is probed except that root's git toplevel (`None` here), so it must sit at the top level of the round's `<findings-root>` — the chunk's own directory — or it resolves nowhere (Receipt Linter; the write/lint window rule at How It Works step 4c). Scoping memory to match is a **choice**, not forced by that: an orchestrator could seed a chunk's journal with prior chunks' entries and still satisfy the location rule. It is chosen because each chunk converges as its own artifact, so its own remediation history is the relevant one. **Accepted cost:** a fix agent does not see other chunks' entries, so a shared-helper edit made in chunk-1 is not visible to chunk-3's fix agent, and the cross-chunk integration round starts empty too — it reviews the integration surface but inherits no chunk's history. Chunk boundaries are chosen at subsystem/module lines precisely to keep that overlap small. |
| Silent-seed judge dispatches (rounds threshold-3 to threshold-1) | **local** (per chunk) | Same reason — comparison history is per-chunk. |
| 15-round safety limit | **global** (across all chunks) | This is runaway-protection circuit-breaker. If a 3-chunk gate is on round 16 globally, something is wrong; force escalation. |
| `Rounds` field in verdict marker | **global** | Downstream consumers need total cost signal. |
| `ScoreTrajectory` field | **global, with chunk boundary markers** | Format: `6,4,3,|,5,3,1,0,|,4,2,1` (pipes mark chunk boundaries). Lets forge analyze per-chunk and cross-chunk trajectory. |

**Cross-chunk round:** After all chunks complete, the final integration round increments the global counter but is conceptually its own "mini-chunk" with `suppression_threshold` = 5 (lower, because integration issues should escalate faster than within-chunk issues). Consensus is mandatory for the cross-chunk round (single-model review is too narrow for integration-surface bugs).

**Cross-chunk layout (pinned, #746).** The integration round's findings root is the reserved `<scratch-dir>/cross-chunk/` directory: its `round-N-findings.md` and `fix-journal.md` sit at that directory's top level, the orchestrator creates it before the round's first lint by the existing empty `round-N-coverage.md` convention (receipt-consensus.md › Create `<findings-root>` before the round's first lint), and that exact directory — never the parent scratch or a sibling `chunk-K/` — is passed as the second `--root` for every integration-round receipt lint. Recovery reads the integration round's files only from this directory. Widening the roots would let a bare-basename citation resolve across chunk boundaries, which layout pin (b) exists to prevent. The round's mandatory consensus membership is recorded in the model-assurance roster before scratch cleanup (loop.md › Model Assurance Inventory).

**Siege on chunked gates:** siege dispatches **once on the full artifact**, not per-chunk (see Security Surface Detection → Dispatch timing → Chunked-gate siege scope for the rationale and the chunk-local tradeoff).

**Canonical `chunk_id` grammar (INV-A15 / #265).** Chunk identifiers used in marker fields (`LookHarderRounds`, `PersistentFindingRounds`), convergence-log entries (`look_harder_rounds`, `persistent_finding_rounds`), and scratch directory names are restricted to TWO forms:

- `chunk-<N>` where `<N>` is a positive integer matching the chunk's directory name (`chunk-1`, `chunk-2`, ...). Used for author-defined chunks.
- `cross-chunk` — reserved string for the synthetic cross-chunk integration round.

**Gate-start validation.** At chunked-gate start, the orchestrator MUST refuse to begin if any author-chunk directory name does not match the regex `^chunk-[1-9][0-9]*$`. The reserved `cross-chunk` token explicitly avoids collision with user-chosen subsystem names (e.g., `integration` would be a valid directory name in some authors' systems but would collide with the integration round's semantic).

**Chunked-gate list-element encoding for new telemetry fields (INV-A15 / S6).** `LookHarderRounds` and `PersistentFindingRounds` are run-level lists in marker output; their elements differ between chunked and non-chunked gates:

- **Non-chunked gates:** bare integers — e.g., `LookHarderRounds: 3, 6`. The convergence-log uses bare integers in the JSON list.
- **Chunked gates:** `<chunk_id>:<local_round>` pairs (colon-separated) in the marker — e.g., `LookHarderRounds: chunk-1:3, chunk-2:5, cross-chunk:2`. The convergence-log encodes elements as JSON objects: `[{"chunk":"chunk-1","local_round":3},{"chunk":"chunk-2","local_round":5},{"chunk":"cross-chunk","local_round":2}]`.

Two chunks could each contribute a "round 3"; without chunk-coordinate qualification a flat integer list would be ambiguous. The same encoding applies to `PersistentFindingRounds` / `persistent_finding_rounds`.

**ArtifactHash and ChunkHash semantics on chunked gates.** `ArtifactHash` is the sha256 hex of the FULL pre-chunking artifact's bytes, computed once at gate start. Every per-chunk verdict marker AND the cross-chunk integration round's marker carry the **same** `ArtifactHash` — it identifies the artifact bytes across all chunks of a single gate run AND across multiple gate runs on the same content (regardless of chunking strategy). Forge consumers group markers by `ArtifactHash` for cross-run comparison, including the `tail-rubric-already-applied` revisit trigger.

`ChunkHash` is the sha256 hex of the specific chunk's bytes. It is present **only** on per-chunk markers in chunked gates; it is **omitted** from non-chunked-gate markers and from the cross-chunk integration round's marker. `ChunkHash` is internal-only for per-chunk recovery scenarios; `ArtifactHash` is the canonical cross-run identifier.

**Recovery semantics:** On compaction mid-chunked-gate, read `chunk-manifest.md` to recover chunk status. The local counter for the in-progress chunk is recovered by reading the highest N in `chunk-K/round-N-score.md`. The global counter is reconstructed by summing rounds across all completed chunks plus the in-progress chunk's local rounds. The look-harder all-files scan (see Compaction Recovery step 6a) operates strictly within the in-progress chunk's directory — never globs across chunks.

The red-team subagent receives the **prepared artifact**, not raw diff. This mirrors audit's Tier 1/Tier 2 context management approach.

### Hypothesis artifacts

Hypotheses are 1-2 sentence statements, not plans or designs. The red-team prompt template is plan-centric and does not map well to hypothesis testing. For hypothesis artifacts, the orchestrator frames the red-team dispatch with hypothesis-specific attack vectors:

- Does this hypothesis explain ALL observed symptoms?
- What evidence would disprove it?
- Are there simpler alternative explanations?
- What assumptions does this hypothesis make that could be wrong?

Include these in the dispatch prompt alongside the standard red-team template. The debugging skill's Phase 3.5 defines these questions -- the quality-gate orchestrator should use them.

## Minor Issue Handling

Minor issues still **do not enter the weighted score and never trigger fix rounds**, but the **stagnation judge may weigh sustained Minor accumulation** at round ≥ threshold (per D1 — see the Step 3 Mixed-branch Minor-accumulation rule in `stagnation-judge-prompt.md`). They accumulate across rounds and contain useful information. Do not silently discard them. <!-- CONTRACT:qg-minor-stagnation-prose — check_qg_stagnation_minor.py Group-B reworded anchor -->

**After the gate completes** (artifact approved or stagnation escalated):

1. **Consolidate:** Collect all Minor observations from all rounds, deduplicate.
2. **Quick-fix pass:** Dispatch a fix subagent (`subagent_type: crucible-qg-fix`, same fix type as the main loop, pinned to Sonnet — `agents/crucible-qg-fix.md`; do not pass a call-level `model:`) with the consolidated minors and the final artifact. On `crucible-qg-fix` resolution failure this dispatch takes the same `general-purpose` fallback and emits the same warning as the main-loop dispatch (see Fix Mechanism) — once per gate run, whichever site reaches it first. The fix agent addresses easy wins only — changes that are simple, low-risk, and unambiguous (typos, naming inconsistencies, missing edge-case guards, trivial cleanup). It skips anything requiring judgment or design decisions.
3. **Present remainder:** Output any minors the fix agent skipped as "Remaining minor observations" so the user can decide whether to address them. No further red-team round on the quick fixes — the gate is already complete. (Because this post-pass quick-fix is **not** re-reviewed, its edits ship on Sonnet unverified — a bounded residual accepted in the #352 plan: blast radius is consolidated Minors on an already-passed artifact. #537 removes the *tier-ambiguity* (the pin is now static and readable in the agent def, rather than resolved from whatever session the gate runs in — install freshness still requires the §8 re-verification). Whether it raises or lowers this residual's floor depends on the orchestrator tier it replaced: strictly lower under an Opus orchestrator, neutral under a Sonnet one, and higher under any session weaker than Sonnet — a configuration no convention forbids (residual (a) governs Fable sessions only, and under a Fable session the pin lowers the floor, matching the Opus-orchestrator case above). Either way the edits remain unverified; the bound is blast radius (consolidated Minors on an already-passed artifact), not fixer strength.)

### Clean-Pass Minor Advisory (#362)

On the **clean-pass exit only** (Exit Precedence slot #1), after consolidating Minors and before writing the verdict marker, the orchestrator computes a **Minor advisory** — a PASS-annotating signal that weighs accumulated Minors against convergence, closing the gap that a `0F/0S`-with-Minors round terminates at slot #1 before the Minor-aware stagnation judge (slot #8) ever runs. **The advisory never changes the verdict or precedence — a clean pass stays PASS (slot #1 stands) and the advisory never blocks.** It adds **zero rounds**: every input is a file already on disk.

Two rules; either firing sets the advisory (both firing → `density+trajectory`):

- **Density (count net, R-independent).** Fire `density` when `m_exit ≥ K`, with **K = 5**. `m_exit` is the clean exit round's Minor count: the deduplicated union (by title / root-cause identity) of `round-R-findings.md`'s Minor observations **(including `Minor`-first-token entries under `### Second Pass Findings`, per the Score source rule's Minor population join, step 7 — #561 fresh round 6 S3: this heading-scoped population name is not file-scoped, matching every other INV-561-1 consumer's site-local qualifier)** AND — when look-harder fired and confirmed on round R — `round-R-look-harder.md`'s Minor observations **(likewise including `Minor`-first-token entries under `### Second Pass Findings` there, per the same Minor population join, step 7 — #561 fresh round 7 S3: round 6's S3 fix widened only the first operand; the identical bare phrase eleven words later needs the identical site-local qualifier, for the identical reason)** (the live spec does not fold a confirming look-harder's Minors into `round-R-findings.md` — so the union is required to avoid under-counting exactly when the tightened rubric finds more). Three exit cases, all covered by the conditional union: (i) **confirmed** → findings ∪ look-harder.md; (ii) **demoted, ordinary path** → the round is non-terminal and is never the exit round; (ii-b) **demoted, discrepancy exception's Look-harder path (#561 fresh round 7 M2)** → the round IS terminal (Score source rule, step 7 › Look-harder path) but exits via the Empty-work-order exception, not via this clean-pass-only advisory (see this rule's own opening sentence above), so `m_exit` is never computed on this branch either; (iii) **skipped** → no `round-R-look-harder.md`, so `m_exit` = `round-R-findings.md` Minors only. Density is the robust primary net and catches the literal `0F/0S/7M` exit regardless of any title drift.
- **Trajectory (recurrence net).** Fire `trajectory` when **R ≥ 3** AND **≥1 Minor recurring across all three rounds R-2, R-1, R** — the same Minor observation (matched by title / root-cause identity, the same basis the persistence checker uses, **NOT** by line number) appears in `round-{R-2,R-1,R}-findings.md` (each round's *final* end-of-round findings, post-demotion-overwrite per INV-A17, so no pre/post-look-harder identity mixing). This mirrors the stagnation judge's recurring-Minor signal (`stagnation-judge-prompt.md` Step-3 Minor-accumulation, counter reaching 2) at the clean exit the judge structurally cannot reach. `R ≥ 3` and "2 transitions" are the **same** window constant (3 rounds ⟺ 2 transitions). There is no Minor-count floor — the rule is recurrence-based, not count-based.

**Constants (internal — no new public argument, per the #265 no-new-args precedent).** The complete pin set is exactly **{ K = 5, R ≥ 3, ≥1-recurring-Minor }**: `K = 5` (density); `R ≥ 3` and the recurrence threshold "≥1 Minor recurring across all three rounds R-2, R-1, R" (trajectory). No count floor; "2 transitions" is derived from `R ≥ 3`, not a separate pin.

**Accepted residuals (advisory-only, never blocks).** (a) Tail-rubric Minor reclassification can inflate late-round Minor counts (a false-positive source for `trajectory`); (b) anti-anchoring title instability can make `trajectory` miss a genuinely recurring Minor whose title drifts across fresh rounds (a false negative). Both are low-harm precisely because nothing blocks; `density` (identity-free, single homogeneous clean-round count) is the robust net.

**Telemetry vs. advisory — writer split across all terminal verdicts.** `MinorTrajectory` (marker) / `minor_trajectory` (convergence-log) are **per-round Minor-count telemetry sourced from the `round-N-score.md` files**, written as part of the **verdict-marker write step** (which runs on ALL exit paths — `## Verdict Marker > When` — including the siege-blocked exit that skips this Minor Issue Handling section), so they are present on every terminal verdict. `MinorAdvisory` / `minor_advisory` are computed **only on the clean-pass exit** (omitted / `null` on every escalation / architectural / siege-demotion exit) — there is no clean exit round to classify on a non-clean verdict. On a fired advisory the orchestrator also surfaces a prominent advisory line to the user alongside the consolidated Minor observations.

## Pre-Flight Dependency Audit

**Parent-dispatched parallel lane.** The parent orchestrator invokes `quality-gate` dependency-audit mode (`dependency-audit.md`) alongside this gate on code artifacts. The scan has its own BLOCKED/FINDINGS/INCONCLUSIVE/FAILED/CLEAN result and arguments; the parent surfaces and integrates that signal. This gate neither dispatches the lane nor receives its receipt. Audit findings are NOT passed to the red-team reviewer or added to the weighted score (INV-2). A direct "audit dependencies" request invokes the audit mode alone.

## Security Surface Detection and Siege Dispatch

Some artifacts touch security-relevant surface and deserve a dedicated security audit pass alongside (not in place of) the red-team loop. Quality-gate inspects each artifact at gate start; when security signal is detected, it dispatches `crucible:siege` in parallel with the first red-team round. Siege runs its own attacker-perspective loop independently. The gate awaits both before declaring PASS.

This mirrors the dependency-audit pattern: siege is a sibling parallel skill, not a quality-gate phase. Findings flow back as an independent signal that blocks PASS but does not feed the weighted score (preserves INV-2).

### Detection Heuristic

Set `security_surface: detected` if ANY of the following signals fires:

**File path / project structure:**
- Path components matching: `auth/`, `crypto/`, `secrets/`, `tokens/`, `permissions/`, `sanitiz`, `validat`, `escape`, `csrf`, `xss`, `sqli`
- Test paths matching the same patterns (test files that exercise security code are themselves security-relevant)

**Code patterns (code artifacts):**
- Regex compiled from user input
- Shell exec with string interpolation (any of: `os.system`, `subprocess.*shell=True`, backticks, `eval`, `exec`)
- Deserialization without schema (pickle.loads, yaml.load without SafeLoader, JSON.parse-then-trust)
- SQL with string concatenation or f-string interpolation against user-controlled values
- File path joins where a path component is user-controlled (`os.path.join(base, user_input)` without sanitization)
- Password / token comparisons not using constant-time (`==` against secret material)
- Cryptographic primitives invoked directly (use of `hashlib`, `cryptography`, `crypto` libraries)

**Design / plan / hypothesis keywords:**
- Single-word match in artifact body: `authentication`, `authorization`, `cryptographic`, `cryptography`, `session token`, `API key`, `permission boundary`, `trust boundary`, `sandbox`, `privilege`, `RBAC`, `OAuth`, `SAML`, `JWT`, `CSRF`, `XSS`, `SQL injection`, `RCE`, `deserialization`, `path traversal`
- Two-word phrases: `user-supplied input`, `untrusted input`, `external input`, `attack surface`, `threat model`

**Dependency-audit signal:** If dependency-audit (running in parallel) flags Critical/High vulnerabilities in security-critical packages (auth libraries, crypto libraries, web frameworks), promote to `security_surface: detected` even if no other signal fired.

**Standalone invocation note:** A standalone full `/quality-gate` on code does not run the audit lane. A user wanting both invokes audit mode separately or uses `/build`. When a parent supplies a completed audit signal, Critical/High findings can promote security-surface detection under the rule above; the gate does not scan or re-run the audit.

**Confidence threshold:** Keyword matches in design/plan/hypothesis artifacts are noisy. Require either ≥2 distinct keyword categories OR 1 keyword + an explicit "## Security" section. A single mention of "authentication" in passing does not trigger detection.

### Decision and Dispatch

After detection runs:
- If `force_siege: true` → dispatch siege unconditionally (skip detection, log as "force-dispatched")
- Else if `skip_siege: true` → never dispatch (log as "skip-requested")
- Else if `security_surface: detected` → dispatch siege
- Else → no siege dispatch (log as "no-security-surface")

**Dispatch timing:** Immediately before the first red-team round, in parallel. Quality-gate's loop proceeds independently; siege runs on its own scratch directory and its own counters.

**Chunked-gate siege scope:** When a *chunked* gate detects a security surface, dispatch `/siege` **once on the full artifact**, NOT per-chunk. Rationale: siege is expensive (~6 Opus agents) and security surfaces are typically cross-cutting (auth / data-flow span chunk boundaries), so per-chunk dispatch both multiplies cost *and* misses cross-chunk interactions. **Acknowledged tradeoff (R1 M2):** once-on-full-artifact can under-weight a chunk-*local* sink that only a per-chunk view would surface; this is accepted because (a) siege itself reasons over the full artifact and (b) the per-chunk red-team loop runs on each chunk and would independently flag a local injection sink.

**Awaiting siege (all exit paths):** Before writing any terminal verdict marker, the orchestrator verifies siege has completed. This applies to ALL exits — PASS, ARCHITECTURAL, SUSTAINED_REGRESSION, STAGNATION, ESCALATED. If siege is still running:

- **For PASS / clean exit:** Wait for siege unconditionally. Siege's Critical/High findings demote PASS to `ESCALATED` with reason "siege-blocked" — fix the security issue and re-run. If siege itself escalates (its own ESCALATED/STAGNATION verdict), include those findings in the gate's escalation summary. **Ordering on clean red-team round** (cross-reference How It Works step 5): (1) await siege; (2) if `SiegeVerdict != PASS`, skip Minor Issue Handling and write `Verdict: ESCALATED, Reason: siege-blocked`; (3) if siege PASSes or was not dispatched, run Minor Issue Handling on the known-passed artifact (Minor Issue Handling does NOT re-trigger siege); (4) apply the Run-completeness guard (`loop.md` › Run-completeness guard (#755)) and only if satisfied write `Verdict: PASS, Reason: clean-pass`; otherwise resolve via Exit Precedence slot #10 (`Verdict: ESCALATED, Reason: incomplete-run`); then cleanup.
- **For any escalation exit (ARCHITECTURAL, SUSTAINED_REGRESSION, STAGNATION, ESCALATED):** Wait for siege if it has been running ≤ 5 minutes; otherwise cancel siege via `crucible:siege`'s interrupt mechanism and write `SiegeVerdict: UNAVAILABLE` with `SiegeReason: cancelled-by-host-exit`. The 5-minute cap prevents an in-flight siege from blocking an already-decided escalation indefinitely.

Quality-gate's verdict is always determined by the local exit condition (see Escalation > Exit Precedence); siege results are integrated into the verdict marker after the local verdict is determined. Siege's Critical/High findings BLOCK quality-gate PASS the same way a Fatal red-team finding does, but they do NOT override a higher-precedence escalation verdict — they are recorded alongside it.

### Result Integration

Verdict marker fields (extend the existing set):

```
SiegeDispatched: true | false
SiegeReason: detected | force | skip-requested | no-security-surface
SiegeVerdict: PASS | ESCALATED | STAGNATION | UNAVAILABLE (only when SiegeDispatched=true)
SiegeFindings: <count of Critical+High findings, 0 if none or N/A>
```

**Verdict mapping:** If `SiegeDispatched: true AND SiegeVerdict != PASS`, quality-gate's verdict cannot be `PASS` — emit `Verdict: ESCALATED` with reason "siege-blocked".

**Independent of weighted score (INV-2):** Siege findings are not summed into Fatal/Significant counts. They appear in the gate output as a separate "Security Findings" section. The red-team never sees siege output (anti-anchoring preserved).

### Standalone Siege Invocations

Siege can still be invoked directly by the user. Quality-gate's siege dispatch is additive — it ensures siege runs when surfaced needs are detected, not exclusive. A user running `/siege` directly followed by `/quality-gate` will see siege run twice unless they pass `skip_siege: true` to the gate.

## Anti-Anchoring Rules

The iterative loop relies on **no contextual anchoring** between rounds — each reviewer receives the artifact and prompt as if reviewing for the first time. This is a structural property the orchestrator controls (what is passed to the reviewer), not a claim about reviewer independence. Two dispatches of the same LLM on the same artifact may produce correlated findings; that correlation is acceptable as long as the orchestrator does not amplify it by leaking prior-round context.

The convergence argument is therefore: *fix-agent edits change what is on the page; the next reviewer reads what is on the page; correlated findings on the same page imply real issues, not anchoring*. No claim about reviewer-to-reviewer statistical independence is made. (See `evals/anti-anchoring/` if it exists for empirical measurement; otherwise this property is asserted as a design boundary, not measured.)

To prevent context leaking between rounds:

1. **Clean artifact only.** The artifact passed to each round's reviewer must be the current version with no revision marks, "Fixed:" annotations, or comments about prior reviews. If the fix agent left review-response comments in the artifact, strip them before the next round. **Exemption:** never strip, edit, or delete a `.crucible/fetched-endpoints.md` line, and never strip a `FETCHED-ENDPOINT:` call-site comment as a "stale annotation" — both are permanent disclosure records, not comments about a prior review round.
2. **Standardized framing.** The orchestrator's dispatch prompt must use the **same framing** for every round. Do not mention that prior review rounds occurred, what was fixed, or how many rounds have run. The reviewer sees the artifact as if it is the first review.
3. **No findings forwarding.** Never pass prior round findings to the next reviewer. This is already specified in quality-gate red-team mode but is restated here because the quality-gate orchestrator is the most likely point of accidental leakage.
