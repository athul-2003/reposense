# Engineering Decisions

## About This Document

This file documents every significant engineering decision
made during the build of RepoSense.

Every entry follows this structure:
- **Problem:** what we discovered during real testing
- **Options considered:** what we evaluated
- **Decision:** what we chose
- **Why:** the reasoning, including trade-offs
- **Result:** actual measured outcomes

These are real constraints found by testing on repos of
different sizes — withcoral/coral (~650 issues) and
django/django (14,000+ issues). The decisions reflect
genuine engineering trade-offs, not shortcuts.

---

## ED-001: Health Score — LEFT JOIN replaced with github.search_issues()

**Date:** May 2026
**Component:** ui/splash.py — calculate_health_score()
**Status:** Implemented ✅

### Problem
The original health score used a LEFT JOIN across
github.issues + github.pulls:

```sql
SELECT COUNT(*) FROM github.issues i
LEFT JOIN github.pulls p
  ON p.owner = '{owner}' AND p.repo = '{repo}'
  AND p.body LIKE '%#' || CAST(i.number AS VARCHAR) || '%'
WHERE i.state = 'open'
  AND i.created_at < NOW() - INTERVAL '14 days'
  AND p.number IS NULL
```

Coral fetches both sides of a JOIN via paginated REST calls
then performs the JOIN locally in DataFusion memory. On large
repos (django/django: 14,000+ issues, 14,000+ PRs) this
required paginating through 28,000+ records before returning
a single count. Result: multi-minute wait, effectively a
timeout on any repo with 10k+ issues.

This is not a Coral bug. It is a fundamental REST API
constraint — GitHub has no server-side endpoint that answers
"give me PRs whose body text mentions issue #X." The filter
cannot be pushed down to the API.

### Options considered
1. LEFT JOIN (original) — accurate but O(issues × PRs) REST calls
2. Proxy query — single table, fast, but less accurate signal
3. github.search_issues() — server-side filtering, accurate, O(1)

### Decision
Replace all 4 health score signals with github.search_issues()
Coral table function. GitHub Search API evaluates all filters
server-side before returning results. Each signal becomes one
API call regardless of repo size.

### Why this is correct, not a workaround
- github.search_issues() is a Coral table function called via
  coral sql through Coral's full DataFusion stack — 100% Coral
- Coral's own architecture docs state search table functions
  are the correct surface for provider-native aggregate queries
- GitHub's own Insights dashboard, LinearB, Swarmia, and every
  serious GitHub analytics tool uses the Search API for
  aggregates — not paginated list JOINs
- Results are exact GitHub Search API counts, not estimates

### Result
- withcoral/coral: 2.5s (maintained)
- django/django: timeout → 2.2s (fixed)
- Works on any repo regardless of size

### Implementation note
4 signals run concurrently via `ThreadPoolExecutor(max_workers=4)`.
Each SQL wraps `search_issues()` in a `LIMIT 50` subquery to cap
Coral pagination. Score formula caps kick in well below 50, so
accuracy is not affected. Without parallelism: ~12s sequential.
Without the LIMIT cap: ~16s even parallel (django stale_prs
fetches hundreds of results before COUNT returns).

---

## ED-002: Contributors — REST tables replaced with search_issues() + LIMIT 100 subquery cap

**Date:** May 2026
**Component:** queries/contributors.sql
**Status:** Implemented ✅

### Problem
The contributors query originally used UNION ALL across 3
subqueries (github.issues, github.pulls, github.comments) each
with LIMIT 100.

Coral applies LIMIT locally after full REST pagination.
LIMIT 100 on a large repo means up to 100 pages of API calls
per table before the filter resolves. On django/django
(14k+ items) this hit the 30s Coral timeout before returning
any data.

Additionally, github.comments tracks commit comments only —
not issue or PR review comments. It consistently returned 0
for all contributors, making it a dead API call that consumed
an entire paginated REST fetch for no value.

