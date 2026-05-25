#!/bin/bash
# RepoSense — AI-powered open source repo intelligence
#
# Usage:
#   ./run.sh                          → interactive mode (prompts for repo)
#   ./run.sh --repo owner/repo        → interactive mode for specific repo
#   ./run.sh --repo owner/repo triage → run specific command
#
# Commands: triage, stale-prs, contributors, health,
#           hn-buzz, cve-scan, release-notes, duplicates,
#           pulse, so-buzz, dev-buzz
#
# Or install globally: uv tool install .
#           then run:  reposense --repo owner/repo

set -e
uv run python reposense.py "$@"
