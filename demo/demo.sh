#!/usr/bin/env bash
# RepoSense inline README demo — ~40 seconds, 4 key commands.
# Record: asciinema rec demo/reposense-demo.cast -c "bash demo/demo.sh" --cols 120 --rows 38
# Convert to GIF: agg demo/reposense-demo.cast demo/demo.gif
#                 or upload .cast to gifcast.ksaitor.com

set -e
rm -f ~/.cache/reposense/query_cache.json   # ensure first runs are live

clear
printf "\033[1;36m"
echo "  ┌─────────────────────────────────────────────────────────────────────┐"
echo "  │  RepoSense — answer any question about any GitHub repo in seconds  │"
echo "  │  12 commands · 6 live sources · powered by Coral SQL               │"
echo "  └─────────────────────────────────────────────────────────────────────┘"
printf "\033[0m"
sleep 3

# ── 1. TRIAGE ─────────────────────────────────────────────────────────────────
printf "\033[1;33m\n  ● triage  —  what needs attention first?\033[0m\n\n"
sleep 1
reposense --repo withcoral/coral triage
sleep 6

# ── 2. CVE SCAN ───────────────────────────────────────────────────────────────
printf "\033[1;33m\n  ● cve-scan  —  known CVEs for express v4.18.2 via GitHub + OSV\033[0m\n\n"
sleep 1
PACKAGE_NAME=express PACKAGE_ECOSYSTEM=npm PACKAGE_VERSION=4.18.2 \
  reposense --repo expressjs/express cve-scan
sleep 6

# ── 3. PULSE — cross-source SQL JOIN ──────────────────────────────────────────
printf "\033[1;33m\n  ● pulse  —  HN trending × open GitHub issues, one cross-source SQL JOIN\033[0m\n\n"
sleep 1
HN_QUERY=sql reposense --repo withcoral/coral pulse
sleep 6

# ── 4. CACHED RESULT ──────────────────────────────────────────────────────────
printf "\033[1;33m\n  ● triage again  —  results cached to disk  ⚡\033[0m\n\n"
sleep 1
reposense --repo withcoral/coral triage
sleep 5

# ── OUTRO ─────────────────────────────────────────────────────────────────────
echo ""
printf "\033[1;32m"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  12 commands · triage · health · stale-prs · contributors · cve-scan"
echo "  release-notes · duplicates · scorecard · pulse · so-buzz · and more"
echo ""
echo "  git clone github.com/athul-2003/reposense && bash setup.sh"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "\033[0m"
sleep 4
