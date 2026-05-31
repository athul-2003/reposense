# How I Built RepoSense: A GitHub Intelligence CLI With Coral SQL

*Posted for the Pirates of the Coral-bean Hackathon — WeMakeDevs × Coral, May 2026*

---

Every developer I know has the same problem: 300 open issues, 40 stale PRs, a security label buried somewhere in the noise — and no fast answer to *what actually needs attention right now?*

I built RepoSense to answer that question in under 10 seconds, for any public GitHub repo, with one terminal command and no dashboard.

---

## The Idea

RepoSense is a terminal intelligence layer for GitHub repos. You point it at any repo and get:

- The oldest unattended issues (triage)
- Non-draft PRs that have been waiting too long (stale-prs)
- What shipped in the last two weeks (release-notes)
- What Hacker News is saying about the project (hn-buzz)
- Known CVEs for your dependencies (cve-scan)
- Who is contributing most right now (contributors)
- Issues that might be duplicates of each other (duplicates)
- A repo health score with a live progress bar
- What the tech community is discussing alongside your open issues (pulse — cross-source SQL JOIN)
- What developers are struggling with on Stack Overflow right now (so-buzz)
- What developers are writing about this tech on Dev.to (dev-buzz)
- The full OpenSSF security posture — 18 checks, zero config (scorecard)

And if none of those match what you need, you can just type a question in plain English and the built-in AI agent (Claude, Groq, or GPT-4o) writes the SQL and runs it for you.

The whole thing runs in your terminal. No browser, no dashboard, no SaaS login.

---

## Why Coral

The data I needed — GitHub issues, PRs, Hacker News posts, OSV vulnerability records — lives in completely different APIs with completely different schemas and auth systems. The traditional approach is to write a separate HTTP client for each, normalise the responses into Python dicts, and glue them together in application code.

Coral makes all of that disappear. It exposes live APIs as SQL tables. GitHub becomes `github.search_issues()`. Hacker News becomes `hn.search`. OSV becomes `osv.query_by_version`. I write one SQL query and Coral handles auth, pagination, and response normalisation for all three.

The architecture looks like this:

```
reposense.py  →  coral sql -- "<SQL>"  →  GitHub API
                                       →  Hacker News API
                                       →  OSV API
```

There is no data warehouse. There is no ETL pipeline. Every query hits live data.

---

## The SQL Is the Product

Here is the triage query:

```sql
SELECT number, title, user_login AS author
FROM github.search_issues(
  q => 'repo:django/django is:open sort:created-asc'
)
LIMIT 15
```

That runs against `django/django` — a repo with 14,000+ open issues — and returns in 1.2 seconds. Not because I cached anything the first time. Because `search_issues()` is a Coral table function that pushes the filter to the GitHub Search API server-side. GitHub evaluates the query and returns only the matching items.

Run it a second time within 5 minutes and it returns in 0.0 seconds — served from RepoSense's disk cache, which matches Coral's own 5-minute HTTP cache window. The footer shows `⚡ cached` so you always know.

I learned this the hard way.

---

## The Hard Lessons

### REST pagination will kill you

My first version used `github.issues` — the REST-paginated table:

```sql
SELECT number, title FROM github.issues
WHERE owner = 'django' AND repo = 'django'
  AND state = 'open'
ORDER BY created_at ASC
LIMIT 15
```

On `withcoral/coral` (650 issues), this returned in 4 seconds. Fine. I deployed it and tested on `django/django`. It never came back. Coral applies `LIMIT` after fetching all pages — `LIMIT 15` on 14,000 issues means 14,000 API calls first, then cut to 15. The query hit Coral's 30-second timeout before returning a single row.

The fix: `github.search_issues()`. GitHub Search API evaluates the filter server-side. `LIMIT 15` on any size repo returns 15 items in under 2 seconds.

