#!/usr/bin/env bash
# build-evals: thin shell entry point for the build skill eval gate.
#
# v0.1 design: run-all is a manual k=3 workflow (see skills/build/evals/README.md).
# This script forwards to the run_evals CLI; subcommands are stage/score for now.
#
# Examples:
#   bash scripts/build-evals.sh stage --fixture b1-simple-feature
#   bash scripts/build-evals.sh score --fixture b1-simple-feature --build-output /tmp/work/...
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec python3 -m skills.build.evals.run_evals "$@"
