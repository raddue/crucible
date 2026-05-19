# Contributing to the Calibration Ledger

The Crucible calibration ledger (`.crucible/ledger/runs.jsonl`) is institutional
memory: every Tier A gate verdict appends one JSONL line capturing what was
gated, what was found, and (later) whether the verdict was falsified by a
subsequent fix. This file is **committed to git** and grows monotonically.

## The kill-switch — what it is, what it is NOT

`CRUCIBLE_CALIBRATION_DISABLED=1` causes Tier A emitters to **no-op return
before any filesystem state change** — no lock acquisition, no append.

### The kill-switch is a fixture-isolation guard

Use it ONLY when a gate run would emit **corrupt or non-representative data**.
Concrete cases:

- A skill running against a **test fixture** in `eval/<skill>/fixtures/`
  rather than a real Crucible artifact.
- A **CI smoke test** that should not pollute the production ledger.
- An **eval harness corpus** seeded for measurement, not real work.

### The kill-switch is NOT a bootstrap-wide silencer

Real Crucible runs against real artifacts during Phases 2–7 **SHOULD emit
normally**. That data is the entire point of the system — every silenced
forward-captured verdict is a permanent epistemic blind spot.

Do **not** set `CRUCIBLE_CALIBRATION_DISABLED=1` globally in a contributor's
shell profile. The kill-switch is scoped per-invocation or per-directory.

## `.envrc.example` — scope the switch to fixture dirs

If you use [direnv](https://direnv.net), the recommended pattern is one
`.envrc` per fixture directory:

```bash
# .envrc in eval/<skill>/fixtures/
export CRUCIBLE_CALIBRATION_DISABLED=1
```

When you `cd` into the fixture dir, direnv sets the env var; when you leave,
it unsets. Real-artifact work in the repo root remains uncorrupted by the
switch.

For non-direnv users, prefix the invocation:

```bash
CRUCIBLE_CALIBRATION_DISABLED=1 python eval/quality-gate/run-fixture.py
```

## Auditing kill-switch use

A grep against `CRUCIBLE_CALIBRATION_DISABLED` in the repository surfaces
every documented usage site. If a contributor adds a new fixture path that
should emit nothing, they MUST update this doc with the rationale.

## What gets committed, what does not

| Path                                                | Committed? |
|-----------------------------------------------------|------------|
| `.crucible/ledger/runs.jsonl`                       | yes        |
| `.crucible/ledger/falsification.jsonl`              | yes        |
| `.crucible/ledger/manual-attribution.jsonl`         | yes        |
| `.crucible/ledger/overflow/`                        | yes        |
| `.crucible/ledger/brier-rolling.json`               | **no** (gitignored) |
| `docs/ledger/weekly-*.md`                           | yes        |

The `brier-rolling.json` file is high-churn derived data; only the
underlying `runs.jsonl` + `falsification.jsonl` need to survive in git.

## Severity discipline

The ledger powers the inflation-detector that watches for severity drift over
4-week rolling windows. Use the severity rubric in
`skills/shared/severity-rubric.md` (when present) and resist the temptation to
inflate Minor → Significant. The headline "caught N silent bugs" only counts
entries where `(severity_histogram.fatal + severity_histogram.significant) >= 1`,
and that headline is auditable per-entry via the `highest_finding` quote.