A second iteration tried LIMIT 30 on github.issues and
github.pulls. This also timed out on django/django, confirming
that Coral fetches all pages before applying LIMIT locally —
the LIMIT value does not reduce the number of API calls made.

### Options considered
1. LIMIT 100 (original) — times out on large repos
2. LIMIT 30 on github.issues/github.pulls — also times out;
   LIMIT is applied locally after full pagination, not at the API
3. github.search_issues() without LIMIT — paginates all results
   in the date window (100+ items × 3s/page = 20+s)
4. github.search_issues() with LIMIT 100 subquery — caps
   pagination at ~3-4 API pages regardless of repo size
5. Two separate search_issues() queries (is:pr + unqualified)
   merged in Python — accurate breakdown but complex, two timeouts

### Decision
Rewrite to a single search_issues() query with LIMIT 100 applied
inside a subquery to cap pagination:

```sql
SELECT user_login as actor, COUNT(*) as total
FROM (
  SELECT user_login
  FROM github.search_issues(
    q => 'repo:{owner}/{repo} created:>{30_days_ago}'
  )
  LIMIT 100
) sub
GROUP BY user_login
ORDER BY total DESC
LIMIT 10
```

The inner LIMIT 100 tells Coral to stop fetching after 100
search results (~3-4 API pages). The outer GROUP BY then runs
on those 100 rows locally.

### Accuracy trade-off
The top 10 contributors in any 30-day window will appear
frequently in any random sample of 100 recent items — the
leaderboard is accurate for its purpose. The issues/PRs
breakdown column is dropped; only a combined "Items" total is
shown. This is documented in the UI footer.

### github.comments removal
github.comments tracks commit comments only, not issue or PR
review comments. It always returned 0 for all contributors and
was consuming a full paginated REST fetch for no value.

### Result
- withcoral/coral: timeout path avoided → 2.9s ✅
- django/django: timeout → 3.2s ✅ (was failing)
- Column change: removed Issues, PRs, Comments — now shows Items (total authored)
- Footer: "Top 10 contributors · last 30 days · items authored (issues + PRs combined)"

---

## ED-003: Triage, Stale PRs, Release Notes — migrated to github.search_issues()

**Date:** May 2026
**Component:** queries/triage.sql, stale_prs.sql, release_notes.sql
**Status:** Implemented ✅

### Problem
All three queries used full table scans on github.issues or
github.pulls with date-based WHERE filters applied locally
after REST pagination. On large repos these fetched thousands
of records before filtering.

### Decision
Replace with github.search_issues() using GitHub Search query
syntax for all date and state filters. Server-side evaluation,
one API call, any repo size.

### Result
All three commands now complete in under 10 seconds on any
public GitHub repo regardless of size.

---

## ED-004: Duplicates — CROSS JOIN bounded to LIMIT 50 each side

**Date:** May 2026
**Component:** queries/duplicates.sql
**Status:** Implemented ✅

### Problem
CROSS JOIN on github.issues × github.issues produces N² pairs.
On django/django with 14k open issues this is 196 million
pairs — never completes.

No search_issues() equivalent exists for pairwise title
comparison. The CROSS JOIN approach is the only correct one
for duplicate detection.

### Decision
Bound both sides with LIMIT 50 using subqueries ordered by
created_at DESC. Maximum 50×50=2500 pairs regardless of repo
size. Covers the 50 most recently opened issues — the most
relevant window for duplicate detection (old duplicates are
already closed or merged).

### Trade-off documented in UI
Footer note: "Scanning 50 most recent open issues for
potential duplicates."

### Result
- Completes in under 30s on any repo
- Covers the most relevant (recent) issues for duplicate
  detection
- Accurate within its stated scope

---

## ED-005: HN Buzz — parallel queries instead of JOIN on issue title

**Date:** May 2026
**Component:** queries/hn_buzz.sql
**Status:** Implemented ✅

