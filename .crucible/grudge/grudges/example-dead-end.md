---
schema: 1
hash: deadendxampl
repo: example-repo
repo_root: /example/example-repo
kind: "dead_end"
approach: JSON-encoding every frontmatter value by hand
reason_failed: reader key-set parser chokes on unescaped unicode in values
files_touched: ["scripts/grudge_append.py"]
date: 2026-01-02
---
## Approach tried
JSON-encoding every frontmatter value by hand.

## Why it failed
The reader's key-set parser chokes on unescaped unicode in values, so a value
with an embedded newline forges a flush-left structural line.

NOTE: this is a SYNTHETIC fixture (repo_root is a placeholder, so it never
surfaces as a real grudge). It demonstrates the dead-end record kind for
eval/grudge tests. Do NOT put real paths or secrets here.