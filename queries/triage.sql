-- Feature 1: Daily Issue Triage
-- Uses github.search_issues() for server-side filtering.
-- Fast on any repo regardless of size.
-- Surfaces the 15 oldest open items (issues + PRs) needing triage.
-- Note: omits is:issue qualifier — Coral search_issues does not support it
--       on large repos; returns issues+PRs sorted by age instead.
-- Sources: github (PAT)

SELECT
  number,
  title,
  html_url,
  state,
  user_login as author
FROM github.search_issues(
  q => 'repo:{owner}/{repo} is:open sort:created-asc'
)
LIMIT 15
