# Skill practices audit

Warn-only snapshot for #719; violations do not fail CI. Refresh with `python3 scripts/check_skill_best_practices.py --write-report`; the default check-only run never updates this file. Scripts column is a best-effort dependency-note heuristic. Later `--enforce` can compare per-skill failures against a ratchet baseline; no baseline or enforcement exists yet.

| Skill | Body | Contents | Nesting | Frontmatter | Scripts | Overall |
| --- | --- | --- | --- | --- | --- | --- |
| anvil | FAIL | PASS | PASS | PASS | PASS | FAIL |
| audit | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| build | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| cartographer-skill | PASS | PASS | PASS | FAIL | PASS | FAIL |
| checkpoint | PASS | PASS | PASS | FAIL | PASS | FAIL |
| consensus | PASS | PASS | PASS | FAIL | PASS | FAIL |
| debugging | FAIL | PASS | PASS | PASS | FAIL | FAIL |
| delve | PASS | FAIL | PASS | PASS | PASS | FAIL |
| dependency-audit | PASS | PASS | PASS | PASS | PASS | PASS |
| design | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| distill | PASS | PASS | PASS | PASS | PASS | PASS |
| finish | PASS | PASS | PASS | FAIL | FAIL | FAIL |
| getting-started | PASS | PASS | PASS | PASS | PASS | PASS |
| grudge | PASS | PASS | PASS | PASS | PASS | PASS |
| inquisitor | PASS | FAIL | PASS | PASS | PASS | FAIL |
| merge-pr | PASS | PASS | PASS | PASS | FAIL | FAIL |
| migrate | FAIL | PASS | PASS | PASS | PASS | FAIL |
| orchestrator | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| parallel | PASS | PASS | PASS | PASS | PASS | PASS |
| planning | PASS | PASS | PASS | FAIL | PASS | FAIL |
| project-init | PASS | PASS | PASS | FAIL | PASS | FAIL |
| prospector | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| quality-gate | FAIL | FAIL | PASS | FAIL | FAIL | FAIL |
| recon | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| red-team | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| replay | PASS | PASS | PASS | PASS | PASS | PASS |
| review-feedback | PASS | FAIL | PASS | PASS | PASS | FAIL |
| siege | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| source-driven-development | PASS | FAIL | PASS | PASS | PASS | FAIL |
| spec | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| stocktake | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| temper | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| test-coverage | PASS | FAIL | PASS | PASS | PASS | FAIL |
| test-driven-development | PASS | PASS | PASS | PASS | PASS | PASS |
| verify | PASS | FAIL | PASS | PASS | PASS | FAIL |
| warden | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| worktree | PASS | PASS | PASS | PASS | PASS | PASS |
| TOTAL | 25/37 | 18/37 | 37/37 | 25/37 | 28/37 | 8/37 |

## Violations (99)

