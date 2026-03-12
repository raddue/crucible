# Quality Gate Transcript

**Artifact type:** code
**Artifact:** `process_user_data` utility function
**Date:** 2026-03-11

---

## Original Artifact

```python
def process_user_data(data):
    name = data['name']
    email = data['email']
    age = int(data['age'])
    query = f"INSERT INTO users VALUES ('{name}', '{email}', {age})"
    db.execute(query)
    return {'status': 'ok', 'message': f'Added {name}'}
```

---

## Round 1 -- Devil's Advocate Review

### Fatal Challenges

1. **SQL Injection via String Interpolation**
   - **What breaks:** The function constructs SQL using f-string interpolation with raw user input (`name`, `email`, `age`). An attacker supplying `name = "'; DROP TABLE users; --"` can execute arbitrary SQL, including data exfiltration, table destruction, or privilege escalation.
   - **Why:** No parameterized queries, no escaping, no sanitization.
   - **Evidence:** Line `query = f"INSERT INTO users VALUES ('{name}', '{email}', {age})"` directly embeds user-controlled strings into SQL.
   - **Proposed fix:** Use parameterized queries: `cursor.execute("INSERT INTO users (name, email, age) VALUES (%s, %s, %s)", (name, email, age))`.

2. **No Input Validation**
   - **What breaks:** `data['name']` accepts any string (including empty, extremely long, or containing control characters). `data['email']` is not validated as an email. `int(data['age'])` accepts negative values, zero, or absurdly large numbers. No bounds checking on any field.
   - **Why:** The function blindly trusts all input.
   - **Evidence:** No validation logic exists anywhere in the function.
   - **Proposed fix:** Add validation for all fields: name length/content, email format (regex or library), age range (0-150).

3. **No Error Handling**
   - **What breaks:** Missing keys in `data` raise `KeyError`. Non-numeric `age` raises `ValueError`. Database failures propagate as unhandled exceptions. The function has zero error handling.
   - **Why:** No try/except blocks, no defensive checks.
   - **Evidence:** Every line can raise an exception that is never caught.
   - **Proposed fix:** Add try/except for type conversion, check for required keys, wrap database operations in error handling that returns meaningful error responses.

### Significant Challenges

4. **No Transaction Management**
   - **Risk:** `db.execute()` is called without commit or rollback. If this is part of a larger operation, the insert may be left uncommitted or in an inconsistent state.
   - **Likelihood:** High in any real application with multiple database operations.
   - **Impact:** Data inconsistency, phantom inserts, or lost writes.
   - **Proposed fix:** Add explicit `commit()` after successful insert and `rollback()` in error paths.

5. **Implicit Column Order (No Column Names)**
   - **Risk:** `INSERT INTO users VALUES (...)` relies on the column order in the table schema. If any column is added, removed, or reordered, this query silently inserts data into wrong columns or fails.
   - **Likelihood:** Medium -- schema changes are common over time.
   - **Impact:** Data corruption or query failure.
   - **Proposed fix:** Specify column names: `INSERT INTO users (name, email, age) VALUES (...)`.

6. **Global `db` Dependency**
   - **Risk:** The function references `db` from the enclosing module scope. This makes the function impossible to unit test without mocking a global, couples it to a specific connection lifecycle, and prevents reuse across different database connections.
   - **Likelihood:** High -- any testing or multi-database scenario hits this.
   - **Impact:** Untestable code, tight coupling.
   - **Proposed fix:** Accept `db_connection` as a parameter.

### Minor Observations

7. **No type hints or docstring.** Non-blocking.
8. **Return value does not indicate errors** -- all error paths raise exceptions, so callers cannot distinguish success from "function never returned." Non-blocking.

### Overall Assessment

- **Verdict:** Fundamentally flawed
- **Confidence:** Very high. The SQL injection is textbook, the missing error handling is self-evident, and the lack of validation is verifiable by reading the code.
- **Summary:** This function has three Fatal-severity issues including a critical SQL injection vulnerability. It must not be deployed in its current form.

### Weighted Score