### Problem
The original design used:
JOIN hn.search h ON h.query = i.title

GitHub issue titles like "feat(ui): port custom icons from
monorepo" are too specific for HN full-text search — returns
0 rows. A literal JOIN on issue title is semantically incorrect
because HN posts discuss technologies and concepts, not
individual issue titles.

### Decision
Redesign as parallel queries:
- Query A: search HN for the project/technology name
- Query B: fetch open github.issues

Claude reads both results and surfaces thematic connections
— "HN is discussing SQL-over-APIs, which relates to your
open issues about query performance."

### Result
Cross-source capability is preserved and displayed. The
connection is thematic rather than literal, which is more
accurate to how HN actually discusses software projects.

---

## End-to-End Test Results

All 10 commands tested across 4 repos of very different sizes and characteristics:
`withcoral/coral` (~650 issues), `django/django` (14k+ issues),
`expressjs/express`, and `facebook/react`. 40/40 pass.

**withcoral/coral results:**

| Command | Time | Status |
|---------|------|--------|
| triage | 1.4s | ✅ |
| stale-prs | 1.9s | ✅ |
| contributors | 2.6s | ✅ |
| hn-buzz | 1.6s | ✅ |
| cve-scan | 3.6s | ✅ |
| release-notes | 2.2s | ✅ |
| duplicates | 15.8s | ✅ |
| health | 2.7s | ✅ |
| pulse | 2.4s | ✅ |
| so-buzz | 0.9s | ✅ |

**django/django, expressjs/express, facebook/react:**

All 10 commands pass on all 3 repos. Representative timings (django/django):
triage 1.8s, contributors 2.9s, health 2.5s, duplicates 28.3s, pulse 2.0s, so-buzz 0.9s.

Commands using `github.search_issues()` consistently return
under 3 seconds regardless of repo size (ED-001, ED-002,
ED-003). The only slow command is `duplicates` (ED-004),
which is a CROSS JOIN by design and documented as such.
`cve-scan` now runs 3 queries (Dependabot + keyword + OSV)
so takes ~4–5s total — still well within the 90s timeout.

---

## ED-006: HN Buzz — keyword search returns ecosystem posts, not tool-specific posts

**Date:** May 2026
**Component:** queries/hn_buzz.sql, agent/coral_runner.py
**Status:** Implemented ✅ — behaviour documented, limitation accepted

### Problem

`hn.search` is keyword full-text search. Searching for a repo name to find HN
posts "about" a project only works when the name is unambiguous and the project
has existing HN presence.

Discovered during testing:
- `"coral"` → 10 results — all about coral reefs, zero about the Coral MCP tool
- `"MCP server"` → 10 results — general MCP ecosystem posts (Ghidra, WhatsApp,
  Apple Health MCP), none specifically about Coral
- `"Coral MCP"` → 3 results — closest match, but very thin coverage
- `"withcoral"` → 0 results

The root cause: Coral the tool is too new to have its own HN presence.
HN full-text search cannot distinguish "Coral the MCP tool" from
"coral the ocean organism".

### Options considered

1. **Search by repo name (default)** — works for established projects (Django,
   React, Next.js). Fails for projects where the name is a common English word.

2. **Search by org name (`withcoral`)** — zero HN results. Rejected.

3. **JOIN on issue title** — already tried: `h.query = i.title` returns 0 rows.
   GitHub issue titles are too specific for HN full-text search to match.
   Documented in ED-005.

4. **Ecosystem search (`"MCP server"`)** — returns the broader technology space
   the project lives in. Relevant for context even if not tool-specific.

5. **User-configurable via HN_QUERY env var / .env** — chosen approach.

### Decision

Default `{hn_query}` to the repo name (correct for most projects). Allow
override via `HN_QUERY` env var loaded from `.env`. Ship `.env.example` with
`HN_QUERY=MCP server` so the demo repo shows the MCP ecosystem context.

