# Receipt — plan-writer (mocked)

VERDICT: PASS
CLAIMS:
- plan-task-count: 1
- plan-saved-at: docs/plans/2026-05-28-get-user-email-implementation-plan.md
WITNESS: kind=read; ran=TRACE#1
TRACE: 1: read design doc; 2: wrote implementation plan
TRIPWIRE: always
SUPERSEDES:

## Plan (summary)

### Task 1: Implement get_user_email

**Files:**
- Modify: `src/users.py` — add `get_user_email(user_id)`
- Create: `src/test_users.py` — test the new function

**Step 1.1: Write failing test**

```python
def test_get_user_email_returns_string():
    assert isinstance(get_user_email(1), str)
```

**Step 1.2: Implement minimal**

```python
def get_user_email(user_id):
    return f"user{user_id}@example.com"
```

**Step 1.3: Verify + commit**
