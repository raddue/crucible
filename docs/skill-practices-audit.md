# Skill practices audit

Warn-only snapshot for #719; violations do not fail CI. Re-run `python3 scripts/check_skill_best_practices.py`. Scripts column is a best-effort dependency-note heuristic. Later `--enforce` can compare per-skill failures against a ratchet baseline; no baseline or enforcement exists yet.

| Skill | Body | Contents | Nesting | Frontmatter | Scripts | Overall |
| --- | --- | --- | --- | --- | --- | --- |
| adr | PASS | PASS | PASS | FAIL | PASS | FAIL |
| adversarial-tester | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| anvil | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| assay | PASS | FAIL | FAIL | PASS | PASS | FAIL |
| audit | FAIL | FAIL | FAIL | PASS | PASS | FAIL |
| build | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| cartographer-skill | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| checkpoint | PASS | PASS | PASS | FAIL | PASS | FAIL |
| compass | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| consensus | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| debugging | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| delve | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| dependency-audit | PASS | PASS | PASS | PASS | PASS | PASS |
| design | PASS | FAIL | FAIL | FAIL | FAIL | FAIL |
| distill | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| finish | PASS | FAIL | FAIL | FAIL | FAIL | FAIL |
| forge | FAIL | FAIL | FAIL | FAIL | PASS | FAIL |
| getting-started | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| grudge | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| handoff | PASS | PASS | PASS | FAIL | FAIL | FAIL |
| innovate | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| inquisitor | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| merge-pr | PASS | PASS | PASS | FAIL | FAIL | FAIL |
| migrate | FAIL | FAIL | FAIL | PASS | PASS | FAIL |
| orchestrator | PASS | FAIL | FAIL | FAIL | FAIL | FAIL |
| parallel | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| planning | PASS | PASS | PASS | FAIL | PASS | FAIL |
| project-init | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| prospector | FAIL | FAIL | FAIL | PASS | PASS | FAIL |
| quality-gate | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| recall | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| recon | FAIL | FAIL | FAIL | FAIL | PASS | FAIL |
| red-team | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| replay | PASS | FAIL | FAIL | PASS | PASS | FAIL |
| review-feedback | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| siege | FAIL | FAIL | FAIL | PASS | FAIL | FAIL |
| source-driven-development | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| spec | FAIL | FAIL | FAIL | FAIL | PASS | FAIL |
| stocktake | PASS | FAIL | FAIL | FAIL | FAIL | FAIL |
| temper | FAIL | FAIL | FAIL | FAIL | PASS | FAIL |
| test-coverage | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| test-driven-development | PASS | PASS | PASS | FAIL | PASS | FAIL |
| verify | PASS | FAIL | FAIL | FAIL | PASS | FAIL |
| warden | FAIL | FAIL | FAIL | FAIL | PASS | FAIL |
| workshop | PASS | PASS | PASS | FAIL | PASS | FAIL |
| worktree | PASS | PASS | PASS | FAIL | PASS | FAIL |
| TOTAL | 33/46 | 9/46 | 13/46 | 7/46 | 34/46 | 1/46 |

## Violations (605)