The feature's intent is: *"what is HN saying about the technology space this
project lives in?"* — not *"what is HN saying about this specific tool?"*
For new/niche tools, ecosystem discussion is the best available proxy.

### Result

- `django/django` + default → HN Django posts ✅
- `facebook/react` + default → HN React posts ✅
- `withcoral/coral` + `HN_QUERY=MCP server` → HN MCP ecosystem posts ✅
- Clearly documented in `.env.example` and shown in the footer of every result

---

---

## ED-007: HN Buzz — smart query auto-detection via github.repo_topics

**Date:** May 2026
**Component:** reposense.py — _detect_hn_query()
**Status:** Implemented ✅

### Problem

ED-006 established that repos with ambiguous names (coral, express, react)
produce off-topic HN results when searching by repo name. The solution was
`HN_QUERY` env var — but this requires manual configuration by every user.
A fresh install searching for "coral" still hits coral reef posts until the
user discovers and sets the env var.

### Options considered

1. **Always require `HN_QUERY`** — makes hn-buzz useless on first run for
   any ambiguous repo name. Breaks plug-and-play goal.
2. **Hardcode a list of ambiguous names** — unmaintainable, arbitrary.
3. **Query `github.repo_topics` at runtime** — GitHub topics are human-curated
   technology tags. `django/django` has `python`, `expressjs/express` has
   `javascript`. These are exactly the right HN search terms.

### Decision

Auto-detect HN search term in priority order:
1. `HN_QUERY` env var (always wins — demo/override use case)
2. First topic from `github.repo_topics` Coral table
3. Repo name (fallback for repos with no topics)

```python
def _detect_hn_query(owner: str, repo: str) -> str:
    if env_val := os.getenv("HN_QUERY"):
        return env_val
    try:
        result = run_query("SELECT names FROM github.repo_topics WHERE ...", ...)
        topics = json.loads(rows[0].get("names", "[]"))
        if topics:
            return topics[0]
    except Exception:
        pass
    return repo
```

Graceful degradation: if the topics query fails or returns empty, falls
back to repo name. No user-visible error.

### Result

- `django/django` → first topic `python` → HN Python posts ✅
- `expressjs/express` → first topic `javascript` → HN JavaScript posts ✅
- `withcoral/coral` → no topics → falls back to repo name "coral",
  but `HN_QUERY=MCP server` in `.env` takes priority → MCP posts ✅
- Zero manual configuration needed for the common case

---

## ED-008: CVE Scan — Dependabot alerts as primary source (Section A)

**Date:** May 2026
**Component:** queries/cve_scan.sql, reposense.py, ui/tables.py
**Status:** Implemented ✅

### Problem

The original cve-scan used GitHub keyword search ("security vulnerability")
to find security-related issues. This is a keyword match — it returns issues
that *mention* those words, not issues that *are* CVEs. Issues like
"design: add SonarQube bundled source" can appear in results. The disclaimer
mitigated this but the data was inherently imprecise.

More importantly: the primary question users have is "are there known CVEs
in my actual dependencies?" — not "are there GitHub issues using the word
security?".

### Options considered

1. **Keyword search only (original)** — imprecise, tangential matches,
   not answering the real question.
2. **Dependabot alerts only** — accurate but requires `security_events`
   PAT scope; many repos don't have Dependabot enabled.
3. **Three-section approach** — Dependabot first (real CVEs), then keyword
   search as context, then OSV for user-specified dependency.

### Decision

Split cve-scan into three sections separated by `-- ==QUERY_B==` and
`-- ==QUERY_C==` delimiters:

- **Section A** (`github.repo_dependabot_alerts`): Real confirmed CVEs
  in this repo's dependencies. Severity from GitHub's advisory database
  (critical/high/medium/low). Graceful dim info note if Dependabot is
  not enabled or PAT lacks `security_events` scope — does not block B/C.
