# Copied from skills/temper/evals/_runid.py (#424). Inquisitor imports ONLY
# validate_run_id; temper's calibrate-only helpers (sanitize_summary, validate_prefix)
# are intentionally omitted — scripts/check_inquisitor_helper_drift.py is function-scoped
# to the functions inquisitor imports, so dropping the unused helpers does not redden CI
# (SP3). validate_run_id's body + docstring stay logic-identical to temper's.
"""Run-id validation utility for the inquisitor fan-out eval harness (#424). I-9
enforcement; mirrors temper's helper of the same name."""
import re

# 2P-4: first char must NOT be `-` (else run-id parses as a CLI flag downstream).
# Subsequent chars may include `-`.
# M-R7-1: leading underscore is technically legal; treated equivalent to alphanumeric for path-traversal safety (`_foo` resolves identically to `foo` w.r.t. directory escape).
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,31}$")


def validate_run_id(run_id: str) -> None:
    """Raise ValueError if run-id violates I-9."""
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            f"invalid run-id {run_id!r}: must match {_RUN_ID_RE.pattern}"
        )
