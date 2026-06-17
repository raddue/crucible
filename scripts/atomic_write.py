#!/usr/bin/env python3
"""Atomic whole-file write — tmp-in-same-dir + fsync + os.replace (#400).

Several persistent stores in the calibration/grudge subsystem rewrite a whole
file on each update (`brier-rolling.json`, `weekly-*.md`, `calibration.json`,
each grudge `<hash>.md`). A bare `open(path, "w")` truncates the destination
BEFORE the new bytes land, so a crash — or a concurrent reader, or a second
writer racing on the same deterministic key — can observe a torn / empty file.
Every reader in the subsystem degrades silently on a parse error, so a torn
write is invisible: the only symptom is "the advisory stopped showing up."

`os.replace` is atomic on a single filesystem (POSIX rename, NTFS
MoveFileEx): a reader sees either the complete old file or the complete new
file, never a partial one, and a second same-key writer's full file simply wins
last — neither is ever truncated mid-flight. The temp file is created in the
DESTINATION directory so the rename stays within one filesystem (a cross-FS
`os.replace` would raise instead of silently copying).

This mirrors the discipline already proven in `compass.py:_atomic_write`,
adding fsync-before-rename (the new bytes are durably on disk before the atomic
swap; note the parent-directory entry is not separately fsynced, so the rename
is atomic but not itself power-loss-durable) and tmp cleanup on error. Pure
stdlib; no third-party deps. Importable as the single source of truth so the
four writers cannot drift.

The replacement inode comes from `tempfile.mkstemp` (mode 0600), so before the
`os.replace` we reapply `open()`-create permission semantics to the temp file:
the destination's CURRENT mode if it already exists, else `0o666 & ~umask`. This
keeps a shared store (e.g. `calibration.json`) world/group-readable as it was
under the old `open(path, "w")` path, avoiding a silent 0600 read-failure for a
second uid.
"""
import os
import stat
import tempfile
from typing import Union


def atomic_write_text(path: str, text: str, *, encoding: str = "utf-8") -> None:
    """Durably replace `path` with `text`.

    Writes to a temp file in the same directory, fsyncs it, then `os.replace`s
    it over `path` in one atomic step. Creates the parent directory if absent.
    On any failure the temp file is removed and the exception propagates — the
    destination is left untouched (old contents intact), never half-written.
    """
    _atomic_write(path, text.encode(encoding))


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Bytes variant of :func:`atomic_write_text`."""
    _atomic_write(path, data)


def _atomic_write(path: str, data: Union[bytes, bytearray]) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    # mkstemp in the destination dir → same-FS guarantee for os.replace.
    fd, tmp = tempfile.mkstemp(prefix=".atomic-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp creates the temp inode at mode 0600; os.replace would swap that
        # in and silently tighten the destination. Reapply open()-create
        # semantics BEFORE the replace so the destination has the right mode the
        # instant it appears (no 0600 window): the destination's CURRENT mode if
        # it already exists, else 0o666 & ~umask for a fresh file.
        if os.path.exists(path):
            mode = stat.S_IMODE(os.stat(path).st_mode)
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        # Leave the destination untouched; never orphan the temp file.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
