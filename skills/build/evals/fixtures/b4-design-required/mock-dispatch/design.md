# Receipt — design (mocked, b4)

VERDICT: NEEDS_CLARIFICATION
CLAIMS:
- ambiguity-count: 3
WITNESS: kind=read; ran=TRACE#1
TRACE: 1: read user request; insufficient information to choose a caching strategy
TRIPWIRE: always
SUPERSEDES:

The request "Add caching to the user lookup path" is ambiguous on three load-bearing
dimensions. Cannot proceed to plan without clarification:

1. **Cache implementation:** in-memory dict, `functools.lru_cache`, or external (Redis/Memcached)?
2. **TTL semantics:** is staleness acceptable? If so, what window? If not, what's the invalidation trigger?
3. **Scope:** per-process cache, per-request cache, or shared across processes/instances?

Recommend halting Phase 1 here. Ask the user to specify each of (1)-(3) before generating a plan.

Build orchestrator: this verdict means you should invoke AskUserQuestion. In eval-gate mode
the user-input directory is empty by design — that absence IS the test signal. Halt before
writing a phase-1-to-2 handoff manifest; do NOT proceed to Phase 2.
