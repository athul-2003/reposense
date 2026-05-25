-- Feature 2: Stale PR Report
-- Uses github.search_issues() for server-side filtering.
-- Fast on any repo regardless of size.
-- Sources: github (PAT)

SELECT
  number,
  title,
  user_login as author
FROM github.search_issues(
  q => 'repo:{owner}/{repo} is:pr is:open draft:false created:<{7_days_ago} sort:updated-desc'
)
LIMIT 30
