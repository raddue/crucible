<!-- DISPATCH: disk-mediated | Staged once by run_evals.py and shared BYTE-IDENTICALLY
     by the WITH 6th aggregation subagent and the MID single agent (#424). Its
     byte-identity across both arms is the load-bearing confound control (design T3):
     do not fork per-arm copies. -->

# Inquisitor Aggregation Prompt

You are given a set of cross-component bug findings produced across the five
inquisitor dimensions — Wiring, Integration, Edge Cases, State & Lifecycle, and
Regression. Your job is to synthesize them into ONE consolidated report.

1. **Merge** the findings into a single deduplicated list of distinct
   cross-component issues. Collapse near-duplicate facets of the same underlying
   bug into one entry (e.g. two findings that are different faces of "this code
   assumes integer ids" are one issue).

2. For each distinct issue, state:
   - **Issue:** what breaks at runtime, and which components interact to cause it.
   - **Dimension(s):** which lens(es) surfaced it.
   - **Fix or test:** a specific proposed fix, or the test that would expose it.

3. Do NOT invent issues that none of the dimension findings support. Do NOT drop a
   real finding just to shorten the list. Do NOT execute any code — no runner is
   available in this eval context.

Report the consolidated issue list and nothing else.
