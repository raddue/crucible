# Cross-Platform Compatibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Make crucible discoverable and installable across Claude Code, Cursor, and OpenAI Codex, with a clean README that positions it as universal-first.

**Architecture:** Documentation and packaging changes only — no SKILL.md instructional text refactoring yet. Clean up README, add plugin manifest, document platform coupling, fix 3 skill descriptions.

**Tech Stack:** Markdown, JSON

---

### Task 1: README Overhaul — Universal Positioning and Cleanup

**Files:**
- Modify: `README.md`

**Step 1: Read the current README**

Read `README.md` and identify all sections that need changes.

**Step 2: Rewrite the README**

Apply these changes:

1. **Opening line** — change from Claude Code-specific to universal:
   - Old: "A collection of Claude Code skills for systematic software development."
   - New: "A collection of agent skills for systematic software development. Works with Claude Code, Cursor, and OpenAI Codex — any platform that supports the Agent Skills specification."

2. **Installation section** — add cross-platform instructions:
   ```markdown
   ## Installation

   ### Claude Code

   Clone and symlink into your skills directory:

   ```bash
   git clone git@github.com:raddue/crucible.git ~/repos/crucible
   ln -s ~/repos/crucible/skills/* ~/.claude/skills/
   ```

   Or install as a plugin:

   ```bash
   claude plugin install raddue/crucible
   ```

   ### Cursor

   Clone into your project and add to your plugin configuration:

   ```bash
   git clone git@github.com:raddue/crucible.git .crucible
   ```

   Skills are auto-discovered from the `skills/` directory.

   ### OpenAI Codex

   Clone and register as a skills source:

   ```bash
   git clone git@github.com:raddue/crucible.git ~/repos/crucible
   ```

   Skills follow the Agent Skills specification and are compatible with Codex's SKILL.md discovery.
   ```

3. **Setup section** — reframe Claude Code-specific settings with a header:
   ```markdown
   ## Setup (Claude Code)

   These settings are specific to Claude Code. Other platforms have equivalent configuration — see [PLATFORMS.md](PLATFORMS.md) for details.
   ```
   Keep the three existing settings (`--dangerously-skip-permissions`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`) but add a note after the agent teams setting:

   > Skills degrade gracefully without agent teams — independent tasks run sequentially instead of in parallel. This applies to all platforms where parallel subagent dispatch is not available.

4. **Skills table** — reorganize into Universal and Domain-Specific sections:
   - Rename "Design & UI" to "Unity UI (Domain-Specific)" and move to bottom before Knowledge & Learning
   - Add a one-line note: "These skills are for Unity UI Toolkit projects. All other skills are language- and framework-agnostic."

5. **Merge duplicate Origin sections** — delete "Origin" (line 161-163) and "Project Origin" (line 171-179). Replace with a single section:
   ```markdown
   ## Origin

   Originally forked from [obra/superpowers](https://github.com/obra/superpowers), now independently maintained and significantly diverged. Crucible was originally developed for a Unity 6 project — the three Unity UI skills (mockup-builder, mock-to-unity, ui-verify) reflect that origin. All other skills are language- and framework-agnostic.
   ```

6. **Third-Party Skills** — keep as-is

**Step 3: Verify the README renders correctly**

Review the final markdown for broken links, table formatting, and section flow.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: reposition README as universal-first with cross-platform installation"
```

---

### Task 2: Create PLATFORMS.md — Platform Coupling Documentation

**Files:**
- Create: `PLATFORMS.md`

**Step 1: Write the platform coupling document**

Create `PLATFORMS.md` documenting:

1. **Cross-platform status** — which skills work where and what needs adaptation
2. **Coupling inventory** — categorized list of Claude Code-specific references:
   - Tool names: Agent, TeamCreate, TaskCreate, TaskUpdate, SendMessage, Skill, Read, Edit, Write, Glob, Grep, Bash
   - Subagent types: `subagent_type="general-purpose"`, `subagent_type="Explore"`
   - Model directives: `model: haiku`, `model: sonnet`, `model: opus`
   - Storage paths: `~/.claude/projects/<hash>/memory/`
   - Skill invocation: `crucible:` prefix (40+ references)
   - Environment variables: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
3. **Graceful degradation** — document what happens when features aren't available:
   - No agent teams → sequential execution (already implemented in build)
   - No subagent dispatch → skill instructions still work as methodology guides
   - No persistent storage → forge and cartographer don't accumulate (but other skills unaffected)
   - No model selection → platform picks model (skill still works)
4. **Skill compatibility tiers:**
   - **Tier 1 — Fully portable** (methodology-only, no tool coupling in instructions): planning, design, test-driven-development, verify, review-feedback, innovate, getting-started, finish
   - **Tier 2 — Portable with reduced capability** (uses subagents for parallelism but degrades gracefully): quality-gate, red-team, inquisitor, code-review, parallel, adversarial-tester, debugging, worktree, stocktake
   - **Tier 3 — Platform-dependent** (requires Claude Code-specific features): build (agent teams), forge-skill (persistent memory), cartographer-skill (persistent memory)
   - **Tier 4 — Domain-specific** (Unity UI Toolkit): mockup-builder, mock-to-unity, ui-verify
5. **Migration roadmap** — what would need to change for full cross-platform support (future work, not this PR)

**Step 2: Commit**

```bash
git add PLATFORMS.md
git commit -m "docs: add PLATFORMS.md documenting cross-platform coupling and compatibility tiers"
```

---

### Task 3: Create Plugin Manifest for Claude Code Marketplace

**Files:**
- Create: `.claude-plugin/plugin.json`

**Step 1: Create the directory and manifest**

```json
{
  "name": "crucible",
  "version": "1.0.0",
  "description": "24 agent skills for systematic software development. Covers the full lifecycle: design, planning, TDD, code review, debugging, quality gates, and adversarial testing. Every skill is eval-tested with measured A/B deltas using Anthropic's skill evaluation framework.",
  "author": {
    "name": "raddue",
    "url": "https://github.com/raddue"
  },
  "homepage": "https://github.com/raddue/crucible",
  "repository": "https://github.com/raddue/crucible",
  "license": "MIT",
  "keywords": [
    "development-pipeline",
    "tdd",
    "code-review",
    "quality-gate",
    "red-team",
    "debugging",
    "planning",
    "design",
    "adversarial-testing",
    "eval-tested"
  ],
  "skills": "./skills/"
}
```

**Step 2: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat: add .claude-plugin/plugin.json for marketplace submission"
```

---

### Task 4: Fix Platform-Specific Skill Descriptions

**Files:**
- Modify: `skills/getting-started/SKILL.md` (line 3)
- Modify: `skills/cartographer-skill/SKILL.md` (line 3)
- Modify: `skills/inquisitor/SKILL.md` (line 3)

Only 3 of 24 descriptions contain platform-specific language.

**Step 1: Fix getting-started description**

Old: `description: Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response including clarifying questions`

New: `description: Use when starting any conversation - establishes how to find and use skills, requiring skill activation before ANY response including clarifying questions`

**Step 2: Fix cartographer-skill description**

Old: `description: Use when exploring unfamiliar code and want to persist what you learn, when starting a task and want to consult known codebase structure, or when a subagent needs module-specific context for implementation or review`

New: `description: Use when exploring unfamiliar code and want to persist what you learn, when starting a task and want to consult known codebase structure, or when collaborators need module-specific context for implementation or review`

**Step 3: Fix inquisitor description**

Old: `description: Use when a full feature is assembled and you want to hunt cross-component bugs before final quality gate. Dispatches 5 parallel adversarial dimensions against the complete implementation diff. Triggers on 'inquisitor', 'hunt bugs', 'cross-component test', 'find integration issues', or automatically in build pipeline Phase 4.`

New: `description: Use when a full feature is assembled and you want to hunt cross-component bugs before final quality gate. Runs 5 parallel adversarial dimensions against the complete implementation diff. Triggers on 'inquisitor', 'hunt bugs', 'cross-component test', 'find integration issues', or automatically in build pipeline Phase 4.`

**Step 4: Commit**

```bash
git add skills/getting-started/SKILL.md skills/cartographer-skill/SKILL.md skills/inquisitor/SKILL.md
git commit -m "fix: make 3 skill descriptions platform-neutral"
```

---

### Task 5: Update .gitignore and Final Verification

**Files:**
- Modify: `.gitignore`

**Step 1: Remove docs/plans/ from .gitignore**

The current `.gitignore` excludes `docs/plans/` — but implementation plans are artifacts we want in the repo. Remove that line. Keep `node_modules/`.

**Step 2: Verify all changes**

- README renders correctly with no broken links or formatting issues
- PLATFORMS.md is accurate against actual skill content
- `.claude-plugin/plugin.json` is valid JSON
- All 3 skill description edits are correct
- No unintended file changes

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "fix: stop excluding docs/plans/ from git"
```
