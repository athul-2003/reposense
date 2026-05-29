# RepoSense — Hackathon Task Checklist

## Day 1 — May 25 · Environment Setup + First Live Query ✅ COMPLETE
- [x] Install Coral (`curl -fsSL https://withcoral.com/install.sh | sh`)
- [x] Verify Coral installed (`coral --version`)
- [x] Create GitHub Personal Access Token
- [x] Connect GitHub source to Coral (`coral source add --interactive github`)
- [x] Install Coral skills for Claude Code (`npx skills add withcoral/skills`)
- [x] Wire Coral to Claude Code via MCP (`claude mcp add --scope user coral -- coral mcp-stdio`)
- [x] Verify MCP connection (Claude Code lists 362 github.* tables)
- [x] Run first live query against `withcoral/coral` repo
- [x] Verify full agent loop (Claude Code → Coral MCP → GitHub API → SQL results)
- [x] Verify full agent loop (Claude Code → Coral MCP → GitHub API → SQL results)

---

## Day 2 — May 26 · Add HN + OSV Sources + All 7 Queries Tested ✅ COMPLETE
- [x] Clone Coral repo to get community source manifests (`git clone https://github.com/withcoral/coral.git coral-repo`)
- [x] Add Hacker News source (`coral source add --file coral-repo/sources/community/hn/manifest.yaml`)
- [x] Verify HN source (`coral source test hn`) — 4 tables, 2/2 tests passed
- [x] Add OSV vulnerability source (`coral source add --file coral-repo/sources/community/osv/manifest.yaml`)
- [x] Verify OSV source (`coral source test osv`) — 3 tables, 1/1 tests passed
- [x] Confirm all 3 sources active (`coral source list` → github ✓ hn ✓ osv ✓)
- [x] Test Feature 1: Daily Issue Triage (LEFT JOIN github.issues + github.pulls)
- [x] Test Feature 2: Stale PR Report (github.pulls >7 days, non-draft)
- [x] Test Feature 3: Release Note Generator (merged PRs by label)
- [x] Test Feature 4: HN Buzz Detector ★ (hn.search parallel query — JOIN on issue title returns 0 rows)
- [x] Test Feature 5: CVE / Security Scan ★ (CROSS JOIN github.issues + osv.query_by_version)
- [x] Test Feature 6: Contributor Activity Summary (UNION ALL across 3 tables)
- [x] Test Feature 7: Duplicate Issue Detector (CROSS JOIN github.issues)
- [x] Save all 7 verified queries as `.sql` files in `queries/`
- [x] Write Claude Code system prompt in `agent/prompts.py`
- [x] Write `agent/coral_runner.py` — subprocess wrapper, smoke tested live
- [x] Fix `cve_scan.sql`: remove `CAST(o.published AS DATE)` (ambiguity error)
- [x] Verify all 3 MCP tool calls return real data (github ✓ hn ✓ osv ✓)

---

## Day 3 — May 27 · Terminal UI Built (rich + click) ✅ COMPLETE
- [x] Initialise uv project (`uv init`) with rich, click, textual dependencies
- [x] `pyproject.toml` and `uv.lock` committed — all Python runs via `uv run python`
- [x] Create `ui/` folder structure (`ui/splash.py`, `ui/chat.py`, `ui/tables.py`, `ui/__init__.py`)
- [x] Write `ui/splash.py` — ASCII art logo + repo health score progress bar
- [x] Write `ui/chat.py` — `show_thinking` spinner, `show_sql`, `show_answer`, `show_error`
- [x] Write `ui/tables.py` — colour-coded table renderers (red/yellow/green)
- [x] Write `reposense.py` — main click CLI entry point with all 7 commands
- [x] Fix `coral_runner.py` — pass `--` before SQL to prevent `--comment` flag parsing
- [x] Test all 7 features end-to-end via `uv run python reposense.py <command>`
- [x] Add `run.sh` — chmod +x convenience wrapper, `./run.sh [command]`
- [x] Write `README.md` — Quick Start, commands table, 3-source setup, tech stack
- [x] Final check: all 7 commands pass via `./run.sh` — triage ✓ stale-prs ✓ contributors ✓ hn-buzz ✓ cve-scan ✓ release-notes ✓ duplicates ✓
- [ ] Write `agent/formatter.py` — rich rendering helpers (deferred to Day 4)
- [ ] Write `.env.example` (GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, GITHUB_PACKAGE)

---

## Day 3.5 — Make RepoSense a Universal CLI Tool ✅ COMPLETE

- [x] Add `--repo` flag to all 7 click commands (owner/repo format)
- [x] Add interactive repo prompt at startup in interactive mode
- [x] Parameterise all SQL queries so owner/repo are runtime inputs
- [x] Add `[project.scripts]` entry to `pyproject.toml` for pip/uv installability
- [x] Test all 7 commands with a different repo (e.g. `django/django`)
- [x] Test: `uv tool install .` and run `reposense` as a global command
- [x] Verify `withcoral/coral` still works (no regression)
- [x] Commit and push Day 3.5

> **Day 3.5 goal:** RepoSense works on ANY public GitHub repo,
> not just withcoral/coral. Same 7 features, same UI,
> owner/repo is now a runtime input not a hardcoded value.
> Demo strategy: show withcoral/coral for judges,
> then switch to facebook/react live to prove universality.

---

## Day 4 — Performance Audit + Query Fixes

### Full Query Performance Audit

After fixing the health score we audited ALL queries in the
project for the same LEFT JOIN / CROSS JOIN pagination problem.

