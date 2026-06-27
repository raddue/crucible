# Blind-author input for the `webshop` siege fixture (#373)

<!-- MODEL-TIER: security-hard-out -->

This is the VERBATIM context handed to the blind ground-truth author. It describes the
feature under review and the codebase facts only. The planted vulnerabilities'
signature tokens and their `desc` strings in `ground-truth-bugs.json` are deliberately
WITHHELD here, so the author cannot reverse-engineer the answer key from this file.
`scripts/check_siege_gt_provenance.py` machine-verifies that none of those withheld
strings appear below.

## Feature under review

A miniature storefront backend in two modules:

- `app.py` — request handlers for the storefront: an endpoint that lists the
  registered users for an operator console, a lookup that returns a single order by
  its identifier, a preview helper that retrieves content from a caller-provided
  address, and a handler that returns a stored file selected by name.
- `db.py` — the data layer: it looks up a single user record by the supplied name and
  restores a previously saved session value handed back by the client.

## Codebase facts

- Pure Python, standard-library only; no external packages and no real server — the
  request objects and network/file calls are illustrative stand-ins that never run.
- Each handler is a few lines; callers pass an ordinary dict for the request.
- The storefront has both anonymous visitors and signed-in customers; the operator
  console is meant for staff only.
- Orders belong to the customer who placed them; the file handler is meant to serve
  only files kept under the storefront's own download directory.

## Task for the reviewer

Audit these two modules from an attacker's perspective and report each security
weakness you find: the file, the line, a short title, the exploitation scenario, and
how you would verify it. Classify each by severity.