- `adr` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `adversarial-tester` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `adversarial-tester` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `adversarial-tester` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `anvil` Body (1): 558 body lines (max 500)
- `anvil` Contents (4): skills/anvil/agents/analyzer.md: >100 lines, no contents list in first 20; skills/anvil/agents/comparator.md: >100 lines, no contents list in first 20; skills/anvil/agents/grader.md: >100 lines, no contents list in first 20; … and 1 more
- `anvil` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `assay` Contents (8): skills/assay/assay-evaluator-prompt.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 5 more
- `assay` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `audit` Body (1): 790 body lines (max 500)
- `audit` Contents (16): skills/audit/audit-architecture-prompt.md: >100 lines, no contents list in first 20; skills/audit/audit-blindspots-prompt.md: >100 lines, no contents list in first 20; skills/audit/audit-consistency-prompt.md: >100 lines, no contents list in first 20; … and 13 more
- `audit` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/return-convention.md not linked directly; … and 3 more
- `build` Body (1): 1426 body lines (max 500)
- `build` Contents (19): skills/build/build-implementer-prompt.md: >100 lines, no contents list in first 20; skills/build/build-reviewer-prompt.md: >100 lines, no contents list in first 20; skills/build/contract-test-writer-prompt.md: >100 lines, no contents list in first 20; … and 16 more
- `build` Nesting (7): skills/build/build-implementer-prompt.md -> skills/shared/fetched-content-containment.md not linked directly; skills/build/build-implementer-prompt.md -> skills/source-driven-development/detect-stack.md not linked directly; skills/red-team/red-team-prompt.md -> skills/shared/harness-adapter.md not linked directly; … and 4 more
- `build` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `build` Scripts (4): SKILL.md:14: script step lacks nearby dependency/setup note (heuristic); SKILL.md:341: script step lacks nearby dependency/setup note (heuristic); SKILL.md:594: script step lacks nearby dependency/setup note (heuristic); … and 1 more
- `cartographer-skill` Contents (8): skills/cartographer-skill/recorder-prompt.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 5 more
- `cartographer-skill` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `cartographer-skill` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `checkpoint` Frontmatter (1): description lacks when-to-use signal
- `compass` Contents (1): skills/shared/compass-protocol.md: >100 lines, no contents list in first 20
- `compass` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `compass` Scripts (1): SKILL.md:57: script step lacks nearby dependency/setup note (heuristic)
- `consensus` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `consensus` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `consensus` Frontmatter (1): description lacks when-to-use signal
- `debugging` Body (1): 1285 body lines (max 500)
- `debugging` Contents (15): skills/debugging/condition-based-waiting.md: >100 lines, no contents list in first 20; skills/debugging/defense-in-depth.md: >100 lines, no contents list in first 20; skills/debugging/implementer-prompt.md: >100 lines, no contents list in first 20; … and 12 more
- `debugging` Nesting (4): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/session-index-convention.md not linked directly; … and 1 more
- `debugging` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `debugging` Scripts (2): SKILL.md:348: script step lacks nearby dependency/setup note (heuristic); SKILL.md:974: script step lacks nearby dependency/setup note (heuristic)
- `delve` Contents (11): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 8 more
- `delve` Nesting (10): skills/shared/delve-engine.md -> skills/shared/reviewer-common.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 7 more
- `delve` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `design` Contents (11): skills/design/investigation-prompts.md: >100 lines, no contents list in first 20; skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; … and 8 more
- `design` Nesting (7): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 4 more
- `design` Frontmatter (2): description should be third-person, not imperative/first/second-person; description lacks when-to-use signal
- `design` Scripts (1): SKILL.md:39: script step lacks nearby dependency/setup note (heuristic)
- `distill` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `distill` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `distill` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `finish` Contents (9): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/compass-protocol.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 6 more
- `finish` Nesting (7): skills/shared/change-sizing.md -> skills/shared/severity-verdict-contract.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; … and 4 more
- `finish` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `finish` Scripts (5): SKILL.md:160: script step lacks nearby dependency/setup note (heuristic); SKILL.md:197: script step lacks nearby dependency/setup note (heuristic); SKILL.md:204: script step lacks nearby dependency/setup note (heuristic); … and 2 more
- `forge` Body (1): 605 body lines (max 500)
- `forge` Contents (11): skills/forge/extraction-analyst-prompt.md: >100 lines, no contents list in first 20; skills/forge/feed-forward-prompt.md: >100 lines, no contents list in first 20; skills/forge/mutation-proposal-prompt.md: >100 lines, no contents list in first 20; … and 8 more
- `forge` Nesting (6): skills/shared/cairn-convention.md -> skills/shared/return-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `forge` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `getting-started` Contents (2): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/compass-protocol.md: >100 lines, no contents list in first 20
- `getting-started` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `getting-started` Scripts (2): SKILL.md:15: script step lacks nearby dependency/setup note (heuristic); SKILL.md:26: script step lacks nearby dependency/setup note (heuristic)
- `grudge` Contents (2): skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `grudge` Nesting (1): skills/shared/ledger-append.md -> skills/shared/model-tier-policy.md not linked directly
- `grudge` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `handoff` Frontmatter (2): description should be third-person, not imperative/first/second-person; description lacks when-to-use signal
- `handoff` Scripts (1): SKILL.md:93: script step lacks nearby dependency/setup note (heuristic)
- `innovate` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `innovate` Nesting (6): skills/shared/cairn-convention.md -> skills/shared/return-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `innovate` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `inquisitor` Contents (10): skills/inquisitor/inquisitor-prompt.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 7 more
- `inquisitor` Nesting (7): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 4 more
- `inquisitor` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `merge-pr` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `merge-pr` Scripts (3): SKILL.md:224: script step lacks nearby dependency/setup note (heuristic); SKILL.md:229: script step lacks nearby dependency/setup note (heuristic); SKILL.md:279: script step lacks nearby dependency/setup note (heuristic)
- `migrate` Body (1): 549 body lines (max 500)
- `migrate` Contents (9): skills/migrate/blast-radius-mapper-prompt.md: >100 lines, no contents list in first 20; skills/migrate/phase-planner-prompt.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; … and 6 more
- `migrate` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `orchestrator` Contents (4): skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20; … and 1 more
- `orchestrator` Nesting (2): skills/shared/return-convention.md -> skills/shared/dispatch-convention.md not linked directly; skills/shared/return-convention.md -> skills/shared/model-tier-policy.md not linked directly
- `orchestrator` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `orchestrator` Scripts (17): SKILL.md:50: script step lacks nearby dependency/setup note (heuristic); SKILL.md:51: script step lacks nearby dependency/setup note (heuristic); SKILL.md:52: script step lacks nearby dependency/setup note (heuristic); … and 14 more
- `parallel` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `parallel` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `parallel` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `planning` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `project-init` Contents (10): skills/project-init/init-recorder-prompt.md: >100 lines, no contents list in first 20; skills/project-init/partition-explorer-prompt.md: >100 lines, no contents list in first 20; skills/project-init/topology-recorder-prompt.md: >100 lines, no contents list in first 20; … and 7 more
- `project-init` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/return-convention.md not linked directly; … and 3 more
- `project-init` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `prospector` Body (1): 726 body lines (max 500)
- `prospector` Contents (13): skills/prospector/REFERENCE.md: >100 lines, no contents list in first 20; skills/prospector/analysis-prompt.md: >100 lines, no contents list in first 20; skills/prospector/design-competitor-prompt.md: >100 lines, no contents list in first 20; … and 10 more
- `prospector` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/return-convention.md not linked directly; … and 3 more
- `quality-gate` Body (1): 1847 body lines (max 500)
- `quality-gate` Contents (15): skills/quality-gate/fix-generated-defect-prompt.md: >100 lines, no contents list in first 20; skills/quality-gate/persistence-checker-prompt.md: >100 lines, no contents list in first 20; skills/quality-gate/stagnation-judge-prompt.md: >100 lines, no contents list in first 20; … and 12 more
- `quality-gate` Nesting (6): skills/quality-gate/fix-verifier-prompt.md -> skills/shared/severity-rubric.md not linked directly; skills/quality-gate/stagnation-judge-prompt.md -> skills/shared/severity-rubric.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/scope-judge-prompt.md not linked directly; … and 3 more
- `quality-gate` Frontmatter (1): description lacks when-to-use signal
- `quality-gate` Scripts (2): SKILL.md:30: script step lacks nearby dependency/setup note (heuristic); SKILL.md:900: script step lacks nearby dependency/setup note (heuristic)
- `recall` Contents (1): skills/shared/session-index-convention.md: >100 lines, no contents list in first 20
- `recall` Frontmatter (1): description lacks when-to-use signal
- `recon` Body (1): 893 body lines (max 500)
- `recon` Contents (16): skills/cartographer-skill/recorder-prompt.md: >100 lines, no contents list in first 20; skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/recon/consumer-mapper-prompt.md: >100 lines, no contents list in first 20; … and 13 more
- `recon` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/return-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/scope-judge-prompt.md not linked directly; … and 3 more
- `recon` Frontmatter (2): description should be third-person, not imperative/first/second-person; description lacks when-to-use signal
- `red-team` Contents (12): skills/red-team/red-team-prompt.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/delve-engine.md: >100 lines, no contents list in first 20; … and 9 more
- `red-team` Nesting (5): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/scope-judge-prompt.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/session-index-convention.md not linked directly; … and 2 more
- `red-team` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `replay` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `replay` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `review-feedback` Contents (2): skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `review-feedback` Nesting (1): skills/shared/ledger-append.md -> skills/shared/model-tier-policy.md not linked directly
- `review-feedback` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `siege` Body (1): 1035 body lines (max 500)
- `siege` Contents (18): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 15 more
- `siege` Nesting (5): skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/scope-judge-prompt.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/session-index-convention.md not linked directly; … and 2 more
- `siege` Scripts (2): SKILL.md:21: script step lacks nearby dependency/setup note (heuristic); SKILL.md:317: script step lacks nearby dependency/setup note (heuristic)
- `source-driven-development` Contents (3): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20; skills/shared/security-signals.md: >100 lines, no contents list in first 20
- `source-driven-development` Nesting (2): skills/shared/fetched-content-containment.md -> skills/getting-started/trust-hierarchy.md not linked directly; skills/shared/fetched-content-containment.md -> skills/shared/security-signals.md not linked directly
- `source-driven-development` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `spec` Body (1): 631 body lines (max 500)
- `spec` Contents (9): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 6 more
- `spec` Nesting (7): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 4 more
- `spec` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `stocktake` Contents (7): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 4 more
- `stocktake` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/return-convention.md not linked directly; … and 3 more
- `stocktake` Frontmatter (1): description lacks when-to-use signal
- `stocktake` Scripts (5): SKILL.md:54: script step lacks nearby dependency/setup note (heuristic); SKILL.md:55: script step lacks nearby dependency/setup note (heuristic); SKILL.md:56: script step lacks nearby dependency/setup note (heuristic); … and 2 more
- `temper` Body (1): 514 body lines (max 500)
- `temper` Contents (13): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 10 more
- `temper` Nesting (10): skills/shared/delve-engine.md -> skills/shared/reviewer-common.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 7 more
- `temper` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `test-coverage` Contents (10): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/harness-adapter.md: >100 lines, no contents list in first 20; … and 7 more
- `test-coverage` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/return-convention.md not linked directly; … and 3 more
- `test-coverage` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `test-driven-development` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `verify` Contents (2): skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `verify` Nesting (1): skills/shared/ledger-append.md -> skills/shared/model-tier-policy.md not linked directly
- `verify` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `warden` Body (1): 942 body lines (max 500)
- `warden` Contents (8): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; … and 5 more
- `warden` Nesting (6): skills/shared/dispatch-convention.md -> skills/shared/cairn-convention.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/harness-adapter.md not linked directly; skills/shared/dispatch-convention.md -> skills/shared/model-tier-policy.md not linked directly; … and 3 more
- `warden` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `workshop` Frontmatter (1): description should be third-person, not imperative/first/second-person
- `worktree` Frontmatter (1): description should be third-person, not imperative/first/second-person
