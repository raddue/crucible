# Fixture: re-run idempotence — same input twice produces byte-identical output

## STRUCTURE SCOUT REPORT

### Project Structure
- The missing config file causes the silent fallback at `src/loader.ts:L10`. [evidence: grep:src/loader.ts:L10] [confidence: high]

## PATTERN SCOUT REPORT

### Existing Patterns
- Auth fails because the token expires — root cause is the 1h TTL in `config/auth.yaml`. [evidence: repro-test:tests/auth_spec.py:test_token_expires] [confidence: high]
