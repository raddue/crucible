# Code Review: `process_user_data`

## Code Under Review

```python
def process_user_data(data):
    name = data['name']
    email = data['email']
    age = int(data['age'])
    query = f"INSERT INTO users VALUES ('{name}', '{email}', {age})"
    db.execute(query)
    return {'status': 'ok', 'message': f'Added {name}'}
```

## Review Summary

This function has several serious issues that must be fixed before it is ready for use. The most critical is a SQL injection vulnerability, but there are also problems with error handling, input validation, and robustness.

---

## Findings

### CRITICAL -- SQL Injection Vulnerability

The query is built by interpolating user-supplied strings directly into the SQL statement using an f-string:

```python
query = f"INSERT INTO users VALUES ('{name}', '{email}', {age})"
db.execute(query)
```

An attacker can supply a crafted `name` or `email` value such as `'; DROP TABLE users; --` to execute arbitrary SQL. This is the textbook definition of a SQL injection flaw.

**Fix:** Use parameterized queries (placeholders) so the database driver handles escaping:

```python
query = "INSERT INTO users (name, email, age) VALUES (?, ?, ?)"
db.execute(query, (name, email, age))
```

(Use `%s` placeholders if the driver follows the DB-API2 `format` paramstyle.)

---

### HIGH -- No Input Validation

- There is no check that `data` actually contains the keys `name`, `email`, and `age`. A missing key raises an unhandled `KeyError`.
- `int(data['age'])` will raise `ValueError` on non-numeric input with no meaningful error message to the caller.
- There is no validation that `email` looks like a valid email address, that `name` is non-empty, or that `age` is within a reasonable range (e.g., 0--150).

**Fix:** Validate inputs explicitly and return clear error responses or raise domain-specific exceptions:

```python
if not data.get('name'):
    raise ValueError("name is required and must be non-empty")
```

---

### HIGH -- No Error Handling Around Database Operation

If `db.execute` fails (connection lost, constraint violation, etc.), the exception propagates uncaught. Depending on the caller, this could expose internal error details to end users or leave the application in an inconsistent state.

**Fix:** Wrap the database call in a try/except and handle or re-raise with context:

```python
try:
    db.execute(query, (name, email, age))
except db.Error as e:
    return {'status': 'error', 'message': 'Failed to insert user'}
```

---

### MEDIUM -- Missing Explicit Column List in INSERT

`INSERT INTO users VALUES (...)` relies on the column order of the table definition. If the schema changes (columns reordered, new column added), this statement silently breaks or inserts data into the wrong columns.

**Fix:** Always specify columns explicitly:

```python
"INSERT INTO users (name, email, age) VALUES (?, ?, ?)"
```

---

### MEDIUM -- `db` Is an Implicit Global Dependency

The function references `db` from the enclosing scope with no indication of where it comes from. This makes the function hard to test and tightly coupled to a module-level singleton.

**Fix:** Pass the database connection as a parameter:

```python
def process_user_data(db, data):
```

---

### LOW -- No Return Value on Failure Path

The function only returns a success dict. If any exception is raised (bad input, DB error), there is no structured error return -- the caller just gets an exception. A consistent return contract (or a consistent exception strategy) would be more robust.

---

## Verdict

**Not ready for merge.** The SQL injection vulnerability alone is a blocking issue. The function needs parameterized queries, input validation, error handling, and an explicit column list before it should be used in any environment.
