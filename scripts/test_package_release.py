#!/usr/bin/env python3
"""Contract checks for the deterministic release archive."""
import json
import tempfile
import unittest
import zipfile
import subprocess
from pathlib import Path

import package_release


class PackageReleaseTest(unittest.TestCase):
    def fixture(self, root):
        (root / "skills" / "demo").mkdir(parents=True)
        (root / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\ndescription: Demo skill.\n---\n", encoding="utf-8"
        )
        (root / "agents").mkdir()
        (root / "agents" / "demo.md").write_text("# Demo agent\n", encoding="utf-8")
        (root / "hooks").mkdir()
        (root / "hooks" / "check.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (root / "hooks" / "check.sh").chmod(0o755)
        (root / "scripts").mkdir()
        (root / "mcp-servers").mkdir()
        (root / ".claude-plugin").mkdir()
        (root / "CHANGELOG.md").write_text("## v1.2.3 - Demo release\n\nChanges.\n", encoding="utf-8")
        (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "demo",
            "version": "1.2.3",
            "skills": "./skills/",
            "hooks": {"PreToolUse": [{"hooks": [{
                "type": "command",
                "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/check.sh\"",
            }]}]},
        }), encoding="utf-8")
        (root / "README.md").write_text(
            "```bash\nmkdir -p ~/.claude/skills\nln -sf ~/repos/crucible/skills/* ~/.claude/skills/\nmkdir -p ~/.claude/agents\nln -sf ~/repos/crucible/agents/* ~/.claude/agents/\n```\n",
            encoding="utf-8",
        )
        for name in ("LICENSE", "PLATFORMS.md", "PRIVACY.md", "CLAUDE.md"):
            (root / name).write_text(name, encoding="utf-8")

    def init_git(self, root):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        subprocess.run(["git", "-C", str(root), "tag", "v1.2.2"], check=True)

    def test_release_validation_requires_newer_tag_and_changelog_heading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            self.init_git(root)
            self.assertEqual(package_release.validate_release(root), "1.2.3")
            manifest = root / ".claude-plugin" / "plugin.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["version"] = "1.2.2"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be greater than latest tag"):
                package_release.validate_release(root)

    def test_build_is_byte_identical_and_normalizes_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            self.fixture(root)
            self.init_git(root)
            file = root / "skills" / "demo" / "SKILL.md"
            file.touch()
            with tempfile.TemporaryDirectory() as outputs:
                first, second = Path(outputs) / "one.zip", Path(outputs) / "two.zip"
                package_release.build(root, first, "HEAD")
                package_release.build(root, second, "HEAD")
                self.assertEqual(first.read_bytes(), second.read_bytes())
                with zipfile.ZipFile(first) as archive:
                    info = archive.getinfo("skills/demo/SKILL.md")
                    self.assertEqual(info.date_time, package_release.ZIP_EPOCH)
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o644)
                    self.assertEqual((archive.getinfo("hooks/check.sh").external_attr >> 16) & 0o777, 0o755)
                    self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                    self.assertNotIn("docs/", "\n".join(archive.namelist()))

    def test_build_smoke_checks_extracted_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            self.fixture(root)
            self.init_git(root)
            output = Path(temp) / "release.zip"
            package_release.build(root, output, "HEAD")
            with tempfile.TemporaryDirectory() as extracted:
                with zipfile.ZipFile(output) as archive:
                    archive.extractall(extracted)
                package_release.smoke_check(Path(extracted))

    def test_smoke_check_rejects_missing_registered_hook(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            (root / "hooks" / "check.sh").unlink()
            with self.assertRaisesRegex(ValueError, "registered hook is missing"):
                package_release.smoke_check(root)


if __name__ == "__main__":
    unittest.main()
