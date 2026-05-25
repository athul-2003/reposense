# Dev.to Source for Coral

Adds `devto.articles` and `devto.top_articles` as queryable SQL tables, powered by the [Dev.to API](https://developers.forem.com/api). No authentication required for public data.

## Install

```bash
coral source add --file sources/devto/manifest.yaml
```

## Tables

| Table | Required filter | Purpose |
|---|---|---|
| `devto.articles` | `tag` | Articles for a technology tag, sorted by newest first. |
| `devto.top_articles` | `top` | Globally top-voted articles in the last N days (no tag needed). |

## Usage

```sql
-- Top Python articles by reactions
SELECT title, reactions, comments_count, author
FROM devto.articles
WHERE tag = 'python'
LIMIT 10
```

```sql
-- Viral developer content this week — no tag needed
SELECT title, reactions, comments_count, author, tags
FROM devto.top_articles
WHERE top = 7
LIMIT 10
```

```sql
-- Top content from the last month
SELECT title, reactions, author, published_at
FROM devto.top_articles
WHERE top = 30
LIMIT 10
```

```sql
-- Rust articles with reading time
SELECT title, reading_time_minutes, reactions, author, published_at
FROM devto.articles
WHERE tag = 'rust'
LIMIT 10
```

```sql
-- Django articles with description
SELECT title, description, author, url
FROM devto.articles
WHERE tag = 'django'
LIMIT 5
```

## Rate limits

| Mode | Requests/day |
|------|-------------|
| No key | ~1,000 |
| With `api_key` filter | 10,000 |

To use with an API key, pass it as a filter (sign up at https://dev.to/settings/extensions → DEV Community API Keys):

```sql
SELECT title, reactions FROM devto.articles
WHERE tag = 'python'
  AND api_key = 'YOUR_DEV_TO_API_KEY'
LIMIT 10
```

## DSL features used

| Pattern | Where used |
|---|---|
| `rows_path: []` | Root JSON array — Dev.to returns `[{...}, ...]` directly (no wrapper object) |
| Nested path (`user.name`) | `author` column — nested object field access |
| Nested path (`user.username`) | `username` column — Dev.to handle of the author |
| `from_filter` | `tag` column (articles) and `top` column (top_articles) — echo query filters back |
| Page-based pagination | `page` / `per_page` — Dev.to uses standard page numbers |
| Two tables, different filter semantics | `articles` filters by tag; `top_articles` filters by time window |

## Limitations

- `tag` is a **required** filter. Queries without it will fail.
- `tag` must be an existing Dev.to tag (e.g. `python`, `javascript`, `rust`). Free-text search is not supported through this endpoint.
- Articles are returned newest-first. There is no sort-by-reactions option in the public `/articles` endpoint.
- Without an API key, rate limit is approximately 1,000 requests/day per IP.
- This source exposes **public articles only** — no draft posts, no private content.

## Validation

```
YAML parse:                     passed for sources/devto/manifest.yaml
Coral manifest schema:          passed (dsl_version: 3, backend: http, 2 tables)
test_queries (articles):        passed — SELECT * FROM devto.articles WHERE tag = 'python' LIMIT 5
test_queries (top_articles):    passed — SELECT title, reactions FROM devto.top_articles WHERE top = 7 LIMIT 5
Live API test (no key):         passed — root JSON array, 30 items, <2s
rows_path: []                   passed — Coral correctly handles root JSON array (no wrapper object)
Integration test (RepoSense):   passed — reposense --repo django/django dev-buzz returns 10 rows in <2s
```

## Used by RepoSense

The `dev-buzz` command uses this source to surface trending Dev.to articles for the technology a GitHub repo uses:

```bash
reposense --repo django/django dev-buzz      # → top 'python' Dev.to articles
reposense --repo expressjs/express dev-buzz  # → top 'javascript' Dev.to articles
reposense --repo rust-lang/rust dev-buzz     # → top 'rust' Dev.to articles
```

Technology tag is auto-detected from `github.repo_topics` — the same mechanism as `hn-buzz`, `so-buzz`, and `pulse`.