- `anvil` Body (1): 558 body lines (max 500)
- `audit` Body (1): 790 body lines (max 500)
- `audit` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `build` Body (1): 1426 body lines (max 500)
- `build` Contents (2): skills/shared/return-convention.md: >100 lines, no contents list in first 20; skills/spec/contract-schema.md: >100 lines, no contents list in first 20
- `build` Scripts (4): SKILL.md:14: script step lacks nearby dependency/setup note (heuristic); SKILL.md:341: script step lacks nearby dependency/setup note (heuristic); SKILL.md:594: script step lacks nearby dependency/setup note (heuristic); … and 1 more
- `cartographer-skill` Frontmatter (1): description should use third-person, not first/second-person voice
- `checkpoint` Frontmatter (1): description lacks when-to-use signal
- `consensus` Frontmatter (1): description lacks when-to-use signal
- `debugging` Body (1): 1285 body lines (max 500)
- `debugging` Scripts (2): SKILL.md:348: script step lacks nearby dependency/setup note (heuristic); SKILL.md:974: script step lacks nearby dependency/setup note (heuristic)
- `delve` Contents (3): skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/severity-verdict-contract.md: >100 lines, no contents list in first 20
- `design` Contents (3): skills/design/approach-evaluation.md: >100 lines, no contents list in first 20; skills/design/decision-records.md: >100 lines, no contents list in first 20; skills/design/innovation.md: >100 lines, no contents list in first 20
- `design` Frontmatter (1): description should use third-person, not first/second-person voice
- `design` Scripts (1): SKILL.md:40: script step lacks nearby dependency/setup note (heuristic)
- `finish` Frontmatter (1): description should use third-person, not first/second-person voice
- `finish` Scripts (5): SKILL.md:160: script step lacks nearby dependency/setup note (heuristic); SKILL.md:197: script step lacks nearby dependency/setup note (heuristic); SKILL.md:204: script step lacks nearby dependency/setup note (heuristic); … and 2 more
- `inquisitor` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `merge-pr` Scripts (3): SKILL.md:224: script step lacks nearby dependency/setup note (heuristic); SKILL.md:229: script step lacks nearby dependency/setup note (heuristic); SKILL.md:279: script step lacks nearby dependency/setup note (heuristic)
- `migrate` Body (1): 549 body lines (max 500)
- `orchestrator` Contents (2): skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `orchestrator` Scripts (17): SKILL.md:50: script step lacks nearby dependency/setup note (heuristic); SKILL.md:51: script step lacks nearby dependency/setup note (heuristic); SKILL.md:52: script step lacks nearby dependency/setup note (heuristic); … and 14 more
- `planning` Frontmatter (1): description should use third-person, not first/second-person voice
- `project-init` Frontmatter (1): description should use third-person, not first/second-person voice
- `prospector` Body (1): 726 body lines (max 500)
- `prospector` Contents (1): skills/prospector/REFERENCE.md: >100 lines, no contents list in first 20
- `quality-gate` Body (1): 1847 body lines (max 500)
- `quality-gate` Contents (3): skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `quality-gate` Frontmatter (1): description lacks when-to-use signal
- `quality-gate` Scripts (2): SKILL.md:30: script step lacks nearby dependency/setup note (heuristic); SKILL.md:900: script step lacks nearby dependency/setup note (heuristic)
- `recon` Body (1): 893 body lines (max 500)
- `recon` Contents (1): skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `red-team` Contents (2): skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `red-team` Frontmatter (1): description should use third-person, not first/second-person voice
- `review-feedback` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `siege` Body (1): 1035 body lines (max 500)
- `siege` Contents (4): skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20; … and 1 more
- `siege` Scripts (2): SKILL.md:21: script step lacks nearby dependency/setup note (heuristic); SKILL.md:317: script step lacks nearby dependency/setup note (heuristic)
- `source-driven-development` Contents (1): skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20
- `spec` Body (1): 631 body lines (max 500)
- `spec` Contents (1): skills/spec/contract-schema.md: >100 lines, no contents list in first 20
- `spec` Frontmatter (1): description should use third-person, not first/second-person voice
- `stocktake` Contents (1): skills/shared/model-tier-policy.md: >100 lines, no contents list in first 20
- `stocktake` Frontmatter (1): description lacks when-to-use signal
- `stocktake` Scripts (5): SKILL.md:54: script step lacks nearby dependency/setup note (heuristic); SKILL.md:55: script step lacks nearby dependency/setup note (heuristic); SKILL.md:56: script step lacks nearby dependency/setup note (heuristic); … and 2 more
- `temper` Body (1): 514 body lines (max 500)
- `temper` Contents (3): skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/severity-verdict-contract.md: >100 lines, no contents list in first 20
- `test-coverage` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `verify` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `warden` Body (1): 942 body lines (max 500)
- `warden` Contents (2): skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20; skills/shared/return-convention.md: >100 lines, no contents list in first 20
- `warden` Frontmatter (1): description should use third-person, not first/second-person voice
