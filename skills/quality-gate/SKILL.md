---
name: quality-gate
description: Iterative red-teaming of any artifact (design docs, plans, code, hypotheses, mockups). Loops until clean or stagnation. Invoked by artifact-producing skills or their parent orchestrator.
origin: crucible
---

# Quality Gate

Shared iterative red-teaming mechanism invoked at the end of artifact-producing skills. Provides rigorous adversarial review as the core quality mechanism.

**Announce at start:** "Running quality gate on [artifact type]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Execution model:** When this skill is running, YOU are the orchestrator. You drive the loop, dispatch fix agents and reviewers as subagents, track scores, and make escalation decisions. All references to "the orchestrator" in this document refer to you.

## Consensus Detection

At the start of the quality gate, check whether the `consensus_query` MCP tool
is available in the current environment:

1. If the tool is available: consensus-eligible rounds will use multi-model
   dispatch (see Multi-Model Red-Team Review and Multi-Model Consensus in
   Stagnation Detection below).
2. If the tool is not available: all rounds use standard single-model dispatch.
   No degradation, no warnings — the gate behaves exactly as it did before
   consensus was introduced.

**Do NOT:**
- Prompt the user to set up consensus if it is unavailable
- Log warnings about missing consensus configuration
- Change any scoring, stagnation, or escalation logic based on consensus availability

Consensus is a transparent enhancement. Its presence improves coverage;
its absence changes nothing.

## How It Works

1. Receives: artifact content, artifact type, project context
2. Prepares the artifact for review (see Artifact Preparation below)
3. Invokes `crucible:red-team` as a **single-pass reviewer** (one dispatch = one review round). Quality-gate owns the iteration loop; red-team produces findings for one round and returns. Red-team does NOT run its own stagnation loop when invoked by quality-gate.
4. If red-team finds **zero Fatal and zero Significant issues:** artifact approved. Write final artifact to scratch directory, output consolidated Minor observations from all rounds (see Minor Issue Handling), clean up, and return.
5. If red-team finds Fatal or Significant issues:
   a. Dispatch a **separate fix agent** (see Fix Mechanism below) — receive revised artifact, append to fix journal
   b. Dispatch **Fix Verifier** (see Fix Verification below) — one Sonnet check per fix round
   c. Append verifier output to fix journal under `### Verifier Assessment` heading; write verdict summary to `round-N-verification.md`
   d. If Fatal-severity Unresolved: flag as "prior unresolved Fatal — must address" in next round's fix dispatch (binding, one-round grace)
   e. If Significant-severity Unresolved: appended to fix journal as informational context
   f. Invoke a FRESH red-team on the revised artifact (no anchoring)
6. Track weighted score between rounds (Fatal=3, Significant=1):
   - **Strictly lower score** → progress, loop again
   - **Same or higher score** → dispatch the Stagnation Judge (see Stagnation Detection below)
7. Read the judge's verdict and act on it (see Stagnation Detection below)
8. **Progress notification.** After round 5 and every 3 rounds thereafter (rounds 5, 8, 11, 14), emit: "Quality gate round [N]: score progression [list]." If the judge was dispatched, append recurring/new counts. Informational only — no pause.
9. **Global safety limit: 15 rounds.** This is a runaway protection circuit-breaker. If you hit 15, escalate to user with full round history.

### Multi-Model Red-Team Review (when available)

**Applies to:** Round 1 and every 3rd round thereafter (rounds 1, 4, 7, 10, 13).
**Intermediate rounds:** Standard single-model red-team dispatch (no change).

On consensus-eligible rounds:
1. Instead of dispatching a single red-team subagent, call `consensus_query(mode: "review")` with the red-team prompt and artifact content
2. The consensus response provides merged findings with per-finding severity (Fatal/Significant/Minor), confidence (High/Medium/Low based on model agreement), provenance (which models raised it), and unique findings flagged as "potentially novel"
3. The orchestrator processes these findings exactly as single-model findings: compute weighted score, compare to prior round, dispatch fix agent if needed
4. Findings from consensus rounds include provenance metadata in `round-N-findings.md`

**Cost control:** The consensus dispatch replaces (not supplements) the single-model dispatch on eligible rounds.
**Fallback:** If consensus is unavailable on an eligible round, dispatch standard single-model red-team review.

## Fix Mechanism

