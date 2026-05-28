#!/usr/bin/env bash
# pre-push REMINDER (not a gate) for build skill changes.
#
# This hook is NOT enforcement. It does not block the push. It prints a
# reminder if the push includes changes to skills/build/SKILL.md or the
# build dispatch prompt templates, asking whether the build-evals fixtures
# were re-run.
#
# To install:
#   cp scripts/hooks/pre-push-build-evals.sh .git/hooks/pre-push
#   chmod +x .git/hooks/pre-push
#
# Why it's a reminder, not a gate:
#  - bypassable via --no-verify
#  - doesn't fire on direct main commits
#  - doesn't fire on PRs opened via the GitHub web UI
# Real enforcement is a v0.2 follow-up (filed under the v0.2 issue).

set -euo pipefail

remote="${1:-origin}"
url="${2:-}"

# Determine which commits are about to be pushed (read from stdin per git docs).
while read -r local_ref local_sha remote_ref remote_sha; do
    if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
        continue  # branch deletion
    fi
    if [ "$remote_sha" = "0000000000000000000000000000000000000000" ]; then
        range="$local_sha"
    else
        range="${remote_sha}..${local_sha}"
    fi
    files=$(git diff --name-only "$range" -- skills/build/SKILL.md 'skills/build/*-prompt.md' 2>/dev/null || true)
    if [ -n "$files" ]; then
        echo "[build-evals reminder] About to push changes to:"
        echo "$files" | sed 's/^/  - /'
        echo "  Reminder: did you re-run the build-evals fixtures since these changes?"
        echo "  Run: bash scripts/build-evals.sh stage --fixture <id>  (per fixture)"
        echo "  This hook is a reminder, not a gate — push proceeds."
    fi
done

exit 0
