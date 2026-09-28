#!/usr/bin/env python3
"""Structural check for the change-bundling dispatch convention (#630).

Invocation (from repo root):
    python3 scripts/check_change_bundling.py            # gate the real files
    python3 scripts/check_change_bundling.py --selftest # in-memory logic test

Asserts, over three path-pinned files (no directory tree-walk, so the checker
cannot self-match — see `scripts/CHECKER_CONVENTIONS.md`):

  scripts/change_bundling.py — the deterministic engine exists and carries the
      public API surface (`parse_git_name_status`, `select_reviewable`,
      `bundle_files`, `coverage_report`) and the coverage machinery
      (`MAX_FILES_PER_BUNDLE`, the locale-sibling stem fold).

  skills/shared/change-bundling-convention.md — the canonical shared reference,
      carrying every load-bearing clause of the deterministic step: the
      enumerate/select/bundle sequence, the explicit-exclusion table
      (`deleted` / `binary`), the locale-sibling + directory-affinity + size-cap
      bundle rules, and the no-silent-skip guarantee (a file that is neither
      bundled nor explicitly skipped is a defect).

  skills/warden/SKILL.md and skills/orchestrator/SKILL.md — each carries the
      canonical link and a dispatch clause: one review worker per bundle, every
      changed file covered exactly once.

Stdlib only. Exits 0 when every clause is present, 1 with a `- <error>` list
otherwise. Style mirrors `scripts/check_dispatch_graphify_consult.py`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ROOT / "scripts/change_bundling.py"
CONVENTION = ROOT / "skills/shared/change-bundling-convention.md"
WARDEN = ROOT / "skills/warden/SKILL.md"
ORCHESTRATOR = ROOT / "skills/orchestrator/SKILL.md"

# label -> literal substring that MUST appear in scripts/change_bundling.py.
ENGINE_REQUIRED: dict[str, str] = {
    "enumerating fn": "parse_git_name_status",
    "selecting fn": "select_reviewable",
    "bundling fn": "bundle_files",
    "coverage fn": "coverage_report",
    "size cap const": "MAX_FILES_PER_BUNDLE = 10",
    "locale-sibling stem fold": "_locale_stem",
}

# label -> literal substring that MUST appear in the convention doc.
CONVENTION_REQUIRED: dict[str, str] = {
    "enumerate step": "### Enumerate",
    "select step": "### Select",
    "bundle step": "### Bundle",
    "cover-report step": "### Cover-report",
    "deleted exclusion token": "`deleted`",
    "binary exclusion token": "`binary`",
    "locale-sibling rule": "locale",
    "directory-affinity rule": "Directory affinity",
    "size-cap rule": "MAX_FILES_PER_BUNDLE",
    "no-silent-skip guarantee": "exactly one",
    "machine-enforced coverage": "raises",
}

# label -> literal substring that MUST appear in BOTH warden + orchestrator
# SKILL.md (the integration clause).
DISPATCH_REQUIRED: dict[str, str] = {
    "canonical link": "<!-- CANONICAL: shared/change-bundling-convention.md -->",
    "per-bundle worker": "bundle",
    "exactly-once coverage": "covered exactly once",
}


def check_required(text: str, required: dict[str, str]) -> list[str]:
    return [f"missing {label}: `{sub}`" for label, sub in required.items()
            if sub not in text]


def selftest() -> int:
    def good(required: dict[str, str]) -> str:
        return " " + " ".join(required.values()) + " "

    for required in (ENGINE_REQUIRED, CONVENTION_REQUIRED, DISPATCH_REQUIRED):
        assert check_required(good(required), required) == [], (
            f"GOOD sample (join of all required substrings) should pass")
        for label, sub in required.items():
            bad = good(required).replace(sub, "")
            errs = check_required(bad, required)
            assert any(e == f"missing {label}: `{sub}`" for e in errs), (
                f"removing {label!r} should flag it, got: {errs}")

    # cross-file probes keep the engine/convention/who-drives-it wiring honest.
    engine = ENGINE.read_text(encoding="utf-8") if ENGINE.is_file() else ""
    convention = (
        CONVENTION.read_text(encoding="utf-8") if CONVENTION.is_file() else "")
    if engine and convention:
        for sym in ("parse_git_name_status", "bundle_files", "coverage_report"):
            assert sym in engine, f"engine lost {sym}"
        assert "change_bundling.py" in convention, \
            "convention must cite the engine module by name"
        assert "warden" in convention.lower(), \
            "convention must name warden as a consumer"
        assert "orchestrator" in convention.lower(), \
            "convention must name orchestrator as a consumer"

    print("selftest OK — GOOD passes; removing a clause flags exactly that "
          "clause; engine/convention wiring consistent.")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()

    errs: list[str] = []
    for path, required, what in (
        (ENGINE, ENGINE_REQUIRED, "the change-bundling engine"),
        (CONVENTION, CONVENTION_REQUIRED, "the change-bundling convention"),
    ):
        if not path.is_file():
            errs.append(f"missing file: {path.relative_to(ROOT)}")
        else:
            errs += check_required(path.read_text(encoding="utf-8"), required)

    for path, what in ((WARDEN, "warden"), (ORCHESTRATOR, "orchestrator")):
        if not path.is_file():
            errs.append(f"missing file: {path.relative_to(ROOT)}")
        else:
            errs += [
                f"missing {label} in {what}: `{sub}`"
                for label, sub in DISPATCH_REQUIRED.items()
                if sub not in path.read_text(encoding="utf-8")
            ]

    if errs:
        print("CHANGE-BUNDLING CONVENTION CHECK FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — deterministic change-bundling engine + convention present; "
          "warden and orchestrator both carry the per-bundle dispatch clause.")
    return 0


if __name__ == "__main__":
    sys.exit(main())