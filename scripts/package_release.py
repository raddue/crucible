#!/usr/bin/env python3
"""Build and verify Crucible's deterministic release ZIP."""
import argparse
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

VERSION_FILE = ".claude-plugin/plugin.json"
INCLUDED_DIRS = ("skills", "agents", "hooks", "scripts", "mcp-servers", ".claude-plugin")
INCLUDED_FILES = ("README.md", "LICENSE", "CHANGELOG.md", "PLATFORMS.md", "PRIVACY.md", "CLAUDE.md", "AGENTS.md")
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
ZIP_EPOCH = (2020, 1, 1, 0, 0, 0)


def version(root):
    value = json.loads((root / VERSION_FILE).read_text(encoding="utf-8"))["version"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError(f"plugin version must be strict X.Y.Z: {value!r}")
    return value


def release_notes(root, value):
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## v{re.escape(value)}(?:\s|$).*?(?=^## |\Z)", text, re.M | re.S)
    if not match:
        raise ValueError(f"CHANGELOG.md missing heading for v{value}")
    return match.group(0).rstrip()


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    result = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def validate_release(root):
    value = version(root)
    tags = subprocess.check_output(
        ["git", "-C", str(root), "tag", "--list", "v[0-9]*"], text=True
    ).splitlines()
    parsed = []
    for tag in tags:
        match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)
        if not match:
            raise ValueError(f"unsupported version tag: {tag}")
        parsed.append(tuple(map(int, match.groups())))
    current = tuple(map(int, value.split(".")))
    if parsed and current <= max(parsed):
        latest = ".".join(map(str, max(parsed)))
        raise ValueError(f"plugin version {value} must be greater than latest tag v{latest}")
    release_notes(root, value)
    return value


def files(root, ref):
    data = subprocess.check_output(["git", "-C", str(root), "archive", "--format=tar", ref])
    allowed = set(INCLUDED_FILES)
    result = []
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            rel = member.name
            if not (rel in allowed or rel.startswith(tuple(f"{d}/" for d in INCLUDED_DIRS))):
                continue
            if any(part in EXCLUDED_PARTS for part in Path(rel).parts):
                continue
            if rel == "AGENTS.md" and member.issym() and member.linkname == "CLAUDE.md":
                # ZIP install keeps the root harness entrypoint without following arbitrary links.
                result.append((rel, archive.extractfile("CLAUDE.md").read(), 0o644))
            elif member.isfile():
                result.append((rel, archive.extractfile(member).read(), 0o755 if member.mode & 0o111 else 0o644))
    return sorted(result)


def build(root, output, ref="HEAD"):
    root, output = Path(root).resolve(), Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for rel, content, permissions in files(root, ref):
            info = zipfile.ZipInfo(rel, ZIP_EPOCH)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | permissions) << 16
            archive.writestr(info, content)
    return output


def smoke_check(root):
    root = Path(root)
    manifest = json.loads((root / VERSION_FILE).read_text(encoding="utf-8"))
    skills = root / manifest.get("skills", "./skills/").removeprefix("./")
    skill_files = list(skills.glob("*/SKILL.md"))
    if not skill_files:
        raise ValueError("extracted archive has no loadable skills")
    for skill_file in skill_files:
        if not {"name", "description"} <= set(_frontmatter(skill_file)):
            raise ValueError(f"skill frontmatter invalid: {skill_file.relative_to(root)}")
    hooks = manifest.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("plugin hooks must be an object")
    for event_hooks in hooks.values():
        for registration in event_hooks:
            for hook in registration.get("hooks", []):
                command = hook.get("command", "")
                for match in re.finditer(r"(?:\$\{CLAUDE_PLUGIN_ROOT\}/|\b)(hooks/[^\s\"']+)", command):
                    hook_path = root / match.group(1)
                    if not hook_path.is_file():
                        raise ValueError(f"registered hook is missing: {match.group(1)}")
                    if subprocess.run(["bash", "-n", str(hook_path)], capture_output=True, text=True).returncode:
                        raise ValueError(f"registered hook syntax invalid: {match.group(1)}")
                    payload = '{"tool_name":"Write","tool_input":{"file_path":"/tmp/crucible-smoke-nonledger.md","content":"x"}}\n'
                    result = subprocess.run(["bash", str(hook_path)], input=payload, text=True, capture_output=True, timeout=10)
                    if result.returncode:
                        raise ValueError(f"registered hook failed smoke execution: {match.group(1)} ({result.returncode})")
    if not (root / "README.md").is_file() or not (root / "agents").is_dir():
        raise ValueError("archive missing documented install inputs")
    readme = (root / "README.md").read_text(encoding="utf-8").splitlines()
    commands = [line.strip() for line in readme if line.strip().startswith((
        "mkdir -p ~/.claude/skills", "ln -sf ~/repos/crucible/skills/",
        "mkdir -p ~/.claude/agents", "ln -sf ~/repos/crucible/agents/",
    ))]
    if len(commands) != 4:
        raise ValueError("README install commands changed; update release smoke check")
    with tempfile.TemporaryDirectory() as temp:
        home = Path(temp)
        install_root = home / "repos" / "crucible"
        install_root.parent.mkdir(parents=True)
        if root != install_root:
            subprocess.run(["cp", "-a", str(root) + "/.", str(install_root)], check=True)
        result = subprocess.run(
            ["bash", "-eu", "-c", "\n".join(commands)],
            env={**os.environ, "HOME": str(home)}, capture_output=True, text=True,
        )
        if result.returncode:
            raise ValueError(f"README symlink install failed: {result.stderr.strip()}")
        skills_dir = home / ".claude/skills"
        agents_dir = home / ".claude/agents"
        skill_links = list(skills_dir.iterdir()) if skills_dir.is_dir() else []
        agent_links = list(agents_dir.iterdir()) if agents_dir.is_dir() else []
        if not skill_links or not all(p.is_symlink() and p.is_dir() for p in skill_links) or not any((p / "SKILL.md").is_file() for p in skill_links):
            raise ValueError("README skill symlinks did not resolve extracted skills")
        if not agent_links or not all(p.is_symlink() and (p.is_file() or p.is_dir()) for p in agent_links) or not any(p.is_file() or (p.is_dir() and any(p.glob("*.md"))) for p in agent_links):
            raise ValueError("README agent symlinks did not resolve extracted agents")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ref", default="HEAD", help="Git commit or ref to package (default: HEAD)")
    parser.add_argument("--smoke", action="store_true", help="extract and smoke-check generated archive")
    parser.add_argument("--validate-release", action="store_true", help="require bumped version and matching changelog heading")
    parser.add_argument("--notes-output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    value = validate_release(root) if args.validate_release else version(root)
    if args.validate_release:
        print(value)
        return
    if args.notes_output:
        args.notes_output.write_text(release_notes(root, value) + "\n", encoding="utf-8")
    output = (args.output or root / f"dist/crucible-v{value}.zip").resolve()
    build(root, output, args.ref)
    if args.smoke:
        with tempfile.TemporaryDirectory() as temp:
            with zipfile.ZipFile(output) as archive:
                archive.extractall(temp)
            smoke_check(Path(temp))
    print(output)


if __name__ == "__main__":
    main()