- **Section B** (`github.search_issues`): Keyword search for context
  (with explicit disclaimer in UI footer).
- **Section C** (`osv.query_by_version`): Known CVEs for a user-specified
  package/version from the OSV database.

### Result

- Dependabot section shows real CVEs when available (critical, high, medium,
  low badges with colour coding)
- When not available: dim ℹ note, sections B and C still run
- withcoral/coral: graceful info note + keyword issues + 5 OSV CVEs shown ✅
- django/django: same 3-section flow ✅
- Total time: ~4–5s (3 queries sequential)

---

## ED-009: Agent — grounding rules to prevent hallucination

**Date:** May 2026
**Component:** agent/prompts.py
**Status:** Implemented ✅

### Problem

LLM agents have training knowledge about popular repos (django, react, etc.).
Without explicit guardrails, the agent might answer questions about a repo
using training knowledge rather than live coral_query results — producing
confident-sounding answers that are stale, wrong, or about a different repo
with the same name.

Example risk: "who is the main maintainer of django/django?" — the agent
might answer from training data rather than from a coral_query on recent
contributor activity.

### Decision

Add explicit grounding rules to the system prompt:

```
## Grounding rules — no hallucination
- Your answer MUST be based ONLY on data returned by coral_query.
- Do NOT use training knowledge to fill gaps about this specific repository,
  its contributors, its maintainers, its codebase, or its history.
- If you do not have enough data from queries to answer confidently, say so
  and suggest which command or query the user could run to get that information.
- Never state something is true about the repo unless a coral_query result
  explicitly confirms it. Do not guess, infer, or extrapolate from repo names.
```

### Why this matters

The "99.99% trustworthy" goal requires that every claim about a repo
is backed by a live query result. The grounding rules make this the
agent's explicit instruction rather than an implicit expectation.

### Result

Agent now says "I don't have that data from the current query" rather
than filling gaps with training knowledge. Users can trust that any
specific claim (contributor name, issue count, PR status) came from
a live Coral query, not from LLM training data.

---

---

## ED-010: `pulse` — CROSS JOIN chosen over UNION ALL for cross-source SQL

**Date:** May 2026
**Component:** queries/pulse.sql, reposense.py — cmd_pulse()
**Status:** Implemented ✅

### Problem

RepoSense needed a command that demonstrates cross-source SQL in a single
statement — the most compelling showcase for Coral's core capability.
The natural design is a UNION ALL: combine GitHub open issues and HN trending
posts into one result set.

### Options considered

**Option A — UNION ALL:** Single query returning rows from two sources interleaved.

```sql
SELECT 'GitHub' as source, ... FROM github.search_issues(...) LIMIT 5
UNION ALL
SELECT 'HN' as source, ... FROM hn.search WHERE query = '...' LIMIT 5
```

**Option B — CROSS JOIN:** Every HN post paired with every GitHub issue.

```sql
SELECT h.title, h.points, g.number, g.title, g.user_login
FROM hn.search h
CROSS JOIN (SELECT ... FROM github.search_issues(...) LIMIT 3) g
WHERE h.query = '...' AND h.points > 20
ORDER BY h.points DESC
LIMIT 9
```

### Decision

CROSS JOIN (Option B).

### Why

Tested UNION ALL on Coral CLI. Parser returned:
`sql parser error: Expected: end of statement, found: UNION at Line: 1, Column: 190`

UNION ALL is not supported. CROSS JOIN works and is arguably a stronger
demonstration: it produces a relational JOIN between two live external APIs in
a single statement, which is exactly what Coral's architecture enables. The
output (HN trending × open GitHub issues) is a natural correlation — judges
evaluating "Best Use of Coral" see an actual JOIN, not just a stack of rows.

### Result