This became the foundational pattern for every query in RepoSense. **If you can express the filter as a GitHub Search query, always use `search_issues()`.** I documented this as [ED-001 through ED-003 in the engineering decisions log](https://github.com/athul-2003/reposense/blob/main/docs/engineering-decisions.md).

### COUNT(*) needs a cap

The repo health score runs four concurrent queries, each counting items in a category (stale issues, stale PRs, merged PRs, closed issues). My original attempt:

```sql
SELECT COUNT(*) as count FROM (
  SELECT 1 FROM github.search_issues(
    q => 'repo:django/django is:issue is:open created:<2026-05-10 comments:<2'
  )
) sub
```

Even with `search_issues()`, this paginates all matching results before `COUNT(*)` runs. On `django/django`, "stale issues older than 14 days with fewer than 2 comments" returns hundreds of items — each page is another API call.

The fix: add `LIMIT 50` inside the subquery. Coral stops fetching after 50 results. The health score formula saturates well below 50 anyway (the penalty for 50 stale issues is the same as 100). Accuracy unchanged. Query time: 2.2 seconds on any repo.

```sql
SELECT COUNT(*) as count FROM (
  SELECT 1 FROM github.search_issues(
    q => 'repo:django/django is:issue is:open created:<2026-05-10 comments:<2'
  ) LIMIT 50
) sub
```

Four of these run in parallel via `ThreadPoolExecutor`. Total health score time: ~2.5 seconds.

### CROSS JOIN needs hard bounds

Duplicate detection requires comparing every issue against every other issue — a `CROSS JOIN`. On 14,000 open issues that is 196 million pairs. It will never complete.

My solution: bound both sides to 50 items with subqueries ordered by `created_at DESC`.

```sql
SELECT a.number, a.title, b.number, b.title
FROM (
  SELECT number, title FROM github.issues
  WHERE owner = 'django' AND repo = 'django' AND state = 'open'
  ORDER BY created_at DESC LIMIT 50
) a
CROSS JOIN (
  SELECT number, title FROM github.issues
  WHERE owner = 'django' AND repo = 'django' AND state = 'open'
  ORDER BY created_at DESC LIMIT 50
) b
WHERE a.number < b.number
LIMIT 2000
```

Maximum 1,225 pairs from 50 issues. A Python post-processing step then filters for pairs with 2+ shared significant keywords (after stripping stopwords and common commit-prefix verbs like `fixed`, `added`, `updated`). The table shows the matched keywords alongside each pair — and uses color-coding: bold for 4+ shared words, yellow for 3, dim for 2.

The SQL CROSS JOIN is also used for the `pulse` command in an entirely different way — joining HN search results against open GitHub issues to show what the tech community is discussing alongside what the project still has open. This is where it gets interesting: `pulse` is a genuine cross-source SQL JOIN across two live external APIs (`github` + `hn`) in a single SQL statement.

### HN full-text search doesn't join on issue titles

My original hn-buzz design joined Hacker News search results against open issue titles:

```sql
SELECT h.title, h.points
FROM hn.search h
JOIN github.search_issues(...) i ON h.query = i.title
```

Returns zero rows. GitHub issue titles like `"feat(ui): port custom icons from monorepo"` are too specific for HN full-text search. HN posts discuss technologies and concepts, not individual issue names.

The correct design: two parallel queries. Query A searches HN for the project name. Query B fetches open GitHub issues. Claude reads both and surfaces *thematic* connections — "HN is discussing SQL-over-APIs performance, which relates to your open issues about query timeouts."

This is more accurate to how HN actually works. It's documented as [ED-005](https://github.com/athul-2003/reposense/blob/main/docs/engineering-decisions.md).

---

## The Architecture

```
reposense/
├── reposense.py          # CLI entrypoint, command routing, interactive loop
├── agent/
│   ├── claude_agent.py   # Agentic loop — Claude, Groq, or GPT-4o, with coral_query tool
│   ├── coral_runner.py   # run_query(), substitute_tokens(), disk cache
│   ├── mcp_server.py     # MCP stdio server — run_command, coral_sql, list_sources
│   └── prompts.py        # System prompt + grounding rules (no hallucination)
├── queries/              # SQL files, one per feature
│   ├── triage.sql
│   ├── stale_prs.sql
│   ├── release_notes.sql
│   ├── hn_buzz.sql
│   ├── cve_scan.sql      # Three queries: Dependabot + keyword + OSV
│   ├── contributors.sql
│   ├── duplicates.sql
│   ├── pulse.sql         # CROSS JOIN: github.search_issues × hn.search
│   ├── so_buzz.sql       # Stack Overflow top questions by vote score
│   ├── dev_buzz.sql      # Dev.to trending articles by tag
│   └── scorecard.sql     # OpenSSF Scorecard checks — sorted by score ASC
├── sources/
│   ├── stackoverflow/
│   │   ├── manifest.yaml # Custom Coral DSL v3 source — Stack Exchange API
│   │   └── README.md
│   ├── devto/
│   │   ├── manifest.yaml # Custom Coral DSL v3 source — Dev.to API
│   │   └── README.md
│   └── scorecard/
│       ├── manifest.yaml # Custom Coral DSL v3 source — OpenSSF Scorecard API
│       └── README.md
└── ui/
    ├── splash.py         # Logo, health score bar, 4 concurrent signals
    ├── chat.py           # SQL panel, spinner, error panel
    └── tables.py         # Rich table renderers — one per command
```

Every command is a `.sql` file. Adding a new feature is: write the SQL, add a command mapping. No new Python code required.

Adding a new *source* is: write a Coral DSL v3 YAML manifest and run `coral source add`. RepoSense ships a Stack Overflow source spec as an example.

The SQL files use runtime tokens that get substituted before execution:

| Token | Resolves to |
|---|---|
| `{owner}` | GitHub org or username |
| `{repo}` | Repository name |
| `{30_days_ago}` | ISO date 30 days back |
| `{14_days_ago}` | ISO date 14 days back |
| `{7_days_ago}` | ISO date 7 days back |
| `{hn_query}` | HN search term (from `HN_QUERY` env var, default: repo name) |
| `{package_name}` | Dependency to scan (from `PACKAGE_NAME` env var) |
| `{package_ecosystem}` | e.g. PyPI, npm, Go (from `PACKAGE_ECOSYSTEM` env var) |
| `{package_version}` | Version to check CVEs for (from `PACKAGE_VERSION` env var) |

---

## The Agent Mode

Running `reposense --repo owner/repo` without a command drops into interactive mode. You can type commands (`triage`, `cve-scan`) or ask questions in plain English:

```
> which contributor should I thank this week?
> are there any security issues related to authentication?
> what did we ship in the last two weeks?
```

Plain English questions go to an AI agent (Claude or GPT-4o — whichever API key you have) that has one tool: `coral_query(sql)`. The agent writes the SQL, runs it via Coral, reads the result, and answers in natural language. The SQL it generates is displayed in the terminal so you can see exactly what it ran.

The agent auto-detects which provider to use:

```python
# Priority: Claude → Groq (free) → GPT-4o
def _get_backend():
    if key := os.getenv("ANTHROPIC_API_KEY"):
        return _ClaudeBackend(key)   # uses claude-sonnet-4-6
    if key := os.getenv("GROQ_API_KEY"):
        return _GroqBackend(key)     # uses llama-3.3-70b-versatile (free)
    if key := os.getenv("OPENAI_API_KEY"):
        return _OpenAIBackend(key)   # uses gpt-4o-mini
    return None                      # shows setup instructions
```

The main loop is provider-agnostic — both backends implement the same interface (`call`, `is_final`, `get_text`, `get_tool_calls`, `append_tool_results`).

The agent can run multiple queries if needed — e.g., "show me stale PRs and who opened them" runs two separate Coral queries before composing a final answer.

---

## Writing a Custom Coral Source

`so-buzz` isn't backed by a built-in Coral source — it uses a community source manifest I wrote for Stack Overflow. The file is `sources/stackoverflow/manifest.yaml` and follows the Coral DSL v3 format.

The Stack Exchange API is zero-auth for public data: 300 requests/day with no key, 10,000/day with a free `STACK_EXCHANGE_KEY`. The manifest handles REST pagination, Unix timestamp → UTC conversion, and nested field access (`owner.display_name` for the asker's display name). Once installed, this is valid SQL:

```sql
SELECT title, score, answer_count, is_answered
FROM stackoverflow.questions
WHERE tagged = 'django' AND site = 'stackoverflow'
ORDER BY score DESC
LIMIT 10
```

This is Coral's extensibility model in practice: any JSON HTTP API can become a queryable SQL table in ~80 lines of YAML. No SDK, no custom connector, no deployment. Write the manifest, run `coral source add`, and the table is live.

I submitted both the Stack Overflow and OpenSSF Scorecard manifests as community contributions to the Coral repo. The Scorecard source uses an unusual DSL pattern — `{{filter.owner}}` and `{{filter.repo}}` injected directly into the URL path, not as query parameters — which is rare across Coral's 90+ community sources.

---

## Test Results

All 12 commands tested across 4 repos of very different sizes and characteristics: `withcoral/coral` (~650 issues), `django/django` (14,000+ issues), `expressjs/express`, and `facebook/react`.

| Command | withcoral/coral | django/django |
|---|---|---|
| triage | 1.4s ✅ | 1.2s ✅ |
| stale-prs | 1.8s ✅ | 1.4s ✅ |
| contributors | 3.0s ✅ | 2.7s ✅ |
| hn-buzz | 1.6s ✅ | 1.5s ✅ |
| cve-scan | 2.3s ✅ | 2.2s ✅ |
| release-notes | 2.4s ✅ | 1.7s ✅ |
| duplicates | 15–20s ✅ | 25–35s ✅ |
| health | 2.5s ✅ | 2.2s ✅ |
| pulse | 2.4s ✅ | 2.4s ✅ |
| so-buzz | 1.1s ✅ | 0.9s ✅ |
| dev-buzz | 1.7s ✅ | 1.7s ✅ |
| scorecard | 1.0s ✅ | 0.9s ✅ |

48/48 commands pass across all 4 repos. 11 of 12 commands complete in under 5 seconds. `duplicates` is slower by design (CROSS JOIN + similarity scan) but completes in under 90 seconds on any public repo.

---

## Running It Yourself

```bash
git clone https://github.com/athul-2003/reposense
cd reposense
bash setup.sh
```

`setup.sh` installs Coral, connects all 6 sources (GitHub, HN, OSV, Stack Overflow, Dev.to, OpenSSF Scorecard), and installs the `reposense` command globally. The only prompt is your GitHub Personal Access Token — needed once.

```bash
reposense --repo withcoral/coral triage
reposense --repo django/django health
reposense --repo expressjs/express cve-scan
reposense --repo withcoral/coral       # interactive agent mode
```

All 12 commands work without any LLM key. Agent mode (plain English questions) uses whichever key you have — Claude, Groq (free), or GPT-4o — in that priority order.

RepoSense also runs as an MCP server for Claude Desktop and other MCP clients:

```bash
# Add to Claude Desktop in one command
claude mcp add reposense -- reposense --mcp
```

Or add manually to your Claude config:

```json
{
  "mcpServers": {
    "reposense": {
      "command": "reposense",
      "args": ["--mcp"]
    }
  }
}
```

MCP tools exposed: `run_command` (all 12 commands), `coral_sql` (arbitrary SQL), `list_sources` (schema discovery).

---

## What I Learned About Coral

Coral is not a database. It's a SQL runtime that turns live APIs into queryable tables. The mental shift is: **you're not querying stored data, you're designing API call patterns**.

Every `FROM` clause is an API request. Every filter you push into a `WHERE` clause inside a `search_issues()` call is a filter you're pushing to GitHub's servers. Every `JOIN` across two tables is two sets of API calls whose results get joined in memory.

Once that clicks, the optimisation instincts are the same as database query optimisation — but the bottleneck is API call count, not disk I/O. The engineering decisions in this project are all expressions of that mental model.

The `search_issues()` table function is particularly powerful. It lets you express complex filters in GitHub Search Query Language and get server-side evaluation — something GitHub's REST API doesn't expose directly. Coral wraps it cleanly as a SQL table function.

---

## What's Next

A few things I'd add with more time:

1. **Slack source** — `coral source add --file slack/manifest.yaml` and RepoSense could show which GitHub issues are being discussed in your team's Slack channels.
2. **Linear/Jira source** — cross-reference GitHub issues against linear tickets. Is the issue tracked? Who's assigned in Linear?
3. **Weekly digest mode** — `reposense digest --repo org/repo --email me@example.com` as a scheduled cron using the same SQL queries.
4. **Shell completion** — `reposense <TAB>` to see available commands.
5. **Multi-repo mode** — monitor a portfolio of repos for an OSS program manager: `reposense --repos org/repo1,org/repo2 triage`.

All of these are purely additive — new `.sql` files, new Coral source additions, or new CLI flags. The architecture supports them without changes to the core.

RepoSense already ships a custom Stack Overflow source spec (`sources/stackoverflow/manifest.yaml`) as a worked example of writing a Coral DSL v3 manifest for a new API. Anyone can follow the same pattern to add any HTTP API as a queryable SQL table.

---

*RepoSense is open source under the MIT license.*
*Built with Coral, Claude/Groq/GPT-4o, rich, click, and uv.*
*[github.com/athul-2003/reposense](https://github.com/athul-2003/reposense)*
*Demo video: [youtu.be/7hxAJ9SiKqU](https://youtu.be/7hxAJ9SiKqU)*
