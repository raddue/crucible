import pytest
from skills.temper.evals._runid import validate_run_id, validate_prefix


def test_validate_run_id_accepts_alphanumeric():
    validate_run_id("R-test")
    validate_run_id("ABC_123-xyz")


def test_validate_run_id_rejects_too_long():
    with pytest.raises(ValueError, match="run-id"):
        validate_run_id("a" * 33)


def test_validate_run_id_rejects_traversal():
    with pytest.raises(ValueError):
        validate_run_id("../etc")
    with pytest.raises(ValueError):
        validate_run_id("a/b")


def test_validate_run_id_rejects_empty():
    with pytest.raises(ValueError):
        validate_run_id("")


def test_validate_run_id_rejects_leading_dash():
    """2P-4: a leading `-` makes the run-id look like a CLI flag downstream
    (e.g. `python -m ... stage -foo` would be parsed as a flag, not a run_id).
    Reject at validation time."""
    with pytest.raises(ValueError):
        validate_run_id("-foo")
    with pytest.raises(ValueError):
        validate_run_id("-")


def test_validate_prefix_caps_at_29():
    validate_prefix("a" * 29)
    with pytest.raises(ValueError):
        validate_prefix("a" * 30)


def test_validate_prefix_rejects_leading_dash():
    """2P-4: same hazard for calibrate prefix."""
    with pytest.raises(ValueError):
        validate_prefix("-prefix")


def test_sanitize_summary_replaces_literal():
    """S-R4-5: literal DISPATCH_STATUS: substring is neutralized."""
    from skills.temper.evals._runid import sanitize_summary
    assert sanitize_summary("DISPATCH_STATUS: ERROR: foo") == "[DISPATCH_STATUS_LITERAL] ERROR: foo"
    assert sanitize_summary("clean text") == "clean text"
    # Case-sensitive — lowercase variants are not the sentinel and are preserved
    assert sanitize_summary("dispatch_status: ok") == "dispatch_status: ok"
