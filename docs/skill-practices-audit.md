# Skill practices audit

Warn-only snapshot for #719; violations do not fail CI. Refresh with `python3 scripts/check_skill_best_practices.py --write-report`; the default check-only run never updates this file. Scripts column is a best-effort dependency-note heuristic. Later `--enforce` can compare per-skill failures against a ratchet baseline; no baseline or enforcement exists yet.

| Skill | Body | Contents | Nesting | Frontmatter | Scripts | Overall |
| --- | --- | --- | --- | --- | --- | --- |
| anvil | PASS | PASS | PASS | PASS | PASS | PASS |
| audit | FAIL | FAIL | PASS | PASS | PASS | FAIL |
| build | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| checkpoint | PASS | PASS | PASS | FAIL | PASS | FAIL |
| debugging | FAIL | PASS | PASS | PASS | FAIL | FAIL |
| delve | PASS | FAIL | PASS | PASS | PASS | FAIL |
| design | PASS | FAIL | PASS | FAIL | FAIL | FAIL |
| distill | PASS | PASS | PASS | PASS | PASS | PASS |
| finish | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| getting-started | PASS | PASS | PASS | PASS | PASS | PASS |
| inquisitor | PASS | FAIL | PASS | PASS | PASS | FAIL |
| parallel | PASS | PASS | PASS | PASS | PASS | PASS |
| planning | PASS | PASS | PASS | FAIL | PASS | FAIL |
| quality-gate | PASS | PASS | PASS | PASS | PASS | PASS |
| recon | PASS | FAIL | FAIL | PASS | PASS | FAIL |
| replay | PASS | PASS | PASS | PASS | PASS | PASS |
| siege | FAIL | FAIL | PASS | PASS | FAIL | FAIL |
| source-driven-development | PASS | FAIL | PASS | PASS | PASS | FAIL |
| spec | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| temper | PASS | FAIL | PASS | PASS | PASS | FAIL |
| test-driven-development | PASS | PASS | PASS | PASS | PASS | PASS |
| verify | PASS | FAIL | PASS | PASS | PASS | FAIL |
| warden | FAIL | FAIL | PASS | FAIL | PASS | FAIL |
| worktree | PASS | PASS | PASS | PASS | PASS | PASS |
| TOTAL | 19/24 | 11/24 | 23/24 | 19/24 | 19/24 | 8/24 |

## Violations (52)

- `audit` Body (1): 790 body lines (max 500)
- `audit` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `build` Contents (1): skills/spec/contract-schema.md: >100 lines, no contents list in first 20
- `build` Scripts (1): SKILL.md:14: script step lacks nearby dependency/setup note (heuristic)
- `checkpoint` Frontmatter (1): description lacks when-to-use signal
- `debugging` Body (1): 1453 body lines (max 500)
- `debugging` Scripts (2): SKILL.md:516: script step lacks nearby dependency/setup note (heuristic); SKILL.md:1142: script step lacks nearby dependency/setup note (heuristic)
- `delve` Contents (3): skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/severity-verdict-contract.md: >100 lines, no contents list in first 20
- `design` Contents (3): skills/design/approach-evaluation.md: >100 lines, no contents list in first 20; skills/design/decision-records.md: >100 lines, no contents list in first 20; skills/design/innovation.md: >100 lines, no contents list in first 20
- `design` Frontmatter (1): description should use third-person, not first/second-person voice
- `design` Scripts (1): SKILL.md:40: script step lacks nearby dependency/setup note (heuristic)
- `finish` Contents (1): CLAUDE.md: >100 lines, no contents list in first 20
- `finish` Scripts (6): SKILL.md:166: script step lacks nearby dependency/setup note (heuristic); SKILL.md:174: script step lacks nearby dependency/setup note (heuristic); SKILL.md:205: script step lacks nearby dependency/setup note (heuristic); … and 3 more
- `inquisitor` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `planning` Frontmatter (1): description should use third-person, not first/second-person voice
- `recon` Contents (9): skills/recon/cartographer/recorder-prompt.md: >100 lines, no contents list in first 20; skills/recon/improvement-discovery.md:7: unresolved #phase-0-5-framework-detection; skills/recon/persistent-map.md:12: unresolved #defect-signatures; … and 6 more
- `recon` Nesting (1): skills/recon/improvement-discovery.md -> skills/recon/prospector/REFERENCE.md not linked directly
- `siege` Body (1): 1035 body lines (max 500)
- `siege` Contents (3): skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/security-signals.md: >100 lines, no contents list in first 20
- `siege` Scripts (2): SKILL.md:21: script step lacks nearby dependency/setup note (heuristic); SKILL.md:317: script step lacks nearby dependency/setup note (heuristic)
- `source-driven-development` Contents (1): skills/shared/fetched-content-containment.md: >100 lines, no contents list in first 20
- `spec` Body (1): 631 body lines (max 500)
- `spec` Contents (1): skills/spec/contract-schema.md: >100 lines, no contents list in first 20
- `spec` Frontmatter (1): description should use third-person, not first/second-person voice
- `temper` Contents (3): skills/shared/delve-engine.md: >100 lines, no contents list in first 20; skills/shared/ledger-append.md: >100 lines, no contents list in first 20; skills/shared/severity-verdict-contract.md: >100 lines, no contents list in first 20
- `verify` Contents (1): skills/shared/ledger-append.md: >100 lines, no contents list in first 20
- `warden` Body (1): 956 body lines (max 500)
- `warden` Contents (1): skills/shared/change-bundling-convention.md: >100 lines, no contents list in first 20
- `warden` Frontmatter (1): description should use third-person, not first/second-person voice
