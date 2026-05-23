"""Run-id validation utilities. I-9 enforcement."""
import re

# 2P-4: first char must NOT be `-` (else run-id parses as a CLI flag downstream).
# Subsequent chars may include `-`.
# M-R7-1: leading underscore is technically legal; treated equivalent to alphanumeric for path-traversal safety (`_foo` resolves identically to `foo` w.r.t. directory escape).
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,31}$")
# 2P-R4-1: 29 chars max = 32 (RUN_ID cap) - 3 ("-<i>" suffix where i=1..99).
# M-1 R5: 3 chars is the WORST-CASE suffix budget (i=10..99 → "-NN" = 3 chars).
# For i=1..9 the suffix is only "-N" (2 chars), so a 30-char prefix would still
# fit for those iterations — but we use the worst-case bound uniformly to keep
# the validator simple and avoid leaking the k value into prefix validation.
_PREFIX_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,28}$")


def validate_run_id(run_id: str) -> None:
    """Raise ValueError if run-id violates I-9."""
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            f"invalid run-id {run_id!r}: must match {_RUN_ID_RE.pattern}"
        )


def validate_prefix(prefix: str) -> None:
    """Raise ValueError if calibrate prefix violates I-9 + 3-char iter suffix budget."""
    if not _PREFIX_RE.fullmatch(prefix):
        raise ValueError(
            f"invalid run-id prefix {prefix!r}: must match {_PREFIX_RE.pattern} "
            f"(reserves 3 chars for `-<i>` iteration suffix)"
        )


# S-R4-5: pure-Python sanitize helper. Lives here (not just in SKILL.md docs)
# so it is testable + invokable by any future tooling that writes manifest.jsonl
# summary fields. SKILL.md Step 7 invokes this helper rather than re-deriving the
# transform inline.
def sanitize_summary(s: str) -> str:
    """2P-FE-5 R3 / S-R4-5: prevent reviewer text from spoofing the DISPATCH_STATUS
    sentinel when grepped from manifest.jsonl. Replaces any literal
    `DISPATCH_STATUS:` substring (case-sensitive) with `[DISPATCH_STATUS_LITERAL]`.
    One-way and lossy by design — auditors who need the raw reviewer output
    should read the `<NNN>-result.md` file, not the manifest.jsonl summary."""
    return s.replace("DISPATCH_STATUS:", "[DISPATCH_STATUS_LITERAL]")
