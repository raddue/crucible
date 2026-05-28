# Receipt — design (mocked)

VERDICT: PASS
CLAIMS:
- design-doc-path: docs/plans/2026-05-28-user-service-design.md
- dec-count: 2
WITNESS: kind=read; ran=TRACE#1
TRACE: 1: read user request; 2: composed design with UserService + UserRepository decomposition
TRIPWIRE: always
SUPERSEDES:

## Design (summary)

DEC-1: UserRepository owns persistence; UserService owns business logic.
DEC-2: Service depends on repository via constructor injection — repository must exist before service.

Acceptance criteria:
- `src/users/repository.py` defines `UserRepository` (data access)
- `src/users/service.py` defines `UserService` (takes a UserRepository in __init__)
