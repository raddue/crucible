# Fixture: structural-only tie-break suppresses dual-scout override

## STRUCTURE SCOUT REPORT

### Project Structure
- The missing `Config/feature-flags.yaml` causes the fallback path to activate in `src/router.ts`. [evidence: structural-only:Config/feature-flags.yaml] [confidence: medium]

## PATTERN SCOUT REPORT

### Existing Patterns
- The missing feature-flags config causes the fallback path to activate in `src/router.ts`. [evidence: grep:src/router.ts:L88] [confidence: medium]
