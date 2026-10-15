# Skill practices audit

Warn-only snapshot for #719; violations do not fail CI. Refresh with `python3 scripts/check_skill_best_practices.py --write-report`; the default check-only run never updates this file. Scripts column is a best-effort dependency-note heuristic. Later `--enforce` can compare per-skill failures against a ratchet baseline; no baseline or enforcement exists yet.

| Skill | Body | Contents | Nesting | Frontmatter | Scripts | Overall |
| --- | --- | --- | --- | --- | --- | --- |
| adr | PASS | PASS | PASS | FAIL | PASS | FAIL |
| adversarial-tester | PASS | FAIL | PASS | PASS | PASS | FAIL |
| anvil | FAIL | PASS | PASS | PASS | PASS | FAIL |
| assay | PASS | FAIL | PASS | PASS | PASS | FAIL |
| audit | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| build | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| cartographer-skill | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| checkpoint | PASS | PASS | PASS | FAIL | PASS | FAIL |
| compass | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| consensus | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| debugging | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| delve | PASS | FAIL | PASS | PASS | PASS | FAIL |
| dependency-audit | PASS | PASS | PASS | PASS | PASS | PASS |
| design | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| distill | PASS | FAIL | PASS | PASS | PASS | FAIL |
| finish | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| forge | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| getting-started | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| grudge | PASS | PASS | PASS | PASS | PASS | PASS |
| handoff | PASS | PASS | PASS | FAIL | FAIL | FAIL |
| innovate | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| inquisitor | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| merge-pr | PASS | PASS | PASS | PASS | FAIL | FAIL |
| migrate | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| orchestrator | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| parallel | PASS | FAIL | PASS | PASS | PASS | FAIL |
| planning | PASS | PASS | PASS | FAIL | PASS | FAIL |
| project-init | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| prospector | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| quality-gate | FAIL | FAIL | PASS | FAIL | FAIL | FAIL |
| recall | PASS | PASS | PASS | FAIL | PASS | FAIL |
| recon | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| red-team | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| replay | PASS | FAIL | PASS | PASS | PASS | FAIL |
| review-feedback | PASS | FAIL | PASS | PASS | PASS | FAIL |
| siege | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| source-driven-development | PASS | FAIL | PASS | PASS | PASS | FAIL |
| spec | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| stocktake | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| temper | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| test-coverage | PASS | FAIL | PASS | PASS | PASS | FAIL |
| test-driven-development | PASS | PASS | PASS | PASS | PASS | PASS |
| verify | PASS | FAIL | PASS | PASS | PASS | FAIL |
| warden | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| workshop | PASS | PASS | PASS | FAIL | PASS | FAIL |
| worktree | PASS | PASS | PASS | PASS | PASS | PASS |
| TOTAL | 33/46 | 12/46 | 46/46 | 23/46 | 34/46 | 4/46 |

## Violations (154)

