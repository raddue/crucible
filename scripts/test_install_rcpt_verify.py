#!/usr/bin/env python3
"""Exercise installer policy without requiring root; only privilege commands are shims."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().with_name("install-rcpt-verify.sh")


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        # id/stat simulate root for the test fixture, but preserve real modes and
        # symlink checks. /tmp is treated as a trusted test-only ancestor.
        shims = {
            "id": '#!/bin/sh\nprintf "0\\n"\n',
            "stat": '#!/bin/sh\nif [ "$3" = "$TEST_UNTRUSTED_OWNER" ]; then echo 1000:755; elif [ "$3" = /tmp ]; then echo 0:755; else /usr/bin/stat -c "%u:%a" "$3" | sed "s/^[0-9]*:/0:/"; fi\n',
            "install": '#!/bin/sh\nif [ "$1" = -d ]; then mkdir -p "$8" && chmod 755 "$8"; else cp "$7" "$8" && chmod 755 "$8"; fi\n',
            "chown": '#!/bin/sh\nexit 0\n',
        }
        for name, body in shims.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)
        self.target = self.base / "target"
        self.python = "/usr/bin/python3"

    def run_install(self, *, target=None, python=None, untrusted_owner=""):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                   CRUCIBLE_RCPT_INSTALL_DIR=str(target or self.target),
                   PYTHON=str(python or self.python), TEST_UNTRUSTED_OWNER=str(untrusted_owner))
        return subprocess.run(["sh", str(SCRIPT)], env=env, text=True,
                              capture_output=True)

    def test_wrapper_and_isolation(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "rcpt-verify").read_text(),
                         f'#!/bin/sh\nexec \'{Path(self.python).resolve()}\' -I \'{self.target}/rcpt_verify.py\' "$@"\n')
        self.assertEqual((self.target / "rcpt_verify.py").stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o755)

    def test_missing_default_parent_names_remedy(self):
        result = self.run_install(target="/usr/local/nonexistent/crucible")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Create it first: sudo install -d -o root -g root -m 0755", result.stderr)

    def test_override_target_discloses_consumer_docs_update(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update skills/shared/return-convention.md", result.stderr)

    def test_unsafe_target_ancestor(self):
        parent = self.base / "writable"
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
        result = self.run_install(target=parent / "target")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target ancestor must be root-owned", result.stderr)
        self.assertFalse((parent / "target").exists())
        parent.chmod(0o755)
        result = self.run_install(target=parent / "target", untrusted_owner=parent)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target ancestor must be root-owned", result.stderr)

    def test_existing_target_mode_and_symlink(self):
        self.target.mkdir(mode=0o700)
        self.target.chmod(0o700)
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target must be root-owned with mode 755", result.stderr)
        self.target.rmdir()
        self.target.symlink_to(self.base)
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target must be a real directory", result.stderr)

    def test_symlink_ancestor(self):
        parent = self.base / "link"
        parent.symlink_to(self.base)
        result = self.run_install(target=parent / "target")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target ancestor must be a real directory", result.stderr)

    def test_python_requires_trusted_ancestors_and_regular_binary(self):
        writable = self.base / "writable"
        writable.mkdir()
        writable.chmod(0o777)
        interpreter = writable / "python3"
        interpreter.write_text("#!/bin/sh\n")
        interpreter.chmod(0o755)
        result = self.run_install(python=interpreter)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python ancestor must be root-owned", result.stderr)
        self.assertFalse(self.target.exists())
        interpreter.unlink()
        interpreter.symlink_to(self.python)
        result = self.run_install(python=interpreter)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python ancestor must be root-owned", result.stderr)
        writable.chmod(0o755)
        interpreter.unlink()
        interpreter.write_text("#!/bin/sh\n")
        interpreter.chmod(0o755)
        result = self.run_install(python=interpreter, untrusted_owner=interpreter)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python must be root-owned", result.stderr)


if __name__ == "__main__":
    unittest.main()
