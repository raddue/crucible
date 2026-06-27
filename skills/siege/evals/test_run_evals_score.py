#!/usr/bin/env python3
"""`score` mechanics for the siege eval harness (#373) — fully synthetic, no live
agents. Stages the committed `webshop` fixture, writes a hand-authored recorded
siege-findings JSON (siege threat-finding records) + .collect-status, and asserts
last_run.json carries the expected matcher metrics + the severity-agreement advisory.

The worked example over `webshop` (6 planted vulns ws-v1..v6): the recorded findings
hit ws-v1 (SQLi), ws-v3 (auth bypass), ws-v5 (SSRF) and ws-v6 (path traversal, off_axis),
miss ws-v2 (deser) and ws-v4 (IDOR), plus one positional false-positive at a non-planted
line. → recall 4/6, FP 1/5, off-axis recall 1/1, severity agreement 3/4 (the auth-bypass
finding is recorded High while the GT planted it Critical).
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.siege.evals import run_evals  # noqa: E402

_EVALS_DIR = pathlib.Path(__file__).resolve().parent

# Recorded siege threat-finding records (the 5-line finding format flattened to JSON;
# the adapter maps title→summary, attack/evidence→failure_scenario, severity→advisory).
SAMPLE_FINDINGS = [
    {"id": "SIEGE-BA-1", "severity": "Critical", "exploitability": "Active",
     "title": "SQL injection in get_user via string interpolation",
     "file": "db.py", "line": "19", "cwe": "CWE-89",
     "attack": "send username `' OR '1'='1` to read every row",
     "evidence": "query built with %-interpolation", "agent": "boundary-attacker"},
    {"id": "SIEGE-BA-2", "severity": "High", "exploitability": "Active",
     "title": "Auth bypass: unauthenticated admin user listing",
     "file": "app.py", "line": "17", "cwe": "CWE-306",
     "attack": "missing authentication lets any caller list users",
     "evidence": "admin_list_users has no role check", "agent": "boundary-attacker"},
    {"id": "SIEGE-BA-3", "severity": "High", "exploitability": "Active",
     "title": "SSRF in fetch_preview",
     "file": "app.py", "line": "30", "cwe": "CWE-918",
     "attack": "point url= at the cloud metadata endpoint",
     "evidence": "urlopen on attacker url", "agent": "boundary-attacker"},
    {"id": "SIEGE-BA-4", "severity": "Medium", "exploitability": "Active",
     "title": "Path traversal in download",
     "file": "app.py", "line": "37", "cwe": "CWE-22",
     "attack": "name=../../etc/passwd escapes the download root",
     "evidence": "os.path.join on unsanitized name", "agent": "boundary-attacker"},
    # A false positive: a real line (the DOWNLOAD_ROOT constant) but a non-planted
    # concern with no signature overlap → must NOT match any vuln.
    {"id": "SIEGE-IP-1", "severity": "Low", "exploitability": "Hardening",
     "title": "Hardcoded download root is not environment-configurable",
     "file": "app.py", "line": "11", "cwe": "CWE-547",
     "attack": "config hygiene — no exploitation",
     "evidence": "module constant", "agent": "infrastructure-prober"},
]


class _DispatchEnv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self._tmp.name
        # Preserve any pre-existing committed/ignored eval outputs.
        self._lr = _EVALS_DIR / "last_run.json"
        self._md = _EVALS_DIR / "results.md"
        self._saved = {p: (p.read_bytes() if p.exists() else None)
                       for p in (self._lr, self._md)}

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._prev
        self._tmp.cleanup()
        for p, data in self._saved.items():
            if data is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_bytes(data)

    def _stage_and_record(self, run_id, findings, *, sentinel="DISPATCH_STATUS: OK",
                          collect=True):
        dispatch_dir = run_evals.stage(run_id, fixture="webshop")
        m = json.loads((dispatch_dir / "stage-manifest.json").read_text("utf-8"))
        cell = m["cells"][0]
        body = json.dumps(findings)
        text = f"{sentinel}\n\n{body}" if sentinel else body
        (dispatch_dir / cell["result_file"]).write_text(text, encoding="utf-8")
        if collect:
            (dispatch_dir / ".collect-status").write_text("", encoding="utf-8")
        return dispatch_dir


class TestScore(_DispatchEnv):
    def test_score_computes_expected_metrics(self):
        self._stage_and_record("test-score-1", SAMPLE_FINDINGS)
        rc = run_evals.score("test-score-1")
        self.assertEqual(rc, 0)

        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        self.assertTrue(lr["complete"])
        self.assertEqual(lr["engine"], "siege")
        agg = lr["aggregate"]
        self.assertEqual(agg["bugs"], 6)
        self.assertEqual(agg["matched"], 4)
        self.assertEqual(agg["recall"], 4 / 6)
        self.assertEqual(agg["findings"], 5)
        self.assertEqual(agg["false_positives"], 1)
        self.assertEqual(agg["false_positive_rate"], 1 / 5)
        # Only ws-v6 is off_axis, and it was hit.
        self.assertEqual(agg["off_axis_recall"], 1.0)
        # 4 matched all carry severity; the auth-bypass finding is High vs GT Critical.
        self.assertEqual(agg["severity_agreement"], 3 / 4)

        pf = lr["per_fixture"][0]
        self.assertEqual(pf["fixture_id"], "webshop")
        self.assertEqual(sorted(pf["unmatched_bugs"]), ["ws-v2", "ws-v4"])
        self.assertEqual(pf["severity_agreement"], 3 / 4)
        self.assertFalse(pf["dispatch_failed"])
        self.assertTrue((_EVALS_DIR / "results.md").exists())

    def test_adapter_maps_title_and_attack(self):
        # A finding that carries ONLY siege fields (title/attack, no summary/
        # failure_scenario) must still match via the adapter: the signature token lives
        # in the title (summary) here, and in the attack (failure_scenario) for the SSRF.
        findings = [
            {"id": "X1", "severity": "Critical", "file": "db.py", "line": "19",
             "title": "sql injection here", "attack": "n/a"},
            {"id": "X2", "severity": "High", "file": "app.py", "line": "30",
             "title": "a vuln", "attack": "this is a server-side request forgery sink"},
        ]
        self._stage_and_record("test-score-adapter", findings)
        self.assertEqual(run_evals.score("test-score-adapter"), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        # ws-v1 (title token) + ws-v5 (attack token) → 2 matched.
        self.assertEqual(lr["aggregate"]["matched"], 2)

    def test_score_reconciles_scope_prefixed_paths(self):
        # The live engine may emit scope-relative paths (`<scope>/app.py`); the harness
        # reconciles the fixture's known scope prefix so verbatim-recorded findings still
        # join — scoring identically to the bare-path case, NOT silently 0.
        scope = "skills/siege/evals/fixtures/webshop"
        prefixed = [{**f, "file": f"{scope}/{f['file']}"} for f in SAMPLE_FINDINGS]
        self._stage_and_record("test-score-scope", prefixed)
        self.assertEqual(run_evals.score("test-score-scope"), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        agg = lr["aggregate"]
        self.assertEqual(agg["matched"], 4)
        self.assertEqual(agg["recall"], 4 / 6)
        self.assertEqual(agg["false_positive_rate"], 1 / 5)
        self.assertEqual(agg["severity_agreement"], 3 / 4)

    def test_score_refuses_without_collect_status(self):
        self._stage_and_record("test-score-2", SAMPLE_FINDINGS, collect=False)
        self.assertEqual(run_evals.score("test-score-2"), 1)
        self.assertEqual(
            run_evals.score("test-score-2", allow_incomplete=True), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        self.assertFalse(lr["complete"])

    def test_score_error_sentinel_scores_zero(self):
        self._stage_and_record("test-score-3", SAMPLE_FINDINGS,
                               sentinel="DISPATCH_STATUS: ERROR")
        self.assertEqual(run_evals.score("test-score-3"), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        agg = lr["aggregate"]
        self.assertEqual(agg["matched"], 0)
        self.assertEqual(agg["findings"], 0)
        self.assertEqual(agg["recall"], 0.0)
        self.assertEqual(agg["false_positive_rate"], 0.0)
        # No matched findings → severity agreement is n/a (None).
        self.assertIsNone(agg["severity_agreement"])
        self.assertTrue(lr["per_fixture"][0]["dispatch_failed"])

    def test_score_no_sentinel_parses_bare_array(self):
        self._stage_and_record("test-score-4", SAMPLE_FINDINGS, sentinel=None)
        self.assertEqual(run_evals.score("test-score-4"), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        self.assertEqual(lr["aggregate"]["matched"], 4)

    def test_score_malformed_records_degrade_to_fp(self):
        # A recorded findings array carrying (a) a non-dict element and (b) a dict whose
        # `file` is not a string must NOT crash score() (S1 regression): both degrade to
        # kept-unmatched false positives exactly like a malformed `line`, the valid hits
        # still match, and the two malformations are reflected in false_positives + the
        # per-cell malformed_findings count.
        malformed = [
            "notadict",                                  # non-dict element
            {"id": "BAD", "severity": "High", "file": 123, "line": "5",
             "title": "garbage file path", "attack": "n/a"},  # non-string file
            *SAMPLE_FINDINGS,                            # the 4 valid hits + 1 FP
        ]
        self._stage_and_record("test-score-malformed", malformed)
        rc = run_evals.score("test-score-malformed")
        self.assertEqual(rc, 0)  # no crash

        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        agg = lr["aggregate"]
        # The 4 valid vulns still match (the 2 malformed records can never match a GT
        # file, so recall is unchanged from the all-valid case).
        self.assertEqual(agg["matched"], 4)
        # 7 recorded findings, 4 matched → 3 kept FPs: the 2 malformed + the original
        # non-planted SIEGE-IP-1 false positive.
        self.assertEqual(agg["findings"], 7)
        self.assertEqual(agg["false_positives"], 3)
        pf = lr["per_fixture"][0]
        self.assertEqual(pf["malformed_findings"], 2)

    def test_score_no_manifest_fails(self):
        self.assertEqual(run_evals.score("test-score-missing"), 1)


if __name__ == "__main__":
    unittest.main()