The orchestrator coordinates the loop but does NOT fix artifacts directly. Fixes are dispatched to a **separate subagent** to maintain separation of concerns between coordination, review, and remediation.

| Artifact Type | Fix Agent |
|---|---|
| design | Plan Writer subagent revises the doc |
| plan | Plan Writer subagent revises the plan |
| code | Fix subagent (new, not the original implementer) |
| hypothesis | Debugging skill's hypothesis refinement (see below) |
| mockup | Fix subagent |
| translation | Fix subagent revises the translation map |

**Before dispatching the fix agent (code artifacts only):** If crucible:checkpoint is available, create checkpoint with reason "pre-qg-fix-round-N". Non-code artifacts (design, plan, hypothesis, mockup, translation) skip this step — they are fully captured by the existing artifact-N.md snapshots.

The fix agent receives: (a) the current artifact, (b) the red-team findings, (c) project context, and (d) the **fix journal** from prior rounds (see Fix Memory below). It returns the revised artifact. The orchestrator writes the revised artifact to the scratch directory and dispatches the next red-team round.

The orchestrator never applies fixes directly. Even trivial fixes go through a fix agent to maintain separation of concerns. The cost of dispatching for a small fix is negligible; the risk of the orchestrator conflating coordination with fixing is not.

## Fix Memory

Anti-anchoring is a property of **review**, not **remediation**. Reviewers need fresh eyes to avoid confirmation bias. Fix agents need institutional memory to avoid repeating failed strategies.

The quality gate maintains a **fix journal** (`fix-journal.md` in the scratch directory) that accumulates across rounds. After each fix agent completes, the orchestrator appends a structured entry:

```
## Round N Fix
- **Findings addressed:** [list of Fatal/Significant findings from round N, summarized]
- **Approach taken:** [1-2 sentence description of fix strategy]
- **Files changed:** [list of files modified]
- **Reasoning:** [why this approach was chosen over alternatives]
```

**On subsequent rounds, the fix agent receives the full fix journal.** This gives the fix agent critical context:
- What approaches were already tried (avoid repeating failed strategies)
- Which files were already modified (avoid unknowingly reverting prior fixes)
- The reasoning chain across rounds (understand the trajectory of remediation)

**Anti-anchoring is preserved.** The fix journal is NEVER passed to the red-team reviewer. Reviewers see only the clean artifact. The journal flows exclusively through the remediation path: fix agent writes it, next fix agent reads it, orchestrator maintains it.

**Round 1 fix agents** receive an empty journal (no prior rounds). This is the only round where the fix agent works without remediation history.

**Why this matters:** Without fix memory, the most common causes of stagnation and oscillation are fix agents repeating failed approaches or unknowingly reverting prior fixes while addressing new findings. Fix memory turns these escalation events into solvable problems -- the fix agent can see what was already tried and choose a genuinely different approach.

**Compaction recovery:** The fix journal is written to `fix-journal.md` in the scratch directory alongside round scores and findings. It is recovered automatically when the orchestrator reads the scratch directory after compaction.

## Fix Verification

After each fix agent completes and before the next red-team round, dispatch a **Fix Verifier** — a dedicated Sonnet agent that checks whether each fix actually resolves its stated finding. No re-fix sub-loop; the verifier checks once, and its output feeds into the fix journal for the next round.

**Dispatch method:** Task tool (model: Sonnet), same pattern as the stagnation judge. The verifier needs no file access; the orchestrator pastes all input directly.

**Input the orchestrator provides:**
1. Round N findings (the findings the fix agent was asked to address)
2. The current round's fix journal entry only — the `## Round N Fix` section just appended (not the full journal)
3. Prepared artifact:
   - Non-code (design docs, plans, hypotheses, mockups, translations): post-fix version in full
   - Code: diff + full post-fix source of files touched by the diff. For large implementations (>2000 lines), dispatch one verifier call per finding if context exceeds limits.
4. The full content of `fix-verifier-prompt.md` as the agent's instructions

**Reading the verdict:** The verifier returns a per-finding Resolved/Unresolved table and an overall PASS/FAIL.