Findings:
- triage.sql: LEFT JOIN body LIKE → all PRs fetched locally 🔴
- stale_prs.sql: full PR scan, date filter local 🟡
- release_notes.sql: full PR scan, date filter local 🟡
- cve_scan.sql: CROSS JOIN issues × CVEs 🔴
- duplicates.sql: CROSS JOIN issues × issues (N²) 🔴
- contributors.sql: UNION ALL 3 tables (no search fix) 🟡
- hn_buzz.sql: already search table function 🟢

Fix: replace all critical queries with github.search_issues()
where possible. Bound the CROSS JOIN in duplicates.sql to
LIMIT 50 each side (2500 max pairs). Add LIMIT 100 safety
to contributors.sql subqueries.

Tasks:
- [ ] Fix queries/triage.sql
- [ ] Fix queries/stale_prs.sql
- [ ] Fix queries/release_notes.sql
- [ ] Fix queries/cve_scan.sql
- [ ] Fix queries/duplicates.sql (LIMIT 50 bound)
- [x] Add LIMIT 100 to contributors.sql subqueries
- [x] Update coral_runner.py date substitutions
- [x] Test all 7 commands on withcoral/coral
- [x] Test all 7 commands on django/django
- [x] Commit

contributors.sql fix — ED-002:
- Rewrote from github.issues/github.pulls (REST-paginated, times out)
  to search_issues() with LIMIT 100 subquery cap
- Root cause: Coral applies LIMIT locally after fetching ALL pages.
  LIMIT value has no effect on number of REST API calls made.
  Even LIMIT 30 timed out on django/django — confirmed via testing.
- search_issues() + LIMIT 100 subquery = ~3-4 API pages = 3-5s any repo
- Removed github.comments CTE (tracked commit commits only, always 0)
- Result: withcoral/coral 2.9s ✅ · django/django 3.2s ✅ (was timeout ❌)
- Documented in docs/engineering-decisions.md ED-002

All engineering decisions documented in:
docs/engineering-decisions.md (linked from README)

---

## Day 4 — May 28 · Full Demo Polish + All 7 Features Tested ✅ COMPLETE

- [x] All 7 features working beautifully in the TUI on `withcoral/coral`
- [x] Repo health score — dynamic, live via github.search_issues() (4 concurrent queries, 2.5s)
- [x] SQL syntax highlighting shown before each query (`rich.syntax`)
- [x] Colour-coded rich tables rendering correctly for all 7 commands
- [x] show_command_header() + show_command_footer() on every command
- [x] parse_table_output() in coral_runner.py — Coral ASCII → list[dict]
- [x] HN Buzz — rich table with upvotes/comments/author/date, fixed 80-char widths
- [x] CVE Scan — two-phase query (github security issues + OSV CVE data)
- [x] Write `demo/demo.sh` — automated 7-feature sequence
- [x] Write `demo/demo_script.md` — 2-minute narration with exact timings
- [x] Write `demo/README.md` — recording guide, asciinema instructions
- [x] Run full demo end-to-end (`./demo/demo.sh withcoral/coral 1`) — all 7 clean ✅

End-to-end test results (PR #20):
| Repo | Command | Time | Status |
|------|---------|------|--------|
| withcoral/coral | triage | 1.4s | ✅ |
| withcoral/coral | stale-prs | 1.8s | ✅ |
| withcoral/coral | contributors | 3.0s | ✅ |
| withcoral/coral | hn-buzz | 1.6s | ✅ |
| withcoral/coral | cve-scan | 2.3s | ✅ |
| withcoral/coral | release-notes | 2.4s | ✅ |
| withcoral/coral | duplicates | 14.8s | ✅ |
| django/django | triage | 1.2s | ✅ |
| django/django | stale-prs | 1.4s | ✅ |
| django/django | contributors | 2.7s | ✅ |
| django/django | hn-buzz | 1.5s | ✅ |
| django/django | cve-scan | 2.2s | ✅ |
| django/django | release-notes | 1.7s | ✅ |
| django/django | duplicates | 26.9s | ✅ |

---

## Day 5 — May 29 · Demo Recording + README
- [ ] Record 2-min demo with asciinema (`demo/demo.cast`)
- [ ] Export screenshots for blog + Discord (`demo/screenshots/`)
- [x] Write `README.md` — SQL hero section, cross-source queries, quick start, engineering decisions link ✅
- [ ] Add demo GIF/link to README (after recording)

---

## Day 6 — May 30 · Blog Post + Bounty Submissions
- [ ] Write `docs/blog-post.md` — "How I built RepoSense with Coral"
- [ ] Publish blog post (all SQL queries, setup steps, 3-source JOIN explanation, lessons learned)
- [ ] Post in Discord `#how-i-coral` with screenshots (Captain's Log bounty)
- [ ] Post on LinkedIn/X tagging @withcoral (Tell the Tale bounty)

---

## Day 7 — May 31 · Final Submission
- [ ] GitHub repo is public with polished README
- [ ] All 7 agent features work end-to-end on a live repo
- [ ] Coral SQL queries (all 4 JOIN types) prominently shown in README
- [ ] 2-minute demo video recorded and linked
- [ ] Blog post published and URL included
- [ ] Discord `#how-i-coral` post done (bounty)
- [ ] LinkedIn/X social post done (bounty)
- [ ] Fill submission form at wemakedevs.org/hackathons/coral
- [ ] Final check of README and submission before 23:59 UTC