`pulse` runs in 2–3s and shows 9 rows (3 HN posts × 3 GitHub issues).
Each row pairs an HN trending post with an open GitHub issue, ordered by
HN upvote score. Color coded by HN score (bold yellow > 500 pts).

---

## ED-011: `duplicates` — Python similarity filter replaces raw CROSS JOIN output

**Date:** May 2026
**Component:** reposense.py — _title_similarity(), cmd_duplicates()
**Status:** Implemented ✅

### Problem

The original `duplicates` command returned all pairs from the CROSS JOIN
(up to 1225 from 50 issues), with a `LIMIT 50` cap on the SQL output.
Result: 50 random pairs shown, most unrelated. On django/django, issue #732
appeared paired with 47 other issues, all sharing only the "Fixed #XXXXX"
prefix — meaningless noise that undermined trust in the feature.

### Decision

Python post-processing: filter pairs by title word overlap using a
stopword-aware similarity function.

```python
def _title_similarity(title_a, title_b):
    sig_words = {w for w in re.split(r'[\W_]+', t.lower())
                 if len(w) > 2 and w not in _STOPWORDS}
    shared = sig_words(title_a) & sig_words(title_b)
    return len(shared), shared
```

Only pairs with ≥2 shared significant words are shown. The SQL LIMIT
was raised from 50 to 2000 to fetch all pairs for filtering.

### Why

The stopword list includes:
- Standard English function words (the, and, is, ...)
- Common commit prefix verbs in both base and past-tense forms:
  add/added, fix/fixed, update/updated, make/made, remove/removed, etc.
- Project-agnostic noise terms: source, community, implement, etc.

These removals prevent false positives from PR title conventions like
Django's "Fixed #XXXXX -- Added/Made/..." pattern, where every PR
title shares the same prefix words without being semantically related.

### Result

- withcoral/coral: 3 genuine pairs from 1225 scanned ✅
- django/django: 0 pairs (all recent issues distinct — PR-style titles) ✅
- expressjs/express: 23 pairs from 1225 — genuine Content-Type/res.set cluster ✅
- Table shows "Matched Keywords" column: shared terms visible to user ✅
- Color coded by match strength (bold yellow ≥4 shared words, yellow ≥3, dim yellow ≥2) ✅

---

## ED-012: Stack Overflow source spec — custom Coral DSL v3 manifest

**Date:** May 2026
**Component:** sources/stackoverflow/manifest.yaml, queries/so_buzz.sql
**Status:** Implemented ✅

### Problem

RepoSense needed a custom Coral source spec to qualify for the hackathon
bounty ($100) and to demonstrate that the source system is extensible.
The source should be genuinely useful as a complement to `hn-buzz`.

### Decision

Stack Overflow (Stack Exchange API) as the custom source.

### Why

Stack Overflow complements HN well in the "buzz detection" story:
- **HN** = what the community is discussing (trends, announcements, opinions)
- **SO** = what developers are actively struggling with (bugs, integration issues)

For a project like RepoSense, knowing the top SO questions about `python`
or `javascript` is actionable: these are real problems developers have right now.

Stack Exchange API advantages:
- Zero auth for 300 req/day (no friction for users to try it)
- Clean JSON, stable API, good tag-based filtering
- `sort=votes` returns the highest-voted questions of all time — authoritative signal
- Tags map directly to `github.repo_topics` auto-detection (django → 'python', etc.)

### Key DSL decisions

1. **`from_filter` echo columns:** Filters (`tagged`, `site`, `sort`, `order`)
   must have corresponding `from_filter` echo columns to be usable in SQL
   WHERE clauses. Without them, Coral reports "No column named `tagged`".

2. **`sort=votes` via filter:** Coral DSL v3 doesn't support static `value:` entries
   in query parameters (schema requires `from:` field). Sort passed through the
   filter system: SQL includes `AND sort = 'votes' AND order = 'desc'`.

3. **`input: seconds` for timestamps:** Stack Exchange uses Unix epoch seconds.
   Correct format_timestamp kind is `input: seconds` (not `unix`).