**Handling Unresolved findings:**
- **Fatal-severity Unresolved:** Flagged as "prior unresolved Fatal — must address" in the next round's fix dispatch. This is binding with one-round grace: if the fix agent addresses it and the next red-team round does NOT re-raise the finding, the binding expires. If the verifier marks the same Fatal as Unresolved again (persistent disagreement), the verdict downgrades to informational. Sonnet should not permanently override Opus.
- **Significant-severity Unresolved:** Appended to the fix journal as informational context. The next round's fix agent may address, disagree with, or deprioritize.
- **All Resolved (PASS):** Proceed to next red-team round normally.

**Fix journal integration:** The verifier's output is appended under a `### Verifier Assessment` heading in the fix journal, distinct from the `## Round N Fix` entry format. This keeps verifier assessments on the remediation path (fix agents see them) without contaminating the review path (red-team never sees them).

**Anti-anchoring preserved:** The verifier is on the remediation path — its output flows to fix agents only, never to the red-team reviewer. Same isolation as the fix journal itself.

**Round counter unchanged:** The verifier dispatch does not increment the round counter. It is part of the fix step, not a separate review round.

## Stagnation Detection

Two-layer system: the orchestrator handles scoring; a dedicated judge agent handles semantic analysis.

### First-Pass Check (orchestrator — runs every round)

Stagnation uses **weighted scoring** (Fatal=3, Significant=1) AND **Fatal count tracking**.

**Progress requires EITHER:**
- Weighted score strictly lower than prior round, OR
- Fatal count strictly lower AND weighted score same-or-lower

If either condition is met → progress, loop again. No judge needed.

**Oscillation detection:** If the weighted score *increases* (not just stays the same), escalate immediately as a **regression**. Report: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating." No judge needed.

**Regression with checkpoint:** If a pre-qg-fix-round checkpoint exists for the prior round, include in the escalation: "A checkpoint of the pre-fix state exists (`<hash>`). Options: (a) restore to pre-fix checkpoint and retry with different fix strategy, (b) continue with current state, (c) escalate to user." If no checkpoint exists, escalate as currently specified.

### Multi-Model Consensus (when available)

When the `consensus_query` MCP tool is available and consensus mode `verdict` is enabled:

1. Instead of dispatching a single Sonnet judge via Task tool, call
   `consensus_query(mode: "verdict")` with:
   - prompt: the stagnation judge prompt from `stagnation-judge-prompt.md`
   - context: round N findings, round N-1 findings, latest fix journal entry,
     prior comparison files (same inputs as the single-model judge)
   - metadata: { artifact_type, round_number, score_progression }

2. Read the consensus response:
   - If `status: "consensus"` or `status: "partial"`:
     - Use the `synthesis` verdict (PROGRESS/STAGNATION/DIMINISHING_RETURNS)
     - If the verdict is STAGNATION or DIMINISHING_RETURNS and disagreements
       exist, include the dissent summary in the escalation message:
       "Stagnation detected (consensus: N/M models agree, dissent: [summary])."
   - If `status: "unavailable"`:
     - Fall back to single-Sonnet judge dispatch (existing behavior)

3. The comparison file (`round-N-comparison.md`) includes the consensus
   metadata: models queried, models responded, agreement level, and any
   dissenting verdicts.

### Judge Dispatch (only when first-pass check would trigger stagnation)

If neither progress condition is met AND the score did not increase (i.e., same score, no Fatal count improvement), dispatch the **Stagnation Judge** — a dedicated Sonnet agent that performs semantic comparison of findings across rounds. If the `consensus_query` tool is not available in the environment, this step uses the standard single-Sonnet dispatch described below.

**Dispatch method:** Task tool (model: Sonnet). The judge needs no file access; the orchestrator pastes all input directly.

**Input the orchestrator provides:**
1. The content of `round-N-findings.md` (current round)
2. The content of `round-(N-1)-findings.md` (prior round)
3. The latest fix journal entry only — extract the last `## Round N Fix` section from `fix-journal.md` (not the full journal)
4. The content of any prior `round-*-comparison.md` files (for consecutive-round state tracking)
5. The full content of `stagnation-judge-prompt.md` as the agent's instructions

**Reading the verdict:** The judge returns a structured verdict: **PROGRESS**, **STAGNATION**, or **DIMINISHING_RETURNS**.
- **PROGRESS** → loop again
- **STAGNATION** → escalate: "Stagnation detected: Round N has [X] recurring issues from round N-1 and [Y] new issues. Recurring: [list from judge]. Escalating."
- **DIMINISHING_RETURNS** → escalate: "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list from judge]. Presenting for user judgment."

