#!/usr/bin/env python3
"""O-8: prose-wiring lint.

The Python helpers are tested in isolation elsewhere; this asserts the host SKILL.md
prose actually invokes them at the specified phases, so deleting the wiring is caught
even though it can't be executed in the authoring session (design fix #8).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def _read(rel):
    p = os.path.join(REPO_ROOT, rel)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


# (skill file, required helper invocation(s))
READ_CONSUMERS = ["skills/build/SKILL.md", "skills/quality-gate/SKILL.md", "skills/debugging/SKILL.md"]
WRITE_CONSUMERS = ["skills/debugging/SKILL.md", "skills/merge-pr/SKILL.md"]


def main():
    skill = _read("skills/grudge/SKILL.md")
    _check("O-8 grudge skill exists", skill is not None)
    if skill:
        _check("O-8 grudge skill documents query helper", "grudge_query.py" in skill)
        _check("O-8 grudge skill documents append helper", "grudge_append.py" in skill)

    for rel in READ_CONSUMERS:
        text = _read(rel)
        _check(f"O-8 {rel} wires grudge_query.py (pre-flight read)",
               text is not None and "grudge_query.py" in text)

    for rel in WRITE_CONSUMERS:
        text = _read(rel)
        _check(f"O-8 {rel} wires grudge_append.py (write-point)",
               text is not None and "grudge_append.py" in text)

    # scripts present and importable-as-files
    for rel in ("scripts/grudge_append.py", "scripts/grudge_query.py"):
        _check(f"O-8 {rel} exists", os.path.isfile(os.path.join(REPO_ROOT, rel)))

    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