4. **HTML entity decoding:** Stack Exchange returns titles with HTML entities
   (`&quot;`, `&#39;`). Applied `html.unescape()` in `render_so_table()`.

### Result

- `coral source add --file sources/stackoverflow/manifest.yaml` installs in one command ✅
- Both test queries pass: `2 declared · 2 passed · 0 failed` ✅
- django/django `so-buzz`: shows Python questions with 7000–13000+ votes ✅
- expressjs/express `so-buzz`: shows JavaScript questions 6000–12000+ votes ✅
- Graceful empty state when tag has no SO questions (e.g. 'coral') ✅

---

## ED-013: CVE Scan Package Config — Auto-Detection (Future Enhancement)

**Date:** May 2026
**Component:** queries/cve_scan.sql (Query C), agent/coral_runner.py
**Status:** Documented — not yet implemented

### Problem

`cve-scan` Query C looks up CVEs for a specific package via the OSV database.
The package is configured via three env vars: `PACKAGE_NAME`, `PACKAGE_ECOSYSTEM`,
`PACKAGE_VERSION`. Their fallback defaults are `requests / PyPI / 2.25.0` — a
Python HTTP library that is irrelevant to most repos.

This means:
- Users who don't set these vars get CVE results for `requests`, not their actual
  dependencies — silently wrong output
- The `.env.example` originally showed these un-commented, making them look mandatory
- Users who scan a JavaScript repo see Python CVE data unless they manually edit `.env`

### Current fix (implemented)

1. **Commented out** the defaults in `.env.example` with clear documentation of what
   ecosystem values are valid and example values per stack (Node, Go, Ruby)
2. The command still runs Queries A (Dependabot) and B (keyword search) even without
   PACKAGE_NAME set — so CVE data is not zero, just OSV lookup is skipped
3. `coral_runner.py` retains code-level fallbacks so the query doesn't crash if env
   vars are absent — it just returns CVEs for `requests` as an illustrative example

### Future enhancement — auto-detection

**Goal:** Detect the primary dependency ecosystem and a representative package
automatically from the repo's manifest file, without requiring any `.env` config.

**Detection logic (proposed):**

| File present | Ecosystem | Read from |
|---|---|---|
| `requirements.txt` or `pyproject.toml` | PyPI | First non-comment package, strip version specifier |
| `package.json` | npm | First dependency in `dependencies{}` |
| `go.mod` | Go | First `require` entry |
| `Gemfile` | RubyGems | First `gem` line |
| `pom.xml` | Maven | First `<artifactId>` under `<dependencies>` |
| `Cargo.toml` | crates.io | First `[dependencies]` entry |

**Implementation approach:**

1. **Fetch manifest file via GitHub API** (not local clone — RepoSense works on any public repo)
   ```sql
   -- Option A: github.repo_contents table if Coral exposes it
   SELECT content FROM github.repo_contents
   WHERE owner='{owner}' AND repo='{repo}' AND path='requirements.txt'
   ```
   Or use a pre-run step that calls the GitHub raw content API before executing the CVE query.

2. **Parse the manifest** — Python regex per ecosystem format, extract package name and version
   (exact version may not always be pinned; can omit version and use OSV's "any version" query)

3. **Fall back to env vars** if auto-detection fails or the manifest is absent

**Why not implemented now:**
- Reading arbitrary file content from a remote repo requires either a new Coral table
  (`github.repo_contents`) or a direct GitHub API call outside Coral — adding a non-SQL
  code path would break the "everything is a SQL query" architecture
- Version parsing across 6+ manifest formats is non-trivial
- Time constraint: May 31 hackathon deadline

**Priority:** Medium — implement after the hackathon as a post-submission improvement.

---

*This document is updated as new engineering decisions are made.
For questions, see the blog post in docs/blog-post.md.*
