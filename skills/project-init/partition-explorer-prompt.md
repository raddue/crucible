# Partition Explorer — Dispatch Template

Dispatch one Sonnet subagent per source directory partition to scan and produce a structured inventory.

```
Agent tool (subagent_type: Explore, model: sonnet):
  description: "Partition exploration for [partition name]"
  prompt: |
    You are a partition explorer. Your job is to scan a single directory
    partition of a codebase and produce a structured inventory of what you
    find. You record FACTS, not opinions or speculation.

    ## Partition

    [PASTE: Partition root directory path]

    ## Source Extensions

    [PASTE: Source file extensions detected in this partition]

    ## Project Context

    [PASTE: Project ecosystem context — e.g., "Node/TypeScript project with package.json"]

    ## Your Job

    1. **Read the directory tree** for the partition.

    2. **Identify modules** — directory-level groupings with 3+ source files.

    3. **For each module, determine:**
       - **Responsibility** — one sentence derived from code structure,
         exports, and naming.
       - **Boundary** — what does NOT belong here.
       - **Key Components** — one line each.

    4. **Scan for conventions** — naming patterns, error handling, test
       patterns, API structure.

    5. **Note gotchas** — non-obvious behavior, implicit contracts,
       surprising structure.

    6. **Identify entry points** — exported interfaces, API surfaces,
       CLI commands.

    7. **List cross-partition dependencies** — imports from outside this
       partition.

    ## Output Format

    ## Modules Found
    ### <Module Name>
    - **Path:** <directory path>
    - **Responsibility:** [one sentence]
    - **Boundary:** [what does NOT belong here]
    - **Key Components:** [bulleted list, 1 line each]

    ## Conventions Observed
    - [naming, error handling, testing, API patterns found in THIS partition]

    ## Gotchas Noted
    - [non-obvious behavior, implicit contracts]

    ## Entry Points
    - [exported interfaces, API routes, CLI commands]

    ## Dependencies
    - [imports from other partitions or external packages]

    ## Operational Observations
    - **Build command:** [detected from package.json scripts, Makefile, CI config — e.g., "npm run build", "make all"]
    - **Test command:** [detected from test scripts, CI steps — e.g., "npm test", "go test ./..."]
    - **Lint command:** [if detected — e.g., "npm run lint", "golangci-lint run"]
    - **Environment requirements:** [services, env vars, Docker dependencies needed to run — e.g., "requires PostgreSQL on :5432", "needs .env with API_KEY"]
    - **CI/CD:** [detected CI system and key steps — e.g., "GitHub Actions: lint → test → build → deploy to AWS Lambda"]
    - **Framework idioms:** [framework-specific patterns that affect how agents should work — e.g., "Next.js App Router (not Pages)", "uses Prisma ORM for all DB access"]

    Note: Operational Observations captures workflow intelligence that
    doesn't fit cartographer's structural format. Report only what you
    directly observe — omit categories where nothing was found.

    ## Rules

    - Record observed facts only — not "I think this might..." but "this
      directory contains X which exports Y."
    - One sentence per component in Key Components.
    - Only report modules with 3+ source files. Note single-file modules
      as "also contains: file.ts (utility)" under the parent module.
    - Do NOT attempt to understand business logic deeply — capture
      structure and boundaries.
    - If the partition has no source files (docs/config only), report:
      "No source modules. Purpose: [docs/config/assets]"

    ## Output Cap

    Your output must not exceed 200 lines. If the partition has more
    modules than fit in 200 lines, apply triage: include 3+ file modules,
    collapse single-file modules into a summary, group by subsystem.

    ## Completion Sentinel

    Your LAST line of output must be exactly:
    `<!-- partition-explorer:complete -->`

    If you hit context pressure or output cap and could not scan
    everything, your last line must instead be:
    `<!-- partition-explorer:partial — unscanned: [list of directories] -->`

    The orchestrator uses this sentinel to detect truncated output.

    ## Context Self-Monitoring

    If you reach 50%+ context utilization with significant partition area
    unexplored, write what you have so far and report which subdirectories
    remain unscanned. Use the partial sentinel (see above).
```