**The judge also writes:** a `round-N-comparison.md` file. The orchestrator saves the judge's full output as `round-N-comparison.md` in the scratch directory. This file is used by future judge dispatches for consecutive-round tracking.

## Artifact Preparation

### Small artifacts (design docs, plans, hypotheses, mockups, translations)

Pass the full artifact content to the red-team subagent. No preparation needed.

### Code artifacts

Code artifacts vary in size. The orchestrator prepares the artifact based on scope:

- **Small implementations (<500 lines diff):** Pass the full diff + any new files in full.
- **Medium implementations (500-2000 lines):** Pass full source of high-risk files (new files, files with complex logic changes) + summaries of routine changes (imports, wiring, boilerplate). Include a change manifest listing all files with 1-line descriptions.
- **Large implementations (>2000 lines):** Split into logical chunks (by subsystem, module, or feature boundary). Run a quality gate on each chunk, then a final cross-chunk round reviewing the integration points. Present the chunking plan to the user before proceeding. Normal stagnation detection, progress notifications, and round 15 safety limit apply to **total rounds across all chunks**, not per chunk. **Chunked compaction recovery:** Use a parent run-id for the entire chunked gate. Write `chunk-manifest.md` (lists all chunks with gated/pending status) to the parent scratch directory. Per-chunk round files go in `chunk-N/` subdirectories. Only delete the parent scratch directory after the final cross-chunk round completes. The `active-run.md` marker references the parent run-id throughout.

The red-team subagent receives the **prepared artifact**, not raw diff. This mirrors audit's Tier 1/Tier 2 context management approach.

### Hypothesis artifacts

Hypotheses are 1-2 sentence statements, not plans or designs. The red-team prompt template is plan-centric and does not map well to hypothesis testing. For hypothesis artifacts, the orchestrator frames the red-team dispatch with hypothesis-specific attack vectors:

- Does this hypothesis explain ALL observed symptoms?
- What evidence would disprove it?
- Are there simpler alternative explanations?
- What assumptions does this hypothesis make that could be wrong?

Include these in the dispatch prompt alongside the standard red-team template. The debugging skill's Phase 3.5 defines these questions -- the quality-gate orchestrator should use them.

## Minor Issue Handling

Minor issues do not trigger fix rounds and do not count toward stagnation. However, they accumulate across rounds and contain useful information. Do not silently discard them.

**After the gate completes** (artifact approved or stagnation escalated):

1. **Consolidate:** Collect all Minor observations from all rounds, deduplicate.
2. **Quick-fix pass:** Dispatch a fix subagent with the consolidated minors and the final artifact. The fix agent addresses easy wins only — changes that are simple, low-risk, and unambiguous (typos, naming inconsistencies, missing edge-case guards, trivial cleanup). It skips anything requiring judgment or design decisions.
3. **Present remainder:** Output any minors the fix agent skipped as "Remaining minor observations" so the user can decide whether to address them. No further red-team round on the quick fixes — the gate is already complete.

## Anti-Anchoring Rules

The iterative loop's value depends on each reviewer seeing the artifact with fresh eyes. To prevent information leaking between rounds:

1. **Clean artifact only.** The artifact passed to each round's reviewer must be the current version with no revision marks, "Fixed:" annotations, or comments about prior reviews. If the fix agent left review-response comments in the artifact, strip them before the next round.
2. **Standardized framing.** The orchestrator's dispatch prompt must use the **same framing** for every round. Do not mention that prior review rounds occurred, what was fixed, or how many rounds have run. The reviewer sees the artifact as if it is the first review.
3. **No findings forwarding.** Never pass prior round findings to the next reviewer. This is already specified in `crucible:red-team` but is restated here because the quality-gate orchestrator is the most likely point of accidental leakage.

## Round History and Compaction Recovery

Quality gate writes round state to disk for compaction recovery.

