"""Deterministic changed-file selection + bundling — single source of truth (#630).

The deterministic step a many-file review fans out from: enumerate changed
files, select the reviewable ones (no silent skips), group related files into
bundles, and emit one coverage report that assigns every changed file to
exactly one bundle (or names the explicit skip). One review worker per bundle
then covers its files, exactly once.

Mirrors alibaba/open-code-review's shape (`selectFiles` + `groupDiffs`),
ported to a pure stdlib Python core. Pure stdlib. No third-party deps.
`test_change_bundling.py` pins the contract.
"""
from __future__ import annotations

import re

# locale token that may sit before a file's extension, e.g. `message_en.properties`
# → stem `message`. Bundling groups `*.en`/`*.zh`/`*.de` siblings into one bundle.
_LOCALE_IN_STEM = re.compile(r"^(.*?)(_[a-z]{2}(?:_[A-Z]{2})?)(\.[^/]*)$")

# A binary file cannot be reviewed — flagged so the skip is explicit.
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib",
}

# Max files per bundle; a directory bulk-change over this splits (alibaba uses 10).
MAX_FILES_PER_BUNDLE = 10


def parse_git_name_status(text: str) -> list[tuple[str, str]]:
    """Parse `git diff --name-status` output into [(status, path), ...].
    Status is the leading letter only (`M`, `A`, `D`, `C`, `R`); for a rename
    the NEW path is kept (`R100\told\tnew`)."""
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0][0]
        path = parts[2] if status == "R" and len(parts) >= 3 else parts[1]
        entries.append((status, path))
    return entries


def select_reviewable(
    entries: list[tuple[str, str]],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Split changed-file entries into (selected, excluded). Deletions and
    binaries are excluded with an explicit reason — the skip is never silent.
    Returns sorted selected paths and sorted excluded (path, reason) pairs."""
    binary_reasons = {p: "binary" for s, p in entries if s != "D"}
    candidates = sorted({p for s, p in entries if s != "D"})
    selected: list[str] = []
    excluded: list[tuple[str, str]] = []
    for path in candidates:
        ext = "." + path.rsplit(".", 1)[1].lower() if "." in path.rsplit("/", 1)[-1] else ""
        if ext in _BINARY_EXTS:
            excluded.append((path, "binary"))
        else:
            selected.append(path)
    excluded += [(p, "deleted") for s, p in entries if s == "D"]
    excluded.sort()
    return selected, excluded


def _locale_stem(path: str) -> str:
    """Bundle key that folds locale siblings onto one stem: `message_en.properties`
    and `message_zh.properties` both key to `message.properties`."""
    head, sep, tail = path.rpartition("/")
    m = _LOCALE_IN_STEM.match(tail)
    if not m:
        return path
    return head + sep + m.group(1) + m.group(3)


def bundle_files(files: list[str]) -> list[list[str]]:
    """Group changed files deterministically: locale siblings first, then
    same-directory affinity, then split any oversized group. The output is a
    partition of the input — every file exactly once, order-independent."""
    files = sorted(set(files))
    # pass 1 — locale siblings: same dir + same locale-stripped stem go together.
    stem_keys: dict[str, list[str]] = {}
    for f in files:
        stem_keys.setdefault(_locale_stem(f), []).append(f)
    bundles = sorted(stem_keys.values(), key=lambda bs: bs[0])
    for b in bundles:
        b.sort()

    # pass 2 — directory affinity: single-file bundles in one dir merge.
    by_dir: dict[str, list[str]] = {}
    order: list[str] = []
    singles = [b[0] for b in bundles if len(b) == 1]
    single_set = set(singles)
    kept: list[list[str]] = []
    for b in bundles:
        if len(b) == 1 and b[0] in single_set:
            d = b[0].rpartition("/")[0]
            by_dir.setdefault(d, []).append(b[0])
        else:
            kept.append(b)
    for d in sorted(by_dir):
        kept.append(sorted(by_dir[d]))
    kept.sort(key=lambda b: b[0])

    # pass 3 — size cap on any bundle that still exceeds the ceiling.
    out: list[list[str]] = []
    for b in kept:
        if len(b) <= MAX_FILES_PER_BUNDLE:
            out.append(b)
        else:
            for i in range(0, len(b), MAX_FILES_PER_BUNDLE):
                out.append(b[i:i + MAX_FILES_PER_BUNDLE])
    out.sort(key=lambda b: b[0])
    return out


def coverage_report(
    changed: list[str],
    bundles: list[list[str]],
    excluded: list[tuple[str, str]],
) -> dict:
    """Emit a per-file coverage report. `changed` is the full changed-file set
    (reviewable + skipped); `bundles` its partition; `excluded` the explicit
    skips. Raises ValueError if any changed file is neither bundled nor
    explicitly skipped — the no-silent-skip guarantee."""
    changed = sorted(set(changed))
    loaded = [p for b in bundles for p in b]
    leftover = [p for p in changed if p not in loaded]
    skip_paths = {p for p, _ in excluded}
    silent = [p for p in leftover if p not in skip_paths]
    if silent:
        raise ValueError(f"changed files with no bundle and no explicit skip: "
                         f"{silent}")
    return {
        "all": changed,
        "bundled": loaded,
        "skipped": sorted(skip_paths),
        "assignment": [p for b in bundles for p in b],
    }