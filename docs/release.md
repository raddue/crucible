# Releases

## Promotion

Merge reviewed `dev` into protected `main` through the normal PR path. That merged `dev` → `main` PR triggers `.github/workflows/release.yml` automatically; the manual **Actions → release → Run workflow** button (enter `release`) is the fallback for when the auto-trigger did not fire. Do not run both — a second run against the already-tagged version fails loudly (`must be greater than latest tag`).

The workflow runs `scripts/run_tests.sh`, requires `.claude-plugin/plugin.json` version to be strict `X.Y.Z` greater than newest `vX.Y.Z` tag, requires a matching `## vX.Y.Z` section in `CHANGELOG.md`, packages and smoke-checks the extracted ZIP, then creates `vX.Y.Z` GitHub Release with `crucible-vX.Y.Z.zip` and its `.sha256` sidecar.

For local package inspection:

```bash
python3 scripts/package_release.py --ref HEAD --output /tmp/crucible.zip --smoke
```

Release ZIP uses allowlist `skills/`, `agents/`, `hooks/`, `scripts/`, `mcp-servers/`, `.claude-plugin/`, and `README.md`, `LICENSE`, `CHANGELOG.md`, `PLATFORMS.md`, `PRIVACY.md`, `CLAUDE.md`, `AGENTS.md`; skill-local eval fixtures remain included. Root `AGENTS.md` is a symlink to `CLAUDE.md` in Git and becomes a regular copy in the ZIP, so Pi/Codex installation works without archive symlink support. `docs/` stays excluded: it is maintainer/reference material, while skill runtime references to `docs/` name files in the target project or illustrative examples; release installs only executable skill content. Top-level `eval/`, `.github/`, `.crucible/`, VCS metadata, untracked files, other symlinks, and Python/macOS cache files are excluded. Paths retain repo-root layout, so extraction under `~/repos/crucible` works with README symlink install commands unchanged. ZIP timestamps are fixed to 2020-01-01; entries sorted; permissions normalized to 0644/0755; stored uncompressed.

Release notes come from the matching `## vX.Y.Z` changelog section, followed by install commands and ZIP SHA-256. Unversioned/`Unreleased` sections above it are skipped, not included in release notes. Version scheme is operator-bumped strict SemVer; workflow does not infer minor vs patch.

## First release runbook

1. Merge this PR to `dev`, then merge `dev` to `main` through its required-review PR. Do not push directly to protected `main`. This merge triggers the release workflow.
2. Confirm `.claude-plugin/plugin.json` version is `1.9.0` (newer than current `v1.8.1`) and `CHANGELOG.md` has a `## v1.9.0` section. Leading unversioned sections remain outside the published release notes.
3. Let the merge-triggered **release** run complete on `main`. Use the **Run workflow** button (enter `release`) only if the auto-trigger did not fire. Wait for tests, archive smoke check, tag, and Release to succeed.
4. Verify `v1.9.0` tag points to released main commit; GitHub Release contains ZIP and `.sha256`; verify with `sha256sum -c crucible-v1.9.0.zip.sha256` after download.

The release workflow does not promote or merge branches. Main protection requires one review, and this worker cannot merge to or tag on `main`; operator must perform the first protected promotion and release.