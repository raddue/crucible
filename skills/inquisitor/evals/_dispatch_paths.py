# Copied from skills/temper/evals/_dispatch_paths.py (#424). The bodies of the
# functions inquisitor imports (resolve_dispatch_dir / fixture_sha / template_sha)
# stay logic-identical to temper's — enforced by scripts/check_inquisitor_helper_drift.py
# (function-scoped AST comparison). Only the module + template_sha docstrings are
# rewritten to the inquisitor context (the drift check strips those two by AST position).
"""Dispatch-dir path resolution + fixture hashing for the inquisitor fan-out eval
harness (#424). Mirrors temper's helper of the same name."""
import hashlib
import json
import os
from pathlib import Path


def resolve_dispatch_dir(run_id: str) -> Path:
    """Resolve XDG_RUNTIME_DIR or /tmp + USER or UID namespacing.

    M-α: USER may be unset in container environments.
    """
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    user = os.environ.get("USER") or str(os.getuid())
    return Path(base) / f"{user}-crucible-dispatch-{run_id}"


def fixture_sha(fixture_record: dict) -> str:
    """S-A: sha256 of canonical JSON of the evals.json fixture record."""
    canonical = json.dumps(fixture_record, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def template_sha(template_path: Path) -> str:
    """sha256 of a committed prompt template (e.g. inquisitor-dimension-prompt-eval.md)
    at stage time, recorded in the manifest so byte-identity invariants are checkable."""
    return hashlib.sha256(template_path.read_bytes()).hexdigest()
