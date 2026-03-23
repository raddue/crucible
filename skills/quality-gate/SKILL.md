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

## How It Works

1. Receives: artifact content, artifact type, project context
2. Prepares the artifact for review (see Artifact Preparation below)
3. Invokes `crucible:red-team` as a **single-pass reviewer** (one dispatch = one review round). Quality-gate owns the iteration loop; red-team produces findings for one round and returns. Red-team does NOT run its own stagnation loop when invoked by quality-gate.
4. If red-team finds **zero Fatal and zero Significant issues:** artifact approved. Write final artifact to scratch directory, output consolidated Minor observations from all rounds (see Minor Issue Handling), clean up, and return.
5. If red-team finds Fatal or Significant issues: dispatch a **separate fix agent** (see Fix Mechanism below), then invoke a FRESH red-team on the revised artifact (no anchoring)
6. Track weighted score between rounds (Fatal=3, Significant=1):
   - **Strictly lower score** → progress, loop again
   - **Same or higher score** → run first-pass score/Fatal check, then semantic comparison if needed, before declaring stagnation (see Stagnation Detection below)
7. **Progress notification (non-blocking).** After round 5 and every 3 rounds thereafter (rounds 5, 8, 11, 14), the orchestrator emits a status line: "Quality gate round [N]: score progression [list], [X] recurring / [Y] new findings this round." This is informational only — it does not pause or require user input.
8. **Global safety limit: 15 rounds.** This is a runaway protection circuit-breaker. If you hit 15, escalate to user with full round history.

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

## Stagnation Detection

Stagnation uses **weighted scoring** (Fatal=3, Significant=1) AND **Fatal count tracking** as a first-pass check. When the first-pass check would trigger stagnation, a **semantic comparison** of findings runs before escalating.

### First-Pass Check (Score-Based)

**Progress requires EITHER:**
- Weighted score strictly lower than prior round, OR
- Fatal count strictly lower AND weighted score same-or-lower

This prevents false stagnation when a Fatal is genuinely fixed but enough new Significants are surfaced to maintain the same weighted score (e.g., 1 Fatal → 0 Fatal + 3 Significant = score 3 → 3, but Fatal count 1 → 0 = progress).

**Oscillation detection:** If the weighted score *increases* in any round (not just stays the same), flag it explicitly as a **regression**, not just stagnation. Report: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating." Oscillation bypasses semantic comparison — it is always an immediate escalation.

If the first-pass check shows progress (score decreased or Fatal count decreased), continue the loop. No semantic comparison needed.

If the first-pass check would trigger stagnation (neither progress condition met, and no oscillation), proceed to semantic comparison.

### Semantic Comparison (Second-Pass)

The semantic comparison only runs when the score-based first-pass check would trigger stagnation — not every round. Round 1 has no prior round, so semantic comparison cannot trigger on round 1. Stagnation detection begins at round 2 at the earliest.

**Procedure:**

1. Read `round-N-findings.md` and `round-(N-1)-findings.md` from the scratch directory.
2. For each finding in round N, determine if it is the same core concern as any finding in round N-1 (semantic match — same section of the artifact, same type of problem, even if worded differently).
3. Classify each round N finding as **Recurring** (appeared in both rounds) or **New** (only in current round).
4. When the match is uncertain, default to **New** (fail-open — err toward declaring progress rather than falsely declaring stagnation).
5. Write the result to `round-N-comparison.md` in the scratch directory as a structured table:

| Round N-1 Finding | Round N Finding | Match Judgment | Reasoning |
|---|---|---|---|
| (prior finding summary) | (current finding summary) | Recurring / New | (why matched or not) |

**Anti-anchoring preserved:** The comparison is orchestrator-internal only. Prior findings are never passed to the reviewer. The comparison uses findings files already on disk (compaction recovery compatible).

### Decision Rules (After Semantic Comparison)

**All New:** All round N findings are new (none recurring). The fix cycle resolved all prior issues; the fresh reviewer found new attack surfaces. This is **progress** — continue loop, then check for diminishing returns (see below).

**All Recurring:** All round N findings appeared in round N-1. This is **stagnation** — escalate.

**Mixed (recurring + new):**
- Any recurring **Fatal** exists: **stagnation** — escalate. A Fatal that survives a fix attempt is genuinely stuck.
- Only recurring **Significants** (no recurring Fatals) AND at least one new finding exists: **progress** — continue. The fix cycle is making headway. However, if the same Significant has recurred for 2 consecutive rounds (appeared in rounds N-2, N-1, AND N), treat it as stuck and escalate. The first recurrence gets benefit of the doubt; the second consecutive recurrence proves iteration cannot resolve it.
- Only recurring **Significants**, no new findings: **stagnation** — escalate. Nothing new was found and the recurring issues were not fixed.

