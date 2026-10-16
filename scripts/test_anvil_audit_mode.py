#!/usr/bin/env python3
"""Regression contract for anvil's skill-suite audit mode (#720)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_audit_mode():
    skill = (ROOT / "skills/anvil/SKILL.md").read_text()
    audit = (ROOT / "skills/anvil/references/skill-audit.md").read_text()
    description = skill.split("---", 2)[1]
    cases = json.loads((ROOT / "skills/anvil/evals/routing.json").read_text())["evals"]
    assert not (ROOT / "skills/stocktake").exists()
    assert len(skill.splitlines()) <= 500
    assert "## Contents" in skill
    assert "references/skill-audit.md" in skill
    assert "overlap" in description and "staleness" in description and "broken references" in description
    assert "skills/anvil/results.json" in audit
    assert "skills/stocktake/results.json" in audit  # legacy cache retained until copied
    assert "no subagent dispatch" in audit
    feed_forward = (ROOT / "skills/getting-started/feed-forward-prompt.md").read_text()
    assert "crucible:anvil" in feed_forward and "skills/stocktake/results.json" in feed_forward
    for mode in ("Quick Scan Flow", "Full Stocktake Flow", "Efficiency Report Flow", "Results File Schema", "Safety"):
        assert mode in audit
    for case in cases:
        if case.get("boundary") != "anvil-skill-audit":
            continue
        assert case["expected_skill"] == "anvil"
        assert "stocktake" not in json.dumps(case).lower()
        assert "anvil" not in case.get("common_mistakes", [])
    assert sum(case.get("boundary") == "anvil-skill-audit" for case in cases) >= 3


if __name__ == "__main__":
    test_audit_mode()
    print("OK — anvil skill audit mode")
