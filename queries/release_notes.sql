-- Feature 3: Release Note Generator
-- Uses github.search_issues() for server-side filtering.
-- Fast on any repo regardless of size.
-- Sources: github (PAT)

SELECT
  number,
  title,
  html_url,
  user_login as author,
  state
FROM github.search_issues(
  q => 'repo:{owner}/{repo} is:pr is:merged merged:>{14_days_ago}'
)
LIMIT 50
