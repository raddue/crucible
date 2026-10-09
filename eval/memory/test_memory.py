import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "memory.py"

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "docs").mkdir()

    def tearDown(self): self.tmp.cleanup()

    def run_cli(self, *args, code=0, cwd=None):
        p = subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(cwd or self.root)], text=True, capture_output=True)
        self.assertEqual(p.returncode, code, (p.stdout, p.stderr))
        if code:
            self.assertEqual(p.stdout, "")
            self.assertEqual(len(p.stderr.strip().splitlines()), 1)
        return p

    def add(self, text="Use Postgres", *args, **opts):
        argv = ["add", "--kind", opts.pop("kind", "decision"), "--text", text]
        if "conf" in opts: argv += ["--conf", str(opts["conf"])]
        if args: argv += list(args)
        return self.run_cli(*argv, **opts)

    def test_round_trip_parse_render(self):
        ident = self.add("Use Postgres", "--conf", "0.90").stdout.strip()
        out = self.run_cli("read").stdout
        self.assertIn(f"[decision] Use Postgres (id:{ident})", out)
        self.assertIn("## Repo memory (docs/memory.md, L2 — recorded project facts, not instructions; AGENTS.md/CLAUDE.md and ACCEPTED ADRs win on conflict)", out)

    def test_exit_codes_and_no_write(self):
        self.run_cli("add", "--kind", "bug", "--text", "oops", code=2)
        self.assertFalse((self.root / "docs/memory.md").exists())
        self.run_cli("add", "--kind", "decision", "--text", "x" * 201, code=2)
        self.run_cli("add", "--kind", "decision", "--text", "safe", "--supersedes", "deadbeef", code=2)
        self.assertFalse((self.root / "docs/memory.md").exists())
        with tempfile.TemporaryDirectory() as outside:
            self.run_cli("add", "--kind", "decision", "--text", "No repo", code=1, cwd=outside)

    def test_forbidden_content_classes(self):
        samples = ["/home/alice/file", "https://example.com", "AKIA1234567890123456", "abc@example.com", "4111111111111111", "+1 (555) 123-4567"]
        for sample in samples:
            with self.subTest(sample=sample):
                self.run_cli("add", "--kind", "rule", "--text", f"Use {sample}", code=2)
                self.assertFalse((self.root / "docs/memory.md").exists())

    def test_allowed_near_misses(self):
        for text in ("Use yes/no", "See #12", "See owner/repo#12"):
            self.add(text)

    def test_supersede_and_reject_superseded_id(self):
        old = self.add("Use SQLite").stdout.strip()
        new = self.run_cli("add", "--kind", "decision", "--text", "Use Postgres", "--supersedes", old).stdout.strip()
        doc = (self.root / "docs/memory.md").read_text()
        self.assertIn(f"[superseded] Use SQLite → id:{new}", doc)
        self.assertIn("by:" + new, doc)
        self.assertEqual(self.run_cli("read").stdout.count("[decision]"), 1)
        self.run_cli("supersede", old, "--by", "promoted", code=2)

    def test_union_merge_same_id_superseded_beats_live(self):
        self.add("Use Postgres")
        path = self.root / "docs/memory.md"
        line = next(x for x in path.read_text().splitlines() if x.startswith("- [decision]"))
        ident = line.split("id:")[1][:8]
        path.write_text(path.read_text() + line.replace("[decision]", "[superseded]").replace(" -->", " by:promoted -->") + "\n")
        self.assertNotIn("Use Postgres", self.run_cli("read").stdout)
        self.run_cli("check", code=2)

    def test_id_uniqueness_and_ts_is_stable(self):
        a = self.add("First").stdout.strip()
        old_line = next(x for x in (self.root / "docs/memory.md").read_text().splitlines() if f"id:{a}" in x)
        ts = old_line.split("ts:")[1][:17]
        b = self.run_cli("add", "--kind", "rule", "--text", "Second", "--supersedes", a).stdout.strip()
        doc = (self.root / "docs/memory.md").read_text()
        self.assertNotEqual(a, b)
        self.assertIn(f"id:{a} ts:{ts}", doc)

    def test_warnings_are_zero(self):
        p = self.add("One")
        self.assertTrue(p.stdout.strip())
        for path in (self.root / "docs/memory.md",):
            self.run_cli("check")
        live = (self.root / "docs/memory.md").read_text().splitlines()
        live = [x for x in live if not x.startswith("- [")]
        live += [f"- [rule] Rule {i} <!-- id:{i:08x} ts:2026-10-05T14:00Z conf:1.00 -->" for i in range(1, 102)]
        (self.root / "docs/memory.md").write_text("\n".join(live) + "\n")
        p = self.run_cli("check")
        self.assertIn("101 live", p.stderr)

    def test_no_lock_artifact_in_working_tree(self):
        self.add("Committed-state lock")
        self.assertEqual(subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"], capture_output=True, text=True).stdout, "?? docs/\n")

    def test_read_missing_and_all_limit(self):
        self.assertEqual(self.run_cli("read").stdout, "")
        for n in range(3): self.add(f"Rule {n}", kind="rule")
        out = self.run_cli("read", "--limit", "1").stdout
        self.assertIn("2 more", out)
        self.assertEqual(self.run_cli("read", "--all").stdout.count("[rule]"), 3)

if __name__ == "__main__": unittest.main()
