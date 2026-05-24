"""Tests for _dispatch_paths: resolve_dispatch_dir + fixture_sha."""
import os
from pathlib import Path

from skills.temper.evals._dispatch_paths import fixture_sha, resolve_dispatch_dir


def test_resolve_dispatch_dir_uses_xdg_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "alice")
    p = resolve_dispatch_dir("R-test")
    assert p == tmp_path / "alice-crucible-dispatch-R-test"


def test_resolve_dispatch_dir_falls_back_to_tmp(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("USER", "alice")
    p = resolve_dispatch_dir("R-test")
    assert str(p).startswith("/tmp/")
    assert "alice-crucible-dispatch-R-test" in str(p)


def test_resolve_dispatch_dir_handles_unset_user(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("USER", raising=False)
    p = resolve_dispatch_dir("R-test")
    assert str(os.getuid()) in str(p)


def test_fixture_sha_deterministic():
    record = {"id": "x", "prompt": "p", "allowed_files": ["a"]}
    h1 = fixture_sha(record)
    h2 = fixture_sha({"prompt": "p", "id": "x", "allowed_files": ["a"]})  # key reorder
    assert h1 == h2  # sort_keys=True normalizes
    assert len(h1) == 64  # sha256 hex
