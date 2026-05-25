# Stack Overflow Source for Coral

Adds `stackoverflow.questions` and `stackoverflow.tags` as queryable SQL tables, powered by the [Stack Exchange API v2.3](https://api.stackexchange.com/docs). No authentication required for public data.

## Install

```bash
coral source add --file sources/stackoverflow/manifest.yaml
```

## Tables

| Table | Required filters | Purpose |
|---|---|---|
| `stackoverflow.questions` | `tagged`, `site` | Top questions for a technology tag, sorted by vote score. |
| `stackoverflow.tags` | `site` | Popular tags on a Stack Exchange site — use to discover valid tag names. |

## Usage

```sql
-- Top Python questions by vote score
SELECT title, score, answer_count, asker
FROM stackoverflow.questions
WHERE tagged = 'python'
  AND site = 'stackoverflow'
LIMIT 10
```

```sql
-- Unanswered Django questions (open issues with no accepted answer)
SELECT title, score, view_count, link
FROM stackoverflow.questions
WHERE tagged = 'django'
  AND site = 'stackoverflow'
  AND is_answered = false
LIMIT 10
```

```sql
-- High-view questions with few answers (opportunity to contribute)
SELECT title, view_count, answer_count, score, link
FROM stackoverflow.questions
WHERE tagged = 'rust'
  AND site = 'stackoverflow'
  AND answer_count < 2
LIMIT 10
```

```sql
-- Cross-site: questions on Software Engineering Stack Exchange
SELECT title, score, answer_count, asker
FROM stackoverflow.questions
WHERE tagged = 'architecture'
  AND site = 'softwareengineering'
LIMIT 10
```

```sql
-- Discover popular tags on Stack Overflow (before querying questions)
SELECT name, count
FROM stackoverflow.tags
WHERE site = 'stackoverflow'
  AND sort = 'popular'
LIMIT 20
```

```sql
-- Tags on a different Stack Exchange site
SELECT name, count
FROM stackoverflow.tags
WHERE site = 'datascience'
LIMIT 10
```

## Rate limits

| Mode | Requests/day |
|------|-------------|
| No key | 300 |
| With `STACK_EXCHANGE_KEY` | 10,000 |

To raise the limit, register at https://stackapps.com → Register Application, then pass the key as a filter:

```sql
SELECT title, score FROM stackoverflow.questions
WHERE tagged = 'python'
  AND site = 'stackoverflow'
  AND key = 'YOUR_STACK_EXCHANGE_KEY'
LIMIT 10
```

## DSL features used

This manifest demonstrates several non-trivial Coral DSL v3 patterns:

| Pattern | Where used |
|---|---|
| `join_array` | `tags` column — joins the `tags` array into a comma-separated string |
| `format_timestamp` with `input: seconds` | `created_at` — converts Stack Exchange Unix epoch to UTC timestamp |
| Nested path (`owner.display_name`) | `asker` column — accesses a nested field in the response |
| `from_filter` | `tagged`, `site`, `sort`, `order` columns — echoes query filters back as columns |
| Page-based pagination | `page` / `pagesize` — Stack Exchange uses page numbers, not cursors |

## Limitations

- Both `tagged` and `site` are **required** filters. Queries without them will fail.
- `tagged` must be an existing Stack Overflow tag (e.g. `python`, `django`, `rust`). Free-text search is not supported.
- The `site` parameter accepts any Stack Exchange network site identifier (e.g. `stackoverflow`, `softwareengineering`, `datascience`).
- The Stack Exchange API compresses responses with gzip. Coral handles decompression automatically.
- Without a `STACK_EXCHANGE_KEY`, daily quota is 300 requests shared across all apps on your IP.
- This source exposes **public questions only** — no private team content, no deleted posts, no user PII beyond display names.

## Limitations

- For `stackoverflow.tags`: only `site` is required. `sort` accepts `popular` (default), `activity`, `name`.
- Without a `STACK_EXCHANGE_KEY`, daily quota is 300 requests shared across all apps on your IP.
- The Stack Exchange API compresses responses with gzip. Coral handles decompression automatically.

## Validation

```
YAML parse:                     passed for sources/stackoverflow/manifest.yaml
Coral manifest schema:          passed (dsl_version: 3, backend: http, 2 tables)
test_queries (questions):       passed — SELECT * FROM stackoverflow.questions WHERE tagged = 'python' AND site = 'stackoverflow' LIMIT 5
test_queries (tags):            passed — SELECT name, count FROM stackoverflow.tags WHERE site = 'stackoverflow' LIMIT 5
Live API test (no key):         passed — 300 req/day public endpoint, returns items array
Live API test (with key):       passed — STACK_EXCHANGE_KEY raising limit to 10,000 req/day
Integration test (RepoSense):   passed — reposense --repo django/django so-buzz returns 10 rows in <2s
```

## Used by RepoSense

The `so-buzz` command uses this source to surface top Stack Overflow questions for the technology a GitHub repo uses:

```bash
reposense --repo django/django so-buzz      # → top 'python' SO questions (13k+ votes)
reposense --repo expressjs/express so-buzz  # → top 'javascript' SO questions
reposense --repo rust-lang/rust so-buzz     # → top 'rust' SO questions
```

Technology tag is auto-detected from `github.repo_topics` — the same mechanism as `hn-buzz` and `pulse`.
