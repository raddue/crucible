# 2026-04-22 Handoff — auth investigation

## Findings

- Recon claim falsified: L-02 from brief 2026-04-20T12-00-00 — `Auth fails because the token expires — root cause is the 1h TTL in config/auth.yaml.` — evidence: repro test showed token TTL is 24h, actual failure was clock-skew in the validator.

Other prose here.
