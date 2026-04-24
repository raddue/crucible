## Verification Ledger
<!-- Records causal claims made by this brief (populated this run). Falsifications flow via handoff-doc entries under docs/handoffs/ per the convention in skills/recon/SKILL.md. -->

- **L-01** — The missing Unity asset in `Resources/config.yaml` causes the silent default-branch fallback at `src/loader.cs:L42`. — method: `dual-scout`, evidence: `structure-scout, pattern-scout`, disposition: `confirmed`
- **L-02** — The build script fails because of the missing `scripts/pre-build.sh` — method: `read`, evidence: `scripts/pre-build.sh`, disposition: `demoted`
- **L-03** — Auth fails because the token expires — root cause is the 1h TTL in `config/auth.yaml`. — method: `repro-test`, evidence: `tests/auth_spec.py:test_token_expires`, disposition: `confirmed`