### Diminishing Returns Detection

When the semantic comparison determines all findings are new (progress), the orchestrator performs one additional check: **difficulty-class tagging**.

Each new finding is classified based on its proposed fix:

- **Surface:** The finding's proposed fix is a targeted change to the artifact (missing section, unclear language, wrong assumption, omitted edge case). The fix agent can resolve this.
- **Structural:** The finding's proposed fix requires rethinking a design decision, changing scope, or accepting a known trade-off (architectural tension, inherent complexity, out-of-scope dependency). Iteration cannot resolve this — it needs user judgment.

The orchestrator determines the class by examining whether each finding's proposed fix targets the artifact directly (Surface) or requires scope/design reconsideration (Structural). When in doubt, classify as **Surface** (fail-safe toward continued iteration rather than premature escalation).

**Decision rule:** Diminishing returns triggers only after **2 consecutive rounds** where all findings are new AND all are classified as Structural. The first all-new-all-Structural round is treated as progress (continue loop) — this confirms the classification is stable and not a one-round artifact. The second consecutive all-new-all-Structural round triggers **diminishing returns**, escalating with a distinct message (see Escalation below). This is NOT stagnation and NOT a failure — it is the gate recognizing it has extracted all the value iteration can provide.

**Three-way exit:** The gate now has three exit modes: **approved** (zero Fatal/Significant) | **stagnation** (recurring issues) | **diminishing returns** (all-new but all-Structural for 2 consecutive rounds).

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
- `round-N-comparison.md`: semantic comparison table (written only on rounds where semantic comparison ran; see Stagnation Detection)

**Compaction recovery:**
1. Glob for `active-run-*.md` markers to locate the scratch directory.
2. Read scratch directory to determine current round (highest N in `round-N-score.md` files).
3. Read the latest `artifact-N.md` as the current artifact state.
4. Read all `round-N-score.md` files to reconstruct the score progression.
5. Read all `round-N-comparison.md` files to determine: (a) whether semantic comparison already ran for the current round, (b) the consecutive-round state needed for diminishing returns detection (2 consecutive all-new-all-Structural rounds) and stuck-Significant tracking (same Significant recurring across 2 consecutive rounds).
6. Read the last 2-3 `round-N-comparison.md` files to reconstruct whether the current round is the first or second consecutive all-new-all-Structural round, and whether any Significant has recurred across consecutive rounds.
7. Output status to user: "Quality gate recovered after compaction. Round N complete, score progression: [list]. Continuing."
8. Dispatch the next red-team round.

**Cleanup:** Delete scratch directory and your `active-run-<run-id>.md` marker after the gate completes (approved, stagnation, or diminishing returns).

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

- **Stagnation** (recurring issues confirmed by semantic comparison) → escalate to user: "Stagnation detected: Round N has [X] recurring issues from round N-1 and [Y] new issues. Recurring: [list]. Escalating."
- **Diminishing returns** (2 consecutive rounds of all-new, all-Structural findings) → escalate to user: "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list with proposed fixes]. Presenting for user judgment."
- **Regression** (score increased) → escalate immediately with regression flag
- **Global safety limit reached** (15 rounds) → escalate to user with full round history
- **Progress notification** (after round 5, then every 3 rounds) → non-blocking status line, no user action required
- **Architectural concerns** → escalate immediately (bypass loop)
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
- Declaring stagnation based on score alone without running semantic comparison of findings when score triggers stagnation

## Integration

- **crucible:red-team** — The engine that performs each review round. **Loop ownership:** Quality-gate uses red-team as a single-pass reviewer only (one dispatch = one review round, findings returned). Quality-gate owns the iteration loop, stagnation detection, and round tracking. Red-team does NOT run its own stagnation loop when invoked by quality-gate. Red-team's stagnation rules apply only when red-team is invoked directly (e.g., by `crucible:finish`).
- **crucible:design** — Produces design docs (gateable artifact)
- **crucible:planning** — Produces plans (gateable artifact)
- **crucible:debugging** — Produces hypotheses and fixes (gateable artifacts). **Note:** Debugging's Phase 5 must invoke `crucible:quality-gate` for fix review, not `crucible:red-team` directly. This ensures fixes get iteration tracking, compaction recovery, and user checkpoints.
- **crucible:mockup-builder** — Produces mockups (gateable artifact)
- **crucible:mock-to-unity** — Produces translation maps and implementations (gateable artifacts)
- **crucible:build** — Outermost orchestrator, controls all gates in pipeline
