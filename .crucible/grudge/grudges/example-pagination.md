---
schema: 1
hash: fixtureexmpl
repo: example-repo
repo_root: /example/example-repo
fixed_in_commit: 0000000
symptom: off-by-one in pagination dropped the last page of results
root_cause: the page-count loop used < instead of <= on the boundary
files_touched: ["src/pagination.py"]
anti_pattern_signature: "range\\(1, page_count\\)"
date_fixed: 2026-01-01
---
## Repro
Request the final page of a multi-page result set; observe the last item missing.

## Why this kept happening
The pagination boundary is written in three places and only one was corrected on
each prior attempt; the other two kept regressing the identical off-by-one.

NOTE: this is a SYNTHETIC fixture (repo_root is a placeholder, so it never
surfaces as a real grudge). It exists for eval/grudge tests and as a worked
example of the on-disk schema. Do NOT put real paths or secrets here.