- `adr` Frontmatter (1): description should use third-person, not first/second-person voice
- `adversarial-tester` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `anvil` Body (1): 558 body lines (max 500)
- `assay` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `audit` Body (1): 790 body lines (max 500)
- `audit` Contents (2): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `build` Body (1): 1426 body lines (max 500)
- `build` Contents (6): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/compass-protocol.md: >100 lines, no contents list in first 20; … and 3 more
- `build` Scripts (4): SKILL.md:14: script step lacks nearby dependency/setup note (heuristic); SKILL.md:341: script step lacks nearby dependency/setup note (heuristic); SKILL.md:594: script step lacks nearby dependency/setup note (heuristic); … and 1 more
- `cartographer-skill` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `cartographer-skill` Frontmatter (1): description should use third-person, not first/second-person voice
- `checkpoint` Frontmatter (1): description lacks when-to-use signal
- `compass` Contents (1): skills/shared/compass-protocol.md: >100 lines, no contents list in first 20
- `compass` Frontmatter (1): description should use third-person, not first/second-person voice
- `compass` Scripts (1): SKILL.md:57: script step lacks nearby dependency/setup note (heuristic)
- `consensus` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `consensus` Frontmatter (1): description lacks when-to-use signal
- `debugging` Body (1): 1285 body lines (max 500)
- `debugging` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `debugging` Scripts (2): SKILL.md:348: script step lacks nearby dependency/setup note (heuristic); SKILL.md:974: script step lacks nearby dependency/setup note (heuristic)
- `delve` Contents (4): skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; … and 1 more
- `design` Contents (2): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `design` Frontmatter (2): description should use third-person, not first/second-person voice; description lacks when-to-use signal
- `design` Scripts (1): SKILL.md:39: script step lacks nearby dependency/setup note (heuristic)
- `distill` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `finish` Contents (2): skills/shared/compass-protocol.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `finish` Frontmatter (1): description should use third-person, not first/second-person voice
- `finish` Scripts (5): SKILL.md:160: script step lacks nearby dependency/setup note (heuristic); SKILL.md:197: script step lacks nearby dependency/setup note (heuristic); SKILL.md:204: script step lacks nearby dependency/setup note (heuristic); … and 2 more
- `forge` Body (1): 605 body lines (max 500)
- `forge` Contents (2): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `forge` Frontmatter (1): description should use third-person, not first/second-person voice
- `getting-started` Contents (2): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/compass-protocol.md: >100 lines, no contents list in first 20
- `getting-started` Scripts (2): SKILL.md:15: script step lacks nearby dependency/setup note (heuristic); SKILL.md:26: script step lacks nearby dependency/setup note (heuristic)
- `handoff` Frontmatter (1): description lacks when-to-use signal
- `handoff` Scripts (1): SKILL.md:93: script step lacks nearby dependency/setup note (heuristic)
- `innovate` Contents (2): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `innovate` Frontmatter (1): description should use third-person, not first/second-person voice
- `inquisitor` Contents (2): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `inquisitor` Frontmatter (1): description should use third-person, not first/second-person voice
- `merge-pr` Scripts (3): SKILL.md:224: script step lacks nearby dependency/setup note (heuristic); SKILL.md:229: script step lacks nearby dependency/setup note (heuristic); SKILL.md:279: script step lacks nearby dependency/setup note (heuristic)
- `migrate` Body (1): 549 body lines (max 500)
- `migrate` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `orchestrator` Contents (2): skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `orchestrator` Scripts (17): SKILL.md:50: script step lacks nearby dependency/setup note (heuristic); SKILL.md:51: script step lacks nearby dependency/setup note (heuristic); SKILL.md:52: script step lacks nearby dependency/setup note (heuristic); … and 14 more
- `parallel` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `planning` Frontmatter (1): description should use third-person, not first/second-person voice
- `project-init` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `project-init` Frontmatter (1): description should use third-person, not first/second-person voice
- `prospector` Body (1): 726 body lines (max 500)
- `prospector` Contents (2): skills/prospector/REFERENCE.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `prospector` Frontmatter (1): description should use third-person, not first/second-person voice
- `quality-gate` Body (1): 1847 body lines (max 500)
- `quality-gate` Contents (5): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; … and 2 more
- `quality-gate` Frontmatter (1): description lacks when-to-use signal
- `quality-gate` Scripts (2): SKILL.md:30: script step lacks nearby dependency/setup note (heuristic); SKILL.md:900: script step lacks nearby dependency/setup note (heuristic)
- `recall` Frontmatter (1): description lacks when-to-use signal
- `recon` Body (1): 893 body lines (max 500)
- `recon` Contents (3): skills/getting-started/trust-hierarchy.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `recon` Frontmatter (1): description lacks when-to-use signal
- `red-team` Contents (3): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `red-team` Frontmatter (1): description should use third-person, not first/second-person voice
- `replay` Contents (1): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20
- `review-feedback` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `siege` Body (1): 1035 body lines (max 500)
- `siege` Contents (6): skills/shared/cairn-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20; … and 3 more
- `siege` Scripts (2): SKILL.md:21: script step lacks nearby dependency/setup note (heuristic); SKILL.md:317: script step lacks nearby dependency/setup note (heuristic)
- `source-driven-development` Contents (1): skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20
- `spec` Body (1): 631 body lines (max 500)
- `spec` Contents (2): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/spec/contract-schema.md: >100 lines, no contents list in first 20
- `spec` Frontmatter (1): description should use third-person, not first/second-person voice
- `stocktake` Contents (2): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `stocktake` Frontmatter (1): description lacks when-to-use signal
- `stocktake` Scripts (5): SKILL.md:54: script step lacks nearby dependency/setup note (heuristic); SKILL.md:55: script step lacks nearby dependency/setup note (heuristic); SKILL.md:56: script step lacks nearby dependency/setup note (heuristic); … and 2 more
- `temper` Body (1): 514 body lines (max 500)
- `temper` Contents (4): skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; … and 1 more
- `temper` Frontmatter (1): description should use third-person, not first/second-person voice
- `test-coverage` Contents (2): skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `verify` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `warden` Body (1): 942 body lines (max 500)
- `warden` Contents (3): skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20; skills/shared/dispatch-convention.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `warden` Frontmatter (1): description should use third-person, not first/second-person voice
- `workshop` Frontmatter (1): description should use third-person, not first/second-person voice
