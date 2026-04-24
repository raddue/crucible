# Fixture: brief with 3 deduplicated causal claims

## STRUCTURE SCOUT REPORT

### Project Structure
- The missing Unity asset in `Resources/config.yaml` causes the silent default-branch fallback at `src/loader.cs:L42`. [evidence: grep:src/loader.cs:L42] [confidence: high]
- The build script fails because of the missing `scripts/pre-build.sh` [evidence: read:scripts/pre-build.sh] [demoted] [confidence: medium]

### Suggested Scope
#### In Scope
- `src/loader.cs`

## PATTERN SCOUT REPORT

### Existing Patterns
- The missing Unity asset at `Resources/config.yaml` is what causes the default-branch fallback behavior at `src/loader.cs`. [evidence: read:src/loader.cs:L40-L50] [confidence: high]
- Auth fails because the token expires — root cause is the 1h TTL in `config/auth.yaml`. [evidence: repro-test:tests/auth_spec.py:test_token_expires] [confidence: high]

### Prior Art
- Similar fallback pattern observed in `src/legacy_loader.cs`
