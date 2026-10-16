#!/usr/bin/env python3
"""Reject contradictory selection evals and unknown expected skills."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check(root: Path) -> list[str]:
    errors = []
    paths = sorted((root / "skills").glob("**/evals/evals.json")) + sorted((root / "eval").glob("**/evals.json"))
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = data["evals"] if isinstance(data, dict) else data
        for index, case in enumerate(cases):
            if "expected_skill" not in case:
                continue
            expected = case["expected_skill"]
            names = expected if isinstance(expected, list) else [expected]
            for name in names:
                label = f"{path.relative_to(root)}:{case.get('id', index)}"
                if name in case.get("common_mistakes", []):
                    errors.append(f"{label}: expected_skill {name!r} also in common_mistakes")
                if not isinstance(name, str) or not (root / "skills" / name / "SKILL.md").is_file():
                    errors.append(f"{label}: expected_skill {name!r} has no skill directory")
    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("OK — eval expected skills consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