**Scratch directory:** `~/.claude/projects/<project-hash>/memory/quality-gate/scratch/<run-id>/` where `<run-id>` is a timestamp generated at the start of the gate. This path is persistent and discoverable (matching the audit skill's pattern), so it survives compaction even if the run-id is lost from context — the orchestrator can list the directory to find active runs.

**Tool constraint:** All scratch directory operations (create, read, list, delete) must use Write, Read, and Glob tools — NOT Bash. Safety hooks block Bash commands referencing `.claude/` paths.

**Active run marker:** At the start of the gate, write `~/.claude/projects/<project-hash>/memory/quality-gate/active-run-<run-id>.md` containing the run-id and scratch directory path. Delete only your own marker when the gate completes. After compaction, glob for `active-run-*.md` files to locate active runs — recover the one whose run-id matches context, or the most recent if context is lost.

**Stale cleanup:** At the start of each gate, delete scratch directories whose timestamps are older than 2 hours AND that are NOT referenced by any `active-run-*.md` marker.

**After each round, write:**
- `round-N-score.md`: weighted score, Fatal count, Significant count, Minor count
- `round-N-findings.md`: the red-team findings for this round
- `artifact-N.md`: the artifact snapshot after fixes (input to round N+1)
- `fix-journal.md`: cumulative fix journal (appended after each fix agent completes; see Fix Memory above)
- `round-N-comparison.md`: stagnation judge output (only exists for rounds where the judge was dispatched — absence on clean-progress rounds is expected, not an error). When multi-model consensus was used, this file also contains consensus metadata: models queried, models responded, agreement level, and any dissenting verdicts.
- `round-N-verification.md`: fix verifier verdict summary (written after every fix round — unlike comparison files, these exist for every round that had fixes)

**Compaction recovery:**
0. Read `## Compression State` from `pipeline-status.md` — recover Goal, Key Decisions (including parent skill decisions that affect the gate), Active Constraints, and Next Steps. If absent, skip to step 1. Note: quality-gate is invoked by a parent skill (build, debugging, spec), so the Compression State reflects the parent's context. The quality-gate orchestrator inherits this context.
1. Glob for `active-run-*.md` markers to locate the scratch directory.
2. Read scratch directory to determine current round (highest N in `round-N-score.md` files).
3. Read the latest `artifact-N.md` as the current artifact state.
4. Read all `round-N-score.md` files to reconstruct the score progression.
5. Read all `round-N-comparison.md` files to reconstruct consecutive-round state for the stagnation judge. Absence of comparison files is expected on clean-progress rounds.
6. Read all `round-N-verification.md` files to recover fix verifier state. If any Fatal-severity Unresolved verdicts exist in the latest verification file, carry them forward as binding context for the next fix dispatch.
7. Output status to user: "Quality gate recovered after compaction. Round N complete, score progression: [list]. Continuing."
8. Emit a Compression State Block into the conversation with gate-specific state: current round, score progression, artifact type under review. Inherit Goal and Key Decisions from the parent skill's last Compression State if available.
8b. Check whether `consensus_query` MCP tool is available (consensus
    availability may have changed across compaction boundary). Use current
    availability for subsequent rounds regardless of what was used pre-compaction.
9. Dispatch the next red-team round.

### Checkpoint Timing

Emit a Compression State Block at:
- **Every 3 rounds:** After rounds 3, 6, 9, 12
- **Before stagnation judge dispatch:** When the first-pass check would trigger stagnation
- **Gate completion:** When the gate passes or escalates (before returning to parent skill)
- **Health transitions:** On any GREEN->YELLOW or YELLOW->RED transition

**Cleanup:** Delete scratch directory and your `active-run-<run-id>.md` marker after the gate completes (pass or stagnation).

## Invocation Convention

Quality gate is invoked by the **outermost orchestrator only** — not self-invoked by child skills. This avoids double-gating.

**Rule: Skills NEVER self-invoke quality-gate.** They only document that their output is gateable. The outermost orchestrator (build, the user session, or another pipeline) always handles gating. This eliminates the ambiguity of skills trying to detect whether they are running standalone or as a sub-skill.

### When Used Standalone (user invokes directly)

The user's session is the outermost orchestrator. When a user runs `/design` directly, the design skill produces the doc and documents it as gateable. The user's session (following the design skill's instructions) invokes quality-gate.

### When Used as a Sub-Skill of Build

Build is the outermost orchestrator and controls all quality gates:

- **Phase 1 (after design):** Quality gate on design doc (artifact type: design)
- **Phase 2 (after plan review):** Quality gate on plan (artifact type: plan)
- **Phase 4 (after implementation):** Quality gate on full implementation (artifact type: code)

### Artifact Types

| Type | Produced By | Gate Trigger |
|------|-------------|-------------|
| design | `crucible:design` | After design doc is saved |
| plan | `crucible:planning` | After plan passes review |
| hypothesis | `crucible:debugging` | Phase 3.5, before implementation |
| code | `crucible:debugging`, build | After implementation/fix |
| mockup | `crucible:mockup-builder` | After mockup is created |
| translation | `crucible:mock-to-unity` | After self-verification |

### Documentation Convention

Each artifact-producing skill's SKILL.md documents:

> "This skill produces **[artifact type]**. The outermost orchestrator invokes `crucible:quality-gate` after [trigger]."

## Escalation

Three exit modes beyond clean approval:

- **Stagnation** → escalate to user with recurring/new classification from the judge: "Stagnation detected: Round N has [X] recurring issues from round N-1 and [Y] new issues. Recurring: [list]. Escalating."
- **Diminishing returns** → escalate to user with structural findings from the judge: "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list]. Presenting for user judgment."
- **Regression** (score increased) → escalate immediately, no judge needed: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating."
- Global safety limit reached (15 rounds) → escalate to user with full round history
- Architectural concerns → escalate immediately (bypass loop)
- User can interrupt at any time to skip the gate

## Red Flags

- Orchestrator fixing artifacts directly instead of dispatching a fix agent
- Rationalizing away red-team findings instead of addressing them
- Skipping the gate without user approval
- Exceeding the 15-round safety limit without escalating
- Using the same red-team agent across rounds (always dispatch fresh)
- Declaring stagnation on raw issue count without using weighted score (Fatal=3, Significant=1)
- Passing revision context, prior findings, round history, or fix journal to the red-team reviewer (fix journal is for fix agents ONLY)
- Leaving review-response artifacts (comments, annotations) in the artifact between rounds
- Dispatching a fix agent without the fix journal on round 2+ (fix agents need remediation history)
- Orchestrator performing semantic comparison inline instead of dispatching the stagnation judge
- Dispatching the judge when the score is strictly improving (waste — score alone is sufficient)
- Forgetting to save the judge's output as `round-N-comparison.md` (breaks consecutive-round tracking)
- Skipping the fix verifier dispatch after a fix agent completes (every fix round gets verified)
- Passing verifier output to the red-team reviewer (verifier is on the remediation path only)
- Re-dispatching the fix agent based on verifier results (no re-fix sub-loop — verifier checks once, output feeds into next round)
- Skipping Compression State Block emission at checkpoint boundaries
- Emitting a Compression State Block with stale or missing Key Decisions (decisions must be cumulative across all prior blocks)
- Allowing the Goal field to drift across successive Compression State Blocks (must match original user request)
- Exceeding 10 entries in the Key Decisions list without overflow-compressing the oldest
- Using consensus on every red-team round (periodic only: rounds 1, 4, 7, ...)
- Treating single-model unique findings from consensus as less important than multi-model agreements
- Passing consensus provenance metadata to the fix agent's red-team framing (provenance is for the fix journal and orchestrator, not for biasing the next reviewer)

## Integration

- **crucible:red-team** — The engine that performs each review round. **Loop ownership:** Quality-gate uses red-team as a single-pass reviewer only (one dispatch = one review round, findings returned). Quality-gate owns the iteration loop, stagnation detection, and round tracking. Red-team does NOT run its own stagnation loop when invoked by quality-gate. Red-team's stagnation rules apply only when red-team is invoked directly (e.g., by `crucible:finish`).
- **crucible:design** — Produces design docs (gateable artifact)
- **crucible:planning** — Produces plans (gateable artifact)
- **crucible:debugging** — Produces hypotheses and fixes (gateable artifacts). **Note:** Debugging's Phase 5 must invoke `crucible:quality-gate` for fix review, not `crucible:red-team` directly. This ensures fixes get iteration tracking, compaction recovery, and user checkpoints.
- **crucible:mockup-builder** — Produces mockups (gateable artifact)
- **crucible:mock-to-unity** — Produces translation maps and implementations (gateable artifacts)
- **crucible:build** — Outermost orchestrator, controls all gates in pipeline
- **crucible:checkpoint** — Shadow git checkpoints before code-artifact fix rounds (recommended). Provides rollback target when fix rounds introduce regressions.