| Severity    | Count | Weight | Subtotal |
|-------------|-------|--------|----------|
| Fatal       | 3     | 3      | 9        |
| Significant | 3     | 1      | 3        |
| **Total**   |       |        | **12**   |

---

## Fixes Applied After Round 1

- Replaced f-string SQL construction with parameterized queries using `%s` placeholders
- Added input validation: required field checks, name length, email regex, age type/range
- Added try/except around database operations with commit/rollback
- Specified explicit column names in INSERT statement
- Accepted `db_connection` as a parameter instead of using global `db`
- Added type hints and docstring

### Revised Artifact (Post Round 1)

```python
import re
from typing import Any

def process_user_data(data: dict[str, Any], db_connection) -> dict[str, str]:
    """Insert a validated user record into the database.

    Args:
        data: Dictionary containing 'name', 'email', and 'age' keys.
        db_connection: A database connection object supporting cursor/execute.

    Returns:
        A dict with 'status' ('ok' or 'error') and 'message'.
    """
    required_fields = ('name', 'email', 'age')
    for field in required_fields:
        if field not in data:
            return {'status': 'error', 'message': f'Missing required field: {field}'}

    name = str(data['name']).strip()
    email = str(data['email']).strip()

    if not name or len(name) > 200:
        return {'status': 'error', 'message': 'Invalid name: must be 1-200 characters'}

    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return {'status': 'error', 'message': 'Invalid email format'}

    try:
        age = int(data['age'])
    except (ValueError, TypeError):
        return {'status': 'error', 'message': 'Age must be a valid integer'}

    if not (0 <= age <= 150):
        return {'status': 'error', 'message': 'Age must be between 0 and 150'}

    query = "INSERT INTO users (name, email, age) VALUES (%s, %s, %s)"
    try:
        cursor = db_connection.cursor()
        cursor.execute(query, (name, email, age))
        db_connection.commit()
    except Exception as e:
        db_connection.rollback()
        return {'status': 'error', 'message': f'Database error: {e}'}

    return {'status': 'ok', 'message': f'Added {name}'}
```

---

## Round 2 -- Fresh Devil's Advocate Review

### Fatal Challenges

(None)

### Significant Challenges

1. **Leaking Internal Error Details**
   - **Risk:** The `except Exception as e` block returns `f'Database error: {e}'` to the caller. If this is surfaced to an end user or API consumer, the raw exception message may reveal internal schema names, database engine info, or connection strings -- an information disclosure vulnerability.
   - **Likelihood:** High in any web or API context.
   - **Impact:** Information disclosure enabling further attack.
   - **Proposed fix:** Log the full error internally, return a generic message to the caller.

2. **Overly Broad Exception Handling**
   - **Risk:** Catching bare `Exception` will swallow programming errors (`AttributeError` if `db_connection` has no `cursor()` method, `TypeError` from bad arguments). This masks bugs and makes debugging harder.
   - **Likelihood:** Medium -- any misconfiguration or API misuse triggers this.
   - **Impact:** Silent failure, masked bugs.
   - **Proposed fix:** Catch specific database exceptions (e.g., `DatabaseError`, `InterfaceError` from PEP 249).

3. **Cursor Not Closed**
   - **Risk:** The cursor is created but never explicitly closed. Cursor leaks can exhaust server-side resources in long-running processes.
   - **Likelihood:** Medium in long-running services.
   - **Impact:** Resource exhaustion.
   - **Proposed fix:** Use a `finally` block to close the cursor.

### Minor Observations

4. **Email regex is simplistic** -- rejects some valid edge-case emails. Non-blocking.
5. **`%s` placeholder style is driver-specific** -- would need abstraction for driver-agnostic code. Non-blocking.

### Overall Assessment

- **Verdict:** Has issues that must be addressed
- **Confidence:** High. The information disclosure and broad exception handling are verifiable by reading the code.
- **Summary:** The major security vulnerabilities from Round 1 are resolved. Three Significant issues remain around error handling hygiene and resource management.

### Weighted Score

| Severity    | Count | Weight | Subtotal |
|-------------|-------|--------|----------|
| Fatal       | 0     | 3      | 0        |
| Significant | 3     | 1      | 3        |
| **Total**   |       |        | **3**    |

