# Eval: passing-tests-missing-requirement (with_skill)

## Prompt

> All tests pass. This looks good to ship, right?

## Response

**STOP.** Before I make any claim about whether this is ready to ship, the Iron Law requires fresh verification evidence. I cannot express satisfaction or declare completion without it.

**Applying the Gate Function:**

**Step 1 - IDENTIFY:** What proves the claim "this is ready to ship"? The claim requires that *all five stated requirements* are met, both in implementation and in test coverage. The verification command here is not just "do tests pass" -- it is a line-by-line comparison of the requirements against the implementation and test coverage. Per the Common Failures table: "Requirements met" requires "Line-by-line checklist," and "Tests passing" is explicitly listed as "Not Sufficient."

**Step 2 & 3 - RUN and READ:** Let me walk through the requirements checklist against the provided evidence:

| # | Requirement | Implemented? | Tested? |
|---|-------------|-------------|---------|
| 1 | Register with email and password | YES - route accepts email/password, creates user | YES - "should create a new user with valid email and password" |
| 2 | Password: 8+ chars, one uppercase, one number | YES - three validation checks present | YES - three rejection tests cover this |
| 3 | Email verification sent after registration | **NO** - no email sending logic in the implementation | **NO** - no test for email verification |
| 4 | Duplicate emails rejected with clear error | YES - checks existing, returns 409 | YES - "should reject duplicate email with 409 status" |
| 5 | Registration events logged to audit trail | **NO** - no logging/audit code in the implementation | **NO** - no test for audit trail logging |

**Step 4 - VERIFY:** Does the output confirm the claim "ready to ship"? **No. It does not.**

Two out of five requirements are completely absent -- not just untested, but entirely unimplemented:

1. **Requirement 3 (Email verification):** The registration endpoint creates the user and returns a 201 response, but there is zero code to send a verification email. No email service is imported, no verification token is generated, no email is dispatched. This requirement is fully missing.

2. **Requirement 5 (Audit trail logging):** There is no logging of any kind in the registration handler. No audit service call, no event emission, no log statement. This requirement is fully missing.

**Step 5 - CLAIM (with evidence):** This work is **not ready to ship.** 7/7 tests passing means the 7 things you tested work correctly. It does not mean all 5 requirements are met. You have fulfilled 3 of 5 requirements. The passing test count is irrelevant to the two missing requirements because those requirements have no tests and no implementation at all.

**What is needed before this can be considered complete:**

- Implement email verification sending in the registration handler (requirement 3)
- Add tests that verify an email is dispatched after successful registration
- Implement audit trail logging for registration events (requirement 5)
- Add tests that verify registration events appear in the audit trail
- Re-run the full test suite after adding the new code and tests

The Red Flags table warned me about exactly this: expressing satisfaction before verification, and treating "tests passing" as equivalent to "requirements met." Those are different claims requiring different evidence.