### Score Comparison: Round 1 (12) -> Round 2 (3). Strictly lower. Progress confirmed. Continuing.

---

## Fixes Applied After Round 2

- Replaced generic error message with safe, opaque message for callers
- Added `logging` to capture full error details server-side
- Narrowed exception handling to `DatabaseError` and `InterfaceError`
- Added `finally` block to close cursor
- Added safe rollback with its own error handling

### Revised Artifact (Post Round 2)

```python
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def process_user_data(data: dict[str, Any], db_connection) -> dict[str, str]:
    """Insert a validated user record into the database.

    Args:
        data: Dictionary containing 'name', 'email', and 'age' keys.
        db_connection: A database connection object supporting cursor/execute.

    Returns:
        A dict with 'status' ('ok' or 'error') and 'message'.
    """
    required_fields = ('name', 'email', 'age')
    for field in required_fields:
        if field not in data:
            return {'status': 'error', 'message': f'Missing required field: {field}'}

    name = str(data['name']).strip()
    email = str(data['email']).strip()

    if not name or len(name) > 200:
        return {'status': 'error', 'message': 'Invalid name: must be 1-200 characters'}

    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return {'status': 'error', 'message': 'Invalid email format'}

    try:
        age = int(data['age'])
    except (ValueError, TypeError):
        return {'status': 'error', 'message': 'Age must be a valid integer'}

    if not (0 <= age <= 150):
        return {'status': 'error', 'message': 'Age must be between 0 and 150'}

    query = "INSERT INTO users (name, email, age) VALUES (%s, %s, %s)"
    cursor = None
    try:
        cursor = db_connection.cursor()
        cursor.execute(query, (name, email, age))
        db_connection.commit()
    except (db_connection.DatabaseError, db_connection.InterfaceError) as e:
        logger.error("Failed to insert user %s: %s", name, e)
        try:
            db_connection.rollback()
        except Exception:
            logger.exception("Rollback also failed")
        return {'status': 'error', 'message': 'A database error occurred. Please try again later.'}
    finally:
        if cursor is not None:
            cursor.close()

    return {'status': 'ok', 'message': f'Added {name}'}
```

---

## Round 3 -- Fresh Devil's Advocate Review

### Fatal Challenges

(None)

### Significant Challenges

(None)

### Minor Observations

1. **`db_connection.DatabaseError` assumes PEP 249 compliance** -- some third-party drivers expose exception classes at module level rather than on the connection object. Non-blocking since all mainstream drivers support this pattern.
2. **User-provided name in log message** -- `logger.error("Failed to insert user %s: %s", name, e)` logs user input. Safe from injection via `%s` formatting, and name is already validated to 200 chars max. Non-blocking.
3. **No duplicate handling** -- unique constraint violations return a generic error. A more user-friendly approach would detect and surface duplicates. Non-blocking since the generic handler is safe.

### Overall Assessment

- **Verdict:** Plan is solid
- **Confidence:** High. No Fatal or Significant issues found after thorough adversarial review.
- **Summary:** The function is well-structured with proper input validation, parameterized queries, scoped error handling, and resource cleanup. Only minor observations remain, none of which are blocking.

### Weighted Score

| Severity    | Count | Weight | Subtotal |
|-------------|-------|--------|----------|
| Fatal       | 0     | 3      | 0        |
| Significant | 0     | 1      | 0        |
| **Total**   |       |        | **0**    |

### Score Comparison: Round 2 (3) -> Round 3 (0). No Fatal or Significant issues. Artifact approved.

---

## Final Disposition

| Round | Fatal | Significant | Minor | Weighted Score | Outcome     |
|-------|-------|-------------|-------|----------------|-------------|
| 1     | 3     | 3           | 2     | 12             | Fix & retry |
| 2     | 0     | 3           | 2     | 3              | Fix & retry |
| 3     | 0     | 0           | 3     | 0              | **Approved**|

**Result: APPROVED after 3 rounds.**

The original code had critical vulnerabilities including SQL injection, missing input validation, and no error handling (weighted score: 12). All Fatal and Significant issues were resolved across two fix cycles. The final artifact is clean with only minor, non-blocking observations.
